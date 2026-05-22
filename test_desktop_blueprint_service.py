from __future__ import annotations

import json
import asyncio
import inspect
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib import request

import pytest

from multi_agent_tcp.desktop_blueprint_service import (
    BlueprintServiceError,
    DesktopBlueprintHTTPServer,
    DesktopBlueprintNoopBackend,
    DesktopBlueprintService,
)
from multi_agent_tcp.blueprint_mcp_runtime import (
    MCP_TOOL_AUDIT_EVENT,
    MCPTokenScope,
    RunMCPRuntimeHandle,
    RunMCPTokenStore,
    resolve_allowed_publish_file,
)
from multi_agent_tcp.codex_bridge import codex_jsonl_event_to_agent_stream_events
from multi_agent_tcp.agent_launch_context import (
    write_private_codex_mcp_config,
)
from multi_agent_tcp.client import AgentTCPClient
from multi_agent_tcp.workspace_manager import DulwichWorkspaceManager


def _document(project_dir: Path | None = None) -> dict:
    ui = {
        "nodes": {"planner": {"x": 120, "y": 96}},
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }
    if project_dir is not None:
        ui["config"] = {
            "python_path": sys.executable,
            "project_workdir": str(project_dir),
            "skill_dir": "",
            "rule_dir": "",
        }
    return {
        "schema_version": 1,
        "id": "default",
        "name": "Default Blueprint",
        "graph": {
            "terminal_nodes": {"start": "start", "end": "end"},
            "agent_nodes": {
                "planner": {
                    "node_id": "planner",
                    "agent_id": "agent-planner",
                    "prompt": "Plan.",
                }
            },
            "route_nodes": {},
            "edges": [
                {"from": "start", "to": "planner", "edge_type": "exec"},
                {"from": "planner", "to": "end", "edge_type": "exec"},
            ],
        },
        "ui": ui,
    }


def _plan() -> dict:
    return {
        "user_goal": "Ship the plan.",
        "agent_descriptions": {
            "planner": "Plans the work.",
        },
        "start_nodes": ["planner"],
        "tasks": {
            "planner": {
                "goal": "Plan the work.",
                "expected_output": "A clear implementation plan.",
                "acceptance": "The plan is actionable.",
            },
        },
        "run_policy": {},
    }


def _codex_real_flow_config_overrides() -> list[str]:
    overrides = [
        'approval_policy="never"',
        'model_reasoning_effort="low"',
        'shell_environment_policy.inherit="all"',
    ]
    if sys.platform == "win32":
        overrides.append('windows.sandbox="unelevated"')
    return overrides


def _real_codex_mcp_project_root(tmp_path: Path) -> tuple[Path, Path | None]:
    if sys.platform != "win32":
        return tmp_path / "project", None
    root = Path(
        os.environ.get("MULTI_AGENT_TCP_REAL_CODEX_MCP_ROOT")
        or Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
        / "multi_agent_tcp"
        / "real_codex_mcp"
    )
    root.mkdir(parents=True, exist_ok=True)
    project = Path(tempfile.mkdtemp(prefix="project-", dir=str(root)))
    return project, project


def _workspace_manifest_entries(run: object, event_type: str) -> list[dict]:
    manifest_path = run.shared_dir / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    writes = data.get("writes", [])
    assert isinstance(writes, list)
    return [
        item
        for item in writes
        if isinstance(item, dict) and item.get("event_type") == event_type
    ]


def _wait_for_live_run_idle(
    service: DesktopBlueprintService,
    run_id: str,
    *,
    timeout_sec: float = 480.0,
) -> dict:
    deadline = time.monotonic() + timeout_sec
    last_status: dict = {}
    while time.monotonic() < deadline:
        last_status = service.status_blueprint_run(run_id)["status"]
        pending = last_status["queues"]["pending_messages"].values()
        queue_empty = all(not items for items in last_status["queues"]["by_agent"].values())
        pending_done = all(
            item.get("status") in {"completed", "failed", "cancelled"}
            for item in pending
        )
        agents_done = all(
            item.get("state") in {"idle", "failed", "timed_out", "cancelled"}
            for item in last_status["agents"].values()
        )
        if queue_empty and pending_done and agents_done:
            return last_status
        time.sleep(0.5)
    raise AssertionError(json.dumps(last_status, ensure_ascii=False, indent=2, default=str))


def _stream_raw_commands(status: dict) -> list[str]:
    commands: list[str] = []
    for event in status.get("agent_stream_events", []):
        raw = event.get("raw")
        if not isinstance(raw, dict):
            continue
        item = raw.get("item")
        if isinstance(item, dict) and item.get("type") == "command_execution":
            command = item.get("command")
            if isinstance(command, str):
                commands.append(command)
    return commands


def _stream_mcp_tool_calls(status: dict) -> list[dict]:
    calls: list[dict] = []
    for event in status.get("agent_stream_events", []):
        raw = event.get("raw")
        if not isinstance(raw, dict):
            continue
        item = raw.get("item")
        if not isinstance(item, dict) or item.get("type") != "mcp_tool_call":
            continue
        error = item.get("error")
        calls.append(
            {
                "server": item.get("server"),
                "tool": item.get("tool"),
                "status": item.get("status"),
                "error": error.get("message") if isinstance(error, dict) else error,
            }
        )
    return calls


def _planning_control_scope(session) -> MCPTokenScope:
    for scope in session.mcp.token_store._scopes_by_token.values():
        if scope.server_kind == "control":
            return scope
    raise AssertionError("missing planning control MCP scope")


def _mcp_url_from_private_codex_home(codex_home: Path, server_name: str) -> str:
    in_target = False
    for line in (codex_home / "config.toml").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == f"[mcp_servers.{server_name}]":
            in_target = True
            continue
        if in_target and stripped.startswith("[") and stripped.endswith("]"):
            break
        if in_target and stripped.startswith("url ="):
            return json.loads(stripped.split("=", 1)[1].strip())
    raise AssertionError(f"missing MCP url for {server_name}")


def test_private_codex_mcp_config_enables_tools_and_clears_stale_nested_tables(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text(
        "[mcp_servers.framework_ordinary]\n"
        "url = \"http://old.example/mcp\"\n"
        "bearer_token_env_var = \"OLD_TOKEN\"\n\n"
        "[mcp_servers.framework_ordinary.tools.workspace_checkout]\n"
        "approval_mode = \"ask\"\n\n"
        "[mcp_servers.keep]\n"
        "url = \"http://keep.example/mcp\"\n",
        encoding="utf-8",
    )

    write_private_codex_mcp_config(
        codex_home,
        server_name="framework_ordinary",
        url="http://127.0.0.1:1234/ordinary/mcp",
        bearer_token_env_var="MULTI_AGENT_MCP_ORDINARY_TOKEN",
        tools=["workspace_submit", "agent_dispatch"],
    )

    config_text = config_path.read_text(encoding="utf-8")
    assert "[mcp_servers.keep]" in config_text
    assert "http://old.example/mcp" not in config_text
    assert "OLD_TOKEN" not in config_text
    assert "[mcp_servers.framework_ordinary.tools.workspace_checkout]" not in config_text
    assert "[mcp_servers.framework_ordinary]" in config_text
    assert "enabled = true" in config_text
    assert 'enabled_tools = ["workspace_submit", "agent_dispatch"]' in config_text
    assert "[mcp_servers.framework_ordinary.tools.workspace_submit]" in config_text
    assert "[mcp_servers.framework_ordinary.tools.agent_dispatch]" in config_text
    assert 'approval_mode = "approve"' in config_text


def test_blueprint_service_save_open_list_and_validate(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()

    saved = service.save_blueprint(project, _document())

    assert (project / ".multi_agent_workspace" / "blueprints" / "default.json").is_file()
    assert saved["id"] == "default"
    assert service.open_blueprint(project, "default")["graph"]["agent_nodes"]["planner"]["prompt"] == "Plan."

    listed = service.list_blueprints(project)
    assert listed == [
        {
            "id": "default",
            "name": "Default Blueprint",
            "path": str(project / ".multi_agent_workspace" / "blueprints" / "default.json"),
            "updated_at": listed[0]["updated_at"],
        }
    ]

    assert service.validate_blueprint(saved) == {"ok": True, "errors": [], "warnings": []}


def test_blueprint_service_relocates_project_workdir_and_handles_target_conflicts(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    source = tmp_path / "source"
    target = tmp_path / "target"
    conflict_target = tmp_path / "conflict-target"
    source.mkdir()
    target.mkdir()
    conflict_target.mkdir()
    current = _document(source)
    service.save_blueprint(source, current)

    unchanged = service.handle_request(
        {
            "command": "blueprint.relocateProjectWorkdir",
            "args": {
                "projectDir": str(source),
                "blueprintId": "default",
                "document": current,
                "projectWorkdir": str(source),
            },
        }
    )
    assert unchanged["changed"] is False
    assert unchanged["projectDir"] == str(source.resolve())
    assert unchanged["targetProjectDir"] == str(source.resolve())
    assert unchanged["document"]["ui"]["config"]["project_workdir"] == str(source.resolve())

    relocated = service.handle_request(
        {
            "command": "blueprint.relocateProjectWorkdir",
            "args": {
                "projectDir": str(source),
                "blueprintId": "default",
                "document": current,
                "projectWorkdir": str(target),
            },
        }
    )
    assert relocated["changed"] is True
    assert (target / ".multi_agent_workspace" / "blueprints" / "default.json").is_file()
    opened = service.open_blueprint(target, "default")
    assert opened["graph"]["agent_nodes"]["planner"]["prompt"] == "Plan."
    assert opened["ui"]["config"]["python_path"] == sys.executable
    assert opened["ui"]["config"]["project_workdir"] == str(target.resolve())

    existing = _document(conflict_target)
    existing["graph"]["agent_nodes"]["planner"]["prompt"] = "Existing target."
    service.save_blueprint(conflict_target, existing)
    conflict = service.handle_request(
        {
            "command": "blueprint.relocateProjectWorkdir",
            "args": {
                "projectDir": str(source),
                "blueprintId": "default",
                "document": current,
                "projectWorkdir": str(conflict_target),
            },
        }
    )
    assert conflict["changed"] is False
    assert conflict["conflict"] == "target_exists"
    assert service.open_blueprint(conflict_target, "default")["graph"]["agent_nodes"]["planner"]["prompt"] == "Existing target."

    loaded = service.handle_request(
        {
            "command": "blueprint.relocateProjectWorkdir",
            "args": {
                "projectDir": str(source),
                "blueprintId": "default",
                "document": current,
                "projectWorkdir": str(conflict_target),
                "conflictPolicy": "load_existing",
            },
        }
    )
    assert loaded["changed"] is True
    assert loaded["document"]["graph"]["agent_nodes"]["planner"]["prompt"] == "Existing target."

    overwritten = service.handle_request(
        {
            "command": "blueprint.relocateProjectWorkdir",
            "args": {
                "projectDir": str(source),
                "blueprintId": "default",
                "document": current,
                "projectWorkdir": str(conflict_target),
                "conflictPolicy": "overwrite",
            },
        }
    )
    assert overwritten["changed"] is True
    assert service.open_blueprint(conflict_target, "default")["graph"]["agent_nodes"]["planner"]["prompt"] == "Plan."


def test_blueprint_service_rejects_invalid_id_and_invalid_graph(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()

    bad_id = _document()
    bad_id["id"] = "../escape"
    try:
        service.save_blueprint(project, bad_id)
    except Exception as exc:
        assert "blueprint id must match" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("invalid blueprint id should fail")

    bad_graph = _document(project)
    bad_graph["graph"] = {
        "terminal_nodes": {"start": "start", "end": "end"},
        "agent_nodes": {},
        "route_nodes": {},
        "edges": [],
    }
    validation = service.validate_blueprint(bad_graph)
    assert validation["ok"] is False
    assert "requires at least one AgentNode" in validation["errors"][0]


def test_blueprint_service_allows_graph_without_terminal_nodes_but_rejects_empty_start_plan(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()
    document = _document(project)
    document["graph"]["terminal_nodes"] = {}
    document["graph"]["edges"] = []
    try:
        saved = service.save_blueprint(project, document)

        assert service.validate_blueprint(saved) == {"ok": True, "errors": [], "warnings": []}
        context = service.ensure_blueprint_planning_context(project, "default", "desktop-session")
        assert context["sessionId"]

        started = service.start_blueprint_run(project, "default", _plan(), execution_mode="status")
        assert started["ok"] is True

        invalid_plan = _plan()
        invalid_plan["start_nodes"] = []
        invalid_plan["tasks"] = {}
        with pytest.raises(BlueprintServiceError) as exc:
            service.start_blueprint_run(project, "default", invalid_plan, execution_mode="status")
        assert exc.value.code == "START_PLAN_INVALID"
        validation = exc.value.details["validation"]
        assert "start_nodes must not be empty" in validation["errors"]
    finally:
        service.close()


def test_blueprint_http_server_round_trip(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    server = DesktopBlueprintHTTPServer(token="secret")
    server.start()
    try:
        saved = _post(
            server.url,
            "secret",
            "blueprint.save",
            {"projectDir": str(project), "document": _document()},
        )
        assert saved["ok"] is True

        opened = _post(
            server.url,
            "secret",
            "blueprint.open",
            {"projectDir": str(project), "blueprintId": "default"},
        )
        assert opened["document"]["id"] == "default"
    finally:
        server.close()


def test_blueprint_service_starts_tracks_events_and_ends_run(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()
    service.save_blueprint(project, _document(project))

    started = service.handle_request(
        {
            "command": "blueprint.start",
            "args": {
                "projectDir": str(project),
                "blueprintId": "default",
                "plan": _plan(),
            },
        }
    )

    assert started["ok"] is True
    assert started["runId"].startswith("run-")
    assert started["run"]["projectDir"] == str(project.resolve())
    assert started["run"]["blueprintId"] == "default"
    assert started["run"]["executionMode"] == "status"
    assert started["validation"]["ok"] is True
    assert started["queuedMessages"][0]["node_id"] == "planner"
    assert started["status"]["run"]["status"] == "running"
    assert started["status"]["queues"]["by_agent"]["planner"][0]["status"] == "queued"
    run = service._runs[started["runId"]]
    assert isinstance(run.runtime.cluster, DesktopBlueprintNoopBackend)
    assert sorted(run.runtime.cluster.worker_configs) == ["agent-planner"]

    status = service.handle_request(
        {"command": "blueprint.status", "args": {"runId": started["runId"]}}
    )
    assert status["status"]["run"]["status"] == "running"
    assert status["status"]["organization"]["agents"]["planner"]["agent_id"] == "agent-planner"
    assert status["explanation"]["pending"]["queued_messages"] == 1

    runs = service.handle_request(
        {
            "command": "blueprint.listRuns",
            "args": {"projectDir": str(project), "blueprintId": "default"},
        }
    )
    assert runs["ok"] is True
    assert runs["runs"][0]["runId"] == started["runId"]
    assert runs["runs"][0]["status"] == "running"

    events = service.handle_request(
        {
            "command": "blueprint.recentEvents",
            "args": {"runId": started["runId"], "limit": 1},
        }
    )
    assert events["ok"] is True
    assert events["limit"] == 1
    assert len(events["events"]) == 1

    ended = service.handle_request(
        {
            "command": "blueprint.end",
            "args": {
                "runId": started["runId"],
                "action": "cancel",
                "reason": "user cancelled",
            },
        }
    )
    assert ended["end"]["run_status"] == "cancelled"
    assert ended["status"]["run"]["final_status"] == "cancelled"

    repeated = service.handle_request(
        {
            "command": "blueprint.end",
            "args": {
                "runId": started["runId"],
                "action": "cancel",
                "reason": "again",
            },
        }
    )
    assert repeated["alreadyEnded"] is True
    assert repeated["status"]["run"]["status"] == "cancelled"

    terminal_status = service.handle_request(
        {"command": "blueprint.status", "args": {"runId": started["runId"]}}
    )
    assert terminal_status["status"]["run"]["status"] == "cancelled"
    assert terminal_status["explanation"]["pending"]["queued_messages"] == 0


def test_blueprint_service_start_rejects_missing_common_config(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()
    service.save_blueprint(project, _document())

    try:
        service.handle_request(
            {
                "command": "blueprint.start",
                "args": {
                    "projectDir": str(project),
                    "blueprintId": "default",
                    "plan": _plan(),
                },
            }
        )
    except BlueprintServiceError as exc:
        assert exc.code == "BLUEPRINT_CONFIG_REQUIRED"
        assert exc.details["issues"] == [
            {"field": "python_path", "reason": "missing"},
            {"field": "project_workdir", "reason": "missing"},
        ]
    else:  # pragma: no cover
        raise AssertionError("missing blueprint common config should fail start")


def test_blueprint_service_agent_info_projects_message_audit_for_node(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()
    service.save_blueprint(project, _document(project))
    started = service.handle_request(
        {
            "command": "blueprint.start",
            "args": {"projectDir": str(project), "blueprintId": "default", "plan": _plan()},
        }
    )
    run = service._runs[started["runId"]]
    run.runtime._record_message_io(
        record_type="agent.outgoing.staged",
        sender={"type": "agent", "agent_id": "agent-planner", "node_id": "planner"},
        receiver={"type": "framework"},
        payload={"prompt": "handoff to reviewer"},
        batch_id="out-1",
        status="staged",
        metadata={"target_node_id": "reviewer", "target_agent_id": "agent-reviewer"},
    )

    info = service.handle_request(
        {"command": "blueprint.agentInfo", "args": {"runId": started["runId"], "nodeId": "planner"}}
    )

    assert info["messageJournal"][-1] == {
        "id": info["messageJournal"][-1]["id"],
        "recordType": "agent.outgoing.staged",
        "time": info["messageJournal"][-1]["time"],
        "from": "planner",
        "to": "framework",
        "status": "staged",
        "summary": "handoff to reviewer",
        "batchId": "out-1",
        "targetNodeId": "reviewer",
        "targetAgentId": "agent-reviewer",
    }
    assert info["frameworkApiCalls"][-1]["api"] == "agent.dispatch"
    assert info["frameworkApiCalls"][-1]["summary"] == "handoff to reviewer"
    assert info["frameworkApiCalls"][-1]["batchId"] == "out-1"


def test_blueprint_service_start_rejects_invalid_graph_and_plan(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()

    bad_graph = _document(project)
    bad_graph["graph"] = {
        "terminal_nodes": {"start": "start", "end": "end"},
        "agent_nodes": {},
        "route_nodes": {},
        "edges": [],
    }
    service.save_blueprint(project, bad_graph)
    try:
        service.handle_request(
            {
                "command": "blueprint.start",
                "args": {
                    "projectDir": str(project),
                    "blueprintId": "default",
                    "plan": _plan(),
                },
            }
        )
    except BlueprintServiceError as exc:
        assert exc.code == "INVALID_BLUEPRINT_GRAPH"
    else:  # pragma: no cover
        raise AssertionError("invalid graph should fail start")

    service.save_blueprint(project, _document(project))
    try:
        service.handle_request(
            {
                "command": "blueprint.start",
                "args": {
                    "projectDir": str(project),
                    "blueprintId": "default",
                },
            }
        )
    except BlueprintServiceError as exc:
        assert exc.code == "BAD_START_PLAN"
    else:  # pragma: no cover
        raise AssertionError("missing start plan should fail")

    invalid_plan = _plan()
    invalid_plan["tasks"] = {}
    try:
        service.handle_request(
            {
                "command": "blueprint.start",
                "args": {
                    "projectDir": str(project),
                    "blueprintId": "default",
                    "plan": invalid_plan,
                },
            }
        )
    except BlueprintServiceError as exc:
        assert exc.code == "START_PLAN_INVALID"
        assert "validation" in exc.details
    else:  # pragma: no cover
        raise AssertionError("invalid start plan should fail")


def test_blueprint_service_rejects_unknown_run_and_bad_end_action(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    try:
        service.handle_request({"command": "blueprint.status", "args": {"runId": "run-missing"}})
    except BlueprintServiceError as exc:
        assert exc.code == "RUN_NOT_FOUND"
        assert exc.status == 404
    else:  # pragma: no cover
        raise AssertionError("unknown run should fail")

    project = tmp_path / "project"
    project.mkdir()
    service.save_blueprint(project, _document(project))
    started = service.handle_request(
        {
            "command": "blueprint.start",
            "args": {"projectDir": str(project), "blueprintId": "default", "plan": _plan()},
        }
    )
    try:
        service.handle_request(
            {
                "command": "blueprint.end",
                "args": {"runId": started["runId"], "action": "archive_only"},
            }
        )
    except BlueprintServiceError as exc:
        assert exc.code == "UNSUPPORTED_RUN_ACTION"
    else:  # pragma: no cover
        raise AssertionError("unsupported end action should fail")

    try:
        service.handle_request(
            {
                "command": "blueprint.start",
                "args": {
                    "projectDir": str(project),
                    "blueprintId": "default",
                    "plan": _plan(),
                    "executionMode": "preview",
                },
            }
        )
    except BlueprintServiceError as exc:
        assert exc.code == "UNSUPPORTED_EXECUTION_MODE"
    else:  # pragma: no cover
        raise AssertionError("unsupported execution mode should fail")


def test_run_mcp_token_store_enforces_server_kind_session_and_closed_state() -> None:
    store = RunMCPTokenStore("run-1", now=lambda: 100.0)
    ordinary = store.create_ordinary_scope(
        agent_node_id="planner",
        agent_id="agent-planner",
        workspace_rpc_token="workspace-token",
        checkout_dir=Path("checkout"),
        private_dir=Path("private"),
        allowed_file_roots=[Path("checkout")],
    )
    control = store.create_control_scope(agent_node_id="top-agent-gulicode", agent_id="gulicode")

    assert store.authenticate(server_kind="ordinary", token=ordinary.token, session_id="s1") is ordinary
    with pytest.raises(PermissionError):
        store.authenticate(server_kind="control", token=ordinary.token, session_id="s2")
    with pytest.raises(PermissionError):
        store.authenticate(server_kind="ordinary", token=control.token, session_id="s1")

    other = store.create_ordinary_scope(
        agent_node_id="reviewer",
        agent_id="agent-reviewer",
        workspace_rpc_token="workspace-token-2",
        checkout_dir=Path("checkout-2"),
        private_dir=Path("private-2"),
        allowed_file_roots=[Path("checkout-2")],
    )
    with pytest.raises(PermissionError):
        store.authenticate(server_kind="ordinary", token=other.token, session_id="s1")

    store.close()
    with pytest.raises(PermissionError):
        store.authenticate(server_kind="ordinary", token=ordinary.token, session_id=None)


def test_run_mcp_agent_dispatch_uses_active_message_scope() -> None:
    class FakeControl:
        def __init__(self) -> None:
            self.calls = []

        async def dispatch_agent_message(self, source_node_id, target_node_id, body, *, batch_id=None):
            self.calls.append(
                {
                    "source": source_node_id,
                    "target": target_node_id,
                    "body": body,
                    "batch_id": batch_id,
                }
            )
            return {"ok": True, "dispatch": self.calls[-1]}

    control = FakeControl()
    clock = {"now": 100.0}
    handle = RunMCPRuntimeHandle(
        run_id="run-1",
        runtime=object(),
        control=control,
        graph=object(),
        workspace_rpc_server=object(),
        manager=object(),
        workspace_run=object(),
        runtime_loop=None,
        now=lambda: clock["now"],
    )
    scope = handle.token_store.create_ordinary_scope(
        agent_node_id="planner",
        agent_id="agent-planner",
        workspace_rpc_token="workspace-token",
        checkout_dir=Path("checkout"),
        private_dir=Path("private"),
        allowed_file_roots=[Path("checkout")],
    )

    async def scenario() -> None:
        with pytest.raises(PermissionError) as no_context_error:
            await handle._agent_dispatch(
                scope,
                target_node_id="reviewer",
                body={"prompt": "review"},
                batch_id=None,
                source_node_id=None,
            )
        assert "agent_dispatch requires an active message context" in str(no_context_error.value)
        assert "workspace_publish" in str(no_context_error.value)
        handle.token_store.update_message_context(
            agent_node_id="planner",
            agent_id="agent-planner",
            current_message_id="msg-leaf",
            outgoing_batch_id=None,
            required_outgoing_targets=[],
            timeout_sec=60,
        )
        with pytest.raises(PermissionError) as no_batch_error:
            await handle._agent_dispatch(
                scope,
                target_node_id="reviewer",
                body={"prompt": "review"},
                batch_id=None,
                source_node_id=None,
            )
        no_batch_message = str(no_batch_error.value)
        assert "agent_dispatch has no current outgoing_batch_id" in no_batch_message
        assert "leaf/no-dispatch path" in no_batch_message
        assert "join_contribute" in no_batch_message
        handle.token_store.update_message_context(
            agent_node_id="planner",
            agent_id="agent-planner",
            current_message_id="msg-1",
            outgoing_batch_id="batch-1",
            required_outgoing_targets=["reviewer"],
            timeout_sec=60,
        )
        with pytest.raises(PermissionError) as wrong_target_error:
            await handle._agent_dispatch(
                scope,
                target_node_id="coder",
                body={"prompt": "code"},
                batch_id=None,
                source_node_id=None,
            )
        wrong_target_message = str(wrong_target_error.value)
        assert "target 'coder' is not in the current required_outgoing_targets" in wrong_target_message
        assert "current_message_id='msg-1'" in wrong_target_message
        assert "workspace_publish" in wrong_target_message
        with pytest.raises(PermissionError):
            await handle._agent_dispatch(
                scope,
                target_node_id="reviewer",
                body={"prompt": "review"},
                batch_id=None,
                source_node_id="other-agent",
            )
        clock["now"] = 200.0
        with pytest.raises(PermissionError):
            await handle._agent_dispatch(
                scope,
                target_node_id="reviewer",
                body={"prompt": "review"},
                batch_id=None,
                source_node_id=None,
            )
        clock["now"] = 100.0
        result = await handle._agent_dispatch(
            scope,
            target_node_id="reviewer",
            body={"prompt": "review"},
            batch_id=None,
            source_node_id=None,
        )
        assert result["dispatch"]["batch_id"] == "batch-1"
        assert control.calls[-1]["source"] == "planner"

    asyncio.run(scenario())


def test_run_mcp_ordinary_agent_context_and_join_contribute_are_scope_bound() -> None:
    class FakeControl:
        def __init__(self) -> None:
            self.requests = []

        def handle_request(self, payload):
            self.requests.append(payload)
            if (
                payload.get("command") == "join.contribute"
                and payload.get("args", {}).get("join_id") == "out-batch"
            ):
                raise KeyError("unknown join barrier: out-batch")
            return {"ok": True, "payload": payload}

    control = FakeControl()
    handle = RunMCPRuntimeHandle(
        run_id="run-1",
        runtime=object(),
        control=control,
        graph=object(),
        workspace_rpc_server=object(),
        manager=object(),
        workspace_run=object(),
        runtime_loop=None,
        now=lambda: 100.0,
    )
    scope = handle.token_store.create_ordinary_scope(
        agent_node_id="planner",
        agent_id="agent-planner",
        workspace_rpc_token="workspace-token",
        checkout_dir=Path("checkout"),
        private_dir=Path("private"),
        allowed_file_roots=[Path("checkout")],
    )
    handle.token_store.update_message_context(
        agent_node_id="planner",
        agent_id="agent-planner",
        current_message_id="msg-1",
        outgoing_batch_id="batch-1",
        required_outgoing_targets=["reviewer"],
        timeout_sec=60,
    )

    context = asyncio.run(handle._ordinary_agent_context(scope, batch_id=None))
    assert context["ok"] is True
    assert control.requests[-1]["command"] == "agent.context"
    assert control.requests[-1]["args"] == {"source_node_id": "planner", "batch_id": "batch-1"}

    task_status = asyncio.run(
        handle._ordinary_agent_task_status(
            scope,
            status="completed",
            summary="planner task done",
            message_id=None,
            batch_id=None,
            reports=[{"path": "reports/planner.md"}],
            artifacts=None,
            changesets=None,
            next_actions=["review"],
            metadata={"via": "mcp"},
        )
    )
    assert task_status["ok"] is True
    assert control.requests[-1]["command"] == "agent.task_status"
    assert control.requests[-1]["args"]["node_id"] == "planner"
    assert control.requests[-1]["args"]["agent_id"] == "agent-planner"
    assert control.requests[-1]["args"]["message_id"] == "msg-1"
    assert control.requests[-1]["args"]["batch_id"] == "batch-1"

    with pytest.raises(PermissionError):
        asyncio.run(
            handle._ordinary_agent_task_status(
                scope,
                status="completed",
                summary="wrong message",
                message_id="other-message",
                batch_id=None,
                reports=None,
                artifacts=None,
                changesets=None,
                next_actions=None,
                metadata=None,
            )
        )

    with pytest.raises(PermissionError) as wrong_batch_error:
        asyncio.run(handle._ordinary_agent_context(scope, batch_id="other-batch"))
    wrong_batch_message = str(wrong_batch_error.value)
    assert "ordinary agent_context cannot read another message batch" in wrong_batch_message
    assert "requested_batch_id='other-batch'" in wrong_batch_message
    assert "current_outgoing_batch_id='batch-1'" in wrong_batch_message
    assert "agent_context({})" in wrong_batch_message
    assert "upstream batch_id values are source/audit labels" in wrong_batch_message
    with pytest.raises(PermissionError):
        asyncio.run(
            handle._ordinary_join_contribute(
                scope,
                join_id="join-1",
                status="completed",
                result={"ok": True},
                source_node_id="other-node",
                source_agent_id=None,
                accepted_changesets=None,
                conflicts=None,
                artifacts=None,
                reports=None,
                test_results=None,
                metadata=None,
            )
        )
    with pytest.raises(PermissionError) as unknown_join_error:
        asyncio.run(
            handle._ordinary_join_contribute(
                scope,
                join_id="out-batch",
                status="completed",
                result={"ok": True},
                source_node_id=None,
                source_agent_id=None,
                accepted_changesets=None,
                conflicts=None,
                artifacts=None,
                reports=None,
                test_results=None,
                metadata=None,
            )
        )
    unknown_join_message = str(unknown_join_error.value)
    assert "join_contribute cannot find a join barrier" in unknown_join_message
    assert "out-*` are not join ids" in unknown_join_message
    assert "current_message_id='msg-1'" in unknown_join_message
    assert "workspace_publish" in unknown_join_message

    joined = asyncio.run(
        handle._ordinary_join_contribute(
            scope,
            join_id="join-1",
            status="completed",
            result={"ok": True},
            source_node_id=None,
            source_agent_id=None,
            accepted_changesets=[{"id": "cs1"}],
            conflicts=None,
            artifacts=None,
            reports=None,
            test_results=None,
            metadata={"via": "mcp"},
        )
    )
    assert joined["ok"] is True
    assert control.requests[-1]["command"] == "join.contribute"
    assert control.requests[-1]["args"]["source_node_id"] == "planner"
    assert control.requests[-1]["args"]["source_agent_id"] == "agent-planner"


def test_run_mcp_publish_file_path_validation_blocks_escape(tmp_path: Path) -> None:
    private = tmp_path / "agents" / "agent" / "private"
    checkout = private / "checkout"
    scratch = private / "scratch"
    artifact_tmp = private / "generated_artifacts"
    checkout.mkdir(parents=True)
    scratch.mkdir()
    artifact_tmp.mkdir()
    allowed = checkout / "report.txt"
    allowed.write_text("ok", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("no", encoding="utf-8")
    scope = MCPTokenScope(
        token="token",
        run_id="run-1",
        server_kind="ordinary",
        agent_node_id="planner",
        agent_id="agent-planner",
        workspace_rpc_token="workspace-token",
        allowed_tools=[],
        checkout_dir=checkout,
        private_dir=private,
        allowed_file_roots=[checkout, scratch, artifact_tmp],
        expires_at=999.0,
    )

    assert resolve_allowed_publish_file(scope, "report.txt") == allowed.resolve()
    assert resolve_allowed_publish_file(scope, str(allowed)) == allowed.resolve()
    with pytest.raises(PermissionError):
        resolve_allowed_publish_file(scope, str(outside))
    with pytest.raises(PermissionError):
        resolve_allowed_publish_file(scope, "..\\..\\..\\outside.txt")
    with pytest.raises(PermissionError):
        resolve_allowed_publish_file(scope, "C:outside.txt")

    link = checkout / "escape-link.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        return
    with pytest.raises(PermissionError):
        resolve_allowed_publish_file(scope, str(link))


def test_run_mcp_provisions_control_context_without_workspace_read_tools(tmp_path: Path) -> None:
    class FakeWorkspaceRPCServer:
        def __init__(self) -> None:
            self.tokens = []

        def token_for(self, agent_id):
            self.tokens.append(agent_id)
            return f"token-for-{agent_id}"

    class FakeTopAgent:
        allowed_run_permissions = ["ask", "start", "status", "end", "utterances"]

    class FakeControl:
        top_agent = FakeTopAgent()

    class TopNode:
        node_id = "top-agent-gulicode"
        runtime_agent_id = "gulicode"

    rpc = FakeWorkspaceRPCServer()
    handle = RunMCPRuntimeHandle(
        run_id="run-1",
        runtime=object(),
        control=FakeControl(),
        graph=object(),
        workspace_rpc_server=rpc,
        manager=object(),
        workspace_run=object(),
        runtime_loop=None,
        top_agent_node_id="top-agent-gulicode",
        top_agent_id="gulicode",
    )

    context = handle.provision_context_for_node(
        node=TopNode(),
        private_dir=tmp_path / "top-private",
        checkout_dir=tmp_path / "top-private" / "checkout",
        codex_home=tmp_path / "top-private" / "codex_home",
    )

    assert context["server_kind"] == "control"
    assert context["server_name"] == "framework_control"
    assert context["bearer_token_env_var"] == "MULTI_AGENT_MCP_CONTROL_TOKEN"
    assert "organization_read" in context["tools"]
    assert "runtime_message_batch" in context["tools"]
    assert "workspace_read" not in context["tools"]
    assert "workspace_list" not in context["tools"]
    assert "workspace_list_archives" not in context["tools"]
    assert "workspace_extract_archive" not in context["tools"]
    assert "workspace_submit" not in context["tools"]
    assert "workspace_publish" not in context["tools"]
    assert "runtime_execute_fixture" not in context["tools"]
    assert rpc.tokens == ["gulicode"]
    assert handle.token_store.summary()["controlScopes"][0]["control_permissions"] == [
        "ask",
        "start",
        "status",
        "end",
        "utterances",
    ]


def test_run_mcp_tool_audit_records_safe_manifest_entries(tmp_path: Path) -> None:
    class FakeManager:
        def __init__(self) -> None:
            self.records = []

        def _record_shared_manifest(self, run, event_type, payload):
            self.records.append((run, event_type, payload))

    class FakeWorkspaceRPCServer:
        def handle_request(self, payload):
            return {"ok": True, "request": payload}

    manager = FakeManager()
    workspace_run = object()
    handle = RunMCPRuntimeHandle(
        run_id="run-1",
        runtime=object(),
        control=object(),
        graph=object(),
        workspace_rpc_server=FakeWorkspaceRPCServer(),
        manager=manager,
        workspace_run=workspace_run,
        runtime_loop=None,
    )
    scope = handle.token_store.create_ordinary_scope(
        agent_node_id="planner",
        agent_id="agent-planner",
        workspace_rpc_token="workspace-secret-token",
        checkout_dir=tmp_path / "checkout",
        private_dir=tmp_path / "private",
        allowed_file_roots=[tmp_path / "checkout"],
    )

    absolute_private = tmp_path / "checkout" / "secret.txt"
    result = handle._workspace_request(
        scope,
        "publish",
        {
            "area": "reports",
            "path": "mcp-audit.md",
            "text": "private report text",
            "file_path": str(absolute_private),
            "rpc_token": "must-not-leak",
        },
    )

    assert result["ok"] is True
    assert len(manager.records) == 1
    run, event_type, payload = manager.records[0]
    assert run is workspace_run
    assert event_type == MCP_TOOL_AUDIT_EVENT
    assert payload["workspace_event"] == "FrameworkMCPToolCalled"
    assert payload["run_id"] == "run-1"
    assert payload["server_kind"] == "ordinary"
    assert payload["agent_id"] == "agent-planner"
    assert payload["node_id"] == "planner"
    assert payload["tool_name"] == "workspace_publish"
    assert payload["args"]["area"] == "reports"
    assert payload["args"]["path"] == "mcp-audit.md"
    assert payload["args"]["text"] == {"type": "text", "chars": len("private report text")}
    assert payload["args"]["file_path"] == {
        "type": "path",
        "absolute": True,
        "name": "secret.txt",
    }
    assert payload["args"]["rpc_token"] == "<redacted>"
    encoded = json.dumps(payload, ensure_ascii=False)
    assert "workspace-secret-token" not in encoded
    assert "must-not-leak" not in encoded
    assert str(tmp_path) not in encoded


def test_run_mcp_streamable_http_tools_are_split_by_token(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    import httpx

    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    handle = RunMCPRuntimeHandle(
        run_id="run-1",
        runtime=object(),
        control=object(),
        graph=object(),
        workspace_rpc_server=object(),
        manager=object(),
        workspace_run=object(),
        runtime_loop=None,
    )
    ordinary = handle.token_store.create_ordinary_scope(
        agent_node_id="planner",
        agent_id="agent-planner",
        workspace_rpc_token="workspace-token",
        checkout_dir=tmp_path / "checkout",
        private_dir=tmp_path / "private",
        allowed_file_roots=[tmp_path / "checkout"],
    )
    control = handle.token_store.create_control_scope(
        agent_node_id="top-agent-gulicode",
        agent_id="gulicode",
    )
    handle.start()

    async def list_tool_names(url: str, token: str) -> list[str]:
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as client:
            async with streamable_http_client(
                url,
                http_client=client,
            ) as (read_stream, write_stream, _session_id):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return sorted(tool.name for tool in result.tools)

    try:
        ordinary_tools = asyncio.run(list_tool_names(handle.ordinary_url, ordinary.token))
        control_tools = asyncio.run(list_tool_names(handle.control_url, control.token))
    finally:
        handle.close()

    assert "agent_dispatch" in ordinary_tools
    assert "agent_context" in ordinary_tools
    assert "agent_task_status" in ordinary_tools
    assert "join_contribute" in ordinary_tools
    assert "workspace_status" in ordinary_tools
    assert "workspace_read" not in ordinary_tools
    assert "workspace_list" not in ordinary_tools
    assert "workspace_list_archives" not in ordinary_tools
    assert "workspace_extract_archive" not in ordinary_tools
    assert "runtime_status" not in ordinary_tools
    assert "organization_read" not in ordinary_tools
    assert "runtime_status" in control_tools
    assert "organization_read" in control_tools
    assert "agent_dispatch" in control_tools
    assert "join_create" in control_tools
    assert "workspace_read" not in control_tools
    assert "workspace_list" not in control_tools
    assert "workspace_list_archives" not in control_tools
    assert "workspace_extract_archive" not in control_tools
    assert "workspace_checkout" not in control_tools
    assert "workspace_submit" not in control_tools
    assert "runtime_execute_fixture" not in control_tools


def test_run_mcp_control_permission_gates(tmp_path: Path) -> None:
    class FakeWorkspaceRPCServer:
        def __init__(self) -> None:
            self.requests = []

        def handle_request(self, payload):
            self.requests.append(payload)
            return {"ok": True, "payload": payload}

    class FakeControl:
        def __init__(self) -> None:
            self.requests = []

        def handle_request(self, payload):
            self.requests.append(payload)
            return {"ok": True, "payload": payload}

    workspace_rpc = FakeWorkspaceRPCServer()
    control = FakeControl()
    handle = RunMCPRuntimeHandle(
        run_id="run-1",
        runtime=object(),
        control=control,
        graph=object(),
        workspace_rpc_server=workspace_rpc,
        manager=object(),
        workspace_run=object(),
        runtime_loop=None,
    )
    scope = handle.token_store.create_control_scope(
        agent_node_id="top-agent-gulicode",
        agent_id="gulicode",
        workspace_rpc_token="workspace-token",
        permissions=["status"],
    )

    with pytest.raises(PermissionError):
        asyncio.run(
            handle._control_request(
                scope,
                tool_name="runtime_message_batch",
                command="message.create_batch",
                args={"source_node_id": "planner", "required_target_node_ids": ["reviewer"]},
                permission="start",
            )
        )

    organization = asyncio.run(
        handle._control_request(
            scope,
            tool_name="organization_read",
            command="organization.read",
            args={"agent_id": "planner"},
            permission="status",
        )
    )
    assert organization["ok"] is True
    assert control.requests[-1]["command"] == "organization.read"


def test_run_mcp_control_requests_cover_control_plane_commands(tmp_path: Path) -> None:
    class FakeControl:
        def __init__(self) -> None:
            self.calls = []

        def handle_request(self, payload):
            self.calls.append(("handle_request", payload))
            return {"ok": True, "command": payload["command"], "args": payload["args"]}

        async def start_run(self, plan, *, manifest_path=None, prestart_all_agents=False):
            self.calls.append(
                (
                    "start_run",
                    {
                        "plan": plan.to_dict(),
                        "manifest_path": manifest_path,
                        "prestart_all_agents": prestart_all_agents,
                    },
                )
            )
            return {"ok": True, "started": True}

        async def execute_fixture_to_archive(
            self,
            plan,
            *,
            runtime_scenarios=None,
            manifest_path=None,
            archive=True,
        ):
            self.calls.append(
                (
                    "execute_fixture_to_archive",
                    {
                        "plan": plan.to_dict(),
                        "runtime_scenarios": runtime_scenarios,
                        "manifest_path": manifest_path,
                        "archive": archive,
                    },
                )
            )
            return {"ok": True, "fixture": True}

        async def _create_message_batch(self, source_node_id, required_target_node_ids, *, batch_id=None):
            self.calls.append(
                (
                    "_create_message_batch",
                    {
                        "source_node_id": source_node_id,
                        "required_target_node_ids": required_target_node_ids,
                        "batch_id": batch_id,
                    },
                )
            )
            return {"ok": True, "batch_id": batch_id or "generated"}

        async def dispatch_agent_message(self, source_node_id, target_node_id, body, *, batch_id=None):
            self.calls.append(
                (
                    "dispatch_agent_message",
                    {
                        "source_node_id": source_node_id,
                        "target_node_id": target_node_id,
                        "body": body,
                        "batch_id": batch_id,
                    },
                )
            )
            return {"ok": True, "dispatched": True}

    class FakeRun:
        shared_dir = tmp_path / "shared"

    control = FakeControl()
    handle = RunMCPRuntimeHandle(
        run_id="run-1",
        runtime=object(),
        control=control,
        graph=object(),
        workspace_rpc_server=object(),
        manager=object(),
        workspace_run=FakeRun(),
        runtime_loop=None,
    )
    scope = handle.token_store.create_control_scope(
        agent_node_id="top-agent-gulicode",
        agent_id="gulicode",
        permissions=["ask", "start", "status", "end", "utterances", "fixture"],
    )
    plan = {
        "user_goal": "goal",
        "agent_descriptions": {"planner": "plans"},
        "start_nodes": ["planner"],
        "tasks": {
            "planner": {
                "goal": "do",
                "expected_output": "out",
                "acceptance": "ok",
            }
        },
        "run_policy": {},
    }

    async def scenario() -> None:
        await handle._control_request(
            scope,
            tool_name="runtime_start",
            command="run.start",
            args={"plan": plan, "manifest_path": "manifests/start.json"},
            permission="start",
        )
        await handle._control_request(
            scope,
            tool_name="runtime_execute_fixture",
            command="run.execute_fixture",
            args={"plan": plan, "runtime_scenarios": {"joins": []}},
            permission="fixture",
        )
        await handle._control_request(
            scope,
            tool_name="runtime_message_batch",
            command="message.create_batch",
            args={"source_node_id": "planner", "required_target_node_ids": ["reviewer"]},
            permission="start",
        )
        await handle._control_request(
            scope,
            tool_name="runtime_message_stage",
            command="message.stage",
            args={"batch_id": "batch-1", "target_node_id": "reviewer", "body": {"prompt": "review"}},
            permission="start",
        )
        await handle._control_request(
            scope,
            tool_name="agent_dispatch",
            command="agent.dispatch",
            args={
                "source_node_id": "planner",
                "target_node_id": "reviewer",
                "body": {"prompt": "review"},
                "batch_id": "batch-1",
            },
            permission="start",
        )
        await handle._control_request(
            scope,
            tool_name="join_create",
            command="join.create",
            args={"required_source_node_ids": ["planner"], "target_node_id": "reviewer"},
            permission="start",
        )
        await handle._control_request(
            scope,
            tool_name="join_contribute",
            command="join.contribute",
            args={"join_id": "join-1", "source_node_id": "planner"},
            permission="start",
        )

    asyncio.run(scenario())

    call_names = [name for name, _payload in control.calls]
    assert "start_run" in call_names
    assert "execute_fixture_to_archive" in call_names
    assert "_create_message_batch" in call_names
    assert "dispatch_agent_message" in call_names
    handled = [
        payload["command"]
        for name, payload in control.calls
        if name == "handle_request"
    ]
    assert "message.stage" in handled
    assert "join.create" in handled
    assert "join.contribute" in handled
    start_payload = next(dict(payload) for name, payload in control.calls if name == "start_run")
    assert Path(start_payload["manifest_path"]).resolve().is_relative_to(FakeRun.shared_dir.resolve())


def test_run_mcp_runtime_end_closes_tokens_and_records_control_audit() -> None:
    pytest.importorskip("mcp")
    import httpx

    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    class FakeEndResult:
        def to_dict(self):
            return {"ok": True, "action": "complete", "run_status": "completed"}

    class FakeRuntime:
        def end_run(self, action, *, reason="", archive=False):
            return FakeEndResult()

    class FakeManager:
        def __init__(self) -> None:
            self.records = []

        def _record_shared_manifest(self, run, event_type, payload):
            self.records.append((event_type, payload))

    manager = FakeManager()
    workspace_run = object()
    handle = RunMCPRuntimeHandle(
        run_id="run-1",
        runtime=FakeRuntime(),
        control=object(),
        graph=object(),
        workspace_rpc_server=object(),
        manager=manager,
        workspace_run=workspace_run,
        runtime_loop=None,
    )
    scope = handle.token_store.create_control_scope(
        agent_node_id="top-agent-gulicode",
        agent_id="gulicode",
    )

    async def scenario() -> dict:
        headers = {"Authorization": f"Bearer {scope.token}"}
        async with httpx.AsyncClient(headers=headers, timeout=20.0) as client:
            async with streamable_http_client(
                handle.control_url,
                http_client=client,
            ) as (read_stream, write_stream, _session_id):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "runtime_end",
                        {"action": "complete", "reason": "mcp test"},
                    )
                    assert not result.isError, result
                    return dict(result.structuredContent or {})

    try:
        handle.start()
        try:
            result = asyncio.run(scenario())
        except BaseExceptionGroup as exc:
            assert "401 Unauthorized" in repr(exc)
        else:
            assert result["ok"] is True
        assert handle.token_store.closed is True
        with pytest.raises(PermissionError):
            handle.token_store.authenticate(
                server_kind="control",
                token=scope.token,
                session_id=None,
            )
    finally:
        handle.close()

    assert manager.records[-1][0] == MCP_TOOL_AUDIT_EVENT
    assert manager.records[-1][1]["tool_name"] == "runtime_end"


def test_run_mcp_runtime_end_prefers_desktop_close_callback() -> None:
    class FakeManager:
        def __init__(self) -> None:
            self.records = []

        def _record_shared_manifest(self, run, event_type, payload):
            self.records.append((event_type, payload))

    calls = []

    def close_callback(*, action: str, reason: str, archive: bool):
        calls.append({"action": action, "reason": reason, "archive": archive})
        return {"ok": True, "action": action, "run_status": "completed", "closed": True}

    manager = FakeManager()
    handle = RunMCPRuntimeHandle(
        run_id="run-1",
        runtime=object(),
        control=object(),
        graph=object(),
        workspace_rpc_server=object(),
        manager=manager,
        workspace_run=object(),
        runtime_loop=None,
        close_run_callback=close_callback,
    )
    scope = handle.token_store.create_control_scope(
        agent_node_id="top-agent-gulicode",
        agent_id="gulicode",
    )

    result = asyncio.run(
        handle._runtime_end(
            scope,
            tool_name="runtime_end",
            action="complete",
            reason="mcp callback",
            archive=True,
        )
    )

    assert result["closed"] is True
    assert calls == [{"action": "complete", "reason": "mcp callback", "archive": True}]
    assert handle.token_store.closed is True
    assert manager.records[-1][0] == MCP_TOOL_AUDIT_EVENT
    assert manager.records[-1][1]["tool_name"] == "runtime_end"


def test_blueprint_service_live_mode_starts_tick_and_streams_agent_events(tmp_path: Path, monkeypatch) -> None:
    class FakeLiveBackend:
        instances = []
        create_calls = []

        def __init__(self, workers) -> None:
            self.workers = workers
            self.worker_configs = {}
            self.stopped = False
            FakeLiveBackend.instances.append(self)

        @classmethod
        async def create(cls, workers, *, port=9140, verbose=False, allow_empty=False):
            cls.create_calls.append({"workers": list(workers), "allow_empty": allow_empty})
            if not workers and not allow_empty:
                raise ValueError("workers list must be non-empty")
            return cls(workers)

        async def ensure_worker(self, worker) -> None:
            self.worker_configs[str(worker.agent_id)] = worker

        async def run_single(self, worker_id, body, *, timeout_sec=600.0, _skip_skill_inject=False, meta=None, stream_callback=None):
            if stream_callback is not None:
                result = stream_callback(
                    {
                        **dict((meta or {}).get("framework_stream") or {}),
                        "kind": "part.delta",
                        "part_id": "fake",
                        "part_type": "text",
                        "field": "text",
                        "delta": "streamed",
                        "text": "streamed",
                    }
                )
                if inspect.isawaitable(result):
                    await result
            return {"type": "message", "body": {"ok": True, "text": "done"}}

        async def stop(self) -> None:
            self.stopped = True

    monkeypatch.setattr("multi_agent_tcp.desktop_blueprint_service.CLIWorkerBackend", FakeLiveBackend)
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()
    service.save_blueprint(project, _document(project))

    started = service.handle_request(
        {
            "command": "blueprint.start",
            "args": {
                "projectDir": str(project),
                "blueprintId": "default",
                "plan": _plan(),
                "executionMode": "live",
            },
        }
    )
    assert started["run"]["executionMode"] == "live"
    assert FakeLiveBackend.create_calls[-1]["workers"] == []
    assert FakeLiveBackend.create_calls[-1]["allow_empty"] is True
    assert set(FakeLiveBackend.instances[-1].worker_configs) == {"agent-planner"}
    run = service._runs[started["runId"]]
    assert run.runtime.message_journal_path == (
        run.runtime.private_context_run.shared_dir / "logs" / "message_journal.jsonl"
    )
    assert run.runtime.archive_run is run.runtime.private_context_run
    run.runtime.private_context_manager.write_shared_text(
        run.runtime.private_context_run,
        "reports/live-status.md",
        "live status ok",
        owner="agent-planner",
    )
    status = service.handle_request({"command": "blueprint.status", "args": {"runId": started["runId"]}})
    reports = status["status"]["workspace"]["reports"]
    assert reports[0]["path"] == "live-status.md"
    assert reports[0]["absolute_path"] == str(
        (run.runtime.private_context_run.shared_reports_dir / "live-status.md").resolve()
    )
    service._async_loop.run(asyncio.sleep(0.2))

    info = service.handle_request(
        {"command": "blueprint.agentInfo", "args": {"runId": started["runId"], "nodeId": "planner"}}
    )
    assert info["runtime"]["state"] in {"idle", "queued", "waiting_for_reply", "processing_reply"}
    assert any(event.get("kind") == "part.delta" for event in info["streamEvents"])

    queued = service.handle_request(
        {
            "command": "blueprint.queueAgentMessage",
            "args": {"runId": started["runId"], "nodeId": "planner", "text": "urgent", "mode": "top"},
        }
    )
    assert queued["result"]["queue_mode"] == "top"

    ended = service.handle_request(
        {"command": "blueprint.end", "args": {"runId": started["runId"], "action": "cancel"}}
    )
    assert ended["status"]["run"]["final_status"] == "cancelled"
    assert service._runs[started["runId"]].mcp.token_store.closed is True
    assert FakeLiveBackend.instances[-1].stopped is True
    service.close()


def test_blueprint_service_desktop_planning_context_plan_flow(tmp_path: Path, monkeypatch) -> None:
    class FakeLiveBackend:
        instances = []
        create_calls = []

        def __init__(self, workers) -> None:
            self.workers = workers
            self.worker_configs = {}
            self.stopped = False
            FakeLiveBackend.instances.append(self)

        @classmethod
        async def create(cls, workers, *, port=9140, verbose=False, allow_empty=False):
            cls.create_calls.append({"workers": list(workers), "allow_empty": allow_empty})
            return cls(workers)

        async def ensure_worker(self, worker) -> None:
            self.worker_configs[str(worker.agent_id)] = worker

        async def run_single(self, worker_id, body, *, timeout_sec=600.0, _skip_skill_inject=False, meta=None, stream_callback=None):
            return {
                "type": "message",
                "body": {"codex": {"final_text": f"reply from {worker_id}"}},
            }

        async def stop(self) -> None:
            self.stopped = True

    monkeypatch.setattr("multi_agent_tcp.desktop_blueprint_service.CLIWorkerBackend", FakeLiveBackend)
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()
    service.save_blueprint(project, _document(project))
    stale_run_id = service._planning_session_id(project, "default", "desktop-session-1")
    DulwichWorkspaceManager.open_or_init(project).create_run(
        run_id=stale_run_id,
        code_mode="project_reference",
    )

    ensured = service.handle_request(
        {
            "command": "blueprint.planning.ensureContext",
            "args": {
                "projectDir": str(project),
                "blueprintId": "default",
                "desktopSessionId": "desktop-session-1",
            },
        }
    )
    session_id = ensured["sessionId"]
    ensured_again = service.handle_request(
        {
            "command": "blueprint.planning.ensureContext",
            "args": {
                "projectDir": str(project),
                "blueprintId": "default",
                "desktopSessionId": "desktop-session-1",
            },
        }
    )
    assert ensured_again["sessionId"] == session_id
    assert len(FakeLiveBackend.instances) == 0

    session = service._planning_sessions[session_id]
    assert ensured["mcpContext"]["server_name"] == "framework_control"
    assert "GuLiCode Desktop Blueprint Planning Mode" in ensured["frameworkSystem"]
    assert "separate bottom Top Agent CLI/worker" in ensured["frameworkSystem"]

    control_scopes = session.mcp.token_store.summary()["controlScopes"]
    assert control_scopes
    tools = set(control_scopes[-1]["allowed_tools"])
    assert "top_agent_request_user_input" in tools
    assert "top_agent_stage_start_plan" in tools
    assert "runtime_validate_start" in tools
    assert "runtime_start" not in tools
    assert "top_agent_ask" not in tools
    assert "top_agent_start_session" not in tools

    question_results: list[dict] = []

    def ask_question() -> None:
        question_results.append(
            service._handle_top_agent_request_user_input(
                session_id,
                [{"id": "scope", "question": "Which scope?"}],
            )
        )

    thread = threading.Thread(target=ask_question)
    thread.start()
    deadline = time.monotonic() + 5
    pending_question = None
    while time.monotonic() < deadline:
        status = service.handle_request(
            {"command": "blueprint.planning.status", "args": {"sessionId": session_id}}
        )
        pending_question = status["pendingQuestion"]
        if pending_question:
            break
        time.sleep(0.05)
    assert pending_question is not None
    service.handle_request(
        {
            "command": "blueprint.planning.answerQuestion",
            "args": {
                "sessionId": session_id,
                "questionId": pending_question["questionId"],
                "answers": {"scope": "all"},
            },
        }
    )
    thread.join(timeout=5)
    assert question_results == [
        {
            "ok": True,
            "questionId": pending_question["questionId"],
            "answers": {"scope": "all"},
        }
    ]

    staged = service._handle_top_agent_stage_start_plan(session_id, _plan(), "Run planner first.")
    assert staged["ok"] is True
    assert staged["pendingPlan"]["validation"]["ok"] is True
    rejected = service.handle_request(
        {
            "command": "blueprint.planning.rejectPlan",
            "args": {"sessionId": session_id, "reason": "try again"},
        }
    )
    assert rejected["pendingPlan"] is None
    assert len(FakeLiveBackend.instances) == 0

    service._handle_top_agent_stage_start_plan(session_id, _plan(), "Run planner first.")
    status = service.handle_request(
        {"command": "blueprint.planning.status", "args": {"sessionId": session_id}}
    )
    scope = _planning_control_scope(session)
    fallback_mcp_status = asyncio.run(
        session.mcp._control_request(
            scope,
            tool_name="runtime_status",
            command="run.status",
            args={"recent_events_limit": 20},
            permission="status",
        )
    )
    assert fallback_mcp_status["status_source"]["selected"] == "planning_context"
    assert fallback_mcp_status["source_run_id"] is None
    started = service.handle_request(
        {
            "command": "blueprint.start",
            "args": {
                "projectDir": str(project),
                "blueprintId": "default",
                "plan": status["pendingPlan"]["plan"],
                "executionMode": "live",
            },
        }
    )
    diagnostics_dir = Path(started["run"]["diagnostics"]["path"])
    assert diagnostics_dir == project / ".multi_agent_workspace" / "runs" / "active" / started["runId"] / "shared" / "logs" / "blueprint-diagnostics"
    assert (diagnostics_dir / "snapshot.json").is_file()
    assert (diagnostics_dir / "events.jsonl").is_file()
    marked = service.handle_request(
        {
            "command": "blueprint.planning.markPlanStarted",
            "args": {
                "sessionId": session_id,
                "runId": started["runId"],
                "started": started,
            },
        }
    )
    assert started["run"]["executionMode"] == "live"
    assert marked["activeRun"]["runId"] == started["runId"]
    assert marked["pendingPlan"] is None
    assert marked["statusSource"]["selected"] == "active_live_run"
    assert marked["statusSource"]["mismatch"] is True
    mcp_status = asyncio.run(
        session.mcp._control_request(
            scope,
            tool_name="runtime_status",
            command="run.status",
            args={"recent_events_limit": 20},
            permission="status",
        )
    )
    assert mcp_status["source_run_id"] == started["runId"]
    assert mcp_status["planning_session_id"] == session_id
    assert mcp_status["status_source"]["selected"] == "active_live_run"
    assert "planner" in mcp_status["status"]["agents"]
    repeated_mcp_status = asyncio.run(
        session.mcp._control_request(
            scope,
            tool_name="runtime_status",
            command="run.status",
            args={"recent_events_limit": 20},
            permission="status",
        )
    )
    assert repeated_mcp_status["source_run_id"] == started["runId"]
    mcp_explanation = asyncio.run(
        session.mcp._control_request(
            scope,
            tool_name="top_agent_explain_status",
            command="top_agent.explain_status",
            args={"recent_events_limit": 20},
            permission="status",
        )
    )
    assert mcp_explanation["source_run_id"] == started["runId"]
    mcp_utterances = asyncio.run(
        session.mcp._control_request(
            scope,
            tool_name="runtime_top_agent_utterances",
            command="top_agent.utterances",
            args={},
            permission="utterances",
        )
    )
    assert mcp_utterances["source_run_id"] == started["runId"]
    assert isinstance(mcp_utterances["utterances"], list)
    events = [
        json.loads(line)
        for line in (diagnostics_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    event_types = [event["type"] for event in events]
    assert "blueprint_run_started" in event_types
    assert "planning_active_run_linked" in event_types
    assert "planning_status_snapshot" in event_types
    assert "planning_mcp_control_call" in event_types
    assert "planning_status_source_mismatch" in event_types
    assert event_types.count("planning_status_source_mismatch") == 1
    snapshot = json.loads((diagnostics_dir / "snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["kind"] == "gulicode.blueprint.diagnostics"
    assert snapshot["focus"] == "planning_status_source"
    assert snapshot["current"]["statusSource"]["selected"] == "active_live_run"
    assert len(FakeLiveBackend.instances) == 1
    assert "agent-planner" in FakeLiveBackend.instances[-1].worker_configs
    service.close()


def test_blueprint_service_live_mode_prestarts_all_agents_with_private_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeLiveBackend:
        instances = []
        create_calls = []

        def __init__(self, workers) -> None:
            self.workers = workers
            self.worker_configs = {}
            self.stopped = False
            FakeLiveBackend.instances.append(self)

        @classmethod
        async def create(cls, workers, *, port=9140, verbose=False, allow_empty=False):
            cls.create_calls.append({"workers": list(workers), "allow_empty": allow_empty})
            return cls(workers)

        async def ensure_worker(self, worker) -> None:
            self.worker_configs[str(worker.agent_id)] = worker

        async def run_single(self, worker_id, body, *, timeout_sec=600.0, _skip_skill_inject=False, meta=None, stream_callback=None):
            return {"type": "message", "body": {"ok": True, "text": "done"}}

        async def stop(self) -> None:
            self.stopped = True

    monkeypatch.setattr("multi_agent_tcp.desktop_blueprint_service.CLIWorkerBackend", FakeLiveBackend)

    project = tmp_path / "project"
    project.mkdir()
    skill_dir = project / "skills"
    business_skill = skill_dir / "business-skill"
    business_skill.mkdir(parents=True)
    (business_skill / "SKILL.md").write_text(
        "---\n"
        "name: business-skill\n"
        "description: Business skill description\n"
        "---\n"
        "# Business Skill\n",
        encoding="utf-8",
    )
    rules_dir = project / "rules"
    rules_dir.mkdir()
    rule = rules_dir / "policy.md"
    rule.write_text("# Business Rule\n\nFollow the policy.\n", encoding="utf-8")

    document = _document(project)
    document["graph"]["agent_nodes"]["planner"].update(
        {
            "cli_kind": "codex",
            "model": "gpt-5.4",
            "command": "codex",
        }
    )
    document["graph"]["agent_nodes"]["test-agent"] = {
        "node_id": "test-agent",
        "agent_id": "agent-test-agent",
        "prompt": "Show panel content.",
        "cli_kind": "codex",
        "model": "gpt-5.4",
        "command": "codex",
        "skills": ["business-skill"],
        "skill_selection": {"mode": "selected", "skill_hashes": ["business-skill"]},
        "rule_paths": ["policy.md"],
        "adapter_options": {"gulicode_test_node": True, "skip_git_repo_check": True},
    }
    document["ui"]["config"] = {
        "python_path": sys.executable,
        "project_workdir": str(project),
        "skill_dir": str(skill_dir),
        "rule_dir": str(rules_dir),
    }
    plan = _plan()
    plan["agent_descriptions"]["test-agent"] = "Test panel agent."
    plan["start_nodes"] = ["planner", "test-agent"]
    plan["tasks"]["test-agent"] = {
        "goal": "Exercise the test panel agent.",
        "expected_output": "A test panel response.",
        "acceptance": "The test panel agent can start with private context.",
    }

    service = DesktopBlueprintService()
    service.save_blueprint(project, document)
    started = service.handle_request(
        {
            "command": "blueprint.start",
            "args": {
                "projectDir": str(project),
                "blueprintId": "default",
                "plan": plan,
                "executionMode": "live",
            },
        }
    )

    backend = FakeLiveBackend.instances[-1]
    assert FakeLiveBackend.create_calls[-1]["workers"] == []
    assert FakeLiveBackend.create_calls[-1]["allow_empty"] is True
    assert set(backend.worker_configs) == {"agent-planner", "agent-test-agent"}

    for agent_id, worker in backend.worker_configs.items():
        private = (
            project
            / ".multi_agent_workspace"
            / "runs"
            / "active"
            / started["runId"]
            / "agents"
            / agent_id
            / "private"
        )
        assert worker.cwd == private / "checkout"
        assert worker.adapter_options["codex_home"] == str(private / "codex_home")
        assert worker.adapter_options["diagnostics_dir"] == str(private / "logs" / "codex")
        assert "prompt_execution_context" in worker.adapter_options
        assert "workspace_api" not in worker.adapter_options["prompt_execution_context"]
        assert "submit_command" not in worker.adapter_options["prompt_execution_context"]["code_workspace"]
        assert "workspace_api" in worker.adapter_options["execution_context"]
        assert "submit_command" in worker.adapter_options["execution_context"]["code_workspace"]
        assert worker.extra_env["MULTI_AGENT_WORKSPACE_CONTEXT"] == str(
            private / "workspace_api_context.json"
        )
        assert "MULTI_AGENT_MCP_ORDINARY_TOKEN" in worker.extra_env
        assert (private / "workspace_api_context.json").is_file()
        assert (private / "checkout" / "AGENTS.md").is_file()
        config_text = (private / "codex_home" / "config.toml").read_text(encoding="utf-8")
        assert "[mcp_servers.framework_ordinary]" in config_text
        assert "enabled = true" in config_text
        assert "bearer_token_env_var = \"MULTI_AGENT_MCP_ORDINARY_TOKEN\"" in config_text
        assert '"workspace_checkout"' in config_text
        assert '"agent_dispatch"' in config_text
        assert "[mcp_servers.framework_ordinary.tools.workspace_checkout]" in config_text
        assert "[mcp_servers.framework_ordinary.tools.agent_dispatch]" in config_text
        assert 'approval_mode = "approve"' in config_text
        framework_skill = private / "codex_home" / "skills" / "framework-agent-runtime" / "SKILL.md"
        assert framework_skill.is_file()
        assert "use those MCP tools first" in framework_skill.read_text(encoding="utf-8")
        assert worker.adapter_options["execution_context"]["mcp"]["server_name"] == "framework_ordinary"
        prompt_mcp = worker.adapter_options["prompt_execution_context"]["mcp"]
        assert prompt_mcp["server_name"] == "framework_ordinary"
        assert "bearer_token" not in json.dumps(worker.adapter_options["prompt_execution_context"])
        assert worker.extra_env["MULTI_AGENT_MCP_ORDINARY_TOKEN"] not in json.dumps(
            worker.adapter_options["prompt_execution_context"]
        )

    test_worker = backend.worker_configs["agent-test-agent"]
    private_context = test_worker.adapter_options["execution_context"]["private_context"]
    assert test_worker.adapter_options["gulicode_test_node"] is True
    assert any(
        item.get("hash") == "business-skill" and item.get("source") == "business"
        for item in private_context["skill_catalog"]
    )
    assert private_context["rule_catalog"][0]["name"] == "Business Rule"
    assert Path(private_context["rule_catalog"][0]["rule_path"]).is_file()

    service.close()


def test_live_blueprint_mcp_workspace_dispatch_flow_with_agent_backend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pytest.importorskip("mcp")

    marker = "DETERMINISTIC_MCP_WORKSPACE_SUBMIT_SUCCESS"
    reviewer_marker = "DETERMINISTIC_MCP_REVIEWER_READ_OK"

    async def call_tool(worker, tool_name: str, arguments: dict) -> dict:
        import httpx

        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        token = worker.extra_env["MULTI_AGENT_MCP_ORDINARY_TOKEN"]
        url = _mcp_url_from_private_codex_home(
            Path(worker.adapter_options["codex_home"]),
            "framework_ordinary",
        )
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(headers=headers, timeout=20.0) as client:
            async with streamable_http_client(url, http_client=client) as (
                read_stream,
                write_stream,
                _session_id,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
        assert not result.isError, result
        assert result.structuredContent is not None
        return dict(result.structuredContent)

    class FakeLiveBackend:
        instances = []

        def __init__(self, workers) -> None:
            self.worker_configs = {}
            self.stopped = False
            FakeLiveBackend.instances.append(self)

        @classmethod
        async def create(cls, workers, *, port=9140, verbose=False, allow_empty=False):
            return cls(workers)

        async def ensure_worker(self, worker) -> None:
            self.worker_configs[str(worker.agent_id)] = worker

        async def run_single(
            self,
            worker_id,
            body,
            *,
            timeout_sec=600.0,
            _skip_skill_inject=False,
            meta=None,
            stream_callback=None,
        ):
            worker = self.worker_configs[str(worker_id)]
            if str(worker_id) == "agent-planner":
                project_context = Path(
                    worker.adapter_options["execution_context"]["code_workspace"]["project_context"]
                )
                assert (
                    project_context / "src" / "mcp_probe.txt"
                ).read_text(encoding="utf-8") == "base mcp probe\n"
                await call_tool(worker, "workspace_checkout", {"paths": ["src/mcp_probe.txt"]})
                probe = Path(worker.cwd) / "src" / "mcp_probe.txt"
                probe.write_text(
                    probe.read_text(encoding="utf-8")
                    + f"{marker}\n"
                    + "DETERMINISTIC_MCP_BUSINESS_SKILL_SEEN\n"
                    + "DETERMINISTIC_MCP_BUSINESS_RULE_SEEN\n",
                    encoding="utf-8",
                )
                await call_tool(worker, "workspace_status", {})
                await call_tool(worker, "workspace_diff", {})
                submitted = await call_tool(
                    worker,
                    "workspace_submit",
                    {
                        "task_id": "deterministic-mcp-submit",
                        "summary": "deterministic mcp accepted",
                    },
                )
                submit_result = submitted.get("result", submitted)
                assert submit_result.get("status") == "accepted", submitted
                (Path(worker.cwd) / "private-direct-ok.txt").write_text(
                    "DETERMINISTIC_MCP_PRIVATE_WRITE_ALLOWED",
                    encoding="utf-8",
                )
                await call_tool(
                    worker,
                    "workspace_publish",
                    {
                        "area": "reports",
                        "path": "mcp-live-report.md",
                        "text": f"{marker}\nDETERMINISTIC_MCP_BUSINESS_SKILL_SEEN\n"
                        "DETERMINISTIC_MCP_BUSINESS_RULE_SEEN\n",
                    },
                )
                await call_tool(
                    worker,
                    "workspace_publish_file",
                    {
                        "area": "artifacts",
                        "path": "private-direct-ok.txt",
                        "file_path": "private-direct-ok.txt",
                    },
                )
                await call_tool(
                    worker,
                    "agent_dispatch",
                    {
                        "target_node_id": "reviewer",
                        "body": {
                            "prompt": (
                                "Read mcp-live-report.md directly from shared_workspace.reports "
                                f"and include {reviewer_marker} plus {marker}."
                            )
                        },
                    },
                )
                return {"type": "message", "body": {"ok": True, "text": f"{marker} dispatched"}}

            shared_reports = Path(
                worker.adapter_options["execution_context"]["shared_workspace"]["reports"]
            )
            read = (shared_reports / "mcp-live-report.md").read_text(encoding="utf-8")
            assert marker in read
            return {
                "type": "message",
                "body": {"ok": True, "text": f"{reviewer_marker} {marker}"},
            }

        async def stop(self) -> None:
            self.stopped = True

    monkeypatch.setattr("multi_agent_tcp.desktop_blueprint_service.CLIWorkerBackend", FakeLiveBackend)

    project, cleanup_project = _real_codex_mcp_project_root(tmp_path)
    project.mkdir(parents=True, exist_ok=True)
    probe = project / "src" / "mcp_probe.txt"
    probe.parent.mkdir()
    probe.write_text("base mcp probe\n", encoding="utf-8")
    skill_dir = project / "skills"
    business_skill = skill_dir / "s"
    business_skill.mkdir(parents=True)
    (business_skill / "SKILL.md").write_text(
        "---\n"
        "name: s\n"
        "description: DETERMINISTIC_MCP_BUSINESS_SKILL_DESCRIPTION\n"
        "---\n"
        "# Business Skill\n\n"
        "The deterministic MCP smoke must mention DETERMINISTIC_MCP_BUSINESS_SKILL_SEEN.\n",
        encoding="utf-8",
    )
    rules_dir = project / "rules"
    rules_dir.mkdir()
    (rules_dir / "policy.md").write_text(
        "# Business Rule\n\n"
        "The deterministic MCP smoke must mention DETERMINISTIC_MCP_BUSINESS_RULE_SEEN.\n",
        encoding="utf-8",
    )

    document = _document(project)
    document["graph"]["agent_nodes"] = {
        "planner": {
            "node_id": "planner",
            "agent_id": "agent-planner",
            "prompt": "Run deterministic MCP planner.",
            "cli_kind": "codex",
            "model": "gpt-5.4",
            "command": "codex",
            "write_scope": ["src/mcp_probe.txt"],
            "skills": ["s"],
            "skill_selection": {"mode": "selected", "skill_hashes": ["s"]},
            "rule_paths": ["policy.md"],
        },
        "reviewer": {
            "node_id": "reviewer",
            "agent_id": "agent-reviewer",
            "prompt": "Run deterministic MCP reviewer.",
            "cli_kind": "codex",
            "model": "gpt-5.4",
            "command": "codex",
        },
    }
    document["graph"]["edges"] = [
        {"from": "start", "to": "planner", "edge_type": "exec"},
        {"from": "planner", "to": "reviewer", "edge_type": "exec"},
        {"from": "reviewer", "to": "end", "edge_type": "exec"},
    ]
    document["ui"]["config"] = {
        "python_path": sys.executable,
        "project_workdir": str(project),
        "skill_dir": str(skill_dir),
        "rule_dir": str(rules_dir),
    }
    plan = {
        "user_goal": "Verify deterministic MCP workspace and dispatch behavior.",
        "agent_descriptions": {
            "planner": "Uses MCP tools for workspace changes and dispatch.",
            "reviewer": "Reads planner's published report directly from the shared workspace.",
        },
        "start_nodes": ["planner"],
        "tasks": {
            "planner": {
                "goal": "Use MCP tools for checkout, submit, publish, and dispatch.",
                "expected_output": "Accepted MCP changeset, report, artifact, and reviewer dispatch.",
                "acceptance": "MCP audit includes workspace tools and agent_dispatch.",
            },
        },
        "run_policy": {},
    }

    run_id = "r-mcp"
    service = DesktopBlueprintService()
    monkeypatch.setattr(service, "_generate_run_id_locked", lambda: run_id)
    passed = False
    try:
        service.save_blueprint(project, document)
        started = service.handle_request(
            {
                "command": "blueprint.start",
                "args": {
                    "projectDir": str(project),
                    "blueprintId": "default",
                    "plan": plan,
                    "executionMode": "live",
                },
            }
        )
        assert started["ok"] is True
        status = _wait_for_live_run_idle(service, run_id, timeout_sec=120.0)

        pending = status["queues"]["pending_messages"]
        assert pending
        assert all(item["status"] == "completed" for item in pending.values()), status
        desktop_run = service._runs[run_id]
        workspace_run = desktop_run.runtime.private_context_run
        assert workspace_run is not None

        mcp_tools = [
            item["tool_name"]
            for item in _workspace_manifest_entries(workspace_run, MCP_TOOL_AUDIT_EVENT)
        ]
        expected_mcp_tools = [
            "workspace_checkout",
            "workspace_status",
            "workspace_diff",
            "workspace_submit",
            "workspace_publish",
            "workspace_publish_file",
            "agent_dispatch",
        ]
        missing_mcp_tools = [item for item in expected_mcp_tools if item not in mcp_tools]
        assert not missing_mcp_tools, json.dumps(
            {
                "missing_mcp_tools": missing_mcp_tools,
                "manifest_mcp_tools": mcp_tools,
                "jsonl_mcp_calls": _stream_mcp_tool_calls(status),
                "raw_shell_commands": _stream_raw_commands(status),
                "manifest_path": str(workspace_run.shared_dir / "manifest.json"),
                "planner_diagnostics_dir": str(
                    workspace_run.path / "agents" / "agent-planner" / "private" / "logs" / "codex"
                ),
                "reviewer_diagnostics_dir": str(
                    workspace_run.path / "agents" / "agent-reviewer" / "private" / "logs" / "codex"
                ),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        workspace_commands = [
            item["command"]
            for item in _workspace_manifest_entries(workspace_run, "workspace_api_call")
        ]
        for expected in ["checkout", "status", "diff", "submit", "publish", "publish-file"]:
            assert expected in workspace_commands, workspace_commands

        assert probe.read_text(encoding="utf-8").count(marker) == 1
        assert "DETERMINISTIC_MCP_BUSINESS_SKILL_SEEN" in probe.read_text(encoding="utf-8")
        assert "DETERMINISTIC_MCP_BUSINESS_RULE_SEEN" in probe.read_text(encoding="utf-8")
        assert marker in (workspace_run.shared_reports_dir / "mcp-live-report.md").read_text(encoding="utf-8")
        assert (
            workspace_run.shared_artifacts_dir / "private-direct-ok.txt"
        ).read_text(encoding="utf-8-sig").strip() == "DETERMINISTIC_MCP_PRIVATE_WRITE_ALLOWED"
        journal = workspace_run.shared_dir / "logs" / "message_journal.jsonl"
        assert journal.is_file()
        journal_text = journal.read_text(encoding="utf-8")
        assert "agent.outgoing.staged" in journal_text
        assert "framework.message.queued" in journal_text
        assert reviewer_marker in json.dumps(status["agent_stream_events"], ensure_ascii=False)

        private = workspace_run.path / "agents" / "agent-planner" / "private"
        config_text = (private / "codex_home" / "config.toml").read_text(encoding="utf-8")
        assert "[mcp_servers.framework_ordinary]" in config_text
        assert "enabled = true" in config_text
        assert "bearer_token_env_var = \"MULTI_AGENT_MCP_ORDINARY_TOKEN\"" in config_text
        assert "[mcp_servers.framework_ordinary.tools.workspace_checkout]" in config_text
        assert "[mcp_servers.framework_ordinary.tools.agent_dispatch]" in config_text
        assert 'approval_mode = "approve"' in config_text
        assert (private / "codex_home" / "skills" / "framework-agent-runtime" / "SKILL.md").is_file()
        assert list((private / "codex_home" / "skills").glob("*s/SKILL.md"))
        assert (private / "rules" / "01-policy.md").is_file()
        prompt_context = desktop_run.runtime._launch_nodes["planner"].adapter_options[
            "prompt_execution_context"
        ]
        prompt_dump = json.dumps(prompt_context, ensure_ascii=False)
        assert "framework_ordinary" in prompt_dump
        assert "bearer_token" not in prompt_dump
        assert "rpc_token" not in prompt_dump
        assert str(private) not in prompt_dump
        passed = True
    finally:
        service.close()
        if (
            passed
            and cleanup_project is not None
            and os.environ.get("MULTI_AGENT_TCP_KEEP_REAL_CODEX_MCP") != "1"
        ):
            shutil.rmtree(cleanup_project, ignore_errors=True)


def test_real_codex_live_blueprint_uses_mcp_for_workspace_and_dispatch_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    if os.environ.get("MULTI_AGENT_TCP_RUN_REAL_CODEX_MCP") != "1":
        pytest.skip("set MULTI_AGENT_TCP_RUN_REAL_CODEX_MCP=1 to run the external Codex MCP smoke")
    codex = shutil.which("codex")
    if codex is None:
        pytest.skip("codex CLI is not installed on PATH")

    project, cleanup_project = _real_codex_mcp_project_root(tmp_path)
    project.mkdir(parents=True, exist_ok=True)
    probe = project / "src" / "mcp_probe.txt"
    probe.parent.mkdir()
    probe.write_text("base mcp probe\n", encoding="utf-8")
    skill_dir = project / "skills"
    business_skill = skill_dir / "business-skill"
    business_skill.mkdir(parents=True)
    (business_skill / "SKILL.md").write_text(
        "---\n"
        "name: business-skill\n"
        "description: REAL_MCP_BUSINESS_SKILL_DESCRIPTION\n"
        "---\n"
        "# Business Skill\n\n"
        "The live MCP smoke must mention REAL_MCP_BUSINESS_SKILL_SEEN.\n",
        encoding="utf-8",
    )
    rules_dir = project / "rules"
    rules_dir.mkdir()
    (rules_dir / "policy.md").write_text(
        "# Business Rule\n\n"
        "The live MCP smoke must mention REAL_MCP_BUSINESS_RULE_SEEN.\n",
        encoding="utf-8",
    )

    run_id = "run-real-mcp-live"
    marker = "REAL_MCP_WORKSPACE_SUBMIT_SUCCESS"
    reviewer_marker = "REAL_MCP_REVIEWER_READ_OK"
    project_read_marker = "REAL_MCP_PROJECT_DIRECT_READ_OK"
    codex_options = {
        "model": "gpt-5.5",
        "timeout_sec": 420.0,
        "disable_features": ["shell_snapshot"],
        "config_overrides": _codex_real_flow_config_overrides(),
        "extra_args": ["--full-auto"],
    }
    document = _document(project)
    document["graph"]["agent_nodes"] = {
        "planner": {
            "node_id": "planner",
            "agent_id": "agent-planner",
            "prompt": "Run the live MCP planner smoke.",
            "cli_kind": "codex",
            "model": "gpt-5.5",
            "command": codex,
            "timeout_sec": 480.0,
            "write_scope": ["src/mcp_probe.txt"],
            "skills": ["business-skill"],
            "skill_selection": {"mode": "selected", "skill_hashes": ["business-skill"]},
            "rule_paths": ["policy.md"],
            "adapter_options": codex_options,
        },
        "reviewer": {
            "node_id": "reviewer",
            "agent_id": "agent-reviewer",
            "prompt": "Run the live MCP reviewer smoke.",
            "cli_kind": "codex",
            "model": "gpt-5.5",
            "command": codex,
            "timeout_sec": 360.0,
            "adapter_options": codex_options,
        },
    }
    document["graph"]["edges"] = [
        {"from": "start", "to": "planner", "edge_type": "exec"},
        {"from": "planner", "to": "reviewer", "edge_type": "exec"},
        {"from": "reviewer", "to": "end", "edge_type": "exec"},
    ]
    document["ui"]["config"] = {
        "python_path": sys.executable,
        "project_workdir": str(project),
        "skill_dir": str(skill_dir),
        "rule_dir": str(rules_dir),
    }
    planner_goal = (
        "This is a real Codex live blueprint MCP smoke. You must use the MCP "
        "tools exposed by framework_ordinary; do not run `python -m "
        "multi_agent_tcp.workspace_api`.\n\n"
        "Required sequence:\n"
        "1. Read `src/mcp_probe.txt` directly from `code_workspace.project_context` "
        f"in the Codex Execution Context and remember {project_read_marker}.\n"
        "2. Call `mcp__framework_ordinary__workspace_checkout` for path "
        "`src/mcp_probe.txt`.\n"
        "3. Use shell only inside the current private checkout to append these "
        f"three lines to src/mcp_probe.txt: {marker}, "
        "REAL_MCP_BUSINESS_SKILL_SEEN, REAL_MCP_BUSINESS_RULE_SEEN. Also create "
        "private-direct-ok.txt in the current private checkout containing "
        "REAL_MCP_PRIVATE_WRITE_ALLOWED.\n"
        "4. Call `mcp__framework_ordinary__workspace_status`.\n"
        "5. Call `mcp__framework_ordinary__workspace_diff`.\n"
        "6. Call `mcp__framework_ordinary__workspace_submit` with task_id "
        "`real-mcp-live-submit` and summary `live mcp accepted`.\n"
        "7. Call `mcp__framework_ordinary__workspace_publish` for area `reports`, "
        "path `mcp-live-report.md`, and text containing the submit marker plus "
        "both skill/rule markers.\n"
        "8. Call `mcp__framework_ordinary__workspace_publish_file` for area "
        "`artifacts`, path `private-direct-ok.txt`, and file_path "
        "`private-direct-ok.txt`.\n"
        "9. Call `mcp__framework_ordinary__agent_dispatch` to target `reviewer` "
        "with body JSON containing prompt `Read mcp-live-report.md directly from "
        "shared_workspace.reports in the Codex Execution Context and final answer must include "
        f"{reviewer_marker} plus {marker}.`\n\n"
        f"Your final answer must include {marker} REAL_MCP_CONTEXT_OK "
        f"{project_read_marker} REAL_MCP_BUSINESS_SKILL_SEEN REAL_MCP_BUSINESS_RULE_SEEN and "
        "agent_dispatch sent."
    )
    plan = {
        "user_goal": "Verify real Codex live MCP workspace and dispatch behavior.",
        "agent_descriptions": {
            "planner": "Uses MCP tools for workspace changes and dispatch.",
            "reviewer": "Reads planner's published report directly from the shared workspace.",
        },
        "start_nodes": ["planner"],
        "tasks": {
            "planner": {
                "goal": planner_goal,
                "expected_output": "Accepted MCP changeset, report, artifact, and reviewer dispatch.",
                "acceptance": "MCP audit includes workspace tools and agent_dispatch.",
            },
        },
        "run_policy": {},
    }

    service = DesktopBlueprintService()
    monkeypatch.setattr(service, "_generate_run_id_locked", lambda: run_id)
    passed = False
    try:
        service.save_blueprint(project, document)
        started = service.handle_request(
            {
                "command": "blueprint.start",
                "args": {
                    "projectDir": str(project),
                    "blueprintId": "default",
                    "plan": plan,
                    "executionMode": "live",
                },
            }
        )
        assert started["ok"] is True
        status = _wait_for_live_run_idle(service, run_id, timeout_sec=540.0)

        pending = status["queues"]["pending_messages"]
        assert pending
        assert all(item["status"] == "completed" for item in pending.values()), status
        desktop_run = service._runs[run_id]
        workspace_run = desktop_run.runtime.private_context_run
        assert workspace_run is not None

        mcp_tools = [
            item["tool_name"]
            for item in _workspace_manifest_entries(workspace_run, MCP_TOOL_AUDIT_EVENT)
        ]
        expected_mcp_tools = [
            "workspace_checkout",
            "workspace_status",
            "workspace_diff",
            "workspace_submit",
            "workspace_publish",
            "workspace_publish_file",
            "agent_dispatch",
        ]
        missing_mcp_tools = [item for item in expected_mcp_tools if item not in mcp_tools]
        assert not missing_mcp_tools, json.dumps(
            {
                "missing_mcp_tools": missing_mcp_tools,
                "manifest_mcp_tools": mcp_tools,
                "jsonl_mcp_calls": _stream_mcp_tool_calls(status),
                "raw_shell_commands": _stream_raw_commands(status),
                "manifest_path": str(workspace_run.shared_dir / "manifest.json"),
                "planner_diagnostics_dir": str(
                    workspace_run.path / "agents" / "agent-planner" / "private" / "logs" / "codex"
                ),
                "reviewer_diagnostics_dir": str(
                    workspace_run.path / "agents" / "agent-reviewer" / "private" / "logs" / "codex"
                ),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        workspace_commands = [
            item["command"]
            for item in _workspace_manifest_entries(workspace_run, "workspace_api_call")
        ]
        for expected in ["checkout", "status", "diff", "submit", "publish", "publish-file"]:
            assert expected in workspace_commands, workspace_commands

        probe_text = probe.read_text(encoding="utf-8")
        assert probe_text.count(marker) == 1
        assert "REAL_MCP_BUSINESS_SKILL_SEEN" in probe_text
        assert "REAL_MCP_BUSINESS_RULE_SEEN" in probe_text
        assert project_read_marker in json.dumps(status["agent_stream_events"], ensure_ascii=False)
        report = workspace_run.shared_reports_dir / "mcp-live-report.md"
        assert marker in report.read_text(encoding="utf-8")
        artifact = workspace_run.shared_artifacts_dir / "private-direct-ok.txt"
        assert artifact.read_text(encoding="utf-8-sig").strip() == "REAL_MCP_PRIVATE_WRITE_ALLOWED"

        private = workspace_run.path / "agents" / "agent-planner" / "private"
        assert (private / "checkout" / "AGENTS.md").is_file()
        config_text = (private / "codex_home" / "config.toml").read_text(encoding="utf-8")
        assert "[mcp_servers.framework_ordinary]" in config_text
        assert "enabled = true" in config_text
        assert "bearer_token_env_var = \"MULTI_AGENT_MCP_ORDINARY_TOKEN\"" in config_text
        assert "[mcp_servers.framework_ordinary.tools.workspace_checkout]" in config_text
        assert "[mcp_servers.framework_ordinary.tools.agent_dispatch]" in config_text
        assert 'approval_mode = "approve"' in config_text
        assert (private / "codex_home" / "skills" / "framework-agent-runtime" / "SKILL.md").is_file()
        assert list((private / "codex_home" / "skills").glob("*business-skill/SKILL.md"))
        assert (private / "rules" / "01-policy.md").is_file()
        prompt_context = desktop_run.runtime._launch_nodes["planner"].adapter_options[
            "prompt_execution_context"
        ]
        prompt_dump = json.dumps(prompt_context, ensure_ascii=False)
        assert "framework_ordinary" in prompt_dump
        assert "bearer_token" not in prompt_dump
        assert "rpc_token" not in prompt_dump
        assert str(private) not in prompt_dump

        commands = "\n".join(_stream_raw_commands(status))
        assert "multi_agent_tcp.workspace_api" not in commands
        assert reviewer_marker in json.dumps(status["agent_stream_events"], ensure_ascii=False)
        passed = True
    finally:
        service.close()
        if (
            passed
            and cleanup_project is not None
            and os.environ.get("MULTI_AGENT_TCP_KEEP_REAL_CODEX_MCP") != "1"
        ):
            shutil.rmtree(cleanup_project, ignore_errors=True)


def test_blueprint_service_live_mode_does_not_start_workers_for_invalid_plan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeLiveBackend:
        instances = []

        def __init__(self, workers) -> None:
            self.worker_configs = {}
            self.stopped = False
            FakeLiveBackend.instances.append(self)

        @classmethod
        async def create(cls, workers, *, port=9140, verbose=False, allow_empty=False):
            return cls(workers)

        async def ensure_worker(self, worker) -> None:
            self.worker_configs[str(worker.agent_id)] = worker

        async def stop(self) -> None:
            self.stopped = True

    monkeypatch.setattr("multi_agent_tcp.desktop_blueprint_service.CLIWorkerBackend", FakeLiveBackend)
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService()
    service.save_blueprint(project, _document(project))
    bad_plan = _plan()
    bad_plan["agent_descriptions"] = {}

    try:
        service.handle_request(
            {
                "command": "blueprint.start",
                "args": {
                    "projectDir": str(project),
                    "blueprintId": "default",
                    "plan": bad_plan,
                    "executionMode": "live",
                },
            }
        )
    except BlueprintServiceError as exc:
        assert exc.code == "START_PLAN_INVALID"
    else:  # pragma: no cover
        raise AssertionError("invalid live start plan should fail")

    assert FakeLiveBackend.instances[-1].worker_configs == {}
    assert FakeLiveBackend.instances[-1].stopped is True
    service.close()


def test_blueprint_service_live_mode_cleans_up_failed_private_agent_start(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeLiveBackend:
        instances = []

        def __init__(self, workers) -> None:
            self.stopped = False
            FakeLiveBackend.instances.append(self)

        @classmethod
        async def create(cls, workers, *, port=9140, verbose=False, allow_empty=False):
            return cls(workers)

        async def ensure_worker(self, worker) -> None:
            raise RuntimeError("boom")

        async def stop(self) -> None:
            self.stopped = True

    monkeypatch.setattr("multi_agent_tcp.desktop_blueprint_service.CLIWorkerBackend", FakeLiveBackend)
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService()
    service.save_blueprint(project, _document(project))

    try:
        service.handle_request(
            {
                "command": "blueprint.start",
                "args": {
                    "projectDir": str(project),
                    "blueprintId": "default",
                    "plan": _plan(),
                    "executionMode": "live",
                },
            }
        )
    except BlueprintServiceError as exc:
        assert exc.code == "LIVE_AGENT_START_FAILED"
        assert "boom" in exc.details["error"]
    else:  # pragma: no cover
        raise AssertionError("failed live Agent startup should surface a stable error")

    assert FakeLiveBackend.instances[-1].stopped is True
    service.close()


def test_codex_jsonl_event_to_agent_stream_events_maps_public_parts() -> None:
    events = codex_jsonl_event_to_agent_stream_events(
        {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "hello"}},
        stream_context={"run_id": "run-1", "node_id": "planner", "agent_id": "agent-planner", "message_id": "msg-1"},
    )

    assert events == [
        {
            "kind": "part.delta",
            "run_id": "run-1",
            "node_id": "planner",
            "agent_id": "agent-planner",
            "message_id": "msg-1",
            "raw": {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "hello"}},
            "part_id": "item_1",
            "part_type": "text",
            "field": "text",
            "delta": "hello",
            "text": "hello",
            "status": "completed",
        }
    ]


def test_codex_jsonl_event_to_agent_stream_events_maps_mcp_tool_calls() -> None:
    events = codex_jsonl_event_to_agent_stream_events(
        {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "type": "mcp_tool_call",
                "server": "framework_ordinary",
                "tool": "workspace_checkout",
                "arguments": {"paths": ["src/mcp_probe.txt"]},
                "error": {"message": "user cancelled MCP tool call"},
                "status": "failed",
            },
        },
        stream_context={"run_id": "run-1", "node_id": "planner", "agent_id": "agent-planner", "message_id": "msg-1"},
    )

    assert events == [
        {
            "kind": "tool.completed",
            "run_id": "run-1",
            "node_id": "planner",
            "agent_id": "agent-planner",
            "message_id": "msg-1",
            "raw": {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "mcp_tool_call",
                    "server": "framework_ordinary",
                    "tool": "workspace_checkout",
                    "arguments": {"paths": ["src/mcp_probe.txt"]},
                    "error": {"message": "user cancelled MCP tool call"},
                    "status": "failed",
                },
            },
            "part_id": "item_1",
            "part_type": "tool",
            "tool_name": "workspace_checkout",
            "tool_kind": "mcp_tool_call",
            "tool_input": {"paths": ["src/mcp_probe.txt"]},
            "tool_output": None,
            "status": "failed",
            "tool_server": "framework_ordinary",
            "tool_error": {"message": "user cancelled MCP tool call"},
        }
    ]


def test_agent_tcp_client_stream_messages_do_not_satisfy_final_reply() -> None:
    async def scenario() -> None:
        client = AgentTCPClient("orchestrator", "127.0.0.1", 0)
        events = []
        await client._enqueue_received(
            {
                "type": "message",
                "from": "agent-planner",
                "body": {"type": "agent.stream", "event": {"kind": "part.delta", "delta": "hello"}},
            }
        )
        await client._enqueue_received(
            {
                "type": "message",
                "from": "agent-planner",
                "body": {"ok": True, "text": "final"},
            }
        )

        async def stream_callback(event: dict) -> None:
            events.append(event)

        reply = await client.wait_for_message(
            expect_from="agent-planner",
            timeout_sec=1,
            stream_callback=stream_callback,
        )
        assert reply["body"]["text"] == "final"
        assert events == [{"kind": "part.delta", "delta": "hello"}]

    asyncio.run(scenario())


def test_agent_tcp_client_preserves_unmatched_sender_replies() -> None:
    async def scenario() -> None:
        client = AgentTCPClient("orchestrator", "127.0.0.1", 0)

        planner_waiter = asyncio.create_task(
            client.wait_for_message(expect_from="agent-planner", timeout_sec=1)
        )
        await client._enqueue_received(
            {
                "type": "message",
                "from": "agent-reviewer",
                "body": {"ok": True, "text": "reviewer final"},
            }
        )
        await asyncio.sleep(0)
        assert planner_waiter.done() is False

        await client._enqueue_received(
            {
                "type": "message",
                "from": "agent-planner",
                "body": {"ok": True, "text": "planner final"},
            }
        )

        planner_reply = await planner_waiter
        reviewer_reply = await client.wait_for_message(
            expect_from="agent-reviewer",
            timeout_sec=1,
        )

        assert planner_reply["body"]["text"] == "planner final"
        assert reviewer_reply["body"]["text"] == "reviewer final"

    asyncio.run(scenario())


def test_agent_tcp_client_demuxes_concurrent_waiters_and_streams() -> None:
    async def scenario() -> None:
        client = AgentTCPClient("orchestrator", "127.0.0.1", 0)
        planner_events: list[dict] = []
        reviewer_events: list[dict] = []

        async def planner_stream(event: dict) -> None:
            planner_events.append(event)

        async def reviewer_stream(event: dict) -> None:
            reviewer_events.append(event)

        planner_waiter = asyncio.create_task(
            client.wait_for_message(
                expect_from="agent-planner",
                timeout_sec=1,
                stream_callback=planner_stream,
            )
        )
        reviewer_waiter = asyncio.create_task(
            client.wait_for_message(
                expect_from="agent-reviewer",
                timeout_sec=1,
                stream_callback=reviewer_stream,
            )
        )
        await asyncio.sleep(0)

        await client._enqueue_received(
            {
                "type": "message",
                "from": "agent-reviewer",
                "body": {"type": "agent.stream", "event": {"kind": "part.delta", "delta": "review"}},
            }
        )
        await client._enqueue_received(
            {
                "type": "message",
                "from": "agent-reviewer",
                "body": {"ok": True, "text": "reviewer final"},
            }
        )
        await client._enqueue_received(
            {
                "type": "message",
                "from": "agent-planner",
                "body": {"type": "agent.stream", "event": {"kind": "part.delta", "delta": "plan"}},
            }
        )
        await client._enqueue_received(
            {
                "type": "message",
                "from": "agent-planner",
                "body": {"ok": True, "text": "planner final"},
            }
        )

        planner_reply, reviewer_reply = await asyncio.gather(planner_waiter, reviewer_waiter)

        assert planner_reply["body"]["text"] == "planner final"
        assert reviewer_reply["body"]["text"] == "reviewer final"
        assert planner_events == [{"kind": "part.delta", "delta": "plan"}]
        assert reviewer_events == [{"kind": "part.delta", "delta": "review"}]

    asyncio.run(scenario())


def test_blueprint_http_server_returns_error_details(tmp_path: Path) -> None:
    server = DesktopBlueprintHTTPServer(token="secret")
    server.start()
    try:
        response = _post(
            server.url,
            "secret",
            "blueprint.status",
            {"runId": "run-missing"},
            expect_error=True,
        )
        assert response["ok"] is False
        assert response["code"] == "RUN_NOT_FOUND"
    finally:
        server.close()


def _post(url: str, token: str, command: str, args: dict, *, expect_error: bool = False) -> dict:
    body = json.dumps({"token": token, "command": command, "args": args}).encode("utf-8")
    req = request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=5) as response:  # noqa: S310 - local test server
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        if not expect_error:
            raise
        payload = getattr(exc, "read", lambda: b"")()
        return json.loads(payload.decode("utf-8"))
