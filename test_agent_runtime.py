from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from multi_agent_tcp import (
    AdapterResult,
    AgentMessage,
    AgentNode,
    AgentSkillSelection,
    BlueprintTerminalNode,
    CodexAdapter,
    CodeMakerAdapter,
    GraphDefinition,
    GraphEdge,
    GraphExecutor,
    GraphRuntime,
    MultiModalEnvelope,
    RouteNode,
    WorkspaceManifest,
    WorkerConfig,
    adapter_from_agent_config,
    body_to_agent_message,
    compile_ryven_flow,
    extract_codex_final_text,
    normalize_envelope,
)

from multi_agent_tcp.skill_space import SkillSpace, SuperAgentProfile


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
    assert node.execution_mode == "nonblocking"
    assert worker.agent_id == "agent-1"
    assert worker.cli_kind == "codemaker"
    assert worker.adapter_options == {"prompt_via_file": "always"}
    assert worker.extra_env == {"A": "1"}
    assert node.read_scope == ["src"]
    assert node.write_scope == ["out"]
    assert node.artifact_scope == ["artifacts"]


def test_agent_node_from_dict_auto_generates_node_id() -> None:
    node = AgentNode.from_dict({"cwd": "."})

    assert node.node_id.startswith("agent-node-")
    assert node.runtime_agent_id == node.node_id


def test_agent_node_to_dict_round_trips_ui_config() -> None:
    node = AgentNode.from_dict(
        {
            "node_id": "node-ui",
            "agent_id": "agent-ui",
            "cli_kind": "codex",
            "model": "gpt-5.4",
            "cwd": ".",
            "skill_selection": {"mode": "selected", "skill_hashes": ["hash-a"]},
        }
    )

    restored = AgentNode.from_dict(node.to_dict())

    assert restored.node_id == "node-ui"
    assert restored.runtime_agent_id == "agent-ui"
    assert restored.cli_kind == "codex"
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
    assert upstream_node.resolve_skill_hashes(
        space,
        upstream_super_agent=super_agent,
        upstream_skill_hashes=[rec_b.skill_hash],
    ) == [rec_b.skill_hash]

    with pytest.raises(PermissionError):
        upstream_node.resolve_skill_hashes(space, upstream_skill_hashes=[rec_b.skill_hash])
    with pytest.raises(PermissionError):
        upstream_node.resolve_skill_hashes(
            space,
            upstream_super_agent=super_agent,
            upstream_skill_hashes=[rec_a.skill_hash],
        )


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

    async def ensure_worker(self, worker: WorkerConfig) -> None:
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
    assert reply["body"]["ok"] is True


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


def test_workspace_manifest_rejects_scope_escape(tmp_path: Path) -> None:
    manifest = WorkspaceManifest("ws-1", tmp_path)

    with pytest.raises(ValueError):
        manifest.validate_scopes(write_scope=[".."])


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
