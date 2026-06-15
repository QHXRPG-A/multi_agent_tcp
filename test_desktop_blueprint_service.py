from __future__ import annotations

import json
import asyncio
import hashlib
import importlib.util
import inspect
import os
import shutil
import sys
import tempfile
import threading
import time
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib import request

import pytest

from multi_agent_tcp.desktop_blueprint_service import (
    BlueprintServiceError,
    DesktopBlueprintRun,
    DesktopBlueprintHTTPServer,
    DesktopBlueprintNoopBackend,
    DesktopBlueprintService,
    blueprint_legacy_session_key_for_pool,
    blueprint_popo_named_session_key,
    blueprint_session_key_for_pool,
)
from multi_agent_tcp import blueprint_script_nodes
from multi_agent_tcp import desktop_blueprint_service as desktop_blueprint_service_module
from multi_agent_tcp.blueprint_resident_services import discover_resident_services, _resident_service_call_timeout
from multi_agent_tcp.blueprint_mcp_runtime import (
    MCP_TOOL_AUDIT_EVENT,
    MCPTokenScope,
    RunMCPRuntimeHandle,
    RunMCPTokenStore,
    resolve_allowed_publish_file,
)
from multi_agent_tcp.codex_bridge import codex_jsonl_event_to_agent_stream_events
from multi_agent_tcp.agent_launch_context import (
    CODEX_RUNTIME_STATE_FILES,
    write_private_codex_mcp_config,
)
from multi_agent_tcp._asyncio_utils import (
    install_asyncio_connection_reset_filter,
    _should_suppress_asyncio_connection_reset,
)
from multi_agent_tcp.client import AgentTCPClient
from multi_agent_tcp.excel_audit import finalize_service_call_audit, prepare_service_call_audit
from multi_agent_tcp.graph_runtime import ScriptNode
from multi_agent_tcp.protocol import read_frame, write_frame
from multi_agent_tcp.workspace_manager import DulwichWorkspaceManager, RunWorkspace


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any], *, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload


def _load_gulicode_bp_installer_module():
    path = Path(__file__).resolve().parent / "plugins" / "gulicode-bp" / "scripts" / "install_personal_plugin.py"
    spec = importlib.util.spec_from_file_location("gulicode_bp_install_personal_plugin", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_gulicode_bp_smoke_module():
    path = Path(__file__).resolve().parent / "plugins" / "gulicode-bp" / "scripts" / "smoke_standalone_plugin.py"
    spec = importlib.util.spec_from_file_location("gulicode_bp_smoke_standalone_plugin", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resident_service_invalid_display_name_falls_back_to_file_stem(tmp_path: Path) -> None:
    service_root = tmp_path / "state" / "resident_services"
    service_root.mkdir(parents=True)
    for filename, class_name, title in (
        ("table_queue_service.py", "TableQueueService", "占表服务"),
        ("xltool_service.py", "XltoolService", "策划填表服务"),
    ):
        (service_root / filename).write_text(
            "\n".join(
                [
                    "from gulicode_blueprint_service import blueprint_service, service_method",
                    "",
                    f"@blueprint_service(name={json.dumps(title, ensure_ascii=False)}, title={json.dumps(title, ensure_ascii=False)})",
                    f"class {class_name}:",
                    '    @service_method(name="health")',
                    "    def health(self) -> dict:",
                    '        return {"ok": True}',
                    "",
                ]
            ),
            encoding="utf-8",
        )

    discovered = discover_resident_services(tmp_path / "state")

    services = {service["module_path"]: service["service_name"] for service in discovered["services"]}
    assert services["table_queue_service.py"] == "table_queue"
    assert services["xltool_service.py"] == "xltool"
    assert [diagnostic["path"] for diagnostic in discovered["diagnostics"]] == [
        "table_queue_service.py",
        "xltool_service.py",
    ]


def _load_gulicode_bp_bootstrap_runtime_module():
    path = Path(__file__).resolve().parent / "plugins" / "gulicode-bp" / "scripts" / "bootstrap_runtime.py"
    spec = importlib.util.spec_from_file_location("gulicode_bp_bootstrap_runtime", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_gulicode_bp_mcp_module():
    path = Path(__file__).resolve().parent / "plugins" / "gulicode-bp" / "mcp" / "gulicode_bp_mcp.py"
    spec = importlib.util.spec_from_file_location("gulicode_bp_mcp", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
                    "node_type": "agent",
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


def _popo_document(
    project_dir: Path,
    *,
    blueprint_id: str,
    name: str,
    prompt: str,
    robot_app_key: str = "robot-1",
) -> dict:
    document = _document(project_dir)
    document["id"] = blueprint_id
    document["name"] = name
    document["graph"]["agent_nodes"]["planner"]["prompt"] = prompt
    document["runtime"] = _popo_runtime(robot_app_key=robot_app_key)
    return document


def _popo_entry(robot_app_key: str = "robot-1") -> dict:
    return {
        "enabled": True,
        "robot_app_key": robot_app_key,
        "robot_name": "Robot",
        "robot_app_secret": "secret",
        "callback_token": "token",
        "aes_key": "0123456789abcdef0123456789abcdef",
    }


def _popo_runtime(start_node_id: str = "planner", robot_app_key: str = "robot-1") -> dict:
    return {
        "start_node_id": start_node_id,
        "popo_entry": _popo_entry(robot_app_key),
    }


def _enable_agent_popo(document: dict, node_id: str = "planner", robot_app_key: str = "robot-1") -> dict:
    document.setdefault("runtime", {})["start_node_id"] = node_id
    document["graph"]["agent_nodes"][node_id]["popo_entry"] = _popo_entry(robot_app_key)
    return document


def _register_fake_slot(
    service: DesktopBlueprintService,
    project: Path,
    document: dict,
    *,
    run_id: str = "run-slot-1",
    robot_app_key: str = "robot-1",
    slot_status: str = "idle",
) -> DesktopBlueprintRun:
    preflight = service._blueprint_session_preflight(
        project,
        str(document["id"]),
        require_popo=False,
    )
    graph = preflight["graph"]
    structure_id = str(preflight["blueprintStructureId"])
    pool_key = desktop_blueprint_service_module.blueprint_slot_pool_key(
        project_dir=project,
        source="popo",
        source_binding=robot_app_key,
        blueprint_structure_id=structure_id,
    )
    reset_calls: list[dict[str, Any]] = []

    async def reset_started_agents_for_session(graph_arg=None, **kwargs: Any) -> dict[str, Any]:
        reset_calls.append(
            {
                "graph": graph_arg,
                "popoTerminationSessionKey": runtime.popo_termination_session_key,
                "popoReplySessionKey": runtime.popo_reply_session_key,
                "kwargs": dict(kwargs),
            }
        )
        return {"ok": True, "restarted": [{"node_id": "planner", "agent_id": "agent-planner"}]}

    runtime = SimpleNamespace(
        popo_termination_start_node_id="",
        popo_termination_session_key="",
        popo_termination_reminder_interval_sec=0.0,
        popo_reply_start_node_id="",
        popo_reply_session_key="",
        reset_calls=reset_calls,
        ready_for_session_reset=lambda: True,
        reset_started_agents_for_session=reset_started_agents_for_session,
    )
    mcp_calls: list[dict[str, str]] = []
    mcp_history_calls: list[dict[str, str]] = []
    mcp_clear_calls: list[str] = []

    def enable_blueprint_session_termination(*, start_node_id: str, session_key: str) -> None:
        mcp_calls.append({"startNodeId": start_node_id, "sessionKey": session_key})

    def enable_popo_session_termination(*, start_node_id: str, session_key: str) -> None:
        enable_blueprint_session_termination(start_node_id=start_node_id, session_key=session_key)

    def enable_session_history_tools(*, start_node_id: str, session_key: str) -> None:
        mcp_history_calls.append({"startNodeId": start_node_id, "sessionKey": session_key})

    mcp = SimpleNamespace(
        termination_calls=mcp_calls,
        history_calls=mcp_history_calls,
        clear_calls=mcp_clear_calls,
        enable_blueprint_session_termination=enable_blueprint_session_termination,
        enable_popo_session_termination=enable_popo_session_termination,
        enable_session_history_tools=enable_session_history_tools,
        clear_blueprint_session_termination=lambda: mcp_clear_calls.append("terminate"),
        clear_session_history_tools=lambda: mcp_clear_calls.append("history"),
        close=lambda: mcp_clear_calls.append("close"),
        summary=lambda: {
            "terminationCalls": list(mcp_calls),
            "historyCalls": list(mcp_history_calls),
            "clearCalls": list(mcp_clear_calls),
        },
    )
    run = DesktopBlueprintRun(
        run_id=run_id,
        project_dir=project.resolve(),
        blueprint_id=str(document["id"]),
        document=document,
        graph=graph,
        runtime=runtime,
        control=None,
        execution_mode="live",
        created_at=1.0,
        updated_at=1.0,
        start_node_id=document["runtime"]["start_node_id"],
        slot_status=slot_status,
        slot_pool_key=pool_key,
        blueprint_structure_id=structure_id,
        robot_app_key=robot_app_key,
        mcp=mcp,
        slot_started_at=1.0,
        slot_last_touched_at=1.0,
    )
    service._runs[run_id] = run
    return run


def _patch_fake_session_instances(
    monkeypatch: pytest.MonkeyPatch,
    service: DesktopBlueprintService,
    *,
    run_prefix: str = "run-session",
) -> list[DesktopBlueprintRun]:
    runs: list[DesktopBlueprintRun] = []

    def fake_start_session_instance(**kwargs: Any):
        run_id = f"{run_prefix}-{len(runs) + 1}"
        project_dir = Path(str(kwargs["project_dir"]))
        document = dict(kwargs["document"])
        run = _register_fake_slot(
            service,
            project_dir,
            document,
            run_id=run_id,
            robot_app_key=str(kwargs.get("robot_app_key") or ""),
            slot_status="",
        )
        run.session_key = str(kwargs.get("session_key") or "")
        run.bound_session_key = ""
        run.blueprint_structure_id = str(kwargs.get("blueprint_structure_id") or run.blueprint_structure_id)
        run.source_bindings = dict(kwargs.get("source_bindings") or {})
        runs.append(run)
        return run, {
            "ok": True,
            "pending": False,
            "validation": {"ok": True, "errors": [], "warnings": []},
            "queued_messages": [],
            "start_manifest": {},
        }

    monkeypatch.setattr(service, "_start_blueprint_session_instance", fake_start_session_instance)
    return runs


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


def test_blueprint_runtime_set_start_agent_saves_without_starting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["graph"]["agent_nodes"]["review"] = {
        "node_id": "review",
        "node_type": "agent",
        "agent_id": "agent-review",
        "prompt": "Review.",
    }
    document["runtime"] = {"start_node_id": "planner"}
    service.save_blueprint(project, document)
    start_called = False

    def fake_start(*args, **kwargs):
        nonlocal start_called
        start_called = True
        return {"ok": True}

    monkeypatch.setattr(service, "start_blueprint_run", fake_start)

    result = service.handle_request(
        {
            "command": "blueprint.runtime.setStartAgent",
            "args": {"projectDir": str(project), "blueprintId": "default", "startNodeId": "review"},
        }
    )

    assert result["ok"] is True
    assert result["startNodeId"] == "review"
    assert service.open_blueprint(project, "default")["runtime"]["start_node_id"] == "review"
    assert start_called is False


def test_blueprint_runtime_set_start_agent_rejects_worker_node(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document()
    document["graph"]["agent_nodes"]["worker"] = {
        "node_id": "worker",
        "node_type": "worker_agent",
        "agent_id": "agent-worker",
        "prompt": "Worker.",
    }
    document["runtime"] = {"start_node_id": "planner"}
    service.save_blueprint(project, document)

    with pytest.raises(BlueprintServiceError) as exc:
        service.handle_request(
            {
                "command": "blueprint.runtime.setStartAgent",
                "args": {"projectDir": str(project), "blueprintId": "default", "startNodeId": "worker"},
            }
        )

    assert exc.value.code == "BLUEPRINT_START_NODE_REQUIRED"
    assert exc.value.details["validStartNodes"] == ["planner"]
    assert service.open_blueprint(project, "default")["runtime"]["start_node_id"] == "planner"
    invalid = service.open_blueprint(project, "default")
    invalid["runtime"]["start_node_id"] = "worker"
    validation = service.validate_blueprint(invalid)
    assert validation["ok"] is False
    assert "full Agent node" in validation["errors"][0]


def test_blueprint_runtime_set_start_agent_disables_previous_popo_entry(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["graph"]["agent_nodes"]["review"] = {
        "node_id": "review",
        "node_type": "agent",
        "agent_id": "agent-review",
        "prompt": "Review.",
    }
    _enable_agent_popo(document, "planner", "robot-1")
    service.save_blueprint(project, document)

    result = service.handle_request(
        {
            "command": "blueprint.runtime.setStartAgent",
            "args": {"projectDir": str(project), "blueprintId": "default", "startNodeId": "review"},
        }
    )
    saved = service.open_blueprint(project, "default")

    assert result["ok"] is True
    assert saved["runtime"]["start_node_id"] == "review"
    assert saved["runtime"]["popo_entry"]["enabled"] is False
    assert saved["graph"]["agent_nodes"]["planner"]["popo_entry"]["enabled"] is False
    assert saved["graph"]["agent_nodes"]["planner"]["popo_entry"]["robot_app_key"] == "robot-1"


def test_blueprint_service_validation_allows_bounded_agent_ring_graph(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = {"start_node_id": "planner"}
    document["graph"]["agent_nodes"] = {
        "planner": {
            "node_id": "planner",
            "node_type": "agent",
            "agent_id": "agent-planner",
            "prompt": "Planner.",
        },
        "worker": {
            "node_id": "worker",
            "node_type": "worker_agent",
            "agent_id": "agent-worker",
            "prompt": "Worker.",
        },
    }
    document["graph"]["edges"] = [
        {"from": "planner", "to": "worker", "edge_type": "exec"},
        {"from": "worker", "to": "planner", "edge_type": "exec"},
    ]
    document["graph"]["agent_ring_max_circulations"] = {"ring-planner-worker": 1}
    document["graph"]["agent_ring_context_refresh_periods"] = {"ring-planner-worker": 1}

    assert service.validate_blueprint(document, project_dir=project) == {
        "ok": True,
        "errors": [],
        "warnings": [],
    }


def test_blueprint_service_validation_rejects_invalid_popo_forwarding_agents(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = {"start_node_id": "planner"}
    document["graph"]["agent_nodes"]["review"] = {
        "node_id": "review",
        "node_type": "agent",
        "agent_id": "agent-review",
        "prompt": "Review.",
        "popo_entry": _popo_entry("robot-2"),
    }

    validation = service.validate_blueprint(document, project_dir=project)
    assert validation["ok"] is False
    assert "saved start full Agent" in validation["errors"][0]

    document["graph"]["agent_nodes"]["planner"]["popo_entry"] = _popo_entry("robot-1")
    validation = service.validate_blueprint(document, project_dir=project)
    assert validation["ok"] is False
    assert "only one full Agent" in validation["errors"][0]


def test_blueprint_runtime_execute_plan_dispatches_saved_start_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = {"start_node_id": "planner"}
    service.save_blueprint(project, document)
    captured: dict[str, object] = {}

    def fake_start(project_dir, blueprint_id, plan_data, *, execution_mode="status", session_key="", start_node_id=""):
        captured.update(
            {
                "project_dir": project_dir,
                "blueprint_id": blueprint_id,
                "plan": plan_data,
                "execution_mode": execution_mode,
                "session_key": session_key,
                "start_node_id": start_node_id,
            }
        )
        return {"ok": True, "runId": "run-execute", "status": {"run": {"status": "running"}}}

    monkeypatch.setattr(service, "start_blueprint_run", fake_start)

    result = service.handle_request(
        {
            "command": "blueprint.runtime.executePlan",
            "args": {"projectDir": str(project), "blueprintId": "default", "plan": _plan(), "executionMode": "live"},
        }
    )

    assert result["runId"] == "run-execute"
    assert captured["execution_mode"] == "live"
    assert captured["start_node_id"] == "planner"
    assert captured["plan"]["start_nodes"] == ["planner"]
    assert captured["plan"]["run_policy"]["requires_confirmation"] is False


def test_blueprint_runtime_execute_plan_rejects_other_start_node(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = {"start_node_id": "planner"}
    service.save_blueprint(project, document)
    plan = _plan()
    plan["start_nodes"] = ["other"]

    with pytest.raises(BlueprintServiceError) as exc:
        service.execute_blueprint_plan(project, "default", plan, execution_mode="live")

    assert exc.value.code == "BLUEPRINT_PLAN_START_NODE_MISMATCH"


def test_blueprint_session_message_persists_context_and_uses_stable_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = {"start_node_id": "planner"}
    service.save_blueprint(project, document)
    starts: list[dict] = []

    def fake_start(project_dir, blueprint_id, plan_data, *, execution_mode="status", session_key="", start_node_id=""):
        starts.append(
            {
                "project_dir": project_dir,
                "blueprint_id": blueprint_id,
                "plan": plan_data,
                "execution_mode": execution_mode,
                "session_key": session_key,
                "start_node_id": start_node_id,
            }
        )
        return {"ok": True, "runId": f"run-{len(starts)}", "status": {"run": {"status": "running"}}}

    monkeypatch.setattr(service, "start_blueprint_run", fake_start)

    first = service.message_blueprint_session(
        project,
        "default",
        "第一条消息",
        source="popo",
        popo_user_id="u1",
        popo_session_id="s1",
        popo_group_id="g1",
    )
    second = service.message_blueprint_session(
        project,
        "default",
        "第二条消息",
        source="popo",
        popo_user_id="u1",
        popo_session_id="s1",
        popo_group_id="g1",
    )

    assert first["sessionKey"] == second["sessionKey"]
    assert starts[0]["execution_mode"] == "live"
    assert starts[0]["start_node_id"] == "planner"
    assert starts[0]["plan"]["start_nodes"] == ["planner"]
    assert "第一条消息" in starts[0]["plan"]["tasks"]["planner"]["goal"]
    assert "第二条消息" in starts[1]["plan"]["tasks"]["planner"]["goal"]
    session_path = service.blueprint_sessions_dir() / first["sessionKey"] / "session.json"
    transcript_path = service.blueprint_sessions_dir() / first["sessionKey"] / "transcript.jsonl"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    transcript = transcript_path.read_text(encoding="utf-8")
    assert session["messageCount"] == 2
    assert session["activeRunId"] == "run-2"
    assert "第一条消息" in transcript
    assert "第二条消息" in transcript


def test_blueprint_session_message_requires_configured_start_node(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    service.save_blueprint(project, _document(project))

    with pytest.raises(BlueprintServiceError) as exc:
        service.message_blueprint_session(project, "default", "start", source="popo", popo_user_id="u1")

    assert exc.value.code == "BLUEPRINT_START_NODE_REQUIRED"


def test_blueprint_session_message_queues_when_session_is_already_running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = {"start_node_id": "planner"}
    service.save_blueprint(project, document)
    queued: list[tuple[str, str, str]] = []

    monkeypatch.setattr(service, "_active_run_for_session", lambda session_key: SimpleNamespace(run_id="run-active"))

    def fake_queue(run_id, node_id, text, *, mode="default", **kwargs):
        queued.append((run_id, node_id, text))
        return {"ok": True}

    monkeypatch.setattr(service, "queue_agent_message", fake_queue)

    result = service.message_blueprint_session(
        project,
        "default",
        "继续处理",
        source="popo",
        popo_user_id="u1",
        popo_session_id="s1",
    )

    assert result["queued"] is True
    assert result["runId"] == "run-active"
    assert queued == [("run-active", "planner", "继续处理")]


def test_blueprint_session_message_starts_instance_without_structure_capacity_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    runs = _patch_fake_session_instances(monkeypatch, service)
    monkeypatch.setattr(service, "queue_agent_message", lambda run_id, node_id, text, *, mode="default", **kwargs: {"ok": True})
    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda run, graph=None: {"run": {"runId": run.run_id, "status": "running"}, "recent_events": []},
    )

    first = service.message_blueprint_session(
        project,
        "default",
        "start",
        source="popo",
        popo_user_id="u1",
        popo_session_id="s1",
    )
    second = service.message_blueprint_session(
        project,
        "default",
        "start",
        source="popo",
        popo_user_id="u2",
        popo_session_id="s2",
    )

    assert first["runId"] == "run-session-1"
    assert second["runId"] == "run-session-2"
    assert first["sessionKey"] != second["sessionKey"]
    assert [run.session_key for run in runs] == [first["sessionKey"], second["sessionKey"]]


def test_blueprint_session_message_persists_context_and_uses_stable_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    queued: list[tuple[str, str, str]] = []
    runs = _patch_fake_session_instances(monkeypatch, service)

    monkeypatch.setattr(service, "_run_is_active", lambda run: True)
    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda run, graph=None: {"run": {"runId": run.run_id, "status": "running"}, "recent_events": []},
    )

    def fake_queue(run_id, node_id, text, *, mode="default", **kwargs):
        queued.append((run_id, node_id, text))
        return {"ok": True}

    monkeypatch.setattr(service, "queue_agent_message", fake_queue)

    first = service.message_blueprint_session(
        project,
        "default",
        "first message",
        source="popo",
        popo_user_id="u1",
        popo_session_id="s1",
        popo_group_id="g1",
    )
    second = service.message_blueprint_session(
        project,
        "default",
        "second message",
        source="popo",
        popo_user_id="u1",
        popo_session_id="s1",
        popo_group_id="g1",
    )

    assert first["sessionKey"] == second["sessionKey"]
    assert first["runId"] == "run-session-1"
    assert second["runId"] == "run-session-1"
    assert len(runs) == 1
    assert queued[0][:2] == ("run-session-1", "planner")
    assert "first message" in queued[0][2]
    assert "second message" in queued[1][2]
    run = service._runs["run-session-1"]
    assert run.runtime.popo_termination_start_node_id == ""
    assert run.runtime.popo_termination_session_key == ""
    assert run.mcp.termination_calls == []
    assert run.mcp.history_calls[-1] == {"startNodeId": "planner", "sessionKey": first["sessionKey"]}
    session_path = service.blueprint_sessions_dir() / first["sessionKey"] / "session.json"
    transcript_path = service.blueprint_sessions_dir() / first["sessionKey"] / "transcript.jsonl"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    transcript = transcript_path.read_text(encoding="utf-8")
    assert session["messageCount"] == 2
    assert session["activeRunId"] == "run-session-1"
    assert "first message" in transcript
    assert "second message" in transcript


def test_blueprint_session_stop_terminates_active_session_without_agent_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    _patch_fake_session_instances(monkeypatch, service)
    queued: list[tuple[str, str, str]] = []
    closed: list[tuple[str, str]] = []

    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda run, graph=None: {"run": {"runId": run.run_id, "status": "running"}, "recent_events": []},
    )

    def fake_queue(run_id, node_id, text, *, mode="default", **kwargs):
        queued.append((run_id, node_id, text))
        return {"ok": True}

    def fake_close(run_id: str, *, reason: str = "") -> str:
        closed.append((run_id, reason))
        return ""

    monkeypatch.setattr(service, "queue_agent_message", fake_queue)
    monkeypatch.setattr(service, "_close_blueprint_session_run_best_effort", fake_close)

    first = service.message_blueprint_session(
        project,
        "default",
        "start task",
        source="popo",
        popo_user_id="u1",
        popo_session_id="s1",
    )
    stopped = service.message_blueprint_session(
        project,
        "default",
        "/stop",
        source="popo",
        popo_user_id="u1",
        popo_session_id="s1",
    )

    assert stopped["ok"] is True
    assert stopped["stopped"] is True
    assert stopped["terminated"] is True
    assert stopped["message"] == "已结束当前会话"
    assert stopped["runId"] == first["runId"]
    assert queued and len(queued) == 1
    assert "/stop" not in queued[0][2]
    assert closed == [(first["runId"], "popo requested /stop")]

    session = service._load_blueprint_session(first["sessionKey"])
    assert session is not None
    assert session["status"] == "terminated"
    assert session["activeRunId"] == ""
    assert session["lastRunId"] == first["runId"]
    transcript = (service.blueprint_sessions_dir() / first["sessionKey"] / "transcript.jsonl").read_text(encoding="utf-8")
    assert '"type": "session_terminated"' in transcript
    assert "popo requested /stop" in transcript


def test_blueprint_session_stop_marks_idle_existing_session_terminated_without_starting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = {"start_node_id": "planner"}
    service.save_blueprint(project, document)
    session_key = "main+default"
    service._save_blueprint_session(
        {
            "sessionKey": session_key,
            "projectDir": str(project.resolve()),
            "blueprintId": "default",
            "blueprintName": "Default Blueprint",
            "source": "ui",
            "status": "idle",
            "activeRunId": "",
            "queuedMessages": [],
            "queuedMessageCount": 0,
            "createdAt": 1.0,
            "lastTouchedAt": 1.0,
            "deleted": False,
        }
    )

    monkeypatch.setattr(service, "_start_blueprint_session_instance", lambda **kwargs: pytest.fail("/stop must not start a run"))
    monkeypatch.setattr(service, "queue_agent_message", lambda *args, **kwargs: pytest.fail("/stop must not dispatch to an Agent"))

    result = service.message_blueprint_session(
        project,
        "default",
        "/stop",
        source="ui",
        session_key=session_key,
    )

    assert result["ok"] is True
    assert result["stopped"] is True
    assert result["terminated"] is True
    assert result["previousStatus"] == "idle"
    assert result["message"] == "已结束当前会话"
    session = service._load_blueprint_session(session_key)
    assert session is not None
    assert session["status"] == "terminated"
    assert session["activeRunId"] == ""
    transcript = (service.blueprint_sessions_dir() / session_key / "transcript.jsonl").read_text(encoding="utf-8")
    assert '"type": "session_terminated"' in transcript
    assert "ui requested /stop" in transcript


def test_blueprint_session_stop_without_existing_session_is_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = {"start_node_id": "planner"}
    service.save_blueprint(project, document)

    monkeypatch.setattr(service, "_start_blueprint_session_instance", lambda **kwargs: pytest.fail("/stop must not start a run"))
    monkeypatch.setattr(service, "queue_agent_message", lambda *args, **kwargs: pytest.fail("/stop must not dispatch to an Agent"))

    result = service.message_blueprint_session(
        project,
        "default",
        "/stop",
        source="ui",
        session_key="main+default",
    )

    assert result == {
        "ok": True,
        "sessionKey": "main+default",
        "stopped": True,
        "alreadyStopped": True,
        "message": "当前没有正在运行的会话",
    }
    assert not service._blueprint_session_path("main+default").exists()


def test_blueprint_sessions_clear_terminates_and_deletes_only_current_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    selected_key = "main+default"
    other_key = "main+other"
    for session_key, run_id in ((selected_key, "run-selected"), (other_key, "")):
        service._save_blueprint_session(
            {
                "sessionKey": session_key,
                "projectDir": str(tmp_path),
                "blueprintId": session_key.split("+", 1)[1],
                "blueprintName": session_key,
                "source": "ui",
                "status": "running" if run_id else "idle",
                "activeRunId": run_id,
                "queuedMessages": ["pending"],
                "queuedMessageCount": 1,
                "messageCount": 3,
                "contextSummary": "old context",
                "createdAt": 1.0,
                "lastTouchedAt": 1.0,
                "deleted": False,
            }
        )
        session_dir = service._blueprint_session_dir(session_key)
        service._blueprint_session_transcript_path(session_key).write_text("old transcript\n", encoding="utf-8")
        excel_record = session_dir / "excel_ops" / "agent" / "record.json"
        excel_record.parent.mkdir(parents=True, exist_ok=True)
        excel_record.write_text("{}", encoding="utf-8")

    closed: list[tuple[str, str]] = []
    monkeypatch.setattr(
        service,
        "_active_run_for_session",
        lambda session_key: SimpleNamespace(run_id="run-selected") if session_key == selected_key else None,
    )
    monkeypatch.setattr(
        service,
        "_close_blueprint_session_run_best_effort",
        lambda run_id, *, reason="": closed.append((run_id, reason)),
    )

    result = service.handle_request(
        {
            "command": "blueprint.sessions.clear",
            "args": {"sessionKey": selected_key, "reason": "test clear"},
        }
    )

    assert result["ok"] is True
    assert result["sessionKey"] == selected_key
    assert result["historyCleared"] is True
    assert result["deleteErrors"] == []
    assert str(service._blueprint_session_dir(selected_key) / "excel_ops") in result["deletedPaths"]
    assert closed == [("run-selected", "test clear")]
    selected_session = service._load_blueprint_session(selected_key)
    assert selected_session is not None
    assert selected_session["status"] == "idle"
    assert selected_session["activeRunId"] == ""
    assert selected_session["queuedMessages"] == []
    assert selected_session["queuedMessageCount"] == 0
    assert selected_session["messageCount"] == 0
    assert selected_session["contextSummary"] == ""
    assert selected_session["lastRunId"] == "run-selected"
    assert service._blueprint_session_transcript_path(selected_key).read_text(encoding="utf-8") == ""
    assert not (service._blueprint_session_dir(selected_key) / "excel_ops").exists()
    assert service._blueprint_session_transcript_path(other_key).read_text(encoding="utf-8") == "old transcript\n"
    assert (service._blueprint_session_dir(other_key) / "excel_ops" / "agent" / "record.json").is_file()


def test_blueprint_sessions_clear_idle_session_history_and_rejects_missing_session(tmp_path: Path) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    session_key = "main+default"
    service._save_blueprint_session(
        {
            "sessionKey": session_key,
            "projectDir": str(tmp_path),
            "blueprintId": "default",
            "blueprintName": "Default Blueprint",
            "source": "ui",
            "status": "idle",
            "activeRunId": "",
            "queuedMessages": [],
            "queuedMessageCount": 0,
            "messageCount": 1,
            "createdAt": 1.0,
            "lastTouchedAt": 1.0,
            "deleted": False,
        }
    )
    service._blueprint_session_transcript_path(session_key).write_text("old transcript\n", encoding="utf-8")
    excel_record = service._blueprint_session_dir(session_key) / "excel_ops" / "user" / "record.md"
    excel_record.parent.mkdir(parents=True, exist_ok=True)
    excel_record.write_text("old fill", encoding="utf-8")

    result = service.handle_request(
        {
            "command": "blueprint.sessions.clear",
            "args": {"sessionKey": session_key},
        }
    )

    assert result["ok"] is True
    assert result["cancelledRunId"] == ""
    assert service._blueprint_session_transcript_path(session_key).read_text(encoding="utf-8") == ""
    assert not (service._blueprint_session_dir(session_key) / "excel_ops").exists()

    with pytest.raises(BlueprintServiceError) as exc:
        service.handle_request(
            {
                "command": "blueprint.sessions.clear",
                "args": {"sessionKey": "main+missing"},
            }
        )
    assert exc.value.code == "BLUEPRINT_SESSION_NOT_FOUND"


def test_blueprint_new_clear_keeps_excel_ops_history(tmp_path: Path) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    session_key = "main+default"
    service._save_blueprint_session(
        {
            "sessionKey": session_key,
            "projectDir": str(tmp_path),
            "blueprintId": "default",
            "blueprintName": "Default Blueprint",
            "source": "ui",
            "status": "idle",
            "activeRunId": "",
            "queuedMessages": [],
            "queuedMessageCount": 0,
            "messageCount": 1,
            "createdAt": 1.0,
            "lastTouchedAt": 1.0,
            "deleted": False,
        }
    )
    service._blueprint_session_transcript_path(session_key).write_text("old transcript\n", encoding="utf-8")
    excel_record = service._blueprint_session_dir(session_key) / "excel_ops" / "agent" / "record.json"
    excel_record.parent.mkdir(parents=True, exist_ok=True)
    excel_record.write_text("{}", encoding="utf-8")

    result = service.clear_blueprint_session(session_key, reason="test /new")

    assert result["ok"] is True
    assert service._blueprint_session_transcript_path(session_key).read_text(encoding="utf-8") == ""
    assert excel_record.is_file()


def test_blueprint_session_excel_history_list_filters_current_blueprint_and_sorts(tmp_path: Path) -> None:
    project = (tmp_path / "project").resolve()
    project.mkdir()
    other_project = (tmp_path / "other-project").resolve()
    other_project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")

    def save_session(
        session_key: str,
        *,
        project_dir: Path = project,
        blueprint_id: str = "default",
        deleted: bool = False,
        superseded: bool = False,
    ) -> None:
        service._save_blueprint_session(
            {
                "sessionKey": session_key,
                "projectDir": str(project_dir),
                "blueprintId": blueprint_id,
                "blueprintName": f"Blueprint {blueprint_id}",
                "sessionDisplayName": f"Session {session_key}",
                "source": "ui",
                "status": "idle",
                "activeRunId": "",
                "createdAt": 1.0,
                "lastTouchedAt": 1.0,
                "deleted": deleted,
                "superseded": superseded,
            }
        )

    def write_record(
        session_key: str,
        service_name: str,
        method_name: str,
        arguments: dict[str, Any],
        timestamp: float,
        *,
        blueprint_id: str = "default",
    ) -> None:
        prepared = prepare_service_call_audit(
            {
                "session_key": session_key,
                "session_dir": str(service._blueprint_session_dir(session_key)),
                "project_dir": str(project),
                "blueprint_id": blueprint_id,
            },
            service_name,
            method_name,
            arguments,
            now=lambda: timestamp,
        )
        assert prepared is not None
        finalize_service_call_audit(prepared, {"ok": True, "data": {"changed": True}})

    save_session("main+default-a")
    save_session("main+default-b")
    save_session("main+other-blueprint", blueprint_id="other")
    save_session("main+other-project", project_dir=other_project)
    save_session("main+deleted", deleted=True)
    save_session("main+superseded", superseded=True)

    write_record("main+default-a", "table_queue", "occupy", {"tableNames": ["15-0.xlsx"]}, 1_800_000_000.0)
    write_record(
        "main+default-a",
        "xltool",
        "set_cell",
        {"file": str(project / "15-0.xlsx"), "sheet": "Sheet1", "cell": "A1", "value": "v1", "in_place": True},
        1_800_000_001.0,
    )
    write_record(
        "main+default-b",
        "xltool",
        "set_cell",
        {"file": str(project / "16-0.xlsx"), "sheet": "Sheet1", "cell": "B2", "value": "v2", "in_place": True},
        1_800_000_002.0,
    )
    write_record(
        "main+other-blueprint",
        "xltool",
        "set_cell",
        {"file": str(project / "other.xlsx"), "sheet": "Sheet1", "cell": "C3", "value": "v3", "in_place": True},
        1_800_000_003.0,
        blueprint_id="other",
    )
    write_record(
        "main+other-project",
        "xltool",
        "set_cell",
        {"file": str(other_project / "other-project.xlsx"), "sheet": "Sheet1", "cell": "D4", "value": "v4", "in_place": True},
        1_800_000_004.0,
    )
    write_record(
        "main+deleted",
        "xltool",
        "set_cell",
        {"file": str(project / "deleted.xlsx"), "sheet": "Sheet1", "cell": "E5", "value": "v5", "in_place": True},
        1_800_000_005.0,
    )
    write_record(
        "main+superseded",
        "xltool",
        "set_cell",
        {"file": str(project / "superseded.xlsx"), "sheet": "Sheet1", "cell": "F6", "value": "v6", "in_place": True},
        1_800_000_006.0,
    )

    result = service.handle_request(
        {
            "command": "blueprint.sessions.excelHistoryList",
            "args": {"projectDir": str(project), "blueprintId": "default"},
        }
    )

    assert result["ok"] is True
    assert result["category"] == "all"
    assert [item["sessionKey"] for item in result["sessions"]] == ["main+default-b", "main+default-a"]
    assert result["sessions"][0]["recordCount"] == 1
    assert result["sessions"][0]["latestWorkbook"] == str(project / "16-0.xlsx")
    assert result["sessions"][0]["latestCommand"] == "set-cell"
    assert result["sessions"][1]["recordCount"] == 2
    assert result["sessions"][1]["latestWorkbook"] == str(project / "15-0.xlsx")
    assert result["sessions"][1]["latestCommand"] == "set-cell"


def test_blueprint_session_excel_history_returns_details_and_rejects_missing_or_hidden(tmp_path: Path) -> None:
    project = (tmp_path / "project").resolve()
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")

    for session_key, extra in (
        ("main+default", {}),
        ("main+deleted", {"deleted": True}),
        ("main+superseded", {"superseded": True}),
    ):
        service._save_blueprint_session(
            {
                "sessionKey": session_key,
                "projectDir": str(project),
                "blueprintId": "default",
                "blueprintName": "Default Blueprint",
                "source": "ui",
                "status": "idle",
                "createdAt": 1.0,
                "lastTouchedAt": 1.0,
                **extra,
            }
        )

    for service_name, method_name, arguments, timestamp in (
        ("table_queue", "release", {"tableNames": ["15-0.xlsx"]}, 1_800_000_000.0),
        (
            "xltool",
            "set_cell",
            {"file": str(project / "15-0.xlsx"), "sheet": "Sheet1", "cell": "A1", "value": "v1", "in_place": True},
            1_800_000_001.0,
        ),
    ):
        prepared = prepare_service_call_audit(
            {
                "session_key": "main+default",
                "session_dir": str(service._blueprint_session_dir("main+default")),
                "project_dir": str(project),
                "blueprint_id": "default",
            },
            service_name,
            method_name,
            arguments,
            now=lambda timestamp=timestamp: timestamp,
        )
        assert prepared is not None
        finalize_service_call_audit(prepared, {"ok": True, "data": {"changed": True}})

    result = service.handle_request(
        {
            "command": "blueprint.sessions.excelHistory",
            "args": {"sessionKey": "main+default", "category": "all", "limit": 10},
        }
    )

    assert result["ok"] is True
    assert result["sessionKey"] == "main+default"
    assert result["count"] == 2
    assert {record["category"] for record in result["records"]} == {"xltool", "table_queue"}
    assert result["records"][0]["command"] == "set-cell"
    assert result["records"][0]["workbook"] == str(project / "15-0.xlsx")
    assert result["records"][1]["workbook"] == "15-0.xlsx"

    for session_key in ("main+missing", "main+deleted", "main+superseded"):
        with pytest.raises(BlueprintServiceError) as exc:
            service.handle_request(
                {
                    "command": "blueprint.sessions.excelHistory",
                    "args": {"sessionKey": session_key},
                }
            )
        assert exc.value.code == "BLUEPRINT_SESSION_NOT_FOUND"


def test_popo_help_command_lists_direct_commands_without_binding_or_agent_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")

    monkeypatch.setattr(
        service,
        "_find_global_popo_blueprint_binding",
        lambda *args, **kwargs: pytest.fail("/help must not require a POPO blueprint binding"),
    )
    monkeypatch.setattr(
        service,
        "_start_blueprint_session_instance",
        lambda **kwargs: pytest.fail("/help must not start a run"),
    )
    monkeypatch.setattr(
        service,
        "queue_agent_message",
        lambda *args, **kwargs: pytest.fail("/help must not dispatch to an Agent"),
    )

    result = service.handle_request(
        {
            "command": "blueprint.sessions.message",
            "args": {
                "message": "/help",
                "source": "popo",
                "sourceIdentity": {"robotAppKey": "robot-key"},
                "sessionIdentity": {"popoUserId": "u1", "popoSessionId": "s1"},
            },
        }
    )

    assert result["ok"] is True
    assert result["help"] is True
    assert "后端直接处理" in result["message"]
    assert "不会发送给 Agent" in result["message"]
    commands = {command["command"] for command in result["commands"]}
    assert {"/help", "/new", "/stop", "/excel-log"}.issubset(commands)
    excel_log = next(command for command in result["commands"] if command["command"] == "/excel-log")
    assert excel_log["usage"].startswith("/excel-log ")


def test_blueprint_session_timeline_preserves_order_and_context_skips_queued_messages(tmp_path: Path) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    session_key = "bps_popo_user_1234567890abcdef12345678"
    session = {
        "sessionKey": session_key,
        "contextSummary": "",
    }
    service._append_blueprint_session_event(session_key, {"type": "user_message", "message": "first user"})
    service._append_blueprint_session_event(session_key, {"type": "queued_message", "message": "queued duplicate"})
    service._append_blueprint_session_event(session_key, {"type": "agent_reply", "content": "agent reply"})

    timeline = service.blueprint_session_timeline(session_key)
    assert [event["type"] for event in timeline["events"]] == ["user_message", "queued_message", "agent_reply"]
    assert [event["content"] for event in timeline["events"]] == ["first user", "queued duplicate", "agent reply"]

    context = service._build_blueprint_session_context(session, "current user")
    assert "User: first user" in context
    assert "Agent: agent reply" in context
    assert "[popo_user] current user" in context
    assert "queued duplicate" not in context
    assert "Queued user" not in context


@pytest.mark.skip(reason="run slot reset/reuse model removed")
def test_blueprint_session_terminate_resets_agents_without_ending_run_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    _patch_fake_session_instances(monkeypatch, service)
    queued: list[tuple[str, str, str]] = []

    monkeypatch.setattr(service, "_run_is_active", lambda run: True)
    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda run, graph=None: {"run": {"runId": run.run_id, "status": "running"}, "recent_events": []},
    )
    monkeypatch.setattr(
        service,
        "queue_agent_message",
        lambda run_id, node_id, text, *, mode="default", **kwargs: queued.append((run_id, node_id, text)) or {"ok": True},
    )
    monkeypatch.setattr(
        service,
        "_end_live_run_from_mcp",
        lambda *args, **kwargs: pytest.fail("session termination must not end the run slot"),
    )
    monkeypatch.setattr(
        service,
        "_dispatch_queued_sessions_for_structure_in_thread",
        lambda **kwargs: service._dispatch_queued_sessions_for_structure(**kwargs),
    )

    first = service.message_blueprint_slot(
        project,
        "first message",
        source="popo",
        source_identity={"robotAppKey": "robot-1"},
        session_identity={"popoUserId": "u1", "popoSessionId": "s1"},
    )
    service._append_blueprint_session_event(
        first["sessionKey"],
        {
            "type": "agent_reply",
            "runId": first["runId"],
            "startNodeId": "planner",
            "agentNodeId": "planner",
            "agentId": "agent-planner",
            "content": "agent handled first message",
        },
    )
    monkeypatch.setattr(service, "_active_blueprint_slot_run_count_for_structure", lambda **kwargs: 3)
    second = service.message_blueprint_slot(
        project,
        "second message",
        source="popo",
        source_identity={"robotAppKey": "robot-1"},
        session_identity={"popoUserId": "u2", "popoSessionId": "s2"},
    )
    assert second["deferred"] is True
    assert second["runId"] == ""
    monkeypatch.setattr(service, "_active_blueprint_slot_run_count_for_structure", lambda **kwargs: 0)

    terminated = service._terminate_blueprint_session_from_mcp(
        first["runId"],
        reason="done",
        save_history=True,
        agent_node_id="planner",
        agent_id="agent-planner",
    )
    run = service._runs[first["runId"]]
    assert terminated["ok"] is True
    assert terminated["slotStatus"] == "resetting"
    assert "end" not in terminated

    assert run.slot_reset_future is not None
    run.slot_reset_future.result(timeout=5)

    session_path = service.blueprint_sessions_dir() / first["sessionKey"] / "session.json"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert session["activeRunId"] == ""
    assert session["lastRunId"] == first["runId"]
    assert session["status"] == "terminated"
    assert session["lastTerminatedByAgentNodeId"] == "planner"
    assert run.slot_status == "assigned"
    assert run.session_key == second["sessionKey"]
    assert run.bound_session_key == second["sessionKey"]
    assert run.runtime.reset_calls
    assert run.mcp.clear_calls == ["reply"]

    assert second["sessionKey"] != first["sessionKey"]
    second_session_path = service.blueprint_sessions_dir() / second["sessionKey"] / "session.json"
    second_session = json.loads(second_session_path.read_text(encoding="utf-8"))
    assert second_session["activeRunId"] == first["runId"]
    assert second_session["status"] == "running"
    assert queued[-1][0:2] == (first["runId"], "planner")
    assert "second message" in queued[-1][2]


@pytest.mark.skip(reason="run slot reset/reuse model removed")
def test_blueprint_session_terminate_reset_failure_blocks_slot_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    run = _register_fake_slot(service, project, service.open_blueprint(project, "default"))

    monkeypatch.setattr(service, "_run_is_active", lambda active_run: True)
    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda active_run, graph=None: {"run": {"runId": active_run.run_id, "status": "running"}, "recent_events": []},
    )
    monkeypatch.setattr(service, "queue_agent_message", lambda run_id, node_id, text, *, mode="default", **kwargs: {"ok": True})

    async def failing_reset(graph_arg=None) -> dict[str, Any]:
        raise RuntimeError("restart failed")

    run.runtime.reset_started_agents_for_session = failing_reset

    first = service.message_blueprint_slot(
        project,
        "first message",
        source="popo",
        source_identity={"robotAppKey": "robot-1"},
        session_identity={"popoUserId": "u1", "popoSessionId": "s1"},
    )
    service._terminate_blueprint_session_from_mcp(
        first["runId"],
        reason="done",
        save_history=True,
        agent_node_id="planner",
        agent_id="agent-planner",
    )

    assert run.slot_reset_future is not None
    with pytest.raises(RuntimeError, match="restart failed"):
        run.slot_reset_future.result(timeout=5)
    assert run.slot_status == "reset_failed"
    assert run.slot_reset_error == "restart failed"

    started: list[str] = []

    def start_new_slot(project_dir: Path, blueprint_id: str = "default") -> dict[str, Any]:
        started.append(blueprint_id)
        new_run = _register_fake_slot(
            service,
            project_dir,
            service.open_blueprint(project_dir, blueprint_id),
            run_id="run-slot-2",
        )
        return {"ok": True, "runId": new_run.run_id}

    monkeypatch.setattr(service, "start_blueprint_slot", start_new_slot)

    second = service.message_blueprint_slot(
        project,
        "second message",
        source="popo",
        source_identity={"robotAppKey": "robot-1"},
        session_identity={"popoUserId": "u1", "popoSessionId": "s1"},
    )
    assert started == ["default"]
    assert second["runId"] == "run-slot-2"
    assert run.slot_status == "reset_failed"


@pytest.mark.skip(reason="run slot reset/reuse model removed")
def test_blueprint_session_terminate_defers_reset_until_runtime_idle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    run = _register_fake_slot(service, project, service.open_blueprint(project, "default"))
    ready = {"value": False}
    run.runtime.ready_for_session_reset = lambda: ready["value"]

    monkeypatch.setattr(service, "_run_is_active", lambda active_run: True)
    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda active_run, graph=None: {"run": {"runId": active_run.run_id, "status": "running"}, "recent_events": []},
    )
    monkeypatch.setattr(service, "queue_agent_message", lambda run_id, node_id, text, *, mode="default", **kwargs: {"ok": True})

    first = service.message_blueprint_slot(
        project,
        "first message",
        source="popo",
        source_identity={"robotAppKey": "robot-1"},
        session_identity={"popoUserId": "u1", "popoSessionId": "s1"},
    )
    service._terminate_blueprint_session_from_mcp(
        first["runId"],
        reason="done",
        save_history=True,
        agent_node_id="planner",
        agent_id="agent-planner",
    )

    assert run.slot_reset_future is not None
    time.sleep(0.35)
    assert run.slot_reset_future.done() is False
    assert run.slot_status == "resetting"

    ready["value"] = True
    run.slot_reset_future.result(timeout=5)
    assert run.slot_status == "idle"
    assert run.mcp.clear_calls == ["reply"]


def test_blueprint_session_auto_terminates_after_ten_idle_minutes_without_queue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    _patch_fake_session_instances(monkeypatch, service)
    closed: list[tuple[str, str]] = []

    monkeypatch.setattr(service, "_run_is_active", lambda active_run: True)
    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda active_run, graph=None: {"run": {"runId": active_run.run_id, "status": "running"}, "recent_events": []},
    )
    monkeypatch.setattr(service, "queue_agent_message", lambda run_id, node_id, text, *, mode="default", **kwargs: {"ok": True})
    monkeypatch.setattr(
        service,
        "_close_blueprint_session_run_best_effort",
        lambda run_id, reason="": closed.append((run_id, reason)) or "",
    )

    first = service.message_blueprint_session(
        project,
        "default",
        "first message",
        source="popo",
        popo_user_id="u1",
        popo_session_id="s1",
    )
    session_payload = service._load_blueprint_session(first["sessionKey"])
    assert session_payload is not None
    session_payload["lastTerminatedBy"] = "agent"
    session_payload["lastTerminatedByAgentNodeId"] = "planner"
    session_payload["lastTerminatedByAgentId"] = "agent-planner"
    service._save_blueprint_session(session_payload)

    snapshot = {
        "runStatus": "running",
        "pendingWork": False,
        "readyForSessionReset": True,
        "allAgentsIdle": True,
        "scriptRunning": False,
        "residentServiceRunning": False,
        "workIdleSeconds": 599.0,
        "lastResidentServiceCompletedAt": None,
        "residentServiceIdleSeconds": None,
    }
    monkeypatch.setattr(service, "_runtime_session_idle_snapshot", lambda active_run: dict(snapshot))
    assert service._maybe_auto_terminate_blueprint_session(first["runId"]) is None
    assert closed == []

    snapshot["workIdleSeconds"] = 600.0
    result = service._maybe_auto_terminate_blueprint_session(first["runId"])
    assert result is not None and result["ok"] is True
    assert result["closed"] is True
    assert closed and closed[-1][0] == first["runId"]

    session = json.loads((service.blueprint_sessions_dir() / first["sessionKey"] / "session.json").read_text(encoding="utf-8"))
    assert session["status"] == "terminated"
    assert session["lastTerminatedBy"] == "framework_auto_idle"
    assert "lastTerminatedByAgentNodeId" not in session
    assert "lastTerminatedByAgentId" not in session
    transcript = (service.blueprint_sessions_dir() / first["sessionKey"] / "transcript.jsonl").read_text(encoding="utf-8")
    assert "framework_auto_idle" in transcript


@pytest.mark.skip(reason="queued run slot dispatch model removed")
def test_blueprint_session_auto_terminates_after_five_idle_minutes_when_queue_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    run = _register_fake_slot(service, project, service.open_blueprint(project, "default"))

    monkeypatch.setattr(service, "_run_is_active", lambda active_run: True)
    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda active_run, graph=None: {"run": {"runId": active_run.run_id, "status": "running"}, "recent_events": []},
    )
    monkeypatch.setattr(service, "queue_agent_message", lambda run_id, node_id, text, *, mode="default", **kwargs: {"ok": True})
    monkeypatch.setattr(service, "_dispatch_queued_sessions_for_structure_in_thread", lambda **kwargs: None)

    first = service.message_blueprint_slot(
        project,
        "first message",
        source="popo",
        source_identity={"robotAppKey": "robot-1"},
        session_identity={"popoUserId": "u1", "popoSessionId": "s1"},
    )
    monkeypatch.setattr(service, "_active_blueprint_slot_run_count_for_structure", lambda **kwargs: 3)
    queued = service.message_blueprint_slot(
        project,
        "queued message",
        source="popo",
        source_identity={"robotAppKey": "robot-1"},
        session_identity={"popoUserId": "u2", "popoSessionId": "s2"},
    )
    assert queued["deferred"] is True

    snapshot = {
        "runStatus": "running",
        "pendingWork": False,
        "readyForSessionReset": True,
        "allAgentsIdle": True,
        "scriptRunning": False,
        "residentServiceRunning": False,
        "workIdleSeconds": 299.0,
        "lastResidentServiceCompletedAt": 10.0,
        "residentServiceIdleSeconds": 299.0,
    }
    monkeypatch.setattr(service, "_runtime_session_idle_snapshot", lambda active_run: dict(snapshot))
    assert service._maybe_auto_terminate_blueprint_session(first["runId"]) is None
    assert run.slot_status == "assigned"

    snapshot["workIdleSeconds"] = 300.0
    snapshot["residentServiceIdleSeconds"] = 300.0
    result = service._maybe_auto_terminate_blueprint_session(first["runId"])
    assert result is not None and result["ok"] is True
    assert run.slot_reset_future is not None
    run.slot_reset_future.result(timeout=5)
    assert run.slot_status == "idle"


@pytest.mark.skip(reason="run slot status API removed")
def test_blueprint_slot_status_counts_idle_live_run_as_running_slot(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    _patch_fake_session_instances(monkeypatch, service)

    status = service.blueprint_slot_status(project, "default")

    assert status["status"] == "running"
    assert status["activeSessionCount"] == 0
    assert status["runningRunCount"] == 1
    assert status["idleRunCount"] == 1
    assert status["runningRunIds"] == ["run-slot-1"]


@pytest.mark.skip(reason="run slot status API removed")
def test_blueprint_slot_status_does_not_probe_live_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    _patch_fake_session_instances(monkeypatch, service)

    def fail_runtime_call(*args, **kwargs):
        pytest.fail("slot status summary must not wait on live runtime status")

    monkeypatch.setattr(service, "_runtime_call", fail_runtime_call)

    status = service.blueprint_slot_status(project, "default")

    assert status["status"] == "running"
    assert status["runningRunIds"] == ["run-slot-1"]
    assert status["runningRunCount"] == 1


def test_popo_callback_config_does_not_probe_active_slot_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    service.save_popo_robot(_popo_entry("robot-1"))
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)

    def fail_runtime_call(*args, **kwargs):
        pytest.fail("POPO callback config lookup must not wait on live runtime status")

    monkeypatch.setattr(service, "_runtime_call", fail_runtime_call)

    result = service.resolve_popo_callback_config("robot-1")

    assert result["ok"] is True
    assert result["blueprintId"] == "default"
    assert result["startNodeId"] == "planner"


@pytest.mark.skip(reason="idle run slot selection removed")
def test_blueprint_slot_message_chooses_idle_slot_without_runtime_active_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    _patch_fake_session_instances(monkeypatch, service)
    queued: list[tuple[str, str, str]] = []

    def fail_active_probe(run):
        pytest.fail("slot message routing must use slot metadata, not runtime active probes")

    def fake_queue(run_id, node_id, text, *, mode="default", **kwargs):
        queued.append((run_id, node_id, text))
        return {"ok": True}

    monkeypatch.setattr(service, "_run_is_active", fail_active_probe)
    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda run, graph=None: {"run": {"runId": run.run_id, "status": "running"}, "recent_events": []},
    )
    monkeypatch.setattr(service, "queue_agent_message", fake_queue)

    result = service.message_blueprint_slot(
        project,
        "hello",
        source="popo",
        source_identity={"robotAppKey": "robot-1"},
        session_identity={"popoUserId": "u1", "popoSessionId": "s1"},
    )

    assert result["ok"] is True
    assert result["runId"] == "run-slot-1"
    assert queued[0][:2] == ("run-slot-1", "planner")


@pytest.mark.skip(reason="idle run slot selection removed")
def test_blueprint_slot_idle_selection_ignores_locally_closed_runtime(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    closed = _register_fake_slot(service, project, service.open_blueprint(project, "default"), run_id="run-slot-closed")
    open_run = _register_fake_slot(service, project, service.open_blueprint(project, "default"), run_id="run-slot-open")
    closed.runtime._closed = True

    chosen = service._choose_idle_slot(project, closed.slot_pool_key)

    assert chosen is open_run


def test_blueprint_run_active_check_uses_short_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    run = _register_fake_slot(service, project, service.open_blueprint(project, "default"))
    timeouts: list[float | None] = []

    def timeout_runtime_call(active_run: DesktopBlueprintRun, fn, *, timeout=None):
        timeouts.append(timeout)
        raise desktop_blueprint_service_module.FutureTimeoutError()

    monkeypatch.setattr(service, "_runtime_call", timeout_runtime_call)

    assert service._run_is_active(run) is True
    assert timeouts == [desktop_blueprint_service_module.LIVE_RUN_ACTIVE_CHECK_TIMEOUT_SECONDS]


def test_blueprint_list_runs_times_out_live_runtime_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    _patch_fake_session_instances(monkeypatch, service)
    timeouts: list[float | None] = []

    def timeout_runtime_call(active_run: DesktopBlueprintRun, fn, *, timeout=None):
        timeouts.append(timeout)
        raise desktop_blueprint_service_module.FutureTimeoutError()

    monkeypatch.setattr(service, "_runtime_call", timeout_runtime_call)

    runs = service.list_blueprint_runs(project, "default")

    assert len(runs) == 1
    assert runs[0]["runId"] == "run-slot-1"
    assert runs[0]["status"] == "starting"
    assert runs[0]["statusPending"] is True
    assert "startPending" not in runs[0]
    assert timeouts == [desktop_blueprint_service_module.LIVE_RUNTIME_STATUS_TIMEOUT_SECONDS]


@pytest.mark.skip(reason="run slot terminate API removed")
def test_blueprint_slot_terminate_closes_all_runs_and_sessions(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    opened = service.open_blueprint(project, "default")
    runs = [
        _register_fake_slot(service, project, opened, run_id="run-slot-1", slot_status="assigned"),
        _register_fake_slot(service, project, opened, run_id="run-slot-2", slot_status="assigned"),
        _register_fake_slot(service, project, opened, run_id="run-slot-3", slot_status="idle"),
    ]
    events: list[tuple[str, str, str, bool | None]] = []

    class FakeEndResult:
        def __init__(self, run_id: str, action: str, archive: bool) -> None:
            self.run_id = run_id
            self.action = action
            self.archive = archive

        def to_dict(self) -> dict[str, Any]:
            return {
                "ok": True,
                "action": self.action,
                "run_status": "cancelled",
                "archived": self.archive,
            }

    def install_runtime(run: DesktopBlueprintRun) -> None:
        def end_run(action: str, *, reason: str = "", archive: bool = False) -> FakeEndResult:
            events.append(("end", run.run_id, action, archive))
            return FakeEndResult(run.run_id, action, archive)

        async def close() -> None:
            events.append(("close", run.run_id, "", None))

        async def stop() -> None:
            events.append(("stop", run.run_id, "", None))

        run.runtime.end_run = end_run
        run.runtime.close = close
        run.backend = SimpleNamespace(stop=stop)

    for run in runs:
        install_runtime(run)

    structure_id = runs[0].blueprint_structure_id
    pool_key = runs[0].slot_pool_key

    def save_session(session_key: str, status: str, run_id: str = "") -> None:
        service._save_blueprint_session(
            {
                "sessionKey": session_key,
                "projectDir": str(project.resolve()),
                "poolKey": pool_key,
                "robotAppKey": "robot-1",
                "blueprintId": "default",
                "assignedBlueprintId": "default",
                "blueprintName": "Default Blueprint",
                "blueprintStructureId": structure_id,
                "source": "popo",
                "popoUserId": session_key.removeprefix("bps_popo_").rsplit("_", 1)[0],
                "popoSessionId": "",
                "popoGroupId": "",
                "status": status,
                "activeRunId": run_id,
                "lastRunId": "",
                "contextSummary": "",
                "messageCount": 0,
                "queuedMessages": [{"message": "queued work"}] if status == "queued" else [],
                "queuedMessageCount": 1 if status == "queued" else 0,
                "createdAt": 1.0,
                "lastTouchedAt": 1.0,
                "deleted": False,
            }
        )

    session_keys = [
        "bps_popo_user1_000000000000000000000001",
        "bps_popo_user2_000000000000000000000002",
        "bps_popo_user3_000000000000000000000003",
    ]
    save_session(session_keys[0], "running", "run-slot-1")
    save_session(session_keys[1], "running", "run-slot-2")
    save_session(session_keys[2], "queued")
    runs[0].session_key = runs[0].bound_session_key = session_keys[0]
    runs[1].session_key = runs[1].bound_session_key = session_keys[1]

    result = service.terminate_blueprint_slot(project, "default", reason="user requested slot terminate")

    assert result["terminated"] is True
    assert result["runningRunCount"] == 0
    assert result["activeSessionCount"] == 0
    assert result["queuedSessionCount"] == 0
    assert result["terminatedRunIds"] == ["run-slot-1", "run-slot-2", "run-slot-3"]
    assert result["terminatedSessionKeys"] == sorted(session_keys)
    assert result["closeErrors"] == []
    for run in runs:
        assert run.slot_status == "closed"
        assert run.session_key == ""
        assert run.bound_session_key == ""
    for session_key in session_keys:
        session = service._load_blueprint_session(session_key)
        assert session is not None
        assert session["status"] == "terminated"
        assert session["activeRunId"] == ""
        assert session["queuedMessages"] == []
        assert session["queuedMessageCount"] == 0
        transcript = service._read_blueprint_session_timeline(session_key)
        assert transcript[-1]["type"] == "session_terminated"
        assert transcript[-1]["actor"] == "slot"
    assert ("end", "run-slot-1", "cancel", False) in events
    assert ("end", "run-slot-2", "cancel", False) in events
    assert ("end", "run-slot-3", "cancel", False) in events
    assert ("stop", "run-slot-1", "", None) in events
    assert ("stop", "run-slot-2", "", None) in events
    assert ("stop", "run-slot-3", "", None) in events


@pytest.mark.skip(reason="run slot terminate API removed")
def test_blueprint_slot_terminate_records_run_close_errors(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    run = _register_fake_slot(
        service,
        project,
        service.open_blueprint(project, "default"),
        run_id="run-slot-1",
        slot_status="assigned",
    )
    session_key = "bps_popo_user10_000000000000000000000010"
    service._save_blueprint_session(
        {
            "sessionKey": session_key,
            "projectDir": str(project.resolve()),
            "poolKey": run.slot_pool_key,
            "robotAppKey": "robot-1",
            "blueprintId": "default",
            "assignedBlueprintId": "default",
            "blueprintName": "Default Blueprint",
            "blueprintStructureId": run.blueprint_structure_id,
            "source": "popo",
            "status": "running",
            "activeRunId": run.run_id,
            "queuedMessages": [],
            "queuedMessageCount": 0,
            "createdAt": 1.0,
            "lastTouchedAt": 1.0,
            "deleted": False,
        }
    )
    run.session_key = run.bound_session_key = session_key

    def fail_end_run(action: str, *, reason: str = "", archive: bool = False) -> None:
        raise RuntimeError("cancel failed")

    async def close() -> None:
        return None

    async def stop() -> None:
        return None

    run.runtime.end_run = fail_end_run
    run.runtime.close = close
    run.backend = SimpleNamespace(stop=stop)

    result = service.terminate_blueprint_slot(project, "default")

    assert result["terminated"] is True
    assert result["terminatedRunIds"] == ["run-slot-1"]
    assert result["terminatedSessionKeys"] == [session_key]
    assert result["runningRunCount"] == 0
    assert result["closeErrors"]
    assert result["closeErrors"][0]["runId"] == "run-slot-1"
    assert "cancel failed" in result["closeErrors"][0]["error"]
    assert run.slot_status == "closed"
    assert service._load_blueprint_session(session_key)["status"] == "terminated"


def test_blueprint_session_message_requires_configured_start_node(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = {"start_node_id": ""}
    document["graph"]["agent_nodes"]["planner"]["popo_entry"] = _popo_entry("robot-1")
    service.save_blueprint(project, document)

    with pytest.raises(BlueprintServiceError) as exc:
        service.message_blueprint_session(
            project,
            "default",
            "start",
            source="popo",
            source_identity={"robotAppKey": "robot-1"},
            session_identity={"popoUserId": "u1"},
        )

    assert exc.value.code == "BLUEPRINT_POPO_START_AGENT_REQUIRED"


def test_blueprint_session_message_queues_when_session_is_already_running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    _patch_fake_session_instances(monkeypatch, service)
    queued: list[tuple[str, str, str]] = []

    monkeypatch.setattr(service, "_run_is_active", lambda run: True)
    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda run, graph=None: {"run": {"runId": run.run_id, "status": "running"}, "recent_events": []},
    )

    def fake_queue(run_id, node_id, text, *, mode="default", **kwargs):
        queued.append((run_id, node_id, text))
        return {"ok": True}

    monkeypatch.setattr(service, "queue_agent_message", fake_queue)

    first = service.message_blueprint_session(
        project,
        "default",
        "start task",
        source="popo",
        popo_user_id="u1",
        popo_session_id="s1",
    )
    second = service.message_blueprint_session(
        project,
        "default",
        "continue task",
        source="popo",
        popo_user_id="u1",
        popo_session_id="s1",
    )

    assert second["queued"] is True
    assert second["runId"] == first["runId"] == "run-session-1"
    assert queued[-1][0:2] == ("run-session-1", "planner")
    assert "continue task" in queued[-1][2]


def test_live_session_start_prestarts_all_agent_nodes(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    document = _document(project)
    document["runtime"] = _popo_runtime()
    document["graph"]["agent_nodes"]["worker"] = {
        "node_id": "worker",
        "node_type": "worker_agent",
        "agent_id": "agent-worker",
        "prompt": "Fill planning tables.",
        "write_scope": ["**"],
    }
    document["graph"]["edges"].append(
        {"from": "planner", "to": "worker", "edge_type": "exec"},
    )
    graph = desktop_blueprint_service_module.graph_definition_from_dict(document["graph"])
    runtime = desktop_blueprint_service_module.GraphRuntime(DesktopBlueprintNoopBackend())
    control = desktop_blueprint_service_module.GraphRuntimeControlPlane(runtime, graph)
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    run = DesktopBlueprintRun(
        run_id="run-session-1",
        project_dir=project,
        blueprint_id="default",
        document=document,
        graph=graph,
        runtime=runtime,
        control=control,
        execution_mode="live",
        created_at=1.0,
        updated_at=1.0,
        backend=runtime.cluster,
        start_node_id="planner",
        slot_status="idle",
    )

    try:
        result = asyncio.run(service._complete_live_session_start(run))

        assert result["ok"] is True
        assert set(runtime.instances) == {"planner", "worker"}
        assert runtime.instances["planner"].state == "idle"
        assert runtime.instances["worker"].state == "idle"
        assert set(runtime.cluster.worker_configs) == {"agent-planner", "agent-worker"}
    finally:
        asyncio.run(runtime.close())


def test_graph_runtime_session_reset_restarts_started_agents_only(tmp_path: Path) -> None:
    class FakeCluster:
        def __init__(self) -> None:
            self.ensured: list[str] = []
            self.restarted: list[str] = []

        async def ensure_worker(self, worker: Any) -> None:
            self.ensured.append(str(worker.agent_id))

        async def restart_worker(self, worker: Any) -> None:
            self.restarted.append(str(worker.agent_id))

    document = _document(tmp_path)
    document["graph"]["agent_nodes"]["worker"] = {
        "node_id": "worker",
        "node_type": "worker_agent",
        "prompt": "Work.",
    }
    document["graph"]["agent_nodes"]["not-started"] = {
        "node_id": "not-started",
        "node_type": "worker_agent",
        "prompt": "Do not start.",
    }
    graph = desktop_blueprint_service_module.graph_definition_from_dict(document["graph"])
    cluster = FakeCluster()
    runtime = desktop_blueprint_service_module.GraphRuntime(cluster)

    async def scenario() -> dict[str, Any]:
        planner = await runtime.ensure_agent(graph.agent_nodes["planner"])
        worker = await runtime.ensure_agent(graph.agent_nodes["worker"])
        planner.messages_sent = 2
        planner.task_status = "completed"
        planner.task_summary = "old summary"
        planner.run_prompt_injected = True
        planner.prompt_node_injected_ids = {"prompt-1"}
        worker.messages_sent = 1
        return await runtime.reset_started_agents_for_session(graph)

    result = asyncio.run(scenario())

    assert result["ok"] is True
    assert cluster.ensured == ["agent-planner", "worker"]
    assert cluster.restarted == ["agent-planner", "worker"]
    assert "not-started" not in runtime.instances
    planner_state = runtime.instances["planner"]
    assert planner_state.messages_sent == 0
    assert planner_state.task_status == "not_started"
    assert planner_state.task_summary == ""
    assert planner_state.run_prompt_injected is False
    assert planner_state.prompt_node_injected_ids == set()
    assert planner_state.state == "idle"


def test_graph_runtime_session_reset_can_cancel_active_session_work(tmp_path: Path) -> None:
    class FakeCluster:
        def __init__(self) -> None:
            self.restarted: list[str] = []

        async def ensure_worker(self, worker: Any) -> None:
            pass

        async def restart_worker(self, worker: Any) -> None:
            self.restarted.append(str(worker.agent_id))

    document = _document(tmp_path)
    graph = desktop_blueprint_service_module.graph_definition_from_dict(document["graph"])
    cluster = FakeCluster()
    runtime = desktop_blueprint_service_module.GraphRuntime(cluster)

    async def scenario() -> dict[str, Any]:
        planner = await runtime.ensure_agent(graph.agent_nodes["planner"])
        queued = runtime.queue_agent_message(
            graph.agent_nodes["planner"],
            {"prompt": "old session work"},
        )
        planner.busy_count = 1
        planner.current_message_id = queued.message_id
        planner.task_status = "working"
        return await runtime.reset_started_agents_for_session(
            graph,
            cancel_pending=True,
            reason="new session",
        )

    result = asyncio.run(scenario())

    assert result["ok"] is True
    assert result["cancelled"]["messages"]
    assert cluster.restarted == ["agent-planner"]
    planner_state = runtime.instances["planner"]
    assert planner_state.busy_count == 0
    assert planner_state.current_message_id is None
    assert planner_state.task_status == "not_started"
    assert planner_state.state == "idle"


def test_queue_agent_message_ensures_agent_before_queueing(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    document = _document(project)
    graph = desktop_blueprint_service_module.graph_definition_from_dict(document["graph"])
    runtime = desktop_blueprint_service_module.GraphRuntime(DesktopBlueprintNoopBackend())
    control = desktop_blueprint_service_module.GraphRuntimeControlPlane(runtime, graph)
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    run = DesktopBlueprintRun(
        run_id="run-live-1",
        project_dir=project,
        blueprint_id="default",
        document=document,
        graph=graph,
        runtime=runtime,
        control=control,
        execution_mode="live",
        created_at=1.0,
        updated_at=1.0,
        backend=runtime.cluster,
        start_node_id="planner",
    )
    service._runs[run.run_id] = run

    try:
        queued = service.queue_agent_message(run.run_id, "planner", "hello", mode="top")

        assert queued["ok"] is True
        assert "planner" in runtime.instances
        assert runtime.agent_message_queues["planner"][0].message_id == queued["result"]["message_id"]
        body = runtime.agent_message_queues["planner"][0].body
        assert body["context"]["framework_context"]["agent_node_id"] == "planner"
    finally:
        asyncio.run(runtime.close())


def test_queue_framework_notification_does_not_create_outgoing_batch(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    document = _document(project)
    graph = desktop_blueprint_service_module.graph_definition_from_dict(document["graph"])
    runtime = desktop_blueprint_service_module.GraphRuntime(DesktopBlueprintNoopBackend())
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    run = DesktopBlueprintRun(
        run_id="run-live-1",
        project_dir=project,
        blueprint_id="default",
        document=document,
        graph=graph,
        runtime=runtime,
        control=object(),
        execution_mode="live",
        created_at=1.0,
        updated_at=1.0,
        backend=runtime.cluster,
        start_node_id="planner",
    )

    try:
        queued = service._async_loop.run(
            service._queue_framework_notification_for_runtime(
                run,
                graph.agent_nodes["planner"],
                {
                    "type": "framework_table_queue_notification",
                    "prompt": "table is occupied",
                    "framework_message_kind": "framework_table_queue_notification",
                    "reply_required": True,
                    "reply_visibility": "session_event",
                },
                queue_mode="top",
            )
        )

        assert queued["message_id"].startswith("framework-notification-planner-")
        assert runtime.outgoing_batches == {}
        body = runtime.agent_message_queues["planner"][0].body
        assert body["type"] == "framework_table_queue_notification"
        envelope = body["context"]["framework_context"]["message_envelope"]
        assert envelope["required_script_calls"] == []
        assert envelope["required_outgoing_targets"] == []
        assert envelope["remaining_targets"] == []
        assert envelope["framework_message_kind"] == "framework_table_queue_notification"
        assert envelope["reply_required"] is True
        assert envelope["reply_visibility"] == "session_event"
    finally:
        asyncio.run(runtime.close())


def test_table_queue_notification_consumer_delivers_to_active_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    document = _document(project)
    graph = desktop_blueprint_service_module.graph_definition_from_dict(document["graph"])
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    session_key = "main+default"
    session = {
        "sessionKey": session_key,
        "projectDir": str(project),
        "source": "popo",
        "robotAppKey": "robot-1",
        "blueprintId": "default",
        "assignedBlueprintId": "default",
        "blueprintName": "Default Blueprint",
        "blueprintStructureId": "structure-1",
        "status": "running",
        "activeRunId": "run-live-1",
        "lastRunId": "run-live-1",
        "startNodeId": "planner",
        "deleted": False,
        "createdAt": 1.0,
        "lastTouchedAt": 1.0,
        "messageCount": 1,
    }
    service._save_blueprint_session(session)
    runtime = SimpleNamespace(
        status_snapshot=lambda: {"run": {"status": "running"}},
        popo_reply_start_node_id="",
        popo_reply_session_key="",
    )
    mcp = SimpleNamespace(enable_session_history_tools=lambda **kwargs: None)
    run = DesktopBlueprintRun(
        run_id="run-live-1",
        project_dir=project,
        blueprint_id="default",
        document=document,
        graph=graph,
        runtime=runtime,
        control=object(),
        execution_mode="live",
        created_at=1.0,
        updated_at=1.0,
        start_node_id="planner",
        session_key=session_key,
        robot_app_key="robot-1",
        mcp=mcp,
    )
    service._runs[run.run_id] = run
    captured: list[dict[str, Any]] = []

    async def fake_queue(run_arg: DesktopBlueprintRun, node: Any, body: dict[str, Any], *, queue_mode: str) -> dict[str, Any]:
        captured.append({"run": run_arg.run_id, "node": node.node_id, "body": body, "queue_mode": queue_mode})
        return {"message_id": "queued-notification-1"}

    monkeypatch.setattr(service, "_queue_framework_notification_for_runtime", fake_queue)
    notification = {
        "version": 1,
        "notificationId": "tqn-1",
        "sessionKey": session_key,
        "queueId": "Q1",
        "status": "done",
        "newlyOccupiedTables": ["15-0-table.xlsx"],
        "pendingTables": [],
        "allTables": ["15-0-table.xlsx"],
        "createdAt": "2026-06-12T10:00:00Z",
    }
    path = service._table_queue_notification_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notification, ensure_ascii=False) + "\n", encoding="utf-8")

    result = service.process_table_queue_notifications()

    assert result["ok"] is True
    assert result["delivered"][0]["notificationId"] == "tqn-1"
    assert captured[0]["run"] == "run-live-1"
    assert captured[0]["node"] == "planner"
    assert captured[0]["queue_mode"] == "top"
    assert captured[0]["body"]["type"] == "framework_table_queue_notification"
    assert captured[0]["body"]["reply_required"] is True
    assert "Do not reply only to acknowledge" in captured[0]["body"]["prompt"]
    processed = json.loads(service._table_queue_notification_processed_path().read_text(encoding="utf-8"))
    assert processed["processedNotificationIds"] == ["tqn-1"]
    transcript = (service.blueprint_sessions_dir() / session_key / "transcript.jsonl").read_text(encoding="utf-8")
    assert '"type": "table_queue_notification"' in transcript
    assert "15-0-table.xlsx" in transcript


def test_table_queue_notification_consumer_skips_deleted_session(tmp_path: Path) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    session_key = "main+default"
    service._save_blueprint_session(
        {
            "sessionKey": session_key,
            "projectDir": str(tmp_path / "project"),
            "source": "ui",
            "blueprintId": "default",
            "blueprintName": "Default Blueprint",
            "status": "idle",
            "activeRunId": "",
            "lastRunId": "",
            "deleted": True,
            "createdAt": 1.0,
            "lastTouchedAt": 1.0,
            "messageCount": 0,
        }
    )
    notification = {
        "version": 1,
        "notificationId": "tqn-deleted",
        "sessionKey": session_key,
        "queueId": "Q1",
        "status": "done",
        "newlyOccupiedTables": ["15-0-table.xlsx"],
        "pendingTables": [],
        "allTables": ["15-0-table.xlsx"],
    }
    path = service._table_queue_notification_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notification, ensure_ascii=False) + "\n", encoding="utf-8")

    result = service.process_table_queue_notifications()

    assert result["ok"] is True
    assert result["delivered"] == []
    assert result["skipped"][0]["reason"] == "session deleted or superseded"
    processed = json.loads(service._table_queue_notification_processed_path().read_text(encoding="utf-8"))
    assert processed["processedNotificationIds"] == ["tqn-deleted"]
    transcript = (service.blueprint_sessions_dir() / session_key / "transcript.jsonl").read_text(encoding="utf-8")
    assert '"type": "table_queue_notification_skipped"' in transcript


def test_planning_table_skill_update_notification_delivers_to_fill_planning_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    document = _document(project)
    document["id"] = "fill-planning-form"
    document["name"] = "fill planning form"
    document["runtime"] = {"start_node_id": "planner"}
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    service.save_blueprint(project, document)
    graph = desktop_blueprint_service_module.graph_definition_from_dict(document["graph"])
    captured: list[dict[str, Any]] = []

    def fake_start_session_instance(**kwargs):  # noqa: ANN003, ANN202
        runtime = SimpleNamespace(
            status_snapshot=lambda: {"run": {"status": "running"}},
            popo_reply_start_node_id="",
            popo_reply_session_key="",
        )
        mcp = SimpleNamespace(enable_session_history_tools=lambda **tool_kwargs: None)
        run = DesktopBlueprintRun(
            run_id="run-skill-update",
            project_dir=project,
            blueprint_id="fill-planning-form",
            document=document,
            graph=graph,
            runtime=runtime,
            control=object(),
            execution_mode="live",
            created_at=1.0,
            updated_at=1.0,
            start_node_id="planner",
            session_key=str(kwargs["session_key"]),
            mcp=mcp,
        )
        service._runs[run.run_id] = run
        return run, {"pending": False}

    async def fake_queue(
        run_arg: DesktopBlueprintRun,
        node: Any,
        body: dict[str, Any],
        *,
        queue_mode: str,
    ) -> dict[str, Any]:
        captured.append({"run": run_arg.run_id, "node": node.node_id, "body": body, "queue_mode": queue_mode})
        return {"message_id": "queued-skill-update-1"}

    monkeypatch.setattr(service, "_start_blueprint_session_instance", fake_start_session_instance)
    monkeypatch.setattr(service, "_queue_framework_notification_for_runtime", fake_queue)
    notification = {
        "version": 1,
        "notificationId": "pts-1",
        "kind": "planning_table_skill_update",
        "skillRoot": str(tmp_path / "AISkills"),
        "indexPath": str(tmp_path / "AISkills" / "planning-table-skill-index.md"),
        "targetProjectDir": str(project),
        "targetBlueprintId": "fill-planning-form",
        "commitMessage": "#753970 Codex调试客户端1对多",
        "candidates": [
            {
                "name": "new-fill-skill",
                "skillPath": str(tmp_path / "AISkills" / "new-fill-skill" / "SKILL.md"),
                "description": "新增填表 skill。",
                "indexed": False,
            }
        ],
    }
    path = service._planning_table_skill_update_notification_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notification, ensure_ascii=False) + "\n", encoding="utf-8")

    result = service.process_planning_table_skill_update_notifications()

    assert result["ok"] is True
    assert result["delivered"][0]["notificationId"] == "pts-1"
    assert captured[0]["run"] == "run-skill-update"
    assert captured[0]["node"] == "planner"
    assert captured[0]["queue_mode"] == "top"
    body = captured[0]["body"]
    assert body["type"] == "framework_planning_table_skill_update_notification"
    prompt = body["prompt"]
    assert "Only process the new skill candidates listed below" in prompt
    assert "new-fill-skill" in prompt
    assert "planning-table-skill-index.md" in prompt
    assert "#753970 Codex调试客户端1对多" in prompt
    assert "planning_table_skill_update" in prompt
    assert "mark_processed" in prompt
    processed = json.loads(
        service._planning_table_skill_update_notification_processed_path().read_text(encoding="utf-8")
    )
    assert processed["processedNotificationIds"] == ["pts-1"]


def test_queue_agent_message_does_not_prestart_downstream_agents(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    document = _document(project)
    document["graph"]["agent_nodes"]["worker"] = {
        "node_id": "worker",
        "node_type": "worker_agent",
        "agent_id": "agent-worker",
        "prompt": "Work.",
        "write_scope": ["**"],
    }
    document["graph"]["edges"].append(
        {"from": "planner", "to": "worker", "edge_type": "exec"},
    )
    graph = desktop_blueprint_service_module.graph_definition_from_dict(document["graph"])
    backend = DesktopBlueprintNoopBackend()
    runtime = desktop_blueprint_service_module.GraphRuntime(backend)
    control = desktop_blueprint_service_module.GraphRuntimeControlPlane(runtime, graph)
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    run = DesktopBlueprintRun(
        run_id="run-live-1",
        project_dir=project,
        blueprint_id="default",
        document=document,
        graph=graph,
        runtime=runtime,
        control=control,
        execution_mode="live",
        created_at=1.0,
        updated_at=1.0,
        backend=runtime.cluster,
        start_node_id="planner",
    )
    service._runs[run.run_id] = run

    try:
        queued = service.queue_agent_message(run.run_id, "planner", "hello", mode="top")

        assert queued["ok"] is True
        assert set(runtime.instances) == {"planner"}
        assert set(backend.worker_configs) == {"agent-planner"}
        body = runtime.agent_message_queues["planner"][0].body
        framework_context = body["context"]["framework_context"]
        assert framework_context["message_envelope"]["required_outgoing_targets"] == ["worker"]
        batch_id = framework_context["message_envelope"]["outgoing_batch_id"]
        batch = runtime.outgoing_batches[batch_id]
        assert batch.required_target_node_ids == ["worker"]
        assert batch.required_target_agent_ids == ["agent-worker"]
    finally:
        asyncio.run(runtime.close())


def test_queue_agent_message_includes_direct_feedback_script_call_context(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    document = _document(project)
    document["graph"]["script_nodes"] = {
        "table_queue_service": {
            "script_id": "table_queue_service.py:table_queue_service",
            "module_path": "table_queue_service.py",
            "function_name": "table_queue_service",
            "title": "table_queue_service",
            "description": "Call table_queue.",
            "inputs": [
                {"name": "action", "type": "str", "required": True},
                {"name": "arguments", "type": "dict", "required": True},
            ],
            "outputs": [{"name": "result", "type": "dict", "required": True}],
            "feedback_only": True,
        }
    }
    document["graph"]["edges"].append(
        {"from": "planner", "to": "table_queue_service", "edge_type": "exec"},
    )
    graph = desktop_blueprint_service_module.graph_definition_from_dict(document["graph"])
    runtime = desktop_blueprint_service_module.GraphRuntime(DesktopBlueprintNoopBackend())
    control = desktop_blueprint_service_module.GraphRuntimeControlPlane(runtime, graph)
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    run = DesktopBlueprintRun(
        run_id="run-live-1",
        project_dir=project,
        blueprint_id="default",
        document=document,
        graph=graph,
        runtime=runtime,
        control=control,
        execution_mode="live",
        created_at=1.0,
        updated_at=1.0,
        backend=runtime.cluster,
        start_node_id="planner",
    )
    service._runs[run.run_id] = run

    try:
        queued = service.queue_agent_message(run.run_id, "planner", "help", mode="top")

        assert queued["ok"] is True
        body = runtime.agent_message_queues["planner"][0].body
        envelope = body["context"]["framework_context"]["message_envelope"]
        assert envelope["required_outgoing_targets"] == []
        assert envelope["outgoing_batch_id"] in runtime.outgoing_batches
        script_call = envelope["required_script_calls"][0]
        assert script_call["script_node_id"] == "table_queue_service"
        assert script_call["function_name"] == "table_queue_service"
        batch = runtime.outgoing_batches[envelope["outgoing_batch_id"]]
        assert batch.required_target_node_ids == []
        assert batch.script_calls["table_queue_service"]["direct_call"] is True
    finally:
        asyncio.run(runtime.close())


def test_queue_agent_message_merges_same_session_pending_messages_fifo(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    document = _document(project)
    graph = desktop_blueprint_service_module.graph_definition_from_dict(document["graph"])
    runtime = desktop_blueprint_service_module.GraphRuntime(DesktopBlueprintNoopBackend())
    control = desktop_blueprint_service_module.GraphRuntimeControlPlane(runtime, graph)
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    run = DesktopBlueprintRun(
        run_id="run-live-1",
        project_dir=project,
        blueprint_id="default",
        document=document,
        graph=graph,
        runtime=runtime,
        control=control,
        execution_mode="live",
        created_at=1.0,
        updated_at=1.0,
        backend=runtime.cluster,
        start_node_id="planner",
    )
    service._runs[run.run_id] = run
    merge_key = "blueprint-session:bps_popo_user:planner"

    try:
        first = service.queue_agent_message(
            run.run_id,
            "planner",
            "first",
            mode="top",
            merge_key=merge_key,
            merge_append_text="first",
        )
        second = service.queue_agent_message(
            run.run_id,
            "planner",
            "second",
            mode="top",
            merge_key=merge_key,
            merge_append_text="second",
        )
        third = service.queue_agent_message(
            run.run_id,
            "planner",
            "third",
            mode="top",
            merge_key=merge_key,
            merge_append_text="third",
        )

        queue = runtime.agent_message_queues["planner"]
        assert len(queue) == 1
        pending = queue[0]
        assert first["result"]["message_id"] == second["result"]["message_id"] == third["result"]["message_id"]
        assert pending.merge_count == 3
        assert pending.merge_key == merge_key
        prompt = pending.body["prompt"]
        assert prompt.index("first") < prompt.index("second") < prompt.index("third")
    finally:
        asyncio.run(runtime.close())


def test_popo_config_without_project_dir_uses_registered_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)

    result = service.handle_request({"command": "blueprint.popo.config", "args": {"robotAppKey": "robot-1"}})

    assert result["ok"] is True
    assert result["projectDir"] == str(project.resolve())
    assert result["startNodeId"] == "planner"
    assert result["popoEntry"]["robot_app_key"] == "robot-1"


def test_popo_config_uses_start_agent_popo_entry(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    _enable_agent_popo(document, "planner", "robot-agent")
    saved = service.save_blueprint(project, document)

    result = service.handle_request({"command": "blueprint.popo.config", "args": {"robotAppKey": "robot-agent"}})

    assert saved["runtime"]["popo_entry"]["enabled"] is False
    assert saved["graph"]["agent_nodes"]["planner"]["popo_entry"]["robot_app_key"] == "robot-agent"
    assert result["ok"] is True
    assert result["robotAppKey"] == "robot-agent"
    assert result["startNodeId"] == "planner"
    assert result["popoEntry"]["robot_app_key"] == "robot-agent"


def test_popo_config_without_robot_key_uses_single_registered_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime(robot_app_key="robot-legacy")
    service.save_blueprint(project, document)

    result = service.handle_request({"command": "blueprint.popo.config", "args": {}})

    assert result["ok"] is True
    assert result["robotAppKey"] == "robot-legacy"
    assert result["projectDir"] == str(project.resolve())
    assert result["popoEntry"]["robot_app_key"] == "robot-legacy"


def test_popo_robot_routes_persist_and_toggle(tmp_path: Path) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")

    saved = service.handle_request(
        {
            "command": "blueprint.popo.robot.save",
            "args": {"robot": {"enabled": False, "robot_app_key": "robot-1", "robot_name": "Relu"}},
        }
    )

    assert saved["ok"] is True
    assert saved["robots"][0]["robot_app_key"] == "robot-1"
    assert saved["robots"][0]["enabled"] is False
    assert service.popo_robot_routes_path().is_file()

    reloaded = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    listed = reloaded.handle_request({"command": "blueprint.popo.robots", "args": {}})
    assert listed["robots"][0]["robot_name"] == "Relu"

    with pytest.raises(BlueprintServiceError) as incomplete:
        reloaded.handle_request(
            {
                "command": "blueprint.popo.robot.enabled",
                "args": {"robotAppKey": "robot-1", "enabled": True},
            }
        )
    assert incomplete.value.code == "BLUEPRINT_POPO_ENTRY_REQUIRED"

    robot = _popo_entry("robot-1")
    robot["enabled"] = False
    robot["robot_name"] = "Relu"
    reloaded.handle_request(
        {
            "command": "blueprint.popo.robot.save",
            "args": {"robot": robot},
        }
    )
    toggled = reloaded.handle_request(
        {
            "command": "blueprint.popo.robot.enabled",
            "args": {"robotAppKey": "robot-1", "enabled": True},
        }
    )
    assert toggled["robot"]["enabled"] is True

    deleted = reloaded.handle_request(
        {
            "command": "blueprint.popo.robot.delete",
            "args": {"robotAppKey": "robot-1"},
        }
    )
    assert deleted["deleted"] is True
    assert deleted["robots"] == []


def test_popo_callback_config_requires_enabled_global_robot(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime(robot_app_key="robot-1")
    service.save_blueprint(project, document)

    with pytest.raises(BlueprintServiceError) as missing:
        service.handle_request({"command": "blueprint.popo.callbackConfig", "args": {"robotAppKey": "robot-1"}})
    assert missing.value.code == "BLUEPRINT_POPO_ROBOT_NOT_BOUND"

    robot = _popo_entry("robot-1")
    robot["enabled"] = False
    service.handle_request({"command": "blueprint.popo.robot.save", "args": {"robot": robot}})

    with pytest.raises(BlueprintServiceError) as disabled:
        service.handle_request({"command": "blueprint.popo.callbackConfig", "args": {"robotAppKey": "robot-1"}})
    assert disabled.value.code == "BLUEPRINT_POPO_ROBOT_DISABLED"


def test_popo_callback_config_uses_global_robot_credentials_and_blueprint_binding(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime(robot_app_key="robot-1")
    service.save_blueprint(project, document)
    robot = _popo_entry("robot-1")
    robot.update(
        {
            "robot_name": "Global Relu",
            "robot_app_secret": "global-secret",
            "callback_token": "global-token",
            "aes_key": "abcdef0123456789abcdef0123456789",
        }
    )
    service.handle_request({"command": "blueprint.popo.robot.save", "args": {"robot": robot}})

    result = service.handle_request({"command": "blueprint.popo.callbackConfig", "args": {"robotAppKey": "robot-1"}})
    legacy = service.handle_request({"command": "blueprint.popo.callbackConfig", "args": {}})

    assert result["ok"] is True
    assert result["robotAppKey"] == "robot-1"
    assert result["projectDir"] == str(project.resolve())
    assert result["startNodeId"] == "planner"
    assert result["popoEntry"]["robot_app_secret"] == "global-secret"
    assert result["popoEntry"]["callback_token"] == "global-token"
    assert result["popoEntry"]["aes_key"] == "abcdef0123456789abcdef0123456789"
    assert result["blueprintPopoEntry"]["robot_app_secret"] == "secret"
    assert legacy["robotAppKey"] == "robot-1"


def test_popo_callback_config_legacy_conflicts_on_multiple_enabled_global_robots(tmp_path: Path) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    for robot_app_key in ("robot-1", "robot-2"):
        service.handle_request(
            {
                "command": "blueprint.popo.robot.save",
                "args": {"robot": _popo_entry(robot_app_key)},
            }
        )

    with pytest.raises(BlueprintServiceError) as exc:
        service.handle_request({"command": "blueprint.popo.callbackConfig", "args": {}})

    assert exc.value.code == "BLUEPRINT_POPO_ROBOT_STRUCTURE_CONFLICT"
    assert exc.value.status == 409


def test_popo_session_message_without_project_dir_routes_to_registered_blueprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    _patch_fake_session_instances(monkeypatch, service)
    queued: list[tuple[str, str, str, str]] = []

    monkeypatch.setattr(service, "_run_is_active", lambda run: True)
    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda run, graph=None: {"run": {"runId": run.run_id, "status": "running"}, "recent_events": []},
    )

    def fake_queue(run_id, node_id, text, *, mode="default", **kwargs):
        queued.append((run_id, node_id, text, mode))
        return {"ok": True}

    monkeypatch.setattr(service, "queue_agent_message", fake_queue)

    result = service.handle_request(
        {
            "command": "blueprint.sessions.message",
            "args": {
                "message": "hello from popo",
                "source": "popo",
                "sourceIdentity": {"robotAppKey": "robot-1"},
                "sessionIdentity": {
                    "popoUserId": "u1",
                    "popoSessionId": "s1",
                    "popoReplyTo": "reply-u1",
                    "popoSessionType": "1",
                },
            },
        }
    )

    assert result["ok"] is True
    assert result["runId"] == "run-session-1"
    assert result["sessionKey"] == "bps_popo_u1+default-blueprint"
    assert result["session"]["sessionDisplayName"] == "POPO u1"
    assert result["session"]["popoReplyTo"] == "reply-u1"
    assert result["session"]["popoSessionType"] == "1"
    assert queued[-1][0:2] == ("run-session-1", "planner")
    assert queued[-1][3] == "top"
    assert "hello from popo" in queued[-1][2]


def test_blueprint_open_records_current_blueprint_without_internal_open(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    service.save_blueprint(project, _popo_document(project, blueprint_id="alpha", name="Alpha", prompt="Plan alpha."))
    service.save_blueprint(project, _popo_document(project, blueprint_id="beta", name="Beta", prompt="Plan beta."))

    assert service.open_blueprint(project, "alpha")["id"] == "alpha"
    registered_after_internal_open = service.list_registered_blueprint_projects()
    assert registered_after_internal_open[0]["lastOpenedBlueprintId"] == ""

    opened = service.handle_request(
        {"command": "blueprint.open", "args": {"projectDir": str(project), "blueprintId": "beta"}}
    )
    registered_after_workbench_open = service.list_registered_blueprint_projects()

    assert opened["document"]["id"] == "beta"
    assert registered_after_workbench_open[0]["lastOpenedBlueprintId"] == "beta"
    assert registered_after_workbench_open[0]["lastOpenedBlueprintName"] == "Beta"
    assert registered_after_workbench_open[0]["lastOpenedAt"] > 0


def test_popo_global_message_conflicts_when_multiple_candidates_have_no_current_blueprint(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    service.save_blueprint(project, _popo_document(project, blueprint_id="alpha", name="Alpha", prompt="Plan alpha."))
    service.save_blueprint(project, _popo_document(project, blueprint_id="beta", name="Beta", prompt="Plan beta."))

    with pytest.raises(BlueprintServiceError) as exc:
        service.handle_request(
            {
                "command": "blueprint.sessions.message",
                "args": {
                    "message": "hello from popo",
                    "source": "popo",
                    "sourceIdentity": {"robotAppKey": "robot-1"},
                    "sessionIdentity": {"popoUserId": "u1", "popoSessionId": "s1"},
                },
            }
        )

    assert exc.value.code == "BLUEPRINT_POPO_ROBOT_STRUCTURE_CONFLICT"
    assert exc.value.details["selectionReason"] == "no_current_blueprint"


def test_popo_global_message_uses_current_blueprint_when_multiple_candidates_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    service.save_blueprint(project, _popo_document(project, blueprint_id="alpha", name="Alpha", prompt="Plan alpha."))
    service.save_blueprint(project, _popo_document(project, blueprint_id="beta", name="Beta", prompt="Plan beta."))
    service.handle_request({"command": "blueprint.open", "args": {"projectDir": str(project), "blueprintId": "beta"}})
    _patch_fake_session_instances(monkeypatch, service)

    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda run, graph=None: {"run": {"runId": run.run_id, "status": "running"}, "recent_events": []},
    )
    monkeypatch.setattr(service, "queue_agent_message", lambda run_id, node_id, text, *, mode="default", **kwargs: {"ok": True})

    result = service.handle_request(
        {
            "command": "blueprint.sessions.message",
            "args": {
                "message": "hello from popo",
                "source": "popo",
                "sourceIdentity": {"robotAppKey": "robot-1"},
                "sessionIdentity": {"popoUserId": "u2", "popoSessionId": "s2"},
            },
        }
    )

    assert result["runId"] == "run-session-1"
    assert result["session"]["blueprintId"] == "beta"


def test_popo_global_binding_falls_back_to_current_blueprint_when_no_existing_session(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    service.save_blueprint(project, _popo_document(project, blueprint_id="alpha", name="Alpha", prompt="Plan alpha."))
    service.save_blueprint(project, _popo_document(project, blueprint_id="beta", name="Beta", prompt="Plan beta."))
    service.handle_request({"command": "blueprint.open", "args": {"projectDir": str(project), "blueprintId": "beta"}})

    binding = service._find_global_popo_blueprint_binding("robot-1")

    assert binding["blueprintId"] == "beta"


def test_popo_existing_session_wins_over_current_blueprint_fallback(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    service.save_blueprint(project, _popo_document(project, blueprint_id="alpha", name="Alpha", prompt="Plan alpha."))
    service.save_blueprint(project, _popo_document(project, blueprint_id="beta", name="Beta", prompt="Plan beta."))
    service.handle_request({"command": "blueprint.open", "args": {"projectDir": str(project), "blueprintId": "beta"}})
    alpha_preflight = service._blueprint_session_preflight(project, "alpha", require_popo=False)
    alpha_pool = desktop_blueprint_service_module.blueprint_slot_pool_key(
        project_dir=project,
        source="popo",
        source_binding="robot-1",
        blueprint_structure_id=str(alpha_preflight["blueprintStructureId"]),
    )
    session_key = blueprint_session_key_for_pool(
        pool_key=alpha_pool,
        source="popo",
        popo_user_id="u3",
        popo_session_id="s3",
    )
    service._save_blueprint_session(
        {
            "sessionKey": session_key,
            "projectDir": str(project.resolve()),
            "poolKey": alpha_pool,
            "robotAppKey": "robot-1",
            "blueprintId": "alpha",
            "blueprintName": "Alpha",
            "blueprintStructureId": str(alpha_preflight["blueprintStructureId"]),
            "source": "popo",
            "popoUserId": "u3",
            "popoSessionId": "s3",
            "popoGroupId": "",
            "status": "idle",
            "createdAt": 1.0,
            "lastTouchedAt": 2.0,
            "deleted": False,
        }
    )

    binding = service._find_global_popo_blueprint_binding(
        "robot-1",
        session_identity={"popoUserId": "u3", "popoSessionId": "s3"},
    )

    assert binding["blueprintId"] == "alpha"


def test_popo_current_blueprint_must_be_candidate_binding(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    service.save_blueprint(project, _popo_document(project, blueprint_id="alpha", name="Alpha", prompt="Plan alpha."))
    service.save_blueprint(project, _popo_document(project, blueprint_id="gamma", name="Gamma", prompt="Plan gamma."))
    service.save_blueprint(
        project,
        _popo_document(project, blueprint_id="beta", name="Beta", prompt="Plan beta.", robot_app_key="robot-2"),
    )
    service.handle_request({"command": "blueprint.open", "args": {"projectDir": str(project), "blueprintId": "beta"}})

    with pytest.raises(BlueprintServiceError) as exc:
        service._find_global_popo_blueprint_binding("robot-1")

    assert exc.value.code == "BLUEPRINT_POPO_ROBOT_STRUCTURE_CONFLICT"
    assert exc.value.details["selectionReason"] == "no_current_blueprint"


def test_popo_robot_can_bind_multiple_structures(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    service.save_blueprint(project, _popo_document(project, blueprint_id="alpha", name="Alpha", prompt="Plan alpha."))
    service.save_blueprint(project, _popo_document(project, blueprint_id="beta", name="Beta", prompt="Plan beta."))
    bindings = service._collect_popo_blueprint_bindings(project, "robot-1")

    assert {binding["blueprintId"] for binding in bindings} == {"alpha", "beta"}


def test_popo_private_session_key_contains_user_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    _patch_fake_session_instances(monkeypatch, service)

    monkeypatch.setattr(service, "_run_is_active", lambda run: True)
    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda run, graph=None: {"run": {"runId": run.run_id, "status": "running"}, "recent_events": []},
    )
    monkeypatch.setattr(service, "queue_agent_message", lambda run_id, node_id, text, *, mode="default", **kwargs: {"ok": True})

    result = service.message_blueprint_session(
        project,
        "default",
        "hello",
        source="popo",
        popo_user_id="qiuhaoxuan",
        popo_session_id="p2p-session-1",
        session_identity={"popoReplyTo": "qiuhaoxuan", "popoSessionType": "1"},
    )

    assert result["sessionKey"].startswith("bps_popo_qiuhaoxuan+")
    assert result["sessionKey"].endswith("+default-blueprint")
    assert result["session"]["sessionDisplayName"] == "POPO qiuhaoxuan"
    session_path = service.blueprint_sessions_dir() / result["sessionKey"] / "session.json"
    assert session_path.is_file()


def test_popo_session_key_uses_blueprint_name_when_structure_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    _patch_fake_session_instances(monkeypatch, service)
    monkeypatch.setattr(service, "_run_is_active", lambda run: True)
    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda run, graph=None: {"run": {"runId": run.run_id, "status": "running"}, "recent_events": []},
    )
    monkeypatch.setattr(service, "queue_agent_message", lambda run_id, node_id, text, *, mode="default", **kwargs: {"ok": True})

    first = service.message_blueprint_session(
        project,
        "default",
        "first",
        source="popo",
        popo_user_id="qiuhaoxuan",
        popo_session_id="p2p-session-1",
    )
    changed = service.open_blueprint(project, "default")
    changed["graph"]["agent_nodes"]["planner"]["prompt"] = "Changed structure."
    service.save_blueprint(project, changed)
    second = service.message_blueprint_session(
        project,
        "default",
        "second",
        source="popo",
        popo_user_id="qiuhaoxuan",
        popo_session_id="p2p-session-1",
    )

    expected_key = blueprint_popo_named_session_key(
        blueprint_name="Default Blueprint",
        blueprint_id="default",
        popo_user_id="qiuhaoxuan",
        popo_session_id="p2p-session-1",
    )
    assert first["sessionKey"] == second["sessionKey"] == expected_key
    assert first["session"]["blueprintStructureId"] != second["session"]["blueprintStructureId"]


def test_restart_blueprint_sessions_supersedes_and_hides_blueprint_name_family(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    runs = _patch_fake_session_instances(monkeypatch, service)
    monkeypatch.setattr(service, "_run_is_active", lambda run: True)
    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda run, graph=None: {"run": {"runId": run.run_id, "status": "running"}, "recent_events": []},
    )
    monkeypatch.setattr(service, "queue_agent_message", lambda run_id, node_id, text, *, mode="default", **kwargs: {"ok": True})

    def fake_close(run_id: str, *, reason: str = "") -> str:
        runs_by_id = {run.run_id: run for run in runs}
        run = runs_by_id.get(run_id)
        if run is not None:
            run.session_key = ""
            run.bound_session_key = ""
        return ""

    monkeypatch.setattr(service, "_close_blueprint_session_run_best_effort", fake_close)

    started = service.message_blueprint_session(
        project,
        "default",
        "start",
        source="popo",
        popo_user_id="qiuhaoxuan",
        popo_session_id="p2p-session-1",
    )
    legacy_key = "bps_popo_qiuhaoxuan_000000000000000000000001"
    service._save_blueprint_session(
        {
            "sessionKey": legacy_key,
            "projectDir": str(project.resolve()),
            "robotAppKey": "robot-1",
            "blueprintId": "default",
            "blueprintName": "Default Blueprint",
            "blueprintStructureId": "old-structure",
            "source": "popo",
            "popoUserId": "qiuhaoxuan",
            "popoSessionId": "old-session",
            "popoGroupId": "",
            "status": "idle",
            "activeRunId": "",
            "createdAt": 1.0,
            "lastTouchedAt": 2.0,
            "deleted": False,
        }
    )

    result = service.handle_request(
        {
            "command": "blueprint.sessions.restartBlueprint",
            "args": {
                "projectDir": str(project),
                "blueprintId": "default",
                "reason": "test restart",
            },
        }
    )

    assert result["ok"] is True
    assert result["terminatedRunIds"] == ["run-session-1"]
    assert legacy_key in result["supersededSessionKeys"]
    archived_started_key = next(
        key for key in result["supersededSessionKeys"] if key.startswith(started["sessionKey"] + "-superseded-")
    )
    assert service._load_blueprint_session(started["sessionKey"]) is None
    archived_session = service._load_blueprint_session(archived_started_key)
    assert archived_session["superseded"] is True
    assert archived_session["status"] == "superseded"
    assert "start" in service._blueprint_session_transcript_path(archived_started_key).read_text(encoding="utf-8")
    assert service._load_blueprint_session(legacy_key)["superseded"] is True
    assert service.list_blueprint_sessions(project, "default") == []

    next_message = service.message_blueprint_session(
        project,
        "default",
        "after restart",
        source="popo",
        popo_user_id="qiuhaoxuan",
        popo_session_id="p2p-session-1",
    )

    assert next_message["sessionKey"] == started["sessionKey"]
    assert next_message["runId"] == "run-session-2"


def test_popo_legacy_hash_session_key_migrates_to_readable_user_key(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    pool_key = "pool-1"
    legacy_key = blueprint_legacy_session_key_for_pool(
        pool_key=pool_key,
        source="popo",
        popo_user_id="qiuhaoxuan",
        popo_session_id="p2p-session-1",
    )
    readable_key = blueprint_session_key_for_pool(
        pool_key=pool_key,
        source="popo",
        popo_user_id="qiuhaoxuan",
        popo_session_id="p2p-session-1",
    )
    named_key = blueprint_popo_named_session_key(
        blueprint_name="Default Blueprint",
        blueprint_id="default",
        popo_user_id="qiuhaoxuan",
        popo_session_id="p2p-session-1",
    )
    service._save_blueprint_session(
        {
            "sessionKey": legacy_key,
            "projectDir": str(project.resolve()),
            "poolKey": pool_key,
            "robotAppKey": "robot-1",
            "blueprintId": "default",
            "blueprintName": "Default Blueprint",
            "blueprintStructureId": "structure-1",
            "source": "popo",
            "popoUserId": "qiuhaoxuan",
            "popoSessionId": "p2p-session-1",
            "popoGroupId": "",
            "status": "idle",
            "createdAt": 1.0,
            "lastTouchedAt": 2.0,
            "deleted": False,
        }
    )

    sessions = service.list_blueprint_sessions(project, "default")

    assert sessions[0]["sessionKey"] == named_key
    assert sessions[0]["sessionDisplayName"] == "POPO qiuhaoxuan"
    assert (service.blueprint_sessions_dir() / named_key / "session.json").is_file()
    assert not (service.blueprint_sessions_dir() / readable_key).exists()
    assert not (service.blueprint_sessions_dir() / legacy_key).exists()


def test_atomic_write_json_uses_unique_temp_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    path = tmp_path / "state" / "session.json"
    sources: list[str] = []
    original_replace = Path.replace

    def spy_replace(self: Path, target: Path) -> Path:
        sources.append(self.name)
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", spy_replace)

    service._atomic_write_json(path, {"value": 1})
    service._atomic_write_json(path, {"value": 2})

    assert len(sources) == 2
    assert len(set(sources)) == 2
    assert all(not name.endswith(f".{os.getpid()}.tmp") for name in sources)
    assert json.loads(path.read_text(encoding="utf-8")) == {"value": 2}


def test_send_popo_message_prefers_streaming_card_and_reuses_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    fixed_uuid = desktop_blueprint_service_module.uuid.UUID("12345678-1234-5678-1234-567812345678")
    monkeypatch.setattr(desktop_blueprint_service_module.uuid, "uuid4", lambda: fixed_uuid)
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None, timeout: int) -> _FakeHTTPResponse:
        calls.append({"method": "POST", "url": url, "json": json, "headers": headers, "timeout": timeout})
        if url.endswith("/open-apis/robots/v1/token"):
            return _FakeHTTPResponse(
                {
                    "errcode": 0,
                    "data": {
                        "accessToken": "access-token-1",
                        "accessExpiredAt": int(time.time() * 1000) + 900000,
                    },
                }
            )
        return _FakeHTTPResponse({"errcode": 0})

    def fake_put(url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None, timeout: int) -> _FakeHTTPResponse:
        calls.append({"method": "PUT", "url": url, "json": json, "headers": headers, "timeout": timeout})
        return _FakeHTTPResponse({"errcode": 0})

    monkeypatch.setattr(desktop_blueprint_service_module.requests, "post", fake_post)
    monkeypatch.setattr(desktop_blueprint_service_module.requests, "put", fake_put)

    result = service._send_popo_message(
        receiver="qiuhaoxuan@corp.netease.com",
        content="最终回复",
        robot_config={"robot_app_key": "robot-1", "robot_app_secret": "secret-1"},
    )
    second = service._send_popo_message(
        receiver="qiuhaoxuan@corp.netease.com",
        content="第二条",
        robot_config={"robot_app_key": "robot-1", "robot_app_secret": "secret-1"},
    )

    assert result == {
        "ok": True,
        "sent": True,
        "errcode": 0,
        "transport": "streaming_card",
        "messageId": "12345678-1234-5678-1234-567812345678",
    }
    assert second["transport"] == "streaming_card"
    token_calls = [call for call in calls if call["url"].endswith("/open-apis/robots/v1/token")]
    assert len(token_calls) == 1
    card_posts = [call for call in calls if call["method"] == "POST" and call["json"].get("msgType") == "card"]
    assert len(card_posts) == 2
    first_card = card_posts[0]
    assert first_card["headers"]["Open-Access-Token"] == "access-token-1"
    assert first_card["json"]["receiver"] == "qiuhaoxuan@corp.netease.com"
    assert first_card["json"]["message"]["instanceUuid"] == "12345678-1234-5678-1234-567812345678"
    assert first_card["json"]["message"]["templateUuid"] == "series_5564199"
    assert first_card["json"]["message"]["options"]["lastMessage"] == "AI正在回复..."
    assert first_card["json"]["message"]["options"]["compatibleMessage"] == "最终回复"
    text_posts = [call for call in calls if call["method"] == "POST" and call["json"].get("msgType") == "text"]
    assert text_posts == []
    updates = [call for call in calls if call["method"] == "PUT"]
    assert updates[0]["url"].endswith("/open-apis/robots/v1/im/msg-card/stream")
    assert updates[0]["headers"]["Open-Access-Token"] == "access-token-1"
    assert updates[0]["json"] == {
        "instanceUuid": "12345678-1234-5678-1234-567812345678",
        "templateUuid": "series_5564199",
        "key": "resultStream",
        "content": "最终回复",
        "sequence": 1,
        "isFinalize": True,
    }


def test_send_popo_message_falls_back_to_text_when_streaming_card_init_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None, timeout: int) -> _FakeHTTPResponse:
        calls.append({"method": "POST", "url": url, "json": json, "headers": headers, "timeout": timeout})
        if url.endswith("/open-apis/robots/v1/token"):
            return _FakeHTTPResponse(
                {
                    "errcode": 0,
                    "data": {
                        "accessToken": "access-token-1",
                        "accessExpiredAt": int(time.time() * 1000) + 900000,
                    },
                }
            )
        if json.get("msgType") == "card":
            return _FakeHTTPResponse({"errcode": 4001, "errmsg": "card disabled"})
        return _FakeHTTPResponse({"errcode": 0})

    def fake_put(*args: Any, **kwargs: Any) -> _FakeHTTPResponse:
        raise AssertionError("streaming card update should not be called when init fails")

    monkeypatch.setattr(desktop_blueprint_service_module.requests, "post", fake_post)
    monkeypatch.setattr(desktop_blueprint_service_module.requests, "put", fake_put)

    result = service._send_popo_message(
        receiver="qiuhaoxuan@corp.netease.com",
        content="fallback reply",
        robot_config={"robot_app_key": "robot-1", "robot_app_secret": "secret-1"},
    )

    assert result["transport"] == "text_fallback"
    assert result["sent"] is True
    assert "errcode=4001" in result["fallbackReason"]
    send_posts = [call for call in calls if call["url"].endswith("/open-apis/robots/v1/im/send-msg")]
    assert [call["json"]["msgType"] for call in send_posts] == ["card", "text"]
    assert send_posts[-1]["json"]["message"]["content"] == "fallback reply"


def test_send_popo_message_falls_back_to_text_when_streaming_card_update_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None, timeout: int) -> _FakeHTTPResponse:
        calls.append({"method": "POST", "url": url, "json": json, "headers": headers, "timeout": timeout})
        if url.endswith("/open-apis/robots/v1/token"):
            return _FakeHTTPResponse(
                {
                    "errcode": 0,
                    "data": {
                        "accessToken": "access-token-1",
                        "accessExpiredAt": int(time.time() * 1000) + 900000,
                    },
                }
            )
        return _FakeHTTPResponse({"errcode": 0})

    def fake_put(url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None, timeout: int) -> _FakeHTTPResponse:
        calls.append({"method": "PUT", "url": url, "json": json, "headers": headers, "timeout": timeout})
        return _FakeHTTPResponse({"errcode": 4002, "errmsg": "stream rejected"})

    monkeypatch.setattr(desktop_blueprint_service_module.requests, "post", fake_post)
    monkeypatch.setattr(desktop_blueprint_service_module.requests, "put", fake_put)

    result = service._send_popo_message(
        receiver="qiuhaoxuan@corp.netease.com",
        content="fallback after update",
        robot_config={"robot_app_key": "robot-1", "robot_app_secret": "secret-1"},
    )

    assert result["transport"] == "text_fallback"
    assert result["sent"] is True
    assert "errcode=4002" in result["fallbackReason"]
    send_posts = [call for call in calls if call["method"] == "POST" and call["url"].endswith("/open-apis/robots/v1/im/send-msg")]
    assert [call["json"]["msgType"] for call in send_posts] == ["card", "text"]
    assert [call["method"] for call in calls].count("PUT") == 1


def test_popo_progress_card_streams_thinking_status_and_finalizes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    service.save_popo_robot(_popo_entry("robot-1"))
    fixed_uuid = desktop_blueprint_service_module.uuid.UUID("12345678-1234-5678-1234-567812345678")
    monkeypatch.setattr(desktop_blueprint_service_module.uuid, "uuid4", lambda: fixed_uuid)
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None, timeout: int) -> _FakeHTTPResponse:
        calls.append({"method": "POST", "url": url, "json": json, "headers": headers, "timeout": timeout})
        if url.endswith("/open-apis/robots/v1/token"):
            return _FakeHTTPResponse(
                {
                    "errcode": 0,
                    "data": {
                        "accessToken": "access-token-1",
                        "accessExpiredAt": int(time.time() * 1000) + 900000,
                    },
                }
            )
        if url.endswith("/open-apis/robots/v1/im/send-msg") and json.get("msgType") == "card":
            return _FakeHTTPResponse({"errcode": 0, "data": {"msgInfo": {"reply-u1": "popo-msg-1"}}})
        return _FakeHTTPResponse({"errcode": 0})

    def fake_put(url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None, timeout: int) -> _FakeHTTPResponse:
        calls.append({"method": "PUT", "url": url, "json": json, "headers": headers, "timeout": timeout})
        return _FakeHTTPResponse({"errcode": 0})

    monkeypatch.setattr(desktop_blueprint_service_module.requests, "post", fake_post)
    monkeypatch.setattr(desktop_blueprint_service_module.requests, "put", fake_put)

    runtime = SimpleNamespace(popo_reply_session_key="main+default")
    run = DesktopBlueprintRun(
        run_id="run-1",
        project_dir=tmp_path / "project",
        blueprint_id="default",
        document=_document(tmp_path / "project"),
        graph=object(),
        runtime=runtime,
        control=object(),
        execution_mode="live",
        created_at=1.0,
        updated_at=1.0,
        session_key="main+default",
        start_node_id="planner",
        robot_app_key="robot-1",
    )
    session = {
        "sessionKey": "session-1",
        "source": "popo",
        "robotAppKey": "robot-1",
        "popoReplyTo": "reply-u1",
    }

    begin = service._begin_popo_progress_card_for_session(run, session)
    service._update_popo_progress_from_stream_event(
        "run-1",
        {"kind": "tool.started", "tool_name": "shell_command", "tool_input": "rg TODO desktop_blueprint_service.py"},
    )
    final = service._finalize_popo_progress_for_run(
        "run-1",
        session_key="session-1",
        content="final answer",
    )

    assert begin is not None
    assert begin["transport"] == "streaming_card_progress"
    assert final is not None
    assert final["transport"] == "streaming_card_progress_recall"
    token_calls = [call for call in calls if call["url"].endswith("/open-apis/robots/v1/token")]
    assert len(token_calls) == 1
    card_posts = [call for call in calls if call["method"] == "POST" and call["json"].get("msgType") == "card"]
    assert len(card_posts) == 1
    assert card_posts[0]["json"]["message"]["instanceUuid"] == "12345678-1234-5678-1234-567812345678"
    assert card_posts[0]["json"]["message"]["options"]["lastMessage"] == desktop_blueprint_service_module.POPO_PROGRESS_THINKING_TEXT
    assert card_posts[0]["json"]["message"]["options"]["compatibleMessage"] == desktop_blueprint_service_module.POPO_PROGRESS_THINKING_TEXT
    updates = [call for call in calls if call["method"] == "PUT"]
    assert [call["json"]["sequence"] for call in updates] == [1, 2]
    assert updates[0]["json"]["content"] == desktop_blueprint_service_module.POPO_PROGRESS_THINKING_TEXT
    assert updates[0]["json"]["isFinalize"] is False
    assert updates[1]["json"]["content"] == "\n正在搜索代码..."
    assert updates[1]["json"]["isFinalize"] is False
    recalls = [call for call in calls if call["method"] == "POST" and call["url"].endswith("/popo-msg-1/recall")]
    assert recalls == [
        {
            "method": "POST",
            "url": "https://open.popo.netease.com/open-apis/robots/v1/im/popo-msg-1/recall",
            "json": {"sessionId": "reply-u1", "sessionType": 1},
            "headers": {"Content-Type": "application/json", "Open-Access-Token": "access-token-1"},
            "timeout": 10,
        }
    ]
    assert "run-1" not in service._popo_progress_cards


def test_popo_progress_card_appends_visible_agent_delta(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    service.save_popo_robot(_popo_entry("robot-1"))
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None, timeout: int) -> _FakeHTTPResponse:
        calls.append({"method": "POST", "url": url, "json": json, "headers": headers, "timeout": timeout})
        if url.endswith("/open-apis/robots/v1/token"):
            return _FakeHTTPResponse(
                {
                    "errcode": 0,
                    "data": {
                        "accessToken": "access-token-1",
                        "accessExpiredAt": int(time.time() * 1000) + 900000,
                    },
                }
            )
        if url.endswith("/open-apis/robots/v1/im/send-msg") and json.get("msgType") == "card":
            return _FakeHTTPResponse({"errcode": 0, "data": {"msgInfo": {"reply-u1": "popo-msg-1"}}})
        return _FakeHTTPResponse({"errcode": 0})

    def fake_put(url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None, timeout: int) -> _FakeHTTPResponse:
        calls.append({"method": "PUT", "url": url, "json": json, "headers": headers, "timeout": timeout})
        return _FakeHTTPResponse({"errcode": 0})

    monkeypatch.setattr(desktop_blueprint_service_module.requests, "post", fake_post)
    monkeypatch.setattr(desktop_blueprint_service_module.requests, "put", fake_put)

    run = DesktopBlueprintRun(
        run_id="run-1",
        project_dir=tmp_path / "project",
        blueprint_id="default",
        document=_document(tmp_path / "project"),
        graph=object(),
        runtime=SimpleNamespace(popo_reply_session_key="session-1"),
        control=object(),
        execution_mode="live",
        created_at=1.0,
        updated_at=1.0,
        session_key="session-1",
        start_node_id="planner",
        robot_app_key="robot-1",
    )
    session = {
        "sessionKey": "session-1",
        "source": "popo",
        "robotAppKey": "robot-1",
        "popoReplyTo": "reply-u1",
    }

    assert service._begin_popo_progress_card_for_session(run, session) is not None
    service._popo_progress_cards["run-1"].last_update_at = 0
    service._update_popo_progress_from_stream_event(
        "run-1",
        {
            "kind": "part.delta",
            "part_type": "text",
            "delta": "第二行已写入。继续最后一行，然后统一回读校验。",
        },
    )
    service._update_popo_progress_from_stream_event(
        "run-1",
        {
            "kind": "part.delta",
            "part_type": "reasoning",
            "delta": "internal reasoning should not be shown",
        },
    )
    service._update_popo_progress_from_stream_event(
        "run-1",
        {
            "kind": "part.delta",
            "part_type": "stderr",
            "delta": '2026-06-15 WARN codex_core_plugins::loader: failed to load plugin: plugin is not installed',
        },
    )

    updates = [call for call in calls if call["method"] == "PUT"]
    assert updates[-1]["json"]["content"] == "\n\nAgent 回复\n第二行已写入。继续最后一行，然后统一回读校验。"
    streamed_content = "".join(call["json"]["content"] for call in updates)
    assert "internal reasoning" not in streamed_content
    assert "codex_core_plugins::loader" not in streamed_content


def test_popo_progress_card_update_failure_is_recalled_on_final_reply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    service.save_popo_robot(_popo_entry("robot-1"))
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None, timeout: int) -> _FakeHTTPResponse:
        calls.append({"method": "POST", "url": url, "json": json, "headers": headers, "timeout": timeout})
        if url.endswith("/open-apis/robots/v1/token"):
            return _FakeHTTPResponse(
                {
                    "errcode": 0,
                    "data": {
                        "accessToken": "access-token-1",
                        "accessExpiredAt": int(time.time() * 1000) + 900000,
                    },
                }
            )
        if url.endswith("/open-apis/robots/v1/im/send-msg") and json.get("msgType") == "card":
            return _FakeHTTPResponse({"errcode": 0, "data": {"msgInfo": {"reply-u1": "popo-msg-1"}}})
        return _FakeHTTPResponse({"errcode": 0})

    def fake_put(url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None, timeout: int) -> _FakeHTTPResponse:
        calls.append({"method": "PUT", "url": url, "json": json, "headers": headers, "timeout": timeout})
        return _FakeHTTPResponse({"errcode": 4002, "errmsg": "stream rejected"})

    monkeypatch.setattr(desktop_blueprint_service_module.requests, "post", fake_post)
    monkeypatch.setattr(desktop_blueprint_service_module.requests, "put", fake_put)

    runtime = SimpleNamespace(popo_reply_session_key="main+default")
    run = DesktopBlueprintRun(
        run_id="run-1",
        project_dir=tmp_path / "project",
        blueprint_id="default",
        document=_document(tmp_path / "project"),
        graph=object(),
        runtime=runtime,
        control=object(),
        execution_mode="live",
        created_at=1.0,
        updated_at=1.0,
        session_key="main+default",
        start_node_id="planner",
        robot_app_key="robot-1",
    )
    session = {
        "sessionKey": "session-1",
        "source": "popo",
        "robotAppKey": "robot-1",
        "popoReplyTo": "reply-u1",
    }

    begin = service._begin_popo_progress_card_for_session(run, session)
    card = service._popo_progress_cards["run-1"]
    assert begin is not None
    assert card.failed is True

    final = service._finalize_popo_progress_for_run(
        "run-1",
        session_key="session-1",
        content="final answer",
    )

    assert final is not None
    assert final["transport"] == "streaming_card_progress_recall"
    recalls = [call for call in calls if call["method"] == "POST" and call["url"].endswith("/popo-msg-1/recall")]
    assert recalls == [
        {
            "method": "POST",
            "url": "https://open.popo.netease.com/open-apis/robots/v1/im/popo-msg-1/recall",
            "json": {"sessionId": "reply-u1", "sessionType": 1},
            "headers": {"Content-Type": "application/json", "Open-Access-Token": "access-token-1"},
            "timeout": 10,
        }
    ]
    assert "run-1" not in service._popo_progress_cards


def test_popo_progress_event_mapper_uses_generic_non_leaky_statuses(tmp_path: Path) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")

    assert service._popo_progress_line_from_agent_stream_event({"kind": "part.delta", "text": "secret answer"}) == ""
    assert service._popo_progress_line_from_agent_stream_event({"kind": "message.completed", "text": "final"}) == ""
    assert service._popo_progress_line_from_agent_stream_event({"kind": "message.started"}) == "正在处理消息..."
    assert (
        service._popo_progress_line_from_agent_stream_event(
            {"kind": "tool.started", "tool_name": "shell_command", "tool_input": "pytest -q"}
        )
        == "正在执行命令..."
    )
    assert (
        service._popo_progress_line_from_agent_stream_event(
            {"kind": "tool.started", "tool_name": "read_file", "tool_input": {"path": "desktop_blueprint_service.py"}}
        )
        == "正在读取文件..."
    )
    assert (
        service._popo_progress_line_from_agent_stream_event(
            {"kind": "tool.started", "tool_name": "blueprint_script_call"}
        )
        == "正在调用脚本节点..."
    )
    assert (
        service._popo_progress_line_from_agent_stream_event(
            {"kind": "tool.started", "tool_name": "custom_tool"}
        )
        == "正在调用工具 custom_tool..."
    )


def test_framework_popo_reply_finalizes_existing_progress_card(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    service.save_popo_robot(_popo_entry("robot-1"))
    session_key = "bps_popo_u1+default-blueprint"
    run = DesktopBlueprintRun(
        run_id="run-1",
        project_dir=project,
        blueprint_id="default",
        document=_document(project),
        graph=object(),
        runtime=SimpleNamespace(popo_reply_session_key=session_key),
        control=object(),
        execution_mode="live",
        created_at=1.0,
        updated_at=1.0,
        session_key=session_key,
        start_node_id="planner",
        robot_app_key="robot-1",
    )
    service._runs[run.run_id] = run
    service._save_blueprint_session(
        {
            "sessionKey": session_key,
            "source": "popo",
            "status": "running",
            "activeRunId": "run-1",
            "lastRunId": "run-1",
            "robotAppKey": "robot-1",
            "popoReplyTo": "reply-u1",
        }
    )
    service._popo_progress_cards["run-1"] = desktop_blueprint_service_module.PopoStreamingProgressCard(
        run_id="run-1",
        session_key=session_key,
        receiver="reply-u1",
        robot_app_key="robot-1",
        token="access-token-1",
        instance_uuid="card-1",
        popo_message_id="popo-msg-1",
        session_type="1",
        sequence=1,
        last_content="正在搜索代码...",
        lines=["正在搜索代码..."],
        progress_started=True,
    )
    recalls: list[dict[str, Any]] = []
    replies: list[dict[str, Any]] = []

    def fake_recall(**kwargs: Any) -> dict[str, Any]:
        recalls.append(dict(kwargs))
        return {"ok": True, "sent": True, "recalled": True, "errcode": 0}

    def fake_send_popo_message(**kwargs: Any) -> dict[str, Any]:
        replies.append(dict(kwargs))
        return {"ok": True, "sent": True, "errcode": 0, "transport": "streaming_card", "messageId": "final-card-1"}

    monkeypatch.setattr(service, "_recall_popo_message", fake_recall)
    monkeypatch.setattr(service, "_send_popo_message", fake_send_popo_message)

    result = service._reply_popo_user_from_framework(
        "run-1",
        content="agent reply",
        session_key=session_key,
        agent_node_id="planner",
        agent_id="agent-planner",
        message_id="msg-1",
    )

    assert result["ok"] is True
    assert result["sent"] is True
    assert recalls == [
        {
            "message_id": "popo-msg-1",
            "session_id": "reply-u1",
            "session_type": "1",
            "token": "access-token-1",
        }
    ]
    assert replies == [
        {
            "receiver": "reply-u1",
            "content": "agent reply",
            "robot_config": service._resolve_popo_callback_robot("robot-1"),
        }
    ]
    assert "run-1" not in service._popo_progress_cards
    transcript = (service.blueprint_sessions_dir() / session_key / "transcript.jsonl").read_text(encoding="utf-8")
    assert '"transport": "streaming_card"' in transcript
    assert '"popoMessageId": "final-card-1"' in transcript
    assert '"progressTransport": "streaming_card_progress_recall"' in transcript
    assert '"recalledProgressMessageId": "popo-msg-1"' in transcript


def test_framework_popo_reply_sends_start_agent_utterance_to_saved_reply_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    service.save_popo_robot(_popo_entry("robot-1"))
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)
    _patch_fake_session_instances(monkeypatch, service)
    monkeypatch.setattr(service, "_begin_popo_progress_card_for_session", lambda *args, **kwargs: None)

    monkeypatch.setattr(service, "_run_is_active", lambda run: True)
    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda run, graph=None: {"run": {"runId": run.run_id, "status": "running"}, "recent_events": []},
    )
    monkeypatch.setattr(service, "queue_agent_message", lambda run_id, node_id, text, *, mode="default", **kwargs: {"ok": True})

    started = service.handle_request(
        {
            "command": "blueprint.sessions.message",
            "args": {
                "message": "hello from popo",
                "source": "popo",
                "sourceIdentity": {"robotAppKey": "robot-1"},
                "sessionIdentity": {
                    "popoUserId": "u1",
                    "popoSessionId": "s1",
                    "popoReplyTo": "reply-u1",
                    "popoSessionType": "1",
                },
            },
        }
    )
    sent: list[dict[str, Any]] = []

    def fake_send_popo_message(*, receiver: str, content: str, robot_config: dict[str, Any]) -> dict[str, Any]:
        sent.append(
            {
                "receiver": receiver,
                "content": content,
                "robotAppKey": robot_config["robot_app_key"],
                "hasSecret": "robot_app_secret" in robot_config,
            }
        )
        return {"ok": True, "sent": True, "errcode": 0, "transport": "streaming_card", "messageId": "card-1"}

    monkeypatch.setattr(service, "_send_popo_message", fake_send_popo_message)
    with service._lock:
        run = service._runs[started["runId"]]
        control_requests: list[dict[str, Any]] = []
        run.control = SimpleNamespace(
            handle_request=lambda request: control_requests.append(request) or {"ok": True}
        )
    session_path = service.blueprint_sessions_dir() / started["sessionKey"] / "session.json"
    session_payload = json.loads(session_path.read_text(encoding="utf-8"))
    session_payload["activeRunId"] = started["runId"]
    session_payload["lastRunId"] = started["runId"]
    session_payload["status"] = "running"
    service._save_blueprint_session(session_payload)

    result = service._forward_framework_popo_reply(
        started["runId"],
        {
            "said": "agent reply",
            "node_id": "planner",
            "agent_id": "agent-planner",
            "message_id": "msg-framework-reply",
        },
    )

    assert result is not None
    assert result["ok"] is True
    assert result["sent"] is True
    assert "receiver" not in result
    assert sent == [
        {"receiver": "reply-u1", "content": "agent reply", "robotAppKey": "robot-1", "hasSecret": True}
    ]
    transcript = (service.blueprint_sessions_dir() / started["sessionKey"] / "transcript.jsonl").read_text(encoding="utf-8")
    assert '"type": "agent_reply"' in transcript
    assert '"type": "popo_reply_sent"' in transcript
    assert '"messageId": "msg-framework-reply"' in transcript
    assert '"source": "framework_popo_reply"' in transcript
    assert '"frameworkReply": true' in transcript
    assert '"transport": "streaming_card"' in transcript
    assert '"popoMessageId": "card-1"' in transcript
    assert "agent reply" in transcript
    assert control_requests[-1]["command"] == "agent.task_status"
    assert control_requests[-1]["args"]["metadata"]["source"] == "framework_popo_reply"


def test_stream_notification_registers_framework_popo_reply_callback(tmp_path: Path) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    runtime = SimpleNamespace(agent_stream_event_callback=None, agent_reply_callback=None)
    run = DesktopBlueprintRun(
        run_id="run-1",
        project_dir=tmp_path / "project",
        blueprint_id="default",
        document=_document(tmp_path / "project"),
        graph=object(),
        runtime=runtime,
        control=object(),
        execution_mode="live",
        created_at=1.0,
        updated_at=1.0,
    )

    service._attach_stream_notification(run)

    assert callable(runtime.agent_stream_event_callback)
    assert callable(runtime.agent_reply_callback)


def test_framework_popo_reply_filters_non_user_visible_utterances(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    runtime = SimpleNamespace(popo_reply_session_key="main+default")
    run = DesktopBlueprintRun(
        run_id="run-1",
        project_dir=tmp_path / "project",
        blueprint_id="default",
        document=_document(tmp_path / "project"),
        graph=object(),
        runtime=runtime,
        control=object(),
        execution_mode="live",
        created_at=1.0,
        updated_at=1.0,
        start_node_id="planner",
        session_key="main+default",
        robot_app_key="robot-1",
    )
    service._runs[run.run_id] = run
    forwarded: list[dict[str, Any]] = []

    def fake_reply(run_id: str, **kwargs: Any) -> dict[str, Any]:
        forwarded.append({"runId": run_id, **kwargs})
        return {"ok": True}

    monkeypatch.setattr(service, "_reply_popo_user_from_framework", fake_reply)
    monkeypatch.setattr(service, "_auto_complete_framework_popo_reply_task_status", lambda *args, **kwargs: None)
    temporary_replies: list[dict[str, Any]] = []

    def fake_temporary(run_id: str, text: str) -> dict[str, Any]:
        temporary_replies.append({"runId": run_id, "text": text})
        return {"ok": True, "sent": True, "transport": "streaming_card_progress"}

    monkeypatch.setattr(service, "_append_popo_progress_temporary_reply", fake_temporary)

    assert service._forward_framework_popo_reply("run-1", {"said": "", "node_id": "planner"}) is None
    assert service._forward_framework_popo_reply("run-1", {"said": "review", "node_id": "reviewer"}) is None
    assert service._forward_framework_popo_reply(
        "run-1",
        {"said": "summary", "node_id": "planner", "message_id": "summary-msg-planner-1"},
    ) is None
    assert service._forward_framework_popo_reply(
        "run-1",
        {
            "said": "internal script reminder reply",
            "node_id": "planner",
            "message_id": "script-call-reminder-planner-1",
            "reply_required": False,
            "reply_visibility": "framework_internal",
            "framework_message_kind": "blueprint_script_call_reminder",
        },
    ) is None
    assert service._forward_framework_popo_reply(
        "run-1",
        {
            "said": "internal target reminder reply",
            "node_id": "planner",
            "message_id": "outgoing-targets-reminder-planner-1",
        },
    ) is None

    utterance = {
        "said": "visible reply",
        "node_id": "planner",
        "agent_id": "agent-planner",
        "message_id": "msg-1",
    }
    temporary_utterance = {
        "said": "第二行已写入。继续最后一行，然后统一回读校验。",
        "node_id": "planner",
        "agent_id": "agent-planner",
        "message_id": "msg-temp",
        "reply_visibility": "session_event",
    }
    assert service._forward_framework_popo_reply("run-1", temporary_utterance) == {
        "ok": True,
        "sent": True,
        "transport": "streaming_card_progress",
    }
    final_session_event_utterance = {
        "said": "待提交信息：#695508\n请确认是否提交 SVN。",
        "node_id": "planner",
        "agent_id": "agent-planner",
        "message_id": "msg-final",
        "reply_visibility": "session_event",
    }
    assert service._forward_framework_popo_reply("run-1", final_session_event_utterance) == {"ok": True}
    assert service._forward_framework_popo_reply("run-1", utterance) == {"ok": True}
    assert service._forward_framework_popo_reply("run-1", utterance) is None
    assert temporary_replies == [
        {
            "runId": "run-1",
            "text": "第二行已写入。继续最后一行，然后统一回读校验。",
        }
    ]
    assert [item["content"] for item in forwarded] == ["待提交信息：#695508\n请确认是否提交 SVN。", "visible reply"]


@pytest.mark.skip(reason="run slot message wrapper removed from UI flow")
def test_blueprint_slot_ui_message_uses_main_session_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = {"start_node_id": "planner"}
    service.save_blueprint(project, document)
    _register_fake_slot(service, project, service.open_blueprint(project, "default"), robot_app_key="")
    queued: list[tuple[str, str, str, str]] = []

    monkeypatch.setattr(service, "_run_is_active", lambda run: True)
    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda run, graph=None: {"run": {"runId": run.run_id, "status": "running"}, "recent_events": []},
    )

    def fake_queue(run_id, node_id, text, *, mode="default", **kwargs):
        queued.append((run_id, node_id, text, mode))
        return {"ok": True}

    monkeypatch.setattr(service, "queue_agent_message", fake_queue)

    result = service.message_blueprint_slot(
        project,
        "hello from ui",
        source="ui",
        blueprint_id="default",
        run_id="run-slot-1",
    )

    assert result["ok"] is True
    assert result["sessionKey"] == "main+default"
    assert result["runId"] == "run-slot-1"
    assert queued[-1][0:2] == ("run-slot-1", "planner")
    assert queued[-1][3] == "top"
    assert "hello from ui" in queued[-1][2]
    run = service._runs["run-slot-1"]
    assert run.mcp.termination_calls == []
    assert run.mcp.reply_calls == []
    session_path = service.blueprint_sessions_dir() / "main+default" / "session.json"
    transcript_path = service.blueprint_sessions_dir() / "main+default" / "transcript.jsonl"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert session["sessionKey"] == "main+default"
    assert session["source"] == "ui"
    assert session["messageCount"] == 1
    assert "hello from ui" in transcript_path.read_text(encoding="utf-8")


@pytest.mark.skip(reason="run slot reset/reuse model removed")
def test_blueprint_slot_new_clears_main_session_without_deleting_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = {"start_node_id": "planner"}
    service.save_blueprint(project, document)
    run = _register_fake_slot(service, project, service.open_blueprint(project, "default"), robot_app_key="")

    monkeypatch.setattr(service, "_run_is_active", lambda active_run: True)
    monkeypatch.setattr(
        service,
        "_runtime_status_snapshot_or_starting",
        lambda active_run, graph=None: {"run": {"runId": active_run.run_id, "status": "running"}, "recent_events": []},
    )
    monkeypatch.setattr(service, "queue_agent_message", lambda run_id, node_id, text, *, mode="default", **kwargs: {"ok": True})

    started = service.message_blueprint_slot(
        project,
        "hello from ui",
        source="ui",
        blueprint_id="default",
        run_id="run-slot-1",
    )
    excel_marker = service._blueprint_session_dir("main+default") / "excel_ops" / "agent" / "marker.json"
    excel_marker.parent.mkdir(parents=True, exist_ok=True)
    excel_marker.write_text("{}", encoding="utf-8")
    def fail_end(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("/new must not close or cancel a blueprint slot run")

    monkeypatch.setattr(service, "end_blueprint_run", fail_end)

    cleared = service.message_blueprint_slot(
        project,
        "/new",
        source="ui",
        blueprint_id="default",
        run_id="run-slot-1",
    )

    assert started["sessionKey"] == "main+default"
    assert cleared["ok"] is True
    assert cleared["sessionKey"] == "main+default"
    assert cleared["cancelledRunId"] == ""
    assert cleared["resetRunId"] == "run-slot-1"
    assert run.slot_reset_future is not None
    run.slot_reset_future.result(timeout=5)
    session_path = service.blueprint_sessions_dir() / "main+default" / "session.json"
    transcript_path = service.blueprint_sessions_dir() / "main+default" / "transcript.jsonl"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert session["deleted"] is False
    assert session["status"] == "idle"
    assert session["messageCount"] == 0
    assert session["activeRunId"] == ""
    assert session["lastRunId"] == "run-slot-1"
    assert session["queuedMessages"] == []
    assert session["queuedMessageCount"] == 0
    assert transcript_path.read_text(encoding="utf-8") == ""
    assert excel_marker.is_file()
    assert run.runtime.reset_calls
    assert run.runtime.reset_calls[-1]["kwargs"]["cancel_pending"] is True
    assert run.slot_status == "idle"
    assert run.session_key == ""
    assert run.bound_session_key == ""


def test_blueprint_slot_excel_log_returns_records_without_agent_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = {"start_node_id": "planner"}
    service.save_blueprint(project, document)

    workbook = tmp_path / "table.xlsx"
    workbook.write_text("before", encoding="utf-8")
    session_dir = service._blueprint_session_dir("main+default")
    prepared = prepare_service_call_audit(
        {"session_key": "main+default", "session_dir": str(session_dir), "source_node_id": "planner"},
        "xltool",
        "set_cell",
        {"file": str(workbook), "cell": "A1", "value": "after", "in_place": True},
        now=lambda: 1_800_000_000.0,
    )
    assert prepared is not None
    workbook.write_text("after", encoding="utf-8")
    finalize_service_call_audit(prepared, {"ok": True, "data": {"changed": True}})

    def fail_queue(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("/excel-log must not dispatch to an Agent")

    monkeypatch.setattr(service, "queue_agent_message", fail_queue)

    result = service.message_blueprint_session(
        project,
        "default",
        "/excel-log 2020 1 1 0 0 0 0-2030 1 1 0 0 0 0",
        source="ui",
        session_key="main+default",
    )

    assert result["ok"] is True
    assert result["excelLog"] is True
    assert "xltool.set_cell" in result["message"]
    assert "table.xlsx" in result["message"]


def test_popo_global_binding_conflicts_on_multiple_registered_projects(tmp_path: Path) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    for name in ("project-a", "project-b"):
        project = tmp_path / name
        project.mkdir()
        document = _document(project)
        document["runtime"] = _popo_runtime(robot_app_key="robot-1")
        service.save_blueprint(project, document)

    with pytest.raises(BlueprintServiceError) as exc:
        service.handle_request({"command": "blueprint.popo.config", "args": {"robotAppKey": "robot-1"}})

    assert exc.value.code == "BLUEPRINT_POPO_ROBOT_STRUCTURE_CONFLICT"


def test_popo_config_without_robot_key_conflicts_on_multiple_registered_projects(tmp_path: Path) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    for name, robot in (("project-a", "robot-a"), ("project-b", "robot-b")):
        project = tmp_path / name
        project.mkdir()
        document = _document(project)
        document["runtime"] = _popo_runtime(robot_app_key=robot)
        service.save_blueprint(project, document)

    with pytest.raises(BlueprintServiceError) as exc:
        service.handle_request({"command": "blueprint.popo.config", "args": {}})

    assert exc.value.code == "BLUEPRINT_POPO_ROBOT_STRUCTURE_CONFLICT"


def test_popo_callback_health_and_p2p_event(monkeypatch: pytest.MonkeyPatch) -> None:
    popo = pytest.importorskip("multi_agent_tcp.popo_agent_bot_run")
    aes_key = "0123456789abcdef0123456789abcdef"
    token = "callback-token"
    captured: list[dict[str, str]] = []
    popo._event_cache.clear()

    monkeypatch.setattr(
        popo,
        "load_popo_config",
        lambda robot_app_key: {
            "robot_app_key": robot_app_key or "robot-1",
            "robot_app_secret": "secret",
            "callback_token": token,
            "aes_key": aes_key,
        },
    )
    monkeypatch.setattr(
        popo,
        "_start_handler_thread",
        lambda robot_config, reply_to, notify, sender, popo_session_id, popo_group_id="", session_type="": captured.append(
            {
                "robot": robot_config["robot_app_key"],
                "replyTo": reply_to,
                "notify": notify,
                "sender": sender,
                "sessionId": popo_session_id,
                "groupId": popo_group_id,
                "sessionType": session_type,
            }
        ),
    )

    client = popo.app.test_client()
    assert client.get("/health").get_json()["ok"] is True

    timestamp = "1"
    nonce = "2"
    signature = popo.check_sha256_signature
    raw = {"token": token, "timestamp": timestamp, "nonce": nonce}
    sign_text = "".join(value for _, value in sorted(raw.items(), key=lambda item: item[1]))
    digest = hashlib.sha256(sign_text.encode()).hexdigest()
    payload = {
        "eventType": "IM_P2P_TO_ROBOT_MSG",
        "eventData": {"from": "user-1", "notify": "hello", "sessionId": "session-1"},
    }
    encrypted = popo.AESCipher(aes_key).aes_cbc_encrypt(json.dumps(payload))

    response = client.post(
        f"/popo/callback/robot-1?timestamp={timestamp}&nonce={nonce}&signature={digest}",
        json={"encrypt": encrypted},
    )
    legacy_response = client.post(
        f"/popo/callback?timestamp={timestamp}&nonce={nonce}&signature={digest}",
        json={"encrypt": encrypted},
    )

    assert signature(token, timestamp, nonce, digest) is True
    assert response.status_code == 200
    assert legacy_response.status_code == 200
    assert captured == [
        {
            "robot": "robot-1",
            "replyTo": "user-1",
            "notify": "hello",
            "sender": "user-1",
            "sessionId": "session-1",
            "groupId": "",
            "sessionType": "",
        },
        {
            "robot": "robot-1",
            "replyTo": "user-1",
            "notify": "hello",
            "sender": "user-1",
            "sessionId": "session-1",
            "groupId": "",
            "sessionType": "",
        },
    ]


def test_popo_callback_ignores_duplicate_event_uuid(monkeypatch: pytest.MonkeyPatch) -> None:
    popo = pytest.importorskip("multi_agent_tcp.popo_agent_bot_run")
    aes_key = "0123456789abcdef0123456789abcdef"
    token = "callback-token"
    captured: list[str] = []
    popo._event_cache.clear()

    monkeypatch.setattr(
        popo,
        "load_popo_config",
        lambda robot_app_key: {
            "robot_app_key": robot_app_key or "robot-1",
            "robot_app_secret": "secret",
            "callback_token": token,
            "aes_key": aes_key,
        },
    )
    monkeypatch.setattr(
        popo,
        "_start_handler_thread",
        lambda robot_config, reply_to, notify, sender, popo_session_id, popo_group_id="", session_type="": captured.append(
            notify
        ),
    )

    timestamp = "1"
    nonce = "2"
    sign_text = "".join(value for _, value in sorted({"token": token, "timestamp": timestamp, "nonce": nonce}.items(), key=lambda item: item[1]))
    digest = hashlib.sha256(sign_text.encode()).hexdigest()
    payload = {
        "eventType": "IM_P2P_TO_ROBOT_MSG",
        "eventData": {
            "uuid": "same-event-uuid",
            "from": "user-1",
            "notify": "hello",
            "sessionId": "session-1",
            "sessionType": 1,
        },
    }
    encrypted = popo.AESCipher(aes_key).aes_cbc_encrypt(json.dumps(payload))
    client = popo.app.test_client()

    first = client.post(
        f"/popo/callback/robot-1?timestamp={timestamp}&nonce={nonce}&signature={digest}",
        json={"encrypt": encrypted},
    )
    second = client.post(
        f"/popo/callback/robot-1?timestamp={timestamp}&nonce={nonce}&signature={digest}",
        json={"encrypt": encrypted},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert captured == ["hello"]


def test_popo_callback_config_falls_back_to_local_routes_on_service_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    popo = pytest.importorskip("multi_agent_tcp.popo_agent_bot_run")
    routes_path = tmp_path / "popo_robot_routes.json"
    popo._config_cache.clear()
    routes_path.write_text(
        json.dumps(
            {
                "version": 1,
                "robots": {
                    "robot-1": {
                        "enabled": True,
                        "robot_app_key": "robot-1",
                        "robot_name": "Robot 1",
                        "robot_app_secret": "secret",
                        "callback_token": "token",
                        "aes_key": "0123456789abcdef0123456789abcdef",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def timeout_config(*args, **kwargs):
        calls.append((args, kwargs))
        raise popo.SingletonServiceError("SERVICE_ERROR", "timed out")

    monkeypatch.setattr(popo, "POPO_ROBOT_ROUTES_PATH", routes_path)
    monkeypatch.setattr(popo, "blueprint_request", timeout_config)

    result = popo.load_popo_config("robot-1")
    legacy = popo.load_popo_config("")

    assert result["robot_app_key"] == "robot-1"
    assert result["callback_token"] == "token"
    assert result["source"] == "local_routes"
    assert legacy["robot_app_key"] == "robot-1"
    assert calls == []


def test_blueprint_slots_start_command_is_removed(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    document["runtime"] = _popo_runtime()
    service.save_blueprint(project, document)

    with pytest.raises(BlueprintServiceError) as exc:
        service.handle_request(
            {
                "command": "blueprint.slots.start",
                "args": {"projectDir": str(project), "blueprintId": "default"},
            }
        )

    assert exc.value.code == "UNKNOWN_COMMAND"


def test_blueprint_service_creates_and_soft_deletes_blueprint(tmp_path: Path) -> None:
    service = DesktopBlueprintService()

    created = service.handle_request(
        {
            "command": "blueprint.create",
            "args": {"projectDir": str(tmp_path), "blueprintId": "plugin-test", "name": "Plugin Test"},
        }
    )
    listed = service.handle_request({"command": "blueprint.list", "args": {"projectDir": str(tmp_path)}})
    deleted = service.handle_request(
        {"command": "blueprint.delete", "args": {"projectDir": str(tmp_path), "blueprintId": "plugin-test"}}
    )
    listed_after_delete = service.handle_request({"command": "blueprint.list", "args": {"projectDir": str(tmp_path)}})

    assert created["ok"] is True
    assert created["document"]["id"] == "plugin-test"
    assert [item["id"] for item in listed["blueprints"]] == ["plugin-test"]
    assert deleted["ok"] is True
    assert Path(deleted["trashPath"]).is_file()
    assert listed_after_delete["blueprints"] == []


def test_resident_service_template_docs_lifecycle_and_logs(tmp_path: Path) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "bp-data")
    created = service.handle_request(
        {
            "command": "blueprint.createResidentService",
            "args": {"name": "Echo Service", "description": "Echo test payloads."},
        }
    )
    service_name = created["service_name"]

    try:
        listed = service.handle_request({"command": "blueprint.residentServices", "args": {}})
        docs = service.handle_request(
            {"command": "blueprint.residentServiceDocs", "args": {"serviceName": service_name}}
        )
        started = service.handle_request(
            {"command": "blueprint.startResidentService", "args": {"serviceName": service_name}}
        )
        called = service.resident_service_manager().call(service_name, "echo", {"message": "hello"})
        logs = service.handle_request(
            {"command": "blueprint.residentServiceLogs", "args": {"serviceName": service_name, "limit": 40}}
        )

        assert created["ok"] is True
        assert Path(created["file_path"]).is_file()
        assert listed["services"][0]["service_name"] == service_name
        assert listed["services"][0]["status"] in {"stopped", "stale"}
        assert docs["ok"] is True
        assert docs["service"]["methods"][0]["name"] == "echo"
        assert started["ok"] is True
        assert started["service"]["status"] == "running"
        assert called["ok"] is True
        assert called["result"] == {"message": "hello"}
        assert "Resident service" in logs["logs"]
    finally:
        with suppress(Exception):
            service.handle_request({"command": "blueprint.stopResidentService", "args": {"serviceName": service_name}})


def test_resident_service_call_returns_error_when_not_running(tmp_path: Path) -> None:
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "bp-data")
    created = service.handle_request(
        {
            "command": "blueprint.createResidentService",
            "args": {"name": "Stopped Service", "description": ""},
        }
    )

    called = service.resident_service_manager().call(created["service_name"], "echo", {"message": "hello"})

    assert called["ok"] is False
    assert called["code"] == "RESIDENT_SERVICE_NOT_RUNNING"


def test_resident_service_call_timeout_respects_method_timeout_argument() -> None:
    assert _resident_service_call_timeout({}) == 20.0
    assert _resident_service_call_timeout({"timeout_seconds": 60}) == 65.0
    assert _resident_service_call_timeout({"timeoutSeconds": 60}) == 65.0
    assert _resident_service_call_timeout({"timeout_seconds": 1000}) == 125.0


def test_blueprint_service_delete_rejects_active_run(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    try:
        service.handle_request(
            {"command": "blueprint.save", "args": {"projectDir": str(tmp_path), "document": _document(tmp_path)}}
        )
        started = service.handle_request(
            {
                "command": "blueprint.start",
                "args": {
                    "projectDir": str(tmp_path),
                    "blueprintId": "default",
                    "plan": _plan(),
                    "executionMode": "status",
                },
            }
        )

        with pytest.raises(BlueprintServiceError) as exc:
            service.handle_request(
                {"command": "blueprint.delete", "args": {"projectDir": str(tmp_path), "blueprintId": "default"}}
            )

        assert started["ok"] is True
        assert exc.value.code == "BLUEPRINT_IN_USE"
    finally:
        service.close()


def test_blueprint_service_creates_and_validates_start_plan(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    service.handle_request(
        {"command": "blueprint.save", "args": {"projectDir": str(tmp_path), "document": _document(tmp_path)}}
    )

    with pytest.raises(BlueprintServiceError) as exc:
        service.handle_request(
            {
                "command": "blueprint.plan.create",
                "args": {"projectDir": str(tmp_path), "blueprintId": "default", "task": "Ship it"},
            }
        )
    created = service.handle_request(
        {
            "command": "blueprint.plan.create",
            "args": {
                "projectDir": str(tmp_path),
                "blueprintId": "default",
                "task": "Ship it",
                "startNodeIds": ["planner"],
            },
        }
    )
    validated = service.handle_request(
        {
            "command": "blueprint.plan.validate",
            "args": {"projectDir": str(tmp_path), "blueprintId": "default", "plan": created["plan"]},
        }
    )

    assert exc.value.code == "START_NODES_REQUIRED"
    assert created["ok"] is True
    assert created["plan"]["user_goal"] == "Ship it"
    assert created["plan"]["start_nodes"] == ["planner"]
    assert created["validation"]["ok"] is True
    assert created["validation"]["valid_start_nodes"] == ["planner"]
    assert validated["validation"]["ok"] is True


def test_blueprint_service_plan_overrides_cannot_replace_start_nodes(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    service.handle_request(
        {"command": "blueprint.save", "args": {"projectDir": str(tmp_path), "document": _document(tmp_path)}}
    )

    with pytest.raises(BlueprintServiceError) as exc:
        service.handle_request(
            {
                "command": "blueprint.plan.create",
                "args": {
                    "projectDir": str(tmp_path),
                    "blueprintId": "default",
                    "task": "Ship it",
                    "startNodeIds": ["planner"],
                    "planOverrides": {"start_nodes": ["ghost"]},
                },
            }
        )
    overridden = service.handle_request(
        {
            "command": "blueprint.plan.create",
            "args": {
                "projectDir": str(tmp_path),
                "blueprintId": "default",
                "task": "Ship it",
                "startNodeIds": ["planner"],
                "planOverrides": {"user_goal": "Override goal"},
            },
        }
    )

    assert exc.value.code == "START_PLAN_OVERRIDE_REJECTED"
    assert overridden["plan"]["user_goal"] == "Override goal"
    assert overridden["plan"]["start_nodes"] == ["planner"]


def test_gulicode_bp_standalone_mcp_payload_uses_plugin_runtime(tmp_path: Path) -> None:
    installer = _load_gulicode_bp_installer_module()
    plugin_root = tmp_path / "gulicode-bp"

    payload = installer.build_mcp_payload(plugin_root)
    server = payload["mcpServers"]["gulicode-bp"]
    env = server["env"]

    assert server["command"] == "python"
    assert server["args"] == ["scripts/bootstrap_mcp.py"]
    assert server["cwd"] == str(plugin_root)
    assert env["GULICODE_BP_PLUGIN_ROOT"] == str(plugin_root)
    assert env["GULICODE_BP_RUNTIME_HOME"] == str(plugin_root / ".runtime")
    assert env["GULICODE_BP_DATA_DIR"] == str(plugin_root / ".runtime" / "state")
    assert env["GULICODE_BP_DISABLE_REPO_FALLBACK"] == "1"
    assert "GULICODE_BP_REPO_ROOT" not in env
    assert "PYTHONPATH" not in env


def test_gulicode_bp_bootstrap_creates_runtime_and_installs_wheel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap = _load_gulicode_bp_bootstrap_runtime_module()
    plugin_root = tmp_path / "gulicode-bp"
    wheel = plugin_root / "runtime" / "wheels" / "multi_agent_tcp-0.5.0-py3-none-any.whl"
    wheel.parent.mkdir(parents=True)
    wheel.write_text("wheel", encoding="utf-8")
    runtime_root = plugin_root / ".runtime"
    runtime_python = bootstrap.runtime_venv_python(runtime_root)
    calls: list[list[str]] = []

    class Completed:
        stdout = ""
        stderr = ""
        returncode = 0

    def fake_run_checked(args, **kwargs):
        call = [str(item) for item in args]
        calls.append(call)
        if call[1:3] == ["-m", "venv"]:
            runtime_python.parent.mkdir(parents=True)
            runtime_python.write_text("", encoding="utf-8")
        return Completed()

    def fake_validate(python: Path, root: Path, runtime: Path) -> dict[str, str]:
        assert python == runtime_python
        assert root == plugin_root.resolve()
        assert runtime == runtime_root.resolve()
        return {"runtimePackage": str(runtime / "venv" / "Lib" / "site-packages" / "multi_agent_tcp" / "__init__.py")}

    monkeypatch.setattr(bootstrap, "_run_checked", fake_run_checked)
    monkeypatch.setattr(bootstrap, "pip_available", lambda python: True)
    monkeypatch.setattr(bootstrap, "validate_runtime_imports", fake_validate)

    result = bootstrap.prepare_runtime(plugin_root)

    install_calls = [call for call in calls if call[1:4] == ["-m", "pip", "install"]]
    assert result["createdVenv"] is True
    assert result["installedRuntime"] is True
    assert len(install_calls) == 1
    install_call = install_calls[0]
    assert "--upgrade" in install_call
    assert "--force-reinstall" in install_call
    assert "--no-deps" not in install_call
    assert "--ignore-installed" not in install_call
    assert install_call[-1] == str(wheel.resolve())
    assert (runtime_root / "state" / "bootstrap.json").is_file()
    status = json.loads((runtime_root / "state" / "mcp_status.json").read_text(encoding="utf-8"))
    assert status["status"] == "starting"
    assert status["phase"] == "runtime-ready"
    assert status["component"] == "runtime-bootstrap"
    log_text = (runtime_root / "state" / "logs" / "gulicode-bp-bootstrap.log").read_text(encoding="utf-8")
    assert "prepare-start" in log_text
    assert "runtime-install-start" in log_text
    assert "prepare-complete" in log_text


def test_gulicode_bp_bootstrap_removes_dead_pid_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap = _load_gulicode_bp_bootstrap_runtime_module()
    plugin_root = tmp_path / "gulicode-bp"
    wheel = plugin_root / "runtime" / "wheels" / "multi_agent_tcp-0.5.0-py3-none-any.whl"
    wheel.parent.mkdir(parents=True)
    wheel.write_text("wheel", encoding="utf-8")
    runtime_root = plugin_root / ".runtime"
    runtime_python = bootstrap.runtime_venv_python(runtime_root)
    runtime_python.parent.mkdir(parents=True)
    runtime_python.write_text("", encoding="utf-8")
    state_dir = runtime_root / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "bootstrap.json").write_text(
        json.dumps({"runtimeWheel": bootstrap._wheel_identity(wheel.resolve())}),
        encoding="utf-8",
    )
    lock_path = runtime_root / "bootstrap.lock"
    lock_path.write_text("pid=987654\ncreated=2026-06-02T00:00:00Z\ncommand=test\n", encoding="utf-8")

    monkeypatch.setattr(bootstrap, "_pid_is_running", lambda pid: False)
    monkeypatch.setattr(bootstrap, "pip_available", lambda python: True)
    monkeypatch.setattr(
        bootstrap,
        "validate_runtime_imports",
        lambda python, root, runtime: {"runtimePackage": str(runtime / "venv" / "multi_agent_tcp" / "__init__.py")},
    )

    result = bootstrap.prepare_runtime(plugin_root)

    assert result["createdVenv"] is False
    assert result["installedRuntime"] is False
    assert not lock_path.exists()
    log_text = (state_dir / "logs" / "gulicode-bp-bootstrap.log").read_text(encoding="utf-8")
    assert "stale-lock-removed" in log_text
    assert "dead-pid" in log_text


def test_gulicode_bp_bootstrap_keeps_live_pid_lock_until_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap = _load_gulicode_bp_bootstrap_runtime_module()
    runtime_root = tmp_path / ".runtime"
    runtime_root.mkdir()
    state_dir = runtime_root / "state"
    lock_path = runtime_root / "bootstrap.lock"
    lock_path.write_text(f"pid={os.getpid()}\ncreated=2026-06-02T00:00:00Z\ncommand=test\n", encoding="utf-8")

    monkeypatch.setattr(bootstrap, "_pid_is_running", lambda pid: True)

    with pytest.raises(RuntimeError, match="timed out waiting"):
        with bootstrap._bootstrap_lock(runtime_root, data_dir=state_dir, timeout=0.01, poll_interval=0.01):
            pass

    assert lock_path.exists()
    status = json.loads((state_dir / "mcp_status.json").read_text(encoding="utf-8"))
    assert status["status"] == "error"
    assert status["phase"] == "bootstrap-lock"
    log_text = (state_dir / "logs" / "gulicode-bp-bootstrap.log").read_text(encoding="utf-8")
    assert "lock-wait" in log_text
    assert "lock-timeout" in log_text


def test_gulicode_bp_bootstrap_failure_writes_status_and_log(tmp_path: Path) -> None:
    bootstrap = _load_gulicode_bp_bootstrap_runtime_module()
    plugin_root = tmp_path / "gulicode-bp"

    with pytest.raises(RuntimeError, match="runtime wheel is missing"):
        bootstrap.prepare_runtime(plugin_root, status_component="test-bootstrap")

    state_dir = plugin_root / ".runtime" / "state"
    status = json.loads((state_dir / "mcp_status.json").read_text(encoding="utf-8"))
    assert status["status"] == "error"
    assert status["component"] == "test-bootstrap"
    assert status["phase"] == "prepare-runtime"
    assert "runtime wheel is missing" in status["lastError"]
    log_text = (state_dir / "logs" / "gulicode-bp-bootstrap.log").read_text(encoding="utf-8")
    assert "prepare-start" in log_text
    assert "prepare-error" in log_text


def test_gulicode_bp_bootstrap_validation_disables_repo_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap = _load_gulicode_bp_bootstrap_runtime_module()
    plugin_root = tmp_path / "gulicode-bp"
    runtime_root = plugin_root / ".runtime"
    runtime_python = bootstrap.runtime_venv_python(runtime_root)
    runtime_package = runtime_root / "venv" / "Lib" / "site-packages" / "multi_agent_tcp" / "__init__.py"
    captured: dict[str, Any] = {}

    class Completed:
        stdout = json.dumps({"runtimePackage": str(runtime_package)})
        stderr = ""
        returncode = 0

    def fake_run_checked(args, **kwargs):
        captured["env"] = kwargs["env"]
        captured["cwd"] = kwargs["cwd"]
        return Completed()

    monkeypatch.setenv("GULICODE_BP_REPO_ROOT", r"F:\src\Package\Script\Python\multi_agent_tcp")
    monkeypatch.setenv("PYTHONPATH", r"F:\src\Package\Script\Python")
    monkeypatch.setattr(bootstrap, "_run_checked", fake_run_checked)

    result = bootstrap.validate_runtime_imports(runtime_python, plugin_root, runtime_root)

    env = captured["env"]
    assert result["runtimePackage"] == str(runtime_package.resolve())
    assert captured["cwd"] == plugin_root
    assert env["GULICODE_BP_PLUGIN_ROOT"] == str(plugin_root)
    assert env["GULICODE_BP_RUNTIME_HOME"] == str(runtime_root)
    assert env["GULICODE_BP_DATA_DIR"] == str(runtime_root / "state")
    assert env["GULICODE_BP_DISABLE_REPO_FALLBACK"] == "1"
    assert "GULICODE_BP_REPO_ROOT" not in env
    assert "PYTHONPATH" not in env


def test_gulicode_bp_installer_installs_runtime_dependencies_and_validates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installer = _load_gulicode_bp_installer_module()
    plugin_root = tmp_path / "gulicode-bp"
    wheel = tmp_path / "multi_agent_tcp-0.5.0-py3-none-any.whl"
    wheel.write_text("wheel", encoding="utf-8")
    runtime_python = installer.runtime_venv_python(plugin_root / ".runtime")
    runtime_python.parent.mkdir(parents=True)
    runtime_python.write_text("", encoding="utf-8")
    calls: list[list[str]] = []
    validated: list[tuple[Path, Path]] = []

    class Completed:
        returncode = 0

    def fake_run(args, **kwargs):
        calls.append([str(item) for item in args])
        return Completed()

    def fake_validate(python: Path, root: Path) -> None:
        validated.append((python, root))

    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    monkeypatch.setattr(installer, "validate_runtime_imports", fake_validate)

    result = installer.ensure_runtime_venv(plugin_root, wheel)

    install_calls = [call for call in calls if call[1:4] == ["-m", "pip", "install"]]
    assert result == runtime_python
    assert len(install_calls) == 1
    install_call = install_calls[0]
    assert "--upgrade" in install_call
    assert "--force-reinstall" in install_call
    assert "--no-deps" not in install_call
    assert "--ignore-installed" not in install_call
    assert install_call[-1] == str(wheel)
    assert validated == [(runtime_python, plugin_root)]


def test_gulicode_bp_installer_syncs_codex_cache_mcp(tmp_path: Path) -> None:
    installer = _load_gulicode_bp_installer_module()
    installed = tmp_path / "plugins" / "gulicode-bp"
    cache_root = tmp_path / ".codex" / "plugins" / "cache" / "personal" / "gulicode-bp"
    legacy_cache = cache_root / "0.1.2"
    installed.mkdir(parents=True)
    legacy_cache.mkdir(parents=True)
    (installed / ".codex-plugin").mkdir()
    (installed / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": "gulicode-bp", "version": "0.1.3"}),
        encoding="utf-8",
    )
    (installed / ".mcp.json").write_text("{}", encoding="utf-8")
    (legacy_cache / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "gulicode-bp": {
                        "env": {
                            "GULICODE_BP_REPO_ROOT": r"F:\src\Package\Script\Python\multi_agent_tcp",
                            "PYTHONPATH": r"F:\src\Package\Script\Python",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    updated = installer.sync_codex_cache(
        installed,
        version="0.1.3",
        cache_root=cache_root,
        force=True,
    )

    assert str(cache_root / "0.1.2") in updated
    assert str(cache_root / "0.1.3") in updated
    for version in ("0.1.2", "0.1.3"):
        payload = json.loads((cache_root / version / ".mcp.json").read_text(encoding="utf-8"))
        server = payload["mcpServers"]["gulicode-bp"]
        assert server["command"] == "python"
        assert server["args"] == ["scripts/bootstrap_mcp.py"]
        assert server["cwd"] == str(installed)
        assert server["env"]["GULICODE_BP_PLUGIN_ROOT"] == str(installed)
        assert server["env"]["GULICODE_BP_DISABLE_REPO_FALLBACK"] == "1"
        assert "GULICODE_BP_REPO_ROOT" not in server["env"]
        assert "PYTHONPATH" not in server["env"]


def test_gulicode_bp_release_package_contains_bootstrap_runtime_wheel_and_web_dist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installer = _load_gulicode_bp_installer_module()
    source = tmp_path / "source" / "gulicode-bp"
    package_dir = tmp_path / "source" / "multi_agent_tcp"
    release = tmp_path / "dist" / "gulicode-bp-0.1.3"
    for path in [
        source / ".codex-plugin",
        source / "mcp",
        source / "scripts",
        source / "skills" / "blueprint",
        source / "web" / "dist",
    ]:
        path.mkdir(parents=True)
    (source / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": "gulicode-bp", "version": "0.1.3"}),
        encoding="utf-8",
    )
    (source / ".mcp.json").write_text("{}", encoding="utf-8")
    (source / "mcp" / "gulicode_bp_mcp.py").write_text("# mcp\n", encoding="utf-8")
    (source / "scripts" / "bootstrap_mcp.py").write_text("# bootstrap mcp\n", encoding="utf-8")
    (source / "scripts" / "bootstrap_runtime.py").write_text("# bootstrap runtime\n", encoding="utf-8")
    (source / "skills" / "blueprint" / "SKILL.md").write_text("# skill\n", encoding="utf-8")
    (source / "web" / "dist" / "index.html").write_text("<html></html>\n", encoding="utf-8")
    (source / ".runtime").mkdir()

    def fake_copy_web_dist(plugin_root: Path, runtime_package: Path, *, skip_build: bool) -> str:
        assert plugin_root == source
        assert runtime_package == package_dir
        assert skip_build is True
        return str(plugin_root / "web" / "dist")

    def fake_build_runtime_wheel(runtime_package: Path, wheelhouse: Path) -> Path:
        assert runtime_package == package_dir
        wheelhouse.mkdir(parents=True)
        wheel = wheelhouse / "multi_agent_tcp-0.5.0-py3-none-any.whl"
        wheel.write_text("wheel", encoding="utf-8")
        return wheel

    monkeypatch.setattr(installer, "copy_web_dist", fake_copy_web_dist)
    monkeypatch.setattr(installer, "build_runtime_wheel", fake_build_runtime_wheel)

    payload = installer.prepare_release_package(
        source,
        package_dir,
        release,
        force=True,
        skip_build=True,
    )

    mcp_payload = json.loads((release / ".mcp.json").read_text(encoding="utf-8"))
    server = mcp_payload["mcpServers"]["gulicode-bp"]
    assert payload["mcpMode"] == "bootstrap"
    assert Path(payload["runtimeWheel"]).is_file()
    assert (release / "web" / "dist" / "index.html").is_file()
    assert (release / "runtime" / "wheels" / "multi_agent_tcp-0.5.0-py3-none-any.whl").is_file()
    assert not (release / ".runtime").exists()
    assert server["command"] == "python"
    assert server["args"] == ["scripts/bootstrap_mcp.py"]
    assert server["cwd"] == "."
    assert server["env"]["GULICODE_BP_PLUGIN_ROOT"] == "."
    assert server["env"]["GULICODE_BP_DISABLE_REPO_FALLBACK"] == "1"
    assert "GULICODE_BP_REPO_ROOT" not in server["env"]
    assert "PYTHONPATH" not in server["env"]


def test_gulicode_bp_standalone_smoke_env_disables_repo_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smoke = _load_gulicode_bp_smoke_module()
    plugin_root = tmp_path / "gulicode-bp"
    runtime_home = plugin_root / ".runtime"
    plugin_root.mkdir()
    (plugin_root / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "gulicode-bp": {
                        "type": "stdio",
                        "command": "python",
                        "args": ["scripts/bootstrap_mcp.py"],
                        "cwd": ".",
                        "env": {
                            "GULICODE_BP_PLUGIN_ROOT": ".",
                            "GULICODE_BP_DISABLE_REPO_FALLBACK": "1",
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GULICODE_BP_REPO_ROOT", r"F:\src\Package\Script\Python\multi_agent_tcp")
    monkeypatch.setenv("PYTHONPATH", r"F:\src\Package\Script\Python")

    server = smoke.load_mcp_server(plugin_root)
    env = smoke.build_child_env(plugin_root, server)

    assert server["command"] == "python"
    assert server["args"] == ["scripts/bootstrap_mcp.py"]
    assert env["GULICODE_BP_PLUGIN_ROOT"] == str(plugin_root)
    assert env["GULICODE_BP_RUNTIME_HOME"] == str(runtime_home)
    assert env["GULICODE_BP_DATA_DIR"] == str(runtime_home / "state")
    assert env["GULICODE_BP_DISABLE_REPO_FALLBACK"] == "1"
    assert env["PYTHONPATH"] == ""
    assert "GULICODE_BP_REPO_ROOT" not in env


def test_blueprint_service_lists_script_nodes_without_importing_user_code(tmp_path: Path) -> None:
    script_dir = tmp_path / ".multi_agent_workspace" / "scripts"
    script_dir.mkdir(parents=True)
    (script_dir / "score.py").write_text(
        "\n".join(
            [
                "raise RuntimeError('imported during scan')",
                "",
                "@blueprint_node(name='Format score', description='Build a display string')",
                "def format_score(count: int, ratio: float) -> str:",
                "    return f'{count}:{ratio:.2f}'",
            ]
        ),
        encoding="utf-8",
    )

    service = DesktopBlueprintService()
    result = service.handle_request({"command": "blueprint.scriptNodes", "args": {"projectDir": str(tmp_path)}})

    assert result["ok"] is True
    assert Path(result["script_dir"]) == script_dir.resolve()
    assert result["diagnostics"] == []
    assert result["nodes"] == [
        {
            "script_id": "score.py:format_score",
            "module_path": "score.py",
            "function_name": "format_score",
            "title": "Format score",
            "description": "Build a display string",
            "inputs": [
                {"name": "count", "type": "int", "required": True},
                {"name": "ratio", "type": "float", "required": True},
            ],
            "outputs": [{"name": "result", "type": "str", "required": True}],
        }
    ]


def test_blueprint_service_creates_script_node_template_and_catalog_item(tmp_path: Path) -> None:
    service = DesktopBlueprintService()

    result = service.handle_request(
        {
            "command": "blueprint.createScriptNode",
            "args": {
                "projectDir": str(tmp_path),
                "name": "Format Score",
                "description": "Formats a score for display",
            },
        }
    )
    second = service.handle_request(
        {"command": "blueprint.createScriptNode", "args": {"projectDir": str(tmp_path), "name": "Format Score"}}
    )

    script_dir = tmp_path / ".multi_agent_workspace" / "scripts"
    script_path = script_dir / "format_score.py"
    second_path = script_dir / "format_score_2.py"
    script_api_path = script_dir / "gulicode_blueprint.py"
    pyright = json.loads((script_dir / "pyrightconfig.json").read_text(encoding="utf-8"))
    vscode_settings = json.loads((script_dir / ".vscode" / "settings.json").read_text(encoding="utf-8"))
    workspace = json.loads((script_dir / "blueprint-scripts.code-workspace").read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert Path(result["script_dir"]) == script_dir.resolve()
    assert Path(result["file_path"]) == script_path.resolve()
    assert result["module_path"] == "format_score.py"
    assert result["function_name"] == "format_score"
    assert second["module_path"] == "format_score_2.py"
    assert second["function_name"] == "format_score"
    assert script_path.read_text(encoding="utf-8") == "\n".join(
        [
            "from gulicode_blueprint import blueprint_node",
            "",
            '@blueprint_node(name="Format Score", description="Formats a score for display")',
            "def format_score(payload: dict) -> dict:",
            "    return payload",
            "",
        ]
    )
    assert second_path.exists()
    script_api_text = script_api_path.read_text(encoding="utf-8")
    assert "def blueprint_node(" in script_api_text
    assert "def blueprint_service_call(" in script_api_text
    assert pyright["include"] == ["."]
    assert pyright["extraPaths"] == ["."]
    assert vscode_settings["python.analysis.extraPaths"] == ["."]
    assert vscode_settings["python.defaultInterpreterPath"] == sys.executable
    assert workspace["folders"] == [{"name": "Blueprint Scripts", "path": "."}]
    assert workspace["settings"]["python.analysis.extraPaths"] == ["."]
    assert result["dev_environment"]["workspace_file"] == str((script_dir / "blueprint-scripts.code-workspace").resolve())
    assert result["dev_environment"]["script_api_module"] == "gulicode_blueprint"
    assert result["dev_environment"]["script_api_path"] == str(script_api_path.resolve())
    assert result["node"] == {
        "script_id": "format_score.py:format_score",
        "module_path": "format_score.py",
        "function_name": "format_score",
        "title": "Format Score",
        "description": "Formats a score for display",
        "inputs": [{"name": "payload", "type": "dict", "required": True}],
        "outputs": [{"name": "result", "type": "dict", "required": True}],
    }

    output = asyncio.run(
        blueprint_script_nodes.execute_script_node(
            script_dir,
            ScriptNode.from_dict(
                {
                    "node_id": "format",
                    "script_id": "format_score.py:format_score",
                    "module_path": "format_score.py",
                    "function_name": "format_score",
                    "inputs": [{"name": "payload", "type": "dict", "required": True}],
                    "outputs": [{"name": "result", "type": "dict", "required": True}],
                }
            ),
            {"payload": {"value": 7}},
        )
    )
    assert output["result"] == {"value": 7}


def test_blueprint_script_node_legacy_runtime_import_still_executes(tmp_path: Path) -> None:
    script_dir = tmp_path / ".multi_agent_workspace" / "scripts"
    script_dir.mkdir(parents=True)
    (script_dir / "legacy.py").write_text(
        "\n".join(
            [
                "from multi_agent_tcp.blueprint_script_nodes import blueprint_node",
                "",
                "@blueprint_node(name='Legacy format')",
                "def legacy_format(payload: dict) -> dict:",
                "    return {'legacy': payload['value']}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    discovered = DesktopBlueprintService().handle_request(
        {"command": "blueprint.scriptNodes", "args": {"projectDir": str(tmp_path)}}
    )
    output = asyncio.run(
        blueprint_script_nodes.execute_script_node(
            script_dir,
            ScriptNode.from_dict(
                {
                    "node_id": "legacy",
                    "script_id": "legacy.py:legacy_format",
                    "module_path": "legacy.py",
                    "function_name": "legacy_format",
                    "inputs": [{"name": "payload", "type": "dict", "required": True}],
                    "outputs": [{"name": "result", "type": "dict", "required": True}],
                }
            ),
            {"payload": {"value": 9}},
        )
    )

    assert discovered["nodes"][0]["script_id"] == "legacy.py:legacy_format"
    assert output["result"] == {"legacy": 9}


def test_blueprint_script_node_service_call_helper_executes_in_runtime_context(tmp_path: Path) -> None:
    env = blueprint_script_nodes.ensure_script_nodes_dev_environment(tmp_path)
    script_dir = Path(env["script_dir"])
    (script_dir / "service_proxy.py").write_text(
        "\n".join(
            [
                "from gulicode_blueprint import blueprint_node, blueprint_service_call",
                "",
                "@blueprint_node(outputs={'result': dict})",
                "def service_proxy(payload: dict) -> dict:",
                "    return blueprint_service_call('table_queue', 'health', payload)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def service_call(service_name: str, method_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        calls.append((service_name, method_name, dict(arguments)))
        return {"ok": True, "service_name": service_name, "method_name": method_name, "result": dict(arguments)}

    output = asyncio.run(
        blueprint_script_nodes.execute_script_node(
            script_dir,
            ScriptNode.from_dict(
                {
                    "node_id": "service_proxy",
                    "script_id": "service_proxy.py:service_proxy",
                    "module_path": "service_proxy.py",
                    "function_name": "service_proxy",
                    "inputs": [{"name": "payload", "type": "dict", "required": True}],
                    "outputs": [{"name": "result", "type": "dict", "required": True}],
                }
            ),
            {"payload": {"probe": True}},
            service_call=service_call,
        )
    )

    assert calls == [("table_queue", "health", {"probe": True})]
    assert output["result"] == {
        "ok": True,
        "service_name": "table_queue",
        "method_name": "health",
        "result": {"probe": True},
    }
    with pytest.raises(RuntimeError, match="only available while a Blueprint ScriptNode is running"):
        blueprint_script_nodes.blueprint_service_call("table_queue", "health", {})


def test_blueprint_service_opens_script_directory_with_system_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[Path] = []
    monkeypatch.setattr(desktop_blueprint_service_module, "_open_path_with_system_default", opened.append)

    result = DesktopBlueprintService().handle_request(
        {
            "command": "blueprint.openScriptInEditor",
            "args": {"projectDir": str(tmp_path), "modulePath": "format_score.py", "editorId": "system"},
        }
    )

    script_dir = tmp_path / ".multi_agent_workspace" / "scripts"
    assert result == {"ok": True, "path": str(script_dir.resolve()), "editorId": "system"}
    assert opened == [script_dir.resolve()]


def test_blueprint_editor_detection_uses_real_vscode_when_code_alias_points_to_cursor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "program-files"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "program-files-x86"))
    vscode_command = tmp_path / "Programs" / "Microsoft VS Code" / "bin" / "code.cmd"
    vscode_command.parent.mkdir(parents=True)
    vscode_command.write_text("", encoding="utf-8")

    def fake_which(command: str) -> str | None:
        if command == "code":
            return r"C:\Users\qiuhaoxuan\AppData\Local\Programs\cursor\resources\app\codeBin\code.cmd"
        if command == "cursor":
            return r"C:\Users\qiuhaoxuan\AppData\Local\Programs\cursor\resources\app\bin\cursor.cmd"
        return None

    monkeypatch.setattr(desktop_blueprint_service_module.shutil, "which", fake_which)

    editors = desktop_blueprint_service_module.list_blueprint_editors()

    assert editors[0]["id"] == "vscode"
    assert editors[0]["command"] == str(vscode_command)
    assert editors[1]["id"] == "cursor"
    assert editors[1]["command"].endswith("cursor.cmd")


def test_blueprint_known_editors_open_in_new_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launched: list[list[str]] = []

    class FakeProcess:
        pass

    def fake_popen(args, **kwargs):  # noqa: ANN001, ANN202
        launched.append([str(arg) for arg in args])
        return FakeProcess()

    monkeypatch.setattr(desktop_blueprint_service_module.subprocess, "Popen", fake_popen)

    desktop_blueprint_service_module._launch_blueprint_editor(
        {"id": "vscode", "command": "code", "args": ["--reuse-window", "--wait"]},
        tmp_path,
    )

    assert launched == [["code", "--new-window", str(tmp_path)]]


def test_blueprint_service_rejects_script_editor_module_path_escape(tmp_path: Path) -> None:
    with pytest.raises(BlueprintServiceError) as exc:
        DesktopBlueprintService().handle_request(
            {
                "command": "blueprint.openScriptInEditor",
                "args": {"projectDir": str(tmp_path), "modulePath": "../format_score.py"},
            }
        )

    assert exc.value.code == "BAD_REQUEST"
    assert "modulePath must stay inside the script directory" in str(exc.value)


def test_blueprint_service_rejects_blank_script_node_name(tmp_path: Path) -> None:
    with pytest.raises(BlueprintServiceError) as exc:
        DesktopBlueprintService().handle_request(
            {"command": "blueprint.createScriptNode", "args": {"projectDir": str(tmp_path), "name": "  "}}
        )

    assert exc.value.code == "BAD_REQUEST"
    assert "name must be a non-empty string" in str(exc.value)


def test_blueprint_service_reports_script_annotation_diagnostics(tmp_path: Path) -> None:
    script_dir = tmp_path / ".multi_agent_workspace" / "scripts"
    script_dir.mkdir(parents=True)
    (script_dir / "bad.py").write_text(
        "\n".join(
            [
                "@blueprint_node",
                "def summarize(count, payload: set) -> tuple:",
                "    return count, payload",
            ]
        ),
        encoding="utf-8",
    )

    result = DesktopBlueprintService().handle_request(
        {"command": "blueprint.scriptNodes", "args": {"projectDir": str(tmp_path)}}
    )

    messages = [item["message"] for item in result["diagnostics"]]
    assert any("missing type annotation" in message and "count" in message for message in messages)
    assert any("unsupported type annotation 'set'" in message for message in messages)
    assert any("unsupported type annotation 'tuple'" in message for message in messages)
    node = result["nodes"][0]
    assert node["inputs"][0] == {"name": "count", "type": "Any", "required": True}
    assert node["inputs"][1] == {"name": "payload", "type": "Any", "required": True}
    assert node["outputs"] == [{"name": "result", "type": "Any", "required": True}]


def test_blueprint_validate_rejects_missing_script_node_function(tmp_path: Path) -> None:
    document = _document(tmp_path)
    document["graph"]["script_nodes"] = {
        "format": {
            "script_id": "missing.py:format_score",
            "module_path": "missing.py",
            "function_name": "format_score",
            "title": "Format score",
            "inputs": [{"name": "count", "type": "int"}],
            "outputs": [{"name": "result", "type": "str"}],
        }
    }
    document["graph"]["edges"] = [
        {"from": "start", "to": "planner", "edge_type": "exec"},
        {"from": "planner", "to": "format", "edge_type": "exec"},
        {"from": "format", "to": "end", "edge_type": "exec"},
    ]

    result = DesktopBlueprintService().handle_request(
        {"command": "blueprint.validate", "args": {"projectDir": str(tmp_path), "document": document}}
    )

    assert result["ok"] is False
    assert "missing script node function" in result["errors"][0]


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


def test_blueprint_service_exposes_run_and_changeset_diff_commands(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "a.txt").write_text("base\n", encoding="utf-8")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    workspace_run = manager.create_run(run_id="run-service-diff", code_mode="project_reference")
    checkout = manager.checkout_agent(workspace_run, "agent-a", checkout_paths=["src/a.txt"])
    (checkout.checkout_dir / "src" / "a.txt").write_text("changed\n", encoding="utf-8")
    result = manager.submit_checkout(workspace_run, checkout, task_id="task-1", summary="change a")

    active_path = workspace_run.path
    stale_workspace_run = RunWorkspace(
        run_id=workspace_run.run_id,
        path=active_path,
        base_dir=active_path / "base",
        integration_dir=active_path / "shared" / "code",
        jobs_dir=active_path / "jobs",
        agents_dir=active_path / "agents",
        shared_dir=active_path / "shared",
        shared_code_dir=active_path / "shared" / "code",
        shared_artifacts_dir=active_path / "shared" / "artifacts",
        shared_reports_dir=active_path / "shared" / "reports",
        shared_locks_dir=active_path / "shared" / ".locks",
        status="running",
        long_term_workspace_root=manager.workspace_root,
        code_mode="project_reference",
    )

    class FakeRuntime:
        archive_manager = manager
        archive_run = workspace_run
        private_context_manager = None
        private_context_run = None

    fake_runtime = FakeRuntime()
    service = DesktopBlueprintService()
    service._runs["run-service-diff"] = DesktopBlueprintRun(
        run_id="run-service-diff",
        project_dir=tmp_path.resolve(),
        blueprint_id="default",
        document=_document(tmp_path),
        graph=None,
        runtime=fake_runtime,
        control=None,
        execution_mode="status",
        created_at=1.0,
        updated_at=1.0,
    )

    summary = service.handle_request({"command": "blueprint.runDiff", "args": {"runId": "run-service-diff"}})
    detail = service.handle_request(
        {
            "command": "blueprint.changesetDiff",
            "args": {"runId": "run-service-diff", "changesetId": result.changeset_id},
        }
    )

    assert summary["ok"] is True
    assert summary["summary"]["accepted"] == 1
    assert summary["acceptedDiffs"][0]["file"] == "src/a.txt"
    assert detail["ok"] is True
    assert detail["changesetId"] == result.changeset_id
    assert detail["diffs"][0]["file"] == "src/a.txt"

    archive_path = manager.archive_run(workspace_run)
    fake_runtime.archive_run = stale_workspace_run
    archived_summary = service.handle_request({"command": "blueprint.runDiff", "args": {"runId": "run-service-diff"}})
    assert archived_summary["summary"]["accepted"] == 1
    assert archived_summary["acceptedDiffs"][0]["file"] == "src/a.txt"
    assert fake_runtime.archive_run.path == archive_path

    assert result.archive_path is not None
    (archive_path / "changesets" / result.changeset_id / "patch.diff").unlink()
    with pytest.raises(BlueprintServiceError) as exc:
        service.handle_request(
            {
                "command": "blueprint.changesetDiff",
                "args": {"runId": "run-service-diff", "changesetId": result.changeset_id},
            }
        )
    assert exc.value.code == "CHANGESET_PATCH_MISSING"


def test_blueprint_service_exposes_rollback_and_restore_commands(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "a.txt").write_text("base\n", encoding="utf-8")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    workspace_run = manager.create_run(run_id="run-service-rollback-workspace", code_mode="project_reference")
    checkout = manager.checkout_agent(workspace_run, "agent-a", checkout_paths=["src/a.txt"])
    (checkout.checkout_dir / "src" / "a.txt").write_text("changed\n", encoding="utf-8")
    result = manager.submit_checkout(workspace_run, checkout, task_id="task-1", summary="change a")

    class FakeRuntime:
        archive_manager = manager
        archive_run = workspace_run
        private_context_manager = None
        private_context_run = None

        def status_snapshot(self, graph: object | None = None) -> dict:
            return {"run": {"status": "completed"}}

    service = DesktopBlueprintService()
    service._runs["run-service-rollback"] = DesktopBlueprintRun(
        run_id="run-service-rollback",
        project_dir=tmp_path.resolve(),
        blueprint_id="default",
        document=_document(tmp_path),
        graph=None,
        runtime=FakeRuntime(),
        control=None,
        execution_mode="status",
        created_at=1.0,
        updated_at=1.0,
    )

    rollback = service.handle_request(
        {
            "command": "blueprint.rollbackChangesets",
            "args": {
                "runId": "run-service-rollback",
                "toChangesetId": result.changeset_id,
                "reason": "test",
            },
        }
    )
    rolled_diff = service.handle_request({"command": "blueprint.runDiff", "args": {"runId": "run-service-rollback"}})

    assert rollback["ok"] is True
    assert rollback["rollback"]["status"] == "rolled_back"
    assert (tmp_path / "src" / "a.txt").read_text(encoding="utf-8") == "base\n"
    assert rolled_diff["summary"]["rolledBack"] == 1

    restore = service.handle_request(
        {
            "command": "blueprint.restoreRollback",
            "args": {
                "runId": "run-service-rollback",
                "rollbackId": rollback["rollback"]["rollbackId"],
            },
        }
    )

    assert restore["ok"] is True
    assert restore["restore"]["status"] == "restored"
    assert (tmp_path / "src" / "a.txt").read_text(encoding="utf-8") == "changed\n"


def test_blueprint_service_rejects_rollback_for_active_run(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "a.txt").write_text("base\n", encoding="utf-8")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    workspace_run = manager.create_run(run_id="run-service-active-workspace", code_mode="project_reference")
    checkout = manager.checkout_agent(workspace_run, "agent-a", checkout_paths=["src/a.txt"])
    (checkout.checkout_dir / "src" / "a.txt").write_text("changed\n", encoding="utf-8")
    result = manager.submit_checkout(workspace_run, checkout)

    class FakeRuntime:
        archive_manager = manager
        archive_run = workspace_run
        private_context_manager = None
        private_context_run = None

        def status_snapshot(self, graph: object | None = None) -> dict:
            return {"run": {"status": "running"}}

    service = DesktopBlueprintService()
    service._runs["run-service-active"] = DesktopBlueprintRun(
        run_id="run-service-active",
        project_dir=tmp_path.resolve(),
        blueprint_id="default",
        document=_document(tmp_path),
        graph=None,
        runtime=FakeRuntime(),
        control=None,
        execution_mode="status",
        created_at=1.0,
        updated_at=1.0,
    )

    with pytest.raises(BlueprintServiceError) as exc:
        service.handle_request(
            {
                "command": "blueprint.rollbackChangesets",
                "args": {"runId": "run-service-active", "toChangesetId": result.changeset_id},
            }
        )

    assert exc.value.code == "RUN_NOT_TERMINAL"


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


def test_blueprint_service_detects_python_for_plugin_workbench(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    detected_python = tmp_path / "Python313" / "python.exe"

    def fake_run(args, **kwargs):  # noqa: ANN001, ANN202
        command = [str(arg) for arg in args]
        calls.append(command)
        if command[0] == "python":
            return desktop_blueprint_service_module.subprocess.CompletedProcess(
                command,
                0,
                stdout=f"{detected_python}\n",
                stderr="",
            )
        return desktop_blueprint_service_module.subprocess.CompletedProcess(command, 1, stdout="", stderr="missing")

    monkeypatch.setattr(desktop_blueprint_service_module.subprocess, "run", fake_run)

    result = DesktopBlueprintService().handle_request(
        {
            "command": "blueprint.detectPython",
            "args": {
                "projectDir": str(tmp_path),
                "pythonCommand": r"Z:\missing\python.exe",
            },
        }
    )

    assert result == {"ok": True, "pythonCommand": str(detected_python), "source": "PATH python"}
    assert calls[0] == ["python", "-c", "import sys; print(sys.executable)"]


def test_blueprint_service_detect_python_uses_configured_command_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_python = tmp_path / "custom python" / "python.exe"
    configured_python.parent.mkdir()
    configured_python.write_text("", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):  # noqa: ANN001, ANN202
        command = [str(arg) for arg in args]
        calls.append(command)
        return desktop_blueprint_service_module.subprocess.CompletedProcess(
            command,
            0,
            stdout=f"{configured_python}\n",
            stderr="",
        )

    monkeypatch.setattr(desktop_blueprint_service_module.subprocess, "run", fake_run)

    result = DesktopBlueprintService().handle_request(
        {
            "command": "blueprint.detectPython",
            "args": {
                "projectDir": str(tmp_path),
                "pythonCommand": f'"{configured_python}" -E',
            },
        }
    )

    assert result == {
        "ok": True,
        "pythonCommand": str(configured_python),
        "source": "blueprint common config python_path",
    }
    assert calls == [[str(configured_python), "-E", "-c", "import sys; print(sys.executable)"]]


def test_gulicode_bp_mcp_whitelists_python_detection_command() -> None:
    source = (Path(__file__).resolve().parent / "plugins" / "gulicode-bp" / "mcp" / "gulicode_bp_mcp.py").read_text(
        encoding="utf-8"
    )

    assert '"blueprint.detectPython"' in source
    assert '"blueprint.listModels"' in source
    assert '"blueprint.listRules"' in source
    assert '"blueprint.planning.submit"' not in source
    assert "blueprint_take_planning_request" not in source
    assert "blueprint_complete_planning_request" not in source
    assert "blueprint_fail_planning_request" not in source
    assert "MCP_STATUS_PATH" in source
    assert "gulicode-bp-mcp.log" in source
    assert "_write_mcp_status(" in source
    assert "MCP_HEARTBEAT_INTERVAL_SECONDS" in source
    assert "MCP_HEARTBEAT_STALE_AFTER_SECONDS" in source
    assert "_start_mcp_status_heartbeat(" in source
    assert '"mcp-running"' in source
    assert "SingletonProxyState" in source
    assert "SingletonServiceServer" in source
    assert "GULICODE_BP_SINGLETON_ROLE" in source
    assert "service.startWorkbench" in source

    singleton_source = (
        Path(__file__).resolve().parent / "plugins" / "gulicode-bp" / "mcp" / "gulicode_bp_singleton.py"
    ).read_text(encoding="utf-8")
    assert "service.lock" in singleton_source
    assert "service.json" in singleton_source
    assert "service.log.jsonl" in singleton_source


def test_gulicode_bp_plugin_manifest_default_prompts_stay_within_codex_limit() -> None:
    manifest_path = Path(__file__).resolve().parent / "plugins" / "gulicode-bp" / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    default_prompts = manifest["interface"]["defaultPrompt"]
    assert len(default_prompts) <= 3


def test_gulicode_bp_mcp_popo_robot_route_commands_are_internal_only() -> None:
    module = _load_gulicode_bp_mcp_module()
    robot_route_commands = {
        "blueprint.popo.callbackConfig",
        "blueprint.popo.robots",
        "blueprint.popo.robot.save",
        "blueprint.popo.robot.delete",
        "blueprint.popo.robot.enabled",
    }

    assert robot_route_commands.issubset(module.INTERNAL_COMMANDS)
    assert robot_route_commands.isdisjoint(module.ALLOWED_COMMANDS)


def test_gulicode_bp_mcp_planning_thread_context_does_not_leak_into_workbench_config(tmp_path: Path, monkeypatch) -> None:
    module = _load_gulicode_bp_mcp_module()
    ctx = SimpleNamespace(request_context=SimpleNamespace(meta=SimpleNamespace(model_extra={"threadId": "thread-meta"})))
    assert module._planning_thread_id_from_context(ctx) == "thread-meta"
    captured: dict[str, str] = {}

    class FakeWorkbench:
        def __init__(
            self,
            service,
            request_fn,
            *,
            default_project_dir,
                default_blueprint_id,
                collaboration_url,
                ensure_collaboration_fn,
                popo_status_fn=None,
            ):
            captured["default_project_dir"] = default_project_dir
            captured["default_blueprint_id"] = default_blueprint_id
            self.default_project_dir = default_project_dir
            self.default_blueprint_id = default_blueprint_id
            self.url = f"http://127.0.0.1:1/blueprint-window/{default_blueprint_id}"

        def start(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(module, "WorkbenchServer", FakeWorkbench)
    state = module.PluginState()
    state.ensure_collaboration_server = lambda: None
    try:
        opened = state.start_workbench(str(tmp_path), "default", planning_thread_id="thread-meta")
        assert "planningThreadId" not in opened
        assert captured["default_project_dir"] == str(tmp_path)
        assert captured["default_blueprint_id"] == "default"
    finally:
        state.close()


def test_gulicode_bp_mcp_persistent_workbench_process_keeps_refreshable_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_gulicode_bp_mcp_module()
    popen_called = False

    class FakeWorkbench:
        def __init__(
            self,
            service,
            request_fn,
            *,
            default_project_dir="",
            default_blueprint_id="default",
            **kwargs,
        ):  # noqa: ANN001, ANN202
            self.default_project_dir = default_project_dir
            self.default_blueprint_id = default_blueprint_id
            self.url = "http://127.0.0.1:54321/project/blueprint-window/new1"

        def start(self):
            return None

        def close(self):
            return None

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        nonlocal popen_called
        popen_called = True
        raise AssertionError("start_persistent_workbench must not spawn start_workbench.py")

    monkeypatch.setattr(module, "PERSISTENT_WORKBENCH_LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(module, "WorkbenchServer", FakeWorkbench)
    monkeypatch.setattr(module.PluginState, "ensure_collaboration_server", lambda self: None)
    monkeypatch.setattr(module.subprocess, "Popen", fail_popen)

    state = module.PluginState()
    state.persistent_workbench_ready_path = tmp_path / "ready.json"
    try:
        first = state.start_persistent_workbench(str(tmp_path), "new1", planning_thread_id="thread-a")
        second = state.start_persistent_workbench(str(tmp_path), "new1", planning_thread_id="thread-a")

        assert first["persistent"] is True
        assert first["reused"] is False
        assert second["reused"] is True
        assert first["pid"] == os.getpid()
        ready = json.loads(state.persistent_workbench_ready_path.read_text(encoding="utf-8"))
        assert ready["url"] == first["url"]
        assert "planningThreadId" not in ready
        assert popen_called is False
    finally:
        state.close()


def test_gulicode_bp_mcp_removes_planning_and_start_tools_but_keeps_session_commands() -> None:
    module = _load_gulicode_bp_mcp_module()
    source = (Path(__file__).resolve().parent / "plugins" / "gulicode-bp" / "mcp" / "gulicode_bp_mcp.py").read_text(
        encoding="utf-8"
    )
    removed = [
        "PLANNING_REQUESTS_PATH",
        "planning_requests.json",
        '"blueprint.planning.submit"',
        '"blueprint.planning.status"',
        '"blueprint.planning.cancel"',
        '"blueprint.plan.create"',
        '"blueprint.plan.validate"',
        '"blueprint.start"',
        "blueprint_take_planning_request",
        "blueprint_complete_planning_request",
        "blueprint_fail_planning_request",
        "def blueprint_plan_create",
        "def blueprint_plan_validate",
        "def blueprint_start(",
        "service.takePlanningRequest",
        "service.completePlanningRequest",
        "service.failPlanningRequest",
    ]
    for text in removed:
        assert text not in source
    for text in [
        '"blueprint.sessions.list"',
        '"blueprint.sessions.excelHistoryList"',
        '"blueprint.sessions.excelHistory"',
        '"blueprint.sessions.delete"',
        '"blueprint.sessions.clear"',
        '"blueprint.sessions.message"',
        '"blueprint.runtime.setStartAgent"',
        '"blueprint.runtime.executePlan"',
        "def blueprint_set_start_agent",
        "def blueprint_execute_plan",
        "def blueprint_list_runs",
        "def blueprint_status",
        "def blueprint_recent_events",
    ]:
        assert text in source
    write_commands = source[source.index("WRITE_COMMANDS = {") : source.index("CONTROL_COMMANDS = {")]
    assert '"blueprint.sessions.excelHistoryList"' not in write_commands
    assert '"blueprint.sessions.excelHistory"' not in write_commands

    state = module.PluginState()
    try:
        with pytest.raises(module.BlueprintServiceError) as exc:
            state.request("blueprint.planning.submit", {})
        assert exc.value.code == "UNKNOWN_COMMAND"
    finally:
        state.close()


def test_gulicode_bp_plugin_state_starts_planning_table_skill_update_watcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_gulicode_bp_mcp_module()
    if hasattr(module.state, "close"):
        module.state.close()
    calls: list[tuple[str, str]] = []

    class FakeManager:
        def discover(self) -> dict[str, Any]:
            return {"services": [{"service_name": "planning_table_skill_update"}]}

        def start(self, service_name: str) -> dict[str, Any]:
            calls.append(("start", service_name))
            return {"ok": True, "alreadyRunning": False}

        def stop_all(self) -> dict[str, Any]:
            calls.append(("stop_all", "all"))
            return {"ok": True}

    class FakeService:
        def __init__(self, *, resident_services_data_dir=None) -> None:  # noqa: ANN001
            self.manager = FakeManager()

        def start_table_queue_notification_watcher(self) -> None:
            calls.append(("watcher", "table_queue"))

        def start_planning_table_skill_update_notification_watcher(self) -> None:
            calls.append(("watcher", "planning_table_skill_update"))

        def resident_service_manager(self) -> FakeManager:
            return self.manager

        def close(self) -> None:
            calls.append(("close", "service"))

    monkeypatch.setenv("GULICODE_BP_AUTOSTART_RESIDENTS_IN_TESTS", "1")
    monkeypatch.setattr(module, "DesktopBlueprintService", FakeService)
    monkeypatch.setattr(module, "append_service_log", lambda *args, **kwargs: None)

    state = module.PluginState()
    try:
        assert ("watcher", "table_queue") in calls
        assert ("watcher", "planning_table_skill_update") in calls
        assert ("start", "planning_table_skill_update") in calls
    finally:
        state.close()


def test_blueprint_service_preserves_settings_and_applies_common_config_paths(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    rules = project / "rules"
    project.mkdir()
    rules.mkdir()
    (rules / "policy.md").write_text("# Policy\n", encoding="utf-8")

    document = _document(project)
    document["id"] = "settings"
    document["name"] = "Settings"
    document["graph"]["common_nodes"] = {
        "clock": {"node_id": "clock", "kind": "tick", "every_n_seconds": 11}
    }
    document["graph"]["agent_nodes"]["planner"].update(
        {
            "prompt": "Plan with saved settings.",
            "run_prompt": "Use the saved prompt once.",
            "execution_mode": "nonblocking",
            "cli_kind": "codex",
            "model": "gpt-5.4",
            "skills": ["business-skill"],
            "skill_selection": {"mode": "selected", "skill_hashes": ["business-skill"]},
            "rule_paths": ["policy.md"],
            "timeout_sec": 321,
            "prompt_via_file": "always",
            "adapter_options": {"temperature": 0.2, "retry": True},
            "extra_env": {"GULI_SETTING": "1"},
            "external": True,
        }
    )
    document["graph"]["edges"] = [
        {
            "from": "clock",
            "to": "planner",
            "edge_type": "exec",
            "output_port": "tick",
            "input_port": "in",
        }
    ]
    document["ui"]["config"] = {
        "python_path": sys.executable,
        "project_workdir": str(project),
        "skill_dir": str(project / "skills"),
        "rule_dir": str(rules),
    }
    document["ui"]["nodes"]["clock"] = {"x": 312, "y": 120}
    document["ui"]["viewport"] = {"x": 33, "y": -12, "zoom": 1.25}
    document["ui"]["selection"] = {"type": "node", "id": "clock"}
    document["ui"]["inspector"] = {"type": "node", "id": "planner"}

    saved = service.save_blueprint(project, document)
    opened = service.open_blueprint(project, "settings")

    assert opened == saved
    assert opened["ui"]["config"]["project_workdir"] == str(project)
    assert opened["ui"]["config"]["rule_dir"] == str(rules)
    assert opened["graph"]["common_nodes"]["clock"]["every_n_seconds"] == 11
    assert opened["graph"]["agent_nodes"]["planner"]["run_prompt"] == "Use the saved prompt once."
    assert opened["graph"]["agent_nodes"]["planner"]["rule_paths"] == ["policy.md"]
    assert opened["graph"]["agent_nodes"]["planner"]["adapter_options"] == {"temperature": 0.2, "retry": True}
    assert opened["graph"]["agent_nodes"]["planner"]["extra_env"] == {"GULI_SETTING": "1"}
    assert opened["ui"]["nodes"]["clock"] == {"x": 312, "y": 120}
    assert opened["ui"]["viewport"] == {"x": 33, "y": -12, "zoom": 1.25}
    assert opened["ui"]["selection"] == {"type": "node", "id": "clock"}
    assert opened["ui"]["inspector"] == {"type": "node", "id": "planner"}

    graph = service._blueprint_graph_for_plan(project, "settings")
    assert Path(graph.agent_nodes["planner"].cwd) == project.resolve()
    assert [Path(path) for path in graph.agent_nodes["planner"].rule_paths] == [(rules / "policy.md").resolve()]
    assert graph.common_nodes["clock"].every_n_seconds == 11


def test_blueprint_service_lists_default_codex_home_skills(
    tmp_path: Path,
    monkeypatch,
) -> None:
    codex_home = tmp_path / "codex-home"
    skill = codex_home / "skills" / "business-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\n"
        "name: business-skill\n"
        "description: >-\n"
        "  Business skill description\n"
        "  from Codex home\n"
        "---\n"
        "# Business Skill\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    service = DesktopBlueprintService()
    response = service.handle_request({"command": "blueprint.listSkills", "args": {}})

    assert response == {
        "ok": True,
        "skills": [
            {
                "value": "business-skill",
                "label": "business-skill",
                "description": "Business skill description from Codex home",
            }
        ],
    }


def test_blueprint_service_lists_skills_from_multiple_dirs_with_first_duplicate_winning(tmp_path: Path) -> None:
    first = tmp_path / "skills-a"
    second = tmp_path / "skills-b"
    (first / "business-skill").mkdir(parents=True)
    (second / "business-skill").mkdir(parents=True)
    (second / "review-skill").mkdir(parents=True)
    (first / "business-skill" / "SKILL.md").write_text(
        "---\n"
        "description: First business skill\n"
        "---\n"
        "# Business\n",
        encoding="utf-8",
    )
    (second / "business-skill" / "SKILL.md").write_text(
        "---\n"
        "description: Second business skill\n"
        "---\n",
        encoding="utf-8",
    )
    (second / "review-skill" / "SKILL.md").write_text("# Review skill\n", encoding="utf-8")

    response = DesktopBlueprintService().handle_request(
        {"command": "blueprint.listSkills", "args": {"dirs": [str(first), str(second)]}}
    )

    assert response == {
        "ok": True,
        "skills": [
            {
                "value": "business-skill",
                "label": "business-skill",
                "description": "First business skill",
            },
            {
                "value": "review-skill",
                "label": "review-skill",
                "description": "Review skill",
            },
        ],
    }


def test_blueprint_service_lists_rules_from_multiple_dirs_with_absolute_values(tmp_path: Path) -> None:
    first = tmp_path / "rules-a"
    second = tmp_path / "rules-b"
    first.mkdir()
    second.mkdir()
    (first / "policy.md").write_text("# Policy A\n", encoding="utf-8")
    (second / "policy.md").write_text("# Policy B\n", encoding="utf-8")
    (second / "review.yaml").write_text("review: true\n", encoding="utf-8")

    response = DesktopBlueprintService().handle_request(
        {"command": "blueprint.listRules", "args": {"dirs": [str(first), str(second)]}}
    )

    assert response == {
        "ok": True,
        "rules": [
            {
                "value": str((first / "policy.md").resolve()),
                "label": "policy.md",
                "description": str(first.resolve()),
            },
            {
                "value": str((second / "policy.md").resolve()),
                "label": "policy.md",
                "description": str(second.resolve()),
            },
            {
                "value": str((second / "review.yaml").resolve()),
                "label": "review.yaml",
                "description": str(second.resolve()),
            },
        ],
    }


def test_blueprint_service_resolves_rule_dirs_and_absolute_rule_paths(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    first = project / "rules-a"
    second = project / "rules-b"
    project.mkdir()
    first.mkdir()
    second.mkdir()
    (first / "legacy.md").write_text("# Legacy\n", encoding="utf-8")
    absolute_rule = second / "absolute.md"
    absolute_rule.write_text("# Absolute\n", encoding="utf-8")

    document = _document(project)
    document["id"] = "multi-rules"
    document["graph"]["agent_nodes"]["planner"]["rule_paths"] = ["legacy.md", str(absolute_rule)]
    document["ui"]["config"] = {
        "python_path": sys.executable,
        "project_workdir": str(project),
        "rule_dir": str(first),
        "rule_dirs": [str(first), str(second)],
    }
    service.save_blueprint(project, document)

    graph = service._blueprint_graph_for_plan(project, "multi-rules")

    assert [Path(path) for path in graph.agent_nodes["planner"].rule_paths] == [
        (first / "legacy.md").resolve(),
        absolute_rule.resolve(),
    ]


def test_blueprint_service_lists_codex_models_from_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):  # noqa: ANN001, ANN202
        command = [str(arg) for arg in args]
        calls.append(command)
        return desktop_blueprint_service_module.subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "models": [
                        {"slug": "gpt-5.5"},
                        {"slug": "gpt-5.4"},
                        {"slug": ""},
                        {"id": "ignored"},
                        {"slug": "gpt-5.5"},
                    ]
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(desktop_blueprint_service_module.subprocess, "run", fake_run)

    response = DesktopBlueprintService().handle_request({"command": "blueprint.listModels", "args": {"cliKind": "codex"}})

    assert response == {"ok": True, "models": ["gpt-5.5", "gpt-5.4"]}
    assert calls == [["codex", "debug", "models"]]


def test_blueprint_service_model_listing_returns_empty_for_unsupported_cli_kind() -> None:
    response = DesktopBlueprintService().handle_request(
        {"command": "blueprint.listModels", "args": {"cliKind": "unsupported"}}
    )

    assert response == {"ok": True, "models": []}


def test_blueprint_service_model_listing_retries_codex_cmd_on_windows_oserror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):  # noqa: ANN001, ANN202
        command = [str(arg) for arg in args]
        calls.append(command)
        if command[0] == "codex":
            raise OSError(5, "Access is denied")
        return desktop_blueprint_service_module.subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"models": [{"slug": "gpt-5.5"}]}),
            stderr="",
        )

    monkeypatch.setattr(desktop_blueprint_service_module.sys, "platform", "win32")
    monkeypatch.setattr(desktop_blueprint_service_module.subprocess, "run", fake_run)

    response = DesktopBlueprintService().handle_request({"command": "blueprint.listModels", "args": {}})

    assert response == {"ok": True, "models": ["gpt-5.5"]}
    assert calls == [["codex", "debug", "models"], ["codex.cmd", "debug", "models"]]


def test_blueprint_service_model_listing_returns_empty_on_cli_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_invalid_json(args, **kwargs):  # noqa: ANN001, ANN202
        return desktop_blueprint_service_module.subprocess.CompletedProcess(args, 0, stdout="{not json", stderr="")

    monkeypatch.setattr(desktop_blueprint_service_module.subprocess, "run", fake_invalid_json)
    assert DesktopBlueprintService().handle_request({"command": "blueprint.listModels", "args": {}}) == {
        "ok": True,
        "models": [],
    }

    def fake_nonzero(args, **kwargs):  # noqa: ANN001, ANN202
        return desktop_blueprint_service_module.subprocess.CompletedProcess(args, 1, stdout="", stderr="missing auth")

    monkeypatch.setattr(desktop_blueprint_service_module.subprocess, "run", fake_nonzero)
    assert DesktopBlueprintService().handle_request({"command": "blueprint.listModels", "args": {}}) == {
        "ok": True,
        "models": [],
    }

    def fake_timeout(args, **kwargs):  # noqa: ANN001, ANN202
        raise desktop_blueprint_service_module.subprocess.TimeoutExpired(args, 15)

    monkeypatch.setattr(desktop_blueprint_service_module.subprocess, "run", fake_timeout)
    assert DesktopBlueprintService().handle_request({"command": "blueprint.listModels", "args": {}}) == {
        "ok": True,
        "models": [],
    }


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

        duplicate = service.start_blueprint_run(project, "default", _plan(), execution_mode="status")
        assert duplicate["ok"] is True
        assert duplicate["alreadyActive"] is True
        assert duplicate["runId"] == started["runId"]
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


def test_blueprint_service_agent_info_does_not_hold_service_lock_during_runtime_calls(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()

    class BlockingRuntime:
        def __init__(self) -> None:
            self.entered = threading.Event()
            self.release = threading.Event()
            self.message_journal = []
            self.events = []

        def status_snapshot(self, *, graph=None, recent_events_limit=None):
            self.entered.set()
            assert self.release.wait(timeout=5)
            return {
                "run": {"status": "running"},
                "agents": {"planner": {"agent_id": "agent-planner", "state": "idle"}},
                "queues": {"by_agent": {"planner": []}},
            }

        def agent_stream_events_after(self, **kwargs):
            return []

    runtime = BlockingRuntime()
    node = SimpleNamespace(runtime_agent_id="agent-planner", to_dict=lambda: {"node_id": "planner"})
    graph = SimpleNamespace(agent_nodes={"planner": node})
    run = DesktopBlueprintRun(
        run_id="run-agent-info-lock",
        project_dir=project,
        blueprint_id="default",
        document={},
        graph=graph,
        runtime=runtime,
        control=object(),
        execution_mode="status",
        created_at=1.0,
        updated_at=1.0,
    )
    with service._lock:
        service._runs[run.run_id] = run

    result: list[dict[str, Any]] = []
    errors: list[BaseException] = []

    def call_agent_info() -> None:
        try:
            result.append(service.agent_info("planner", run_id=run.run_id))
        except BaseException as exc:  # pragma: no cover - assertion detail
            errors.append(exc)

    thread = threading.Thread(target=call_agent_info)
    thread.start()
    assert runtime.entered.wait(timeout=2)
    lock_acquired = service._lock.acquire(blocking=False)
    if lock_acquired:
        service._lock.release()
    runtime.release.set()
    thread.join(timeout=5)

    assert lock_acquired is True
    assert errors == []
    assert result[0]["runtime"]["agent_id"] == "agent-planner"


def test_blueprint_service_status_does_not_hold_service_lock_during_runtime_calls(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()

    class BlockingRuntime:
        def __init__(self) -> None:
            self.entered = threading.Event()
            self.release = threading.Event()

        def status_snapshot(self, *, graph=None, recent_events_limit=None):
            self.entered.set()
            assert self.release.wait(timeout=5)
            return {"run": {"status": "running"}, "recent_events": []}

        def explain_status(self, *, graph=None):
            return {"status": "running", "summary": "ok"}

    runtime = BlockingRuntime()
    run = DesktopBlueprintRun(
        run_id="run-status-lock",
        project_dir=project,
        blueprint_id="default",
        document={},
        graph=SimpleNamespace(agent_nodes={}),
        runtime=runtime,
        control=object(),
        execution_mode="status",
        created_at=1.0,
        updated_at=1.0,
    )
    with service._lock:
        service._runs[run.run_id] = run

    result: list[dict[str, Any]] = []
    errors: list[BaseException] = []

    def call_status() -> None:
        try:
            result.append(service.status_blueprint_run(run.run_id))
        except BaseException as exc:  # pragma: no cover - assertion detail
            errors.append(exc)

    thread = threading.Thread(target=call_status)
    thread.start()
    assert runtime.entered.wait(timeout=2)
    lock_acquired = service._lock.acquire(blocking=False)
    if lock_acquired:
        service._lock.release()
    runtime.release.set()
    thread.join(timeout=5)

    assert lock_acquired is True
    assert errors == []
    assert result[0]["status"]["run"]["status"] == "running"


def test_blueprint_agent_stream_runtime_timeout_does_not_block_forever(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()
    run = DesktopBlueprintRun(
        run_id="run-stream-timeout",
        project_dir=project,
        blueprint_id="default",
        document={},
        graph=SimpleNamespace(agent_nodes={}),
        runtime=object(),
        control=object(),
        execution_mode="live",
        created_at=1.0,
        updated_at=1.0,
    )
    with service._lock:
        service._runs[run.run_id] = run
    calls: list[float | None] = []

    def fake_runtime_call(active_run: DesktopBlueprintRun, fn, *, timeout=None):
        calls.append(timeout)
        if len(calls) == 1:
            raise desktop_blueprint_service_module.FutureTimeoutError()
        return {"status": "completed"}

    monkeypatch.setattr(service, "_runtime_call", fake_runtime_call)

    service.stream_agent_events(run.run_id, send=lambda event: pytest.fail("no events expected"))

    assert calls == [
        desktop_blueprint_service_module.LIVE_AGENT_STREAM_READ_TIMEOUT_SECONDS,
        desktop_blueprint_service_module.LIVE_AGENT_STREAM_READ_TIMEOUT_SECONDS,
    ]


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
            self.script_calls = []

        def handle_request(self, payload):
            self.requests.append(payload)
            if (
                payload.get("command") == "join.contribute"
                and payload.get("args", {}).get("join_id") == "out-batch"
            ):
                raise KeyError("unknown join barrier: out-batch")
            return {"ok": True, "payload": payload}

        async def call_script_node(self, source_node_id, function_name, arguments, *, script_node_id=None, batch_id=None):
            self.script_calls.append(
                {
                    "source_node_id": source_node_id,
                    "function_name": function_name,
                    "arguments": dict(arguments),
                    "script_node_id": script_node_id,
                    "batch_id": batch_id,
                }
            )
            return {"ok": True, "script_call": self.script_calls[-1]}

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

    script_call = asyncio.run(
        handle._ordinary_blueprint_script_call(
            scope,
            function_name="format_score",
            arguments={"count": 3},
            script_node_id="format",
            batch_id=None,
        )
    )
    assert script_call["ok"] is True
    assert control.script_calls[-1] == {
        "source_node_id": "planner",
        "function_name": "format_score",
        "arguments": {"count": 3},
        "script_node_id": "format",
        "batch_id": "batch-1",
    }

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


def test_run_mcp_provisions_full_agent_message_only_context(tmp_path: Path) -> None:
    class FakeWorkspaceRPCServer:
        def __init__(self) -> None:
            self.tokens = []

        def token_for(self, agent_id):
            self.tokens.append(agent_id)
            return f"token-for-{agent_id}"

    class FullAgentNode:
        node_id = "shell"
        runtime_agent_id = "agent-shell"
        node_type = "agent"
        access_policy = {
            "direct_project_io": True,
            "outside_project_io": True,
            "unrestricted_commands": True,
            "disable_sandbox": True,
            "framework_message_tools": True,
        }

    rpc = FakeWorkspaceRPCServer()
    handle = RunMCPRuntimeHandle(
        run_id="run-1",
        runtime=object(),
        control=object(),
        graph=object(),
        workspace_rpc_server=rpc,
        manager=object(),
        workspace_run=object(),
        runtime_loop=None,
    )

    context = handle.provision_context_for_node(
        node=FullAgentNode(),
        private_dir=tmp_path / "support",
        checkout_dir=tmp_path / "project",
        codex_home=tmp_path / "support" / "codex_home",
    )

    assert context["server_kind"] == "ordinary"
    assert context["server_name"] == "framework_ordinary"
    assert context["tools"] == [
        "agent_dispatch",
        "agent_context",
        "blueprint_script_call",
        "blueprint_service_docs",
        "blueprint_service_call",
        "agent_task_status",
        "join_contribute",
    ]
    assert "workspace_checkout" not in context["tools"]
    assert "workspace_submit" not in context["tools"]
    assert rpc.tokens == []
    scope = handle.token_store.authenticate(
        server_kind="ordinary",
        token=context["bearer_token"],
        session_id=None,
    )
    assert scope.workspace_rpc_token is None
    assert scope.checkout_dir is None
    assert scope.private_dir is None
    assert scope.allowed_tools == context["tools"]


def test_run_mcp_session_termination_tool_is_not_exposed_to_agents(tmp_path: Path) -> None:
    class FakeManager:
        def __init__(self) -> None:
            self.records = []

        def _record_shared_manifest(self, run, event_type, payload):
            self.records.append((event_type, payload))

    class FakeControl:
        def __init__(self) -> None:
            self.requests = []

        def handle_request(self, payload):
            self.requests.append(payload)
            return {"ok": True}

    def full_agent(node_id: str, agent_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            node_id=node_id,
            runtime_agent_id=agent_id,
            node_type="agent",
            access_policy={"framework_message_tools": True},
        )

    def worker_agent(node_id: str, agent_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            node_id=node_id,
            runtime_agent_id=agent_id,
            node_type="worker_agent",
            access_policy={"framework_message_tools": True},
        )

    manager = FakeManager()
    control = FakeControl()
    handle = RunMCPRuntimeHandle(
        run_id="run-1",
        runtime=object(),
        control=control,
        graph=object(),
        workspace_rpc_server=SimpleNamespace(token_for=lambda agent_id: f"token-{agent_id}"),
        manager=manager,
        workspace_run=object(),
        runtime_loop=None,
    )
    handle.enable_blueprint_session_termination(start_node_id="planner", session_key="main+default")

    reviewer_context = handle.provision_context_for_node(
        node=full_agent("reviewer", "agent-reviewer"),
        private_dir=tmp_path / "reviewer-private",
        checkout_dir=tmp_path / "project",
        codex_home=tmp_path / "reviewer-private" / "codex_home",
    )
    worker_context = handle.provision_context_for_node(
        node=worker_agent("worker", "agent-worker"),
        private_dir=tmp_path / "worker-private",
        checkout_dir=tmp_path / "project",
        codex_home=tmp_path / "worker-private" / "codex_home",
    )
    planner_context = handle.provision_context_for_node(
        node=full_agent("planner", "agent-planner"),
        private_dir=tmp_path / "planner-private",
        checkout_dir=tmp_path / "project",
        codex_home=tmp_path / "planner-private" / "codex_home",
    )
    handle.token_store.update_message_context(
        agent_node_id="planner",
        agent_id="agent-planner",
        current_message_id="msg-1",
        outgoing_batch_id=None,
        required_outgoing_targets=[],
        timeout_sec=60,
    )

    planner_scope = handle.token_store.authenticate(
        server_kind="ordinary",
        token=planner_context["bearer_token"],
        session_id=None,
    )

    assert "blueprint_terminate_session" not in reviewer_context["tools"]
    assert "blueprint_terminate_session" not in worker_context["tools"]
    assert "blueprint_terminate_session" not in planner_context["tools"]
    assert "runtime_end" not in reviewer_context["tools"]
    assert "runtime_end" not in worker_context["tools"]
    assert "runtime_end" not in planner_context["tools"]
    assert "blueprint_end" not in planner_context["tools"]
    assert "blueprint_terminate_session" not in planner_scope.allowed_tools
    assert handle.token_store.closed is False
    assert manager.records == []


def test_run_mcp_session_history_tools_keep_excel_history_start_agent_scoped(tmp_path: Path) -> None:
    class FakeManager:
        def __init__(self) -> None:
            self.records = []

        def _record_shared_manifest(self, run, event_type, payload):
            self.records.append((event_type, payload))

    def full_agent(node_id: str, agent_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            node_id=node_id,
            runtime_agent_id=agent_id,
            node_type="agent",
            access_policy={"framework_message_tools": True},
        )

    calls: list[dict[str, Any]] = []

    def query_callback(
        *,
        start_time: str = "",
        end_time: str = "",
        workbook: str = "",
        field: str = "",
        category: str = "xltool",
        limit: int = 50,
        session_key: str,
        agent_node_id: str,
        agent_id: str,
    ):
        calls.append(
            {
                "start_time": start_time,
                "end_time": end_time,
                "workbook": workbook,
                "field": field,
                "category": category,
                "limit": limit,
                "session_key": session_key,
                "agent_node_id": agent_node_id,
                "agent_id": agent_id,
            }
        )
        return {"ok": True, "records": [], "count": 0}

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
        query_excel_history_callback=query_callback,
    )
    handle.enable_session_history_tools(start_node_id="planner", session_key="bps_000000000000000000000001")

    reviewer_context = handle.provision_context_for_node(
        node=full_agent("reviewer", "agent-reviewer"),
        private_dir=tmp_path / "reviewer-private",
        checkout_dir=tmp_path / "project",
        codex_home=tmp_path / "reviewer-private" / "codex_home",
    )
    planner_context = handle.provision_context_for_node(
        node=full_agent("planner", "agent-planner"),
        private_dir=tmp_path / "planner-private",
        checkout_dir=tmp_path / "project",
        codex_home=tmp_path / "planner-private" / "codex_home",
    )
    reviewer_scope = handle.token_store.authenticate(
        server_kind="ordinary",
        token=reviewer_context["bearer_token"],
        session_id=None,
    )
    planner_scope = handle.token_store.authenticate(
        server_kind="ordinary",
        token=planner_context["bearer_token"],
        session_id=None,
    )

    assert "blueprint_reply_popo_user" not in reviewer_context["tools"]
    assert "blueprint_reply_popo_user" not in planner_context["tools"]
    assert "blueprint_revert_excel_changes" not in reviewer_context["tools"]
    assert "blueprint_revert_excel_changes" not in planner_context["tools"]
    assert "blueprint_query_excel_history" not in reviewer_context["tools"]
    assert "blueprint_query_excel_history" in planner_context["tools"]
    assert not hasattr(handle, "_ordinary_blueprint_reply_popo_user")

    async def scenario() -> dict:
        with pytest.raises(PermissionError):
            await handle._ordinary_blueprint_query_excel_history(
                reviewer_scope,
                start_time="2026-06-11 10:00:00",
                end_time="2026-06-11 10:30:00",
            )
        return await handle._ordinary_blueprint_query_excel_history(
            planner_scope,
            start_time="2026-06-11 10:00:00",
            end_time="2026-06-11 10:30:00",
            workbook="15-0",
            field="is_download",
            category="xltool",
            limit=5,
        )

    result = asyncio.run(scenario())

    assert result == {"ok": True, "records": [], "count": 0}
    assert calls == [
        {
            "start_time": "2026-06-11 10:00:00",
            "end_time": "2026-06-11 10:30:00",
            "workbook": "15-0",
            "field": "is_download",
            "category": "xltool",
            "limit": 5,
            "session_key": "bps_000000000000000000000001",
            "agent_node_id": "planner",
            "agent_id": "agent-planner",
        }
    ]
    assert handle.token_store.closed is False
    assert manager.records[-1][0] == MCP_TOOL_AUDIT_EVENT
    assert manager.records[-1][1]["tool_name"] == "blueprint_query_excel_history"
    assert "receiver" not in manager.records[-1][1]["args"]
    assert "token" not in manager.records[-1][1]["args"]
    assert "secret" not in manager.records[-1][1]["args"]


def test_query_excel_history_from_mcp_uses_bound_session_only(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBlueprintService(resident_services_data_dir=tmp_path / "state")
    document = _document(project)
    run = DesktopBlueprintRun(
        run_id="run-history",
        project_dir=project.resolve(),
        blueprint_id="default",
        document=document,
        graph=object(),
        runtime=SimpleNamespace(popo_reply_session_key=""),
        control=object(),
        execution_mode="live",
        created_at=1.0,
        updated_at=1.0,
        session_key="main+default",
        start_node_id="planner",
    )
    service._runs[run.run_id] = run
    for session_key in ("main+default", "main+other"):
        service._save_blueprint_session(
            {
                "sessionKey": session_key,
                "activeRunId": run.run_id,
                "projectDir": str(project.resolve()),
                "blueprintId": "default",
                "createdAt": 1.0,
                "lastTouchedAt": 1.0,
            }
        )

    current_workbook = service._blueprint_session_dir("main+default") / "current.xlsx"
    current_workbook.write_text("before", encoding="utf-8")
    prepared = prepare_service_call_audit(
        {
            "session_key": "main+default",
            "session_dir": str(service._blueprint_session_dir("main+default")),
            "run_id": run.run_id,
            "source_node_id": "planner",
        },
        "xltool",
        "set_cell",
        {"file": str(current_workbook), "cell": "A1", "value": "after", "in_place": True},
        now=lambda: 1_800_000_000.0,
    )
    assert prepared is not None
    current_workbook.write_text("after", encoding="utf-8")
    finalize_service_call_audit(prepared, {"ok": True, "data": {"changed": True}})

    other_workbook = service._blueprint_session_dir("main+other") / "other.xlsx"
    other_workbook.write_text("before", encoding="utf-8")
    other_prepared = prepare_service_call_audit(
        {
            "session_key": "main+other",
            "session_dir": str(service._blueprint_session_dir("main+other")),
            "run_id": run.run_id,
            "source_node_id": "planner",
        },
        "xltool",
        "set_cell",
        {"file": str(other_workbook), "cell": "A1", "value": "after", "in_place": True},
        now=lambda: 1_800_000_001.0,
    )
    assert other_prepared is not None
    other_workbook.write_text("after", encoding="utf-8")
    finalize_service_call_audit(other_prepared, {"ok": True, "data": {"changed": True}})

    result = service._query_excel_history_from_mcp(
        run.run_id,
        agent_node_id="planner",
        agent_id="agent-planner",
        category="all",
        limit=10,
    )
    assert result["ok"] is True
    assert result["sessionKey"] == "main+default"
    assert result["count"] == 1
    assert result["records"][0]["workbook"] == str(current_workbook)

    with pytest.raises(BlueprintServiceError) as exc:
        service._query_excel_history_from_mcp(
            run.run_id,
            session_key="main+other",
            agent_node_id="planner",
            agent_id="agent-planner",
            category="all",
            limit=10,
        )
    assert exc.value.code == "BLUEPRINT_EXCEL_HISTORY_FORBIDDEN"

    service.close()


def test_run_mcp_skips_full_agent_context_when_message_tools_disabled(tmp_path: Path) -> None:
    class FullAgentNode:
        node_id = "shell"
        runtime_agent_id = "agent-shell"
        node_type = "agent"
        access_policy = {"framework_message_tools": False}

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

    context = handle.provision_context_for_node(
        node=FullAgentNode(),
        private_dir=tmp_path / "support",
        checkout_dir=tmp_path / "project",
        codex_home=tmp_path / "support" / "codex_home",
    )

    assert context == {}
    assert handle.token_store.summary()["ordinaryScopes"] == []


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
    message_only = handle.token_store.create_message_scope(
        agent_node_id="shell",
        agent_id="agent-shell",
    )
    control = handle.token_store.create_control_scope(
        agent_node_id="top-agent-gulicode",
        agent_id="gulicode",
    )
    handle.start()

    async def list_tool_names(url: str, token: str) -> list[str]:
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            trust_env=False,
        ) as client:
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
        message_only_tools = asyncio.run(list_tool_names(handle.ordinary_url, message_only.token))
        control_tools = asyncio.run(list_tool_names(handle.control_url, control.token))
    finally:
        handle.close()

    assert "agent_dispatch" in ordinary_tools
    assert "agent_context" in ordinary_tools
    assert "agent_task_status" in ordinary_tools
    assert "blueprint_service_docs" in ordinary_tools
    assert "blueprint_service_call" in ordinary_tools
    assert "join_contribute" in ordinary_tools
    assert "workspace_status" in ordinary_tools
    assert "workspace_read" not in ordinary_tools
    assert "workspace_list" not in ordinary_tools
    assert "workspace_list_archives" not in ordinary_tools
    assert "workspace_extract_archive" not in ordinary_tools
    assert "runtime_status" not in ordinary_tools
    assert "organization_read" not in ordinary_tools
    assert message_only_tools == [
        "agent_context",
        "agent_dispatch",
        "agent_task_status",
        "blueprint_script_call",
        "blueprint_service_call",
        "blueprint_service_docs",
        "join_contribute",
    ]
    assert "workspace_checkout" not in message_only_tools
    assert "workspace_status" not in message_only_tools
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
        async with httpx.AsyncClient(headers=headers, timeout=20.0, trust_env=False) as client:
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


def test_blueprint_service_live_start_returns_pending_when_runtime_start_blocks(tmp_path: Path, monkeypatch) -> None:
    class FakeLiveBackend:
        @classmethod
        async def create(cls, workers, *, port=9140, verbose=False, allow_empty=False):
            return cls()

        async def stop(self) -> None:
            pass

    async def blocked_start(self, plan, *, manifest_path=None, prestart_all_agents=False):
        time.sleep(0.1)
        return {
            "ok": True,
            "validation": {"ok": True, "errors": [], "warnings": []},
            "queued_messages": [],
            "start_manifest": {},
        }

    monkeypatch.setattr("multi_agent_tcp.desktop_blueprint_service.CLIWorkerBackend", FakeLiveBackend)
    monkeypatch.setattr(desktop_blueprint_service_module, "LIVE_START_RESULT_WAIT_SECONDS", 0.01)
    monkeypatch.setattr(desktop_blueprint_service_module, "LIVE_RUNTIME_CALL_STARTING_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        "multi_agent_tcp.desktop_blueprint_service.GraphRuntimeControlPlane.start_run",
        blocked_start,
    )

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

    assert started["ok"] is True
    assert started["startPending"] is True
    assert started["run"]["startPending"] is True
    runs = service.handle_request(
        {"command": "blueprint.listRuns", "args": {"projectDir": str(project), "blueprintId": "default"}}
    )
    assert runs["runs"][0]["runId"] == started["runId"]
    assert runs["runs"][0]["status"] == "starting"
    status = service.handle_request({"command": "blueprint.status", "args": {"runId": started["runId"]}})
    assert status["run"]["startPending"] is True
    assert status["status"]["run"]["status"] == "starting"

    service._async_loop.run(asyncio.sleep(0.2))
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
    ended = service.handle_request(
        {"command": "blueprint.end", "args": {"runId": started["runId"], "action": "cancel"}}
    )
    assert ended["status"]["run"]["status"] == "cancelled"
    after_end = service.handle_request(
        {"command": "blueprint.planning.status", "args": {"sessionId": session_id}}
    )
    assert after_end["activeRun"] is None
    assert after_end["statusSource"]["selected"] == "planning_context"
    assert service._planning_sessions[session_id].active_run_id is None
    service.close()


def test_blueprint_service_live_mode_starts_start_agents_with_private_context(
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
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    skill_dir = codex_home / "skills"
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
    document["graph"]["agent_nodes"]["observer"] = {
        "node_id": "observer",
        "agent_id": "agent-observer",
        "prompt": "Observe downstream work.",
        "cli_kind": "codex",
        "model": "gpt-5.4",
        "command": "codex",
        "adapter_options": {"skip_git_repo_check": True},
    }
    document["graph"]["edges"].append({"from": "planner", "to": "observer", "edge_type": "exec"})
    document["graph"]["agent_nodes"]["leaf"] = {
        "node_id": "leaf",
        "agent_id": "agent-leaf",
        "prompt": "Finish downstream work.",
        "cli_kind": "codex",
        "model": "gpt-5.4",
        "command": "codex",
        "adapter_options": {"skip_git_repo_check": True},
    }
    document["graph"]["edges"].append({"from": "observer", "to": "leaf", "edge_type": "exec"})
    document["ui"]["config"] = {
        "python_path": sys.executable,
        "project_workdir": str(project),
            "skill_dir": str(skill_dir),
        "rule_dir": str(rules_dir),
    }
    plan = _plan()
    plan["agent_descriptions"]["test-agent"] = "Test panel agent."
    plan["agent_descriptions"]["observer"] = "Observer receives the start node outgoing batch."
    plan["agent_descriptions"]["leaf"] = "Leaf should start lazily when scheduled later."
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
    assert set(backend.worker_configs) == {"agent-planner", "agent-test-agent", "agent-observer"}
    assert "agent-leaf" not in backend.worker_configs

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
        assert "127.0.0.1" in worker.extra_env["NO_PROXY"].split(",")
        assert "localhost" in worker.extra_env["no_proxy"].split(",")
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
        framework_skill_text = framework_skill.read_text(encoding="utf-8")
        assert "use those MCP tools first" in framework_skill_text
        assert "query fill history first for revert requests" in framework_skill_text
        assert "release without ticket/commit for uncommitted reverts" in framework_skill_text
        assert "blueprint_revert_excel_changes" not in framework_skill_text
        planning_workflow_text = (
            private
            / "codex_home"
            / "skills"
            / "framework-agent-runtime"
            / "planning_table_popo_workflow.md"
        ).read_text(encoding="utf-8")
        assert "blueprint_query_excel_history" in planning_workflow_text
        assert "Do not call automatic Excel rollback" in planning_workflow_text
        assert "If the original fill was not committed" in planning_workflow_text
        assert "do not ask for a ticket and do not run" in planning_workflow_text
        assert "If the original fill was committed" in planning_workflow_text
        assert "blueprint_revert_excel_changes" not in planning_workflow_text
        framework_rule = private / "rules" / "framework-agent-runtime.md"
        assert framework_rule.is_file()
        framework_rule_text = framework_rule.read_text(encoding="utf-8")
        assert "Multi-Agent Framework Baseline Rules" in framework_rule_text
        assert "blueprint_query_excel_history" in framework_rule_text
        assert "uncommitted reverts do not require a ticket" in framework_rule_text
        assert "Do not restore workbook backups over current files" in framework_rule_text
        assert "blueprint_revert_excel_changes" not in framework_rule_text
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
    selected_skill_index = Path(private_context["selected_skill_index_path"])
    assert selected_skill_index.is_file()
    selected_skill_index_text = selected_skill_index.read_text(encoding="utf-8")
    assert "business-skill" in selected_skill_index_text
    assert "Business skill description" in selected_skill_index_text
    assert str(business_skill / "SKILL.md") in selected_skill_index_text
    prompt_private_context = test_worker.adapter_options["prompt_execution_context"]["private_context"]
    assert prompt_private_context["selected_skill_index_path"] == str(selected_skill_index)
    assert "skill_catalog" not in prompt_private_context
    assert any(
        item.get("hash") == "business-skill" and item.get("source") == "business"
        for item in private_context["skill_catalog"]
    )
    assert any(
        item.get("hash") == "business-skill"
        and item.get("source") == "business"
        and item.get("skill_md_path") == str(business_skill / "SKILL.md")
        for item in private_context["skill_catalog"]
    )
    assert private_context["rule_catalog"][0]["source"] == "framework"
    assert private_context["rule_catalog"][0]["name"] == "framework-agent-runtime"
    assert Path(private_context["rule_catalog"][0]["rule_path"]).is_file()
    assert any(
        item.get("name") == "Business Rule" and Path(item.get("rule_path", "")).is_file()
        for item in private_context["rule_catalog"]
    )

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
        async with httpx.AsyncClient(headers=headers, timeout=20.0, trust_env=False) as client:
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
            if str(worker_id) == "agent-starter":
                await call_tool(
                    worker,
                    "agent_dispatch",
                    {
                        "target_node_id": "planner",
                        "body": {
                            "prompt": "Use MCP tools for checkout, submit, publish, and reviewer dispatch."
                        },
                    },
                )
                return {"type": "message", "body": {"ok": True, "text": "starter dispatched planner"}}

            if str(worker_id) == "agent-planner":
                execution_context = worker.adapter_options.get("execution_context") or {}
                code_workspace = execution_context.get("code_workspace") or {}
                project_context_value = code_workspace.get("project_context")
                if not project_context_value:
                    context_path = worker.extra_env.get("MULTI_AGENT_WORKSPACE_CONTEXT")
                    if context_path:
                        workspace_context = json.loads(Path(context_path).read_text(encoding="utf-8"))
                        project_context_value = workspace_context.get("project_context")
                project_context = Path(project_context_value or project)
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
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    skill_dir = codex_home / "skills"
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
        "starter": {
            "node_id": "starter",
            "node_type": "agent",
            "agent_id": "agent-starter",
            "prompt": "Dispatch deterministic MCP planner.",
            "cli_kind": "codex",
            "model": "gpt-5.4",
            "command": "codex",
        },
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
        {"from": "start", "to": "starter", "edge_type": "exec"},
        {"from": "starter", "to": "planner", "edge_type": "exec"},
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
            "starter": "Dispatches the workspace task to planner.",
            "planner": "Uses MCP tools for workspace changes and dispatch.",
            "reviewer": "Reads planner's published report directly from the shared workspace.",
        },
        "start_nodes": ["starter"],
        "tasks": {
            "starter": {
                "goal": "Dispatch the workspace MCP task to planner.",
                "expected_output": "Planner receives the workspace task.",
                "acceptance": "MCP audit includes starter agent_dispatch.",
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
        assert (private / "rules" / "01-policy.md").is_file()
        prompt_context = desktop_run.runtime._launch_nodes["planner"].adapter_options[
            "prompt_execution_context"
        ]
        prompt_dump = json.dumps(prompt_context, ensure_ascii=False)
        private_context = desktop_run.runtime._launch_nodes["planner"].adapter_options[
            "execution_context"
        ]["private_context"]
        assert any(
            item.get("hash") == "s"
            and item.get("source") == "business"
            and item.get("skill_md_path") == str(business_skill / "SKILL.md")
            for item in private_context["skill_catalog"]
        )
        selected_skill_index = Path(private_context["selected_skill_index_path"])
        assert selected_skill_index.is_file()
        selected_skill_index_text = selected_skill_index.read_text(encoding="utf-8")
        assert "s" in selected_skill_index_text
        assert "DETERMINISTIC_MCP_BUSINESS_SKILL_DESCRIPTION" in selected_skill_index_text
        assert str(business_skill / "SKILL.md") in selected_skill_index_text
        assert "framework_ordinary" in prompt_dump
        assert "bearer_token" not in prompt_dump
        assert "rpc_token" not in prompt_dump
        assert prompt_context["private_context"]["selected_skill_index_path"] == str(selected_skill_index)
        assert str(business_skill / "SKILL.md") not in prompt_dump
        assert "skill_catalog" not in prompt_context["private_context"]
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
    source_codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()
    codex_home = tmp_path / "codex-home"
    for name in CODEX_RUNTIME_STATE_FILES:
        src = source_codex_home / name
        if src.is_file():
            dst = codex_home / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    skill_dir = codex_home / "skills"
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
        assert (private / "rules" / "01-policy.md").is_file()
        prompt_context = desktop_run.runtime._launch_nodes["planner"].adapter_options[
            "prompt_execution_context"
        ]
        prompt_dump = json.dumps(prompt_context, ensure_ascii=False)
        private_context = desktop_run.runtime._launch_nodes["planner"].adapter_options[
            "execution_context"
        ]["private_context"]
        assert any(
            item.get("hash") == "business-skill"
            and item.get("source") == "business"
            and item.get("skill_md_path") == str(business_skill / "SKILL.md")
            for item in private_context["skill_catalog"]
        )
        selected_skill_index = Path(private_context["selected_skill_index_path"])
        assert selected_skill_index.is_file()
        selected_skill_index_text = selected_skill_index.read_text(encoding="utf-8")
        assert "business-skill" in selected_skill_index_text
        assert "REAL_MCP_BUSINESS_SKILL_DESCRIPTION" in selected_skill_index_text
        assert str(business_skill / "SKILL.md") in selected_skill_index_text
        assert "framework_ordinary" in prompt_dump
        assert "bearer_token" not in prompt_dump
        assert "rpc_token" not in prompt_dump
        assert str(selected_skill_index) in prompt_dump
        assert str(business_skill / "SKILL.md") not in prompt_dump
        assert "skill_catalog" not in prompt_context["private_context"]

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


def test_real_codex_live_blueprint_agent_ring_limits_and_refresh_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    if os.environ.get("MULTI_AGENT_TCP_RUN_REAL_CODEX_MCP") != "1":
        pytest.skip("set MULTI_AGENT_TCP_RUN_REAL_CODEX_MCP=1 to run the external Codex MCP ring smoke")
    codex = shutil.which("codex")
    if codex is None:
        pytest.skip("codex CLI is not installed on PATH")

    project, cleanup_project = _real_codex_mcp_project_root(tmp_path)
    project.mkdir(parents=True, exist_ok=True)
    source_codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()
    codex_home = tmp_path / "codex-home-ring"
    for name in CODEX_RUNTIME_STATE_FILES:
        src = source_codex_home / name
        if src.is_file():
            dst = codex_home / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    run_id = "run-real-mcp-ring"
    codex_options = {
        "model": "gpt-5.5",
        "timeout_sec": 360.0,
        "disable_features": ["shell_snapshot"],
        "config_overrides": _codex_real_flow_config_overrides(),
    }
    document = _document(project)
    document["graph"]["agent_nodes"] = {
        "planner": {
            "node_id": "planner",
            "node_type": "agent",
            "agent_id": "agent-ring-planner",
            "prompt": "Start and close the real Codex ring smoke.",
            "cli_kind": "codex",
            "model": "gpt-5.5",
            "command": codex,
            "timeout_sec": 360.0,
            "adapter_options": codex_options,
        },
        "reviewer": {
            "node_id": "reviewer",
            "node_type": "worker_agent",
            "agent_id": "agent-ring-reviewer",
            "prompt": "Return the real Codex ring smoke to planner.",
            "cli_kind": "codex",
            "model": "gpt-5.5",
            "command": codex,
            "timeout_sec": 360.0,
            "adapter_options": codex_options,
        },
    }
    document["graph"]["edges"] = [
        {"from": "planner", "to": "reviewer", "edge_type": "exec"},
        {"from": "reviewer", "to": "planner", "edge_type": "exec"},
    ]
    document["graph"]["agent_ring_max_circulations"] = {"ring-planner-reviewer": 1}
    document["graph"]["agent_ring_context_refresh_periods"] = {"ring-planner-reviewer": 1}
    document["runtime"] = {"start_node_id": "planner"}
    document["ui"]["config"] = {
        "python_path": sys.executable,
        "project_workdir": str(project),
        "skill_dir": "",
        "rule_dir": "",
    }
    planner_goal = (
        "This is a real Codex live blueprint agent ring smoke. Use the MCP "
        "tools exposed by framework_ordinary; do not use shell commands.\n\n"
        "Call `mcp__framework_ordinary__agent_dispatch` exactly once to target "
        "`reviewer` with body JSON containing this prompt:\n"
        "`Inspect your framework_context.ring_context and confirm it contains "
        "ring1. Then call mcp__framework_ordinary__agent_dispatch exactly once "
        "to target planner with body JSON prompt REAL_RING_CLOSE_DONE. Do not "
        "dispatch anywhere else. Your final answer must include "
        "REAL_RING_REVIEWER_DISPATCHED.`\n\n"
        "Your final answer must include REAL_RING_PLANNER_DISPATCHED."
    )
    plan = {
        "user_goal": "Verify real Codex ring limit and context refresh behavior.",
        "agent_descriptions": {
            "planner": "Dispatches to reviewer once.",
            "reviewer": "Dispatches back to planner once.",
        },
        "start_nodes": ["planner"],
        "tasks": {
            "planner": {
                "goal": planner_goal,
                "expected_output": "A single closed ring circulation.",
                "acceptance": "Ring context refreshes once and the ring is exhausted.",
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
        status = _wait_for_live_run_idle(service, run_id, timeout_sec=420.0)

        pending = status["queues"]["pending_messages"]
        assert pending
        assert all(item["status"] == "completed" for item in pending.values()), status
        ring_status = status["agent_rings"]["rings"]["ring1"]
        assert ring_status["topology_id"] == "ring-planner-reviewer"
        assert ring_status["max_circulations"] == 1
        assert ring_status["context_refresh_period"] == 1
        assert ring_status["completed_circulations"] == 1
        assert ring_status["context_generation"] == 1
        assert ring_status["remaining_circulations"] == 0

        events = service.recent_blueprint_events(run_id, limit=100)["events"]
        event_types = [event["event_type"] for event in events]
        assert "AgentRingContextRefreshed" in event_types
        assert "AgentRingCirculationExhausted" in event_types
        advanced = [
            event
            for event in events
            if event["event_type"] == "AgentRingCirculationAdvanced"
        ]
        assert advanced
        assert "ring1" in advanced[-1]["payload"]["refreshed_ring_ids"]
        assert "ring1" in advanced[-1]["payload"]["exhausted_ring_ids"]

        desktop_run = service._runs[run_id]
        workspace_run = desktop_run.runtime.private_context_run
        assert workspace_run is not None
        mcp_tools = [
            item["tool_name"]
            for item in _workspace_manifest_entries(workspace_run, MCP_TOOL_AUDIT_EVENT)
        ]
        assert mcp_tools.count("agent_dispatch") >= 2
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

    assert FakeLiveBackend.instances == []
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


def test_agent_tcp_client_close_stops_reader_pump() -> None:
    async def scenario() -> None:
        registered = asyncio.Event()

        async def handle_client(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            try:
                msg = await read_frame(reader)
                assert msg["type"] == "register"
                await write_frame(writer, {"type": "registered", "agent_id": msg["agent_id"]})
                registered.set()
                await reader.read()
            finally:
                writer.close()
                with suppress(ConnectionError, OSError, asyncio.TimeoutError):
                    await asyncio.wait_for(writer.wait_closed(), timeout=1)

        server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
        try:
            assert server.sockets
            host, port = server.sockets[0].getsockname()[:2]
            client = AgentTCPClient("orchestrator", str(host), int(port))
            await client.connect()
            await asyncio.wait_for(registered.wait(), timeout=1)
            assert client._reader_task is not None
            assert client._reader_task.done() is False

            await asyncio.wait_for(client.close(), timeout=1)

            assert client._reader_task is None
            assert client._writer is None
            assert client._reader is None
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def test_asyncio_connection_reset_filter_suppresses_windows_proactor_noise() -> None:
    if sys.platform != "win32":
        pytest.skip("Windows Proactor-specific noise filter")

    class FakeHandle:
        def __str__(self) -> str:
            return "<Handle _ProactorBasePipeTransport._call_connection_lost()>"

    context = {
        "exception": ConnectionResetError(10054, "connection reset"),
        "handle": FakeHandle(),
    }
    assert _should_suppress_asyncio_connection_reset(context) is True

    loop = asyncio.new_event_loop()
    calls: list[dict] = []

    def previous_handler(_loop: asyncio.AbstractEventLoop, ctx: dict) -> None:
        calls.append(ctx)

    try:
        loop.set_exception_handler(previous_handler)
        install_asyncio_connection_reset_filter(loop)
        handler = loop.get_exception_handler()
        assert handler is not None

        handler(loop, context)
        assert calls == []

        runtime_context = {"exception": RuntimeError("real failure")}
        handler(loop, runtime_context)
        assert calls == [runtime_context]
    finally:
        loop.close()


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
