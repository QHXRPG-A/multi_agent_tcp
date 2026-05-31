from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

from multi_agent_tcp import (
    AdapterResult,
    AgentMessage,
    AgentNode,
    AgentSkillSelection,
    BlueprintTerminalNode,
    CLIWorkerBackend,
    CommonNode,
    CodexAdapter,
    CodeMakerAdapter,
    GuLiCodeTopAgentProfile,
    AgentTCPClient,
    GraphDefinition,
    GraphEdge,
    GraphExecutor,
    GraphJob,
    GraphRuntime,
    GraphRuntimeControlPlane,
    MultiModalEnvelope,
    RouteNode,
    TopAgentStartPlan,
    WorkspaceManifest,
    WorkerConfig,
    adapter_from_agent_config,
    body_to_agent_message,
    compile_ryven_flow,
    extract_codex_final_text,
    graph_definition_from_dict,
    normalize_envelope,
)

from multi_agent_tcp.skill_space import SkillSpace, SuperAgentProfile
from multi_agent_tcp.workspace_rpc import WorkspaceRPCServer
from multi_agent_tcp.codemaker_bridge import _merge_prompt as _merge_codemaker_prompt
from multi_agent_tcp.codemaker_bridge import load_codemaker_runtime
from multi_agent_tcp.codex_bridge import _merge_prompt as _merge_codex_prompt
from multi_agent_tcp.codex_bridge import _write_codex_diagnostics
from multi_agent_tcp.codex_bridge import _CodexStderrStreamLimiter
from multi_agent_tcp.codex_bridge import compact_codex_result_for_transport
from multi_agent_tcp.codex_bridge import load_codex_runtime
from multi_agent_tcp.agent_launch_context import (
    _apply_local_mcp_proxy_env,
    initialize_private_codex_home,
)
from multi_agent_tcp.blueprint_mcp_runtime import RunMCPRuntimeHandle
from multi_agent_tcp.ryven_blueprint import _apply_run_workspace_to_node
from multi_agent_tcp.workspace_api import CONTEXT_ENV as WORKSPACE_API_CONTEXT_ENV
from multi_agent_tcp.workspace_api import main as workspace_api_main
from multi_agent_tcp.workspace_manager import DulwichWorkspaceManager


def _codex_real_flow_config_overrides() -> list[str]:
    overrides = [
        'approval_policy="never"',
        'shell_environment_policy.inherit="all"',
    ]
    if sys.platform == "win32":
        overrides.append('windows.sandbox="unelevated"')
    return overrides


def _codex_command_executions(codex_result: dict[str, Any]) -> list[str]:
    commands: list[str] = []
    for event in codex_result.get("events") or []:
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if item.get("type") != "command_execution":
            continue
        command = item.get("command")
        if isinstance(command, str):
            commands.append(command)
    return commands


def _assert_codex_ran_workspace_api_commands(
    codex_result: dict[str, Any],
    expected: list[str],
) -> None:
    commands = _codex_command_executions(codex_result)
    combined = "\n".join(commands)
    missing = [item for item in expected if item not in combined]
    assert not missing, {
        "missing": missing,
        "commands": commands,
        "stdout": codex_result.get("stdout", ""),
        "stderr": codex_result.get("stderr", ""),
    }


def test_hidden_subprocess_kwargs_suppresses_windows_console() -> None:
    from multi_agent_tcp._proc_utils import hidden_subprocess_kwargs

    kwargs = hidden_subprocess_kwargs()
    if sys.platform != "win32":
        assert kwargs == {}
        return

    flags = kwargs.get("creationflags", 0)
    assert flags & subprocess.CREATE_NO_WINDOW
    assert not flags & subprocess.CREATE_NEW_CONSOLE
    startupinfo = kwargs.get("startupinfo")
    assert startupinfo is not None
    assert startupinfo.dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert startupinfo.wShowWindow == subprocess.SW_HIDE


def test_cluster_spawn_hides_worker_console_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform != "win32":
        pytest.skip("Windows-specific subprocess launch flags")

    import multi_agent_tcp.cluster as cluster_module

    captured: dict[str, Any] = {}

    class DummyProcess:
        pid = 12345

    def fake_popen(cmd: list[str], **kwargs: Any) -> DummyProcess:
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return DummyProcess()

    monkeypatch.setattr(cluster_module.subprocess, "Popen", fake_popen)

    proc = cluster_module._spawn(
        ["python", "-V"],
        "AGENT planner",
        verbose=False,
        env={"PYTHONUTF8": "1"},
    )

    assert proc.pid == 12345
    assert captured["cmd"] == ["python", "-V"]
    kwargs = captured["kwargs"]
    flags = kwargs.get("creationflags", 0)
    assert flags & subprocess.CREATE_NO_WINDOW
    assert not flags & subprocess.CREATE_NEW_CONSOLE
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL


def _workspace_api_audit_commands(run: Any) -> list[str]:
    manifest_path = run.shared_dir / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    writes = data.get("writes", [])
    assert isinstance(writes, list)
    return [
        str(item.get("command"))
        for item in writes
        if isinstance(item, dict) and item.get("event_type") == "workspace_api_call"
    ]


def test_body_to_agent_message_preserves_prompt_context_and_attachments() -> None:
    message = body_to_agent_message(
        {
            "prompt": "  hello agent  ",
            "context": {"previous": "answer"},
            "attachments": [{"kind": "file", "value": {"path": "a.txt"}}],
        }
    )

    assert message.prompt == "hello agent"
    assert message.context == '{"previous": "answer"}'
    assert message.attachments == [{"kind": "file", "value": {"path": "a.txt"}}]


def test_body_to_agent_message_uses_whole_dict_when_prompt_missing() -> None:
    message = body_to_agent_message({"task": "summarize", "id": 1})

    assert message.prompt == '{"task": "summarize", "id": 1}'
    assert message.context is None


def test_initialize_private_codex_home_seeds_runtime_state_only(tmp_path: Path) -> None:
    source = tmp_path / "source-codex-home"
    source.mkdir()
    (source / "config.toml").write_text('model = "gpt-5.5"\n', encoding="utf-8")
    (source / "auth.json").write_text('{"auth_mode":"api"}\n', encoding="utf-8")
    (source / "models_cache.json").write_text('{"models":[]}\n', encoding="utf-8")
    user_skill = source / "skills" / "user-skill"
    user_skill.mkdir(parents=True)
    (user_skill / "SKILL.md").write_text("# user skill\n", encoding="utf-8")
    (source / "sessions").mkdir()

    private = tmp_path / "private-codex-home"
    initialize_private_codex_home(private, source_codex_home=source)

    assert (private / "config.toml").read_text(encoding="utf-8") == 'model = "gpt-5.5"\n'
    assert (private / "auth.json").read_text(encoding="utf-8") == '{"auth_mode":"api"}\n'
    assert (private / "models_cache.json").read_text(encoding="utf-8") == '{"models":[]}\n'
    assert not (private / "skills" / "user-skill").exists()
    assert not (private / "sessions").exists()


def test_local_mcp_proxy_env_preserves_proxy_compatibility(monkeypatch) -> None:
    monkeypatch.setenv("NO_PROXY", "env.local;localhost")
    monkeypatch.setattr(
        "multi_agent_tcp.agent_launch_context.urllib.request.getproxies",
        lambda: {
            "http": "http://system-proxy:8080",
            "https": "http://system-proxy:8443",
            "no": "registry.local",
        },
    )
    extra_env = {
        "NO_PROXY": "internal.local,127.0.0.1",
        "HTTPS_PROXY": "http://custom-proxy:9443",
    }

    _apply_local_mcp_proxy_env(extra_env)

    no_proxy_hosts = extra_env["NO_PROXY"].split(",")
    assert extra_env["no_proxy"] == extra_env["NO_PROXY"]
    assert no_proxy_hosts.count("127.0.0.1") == 1
    assert no_proxy_hosts.count("localhost") == 1
    assert {"internal.local", "env.local", "registry.local", "::1"}.issubset(no_proxy_hosts)
    assert extra_env["HTTP_PROXY"] == "http://system-proxy:8080"
    assert extra_env["http_proxy"] == "http://system-proxy:8080"
    assert extra_env["HTTPS_PROXY"] == "http://custom-proxy:9443"
    assert extra_env["https_proxy"] == "http://custom-proxy:9443"


def test_worker_config_serializes_adapter_fields() -> None:
    cfg = WorkerConfig(
        "agent-a",
        cwd=Path("."),
        cli_kind="codemaker",
        adapter_options={"anchor_message": "Use attached prompt"},
        extra_env={"CODEMAKER_AUTH_TOKEN": "token"},
    ).to_agent_json("127.0.0.1", 9140)

    assert cfg["agent_id"] == "agent-a"
    assert cfg["cli_kind"] == "codemaker"
    assert cfg["mode"] == "codemaker-worker"
    assert cfg["codemaker"]["anchor_message"] == "Use attached prompt"
    assert cfg["extra_env"] == {"CODEMAKER_AUTH_TOKEN": "token"}


def test_codemaker_runtime_merges_blueprint_context_into_prompt(tmp_path: Path) -> None:
    runtime = load_codemaker_runtime(
        {
            "codemaker": {
                "cwd": str(tmp_path),
                "prompt_preamble": "Blueprint workspace contract",
                "execution_context": {"shared_code": str(tmp_path / "shared" / "code")},
            }
        }
    )

    merged = _merge_codemaker_prompt("Do the task", "Upstream result", runtime)

    assert "Blueprint workspace contract" in merged
    assert "Agent Execution Context" in merged
    assert "shared_code" in merged
    assert "Do the task" in merged
    assert "Upstream result" in merged


def test_worker_config_serializes_codex_worker_and_model() -> None:
    cfg = WorkerConfig(
        "agent-cx",
        cwd=Path("."),
        cli_kind="codex",
        model="gpt-5.4",
        adapter_options={"sandbox": "workspace-write"},
    ).to_agent_json("127.0.0.1", 9140)

    assert cfg["cli_kind"] == "codex"
    assert cfg["mode"] == "codex-worker"
    assert cfg["role"] == "codex"
    assert cfg["codex"]["command"] == "codex"
    assert cfg["codex"]["model"] == "gpt-5.4"
    assert cfg["codex"]["sandbox"] == "workspace-write"


def test_agent_node_from_dict_and_worker_config() -> None:
    node = AgentNode.from_dict(
        {
            "node_id": "node-1",
            "agent_id": "agent-1",
            "prompt": "Describe node 1.",
            "run_prompt": "Always follow the run contract.",
            "execution_mode": "nonblocking",
            "cli_kind": "codemaker",
            "cwd": ".",
            "adapter_options": {"prompt_via_file": "always"},
            "extra_env": {"A": 1},
            "read_scope": ["src"],
            "write_scope": ["out"],
            "artifact_scope": ["artifacts"],
        }
    )

    worker = node.to_worker_config()

    assert node.runtime_agent_id == "agent-1"
    assert node.prompt == "Describe node 1."
    assert node.run_prompt == "Always follow the run contract."
    assert node.execution_mode == "nonblocking"
    assert worker.agent_id == "agent-1"
    assert worker.cli_kind == "codemaker"
    assert worker.adapter_options["prompt_via_file"] == "always"
    assert worker.adapter_options["node_type"] == "worker_agent"
    assert worker.adapter_options["access_policy"] == {
        "direct_project_io": False,
        "outside_project_io": False,
        "unrestricted_commands": False,
        "disable_sandbox": False,
        "framework_message_tools": True,
    }
    assert worker.extra_env == {"A": "1"}
    assert node.read_scope == ["src"]
    assert node.write_scope == ["out"]
    assert node.artifact_scope == ["artifacts"]


def test_agent_node_from_dict_defaults_full_agent_to_codex_access() -> None:
    node = AgentNode.from_dict(
        {
            "node_id": "shell",
            "node_type": "agent",
            "cwd": ".",
        }
    )

    assert node.node_type == "agent"
    assert node.cli_kind == "codex"
    assert node.model == "gpt-5.4"
    assert node.command == "codex"
    assert node.access_policy == {
        "direct_project_io": True,
        "outside_project_io": True,
        "unrestricted_commands": True,
        "disable_sandbox": True,
        "framework_message_tools": True,
    }
    worker = node.to_worker_config()
    assert worker.adapter_options["node_type"] == "agent"
    assert worker.adapter_options["access_policy"]["disable_sandbox"] is True


def test_agent_node_from_dict_auto_generates_node_id() -> None:
    node = AgentNode.from_dict({"cwd": "."})

    assert node.node_id.startswith("agent-node-")
    assert node.runtime_agent_id == node.node_id
    assert node.write_scope == ["**"]


def test_agent_node_from_dict_migrates_legacy_report_only_write_scope() -> None:
    node = AgentNode.from_dict({"cwd": ".", "write_scope": ["shared/reports/**"]})

    assert node.write_scope == ["**"]


def test_agent_node_to_dict_round_trips_ui_config() -> None:
    node = AgentNode.from_dict(
        {
            "node_id": "node-ui",
            "agent_id": "agent-ui",
            "cli_kind": "codex",
            "model": "gpt-5.4",
            "cwd": ".",
            "run_prompt": "Use the private checkout.",
            "skill_selection": {"mode": "selected", "skill_hashes": ["hash-a"]},
        }
    )

    restored = AgentNode.from_dict(node.to_dict())

    assert restored.node_id == "node-ui"
    assert restored.runtime_agent_id == "agent-ui"
    assert restored.cli_kind == "codex"
    assert restored.run_prompt == "Use the private checkout."
    assert restored.skill_selection.skill_hashes == ["hash-a"]


def test_agent_node_rejects_blank_node_id_when_explicit() -> None:
    with pytest.raises(ValueError):
        AgentNode.from_dict({"node_id": "  "})


def test_agent_node_legacy_skills_become_selected_skill_selection() -> None:
    node = AgentNode.from_dict({"skills": ["hash-a", "hash-b"]})

    assert node.skill_selection.mode == "selected"
    assert node.skill_selection.skill_hashes == ["hash-a", "hash-b"]
    assert node.skills == ["hash-a", "hash-b"]


def test_agent_node_skill_selection_none_all_selected_and_upstream(tmp_path: Path) -> None:
    def make_skill(name: str) -> Path:
        path = tmp_path / "source" / name
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {name}\n---\n# {name}\n",
            encoding="utf-8",
        )
        return path

    space = SkillSpace.open_or_init(tmp_path / "skill-space")
    rec_a = space.add_skill_copy(make_skill("a"))
    rec_b = space.add_skill_copy(make_skill("b"))

    none_node = AgentNode.from_dict({"skill_selection": {"mode": "none"}})
    all_node = AgentNode.from_dict({"skill_selection": {"mode": "all"}})
    selected_node = AgentNode.from_dict(
        {"skill_selection": {"mode": "selected", "skill_hashes": [rec_a.skill_hash]}}
    )
    upstream_node = AgentNode.from_dict({"skill_selection": {"mode": "upstream"}})
    super_agent = SuperAgentProfile(
        agent_id="super",
        assignable_skill_hashes=[rec_b.skill_hash],
    )

    assert none_node.resolve_skill_hashes(space) == []
    assert all_node.resolve_skill_hashes(space) == sorted([rec_a.skill_hash, rec_b.skill_hash])
    assert selected_node.resolve_skill_hashes(space) == [rec_a.skill_hash]


def test_graph_definition_agent_cycle_groups_detects_agent_cycles() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "a": AgentNode.from_dict({"node_id": "a"}),
            "b": AgentNode.from_dict({"node_id": "b"}),
            "c": AgentNode.from_dict({"node_id": "c"}),
            "d": AgentNode.from_dict({"node_id": "d"}),
            "e": AgentNode.from_dict({"node_id": "e"}),
            "f": AgentNode.from_dict({"node_id": "f"}),
        },
        route_nodes={
            "r1": RouteNode(node_id="r1", route_kind="sequence"),
        },
        edges=[
            GraphEdge("a", "b", edge_type="exec"),
            GraphEdge("b", "c", edge_type="exec"),
            GraphEdge("c", "a", edge_type="exec"),
            GraphEdge("d", "e", edge_type="exec"),
            GraphEdge("e", "f", edge_type="exec"),
            GraphEdge("f", "d", edge_type="exec"),
            GraphEdge("c", "r1", edge_type="exec"),
            GraphEdge("r1", "d", edge_type="exec"),
        ],
    )

    assert graph.agent_cycle_groups() == [["a", "b", "c"], ["d", "e", "f"]]


def test_graph_definition_agent_cycle_groups_ignores_acyclic_graphs() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "planner": AgentNode.from_dict({"node_id": "planner"}),
            "coder": AgentNode.from_dict({"node_id": "coder"}),
            "reviewer": AgentNode.from_dict({"node_id": "reviewer"}),
        },
        edges=[
            GraphEdge("planner", "coder", edge_type="exec"),
            GraphEdge("coder", "reviewer", edge_type="exec"),
        ],
    )

    assert graph.agent_cycle_groups() == []


def test_graph_definition_agent_rings_start_at_two_agent_mutual_edges() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "a": AgentNode.from_dict({"node_id": "a"}),
            "b": AgentNode.from_dict({"node_id": "b"}),
            "c": AgentNode.from_dict({"node_id": "c"}),
        },
        edges=[
            GraphEdge("a", "a", edge_type="exec"),
            GraphEdge("a", "b", edge_type="exec"),
            GraphEdge("b", "a", edge_type="exec"),
            GraphEdge("b", "c", edge_type="exec"),
        ],
    )

    assert graph.agent_cycle_groups() == [["a", "b"]]
    assert graph.agent_rings()[0].to_dict()["closing_edge"] == {"from": "b", "to": "a"}


@pytest.mark.asyncio
async def test_cycle_groups_are_observational_and_do_not_change_dispatch() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "a": AgentNode.from_dict({"node_id": "a"}),
            "b": AgentNode.from_dict({"node_id": "b"}),
            "c": AgentNode.from_dict({"node_id": "c"}),
            "external-c": AgentNode.from_dict({"node_id": "external-c"}),
        },
        edges=[
            GraphEdge("a", "b", edge_type="exec"),
            GraphEdge("b", "c", edge_type="exec"),
            GraphEdge("c", "a", edge_type="exec"),
            GraphEdge("c", "external-c", edge_type="exec"),
        ],
    )
    runtime = GraphRuntime(_FakeCluster())
    await runtime.prestart_agents(list(graph.agent_nodes.values()))

    assert graph.agent_cycle_groups() == [["a", "b", "c"]]
    batch = await runtime.create_outgoing_batch_from_graph(
        graph,
        "c",
        required_target_node_ids=["a", "external-c"],
    )
    runtime.stage_outgoing_message(batch.batch_id, graph.agent_nodes["a"], {"prompt": "cycle"})
    result = runtime.stage_outgoing_message(
        batch.batch_id,
        graph.agent_nodes["external-c"],
        {"prompt": "external"},
    )

    assert result["ready_to_dispatch"] is True
    assert len(runtime.agent_message_queues["a"]) == 1
    assert len(runtime.agent_message_queues["external-c"]) == 1
    assert runtime.status_snapshot(graph=graph)["organization"]["cycle_groups"] == [["a", "b", "c"]]
    assert "ring_sessions" not in runtime.status_snapshot()


@pytest.mark.asyncio
async def test_graph_runtime_enforces_independent_overlapping_ring_circulations() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "a": AgentNode.from_dict({"node_id": "a"}),
            "b": AgentNode.from_dict({"node_id": "b"}),
            "c": AgentNode.from_dict({"node_id": "c"}),
        },
        edges=[
            GraphEdge("a", "b", edge_type="exec"),
            GraphEdge("b", "a", edge_type="exec"),
            GraphEdge("b", "c", edge_type="exec"),
            GraphEdge("c", "a", edge_type="exec"),
        ],
    )
    runtime = GraphRuntime(_FakeCluster())
    await runtime.prestart_agents(list(graph.agent_nodes.values()))

    assert graph.agent_cycle_groups() == [["a", "b"], ["a", "b", "c"]]
    assert runtime.active_agent_connections(graph, "a") == ["b"]

    first = await runtime.create_outgoing_batch_from_graph(
        graph,
        "a",
        required_target_node_ids=["b"],
        batch_id="a-to-b-1",
    )
    runtime.stage_outgoing_message(first.batch_id, graph.agent_nodes["b"], {"prompt": "a to b"})
    small_close = await runtime.create_outgoing_batch_from_graph(
        graph,
        "b",
        required_target_node_ids=["a"],
        batch_id="b-to-a",
    )
    runtime.stage_outgoing_message(small_close.batch_id, graph.agent_nodes["a"], {"prompt": "b to a"})

    counts = runtime.agent_ring_status(graph)["counts_by_agent"]
    assert counts["a"] == {"ring1": 0, "ring2": 1}
    assert runtime.active_agent_connections(graph, "a") == ["b"]

    second = await runtime.create_outgoing_batch_from_graph(
        graph,
        "a",
        required_target_node_ids=["b"],
        batch_id="a-to-b-2",
    )
    runtime.stage_outgoing_message(second.batch_id, graph.agent_nodes["b"], {"prompt": "a to b again"})
    b_to_c = await runtime.create_outgoing_batch_from_graph(
        graph,
        "b",
        required_target_node_ids=["c"],
        batch_id="b-to-c",
    )
    runtime.stage_outgoing_message(b_to_c.batch_id, graph.agent_nodes["c"], {"prompt": "b to c"})
    big_close = await runtime.create_outgoing_batch_from_graph(
        graph,
        "c",
        required_target_node_ids=["a"],
        batch_id="c-to-a",
    )
    runtime.stage_outgoing_message(big_close.batch_id, graph.agent_nodes["a"], {"prompt": "c to a"})

    assert runtime.agent_ring_status(graph)["counts_by_agent"]["a"] == {
        "ring1": 0,
        "ring2": 0,
    }
    assert runtime.active_agent_connections(graph, "a") == []
    with pytest.raises(ValueError, match="not reachable"):
        await runtime.create_outgoing_batch_from_graph(
            graph,
            "a",
            required_target_node_ids=["b"],
        )


@pytest.mark.asyncio
async def test_graph_runtime_branch_routes_true_false_and_rejects_non_bool() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "yes": AgentNode.from_dict({"node_id": "yes", "agent_id": "worker-yes"}),
            "no": AgentNode.from_dict({"node_id": "no", "agent_id": "worker-no"}),
        },
        common_nodes={
            "gate": CommonNode(node_id="gate", kind="branch"),
        },
        edges=[
            GraphEdge("gate", "yes", output_port="true", edge_type="exec"),
            GraphEdge("gate", "no", output_port="false", edge_type="exec"),
        ],
    )
    runtime = GraphRuntime(_FakeCluster())
    runtime.configure_common_nodes(graph)

    runtime.queue_common_node_message("gate", {"condition": True, "prompt": "true branch"})
    await runtime.tick()
    assert [message.body["prompt"] for message in runtime.agent_message_queues["yes"]] == ["true branch"]
    assert runtime.agent_message_queues.get("no", []) == []

    runtime.queue_common_node_message("gate", {"condition": False, "prompt": "false branch"})
    await runtime.tick()
    assert [message.body["prompt"] for message in runtime.agent_message_queues["no"]] == ["false branch"]

    runtime.queue_common_node_message("gate", {"condition": "true", "prompt": "bad branch"})
    await runtime.tick()
    snapshot = runtime.status_snapshot(graph=graph)
    event_types = [event["event_type"] for event in snapshot["recent_events"]]
    assert "BranchNodeFailed" in event_types
    assert len(runtime.agent_message_queues["yes"]) == 1
    assert len(runtime.agent_message_queues["no"]) == 1


@pytest.mark.asyncio
async def test_graph_runtime_tick_emits_on_interval_and_applies_backpressure() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "worker": AgentNode.from_dict({"node_id": "worker", "agent_id": "worker"}),
        },
        common_nodes={
            "clock": CommonNode(node_id="clock", kind="tick", every_n_ticks=2),
        },
        edges=[
            GraphEdge("clock", "worker", output_port="tick", edge_type="exec"),
        ],
    )
    runtime = GraphRuntime(_FakeCluster())
    runtime.configure_common_nodes(graph)

    await runtime.tick()
    assert runtime.agent_message_queues.get("worker", []) == []

    await runtime.tick()
    queued = runtime.agent_message_queues["worker"]
    assert len(queued) == 1
    assert queued[0].body["type"] == "tick"
    assert queued[0].body["tick_count"] == 2

    await runtime.tick()
    await runtime.tick()
    assert len(runtime.agent_message_queues["worker"]) == 1
    event_types = [event["event_type"] for event in runtime.status_snapshot(graph=graph)["recent_events"]]
    assert "TickNodeSkipped" in event_types


def test_top_agent_start_plan_allows_tick_only_runs() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "worker": AgentNode.from_dict({"node_id": "worker"}),
        },
        common_nodes={
            "clock": CommonNode(node_id="clock", kind="tick"),
        },
        edges=[
            GraphEdge("clock", "worker", output_port="tick", edge_type="exec"),
        ],
    )
    plan = TopAgentStartPlan.from_dict(
        {
            "user_goal": "Run from tick source.",
            "agent_descriptions": {"worker": "Handles ticks."},
            "start_nodes": [],
            "tasks": {},
        }
    )

    assert GuLiCodeTopAgentProfile().validate_start_plan(graph, plan).ok is True
    assert graph.has_tick_source() is True


def test_agent_skill_selection_serializes() -> None:
    selection = AgentSkillSelection(
        mode="selected",
        skill_hashes=["hash-a"],
        assigned_by="super",
    )

    assert selection.to_dict() == {
        "mode": "selected",
        "skill_hashes": ["hash-a"],
        "assigned_by": "super",
    }


def test_codex_agent_node_maps_model_to_worker_config() -> None:
    node = AgentNode.from_dict(
        {
            "node_id": "codex-node",
            "cli_kind": "codex",
            "model": "gpt-5.4",
            "cwd": ".",
        }
    )

    worker = node.to_worker_config()
    cfg = worker.to_agent_json("127.0.0.1", 9140)

    assert worker.cli_kind == "codex"
    assert cfg["codex"]["model"] == "gpt-5.4"


def test_adapter_from_agent_config_accepts_codex_worker_mode_without_cli_kind() -> None:
    adapter = adapter_from_agent_config(
        {
            "agent_id": "agent-cx",
            "mode": "codex-worker",
            "codex": {"cwd": "."},
        }
    )

    assert isinstance(adapter, CodexAdapter)


def test_codex_runtime_rejects_danger_full_access() -> None:
    with pytest.raises(ValueError, match="danger-full-access"):
        load_codex_runtime(
            {
                "agent_id": "agent-cx",
                "codex": {
                    "cwd": ".",
                    "sandbox": "danger-full-access",
                },
            }
        )


def test_codex_runtime_allows_danger_full_access_for_full_agent_only(tmp_path: Path) -> None:
    runtime = load_codex_runtime(
        {
            "agent_id": "agent-cx",
            "codex": {
                "cwd": str(tmp_path),
                "node_type": "agent",
                "access_policy": {"disable_sandbox": True},
                "dangerous_access": True,
                "sandbox": "danger-full-access",
                "extra_args": ["--dangerously-bypass-approvals-and-sandbox"],
            },
        }
    )

    assert runtime["sandbox"] == "danger-full-access"
    assert runtime["node_type"] == "agent"
    assert runtime["dangerous_access"] is True

    with pytest.raises(ValueError, match="danger-full-access"):
        load_codex_runtime(
            {
                "agent_id": "agent-cx",
                "codex": {
                    "cwd": str(tmp_path),
                    "node_type": "worker_agent",
                    "access_policy": {"disable_sandbox": True},
                    "dangerous_access": True,
                    "sandbox": "danger-full-access",
                },
            }
        )

    with pytest.raises(ValueError, match="danger-full-access"):
        load_codex_runtime(
            {
                "agent_id": "agent-cx",
                "codex": {
                    "cwd": str(tmp_path),
                    "node_type": "agent",
                    "access_policy": {"disable_sandbox": False},
                    "dangerous_access": True,
                    "sandbox": "danger-full-access",
                },
            }
        )


def test_codex_runtime_prefers_windows_cmd_shim_for_ps1(tmp_path: Path) -> None:
    ps1 = tmp_path / "codex.ps1"
    cmd = tmp_path / "codex.cmd"
    ps1.write_text("Write-Output codex", encoding="utf-8")
    cmd.write_text("@echo off\r\n", encoding="utf-8")

    runtime = load_codex_runtime(
        {
            "agent_id": "agent-cx",
            "codex": {
                "cwd": str(tmp_path),
                "command": str(ps1),
            },
        }
    )

    if ps1.suffix.lower() == ".ps1":
        assert runtime["command"] == str(cmd)


def test_codex_runtime_rejects_extra_args_add_dir_for_project_context(tmp_path: Path) -> None:
    project = tmp_path / "project"
    checkout = tmp_path / "run" / "agents" / "agent-cx" / "private" / "checkout"
    project.mkdir()
    checkout.mkdir(parents=True)

    with pytest.raises(ValueError, match="--add-dir"):
        load_codex_runtime(
            {
                "agent_id": "agent-cx",
                "codex": {
                    "cwd": str(checkout),
                    "sandbox": "workspace-write",
                    "extra_args": ["--add-dir", str(project)],
                    "execution_context": {
                        "code_workspace": {
                            "project_context": str(project),
                        },
                    },
                },
            }
        )


def test_codex_runtime_rejects_extra_args_add_dir_for_project_code_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    subdir = project / "pkg"
    checkout = tmp_path / "run" / "agents" / "agent-cx" / "private" / "checkout"
    subdir.mkdir(parents=True)
    checkout.mkdir(parents=True)

    with pytest.raises(ValueError, match="--add-dir"):
        load_codex_runtime(
            {
                "agent_id": "agent-cx",
                "codex": {
                    "cwd": str(checkout),
                    "sandbox": "workspace-write",
                    "extra_args": ["--add-dir", str(project)],
                    "execution_context": {
                        "code_workspace": {
                            "project_context": str(subdir),
                            "project_code_root": str(project),
                        },
                    },
                },
            }
        )


def test_codex_runtime_rejects_extra_args_add_dir_for_shared_workspace(tmp_path: Path) -> None:
    checkout = tmp_path / "run" / "agents" / "agent-cx" / "private" / "checkout"
    shared = tmp_path / "run" / "shared"
    checkout.mkdir(parents=True)
    shared.mkdir(parents=True)

    with pytest.raises(ValueError, match="--add-dir"):
        load_codex_runtime(
            {
                "agent_id": "agent-cx",
                "codex": {
                    "cwd": str(checkout),
                    "sandbox": "workspace-write",
                    "extra_args": ["--add-dir", str(shared)],
                    "execution_context": {
                        "shared_workspace": {
                            "root": str(shared),
                        },
                    },
                },
            }
        )


def test_codex_diagnostics_writer_preserves_stdout_stderr_and_final_text(tmp_path: Path) -> None:
    diagnostics = _write_codex_diagnostics(
        codex_cfg={"diagnostics_dir": str(tmp_path / "diag")},
        cmd=["codex", "exec", "-"],
        cwd=tmp_path,
        stdout='{"type":"message","message":"hello"}\n',
        stderr="warning\n",
        final_text="hello",
        returncode=0,
        timeout=False,
        elapsed_sec=1.25,
    )

    meta = json.loads(Path(diagnostics["meta"]).read_text(encoding="utf-8"))
    assert meta["returncode"] == 0
    assert meta["timeout"] is False
    assert meta["event_count"] == 1
    assert Path(diagnostics["stdout"]).read_text(encoding="utf-8").strip()
    assert Path(diagnostics["stderr"]).read_text(encoding="utf-8") == "warning\n"
    assert Path(diagnostics["final_text"]).read_text(encoding="utf-8") == "hello"


def test_codex_stderr_stream_limiter_truncates_live_noise_once() -> None:
    limiter = _CodexStderrStreamLimiter(max_chars=5, notice="[truncated]")

    assert limiter.chunks("abc") == ["abc"]
    assert limiter.chunks("defgh") == ["de", "[truncated]"]
    assert limiter.chunks("ijk") == []


def test_compact_codex_result_for_transport_truncates_large_stderr_only() -> None:
    result = {
        "returncode": 0,
        "stdout": "ok",
        "stderr": "x" * 20000,
        "final_text": "done",
    }

    compacted = compact_codex_result_for_transport(result)

    assert compacted["stdout"] == "ok"
    assert compacted["stderr"].startswith("x" * 100)
    assert compacted["stderr_truncated"] is True
    assert compacted["stderr_original_chars"] == 20000
    assert compacted["final_text"] == "done"


def test_multimodal_envelope_serializes_and_normalizes() -> None:
    env = MultiModalEnvelope.text("hello", meta={"port": "out"})

    assert env.to_dict() == {
        "kind": "text",
        "encoding": "inline",
        "value": "hello",
        "meta": {"port": "out"},
        "mime": "text/plain",
    }
    assert normalize_envelope("hello").to_dict()["kind"] == "text"
    assert normalize_envelope({"a": 1}).mime == "application/json"


class _FakeCluster:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.sent: list[tuple[str, Any, float]] = []
        self.worker_configs: dict[str, WorkerConfig] = {}

    async def ensure_worker(self, worker: WorkerConfig) -> None:
        self.started.append(worker.agent_id)
        self.worker_configs[worker.agent_id] = worker

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


class _FailingThenOkCluster(_FakeCluster):
    async def run_single(
        self,
        worker_id: str,
        body: Any,
        *,
        timeout_sec: float = 600.0,
        _skip_skill_inject: bool = False,
    ) -> dict[str, Any]:
        self.sent.append((worker_id, body, timeout_sec))
        if len(self.sent) > 1:
            return {"type": "message", "from": worker_id, "body": {"ok": True, "recovered": True}}
        return {
            "type": "message",
            "from": worker_id,
            "body": {
                "ok": False,
                "codex": {
                    "returncode": 1,
                    "stderr": "stream disconnected before response.completed",
                    "final_text": "",
                    "timeout": False,
                },
            },
        }


class _TimeoutThenOkCluster(_FakeCluster):
    async def run_single(
        self,
        worker_id: str,
        body: Any,
        *,
        timeout_sec: float = 600.0,
        _skip_skill_inject: bool = False,
    ) -> dict[str, Any]:
        self.sent.append((worker_id, body, timeout_sec))
        if len(self.sent) > 1:
            return {"type": "message", "from": worker_id, "body": {"ok": True, "recovered": True}}
        return {
            "type": "message",
            "from": worker_id,
            "body": {
                "ok": False,
                "codex": {
                    "returncode": -9,
                    "stderr": "plugin warning noise",
                    "final_text": "partial progress",
                    "timeout": True,
                },
            },
        }


class _BackendTimeoutThenOkCluster(_FakeCluster):
    async def run_single(
        self,
        worker_id: str,
        body: Any,
        *,
        timeout_sec: float = 600.0,
        _skip_skill_inject: bool = False,
    ) -> dict[str, Any]:
        self.sent.append((worker_id, body, timeout_sec))
        if len(self.sent) > 1:
            return {"type": "message", "from": worker_id, "body": {"ok": True, "recovered": True}}
        raise asyncio.TimeoutError


class _RouteCluster(_FakeCluster):
    def __init__(self) -> None:
        super().__init__()
        self.parallel_tasks: list[list[tuple[str, Any]]] = []
        self.chain_tasks: list[list[tuple[str, Any]]] = []
        self.reduce_tasks: list[tuple[list[tuple[str, Any]], str, str]] = []

    async def run_parallel(
        self,
        tasks: list[tuple[str, Any]],
        *,
        timeout_sec: float = 600.0,
    ) -> dict[str, Any]:
        self.parallel_tasks.append(tasks)
        return {"route": "parallel", "tasks": tasks}

    async def run_chain(
        self,
        tasks: list[tuple[str, Any]],
        *,
        timeout_sec: float = 600.0,
    ) -> list[dict[str, Any]]:
        self.chain_tasks.append(tasks)
        return [{"route": "sequence", "tasks": tasks}]

    async def run_parallel_reduce(
        self,
        tasks: list[tuple[str, Any]],
        *,
        reduce_worker: str,
        reduce_prompt: str,
        timeout_sec: float = 600.0,
    ) -> dict[str, Any]:
        self.reduce_tasks.append((tasks, reduce_worker, reduce_prompt))
        return {"route": "parallel_reduce", "reduce_worker": reduce_worker}


class _RestartableCluster(_FakeCluster):
    def __init__(self) -> None:
        super().__init__()
        self.worker_cwds: dict[str, Path] = {}
        self.restarted: list[str] = []

    async def ensure_worker(self, worker: WorkerConfig) -> None:
        if worker.agent_id not in self.started:
            await super().ensure_worker(worker)
        self.worker_cwds[worker.agent_id] = worker.cwd

    async def restart_worker(self, worker: WorkerConfig) -> None:
        self.restarted.append(worker.agent_id)
        self.worker_cwds[worker.agent_id] = worker.cwd

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


class _SequencedCluster(_FakeCluster):
    def __init__(self) -> None:
        super().__init__()
        self._started_events: list[asyncio.Event] = []
        self._release_events: list[asyncio.Event] = []

    async def run_single(
        self,
        worker_id: str,
        body: Any,
        *,
        timeout_sec: float = 600.0,
        _skip_skill_inject: bool = False,
    ) -> dict[str, Any]:
        idx = len(self.sent)
        started = asyncio.Event()
        release = asyncio.Event()
        self._started_events.append(started)
        self._release_events.append(release)
        self.sent.append((worker_id, body, timeout_sec))
        started.set()
        await release.wait()
        return {"type": "message", "from": worker_id, "body": {"ok": True, "idx": idx}}

    async def wait_started(self, idx: int) -> None:
        while len(self._started_events) <= idx:
            await asyncio.sleep(0)
        await self._started_events[idx].wait()

    def release(self, idx: int) -> None:
        self._release_events[idx].set()


class _SharedClientCluster(_FakeCluster):
    def __init__(self) -> None:
        super().__init__()
        self.client = AgentTCPClient("graph-runtime", "127.0.0.1", 0)
        self._started_events: list[asyncio.Event] = []

    async def run_single(
        self,
        worker_id: str,
        body: Any,
        *,
        timeout_sec: float = 600.0,
        _skip_skill_inject: bool = False,
        meta: dict[str, Any] | None = None,
        stream_callback: Any = None,
    ) -> dict[str, Any]:
        started = asyncio.Event()
        self._started_events.append(started)
        self.sent.append((worker_id, body, timeout_sec))
        started.set()
        return await self.client.wait_for_message(
            expect_from=worker_id,
            timeout_sec=timeout_sec,
            stream_callback=stream_callback,
        )

    async def wait_started(self, idx: int) -> None:
        while len(self._started_events) <= idx:
            await asyncio.sleep(0)
        await self._started_events[idx].wait()

    async def emit_worker_message(self, worker_id: str, body: Any) -> None:
        await self.client._enqueue_received(
            {
                "type": "message",
                "from": worker_id,
                "body": body,
            }
        )


class _VerboseReplyCluster(_FakeCluster):
    async def run_single(
        self,
        worker_id: str,
        body: Any,
        *,
        timeout_sec: float = 600.0,
        _skip_skill_inject: bool = False,
    ) -> dict[str, Any]:
        self.sent.append((worker_id, body, timeout_sec))
        return {
            "type": "message",
            "from": worker_id,
            "body": {
                "ok": True,
                "codex": {
                    "final_text": "submitted report through workspace API",
                    "stdout": "raw jsonl debug stream",
                    "stderr": "diagnostic warning",
                },
                "adapter": {"debug": "drop-me"},
            },
        }


@pytest.mark.asyncio
async def test_graph_runtime_lazy_starts_and_reuses_agent_node() -> None:
    cluster = _FakeCluster()
    node = AgentNode(node_id="node-a", cwd=Path("."), timeout_sec=42.0)

    async with GraphRuntime(cluster) as runtime:
        first = await runtime.ensure_agent(node)
        second = await runtime.ensure_agent(node)
        reply = await runtime.send_agent_message(node, {"prompt": "next"})

    assert first is second
    assert cluster.started == ["node-a"]
    assert cluster.sent == [("node-a", {"prompt": "next"}, 42.0)]
    assert first.messages_sent == 1
    assert reply["agent_id"] == "node-a"
    assert reply["node_id"] == "node-a"
    assert reply["said"] == json.dumps({"ok": True}, ensure_ascii=False)
    assert len(runtime.agent_utterances) == 1


@pytest.mark.asyncio
async def test_graph_runtime_injects_run_prompt_once_per_agent_run() -> None:
    cluster = _FakeCluster()
    node = AgentNode(
        node_id="node-a",
        cwd=Path("."),
        timeout_sec=42.0,
        run_prompt="Follow the per-run contract.",
    )

    async with GraphRuntime(cluster) as runtime:
        await runtime.send_agent_message(node, {"prompt": "first task"})
        await runtime.send_agent_message(node, {"prompt": "second task"})
        runtime.reset_run_prompt_injections()
        await runtime.send_agent_message(node, {"prompt": "new run task"})

    assert cluster.sent[0] == (
        "node-a",
        {"prompt": "# Agent Run Prompt\n\nFollow the per-run contract.\n\n---\n\nfirst task"},
        42.0,
    )
    assert cluster.sent[1] == ("node-a", {"prompt": "second task"}, 42.0)
    assert cluster.sent[2] == (
        "node-a",
        {"prompt": "# Agent Run Prompt\n\nFollow the per-run contract.\n\n---\n\nnew run task"},
        42.0,
    )


@pytest.mark.asyncio
async def test_graph_runtime_injects_run_prompt_independently_per_agent() -> None:
    cluster = _FakeCluster()
    node_a = AgentNode(node_id="node-a", cwd=Path("."), run_prompt="A runtime rules.")
    node_b = AgentNode(node_id="node-b", cwd=Path("."), run_prompt="B runtime rules.")

    async with GraphRuntime(cluster) as runtime:
        await runtime.send_agent_message(node_a, {"prompt": "work a"})
        await runtime.send_agent_message(node_b, {"prompt": "work b"})

    assert cluster.sent[0][1] == {
        "prompt": "# Agent Run Prompt\n\nA runtime rules.\n\n---\n\nwork a"
    }
    assert cluster.sent[1][1] == {
        "prompt": "# Agent Run Prompt\n\nB runtime rules.\n\n---\n\nwork b"
    }


@pytest.mark.asyncio
async def test_graph_runtime_queues_messages_until_agent_is_idle() -> None:
    cluster = _SequencedCluster()
    node = AgentNode(node_id="node-a", cwd=Path("."), timeout_sec=42.0)
    runtime = GraphRuntime(cluster)

    first_task = asyncio.create_task(runtime.send_agent_message(node, {"prompt": "first"}))
    await cluster.wait_started(0)

    queued = await runtime.send_agent_message(
        node,
        {"prompt": "second"},
        source_node_id="node-b",
        source_agent_id="agent-b",
    )

    assert queued["type"] == "graph_message_queued"
    assert queued["queue_size"] == 1
    assert runtime.agent_message_queues["node-a"][0].body == {"prompt": "second"}
    assert runtime.instances["node-a"].state == "waiting_for_reply"

    cluster.release(0)
    first_reply = await first_task
    assert first_reply["said"] == json.dumps({"ok": True, "idx": 0}, ensure_ascii=False)
    assert runtime.instances["node-a"].state == "idle"

    await runtime.tick()
    await cluster.wait_started(1)
    assert cluster.sent[1] == ("node-a", {"prompt": "second"}, 42.0)
    assert runtime.agent_message_queues["node-a"] == []

    cluster.release(1)
    for _ in range(20):
        await asyncio.sleep(0)
        pending = runtime.pending_messages[queued["message_id"]]
        if pending.status == "completed":
            break

    pending = runtime.pending_messages[queued["message_id"]]
    assert pending.status == "completed"
    assert pending.source_node_id == "node-b"
    assert pending.receipt is not None
    assert pending.receipt["agent_id"] == "node-a"
    assert pending.receipt["node_id"] == "node-a"
    assert pending.receipt["message_id"] == queued["message_id"]
    assert pending.receipt["said"] == json.dumps({"ok": True, "idx": 1}, ensure_ascii=False)
    queue_updates = [
        event
        for event in runtime.agent_stream_events
        if event.get("kind") == "queue.updated"
        and event.get("message_id") == queued["message_id"]
    ]
    assert queue_updates[-1]["status"] == "completed"
    assert queue_updates[-1]["last_error"] is None
    assert runtime.instances["node-a"].messages_sent == 2
    states = [entry["state"] for entry in runtime.instances["node-a"].state_history]
    assert "starting" in states
    assert "idle" in states
    assert "dispatching" in states
    assert "running" in states
    assert "waiting_for_reply" in states
    assert "processing_reply" in states


@pytest.mark.asyncio
async def test_graph_runtime_completes_concurrent_worker_replies_out_of_order() -> None:
    cluster = _SharedClientCluster()
    node_a = AgentNode(node_id="node-a", agent_id="agent-a", cwd=Path("."), timeout_sec=1.0)
    node_b = AgentNode(node_id="node-b", agent_id="agent-b", cwd=Path("."), timeout_sec=1.0)
    runtime = GraphRuntime(cluster)

    task_a = asyncio.create_task(runtime.send_agent_message(node_a, {"prompt": "a"}))
    task_b = asyncio.create_task(runtime.send_agent_message(node_b, {"prompt": "b"}))
    await cluster.wait_started(1)

    await cluster.emit_worker_message(
        "agent-b",
        {
            "type": "agent.stream",
            "event": {
                "kind": "part.delta",
                "node_id": "node-b",
                "agent_id": "agent-b",
                "delta": "b-progress",
            },
        },
    )
    await cluster.emit_worker_message("agent-b", {"ok": True, "text": "b final"})
    await cluster.emit_worker_message(
        "agent-a",
        {
            "type": "agent.stream",
            "event": {
                "kind": "part.delta",
                "node_id": "node-a",
                "agent_id": "agent-a",
                "delta": "a-progress",
            },
        },
    )
    await cluster.emit_worker_message("agent-a", {"ok": True, "text": "a final"})

    reply_a, reply_b = await asyncio.gather(task_a, task_b)

    assert reply_a["said"] == "a final"
    assert reply_b["said"] == "b final"
    assert runtime.instances["node-a"].state == "idle"
    assert runtime.instances["node-b"].state == "idle"
    assert runtime.instances["node-a"].busy_count == 0
    assert runtime.instances["node-b"].busy_count == 0
    assert runtime.instances["node-a"].messages_sent == 1
    assert runtime.instances["node-b"].messages_sent == 1
    deltas = {
        (event.get("node_id"), event.get("delta"))
        for event in runtime.agent_stream_events
        if event.get("kind") == "part.delta"
    }
    assert ("node-a", "a-progress") in deltas
    assert ("node-b", "b-progress") in deltas
    completed_nodes = {
        event.get("node_id")
        for event in runtime.agent_stream_events
        if event.get("kind") == "message.completed"
    }
    assert {"node-a", "node-b"} <= completed_nodes


@pytest.mark.asyncio
async def test_graph_runtime_keeps_agent_idle_after_worker_ok_false() -> None:
    cluster = _FailingThenOkCluster()
    node = AgentNode(node_id="node-a", cwd=Path("."), timeout_sec=42.0)
    runtime = GraphRuntime(cluster)

    with pytest.raises(RuntimeError, match="stream disconnected"):
        await runtime.send_agent_message(node, {"prompt": "next"})

    inst = runtime.instances["node-a"]
    assert inst.state == "idle"
    assert "stream disconnected" in (inst.last_error or "")
    status_events = [event for event in runtime.agent_stream_events if event.get("kind") == "status"]
    assert status_events[-1]["agent_state"] == "idle"
    assert status_events[-1]["busy_count"] == 0
    assert "stream disconnected" in status_events[-1]["last_error"]

    recovered = await runtime.send_agent_message(node, {"prompt": "retry"})
    assert recovered["said"] == json.dumps({"ok": True, "recovered": True}, ensure_ascii=False)
    assert runtime.instances["node-a"].state == "idle"
    assert cluster.sent == [
        ("node-a", {"prompt": "next"}, 42.0),
        ("node-a", {"prompt": "retry"}, 42.0),
    ]


@pytest.mark.asyncio
async def test_graph_runtime_keeps_agent_idle_after_structured_worker_timeout() -> None:
    cluster = _TimeoutThenOkCluster()
    node = AgentNode(node_id="node-a", cwd=Path("."), timeout_sec=42.0)
    runtime = GraphRuntime(cluster)

    with pytest.raises(RuntimeError, match="codex timed out"):
        await runtime.send_agent_message(node, {"prompt": "next"})

    inst = runtime.instances["node-a"]
    assert inst.state == "idle"
    assert inst.last_error == "agent reply failed: codex timed out"
    status_events = [event for event in runtime.agent_stream_events if event.get("kind") == "status"]
    assert status_events[-1]["agent_state"] == "idle"
    assert status_events[-1]["busy_count"] == 0
    assert status_events[-1]["last_error"] == "agent reply failed: codex timed out"

    recovered = await runtime.send_agent_message(node, {"prompt": "retry"})
    assert recovered["said"] == json.dumps({"ok": True, "recovered": True}, ensure_ascii=False)
    assert runtime.instances["node-a"].state == "idle"
    assert cluster.sent == [
        ("node-a", {"prompt": "next"}, 42.0),
        ("node-a", {"prompt": "retry"}, 42.0),
    ]


@pytest.mark.asyncio
async def test_graph_runtime_queued_worker_failure_emits_terminal_stream_update() -> None:
    cluster = _TimeoutThenOkCluster()
    node = AgentNode(node_id="node-a", cwd=Path("."), timeout_sec=42.0)
    runtime = GraphRuntime(cluster)
    await runtime.ensure_agent(node)

    pending = runtime.queue_agent_message(node, {"prompt": "queued"})
    await runtime.tick()
    for _ in range(20):
        await asyncio.sleep(0)
        if runtime.pending_messages[pending.message_id].status == "failed":
            break

    completed = runtime.pending_messages[pending.message_id]
    assert completed.status == "failed"
    assert completed.error == "agent reply failed: codex timed out"
    queue_updates = [
        event
        for event in runtime.agent_stream_events
        if event.get("kind") == "queue.updated"
        and event.get("message_id") == pending.message_id
    ]
    assert queue_updates[-1]["status"] == "failed"
    assert queue_updates[-1]["last_error"] == "agent reply failed: codex timed out"


@pytest.mark.asyncio
async def test_graph_runtime_can_retry_after_backend_timeout() -> None:
    cluster = _BackendTimeoutThenOkCluster()
    node = AgentNode(node_id="node-a", cwd=Path("."), timeout_sec=42.0)
    runtime = GraphRuntime(cluster)

    with pytest.raises(asyncio.TimeoutError):
        await runtime.send_agent_message(node, {"prompt": "slow"})

    inst = runtime.instances["node-a"]
    assert inst.state == "timed_out"
    assert inst.can_accept_message is True
    status_events = [event for event in runtime.agent_stream_events if event.get("kind") == "status"]
    assert status_events[-1]["agent_state"] == "timed_out"
    assert status_events[-1]["busy_count"] == 0

    recovered = await runtime.send_agent_message(node, {"prompt": "retry"})
    assert recovered["said"] == json.dumps({"ok": True, "recovered": True}, ensure_ascii=False)
    assert runtime.instances["node-a"].state == "idle"
    assert cluster.sent == [
        ("node-a", {"prompt": "slow"}, 42.0),
        ("node-a", {"prompt": "retry"}, 42.0),
    ]


@pytest.mark.asyncio
async def test_worker_reply_is_reduced_to_framework_private_utterance() -> None:
    cluster = _VerboseReplyCluster()
    node = AgentNode(node_id="node-a", agent_id="worker-a", cwd=Path("."))
    runtime = GraphRuntime(cluster)

    receipt = await runtime.send_agent_message(
        node,
        {"prompt": "do work", "task_id": "task-1"},
        timeout_sec=7.0,
        source_node_id="node-top",
    )

    assert receipt["agent_id"] == "worker-a"
    assert receipt["node_id"] == "node-a"
    assert receipt["task_id"] == "task-1"
    assert receipt["said"] == "submitted report through workspace API"
    assert "stdout" not in json.dumps(receipt)
    assert "stderr" not in json.dumps(receipt)
    assert runtime.agent_utterances[receipt["utterance_id"]].said == receipt["said"]
    assert runtime.private_agent_utterances(task_id="task-1") == [receipt]
    assert runtime.status_snapshot()["recent_events"] == []
    assert [event.event_type for event in runtime.events] == []


@pytest.mark.asyncio
async def test_graph_runtime_persists_agent_and_framework_message_io(tmp_path: Path) -> None:
    cluster = _FakeCluster()
    source = AgentNode(node_id="planner", agent_id="agent-planner", cwd=Path("."))
    target = AgentNode(node_id="coder", agent_id="agent-coder", cwd=Path("."))
    journal_path = tmp_path / "shared" / "logs" / "message_journal.jsonl"
    runtime = GraphRuntime(cluster, message_journal_path=journal_path)

    direct = await runtime.send_agent_message(source, {"prompt": "plan"})
    assert direct["agent_id"] == "agent-planner"

    await runtime.create_outgoing_batch(source, [target], batch_id="batch-1")
    staged = runtime.stage_outgoing_message(
        "batch-1",
        target,
        {"prompt": "implement"},
    )

    assert staged["ready_to_dispatch"] is True
    assert journal_path.is_file()
    lines = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    record_types = [item["record_type"] for item in lines]
    assert record_types == [
        "framework.message.sent",
        "agent.reply.received",
        "agent.outgoing.staged",
        "framework.message.queued",
    ]
    assert lines[0]["payload"] == {"prompt": "plan"}
    assert lines[1]["payload"]["said"] == json.dumps({"ok": True}, ensure_ascii=False)
    assert lines[2]["sender"]["agent_id"] == "agent-planner"
    assert lines[2]["metadata"]["target_node_id"] == "coder"
    assert lines[3]["receiver"]["agent_id"] == "agent-coder"
    assert runtime.status_snapshot()["run"]["message_journal"]["path"] == str(journal_path)
    assert runtime.status_snapshot()["run"]["message_journal"]["record_count"] == 4
    assert runtime.message_journal == lines


def test_complex_blueprint_runtime_journal_covers_fanout_join_retry_and_workspace(
    tmp_path: Path,
) -> None:
    fixture = json.loads(
        Path("docs/blueprints/complex_test_blueprint.json").read_text(encoding="utf-8")
    )
    graph = graph_definition_from_dict(fixture["graph"])
    workspace = WorkspaceManifest("ws-complex", tmp_path)
    runtime = GraphRuntime(_FakeCluster(), workspace=workspace)
    control = GraphRuntimeControlPlane(runtime, graph)
    start_plan = TopAgentStartPlan.from_dict(fixture["top_agent_start_plan"])

    started = control.handle_request(
        {"command": "run.start", "args": {"plan": start_plan.to_dict()}}
    )
    assert started["ok"] is True
    requirements_body = runtime.status_snapshot()["queues"]["by_agent"]["requirements"][0]["body"]
    requirements_batch_id = requirements_body["context"]["framework_context"]["message_envelope"][
        "outgoing_batch_id"
    ]

    for target in ("risk_scan", "architecture", "test_planner"):
        dispatched = control.handle_request(
            {
                "command": "agent.dispatch",
                "args": {
                    "source_node_id": "requirements",
                    "target_node_id": target,
                    "batch_id": requirements_batch_id,
                    "body": {"prompt": f"complex fixture work for {target}"},
                },
            }
        )
    assert dispatched["dispatch"]["ready_to_dispatch"] is True
    assert len(runtime.agent_message_queues["risk_scan"]) == 1
    assert len(runtime.agent_message_queues["architecture"]) == 1
    assert len(runtime.agent_message_queues["test_planner"]) == 1

    implementation_join = runtime.create_join_barrier(
        required_sources=["backend_impl", "frontend_impl"],
        target_node=graph.agent_nodes["review"],
        join_id="join-implementation-ready",
    )
    runtime.submit_join_contribution(
        implementation_join.join_id,
        "backend_impl",
        source_agent_id="agent-backend-impl",
        accepted_changesets=[{"changeset_id": "backend-cs"}],
        artifacts=[{"path": "backend/build.log"}],
        reports=[{"path": "backend/report.md"}],
    )
    ready = runtime.submit_join_contribution(
        implementation_join.join_id,
        "frontend_impl",
        source_agent_id="agent-frontend-impl",
        accepted_changesets=[{"changeset_id": "frontend-cs"}],
        artifacts=[{"path": "frontend/build.log"}],
        reports=[{"path": "frontend/report.md"}],
    )
    assert ready["ready"] is True
    review_aggregate = runtime.agent_message_queues["review"][0].body["aggregate"]
    assert review_aggregate["accepted_changesets"] == [
        {"changeset_id": "backend-cs"},
        {"changeset_id": "frontend-cs"},
    ]

    test_join = runtime.create_join_barrier(
        required_sources=["unit_tests", "e2e_tests"],
        target_node=graph.agent_nodes["integration"],
        join_id="join-test-ready",
    )
    runtime.submit_join_contribution(
        test_join.join_id,
        "unit_tests",
        test_results=[{"suite": "unit", "status": "passed"}],
    )
    runtime.submit_join_contribution(
        test_join.join_id,
        "e2e_tests",
        test_results=[{"suite": "e2e", "status": "passed"}],
    )
    integration_aggregate = runtime.agent_message_queues["integration"][0].body["aggregate"]
    assert integration_aggregate["test_results"] == [
        {"suite": "unit", "status": "passed"},
        {"suite": "e2e", "status": "passed"},
    ]

    review_batch = asyncio.run(
        runtime.create_outgoing_batch(
            graph.agent_nodes["review"],
            [graph.agent_nodes["patch"]],
            batch_id="review-failed",
        )
    )
    assert review_batch.batch_id == "review-failed"
    runtime.stage_outgoing_message(
        "review-failed",
        graph.agent_nodes["patch"],
        {"prompt": "Patch review findings and resubmit."},
    )

    retry_batch = asyncio.run(
        runtime.create_outgoing_batch(
            graph.agent_nodes["failure_analysis"],
            [graph.agent_nodes["patch"]],
            batch_id="integration-retry",
        )
    )
    assert retry_batch.batch_id == "integration-retry"
    runtime.stage_outgoing_message(
        "integration-retry",
        graph.agent_nodes["patch"],
        {"prompt": "Retry from integration failure attribution."},
    )

    journal_path = tmp_path / "shared" / "logs" / "message_journal.jsonl"
    records = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    record_types = [record["record_type"] for record in records]
    assert record_types.count("agent.outgoing.staged") == 5
    assert record_types.count("framework.message.queued") == 8
    assert any(record.get("message_id") == "join-msg-join-implementation-ready" for record in records)
    assert any(record.get("message_id") == "join-msg-join-test-ready" for record in records)
    assert workspace.run["message_journal"]["path"] == str(journal_path)
    assert workspace.run["message_journal"]["record_count"] == len(records)
    assert runtime.status_snapshot()["workspace"]["workspace_id"] == "ws-complex"


def test_complex_blueprint_executes_from_top_plan_to_archive(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-complex", code_mode="project_reference")
    fixture = json.loads(
        Path("docs/blueprints/complex_test_blueprint.json").read_text(encoding="utf-8")
    )
    graph = graph_definition_from_dict(fixture["graph"])
    runtime = GraphRuntime(_FakeCluster(), archive_manager=manager, archive_run=run)
    control = GraphRuntimeControlPlane(runtime, graph)
    start_plan = TopAgentStartPlan.from_dict(fixture["top_agent_start_plan"])

    result = control.handle_request(
        {
            "command": "run.execute_fixture",
            "args": {
                "plan": start_plan.to_dict(),
                "runtime_scenarios": fixture["runtime_scenarios"],
                "archive": True,
            },
        }
    )

    assert result["ok"] is True
    assert result["execution"]["status"] == "completed"
    assert result["end"]["final_status"] == "success"
    assert result["end"]["archived"] is True
    executed = result["execution"]["executed_nodes"]
    assert executed[:4] == ["requirements", "risk_scan", "security_review", "architecture"]
    assert executed.count("patch") == 2
    assert executed.count("integration") == 2
    assert executed[-3:] == ["summary", "event_monitor", "workspace_state"]
    route_types = [item["event_type"] for item in result["execution"]["route_history"]]
    assert route_types == [
        "ConditionalRouteTaken",
        "ConditionalRouteTaken",
        "RetryRouteTaken",
        "RetryRouteTaken",
    ]
    assert all(not messages for messages in result["status"]["queues"]["by_agent"].values())
    assert all(
        message["status"] == "completed"
        for message in result["status"]["queues"]["pending_messages"].values()
    )

    archive_path = Path(result["end"]["summary"]["archive_path"])
    report_path = Path(result["end"]["summary"]["final_report_path"])
    journal_path = archive_path / "shared" / "logs" / "message_journal.jsonl"
    assert report_path == archive_path / "shared" / "reports" / "final_report.json"
    assert report_path.is_file()
    assert journal_path.is_file()
    journal_records = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    record_types = [record["record_type"] for record in journal_records]
    assert "framework.message.sent" in record_types
    assert "framework.message.queued" in record_types
    assert "agent.outgoing.staged" in record_types
    assert "agent.reply.received" in record_types
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["final_status"] == "success"
    assert report["status_snapshot"]["run"]["message_journal"]["record_count"] == len(journal_records)
    assert "RunArchiveIndexed" in [event["event_type"] for event in result["status"]["recent_events"]]


@pytest.mark.asyncio
async def test_graph_runtime_tick_dispatches_only_one_queued_message_per_frame() -> None:
    cluster = _SequencedCluster()
    node = AgentNode(node_id="node-a", cwd=Path("."))
    runtime = GraphRuntime(cluster)
    await runtime.ensure_agent(node)

    first = runtime.queue_agent_message(node, {"prompt": "first"})
    second = runtime.queue_agent_message(node, {"prompt": "second"})

    await runtime.tick()
    await cluster.wait_started(0)

    assert cluster.sent == [("node-a", {"prompt": "first"}, 1800.0)]
    assert runtime.agent_message_queues["node-a"][0].message_id == second.message_id

    await runtime.tick()
    assert len(cluster.sent) == 1

    cluster.release(0)
    for _ in range(20):
        await asyncio.sleep(0)
        if runtime.pending_messages[first.message_id].status == "completed":
            break

    await runtime.tick()
    await cluster.wait_started(1)

    assert cluster.sent[1] == ("node-a", {"prompt": "second"}, 1800.0)
    cluster.release(1)


@pytest.mark.asyncio
async def test_graph_runtime_stages_outgoing_messages_until_all_targets_are_ready() -> None:
    cluster = _FakeCluster()
    source = AgentNode(node_id="agent-a", agent_id="worker-a", cwd=Path("."))
    target_b = AgentNode(node_id="agent-b", agent_id="worker-b", cwd=Path("."))
    target_c = AgentNode(node_id="agent-c", agent_id="worker-c", cwd=Path("."))
    runtime = GraphRuntime(cluster)

    batch = await runtime.create_outgoing_batch(
        source,
        [target_b, target_c],
        batch_id="batch-1",
    )

    first = runtime.stage_outgoing_message(
        "batch-1",
        target_b,
        {"prompt": "initial for b"},
    )
    overwrite = runtime.stage_outgoing_message(
        "batch-1",
        target_b,
        {"prompt": "revised for b"},
    )

    assert first["ready_to_dispatch"] is False
    assert first["remaining_targets"] == ["agent-c"]
    assert overwrite["overwritten"] is True
    assert runtime.outgoing_batches["batch-1"].status == "staging"
    assert runtime.agent_message_queues["agent-b"] == []
    assert batch.staged_messages["agent-b"].body == {"prompt": "revised for b"}

    final = runtime.stage_outgoing_message("batch-1", target_c, {"prompt": ""})

    assert final["ready_to_dispatch"] is True
    assert runtime.outgoing_batches["batch-1"].status == "dispatched"
    assert len(runtime.agent_message_queues["agent-b"]) == 1
    assert len(runtime.agent_message_queues["agent-c"]) == 1
    assert runtime.agent_message_queues["agent-b"][0].body == {"prompt": "revised for b"}
    assert runtime.agent_message_queues["agent-c"][0].body == {"prompt": ""}
    assert runtime.agent_message_queues["agent-b"][0].source_agent_id == "worker-a"
    assert [event.event_type for event in runtime.events] == [
        "AgentOutgoingBatchCreated",
        "AgentMessageStaged",
        "AgentMessageStaged",
        "AgentMessageStaged",
        "AgentMessageQueued",
        "AgentMessageQueued",
        "AgentOutgoingBatchDispatched",
    ]


@pytest.mark.asyncio
async def test_graph_runtime_empty_string_or_zero_marks_target_no_op_without_queueing() -> None:
    source = AgentNode(node_id="agent-a", agent_id="worker-a", cwd=Path("."))
    target_b = AgentNode(node_id="agent-b", agent_id="worker-b", cwd=Path("."))
    target_c = AgentNode(node_id="agent-c", agent_id="worker-c", cwd=Path("."))
    runtime = GraphRuntime(_FakeCluster())

    await runtime.create_outgoing_batch(source, [target_b, target_c], batch_id="batch-1")
    first = runtime.stage_outgoing_message("batch-1", target_b, "")
    final = runtime.stage_outgoing_message("batch-1", target_c, 0)

    assert first["no_op"] is True
    assert final["ready_to_dispatch"] is True
    assert runtime.outgoing_batches["batch-1"].status == "dispatched"
    assert runtime.outgoing_batches["batch-1"].no_op_target_node_ids == ["agent-b", "agent-c"]
    assert runtime.outgoing_batches["batch-1"].dispatched_message_ids == []
    assert runtime.agent_message_queues["agent-b"] == []
    assert runtime.agent_message_queues["agent-c"] == []
    assert [
        event.event_type for event in runtime.events
        if event.event_type in {"AgentOutgoingTargetNoOp", "AgentMessageQueued"}
    ] == ["AgentOutgoingTargetNoOp", "AgentOutgoingTargetNoOp"]

    await runtime.create_outgoing_batch(source, [target_b], batch_id="batch-2")
    false_payload = runtime.stage_outgoing_message("batch-2", target_b, False)

    assert false_payload["no_op"] is False
    assert runtime.outgoing_batches["batch-2"].no_op_target_node_ids == []
    assert len(runtime.agent_message_queues["agent-b"]) == 1


@pytest.mark.asyncio
async def test_graph_runtime_rejects_outgoing_message_to_unrequired_target() -> None:
    cluster = _FakeCluster()
    source = AgentNode(node_id="agent-a", cwd=Path("."))
    target_b = AgentNode(node_id="agent-b", cwd=Path("."))
    target_c = AgentNode(node_id="agent-c", cwd=Path("."))
    runtime = GraphRuntime(cluster)

    await runtime.create_outgoing_batch(source, [target_b], batch_id="batch-1")

    with pytest.raises(ValueError, match="not required"):
        runtime.stage_outgoing_message("batch-1", target_c, {"prompt": "nope"})


@pytest.mark.asyncio
async def test_graph_runtime_rejects_required_target_outside_allowed_connections() -> None:
    cluster = _FakeCluster()
    source = AgentNode(node_id="agent-a", cwd=Path("."))
    target_b = AgentNode(node_id="agent-b", cwd=Path("."))
    target_c = AgentNode(node_id="agent-c", cwd=Path("."))
    runtime = GraphRuntime(cluster)

    with pytest.raises(ValueError, match="not reachable"):
        await runtime.create_outgoing_batch(
            source,
            [target_b, target_c],
            allowed_targets=[target_b],
        )


@pytest.mark.asyncio
async def test_graph_runtime_reminds_idle_source_about_remaining_outgoing_targets() -> None:
    cluster = _FakeCluster()
    source = AgentNode(node_id="agent-a", cwd=Path("."))
    target_b = AgentNode(node_id="agent-b", cwd=Path("."))
    target_c = AgentNode(node_id="agent-c", cwd=Path("."))
    runtime = GraphRuntime(cluster)

    await runtime.create_outgoing_batch(source, [target_b, target_c], batch_id="batch-1")
    runtime.stage_outgoing_message("batch-1", target_b, {"prompt": "for b"})

    await runtime.tick()
    await runtime.tick()

    reminders = [
        event
        for event in runtime.events
        if event.event_type == "AgentOutgoingTargetsReminder"
    ]
    assert len(reminders) == 1
    assert reminders[0].payload["remaining_targets"] == ["agent-c"]
    assert reminders[0].payload["required_outgoing_targets"] == ["agent-b", "agent-c"]


@pytest.mark.asyncio
async def test_graph_runtime_reminds_idle_source_about_required_script_calls() -> None:
    graph = graph_definition_from_dict(
        {
            "agent_nodes": {
                "planner": {"agent_id": "agent-planner"},
                "writer": {"agent_id": "agent-writer"},
            },
            "script_nodes": {
                "format": {
                    "script_id": "score.py:format_score",
                    "module_path": "score.py",
                    "function_name": "format_score",
                    "title": "Format score",
                    "description": "Format the score payload.",
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

    batch = await runtime.create_outgoing_batch_from_graph(graph, "planner", batch_id="batch-script")
    assert batch.script_calls["format"]["status"] == "pending"

    await runtime.tick()
    await runtime.tick()

    reminders = [
        event for event in runtime.events if event.event_type == "AgentScriptCallReminder"
    ]
    assert len(reminders) == 1
    reminder = reminders[0]
    assert reminder.payload["batch_id"] == "batch-script"
    assert reminder.payload["required_script_calls"][0]["function_name"] == "format_score"
    assert reminder.payload["required_script_calls"][0]["description"] == "Format the score payload."
    pending = runtime.pending_messages[reminder.payload["message_id"]]
    assert pending.body["type"] == "blueprint_script_call_reminder"
    envelope = pending.body["context"]["framework_context"]["message_envelope"]
    assert envelope["outgoing_batch_id"] == "batch-script"
    assert envelope["required_script_calls"][0]["script_node_id"] == "format"


@pytest.mark.asyncio
async def test_graph_runtime_prompts_idle_agent_summary_after_threshold(monkeypatch) -> None:
    now = {"value": 1000.0}
    monkeypatch.setattr("multi_agent_tcp.graph_runtime.time.monotonic", lambda: now["value"])
    runtime = GraphRuntime(_FakeCluster())
    node = AgentNode(node_id="agent-a", agent_id="worker-a", cwd=Path("."))

    await runtime.send_agent_message(node, {"prompt": "do work"})
    inst = runtime.instances["agent-a"]
    assert inst.has_received_flow is True
    assert inst.task_status == "working"

    now["value"] += 20.0
    await runtime.tick()
    assert not [event for event in runtime.events if event.event_type == "AgentSummaryRequested"]

    now["value"] += 11.0
    await runtime.tick()

    summary_events = [
        event for event in runtime.events if event.event_type == "AgentSummaryRequested"
    ]
    assert len(summary_events) == 1
    queued = runtime.pending_messages[summary_events[0].payload["message_id"]]
    assert queued.body["type"] == "framework_summary_request"
    assert "your own current task" in queued.body["prompt"]


@pytest.mark.asyncio
async def test_graph_runtime_idle_timer_resets_when_new_work_arrives(monkeypatch) -> None:
    now = {"value": 2000.0}
    monkeypatch.setattr("multi_agent_tcp.graph_runtime.time.monotonic", lambda: now["value"])
    runtime = GraphRuntime(_FakeCluster())
    node = AgentNode(node_id="agent-a", agent_id="worker-a", cwd=Path("."))

    await runtime.send_agent_message(node, {"prompt": "first"})
    runtime.record_agent_task_status(
        "agent-a",
        agent_id="worker-a",
        status="completed",
        summary="first done",
    )
    assert runtime.instances["agent-a"].task_status == "completed"

    now["value"] += 20.0
    await runtime.send_agent_message(node, {"prompt": "second"})
    inst = runtime.instances["agent-a"]
    assert inst.task_status == "working"
    assert inst.summary_prompted_at is None

    now["value"] += 20.0
    await runtime.tick()
    assert not [event for event in runtime.events if event.event_type == "AgentSummaryRequested"]

    now["value"] += 11.0
    await runtime.tick()
    assert [event for event in runtime.events if event.event_type == "AgentSummaryRequested"]


@pytest.mark.asyncio
async def test_graph_runtime_ring_agent_waits_for_circulation_counts_before_summary(monkeypatch) -> None:
    now = {"value": 3000.0}
    monkeypatch.setattr("multi_agent_tcp.graph_runtime.time.monotonic", lambda: now["value"])
    graph = GraphDefinition(
        agent_nodes={
            "a": AgentNode(node_id="a", agent_id="worker-a", cwd=Path(".")),
            "b": AgentNode(node_id="b", agent_id="worker-b", cwd=Path(".")),
        },
        edges=[
            GraphEdge("a", "b", edge_type="exec"),
            GraphEdge("b", "a", edge_type="exec"),
        ],
    )
    runtime = GraphRuntime(_FakeCluster())
    runtime.configure_completion_tracking(graph)

    await runtime.send_agent_message(graph.agent_nodes["a"], {"prompt": "ring work"})
    now["value"] += 31.0
    await runtime.tick()
    assert not [event for event in runtime.events if event.event_type == "AgentSummaryRequested"]

    for counts in runtime._agent_ring_circulation_counts.values():
        for ring_id in list(counts):
            counts[ring_id] = 0
    await runtime.tick()

    summary_events = [
        event for event in runtime.events if event.event_type == "AgentSummaryRequested"
    ]
    assert len(summary_events) == 1
    assert summary_events[0].node_id == "a"


@pytest.mark.asyncio
async def test_graph_runtime_ready_for_top_agent_summary_after_all_agents_terminal() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "a": AgentNode(node_id="a", agent_id="worker-a", cwd=Path(".")),
            "b": AgentNode(node_id="b", agent_id="worker-b", cwd=Path(".")),
        },
    )
    runtime = GraphRuntime(_FakeCluster())
    runtime.configure_completion_tracking(graph)

    await runtime.send_agent_message(graph.agent_nodes["a"], {"prompt": "a"})
    await runtime.send_agent_message(graph.agent_nodes["b"], {"prompt": "b"})
    runtime.record_agent_task_status("a", agent_id="worker-a", status="completed", summary="a done")
    runtime.record_agent_task_status("b", agent_id="worker-b", status="completed", summary="b done")

    snapshot = runtime.status_snapshot(graph=graph)
    assert snapshot["run"]["ready_for_top_agent_summary"] is True
    assert any(event.event_type == "RunReadyForTopAgentSummary" for event in runtime.events)


def test_graph_runtime_join_barrier_wait_all_aggregates_source_metadata() -> None:
    runtime = GraphRuntime(_FakeCluster())
    target = AgentNode(node_id="reviewer", agent_id="worker-reviewer", cwd=Path("."))

    barrier = runtime.create_join_barrier(
        required_sources=["coder", "tester"],
        target_node=target,
        policy="wait-all",
        join_id="join-1",
    )

    first = runtime.submit_join_contribution(
        "join-1",
        "coder",
        source_agent_id="worker-coder",
        result={"summary": "implemented"},
        accepted_changesets=[{"changeset_id": "cs-1", "files": ["src/a.py"]}],
        artifacts=[{"path": "artifacts/build.log"}],
        reports=[{"path": "reports/coder.md"}],
        test_results=[{"name": "unit", "status": "passed"}],
        metadata={"risk": "low"},
    )
    final = runtime.submit_join_contribution(
        "join-1",
        "tester",
        source_agent_id="worker-tester",
        result={"summary": "verified"},
        reports=[{"path": "reports/tester.md"}],
    )

    assert first["ready"] is False
    assert first["missing_sources"] == ["tester"]
    assert final["ready"] is True
    assert barrier.status == "ready"
    assert barrier.final_reason == "all_sources_submitted"
    aggregate = final["aggregate"]
    assert aggregate["accepted_changesets"] == [{"changeset_id": "cs-1", "files": ["src/a.py"]}]
    assert aggregate["artifacts"] == [{"path": "artifacts/build.log"}]
    assert aggregate["reports"] == [
        {"path": "reports/coder.md"},
        {"path": "reports/tester.md"},
    ]
    assert aggregate["test_results"] == [{"name": "unit", "status": "passed"}]
    assert aggregate["source_metadata"] == {"coder": {"risk": "low"}}
    assert barrier.aggregate_message_id == "join-msg-join-1"
    assert runtime.agent_message_queues["reviewer"][0].body["type"] == "join_aggregate"
    assert runtime.agent_message_queues["reviewer"][0].body["aggregate"]["accepted_changesets"] == [
        {"changeset_id": "cs-1", "files": ["src/a.py"]}
    ]
    assert [event.event_type for event in runtime.events] == [
        "JoinBarrierCreated",
        "JoinContributionSubmitted",
        "JoinContributionSubmitted",
        "AgentMessageQueued",
        "JoinBarrierAggregateQueued",
        "JoinBarrierReady",
    ]


def test_graph_runtime_join_barrier_wait_any_quorum_timeout_and_rejections() -> None:
    runtime = GraphRuntime(_FakeCluster())

    any_barrier = runtime.create_join_barrier(
        required_sources=["a", "b"],
        policy="wait-any",
        join_id="join-any",
    )
    any_result = runtime.submit_join_contribution("join-any", "b", result={"ok": True})
    assert any_result["ready"] is True
    assert any_barrier.final_reason == "any_source_submitted"
    assert any_result["missing_sources"] == ["a"]

    quorum_barrier = runtime.create_join_barrier(
        required_sources=["a", "b", "c"],
        policy="quorum",
        quorum=2,
        join_id="join-quorum",
    )
    runtime.submit_join_contribution("join-quorum", "a", status="failed")
    quorum_result = runtime.submit_join_contribution("join-quorum", "b", status="completed")
    assert quorum_result["ready"] is False
    quorum_result = runtime.submit_join_contribution("join-quorum", "c", status="passed")
    assert quorum_result["ready"] is True
    assert quorum_barrier.final_reason == "quorum_reached"

    timeout_barrier = runtime.create_join_barrier(
        required_sources=["slow"],
        timeout_sec=0,
        join_id="join-timeout",
    )
    runtime._check_join_timeouts()
    assert timeout_barrier.status == "timed_out"
    assert runtime.compute_final_status() == "timed_out"

    waiting_barrier = runtime.create_join_barrier(
        required_sources=["known"],
        join_id="join-waiting",
    )
    with pytest.raises(ValueError, match="not required"):
        runtime.submit_join_contribution(waiting_barrier.join_id, "ghost")
    with pytest.raises(RuntimeError, match="already ready"):
        runtime.submit_join_contribution("join-any", "a")


@pytest.mark.asyncio
async def test_graph_runtime_status_snapshot_includes_run_queues_batches_and_workspace(
    tmp_path: Path,
) -> None:
    cluster = _FakeCluster()
    workspace = WorkspaceManifest("ws-1", tmp_path)
    source = AgentNode(node_id="agent-a", agent_id="worker-a", cwd=Path("."))
    target = AgentNode(node_id="agent-b", agent_id="worker-b", cwd=Path("."))
    graph = GraphDefinition(
        agent_nodes={"agent-a": source, "agent-b": target},
        edges=[GraphEdge("agent-a", "agent-b", edge_type="exec")],
    )
    runtime = GraphRuntime(cluster, workspace=workspace)

    await runtime.ensure_agent(source)
    await runtime.create_outgoing_batch(source, [target], batch_id="batch-1")
    runtime.stage_outgoing_message("batch-1", target, {"prompt": "go"})
    runtime.create_join_barrier(
        required_sources=["agent-a"],
        target_node=target,
        join_id="join-1",
    )

    snapshot = runtime.status_snapshot(graph=graph, recent_events_limit=3)

    assert snapshot["run"]["status"] == "running"
    assert snapshot["agents"]["agent-a"]["state"] == "idle"
    assert snapshot["agents"]["agent-b"]["state"] == "queued"
    assert snapshot["queues"]["by_agent"]["agent-b"][0]["body"] == {"prompt": "go"}
    assert snapshot["outgoing_batches"]["batch-1"]["status"] == "dispatched"
    assert snapshot["joins"]["join-1"]["missing_sources"] == ["agent-a"]
    assert snapshot["workspace"]["workspace_id"] == "ws-1"
    assert snapshot["organization"]["agent_connections"] == {"agent-a": ["agent-b"], "agent-b": []}
    assert len(snapshot["recent_events"]) == 3


def test_graph_runtime_end_run_final_statuses_are_deterministic() -> None:
    success_runtime = GraphRuntime(_FakeCluster())
    success_runtime.create_join_barrier(
        required_sources=["coder"],
        policy="wait-all",
        join_id="join-ok",
    )
    success_runtime.submit_join_contribution(
        "join-ok",
        "coder",
        accepted_changesets=[{"changeset_id": "cs-1"}],
    )
    success = success_runtime.end_run("complete", reason="all work accepted")

    assert success.final_status == "success"
    assert success.run_status == "completed"
    assert success.summary["accepted_changesets"] == [{"changeset_id": "cs-1"}]
    assert success_runtime.status_snapshot()["run"]["final_status"] == "success"

    conflicted_runtime = GraphRuntime(_FakeCluster())
    conflicted_runtime.create_join_barrier(required_sources=["coder"], join_id="join-cf")
    conflicted_runtime.submit_join_contribution(
        "join-cf",
        "coder",
        conflicts=[{"path": "src/a.py", "reason": "merge_conflict"}],
    )
    conflicted = conflicted_runtime.end_run("complete", reason="needs repair")
    assert conflicted.final_status == "conflicted"

    partial_runtime = GraphRuntime(_FakeCluster())
    partial_runtime.create_join_barrier(required_sources=["coder", "reviewer"], join_id="join-open")
    partial_runtime.submit_join_contribution(
        "join-open",
        "coder",
        accepted_changesets=[{"changeset_id": "cs-2"}],
    )
    partial = partial_runtime.end_run("complete", reason="reviewer still pending")
    assert partial.final_status == "partial_success"

    cancelled = GraphRuntime(_FakeCluster()).end_run("cancel", reason="user cancelled")
    assert cancelled.final_status == "cancelled"

    paused_runtime = GraphRuntime(_FakeCluster())
    paused = paused_runtime.end_run("pause", reason="waiting for user")
    assert paused.final_status is None
    assert paused_runtime.status_snapshot()["run"]["status"] == "paused"

    archived = paused_runtime.end_run("archive_only", reason="save snapshot")
    assert archived.archived is True
    assert archived.run_status == "paused"


def test_graph_runtime_records_start_manifest_and_writes_workspace_json(tmp_path: Path) -> None:
    workspace = WorkspaceManifest("ws-1", tmp_path)
    runtime = GraphRuntime(_FakeCluster(), workspace=workspace)
    manifest_path = tmp_path / "run_manifest.json"

    entry = runtime.record_start_manifest(
        top_agent={"agent_id": "gulicode"},
        start_plan={"user_goal": "Ship it.", "start_nodes": ["planner"]},
        organization={"agents": {"planner": {"node_id": "planner"}}},
        queued_messages=[{"message_id": "msg-1", "node_id": "planner"}],
        manifest_path=manifest_path,
    )

    assert entry["start_plan"]["user_goal"] == "Ship it."
    assert runtime.status_snapshot()["run"]["manifest"]["start"]["top_agent"]["agent_id"] == "gulicode"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["run"]["start"]["queued_messages"][0]["message_id"] == "msg-1"
    assert "RunStarted" in [event.event_type for event in runtime.events]


def test_graph_runtime_cancel_run_clears_pending_messages_jobs_and_waiting_joins() -> None:
    runtime = GraphRuntime(_FakeCluster())
    node = AgentNode(node_id="worker", agent_id="worker-a", cwd=Path("."))
    runtime.queue_agent_message(node, {"prompt": "queued"})
    runtime.create_join_barrier(
        required_sources=["coder"],
        target_node=node,
        join_id="join-open",
    )
    job = GraphJob(
        job_id="job-open",
        node_id="worker",
        agent_id="worker-a",
        body={"prompt": "background"},
        status="queued",
    )
    runtime._jobs[job.job_id] = job

    result = runtime.end_run("cancel", reason="user stopped")

    assert result.final_status == "cancelled"
    assert result.summary["cancelled"]["messages"]
    assert result.summary["cancelled"]["jobs"] == ["job-open"]
    assert result.summary["cancelled"]["joins"] == ["join-open"]
    assert runtime.agent_message_queues["worker"] == []
    assert runtime.pending_messages[result.summary["cancelled"]["messages"][0]].status == "cancelled"
    assert runtime.jobs["job-open"].status == "cancelled"
    assert runtime.join_barriers["join-open"].status == "cancelled"
    assert "RunPendingWorkCancelled" in [event.event_type for event in runtime.events]


@pytest.mark.asyncio
async def test_nonblocking_agent_job_records_events_and_manifest(tmp_path: Path) -> None:
    cluster = _FakeCluster()
    workspace = WorkspaceManifest("ws-1", tmp_path)
    node = AgentNode(
        node_id="node-a",
        cwd=tmp_path,
        execution_mode="nonblocking",
        workspace_id="ws-1",
        workspace_root=tmp_path,
        write_scope=["changes"],
    )

    runtime = GraphRuntime(cluster, workspace=workspace)
    job = await runtime.submit_agent_job(node, {"prompt": "background"}, job_id="job-1")

    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert job.status == "completed"
    assert workspace.jobs["job-1"]["status"] == "completed"
    assert [event.event_type for event in runtime.events] == [
        "TaskStarted",
        "TaskProgress",
        "TaskCompleted",
    ]
    assert cluster.sent == [("node-a", {"prompt": "background"}, 1800.0)]


@pytest.mark.asyncio
async def test_nonblocking_agent_job_fails_on_worker_ok_false(tmp_path: Path) -> None:
    cluster = _FailingThenOkCluster()
    workspace = WorkspaceManifest("ws-1", tmp_path)
    node = AgentNode(
        node_id="node-a",
        cwd=tmp_path,
        execution_mode="nonblocking",
        workspace_id="ws-1",
        workspace_root=tmp_path,
        write_scope=["changes"],
    )

    runtime = GraphRuntime(cluster, workspace=workspace)
    job = await runtime.submit_agent_job(node, {"prompt": "background"}, job_id="job-1")

    for _ in range(20):
        await asyncio.sleep(0)
        if job.status == "failed":
            break

    assert job.status == "failed"
    assert "stream disconnected" in workspace.jobs["job-1"]["error"]
    assert [event.event_type for event in runtime.events] == [
        "TaskStarted",
        "TaskProgress",
        "TaskFailed",
    ]


def test_workspace_manifest_rejects_scope_escape(tmp_path: Path) -> None:
    manifest = WorkspaceManifest("ws-1", tmp_path)

    with pytest.raises(ValueError):
        manifest.validate_scopes(write_scope=[".."])


def test_blueprint_workspace_application_uses_private_checkout_and_rpc_context(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-blueprint")
    private = manager.agent_workspace_dir(run, "agent-cx")
    server = WorkspaceRPCServer(manager, run)
    server.start()
    try:
        node = AgentNode(
            node_id="agent-node",
            agent_id="agent-cx",
            cli_kind="codex",
            cwd=Path("."),
        )
        adjusted = _apply_run_workspace_to_node(
            node,
            manager=manager,
            run=run,
            private_dir=private,
            rpc_server=server,
        )

        checkout_path = private / "checkout"
        assert adjusted.cwd == checkout_path
        assert (checkout_path / "src").is_dir()
        assert adjusted.adapter_options["sandbox"] == "workspace-write"
        code_workspace = adjusted.adapter_options["execution_context"]["code_workspace"]
        assert code_workspace["mode"] == "vcs_checkout"
        assert code_workspace["checkout_path"] == str(checkout_path)
        assert code_workspace["integration_dir"] == str(run.integration_dir)
        shared_workspace = adjusted.adapter_options["execution_context"]["shared_workspace"]
        assert shared_workspace["root"] == str(run.shared_dir.resolve())
        assert shared_workspace["reports"] == str(run.shared_reports_dir.resolve())
        assert shared_workspace["manifest"] == str((run.shared_dir / "manifest.json").resolve())
        agents_md = (checkout_path / "AGENTS.md").read_text(encoding="utf-8")
        assert f"Read-only shared workspace: `{shared_workspace['root']}`" in agents_md
        assert f"Shared reports: `{shared_workspace['reports']}`" in agents_md
        context_path = private / "workspace_api_context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        assert context["transport"] == "rpc"
        assert context["shared_workspace"]["root"] == str(run.shared_dir)
        assert "archive_commands" not in context
    finally:
        server.close()


def test_blueprint_workspace_application_rejects_codex_danger_full_access(
    tmp_path: Path,
) -> None:
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-blueprint")
    private = manager.agent_workspace_dir(run, "agent-cx")
    server = WorkspaceRPCServer(manager, run)
    server.start()
    try:
        node = AgentNode(
            node_id="agent-node",
            agent_id="agent-cx",
            cli_kind="codex",
            cwd=Path("."),
            adapter_options={"sandbox": "danger-full-access"},
        )

        with pytest.raises(ValueError, match="danger-full-access"):
            _apply_run_workspace_to_node(
                node,
                manager=manager,
                run=run,
                private_dir=private,
                rpc_server=server,
            )
    finally:
        server.close()


def test_blueprint_workspace_application_rejects_codex_project_add_dir(
    tmp_path: Path,
) -> None:
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-blueprint")
    private = manager.agent_workspace_dir(run, "agent-cx")
    server = WorkspaceRPCServer(manager, run)
    server.start()
    try:
        node = AgentNode(
            node_id="agent-node",
            agent_id="agent-cx",
            cli_kind="codex",
            cwd=Path("."),
            adapter_options={"extra_args": ["--add-dir", str(tmp_path)]},
        )

        with pytest.raises(ValueError, match="--add-dir"):
            _apply_run_workspace_to_node(
                node,
                manager=manager,
                run=run,
                private_dir=private,
                rpc_server=server,
            )
    finally:
        server.close()


def test_blueprint_workspace_application_rejects_codex_shared_add_dir(
    tmp_path: Path,
) -> None:
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-blueprint")
    private = manager.agent_workspace_dir(run, "agent-cx")
    server = WorkspaceRPCServer(manager, run)
    server.start()
    try:
        node = AgentNode(
            node_id="agent-node",
            agent_id="agent-cx",
            cli_kind="codex",
            cwd=Path("."),
            adapter_options={"extra_args": ["--add-dir", str(run.shared_dir)]},
        )

        with pytest.raises(ValueError, match="--add-dir"):
            _apply_run_workspace_to_node(
                node,
                manager=manager,
                run=run,
                private_dir=private,
                rpc_server=server,
            )
    finally:
        server.close()


@pytest.mark.asyncio
async def test_graph_runtime_private_context_materializes_codex_skill_and_rules(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    rule = project / "business-rule.md"
    rule.write_text("# Business Review Rule\n\nDo the private thing.\n", encoding="utf-8")

    source_skill = tmp_path / "source-skills" / "biz-skill"
    source_skill.mkdir(parents=True)
    (source_skill / "SKILL.md").write_text(
        "---\n"
        "name: biz-skill\n"
        "description: PRIVATE_RUNTIME_SKILL_DESCRIPTION\n"
        "---\n"
        "# Biz Skill\n\n"
        "PRIVATE_RUNTIME_SKILL_BODY\n",
        encoding="utf-8",
    )
    skill_space = SkillSpace.open_or_init(tmp_path / "skill-space")
    rec = skill_space.add_skill_copy(source_skill)

    manager = DulwichWorkspaceManager.open_or_init(project)
    run = manager.create_run(run_id="run-private")
    server = WorkspaceRPCServer(manager, run)
    server.start()
    cluster = _RestartableCluster()
    try:
        runtime = GraphRuntime(
            cluster,
            enforce_private_agent_context=True,
            private_context_manager=manager,
            private_context_run=run,
            private_context_rpc_server=server,
            skill_space=skill_space,
        )
        node = AgentNode(
            node_id="agent-node",
            agent_id="agent-cx",
            cli_kind="codex",
            cwd=project,
            write_scope=["src/**"],
            skill_selection={"mode": "selected", "skill_hashes": [rec.skill_hash]},
            rule_paths=[str(rule)],
        )

        inst = await runtime.ensure_agent(node)

        private = manager.agent_workspace_dir(run, "agent-cx")
        checkout = private / "checkout"
        codex_home = private / "codex_home"
        assert inst.node.cwd == checkout
        assert cluster.worker_cwds["agent-cx"] == checkout
        assert (checkout / "AGENTS.md").is_file()
        assert (private / "state" / "base" / "AGENTS.md").is_file()
        assert manager.status_checkout(run, manager.open_agent_checkout(run, "agent-cx")) == []
        agents_md = (checkout / "AGENTS.md").read_text(encoding="utf-8")
        assert "Business Review Rule" in agents_md
        assert "`framework_context.message_envelope.outgoing_batch_id`" in agents_md
        assert "Upstream/source batch ids" in agents_md
        assert "leaf work" in agents_md
        assert "out-*` are not join ids" in agents_md
        assert (private / "rules" / "01-business-rule.md").is_file()
        assert (codex_home / "skills" / "framework-agent-runtime" / "SKILL.md").is_file()
        framework_skill = (
            codex_home / "skills" / "framework-agent-runtime" / "SKILL.md"
        ).read_text(encoding="utf-8")
        assert "framework-private utterance record" in framework_skill
        assert "not a communication channel to other AgentNodes" in framework_skill
        assert "call `agent_context({})` with no explicit batch_id" in framework_skill
        assert "source/audit labels and must not be passed" in framework_skill
        assert "`framework_context.message_envelope.required_outgoing_targets` is empty" in framework_skill
        assert "Outgoing batch ids such as `out-*` are not join ids" in framework_skill
        copied_skills = list((codex_home / "skills").glob(f"{rec.skill_hash}-biz-skill/SKILL.md"))
        assert copied_skills
        assert not (codex_home / "skills" / "biz-skill").exists()
        assert inst.node.adapter_options["sandbox"] == "workspace-write"
        assert inst.node.adapter_options["codex_home"] == str(codex_home)
        assert inst.node.extra_env["MULTI_AGENT_WORKSPACE_CONTEXT"] == str(
            private / "workspace_api_context.json"
        )
        assert str(Path(__file__).resolve().parent.parent) in inst.node.extra_env["PYTHONPATH"]
        launched_worker = cluster.worker_configs["agent-cx"]
        worker_json = launched_worker.to_agent_json("127.0.0.1", 9140)
        assert worker_json["codex"]["cwd"] == str(checkout)
        assert worker_json["extra_env"]["MULTI_AGENT_WORKSPACE_CONTEXT"] == str(
            private / "workspace_api_context.json"
        )
        merged_prompt = _merge_codex_prompt(
            "Implement the task.",
            '{"framework_context": {"message_envelope": {"outgoing_batch_id": "out-1"}}}',
            worker_json["codex"],
        )
        assert "Workspace API" not in merged_prompt
        assert "multi_agent_tcp.workspace_api" not in merged_prompt
        assert "Codex Execution Context" in merged_prompt
        assert json.dumps(str(checkout), ensure_ascii=False)[1:-1] in merged_prompt
        assert json.dumps(str(project), ensure_ascii=False)[1:-1] in merged_prompt
        assert json.dumps(str(run.shared_dir.resolve()), ensure_ascii=False)[1:-1] in merged_prompt
        assert "PRIVATE_RUNTIME_SKILL_DESCRIPTION" in merged_prompt
        assert "outgoing_batch_id" in merged_prompt
        assert "out-1" in merged_prompt
        private_context = inst.node.adapter_options["execution_context"]["private_context"]
        assert private_context["codex_home"] == str(codex_home)
        assert private_context["rule_catalog"][0]["rule_path"] == str(private / "rules" / "01-business-rule.md")
        prompt_context = inst.node.adapter_options["prompt_execution_context"]
        assert "codex_home" not in prompt_context["private_context"]
        assert "workspace_api" not in prompt_context
        assert prompt_context["code_workspace"]["project_context"] == str(project)
        assert prompt_context["code_workspace"]["checkout_path"] == str(checkout)
        assert "submit_command" not in prompt_context["code_workspace"]
        assert prompt_context["shared_workspace"]["root"] == str(run.shared_dir.resolve())
        assert (private / "workspace_api_context.json").is_file()
    finally:
        server.close()


@pytest.mark.asyncio
async def test_graph_runtime_full_agent_skips_private_workspace(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    manager = DulwichWorkspaceManager.open_or_init(project)
    run = manager.create_run(run_id="run-full-agent")
    cluster = _RestartableCluster()

    def mcp_provider(**kwargs: Any) -> dict[str, Any]:
        return {
            "server_kind": "ordinary",
            "server_name": "framework_ordinary",
            "url": "http://127.0.0.1:9876/ordinary/mcp",
            "bearer_token_env_var": "MULTI_AGENT_MCP_ORDINARY_TOKEN",
            "bearer_token": "message-token",
            "tools": ["agent_dispatch", "agent_context", "agent_task_status", "join_contribute"],
        }

    runtime = GraphRuntime(
        cluster,
        enforce_private_agent_context=True,
        private_context_manager=manager,
        private_context_run=run,
        private_context_mcp_provider=mcp_provider,
    )
    node = AgentNode(
        node_id="shell",
        node_type="agent",
        agent_id="agent-shell",
        cli_kind="codex",
        cwd=Path("."),
    )

    inst = await runtime.ensure_agent(node)

    assert inst.node.node_type == "agent"
    assert inst.node.cwd == project.resolve()
    assert cluster.worker_cwds["agent-shell"] == project.resolve()
    assert not (run.agents_dir / "agent-shell").exists()
    assert (run.path / "runtime_agent_context" / "agent-shell" / "codex_home").is_dir()
    assert inst.node.workspace_id is None
    assert inst.node.workspace_root is None
    assert inst.node.read_scope == []
    assert inst.node.write_scope == []
    assert inst.node.artifact_scope == []
    assert inst.node.adapter_options["sandbox"] == "danger-full-access"
    assert inst.node.adapter_options["dangerous_access"] is True
    assert "--dangerously-bypass-approvals-and-sandbox" in inst.node.adapter_options["extra_args"]
    assert inst.node.adapter_options["execution_context"]["agent_access"]["workspace_tools"] is False
    assert inst.node.adapter_options["execution_context"]["mcp"]["tools"] == [
        "agent_dispatch",
        "agent_context",
        "agent_task_status",
        "join_contribute",
    ]
    assert "MULTI_AGENT_WORKSPACE_CONTEXT" not in inst.node.extra_env
    assert inst.node.extra_env["MULTI_AGENT_MCP_ORDINARY_TOKEN"] == "message-token"


@pytest.mark.asyncio
async def test_full_agent_receives_standard_context_and_dispatches_via_message_mcp(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    manager = DulwichWorkspaceManager.open_or_init(project)
    run = manager.create_run(run_id="run-full-agent-mcp", code_mode="project_reference")
    server = WorkspaceRPCServer(manager, run)
    server.start()
    cluster = _RestartableCluster()
    try:
        graph = GraphDefinition(
            agent_nodes={
                "shell": AgentNode.from_dict(
                    {
                        "node_id": "shell",
                        "node_type": "agent",
                        "agent_id": "agent-shell",
                        "cwd": ".",
                    }
                ),
                "worker": AgentNode.from_dict(
                    {
                        "node_id": "worker",
                        "node_type": "worker_agent",
                        "agent_id": "agent-worker",
                        "cwd": ".",
                    }
                ),
            },
            edges=[GraphEdge("shell", "worker", edge_type="exec")],
        )
        runtime = GraphRuntime(
            cluster,
            enforce_private_agent_context=True,
            private_context_manager=manager,
            private_context_run=run,
            private_context_rpc_server=server,
        )
        control = GraphRuntimeControlPlane(runtime, graph)
        mcp = RunMCPRuntimeHandle(
            run_id="run-full-agent-mcp",
            runtime=runtime,
            control=control,
            graph=graph,
            workspace_rpc_server=server,
            manager=manager,
            workspace_run=run,
            runtime_loop=None,
        )
        runtime.private_context_mcp_provider = mcp.provision_context_for_node
        runtime.agent_message_context_callback = mcp.refresh_message_context
        plan = TopAgentStartPlan.from_dict(
            {
                "user_goal": "Run shell then worker.",
                "agent_descriptions": {
                    "shell": "Full CLI agent with direct project access.",
                    "worker": "Framework-managed worker agent.",
                },
                "start_nodes": ["shell"],
                "tasks": {
                    "shell": {
                        "goal": "Use MCP to hand off to worker.",
                        "expected_output": "Worker receives a delegated task.",
                        "acceptance": "The delegated task is queued for worker.",
                    }
                },
            }
        )

        started = await control.start_run(plan, prestart_all_agents=True)
        assert started["ok"] is True
        queued = started["queued_messages"][0]
        assert queued["node_id"] == "shell"
        shell_body = queued["body"]
        shell_context = shell_body["context"]["framework_context"]
        shell_batch_id = shell_context["message_envelope"]["outgoing_batch_id"]
        assert shell_context["agent_node_id"] == "shell"
        assert shell_context["agent_id"] == "agent-shell"
        assert shell_context["message_envelope"]["required_outgoing_targets"] == ["worker"]
        assert shell_context["message_envelope"]["remaining_targets"] == ["worker"]

        full_worker = cluster.worker_configs["agent-shell"]
        full_worker_json = full_worker.to_agent_json("127.0.0.1", 9140)
        assert full_worker.cwd == project.resolve()
        assert full_worker_json["codex"]["cwd"] == str(project.resolve())
        assert full_worker_json["codex"]["sandbox"] == "danger-full-access"
        assert full_worker_json["codex"]["dangerous_access"] is True
        assert "--dangerously-bypass-approvals-and-sandbox" in full_worker_json["codex"]["extra_args"]
        assert "MULTI_AGENT_WORKSPACE_CONTEXT" not in full_worker.extra_env
        token = full_worker.extra_env["MULTI_AGENT_MCP_ORDINARY_TOKEN"]
        scope = mcp.token_store.authenticate(
            server_kind="ordinary",
            token=token,
            session_id=None,
        )
        assert scope.workspace_rpc_token is None
        assert scope.allowed_tools == [
            "agent_dispatch",
            "agent_context",
            "blueprint_script_call",
            "agent_task_status",
            "join_contribute",
        ]

        pending = await runtime.dispatch_queued_message_now(queued["message_id"])
        assert pending.status == "completed"
        assert cluster.sent[-1][0] == "agent-shell"
        assert cluster.sent[-1][1]["context"]["framework_context"] == shell_context
        assert scope.current_message_context is not None
        assert scope.current_message_context.outgoing_batch_id == shell_batch_id
        assert scope.current_message_context.required_outgoing_targets == ["worker"]

        dispatch = await mcp._agent_dispatch(
            scope,
            target_node_id="worker",
            body={"prompt": "Worker task from full Agent."},
            batch_id=None,
            source_node_id=None,
        )

        assert dispatch["dispatch"]["ready_to_dispatch"] is True
        worker_queue = runtime.agent_message_queues["worker"]
        assert len(worker_queue) == 1
        worker_body = worker_queue[0].body
        worker_context = worker_body["context"]["framework_context"]
        assert worker_body["prompt"] == "Worker task from full Agent."
        assert worker_context["agent_node_id"] == "worker"
        assert worker_context["agent_id"] == "agent-worker"
        assert worker_context["upstream_agents"] == ["shell"]
        assert worker_context["downstream_agents"] == []
        assert worker_context["message_envelope"]["outgoing_batch_id"] is None
        assert worker_context["message_envelope"]["required_outgoing_targets"] == []
        assert worker_context["organization"]["scope"] == "agent"
    finally:
        server.close()


@pytest.mark.asyncio
async def test_real_codex_cli_framework_private_checkout_submit_and_archive_flow(
    unused_tcp_port: int,
) -> None:
    codex = shutil.which("codex")
    if codex is None:
        pytest.skip("codex CLI is not installed on PATH")

    repo_tmp = (
        Path(__file__).resolve().parent
        / ".pytest_tmp"
        / f"real_codex_flow_{unused_tcp_port}"
    )
    if repo_tmp.exists():
        shutil.rmtree(repo_tmp, ignore_errors=True)
    project = repo_tmp / "p"
    server = None
    cluster = None
    try:
        probe = project / "src" / "framework_probe.txt"
        probe.parent.mkdir(parents=True)
        probe.write_text("base framework probe\n", encoding="utf-8")
        rule = project / "rules" / "framework-flow-rule.md"
        rule.parent.mkdir(parents=True)
        rule.write_text(
            "# Framework Flow Rule\n\n"
            "You must prove the private checkout workflow by writing "
            "REAL_CODEX_FRAMEWORK_FLOW_RULE_SEEN into the probe file and report.\n",
            encoding="utf-8",
        )

        source_skill = repo_tmp / "source-skills" / "framework-flow-skill"
        source_skill.mkdir(parents=True)
        (source_skill / "SKILL.md").write_text(
            "---\n"
            "name: framework-flow-skill\n"
            "description: REAL_CODEX_FRAMEWORK_FLOW_SKILL_DESCRIPTION\n"
            "---\n"
            "# Framework Flow Skill\n\n"
            "When validating this flow, include REAL_CODEX_FRAMEWORK_FLOW_SKILL_SEEN "
            "in the submitted file and report.\n",
            encoding="utf-8",
        )
        skill_space = SkillSpace.open_or_init(repo_tmp / "skill-space")
        rec = skill_space.add_skill_copy(source_skill)

        manager = DulwichWorkspaceManager.open_or_init(project, workspace_root=repo_tmp / "w")
        run = manager.create_run(
            run_id="run-codex-flow",
            code_mode="project_reference",
        )
        original_submit_checkout = manager.submit_checkout
        submit_saw_project_base = False

        def guarded_submit_checkout(run_arg: Any, checkout_arg: Any, **kwargs: Any) -> Any:
            nonlocal submit_saw_project_base
            assert probe.read_text(encoding="utf-8") == "base framework probe\n"
            submit_saw_project_base = True
            return original_submit_checkout(run_arg, checkout_arg, **kwargs)

        manager.submit_checkout = guarded_submit_checkout  # type: ignore[method-assign]
        server = WorkspaceRPCServer(manager, run)
        server.start()

        codex_config_overrides = _codex_real_flow_config_overrides()
        node = AgentNode(
            node_id="codex-node",
            agent_id="agent-codex",
            cli_kind="codex",
            command=codex,
            cwd=project,
            timeout_sec=420.0,
            write_scope=["src/framework_probe.txt"],
            skill_selection={"mode": "selected", "skill_hashes": [rec.skill_hash]},
            rule_paths=[str(rule)],
            adapter_options={
                "model": "gpt-5.5",
                "timeout_sec": 360.0,
                "disable_features": ["plugins", "shell_snapshot"],
                "config_overrides": codex_config_overrides,
                "extra_args": ["--full-auto"],
            },
        )
        cluster = await CLIWorkerBackend.create(
            [
                WorkerConfig(
                    "bootstrap-real-codex",
                    cwd=project,
                    timeout_sec=30.0,
                    command=codex,
                    cli_kind="codex",
                    adapter_options={
                        "model": "gpt-5.5",
                        "sandbox": "workspace-write",
                        "skip_git_repo_check": True,
                        "disable_features": ["plugins", "shell_snapshot"],
                        "config_overrides": codex_config_overrides,
                        "extra_args": ["--full-auto"],
                    },
                )
            ],
            port=unused_tcp_port,
        )
        runtime = GraphRuntime(
            cluster,
            enforce_private_agent_context=True,
            private_context_manager=manager,
            private_context_run=run,
            private_context_rpc_server=server,
            skill_space=skill_space,
            archive_manager=manager,
            archive_run=run,
        )

        marker = "REAL_CODEX_FRAMEWORK_FLOW_SUCCESS"
        inst = await runtime.ensure_agent(node)
        prompt = (
            "You are running as a real Codex CLI worker inside the framework private "
            "AgentNode context. Complete this exact flow and do not edit the project "
            "directory directly.\n\n"
            "1. Read AGENTS.md and the Codex Execution Context catalog. Confirm the "
            "injected skill catalog includes framework-agent-runtime and "
            "framework-flow-skill, and the rule catalog includes Framework Flow Rule. "
            "Do not open individual SKILL.md or rule files with shell commands; the "
            "catalog is the required injected context for this test.\n"
            "2. Run: python -m multi_agent_tcp.workspace_api checkout --path "
            "src/framework_probe.txt\n"
            "3. Modify only src/framework_probe.txt in your current private checkout. "
            f"Keep the base line and add exactly these lines: {marker}, "
            "REAL_CODEX_FRAMEWORK_FLOW_RULE_SEEN, "
            "REAL_CODEX_FRAMEWORK_FLOW_SKILL_SEEN.\n"
            "4. Run: python -m multi_agent_tcp.workspace_api status\n"
            "5. Run: python -m multi_agent_tcp.workspace_api diff\n"
            "6. Run: python -m multi_agent_tcp.workspace_api submit --task-id "
            "real-codex-framework-flow --summary \"real codex framework flow\"\n"
            "7. Run: python -m multi_agent_tcp.workspace_api publish --area reports "
            "--path codex-framework-flow.md --text \"REAL_CODEX_FRAMEWORK_FLOW_SUCCESS "
            "REAL_CODEX_FRAMEWORK_FLOW_RULE_SEEN REAL_CODEX_FRAMEWORK_FLOW_SKILL_SEEN "
            "changeset submitted accepted\"\n\n"
            f"Final answer must include: {marker} REAL_CODEX_CONTEXT_OK "
            "framework-agent-runtime framework-flow-skill Framework Flow Rule "
            "changeset submitted accepted."
        )

        raw_reply = await cluster.run_single(
            inst.agent_id,
            {"prompt": prompt},
            timeout_sec=420.0,
            _skip_skill_inject=True,
        )
        body = raw_reply["body"]
        assert body["ok"] is True, body.get("codex")
        codex_result = body["codex"]
        assert codex_result["returncode"] == 0
        _assert_codex_ran_workspace_api_commands(
            codex_result,
            [
                "multi_agent_tcp.workspace_api checkout",
                "src/framework_probe.txt",
                "multi_agent_tcp.workspace_api status",
                "multi_agent_tcp.workspace_api diff",
                "multi_agent_tcp.workspace_api submit",
                "real-codex-framework-flow",
                "multi_agent_tcp.workspace_api publish",
                "codex-framework-flow.md",
            ],
        )
        final_text = codex_result.get("final_text") or codex_result.get("last_message") or ""
        assert marker in final_text
        assert "REAL_CODEX_CONTEXT_OK" in final_text
        assert "framework-agent-runtime" in final_text
        assert "framework-flow-skill" in final_text
        assert "changeset submitted accepted" in final_text
        utterance = runtime._record_agent_utterance(
            node_id=node.node_id,
            agent_id=inst.agent_id,
            reply=raw_reply,
            task_id="real-codex-framework-flow",
        )
        assert marker in utterance.said

        private = manager.agent_workspace_dir(run, "agent-codex")
        checkout = private / "checkout"
        codex_home = private / "codex_home"
        assert (checkout / "AGENTS.md").is_file()
        assert (codex_home / "skills" / "framework-agent-runtime" / "SKILL.md").is_file()
        assert list((codex_home / "skills").glob(f"{rec.skill_hash}-framework-flow-skill/SKILL.md"))
        assert (private / "rules" / "01-framework-flow-rule.md").is_file()

        audit_commands = _workspace_api_audit_commands(run)
        for expected in ["checkout", "status", "diff", "submit", "publish"]:
            assert expected in audit_commands, {
                "missing": expected,
                "audit_commands": audit_commands,
            }
        assert audit_commands.index("checkout") < audit_commands.index("submit") < audit_commands.index("publish")
        assert audit_commands.index("status") < audit_commands.index("submit")
        assert audit_commands.index("diff") < audit_commands.index("submit")
        assert audit_commands.count("submit") == 1
        assert submit_saw_project_base is True

        assert (project / "src" / "framework_probe.txt").read_text(encoding="utf-8").count(marker) == 1
        assert "REAL_CODEX_FRAMEWORK_FLOW_RULE_SEEN" in probe.read_text(encoding="utf-8")
        assert "REAL_CODEX_FRAMEWORK_FLOW_SKILL_SEEN" in probe.read_text(encoding="utf-8")
        assert not (run.integration_dir / "src" / "framework_probe.txt").exists()

        changesets = sorted((run.path / "changesets").glob("cs-*"), key=lambda p: p.stat().st_mtime)
        assert changesets
        accepted_submit = json.loads(
            (changesets[-1] / "submit_result.json").read_text(encoding="utf-8")
        )
        assert accepted_submit["ok"] is True
        assert accepted_submit["status"] == "accepted"
        assert accepted_submit["merged_files"] == ["src/framework_probe.txt"]
        assert accepted_submit["changeset_id"]

        report = run.shared_reports_dir / "codex-framework-flow.md"
        assert report.is_file()
        report_text = report.read_text(encoding="utf-8")
        assert marker in report_text
        assert "REAL_CODEX_FRAMEWORK_FLOW_RULE_SEEN" in report_text
        assert "REAL_CODEX_FRAMEWORK_FLOW_SKILL_SEEN" in report_text
        assert "changeset submitted" in report_text

        end = runtime.end_run("complete", reason="real codex framework flow verified", archive=True)
        assert end.final_status == "success"
        archive_path = Path(end.summary["archive_path"])
        assert archive_path.is_dir()
        assert (manager.workspace_root / "shared" / "archives" / "run-codex-flow-completed.zip").is_file()
        assert (
            archive_path / "shared" / "reports" / "codex-framework-flow.md"
        ).read_text(encoding="utf-8") == report_text
        assert (archive_path / "changesets" / accepted_submit["changeset_id"] / "submit_result.json").is_file()
        assert not (archive_path / "agents" / "agent-codex" / "private").exists()
        assert not (archive_path / "agents" / "agent-codex" / "private" / "checkout").exists()

        with zipfile.ZipFile(
            manager.workspace_root / "shared" / "archives" / "run-codex-flow-completed.zip"
        ) as zf:
            assert "reports/codex-framework-flow.md" in zf.namelist()
    finally:
        if cluster is not None:
            await cluster.stop()
        if server is not None:
            server.close()
        shutil.rmtree(repo_tmp, ignore_errors=True)


@pytest.mark.asyncio
async def test_real_codex_cli_framework_blocks_direct_project_and_shared_writes(
    unused_tcp_port: int,
) -> None:
    codex = shutil.which("codex")
    if codex is None:
        pytest.skip("codex CLI is not installed on PATH")

    repo_tmp = (
        Path(__file__).resolve().parent
        / ".pytest_tmp"
        / f"real_codex_direct_write_{unused_tcp_port}"
    )
    if repo_tmp.exists():
        shutil.rmtree(repo_tmp, ignore_errors=True)
    project = repo_tmp / "p"
    server = None
    cluster = None
    try:
        probe = project / "src" / "direct_write_probe.txt"
        probe.parent.mkdir(parents=True)
        probe.write_text("base direct write probe\n", encoding="utf-8")

        manager = DulwichWorkspaceManager.open_or_init(project, workspace_root=repo_tmp / "w")
        run = manager.create_run(
            run_id="run-codex-direct-write",
            code_mode="project_reference",
        )
        server = WorkspaceRPCServer(manager, run)
        server.start()

        codex_config_overrides = _codex_real_flow_config_overrides()
        node = AgentNode(
            node_id="codex-direct-write-node",
            agent_id="agent-codex-direct-write",
            cli_kind="codex",
            command=codex,
            cwd=project,
            timeout_sec=300.0,
            write_scope=["src/direct_write_probe.txt"],
            adapter_options={
                "model": "gpt-5.5",
                "timeout_sec": 240.0,
                "disable_features": ["plugins", "shell_snapshot"],
                "config_overrides": codex_config_overrides,
                "extra_args": ["--full-auto"],
            },
        )
        cluster = await CLIWorkerBackend.create(
            [
                WorkerConfig(
                    "bootstrap-real-codex-direct-write",
                    cwd=project,
                    timeout_sec=30.0,
                    command=codex,
                    cli_kind="codex",
                    adapter_options={
                        "model": "gpt-5.5",
                        "sandbox": "workspace-write",
                        "skip_git_repo_check": True,
                        "disable_features": ["plugins", "shell_snapshot"],
                        "config_overrides": codex_config_overrides,
                        "extra_args": ["--full-auto"],
                    },
                )
            ],
            port=unused_tcp_port,
        )
        runtime = GraphRuntime(
            cluster,
            enforce_private_agent_context=True,
            private_context_manager=manager,
            private_context_run=run,
            private_context_rpc_server=server,
            archive_manager=manager,
            archive_run=run,
        )

        inst = await runtime.ensure_agent(node)
        private = manager.agent_workspace_dir(run, "agent-codex-direct-write")
        checkout = private / "checkout"
        shared_direct = run.shared_reports_dir / "direct-write-forbidden.md"
        prompt = (
            "This is a negative boundary test. Do not use workspace_api. "
            "Run shell commands that intentionally attempt to write "
            "REAL_CODEX_DIRECT_WRITE_FORBIDDEN to both absolute paths below. "
            "Catch and print errors so the turn can finish even when writes are "
            "blocked.\n\n"
            f"Project file path: {probe}\n"
            f"Temporary shared report path: {shared_direct}\n\n"
            "After those two direct write attempts, write "
            "REAL_CODEX_PRIVATE_WRITE_ALLOWED into private-direct-ok.txt in your "
            "current cwd to prove the private checkout is still writable. Final "
            "answer must include REAL_CODEX_DIRECT_WRITE_BLOCKED."
        )

        raw_reply = await cluster.run_single(
            inst.agent_id,
            {"prompt": prompt},
            timeout_sec=300.0,
            _skip_skill_inject=True,
        )
        body = raw_reply["body"]
        assert body["ok"] is True, body.get("codex")
        codex_result = body["codex"]
        assert codex_result["returncode"] == 0
        commands = _codex_command_executions(codex_result)
        assert commands, codex_result
        command_output = "\n".join(
            str(item.get("item", {}).get("aggregated_output", ""))
            for item in codex_result.get("events") or []
            if isinstance(item, dict)
        )
        blocked_markers = command_output.count("DIRECT_WRITE_BLOCKED") + command_output.count(
            "WRITE_BLOCKED_OR_FAILED"
        )
        denied = (
            "Access to the path" in command_output
            or "访问被拒绝" in command_output
            or "denied" in command_output.lower()
        )
        assert blocked_markers >= 2 or denied, command_output
        final_text = codex_result.get("final_text") or codex_result.get("last_message") or ""
        assert "REAL_CODEX_DIRECT_WRITE_BLOCKED" in final_text

        assert probe.read_text(encoding="utf-8") == "base direct write probe\n"
        assert not shared_direct.exists()
        assert (checkout / "private-direct-ok.txt").read_text(
            encoding="utf-8-sig"
        ).strip() == "REAL_CODEX_PRIVATE_WRITE_ALLOWED"
        assert _workspace_api_audit_commands(run) == []
    finally:
        if cluster is not None:
            await cluster.stop()
        if server is not None:
            server.close()
        shutil.rmtree(repo_tmp, ignore_errors=True)


@pytest.mark.asyncio
async def test_real_codex_cli_framework_recovers_from_blocked_direct_write(
    unused_tcp_port: int,
) -> None:
    codex = shutil.which("codex")
    if codex is None:
        pytest.skip("codex CLI is not installed on PATH")

    repo_tmp = (
        Path(__file__).resolve().parent
        / ".pytest_tmp"
        / f"real_codex_blocked_recovery_{unused_tcp_port}"
    )
    if repo_tmp.exists():
        shutil.rmtree(repo_tmp, ignore_errors=True)
    project = repo_tmp / "p"
    server = None
    cluster = None
    try:
        probe = project / "src" / "blocked_recovery_probe.txt"
        probe.parent.mkdir(parents=True)
        probe.write_text("base blocked recovery probe\n", encoding="utf-8")

        manager = DulwichWorkspaceManager.open_or_init(project, workspace_root=repo_tmp / "w")
        run = manager.create_run(
            run_id="run-codex-blocked-recovery",
            code_mode="project_reference",
        )
        original_submit_checkout = manager.submit_checkout
        submit_saw_project_base = False

        def guarded_submit_checkout(run_arg: Any, checkout_arg: Any, **kwargs: Any) -> Any:
            nonlocal submit_saw_project_base
            assert probe.read_text(encoding="utf-8") == "base blocked recovery probe\n"
            submit_saw_project_base = True
            return original_submit_checkout(run_arg, checkout_arg, **kwargs)

        manager.submit_checkout = guarded_submit_checkout  # type: ignore[method-assign]
        server = WorkspaceRPCServer(manager, run)
        server.start()

        codex_config_overrides = _codex_real_flow_config_overrides()
        node = AgentNode(
            node_id="codex-blocked-recovery-node",
            agent_id="agent-codex-blocked-recovery",
            cli_kind="codex",
            command=codex,
            cwd=project,
            timeout_sec=360.0,
            write_scope=["src/blocked_recovery_probe.txt"],
            adapter_options={
                "model": "gpt-5.5",
                "timeout_sec": 300.0,
                "disable_features": ["plugins", "shell_snapshot"],
                "config_overrides": codex_config_overrides,
                "extra_args": ["--full-auto"],
            },
        )
        cluster = await CLIWorkerBackend.create(
            [
                WorkerConfig(
                    "bootstrap-real-codex-blocked-recovery",
                    cwd=project,
                    timeout_sec=30.0,
                    command=codex,
                    cli_kind="codex",
                    adapter_options={
                        "model": "gpt-5.5",
                        "sandbox": "workspace-write",
                        "skip_git_repo_check": True,
                        "disable_features": ["plugins", "shell_snapshot"],
                        "config_overrides": codex_config_overrides,
                        "extra_args": ["--full-auto"],
                    },
                )
            ],
            port=unused_tcp_port,
        )
        runtime = GraphRuntime(
            cluster,
            enforce_private_agent_context=True,
            private_context_manager=manager,
            private_context_run=run,
            private_context_rpc_server=server,
            archive_manager=manager,
            archive_run=run,
        )

        marker = "REAL_CODEX_BLOCKED_WRITE_RECOVERED"
        inst = await runtime.ensure_agent(node)
        prompt = (
            "This test checks recovery after boundary enforcement. First, run a "
            "shell command that intentionally tries to append "
            f"{marker} to this absolute project file path without workspace_api: "
            f"{probe}. Catch and print the error, then continue the same task.\n\n"
            "After the direct write is blocked, recover by running exactly this "
            "framework flow:\n"
            "1. python -m multi_agent_tcp.workspace_api checkout --path "
            "src/blocked_recovery_probe.txt\n"
            "2. Modify only src/blocked_recovery_probe.txt in the current private "
            f"checkout. Keep the base line and add {marker}.\n"
            "3. python -m multi_agent_tcp.workspace_api status\n"
            "4. python -m multi_agent_tcp.workspace_api diff\n"
            "5. python -m multi_agent_tcp.workspace_api submit --task-id "
            "real-codex-blocked-recovery --summary \"blocked write recovered via workspace api\"\n"
            "6. python -m multi_agent_tcp.workspace_api publish --area reports "
            "--path codex-blocked-recovery.md --text "
            f"\"{marker} blocked direct write recovered via workspace api changeset accepted\"\n\n"
            f"Final answer must include {marker} DIRECT_WRITE_BLOCKED_THEN_RECOVERED "
            "changeset accepted."
        )

        raw_reply = await cluster.run_single(
            inst.agent_id,
            {"prompt": prompt},
            timeout_sec=360.0,
            _skip_skill_inject=True,
        )
        body = raw_reply["body"]
        assert body["ok"] is True, body.get("codex")
        codex_result = body["codex"]
        assert codex_result["returncode"] == 0
        _assert_codex_ran_workspace_api_commands(
            codex_result,
            [
                "multi_agent_tcp.workspace_api checkout",
                "src/blocked_recovery_probe.txt",
                "multi_agent_tcp.workspace_api status",
                "multi_agent_tcp.workspace_api diff",
                "multi_agent_tcp.workspace_api submit",
                "real-codex-blocked-recovery",
                "multi_agent_tcp.workspace_api publish",
                "codex-blocked-recovery.md",
            ],
        )
        command_output = "\n".join(
            str(item.get("item", {}).get("aggregated_output", ""))
            for item in codex_result.get("events") or []
            if isinstance(item, dict)
        )
        assert (
            "Access to the path" in command_output
            or "denied" in command_output.lower()
            or "DIRECT_WRITE_BLOCKED" in command_output
            or "WRITE_BLOCKED" in command_output
        ), command_output
        final_text = codex_result.get("final_text") or codex_result.get("last_message") or ""
        assert marker in final_text
        assert "DIRECT_WRITE_BLOCKED_THEN_RECOVERED" in final_text
        assert "changeset accepted" in final_text

        assert submit_saw_project_base is True
        project_text = probe.read_text(encoding="utf-8")
        assert project_text.count(marker) == 1
        assert project_text.startswith("base blocked recovery probe\n")
        assert not (run.integration_dir / "src" / "blocked_recovery_probe.txt").exists()
        assert (run.shared_reports_dir / "codex-blocked-recovery.md").is_file()
        report = (run.shared_reports_dir / "codex-blocked-recovery.md").read_text(
            encoding="utf-8"
        )
        assert marker in report
        assert "changeset accepted" in report

        audit_commands = _workspace_api_audit_commands(run)
        audit_index = 0
        for expected in ["checkout", "status", "diff", "submit", "publish"]:
            while audit_index < len(audit_commands) and audit_commands[audit_index] != expected:
                audit_index += 1
            assert audit_index < len(audit_commands), {
                "missing": expected,
                "audit_commands": audit_commands,
            }
            audit_index += 1
        assert audit_commands.count("submit") == 1

        changesets = sorted((run.path / "changesets").glob("cs-*"), key=lambda p: p.stat().st_mtime)
        assert changesets
        submit_result = json.loads(
            (changesets[-1] / "submit_result.json").read_text(encoding="utf-8")
        )
        assert submit_result["ok"] is True
        assert submit_result["status"] == "accepted"
        assert submit_result["merged_files"] == ["src/blocked_recovery_probe.txt"]
    finally:
        if cluster is not None:
            await cluster.stop()
        if server is not None:
            server.close()
        shutil.rmtree(repo_tmp, ignore_errors=True)


@pytest.mark.asyncio
async def test_graph_runtime_auto_private_context_uses_project_reference_mode(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "app.py").write_text("print('base')\n", encoding="utf-8")
    cluster = _RestartableCluster()
    runtime = GraphRuntime(cluster, enforce_private_agent_context=True)
    node = AgentNode(
        node_id="agent-node",
        agent_id="agent-cx",
        cli_kind="codex",
        cwd=project,
    )

    inst = await runtime.ensure_agent(node)

    assert runtime.private_context_manager is not None
    assert runtime.private_context_run is not None
    assert runtime.private_context_run.code_mode == "project_reference"
    assert not (runtime.private_context_run.integration_dir / "src" / "app.py").exists()
    private = runtime.private_context_manager.agent_workspace_dir(
        runtime.private_context_run,
        "agent-cx",
    )
    assert inst.node.cwd == private / "checkout"
    assert not (private / "checkout" / "src" / "app.py").exists()


def test_graph_definition_detects_cycles() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "a": AgentNode(node_id="a"),
            "b": AgentNode(node_id="b"),
        },
        edges=[
            GraphEdge("a", "b"),
            GraphEdge("b", "a"),
        ],
    )

    with pytest.raises(ValueError):
        graph.validate_dag()


def test_graph_definition_validate_runnable_requires_start_to_end_path() -> None:
    graph = GraphDefinition(
        terminal_nodes={
            "start": BlueprintTerminalNode("start", "start"),
            "end": BlueprintTerminalNode("end", "end"),
        },
        agent_nodes={"a": AgentNode(node_id="a")},
        edges=[
            GraphEdge("start", "a"),
            GraphEdge("a", "end"),
        ],
    )

    graph.validate_runnable()

    missing_path = GraphDefinition(
        terminal_nodes={
            "start": BlueprintTerminalNode("start", "start"),
            "end": BlueprintTerminalNode("end", "end"),
        },
        agent_nodes={"a": AgentNode(node_id="a")},
        edges=[GraphEdge("start", "a")],
    )

    with pytest.raises(ValueError, match="path from start to end"):
        missing_path.validate_runnable()


def test_graph_definition_validate_runnable_rejects_duplicate_terminals() -> None:
    graph = GraphDefinition(
        terminal_nodes={
            "start-1": BlueprintTerminalNode("start-1", "start"),
            "start-2": BlueprintTerminalNode("start-2", "start"),
            "end": BlueprintTerminalNode("end", "end"),
        },
        edges=[GraphEdge("start-1", "end")],
    )

    with pytest.raises(ValueError, match="exactly one start"):
        graph.validate_runnable()


def test_graph_definition_validate_runnable_uses_exec_edges_for_path() -> None:
    graph = GraphDefinition(
        terminal_nodes={
            "start": BlueprintTerminalNode("start", "start"),
            "end": BlueprintTerminalNode("end", "end"),
        },
        edges=[GraphEdge("start", "end", edge_type="data")],
    )

    with pytest.raises(ValueError, match="path from start to end"):
        graph.validate_runnable()


def test_graph_definition_builds_agent_connections_and_organization_view() -> None:
    graph = GraphDefinition(
        terminal_nodes={
            "start": BlueprintTerminalNode("start", "start"),
            "end": BlueprintTerminalNode("end", "end"),
        },
        agent_nodes={
            "planner": AgentNode(
                node_id="planner",
                agent_id="worker-planner",
                cli_kind="codex",
                execution_mode="blocking",
            ),
            "coder": AgentNode(node_id="coder", write_scope=["src/**"]),
            "doc": AgentNode(node_id="doc", write_scope=["docs/**"]),
            "reviewer": AgentNode(node_id="reviewer"),
        },
        edges=[
            GraphEdge("start", "planner", edge_type="exec"),
            GraphEdge("planner", "coder", edge_type="exec"),
            GraphEdge("planner", "doc", edge_type="exec"),
            GraphEdge("planner", "reviewer", edge_type="data"),
            GraphEdge("coder", "reviewer", edge_type="exec"),
            GraphEdge("doc", "reviewer", edge_type="exec"),
            GraphEdge("reviewer", "end", edge_type="exec"),
        ],
    )

    assert graph.agent_connections() == {
        "planner": ["coder", "doc"],
        "coder": ["reviewer"],
        "doc": ["reviewer"],
        "reviewer": [],
    }

    view = graph.agent_organization_view()
    assert view["agent_connections"]["planner"] == ["coder", "doc"]
    assert view["start_policy"] == {
        "selected_by": "top_agent",
        "framework_role": "validate_only",
        "valid_start_nodes": ["planner", "coder", "doc", "reviewer"],
        "required_start_groups": [
            {
                "group_id": "start-group-planner",
                "node_ids": ["planner"],
                "required_count": 1,
                "kind": "source_agent",
            }
        ],
    }
    assert view["agents"]["planner"]["agent_id"] == "worker-planner"
    assert view["agents"]["planner"]["downstream_agents"] == ["coder", "doc"]
    assert view["agents"]["reviewer"]["upstream_agents"] == ["coder", "doc"]
    assert view["agents"]["coder"]["write_scope"] == ["src/**"]
    assert view["graph"]["terminal_nodes"] == {"start": "start", "end": "end"}


@pytest.mark.asyncio
async def test_graph_runtime_creates_outgoing_batch_from_graph_connections() -> None:
    cluster = _FakeCluster()
    graph = GraphDefinition(
        agent_nodes={
            "agent-a": AgentNode(node_id="agent-a", agent_id="worker-a"),
            "agent-b": AgentNode(node_id="agent-b", agent_id="worker-b"),
            "agent-c": AgentNode(node_id="agent-c", agent_id="worker-c"),
            "agent-d": AgentNode(node_id="agent-d", agent_id="worker-d"),
        },
        edges=[
            GraphEdge("agent-a", "agent-b", edge_type="exec"),
            GraphEdge("agent-a", "agent-c", edge_type="exec"),
            GraphEdge("agent-a", "agent-d", edge_type="data"),
        ],
    )
    runtime = GraphRuntime(cluster)

    batch = await runtime.create_outgoing_batch_from_graph(
        graph,
        "agent-a",
        batch_id="batch-1",
    )

    assert batch.required_target_node_ids == ["agent-b", "agent-c"]
    assert batch.required_target_agent_ids == ["worker-b", "worker-c"]
    assert cluster.started == ["worker-a", "worker-b", "worker-c"]

    with pytest.raises(ValueError, match="not reachable"):
        await runtime.create_outgoing_batch_from_graph(
            graph,
            "agent-a",
            required_target_node_ids=["agent-d"],
        )


def test_gulicode_top_agent_context_and_start_plan_validation() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "planner": AgentNode(node_id="planner", cli_kind="codex"),
            "coder": AgentNode(node_id="coder", write_scope=["src/**"]),
            "reviewer": AgentNode(node_id="reviewer"),
        },
        edges=[
            GraphEdge("planner", "coder", edge_type="exec"),
            GraphEdge("coder", "reviewer", edge_type="exec"),
        ],
    )
    profile = GuLiCodeTopAgentProfile()

    context = profile.organization_context(graph)
    assert context["top_agent"]["agent_id"] == "gulicode"
    assert "Choose start_nodes explicitly" in context["top_agent"]["rule"]
    assert context["organization"]["start_policy"]["selected_by"] == "top_agent"

    plan = TopAgentStartPlan.from_dict(
        {
            "user_goal": "Implement and review the feature.",
            "agent_descriptions": {
                "planner": "Breaks down the user goal and coordinates downstream work.",
                "coder": "Implements source changes.",
                "reviewer": "Reviews accepted changes and risks.",
            },
            "start_nodes": ["planner"],
            "tasks": {
                "planner": {
                    "goal": "Plan the implementation and decide downstream messages.",
                    "expected_output": "A staged dispatch plan for coder and reviewer.",
                    "acceptance": "Plan references concrete files and risks.",
                }
            },
            "run_policy": {"allow_parallel": True},
        }
    )
    validation = profile.validate_start_plan(graph, plan)

    assert validation.ok is True
    assert validation.errors == []
    assert validation.normalized_plan is not None
    assert validation.normalized_plan["start_nodes"] == ["planner"]
    assert validation.required_start_groups == [
        {
            "group_id": "start-group-planner",
            "node_ids": ["planner"],
            "required_count": 1,
            "kind": "source_agent",
        }
    ]


def test_graph_definition_required_start_groups_cover_source_components() -> None:
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
        ],
    )

    assert graph.required_start_groups() == [
        {
            "group_id": "start-group-a",
            "node_ids": ["a"],
            "required_count": 1,
            "kind": "source_agent",
        },
        {
            "group_id": "start-group-d",
            "node_ids": ["d"],
            "required_count": 1,
            "kind": "source_agent",
        },
    ]

    profile = GuLiCodeTopAgentProfile()
    valid = TopAgentStartPlan.from_dict(
        {
            "user_goal": "Run both components.",
            "agent_descriptions": {
                "a": "Starts ABC.",
                "b": "Middle.",
                "c": "End.",
                "d": "Independent.",
            },
            "start_nodes": ["a", "d"],
            "tasks": {
                "a": {
                    "goal": "Start ABC.",
                    "expected_output": "ABC flow dispatched.",
                    "acceptance": "B receives work.",
                },
                "d": {
                    "goal": "Handle D.",
                    "expected_output": "D result.",
                    "acceptance": "D completes.",
                },
            },
        }
    )
    assert profile.validate_start_plan(graph, valid).ok is True

    invalid = TopAgentStartPlan.from_dict(
        {
            **valid.to_dict(),
            "start_nodes": ["b"],
            "tasks": {
                "b": {
                    "goal": "Wrong start.",
                    "expected_output": "No.",
                    "acceptance": "No.",
                }
            },
        }
    )
    validation = profile.validate_start_plan(graph, invalid)
    assert validation.ok is False
    joined = "\n".join(validation.errors)
    assert "not valid source start nodes: b" in joined
    assert "missing required start group start-group-a" in joined
    assert "missing required start group start-group-d" in joined


def test_graph_definition_required_start_groups_allow_one_node_from_source_ring() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "a": AgentNode(node_id="a"),
            "b": AgentNode(node_id="b"),
            "c": AgentNode(node_id="c"),
        },
        edges=[
            GraphEdge("a", "b", edge_type="exec"),
            GraphEdge("b", "a", edge_type="exec"),
            GraphEdge("b", "c", edge_type="exec"),
        ],
    )

    assert graph.required_start_groups() == [
        {
            "group_id": "start-group-a-b",
            "node_ids": ["a", "b"],
            "required_count": 1,
            "kind": "source_component",
        }
    ]


def test_gulicode_top_agent_start_plan_validation_rejects_unsafe_shape() -> None:
    graph = GraphDefinition(
        agent_nodes={
            "planner": AgentNode(node_id="planner"),
            "coder": AgentNode(node_id="coder"),
        }
    )
    profile = GuLiCodeTopAgentProfile()
    plan = TopAgentStartPlan.from_dict(
        {
            "user_goal": "",
            "agent_descriptions": {"planner": "Plans.", "ghost": "Unknown."},
            "start_nodes": ["coder", "coder", "ghost"],
            "tasks": {
                "coder": {
                    "goal": "Do work.",
                    "expected_output": "",
                    "acceptance": "Done.",
                },
                "planner": {
                    "goal": "Extra task.",
                    "expected_output": "Nope.",
                    "acceptance": "Nope.",
                },
            },
        }
    )

    validation = profile.validate_start_plan(graph, plan)

    assert validation.ok is False
    assert validation.normalized_plan is None
    joined = "\n".join(validation.errors)
    assert "user_goal is required" in joined
    assert "missing: coder" in joined
    assert "unknown AgentNode ids: ghost" in joined
    assert "start_nodes contains unknown AgentNode ids: ghost" in joined
    assert "start_nodes must not contain duplicates" in joined
    assert "task 'coder' missing required fields: expected_output" in joined
    assert "tasks contains entries for non-start nodes: planner" in joined


def test_compile_ryven_flow_builds_graph_definition_with_port_semantics() -> None:
    import os

    os.environ["RYVEN_MODE"] = "no-gui"
    from multi_agent_tcp.ryven_launcher import _BLUEPRINT_NODES_PACKAGE, _ensure_vendor_paths

    _ensure_vendor_paths()
    from ryven.main.packages.nodes_package import import_nodes_package
    from ryvencore import Session

    node_types, _ = import_nodes_package(directory=str(_BLUEPRINT_NODES_PACKAGE))
    agent_cls = next(node_type for node_type in node_types if node_type.title == "AgentNode")

    session = Session()
    session.register_node_types(node_types)
    flow = session.create_flow("compile-test")
    start = next(node for node in flow.nodes if node.title == "Start")
    end = next(node for node in flow.nodes if node.title == "End")

    first = flow.create_node(agent_cls)
    second = flow.create_node(agent_cls)
    first.set_agent_config({"node_id": "agent-a", "agent_id": "worker-a", "cwd": "."})
    second.set_agent_config({"node_id": "agent-b", "agent_id": "worker-b", "cwd": "."})

    flow.connect_nodes(start.outputs[0], first.inputs[0])
    flow.connect_nodes(first.outputs[0], second.inputs[0])
    flow.connect_nodes(first.outputs[1], second.inputs[1])
    flow.connect_nodes(second.outputs[0], end.inputs[0])

    graph = compile_ryven_flow(flow, validate=True)

    assert set(graph.terminal_nodes) == {"blueprint-start", "blueprint-end"}
    assert set(graph.agent_nodes) == {"agent-a", "agent-b"}
    assert graph.agent_nodes["agent-a"].runtime_agent_id == "worker-a"
    assert [
        (edge.source, edge.target, edge.output_port, edge.input_port, edge.edge_type)
        for edge in graph.edges
    ] == [
        ("blueprint-start", "agent-a", "next", "in", "exec"),
        ("agent-a", "agent-b", "out", "in", "exec"),
        ("agent-a", "agent-b", "result", "prompt", "data"),
        ("agent-b", "blueprint-end", "out", "done", "exec"),
    ]


@pytest.mark.asyncio
async def test_graph_executor_routes_to_cluster_primitives() -> None:
    cluster = _RouteCluster()
    executor = GraphExecutor(GraphRuntime(cluster))
    tasks = [("a", {"prompt": "A"}), ("b", {"prompt": "B"})]

    parallel = await executor.run_route(RouteNode("r1", "parallel"), tasks)
    sequence = await executor.run_route(RouteNode("r2", "sequence"), tasks)
    reduced = await executor.run_route(
        RouteNode("r3", "parallel_reduce", reduce_target="a", reduce_prompt="merge {results}"),
        tasks,
    )

    assert parallel["route"] == "parallel"
    assert sequence[0]["route"] == "sequence"
    assert reduced["route"] == "parallel_reduce"
    assert cluster.parallel_tasks == [tasks]
    assert cluster.chain_tasks == [tasks]
    assert cluster.reduce_tasks == [(tasks, "a", "merge {results}")]


@pytest.mark.asyncio
async def test_graph_executor_runs_minimal_blueprint_and_starts_agents() -> None:
    cluster = _FakeCluster()
    runtime = GraphRuntime(cluster)
    executor = GraphExecutor(runtime)
    graph = GraphDefinition(
        terminal_nodes={
            "start": BlueprintTerminalNode("start", "start"),
            "end": BlueprintTerminalNode("end", "end"),
        },
        agent_nodes={
            "a": AgentNode(node_id="a", prompt="first", timeout_sec=12),
            "b": AgentNode(node_id="b", prompt="second", timeout_sec=13),
        },
        edges=[
            GraphEdge("start", "a", output_port="next", input_port="in", edge_type="exec"),
            GraphEdge("a", "b", output_port="out", input_port="in", edge_type="exec"),
            GraphEdge("a", "b", output_port="result", input_port="prompt", edge_type="data"),
            GraphEdge("b", "end", output_port="out", input_port="done", edge_type="exec"),
        ],
    )
    events = []

    result = await executor.run_blueprint(graph, event_callback=events.append)

    assert result["ok"] is True
    assert result["executed_nodes"] == ["a", "b"]
    assert cluster.started == ["a", "b"]
    assert cluster.sent[0] == ("a", {"prompt": "first"}, 12)
    assert cluster.sent[1][0] == "b"
    assert "prompt" in cluster.sent[1][1]
    assert [event.event_type for event in events] == [
        "BlueprintStarted",
        "NodeQueued",
        "NodeRunning",
        "NodeCompleted",
        "NodeQueued",
        "NodeRunning",
        "NodeCompleted",
        "BlueprintCompleted",
    ]


@pytest.mark.asyncio
async def test_graph_executor_auto_joins_multi_input_exec_edges() -> None:
    cluster = _FakeCluster()
    runtime = GraphRuntime(cluster)
    executor = GraphExecutor(runtime)
    graph = GraphDefinition(
        terminal_nodes={
            "start": BlueprintTerminalNode("start", "start"),
            "end": BlueprintTerminalNode("end", "end"),
        },
        agent_nodes={
            "coder": AgentNode(node_id="coder", prompt="code"),
            "doc": AgentNode(node_id="doc", prompt="docs"),
            "reviewer": AgentNode(node_id="reviewer", prompt="review"),
        },
        edges=[
            GraphEdge("start", "coder", edge_type="exec"),
            GraphEdge("start", "doc", edge_type="exec"),
            GraphEdge("coder", "reviewer", edge_type="exec"),
            GraphEdge("doc", "reviewer", edge_type="exec"),
            GraphEdge("reviewer", "end", edge_type="exec"),
        ],
    )

    result = await executor.run_blueprint(graph)

    assert result["ok"] is True
    assert result["executed_nodes"] == ["coder", "doc", "reviewer"]
    assert cluster.sent[0] == ("coder", {"prompt": "code"}, 1800.0)
    assert cluster.sent[1] == ("doc", {"prompt": "docs"}, 1800.0)
    assert cluster.sent[2][0] == "reviewer"
    assert cluster.sent[2][1]["type"] == "join_aggregate"
    assert cluster.sent[2][1]["aggregate"]["required_source_node_ids"] == ["coder", "doc"]
    assert runtime.join_barriers["join-reviewer-3"].aggregate_message_id == "join-msg-join-reviewer-3"
    assert runtime.pending_messages["join-msg-join-reviewer-3"].status == "completed"
    assert "JoinBarrierAggregateQueued" in [event.event_type for event in runtime.events]


def test_graph_runtime_complete_writes_final_report_and_archive_index(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-final")
    runtime = GraphRuntime(_FakeCluster(), archive_manager=manager, archive_run=run)

    result = runtime.end_run("complete", reason="done")

    assert result.final_status == "success"
    assert result.archived is True
    archive_path = Path(result.summary["archive_path"])
    report_path = archive_path / "shared" / "reports" / "final_report.json"
    assert Path(result.summary["final_report_path"]) == report_path
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["final_status"] == "success"
    archives = manager.list_long_term_archives()
    assert archives[0]["archive_id"] == "run-final-completed"
    assert "FinalReportPublished" in [event.event_type for event in runtime.events]
    assert "RunArchiveIndexed" in [event.event_type for event in runtime.events]


def test_graph_runtime_workspace_status_hydrates_shared_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    (tmp_path / "src").mkdir()
    manager = DulwichWorkspaceManager.open_or_init(tmp_path, workspace_id="ws-outputs")
    run = manager.create_run(run_id="run-outputs")
    private = manager.agent_workspace_dir(run, "agent-coder")
    server = WorkspaceRPCServer(manager, run)
    server.start()
    try:
        context_path = private / "workspace_api_context.json"
        context_path.write_text(
            json.dumps(server.context_for("agent-coder"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        monkeypatch.setenv(WORKSPACE_API_CONTEXT_ENV, str(context_path))

        assert workspace_api_main(
            ["publish", "--area", "reports", "--path", "summary.md", "--text", "report ok"]
        ) == 0
        report_out = json.loads(capsys.readouterr().out)
        artifact_source = private / "build.log"
        artifact_source.write_text("build ok\n", encoding="utf-8")
        assert workspace_api_main(
            [
                "publish-file",
                "--area",
                "artifacts",
                "--path",
                "logs/build.log",
                "--file",
                str(artifact_source),
            ]
        ) == 0
        artifact_out = json.loads(capsys.readouterr().out)

        runtime = GraphRuntime(_FakeCluster(), archive_manager=manager, archive_run=run)
        workspace = runtime.status_snapshot()["workspace"]

        assert workspace["workspace_id"] == "ws-outputs"
        assert workspace["workspace_root"] == str(run.path.resolve())
        assert workspace["shared_root"] == str(run.shared_dir.resolve())
        assert workspace["directories"]["reports"] == str(run.shared_reports_dir.resolve())
        assert workspace["directories"]["artifacts"] == str(run.shared_artifacts_dir.resolve())
        assert workspace["reports"] == [
            {
                "area": "reports",
                "name": "summary.md",
                "path": "summary.md",
                "absolute_path": str((run.shared_reports_dir / "summary.md").resolve()),
                "version": report_out["version"],
                "owner": "agent-coder",
                "updated_at": workspace["reports"][0]["updated_at"],
                "lease_id": workspace["reports"][0]["lease_id"],
            }
        ]
        assert workspace["artifacts"][0]["area"] == artifact_out["area"]
        assert workspace["artifacts"][0]["path"] == artifact_out["path"]
        assert workspace["artifacts"][0]["absolute_path"] == str((run.shared_artifacts_dir / "logs" / "build.log").resolve())
        assert workspace["artifacts"][0]["version"] == artifact_out["version"]
    finally:
        server.close()


def test_graph_runtime_workspace_status_hydrates_accepted_changesets(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('base')\n", encoding="utf-8")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path, workspace_id="ws-changes")
    run = manager.create_run(run_id="run-changes", code_mode="project_reference")
    checkout = manager.checkout_agent(run, "agent-coder", write_scope=["src/**"])
    (checkout.checkout_dir / "src" / "app.py").write_text("print('changed')\n", encoding="utf-8")
    result = manager.submit_checkout(run, checkout, task_id="task-code", summary="change app")

    runtime = GraphRuntime(_FakeCluster(), archive_manager=manager, archive_run=run)
    workspace = runtime.status_snapshot()["workspace"]

    assert result.status == "accepted"
    assert workspace["workspace_id"] == "ws-changes"
    assert workspace["directories"]["changesets"] == str((run.path / "changesets").resolve())
    assert workspace["changesets"] == [
        {
            "changeset_id": result.changeset_id,
            "name": result.changeset_id,
            "path": result.changeset_id,
            "absolute_path": str((run.path / "changesets" / result.changeset_id).resolve()),
            "files": ["src/app.py"],
            "agent_id": "agent-coder",
            "status": "accepted",
            "integration_ref": result.integration_ref,
        }
    ]


@pytest.mark.asyncio
async def test_message_journal_is_archived_with_run_workspace(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-journal")
    runtime = GraphRuntime(_FakeCluster(), archive_manager=manager, archive_run=run)

    await runtime.send_agent_message(
        AgentNode(node_id="summary", agent_id="agent-summary", cwd=Path(".")),
        {"prompt": "write archiveable message journal"},
    )
    result = runtime.end_run("complete", reason="done")

    archive_path = Path(result.summary["archive_path"])
    journal_path = archive_path / "shared" / "logs" / "message_journal.jsonl"
    assert result.final_status == "success"
    assert journal_path.is_file()
    records = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [record["record_type"] for record in records] == [
        "framework.message.sent",
        "agent.reply.received",
    ]


@pytest.mark.asyncio
async def test_agent_workspace_outputs_feed_join_and_final_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('base')\n", encoding="utf-8")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-output-chain")
    private = manager.agent_workspace_dir(run, "agent-coder")
    server = WorkspaceRPCServer(manager, run)
    server.start()
    try:
        context_path = private / "workspace_api_context.json"
        context_path.write_text(
            json.dumps(server.context_for("agent-coder"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        monkeypatch.setenv(WORKSPACE_API_CONTEXT_ENV, str(context_path))

        assert workspace_api_main(["checkout", "--scope-path", "src/**"]) == 0
        checkout_out = json.loads(capsys.readouterr().out)
        checkout_path = Path(checkout_out["checkout_path"])
        (checkout_path / "src" / "app.py").write_text("print('changed')\n", encoding="utf-8")

        assert workspace_api_main(["status"]) == 0
        status_out = json.loads(capsys.readouterr().out)
        assert status_out["files"][0]["path"] == "src/app.py"

        assert workspace_api_main(["submit", "--task-id", "task-code", "--summary", "change app"]) == 0
        changeset = json.loads(capsys.readouterr().out)
        assert changeset["ok"] is True
        assert changeset["status"] == "accepted"
        assert changeset["merged_files"] == ["src/app.py"]
        assert (run.integration_dir / "src" / "app.py").read_text(encoding="utf-8") == "print('changed')\n"

        assert workspace_api_main(
            ["publish", "--area", "reports", "--path", "coder.md", "--text", "implemented"]
        ) == 0
        report_out = json.loads(capsys.readouterr().out)
        artifact_source = private / "build.log"
        artifact_source.write_text("build ok\n", encoding="utf-8")
        assert workspace_api_main(
            [
                "publish-file",
                "--area",
                "artifacts",
                "--path",
                "logs/build.log",
                "--file",
                str(artifact_source),
            ]
        ) == 0
        artifact_out = json.loads(capsys.readouterr().out)

        runtime = GraphRuntime(_FakeCluster(), archive_manager=manager, archive_run=run)
        target = AgentNode(node_id="reviewer", agent_id="worker-reviewer", cwd=Path("."))
        await runtime.ensure_agent(target)
        runtime.create_join_barrier(
            required_sources=["coder"],
            target_node=target,
            policy="wait-all",
            join_id="join-products",
        )
        contribution = runtime.submit_join_contribution(
            "join-products",
            "coder",
            source_agent_id="agent-coder",
            accepted_changesets=[
                {
                    "changeset_id": changeset["changeset_id"],
                    "status": changeset["status"],
                    "merged_files": changeset["merged_files"],
                    "archive_path": changeset["archive_path"],
                }
            ],
            artifacts=[
                {
                    "area": artifact_out["area"],
                    "path": artifact_out["path"],
                    "owner": artifact_out["owner"],
                    "version": artifact_out["version"],
                }
            ],
            reports=[
                {
                    "area": report_out["area"],
                    "path": report_out["path"],
                    "owner": report_out["owner"],
                    "version": report_out["version"],
                }
            ],
            test_results=[{"name": "workspace-output-chain", "status": "passed"}],
            metadata={"task_id": "task-code"},
        )

        assert contribution["ready"] is True
        aggregate = contribution["aggregate"]
        assert aggregate["accepted_changesets"][0]["changeset_id"] == changeset["changeset_id"]
        assert aggregate["reports"] == [
            {"area": "reports", "path": "coder.md", "owner": "agent-coder", "version": 1}
        ]
        assert aggregate["artifacts"] == [
            {"area": "artifacts", "path": "logs/build.log", "owner": "agent-coder", "version": 1}
        ]
        assert runtime.agent_message_queues["reviewer"][0].body["aggregate"]["test_results"] == [
            {"name": "workspace-output-chain", "status": "passed"}
        ]
        pending = await runtime.dispatch_queued_message_now("join-msg-join-products")
        assert pending.status == "completed"
        assert pending.receipt is not None
        assert pending.receipt["node_id"] == "reviewer"

        result = runtime.end_run("complete", reason="products verified")
        assert result.final_status == "success"
        assert result.summary["accepted_changesets"][0]["changeset_id"] == changeset["changeset_id"]
        final_report = Path(result.summary["final_report_path"])
        assert final_report.is_file()
        report = json.loads(final_report.read_text(encoding="utf-8"))
        assert report["summary"]["accepted_changesets"][0]["merged_files"] == ["src/app.py"]
        assert report["status_snapshot"]["joins"]["join-products"]["reports"][0]["path"] == "coder.md"
        assert report["status_snapshot"]["joins"]["join-products"]["artifacts"][0]["path"] == "logs/build.log"
    finally:
        server.close()


@pytest.mark.asyncio
async def test_super_agent_assigns_downstream_workdir_by_runtime_api(tmp_path: Path) -> None:
    assigned = tmp_path / "assigned-project"
    assigned.mkdir()
    cluster = _RestartableCluster()
    runtime = GraphRuntime(cluster)
    target = AgentNode(node_id="target", agent_id="worker-target", cwd=tmp_path)
    super_agent = SuperAgentProfile(
        agent_id="super",
        can_assign_downstream_workdir=True,
        assignable_workdir_roots=[tmp_path],
    )

    await runtime.prestart_agents([target])
    result = await runtime.assign_agent_workdir(
        super_agent=super_agent,
        target_node_id="target",
        cwd=assigned,
    )

    assert result.ok is True
    assert result.cwd == assigned.resolve()
    assert cluster.started == ["worker-target"]
    assert cluster.restarted == ["worker-target"]
    assert cluster.worker_cwds["worker-target"] == assigned.resolve()


@pytest.mark.asyncio
async def test_workdir_assignment_rejects_busy_agent(tmp_path: Path) -> None:
    cluster = _RestartableCluster()
    runtime = GraphRuntime(cluster)
    target = AgentNode(node_id="target", agent_id="worker-target", cwd=tmp_path)
    super_agent = SuperAgentProfile(
        agent_id="super",
        can_assign_downstream_workdir=True,
        assignable_workdir_roots=[tmp_path],
    )

    inst = await runtime.ensure_agent(target)
    inst.busy_count = 1
    result = await runtime.assign_agent_workdir(
        super_agent=super_agent,
        target_node_id="target",
        cwd=tmp_path,
    )

    assert result.ok is False
    assert result.error_code == "AGENT_BUSY"
    assert cluster.restarted == []


@pytest.mark.asyncio
async def test_cli_worker_backend_waits_for_worker_timeout_reply_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.sent: list[tuple[str, Any, dict[str, Any] | None]] = []
            self.wait_timeout_sec: float | None = None

        async def send_to(
            self,
            worker_id: str,
            body: Any,
            *,
            meta: dict[str, Any] | None = None,
        ) -> None:
            self.sent.append((worker_id, body, meta))

        async def wait_for_message(
            self,
            *,
            expect_from: str | None = None,
            timeout_sec: float = 300.0,
            stream_callback: Any = None,
        ) -> dict[str, Any]:
            self.wait_timeout_sec = timeout_sec
            if stream_callback is not None:
                await stream_callback({"kind": "part.delta", "delta": "progress"})
            return {"type": "message", "from": expect_from, "body": {"ok": True}}

    backend = CLIWorkerBackend()
    fake_client = FakeClient()
    stream_events: list[dict[str, Any]] = []

    async def fake_ensure_client() -> FakeClient:
        return fake_client

    monkeypatch.setattr(backend, "_ensure_client", fake_ensure_client)

    reply = await backend.run_single(
        "agent-a",
        {"prompt": "work"},
        timeout_sec=2.0,
        meta={"framework_stream": {"node_id": "agent-a"}},
        stream_callback=lambda event: stream_events.append(event),
    )

    assert reply["body"]["ok"] is True
    assert fake_client.sent == [
        ("agent-a", {"prompt": "work"}, {"framework_stream": {"node_id": "agent-a"}})
    ]
    assert fake_client.wait_timeout_sec == 32.0
    assert stream_events == [{"kind": "part.delta", "delta": "progress"}]


@pytest.mark.asyncio
async def test_codemaker_adapter_reuses_instance_for_multiple_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str | None, dict[str, Any]]] = []

    async def fake_codemaker_run(
        prompt: str,
        *,
        stdin_context: str | None = None,
        codemaker_cfg: dict[str, Any],
    ) -> dict[str, Any]:
        calls.append((prompt, stdin_context, codemaker_cfg))
        return {
            "returncode": 0,
            "stdout": '{"type":"text","part":{"text":"ok"}}',
            "stderr": "",
            "timeout": False,
        }

    monkeypatch.setattr("multi_agent_tcp.adapters.codemaker_run", fake_codemaker_run)
    adapter = CodeMakerAdapter("agent-a", {"cwd": Path("."), "extra_env": {"A": "B"}})

    await adapter.start()
    first = await adapter.send_message(AgentMessage(prompt="one", context="ctx"))
    second = await adapter.send_message(AgentMessage(prompt="two"))
    await adapter.close()

    assert isinstance(first, AdapterResult)
    assert first.ok is True
    assert second.ok is True
    assert adapter.messages_handled == 2
    assert calls[0][0:2] == ("one", "ctx")
    assert calls[1][0:2] == ("two", None)
    assert first.payload["adapter"]["persistent_instance"] is True
    assert first.payload["adapter"]["per_message_subprocess"] is True


@pytest.mark.asyncio
async def test_codex_adapter_reuses_instance_for_multiple_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str | None, list[Any], dict[str, Any]]] = []

    async def fake_codex_run(
        prompt: str,
        *,
        stdin_context: str | None = None,
        attachments: list[Any] | None = None,
        codex_cfg: dict[str, Any],
        stream_callback: Any = None,
        stream_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls.append((prompt, stdin_context, list(attachments or []), codex_cfg))
        return {
            "returncode": 0,
            "stdout": '{"type":"message","message":"ok"}',
            "stderr": "",
            "timeout": False,
            "final_text": "ok",
        }

    monkeypatch.setattr("multi_agent_tcp.adapters.codex_run", fake_codex_run)
    adapter = CodexAdapter("agent-cx", {"cwd": Path("."), "model": "gpt-5.4"})

    await adapter.start()
    first = await adapter.send_message(
        AgentMessage(prompt="one", context="ctx", attachments=[{"kind": "image", "value": "a.png"}])
    )
    second = await adapter.send_message(AgentMessage(prompt="two"))
    await adapter.close()

    assert isinstance(first, AdapterResult)
    assert first.ok is True
    assert second.ok is True
    assert adapter.messages_handled == 2
    assert calls[0][0:3] == ("one", "ctx", [{"kind": "image", "value": "a.png"}])
    assert calls[1][0:3] == ("two", None, [])
    assert first.payload["codex"]["final_text"] == "ok"
    assert first.payload["adapter"]["persistent_instance"] is True
    assert first.payload["adapter"]["per_message_subprocess"] is True


def test_extract_codex_final_text_from_jsonl_message() -> None:
    stdout = (
        '{"type":"task_started"}\n'
        '{"type":"item.completed","item":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"first"}]}}\n'
        '{"type":"message","message":"final"}\n'
    )

    assert extract_codex_final_text(stdout) == "final"
