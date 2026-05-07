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
from multi_agent_tcp.codemaker_bridge import _merge_prompt as _merge_codemaker_prompt
from multi_agent_tcp.codemaker_bridge import load_codemaker_runtime
from multi_agent_tcp.codex_bridge import load_codex_runtime
from multi_agent_tcp.ryven_blueprint import _apply_run_workspace_to_node
from multi_agent_tcp.workspace_manager import DulwichWorkspaceManager
from multi_agent_tcp.workspace_rpc import WorkspaceRPCServer


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
    assert first_reply["body"]["idx"] == 0
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
    assert pending.result["body"]["idx"] == 1
    assert runtime.instances["node-a"].messages_sent == 2
    states = [entry["state"] for entry in runtime.instances["node-a"].state_history]
    assert "starting" in states
    assert "idle" in states
    assert "dispatching" in states
    assert "running" in states
    assert "waiting_for_reply" in states
    assert "processing_reply" in states


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
        context_path = private / "workspace_api_context.json"
        context = context_path.read_text(encoding="utf-8")
        assert '"transport": "rpc"' in context
        assert str(manager.workspace_root) not in context
        assert str(run.path) not in context
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
