from __future__ import annotations

import asyncio
import json
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
    GuLiCodeTopAgentProfile,
    GraphDefinition,
    GraphEdge,
    GraphExecutor,
    GraphJob,
    GraphRuntime,
    MultiModalEnvelope,
    RouteNode,
    TopAgentStartPlan,
    WorkspaceManifest,
    WorkerConfig,
    adapter_from_agent_config,
    body_to_agent_message,
    compile_ryven_flow,
    extract_codex_final_text,
    normalize_envelope,
)

from multi_agent_tcp.skill_space import SkillSpace, SuperAgentProfile
from multi_agent_tcp.workspace_rpc import WorkspaceRPCServer
from multi_agent_tcp.codemaker_bridge import _merge_prompt as _merge_codemaker_prompt
from multi_agent_tcp.codemaker_bridge import load_codemaker_runtime
from multi_agent_tcp.codex_bridge import _merge_prompt as _merge_codex_prompt
from multi_agent_tcp.codex_bridge import load_codex_runtime
from multi_agent_tcp.ryven_blueprint import _apply_run_workspace_to_node
from multi_agent_tcp.workspace_api import CONTEXT_ENV as WORKSPACE_API_CONTEXT_ENV
from multi_agent_tcp.workspace_api import main as workspace_api_main
from multi_agent_tcp.workspace_manager import DulwichWorkspaceManager


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
    assert runtime.instances["node-a"].messages_sent == 2
    states = [entry["state"] for entry in runtime.instances["node-a"].state_history]
    assert "starting" in states
    assert "idle" in states
    assert "dispatching" in states
    assert "running" in states
    assert "waiting_for_reply" in states
    assert "processing_reply" in states


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
        assert "Business Review Rule" in (checkout / "AGENTS.md").read_text(encoding="utf-8")
        assert (private / "rules" / "01-business-rule.md").is_file()
        assert (codex_home / "skills" / "framework-agent-runtime" / "SKILL.md").is_file()
        framework_skill = (
            codex_home / "skills" / "framework-agent-runtime" / "SKILL.md"
        ).read_text(encoding="utf-8")
        assert "framework-private utterance record" in framework_skill
        assert "not a communication channel to other AgentNodes" in framework_skill
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
        assert "Workspace API" in merged_prompt
        assert "Codex Execution Context" in merged_prompt
        assert "checkout_path" in merged_prompt
        assert json.dumps(str(checkout), ensure_ascii=False)[1:-1] in merged_prompt
        assert "project_context" in merged_prompt
        assert json.dumps(str(project), ensure_ascii=False)[1:-1] in merged_prompt
        assert "PRIVATE_RUNTIME_SKILL_DESCRIPTION" in merged_prompt
        assert "outgoing_batch_id" in merged_prompt
        assert "out-1" in merged_prompt
        private_context = inst.node.adapter_options["execution_context"]["private_context"]
        assert private_context["codex_home"] == str(codex_home)
        assert private_context["rule_catalog"][0]["rule_path"] == str(private / "rules" / "01-business-rule.md")
        assert (private / "workspace_api_context.json").is_file()
    finally:
        server.close()


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
