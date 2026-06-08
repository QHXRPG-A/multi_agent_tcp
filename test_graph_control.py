from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from multi_agent_tcp import (
    body_to_agent_message,
    AgentNode,
    CommonNode,
    GuLiCodeTopAgentProfile,
    GraphDefinition,
    GraphEdge,
    GraphRuntime,
    GraphRuntimeControlPlane,
    GraphRuntimeRPCServer,
    graph_definition_from_dict,
    load_top_agent_profile,
    scoped_organization_view,
    ScriptNode,
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
            "planner": {
                "agent_id": "worker-planner",
                "cli_kind": "codex",
                "run_prompt": "Use the planning run prompt.",
            },
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


def test_graph_definition_json_loads_agent_ring_refresh_periods() -> None:
    graph = graph_definition_from_dict(
        {
            "agent_nodes": {"a": {}, "b": {}},
            "edges": [
                {"from": "a", "to": "b", "edge_type": "exec"},
                {"from": "b", "to": "a", "edge_type": "exec"},
            ],
            "agent_ring_max_circulations": {"ring-a-b": 2},
            "agent_ring_context_refresh_periods": {"ring-a-b": 3},
        }
    )

    ring = graph.agent_rings()[0]
    assert ring.topology_id == "ring-a-b"
    assert ring.max_circulations == 2
    assert ring.context_refresh_period == 3
    assert ring.to_dict()["context_refresh_period"] == 3


def test_graph_definition_json_loads_prompt_nodes_and_validates_prompt_edges() -> None:
    graph = graph_definition_from_dict(
        {
            "agent_nodes": {
                "coder": {
                    "agent_id": "worker-coder",
                    "prompt_input_enabled": False,
                },
            },
            "prompt_nodes": {
                "guidance": {
                    "text": "Use the project conventions.",
                    "trigger": "always",
                    "expanded": True,
                },
            },
            "edges": [
                {
                    "from": "guidance",
                    "to": "coder",
                    "edge_type": "data",
                    "output_port": "out",
                    "input_port": "prompt",
                },
            ],
        }
    )

    assert graph.prompt_nodes["guidance"].text == "Use the project conventions."
    assert graph.prompt_nodes["guidance"].trigger == "always"
    assert graph.agent_organization_view()["graph"]["prompt_nodes"]["guidance"]["expanded"] is True

    with pytest.raises(ValueError, match="PromptNode edges must connect"):
        graph_definition_from_dict(
            {
                "agent_nodes": {"coder": {"prompt_input_enabled": False}},
                "script_nodes": {
                    "formatter": {
                        "script_id": "formatter.py:formatter",
                        "module_path": "formatter.py",
                        "function_name": "formatter",
                    },
                },
                "edges": [
                    {
                        "from": "formatter",
                        "to": "coder",
                        "edge_type": "data",
                        "output_port": "result",
                        "input_port": "prompt",
                    }
                ],
            }
        )


def test_control_plane_executes_script_nodes_between_agents(tmp_path: Path) -> None:
    script_root = tmp_path / ".multi_agent_workspace" / "scripts"
    script_root.mkdir(parents=True)
    (script_root / "score.py").write_text(
        "\n".join(
            [
                "from multi_agent_tcp.blueprint_script_nodes import blueprint_node",
                "",
                "@blueprint_node(name='Format score')",
                "def format_score(count: int, ratio: float) -> str:",
                "    return f'{count}:{ratio:.2f}'",
            ]
        ),
        encoding="utf-8",
    )
    graph = graph_definition_from_dict(
        {
            "agent_nodes": {
                "planner": {"agent_id": "planner"},
                "writer": {"agent_id": "writer"},
            },
            "script_nodes": {
                "format": {
                    "script_id": "score.py:format_score",
                    "module_path": "score.py",
                    "function_name": "format_score",
                    "title": "Format score",
                    "inputs": [
                        {"name": "count", "type": "int"},
                        {"name": "ratio", "type": "float"},
                    ],
                    "outputs": [{"name": "result", "type": "str"}],
                }
            },
            "edges": [
                {"from": "planner", "to": "format", "edge_type": "exec"},
                {"from": "format", "to": "writer", "edge_type": "exec"},
            ],
        }
    )
    runtime = GraphRuntime(_FakeCluster())
    control = GraphRuntimeControlPlane(runtime, graph, script_root=script_root)

    assert graph.agent_connections() == {"planner": ["writer"], "writer": []}
    assert graph.script_path_between_agents("planner", "writer") == ["format"]

    batch = control.handle_request(
        {
            "command": "message.create_batch",
            "args": {
                "source_node_id": "planner",
                "required_target_node_ids": ["writer"],
                "batch_id": "script-batch",
            },
        }
    )
    assert batch["batch"]["script_calls"]["format"]["function_name"] == "format_score"
    assert batch["batch"]["script_calls"]["format"]["required_target_node_ids"] == ["writer"]
    with pytest.raises(ValueError, match="requires blueprint_script_call"):
        control.handle_request(
            {
                "command": "agent.dispatch",
                "args": {
                    "source_node_id": "planner",
                    "target_node_id": "writer",
                    "batch_id": batch["batch"]["batch_id"],
                    "body": {"count": 3, "ratio": 0.125},
                },
            }
        )
    with pytest.raises(ValueError, match="requires blueprint_script_call"):
        control.handle_request(
            {
                "command": "agent.dispatch",
                "args": {
                    "source_node_id": "planner",
                    "target_node_id": "writer",
                    "batch_id": batch["batch"]["batch_id"],
                    "body": "",
                },
            }
        )

    dispatched = control.handle_request(
        {
            "command": "script.call",
            "args": {
                "source_node_id": "planner",
                "batch_id": batch["batch"]["batch_id"],
                "function_name": "format_score",
                "arguments": {"count": 3, "ratio": 0.125},
            },
        }
    )

    assert dispatched["ok"] is True
    assert dispatched["script_call"]["status"] == "delivered"
    assert dispatched["script_call"]["result"]["result"] == "3:0.12"
    assert dispatched["delivery"][0]["target_node_id"] == "writer"
    writer_body = runtime.status_snapshot()["queues"]["by_agent"]["writer"][0]["body"]
    assert writer_body["function_name"] == "format_score"
    assert writer_body["function_description"] == ""
    assert writer_body["arguments_summary"] == {"count": 3, "ratio": 0.125}
    assert writer_body["outputs"] == {"result": "3:0.12"}
    assert writer_body["result"] == "3:0.12"
    assert writer_body["source"]["node_id"] == "planner"
    event_types = [event["event_type"] for event in runtime.status_snapshot()["recent_events"]]
    assert "ScriptNodeRunning" in event_types
    assert "ScriptNodeCompleted" in event_types


class _FakeResidentServices:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def summary(self) -> list[dict[str, Any]]:
        return [
            {
                "service_name": "echo_service",
                "title": "Echo Service",
                "description": "Echoes payloads.",
                "status": "running",
            }
        ]

    def docs(self, service_name: str) -> dict[str, Any]:
        return {
            "ok": True,
            "service": {"service_name": service_name, "methods": [{"name": "echo"}]},
        }

    def call(self, service_name: str, method_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((service_name, method_name, arguments))
        return dict(self.result)


def test_control_plane_exposes_resident_services_and_queues_call_result() -> None:
    graph = graph_definition_from_dict({"agent_nodes": {"planner": {"agent_id": "planner"}}})
    runtime = GraphRuntime(_FakeCluster())
    services = _FakeResidentServices(
        {
            "ok": True,
            "service_name": "echo_service",
            "method_name": "echo",
            "result": {"message": "hello"},
        }
    )
    control = GraphRuntimeControlPlane(runtime, graph, resident_services=services)

    context = control.handle_request({"command": "agent.context", "args": {"source_node_id": "planner"}})
    docs = control.handle_request({"command": "resident_service.docs", "args": {"service_name": "echo_service"}})
    called = asyncio.run(control.call_resident_service("planner", "echo_service", "echo", {"message": "hello"}))

    assert context["context"]["resident_services"] == services.summary()
    assert docs["docs"]["service"]["service_name"] == "echo_service"
    assert services.calls == [("echo_service", "echo", {"message": "hello"})]
    assert called["ok"] is True
    assert called["result"] == {"message": "hello"}
    queued = runtime.status_snapshot()["queues"]["by_agent"]["planner"][0]["body"]
    assert queued["type"] == "blueprint_service_result"
    assert queued["service_name"] == "echo_service"
    assert queued["result"] == {"message": "hello"}
    assert queued["context"]["framework_context"]["resident_services"][0]["service_name"] == "echo_service"


def test_control_plane_queues_resident_service_error_for_stopped_service() -> None:
    graph = graph_definition_from_dict({"agent_nodes": {"planner": {"agent_id": "planner"}}})
    runtime = GraphRuntime(_FakeCluster())
    services = _FakeResidentServices(
        {
            "ok": False,
            "code": "RESIDENT_SERVICE_NOT_RUNNING",
            "error": "resident service is not running: echo_service",
            "service_name": "echo_service",
            "method_name": "echo",
        }
    )
    control = GraphRuntimeControlPlane(runtime, graph, resident_services=services)

    called = asyncio.run(control.call_resident_service("planner", "echo_service", "echo", {"message": "hello"}))

    assert called["ok"] is False
    queued = runtime.status_snapshot()["queues"]["by_agent"]["planner"][0]["body"]
    assert queued["type"] == "blueprint_service_error"
    assert queued["code"] == "RESIDENT_SERVICE_NOT_RUNNING"
    assert queued["error"] == "resident service is not running: echo_service"


def test_graph_definition_parses_common_nodes_and_validates_port_types() -> None:
    graph = graph_definition_from_dict(
        {
            "agent_nodes": {
                "source": {"agent_id": "source"},
                "worker": {"agent_id": "worker"},
            },
            "common_nodes": {
                "gate": {"kind": "branch"},
                "clock": {"kind": "tick", "every_n_seconds": 0},
            },
            "edges": [
                {"from": "source", "to": "gate", "input_port": "condition", "edge_type": "exec"},
                {"from": "gate", "output_port": "true", "to": "worker", "edge_type": "exec"},
                {"from": "clock", "output_port": "tick", "to": "worker", "edge_type": "exec"},
            ],
        }
    )

    assert graph.common_nodes["gate"].kind == "branch"
    assert graph.common_nodes["clock"].every_n_seconds == 1
    assert graph.framework_connections()["source"] == ["gate"]
    assert graph.framework_connections()["gate"] == ["worker"]
    organization = graph.agent_organization_view()
    assert organization["graph"]["common_nodes"] == {
        "gate": {"node_id": "gate", "kind": "branch"},
        "clock": {"node_id": "clock", "kind": "tick", "every_n_seconds": 1},
    }

    with pytest.raises(ValueError, match="edge port type mismatch"):
        graph_definition_from_dict(
            {
                "common_nodes": {
                    "clock": {"kind": "tick"},
                    "gate": {"kind": "branch"},
                },
                "edges": [
                    {
                        "from": "clock",
                        "output_port": "tick",
                        "to": "gate",
                        "input_port": "condition",
                        "edge_type": "exec",
                    }
                ],
            }
        )


def test_control_plane_dispatches_agent_message_to_branch_common_node() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "source": AgentNode(node_id="source", agent_id="source"),
            "yes": AgentNode(node_id="yes", agent_id="yes"),
            "no": AgentNode(node_id="no", agent_id="no"),
        },
        common_nodes={
            "gate": CommonNode(node_id="gate", kind="branch"),
        },
        edges=[
            GraphEdge("source", "gate", input_port="condition", edge_type="exec"),
            GraphEdge("gate", "yes", output_port="true", edge_type="exec"),
            GraphEdge("gate", "no", output_port="false", edge_type="exec"),
        ],
    )
    runtime = GraphRuntime(_FakeCluster())
    control = GraphRuntimeControlPlane(runtime, graph)

    organization = control.handle_request({"command": "organization.read", "args": {}})["organization"]
    assert organization["graph"]["common_nodes"]["gate"] == {"node_id": "gate", "kind": "branch"}
    assert organization["framework_connections"]["source"] == ["gate"]
    batch = control.handle_request(
        {
            "command": "message.create_batch",
            "args": {
                "source_node_id": "source",
                "required_target_node_ids": ["gate"],
                "batch_id": "source-to-branch",
            },
        }
    )
    dispatched = control.handle_request(
        {
            "command": "agent.dispatch",
            "args": {
                "source_node_id": "source",
                "target_node_id": "gate",
                "batch_id": batch["batch"]["batch_id"],
                "body": {"condition": True, "prompt": "go yes"},
            },
        }
    )

    assert dispatched["ok"] is True
    assert runtime.status_snapshot(graph=graph)["queues"]["by_common_node"]["gate"][0]["body"]["condition"] is True
    asyncio.run(runtime.tick())
    snapshot = runtime.status_snapshot(graph=graph)
    assert [item["body"]["prompt"] for item in snapshot["queues"]["by_agent"]["yes"]] == ["go yes"]
    assert snapshot["queues"]["by_agent"].get("no", []) == []
    event_types = [event["event_type"] for event in snapshot["recent_events"]]
    assert "BranchNodeCompleted" in event_types


def test_control_plane_live_fan_in_waits_for_all_message_inputs() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "left": AgentNode(node_id="left", agent_id="left"),
            "right": AgentNode(node_id="right", agent_id="right"),
            "joiner": AgentNode(node_id="joiner", agent_id="joiner"),
        },
        edges=[
            GraphEdge("left", "joiner", edge_type="exec"),
            GraphEdge("right", "joiner", edge_type="exec"),
        ],
    )
    runtime = GraphRuntime(_FakeCluster())
    control = GraphRuntimeControlPlane(runtime, graph)

    left_batch = control.handle_request(
        {
            "command": "message.create_batch",
            "args": {
                "source_node_id": "left",
                "required_target_node_ids": ["joiner"],
                "batch_id": "left-batch",
                "route_id": "route-join",
            },
        }
    )["batch"]
    left_dispatch = control.handle_request(
        {
            "command": "agent.dispatch",
            "args": {
                "source_node_id": "left",
                "target_node_id": "joiner",
                "batch_id": left_batch["batch_id"],
                "body": {"prompt": "left result"},
            },
        }
    )

    assert left_dispatch["ok"] is True
    assert runtime.agent_message_queues.get("joiner", []) == []
    assert left_dispatch["dispatch"]["fan_in"]["status"] == "waiting"
    assert left_dispatch["dispatch"]["fan_in"]["missing_inputs"] == [
        {
            "source_node_id": "right",
            "source_output_port": "out",
            "target_input_port": "in",
            "edge_type": "exec",
        }
    ]

    right_batch = control.handle_request(
        {
            "command": "message.create_batch",
            "args": {
                "source_node_id": "right",
                "required_target_node_ids": ["joiner"],
                "batch_id": "right-batch",
                "route_id": "route-join",
            },
        }
    )["batch"]
    right_dispatch = control.handle_request(
        {
            "command": "agent.dispatch",
            "args": {
                "source_node_id": "right",
                "target_node_id": "joiner",
                "batch_id": right_batch["batch_id"],
                "body": {"prompt": "right result"},
            },
        }
    )

    assert right_dispatch["dispatch"]["fan_in"]["status"] == "ready"
    queued = runtime.agent_message_queues["joiner"]
    assert len(queued) == 1
    body = queued[0].body
    assert body["type"] == "fan_in_aggregate"
    assert body["aggregate"]["route_id"] == "route-join"
    assert body["context"]["framework_context"]["message_envelope"]["route_id"] == "route-join"
    assert [item["source_node_id"] for item in body["aggregate"]["contributions"]] == ["left", "right"]
    assert body["aggregate"]["inputs"]["in"] == [
        {"prompt": "left result"},
        {"prompt": "right result"},
    ]


def test_control_plane_branch_true_fan_in_gates_agent_and_false_skips() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "other": AgentNode(node_id="other", agent_id="other"),
            "joiner": AgentNode(node_id="joiner", agent_id="joiner"),
        },
        common_nodes={"gate": CommonNode(node_id="gate", kind="branch")},
        edges=[
            GraphEdge("other", "joiner", edge_type="exec"),
            GraphEdge("gate", "joiner", output_port="true", edge_type="exec"),
        ],
    )
    runtime = GraphRuntime(_FakeCluster())
    control = GraphRuntimeControlPlane(runtime, graph)

    other_batch = control.handle_request(
        {
            "command": "message.create_batch",
            "args": {
                "source_node_id": "other",
                "required_target_node_ids": ["joiner"],
                "batch_id": "other-batch",
                "route_id": "route-branch",
            },
        }
    )["batch"]
    control.handle_request(
        {
            "command": "agent.dispatch",
            "args": {
                "source_node_id": "other",
                "target_node_id": "joiner",
                "batch_id": other_batch["batch_id"],
                "body": {"prompt": "other ready"},
            },
        }
    )
    assert runtime.agent_message_queues.get("joiner", []) == []

    runtime.queue_common_node_message(
        "gate",
        {"condition": False, "prompt": "branch false"},
        route_id="route-branch",
    )
    asyncio.run(runtime.tick())
    assert runtime.agent_message_queues.get("joiner", []) == []
    gate = runtime.fan_in_gates["route-branch::joiner"]
    assert gate.status == "skipped"

    graph_true = GraphDefinition(
        agent_nodes={
            "other": AgentNode(node_id="other", agent_id="other"),
            "joiner": AgentNode(node_id="joiner", agent_id="joiner"),
        },
        common_nodes={"gate": CommonNode(node_id="gate", kind="branch")},
        edges=[
            GraphEdge("other", "joiner", edge_type="exec"),
            GraphEdge("gate", "joiner", output_port="true", edge_type="exec"),
        ],
    )
    cluster_true = _FakeCluster()
    runtime_true = GraphRuntime(cluster_true)
    control_true = GraphRuntimeControlPlane(runtime_true, graph_true)
    other_batch_true = control_true.handle_request(
        {
            "command": "message.create_batch",
            "args": {
                "source_node_id": "other",
                "required_target_node_ids": ["joiner"],
                "batch_id": "other-batch-true",
                "route_id": "route-branch-true",
            },
        }
    )["batch"]
    control_true.handle_request(
        {
            "command": "agent.dispatch",
            "args": {
                "source_node_id": "other",
                "target_node_id": "joiner",
                "batch_id": other_batch_true["batch_id"],
                "body": {"prompt": "other ready"},
            },
        }
    )
    runtime_true.queue_common_node_message(
        "gate",
        {"condition": True, "prompt": "branch true"},
        route_id="route-branch-true",
    )
    asyncio.run(runtime_true.tick())
    assert len(cluster_true.sent) == 1
    body = cluster_true.sent[0][1]
    assert body["type"] == "fan_in_aggregate"
    assert [item["source_node_id"] for item in body["aggregate"]["contributions"]] == [
        "other",
        "gate",
    ]


def test_runtime_live_fan_in_wraps_message_and_value_inputs() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "source": AgentNode(node_id="source", agent_id="source"),
            "joiner": AgentNode(node_id="joiner", agent_id="joiner"),
        },
        script_nodes={
            "score_script": ScriptNode(
                node_id="score_script",
                script_id="score_script",
                module_path="score.py",
                function_name="score",
                outputs=[{"name": "score", "type": "int"}],
            ),
        },
        edges=[
            GraphEdge("source", "joiner", edge_type="exec"),
            GraphEdge("score_script", "joiner", output_port="score", input_port="score", edge_type="data"),
        ],
    )
    runtime = GraphRuntime(_FakeCluster())
    control = GraphRuntimeControlPlane(runtime, graph)

    batch = control.handle_request(
        {
            "command": "message.create_batch",
            "args": {
                "source_node_id": "source",
                "required_target_node_ids": ["joiner"],
                "batch_id": "source-batch",
                "route_id": "route-mixed",
            },
        }
    )["batch"]
    control.handle_request(
        {
            "command": "agent.dispatch",
            "args": {
                "source_node_id": "source",
                "target_node_id": "joiner",
                "batch_id": batch["batch_id"],
                "body": {"prompt": "message input"},
            },
        }
    )
    assert runtime.agent_message_queues.get("joiner", []) == []

    value_result = runtime.offer_fan_in_contribution(
        graph,
        "joiner",
        source_node_id="score_script",
        source_output_port="score",
        target_input_port="score",
        edge_type="data",
        kind="value",
        value=42,
        route_id="route-mixed",
    )

    assert value_result["status"] == "ready"
    queued = runtime.agent_message_queues["joiner"]
    assert len(queued) == 1
    body = queued[0].body
    assert body["type"] == "fan_in_aggregate"
    assert body["context"]["framework_context"]["message_envelope"]["route_id"] == "route-mixed"
    assert body["aggregate"]["inputs"]["score"] == 42
    assert body["aggregate"]["inputs"]["in"] == {"prompt": "message input"}
    value_contribution = [
        item for item in body["aggregate"]["contributions"]
        if item["kind"] == "value"
    ][0]
    assert value_contribution["value_type"] == "int"
    assert value_contribution["value"] == 42


def test_runtime_branch_condition_accepts_only_strict_bool_value() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "yes": AgentNode(node_id="yes", agent_id="yes"),
            "no": AgentNode(node_id="no", agent_id="no"),
        },
        script_nodes={
            "flag_script": ScriptNode(
                node_id="flag_script",
                script_id="flag_script",
                module_path="flag.py",
                function_name="flag",
                outputs=[{"name": "flag", "type": "bool"}],
            ),
        },
        common_nodes={"gate": CommonNode(node_id="gate", kind="branch")},
        edges=[
            GraphEdge("flag_script", "gate", output_port="flag", input_port="condition", edge_type="data"),
            GraphEdge("gate", "yes", output_port="true", edge_type="exec"),
            GraphEdge("gate", "no", output_port="false", edge_type="exec"),
        ],
    )
    runtime = GraphRuntime(_FakeCluster())
    runtime.configure_common_nodes(graph)

    result = runtime.offer_fan_in_contribution(
        graph,
        "gate",
        source_node_id="flag_script",
        source_output_port="flag",
        target_input_port="condition",
        edge_type="data",
        kind="value",
        value=True,
        route_id="route-bool",
    )
    assert result["status"] == "direct"
    asyncio.run(runtime.tick())
    assert [message.body["condition"] for message in runtime.agent_message_queues["yes"]] == [True]
    assert runtime.agent_message_queues.get("no", []) == []

    runtime_bad = GraphRuntime(_FakeCluster())
    runtime_bad.configure_common_nodes(graph)
    runtime_bad.offer_fan_in_contribution(
        graph,
        "gate",
        source_node_id="flag_script",
        source_output_port="flag",
        target_input_port="condition",
        edge_type="data",
        kind="value",
        value="true",
        route_id="route-string",
    )
    asyncio.run(runtime_bad.tick())
    snapshot = runtime_bad.status_snapshot(graph=graph)
    assert runtime_bad.agent_message_queues.get("yes", []) == []
    assert runtime_bad.agent_message_queues.get("no", []) == []
    assert snapshot["recent_events"][-1]["event_type"] == "BranchNodeFailed"


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
            "planning-context",
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
    cluster = _FakeCluster()
    runtime = GraphRuntime(cluster)
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
        asyncio.run(runtime.dispatch_queued_message_now(started["queued_messages"][0]["message_id"]))
        assert cluster.sent[0][0] == "worker-planner"
        assert cluster.sent[0][1]["prompt"] == (
            "# Agent Run Prompt\n\nUse the planning run prompt.\n\n---\n\nPlan implementation."
        )

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

        noop_batch = control.handle_request(
            {
                "command": "message.create_batch",
                "args": {
                    "source_node_id": "planner",
                    "required_target_node_ids": ["coder"],
                    "batch_id": "noop-1",
                },
            }
        )
        noop = control.handle_request(
            {
                "command": "agent.dispatch",
                "args": {
                    "source_node_id": "planner",
                    "target_node_id": "coder",
                    "body": 0,
                    "batch_id": noop_batch["batch"]["batch_id"],
                },
            }
        )
        assert noop["dispatch"]["no_op"] is True
        assert runtime.outgoing_batches["noop-1"].no_op_target_node_ids == ["coder"]

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


@pytest.mark.asyncio
async def test_control_plane_sync_entrypoint_runs_start_inside_event_loop() -> None:
    graph = graph_definition_from_dict(_graph_dict())
    runtime = GraphRuntime(_FakeCluster())
    control = GraphRuntimeControlPlane(runtime, graph)

    started = control.handle_request(
        {
            "command": "run.start",
            "args": {"plan": _plan_dict()},
        }
    )

    assert started["ok"] is True
    assert started["queued_messages"][0]["node_id"] == "planner"
    assert runtime.status_snapshot()["agents"]["planner"]["state"] == "queued"


def test_control_plane_reports_cycle_groups_as_observation_only() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "a": AgentNode(node_id="a"),
            "b": AgentNode(node_id="b"),
            "c": AgentNode(node_id="c"),
            "external-c": AgentNode(node_id="external-c"),
        },
        edges=[
            GraphEdge("a", "b", edge_type="exec"),
            GraphEdge("b", "c", edge_type="exec"),
            GraphEdge("c", "a", edge_type="exec"),
            GraphEdge("c", "external-c", edge_type="exec"),
        ],
    )
    runtime = GraphRuntime(_FakeCluster())
    control = GraphRuntimeControlPlane(runtime, graph)

    c_context = control.handle_request(
        {
            "command": "agent.context",
            "args": {"source_node_id": "c"},
        }
    )["context"]
    org = control.handle_request({"command": "organization.read", "args": {}})["organization"]

    assert org["cycle_groups"] == [["a", "b", "c"]]
    assert c_context["downstream_agents"] == ["a", "external-c"]
    assert c_context["organization"]["cycle_groups"] == [["a", "b", "c"]]
    assert "ring_session" not in c_context


def test_control_plane_prunes_exhausted_ring_targets_from_agent_context() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "a": AgentNode(node_id="a"),
            "b": AgentNode(node_id="b"),
        },
        edges=[
            GraphEdge("a", "b", edge_type="exec"),
            GraphEdge("b", "a", edge_type="exec"),
        ],
    )
    runtime = GraphRuntime(_FakeCluster())
    control = GraphRuntimeControlPlane(runtime, graph)

    a_batch = control.handle_request(
        {
            "command": "message.create_batch",
            "args": {
                "source_node_id": "a",
                "required_target_node_ids": ["b"],
                "batch_id": "a-to-b",
            },
        }
    )
    control.handle_request(
        {
            "command": "agent.dispatch",
            "args": {
                "source_node_id": "a",
                "target_node_id": "b",
                "batch_id": a_batch["batch"]["batch_id"],
                "body": {"prompt": "start ring"},
            },
        }
    )

    b_context_before_close = runtime.status_snapshot()["queues"]["by_agent"]["b"][0]["body"]["context"]["framework_context"]
    assert b_context_before_close["downstream_agents"] == ["a"]

    b_batch_id = b_context_before_close["message_envelope"]["outgoing_batch_id"]
    control.handle_request(
        {
            "command": "agent.dispatch",
            "args": {
                "source_node_id": "b",
                "target_node_id": "a",
                "batch_id": b_batch_id,
                "body": {"prompt": "close ring"},
            },
        }
    )

    a_context_after_close = runtime.status_snapshot()["queues"]["by_agent"]["a"][0]["body"]["context"]["framework_context"]
    assert a_context_after_close["downstream_agents"] == []
    assert a_context_after_close["ring_circulation_counts"] == {"ring1": 0}
    with pytest.raises(ValueError, match="not reachable"):
        control.handle_request(
            {
                "command": "message.create_batch",
                "args": {
                    "source_node_id": "a",
                    "required_target_node_ids": ["b"],
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


def test_top_agent_start_and_ask_commands_are_not_control_plane_surface() -> None:
    graph = graph_definition_from_dict(_graph_dict())
    runtime = GraphRuntime(_FakeCluster())
    profile = GuLiCodeTopAgentProfile(agent_id="gu", external=False)
    control = GraphRuntimeControlPlane(runtime, graph, top_agent=profile)

    with pytest.raises(ValueError):
        control.handle_request({"command": "top_agent.start_session", "args": {}})
    with pytest.raises(ValueError):
        control.handle_request(
            {
                "command": "top_agent.ask",
                "args": {"prompt": "What is happening?", "recent_events_limit": 3},
            }
        )
    assert runtime.cluster.started == []
    assert runtime.cluster.sent == []


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
