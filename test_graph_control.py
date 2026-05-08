from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from multi_agent_tcp import (
    GuLiCodeTopAgentProfile,
    GraphRuntime,
    GraphRuntimeControlPlane,
    GraphRuntimeRPCServer,
    graph_definition_from_dict,
    load_top_agent_profile,
    scoped_organization_view,
)
from multi_agent_tcp.__main__ import main


class _FakeCluster:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.sent: list[tuple[str, Any, float]] = []

    async def ensure_worker(self, worker: Any) -> None:
        self.started.append(worker.agent_id)

    async def run_single(
        self,
        worker_id: str,
        body: Any,
        *,
        timeout_sec: float = 600.0,
        _skip_skill_inject: bool = False,
    ) -> dict[str, Any]:
        self.sent.append((worker_id, body, timeout_sec))
        return {"type": "message", "from": worker_id, "body": {"ok": True}}


def _graph_dict() -> dict[str, Any]:
    return {
        "agent_nodes": {
            "planner": {"agent_id": "worker-planner", "cli_kind": "codex"},
            "coder": {"write_scope": ["src/**"]},
            "reviewer": {},
        },
        "edges": [
            {"from": "planner", "to": "coder", "edge_type": "exec"},
            {"from": "coder", "to": "reviewer", "edge_type": "exec"},
        ],
    }


def _plan_dict() -> dict[str, Any]:
    return {
        "user_goal": "Implement and review.",
        "agent_descriptions": {
            "planner": "Plans the work.",
            "coder": "Implements code.",
            "reviewer": "Reviews results.",
        },
        "start_nodes": ["planner"],
        "tasks": {
            "planner": {
                "goal": "Plan implementation.",
                "expected_output": "Messages for downstream agents.",
                "acceptance": "Plan references files and risks.",
            }
        },
    }


def test_graph_definition_json_and_scoped_organization_view() -> None:
    graph = graph_definition_from_dict(_graph_dict())

    full = scoped_organization_view(graph)
    scoped = scoped_organization_view(graph, agent_id="coder")

    assert full["agent_connections"] == {
        "planner": ["coder"],
        "coder": ["reviewer"],
        "reviewer": [],
    }
    assert scoped["scope"] == "agent"
    assert scoped["agent"]["node_id"] == "coder"
    assert scoped["agent"]["upstream_agents"] == ["planner"]
    assert scoped["agent"]["downstream_agents"] == ["reviewer"]
    assert scoped["graph"]["agent_nodes"] == ["coder"]


def test_organization_and_validate_start_cli(tmp_path: Path, capsys: Any) -> None:
    graph_path = tmp_path / "graph.json"
    plan_path = tmp_path / "plan.json"
    profile_path = tmp_path / "top_agent_profile.json"
    graph_path.write_text(json.dumps(_graph_dict()), encoding="utf-8")
    plan_path.write_text(json.dumps(_plan_dict()), encoding="utf-8")
    profile_path.write_text(
        json.dumps(
            {
                "agent_id": "gu",
                "display_name": "GuLiCode Custom",
                "allowed_run_permissions": ["ask", "status"],
                "rule": "custom rule",
                "skill": "custom skill",
            }
        ),
        encoding="utf-8",
    )

    main(["organization", "--graph", str(graph_path), "--agent-id", "coder"])
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["organization"]["agent"]["node_id"] == "coder"

    main(["runtime", "validate-start", "--graph", str(graph_path), "--plan", str(plan_path)])
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["normalized_plan"]["start_nodes"] == ["planner"]

    main(
        [
            "runtime",
            "validate-start",
            "--graph",
            str(graph_path),
            "--plan",
            str(plan_path),
            "--top-agent-profile",
            str(profile_path),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert "not allowed to start runs" in out["errors"][0]

    main(
        [
            "runtime",
            "top-agent-context",
            "--graph",
            str(graph_path),
            "--top-agent-profile",
            str(profile_path),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["context"]["top_agent"]["agent_id"] == "gu"
    assert out["context"]["top_agent"]["rule"] == "custom rule"


def test_top_agent_profile_json_round_trip(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    profile = GuLiCodeTopAgentProfile(
        agent_id="lead",
        display_name="Lead Agent",
        cli_kind="codex",
        model="gpt-5.4-mini",
        cwd=tmp_path,
        timeout_sec=123.0,
        external=True,
        allowed_run_permissions=["ask", "start"],
        rule="rule text",
        skill="skill text",
    )

    profile.save(profile_path)
    loaded = load_top_agent_profile(profile_path)

    assert loaded.agent_id == "lead"
    assert loaded.allowed_run_permissions == ["ask", "start"]
    assert loaded.rule_text() == "rule text"
    assert loaded.skill_text() == "skill text"
    assert loaded.to_agent_node().agent_id == "lead"
    assert loaded.to_agent_node().model == "gpt-5.4-mini"
    assert loaded.to_agent_node().external is True


def test_graph_runtime_control_plane_and_rpc_round_trip() -> None:
    graph = graph_definition_from_dict(_graph_dict())
    runtime = GraphRuntime(_FakeCluster())
    control = GraphRuntimeControlPlane(runtime, graph)
    server = GraphRuntimeRPCServer(control, token="secret")
    server.start()
    try:
        org = control.handle_request(
            {
                "command": "organization.read",
                "args": {"agent_id": "coder"},
            }
        )
        assert org["organization"]["agent"]["node_id"] == "coder"

        started = control.handle_request(
            {
                "command": "run.start",
                "args": {"plan": _plan_dict()},
            }
        )
        assert started["ok"] is True
        assert started["queued_messages"][0]["node_id"] == "planner"
        snapshot = runtime.status_snapshot()
        assert snapshot["agents"]["planner"]["state"] == "queued"
        queued_body = snapshot["queues"]["by_agent"]["planner"][0]["body"]
        ctx = queued_body["context"]["framework_context"]
        assert ctx["message_envelope"]["required_outgoing_targets"] == ["coder"]
        assert ctx["tools"]["agent.dispatch"]["required_args"] == [
            "source_node_id",
            "target_node_id",
            "batch_id",
            "body",
        ]
        assert snapshot["run"]["manifest"]["start"]["start_plan"]["user_goal"] == "Implement and review."
        assert started["start_manifest"]["organization"]["agents"]["planner"]["node_id"] == "planner"

        batch = control.handle_request(
            {
                "command": "message.create_batch",
                "args": {
                    "source_node_id": "planner",
                    "required_target_node_ids": ["coder"],
                    "batch_id": "batch-1",
                },
            }
        )
        assert batch["batch"]["remaining_targets"] == ["coder"]
        staged = control.handle_request(
            {
                "command": "message.stage",
                "args": {
                    "batch_id": "batch-1",
                    "target_node_id": "coder",
                    "body": {"prompt": "please implement"},
                },
            }
        )
        assert staged["ready_to_dispatch"] is True

        with pytest.raises(ValueError, match="requires the current outgoing batch_id"):
            control.handle_request(
                {
                    "command": "agent.dispatch",
                    "args": {
                        "source_node_id": "coder",
                        "target_node_id": "reviewer",
                        "body": {"prompt": "review this"},
                    },
                }
            )

        coder_batch = control.handle_request(
            {
                "command": "message.create_batch",
                "args": {
                    "source_node_id": "coder",
                    "required_target_node_ids": ["reviewer"],
                    "batch_id": "dispatch-1",
                },
            }
        )
        coder_batch_id = coder_batch["batch"]["batch_id"]
        dispatched = control.handle_request(
            {
                "command": "agent.dispatch",
                "args": {
                    "source_node_id": "coder",
                    "target_node_id": "reviewer",
                    "body": {"prompt": "review this"},
                    "batch_id": coder_batch_id,
                },
            }
        )
        assert dispatched["ok"] is True
        assert dispatched["dispatch"]["ready_to_dispatch"] is True
        reviewer_body = runtime.status_snapshot()["queues"]["by_agent"]["reviewer"][0]["body"]
        assert reviewer_body["prompt"] == "review this"
        assert reviewer_body["context"]["framework_context"]["agent_node_id"] == "reviewer"
        assert reviewer_body["context"]["framework_context"]["message_envelope"]["required_outgoing_targets"] == []

        agent_context = control.handle_request(
            {
                "command": "agent.context",
                "args": {
                    "source_node_id": "coder",
                    "batch_id": coder_batch_id,
                },
            }
        )
        assert agent_context["context"]["message_envelope"]["outgoing_batch_id"] == coder_batch_id

        join = control.handle_request(
            {
                "command": "join.create",
                "args": {
                    "join_id": "join-1",
                    "target_node_id": "reviewer",
                    "required_source_node_ids": ["coder"],
                },
            }
        )
        assert join["join"]["status"] == "waiting"
        contributed = control.handle_request(
            {
                "command": "join.contribute",
                "args": {
                    "join_id": "join-1",
                    "source_node_id": "coder",
                    "accepted_changesets": [{"changeset_id": "cs-1"}],
                },
            }
        )
        assert contributed["ready"] is True

        status = control.handle_request({"command": "run.status", "args": {}})
        assert status["status"]["joins"]["join-1"]["status"] == "ready"
        explanation = control.handle_request(
            {"command": "top_agent.explain_status", "args": {"recent_events_limit": 5}}
        )
        assert "summary" in explanation["explanation"]
        assert explanation["explanation"]["recent_events"]

        ended = control.handle_request(
            {"command": "run.end", "args": {"action": "complete"}}
        )
        assert ended["final_status"] == "partial_success"
    finally:
        server.close()


def test_top_agent_session_and_ask_use_long_lived_worker() -> None:
    graph = graph_definition_from_dict(_graph_dict())
    runtime = GraphRuntime(_FakeCluster())
    profile = GuLiCodeTopAgentProfile(agent_id="gu", external=False)
    control = GraphRuntimeControlPlane(runtime, graph, top_agent=profile)

    started = control.handle_request({"command": "top_agent.start_session", "args": {}})
    assert started["ok"] is True
    assert started["session"]["agent_id"] == "gu"

    asked = control.handle_request(
        {
            "command": "top_agent.ask",
            "args": {"prompt": "What is happening?", "recent_events_limit": 3},
        }
    )
    assert asked["ok"] is True
    assert runtime.cluster.started == ["gu"]
    assert runtime.cluster.sent[0][0] == "gu"
    assert runtime.cluster.sent[0][1]["context"]["top_agent"]["agent_id"] == "gu"
    assert "status_explanation" in runtime.cluster.sent[0][1]["context"]
