from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from multi_agent_tcp import (
    body_to_agent_message,
    AgentNode,
    GuLiCodeTopAgentProfile,
    GraphDefinition,
    GraphEdge,
    GraphRuntime,
    GraphRuntimeControlPlane,
    GraphRuntimeRPCServer,
    graph_definition_from_dict,
    load_top_agent_profile,
    scoped_organization_view,
    TopAgentStartPlan,
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


def test_top_agent_default_rules_include_utterance_contract() -> None:
    profile = GuLiCodeTopAgentProfile()

    assert "utterances" in profile.allowed_run_permissions
    assert "utterance records" in profile.rule_text()
    assert "Utterance records" in profile.skill_text()


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
        assert ctx["downstream_agents"] == ["coder"]
        assert ctx["organization"]["scope"] == "agent"
        assert ctx["organization"]["agent"]["node_id"] == "planner"
        assert "tools" not in ctx
        assert "rules" not in ctx
        queued_message = body_to_agent_message(queued_body)
        assert queued_message.prompt == "Plan implementation."
        assert queued_message.context is not None
        queued_context = json.loads(queued_message.context)
        assert queued_context["framework_context"]["agent_node_id"] == "planner"
        assert (
            queued_context["framework_context"]["message_envelope"]["outgoing_batch_id"]
            == ctx["message_envelope"]["outgoing_batch_id"]
        )
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
        with pytest.raises(KeyError, match="unknown outgoing batch"):
            control.handle_request(
                {
                    "command": "agent.dispatch",
                    "args": {
                        "source_node_id": "coder",
                        "target_node_id": "reviewer",
                        "body": {"prompt": "review this"},
                        "batch_id": "missing-batch",
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
        with pytest.raises(ValueError, match="belongs to source"):
            control.handle_request(
                {
                    "command": "agent.dispatch",
                    "args": {
                        "source_node_id": "planner",
                        "target_node_id": "reviewer",
                        "body": {"prompt": "wrong source"},
                        "batch_id": coder_batch_id,
                    },
                }
            )
        with pytest.raises(ValueError, match="not in current required_outgoing_targets"):
            control.handle_request(
                {
                    "command": "agent.dispatch",
                    "args": {
                        "source_node_id": "coder",
                        "target_node_id": "planner",
                        "body": {"prompt": "wrong target"},
                        "batch_id": coder_batch_id,
                    },
                }
            )
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
        assert reviewer_body["context"]["framework_context"]["downstream_agents"] == []
        reviewer_message = body_to_agent_message(reviewer_body)
        assert reviewer_message.prompt == "review this"
        assert reviewer_message.context is not None
        reviewer_context = json.loads(reviewer_message.context)
        assert reviewer_context["framework_context"]["agent_node_id"] == "reviewer"
        assert (
            reviewer_context["framework_context"]["message_envelope"]["outgoing_batch_id"]
            is None
        )

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


def test_control_plane_ring_context_uses_dynamic_reachability() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "e": AgentNode(node_id="e"),
            "a": AgentNode(node_id="a"),
            "b": AgentNode(node_id="b"),
            "c": AgentNode(node_id="c"),
            "d": AgentNode(node_id="d"),
            "external-b": AgentNode(node_id="external-b"),
            "external-c": AgentNode(node_id="external-c"),
        },
        edges=[
            GraphEdge("e", "a", edge_type="exec"),
            GraphEdge("a", "b", edge_type="exec"),
            GraphEdge("b", "c", edge_type="exec"),
            GraphEdge("c", "d", edge_type="exec"),
            GraphEdge("d", "e", edge_type="exec"),
            GraphEdge("b", "external-b", edge_type="exec"),
            GraphEdge("c", "external-c", edge_type="exec"),
        ],
    )
    runtime = GraphRuntime(_FakeCluster())
    plan = graph.plan_ring_session(["e", "a", "b", "c", "d"], start_node_id="e", session_id="ring-ctx")
    runtime.register_ring_session(plan)
    control = GraphRuntimeControlPlane(runtime, graph)

    b_context = control.handle_request(
        {
            "command": "agent.context",
            "args": {"source_node_id": "b", "ring_session_id": "ring-ctx"},
        }
    )["context"]
    c_context = control.handle_request(
        {
            "command": "agent.context",
            "args": {"source_node_id": "c", "ring_session_id": "ring-ctx"},
        }
    )["context"]
    d_context = control.handle_request(
        {
            "command": "agent.context",
            "args": {
                "source_node_id": "d",
                "ring_session_id": "ring-ctx",
                "ring_phase": "final",
            },
        }
    )["context"]

    assert b_context["downstream_agents"] == ["c", "external-b"]
    assert c_context["downstream_agents"] == ["d"]
    assert d_context["downstream_agents"] == ["external-c"]
    assert c_context["ring_session"]["auditor_node_id"] == "d"


def test_control_plane_registers_ring_session_from_entries() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "a": AgentNode(node_id="a"),
            "b": AgentNode(node_id="b"),
            "c": AgentNode(node_id="c"),
            "d": AgentNode(node_id="d"),
        },
        edges=[
            GraphEdge("a", "b", edge_type="exec"),
            GraphEdge("b", "c", edge_type="exec"),
            GraphEdge("c", "d", edge_type="exec"),
            GraphEdge("d", "a", edge_type="exec"),
        ],
    )
    runtime = GraphRuntime(_FakeCluster())
    control = GraphRuntimeControlPlane(runtime, graph)

    registered = control.handle_request(
        {
            "command": "ring.register",
            "args": {
                "cycle_node_ids": ["a", "b", "c", "d"],
                "start_node_id": "a",
                "session_id": "ring-control",
                "entry_messages": [
                    {"target_node_id": "c", "body": {"prompt": "later"}},
                    {"target_node_id": "b", "body": {"prompt": "earlier"}},
                ],
            },
        }
    )

    assert registered["ok"] is True
    assert registered["ring_session"]["plan"]["start_node_id"] == "b"
    assert registered["ring_session"]["entry_messages"]["c"][0]["body"] == {"prompt": "later"}
    assert runtime.ring_sessions["ring-control"].plan.auditor_node_id == "a"


def test_control_plane_ring_final_dispatch_is_idempotent() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "e": AgentNode(node_id="e"),
            "a": AgentNode(node_id="a"),
            "b": AgentNode(node_id="b"),
            "c": AgentNode(node_id="c"),
            "d": AgentNode(node_id="d"),
            "external-c": AgentNode(node_id="external-c"),
        },
        edges=[
            GraphEdge("e", "a", edge_type="exec"),
            GraphEdge("a", "b", edge_type="exec"),
            GraphEdge("b", "c", edge_type="exec"),
            GraphEdge("c", "d", edge_type="exec"),
            GraphEdge("d", "e", edge_type="exec"),
            GraphEdge("c", "external-c", edge_type="exec"),
        ],
    )
    runtime = GraphRuntime(_FakeCluster())
    plan = graph.plan_ring_session(["e", "a", "b", "c", "d"], start_node_id="e", session_id="ring-final")
    runtime.register_ring_session(plan)
    control = GraphRuntimeControlPlane(runtime, graph)

    batch = control.handle_request(
        {
            "command": "message.create_batch",
            "args": {
                "source_node_id": "d",
                "ring_session_id": "ring-final",
                "ring_phase": "final",
                "is_ring_final_output": True,
            },
        }
    )
    dispatched = control.handle_request(
        {
            "command": "agent.dispatch",
            "args": {
                "source_node_id": "d",
                "target_node_id": "external-c",
                "batch_id": batch["batch"]["batch_id"],
                "body": {"prompt": "final"},
                "ring_session_id": "ring-final",
                "ring_phase": "final",
                "is_ring_final_output": True,
            },
        }
    )

    assert dispatched["ok"] is True
    assert runtime.ring_sessions["ring-final"].final_output_dispatched is True
    with pytest.raises(RuntimeError, match="already dispatched"):
        control.handle_request(
            {
                "command": "message.create_batch",
                "args": {
                    "source_node_id": "d",
                    "ring_session_id": "ring-final",
                    "ring_phase": "final",
                    "is_ring_final_output": True,
                },
            }
        )


def test_complex_blueprint_fixture_compiles_validates_and_starts(tmp_path: Path) -> None:
    fixture_path = Path("docs/blueprints/complex_test_blueprint.json")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    graph = graph_definition_from_dict(fixture["graph"])
    graph.validate_runnable()
    profile = GuLiCodeTopAgentProfile()
    start_plan = TopAgentStartPlan.from_dict(fixture["top_agent_start_plan"])
    validation = profile.validate_start_plan(graph, start_plan)

    assert validation.ok is True
    organization = graph.agent_organization_view()
    assert organization["agent_connections"]["requirements"] == [
        "risk_scan",
        "architecture",
        "test_planner",
    ]
    assert organization["agent_connections"]["architecture"] == [
        "backend_impl",
        "frontend_impl",
    ]
    assert organization["agent_connections"]["test_planner"] == [
        "unit_tests",
        "e2e_tests",
    ]

    journal_path = tmp_path / "shared" / "logs" / "message_journal.jsonl"
    runtime = GraphRuntime(_FakeCluster(), message_journal_path=journal_path)
    control = GraphRuntimeControlPlane(runtime, graph, top_agent=profile)
    started = control.handle_request(
        {
            "command": "run.start",
            "args": {"plan": start_plan.to_dict()},
        }
    )

    assert started["ok"] is True
    assert started["queued_messages"][0]["node_id"] == "requirements"
    assert journal_path.is_file()
    records = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert records[0]["record_type"] == "framework.message.queued"
    assert records[0]["receiver"]["node_id"] == "requirements"
    queued_body = runtime.status_snapshot()["queues"]["by_agent"]["requirements"][0]["body"]
    envelope = queued_body["context"]["framework_context"]["message_envelope"]
    assert envelope["required_outgoing_targets"] == [
        "risk_scan",
        "architecture",
        "test_planner",
    ]
    assert runtime.status_snapshot()["run"]["message_journal"]["record_count"] == 1


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


def test_top_agent_utterances_interface_is_top_agent_only() -> None:
    graph = graph_definition_from_dict(_graph_dict())
    runtime = GraphRuntime(_FakeCluster())
    control = GraphRuntimeControlPlane(runtime, graph)

    receipt = runtime._record_agent_utterance(
        node_id="coder",
        agent_id="worker-coder",
        reply={"type": "message", "body": {"codex": {"final_text": "done via API"}}},
        message_id="msg-1",
        task_id="task-1",
    ).to_dict()

    out = control.handle_request(
        {
            "command": "top_agent.utterances",
            "args": {"task_id": "task-1", "agent_id": "worker-coder"},
        }
    )
    assert out["ok"] is True
    assert out["utterances"] == [receipt]
    assert out["filters"]["task_id"] == "task-1"

    agent_ctx = control.handle_request(
        {
            "command": "agent.context",
            "args": {"source_node_id": "coder"},
        }
    )
    assert "top_agent.utterances" not in json.dumps(agent_ctx)
    assert "utterance" not in json.dumps(agent_ctx).lower()

    no_access = GraphRuntimeControlPlane(
        runtime,
        graph,
        top_agent=GuLiCodeTopAgentProfile(allowed_run_permissions=["ask", "status"]),
    )
    with pytest.raises(PermissionError):
        no_access.handle_request({"command": "top_agent.utterances", "args": {}})
