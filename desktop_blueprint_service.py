"""Desktop-facing blueprint service for GuLiCode.

This module is intentionally a thin HTTP/JSON facade around project blueprint
files and the runtime control-plane data model. It keeps renderer and Electron
code away from Python package paths, runtime tokens, and direct file writes.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Callable, Dict, Optional, Sequence
from urllib.parse import parse_qs, urlparse

import requests

from .cluster import CLIWorkerBackend
from .blueprint_mcp_runtime import RunMCPRuntimeHandle, TOP_AGENT_PLANNING_CONTROL_TOOLS
from .excel_audit import (
    parse_excel_log_command,
    parse_time_range,
    query_excel_history,
    render_user_log,
)
from .blueprint_script_nodes import (
    create_script_node,
    discover_script_nodes,
    ensure_script_nodes_dir,
    script_nodes_dir,
    validate_script_node_references,
)
from .blueprint_resident_services import (
    ResidentServiceManager,
    ensure_resident_services_dir,
)
from .planning_table_skill_update import (
    DEFAULT_COMMIT_MESSAGE as PLANNING_TABLE_SKILL_UPDATE_COMMIT_MESSAGE,
    DEFAULT_INDEX_PATH as PLANNING_TABLE_SKILL_UPDATE_INDEX_PATH,
    DEFAULT_SKILL_ROOT as PLANNING_TABLE_SKILL_UPDATE_ROOT,
    DEFAULT_TARGET_BLUEPRINT_ID as PLANNING_TABLE_SKILL_UPDATE_BLUEPRINT_ID,
    DEFAULT_TARGET_PROJECT_DIR as PLANNING_TABLE_SKILL_UPDATE_PROJECT_DIR,
)
from .graph_control import (
    GraphRuntimeControlPlane,
    graph_definition_from_dict,
    inject_framework_context,
    ordinary_agent_framework_context,
)
from .graph_runtime import GraphRuntime, GuLiCodeTopAgentProfile, TopAgentStartPlan
from ._asyncio_utils import install_asyncio_connection_reset_filter
from .skill_space import SkillRecord
from .workspace_manager import DulwichWorkspaceManager
from .workspace_rpc import WorkspaceRPCServer

log = logging.getLogger(__name__)

BLUEPRINT_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+)")
DEFAULT_BLUEPRINT_ID = "default"
DEFAULT_BLUEPRINT_NAME = "Default Blueprint"
BLUEPRINT_DIAGNOSTICS_SCHEMA_VERSION = 1
BLUEPRINT_DIAGNOSTICS_KIND = "gulicode.blueprint.diagnostics"
BLUEPRINT_DIAGNOSTICS_FOCUS = "planning_status_source"
BLUEPRINT_DIAGNOSTICS_DIR = "blueprint-diagnostics"
PLANNING_STATUS_SOURCE_COMMANDS = {
    "run.status",
    "top_agent.explain_status",
    "top_agent.utterances",
}
TERMINAL_RUN_STATUSES = {"completed", "cancelled", "failed"}
LIVE_START_RESULT_WAIT_SECONDS = 5.0
LIVE_RUNTIME_CALL_STARTING_TIMEOUT_SECONDS = 2.0
LIVE_RUNTIME_STATUS_TIMEOUT_SECONDS = 1.0
LIVE_SLOT_TERMINATE_TIMEOUT_SECONDS = 1.0
LIVE_RUN_ACTIVE_CHECK_TIMEOUT_SECONDS = 0.25
LIVE_AGENT_STREAM_READ_TIMEOUT_SECONDS = 1.0
BLUEPRINT_MODEL_COMMAND_TIMEOUT_SECONDS = 15.0
BLUEPRINT_SESSION_CONTEXT_RECENT_LIMIT = 20
BLUEPRINT_SESSION_CONTEXT_CHAR_LIMIT = 12_000
BLUEPRINT_SESSION_TIMELINE_LIMIT = 500
BLUEPRINT_SESSION_AUTO_TERMINATE_IDLE_SECONDS = 10 * 60.0
BLUEPRINT_SESSION_AUTO_TERMINATE_CHECK_INTERVAL_SECONDS = 2.0
BLUEPRINT_SESSION_SCHEMA_VERSION = 1
TABLE_QUEUE_NOTIFICATION_FILENAME = "table_queue_notifications.jsonl"
TABLE_QUEUE_NOTIFICATION_PROCESSED_FILENAME = "table_queue_notifications_processed.json"
TABLE_QUEUE_NOTIFICATION_WATCH_INTERVAL_SECONDS = 5.0
PLANNING_TABLE_SKILL_UPDATE_NOTIFICATION_FILENAME = "planning_table_skill_update_notifications.jsonl"
PLANNING_TABLE_SKILL_UPDATE_NOTIFICATION_PROCESSED_FILENAME = (
    "planning_table_skill_update_notifications_processed.json"
)
PLANNING_TABLE_SKILL_UPDATE_WATCH_INTERVAL_SECONDS = 5.0
BLUEPRINT_PROJECT_REGISTRY_FILENAME = "blueprint_projects.json"
POPO_ROBOT_ROUTES_FILENAME = "popo_robot_routes.json"
POPO_API_BASE = "https://open.popo.netease.com"
POPO_STREAMING_CARD_TEMPLATE_UUID = "series_5564199"
POPO_STREAMING_CARD_KEY = "resultStream"
POPO_STREAMING_CARD_LAST_MESSAGE = "AI正在回复..."
POPO_PROGRESS_THINKING_TEXT = "思考中..."
POPO_PROGRESS_REPLACED_TEXT = "收到新消息，继续处理..."
POPO_PROGRESS_COMPLETED_TEXT = "处理完成"
POPO_PROGRESS_STOPPED_TEXT = "已停止"
POPO_PROGRESS_FAILED_TEXT = "处理失败"
POPO_PROGRESS_UPDATE_INTERVAL_SECONDS = 0.8
POPO_PROGRESS_MAX_LINES = 3
POPO_PROGRESS_LINE_CHAR_LIMIT = 80
POPO_PROGRESS_TEXT_DELTA_FLUSH_CHARS = 40
POPO_PROGRESS_TEMP_REPLY_CHAR_LIMIT = 1200
BLUEPRINT_MAIN_SESSION_PREFIX = "main+"
BLUEPRINT_POPO_SESSION_PREFIX = "bps_popo_"
POPO_TERMINATION_REMINDER_INTERVAL_SECONDS = 300.0
POPO_ENTRY_REQUIRED_FIELDS = (
    "robot_app_key",
    "robot_name",
    "robot_app_secret",
    "callback_token",
    "aes_key",
)
BLUEPRINT_SESSION_DIRECT_USER_COMMANDS = (
    {
        "command": "/help",
        "description": "查看可用指令列表。",
    },
    {
        "command": "/new",
        "description": "开启新会话，清空当前会话上下文。",
    },
    {
        "command": "/stop",
        "description": "结束当前会话，保留历史记录。",
    },
    {
        "command": "/excel-log",
        "usage": "/excel-log <起始时间>-<结束时间>",
        "description": "查看当前会话内表格修改记录，时间格式：YYYY M D H M S [ms]-YYYY M D H M S [ms]。",
    },
)


def _is_blueprint_session_help_command(message: str) -> bool:
    return str(message or "").strip() == "/help"


def _blueprint_session_direct_command_help_response(session_key: str = "") -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "ok": True,
        "help": True,
        "commands": [dict(command) for command in BLUEPRINT_SESSION_DIRECT_USER_COMMANDS],
        "message": "\n".join(
            [
                "可用指令（后端直接处理，不会发送给 Agent）：",
                *[
                    f"{command.get('usage') or command['command']} - {command['description']}"
                    for command in BLUEPRINT_SESSION_DIRECT_USER_COMMANDS
                ],
            ]
        ),
    }
    if session_key:
        payload["sessionKey"] = blueprint_session_key_path_component(session_key)
    return payload


def validate_desktop_blueprint_graph(graph: Any, *, project_dir: Optional[Path] = None) -> None:
    graph.validate_agent_ring_graph()
    if not graph.agent_nodes:
        raise ValueError("blueprint graph requires at least one AgentNode")
    if project_dir is not None and getattr(graph, "script_nodes", None):
        validate_script_node_references(project_dir, graph.script_nodes.values())


class BlueprintServiceError(ValueError):
    """Expected desktop service error with a stable UI-facing code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 400,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = dict(details or {})


def system_default_blueprint_editor() -> Dict[str, Any]:
    return {
        "id": "system",
        "label": "System default",
        "source": "system",
        "systemDefault": True,
    }


def list_blueprint_editors() -> list[Dict[str, Any]]:
    candidates: list[Dict[str, Any]] = []
    seen: set[str] = set()

    def add(candidate: Optional[Dict[str, Any]]) -> None:
        if not candidate:
            return
        key = (
            str(candidate.get("id", ""))
            if candidate.get("systemDefault")
            else "\0".join([str(candidate.get("command", "")), *[str(arg) for arg in candidate.get("args", [])]])
            .casefold()
        )
        if key in seen:
            return
        seen.add(key)
        candidates.append(candidate)

    add(_blueprint_editor_from_env("VISUAL"))
    add(_blueprint_editor_from_env("EDITOR"))
    add(_blueprint_editor_from_known_command("vscode", "VS Code", _vscode_command_candidates()))
    add(_blueprint_editor_from_known_command("cursor", "Cursor", ["cursor"]))
    add(_blueprint_editor_from_known_command("windsurf", "Windsurf", ["windsurf"]))
    add(_blueprint_editor_from_known_command("zed", "Zed", ["zed"]))
    add(_blueprint_editor_from_known_command("pycharm", "PyCharm", ["pycharm64", "pycharm"]))
    add(system_default_blueprint_editor())

    return candidates


def resolve_blueprint_editor(editor_id: Optional[str]) -> Dict[str, Any]:
    selected = str(editor_id or "").strip()
    for editor in list_blueprint_editors():
        if editor.get("id") == selected:
            return editor
    return system_default_blueprint_editor()


def open_blueprint_script_in_editor(
    project_dir: Path,
    module_path: str,
    editor_id: Optional[str] = None,
) -> Dict[str, Any]:
    script_root = _blueprint_script_root_for_module(project_dir, module_path)
    editor = resolve_blueprint_editor(editor_id)
    if editor.get("systemDefault") or not editor.get("command"):
        _open_path_with_system_default(script_root)
        return {"ok": True, "path": str(script_root), "editorId": "system"}
    _launch_blueprint_editor(editor, script_root)
    return {"ok": True, "path": str(script_root), "editorId": str(editor.get("id") or "")}


def open_blueprint_resident_service_in_editor(
    data_dir: Path,
    module_path: str,
    editor_id: Optional[str] = None,
) -> Dict[str, Any]:
    service_root = _blueprint_resident_service_root_for_module(data_dir, module_path)
    editor = resolve_blueprint_editor(editor_id)
    if editor.get("systemDefault") or not editor.get("command"):
        _open_path_with_system_default(service_root)
        return {"ok": True, "path": str(service_root), "editorId": "system"}
    _launch_blueprint_editor(editor, service_root)
    return {"ok": True, "path": str(service_root), "editorId": str(editor.get("id") or "")}


def _blueprint_editor_from_env(env_name: str) -> Optional[Dict[str, Any]]:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return None
    parts = _split_editor_command(raw)
    command = parts[0] if parts else ""
    if not command:
        return None
    resolved = _resolve_editor_program(command)
    if not resolved:
        return None
    return {
        "id": f"env:{env_name.lower()}",
        "label": f"{env_name}: {Path(command).name}",
        "command": resolved,
        "args": parts[1:],
        "source": env_name,
    }


def _blueprint_editor_from_known_command(
    editor_id: str,
    label: str,
    commands: Sequence[str],
) -> Optional[Dict[str, Any]]:
    for command in commands:
        resolved = _resolve_editor_program(command)
        if resolved and _resolved_editor_matches(editor_id, resolved):
            return {
                "id": editor_id,
                "label": label,
                "command": resolved,
                "args": [],
                "source": f"PATH {command}",
            }
    return None


def _vscode_command_candidates() -> list[str]:
    candidates = ["code"]
    if sys.platform == "win32":
        for root_name in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
            root = os.environ.get(root_name)
            if root:
                candidates.append(str(Path(root) / "Microsoft VS Code" / "bin" / "code.cmd"))
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(str(Path(local_app_data) / "Programs" / "Microsoft VS Code" / "bin" / "code.cmd"))
            candidates.append(str(Path(local_app_data) / "Programs" / "Microsoft VS Code Insiders" / "bin" / "code-insiders.cmd"))
    return candidates


def _resolved_editor_matches(editor_id: str, command: str) -> bool:
    resolved = str(command or "").replace("\\", "/").lower()
    if editor_id == "vscode":
        parts = [part for part in resolved.split("/") if part]
        for index, part in enumerate(parts):
            if part == "cursor" and parts[index + 1 : index + 4] == ["resources", "app", "codebin"]:
                return False
            if part == "cursor" and parts[index + 1 : index + 4] == ["resources", "app", "bin"]:
                return False
        return True
    return True


def _split_editor_command(raw: str) -> list[str]:
    matches = re.finditer(r'"([^"]*)"|\'([^\']*)\'|(\S+)', raw)
    return [part for match in matches for part in [match.group(1) or match.group(2) or match.group(3) or ""] if part]


def _resolve_editor_program(program: str) -> Optional[str]:
    if "\\" in program or "/" in program:
        path = Path(program).expanduser()
        return str(path) if path.exists() else None
    return shutil.which(program)


def _blueprint_script_root_for_module(project_dir: Path, module_path: str) -> Path:
    script_root = ensure_script_nodes_dir(project_dir).resolve()
    normalized = str(module_path or "").replace("\\", "/").strip()
    parts = [part for part in normalized.split("/") if part]
    if (
        not normalized
        or normalized.startswith("/")
        or WINDOWS_ABSOLUTE_PATH_RE.match(normalized)
        or any(part == ".." for part in parts)
    ):
        raise BlueprintServiceError("BAD_REQUEST", "modulePath must stay inside the script directory")
    if not normalized.endswith(".py"):
        raise BlueprintServiceError("BAD_REQUEST", "modulePath must point to a .py file")

    target = script_root.joinpath(*parts).resolve()
    try:
        target.relative_to(script_root)
    except ValueError as exc:
        raise BlueprintServiceError("BAD_REQUEST", "modulePath escapes the script directory") from exc
    return script_root


def _blueprint_resident_service_root_for_module(data_dir: Path, module_path: str) -> Path:
    service_root = ensure_resident_services_dir(data_dir).resolve()
    normalized = str(module_path or "").replace("\\", "/").strip()
    parts = [part for part in normalized.split("/") if part]
    if (
        not normalized
        or normalized.startswith("/")
        or WINDOWS_ABSOLUTE_PATH_RE.match(normalized)
        or any(part == ".." for part in parts)
    ):
        raise BlueprintServiceError("BAD_REQUEST", "modulePath must stay inside the resident service directory")
    if not normalized.endswith(".py"):
        raise BlueprintServiceError("BAD_REQUEST", "modulePath must point to a .py file")

    target = service_root.joinpath(*parts).resolve()
    try:
        target.relative_to(service_root)
    except ValueError as exc:
        raise BlueprintServiceError("BAD_REQUEST", "modulePath escapes the resident service directory") from exc
    return service_root


def _open_path_with_system_default(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    command = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen(
        [command, str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def _launch_blueprint_editor(editor: Dict[str, Any], script_root: Path) -> None:
    command = str(editor.get("command") or "").strip()
    if not command:
        raise BlueprintServiceError("BAD_REQUEST", "editor command is missing")
    args = [
        *[
            str(arg)
            for arg in editor.get("args", [])
            if str(arg) not in {"--wait", "-w", "--reuse-window", "-r"}
        ],
        *_editor_window_args(editor),
        str(script_root),
    ]
    launch = [command, *args]
    if sys.platform == "win32" and Path(command).suffix.lower() in {".bat", ".cmd"}:
        launch = [os.environ.get("ComSpec") or "cmd.exe", "/c", command, *args]
    popen_kwargs: Dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(launch, **popen_kwargs)


def _editor_window_args(editor: Dict[str, Any]) -> list[str]:
    editor_id = str(editor.get("id") or "").lower()
    command_name = Path(str(editor.get("command") or "")).name.lower()
    if (
        editor_id in {"vscode", "cursor", "windsurf"}
        or command_name in {"code", "code.exe", "code.cmd", "cursor", "cursor.exe", "cursor.cmd", "windsurf", "windsurf.exe", "windsurf.cmd"}
    ):
        return ["--new-window"]
    return []


@dataclass(frozen=True)
class BlueprintPythonCandidate:
    command: str
    args: Sequence[str]
    source: str


def detect_blueprint_python(
    *,
    project_dir: Optional[Path] = None,
    python_command: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    package_root: Optional[Path] = None,
) -> Dict[str, Any]:
    try:
        python = _resolve_blueprint_python(
            project_dir=project_dir,
            python_command=python_command,
            env=env or os.environ,
            package_root=package_root or Path(__file__).resolve().parent,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "pythonCommand": python["executable"], "source": python["source"]}


def _resolve_blueprint_python(
    *,
    project_dir: Optional[Path],
    python_command: Optional[str],
    env: Dict[str, str],
    package_root: Path,
) -> Dict[str, str]:
    configured = (python_command or "").strip()
    if configured:
        candidate = _blueprint_python_candidate_from_command(configured, "blueprint common config python_path")
        executable = _blueprint_python_executable(candidate)
        if executable:
            return {"executable": executable, "source": candidate.source}

    env_python = (env.get("GULICODE_PYTHON") or "").strip()
    if env_python:
        candidate = _blueprint_python_candidate_from_command(env_python, "GULICODE_PYTHON")
        executable = _blueprint_python_executable(candidate)
        if executable:
            return {"executable": executable, "source": candidate.source}

    candidates = [
        BlueprintPythonCandidate("python", (), "PATH python"),
        BlueprintPythonCandidate("python3", (), "PATH python3"),
    ]
    if sys.platform == "win32":
        candidates.append(BlueprintPythonCandidate("py", ("-3",), "Windows py -3"))
    candidates.extend(_blueprint_venv_python_candidates(project_dir))
    candidates.extend(_blueprint_venv_python_candidates(package_root))

    for candidate in candidates:
        executable = _blueprint_python_executable(candidate)
        if executable:
            return {"executable": executable, "source": candidate.source}

    raise RuntimeError(
        "Python interpreter is required for blueprint runtime. Set the Blueprint config Python path or GULICODE_PYTHON."
    )


def _blueprint_python_candidate_from_command(value: str, source: str) -> BlueprintPythonCandidate:
    command, args = _parse_blueprint_python_command(value)
    return BlueprintPythonCandidate(command, tuple(args), source)


def _parse_blueprint_python_command(value: str) -> tuple[str, list[str]]:
    trimmed = value.strip()
    if trimmed.startswith('"'):
        end = trimmed.find('"', 1)
        if end > 1:
            command = trimmed[1:end]
            rest = trimmed[end + 1 :].strip()
            return command, _split_editor_command(rest) if rest else []
    if trimmed.startswith("'"):
        end = trimmed.find("'", 1)
        if end > 1:
            command = trimmed[1:end]
            rest = trimmed[end + 1 :].strip()
            return command, _split_editor_command(rest) if rest else []
    if Path(trimmed).expanduser().exists() or "\\" in trimmed or "/" in trimmed:
        return trimmed, []
    parts = _split_editor_command(trimmed)
    return (parts[0], parts[1:]) if parts else (trimmed, [])


def _blueprint_venv_python_candidates(root: Optional[Path]) -> list[BlueprintPythonCandidate]:
    if root is None:
        return []
    command = root / ".venv" / "Scripts" / "python.exe" if sys.platform == "win32" else root / ".venv" / "bin" / "python"
    return [BlueprintPythonCandidate(str(command), (), f".venv Python at {command}")]


def _blueprint_python_executable(candidate: BlueprintPythonCandidate) -> Optional[str]:
    command = candidate.command.strip()
    if not command:
        return None
    if ("\\" in command or "/" in command) and not Path(command).expanduser().exists():
        return None
    try:
        result = subprocess.run(
            [command, *candidate.args, "-c", "import sys; print(sys.executable)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3,
            check=False,
            shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    executable = (result.stdout or "").strip().splitlines()[0].strip() if (result.stdout or "").strip() else ""
    if not executable:
        return None
    if not (Path(executable).is_absolute() or WINDOWS_ABSOLUTE_PATH_RE.match(executable)):
        return None
    return executable


class DesktopAsyncLoop:
    """Small owner for the asyncio loop used by live desktop blueprint runs."""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._lock = threading.Lock()

    def _ensure_started(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is not None and self._thread is not None and self._thread.is_alive():
                return self._loop

            self._ready.clear()

            def run_loop() -> None:
                loop = asyncio.new_event_loop()
                install_asyncio_connection_reset_filter(loop)
                asyncio.set_event_loop(loop)
                self._loop = loop
                self._ready.set()
                loop.run_forever()
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.close()

            self._thread = threading.Thread(target=run_loop, name="desktop-blueprint-live-loop", daemon=True)
            self._thread.start()
        self._ready.wait(timeout=5)
        if self._loop is None:
            raise RuntimeError("desktop live runtime event loop failed to start")
        return self._loop

    def run(self, coro: Any, *, timeout: Optional[float] = None) -> Any:
        future = self.submit(coro)
        return future.result(timeout=timeout)

    def submit(self, coro: Any) -> Future[Any]:
        loop = self._ensure_started()
        return asyncio.run_coroutine_threadsafe(coro, loop)

    def call(self, fn: Callable[[], Any], *, timeout: Optional[float] = None) -> Any:
        async def wrapper() -> Any:
            return fn()

        return self.run(wrapper(), timeout=timeout)

    def close(self) -> None:
        loop = self._loop
        if loop is None:
            return
        loop.call_soon_threadsafe(loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._loop = None
        self._thread = None


@dataclass
class DesktopBlueprintRun:
    """One live, service-owned blueprint runtime."""

    run_id: str
    project_dir: Path
    blueprint_id: str
    document: Dict[str, Any]
    graph: Any
    runtime: GraphRuntime
    control: GraphRuntimeControlPlane
    execution_mode: str
    created_at: float
    updated_at: float
    backend: Any = None
    mcp: Any = None
    diagnostics_dir: Optional[Path] = None
    session_key: str = ""
    start_node_id: str = ""
    slot_status: str = ""
    slot_pool_key: str = ""
    blueprint_structure_id: str = ""
    robot_app_key: str = ""
    source_bindings: Dict[str, Any] = field(default_factory=dict)
    bound_session_key: str = ""
    slot_started_at: float = 0.0
    slot_last_touched_at: float = 0.0
    slot_reset_error: str = ""
    session_auto_idle_checked_at: float = 0.0
    session_auto_idle_terminating: bool = False
    slot_reset_future: Optional[Future[Any]] = field(default=None, repr=False)
    live_start_future: Optional[Future[Any]] = field(default=None, repr=False)
    live_start_result: Optional[Dict[str, Any]] = field(default=None, repr=False)
    live_start_error: str = ""
    planning_status_mismatch_keys: set[str] = field(default_factory=set, repr=False)
    popo_framework_reply_keys: set[str] = field(default_factory=set, repr=False)
    stream_condition: Any = field(default_factory=threading.Condition)

    def summary(self) -> Dict[str, Any]:
        data = {
            "runId": self.run_id,
            "projectDir": str(self.project_dir),
            "blueprintId": self.blueprint_id,
            "executionMode": self.execution_mode,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
        if self.session_key:
            data["sessionKey"] = self.session_key
        if self.start_node_id:
            data["startNodeId"] = self.start_node_id
        if self.blueprint_structure_id:
            data["blueprintStructureId"] = self.blueprint_structure_id
        if self.robot_app_key:
            data["robotAppKey"] = self.robot_app_key
        if self.source_bindings:
            data["sourceBindings"] = dict(self.source_bindings)
        if self.diagnostics_dir is not None:
            data["diagnostics"] = {
                "path": str(self.diagnostics_dir),
                "snapshot": str(self.diagnostics_dir / "snapshot.json"),
                "events": str(self.diagnostics_dir / "events.jsonl"),
            }
        if self.mcp is not None:
            data["mcp"] = self.mcp.summary()
        if self.live_start_future is not None:
            data["startPending"] = not self.live_start_future.done()
        if self.live_start_error:
            data["startError"] = self.live_start_error
        return data


@dataclass
class PopoStreamingProgressCard:
    run_id: str
    session_key: str
    receiver: str
    robot_app_key: str
    token: str
    instance_uuid: str
    popo_message_id: str = ""
    session_type: str = ""
    sequence: int = 0
    finalized: bool = False
    failed: bool = False
    fallback_reason: str = ""
    lines: list[str] = field(default_factory=list)
    last_content: str = ""
    last_update_at: float = 0.0
    pending_text_delta: str = ""
    agent_reply_started: bool = False
    temporary_reply_keys: set[str] = field(default_factory=set)
    progress_started: bool = False


@dataclass
class DesktopBlueprintPlanningQuestion:
    question_id: str
    questions: list[Dict[str, Any]]
    created_at: float
    status: str = "pending"
    answers: Any = None
    reason: str = ""
    answered_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "questionId": self.question_id,
            "questions": list(self.questions),
            "createdAt": _iso_time(self.created_at),
            "status": self.status,
        }
        if self.answers is not None:
            data["answers"] = self.answers
        if self.reason:
            data["reason"] = self.reason
        if self.answered_at is not None:
            data["answeredAt"] = _iso_time(self.answered_at)
        return data


@dataclass
class DesktopBlueprintPlanningSession:
    """One desktop conversation's blueprint planning control context."""

    session_id: str
    desktop_session_id: str
    project_dir: Path
    blueprint_id: str
    document: Dict[str, Any]
    graph: Any
    runtime: GraphRuntime
    control: GraphRuntimeControlPlane
    created_at: float
    updated_at: float
    framework_system: str = ""
    mcp_context: Optional[Dict[str, Any]] = None
    mcp: Any = None
    status: str = "ready"
    pending_question: Optional[DesktopBlueprintPlanningQuestion] = None
    pending_plan: Optional[Dict[str, Any]] = None
    active_run_id: Optional[str] = None
    events: list[Dict[str, Any]] = field(default_factory=list)
    condition: Any = field(default_factory=threading.Condition, repr=False)

    def summary(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "sessionId": self.session_id,
            "desktopSessionId": self.desktop_session_id,
            "projectDir": str(self.project_dir),
            "blueprintId": self.blueprint_id,
            "status": self.status,
            "createdAt": _iso_time(self.created_at),
            "updatedAt": _iso_time(self.updated_at),
        }
        if self.active_run_id:
            data["activeRunId"] = self.active_run_id
        if self.mcp is not None:
            data["mcp"] = self.mcp.summary()
        if self.mcp_context is not None:
            data["mcpContext"] = dict(self.mcp_context)
        return data


class DesktopBlueprintNoopBackend:
    """Runtime backend for the desktop middle layer before live CLI execution."""

    def __init__(self) -> None:
        self.worker_configs: Dict[str, Any] = {}

    async def ensure_worker(self, worker: Any) -> None:
        self.worker_configs[str(worker.agent_id)] = worker

    async def run_single(
        self,
        worker_id: str,
        body: Any,
        *,
        timeout_sec: float = 600.0,
        _skip_skill_inject: bool = False,
        meta: Optional[Dict[str, Any]] = None,
        stream_callback: Any = None,
    ) -> Dict[str, Any]:
        raise RuntimeError(
            "desktop blueprint runtime v1 does not execute CLI workers; "
            "only run registration, initial queueing, status, events, and end are available"
        )


class DesktopBlueprintSkillCatalog:
    """SkillSpace-compatible view over the desktop blueprint skill directories."""

    def __init__(self, skill_dirs: Optional[Path | Sequence[Path]]) -> None:
        if skill_dirs is None:
            raw_dirs: Sequence[Path] = []
        elif isinstance(skill_dirs, Path):
            raw_dirs = [skill_dirs]
        else:
            raw_dirs = list(skill_dirs)
        self.skill_dirs = [_resolve_catalog_dir(path) for path in raw_dirs if str(path).strip()]
        self.skill_dir = self.skill_dirs[0] if self.skill_dirs else None
        self._records: Optional[Dict[str, SkillRecord]] = None

    def records(self) -> Dict[str, SkillRecord]:
        if self._records is None:
            self._records = self._scan_records()
        return dict(self._records)

    def resolve_hashes(self, skill_hashes: Sequence[str]) -> list[SkillRecord]:
        records = self.records()
        resolved: list[SkillRecord] = []
        for raw in skill_hashes:
            key = str(raw).strip()
            rec = records.get(key)
            if rec is None:
                raise KeyError(f"skill not found in desktop skill directory: {key}")
            if self.skill_dirs and not _path_is_under_any(rec.skill_dir.resolve(), self.skill_dirs):
                raise ValueError(f"skill path escapes desktop skill directories: {rec.skill_dir}")
            resolved.append(rec)
        return resolved

    def _scan_records(self) -> Dict[str, SkillRecord]:
        records: Dict[str, SkillRecord] = {}
        for root in self.skill_dirs:
            if not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                skill_md = child / "SKILL.md"
                if not child.is_dir() or not skill_md.is_file():
                    continue
                name = child.name
                if name in records:
                    continue
                records[name] = SkillRecord(
                    skill_hash=name,
                    name=name,
                    description=_description_from_skill_md(skill_md),
                    skill_dir=child.resolve(),
                    skill_md_path=skill_md.resolve(),
                )
        return records


def default_codex_skill_dir() -> Path:
    raw = os.environ.get("CODEX_HOME")
    if raw and raw.strip():
        return Path(raw).expanduser() / "skills"
    return Path.home() / ".codex" / "skills"


def _resolve_catalog_dir(path: Path) -> Path:
    return Path(path).expanduser().resolve()


def _path_is_under_any(path: Path, roots: Sequence[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _blueprint_catalog_item_from_skill_record(rec: SkillRecord) -> Dict[str, str]:
    return {
        "value": rec.skill_hash,
        "label": rec.name,
        "description": rec.description,
    }


def list_blueprint_skills_for_dirs(skill_dirs: Sequence[Path]) -> list[Dict[str, str]]:
    roots = list(skill_dirs) or [default_codex_skill_dir()]
    records = DesktopBlueprintSkillCatalog(roots).records()
    return [_blueprint_catalog_item_from_skill_record(rec) for rec in records.values()]


def list_default_blueprint_skills() -> list[Dict[str, str]]:
    return list_blueprint_skills_for_dirs([default_codex_skill_dir()])


def list_blueprint_rules_for_dirs(rule_dirs: Sequence[Path]) -> list[Dict[str, str]]:
    rules: list[Dict[str, str]] = []
    seen: set[str] = set()
    for root in [_resolve_catalog_dir(path) for path in rule_dirs if str(path).strip()]:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_file() or child.name.startswith("."):
                continue
            resolved = str(child.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            rules.append(
                {
                    "value": resolved,
                    "label": child.name,
                    "description": str(root),
                }
            )
    return rules


def parse_codex_model_slugs(output: str) -> list[str]:
    try:
        data = json.loads(str(output or "").strip())
    except json.JSONDecodeError:
        return []
    raw_models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(raw_models, list):
        return []
    models: list[str] = []
    seen: set[str] = set()
    for item in raw_models:
        slug = str(item.get("slug", "")).strip() if isinstance(item, dict) else ""
        if not slug or slug in seen:
            continue
        seen.add(slug)
        models.append(slug)
    return models


def codex_model_command_candidates() -> list[list[str]]:
    commands = [["codex", "debug", "models"]]
    if sys.platform == "win32":
        commands.append(["codex.cmd", "debug", "models"])
    return commands


def list_blueprint_models(cli_kind: str = "codex") -> list[str]:
    kind = str(cli_kind or "").strip() or "codex"
    if kind != "codex":
        return []
    commands = codex_model_command_candidates()
    for index, command in enumerate(commands):
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=BLUEPRINT_MODEL_COMMAND_TIMEOUT_SECONDS,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            log.warning("codex model listing timed out: %s", exc)
            return []
        except (FileNotFoundError, OSError) as exc:
            if index + 1 < len(commands):
                continue
            log.warning("codex model listing failed: %s", exc)
            return []
        if proc.returncode != 0:
            log.warning(
                "codex model listing failed with exit code %s: %s",
                proc.returncode,
                str(proc.stderr or "").strip(),
            )
            return []
        return parse_codex_model_slugs(proc.stdout)
    return []


@dataclass
class DesktopBlueprintService:
    """Project blueprint persistence and validation facade."""

    now: Any = time.time
    resident_services_data_dir: Optional[Path] = None
    _lock: Any = field(default_factory=threading.RLock, init=False, repr=False)
    _runs: Dict[str, DesktopBlueprintRun] = field(default_factory=dict, init=False, repr=False)
    _planning_sessions: Dict[str, DesktopBlueprintPlanningSession] = field(default_factory=dict, init=False, repr=False)
    _async_loop: DesktopAsyncLoop = field(default_factory=DesktopAsyncLoop, init=False, repr=False)
    _stream_tokens: Dict[str, Dict[str, Any]] = field(default_factory=dict, init=False, repr=False)
    _pending_rollbacks: set[str] = field(default_factory=set, init=False, repr=False)
    _popo_token_cache: Dict[str, Dict[str, Any]] = field(default_factory=dict, init=False, repr=False)
    _popo_progress_cards: Dict[str, PopoStreamingProgressCard] = field(default_factory=dict, init=False, repr=False)
    _table_queue_notification_stop: Any = field(default_factory=threading.Event, init=False, repr=False)
    _table_queue_notification_thread: Optional[threading.Thread] = field(default=None, init=False, repr=False)
    _planning_table_skill_update_notification_stop: Any = field(default_factory=threading.Event, init=False, repr=False)
    _planning_table_skill_update_notification_thread: Optional[threading.Thread] = field(
        default=None,
        init=False,
        repr=False,
    )

    def handle_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        command = str(payload.get("command", "")).strip()
        args = payload.get("args", {})
        if not isinstance(args, dict):
            raise BlueprintServiceError("BAD_REQUEST", "args must be a JSON object")

        if command == "blueprint.list":
            project_dir = request_project_dir(args)
            return {"ok": True, "blueprints": self.list_blueprints(project_dir)}
        if command == "blueprint.open":
            project_dir = request_project_dir(args)
            document = self.open_blueprint(
                project_dir,
                str(args.get("blueprintId", DEFAULT_BLUEPRINT_ID)),
            )
            self._record_current_open_blueprint(project_dir, document)
            return {
                "ok": True,
                "document": document,
            }
        if command == "blueprint.create":
            project_dir = request_project_dir(args)
            blueprint_id = args.get("blueprintId")
            name = args.get("name")
            return self.create_blueprint(
                project_dir,
                blueprint_id=str(blueprint_id).strip() if blueprint_id is not None else None,
                name=str(name).strip() if name is not None else None,
            )
        if command == "blueprint.delete":
            project_dir = request_project_dir(args)
            return self.delete_blueprint(
                project_dir,
                str(args.get("blueprintId", DEFAULT_BLUEPRINT_ID)),
            )
        if command == "blueprint.save":
            project_dir = request_project_dir(args)
            document = args.get("document")
            if not isinstance(document, dict):
                raise BlueprintServiceError("BAD_REQUEST", "document must be a JSON object")
            saved = self.save_blueprint(project_dir, document)
            return {"ok": True, "document": saved}
        if command == "blueprint.detectPython":
            raw_project_dir = args.get("projectDir")
            project_dir = request_project_dir(args) if isinstance(raw_project_dir, str) and raw_project_dir.strip() else None
            python_command = args.get("pythonCommand")
            if python_command is not None and not isinstance(python_command, str):
                raise BlueprintServiceError("BAD_REQUEST", "pythonCommand must be a string")
            return detect_blueprint_python(project_dir=project_dir, python_command=python_command)
        if command == "blueprint.listModels":
            return {"ok": True, "models": list_blueprint_models(str(args.get("cliKind", "codex")))}
        if command == "blueprint.scriptNodes":
            project_dir = request_project_dir(args)
            return {"ok": True, **discover_script_nodes(project_dir)}
        if command == "blueprint.createScriptNode":
            project_dir = request_project_dir(args)
            name = args.get("name")
            if not isinstance(name, str) or not name.strip():
                raise BlueprintServiceError("BAD_REQUEST", "name must be a non-empty string")
            description = args.get("description")
            if description is not None and not isinstance(description, str):
                raise BlueprintServiceError("BAD_REQUEST", "description must be a string")
            return {"ok": True, **create_script_node(project_dir, name, description or "")}
        if command == "blueprint.listEditors":
            return {"ok": True, "editors": list_blueprint_editors()}
        if command == "blueprint.openScriptInEditor":
            project_dir = request_project_dir(args)
            module_path = args.get("modulePath")
            if not isinstance(module_path, str) or not module_path.strip():
                raise BlueprintServiceError("BAD_REQUEST", "modulePath must be a non-empty string")
            editor_id = args.get("editorId")
            if editor_id is not None and not isinstance(editor_id, str):
                raise BlueprintServiceError("BAD_REQUEST", "editorId must be a string")
            return open_blueprint_script_in_editor(project_dir, module_path, editor_id)
        if command == "blueprint.listSkills":
            skill_dirs = _request_path_list(args, "dirs", "dir")
            return {"ok": True, "skills": list_blueprint_skills_for_dirs(skill_dirs)}
        if command == "blueprint.listRules":
            rule_dirs = _request_path_list(args, "dirs", "dir")
            return {"ok": True, "rules": list_blueprint_rules_for_dirs(rule_dirs)}
        if command == "blueprint.residentServices":
            return {"ok": True, **self.resident_service_manager().discover()}
        if command == "blueprint.popo.robots":
            return self.list_popo_robots()
        if command == "blueprint.popo.robot.save":
            return self.save_popo_robot(
                args.get("robot") if isinstance(args.get("robot"), dict) else args,
                previous_robot_app_key=str(args.get("previousRobotAppKey") or args.get("previous_robot_app_key") or "").strip() or None,
            )
        if command == "blueprint.popo.robot.delete":
            return self.delete_popo_robot(str(args.get("robotAppKey") or args.get("robot_app_key") or "").strip())
        if command == "blueprint.popo.robot.enabled":
            return self.set_popo_robot_enabled(
                str(args.get("robotAppKey") or args.get("robot_app_key") or "").strip(),
                bool(args.get("enabled")),
            )
        if command == "blueprint.popo.callbackConfig":
            robot_app_key = str(args.get("robotAppKey", "") or args.get("robot_app_key", "") or "").strip()
            raw_project_dir = args.get("projectDir")
            return self.resolve_popo_callback_config(
                robot_app_key,
                project_dir=Path(raw_project_dir) if isinstance(raw_project_dir, str) and raw_project_dir.strip() else None,
            )
        if command == "blueprint.createResidentService":
            name = args.get("name")
            if not isinstance(name, str) or not name.strip():
                raise BlueprintServiceError("BAD_REQUEST", "name must be a non-empty string")
            description = args.get("description")
            if description is not None and not isinstance(description, str):
                raise BlueprintServiceError("BAD_REQUEST", "description must be a string")
            return {"ok": True, **self.resident_service_manager().create(name, description or "")}
        if command == "blueprint.openResidentServiceInEditor":
            module_path = args.get("modulePath")
            if not isinstance(module_path, str) or not module_path.strip():
                raise BlueprintServiceError("BAD_REQUEST", "modulePath must be a non-empty string")
            editor_id = args.get("editorId")
            if editor_id is not None and not isinstance(editor_id, str):
                raise BlueprintServiceError("BAD_REQUEST", "editorId must be a string")
            return open_blueprint_resident_service_in_editor(
                self.resident_service_data_dir(),
                module_path,
                editor_id,
            )
        if command == "blueprint.startResidentService":
            service_name = args.get("serviceName")
            if not isinstance(service_name, str) or not service_name.strip():
                raise BlueprintServiceError("BAD_REQUEST", "serviceName must be a non-empty string")
            return self.resident_service_manager().start(service_name)
        if command == "blueprint.stopResidentService":
            service_name = args.get("serviceName")
            if not isinstance(service_name, str) or not service_name.strip():
                raise BlueprintServiceError("BAD_REQUEST", "serviceName must be a non-empty string")
            return self.resident_service_manager().stop(service_name)
        if command == "blueprint.residentServiceLogs":
            service_name = args.get("serviceName")
            if not isinstance(service_name, str) or not service_name.strip():
                raise BlueprintServiceError("BAD_REQUEST", "serviceName must be a non-empty string")
            return self.resident_service_manager().logs(service_name, limit=int(args.get("limit", 200)))
        if command == "blueprint.residentServiceDocs":
            service_name = args.get("serviceName")
            if not isinstance(service_name, str) or not service_name.strip():
                raise BlueprintServiceError("BAD_REQUEST", "serviceName must be a non-empty string")
            return self.resident_service_manager().docs(service_name)
        if command == "blueprint.relocateProjectWorkdir":
            project_dir = request_project_dir(args)
            document = args.get("document")
            if not isinstance(document, dict):
                raise BlueprintServiceError("BAD_REQUEST", "document must be a JSON object")
            project_workdir = args.get("projectWorkdir")
            if not isinstance(project_workdir, str) or not project_workdir.strip():
                raise BlueprintServiceError("BAD_REQUEST", "projectWorkdir must be a non-empty string")
            return self.relocate_project_workdir(
                project_dir,
                str(args.get("blueprintId", DEFAULT_BLUEPRINT_ID)),
                document,
                project_workdir,
                conflict_policy=str(args.get("conflictPolicy", "") or "").strip() or None,
            )
        if command == "blueprint.validate":
            project_dir = request_project_dir(args)
            if args.get("document") is not None:
                document = args["document"]
                if not isinstance(document, dict):
                    raise BlueprintServiceError("BAD_REQUEST", "document must be a JSON object")
            else:
                document = self.open_blueprint(
                    project_dir,
                    str(args.get("blueprintId", DEFAULT_BLUEPRINT_ID)),
                )
            return self.validate_blueprint(document, project_dir=project_dir)
        if command == "blueprint.runtime.setStartAgent":
            project_dir = request_project_dir(args)
            return self.set_blueprint_start_agent(
                project_dir,
                str(args.get("blueprintId", DEFAULT_BLUEPRINT_ID)),
                str(args.get("startNodeId") or args.get("start_node_id") or "").strip(),
            )
        if command == "blueprint.runtime.executePlan":
            project_dir = request_project_dir(args)
            return self.execute_blueprint_plan(
                project_dir,
                str(args.get("blueprintId", DEFAULT_BLUEPRINT_ID)),
                args.get("plan"),
                execution_mode=str(args.get("executionMode", "live")),
            )
        if command == "blueprint.sessions.list":
            project_dir = args.get("projectDir")
            blueprint_id = args.get("blueprintId")
            return {
                "ok": True,
                "sessions": self.list_blueprint_sessions(
                    Path(project_dir) if isinstance(project_dir, str) and project_dir.strip() else None,
                    str(blueprint_id) if blueprint_id is not None else None,
                ),
            }
        if command == "blueprint.sessions.excelHistoryList":
            project_dir = args.get("projectDir")
            blueprint_id = args.get("blueprintId")
            return self.list_blueprint_session_excel_history(
                Path(project_dir) if isinstance(project_dir, str) and project_dir.strip() else None,
                str(blueprint_id) if blueprint_id is not None else None,
                category=str(args.get("category", "all") or "all"),
            )
        if command == "blueprint.sessions.excelHistory":
            return self.blueprint_session_excel_history(
                str(args.get("sessionKey", "")).strip(),
                category=str(args.get("category", "all") or "all"),
                limit=int(args.get("limit", 200) or 200),
            )
        if command == "blueprint.sessions.timeline":
            return self.blueprint_session_timeline(
                str(args.get("sessionKey", "")).strip(),
                limit=int(args.get("limit", BLUEPRINT_SESSION_TIMELINE_LIMIT) or BLUEPRINT_SESSION_TIMELINE_LIMIT),
            )
        if command == "blueprint.sessions.delete":
            return self.delete_blueprint_session(str(args.get("sessionKey", "")).strip())
        if command == "blueprint.sessions.terminate":
            return self.terminate_blueprint_session(
                str(args.get("sessionKey", "")).strip(),
                reason=str(args.get("reason", "")),
            )
        if command == "blueprint.sessions.clear":
            return self.clear_blueprint_session_history(
                str(args.get("sessionKey", "")).strip(),
                reason=str(args.get("reason", "")),
            )
        if command == "blueprint.sessions.restartBlueprint":
            return self.restart_blueprint_sessions(
                request_project_dir(args),
                str(args.get("blueprintId", DEFAULT_BLUEPRINT_ID)),
                reason=str(args.get("reason", "")),
            )
        if command == "blueprint.sessions.processTableQueueNotifications":
            return self.process_table_queue_notifications(
                limit=int(args.get("limit", 100) or 100),
            )
        if command == "blueprint.sessions.processPlanningTableSkillUpdateNotifications":
            return self.process_planning_table_skill_update_notifications(
                limit=int(args.get("limit", 100) or 100),
            )
        if command == "blueprint.sessions.message":
            raw_project_dir = args.get("projectDir")
            source_identity = args.get("sourceIdentity")
            session_identity = args.get("sessionIdentity")
            source = str(args.get("source", "ui"))
            if not isinstance(source_identity, dict):
                source_identity = {"robotAppKey": str(args.get("popoRobotAppKey", "") or "")}
            if not isinstance(session_identity, dict):
                session_identity = {
                    "popoUserId": str(args.get("popoUserId", "") or ""),
                    "popoSessionId": str(args.get("popoSessionId", "") or ""),
                    "popoGroupId": str(args.get("popoGroupId", "") or ""),
                    "popoReplyTo": str(args.get("popoReplyTo", "") or ""),
                    "popoSessionType": str(args.get("popoSessionType", "") or ""),
                }
            if (
                (not isinstance(raw_project_dir, str) or not raw_project_dir.strip())
                and source.strip().lower() == "popo"
                and args.get("runId") is None
            ):
                return self.message_global_popo_blueprint_session(
                    str(args.get("message", "")),
                    source_identity=source_identity,
                    session_identity=session_identity,
                    session_key=str(args.get("sessionKey", "") or "").strip() or None,
                )
            project_dir = request_project_dir(args)
            return self.message_blueprint_session(
                project_dir,
                (str(args.get("blueprintId")) if args.get("blueprintId") is not None else None),
                str(args.get("message", "")),
                source=source,
                source_identity=source_identity,
                session_identity=session_identity,
                session_key=str(args.get("sessionKey", "") or "").strip() or None,
            )
        if command == "blueprint.popo.config":
            robot_app_key = str(args.get("robotAppKey", "") or args.get("robot_app_key", "") or "").strip()
            raw_project_dir = args.get("projectDir")
            if isinstance(raw_project_dir, str) and raw_project_dir.strip():
                binding = self._find_popo_blueprint_binding(Path(raw_project_dir), robot_app_key)
            else:
                binding = self._find_global_popo_blueprint_binding(robot_app_key)
            popo_entry = binding.get("popoEntry") if isinstance(binding.get("popoEntry"), dict) else {}
            resolved_robot_app_key = str(popo_entry.get("robot_app_key") or robot_app_key).strip()
            return {
                "ok": True,
                "robotAppKey": resolved_robot_app_key,
                "projectDir": binding.get("projectDir", ""),
                "blueprintId": binding["blueprintId"],
                "blueprintName": binding["blueprintName"],
                "blueprintStructureId": binding["blueprintStructureId"],
                "startNodeId": binding["startNodeId"],
                "popoEntry": binding["popoEntry"],
            }
        if command == "blueprint.plan.create":
            project_dir = request_project_dir(args)
            return self.create_blueprint_start_plan(
                project_dir,
                str(args.get("blueprintId", DEFAULT_BLUEPRINT_ID)),
                task=args.get("task"),
                start_node_ids=args.get("startNodeIds"),
                plan_overrides=args.get("planOverrides"),
            )
        if command == "blueprint.plan.validate":
            project_dir = request_project_dir(args)
            return self.validate_blueprint_start_plan(
                project_dir,
                str(args.get("blueprintId", DEFAULT_BLUEPRINT_ID)),
                args.get("plan"),
            )
        if command == "blueprint.listRuns":
            project_dir = args.get("projectDir")
            blueprint_id = args.get("blueprintId")
            return {
                "ok": True,
                "runs": self.list_blueprint_runs(
                    Path(project_dir) if isinstance(project_dir, str) and project_dir.strip() else None,
                    str(blueprint_id) if blueprint_id is not None else None,
                ),
            }
        if command == "blueprint.start":
            project_dir = request_project_dir(args)
            return self.start_blueprint_run(
                project_dir,
                str(args.get("blueprintId", DEFAULT_BLUEPRINT_ID)),
                args.get("plan"),
                execution_mode=str(args.get("executionMode", "status")),
            )
        if command == "blueprint.status":
            return self.status_blueprint_run(request_run_id(args))
        if command == "blueprint.runDiff":
            return self.blueprint_run_diff(request_run_id(args))
        if command == "blueprint.changesetDiff":
            return self.blueprint_changeset_diff(
                request_run_id(args),
                str(args.get("changesetId") or args.get("changeset_id") or "").strip(),
            )
        if command == "blueprint.rollbackChangesets":
            return self.rollback_blueprint_changesets(
                request_run_id(args),
                str(args.get("toChangesetId") or args.get("to_changeset_id") or args.get("changesetId") or "").strip(),
                reason=str(args.get("reason", "")),
            )
        if command == "blueprint.restoreRollback":
            rollback_id = args.get("rollbackId") or args.get("rollback_id")
            return self.restore_blueprint_rollback(
                request_run_id(args),
                rollback_id=str(rollback_id).strip() if rollback_id is not None else None,
                reason=str(args.get("reason", "")),
            )
        if command == "blueprint.end":
            return self.end_blueprint_run(
                request_run_id(args),
                str(args.get("action", "")).strip(),
                reason=str(args.get("reason", "")),
            )
        if command == "blueprint.recentEvents":
            return self.recent_blueprint_events(
                request_run_id(args),
                limit=coerce_event_limit(args.get("limit", 20)),
            )
        if command == "blueprint.agentInfo":
            return self.agent_info(
                str(args.get("nodeId", "")).strip(),
                run_id=str(args.get("runId", "")).strip() or None,
            )
        if command == "blueprint.queueAgentMessage":
            return self.queue_agent_message(
                request_run_id(args),
                str(args.get("nodeId", "")).strip(),
                str(args.get("text", "")),
                mode=str(args.get("mode", "default")),
            )
        if command == "blueprint.agentStreamToken":
            return self.agent_stream_token(
                request_run_id(args),
                base_url=str(args.get("baseUrl", "")),
                cursor=args.get("cursor"),
            )
        if command == "blueprint.planning.ensureContext":
            return self.ensure_blueprint_planning_context(
                request_project_dir(args),
                str(args.get("blueprintId", DEFAULT_BLUEPRINT_ID)),
                str(args.get("desktopSessionId", "")).strip(),
            )
        if command == "blueprint.planning.answerQuestion":
            return self.answer_blueprint_planning_question(
                str(args.get("sessionId", "")).strip(),
                str(args.get("questionId", "")).strip(),
                args.get("answers"),
                rejected=bool(args.get("rejected", False)),
                reason=str(args.get("reason", "")),
            )
        if command == "blueprint.planning.rejectPlan":
            return self.reject_blueprint_planning_plan(
                str(args.get("sessionId", "")).strip(),
                reason=str(args.get("reason", "")),
            )
        if command == "blueprint.planning.markPlanStarted":
            return self.mark_blueprint_planning_plan_started(
                str(args.get("sessionId", "")).strip(),
                str(args.get("runId", "")).strip(),
                started=args.get("started"),
            )
        if command == "blueprint.planning.status":
            return self.blueprint_planning_status(str(args.get("sessionId", "")).strip())
        if command == "blueprint.planning.endSession":
            return self.end_blueprint_planning_session(
                str(args.get("sessionId", "")).strip(),
                reason=str(args.get("reason", "")),
            )

        raise BlueprintServiceError("UNKNOWN_COMMAND", f"unsupported desktop blueprint command: {command!r}")

    def resident_service_data_dir(self) -> Path:
        if self.resident_services_data_dir is not None:
            return Path(self.resident_services_data_dir).expanduser().resolve()
        env_data_dir = os.environ.get("GULICODE_BP_DATA_DIR")
        if env_data_dir:
            return Path(env_data_dir).expanduser().resolve()
        codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()
        return (codex_home / "gulicode-bp" / "state").resolve()

    def resident_service_manager(self) -> ResidentServiceManager:
        return ResidentServiceManager(self.resident_service_data_dir())

    def blueprint_project_registry_path(self) -> Path:
        return self.resident_service_data_dir() / BLUEPRINT_PROJECT_REGISTRY_FILENAME

    def popo_robot_routes_path(self) -> Path:
        return self.resident_service_data_dir() / POPO_ROBOT_ROUTES_FILENAME

    def _read_popo_robot_routes(self) -> Dict[str, Any]:
        path = self.popo_robot_routes_path()
        if not path.is_file():
            return {"version": 1, "robots": {}}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "robots": {}}
        if not isinstance(payload, dict):
            return {"version": 1, "robots": {}}
        robots = payload.get("robots")
        if isinstance(robots, list):
            normalized = {}
            for item in robots:
                if not isinstance(item, dict):
                    continue
                robot = normalize_popo_robot_route(item)
                key = str(robot.get("robot_app_key") or "").strip()
                if key:
                    normalized[key] = robot
            robots = normalized
        if not isinstance(robots, dict):
            robots = {}
        return {"version": 1, "robots": robots}

    def _write_popo_robot_routes(self, routes: Dict[str, Any]) -> None:
        self._atomic_write_json(self.popo_robot_routes_path(), routes)

    def list_popo_robots(self) -> Dict[str, Any]:
        routes = self._read_popo_robot_routes()
        robots = []
        for item in (routes.get("robots") or {}).values():
            if not isinstance(item, dict):
                continue
            robot = normalize_popo_robot_route(item)
            if str(robot.get("robot_app_key") or "").strip():
                robots.append(robot)
        robots.sort(key=lambda item: (str(item.get("robot_name") or "").casefold(), str(item.get("robot_app_key") or "")))
        return {"ok": True, "robots": robots, "path": str(self.popo_robot_routes_path())}

    def save_popo_robot(self, robot_payload: Any, *, previous_robot_app_key: Optional[str] = None) -> Dict[str, Any]:
        if not isinstance(robot_payload, dict):
            raise BlueprintServiceError("BAD_REQUEST", "robot must be a JSON object")
        robot = normalize_popo_robot_route(robot_payload)
        robot_app_key = str(robot.get("robot_app_key") or "").strip()
        if not robot_app_key:
            raise BlueprintServiceError("BAD_REQUEST", "robotAppKey must be a non-empty string")
        missing = popo_callback_robot_missing_fields(robot)
        if robot.get("enabled") and missing:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_ENTRY_REQUIRED",
                "enabled POPO callback robots require complete credentials",
                details={"robotAppKey": robot_app_key, "missing": missing},
            )
        now = float(self.now())
        robot["updated_at"] = now
        with self._lock:
            routes = self._read_popo_robot_routes()
            robots = dict(routes.get("robots") or {})
            previous = str(previous_robot_app_key or "").strip()
            if previous and previous != robot_app_key:
                robots.pop(previous, None)
            robots[robot_app_key] = robot
            routes = {"version": 1, "robots": robots, "updatedAt": now}
            self._write_popo_robot_routes(routes)
        return {"ok": True, "robot": robot, "robots": self.list_popo_robots()["robots"]}

    def delete_popo_robot(self, robot_app_key: str) -> Dict[str, Any]:
        key = str(robot_app_key or "").strip()
        if not key:
            raise BlueprintServiceError("BAD_REQUEST", "robotAppKey must be a non-empty string")
        now = float(self.now())
        with self._lock:
            routes = self._read_popo_robot_routes()
            robots = dict(routes.get("robots") or {})
            deleted = key in robots
            robots.pop(key, None)
            self._write_popo_robot_routes({"version": 1, "robots": robots, "updatedAt": now})
        return {"ok": True, "robotAppKey": key, "deleted": deleted, "robots": self.list_popo_robots()["robots"]}

    def set_popo_robot_enabled(self, robot_app_key: str, enabled: bool) -> Dict[str, Any]:
        key = str(robot_app_key or "").strip()
        if not key:
            raise BlueprintServiceError("BAD_REQUEST", "robotAppKey must be a non-empty string")
        now = float(self.now())
        with self._lock:
            routes = self._read_popo_robot_routes()
            robots = dict(routes.get("robots") or {})
            if key not in robots or not isinstance(robots.get(key), dict):
                raise BlueprintServiceError(
                    "BLUEPRINT_POPO_ROBOT_NOT_BOUND",
                    "POPO callback robot is not configured",
                    details={"robotAppKey": key},
                    status=404,
                )
            robot = normalize_popo_robot_route(robots[key])
            missing = popo_callback_robot_missing_fields(robot)
            if enabled and missing:
                raise BlueprintServiceError(
                    "BLUEPRINT_POPO_ENTRY_REQUIRED",
                    "enabled POPO callback robots require complete credentials",
                    details={"robotAppKey": key, "missing": missing},
                )
            robot["enabled"] = bool(enabled)
            robot["updated_at"] = now
            robots[key] = robot
            self._write_popo_robot_routes({"version": 1, "robots": robots, "updatedAt": now})
        return {"ok": True, "robot": robot, "robots": self.list_popo_robots()["robots"]}

    def _resolve_popo_callback_robot(self, robot_app_key: str) -> Dict[str, Any]:
        key = str(robot_app_key or "").strip()
        routes = self._read_popo_robot_routes()
        robots = routes.get("robots") if isinstance(routes.get("robots"), dict) else {}
        if key:
            raw = robots.get(key) if isinstance(robots, dict) else None
            if not isinstance(raw, dict):
                raise BlueprintServiceError(
                    "BLUEPRINT_POPO_ROBOT_NOT_BOUND",
                    "POPO callback robot is not configured",
                    details={"robotAppKey": key},
                    status=404,
                )
            robot = normalize_popo_robot_route(raw)
            if not robot.get("enabled"):
                raise BlueprintServiceError(
                    "BLUEPRINT_POPO_ROBOT_DISABLED",
                    "POPO callback robot is disabled",
                    details={"robotAppKey": key},
                    status=403,
                )
            return robot

        enabled = [
            normalize_popo_robot_route(item)
            for item in (robots.values() if isinstance(robots, dict) else [])
            if isinstance(item, dict) and normalize_popo_robot_route(item).get("enabled")
        ]
        if not enabled:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_ROBOT_NOT_BOUND",
                "no enabled POPO callback robot is configured",
                details={"robotAppKey": key},
                status=404,
            )
        if len(enabled) > 1:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_ROBOT_STRUCTURE_CONFLICT",
                "legacy POPO callback path matched multiple enabled callback robots",
                details={"robotAppKeys": sorted(str(item.get("robot_app_key") or "") for item in enabled)},
                status=409,
            )
        return enabled[0]

    def resolve_popo_callback_config(self, robot_app_key: str, *, project_dir: Optional[Path] = None) -> Dict[str, Any]:
        robot = self._resolve_popo_callback_robot(robot_app_key)
        resolved_robot_app_key = str(robot.get("robot_app_key") or "").strip()
        missing = popo_callback_robot_missing_fields(robot)
        if missing:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_ENTRY_REQUIRED",
                "enabled POPO callback robot is incomplete",
                details={"robotAppKey": resolved_robot_app_key, "missing": missing},
            )
        if project_dir is not None:
            binding = self._find_popo_blueprint_binding(project_dir, resolved_robot_app_key)
        else:
            binding = self._find_global_popo_blueprint_binding(resolved_robot_app_key)
        return {
            "ok": True,
            "robotAppKey": resolved_robot_app_key,
            "projectDir": binding.get("projectDir", ""),
            "blueprintId": binding["blueprintId"],
            "blueprintName": binding["blueprintName"],
            "blueprintStructureId": binding["blueprintStructureId"],
            "startNodeId": binding["startNodeId"],
            "popoEntry": robot,
            "blueprintPopoEntry": binding["popoEntry"],
        }

    def _get_popo_access_token(self, robot_config: Dict[str, Any]) -> str:
        app_key = str(robot_config.get("robot_app_key") or "").strip()
        app_secret = str(robot_config.get("robot_app_secret") or "").strip()
        if not app_key or not app_secret:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_ENTRY_REQUIRED",
                "POPO robot credentials are incomplete",
                details={"robotAppKey": app_key, "missing": [key for key in ("robot_app_key", "robot_app_secret") if not str(robot_config.get(key) or "").strip()]},
                status=400,
            )
        now_ms = int(time.time() * 1000)
        with self._lock:
            cached = dict(self._popo_token_cache.get(app_key) or {})
        if cached.get("access_token") and int(cached.get("expired_at") or 0) - now_ms > 300000:
            return str(cached["access_token"])

        try:
            response = requests.post(
                f"{POPO_API_BASE}/open-apis/robots/v1/token",
                json={"appKey": app_key, "appSecret": app_secret},
                timeout=10,
            )
            data = response.json()
        except Exception as exc:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_TOKEN_FAILED",
                "failed to request POPO access token",
                details={"robotAppKey": app_key, "error": str(exc)},
                status=502,
            ) from exc
        if not isinstance(data, dict):
            data = {}
        if response.status_code >= 400 or data.get("errcode") != 0 or not isinstance(data.get("data"), dict):
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_TOKEN_FAILED",
                "POPO access token request failed",
                details={
                    "robotAppKey": app_key,
                    "statusCode": response.status_code,
                    "errcode": data.get("errcode"),
                    "errmsg": data.get("errmsg"),
                },
                status=502,
            )
        token_data = data["data"]
        access_token = str(token_data.get("accessToken") or "").strip()
        if not access_token:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_TOKEN_FAILED",
                "POPO access token response did not include accessToken",
                details={"robotAppKey": app_key},
                status=502,
            )
        with self._lock:
            self._popo_token_cache[app_key] = {
                "access_token": access_token,
                "expired_at": int(token_data.get("accessExpiredAt") or 0),
            }
        return access_token

    def _popo_api_headers(self, token: str) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Open-Access-Token": token,
        }

    def _safe_popo_response_json(self, response: Any) -> Dict[str, Any]:
        try:
            data = response.json()
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _summarize_popo_send_error(self, exc: Exception) -> str:
        if isinstance(exc, BlueprintServiceError):
            details = exc.details if isinstance(exc.details, dict) else {}
            parts = [exc.code]
            status_code = details.get("statusCode")
            errcode = details.get("errcode")
            errmsg = str(details.get("errmsg") or "").strip()
            if status_code is not None:
                parts.append(f"status={status_code}")
            if errcode is not None:
                parts.append(f"errcode={errcode}")
            if errmsg:
                parts.append(f"errmsg={errmsg[:160]}")
            return "; ".join(parts)
        message = str(exc).strip()
        return f"{type(exc).__name__}: {message[:200]}" if message else type(exc).__name__

    def _send_popo_text_message(
        self,
        *,
        receiver: str,
        content: str,
        token: str,
    ) -> Dict[str, Any]:
        try:
            response = requests.post(
                f"{POPO_API_BASE}/open-apis/robots/v1/im/send-msg",
                json={
                    "receiver": receiver,
                    "msgType": "text",
                    "message": {"content": content},
                },
                headers=self._popo_api_headers(token),
                timeout=10,
            )
            data = self._safe_popo_response_json(response)
        except Exception as exc:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_SEND_FAILED",
                "failed to send POPO reply",
                details={"error": str(exc)},
                status=502,
            ) from exc
        if response.status_code >= 400 or data.get("errcode") != 0:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_SEND_FAILED",
                "POPO send-msg request failed",
                details={
                    "statusCode": response.status_code,
                    "errcode": data.get("errcode"),
                    "errmsg": data.get("errmsg"),
                },
                status=502,
            )
        return {"ok": True, "sent": True, "errcode": data.get("errcode")}

    def _create_popo_streaming_card(
        self,
        *,
        receiver: str,
        compatible_message: str,
        token: str,
        last_message: str = "",
    ) -> Dict[str, Any]:
        instance_uuid = str(uuid.uuid4())
        compatible_text = str(compatible_message or "").strip() or POPO_PROGRESS_THINKING_TEXT
        init_payload = {
            "receiver": receiver,
            "msgType": "card",
            "message": {
                "instanceUuid": instance_uuid,
                "templateUuid": POPO_STREAMING_CARD_TEMPLATE_UUID,
                "options": {
                    "enableForward": True,
                    "enableMultipleSelected": True,
                    "lastMessage": str(last_message or "").strip() or POPO_STREAMING_CARD_LAST_MESSAGE,
                    "compatibleMessage": compatible_text,
                },
            },
        }
        try:
            init_response = requests.post(
                f"{POPO_API_BASE}/open-apis/robots/v1/im/send-msg",
                json=init_payload,
                headers=self._popo_api_headers(token),
                timeout=10,
            )
            init_data = self._safe_popo_response_json(init_response)
        except Exception as exc:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_SEND_FAILED",
                "failed to initialize POPO streaming card",
                details={"error": str(exc)},
                status=502,
            ) from exc
        if init_response.status_code >= 400 or init_data.get("errcode") != 0:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_SEND_FAILED",
                "POPO streaming card init request failed",
                details={
                    "statusCode": init_response.status_code,
                    "errcode": init_data.get("errcode"),
                    "errmsg": init_data.get("errmsg"),
                },
                status=502,
            )
        message_id = ""
        data = init_data.get("data")
        msg_info = data.get("msgInfo") if isinstance(data, dict) else None
        if isinstance(msg_info, dict):
            message_id = str(msg_info.get(receiver) or "").strip()
            if not message_id:
                for value in msg_info.values():
                    message_id = str(value or "").strip()
                    if message_id:
                        break
        return {
            "ok": True,
            "instanceUuid": instance_uuid,
            "popoMessageId": message_id,
            "errcode": init_data.get("errcode"),
        }

    def _update_popo_streaming_card(
        self,
        *,
        instance_uuid: str,
        content: str,
        token: str,
        sequence: int,
        is_finalize: bool,
    ) -> Dict[str, Any]:
        update_payload = {
            "instanceUuid": instance_uuid,
            "templateUuid": POPO_STREAMING_CARD_TEMPLATE_UUID,
            "key": POPO_STREAMING_CARD_KEY,
            "content": content,
            "sequence": int(sequence),
            "isFinalize": bool(is_finalize),
        }
        try:
            update_response = requests.put(
                f"{POPO_API_BASE}/open-apis/robots/v1/im/msg-card/stream",
                json=update_payload,
                headers=self._popo_api_headers(token),
                timeout=10,
            )
            update_data = self._safe_popo_response_json(update_response)
        except Exception as exc:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_SEND_FAILED",
                "failed to finalize POPO streaming card",
                details={"error": str(exc)},
                status=502,
            ) from exc
        if update_response.status_code >= 400 or update_data.get("errcode") != 0:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_SEND_FAILED",
                "POPO streaming card update request failed",
                details={
                    "statusCode": update_response.status_code,
                    "errcode": update_data.get("errcode"),
                    "errmsg": update_data.get("errmsg"),
                },
                status=502,
            )
        return {"ok": True, "sent": True, "errcode": update_data.get("errcode")}

    def _recall_popo_message(
        self,
        *,
        message_id: str,
        session_id: str,
        session_type: str,
        token: str,
    ) -> Dict[str, Any]:
        msg_id = str(message_id or "").strip()
        target_session_id = str(session_id or "").strip()
        raw_session_type = str(session_type or "").strip()
        if not msg_id:
            raise BlueprintServiceError("BLUEPRINT_POPO_RECALL_TARGET_REQUIRED", "POPO message id is missing", status=400)
        if not target_session_id:
            raise BlueprintServiceError("BLUEPRINT_POPO_RECALL_TARGET_REQUIRED", "POPO recall session id is missing", status=400)
        if not raw_session_type:
            raise BlueprintServiceError("BLUEPRINT_POPO_RECALL_TARGET_REQUIRED", "POPO recall session type is missing", status=400)
        recall_payload: Dict[str, Any] = {
            "sessionId": target_session_id,
            "sessionType": int(raw_session_type) if raw_session_type.isdigit() else raw_session_type,
        }
        try:
            recall_response = requests.post(
                f"{POPO_API_BASE}/open-apis/robots/v1/im/{msg_id}/recall",
                json=recall_payload,
                headers=self._popo_api_headers(token),
                timeout=10,
            )
            recall_data = self._safe_popo_response_json(recall_response)
        except Exception as exc:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_RECALL_FAILED",
                "failed to recall POPO message",
                details={"error": str(exc)},
                status=502,
            ) from exc
        if recall_response.status_code >= 400 or recall_data.get("errcode") != 0:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_RECALL_FAILED",
                "POPO recall request failed",
                details={
                    "statusCode": recall_response.status_code,
                    "errcode": recall_data.get("errcode"),
                    "errmsg": recall_data.get("errmsg"),
                },
                status=502,
            )
        return {"ok": True, "sent": True, "recalled": True, "errcode": recall_data.get("errcode")}

    def _send_popo_streaming_card_message(
        self,
        *,
        receiver: str,
        content: str,
        token: str,
    ) -> Dict[str, Any]:
        create_result = self._create_popo_streaming_card(
            receiver=receiver,
            compatible_message=content,
            token=token,
        )
        instance_uuid = str(create_result.get("instanceUuid") or "")
        update_data = self._update_popo_streaming_card(
            instance_uuid=instance_uuid,
            content=content,
            token=token,
            sequence=1,
            is_finalize=True,
        )
        return {
            "ok": True,
            "sent": True,
            "errcode": update_data.get("errcode"),
            "transport": "streaming_card",
            "messageId": instance_uuid,
        }

    def _send_popo_message(self, *, receiver: str, content: str, robot_config: Dict[str, Any]) -> Dict[str, Any]:
        target = str(receiver or "").strip()
        text = str(content or "").strip()
        if not target:
            raise BlueprintServiceError("BLUEPRINT_POPO_REPLY_TARGET_REQUIRED", "POPO reply receiver is missing", status=400)
        if not text:
            raise BlueprintServiceError("BAD_REQUEST", "POPO reply content must be a non-empty string", status=400)
        token = self._get_popo_access_token(robot_config)
        try:
            return self._send_popo_streaming_card_message(receiver=target, content=text, token=token)
        except Exception as exc:
            fallback_reason = self._summarize_popo_send_error(exc)
            log.warning("[blueprint] POPO streaming card send failed; falling back to text: %s", fallback_reason)
        result = self._send_popo_text_message(receiver=target, content=text, token=token)
        return {
            **result,
            "transport": "text_fallback",
            "fallbackReason": fallback_reason,
        }

    @staticmethod
    def _popo_reply_receiver_from_session(session: Dict[str, Any]) -> str:
        return (
            str(session.get("popoReplyTo") or "").strip()
            or str(session.get("popoGroupId") or "").strip()
            or str(session.get("popoUserId") or "").strip()
            or str(session.get("popoSessionId") or "").strip()
        )

    @staticmethod
    def _popo_recall_session_type_from_session(session: Dict[str, Any]) -> str:
        session_type = str(session.get("popoSessionType") or "").strip()
        if session_type:
            return session_type
        if str(session.get("popoGroupId") or "").strip():
            return "3"
        return "1"

    def _send_popo_progress_card_content(
        self,
        card: PopoStreamingProgressCard,
        *,
        content: str,
        is_finalize: bool,
    ) -> Optional[Dict[str, Any]]:
        text = str(content or "")
        if not text.strip():
            return None
        with self._lock:
            if card.finalized or card.failed:
                return None
            card.sequence += 1
            sequence = card.sequence
            token = card.token
            instance_uuid = card.instance_uuid
        try:
            result = self._update_popo_streaming_card(
                instance_uuid=instance_uuid,
                content=text,
                token=token,
                sequence=sequence,
                is_finalize=is_finalize,
            )
        except Exception as exc:
            fallback_reason = self._summarize_popo_send_error(exc)
            with self._lock:
                card.failed = True
                card.fallback_reason = fallback_reason
            log.warning("[blueprint] POPO progress card update failed: %s", fallback_reason)
            return {
                "ok": False,
                "sent": False,
                "transport": "streaming_card_progress",
                "messageId": card.instance_uuid,
                "fallbackReason": fallback_reason,
            }
        with self._lock:
            card.last_content = text if is_finalize else f"{card.last_content}{text}"
            card.last_update_at = time.monotonic()
            if is_finalize:
                card.finalized = True
                if self._popo_progress_cards.get(card.run_id) is card:
                    self._popo_progress_cards.pop(card.run_id, None)
        return {
            **result,
            "transport": "streaming_card_progress",
            "messageId": card.instance_uuid,
        }

    def _recall_popo_progress_card(self, card: PopoStreamingProgressCard) -> Optional[Dict[str, Any]]:
        with self._lock:
            if card.finalized:
                return None
            token = card.token
            popo_message_id = str(card.popo_message_id or "").strip()
            receiver = card.receiver
            session_type = str(card.session_type or "").strip() or "1"
        if not popo_message_id:
            fallback_reason = "missing POPO msgId for progress card recall"
            with self._lock:
                card.failed = True
                card.fallback_reason = fallback_reason
                if self._popo_progress_cards.get(card.run_id) is card:
                    self._popo_progress_cards.pop(card.run_id, None)
            log.warning("[blueprint] POPO progress card recall skipped: %s", fallback_reason)
            return {
                "ok": False,
                "sent": False,
                "transport": "streaming_card_progress_recall",
                "messageId": card.instance_uuid,
                "fallbackReason": fallback_reason,
            }
        try:
            result = self._recall_popo_message(
                message_id=popo_message_id,
                session_id=receiver,
                session_type=session_type,
                token=token,
            )
        except Exception as exc:
            fallback_reason = self._summarize_popo_send_error(exc)
            with self._lock:
                card.failed = True
                card.fallback_reason = fallback_reason
                if self._popo_progress_cards.get(card.run_id) is card:
                    self._popo_progress_cards.pop(card.run_id, None)
            log.warning("[blueprint] POPO progress card recall failed: %s", fallback_reason)
            return {
                "ok": False,
                "sent": False,
                "transport": "streaming_card_progress_recall",
                "messageId": card.instance_uuid,
                "popoMessageId": popo_message_id,
                "fallbackReason": fallback_reason,
            }
        with self._lock:
            card.finalized = True
            if self._popo_progress_cards.get(card.run_id) is card:
                self._popo_progress_cards.pop(card.run_id, None)
        return {
            **result,
            "transport": "streaming_card_progress_recall",
            "messageId": card.instance_uuid,
            "popoMessageId": popo_message_id,
        }

    def _begin_popo_progress_card_for_session(
        self,
        run: DesktopBlueprintRun,
        session: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if str(session.get("source") or "").strip().lower() != "popo":
            return None
        receiver = self._popo_reply_receiver_from_session(session)
        robot_app_key = str(run.robot_app_key or session.get("robotAppKey") or "").strip()
        if not receiver or not robot_app_key:
            return None
        with self._lock:
            previous = self._popo_progress_cards.pop(run.run_id, None)
        if previous is not None and not previous.finalized:
            self._recall_popo_progress_card(previous)
        try:
            robot = self._resolve_popo_callback_robot(robot_app_key)
            missing = popo_callback_robot_missing_fields(robot)
            if missing:
                log.warning(
                    "[blueprint] POPO progress card skipped; robot is incomplete: %s",
                    ", ".join(missing),
                )
                return None
            token = self._get_popo_access_token(robot)
            create_result = self._create_popo_streaming_card(
                receiver=receiver,
                compatible_message=POPO_PROGRESS_THINKING_TEXT,
                token=token,
                last_message=POPO_PROGRESS_THINKING_TEXT,
            )
        except Exception as exc:
            log.warning(
                "[blueprint] POPO progress card init skipped: %s",
                self._summarize_popo_send_error(exc),
            )
            return None
        card = PopoStreamingProgressCard(
            run_id=run.run_id,
            session_key=str(session.get("sessionKey") or run.session_key or "").strip(),
            receiver=receiver,
            robot_app_key=robot_app_key,
            token=token,
            instance_uuid=str(create_result.get("instanceUuid") or ""),
            popo_message_id=str(create_result.get("popoMessageId") or ""),
            session_type=self._popo_recall_session_type_from_session(session),
        )
        with self._lock:
            self._popo_progress_cards[run.run_id] = card
        self._send_popo_progress_card_content(
            card,
            content=POPO_PROGRESS_THINKING_TEXT,
            is_finalize=False,
        )
        return {
            "ok": True,
            "sent": True,
            "transport": "streaming_card_progress",
            "messageId": card.instance_uuid,
            "pending": True,
        }

    def _truncate_popo_progress_line(self, line: str) -> str:
        text = " ".join(str(line or "").strip().split())
        if len(text) <= POPO_PROGRESS_LINE_CHAR_LIMIT:
            return text
        return text[: max(0, POPO_PROGRESS_LINE_CHAR_LIMIT - 3)].rstrip() + "..."

    def _popo_progress_line_from_agent_stream_event(self, event: Dict[str, Any]) -> str:
        if not isinstance(event, dict):
            return ""
        kind = str(event.get("kind") or "").strip().lower()
        if kind in {"message.completed", "status", "queue.updated", "queue.merged", "common.queue.updated"}:
            return ""
        if kind == "message.started":
            return "正在处理消息..."
        if kind == "agent.task_status":
            status = str(event.get("status") or "").strip().lower()
            if status in {"running", "in_progress", "needs_input"}:
                return "正在整理任务状态..."
            if status in {"failed", "blocked"}:
                return "任务处理遇到阻塞..."
            return ""
        if kind not in {"tool.started", "tool.completed"}:
            return ""

        status = str(event.get("status") or "").strip().lower()
        if kind == "tool.completed":
            if status in {"failed", "error"} or event.get("tool_error"):
                return "工具调用失败，正在继续处理..."
            return ""

        tool_name = str(event.get("tool_name") or event.get("name") or event.get("tool") or "").strip()
        tool_kind = str(event.get("tool_kind") or event.get("part_type") or "").strip()
        tool_server = str(event.get("tool_server") or "").strip()
        tool_input = event.get("tool_input")
        if isinstance(tool_input, (dict, list)):
            try:
                tool_input_text = json.dumps(tool_input, ensure_ascii=False)
            except (TypeError, ValueError):
                tool_input_text = str(tool_input)
        else:
            tool_input_text = str(tool_input or "")
        haystack = " ".join(
            part
            for part in [tool_name, tool_kind, tool_server, tool_input_text]
            if part
        ).lower()
        if "blueprint_script_call" in haystack or "scriptnode" in haystack or "script_node" in haystack:
            return "正在调用脚本节点..."
        if "blueprint_service_call" in haystack or "resident" in haystack or "service_call" in haystack:
            return "正在调用服务..."
        if any(token in haystack for token in ("grep", " rg ", "ripgrep", "search", "findstr", "select-string", "search_query")):
            return "正在搜索代码..."
        if any(token in haystack for token in ("read", "open", "cat", "get-content", "source-file", "view_file")):
            return "正在读取文件..."
        if any(token in haystack for token in ("shell", "command", "exec", "bash", "powershell", "cmd.exe", "cmd /c")):
            return "正在执行命令..."
        if tool_name:
            return self._truncate_popo_progress_line(f"正在调用工具 {tool_name}...")
        return "正在调用工具..."

    @staticmethod
    def _popo_visible_text_delta_from_agent_stream_event(event: Dict[str, Any]) -> str:
        if not isinstance(event, dict):
            return ""
        if str(event.get("kind") or "").strip().lower() != "part.delta":
            return ""
        part_type = str(event.get("part_type") or "").strip().lower()
        if part_type in {"reasoning", "reasoning_summary", "thought", "stderr"}:
            return ""
        delta = event.get("delta")
        if delta is None:
            delta = event.get("text")
        return str(delta or "")

    def _append_popo_progress_text_delta(self, run_id: str, delta: str) -> Optional[Dict[str, Any]]:
        text = str(delta or "")
        if not text:
            return None
        now = time.monotonic()
        card_to_send: Optional[PopoStreamingProgressCard] = None
        content_to_send = ""
        with self._lock:
            card = self._popo_progress_cards.get(str(run_id))
            if card is None or card.finalized or card.failed:
                return None
            stripped = text.strip()
            if stripped and (
                card.last_content.rstrip().endswith(stripped)
                or (len(stripped) >= 24 and stripped in card.last_content)
            ):
                return None
            card.pending_text_delta = f"{card.pending_text_delta}{text}"
            if (
                now - float(card.last_update_at or 0.0) < POPO_PROGRESS_UPDATE_INTERVAL_SECONDS
                and len(card.pending_text_delta) < POPO_PROGRESS_TEXT_DELTA_FLUSH_CHARS
            ):
                return None
            pending = card.pending_text_delta
            card.pending_text_delta = ""
            prefix = ""
            if not card.agent_reply_started:
                prefix = ("\n\n" if card.last_content else "") + "Agent 回复\n"
                card.agent_reply_started = True
            card_to_send = card
            content_to_send = f"{prefix}{pending}"
        if card_to_send is not None and content_to_send:
            return self._send_popo_progress_card_content(
                card_to_send,
                content=content_to_send,
                is_finalize=False,
            )
        return None

    def _append_popo_progress_temporary_reply(self, run_id: str, text: str) -> Optional[Dict[str, Any]]:
        content = str(text or "").strip()
        if not content:
            return None
        if len(content) > POPO_PROGRESS_TEMP_REPLY_CHAR_LIMIT:
            content = content[: POPO_PROGRESS_TEMP_REPLY_CHAR_LIMIT - 3].rstrip() + "..."
        card_to_send: Optional[PopoStreamingProgressCard] = None
        content_to_send = ""
        with self._lock:
            card = self._popo_progress_cards.get(str(run_id))
            if card is None or card.finalized or card.failed:
                return None
            dedupe_key = "agent_reply:" + content
            if dedupe_key in card.temporary_reply_keys:
                return None
            card.temporary_reply_keys.add(dedupe_key)
            card.pending_text_delta = ""
            prefix = ("\n\n" if card.last_content else "")
            if not card.agent_reply_started:
                prefix += "Agent 回复\n"
                card.agent_reply_started = True
            card_to_send = card
            content_to_send = f"{prefix}{content}"
        if card_to_send is not None and content_to_send:
            return self._send_popo_progress_card_content(
                card_to_send,
                content=content_to_send,
                is_finalize=False,
            )
        return None

    def _update_popo_progress_from_stream_event(self, run_id: str, event: Dict[str, Any]) -> None:
        delta = self._popo_visible_text_delta_from_agent_stream_event(event)
        if delta:
            self._append_popo_progress_text_delta(run_id, delta)
            return
        line = self._popo_progress_line_from_agent_stream_event(event)
        if not line:
            return
        line = self._truncate_popo_progress_line(line)
        now = time.monotonic()
        card_to_send: Optional[PopoStreamingProgressCard] = None
        content_to_send = ""
        with self._lock:
            card = self._popo_progress_cards.get(str(run_id))
            if card is None or card.finalized or card.failed:
                return
            if line in card.lines:
                return
            lines = list(card.lines)
            lines.append(line)
            lines = lines[-POPO_PROGRESS_MAX_LINES:]
            if card.progress_started and now - float(card.last_update_at or 0.0) < POPO_PROGRESS_UPDATE_INTERVAL_SECONDS:
                card.lines = lines
                return
            card.lines = lines
            card.progress_started = True
            card_to_send = card
            content_to_send = ("\n" if card.last_content else "") + line
        if card_to_send is not None and content_to_send:
            self._send_popo_progress_card_content(
                card_to_send,
                content=content_to_send,
                is_finalize=False,
            )

    def _finalize_popo_progress_for_run(
        self,
        run_id: str,
        *,
        session_key: str,
        content: str,
    ) -> Optional[Dict[str, Any]]:
        text = str(content or "").strip()
        if not text:
            return None
        with self._lock:
            card = self._popo_progress_cards.get(str(run_id))
            if card is None or card.finalized:
                return None
            if session_key and card.session_key and card.session_key != session_key:
                return None
        result = self._recall_popo_progress_card(card)
        if result is None or not result.get("ok", True):
            return None
        return result

    def _finalize_popo_progress_for_run_best_effort(
        self,
        run: DesktopBlueprintRun,
        *,
        content: str,
    ) -> None:
        session_key = str(run.session_key or run.bound_session_key or getattr(run.runtime, "popo_reply_session_key", "") or "").strip()
        try:
            self._finalize_popo_progress_for_run(run.run_id, session_key=session_key, content=content)
        except Exception:
            log.exception("failed to finalize POPO progress card")

    @staticmethod
    def _popo_progress_terminal_content(status: str, *, action: str = "") -> str:
        normalized_status = str(status or "").strip().lower()
        normalized_action = str(action or "").strip().lower()
        if normalized_status == "failed" or normalized_action == "fail":
            return POPO_PROGRESS_FAILED_TEXT
        if normalized_status == "cancelled" or normalized_action == "cancel":
            return POPO_PROGRESS_STOPPED_TEXT
        return POPO_PROGRESS_COMPLETED_TEXT

    def _read_blueprint_project_registry(self) -> Dict[str, Any]:
        path = self.blueprint_project_registry_path()
        if not path.is_file():
            return {"version": 1, "projects": {}}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "projects": {}}
        if not isinstance(payload, dict):
            return {"version": 1, "projects": {}}
        projects = payload.get("projects")
        if not isinstance(projects, dict):
            projects = {}
        return {"version": 1, "projects": projects}

    def register_blueprint_project(self, project_dir: Path) -> Dict[str, Any]:
        resolved = validate_project_dir(project_dir)
        now = float(self.now())
        with self._lock:
            registry = self._read_blueprint_project_registry()
            projects = dict(registry.get("projects") or {})
            key = str(resolved).casefold()
            previous = projects.get(key) if isinstance(projects.get(key), dict) else {}
            projects[key] = {
                **dict(previous),
                "projectDir": str(resolved),
                "lastTouchedAt": now,
            }
            registry = {"version": 1, "projects": projects, "updatedAt": now}
            self._atomic_write_json(self.blueprint_project_registry_path(), registry)
        return {"ok": True, "projectDir": str(resolved), "registeredAt": now}

    def _record_current_open_blueprint(self, project_dir: Path, document: Dict[str, Any]) -> None:
        resolved = validate_project_dir(project_dir)
        blueprint_id = str(document.get("id") or "").strip()
        if not blueprint_id:
            return
        now = float(self.now())
        with self._lock:
            registry = self._read_blueprint_project_registry()
            projects = dict(registry.get("projects") or {})
            key = str(resolved).casefold()
            previous = projects.get(key) if isinstance(projects.get(key), dict) else {}
            projects[key] = {
                **dict(previous),
                "projectDir": str(resolved),
                "lastTouchedAt": now,
                "lastOpenedBlueprintId": blueprint_id,
                "lastOpenedBlueprintName": str(document.get("name") or blueprint_id),
                "lastOpenedAt": now,
            }
            registry = {"version": 1, "projects": projects, "updatedAt": now}
            self._atomic_write_json(self.blueprint_project_registry_path(), registry)

    def list_registered_blueprint_projects(self, *, existing_only: bool = False) -> list[Dict[str, Any]]:
        registry = self._read_blueprint_project_registry()
        projects = registry.get("projects") if isinstance(registry.get("projects"), dict) else {}
        rows: list[Dict[str, Any]] = []
        for item in projects.values():
            if not isinstance(item, dict):
                continue
            raw_project = str(item.get("projectDir") or "").strip()
            if not raw_project:
                continue
            path = Path(raw_project).expanduser()
            exists = path.is_dir()
            if existing_only and not exists:
                continue
            rows.append(
                {
                    "projectDir": str(path.resolve()) if exists else str(path),
                    "exists": exists,
                    "lastTouchedAt": float(item.get("lastTouchedAt") or 0.0),
                    "lastOpenedBlueprintId": str(item.get("lastOpenedBlueprintId") or ""),
                    "lastOpenedBlueprintName": str(item.get("lastOpenedBlueprintName") or ""),
                    "lastOpenedAt": float(item.get("lastOpenedAt") or 0.0),
                }
            )
        return sorted(rows, key=lambda row: (-float(row.get("lastTouchedAt") or 0.0), str(row.get("projectDir") or "")))

    def list_blueprints(self, project_dir: Path) -> list[Dict[str, Any]]:
        self.register_blueprint_project(project_dir)
        directory = blueprint_dir(project_dir)
        if not directory.exists():
            return []
        items: list[Dict[str, Any]] = []
        for path in sorted(directory.glob("*.json")):
            blueprint_id = path.stem
            if not valid_blueprint_id(blueprint_id):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            items.append(
                {
                    "id": str(data.get("id") or blueprint_id),
                    "name": str(data.get("name") or blueprint_id),
                    "path": str(path),
                    "updated_at": path.stat().st_mtime,
                }
            )
        return items

    def open_blueprint(self, project_dir: Path, blueprint_id: str = DEFAULT_BLUEPRINT_ID) -> Dict[str, Any]:
        self.register_blueprint_project(project_dir)
        path = blueprint_path(project_dir, blueprint_id)
        if not path.is_file():
            raise BlueprintServiceError(
                "NOT_FOUND",
                f"blueprint {blueprint_id!r} was not found",
                status=404,
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise BlueprintServiceError("INVALID_DOCUMENT", "blueprint document must be a JSON object")
        return normalize_document(data, fallback_id=blueprint_id)

    def save_blueprint(self, project_dir: Path, document: Dict[str, Any]) -> Dict[str, Any]:
        self.register_blueprint_project(project_dir)
        normalized = normalize_document(document)
        blueprint_id = str(normalized["id"])
        path = blueprint_path(project_dir, blueprint_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
            tmp.write(encoded)
            tmp_path = Path(tmp.name)
        tmp_path.replace(path)
        return normalized

    def create_blueprint(
        self,
        project_dir: Path,
        *,
        blueprint_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        document_name = str(name or "").strip() or DEFAULT_BLUEPRINT_NAME
        normalized_id = (
            validate_blueprint_id(blueprint_id)
            if blueprint_id
            else self._unique_blueprint_id(project_dir, _slug_blueprint_id(document_name))
        )
        path = blueprint_path(project_dir, normalized_id)
        if path.exists():
            raise BlueprintServiceError(
                "BLUEPRINT_EXISTS",
                f"blueprint {normalized_id!r} already exists",
                status=409,
            )
        document = default_blueprint_document(validate_project_dir(project_dir), normalized_id, document_name)
        saved = self.save_blueprint(project_dir, document)
        return {"ok": True, "document": saved, "created": True}

    def delete_blueprint(self, project_dir: Path, blueprint_id: str) -> Dict[str, Any]:
        resolved_project = validate_project_dir(project_dir)
        normalized_id = validate_blueprint_id(blueprint_id)
        path = blueprint_path(resolved_project, normalized_id)
        if not path.is_file():
            raise BlueprintServiceError(
                "NOT_FOUND",
                f"blueprint {normalized_id!r} was not found",
                status=404,
            )
        if self._blueprint_has_active_run(resolved_project, normalized_id):
            raise BlueprintServiceError(
                "BLUEPRINT_IN_USE",
                f"blueprint {normalized_id!r} has a live run and cannot be deleted",
                status=409,
            )
        trash_dir = blueprint_dir(resolved_project) / ".trash"
        trash_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = trash_dir / f"{normalized_id}.{timestamp}.json"
        if target.exists():
            target = trash_dir / f"{normalized_id}.{timestamp}.{uuid.uuid4().hex[:8]}.json"
        path.replace(target)
        return {
            "ok": True,
            "deleted": True,
            "blueprintId": normalized_id,
            "trashPath": str(target),
        }

    def create_blueprint_start_plan(
        self,
        project_dir: Path,
        blueprint_id: str,
        *,
        task: Any,
        start_node_ids: Any = None,
        plan_overrides: Any = None,
    ) -> Dict[str, Any]:
        task_text = str(task or "").strip()
        if not task_text:
            raise BlueprintServiceError("BAD_REQUEST", "task must be a non-empty string")
        graph = self._blueprint_graph_for_plan(project_dir, blueprint_id)
        start_nodes = coerce_string_list(start_node_ids, "startNodeIds")
        if not start_nodes and not graph.has_tick_source():
            raise BlueprintServiceError(
                "START_NODES_REQUIRED",
                "startNodeIds must include at least one valid AgentNode unless the blueprint has a Tick source",
                details=start_plan_validation_context(graph),
            )
        plan_data = default_start_plan_for_graph(graph, task_text, start_nodes)
        if plan_overrides is not None:
            plan_data = apply_start_plan_overrides(plan_data, plan_overrides)
        result = self._validate_blueprint_start_plan_data(graph, plan_data)
        return {
            "ok": True,
            "plan": result["plan"],
            "validation": result["validation"],
        }

    def validate_blueprint_start_plan(
        self,
        project_dir: Path,
        blueprint_id: str,
        plan_data: Any,
    ) -> Dict[str, Any]:
        graph = self._blueprint_graph_for_plan(project_dir, blueprint_id)
        result = self._validate_blueprint_start_plan_data(graph, plan_data)
        return {
            "ok": True,
            "plan": result["plan"],
            "validation": result["validation"],
        }

    def set_blueprint_start_agent(
        self,
        project_dir: Path,
        blueprint_id: str,
        start_node_id: str,
    ) -> Dict[str, Any]:
        start_id = str(start_node_id or "").strip()
        if not start_id:
            raise BlueprintServiceError("BAD_REQUEST", "startNodeId must be a non-empty string")
        document = self.open_blueprint(project_dir, blueprint_id)
        graph_dict = dict(document.get("graph") or {})
        try:
            graph = graph_definition_from_dict(graph_dict)
            validate_desktop_blueprint_graph(graph, project_dir=validate_project_dir(project_dir))
        except Exception as exc:
            raise BlueprintServiceError(
                "INVALID_BLUEPRINT_GRAPH",
                str(exc),
                details={"blueprintId": str(document["id"])},
            ) from exc
        if start_id not in graph.agent_nodes:
            raise BlueprintServiceError(
                "BLUEPRINT_START_NODE_REQUIRED",
                "startNodeId must reference exactly one full Agent node",
                details={"blueprintId": str(document["id"]), "validStartNodes": blueprint_runtime_start_node_ids(graph)},
            )
        valid_start_nodes = set(blueprint_runtime_start_node_ids(graph))
        if start_id not in valid_start_nodes:
            raise BlueprintServiceError(
                "BLUEPRINT_START_NODE_REQUIRED",
                "startNodeId must reference exactly one full Agent node",
                details={"blueprintId": str(document["id"]), "validStartNodes": sorted(valid_start_nodes)},
            )
        previous_start_id = document_start_node_id(document)
        graph_doc = dict(document.get("graph") or {})
        agent_nodes = graph_doc.get("agent_nodes")
        if isinstance(agent_nodes, dict) and previous_start_id and previous_start_id != start_id:
            previous_node = agent_nodes.get(previous_start_id)
            if isinstance(previous_node, dict):
                previous_entry = normalize_popo_entry(previous_node.get("popo_entry") or previous_node.get("popoEntry"))
                if previous_entry.get("enabled"):
                    previous_entry["enabled"] = False
                    updated_previous = dict(previous_node)
                    updated_previous["popo_entry"] = previous_entry
                    agent_nodes[previous_start_id] = updated_previous
                    graph_doc["agent_nodes"] = agent_nodes
                    document["graph"] = graph_doc
        runtime = dict(document.get("runtime") or {})
        runtime["start_node_id"] = start_id
        runtime["popo_entry"] = normalize_popo_entry()
        document["runtime"] = runtime
        saved = self.save_blueprint(project_dir, document)
        return {
            "ok": True,
            "blueprintId": str(saved["id"]),
            "startNodeId": start_id,
            "validStartNodes": blueprint_runtime_start_node_ids(graph),
            "document": saved,
        }

    def execute_blueprint_plan(
        self,
        project_dir: Path,
        blueprint_id: str,
        plan_data: Any,
        *,
        execution_mode: str = "live",
    ) -> Dict[str, Any]:
        document = self.open_blueprint(project_dir, blueprint_id)
        graph_dict = dict(document.get("graph") or {})
        try:
            graph = graph_definition_from_dict(graph_dict)
            validate_desktop_blueprint_graph(graph, project_dir=validate_project_dir(project_dir))
        except Exception as exc:
            raise BlueprintServiceError(
                "INVALID_BLUEPRINT_GRAPH",
                str(exc),
                details={"blueprintId": str(document["id"])},
            ) from exc
        start_node_id = document_start_node_id(document)
        valid_start_nodes = set(blueprint_runtime_start_node_ids(graph))
        if not start_node_id or start_node_id not in graph.agent_nodes or start_node_id not in valid_start_nodes:
            raise BlueprintServiceError(
                "BLUEPRINT_START_NODE_REQUIRED",
                "blueprint runtime.start_node_id must be set to exactly one full Agent node before executing a plan",
                details={"blueprintId": str(document["id"]), "validStartNodes": sorted(valid_start_nodes)},
            )
        plan = normalize_plan_payload(plan_data)
        start_nodes = coerce_string_list(plan.get("start_nodes"), "plan.start_nodes")
        if not start_nodes:
            plan["start_nodes"] = [start_node_id]
            start_nodes = [start_node_id]
        if start_nodes != [start_node_id]:
            raise BlueprintServiceError(
                "BLUEPRINT_PLAN_START_NODE_MISMATCH",
                "plan.start_nodes must contain only the saved runtime.start_node_id",
                details={"startNodeId": start_node_id, "planStartNodes": start_nodes},
            )
        tasks = plan.get("tasks")
        if not isinstance(tasks, dict) or start_node_id not in tasks:
            raise BlueprintServiceError(
                "BAD_START_PLAN",
                "plan.tasks must include the saved runtime.start_node_id task",
                details={"startNodeId": start_node_id},
            )
        run_policy = dict(plan.get("run_policy") or {})
        run_policy["requires_confirmation"] = False
        run_policy["source"] = str(run_policy.get("source") or "codex-desktop-execute-plan")
        plan["run_policy"] = run_policy
        result = self._validate_blueprint_start_plan_data(graph, plan)
        validation = result["validation"]
        if not validation.get("ok"):
            raise BlueprintServiceError(
                "START_PLAN_INVALID",
                "start plan failed validation",
                details={"validation": validation, "blueprintId": str(document["id"])},
            )
        return self.start_blueprint_run(
            project_dir,
            str(document["id"]),
            result["plan"],
            execution_mode=execution_mode,
            start_node_id=start_node_id,
        )

    def _blueprint_graph_for_plan(self, project_dir: Path, blueprint_id: str) -> Any:
        document = self.open_blueprint(project_dir, blueprint_id)
        document = document_with_common_config_paths(document)
        try:
            graph = graph_definition_from_dict(dict(document["graph"]))
            validate_desktop_blueprint_graph(graph, project_dir=validate_project_dir(project_dir))
        except Exception as exc:
            raise BlueprintServiceError(
                "INVALID_BLUEPRINT_GRAPH",
                str(exc),
                details={"blueprintId": str(document["id"])},
            ) from exc
        return graph

    def _validate_blueprint_start_plan_data(self, graph: Any, plan_data: Any) -> Dict[str, Any]:
        if not isinstance(plan_data, dict):
            raise BlueprintServiceError("BAD_START_PLAN", "plan must be a complete start plan JSON object")
        try:
            plan = TopAgentStartPlan.from_dict(plan_data)
        except Exception as exc:
            raise BlueprintServiceError("BAD_START_PLAN", str(exc)) from exc
        validation = GuLiCodeTopAgentProfile().validate_start_plan(graph, plan).to_dict()
        validation.update(start_plan_validation_context(graph))
        invalid_runtime_starts = [
            node_id
            for node_id in plan.start_nodes
            if node_id not in set(blueprint_runtime_start_node_ids(graph))
        ]
        if invalid_runtime_starts:
            validation["ok"] = False
            errors = list(validation.get("errors") or [])
            errors.append(
                "start_nodes contains nodes that are not valid Blueprint runtime start Agent ids: "
                + ", ".join(invalid_runtime_starts)
            )
            validation["errors"] = errors
        return {"plan": plan.to_dict(), "validation": validation}

    def _unique_blueprint_id(self, project_dir: Path, seed: str) -> str:
        base = validate_blueprint_id(seed or DEFAULT_BLUEPRINT_ID)
        candidate = base
        index = 2
        while blueprint_path(project_dir, candidate).exists():
            candidate = f"{base}-{index}"
            index += 1
        return candidate

    def _blueprint_has_active_run(self, project_dir: Path, blueprint_id: str) -> bool:
        return self._active_run_for_blueprint(project_dir, blueprint_id) is not None

    def _active_run_for_blueprint(self, project_dir: Path, blueprint_id: str) -> Optional[DesktopBlueprintRun]:
        with self._lock:
            runs = [
                run
                for run in self._runs.values()
                if run.project_dir == project_dir and run.blueprint_id == blueprint_id
            ]
        for run in runs:
            try:
                status = self._runtime_call(run, lambda: run.runtime.status_snapshot()["run"])
            except Exception:
                return run
            if str(status.get("status") or "").strip() not in TERMINAL_RUN_STATUSES:
                return run
        return None

    def relocate_project_workdir(
        self,
        project_dir: Path,
        blueprint_id: str,
        document: Dict[str, Any],
        project_workdir: str,
        *,
        conflict_policy: Optional[str] = None,
    ) -> Dict[str, Any]:
        source_dir = validate_project_dir(project_dir)
        target_dir = validate_project_dir(Path(project_workdir))
        normalized_id = validate_blueprint_id(blueprint_id)
        relocated = document_with_project_workdir(document, target_dir, blueprint_id=normalized_id)
        base_response = {
            "ok": True,
            "projectDir": str(source_dir),
            "targetProjectDir": str(target_dir),
        }
        if source_dir == target_dir:
            return {
                **base_response,
                "changed": False,
                "document": relocated,
            }

        policy = str(conflict_policy or "").strip()
        target_path = blueprint_path(target_dir, normalized_id)
        if target_path.exists():
            if policy == "load_existing":
                return {
                    **base_response,
                    "changed": True,
                    "document": self.open_blueprint(target_dir, normalized_id),
                }
            if policy != "overwrite":
                return {
                    **base_response,
                    "changed": False,
                    "document": relocated,
                    "conflict": "target_exists",
                }
        elif policy == "load_existing":
            raise BlueprintServiceError(
                "NOT_FOUND",
                f"blueprint {normalized_id!r} was not found",
                status=404,
            )

        saved = self.save_blueprint(target_dir, relocated)
        return {
            **base_response,
            "changed": True,
            "document": saved,
        }

    def validate_blueprint(self, document: Dict[str, Any], *, project_dir: Optional[Path] = None) -> Dict[str, Any]:
        errors: list[str] = []
        warnings: list[str] = []
        try:
            normalized = normalize_document(document)
            graph = graph_definition_from_dict(dict(normalized["graph"]))
            validate_desktop_blueprint_graph(graph, project_dir=project_dir)
            start_node_id = document_start_node_id(normalized)
            if start_node_id and start_node_id not in set(blueprint_runtime_start_node_ids(graph)):
                errors.append(
                    "blueprint runtime.start_node_id must reference exactly one full Agent node"
                )
            enabled_popo = _document_enabled_popo_agent_entries(normalized)
            if len(enabled_popo) > 1:
                errors.append("only one full Agent can enable POPO message forwarding")
            elif enabled_popo and enabled_popo[0][0] != start_node_id:
                errors.append("POPO message forwarding must be enabled on the saved start full Agent")
        except Exception as exc:
            errors.append(str(exc))
        return {"ok": not errors, "errors": errors, "warnings": warnings}

    def blueprint_sessions_dir(self) -> Path:
        return self.resident_service_data_dir() / "blueprint_sessions"

    def _blueprint_session_dir(self, session_key: str) -> Path:
        return self.blueprint_sessions_dir() / blueprint_session_key_path_component(session_key)

    def _blueprint_session_path(self, session_key: str) -> Path:
        return self._blueprint_session_dir(session_key) / "session.json"

    def _blueprint_session_transcript_path(self, session_key: str) -> Path:
        return self._blueprint_session_dir(session_key) / "transcript.jsonl"

    def _load_blueprint_session(self, session_key: str) -> Optional[Dict[str, Any]]:
        path = self._blueprint_session_path(session_key)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _save_blueprint_session(self, session: Dict[str, Any]) -> None:
        session_key = blueprint_session_key_path_component(str(session.get("sessionKey", "")))
        directory = self._blueprint_session_dir(session_key)
        directory.mkdir(parents=True, exist_ok=True)
        payload = dict(session)
        payload["schemaVersion"] = BLUEPRINT_SESSION_SCHEMA_VERSION
        self._atomic_write_json(directory / "session.json", payload)

    def _with_popo_session_display_name(self, session: Dict[str, Any]) -> Dict[str, Any]:
        if str(session.get("source") or "").strip().lower() != "popo":
            return session
        display_name = blueprint_popo_session_display_name(
            popo_user_id=str(session.get("popoUserId") or ""),
            popo_session_id=str(session.get("popoSessionId") or ""),
            popo_group_id=str(session.get("popoGroupId") or ""),
        )
        if str(session.get("sessionDisplayName") or "") == display_name:
            return session
        next_session = dict(session)
        next_session["sessionDisplayName"] = display_name
        return next_session

    def _maybe_upgrade_popo_session_key(self, session: Dict[str, Any]) -> Dict[str, Any]:
        if str(session.get("source") or "").strip().lower() != "popo":
            return session
        old_key = str(session.get("sessionKey") or "").strip()
        try:
            old_key = blueprint_session_key_path_component(old_key)
        except BlueprintServiceError:
            return session
        if not re.fullmatch(r"bps_[0-9a-f]{24}", old_key):
            if re.fullmatch(r"bps_popo_[A-Za-z0-9._-]{1,96}_[0-9a-f]{24}", old_key):
                new_key = blueprint_popo_named_session_key(
                    blueprint_name=str(session.get("blueprintName") or session.get("blueprintId") or ""),
                    blueprint_id=str(session.get("blueprintId") or ""),
                    popo_user_id=str(session.get("popoUserId") or ""),
                    popo_session_id=str(session.get("popoSessionId") or ""),
                    popo_group_id=str(session.get("popoGroupId") or ""),
                )
                if new_key != old_key:
                    new_dir = self._blueprint_session_dir(new_key)
                    old_dir = self._blueprint_session_dir(old_key)
                    if new_dir.exists():
                        next_session = self._with_popo_session_display_name(
                            {
                                **session,
                                "activeRunId": "",
                                "status": "superseded",
                                "superseded": True,
                                "supersededBySessionKey": new_key,
                            }
                        )
                        self._save_blueprint_session(next_session)
                        return next_session
                    next_session = self._with_popo_session_display_name({**session, "sessionKey": new_key})
                    if old_dir.exists():
                        new_dir.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(old_dir), str(new_dir))
                        self._atomic_write_json(new_dir / "session.json", {**next_session, "schemaVersion": BLUEPRINT_SESSION_SCHEMA_VERSION})
                    else:
                        self._save_blueprint_session(next_session)
                    self._replace_run_session_key(old_key, new_key)
                    return next_session
            next_session = self._with_popo_session_display_name(session)
            if next_session is not session:
                self._save_blueprint_session(next_session)
            return next_session
        pool_key = str(session.get("poolKey") or session.get("sessionScopeKey") or "").strip()
        if not pool_key:
            return self._with_popo_session_display_name(session)
        new_key = blueprint_popo_named_session_key(
            blueprint_name=str(session.get("blueprintName") or session.get("blueprintId") or ""),
            blueprint_id=str(session.get("blueprintId") or ""),
            popo_user_id=str(session.get("popoUserId") or ""),
            popo_session_id=str(session.get("popoSessionId") or ""),
            popo_group_id=str(session.get("popoGroupId") or ""),
        )
        if new_key == old_key:
            return self._with_popo_session_display_name(session)
        new_dir = self._blueprint_session_dir(new_key)
        if new_dir.exists():
            next_session = self._with_popo_session_display_name(
                {
                    **session,
                    "activeRunId": "",
                    "status": "superseded",
                    "superseded": True,
                    "supersededBySessionKey": new_key,
                }
            )
            self._save_blueprint_session(next_session)
            return next_session
        old_dir = self._blueprint_session_dir(old_key)
        next_session = self._with_popo_session_display_name({**session, "sessionKey": new_key})
        if old_dir.exists():
            new_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_dir), str(new_dir))
            self._atomic_write_json(new_dir / "session.json", {**next_session, "schemaVersion": BLUEPRINT_SESSION_SCHEMA_VERSION})
        else:
            self._save_blueprint_session(next_session)
        self._replace_run_session_key(old_key, new_key)
        return next_session

    def _replace_run_session_key(self, old_key: str, new_key: str) -> None:
        with self._lock:
            runs = list(self._runs.values())
        for run in runs:
            if run.session_key == old_key:
                run.session_key = new_key
            if run.bound_session_key == old_key:
                run.bound_session_key = new_key
            for attr in ("runtime", "mcp"):
                target = getattr(run, attr, None)
                if target is None:
                    continue
                for key_attr in (
                    "popo_termination_session_key",
                    "popo_reply_session_key",
                    "session_history_tools_session_key",
                ):
                    if getattr(target, key_attr, "") == old_key:
                        setattr(target, key_attr, new_key)

    def _append_blueprint_session_event(self, session_key: str, event: Dict[str, Any]) -> None:
        directory = self._blueprint_session_dir(session_key)
        directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": _iso_time(float(self.now())),
            **event,
        }
        with (directory / "transcript.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def _excel_audit_context_for_run(self, run_id: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        with self._lock:
            run = self._runs.get(str(run_id))
        if run is None:
            return None
        session_key = str(run.session_key or run.bound_session_key or "").strip()
        if not session_key:
            return None
        return {
            "session_key": session_key,
            "session_dir": str(self._blueprint_session_dir(session_key)),
            "run_id": run.run_id,
            "project_dir": str(run.project_dir),
            "blueprint_id": run.blueprint_id,
            "source_node_id": str(kwargs.get("source_node_id") or ""),
            "script_node_id": str(kwargs.get("script_node_id") or ""),
            "batch_id": str(kwargs.get("batch_id") or ""),
            "service_name": str(kwargs.get("service_name") or ""),
            "method_name": str(kwargs.get("method_name") or ""),
        }

    def _excel_log_response_for_session(self, session_key: str, expression: str) -> Dict[str, Any]:
        normalized_key = blueprint_session_key_path_component(session_key)
        try:
            start_ms, end_ms = parse_time_range(expression)
            text = render_user_log(self._blueprint_session_dir(normalized_key), start_ms, end_ms)
            return {
                "ok": True,
                "excelLog": True,
                "sessionKey": normalized_key,
                "startMs": start_ms,
                "endMs": end_ms,
                "message": text,
            }
        except Exception as exc:
            return {
                "ok": False,
                "excelLog": True,
                "sessionKey": normalized_key,
                "code": "BAD_EXCEL_LOG_RANGE",
                "error": str(exc),
                "message": (
                    "Invalid /excel-log range. Use: "
                    "/excel-log YYYY M D H M S [ms]-YYYY M D H M S [ms]"
                ),
            }

    def _record_blueprint_session_terminator(
        self,
        session: Dict[str, Any],
        *,
        actor: str,
        agent_node_id: str = "",
        agent_id: str = "",
    ) -> None:
        session["lastTerminatedBy"] = str(actor or "")
        if agent_node_id:
            session["lastTerminatedByAgentNodeId"] = str(agent_node_id or "")
        else:
            session.pop("lastTerminatedByAgentNodeId", None)
        if agent_id:
            session["lastTerminatedByAgentId"] = str(agent_id or "")
        else:
            session.pop("lastTerminatedByAgentId", None)

    def _read_blueprint_session_events(self, session_key: str, *, limit: int = BLUEPRINT_SESSION_CONTEXT_RECENT_LIMIT) -> list[Dict[str, Any]]:
        path = self._blueprint_session_transcript_path(session_key)
        if not path.is_file():
            return []
        rows: list[Dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        for line in reversed(lines):
            if len(rows) >= limit:
                break
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "") not in {"user_message", "agent_reply"}:
                continue
            rows.append(item)
        rows.reverse()
        return rows

    def _read_blueprint_session_timeline(
        self,
        session_key: str,
        *,
        limit: int = BLUEPRINT_SESSION_TIMELINE_LIMIT,
    ) -> list[Dict[str, Any]]:
        path = self._blueprint_session_transcript_path(session_key)
        if not path.is_file():
            return []
        max_rows = max(1, min(int(limit or BLUEPRINT_SESSION_TIMELINE_LIMIT), 2000))
        rows: list[Dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        start = max(0, len(lines) - max_rows)
        for index, line in enumerate(lines[start:], start=start):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            event_type = str(item.get("type") or "")
            message = str(item.get("message") or "").strip()
            content = str(item.get("content") or message or "").strip()
            rows.append(
                {
                    "id": f"{session_key}:{index + 1}",
                    "seq": index + 1,
                    "type": event_type,
                    "timestamp": str(item.get("timestamp") or ""),
                    "sessionKey": session_key,
                    "runId": str(item.get("runId") or ""),
                    "startNodeId": str(item.get("startNodeId") or ""),
                    "agentNodeId": str(item.get("agentNodeId") or ""),
                    "agentId": str(item.get("agentId") or ""),
                    "source": str(item.get("source") or ""),
                    "message": message,
                    "content": content,
                    "reason": str(item.get("reason") or ""),
                    "actor": str(item.get("actor") or ""),
                    "raw": dict(item),
                }
            )
        return rows

    def blueprint_session_timeline(
        self,
        session_key: str,
        *,
        limit: int = BLUEPRINT_SESSION_TIMELINE_LIMIT,
    ) -> Dict[str, Any]:
        normalized_key = blueprint_session_key_path_component(session_key)
        session = self._load_blueprint_session(normalized_key)
        if session is None and not self._blueprint_session_transcript_path(normalized_key).is_file():
            raise BlueprintServiceError("BLUEPRINT_SESSION_NOT_FOUND", "blueprint session was not found", status=404)
        return {
            "ok": True,
            "sessionKey": normalized_key,
            "session": session,
            "events": self._read_blueprint_session_timeline(normalized_key, limit=limit),
        }

    def list_blueprint_session_excel_history(
        self,
        project_dir: Optional[Path] = None,
        blueprint_id: Optional[str] = None,
        *,
        category: str = "all",
    ) -> Dict[str, Any]:
        summaries: list[Dict[str, Any]] = []
        try:
            sessions = self.list_blueprint_sessions(project_dir, blueprint_id)
            for session in sessions:
                session_key = str(session.get("sessionKey") or "").strip()
                if not session_key:
                    continue
                history = query_excel_history(
                    self._blueprint_session_dir(session_key),
                    category=category,
                    limit=1,
                )
                records = history.get("records") if isinstance(history.get("records"), list) else []
                if not records:
                    continue
                latest = records[0] if isinstance(records[0], dict) else {}
                summaries.append(
                    {
                        "sessionKey": session_key,
                        "sessionDisplayName": str(session.get("sessionDisplayName") or ""),
                        "blueprintName": str(session.get("blueprintName") or ""),
                        "blueprintId": str(session.get("blueprintId") or ""),
                        "source": str(session.get("source") or ""),
                        "status": str(session.get("status") or ""),
                        "lastTouchedAt": session.get("lastTouchedAt"),
                        "recordCount": int(history.get("totalMatches") or len(records)),
                        "latestTimestampMs": int(latest.get("timestampMs") or 0),
                        "latestTime": str(latest.get("time") or ""),
                        "latestWorkbook": str(latest.get("workbook") or ""),
                        "latestCommand": str(latest.get("command") or ""),
                        "latestStatus": str(latest.get("status") or ""),
                    }
                )
        except ValueError as exc:
            raise BlueprintServiceError("BAD_REQUEST", str(exc), status=400) from exc
        summaries.sort(
            key=lambda item: (
                int(item.get("latestTimestampMs") or 0),
                float(item.get("lastTouchedAt") or 0),
                str(item.get("sessionKey") or ""),
            ),
            reverse=True,
        )
        return {
            "ok": True,
            "category": str(category or "all").strip().lower(),
            "count": len(summaries),
            "sessions": summaries,
        }

    def blueprint_session_excel_history(
        self,
        session_key: str,
        *,
        category: str = "all",
        limit: int = 200,
    ) -> Dict[str, Any]:
        normalized_key = blueprint_session_key_path_component(session_key)
        session = self._load_blueprint_session(normalized_key)
        if not session or session.get("deleted") or session.get("superseded"):
            raise BlueprintServiceError("BLUEPRINT_SESSION_NOT_FOUND", "blueprint session was not found", status=404)
        try:
            result = query_excel_history(
                self._blueprint_session_dir(normalized_key),
                category=category,
                limit=limit,
            )
        except ValueError as exc:
            raise BlueprintServiceError("BAD_REQUEST", str(exc), status=400) from exc
        result["sessionKey"] = normalized_key
        result["session"] = session
        return result

    def _atomic_write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(
            f"{path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
        )
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        try:
            for attempt in range(6):
                try:
                    temp.replace(path)
                    return
                except PermissionError:
                    if os.name != "nt" or attempt >= 5:
                        raise
                    time.sleep(0.05 * (attempt + 1))
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass

    def _run_is_active(self, run: DesktopBlueprintRun) -> bool:
        try:
            status = self._runtime_call(
                run,
                lambda: run.runtime.status_snapshot()["run"],
                timeout=LIVE_RUN_ACTIVE_CHECK_TIMEOUT_SECONDS,
            )
        except Exception:
            return True
        return str(status.get("status") or "").strip() not in TERMINAL_RUN_STATUSES

    def _active_run_for_session(self, session_key: str) -> Optional[DesktopBlueprintRun]:
        normalized_key = blueprint_session_key_path_component(session_key)
        with self._lock:
            runs = [run for run in self._runs.values() if run.session_key == normalized_key]
        for run in runs:
            if self._run_is_active(run):
                return run
            self._mark_blueprint_session_run_ended(run)
        return None

    def _active_blueprint_session_run_count(self) -> int:
        with self._lock:
            runs = list(self._runs.values())
        count = 0
        for run in runs:
            if self._run_is_active(run):
                count += 1
            else:
                self._mark_blueprint_session_run_ended(run)
        return count

    def _mark_blueprint_session_run_ended(self, run: DesktopBlueprintRun) -> None:
        if not run.session_key:
            return
        session = self._load_blueprint_session(run.session_key)
        if not session:
            return
        if str(session.get("activeRunId") or "") != run.run_id:
            return
        now = float(self.now())
        session["activeRunId"] = ""
        session["lastRunId"] = run.run_id
        session["status"] = "idle"
        session["lastTouchedAt"] = now
        self._save_blueprint_session(session)
        self._append_blueprint_session_event(
            run.session_key,
            {
                "type": "run_ended",
                "runId": run.run_id,
                "blueprintId": run.blueprint_id,
            },
        )

    def _table_queue_notification_state_dir(self) -> Path:
        return ensure_resident_services_dir(self.resident_service_data_dir()) / ".state"

    def _table_queue_notification_path(self) -> Path:
        return self._table_queue_notification_state_dir() / TABLE_QUEUE_NOTIFICATION_FILENAME

    def _table_queue_notification_processed_path(self) -> Path:
        return self._table_queue_notification_state_dir() / TABLE_QUEUE_NOTIFICATION_PROCESSED_FILENAME

    def _read_table_queue_notifications(self) -> list[Dict[str, Any]]:
        path = self._table_queue_notification_path()
        if not path.is_file():
            return []
        events: list[Dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        for line in lines:
            text = line.strip()
            if not text:
                continue
            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        return events

    def _read_table_queue_processed_ids(self) -> set[str]:
        path = self._table_queue_notification_processed_path()
        if not path.is_file():
            return set()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return set()
        ids = payload.get("processedNotificationIds") if isinstance(payload, dict) else []
        if not isinstance(ids, list):
            return set()
        return {str(item) for item in ids if str(item).strip()}

    def _save_table_queue_processed_ids(self, ids: set[str]) -> None:
        path = self._table_queue_notification_processed_path()
        payload = {
            "version": 1,
            "processedNotificationIds": sorted(ids),
            "updatedAt": float(self.now()),
        }
        self._atomic_write_json(path, payload)

    def start_table_queue_notification_watcher(self) -> None:
        with self._lock:
            thread = self._table_queue_notification_thread
            if thread is not None and thread.is_alive():
                return
            self._table_queue_notification_stop.clear()
            thread = threading.Thread(
                target=self._table_queue_notification_watch_loop,
                name="blueprint-table-queue-notifications",
                daemon=True,
            )
            self._table_queue_notification_thread = thread
            thread.start()

    def stop_table_queue_notification_watcher(self) -> None:
        self._table_queue_notification_stop.set()
        thread = self._table_queue_notification_thread
        if thread is not None:
            thread.join(timeout=2.0)
        with self._lock:
            if self._table_queue_notification_thread is thread:
                self._table_queue_notification_thread = None

    def _table_queue_notification_watch_loop(self) -> None:
        while not self._table_queue_notification_stop.wait(TABLE_QUEUE_NOTIFICATION_WATCH_INTERVAL_SECONDS):
            try:
                self.process_table_queue_notifications(limit=50)
            except Exception:
                log.exception("failed to process table queue notifications")

    def process_table_queue_notifications(self, *, limit: int = 100) -> Dict[str, Any]:
        processed_ids = self._read_table_queue_processed_ids()
        events = self._read_table_queue_notifications()
        delivered: list[Dict[str, Any]] = []
        skipped: list[Dict[str, Any]] = []
        errors: list[Dict[str, Any]] = []
        changed = False
        max_count = max(1, int(limit or 100))
        handled = 0
        for event in events:
            if handled >= max_count:
                break
            notification_id = str(event.get("notificationId") or "").strip()
            if not notification_id or notification_id in processed_ids:
                continue
            try:
                result = self._deliver_table_queue_notification(event)
            except BlueprintServiceError as exc:
                errors.append(
                    {
                        "notificationId": notification_id,
                        "code": exc.code,
                        "error": str(exc),
                    }
                )
                continue
            except Exception as exc:
                errors.append({"notificationId": notification_id, "error": str(exc)})
                continue
            handled += 1
            if result.get("delivered"):
                delivered.append(result)
            else:
                skipped.append(result)
            if result.get("processed", True):
                processed_ids.add(notification_id)
                changed = True
        if changed:
            self._save_table_queue_processed_ids(processed_ids)
        return {
            "ok": not errors,
            "notificationFile": str(self._table_queue_notification_path()),
            "processedFile": str(self._table_queue_notification_processed_path()),
            "delivered": delivered,
            "skipped": skipped,
            "errors": errors,
            "remaining": len(
                [
                    event
                    for event in events
                    if str(event.get("notificationId") or "").strip()
                    and str(event.get("notificationId") or "").strip() not in processed_ids
                ]
            ),
        }

    def _deliver_table_queue_notification(self, event: Dict[str, Any]) -> Dict[str, Any]:
        session_key = blueprint_session_key_path_component(str(event.get("sessionKey") or "").strip())
        notification_id = str(event.get("notificationId") or "").strip()
        if not session_key:
            return {
                "processed": True,
                "delivered": False,
                "notificationId": notification_id,
                "reason": "missing sessionKey",
            }
        session = self._load_blueprint_session(session_key)
        if not session:
            return {
                "processed": True,
                "delivered": False,
                "notificationId": notification_id,
                "sessionKey": session_key,
                "reason": "session not found",
            }
        if session.get("deleted") or session.get("superseded"):
            self._append_blueprint_session_event(
                session_key,
                {
                    "type": "table_queue_notification_skipped",
                    "reason": "session deleted or superseded",
                    "notification": dict(event),
                },
            )
            return {
                "processed": True,
                "delivered": False,
                "notificationId": notification_id,
                "sessionKey": session_key,
                "reason": "session deleted or superseded",
            }

        run = self._active_run_for_session(session_key)
        started: Dict[str, Any] = {}
        if run is None:
            project_dir = Path(str(session.get("projectDir") or ""))
            blueprint_id = str(
                session.get("assignedBlueprintId")
                or session.get("blueprintId")
                or DEFAULT_BLUEPRINT_ID
            )
            preflight = self._blueprint_session_preflight(project_dir, blueprint_id)
            document = preflight["document"]
            graph = preflight["graph"]
            start_node_id = str(session.get("startNodeId") or preflight["startNodeId"])
            source = str(session.get("source") or "ui")
            robot_app_key = str(session.get("robotAppKey") or "")
            source_bindings = (
                {"popo": {"robotAppKey": robot_app_key}}
                if source.strip().lower() == "popo"
                else {"ui": {"blueprintId": str(document["id"])}}
            )
            run, started = self._start_blueprint_session_instance(
                project_dir=project_dir,
                document=document,
                graph=graph,
                session_key=session_key,
                start_node_id=start_node_id,
                blueprint_structure_id=str(preflight["blueprintStructureId"]),
                robot_app_key=robot_app_key if source.strip().lower() == "popo" else "",
                source_bindings=source_bindings,
            )
            self._append_blueprint_session_event(
                session_key,
                {
                    "type": "run_started",
                    "source": "table_queue_notification",
                    "runId": run.run_id,
                    "startNodeId": start_node_id,
                },
            )

        queued = self._queue_table_queue_notification_message(run, session, event, session_key=session_key)
        return {
            "processed": True,
            "delivered": True,
            "notificationId": notification_id,
            "sessionKey": session_key,
            "runId": run.run_id,
            "queue": queued,
            "startPending": bool(started.get("pending")) if started else False,
        }

    def _table_queue_notification_prompt(self, event: Dict[str, Any]) -> str:
        queue_id = str(event.get("queueId") or "").strip()
        status = str(event.get("status") or "").strip() or "updated"
        newly_occupied = [str(item) for item in event.get("newlyOccupiedTables", []) if str(item).strip()]
        pending = [str(item) for item in event.get("pendingTables", []) if str(item).strip()]
        all_tables = [str(item) for item in event.get("allTables", []) if str(item).strip()]
        lines = [
            "[Table Queue Notification]",
            f"Queue {queue_id or '(unknown)'} status: {status}.",
            "Newly occupied tables: " + (", ".join(newly_occupied) if newly_occupied else "(none)"),
            "Still pending tables: " + (", ".join(pending) if pending else "(none)"),
            "All requested tables: " + (", ".join(all_tables) if all_tables else "(unknown)"),
            "",
            "Continue the previously confirmed planning-table workflow from this session.",
            "This notification does not expose a Blueprint ScriptNode call batch and has no required_script_calls.",
            "Do not reply only to acknowledge this notification. Reply to the POPO user only when you need missing information, are blocked, or have a fill-completion report ready for confirmation.",
        ]
        return "\n".join(lines)

    def _queue_table_queue_notification_message(
        self,
        run: DesktopBlueprintRun,
        session: Dict[str, Any],
        event: Dict[str, Any],
        *,
        session_key: str,
    ) -> Dict[str, Any]:
        start_node_id = str(run.start_node_id or session.get("startNodeId") or document_start_node_id(run.document))
        prompt = self._table_queue_notification_prompt(event)
        queued = self._async_loop.run(
            self._queue_framework_notification_for_runtime(
                run,
                run.graph.agent_nodes[start_node_id],
                {
                    "type": "framework_table_queue_notification",
                    "prompt": prompt,
                    "framework_message_kind": "framework_table_queue_notification",
                    "reply_required": True,
                    "reply_visibility": "session_event",
                    "table_queue_notification": dict(event),
                },
                queue_mode="top",
            )
        )
        now = float(self.now())
        source = str(session.get("source") or "ui")
        self._configure_run_session_tools(
            run,
            source=source,
            session_key=session_key,
            start_node_id=start_node_id,
            now=now,
        )
        session["status"] = "running"
        session["activeRunId"] = run.run_id
        session["lastRunId"] = run.run_id
        session["assignedBlueprintId"] = run.blueprint_id
        session["startNodeId"] = start_node_id
        session["lastTouchedAt"] = now
        self._save_blueprint_session(session)
        self._append_blueprint_session_event(
            session_key,
            {
                "type": "table_queue_notification",
                "source": "framework",
                "notification": dict(event),
                "runId": run.run_id,
                "startNodeId": start_node_id,
            },
        )
        return queued

    def _planning_table_skill_update_notification_state_dir(self) -> Path:
        return ensure_resident_services_dir(self.resident_service_data_dir()) / ".state"

    def _planning_table_skill_update_notification_path(self) -> Path:
        return (
            self._planning_table_skill_update_notification_state_dir()
            / PLANNING_TABLE_SKILL_UPDATE_NOTIFICATION_FILENAME
        )

    def _planning_table_skill_update_notification_processed_path(self) -> Path:
        return (
            self._planning_table_skill_update_notification_state_dir()
            / PLANNING_TABLE_SKILL_UPDATE_NOTIFICATION_PROCESSED_FILENAME
        )

    def _read_planning_table_skill_update_notifications(self) -> list[Dict[str, Any]]:
        path = self._planning_table_skill_update_notification_path()
        if not path.is_file():
            return []
        events: list[Dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        for line in lines:
            text = line.strip()
            if not text:
                continue
            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        return events

    def _read_planning_table_skill_update_processed_ids(self) -> set[str]:
        path = self._planning_table_skill_update_notification_processed_path()
        if not path.is_file():
            return set()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return set()
        ids = payload.get("processedNotificationIds") if isinstance(payload, dict) else []
        if not isinstance(ids, list):
            return set()
        return {str(item) for item in ids if str(item).strip()}

    def _save_planning_table_skill_update_processed_ids(self, ids: set[str]) -> None:
        path = self._planning_table_skill_update_notification_processed_path()
        payload = {
            "version": 1,
            "processedNotificationIds": sorted(ids),
            "updatedAt": float(self.now()),
        }
        self._atomic_write_json(path, payload)

    def start_planning_table_skill_update_notification_watcher(self) -> None:
        with self._lock:
            thread = self._planning_table_skill_update_notification_thread
            if thread is not None and thread.is_alive():
                return
            self._planning_table_skill_update_notification_stop.clear()
            thread = threading.Thread(
                target=self._planning_table_skill_update_notification_watch_loop,
                name="blueprint-planning-table-skill-update-notifications",
                daemon=True,
            )
            self._planning_table_skill_update_notification_thread = thread
            thread.start()

    def stop_planning_table_skill_update_notification_watcher(self) -> None:
        self._planning_table_skill_update_notification_stop.set()
        thread = self._planning_table_skill_update_notification_thread
        if thread is not None:
            thread.join(timeout=2.0)
        with self._lock:
            if self._planning_table_skill_update_notification_thread is thread:
                self._planning_table_skill_update_notification_thread = None

    def _planning_table_skill_update_notification_watch_loop(self) -> None:
        while not self._planning_table_skill_update_notification_stop.wait(
            PLANNING_TABLE_SKILL_UPDATE_WATCH_INTERVAL_SECONDS
        ):
            try:
                self.process_planning_table_skill_update_notifications(limit=50)
            except Exception:
                log.exception("failed to process planning-table skill update notifications")

    def process_planning_table_skill_update_notifications(self, *, limit: int = 100) -> Dict[str, Any]:
        processed_ids = self._read_planning_table_skill_update_processed_ids()
        events = self._read_planning_table_skill_update_notifications()
        delivered: list[Dict[str, Any]] = []
        skipped: list[Dict[str, Any]] = []
        errors: list[Dict[str, Any]] = []
        changed = False
        max_count = max(1, int(limit or 100))
        handled = 0
        for event in events:
            if handled >= max_count:
                break
            notification_id = str(event.get("notificationId") or "").strip()
            if not notification_id or notification_id in processed_ids:
                continue
            try:
                result = self._deliver_planning_table_skill_update_notification(event)
            except BlueprintServiceError as exc:
                errors.append(
                    {
                        "notificationId": notification_id,
                        "code": exc.code,
                        "error": str(exc),
                    }
                )
                continue
            except Exception as exc:
                errors.append({"notificationId": notification_id, "error": str(exc)})
                continue
            handled += 1
            if result.get("delivered"):
                delivered.append(result)
            else:
                skipped.append(result)
            if result.get("processed", True):
                processed_ids.add(notification_id)
                changed = True
        if changed:
            self._save_planning_table_skill_update_processed_ids(processed_ids)
        return {
            "ok": not errors,
            "notificationFile": str(self._planning_table_skill_update_notification_path()),
            "processedFile": str(self._planning_table_skill_update_notification_processed_path()),
            "delivered": delivered,
            "skipped": skipped,
            "errors": errors,
            "remaining": len(
                [
                    event
                    for event in events
                    if str(event.get("notificationId") or "").strip()
                    and str(event.get("notificationId") or "").strip() not in processed_ids
                ]
            ),
        }

    def _deliver_planning_table_skill_update_notification(self, event: Dict[str, Any]) -> Dict[str, Any]:
        notification_id = str(event.get("notificationId") or "").strip()
        candidates = event.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            return {
                "processed": True,
                "delivered": False,
                "notificationId": notification_id,
                "reason": "no candidates",
            }
        project_dir = Path(str(event.get("targetProjectDir") or PLANNING_TABLE_SKILL_UPDATE_PROJECT_DIR))
        blueprint_id = str(event.get("targetBlueprintId") or PLANNING_TABLE_SKILL_UPDATE_BLUEPRINT_ID)
        preflight = self._blueprint_session_preflight(project_dir, blueprint_id)
        document = preflight["document"]
        graph = preflight["graph"]
        start_node_id = str(preflight["startNodeId"])
        structure_id = str(preflight["blueprintStructureId"])
        session_key = blueprint_session_key_for_pool(
            pool_key=blueprint_slot_pool_key(
                project_dir=project_dir,
                source="automation",
                source_binding="planning_table_skill_update",
                blueprint_structure_id=structure_id,
            ),
            source="automation",
            popo_user_id="",
            popo_session_id="planning-table-skill-update",
            popo_group_id="",
        )
        session = self._load_blueprint_session(session_key)
        now = float(self.now())
        if not session or session.get("deleted") or session.get("superseded"):
            session = {
                "sessionKey": session_key,
                "sessionDisplayName": "填表 skill 更新服务",
                "projectDir": str(validate_project_dir(project_dir)),
                "sessionScopeKey": "planning_table_skill_update",
                "robotAppKey": "",
                "blueprintId": str(document["id"]),
                "assignedBlueprintId": "",
                "blueprintName": str(document.get("name") or document["id"]),
                "blueprintStructureId": structure_id,
                "source": "automation",
                "popoUserId": "",
                "popoSessionId": "planning-table-skill-update",
                "popoGroupId": "",
                "popoReplyTo": "",
                "popoSessionType": "",
                "status": "idle",
                "activeRunId": "",
                "lastRunId": "",
                "contextSummary": "",
                "messageCount": 0,
                "createdAt": now,
                "lastTouchedAt": now,
                "deleted": False,
            }
        session.update(
            {
                "projectDir": str(validate_project_dir(project_dir)),
                "blueprintId": str(session.get("blueprintId") or document["id"]),
                "blueprintName": str(session.get("blueprintName") or document.get("name") or document["id"]),
                "blueprintStructureId": structure_id,
                "source": "automation",
                "startNodeId": start_node_id,
                "deleted": False,
                "lastTouchedAt": now,
                "messageCount": int(session.get("messageCount") or 0) + 1,
            }
        )
        self._save_blueprint_session(session)

        run = self._active_run_for_session(session_key)
        started: Dict[str, Any] = {}
        if run is None:
            run, started = self._start_blueprint_session_instance(
                project_dir=project_dir,
                document=document,
                graph=graph,
                session_key=session_key,
                start_node_id=start_node_id,
                blueprint_structure_id=structure_id,
                robot_app_key="",
                source_bindings={"automation": {"service": "planning_table_skill_update"}},
            )
            self._append_blueprint_session_event(
                session_key,
                {
                    "type": "run_started",
                    "source": "planning_table_skill_update",
                    "runId": run.run_id,
                    "startNodeId": start_node_id,
                },
            )

        queued = self._queue_planning_table_skill_update_notification_message(
            run,
            session,
            event,
            session_key=session_key,
        )
        return {
            "processed": True,
            "delivered": True,
            "notificationId": notification_id,
            "sessionKey": session_key,
            "runId": run.run_id,
            "queue": queued,
            "startPending": bool(started.get("pending")) if started else False,
        }

    def _planning_table_skill_update_notification_prompt(self, event: Dict[str, Any]) -> str:
        notification_id = str(event.get("notificationId") or "").strip()
        skill_root = str(event.get("skillRoot") or PLANNING_TABLE_SKILL_UPDATE_ROOT)
        index_path = str(event.get("indexPath") or PLANNING_TABLE_SKILL_UPDATE_INDEX_PATH)
        commit_message = str(event.get("commitMessage") or PLANNING_TABLE_SKILL_UPDATE_COMMIT_MESSAGE)
        candidates = [item for item in event.get("candidates", []) if isinstance(item, dict)]
        lines = [
            "[Planning Table Skill Update]",
            f"notificationId: {notification_id}",
            f"skillRoot: {skill_root}",
            f"indexPath: {index_path}",
            "",
            "Only process the new skill candidates listed below. Decide which ones match the existing planning-table skill index scope.",
            "Read each candidate skill file as UTF-8 when possible. If a candidate is a legacy .skill file, inspect it as the existing local tooling allows.",
            "",
            "Candidates:",
        ]
        for candidate in candidates:
            name = str(candidate.get("name") or "").strip()
            path = str(candidate.get("skillPath") or "").strip()
            description = str(candidate.get("description") or "").strip()
            indexed = bool(candidate.get("indexed"))
            lines.append(f"- {name or '(unnamed)'}")
            lines.append(f"  path: {path}")
            lines.append(f"  indexed: {indexed}")
            if description:
                lines.append(f"  description: {description}")
        lines.extend(
            [
                "",
                "Required workflow:",
                f"1. Read `{index_path}` and preserve its UTF-8 Markdown format.",
                "2. Add only candidates that are planning-table skills under the existing index scope: direct table fill/configuration, template fill, table occupation, table sync/export, or planning-table validation helpers.",
                "3. If no listed candidate belongs in the index, or the index content is unchanged, do not run svn commit.",
                "4. Before any commit, run SVN status for the AISkills working copy and confirm only `planning-table-skill-index.md` is modified.",
                f"5. If the index changed, commit only `{index_path}` with message `{commit_message}`.",
                "6. If SVN status shows conflicts or unrelated local changes, stop and report the blocker instead of committing.",
                "7. After a successful commit, or after confirming no index change is needed, call `blueprint_service_call(\"planning_table_skill_update\", \"mark_processed\", {\"notificationId\": \""
                + notification_id
                + "\"})`.",
                "",
                "Use concrete paths in your final session note. Do not modify any other file.",
            ]
        )
        return "\n".join(lines)

    def _queue_planning_table_skill_update_notification_message(
        self,
        run: DesktopBlueprintRun,
        session: Dict[str, Any],
        event: Dict[str, Any],
        *,
        session_key: str,
    ) -> Dict[str, Any]:
        start_node_id = str(run.start_node_id or session.get("startNodeId") or document_start_node_id(run.document))
        prompt = self._planning_table_skill_update_notification_prompt(event)
        queued = self._async_loop.run(
            self._queue_framework_notification_for_runtime(
                run,
                run.graph.agent_nodes[start_node_id],
                {
                    "type": "framework_planning_table_skill_update_notification",
                    "prompt": prompt,
                    "framework_message_kind": "framework_planning_table_skill_update_notification",
                    "reply_required": True,
                    "reply_visibility": "session_event",
                    "planning_table_skill_update_notification": dict(event),
                },
                queue_mode="top",
            )
        )
        now = float(self.now())
        self._configure_run_session_tools(
            run,
            source="automation",
            session_key=session_key,
            start_node_id=start_node_id,
            now=now,
        )
        session["status"] = "running"
        session["activeRunId"] = run.run_id
        session["lastRunId"] = run.run_id
        session["assignedBlueprintId"] = run.blueprint_id
        session["startNodeId"] = start_node_id
        session["lastTouchedAt"] = now
        self._save_blueprint_session(session)
        self._append_blueprint_session_event(
            session_key,
            {
                "type": "planning_table_skill_update_notification",
                "source": "framework",
                "notification": dict(event),
                "runId": run.run_id,
                "startNodeId": start_node_id,
            },
        )
        return queued

    def _build_blueprint_session_context(self, session: Dict[str, Any], current_message: str) -> str:
        lines: list[str] = []
        session_key = str(session.get("sessionKey") or "").strip()
        if session_key:
            lines.append("[BlueprintSession]")
            lines.append(f"sessionKey: {session_key}")
            lines.append(f"source: {str(session.get('source') or '').strip() or 'unknown'}")
            lines.append(
                "Use this sessionKey when table_queue_service occupy needs a sessionKey for later queue notifications."
            )
            lines.append("")
        summary = str(session.get("contextSummary") or "").strip()
        if summary:
            lines.append("[BlueprintSession Summary]")
            lines.append(summary)
            lines.append("")
        events = self._read_blueprint_session_events(str(session.get("sessionKey") or ""))
        if events:
            lines.append("[Recent BlueprintSession Messages]")
            for event in events:
                event_type = str(event.get("type") or "")
                if event_type == "agent_reply":
                    role = "Agent"
                    text = str(event.get("content") or "").strip()
                else:
                    role = "User"
                    text = str(event.get("message") or "").strip()
                if text:
                    lines.append(f"{role}: {text}")
            lines.append("")
        lines.append("[Current POPO Message]")
        lines.append(f"[popo_user] {str(current_message).strip()}")
        context = "\n".join(lines).strip()
        if len(context) <= BLUEPRINT_SESSION_CONTEXT_CHAR_LIMIT:
            return context
        return context[-BLUEPRINT_SESSION_CONTEXT_CHAR_LIMIT:]

    def list_blueprint_sessions(
        self,
        project_dir: Optional[Path] = None,
        blueprint_id: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        resolved_project = validate_project_dir(project_dir) if project_dir is not None else None
        normalized_blueprint_id = validate_blueprint_id(blueprint_id) if blueprint_id else None
        directory = self.blueprint_sessions_dir()
        if not directory.exists():
            return []
        sessions: list[Dict[str, Any]] = []
        for session_path in sorted(directory.glob("*/session.json")):
            try:
                session = json.loads(session_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(session, dict) or session.get("deleted"):
                continue
            if resolved_project is not None and str(session.get("projectDir") or "") != str(resolved_project):
                continue
            if normalized_blueprint_id and str(session.get("blueprintId") or "") != normalized_blueprint_id:
                continue
            session = self._maybe_upgrade_popo_session_key(session)
            if session.get("deleted") or session.get("superseded"):
                continue
            active_run_id = str(session.get("activeRunId") or "")
            if active_run_id:
                with self._lock:
                    run = self._runs.get(active_run_id)
                if run is None:
                    session["activeRunId"] = ""
                    session["status"] = "idle"
                    session["lastRunId"] = active_run_id
                    session["lastTouchedAt"] = float(self.now())
                    self._save_blueprint_session(session)
                elif not self._run_is_active(run):
                    self._mark_blueprint_session_run_ended(run)
                    session = self._load_blueprint_session(str(session.get("sessionKey") or "")) or session
            sessions.append(dict(session))
        return sorted(
            sessions,
            key=lambda item: (
                0 if item.get("activeRunId") else 1,
                -float(item.get("lastTouchedAt") or item.get("createdAt") or 0),
            ),
        )

    def _session_matches_structure(
        self,
        session: Dict[str, Any],
        *,
        project_dir: Path,
        blueprint_structure_id: str,
    ) -> bool:
        return (
            str(session.get("projectDir") or "") == str(validate_project_dir(project_dir))
            and str(session.get("blueprintStructureId") or "") == str(blueprint_structure_id)
            and not bool(session.get("deleted"))
        )

    def _sessions_for_blueprint_structure(
        self,
        *,
        project_dir: Path,
        blueprint_structure_id: str,
    ) -> list[Dict[str, Any]]:
        directory = self.blueprint_sessions_dir()
        if not directory.exists():
            return []
        sessions: list[Dict[str, Any]] = []
        for session_path in sorted(directory.glob("*/session.json")):
            try:
                session = json.loads(session_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(session, dict):
                continue
            if not self._session_matches_structure(
                session,
                project_dir=project_dir,
                blueprint_structure_id=blueprint_structure_id,
            ):
                continue
            session = self._maybe_upgrade_popo_session_key(session)
            if session.get("deleted") or session.get("superseded"):
                continue
            sessions.append(dict(session))
        return sorted(
            sessions,
            key=lambda item: (
                0 if item.get("activeRunId") else 1,
                0 if str(item.get("status") or "") == "queued" else 1,
                -float(item.get("lastTouchedAt") or item.get("createdAt") or 0),
            ),
        )

    def delete_blueprint_session(self, session_key: str) -> Dict[str, Any]:
        normalized_key = blueprint_session_key_path_component(session_key)
        active = self._active_run_for_session(normalized_key)
        if active is not None:
            raise BlueprintServiceError(
                "BLUEPRINT_SESSION_RUNNING",
                "running blueprint sessions cannot be deleted",
                details={"sessionKey": normalized_key, "runId": active.run_id},
            )
        session = self._load_blueprint_session(normalized_key)
        if not session:
            raise BlueprintServiceError("BLUEPRINT_SESSION_NOT_FOUND", "blueprint session was not found", status=404)
        session["deleted"] = True
        session["status"] = "deleted"
        session["lastTouchedAt"] = float(self.now())
        self._save_blueprint_session(session)
        self._append_blueprint_session_event(normalized_key, {"type": "session_deleted"})
        return {"ok": True, "sessionKey": normalized_key, "deleted": True}

    def _mark_idle_session_terminated(
        self,
        session_key: str,
        *,
        reason: str = "",
        actor: str = "ui",
    ) -> Dict[str, Any]:
        normalized_key = blueprint_session_key_path_component(session_key)
        session = self._load_blueprint_session(normalized_key)
        if not session:
            raise BlueprintServiceError("BLUEPRINT_SESSION_NOT_FOUND", "blueprint session was not found", status=404)
        now = float(self.now())
        previous_status = str(session.get("status") or "idle")
        session["activeRunId"] = ""
        session["status"] = "terminated"
        session["queuedMessages"] = []
        session["lastTouchedAt"] = now
        self._record_blueprint_session_terminator(session, actor=actor)
        self._save_blueprint_session(session)
        self._append_blueprint_session_event(
            normalized_key,
            {
                "type": "session_terminated",
                "reason": str(reason or ""),
                "actor": actor,
                "previousStatus": previous_status,
            },
        )
        return {
            "ok": True,
            "sessionKey": normalized_key,
            "terminated": True,
            "previousStatus": previous_status,
            "session": session,
        }

    def terminate_blueprint_session(
        self,
        session_key: str,
        *,
        reason: str = "",
        actor: str = "ui",
    ) -> Dict[str, Any]:
        normalized_key = blueprint_session_key_path_component(session_key)
        active = self._active_run_for_session(normalized_key)
        if active is not None:
            return self._terminate_active_blueprint_session(
                active.run_id,
                reason=reason or f"blueprint session terminated by {actor}",
                save_history=True,
                actor=actor,
            )
        return self._mark_idle_session_terminated(
            normalized_key,
            reason=reason,
            actor=actor,
        )

    def stop_blueprint_session_from_user_command(
        self,
        session_key: str,
        *,
        reason: str = "",
        actor: str = "ui",
    ) -> Dict[str, Any]:
        normalized_key = blueprint_session_key_path_component(session_key)
        active = self._active_run_for_session(normalized_key)
        session = self._load_blueprint_session(normalized_key)
        if active is None and not session:
            return {
                "ok": True,
                "sessionKey": normalized_key,
                "stopped": True,
                "alreadyStopped": True,
                "message": "当前没有正在运行的会话",
            }
        result = self.terminate_blueprint_session(
            normalized_key,
            reason=reason or f"{actor} requested /stop",
            actor=actor,
        )
        result["stopped"] = True
        result.setdefault("message", "已结束当前会话")
        return result

    def _blueprint_session_family_name(self, session: Dict[str, Any]) -> str:
        return _blueprint_session_name_slug(
            str(session.get("blueprintName") or ""),
            fallback=str(session.get("blueprintId") or ""),
        )

    def _superseded_session_archive_key(self, session_key: str) -> str:
        normalized = blueprint_session_key_path_component(session_key)
        reusable = normalized.startswith(BLUEPRINT_MAIN_SESSION_PREFIX) or (
            normalized.startswith(BLUEPRINT_POPO_SESSION_PREFIX) and "+" in normalized
        )
        if not reusable:
            return normalized
        for _attempt in range(100):
            candidate = f"{normalized}-superseded-{secrets.token_hex(4)}"
            if not self._blueprint_session_dir(candidate).exists():
                return candidate
        return f"{normalized}-superseded-{secrets.token_hex(8)}"

    def _mark_blueprint_session_superseded(
        self,
        session_key: str,
        *,
        reason: str,
        current_blueprint_id: str,
        current_blueprint_name: str,
        current_structure_id: str,
    ) -> Optional[str]:
        normalized_key = blueprint_session_key_path_component(session_key)
        session = self._load_blueprint_session(normalized_key)
        if not session:
            return None
        now = float(self.now())
        archive_key = self._superseded_session_archive_key(normalized_key)
        session.update(
            {
                "sessionKey": archive_key,
                "activeRunId": "",
                "queuedMessages": [],
                "queuedMessageCount": 0,
                "status": "superseded",
                "superseded": True,
                "supersededAt": now,
                "supersededReason": str(reason or ""),
                "supersededByBlueprintId": current_blueprint_id,
                "supersededByBlueprintName": current_blueprint_name,
                "supersededByStructureId": current_structure_id,
                "lastTouchedAt": now,
            }
        )
        if archive_key != normalized_key:
            old_dir = self._blueprint_session_dir(normalized_key)
            new_dir = self._blueprint_session_dir(archive_key)
            if old_dir.exists():
                new_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_dir), str(new_dir))
        self._save_blueprint_session(session)
        self._append_blueprint_session_event(
            archive_key,
            {
                "type": "session_superseded",
                "actor": "blueprint_restart",
                "reason": str(reason or ""),
                "previousSessionKey": normalized_key,
                "currentBlueprintId": current_blueprint_id,
                "currentBlueprintName": current_blueprint_name,
                "currentStructureId": current_structure_id,
            },
        )
        self._replace_run_session_key(normalized_key, archive_key)
        return archive_key

    def restart_blueprint_sessions(
        self,
        project_dir: Path,
        blueprint_id: str,
        *,
        reason: str = "",
    ) -> Dict[str, Any]:
        preflight = self._blueprint_session_preflight(project_dir, blueprint_id, require_popo=False)
        document = preflight["document"]
        resolved_project = validate_project_dir(project_dir)
        current_blueprint_id = str(document["id"])
        current_blueprint_name = str(document.get("name") or current_blueprint_id)
        current_structure_id = str(preflight["blueprintStructureId"])
        family_name = _blueprint_session_name_slug(current_blueprint_name, fallback=current_blueprint_id)
        restart_reason = str(reason or "blueprint sessions restarted to apply current structure")
        candidates: list[Dict[str, Any]] = []
        directory = self.blueprint_sessions_dir()
        if directory.exists():
            for session_path in sorted(directory.glob("*/session.json")):
                try:
                    session = json.loads(session_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(session, dict) or session.get("deleted"):
                    continue
                if str(session.get("projectDir") or "") != str(resolved_project):
                    continue
                if self._blueprint_session_family_name(session) != family_name:
                    continue
                candidates.append(dict(session))

        terminated_run_ids: list[str] = []
        superseded_session_keys: list[str] = []
        close_errors: list[Dict[str, str]] = []
        seen_session_keys: set[str] = set()
        for session in candidates:
            session_key = str(session.get("sessionKey") or "").strip()
            if not session_key or session_key in seen_session_keys:
                continue
            seen_session_keys.add(session_key)
            active = self._active_run_for_session(session_key)
            run_id = str(active.run_id if active is not None else session.get("activeRunId") or "").strip()
            if run_id:
                with self._lock:
                    run_exists = run_id in self._runs
                if run_exists:
                    result = self._terminate_active_blueprint_session(
                        run_id,
                        reason=restart_reason,
                        save_history=True,
                        actor="blueprint_restart",
                    )
                    terminated_run_ids.append(run_id)
                    close_error = str(result.get("closeError") or "").strip()
                    if close_error:
                        close_errors.append({"runId": run_id, "error": close_error})
                else:
                    terminated_run_ids.append(run_id)
            archived_key = self._mark_blueprint_session_superseded(
                session_key,
                reason=restart_reason,
                current_blueprint_id=current_blueprint_id,
                current_blueprint_name=current_blueprint_name,
                current_structure_id=current_structure_id,
            )
            if archived_key:
                superseded_session_keys.append(archived_key)

        return {
            "ok": True,
            "projectDir": str(resolved_project),
            "blueprintId": current_blueprint_id,
            "currentBlueprintName": current_blueprint_name,
            "currentStructureId": current_structure_id,
            "terminatedRunIds": terminated_run_ids,
            "supersededSessionKeys": superseded_session_keys,
            "closeErrors": close_errors,
        }

    def clear_blueprint_session(
        self,
        session_key: str,
        *,
        reason: str = "",
        project_dir: Optional[Path] = None,
        blueprint_id: str = "",
    ) -> Dict[str, Any]:
        normalized_key = blueprint_session_key_path_component(session_key)
        cancelled_run_id = ""
        active = self._active_run_for_session(normalized_key)
        if active is not None:
            cancelled_run_id = active.run_id
            try:
                self._close_blueprint_session_run_best_effort(
                    active.run_id,
                    reason=reason or "blueprint session cleared with /new",
                )
            except Exception:
                self._mark_blueprint_session_run_ended(active)
        now = float(self.now())
        session = self._load_blueprint_session(normalized_key) or {
            "sessionKey": normalized_key,
            "projectDir": str(validate_project_dir(project_dir)) if project_dir is not None else "",
            "poolKey": "",
            "robotAppKey": "",
            "blueprintId": str(blueprint_id or ""),
            "assignedBlueprintId": "",
            "blueprintName": str(blueprint_id or ""),
            "blueprintStructureId": "",
            "source": "ui" if normalized_key.startswith(BLUEPRINT_MAIN_SESSION_PREFIX) else "",
            "popoUserId": "",
            "popoSessionId": "",
            "popoGroupId": "",
            "status": "idle",
            "activeRunId": "",
            "lastRunId": "",
            "contextSummary": "",
            "messageCount": 0,
            "createdAt": now,
            "lastTouchedAt": now,
            "deleted": False,
        }
        session["contextSummary"] = ""
        session["messageCount"] = 0
        session["activeRunId"] = ""
        session["queuedMessages"] = []
        session["queuedMessageCount"] = 0
        for key in (
            "lastAgentReplyAt",
            "lastAgentReplyByAgentId",
            "lastAgentReplyByNodeId",
            "lastTerminatedAt",
            "lastTerminatedBy",
            "lastTerminatedByAgentId",
            "lastTerminatedByAgentNodeId",
        ):
            session.pop(key, None)
        if cancelled_run_id:
            session["lastRunId"] = cancelled_run_id
        session["status"] = "idle"
        session["deleted"] = False
        session["lastTouchedAt"] = now
        self._save_blueprint_session(session)
        transcript_path = self._blueprint_session_transcript_path(normalized_key)
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text("", encoding="utf-8")
        return {
            "ok": True,
            "sessionKey": normalized_key,
            "cleared": True,
            "cancelledRunId": cancelled_run_id,
            "resetRunId": "",
            "resetPending": False,
            "session": session,
        }

    def _delete_blueprint_session_history_paths(self, session_key: str) -> tuple[list[str], list[Dict[str, str]]]:
        normalized_key = blueprint_session_key_path_component(session_key)
        session_dir = self._blueprint_session_dir(normalized_key)
        deleted_paths: list[str] = []
        delete_errors: list[Dict[str, str]] = []
        excel_ops_dir = session_dir / "excel_ops"
        if not excel_ops_dir.exists():
            return deleted_paths, delete_errors
        try:
            resolved_session_dir = session_dir.resolve()
            resolved_excel_ops_dir = excel_ops_dir.resolve()
            if resolved_excel_ops_dir == resolved_session_dir or resolved_session_dir not in resolved_excel_ops_dir.parents:
                raise BlueprintServiceError(
                    "BLUEPRINT_SESSION_HISTORY_PATH_INVALID",
                    "refusing to delete a path outside the blueprint session directory",
                    details={"sessionKey": normalized_key, "path": str(excel_ops_dir)},
                )
            if excel_ops_dir.is_dir():
                shutil.rmtree(excel_ops_dir)
            else:
                excel_ops_dir.unlink()
            deleted_paths.append(str(excel_ops_dir))
        except Exception as exc:
            delete_errors.append({"path": str(excel_ops_dir), "error": str(exc)})
        return deleted_paths, delete_errors

    def clear_blueprint_session_history(
        self,
        session_key: str,
        *,
        reason: str = "",
    ) -> Dict[str, Any]:
        normalized_key = blueprint_session_key_path_component(session_key)
        session = self._load_blueprint_session(normalized_key)
        if not session or session.get("deleted") or session.get("superseded"):
            raise BlueprintServiceError("BLUEPRINT_SESSION_NOT_FOUND", "blueprint session was not found", status=404)
        result = self.clear_blueprint_session(
            normalized_key,
            reason=reason or "blueprint session history cleared",
        )
        deleted_paths, delete_errors = self._delete_blueprint_session_history_paths(normalized_key)
        result.update(
            {
                "historyCleared": not delete_errors,
                "clearedPaths": [str(self._blueprint_session_transcript_path(normalized_key))],
                "deletedPaths": deleted_paths,
                "deleteErrors": delete_errors,
            }
        )
        return result

    def _blueprint_session_preflight(
        self,
        project_dir: Path,
        blueprint_id: str,
        *,
        require_popo: bool = False,
    ) -> Dict[str, Any]:
        document = self.open_blueprint(project_dir, blueprint_id)
        config_issues = blueprint_common_config_issues(document)
        if config_issues:
            raise BlueprintServiceError(
                "BLUEPRINT_CONFIG_REQUIRED",
                "required blueprint common config paths must be set before start",
                details={"blueprintId": str(document["id"]), "issues": config_issues},
            )
        document = document_with_common_config_paths(document)
        start_node_id = document_start_node_id(document)
        graph_dict = dict(document["graph"])
        graph = graph_definition_from_dict(graph_dict)
        validate_desktop_blueprint_graph(graph, project_dir=validate_project_dir(project_dir))
        valid_start_nodes = set(blueprint_runtime_start_node_ids(graph))
        if not start_node_id or start_node_id not in graph.agent_nodes or start_node_id not in valid_start_nodes:
            raise BlueprintServiceError(
                "BLUEPRINT_START_NODE_REQUIRED",
                "blueprint runtime.start_node_id must reference exactly one full Agent node before start",
                details={"blueprintId": str(document["id"]), "validStartNodes": sorted(valid_start_nodes)},
            )
        if require_popo:
            popo_entry = require_complete_popo_entry(document)
        else:
            try:
                popo_entry = require_complete_popo_entry(document)
            except BlueprintServiceError:
                popo_entry = document_popo_entry(document)
        structure_id = canonical_blueprint_structure_id(graph_dict)
        return {
            "document": document,
            "graph": graph,
            "graphDict": graph_dict,
            "startNodeId": start_node_id,
            "popoEntry": popo_entry,
            "blueprintStructureId": structure_id,
        }

    def _collect_popo_blueprint_bindings(self, project_dir: Path, robot_app_key: str) -> list[Dict[str, Any]]:
        robot_key = str(robot_app_key or "").strip()
        resolved_project = validate_project_dir(project_dir)
        bindings: list[Dict[str, Any]] = []
        for summary in self.list_blueprints(resolved_project):
            blueprint_id = str(summary.get("id") or "").strip()
            if not blueprint_id:
                continue
            try:
                document = self.open_blueprint(resolved_project, blueprint_id)
            except BlueprintServiceError:
                continue
            enabled_entries = _document_enabled_popo_agent_entries(document)
            if not enabled_entries:
                continue
            if robot_key and all(str(entry.get("robot_app_key") or "") != robot_key for _node_id, entry in enabled_entries):
                continue
            config_issues = blueprint_common_config_issues(document)
            if config_issues:
                raise BlueprintServiceError(
                    "BLUEPRINT_CONFIG_REQUIRED",
                    "required blueprint common config paths must be set before start",
                    details={"blueprintId": blueprint_id, "issues": config_issues},
                )
            document = document_with_common_config_paths(document)
            entry = require_complete_popo_entry(document)
            missing = popo_entry_missing_fields(entry)
            if missing:
                raise BlueprintServiceError(
                    "BLUEPRINT_POPO_ENTRY_REQUIRED",
                    "the saved start full Agent popo_entry is incomplete for this robot",
                    details={"blueprintId": blueprint_id, "missing": missing},
                )
            graph_dict = dict(document.get("graph") or {})
            graph = graph_definition_from_dict(graph_dict)
            validate_desktop_blueprint_graph(graph, project_dir=resolved_project)
            start_node_id = document_start_node_id(document)
            valid_start_nodes = set(blueprint_runtime_start_node_ids(graph))
            if not start_node_id or start_node_id not in graph.agent_nodes or start_node_id not in valid_start_nodes:
                raise BlueprintServiceError(
                    "BLUEPRINT_START_NODE_REQUIRED",
                    "blueprint runtime.start_node_id must reference exactly one full Agent node before start",
                    details={"blueprintId": blueprint_id, "validStartNodes": sorted(valid_start_nodes)},
                )
            bindings.append(
                {
                    "document": document,
                    "projectDir": str(resolved_project),
                    "blueprintId": blueprint_id,
                    "blueprintName": str(document.get("name") or blueprint_id),
                    "blueprintStructureId": canonical_blueprint_structure_id(graph_dict),
                    "startNodeId": start_node_id,
                    "popoEntry": entry,
                }
            )
        return bindings

    def _popo_binding_robot_key(self, binding: Dict[str, Any]) -> str:
        popo_entry = binding.get("popoEntry") if isinstance(binding.get("popoEntry"), dict) else {}
        return str(popo_entry.get("robot_app_key") or binding.get("robotAppKey") or "").strip()

    def _popo_binding_pool_key(self, binding: Dict[str, Any], robot_app_key: str = "") -> str:
        project_text = str(binding.get("projectDir") or "").strip()
        structure_id = str(binding.get("blueprintStructureId") or "").strip()
        robot_key = self._popo_binding_robot_key(binding) or str(robot_app_key or "").strip()
        if not project_text or not structure_id or not robot_key:
            return ""
        return blueprint_slot_pool_key(
            project_dir=Path(project_text),
            source="popo",
            source_binding=robot_key,
            blueprint_structure_id=structure_id,
        )

    def _popo_binding_summary(self, binding: Dict[str, Any], robot_app_key: str = "") -> Dict[str, Any]:
        return {
            "projectDir": str(binding.get("projectDir") or ""),
            "blueprintId": str(binding.get("blueprintId") or ""),
            "blueprintName": str(binding.get("blueprintName") or ""),
            "blueprintStructureId": str(binding.get("blueprintStructureId") or ""),
            "robotAppKey": self._popo_binding_robot_key(binding) or str(robot_app_key or "").strip(),
            "poolKey": self._popo_binding_pool_key(binding, robot_app_key),
            "activeRunId": str(binding.get("activeRunId") or ""),
        }

    def _dedupe_popo_blueprint_bindings(self, bindings: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        unique: dict[tuple[str, str, str], Dict[str, Any]] = {}
        for binding in bindings:
            key = (
                str(binding.get("projectDir") or ""),
                str(binding.get("blueprintId") or ""),
                str(binding.get("blueprintStructureId") or ""),
            )
            if not all(key):
                continue
            current = unique.get(key)
            if current is None or (str(binding.get("activeRunId") or "") and not str(current.get("activeRunId") or "")):
                unique[key] = binding
        return list(unique.values())

    def _find_popo_binding_for_existing_session(
        self,
        bindings: list[Dict[str, Any]],
        robot_app_key: str,
        session_identity: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        identity = dict(session_identity or {})
        popo_user_id = str(identity.get("popoUserId") or identity.get("sourceUserId") or "").strip()
        popo_session_id = str(identity.get("popoSessionId") or identity.get("sourceSessionId") or "").strip()
        popo_group_id = str(identity.get("popoGroupId") or identity.get("sourceGroupId") or "").strip()
        if not (popo_user_id or popo_session_id or popo_group_id):
            return None
        matches: list[tuple[int, float, str, str, Dict[str, Any]]] = []
        for binding in bindings:
            pool_key = self._popo_binding_pool_key(binding, robot_app_key)
            if not pool_key:
                continue
            session_keys = [
                blueprint_popo_named_session_key(
                    blueprint_name=str(binding.get("blueprintName") or binding.get("blueprintId") or ""),
                    blueprint_id=str(binding.get("blueprintId") or ""),
                    popo_user_id=popo_user_id,
                    popo_session_id=popo_session_id,
                    popo_group_id=popo_group_id,
                ),
                blueprint_session_key_for_pool(
                    pool_key=pool_key,
                    source="popo",
                    popo_user_id=popo_user_id,
                    popo_session_id=popo_session_id,
                    popo_group_id=popo_group_id,
                ),
                blueprint_legacy_session_key_for_pool(
                    pool_key=pool_key,
                    source="popo",
                    popo_user_id=popo_user_id,
                    popo_session_id=popo_session_id,
                    popo_group_id=popo_group_id,
                ),
            ]
            for key in session_keys:
                session = self._load_blueprint_session(key)
                if not isinstance(session, dict) or session.get("deleted") or session.get("superseded"):
                    continue
                session = self._maybe_upgrade_popo_session_key(session)
                session_scope = str(session.get("sessionScopeKey") or session.get("poolKey") or "").strip()
                named_session_key = str(session.get("sessionKey") or key).startswith(BLUEPRINT_POPO_SESSION_PREFIX) and "+" in str(session.get("sessionKey") or key)
                if session_scope and session_scope != pool_key and not named_session_key:
                    continue
                session_robot = str(session.get("robotAppKey") or "").strip()
                binding_robot = self._popo_binding_robot_key(binding) or str(robot_app_key or "").strip()
                if session_robot and binding_robot and session_robot != binding_robot:
                    continue
                exact_blueprint = int(str(session.get("blueprintId") or "") == str(binding.get("blueprintId") or ""))
                matches.append(
                    (
                        exact_blueprint,
                        float(session.get("lastTouchedAt") or session.get("createdAt") or 0.0),
                        str(session.get("sessionKey") or key),
                        str(binding.get("blueprintStructureId") or ""),
                        binding,
                    )
                )
        if not matches:
            return None
        return sorted(matches, key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)[0][4]

    def _current_open_popo_binding(self, bindings: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        registry = self._read_blueprint_project_registry()
        projects = registry.get("projects") if isinstance(registry.get("projects"), dict) else {}
        if not projects:
            return None
        rows_by_project: dict[str, Dict[str, Any]] = {}
        for item in projects.values():
            if not isinstance(item, dict):
                continue
            project_text = str(item.get("projectDir") or "").strip()
            if not project_text:
                continue
            rows_by_project[str(Path(project_text).expanduser().resolve()).casefold()] = item
        matches: list[tuple[float, str, Dict[str, Any]]] = []
        for binding in bindings:
            project_text = str(binding.get("projectDir") or "").strip()
            blueprint_id = str(binding.get("blueprintId") or "").strip()
            if not project_text or not blueprint_id:
                continue
            row = rows_by_project.get(str(Path(project_text).expanduser().resolve()).casefold())
            if not row:
                continue
            if str(row.get("lastOpenedBlueprintId") or "") != blueprint_id:
                continue
            matches.append((float(row.get("lastOpenedAt") or 0.0), blueprint_id, binding))
        if not matches:
            return None
        return sorted(matches, key=lambda item: (item[0], item[1]), reverse=True)[0][2]

    def _resolve_popo_blueprint_binding(
        self,
        robot_app_key: str,
        bindings: list[Dict[str, Any]],
        *,
        session_identity: Optional[Dict[str, Any]] = None,
        searched_projects: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        robot_key = str(robot_app_key or "").strip()
        unique = self._dedupe_popo_blueprint_bindings(bindings)
        if not unique:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_ROBOT_NOT_BOUND",
                "no blueprint session target is bound to this POPO robot",
                details={"robotAppKey": robot_key, "searchedProjects": searched_projects or []},
                status=404,
            )
        binding_robot_keys = sorted({self._popo_binding_robot_key(item) for item in unique if self._popo_binding_robot_key(item)})
        if not robot_key and len(binding_robot_keys) > 1:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_ROBOT_STRUCTURE_CONFLICT",
                "legacy POPO callback path matched multiple blueprint robots",
                details={
                    "robotAppKey": robot_key,
                    "robotAppKeys": binding_robot_keys,
                    "bindings": [self._popo_binding_summary(item, robot_key) for item in unique],
                    "searchedProjects": searched_projects or [],
                },
            )
        if len(unique) == 1:
            return unique[0]

        session_binding = self._find_popo_binding_for_existing_session(unique, robot_key, session_identity)
        if session_binding is not None:
            return session_binding

        current_binding = self._current_open_popo_binding(unique)
        if current_binding is not None:
            return current_binding

        raise BlueprintServiceError(
            "BLUEPRINT_POPO_ROBOT_STRUCTURE_CONFLICT",
            "multiple blueprint targets matched this POPO robot and no current blueprint fallback is available",
            details={
                "robotAppKey": robot_key,
                "selectionReason": "no_current_blueprint",
                "bindings": [self._popo_binding_summary(item, robot_key) for item in unique],
                "searchedProjects": searched_projects or [],
            },
        )

    def _find_popo_blueprint_binding(
        self,
        project_dir: Path,
        robot_app_key: str,
        *,
        session_identity: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        robot_key = str(robot_app_key or "").strip()
        bindings = self._active_popo_slot_bindings(robot_key, project_dir=project_dir)
        bindings.extend(self._collect_popo_blueprint_bindings(project_dir, robot_key))
        return self._resolve_popo_blueprint_binding(
            robot_key,
            bindings,
            session_identity=session_identity,
            searched_projects=[str(validate_project_dir(project_dir))],
        )

    def _active_popo_slot_bindings(self, robot_app_key: str, *, project_dir: Optional[Path] = None) -> list[Dict[str, Any]]:
        robot_key = str(robot_app_key or "").strip()
        resolved_project = validate_project_dir(project_dir) if project_dir is not None else None
        with self._lock:
            runs = list(self._runs.values())
        bindings: dict[tuple[str, str, str], Dict[str, Any]] = {}
        for run in runs:
            if resolved_project is not None and run.project_dir != resolved_project:
                continue
            run_robot_key = str(run.robot_app_key or "")
            if not run_robot_key:
                continue
            if robot_key and run_robot_key != robot_key:
                continue
            if not self._run_is_active(run):
                self._mark_blueprint_session_run_ended(run)
                continue
            key = (str(run.project_dir), str(run.blueprint_id), str(run.blueprint_structure_id or ""))
            bindings[key] = {
                "document": run.document,
                "projectDir": str(run.project_dir),
                "blueprintId": run.blueprint_id,
                "blueprintName": str(run.document.get("name") or run.blueprint_id),
                "blueprintStructureId": str(run.blueprint_structure_id or ""),
                "startNodeId": str(run.start_node_id or document_start_node_id(run.document)),
                "popoEntry": document_popo_entry(run.document),
                "activeRunId": run.run_id,
            }
        return list(bindings.values())

    def _find_global_popo_blueprint_binding(
        self,
        robot_app_key: str,
        *,
        session_identity: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        robot_key = str(robot_app_key or "").strip()
        active_bindings = self._active_popo_slot_bindings(robot_key)
        bindings: list[Dict[str, Any]] = list(active_bindings)
        searched_projects: list[str] = []
        for row in self.list_registered_blueprint_projects(existing_only=True):
            project_text = str(row.get("projectDir") or "")
            if not project_text:
                continue
            searched_projects.append(project_text)
            try:
                project_bindings = self._collect_popo_blueprint_bindings(Path(project_text), robot_key)
            except BlueprintServiceError as exc:
                if exc.code == "BLUEPRINT_POPO_ROBOT_NOT_BOUND":
                    continue
                raise
            bindings.extend(project_bindings)
        return self._resolve_popo_blueprint_binding(
            robot_key,
            bindings,
            session_identity=session_identity,
            searched_projects=searched_projects,
        )

    def message_global_popo_blueprint_session(
        self,
        message: str,
        *,
        source_identity: Optional[Dict[str, Any]] = None,
        session_identity: Optional[Dict[str, Any]] = None,
        session_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        if _is_blueprint_session_help_command(message):
            return _blueprint_session_direct_command_help_response(session_key or "")
        source_identity = dict(source_identity or {})
        robot_app_key = str(source_identity.get("robotAppKey") or source_identity.get("robot_app_key") or "").strip()
        binding = self._find_global_popo_blueprint_binding(robot_app_key, session_identity=session_identity or {})
        project_dir = Path(str(binding.get("projectDir") or ""))
        popo_entry = binding.get("popoEntry") if isinstance(binding.get("popoEntry"), dict) else {}
        resolved_robot_app_key = str(popo_entry.get("robot_app_key") or robot_app_key).strip()
        return self.message_blueprint_session(
            project_dir,
            str(binding.get("blueprintId") or DEFAULT_BLUEPRINT_ID),
            message,
            source="popo",
            source_identity={"robotAppKey": resolved_robot_app_key},
            session_identity=session_identity or {},
            session_key=session_key,
            popo_binding=binding,
        )

    def _queue_blueprint_session_message(
        self,
        run: DesktopBlueprintRun,
        session: Dict[str, Any],
        text: str,
        *,
        source: str,
        session_key: str,
        ) -> Dict[str, Any]:
        start_node_id = str(run.start_node_id or document_start_node_id(run.document))
        current_text = str(text or "").strip()
        dispatch_text = current_text
        task_text = self._build_blueprint_session_context(session, current_text)
        queued = self.queue_agent_message(
            run.run_id,
            start_node_id,
            task_text,
            mode="top",
            merge_key=f"blueprint-session:{session_key}:{start_node_id}",
            merge_append_text=dispatch_text or current_text,
        )
        now = float(self.now())
        self._configure_run_session_tools(
            run,
            source=source,
            session_key=session_key,
            start_node_id=start_node_id,
            now=now,
        )
        session["status"] = "running"
        session["activeRunId"] = run.run_id
        session["lastRunId"] = run.run_id
        session["assignedBlueprintId"] = run.blueprint_id
        session["startNodeId"] = start_node_id
        session["queuedMessages"] = []
        session["queuedMessageCount"] = 0
        session["lastTouchedAt"] = now
        self._save_blueprint_session(session)
        self._append_blueprint_session_event(
            session_key,
            {
                "type": "queued_message",
                "source": source,
                "message": dispatch_text or current_text,
                "runId": run.run_id,
                "startNodeId": start_node_id,
            },
        )
        return queued

    def _configure_run_session_tools(
        self,
        run: DesktopBlueprintRun,
        *,
        source: str,
        session_key: str,
        start_node_id: str,
        now: Optional[float] = None,
    ) -> None:
        with self._lock:
            run.session_key = session_key
            run.updated_at = float(self.now() if now is None else now)
            try:
                if run.mcp is not None and callable(getattr(run.mcp, "enable_session_history_tools", None)):
                    run.mcp.enable_session_history_tools(
                        start_node_id=start_node_id,
                        session_key=session_key,
                    )
                if str(source or "").strip().lower() == "popo" and str(run.robot_app_key or "").strip():
                    run.runtime.popo_reply_start_node_id = start_node_id
                    run.runtime.popo_reply_session_key = session_key
                else:
                    run.runtime.popo_reply_start_node_id = ""
                    run.runtime.popo_reply_session_key = ""
            except Exception:
                log.exception("failed to enable blueprint session MCP tools")

    def _start_blueprint_session_instance(
        self,
        *,
        project_dir: Path,
        document: Dict[str, Any],
        graph: Any,
        session_key: str,
        start_node_id: str,
        blueprint_structure_id: str,
        robot_app_key: str = "",
        source_bindings: Optional[Dict[str, Any]] = None,
    ) -> tuple[DesktopBlueprintRun, Dict[str, Any]]:
        with self._lock:
            run_id = self._generate_run_id_locked()
        backend, runtime, control, mcp, diagnostics_dir = self._async_loop.run(
            self._prepare_live_runtime(
                run_id,
                validate_project_dir(project_dir),
                document,
                graph,
            )
        )
        now = float(self.now())
        with self._lock:
            run = DesktopBlueprintRun(
                run_id=run_id,
                project_dir=validate_project_dir(project_dir),
                blueprint_id=str(document["id"]),
                document=document,
                graph=graph,
                runtime=runtime,
                control=control,
                execution_mode="live",
                created_at=now,
                updated_at=now,
                backend=backend,
                mcp=mcp,
                diagnostics_dir=diagnostics_dir,
                session_key=session_key,
                start_node_id=start_node_id,
                blueprint_structure_id=blueprint_structure_id,
                robot_app_key=robot_app_key,
                source_bindings=dict(source_bindings or {}),
            )
            self._attach_stream_notification(run)
            self._runs[run.run_id] = run
        start_future = self._async_loop.submit(self._complete_live_session_start(run))
        with self._lock:
            run.live_start_future = start_future
        try:
            started = start_future.result(timeout=LIVE_START_RESULT_WAIT_SECONDS)
        except FutureTimeoutError:
            started = {
                "ok": True,
                "pending": True,
                "validation": {"ok": True, "errors": [], "warnings": []},
                "queued_messages": [],
                "start_manifest": {},
            }
            self._append_blueprint_diagnostics_event(run, "blueprint_session_start_pending")
        except Exception as exc:
            with self._lock:
                self._runs.pop(run.run_id, None)
                run.live_start_error = str(exc)
            try:
                self._async_loop.run(self._close_live_run(run), timeout=10)
            except Exception:
                pass
            raise BlueprintServiceError(
                "LIVE_AGENT_START_FAILED",
                "failed to start live blueprint session Agents",
                details={"error": str(exc), "blueprintId": str(document["id"])},
            ) from exc
        return run, started

    def message_blueprint_session(
        self,
        project_dir: Path,
        blueprint_id: Optional[str],
        message: str,
        *,
        source: str = "ui",
        popo_user_id: str = "",
        popo_session_id: str = "",
        popo_group_id: str = "",
        source_identity: Optional[Dict[str, Any]] = None,
        session_identity: Optional[Dict[str, Any]] = None,
        session_key: Optional[str] = None,
        popo_binding: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        text = str(message or "").strip()
        if not text:
            raise BlueprintServiceError("BAD_REQUEST", "message must be a non-empty string")
        if _is_blueprint_session_help_command(text):
            return _blueprint_session_direct_command_help_response(session_key or "")
        normalized_source = str(source or "ui").strip().lower() or "ui"
        source_identity = dict(source_identity or {})
        session_identity = dict(session_identity or {})
        if popo_user_id and not session_identity.get("popoUserId"):
            session_identity["popoUserId"] = popo_user_id
        if popo_session_id and not session_identity.get("popoSessionId"):
            session_identity["popoSessionId"] = popo_session_id
        if popo_group_id and not session_identity.get("popoGroupId"):
            session_identity["popoGroupId"] = popo_group_id
        popo_user_id = str(session_identity.get("popoUserId") or session_identity.get("sourceUserId") or "").strip()
        popo_session_id = str(session_identity.get("popoSessionId") or session_identity.get("sourceSessionId") or "").strip()
        popo_group_id = str(session_identity.get("popoGroupId") or session_identity.get("sourceGroupId") or "").strip()
        popo_reply_to = str(session_identity.get("popoReplyTo") or session_identity.get("replyTo") or "").strip()
        popo_session_type = str(session_identity.get("popoSessionType") or session_identity.get("sessionType") or "").strip()
        robot_app_key = str(source_identity.get("robotAppKey") or source_identity.get("robot_app_key") or "").strip()
        pool_key = ""
        structure_id = ""
        assigned_blueprint_id = ""
        blueprint_name = ""
        start_node_id = ""
        if normalized_source == "popo":
            binding = (
                dict(popo_binding)
                if isinstance(popo_binding, dict)
                else self._find_popo_blueprint_binding(project_dir, robot_app_key, session_identity=session_identity)
            )
            project_dir = Path(str(binding.get("projectDir") or project_dir))
            popo_entry = binding.get("popoEntry") if isinstance(binding.get("popoEntry"), dict) else {}
            robot_app_key = str(popo_entry.get("robot_app_key") or robot_app_key).strip()
            structure_id = str(binding["blueprintStructureId"])
            assigned_blueprint_id = str(binding["blueprintId"])
            blueprint_name = str(binding["blueprintName"])
            start_node_id = str(binding["startNodeId"])
            pool_key = self._popo_binding_pool_key(binding, robot_app_key)
        else:
            selected_blueprint_id = str(blueprint_id or DEFAULT_BLUEPRINT_ID)
            preflight = self._blueprint_session_preflight(project_dir, selected_blueprint_id)
            document = preflight["document"]
            structure_id = str(preflight["blueprintStructureId"])
            assigned_blueprint_id = str(document["id"])
            blueprint_name = str(document.get("name") or assigned_blueprint_id)
            start_node_id = str(preflight["startNodeId"])
        normalized_key = (
            blueprint_session_key_path_component(session_key)
            if session_key
            else (
                blueprint_main_session_key(assigned_blueprint_id)
                if normalized_source == "ui"
                else blueprint_popo_named_session_key(
                    blueprint_name=blueprint_name,
                    blueprint_id=assigned_blueprint_id,
                    popo_user_id=popo_user_id,
                    popo_session_id=popo_session_id,
                    popo_group_id=popo_group_id,
                )
            )
        )
        if normalized_source == "popo" and pool_key and not session_key:
            legacy_keys = [
                blueprint_session_key_for_pool(
                    pool_key=pool_key,
                    source=normalized_source,
                    popo_user_id=popo_user_id,
                    popo_session_id=popo_session_id,
                    popo_group_id=popo_group_id,
                ),
                blueprint_legacy_session_key_for_pool(
                    pool_key=pool_key,
                    source=normalized_source,
                    popo_user_id=popo_user_id,
                    popo_session_id=popo_session_id,
                    popo_group_id=popo_group_id,
                ),
            ]
            if self._load_blueprint_session(normalized_key) is None:
                legacy_session = next(
                    (
                        self._load_blueprint_session(legacy_key)
                        for legacy_key in legacy_keys
                        if legacy_key != normalized_key and self._load_blueprint_session(legacy_key) is not None
                    ),
                    None,
                )
                if legacy_session is not None:
                    migrated = self._maybe_upgrade_popo_session_key(legacy_session)
                    normalized_key = str(migrated.get("sessionKey") or normalized_key)
        if text == "/new":
            return self.clear_blueprint_session(
                normalized_key,
                reason=f"{normalized_source} requested /new",
                project_dir=project_dir,
                blueprint_id=assigned_blueprint_id,
            )
        if text == "/stop":
            return self.stop_blueprint_session_from_user_command(
                normalized_key,
                reason=f"{normalized_source} requested /stop",
                actor=normalized_source,
            )
        excel_log_expression = parse_excel_log_command(text)
        if excel_log_expression is not None:
            return self._excel_log_response_for_session(normalized_key, excel_log_expression)
        now = float(self.now())
        session_display_name = (
            blueprint_popo_session_display_name(
                popo_user_id=popo_user_id,
                popo_session_id=popo_session_id,
                popo_group_id=popo_group_id,
            )
            if normalized_source == "popo"
            else ""
        )
        loaded_session = self._load_blueprint_session(normalized_key)
        if loaded_session and loaded_session.get("superseded"):
            loaded_session = None
        session = loaded_session or {
            "sessionKey": normalized_key,
            "sessionDisplayName": session_display_name,
            "projectDir": str(validate_project_dir(project_dir)),
            "sessionScopeKey": pool_key,
            "robotAppKey": robot_app_key,
            "blueprintId": assigned_blueprint_id,
            "assignedBlueprintId": "",
            "blueprintName": blueprint_name,
            "blueprintStructureId": structure_id,
            "source": normalized_source,
            "popoUserId": str(popo_user_id or ""),
            "popoSessionId": str(popo_session_id or ""),
            "popoGroupId": str(popo_group_id or ""),
            "popoReplyTo": str(popo_reply_to or ""),
            "popoSessionType": str(popo_session_type or ""),
            "status": "idle",
            "activeRunId": "",
            "lastRunId": "",
            "contextSummary": "",
            "messageCount": 0,
            "createdAt": now,
            "lastTouchedAt": now,
            "deleted": False,
        }
        session.update(
            {
                "projectDir": str(validate_project_dir(project_dir)),
                "sessionScopeKey": str(session.get("sessionScopeKey") or pool_key),
                "robotAppKey": str(session.get("robotAppKey") or robot_app_key),
                "sessionDisplayName": str(session_display_name or session.get("sessionDisplayName") or ""),
                "blueprintId": str(session.get("blueprintId") or assigned_blueprint_id),
                "blueprintName": str(session.get("blueprintName") or blueprint_name),
                "blueprintStructureId": structure_id,
                "source": normalized_source,
                "popoUserId": str(popo_user_id or session.get("popoUserId") or ""),
                "popoSessionId": str(popo_session_id or session.get("popoSessionId") or ""),
                "popoGroupId": str(popo_group_id or session.get("popoGroupId") or ""),
                "popoReplyTo": str(popo_reply_to or session.get("popoReplyTo") or ""),
                "popoSessionType": str(popo_session_type or session.get("popoSessionType") or ""),
                "startNodeId": start_node_id,
                "deleted": False,
                "lastTouchedAt": now,
                "messageCount": int(session.get("messageCount") or 0) + 1,
            }
        )
        self._save_blueprint_session(session)
        self._append_blueprint_session_event(
            normalized_key,
            {
                "type": "user_message",
                "source": normalized_source,
                "message": text,
                "startNodeId": start_node_id,
                "replyTo": popo_reply_to,
                "sessionType": popo_session_type,
            },
        )

        active_run = self._active_run_for_session(normalized_key)
        if active_run is not None:
            if normalized_source == "popo":
                self._begin_popo_progress_card_for_session(active_run, session)
            queued = self._queue_blueprint_session_message(
                active_run,
                session,
                text,
                source=normalized_source,
                session_key=normalized_key,
            )
            return {
                "ok": True,
                "queued": True,
                "session": session,
                "sessionKey": normalized_key,
                "runId": active_run.run_id,
                "queue": queued,
            }

        preflight = self._blueprint_session_preflight(project_dir, assigned_blueprint_id)
        document = preflight["document"]
        graph = preflight["graph"]
        source_bindings = (
            {
                "popo": {
                    "robotAppKey": robot_app_key,
                    "robotName": str((preflight.get("popoEntry") or {}).get("robot_name") or ""),
                }
            }
            if normalized_source == "popo"
            else {"ui": {"blueprintId": assigned_blueprint_id}}
        )
        target_run, started = self._start_blueprint_session_instance(
            project_dir=project_dir,
            document=document,
            graph=graph,
            session_key=normalized_key,
            start_node_id=start_node_id,
            blueprint_structure_id=structure_id,
            robot_app_key=robot_app_key if normalized_source == "popo" else "",
            source_bindings=source_bindings,
        )
        if normalized_source == "popo":
            self._begin_popo_progress_card_for_session(target_run, session)
        queued = self._queue_blueprint_session_message(
            target_run,
            session,
            text,
            source=normalized_source,
            session_key=normalized_key,
        )
        self._append_blueprint_session_event(
            normalized_key,
            {
                "type": "run_started",
                "runId": target_run.run_id,
                "startNodeId": start_node_id,
            },
        )
        return {
            "ok": True,
            "queued": True,
            "session": session,
            "sessionKey": normalized_key,
            "runId": target_run.run_id,
            "run": target_run.summary(),
            "queue": queued,
            "startPending": bool(started.get("pending")),
            "validation": started.get("validation"),
            "startManifest": started.get("start_manifest", {}),
            "status": self._runtime_status_snapshot_or_starting(target_run, graph=target_run.graph),
        }

    def list_blueprint_runs(
        self,
        project_dir: Optional[Path] = None,
        blueprint_id: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        resolved_project = validate_project_dir(project_dir) if project_dir is not None else None
        normalized_blueprint_id = str(blueprint_id).strip() if blueprint_id is not None else None
        with self._lock:
            runs = list(self._runs.values())
        filtered = []
        for run in runs:
            if resolved_project is not None and run.project_dir != resolved_project:
                continue
            if normalized_blueprint_id and run.blueprint_id != normalized_blueprint_id:
                continue
            summary = run.summary()
            try:
                start_pending = _live_start_pending(run)
                timeout = (
                    LIVE_RUNTIME_CALL_STARTING_TIMEOUT_SECONDS
                    if start_pending
                    else LIVE_RUNTIME_STATUS_TIMEOUT_SECONDS
                )
                status = self._runtime_call(run, lambda: run.runtime.status_snapshot()["run"], timeout=timeout)
                summary["status"] = status["status"]
                summary["finalStatus"] = status.get("final_status")
                summary["endedAt"] = status.get("ended_at")
                if str(status.get("status") or "") in TERMINAL_RUN_STATUSES:
                    self._mark_blueprint_session_run_ended(run)
            except FutureTimeoutError:
                summary["status"] = "starting"
                summary["statusPending"] = True
                if start_pending:
                    summary["startPending"] = True
            filtered.append(summary)
        return sorted(filtered, key=lambda item: float(item.get("updatedAt", 0)), reverse=True)

    def start_blueprint_run(
        self,
        project_dir: Path,
        blueprint_id: str = DEFAULT_BLUEPRINT_ID,
        plan_data: Any = None,
        *,
        execution_mode: str = "status",
        session_key: str = "",
        start_node_id: str = "",
    ) -> Dict[str, Any]:
        execution_mode = str(execution_mode).strip().lower() or "status"
        if execution_mode not in {"status", "live"}:
            raise BlueprintServiceError(
                "UNSUPPORTED_EXECUTION_MODE",
                "desktop blueprint runtime supports executionMode='status' or 'live'",
                details={"supported": ["status", "live"]},
            )
        document = self.open_blueprint(project_dir, blueprint_id)
        config_issues = blueprint_common_config_issues(document)
        if config_issues:
            raise BlueprintServiceError(
                "BLUEPRINT_CONFIG_REQUIRED",
                "required blueprint common config paths must be set before start",
                details={
                    "blueprintId": str(document["id"]),
                    "issues": config_issues,
                },
            )
        document = document_with_common_config_paths(document)
        try:
            graph = graph_definition_from_dict(dict(document["graph"]))
            validate_desktop_blueprint_graph(graph, project_dir=validate_project_dir(project_dir))
        except Exception as exc:
            raise BlueprintServiceError(
                "INVALID_BLUEPRINT_GRAPH",
                str(exc),
                details={"blueprintId": str(document["id"])},
            ) from exc

        if not isinstance(plan_data, dict):
            raise BlueprintServiceError(
                "BAD_START_PLAN",
                "plan must be a complete start plan JSON object",
            )
        try:
            plan = TopAgentStartPlan.from_dict(plan_data)
        except Exception as exc:
            raise BlueprintServiceError(
                "BAD_START_PLAN",
                str(exc),
                details={"blueprintId": str(document["id"])},
            ) from exc
        preflight_validation = GuLiCodeTopAgentProfile().validate_start_plan(graph, plan).to_dict()
        preflight_validation.update(start_plan_validation_context(graph))
        invalid_runtime_starts = [
            node_id
            for node_id in plan.start_nodes
            if node_id not in set(blueprint_runtime_start_node_ids(graph))
        ]
        if invalid_runtime_starts:
            preflight_validation["ok"] = False
            errors = list(preflight_validation.get("errors") or [])
            errors.append(
                "start_nodes contains nodes that are not valid Blueprint runtime start Agent ids: "
                + ", ".join(invalid_runtime_starts)
            )
            preflight_validation["errors"] = errors
        if not preflight_validation.get("ok"):
            raise BlueprintServiceError(
                "START_PLAN_INVALID",
                "start plan failed validation",
                details={
                    "validation": preflight_validation,
                    "blueprintId": str(document["id"]),
                },
            )

        normalized_session_key = blueprint_session_key_path_component(session_key) if session_key else ""
        active_run = (
            self._active_run_for_session(normalized_session_key)
            if normalized_session_key
            else self._active_run_for_blueprint(validate_project_dir(project_dir), str(document["id"]))
        )
        if active_run is not None:
            with self._lock:
                active_run.updated_at = float(self.now())
            status = self._runtime_call(active_run, lambda: active_run.runtime.status_snapshot(graph=active_run.graph))
            run_summary = active_run.summary()
            run_status = status.get("run") if isinstance(status, dict) else None
            if isinstance(run_status, dict):
                run_summary["status"] = run_status.get("status")
                run_summary["finalStatus"] = run_status.get("final_status")
                run_summary["endedAt"] = run_status.get("ended_at")
            return {
                "ok": True,
                "alreadyActive": True,
                "runId": active_run.run_id,
                "run": run_summary,
                "validation": preflight_validation,
                "queuedMessages": [],
                "startManifest": {},
                "status": status,
            }
        with self._lock:
            run_id = self._generate_run_id_locked()

        diagnostics_dir = None
        if execution_mode == "live":
            backend, runtime, control, mcp, diagnostics_dir = self._async_loop.run(
                self._prepare_live_runtime(run_id, validate_project_dir(project_dir), document, graph)
            )
        else:
            backend = DesktopBlueprintNoopBackend()
            runtime = GraphRuntime(backend)
            control = GraphRuntimeControlPlane(
                runtime,
                graph,
                top_agent=GuLiCodeTopAgentProfile(),
                script_root=script_nodes_dir(validate_project_dir(project_dir)),
                resident_services=self.resident_service_manager(),
                excel_audit_context_provider=(
                    lambda **kwargs: self._excel_audit_context_for_run(run_id, **kwargs)
                ),
            )
            mcp = None
            runtime.agent_stream_run_id = run_id
            started = control.handle_request({"command": "run.start", "args": {"plan": plan.to_dict()}})
        if execution_mode != "live" and not started.get("ok"):
            if execution_mode == "live":
                if mcp is not None:
                    mcp.close()
                self._async_loop.run(runtime.close())
                stop = getattr(backend, "stop", None)
                if callable(stop):
                    self._async_loop.run(stop())
            raise BlueprintServiceError(
                "START_PLAN_INVALID",
                "start plan failed validation",
                details={
                    "validation": started,
                    "blueprintId": str(document["id"]),
                },
            )

        now = float(self.now())
        with self._lock:
            run = DesktopBlueprintRun(
                run_id=run_id,
                project_dir=validate_project_dir(project_dir),
                blueprint_id=str(document["id"]),
                document=document,
                graph=graph,
                runtime=runtime,
                control=control,
                execution_mode=execution_mode,
                created_at=now,
                updated_at=now,
                backend=backend,
                mcp=mcp,
                diagnostics_dir=diagnostics_dir,
                session_key=normalized_session_key,
                start_node_id=str(start_node_id or "").strip(),
            )
            self._attach_stream_notification(run)
            self._runs[run.run_id] = run
        if execution_mode == "live":
            start_future = self._async_loop.submit(self._complete_live_start(run, plan))
            with self._lock:
                run.live_start_future = start_future
            try:
                started = start_future.result(timeout=LIVE_START_RESULT_WAIT_SECONDS)
            except FutureTimeoutError:
                started = {
                    "ok": True,
                    "pending": True,
                    "validation": preflight_validation,
                    "queued_messages": [],
                    "start_manifest": {},
                }
                self._append_blueprint_diagnostics_event(
                    run,
                    "blueprint_live_start_pending",
                    validation=_compact_validation(preflight_validation),
                )
            except Exception as exc:
                with self._lock:
                    self._runs.pop(run.run_id, None)
                    run.live_start_error = str(exc)
                try:
                    self._async_loop.run(self._close_live_run(run), timeout=10)
                except Exception:
                    pass
                raise BlueprintServiceError(
                    "LIVE_AGENT_START_FAILED",
                    "failed to start live blueprint Agents",
                    details={"error": str(exc), "blueprintId": str(document["id"])},
                ) from exc
            if not started.get("ok"):
                with self._lock:
                    self._runs.pop(run.run_id, None)
                    run.live_start_result = started
                try:
                    self._async_loop.run(self._close_live_run(run), timeout=10)
                except Exception:
                    pass
                raise BlueprintServiceError(
                    "START_PLAN_INVALID",
                    "start plan failed validation",
                    details={
                        "validation": started,
                        "blueprintId": str(document["id"]),
                    },
                )
        status = self._runtime_status_snapshot_or_starting(run, graph=graph)
        if execution_mode != "live" or not started.get("pending"):
            self._append_blueprint_diagnostics_event(
                run,
                "blueprint_run_started",
                status=_compact_runtime_status(status),
                validation=_compact_validation(started.get("validation")),
                queuedMessageCount=len(started.get("queued_messages", []) or []),
            )
        return {
            "ok": True,
            "startPending": bool(started.get("pending")),
            "runId": run.run_id,
            "run": run.summary(),
            "validation": started.get("validation"),
            "queuedMessages": started.get("queued_messages", []),
            "startManifest": started.get("start_manifest", {}),
            "status": status,
        }

    def status_blueprint_run(self, run_id: str) -> Dict[str, Any]:
        run = self._get_run(run_id)
        status = self._runtime_status_snapshot_or_starting(run, graph=run.graph)
        run_status = status.get("run") if isinstance(status, dict) and isinstance(status.get("run"), dict) else {}
        if str(run_status.get("status") or "") in TERMINAL_RUN_STATUSES:
            self._mark_blueprint_session_run_ended(run)
        try:
            explanation = self._runtime_call(
                run,
                lambda: run.runtime.explain_status(graph=run.graph),
                timeout=(
                    LIVE_RUNTIME_CALL_STARTING_TIMEOUT_SECONDS
                    if _live_start_pending(run)
                    else LIVE_RUNTIME_STATUS_TIMEOUT_SECONDS
                ),
            )
        except FutureTimeoutError:
            explanation = {
                "summary": "Live blueprint runtime status is still pending.",
                "status": "starting",
                "statusPending": True,
            }
        with self._lock:
            current = self._runs.get(run.run_id)
            if current is not None:
                current.updated_at = float(self.now())
                run_summary = current.summary()
            else:
                run_summary = run.summary()
        return {
            "ok": True,
            "runId": run.run_id,
            "run": run_summary,
            "status": status,
            "explanation": explanation,
        }

    def recent_blueprint_events(self, run_id: str, *, limit: int = 20) -> Dict[str, Any]:
        run = self._get_run(run_id)
        status = self._runtime_status_snapshot_or_starting(
            run,
            graph=run.graph,
            recent_events_limit=limit,
        )
        with self._lock:
            current = self._runs.get(run.run_id)
            if current is not None:
                current.updated_at = float(self.now())
        return {
            "ok": True,
            "runId": run.run_id,
            "limit": limit,
            "events": status.get("recent_events", []),
        }

    def blueprint_run_diff(self, run_id: str) -> Dict[str, Any]:
        with self._lock:
            run = self._get_run(run_id)
            source = self._workspace_diff_source(run)
            if source is None:
                return {
                    "ok": True,
                    "runId": run.run_id,
                    "summary": {
                        "total": 0,
                        "accepted": 0,
                        "conflict": 0,
                        "rejected": 0,
                        "pending": 0,
                        "failed": 0,
                        "rolledBack": 0,
                        "restorable": 0,
                        "files": 0,
                        "textFiles": 0,
                        "binaryFiles": 0,
                        "additions": 0,
                        "deletions": 0,
                    },
                    "changesets": [],
                    "acceptedDiffs": [],
                    "binaryFiles": [],
                }
            manager, workspace_run = source
            diff = manager.blueprint_run_diff(workspace_run).to_dict()
            diff["ok"] = True
            diff["runId"] = run.run_id
            run.updated_at = float(self.now())
            return diff

    def blueprint_changeset_diff(self, run_id: str, changeset_id: str) -> Dict[str, Any]:
        if not changeset_id:
            raise BlueprintServiceError("BAD_REQUEST", "changesetId must be a non-empty string")
        with self._lock:
            run = self._get_run(run_id)
            source = self._workspace_diff_source(run)
            if source is None:
                raise BlueprintServiceError(
                    "CHANGESET_NOT_FOUND",
                    f"changeset was not found: {changeset_id}",
                    status=404,
                )
            manager, workspace_run = source
            try:
                detail = manager.blueprint_changeset_detail(workspace_run, changeset_id).to_dict()
            except FileNotFoundError as exc:
                message = str(exc)
                if "patch.diff" in message:
                    raise BlueprintServiceError(
                        "CHANGESET_PATCH_MISSING",
                        f"changeset patch.diff is missing: {changeset_id}",
                        status=404,
                    ) from exc
                raise BlueprintServiceError(
                    "CHANGESET_NOT_FOUND",
                    f"changeset was not found: {changeset_id}",
                    status=404,
                ) from exc
            detail["ok"] = True
            detail["runId"] = run.run_id
            run.updated_at = float(self.now())
            return detail

    def rollback_blueprint_changesets(
        self,
        run_id: str,
        to_changeset_id: str,
        *,
        reason: str = "",
    ) -> Dict[str, Any]:
        if not to_changeset_id:
            raise BlueprintServiceError("BAD_REQUEST", "toChangesetId must be a non-empty string")
        with self._lock:
            run = self._get_run(run_id)
            self._ensure_rollback_allowed(run)
            if run.run_id in self._pending_rollbacks:
                raise BlueprintServiceError(
                    "ROLLBACK_IN_PROGRESS",
                    "rollback already in progress for this blueprint run",
                )
            self._pending_rollbacks.add(run.run_id)
        try:
            with self._lock:
                run = self._get_run(run_id)
                source = self._workspace_diff_source(run)
                if source is None:
                    raise BlueprintServiceError(
                        "WORKSPACE_NOT_FOUND",
                        "blueprint workspace was not found",
                        status=404,
                    )
                manager, workspace_run = source
                try:
                    result = manager.rollback_changesets(
                        workspace_run,
                        to_changeset_id,
                        actor="desktop",
                        reason=reason,
                    ).to_dict()
                except FileNotFoundError as exc:
                    raise BlueprintServiceError(
                        "CHANGESET_NOT_FOUND",
                        str(exc),
                        status=404,
                    ) from exc
                run.updated_at = float(self.now())
                return {
                    "ok": bool(result.get("ok")),
                    "runId": run.run_id,
                    "rollback": result,
                }
        finally:
            with self._lock:
                self._pending_rollbacks.discard(run_id)

    def restore_blueprint_rollback(
        self,
        run_id: str,
        *,
        rollback_id: Optional[str] = None,
        reason: str = "",
    ) -> Dict[str, Any]:
        with self._lock:
            run = self._get_run(run_id)
            self._ensure_rollback_allowed(run)
            if run.run_id in self._pending_rollbacks:
                raise BlueprintServiceError(
                    "ROLLBACK_IN_PROGRESS",
                    "rollback already in progress for this blueprint run",
                )
            self._pending_rollbacks.add(run.run_id)
        try:
            with self._lock:
                run = self._get_run(run_id)
                source = self._workspace_diff_source(run)
                if source is None:
                    raise BlueprintServiceError(
                        "WORKSPACE_NOT_FOUND",
                        "blueprint workspace was not found",
                        status=404,
                    )
                manager, workspace_run = source
                try:
                    result = manager.restore_latest_rollback(
                        workspace_run,
                        rollback_id=rollback_id,
                        actor="desktop",
                        reason=reason,
                    ).to_dict()
                except FileNotFoundError as exc:
                    raise BlueprintServiceError(
                        "CHANGESET_NOT_FOUND",
                        str(exc),
                        status=404,
                    ) from exc
                run.updated_at = float(self.now())
                return {
                    "ok": bool(result.get("ok")),
                    "runId": run.run_id,
                    "restore": result,
                }
        finally:
            with self._lock:
                self._pending_rollbacks.discard(run_id)

    def _ensure_rollback_allowed(self, run: DesktopBlueprintRun) -> None:
        status = ""
        status_snapshot = getattr(run.runtime, "status_snapshot", None)
        if callable(status_snapshot):
            try:
                snapshot = self._runtime_call(run, lambda: status_snapshot(graph=run.graph))
            except TypeError:
                snapshot = self._runtime_call(run, status_snapshot)
            if isinstance(snapshot, dict):
                run_status = snapshot.get("run")
                if isinstance(run_status, dict):
                    status = str(run_status.get("status") or "")
        if not status:
            source = self._workspace_diff_source(run)
            if source is not None:
                _manager, workspace_run = source
                status = str(getattr(workspace_run, "status", "") or "")
        if status not in TERMINAL_RUN_STATUSES:
            raise BlueprintServiceError(
                "RUN_NOT_TERMINAL",
                "blueprint rollback requires a completed, cancelled, or failed run",
                details={"status": status or "unknown"},
            )

    async def _prepare_live_runtime(
        self,
        run_id: str,
        project_dir: Path,
        document: Dict[str, Any],
        graph: Any,
        *,
        session_slot: bool = False,
    ) -> tuple[Any, GraphRuntime, GraphRuntimeControlPlane, Optional[RunMCPRuntimeHandle], Path]:
        backend = None
        runtime = None
        rpc_server = None
        mcp = None

        async def cleanup() -> None:
            if mcp is not None:
                try:
                    mcp.close()
                except Exception:
                    pass
            if runtime is not None:
                try:
                    await runtime.close()
                except Exception:
                    pass
            elif rpc_server is not None:
                try:
                    rpc_server.close()
                except Exception:
                    pass
            if backend is not None:
                try:
                    await backend.stop()
                except Exception:
                    pass

        try:
            backend = await CLIWorkerBackend.create([], port=_free_tcp_port(), allow_empty=True)
            manager = DulwichWorkspaceManager.open_or_init(project_dir)
            workspace_run = manager.create_run(run_id=run_id, code_mode="project_reference")
            diagnostics_dir = _reset_blueprint_diagnostics_dir(workspace_run.shared_dir / "logs" / BLUEPRINT_DIAGNOSTICS_DIR)
            rpc_server = WorkspaceRPCServer(manager, workspace_run)
            rpc_server.start()
            runtime = GraphRuntime(
                backend,
                archive_manager=manager,
                archive_run=workspace_run,
                enforce_private_agent_context=True,
                private_context_manager=manager,
                private_context_run=workspace_run,
                private_context_rpc_server=rpc_server,
                skill_space=_desktop_skill_catalog_from_document(document, project_dir),
                message_journal_path=workspace_run.shared_dir / "logs" / "message_journal.jsonl",
            )
            runtime.agent_stream_run_id = run_id
            runtime.blueprint_session_idle_check_callback = (
                lambda run_id=run_id: self._schedule_blueprint_session_idle_check(run_id)
            )
            control = GraphRuntimeControlPlane(
                runtime,
                graph,
                top_agent=GuLiCodeTopAgentProfile(),
                script_root=script_nodes_dir(project_dir),
                resident_services=self.resident_service_manager(),
                excel_audit_context_provider=(
                    lambda **kwargs: self._excel_audit_context_for_run(run_id, **kwargs)
                ),
            )
            mcp = RunMCPRuntimeHandle(
                run_id=run_id,
                runtime=runtime,
                control=control,
                graph=graph,
                workspace_rpc_server=rpc_server,
                manager=manager,
                workspace_run=workspace_run,
                runtime_loop=self._async_loop,
                top_agent_node_id="desktop-blueprint-planning",
                top_agent_id="gulicode-desktop",
                close_run_callback=lambda **kwargs: self._end_live_run_from_mcp(run_id, **kwargs),
                terminate_session_callback=lambda **kwargs: self._terminate_blueprint_session_from_mcp(run_id, **kwargs),
                query_excel_history_callback=lambda **kwargs: self._query_excel_history_from_mcp(run_id, **kwargs),
            )
            start_node_id = document_start_node_id(document)
            popo_entry = document_popo_entry(document)
            if start_node_id and popo_entry.get("enabled") and not popo_entry_missing_fields(popo_entry):
                mcp.enable_session_history_tools(start_node_id=start_node_id, session_key="pending-popo-session")
            mcp.start()
            runtime.private_context_mcp_provider = mcp.provision_context_for_node
            runtime.agent_message_context_callback = mcp.refresh_message_context
            return backend, runtime, control, mcp, diagnostics_dir
        except BlueprintServiceError:
            await cleanup()
            raise
        except Exception as exc:
            await cleanup()
            raise BlueprintServiceError(
                "LIVE_AGENT_START_FAILED",
                "failed to start live blueprint Agents",
                details={"error": str(exc)},
            ) from exc

    async def _complete_live_start(
        self,
        run: DesktopBlueprintRun,
        plan: TopAgentStartPlan,
    ) -> Dict[str, Any]:
        try:
            started = await run.control.start_run(plan, prestart_all_agents=False)
            run.live_start_result = started
            run.updated_at = float(self.now())
            if not started.get("ok"):
                try:
                    run.runtime.end_run(
                        "fail",
                        reason="live blueprint start failed validation",
                        archive=False,
                    )
                except Exception:
                    pass
                self._append_blueprint_diagnostics_event(
                    run,
                    "blueprint_live_start_failed",
                    validation=_compact_validation(started.get("validation")),
                )
                return started
            run.runtime.start_tick_loop()
            status = run.runtime.status_snapshot(graph=run.graph)
            self._append_blueprint_diagnostics_event(
                run,
                "blueprint_run_started",
                status=_compact_runtime_status(status),
                validation=_compact_validation(started.get("validation")),
                queuedMessageCount=len(started.get("queued_messages", []) or []),
            )
            with run.stream_condition:
                run.stream_condition.notify_all()
            return started
        except Exception as exc:
            run.live_start_error = str(exc)
            run.updated_at = float(self.now())
            try:
                run.runtime.end_run(
                    "fail",
                    reason=f"live blueprint start failed: {exc}",
                    archive=False,
                )
            except Exception:
                pass
            self._append_blueprint_diagnostics_event(
                run,
                "blueprint_live_start_failed",
                error=str(exc),
            )
            with run.stream_condition:
                run.stream_condition.notify_all()
            raise

    async def _complete_live_session_start(self, run: DesktopBlueprintRun) -> Dict[str, Any]:
        try:
            run.runtime.configure_completion_tracking(run.graph)
            await run.runtime.prestart_agents(list(run.graph.agent_nodes.values()))
            run.runtime.start_tick_loop()
            run.live_start_result = {
                "ok": True,
                "validation": {"ok": True, "errors": [], "warnings": []},
                "queued_messages": [],
                "start_manifest": {},
            }
            run.updated_at = float(self.now())
            status = run.runtime.status_snapshot(graph=run.graph)
            self._append_blueprint_diagnostics_event(
                run,
                "blueprint_session_instance_started",
                status=_compact_runtime_status(status),
                queuedMessageCount=0,
            )
            with run.stream_condition:
                run.stream_condition.notify_all()
            return dict(run.live_start_result)
        except Exception as exc:
            run.live_start_error = str(exc)
            run.updated_at = float(self.now())
            try:
                run.runtime.end_run(
                    "fail",
                    reason=f"live blueprint session start failed: {exc}",
                    archive=False,
                )
            except Exception:
                pass
            self._append_blueprint_diagnostics_event(
                run,
                "blueprint_session_instance_start_failed",
                error=str(exc),
            )
            with run.stream_condition:
                run.stream_condition.notify_all()
            raise

    def end_blueprint_run(
        self,
        run_id: str,
        action: str,
        *,
        reason: str = "",
    ) -> Dict[str, Any]:
        action = str(action).strip().lower()
        if action not in {"complete", "cancel", "fail", "pause"}:
            raise BlueprintServiceError(
                "UNSUPPORTED_RUN_ACTION",
                f"unsupported run end action: {action!r}",
                details={"supported": ["complete", "cancel", "fail", "pause"]},
            )
        with self._lock:
            run = self._get_run(run_id)
        run_status = self._runtime_call(run, lambda: run.runtime.status_snapshot()["run"])
        already_ended = run_status["status"] in {
            "completed",
            "cancelled",
            "failed",
        }
        if already_ended:
            end_result: Dict[str, Any] = {
                "ok": True,
                "action": action,
                "run_status": run_status["status"],
                "final_status": run_status.get("final_status"),
                "reason": reason,
                "summary": {},
                "archived": False,
            }
        else:
            end_result = self._runtime_call(
                run,
                lambda: run.runtime.end_run(action, reason=reason, archive=False).to_dict(),
            )
        with self._lock:
            run.updated_at = float(self.now())
        status = self._runtime_call(run, lambda: run.runtime.status_snapshot(graph=run.graph))
        response: Dict[str, Any] = {
            "ok": True,
            "runId": run.run_id,
            "run": run.summary(),
            "end": end_result,
            "status": status,
        }
        if already_ended:
            response["alreadyEnded"] = True
        run_status_after_end = status.get("run") if isinstance(status, dict) and isinstance(status.get("run"), dict) else {}
        terminal_status = str(run_status_after_end.get("status") or "")
        if terminal_status in TERMINAL_RUN_STATUSES:
            self._finalize_popo_progress_for_run_best_effort(
                run,
                content=self._popo_progress_terminal_content(terminal_status, action=action),
            )
            self._mark_blueprint_session_run_ended(run)
        if run.execution_mode == "live" and not already_ended:
            self._async_loop.run(self._close_live_run(run))
        with run.stream_condition:
            run.stream_condition.notify_all()
        return response

    def agent_info(self, node_id: str, *, run_id: Optional[str] = None) -> Dict[str, Any]:
        if not node_id:
            raise BlueprintServiceError("BAD_REQUEST", "nodeId must be a non-empty string")
        if not run_id:
            return {
                "ok": True,
                "nodeId": node_id,
                "running": False,
                "runtime": None,
                "streamEvents": [],
                "messageJournal": [],
                "frameworkApiCalls": [],
            }
        with self._lock:
            run = self._get_run(run_id)
            if node_id not in run.graph.agent_nodes:
                raise BlueprintServiceError(
                    "NODE_NOT_FOUND",
                    f"agent node was not found: {node_id}",
                    status=404,
                )
            node = run.graph.agent_nodes[node_id]
        status = self._runtime_call(run, lambda: run.runtime.status_snapshot(graph=run.graph))
        runtime_agent = status["agents"].get(node_id) or {}
        agent_id = str(runtime_agent.get("agent_id") or node.runtime_agent_id)
        return {
            "ok": True,
            "runId": run.run_id,
            "nodeId": node_id,
            "running": True,
            "node": node.to_dict(),
            "runtime": runtime_agent,
            "queue": status["queues"]["by_agent"].get(node_id, []),
            "streamEvents": self._runtime_call(
                run,
                lambda: run.runtime.agent_stream_events_after(node_id=node_id),
            ),
            "messageJournal": self._runtime_call(
                run,
                lambda: _message_journal_for_node(run.runtime, node_id, limit=200),
            ),
            "frameworkApiCalls": self._runtime_call(
                run,
                lambda: _framework_api_calls_for_node(run, node_id, agent_id, limit=200),
            ),
        }

    def queue_agent_message(
        self,
        run_id: str,
        node_id: str,
        text: str,
        *,
        mode: str = "default",
        merge_key: Optional[str] = None,
        merge_append_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not node_id:
            raise BlueprintServiceError("BAD_REQUEST", "nodeId must be a non-empty string")
        if not text.strip():
            raise BlueprintServiceError("BAD_REQUEST", "text must be a non-empty string")
        normalized_mode = str(mode or "default").strip().lower()
        if normalized_mode not in {"default", "top"}:
            raise BlueprintServiceError(
                "BAD_REQUEST",
                "mode must be 'default' or 'top'",
                details={"supported": ["default", "top"]},
            )
        with self._lock:
            run = self._get_run(run_id)
            if run.execution_mode != "live":
                raise BlueprintServiceError(
                    "RUN_NOT_LIVE",
                    "agent messages can only be sent to a live blueprint run",
                )
            node = run.graph.agent_nodes.get(node_id)
            if node is None:
                raise BlueprintServiceError(
                    "NODE_NOT_FOUND",
                    f"agent node was not found: {node_id}",
                    status=404,
                )
        result = self._async_loop.run(
            self._queue_agent_message_for_runtime(
                run,
                node,
                text.strip(),
                queue_mode=normalized_mode,
                merge_key=merge_key,
                merge_append_text=merge_append_text,
            )
        )
        with self._lock:
            run.updated_at = float(self.now())
        return {
            "ok": True,
            "runId": run.run_id,
            "nodeId": node_id,
            "mode": normalized_mode,
            "result": result,
            "status": self._runtime_call(run, lambda: run.runtime.status_snapshot(graph=run.graph)),
        }

    async def _queue_agent_message_for_runtime(
        self,
        run: DesktopBlueprintRun,
        node: Any,
        text: str,
        *,
        queue_mode: str,
        merge_key: Optional[str] = None,
        merge_append_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        await run.runtime.ensure_agent(node)
        route_id = f"route-{secrets.token_hex(6)}"
        downstream = run.runtime.active_framework_connections(run.graph, node.node_id)
        direct_scripts = run.runtime.active_direct_script_connections(run.graph, node.node_id)
        batch = None
        if downstream or direct_scripts:
            batch = run.runtime._create_outgoing_batch_from_graph_sync(
                run.graph,
                node.node_id,
                required_target_node_ids=downstream,
                required_script_node_ids=direct_scripts,
                route_id=route_id,
            )
        body = inject_framework_context(
            {"prompt": text, "type": "user_message"},
            ordinary_agent_framework_context(
                run.graph,
                node.node_id,
                batch=batch,
                runtime=run.runtime,
                route_id=route_id,
            ),
        )
        return run.runtime.queue_agent_message(
            node,
            body,
            queue_mode=queue_mode,
            route_id=route_id,
            merge_key=merge_key,
            merge_append_text=merge_append_text,
        ).to_dict()

    async def _queue_framework_notification_for_runtime(
        self,
        run: DesktopBlueprintRun,
        node: Any,
        body: Dict[str, Any],
        *,
        queue_mode: str,
    ) -> Dict[str, Any]:
        await run.runtime.ensure_agent(node)
        route_id = f"route-{secrets.token_hex(6)}"
        context = ordinary_agent_framework_context(
            run.graph,
            node.node_id,
            batch=None,
            runtime=run.runtime,
            route_id=route_id,
        )
        envelope = context.setdefault("message_envelope", {})
        if isinstance(envelope, dict):
            envelope["required_script_calls"] = []
            envelope["required_outgoing_targets"] = []
            envelope["remaining_targets"] = []
            for key in ("reply_required", "reply_visibility", "framework_message_kind"):
                if key in body:
                    envelope[key] = body[key]
        message_body = inject_framework_context(dict(body), context)
        return run.runtime.queue_agent_message(
            node,
            message_body,
            queue_mode=queue_mode,
            route_id=route_id,
            message_id=f"framework-notification-{node.node_id}-{secrets.token_hex(4)}",
        ).to_dict()

    def agent_stream_token(
        self,
        run_id: str,
        *,
        base_url: str = "",
        cursor: Any = None,
    ) -> Dict[str, Any]:
        with self._lock:
            run = self._get_run(run_id)
            if run.execution_mode != "live":
                raise BlueprintServiceError(
                    "RUN_NOT_LIVE",
                    "agent stream is only available for live blueprint runs",
                )
            token = secrets.token_urlsafe(24)
            self._stream_tokens[token] = {
                "run_id": run.run_id,
                "expires_at": float(self.now()) + 60.0,
            }
        parsed = urlparse(base_url)
        host = parsed.netloc
        scheme = "wss" if parsed.scheme == "https" else "ws"
        ws_url = f"{scheme}://{host}/agent-stream?streamToken={token}&cursor={int(cursor or 0)}"
        return {"ok": True, "runId": run_id, "streamToken": token, "wsUrl": ws_url}

    def ensure_blueprint_planning_context(
        self,
        project_dir: Path,
        blueprint_id: str = DEFAULT_BLUEPRINT_ID,
        desktop_session_id: str = "",
    ) -> Dict[str, Any]:
        desktop_session_id = str(desktop_session_id).strip()
        if not desktop_session_id:
            raise BlueprintServiceError("BAD_REQUEST", "desktopSessionId must be a non-empty string")
        project_dir = validate_project_dir(project_dir)
        blueprint_id = validate_blueprint_id(blueprint_id)
        session_id = self._planning_session_id(project_dir, blueprint_id, desktop_session_id)
        with self._lock:
            existing = self._planning_sessions.get(session_id)
        if existing is not None and existing.status not in {"ended", "failed"}:
            return self._blueprint_planning_snapshot(existing)

        document = self.open_blueprint(project_dir, blueprint_id)
        try:
            graph = graph_definition_from_dict(dict(document["graph"]))
            validate_desktop_blueprint_graph(graph, project_dir=project_dir)
        except Exception as exc:
            raise BlueprintServiceError(
                "INVALID_BLUEPRINT_GRAPH",
                str(exc),
                details={"blueprintId": str(document["id"])},
            ) from exc

        runtime, control, mcp, mcp_context, prepared = self._async_loop.run(
            self._start_blueprint_planning_context(session_id, project_dir, document, graph),
            timeout=60,
        )
        now = float(self.now())
        session = DesktopBlueprintPlanningSession(
            session_id=session_id,
            desktop_session_id=desktop_session_id,
            project_dir=project_dir,
            blueprint_id=str(document["id"]),
            document=document,
            graph=graph,
            runtime=runtime,
            control=control,
            created_at=now,
            updated_at=now,
            framework_system=self._blueprint_planning_system(control, graph),
            mcp_context=mcp_context,
            mcp=mcp,
        )
        with self._lock:
            self._planning_sessions[session_id] = session
        self._append_blueprint_planning_event(
            session,
            "context_ready",
            summary="Blueprint planning context is ready",
            details={"prepared": prepared},
        )
        return self._blueprint_planning_snapshot(session)

    def answer_blueprint_planning_question(
        self,
        session_id: str,
        question_id: str,
        answers: Any,
        *,
        rejected: bool = False,
        reason: str = "",
    ) -> Dict[str, Any]:
        session = self._get_blueprint_planning_session(session_id)
        with session.condition:
            question = session.pending_question
            if question is None or question.question_id != question_id or question.status != "pending":
                raise BlueprintServiceError(
                    "BLUEPRINT_PLANNING_QUESTION_NOT_FOUND",
                    "pending blueprint planning question was not found",
                    status=404,
                )
            question.status = "rejected" if rejected else "answered"
            question.answers = None if rejected else answers
            question.reason = str(reason or "")
            question.answered_at = float(self.now())
            session.pending_question = None
            session.updated_at = float(self.now())
            session.condition.notify_all()
        self._append_blueprint_planning_event(
            session,
            "question_rejected" if rejected else "question_answered",
            questionId=question_id,
            answers=None if rejected else answers,
            reason=str(reason or ""),
        )
        return self._blueprint_planning_snapshot(session)

    def reject_blueprint_planning_plan(self, session_id: str, *, reason: str = "") -> Dict[str, Any]:
        session = self._get_blueprint_planning_session(session_id)
        with session.condition:
            pending = session.pending_plan
            if pending is None:
                raise BlueprintServiceError("BLUEPRINT_PLANNING_PLAN_NOT_FOUND", "no staged blueprint planning plan is pending")
            plan_id = str(pending.get("planId", ""))
            session.pending_plan = None
            session.updated_at = float(self.now())
        self._append_blueprint_planning_event(
            session,
            "plan_rejected",
            planId=plan_id,
            reason=str(reason or ""),
        )
        return self._blueprint_planning_snapshot(session)

    def mark_blueprint_planning_plan_started(
        self,
        session_id: str,
        run_id: str,
        *,
        started: Any = None,
    ) -> Dict[str, Any]:
        session = self._get_blueprint_planning_session(session_id)
        run_id = str(run_id or "").strip()
        if not run_id:
            raise BlueprintServiceError("BAD_REQUEST", "runId must be a non-empty string")
        with session.condition:
            pending = session.pending_plan
            if pending is None:
                raise BlueprintServiceError("BLUEPRINT_PLANNING_PLAN_NOT_FOUND", "no staged blueprint planning plan is pending")
            plan_id = str(pending.get("planId", ""))
            session.pending_plan = None
            session.active_run_id = run_id
            session.updated_at = float(self.now())
        self._append_blueprint_planning_event(
            session,
            "run_started",
            runId=run_id,
            planId=plan_id,
            started=started if isinstance(started, dict) else None,
        )
        try:
            run = self._get_run(run_id)
        except Exception:
            run = None
        if run is not None:
            status_source = self._planning_status_source_summary(
                session,
                active_run=run if run.execution_mode == "live" else None,
                planning_status=self._planning_runtime_status(session),
                active_status=self._run_runtime_status(run),
            )
            self._append_blueprint_diagnostics_event(
                run,
                "planning_active_run_linked",
                planningSessionId=session.session_id,
                planId=plan_id,
                statusSource=status_source,
                started=_compact_start_response(started),
            )
        return self._blueprint_planning_snapshot(session)

    def blueprint_planning_status(self, session_id: str) -> Dict[str, Any]:
        return self._blueprint_planning_snapshot(self._get_blueprint_planning_session(session_id))

    def end_blueprint_planning_session(self, session_id: str, *, reason: str = "") -> Dict[str, Any]:
        session = self._get_blueprint_planning_session(session_id)
        should_close = False
        with session.condition:
            if session.status not in {"ended", "failed"}:
                session.status = "ending"
                session.updated_at = float(self.now())
                should_close = True
            if session.pending_question is not None and session.pending_question.status == "pending":
                session.pending_question.status = "rejected"
                session.pending_question.reason = str(reason or "session ended")
                session.pending_question.answered_at = float(self.now())
                session.pending_question = None
                session.condition.notify_all()
        if should_close:
            try:
                self._async_loop.run(self._close_blueprint_planning_context(session), timeout=10)
            finally:
                with session.condition:
                    session.status = "ended"
                    session.updated_at = float(self.now())
                    session.condition.notify_all()
                self._append_blueprint_planning_event(
                    session,
                    "session_ended",
                    reason=str(reason or ""),
                )
        return self._blueprint_planning_snapshot(session)

    def accept_stream_token(self, token: str) -> str:
        with self._lock:
            data = self._stream_tokens.pop(str(token), None)
            if not data or float(data.get("expires_at", 0)) < float(self.now()):
                raise BlueprintServiceError("UNAUTHORIZED", "invalid or expired stream token", status=401)
            return str(data["run_id"])

    def stream_agent_events(
        self,
        run_id: str,
        *,
        cursor: int = 0,
        send: Callable[[Dict[str, Any]], None],
    ) -> None:
        run = self._get_run(run_id)
        next_cursor = int(cursor or 0)
        while True:
            try:
                events = self._runtime_call(
                    run,
                    lambda: run.runtime.agent_stream_events_after(next_cursor),
                    timeout=LIVE_AGENT_STREAM_READ_TIMEOUT_SECONDS,
                )
            except FutureTimeoutError:
                events = []
            for event in events:
                send(event)
                next_cursor = max(next_cursor, int(event.get("seq", next_cursor)))
            try:
                status = self._runtime_call(
                    run,
                    lambda: run.runtime.status_snapshot()["run"],
                    timeout=LIVE_AGENT_STREAM_READ_TIMEOUT_SECONDS,
                )
            except FutureTimeoutError:
                status = {"status": "running", "statusPending": True}
            if status.get("status") in {"completed", "cancelled", "failed"} and not events:
                return
            with run.stream_condition:
                run.stream_condition.wait(timeout=15.0)

    def _attach_stream_notification(self, run: DesktopBlueprintRun) -> None:
        def notify(event: Dict[str, Any]) -> None:
            self._update_popo_progress_from_stream_event(run.run_id, event)
            with run.stream_condition:
                run.stream_condition.notify_all()

        def forward_popo_reply(utterance: Dict[str, Any]) -> None:
            try:
                self._forward_framework_popo_reply(run.run_id, utterance)
            finally:
                with run.stream_condition:
                    run.stream_condition.notify_all()

        run.runtime.agent_stream_event_callback = notify
        run.runtime.agent_reply_callback = forward_popo_reply

    @staticmethod
    def _looks_like_final_popo_reply(text: str) -> bool:
        compact = str(text or "").strip()
        if not compact:
            return False
        final_markers = (
            "请确认",
            "是否提交",
            "待提交",
            "完成报告",
            "处理完成",
            "已完成",
            "已处理",
            "变更:",
            "变更：",
            "校验:",
            "校验：",
            "占表:",
            "占表：",
        )
        return any(marker in compact for marker in final_markers)

    @classmethod
    def _framework_popo_reply_is_temporary(cls, utterance: Dict[str, Any], text: str) -> bool:
        reply_visibility = str(utterance.get("reply_visibility") or "").strip().lower()
        if reply_visibility != "session_event":
            return False
        if cls._looks_like_final_popo_reply(text):
            return False
        return True

    def _forward_framework_popo_reply(self, run_id: str, utterance: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(utterance, dict):
            return None
        text = str(utterance.get("said") or "").strip()
        if not text:
            return None
        message_id = str(utterance.get("message_id") or "").strip()
        reply_required = utterance.get("reply_required")
        reply_visibility = str(utterance.get("reply_visibility") or "").strip().lower()
        framework_message_kind = str(utterance.get("framework_message_kind") or "").strip().lower()
        if (
            reply_required is False
            or reply_visibility == "framework_internal"
            or framework_message_kind in {
                "blueprint_script_call_reminder",
                "framework_outgoing_targets_reminder",
            }
        ):
            return None
        if message_id.startswith("summary-msg-"):
            return None
        if message_id.startswith("script-call-reminder-") or message_id.startswith("outgoing-targets-reminder-"):
            return None
        if "framework_summary_request" in text or "idle_task_status_missing" in text:
            return None
        agent_node_id = str(utterance.get("node_id") or "").strip()
        agent_id = str(utterance.get("agent_id") or "").strip()
        with self._lock:
            run = self._runs.get(str(run_id))
            if run is None:
                return None
            session_key = str(run.session_key or run.bound_session_key or getattr(run.runtime, "popo_reply_session_key", "") or "").strip()
            start_node_id = str(run.start_node_id or document_start_node_id(run.document))
            robot_app_key = str(run.robot_app_key or "").strip()
            if not session_key or not robot_app_key or agent_node_id != start_node_id:
                return None
            dedupe_key = f"{message_id}\n{agent_node_id}\n{text}" if message_id else f"{agent_node_id}\n{text}"
            if dedupe_key in run.popo_framework_reply_keys:
                return None
            run.popo_framework_reply_keys.add(dedupe_key)
        if self._framework_popo_reply_is_temporary(utterance, text):
            result = self._append_popo_progress_temporary_reply(run_id, text)
            event: Dict[str, Any] = {
                "type": "agent_reply",
                "source": "framework",
                "content": text,
                "runId": run_id,
                "agentNodeId": agent_node_id,
                "agentId": agent_id,
                "messageId": message_id,
                "temporary": True,
            }
            if result is not None:
                event["transport"] = str(result.get("transport") or "streaming_card_progress")
                fallback_reason = str(result.get("fallbackReason") or "").strip()
                if fallback_reason:
                    event["fallbackReason"] = fallback_reason
            self._append_blueprint_session_event(session_key, event)
            self._auto_complete_framework_popo_reply_task_status(
                run_id,
                agent_node_id=agent_node_id,
                agent_id=agent_id,
                message_id=message_id,
            )
            return result or {
                "ok": True,
                "sent": False,
                "transport": "streaming_card_progress",
                "temporary": True,
            }
        try:
            result = self._reply_popo_user_from_framework(
                run_id,
                content=text,
                session_key=session_key,
                agent_node_id=agent_node_id,
                agent_id=agent_id,
                message_id=message_id,
            )
        except Exception:
            with self._lock:
                run = self._runs.get(str(run_id))
                if run is not None:
                    run.popo_framework_reply_keys.discard(dedupe_key)
            log.exception("failed to forward framework POPO reply")
            return None
        self._auto_complete_framework_popo_reply_task_status(
            run_id,
            agent_node_id=agent_node_id,
            agent_id=agent_id,
            message_id=message_id,
        )
        return result

    def _runtime_call(
        self,
        run: DesktopBlueprintRun,
        fn: Callable[[], Any],
        *,
        timeout: Optional[float] = None,
    ) -> Any:
        if run.execution_mode == "live":
            return self._async_loop.call(fn, timeout=timeout)
        return fn()

    def _runtime_status_snapshot_or_starting(
        self,
        run: DesktopBlueprintRun,
        *,
        graph: Any = None,
        recent_events_limit: int = 20,
    ) -> Dict[str, Any]:
        try:
            timeout = (
                LIVE_RUNTIME_CALL_STARTING_TIMEOUT_SECONDS
                if _live_start_pending(run)
                else LIVE_RUNTIME_STATUS_TIMEOUT_SECONDS
            )
            return self._runtime_call(
                run,
                lambda: run.runtime.status_snapshot(
                    graph=graph,
                    recent_events_limit=recent_events_limit,
                ),
                timeout=timeout,
            )
        except FutureTimeoutError:
            return _starting_runtime_status(status_pending=True)

    def _workspace_diff_source(self, run: DesktopBlueprintRun) -> Optional[tuple[DulwichWorkspaceManager, Any]]:
        manager = getattr(run.runtime, "archive_manager", None) or getattr(run.runtime, "private_context_manager", None)
        workspace_run = getattr(run.runtime, "archive_run", None) or getattr(run.runtime, "private_context_run", None)
        if not isinstance(manager, DulwichWorkspaceManager) or workspace_run is None:
            return None
        run_path = Path(getattr(workspace_run, "path", ""))
        if not run_path.is_dir():
            open_run_any = getattr(manager, "open_run_any", None)
            if callable(open_run_any):
                try:
                    workspace_run = open_run_any(getattr(workspace_run, "run_id", run.run_id))
                except FileNotFoundError:
                    return None
                if getattr(run.runtime, "archive_run", None) is not None:
                    run.runtime.archive_run = workspace_run
                if getattr(run.runtime, "private_context_run", None) is not None:
                    run.runtime.private_context_run = workspace_run
        return manager, workspace_run

    async def _start_blueprint_planning_context(
        self,
        session_id: str,
        project_dir: Path,
        document: Dict[str, Any],
        graph: Any,
    ) -> tuple[GraphRuntime, GraphRuntimeControlPlane, RunMCPRuntimeHandle, Dict[str, Any], Dict[str, Any]]:
        runtime = None
        rpc_server = None
        mcp = None

        async def cleanup() -> None:
            if mcp is not None:
                try:
                    mcp.close()
                except Exception:
                    pass
            if runtime is not None:
                try:
                    await runtime.close()
                except Exception:
                    pass
            elif rpc_server is not None:
                try:
                    rpc_server.close()
                except Exception:
                    pass

        try:
            manager = DulwichWorkspaceManager.open_or_init(project_dir)
            workspace_run_id = f"{session_id}-ctx-{uuid.uuid4().hex[:8]}"
            workspace_run = manager.create_run(run_id=workspace_run_id, code_mode="project_reference")
            rpc_server = WorkspaceRPCServer(manager, workspace_run)
            rpc_server.start()
            runtime = GraphRuntime(
                DesktopBlueprintNoopBackend(),
                enforce_private_agent_context=True,
                private_context_manager=manager,
                private_context_run=workspace_run,
                private_context_rpc_server=rpc_server,
                skill_space=_desktop_skill_catalog_from_document(document, project_dir),
                message_journal_path=workspace_run.shared_dir / "logs" / "message_journal.jsonl",
            )
            runtime.agent_stream_run_id = session_id
            control = GraphRuntimeControlPlane(
                runtime,
                graph,
                top_agent=GuLiCodeTopAgentProfile(),
                script_root=script_nodes_dir(project_dir),
                resident_services=self.resident_service_manager(),
                excel_audit_context_provider=(
                    lambda **kwargs: self._excel_audit_context_for_run(session_id, **kwargs)
                ),
            )
            mcp = RunMCPRuntimeHandle(
                run_id=session_id,
                runtime=runtime,
                control=control,
                graph=graph,
                workspace_rpc_server=rpc_server,
                manager=manager,
                workspace_run=workspace_run,
                runtime_loop=self._async_loop,
                top_agent_node_id="desktop-blueprint-planning",
                top_agent_id="gulicode-desktop",
                request_user_input_callback=lambda questions: self._handle_top_agent_request_user_input(
                    session_id,
                    questions,
                ),
                stage_start_plan_callback=lambda plan, markdown: self._handle_top_agent_stage_start_plan(
                    session_id,
                    plan,
                    markdown,
                ),
                control_command_callback=lambda **kwargs: self._handle_planning_control_command(
                    session_id,
                    **kwargs,
                ),
                control_call_observer=lambda **kwargs: self._record_planning_mcp_control_call(
                    session_id,
                    **kwargs,
                ),
                control_allowed_tools=TOP_AGENT_PLANNING_CONTROL_TOOLS,
            )
            mcp.start()
            mcp_context = mcp.provision_control_context(
                agent_node_id="desktop-blueprint-planning",
                agent_id="gulicode-desktop",
                permissions=control.top_agent.allowed_run_permissions,
                allowed_tools=TOP_AGENT_PLANNING_CONTROL_TOOLS,
            )
            prepared = {
                "organization": graph.agent_organization_summary(),
                "mcp": {
                    "server": mcp_context.get("server_name"),
                    "url": mcp_context.get("url"),
                    "tools": mcp_context.get("tools", []),
                },
                "workspaceRunId": workspace_run.run_id,
            }
            return runtime, control, mcp, mcp_context, prepared
        except BlueprintServiceError:
            await cleanup()
            raise
        except Exception as exc:
            await cleanup()
            raise BlueprintServiceError(
                "BLUEPRINT_PLANNING_CONTEXT_FAILED",
                "failed to prepare desktop blueprint planning context",
                details={"error": str(exc)},
            ) from exc

    def _handle_planning_control_command(
        self,
        session_id: str,
        *,
        scope: Any,
        tool_name: str,
        command: str,
        args: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if str(command) not in PLANNING_STATUS_SOURCE_COMMANDS:
            return None
        session = self._get_blueprint_planning_session(session_id)
        active_run = self._active_live_run_for_planning_session(session)
        planning_status = self._planning_runtime_status(session)
        active_status = self._run_runtime_status(active_run) if active_run is not None else None
        status_source = self._planning_status_source_summary(
            session,
            active_run=active_run,
            planning_status=planning_status,
            active_status=active_status,
        )
        if active_run is not None:
            result = self._planning_control_response_for_run(active_run, command, args)
            self._record_planning_status_mismatch(
                active_run,
                status_source=status_source,
                planning_status=planning_status,
                active_status=active_status,
            )
        else:
            result = session.control.handle_request({"command": command, "args": args})
        payload = dict(result)
        payload["status_source"] = status_source
        payload["source_run_id"] = active_run.run_id if active_run is not None else None
        payload["planning_session_id"] = session.session_id
        return payload

    def _record_planning_mcp_control_call(
        self,
        session_id: str,
        *,
        scope: Any,
        tool_name: str,
        command: str,
        args: Dict[str, Any],
        result: Optional[Dict[str, Any]],
        error: Optional[str],
    ) -> None:
        try:
            session = self._get_blueprint_planning_session(session_id)
        except BlueprintServiceError:
            return
        source_run_id = None
        status_source = None
        if isinstance(result, dict):
            source_run_id = result.get("source_run_id")
            status_source = result.get("status_source")
        run = None
        if source_run_id:
            try:
                run = self._get_run(str(source_run_id))
            except Exception:
                run = None
        if run is None:
            run = self._active_live_run_for_planning_session(session)
        if run is None:
            return
        self._append_blueprint_diagnostics_event(
            run,
            "planning_mcp_control_call",
            planningSessionId=session.session_id,
            toolName=str(tool_name),
            command=str(command),
            args=dict(args or {}),
            statusSource=status_source,
            output=_compact_control_result(result),
            error=error,
        )

    def _handle_top_agent_request_user_input(
        self,
        session_id: str,
        questions: list[dict[str, Any]],
    ) -> Dict[str, Any]:
        session = self._get_blueprint_planning_session(session_id)
        clean_questions = [
            dict(item)
            for item in (questions or [])
            if isinstance(item, dict)
        ]
        if not clean_questions:
            clean_questions = [{"id": "question", "question": "Please provide the missing information."}]
        question = DesktopBlueprintPlanningQuestion(
            question_id=f"question-{uuid.uuid4().hex[:12]}",
            questions=clean_questions,
            created_at=float(self.now()),
        )
        with session.condition:
            if session.pending_question is not None and session.pending_question.status == "pending":
                return {
                    "ok": False,
                    "status": "rejected",
                    "error": "another Top Agent question is already pending",
                }
            session.pending_question = question
            session.updated_at = float(self.now())
            session.condition.notify_all()
        self._append_blueprint_planning_event(
            session,
            "question_requested",
            question=question.to_dict(),
        )
        with session.condition:
            while (
                session.pending_question is question
                and question.status == "pending"
                and session.status not in {"ended", "failed"}
            ):
                session.condition.wait(timeout=15.0)
            if question.status == "answered":
                return {
                    "ok": True,
                    "questionId": question.question_id,
                    "answers": question.answers,
                }
            return {
                "ok": False,
                "questionId": question.question_id,
                "status": "rejected",
                "reason": question.reason or "question was rejected",
            }

    def _handle_top_agent_stage_start_plan(
        self,
        session_id: str,
        plan_data: dict[str, Any],
        plan_markdown: str,
    ) -> Dict[str, Any]:
        session = self._get_blueprint_planning_session(session_id)
        try:
            plan = TopAgentStartPlan.from_dict(dict(plan_data or {}))
            validation = session.control.top_agent.validate_start_plan(session.graph, plan).to_dict()
            validation.update(start_plan_validation_context(session.graph))
            invalid_runtime_starts = [
                node_id
                for node_id in plan.start_nodes
                if node_id not in set(blueprint_runtime_start_node_ids(session.graph))
            ]
            if invalid_runtime_starts:
                validation["ok"] = False
                errors = list(validation.get("errors") or [])
                errors.append(
                    "start_nodes contains nodes that are not valid Blueprint runtime start Agent ids: "
                    + ", ".join(invalid_runtime_starts)
                )
                validation["errors"] = errors
        except Exception as exc:
            validation = {
                "ok": False,
                "errors": [str(exc)],
                "warnings": [],
            }
            plan = None

        pending: Optional[Dict[str, Any]] = None
        if validation.get("ok") and plan is not None:
            pending = {
                "planId": f"plan-{uuid.uuid4().hex[:12]}",
                "plan": dict(validation.get("normalized_plan") or plan.to_dict()),
                "planMarkdown": str(plan_markdown or ""),
                "validation": validation,
                "proposedBy": "top_agent",
                "createdAt": _iso_time(float(self.now())),
                "status": "pending",
            }
            with session.condition:
                session.pending_plan = pending
                session.updated_at = float(self.now())
                session.condition.notify_all()
            self._append_blueprint_planning_event(
                session,
                "plan_staged",
                pendingPlan=pending,
            )
        else:
            self._append_blueprint_planning_event(
                session,
                "plan_validation_failed",
                validation=validation,
            )
        return {
            "ok": bool(validation.get("ok")),
            "validation": validation,
            "pendingPlan": pending,
        }

    async def _close_blueprint_planning_context(self, session: DesktopBlueprintPlanningSession) -> None:
        if session.mcp is not None:
            session.mcp.close()
        await session.runtime.close()

    def _planning_session_id(self, project_dir: Path, blueprint_id: str, desktop_session_id: str) -> str:
        key = "|".join(
            [
                str(Path(project_dir).expanduser().resolve()).lower(),
                str(blueprint_id),
                str(desktop_session_id),
            ]
        )
        return f"planning-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]}"

    def _get_blueprint_planning_session(self, session_id: str) -> DesktopBlueprintPlanningSession:
        value = str(session_id).strip()
        if not value:
            raise BlueprintServiceError("BAD_REQUEST", "sessionId must be a non-empty string")
        with self._lock:
            session = self._planning_sessions.get(value)
        if session is None:
            raise BlueprintServiceError(
                "BLUEPRINT_PLANNING_SESSION_NOT_FOUND",
                f"Blueprint planning session was not found: {value}",
                status=404,
            )
        return session

    def _active_live_run_for_planning_session(
        self,
        session: DesktopBlueprintPlanningSession,
    ) -> Optional[DesktopBlueprintRun]:
        linked: Optional[DesktopBlueprintRun] = None
        with self._lock:
            if session.active_run_id:
                linked = self._runs.get(session.active_run_id)
        if linked is not None and linked.execution_mode == "live":
            try:
                linked_status = self._runtime_call(linked, lambda: linked.runtime.status_snapshot()["run"])
            except Exception:
                linked_status = {}
            if str(linked_status.get("status") or "") not in TERMINAL_RUN_STATUSES:
                return linked
            with session.condition:
                if session.active_run_id == linked.run_id:
                    session.active_run_id = None
                    session.updated_at = float(self.now())
                    session.condition.notify_all()
        with self._lock:
            candidates = [
                run
                for run in self._runs.values()
                if run.execution_mode == "live"
                and run.project_dir == session.project_dir
                and run.blueprint_id == session.blueprint_id
            ]
        for run in sorted(candidates, key=lambda item: item.updated_at, reverse=True):
            try:
                run_status = self._runtime_call(run, lambda: run.runtime.status_snapshot()["run"])
            except Exception:
                continue
            if str(run_status.get("status") or "") not in TERMINAL_RUN_STATUSES:
                return run
        return None

    def _planning_runtime_status(self, session: DesktopBlueprintPlanningSession) -> Optional[Dict[str, Any]]:
        try:
            return session.runtime.status_snapshot(graph=session.graph, recent_events_limit=20)
        except Exception:
            return None

    def _run_runtime_status(self, run: Optional[DesktopBlueprintRun]) -> Optional[Dict[str, Any]]:
        if run is None:
            return None
        try:
            return self._runtime_call(run, lambda: run.runtime.status_snapshot(graph=run.graph, recent_events_limit=20))
        except Exception:
            return None

    def _planning_status_source_summary(
        self,
        session: DesktopBlueprintPlanningSession,
        *,
        active_run: Optional[DesktopBlueprintRun],
        planning_status: Optional[Dict[str, Any]],
        active_status: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        selected = "active_live_run" if active_run is not None else "planning_context"
        mismatch = (
            active_run is not None
            and active_status is not None
            and planning_status is not None
            and _runtime_status_comparison_key(active_status) != _runtime_status_comparison_key(planning_status)
        )
        reason = (
            "linked active live run is available"
            if active_run is not None and session.active_run_id == active_run.run_id
            else "latest matching live run is available"
            if active_run is not None
            else "no active live run is linked to this planning session"
        )
        return {
            "selected": selected,
            "planningSessionId": session.session_id,
            "activeRunId": active_run.run_id if active_run is not None else session.active_run_id,
            "mismatch": bool(mismatch),
            "reason": reason,
        }

    def _planning_control_response_for_run(
        self,
        run: DesktopBlueprintRun,
        command: str,
        args: Dict[str, Any],
    ) -> Dict[str, Any]:
        if command == "run.status":
            return {
                "ok": True,
                "status": self._runtime_call(
                    run,
                    lambda: run.runtime.status_snapshot(
                        graph=run.graph,
                        recent_events_limit=int(args.get("recent_events_limit", 20)),
                    ),
                ),
            }
        if command == "top_agent.explain_status":
            return {
                "ok": True,
                "explanation": self._runtime_call(
                    run,
                    lambda: run.runtime.explain_status(
                        graph=run.graph,
                        recent_events_limit=int(args.get("recent_events_limit", 20)),
                    ),
                ),
            }
        if command == "top_agent.utterances":
            return self._runtime_call(
                run,
                lambda: run.control.top_agent_utterances(
                    task_id=(
                        str(args["task_id"])
                        if args.get("task_id") is not None
                        else None
                    ),
                    agent_id=(
                        str(args["agent_id"])
                        if args.get("agent_id") is not None
                        else None
                    ),
                    node_id=(
                        str(args["node_id"])
                        if args.get("node_id") is not None
                        else None
                    ),
                ),
            )
        return self._runtime_call(run, lambda: run.control.handle_request({"command": command, "args": args}))

    def _record_planning_status_mismatch(
        self,
        run: DesktopBlueprintRun,
        *,
        status_source: Dict[str, Any],
        planning_status: Optional[Dict[str, Any]],
        active_status: Optional[Dict[str, Any]],
    ) -> None:
        if not status_source.get("mismatch"):
            return
        mismatch_key = _planning_status_mismatch_key(status_source, planning_status, active_status)
        if mismatch_key in run.planning_status_mismatch_keys:
            return
        run.planning_status_mismatch_keys.add(mismatch_key)
        self._append_blueprint_diagnostics_event(
            run,
            "planning_status_source_mismatch",
            statusSource=status_source,
            planningStatus=_compact_runtime_status(planning_status),
            activeRunStatus=_compact_runtime_status(active_status),
        )

    def _append_blueprint_diagnostics_event(
        self,
        run: DesktopBlueprintRun,
        event_type: str,
        **data: Any,
    ) -> Optional[Dict[str, Any]]:
        diagnostics_dir = run.diagnostics_dir
        if diagnostics_dir is None:
            return None
        event = {
            "id": f"diag-{uuid.uuid4().hex[:12]}",
            "type": str(event_type),
            "createdAt": _iso_time(float(self.now())),
            **_compact_dict(data),
        }
        try:
            diagnostics_dir.mkdir(parents=True, exist_ok=True)
            events_path = diagnostics_dir / "events.jsonl"
            with events_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
            _write_blueprint_diagnostics_snapshot(
                run,
                current={
                    "lastEvent": event,
                    **_diagnostic_current_from_event(event),
                },
                saved_at=_iso_time(float(self.now())),
            )
        except Exception:
            return None
        return event

    def _append_blueprint_planning_event(
        self,
        session: DesktopBlueprintPlanningSession,
        event_type: str,
        **data: Any,
    ) -> Dict[str, Any]:
        event = {
            "id": f"evt-{uuid.uuid4().hex[:12]}",
            "type": event_type,
            "createdAt": _iso_time(float(self.now())),
            **_compact_dict(data),
        }
        with session.condition:
            session.events.append(event)
            if len(session.events) > 500:
                session.events = session.events[-500:]
            session.updated_at = float(self.now())
            session.condition.notify_all()
        return event

    def _blueprint_planning_snapshot(self, session: DesktopBlueprintPlanningSession) -> Dict[str, Any]:
        with session.condition:
            pending_question = (
                session.pending_question.to_dict()
                if session.pending_question is not None
                else None
            )
            pending_plan = dict(session.pending_plan) if session.pending_plan is not None else None
            events = [dict(event) for event in session.events]
            summary = session.summary()
            active_run_id = session.active_run_id
            framework_system = session.framework_system
            mcp_context = dict(session.mcp_context) if session.mcp_context is not None else None
        runtime_status = None
        runtime_explanation = None
        try:
            runtime_status = session.runtime.status_snapshot(graph=session.graph, recent_events_limit=20)
            runtime_explanation = session.runtime.explain_status(graph=session.graph, recent_events_limit=20)
        except Exception:
            runtime_status = None
            runtime_explanation = None
        active_run_obj = self._active_live_run_for_planning_session(session)
        with session.condition:
            active_run_id = session.active_run_id
        active_run_status = None
        active_run = None
        if active_run_obj is not None:
            try:
                active_run_status = self._runtime_call(
                    active_run_obj,
                    lambda: active_run_obj.runtime.status_snapshot(graph=active_run_obj.graph),
                )
                active_run = {
                    "runId": active_run_obj.run_id,
                    "run": active_run_obj.summary(),
                    "status": active_run_status,
                }
            except Exception:
                active_run = {"runId": active_run_obj.run_id, "status": None}
        elif active_run_id:
            try:
                run = self._get_run(active_run_id)
                active_run_status = self._runtime_call(run, lambda: run.runtime.status_snapshot(graph=run.graph))
                active_run = {
                    "runId": run.run_id,
                    "run": run.summary(),
                    "status": active_run_status,
                }
            except Exception:
                active_run = {"runId": active_run_id, "status": None}
        status_source = self._planning_status_source_summary(
            session,
            active_run=active_run_obj,
            planning_status=runtime_status,
            active_status=active_run_status,
        )
        response = {
            "ok": True,
            "sessionId": session.session_id,
            "session": summary,
            "events": events,
            "pendingQuestion": pending_question,
            "pendingPlan": pending_plan,
            "frameworkSystem": framework_system,
            "mcpContext": mcp_context,
            "runtimeStatus": runtime_status,
            "runtimeExplanation": runtime_explanation,
            "activeRun": active_run,
            "statusSource": status_source,
        }
        if active_run_obj is not None:
            self._append_blueprint_diagnostics_event(
                active_run_obj,
                "planning_status_snapshot",
                planningSessionId=session.session_id,
                statusSource=status_source,
                planningStatus=_compact_runtime_status(runtime_status),
                activeRunStatus=_compact_runtime_status(active_run_status),
                pendingQuestionStatus=(
                    pending_question.get("status")
                    if isinstance(pending_question, dict)
                    else None
                ),
                pendingPlanStatus=(
                    pending_plan.get("status")
                    if isinstance(pending_plan, dict)
                    else None
                ),
            )
            self._record_planning_status_mismatch(
                active_run_obj,
                status_source=status_source,
                planning_status=runtime_status,
                active_status=active_run_status,
            )
        return response

    def _blueprint_planning_system(
        self,
        control: GraphRuntimeControlPlane,
        graph: Any,
    ) -> str:
        profile = control.top_agent
        context = {
            "role": "GuLiCode desktop blueprint planning mode",
            "desktop_is_top_agent": True,
            "no_bottom_top_agent_worker": True,
            "organization": graph.agent_organization_summary(),
            "mcp_server": "framework_control",
            "mcp_tools": [
                f"framework_control_{tool_name}"
                for tool_name in TOP_AGENT_PLANNING_CONTROL_TOOLS
            ],
        }
        return "\n\n".join(
            [
                "# GuLiCode Desktop Blueprint Planning Mode",
                "You are operating inside the GuLiCode desktop app. The desktop app/current chat session is the Top Agent; do not assume or start a separate Top Agent CLI or worker.",
                "You must use the injected framework_control MCP tool calls for organization/status/explanation/user-question/start-plan staging. The available tool names are prefixed as framework_control_*. Do not describe them as direct APIs.",
                "If those framework_control_* tools are not visible in the current turn, say the blueprint planning MCP is not connected and stop instead of inventing a plan or claiming you can use direct framework APIs.",
                "Do not call runtime_start; the desktop app starts blueprints only after user confirmation.",
                "Do not modify or persist blueprint graph structure in this mode.",
                "When the plan depends on missing user choices, call framework_control_top_agent_request_user_input. When a valid start plan is ready, call framework_control_top_agent_stage_start_plan.",
                "## Framework Rule",
                profile.rule_text(),
                "## Framework Skill",
                profile.skill_text(),
                "## Desktop Planning Context",
                json.dumps(context, ensure_ascii=False, indent=2),
            ]
        )

    async def _close_live_run(self, run: DesktopBlueprintRun) -> None:
        if run.mcp is not None:
            run.mcp.close()
        await self._close_live_run_backend(run)

    async def _close_live_run_backend(self, run: DesktopBlueprintRun) -> None:
        await run.runtime.close()
        stop = getattr(run.backend, "stop", None)
        if callable(stop):
            await stop()

    def _end_live_run_from_mcp(
        self,
        run_id: str,
        *,
        action: str,
        reason: str = "",
        archive: bool = False,
    ) -> Dict[str, Any]:
        action = str(action).strip().lower()
        if action not in {"complete", "cancel", "fail", "pause", "archive_only"}:
            raise BlueprintServiceError(
                "UNSUPPORTED_RUN_ACTION",
                f"unsupported run end action: {action!r}",
                details={"supported": ["complete", "cancel", "fail", "pause", "archive_only"]},
            )
        should_close_backend = False
        with self._lock:
            run = self._get_run(run_id)
        run_status = self._runtime_call(run, lambda: run.runtime.status_snapshot()["run"])
        already_ended = run_status["status"] in {"completed", "cancelled", "failed"}
        if already_ended:
            end_result: Dict[str, Any] = {
                "ok": True,
                "action": action,
                "run_status": run_status["status"],
                "final_status": run_status.get("final_status"),
                "reason": reason,
                "summary": {},
                "archived": False,
            }
        else:
            end_result = self._runtime_call(
                run,
                lambda: run.runtime.end_run(
                    action,
                    reason=reason,
                    archive=bool(archive),
                ).to_dict(),
            )
            should_close_backend = run.execution_mode == "live" and action != "archive_only"
        with self._lock:
            run.updated_at = float(self.now())
        if action in {"complete", "cancel", "fail"}:
            self._finalize_popo_progress_for_run_best_effort(
                run,
                content=self._popo_progress_terminal_content("", action=action),
            )
        if should_close_backend:
            self._async_loop.run(self._close_live_run_backend(run), timeout=10)
        with run.stream_condition:
            run.stream_condition.notify_all()
        return end_result

    def _schedule_blueprint_session_idle_check(self, run_id: str) -> None:
        now = time.monotonic()
        with self._lock:
            run = self._runs.get(str(run_id))
            if run is None:
                return
            if run.session_auto_idle_terminating:
                return
            if now - float(run.session_auto_idle_checked_at or 0.0) < BLUEPRINT_SESSION_AUTO_TERMINATE_CHECK_INTERVAL_SECONDS:
                return
            run.session_auto_idle_checked_at = now

        thread = threading.Thread(
            target=lambda: self._maybe_auto_terminate_blueprint_session(str(run_id)),
            name="blueprint-session-auto-terminate-check",
            daemon=True,
        )
        thread.start()

    def _runtime_session_idle_snapshot(self, run: DesktopBlueprintRun) -> Dict[str, Any]:
        snapshotter = getattr(run.runtime, "blueprint_session_idle_snapshot", None)
        if not callable(snapshotter):
            return {
                "runStatus": "",
                "pendingWork": True,
                "readyForSessionReset": False,
                "allAgentsIdle": False,
                "workIdleSeconds": 0.0,
                "residentServiceRunning": False,
                "residentServiceIdleSeconds": None,
            }
        return dict(self._runtime_call(run, snapshotter, timeout=LIVE_RUNTIME_CALL_STARTING_TIMEOUT_SECONDS))

    def _maybe_auto_terminate_blueprint_session(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            run = self._runs.get(str(run_id))
            if run is None or run.session_auto_idle_terminating:
                return None
            session_key = str(run.session_key or run.bound_session_key or "").strip()
            if not session_key:
                return None
            run.session_auto_idle_terminating = True
        try:
            session = self._load_blueprint_session(session_key)
            if not session:
                return None
            if str(session.get("activeRunId") or "") != str(run_id) or str(session.get("status") or "") != "running":
                return None
            snapshot = self._runtime_session_idle_snapshot(run)
            if str(snapshot.get("runStatus") or "") != "running":
                return None
            if snapshot.get("pendingWork") or not snapshot.get("readyForSessionReset"):
                return None
            if not snapshot.get("allAgentsIdle") or snapshot.get("scriptRunning") or snapshot.get("residentServiceRunning"):
                return None
            threshold = BLUEPRINT_SESSION_AUTO_TERMINATE_IDLE_SECONDS
            work_idle_seconds = float(snapshot.get("workIdleSeconds") or 0.0)
            if work_idle_seconds < threshold:
                return None
            resident_completed_at = snapshot.get("lastResidentServiceCompletedAt")
            resident_idle_seconds = snapshot.get("residentServiceIdleSeconds")
            if resident_completed_at is not None and float(resident_idle_seconds or 0.0) < threshold:
                return None
            return self._terminate_active_blueprint_session(
                str(run_id),
                reason=(
                    "framework_auto_idle:"
                    f" idle_seconds={work_idle_seconds:.1f},"
                    f" resident_idle_seconds={resident_idle_seconds if resident_idle_seconds is not None else 'never_called'}"
                ),
                actor="framework_auto_idle",
                save_history=True,
            )
        except Exception:
            log.exception("failed to auto-terminate idle blueprint session")
            return None
        finally:
            with self._lock:
                current = self._runs.get(str(run_id))
                if current is not None:
                    current.session_auto_idle_terminating = False

    def _close_blueprint_session_run_best_effort(self, run_id: str, *, reason: str = "") -> str:
        errors: list[str] = []
        with self._lock:
            run = self._runs.get(str(run_id))
            if run is None:
                return "run not found"
        self._finalize_popo_progress_for_run_best_effort(run, content=POPO_PROGRESS_STOPPED_TEXT)
        with self._lock:
            run.session_key = ""
            run.bound_session_key = ""
            run.updated_at = float(self.now())

        close_mcp = getattr(run.mcp, "close", None)
        clear_history_tools = getattr(run.mcp, "clear_session_history_tools", None)
        if callable(clear_history_tools):
            try:
                clear_history_tools()
            except Exception as exc:
                errors.append(f"mcp history tool clear failed: {exc}")
        if callable(close_mcp):
            try:
                try:
                    close_mcp(timeout=LIVE_SLOT_TERMINATE_TIMEOUT_SECONDS)
                except TypeError:
                    close_mcp()
            except Exception as exc:
                errors.append(f"mcp close failed: {exc}")

        def end_without_archive() -> Any:
            result = run.runtime.end_run(
                "cancel",
                reason=reason or "blueprint session terminated",
                archive=False,
            )
            to_dict = getattr(result, "to_dict", None)
            return to_dict() if callable(to_dict) else result

        try:
            if run.execution_mode == "live":
                self._runtime_call(run, end_without_archive, timeout=LIVE_SLOT_TERMINATE_TIMEOUT_SECONDS)
            else:
                end_without_archive()
        except FutureTimeoutError:
            errors.append("runtime cancel timed out")
        except Exception as exc:
            errors.append(f"runtime cancel failed: {exc}")

        if run.execution_mode == "live":
            try:
                self._async_loop.run(
                    self._close_live_run_backend(run),
                    timeout=LIVE_SLOT_TERMINATE_TIMEOUT_SECONDS,
                )
            except FutureTimeoutError:
                errors.append("runtime close timed out")
            except Exception as exc:
                errors.append(f"runtime close failed: {exc}")

        now = float(self.now())
        with self._lock:
            current = self._runs.get(str(run_id))
            if current is not None:
                for attr in (
                    "popo_termination_start_node_id",
                    "popo_termination_session_key",
                    "popo_reply_start_node_id",
                    "popo_reply_session_key",
                ):
                    if hasattr(current.runtime, attr):
                        setattr(current.runtime, attr, "")
                current.session_key = ""
                current.bound_session_key = ""
                current.updated_at = now
        with run.stream_condition:
            run.stream_condition.notify_all()
        return "; ".join(errors)

    def _terminate_active_blueprint_session(
        self,
        run_id: str,
        *,
        reason: str = "",
        save_history: bool = True,
        actor: str = "framework",
        agent_node_id: str = "",
        agent_id: str = "",
    ) -> Dict[str, Any]:
        with self._lock:
            run = self._get_run(run_id)
            session_key = str(run.session_key or run.bound_session_key or "").strip()
            start_node_id = str(run.start_node_id or document_start_node_id(run.document))
        if not session_key:
            raise BlueprintServiceError(
                "BLUEPRINT_SESSION_NOT_FOUND",
                "blueprint run is not bound to a session",
                details={"runId": run_id},
                status=404,
            )
        session = self._load_blueprint_session(session_key)
        now = float(self.now())
        if session:
            session["activeRunId"] = ""
            session["lastRunId"] = run_id
            session["status"] = "terminated"
            session["queuedMessages"] = []
            session["queuedMessageCount"] = 0
            session["lastTouchedAt"] = now
            if save_history:
                self._record_blueprint_session_terminator(
                    session,
                    actor=actor,
                    agent_node_id=agent_node_id,
                    agent_id=agent_id,
                )
            self._save_blueprint_session(session)
            if save_history:
                self._append_blueprint_session_event(
                    session_key,
                    {
                        "type": "session_terminated",
                        "runId": run_id,
                        "startNodeId": start_node_id,
                        "agentNodeId": str(agent_node_id or ""),
                        "agentId": str(agent_id or ""),
                        "actor": str(actor or ""),
                        "reason": str(reason or ""),
                    },
                )
        with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                run.session_key = ""
                run.bound_session_key = ""
                run.updated_at = now
        close_error = self._close_blueprint_session_run_best_effort(
            run_id,
            reason=reason or "blueprint session terminated",
        )
        return {
            "ok": True,
            "runId": run_id,
            "sessionKey": session_key,
            "terminated": True,
            "saveHistory": bool(save_history),
            "closed": True,
            "closeError": close_error,
            "session": session,
        }

    def _terminate_blueprint_session_from_mcp(
        self,
        run_id: str,
        *,
        reason: str = "",
        save_history: bool = True,
        agent_node_id: str = "",
        agent_id: str = "",
    ) -> Dict[str, Any]:
        with self._lock:
            run = self._get_run(run_id)
            start_node_id = str(run.start_node_id or document_start_node_id(run.document))
        if str(agent_node_id or "") != start_node_id:
            raise BlueprintServiceError(
                "BLUEPRINT_TERMINATE_FORBIDDEN",
                "only the active session start Agent can terminate this blueprint session",
                details={"runId": run_id, "startNodeId": start_node_id, "agentNodeId": agent_node_id},
                status=403,
            )
        return self._terminate_active_blueprint_session(
            run_id,
            reason=reason,
            save_history=save_history,
            actor="agent",
            agent_node_id=agent_node_id,
            agent_id=agent_id,
        )

    def _terminate_popo_session_from_mcp(self, run_id: str, **kwargs: Any) -> Dict[str, Any]:
        return self._terminate_blueprint_session_from_mcp(run_id, **kwargs)

    def _query_excel_history_from_mcp(
        self,
        run_id: str,
        *,
        start_time: str = "",
        end_time: str = "",
        workbook: str = "",
        field: str = "",
        category: str = "xltool",
        limit: int = 50,
        session_key: str = "",
        agent_node_id: str = "",
        agent_id: str = "",
    ) -> Dict[str, Any]:
        with self._lock:
            run = self._get_run(run_id)
            explicit_session_key = str(session_key or "").strip()
            bound_session_key = str(
                run.session_key
                or run.bound_session_key
                or getattr(run.runtime, "popo_reply_session_key", "")
                or ""
            ).strip()
            active_session_key = str(
                bound_session_key
                or explicit_session_key
            ).strip()
            start_node_id = str(run.start_node_id or document_start_node_id(run.document))
        if not active_session_key:
            raise BlueprintServiceError(
                "BLUEPRINT_SESSION_NOT_FOUND",
                "blueprint run is not bound to a session",
                details={"runId": run_id},
                status=404,
            )
        if str(agent_node_id or "") != start_node_id:
            raise BlueprintServiceError(
                "BLUEPRINT_EXCEL_HISTORY_FORBIDDEN",
                "only the session start Agent can query Excel history for this session",
                details={"runId": run_id, "startNodeId": start_node_id, "agentNodeId": agent_node_id},
                status=403,
            )
        if explicit_session_key and bound_session_key and explicit_session_key != bound_session_key:
            raise BlueprintServiceError(
                "BLUEPRINT_EXCEL_HISTORY_FORBIDDEN",
                "Excel history queries are limited to the run's active blueprint session",
                details={
                    "runId": run_id,
                    "sessionKey": bound_session_key,
                    "requestedSessionKey": explicit_session_key,
                },
                status=403,
            )
        session = self._load_blueprint_session(active_session_key)
        if not session or str(session.get("activeRunId") or "") != run_id:
            raise BlueprintServiceError(
                "BLUEPRINT_SESSION_NOT_FOUND",
                "active blueprint session was not found for this run",
                details={"runId": run_id, "sessionKey": active_session_key},
                status=404,
            )
        result = query_excel_history(
            self._blueprint_session_dir(active_session_key),
            start_time=start_time,
            end_time=end_time,
            workbook=workbook,
            field=field,
            category=category,
            limit=limit,
        )
        result["sessionKey"] = active_session_key
        result["runId"] = run_id
        return result

    def _reply_popo_user_from_framework(
        self,
        run_id: str,
        *,
        content: str,
        session_key: str = "",
        agent_node_id: str = "",
        agent_id: str = "",
        message_id: str = "",
    ) -> Dict[str, Any]:
        text = str(content or "").strip()
        if not text:
            raise BlueprintServiceError("BAD_REQUEST", "POPO reply content must be a non-empty string", status=400)
        with self._lock:
            run = self._get_run(run_id)
            explicit_session_key = str(session_key or "").strip()
            session_key = str(
                explicit_session_key
                or run.session_key
                or run.bound_session_key
                or getattr(run.runtime, "popo_reply_session_key", "")
                or ""
            ).strip()
            start_node_id = str(run.start_node_id or document_start_node_id(run.document))
            robot_app_key = str(run.robot_app_key or "").strip()
        if not session_key:
            raise BlueprintServiceError(
                "BLUEPRINT_SESSION_NOT_FOUND",
                "POPO blueprint run is not bound to a session",
                details={"runId": run_id},
                status=404,
            )
        if str(agent_node_id or "") != start_node_id:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_REPLY_FORBIDDEN",
                "only the POPO start Agent can reply to this blueprint session user",
                details={"runId": run_id, "startNodeId": start_node_id, "agentNodeId": agent_node_id},
                status=403,
            )
        if not robot_app_key:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_REPLY_UNAVAILABLE",
                "this blueprint run was not started from a POPO robot",
                details={"runId": run_id},
                status=400,
            )
        session = self._load_blueprint_session(session_key)
        session_run_matches = bool(
            session
            and str(session.get("status") or "") == "running"
            and str(session.get("activeRunId") or "") == run_id
        )
        if not session_run_matches:
            raise BlueprintServiceError(
                "BLUEPRINT_SESSION_NOT_FOUND",
                "active POPO blueprint session was not found for this run",
                details={"runId": run_id, "sessionKey": session_key},
                status=404,
            )
        session_robot_app_key = str(session.get("robotAppKey") or "").strip()
        if session_robot_app_key and session_robot_app_key != robot_app_key:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_ROBOT_STRUCTURE_CONFLICT",
                "POPO session robot binding does not match this run",
                details={"runId": run_id, "sessionKey": session_key},
                status=409,
            )
        receiver = self._popo_reply_receiver_from_session(session)
        if not receiver:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_REPLY_TARGET_REQUIRED",
                "POPO reply receiver is missing from the active session",
                details={"runId": run_id, "sessionKey": session_key},
                status=400,
            )
        robot = self._resolve_popo_callback_robot(robot_app_key)
        missing = popo_callback_robot_missing_fields(robot)
        if missing:
            raise BlueprintServiceError(
                "BLUEPRINT_POPO_ENTRY_REQUIRED",
                "enabled POPO callback robot is incomplete",
                details={"robotAppKey": robot_app_key, "missing": missing},
                status=400,
            )
        progress_recall_result = self._finalize_popo_progress_for_run(
            run_id,
            session_key=session_key,
            content=text,
        )
        send_result = self._send_popo_message(receiver=receiver, content=text, robot_config=robot)
        now = float(self.now())
        session["lastTouchedAt"] = now
        session["lastAgentReplyAt"] = now
        session["lastAgentReplyByNodeId"] = str(agent_node_id or "")
        session["lastAgentReplyByAgentId"] = str(agent_id or "")
        self._save_blueprint_session(session)
        self._append_blueprint_session_event(
            session_key,
            {
                "type": "agent_reply",
                "source": "framework_popo_reply",
                "runId": run_id,
                "startNodeId": start_node_id,
                "agentNodeId": str(agent_node_id or ""),
                "agentId": str(agent_id or ""),
                "messageId": str(message_id or ""),
                "content": text,
                "frameworkReply": True,
            },
        )
        popo_reply_event = {
            "type": "popo_reply_sent",
            "source": "framework_popo_reply",
            "runId": run_id,
            "startNodeId": start_node_id,
            "agentNodeId": str(agent_node_id or ""),
            "agentId": str(agent_id or ""),
            "messageId": str(message_id or ""),
            "content": text,
            "robotAppKey": robot_app_key,
            "frameworkReply": True,
        }
        transport = str(send_result.get("transport") or "").strip()
        popo_message_id = str(send_result.get("messageId") or "").strip()
        fallback_reason = str(send_result.get("fallbackReason") or "").strip()
        if transport:
            popo_reply_event["transport"] = transport
        if popo_message_id:
            popo_reply_event["popoMessageId"] = popo_message_id
        if fallback_reason:
            popo_reply_event["fallbackReason"] = fallback_reason
        if progress_recall_result is not None:
            popo_reply_event["progressTransport"] = str(progress_recall_result.get("transport") or "")
            progress_message_id = str(progress_recall_result.get("popoMessageId") or "").strip()
            if progress_message_id:
                popo_reply_event["recalledProgressMessageId"] = progress_message_id
            progress_fallback_reason = str(progress_recall_result.get("fallbackReason") or "").strip()
            if progress_fallback_reason:
                popo_reply_event["progressFallbackReason"] = progress_fallback_reason
        self._append_blueprint_session_event(session_key, popo_reply_event)
        return {
            "ok": True,
            "sent": bool(send_result.get("sent", True)),
            "runId": run_id,
            "sessionKey": session_key,
        }

    def _auto_complete_framework_popo_reply_task_status(
        self,
        run_id: str,
        *,
        agent_node_id: str,
        agent_id: str,
        message_id: str = "",
    ) -> None:
        with self._lock:
            run = self._runs.get(str(run_id))
        if run is None or run.control is None:
            return
        args = {
            "node_id": str(agent_node_id or ""),
            "agent_id": str(agent_id or ""),
            "status": "completed",
            "summary": "Replied to the POPO user.",
            "message_id": str(message_id or "") or None,
            "batch_id": None,
            "reports": [],
            "artifacts": [],
            "changesets": [],
            "next_actions": [],
            "metadata": {
                "framework_auto": True,
                "source": "framework_popo_reply",
            },
        }
        try:
            run.control.handle_request({"command": "agent.task_status", "args": args})
        except Exception:
            log.exception("failed to auto-complete framework POPO reply task status")

    def close(self) -> None:
        self.stop_table_queue_notification_watcher()
        self.stop_planning_table_skill_update_notification_watcher()
        with self._lock:
            runs = list(self._runs.values())
            planning_sessions = list(self._planning_sessions.values())
        for run in runs:
            self._finalize_popo_progress_for_run_best_effort(run, content=POPO_PROGRESS_STOPPED_TEXT)
            if run.execution_mode == "live":
                try:
                    self._async_loop.run(self._close_live_run(run), timeout=10)
                except Exception:
                    pass
            with run.stream_condition:
                run.stream_condition.notify_all()
        for session in planning_sessions:
            try:
                self._async_loop.run(self._close_blueprint_planning_context(session), timeout=10)
            except Exception:
                pass
            with session.condition:
                session.status = "ended"
                session.condition.notify_all()
        self._async_loop.close()

    def _generate_run_id_locked(self) -> str:
        with self._lock:
            for _ in range(100):
                run_id = f"run-{uuid.uuid4().hex[:12]}"
                if run_id not in self._runs:
                    return run_id
        raise RuntimeError("failed to generate a unique blueprint run id")

    def _get_run(self, run_id: str) -> DesktopBlueprintRun:
        value = str(run_id).strip()
        if not value:
            raise BlueprintServiceError("BAD_REQUEST", "runId must be a non-empty string")
        with self._lock:
            run = self._runs.get(value)
        if run is None:
            raise BlueprintServiceError(
                "RUN_NOT_FOUND",
                f"blueprint run was not found: {value}",
                status=404,
            )
        return run



def valid_blueprint_id(value: str) -> bool:
    return bool(BLUEPRINT_ID_RE.fullmatch(value))


def request_project_dir(args: Dict[str, Any]) -> Path:
    value = args.get("projectDir")
    if not isinstance(value, str) or not value.strip():
        raise BlueprintServiceError("BAD_REQUEST", "projectDir must be a non-empty string")
    return Path(value)


def request_run_id(args: Dict[str, Any]) -> str:
    value = args.get("runId")
    if not isinstance(value, str) or not value.strip():
        raise BlueprintServiceError("BAD_REQUEST", "runId must be a non-empty string")
    return value.strip()


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_ws_text(wfile: Any, text: str) -> None:
    data = text.encode("utf-8")
    header = bytearray([0x81])
    if len(data) < 126:
        header.append(len(data))
    elif len(data) < 65536:
        header.extend([126, (len(data) >> 8) & 0xFF, len(data) & 0xFF])
    else:
        header.append(127)
        header.extend(len(data).to_bytes(8, "big"))
    wfile.write(bytes(header) + data)
    wfile.flush()


def _message_journal_for_node(runtime: GraphRuntime, node_id: str, *, limit: int = 200) -> list[Dict[str, Any]]:
    records = [
        _project_message_record(record)
        for record in runtime.message_journal
        if _message_record_involves_node(record, node_id)
    ]
    return records[-limit:]


def _framework_api_calls_for_node(
    run: DesktopBlueprintRun,
    node_id: str,
    agent_id: str,
    *,
    limit: int = 200,
) -> list[Dict[str, Any]]:
    calls: list[Dict[str, Any]] = []
    for record in run.runtime.message_journal:
        if not _message_record_involves_node(record, node_id):
            continue
        record_type = str(record.get("record_type") or "")
        sender = _record_dict(record.get("sender"))
        if record_type in {"agent.outgoing.staged", "agent.outgoing.no_op"} and sender.get("node_id") == node_id:
            projected = _project_message_record(record)
            calls.append(
                {
                    **projected,
                    "api": "agent.dispatch",
                    "summary": projected.get("summary"),
                }
            )

    for event in run.runtime.events:
        payload = _record_dict(event.payload)
        if event.event_type == "JoinContributionSubmitted" and payload.get("source_node_id") == node_id:
            calls.append(
                _compact_dict(
                    {
                        "id": f"framework-{event.event_type}-{len(calls) + 1}",
                        "api": "join.contribute",
                        "time": None,
                        "from": node_id,
                        "to": "framework",
                        "status": event.status,
                        "summary": payload.get("join_id"),
                    }
                )
            )
        elif event.event_type in {"ChangesetSubmitted", "ChangesetAccepted"} and _event_matches_agent(payload, node_id, agent_id):
            calls.append(
                _compact_dict(
                    {
                        "id": f"framework-{event.event_type}-{len(calls) + 1}",
                        "api": "changeset.submit",
                        "from": node_id,
                        "to": "framework",
                        "status": event.status,
                        "summary": payload.get("summary") or payload.get("changeset_id"),
                    }
                )
            )
        elif event.event_type == "ArtifactPublished" and _event_matches_agent(payload, node_id, agent_id):
            calls.append(
                _compact_dict(
                    {
                        "id": f"framework-{event.event_type}-{len(calls) + 1}",
                        "api": "artifact.publish",
                        "from": node_id,
                        "to": "framework",
                        "status": event.status,
                        "summary": payload.get("path") or payload.get("artifact_id"),
                    }
                )
            )
        elif event.event_type == "AgentReportSubmitted" and _event_matches_agent(payload, node_id, agent_id):
            calls.append(
                _compact_dict(
                    {
                        "id": f"framework-{event.event_type}-{len(calls) + 1}",
                        "api": "report.submit",
                        "from": node_id,
                        "to": "framework",
                        "status": event.status,
                        "summary": payload.get("path") or payload.get("report_id"),
                    }
                )
            )

    calls.extend(_workspace_api_calls_for_agent(run, node_id, agent_id))
    return calls[-limit:]


def _workspace_api_calls_for_agent(run: DesktopBlueprintRun, node_id: str, agent_id: str) -> list[Dict[str, Any]]:
    workspace = getattr(run.runtime, "workspace", None)
    if workspace is None:
        return []
    manifest_path = Path(workspace.workspace_root) / "shared" / "manifest.json"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    calls: list[Dict[str, Any]] = []
    for index, record in enumerate(data.get("writes", []), start=1):
        if not isinstance(record, dict):
            continue
        if record.get("event_type") != "workspace_api_call" and record.get("workspace_event") != "WorkspaceAPICalled":
            continue
        if str(record.get("agent_id") or "") != agent_id:
            continue
        command = str(record.get("command") or "").strip()
        calls.append(
            _compact_dict(
                {
                    "id": f"workspace-api-{index}",
                    "api": "workspace",
                    "command": command,
                    "time": record.get("created_at") or record.get("updated_at"),
                    "from": node_id,
                    "to": "framework",
                    "status": "called",
                    "summary": record.get("path") or record.get("summary") or record.get("area"),
                }
            )
        )
    return calls


def _reset_blueprint_diagnostics_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    (path / "events.jsonl").write_text("", encoding="utf-8")
    return path


def _write_blueprint_diagnostics_snapshot(
    run: DesktopBlueprintRun,
    *,
    current: Dict[str, Any],
    saved_at: Optional[str],
) -> None:
    if run.diagnostics_dir is None:
        return
    snapshot = {
        "schema_version": BLUEPRINT_DIAGNOSTICS_SCHEMA_VERSION,
        "kind": BLUEPRINT_DIAGNOSTICS_KIND,
        "focus": BLUEPRINT_DIAGNOSTICS_FOCUS,
        "runId": run.run_id,
        "projectDir": str(run.project_dir),
        "blueprintId": run.blueprint_id,
        "saved_at": saved_at,
        "current": current,
    }
    (run.diagnostics_dir / "snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _diagnostic_current_from_event(event: Dict[str, Any]) -> Dict[str, Any]:
    event_type = str(event.get("type") or "")
    current: Dict[str, Any] = {}
    if "statusSource" in event:
        current["statusSource"] = event.get("statusSource")
    if event_type == "blueprint_run_started":
        current["runtimeStatus"] = event.get("status")
    elif event_type == "planning_status_snapshot":
        current["planningStatus"] = event.get("planningStatus")
        current["activeRunStatus"] = event.get("activeRunStatus")
    elif event_type == "planning_mcp_control_call":
        current["lastMcpControlCall"] = {
            "toolName": event.get("toolName"),
            "command": event.get("command"),
            "args": event.get("args"),
            "statusSource": event.get("statusSource"),
            "output": event.get("output"),
            "error": event.get("error"),
        }
    elif event_type == "planning_status_source_mismatch":
        current["planningStatus"] = event.get("planningStatus")
        current["activeRunStatus"] = event.get("activeRunStatus")
    return _compact_dict(current)


def _compact_runtime_status(status: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(status, dict):
        return None
    run = _record_dict(status.get("run"))
    message_journal = _record_dict(run.get("message_journal"))
    agents: Dict[str, Any] = {}
    raw_agents = status.get("agents")
    if isinstance(raw_agents, dict):
        for node_id, raw_agent in sorted(raw_agents.items()):
            agent = _record_dict(raw_agent)
            agents[str(node_id)] = _compact_dict(
                {
                    "agent_id": agent.get("agent_id"),
                    "state": agent.get("state"),
                    "busy_count": agent.get("busy_count"),
                    "queue_size": agent.get("queue_size"),
                    "current_message_id": agent.get("current_message_id"),
                    "last_error": agent.get("last_error"),
                }
            )
    return {
        "run": _compact_dict(
            {
                "status": run.get("status"),
                "final_status": run.get("final_status"),
                "message_journal": _compact_dict(
                    {
                        "path": message_journal.get("path"),
                        "record_count": message_journal.get("record_count"),
                    }
                ),
            }
        ),
        "agents": agents,
    }


def _runtime_status_comparison_key(status: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    compact = _compact_runtime_status(status) or {}
    agents = compact.get("agents") if isinstance(compact.get("agents"), dict) else {}
    return {
        "run": _record_dict(compact.get("run")).get("status"),
        "agents": {
            str(node_id): {
                "state": _record_dict(agent).get("state"),
                "busy_count": _record_dict(agent).get("busy_count"),
                "queue_size": _record_dict(agent).get("queue_size"),
                "current_message_id": _record_dict(agent).get("current_message_id"),
                "last_error": _record_dict(agent).get("last_error"),
            }
            for node_id, agent in sorted(agents.items())
        },
    }


def _planning_status_mismatch_key(
    status_source: Dict[str, Any],
    planning_status: Optional[Dict[str, Any]],
    active_status: Optional[Dict[str, Any]],
) -> str:
    data = {
        "planning_session_id": status_source.get("planningSessionId"),
        "active_run_id": status_source.get("activeRunId"),
        "selected": status_source.get("selected"),
        "planning": _runtime_status_comparison_key(planning_status),
        "active": _runtime_status_comparison_key(active_status),
    }
    return json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)


def _compact_control_result(result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(result, dict):
        return None
    compact: Dict[str, Any] = {
        "ok": result.get("ok"),
        "status_source": result.get("status_source"),
        "source_run_id": result.get("source_run_id"),
        "planning_session_id": result.get("planning_session_id"),
    }
    if isinstance(result.get("status"), dict):
        compact["status"] = _compact_runtime_status(result.get("status"))
    if isinstance(result.get("explanation"), dict):
        explanation = _record_dict(result.get("explanation"))
        compact["explanation"] = _compact_dict(
            {
                "summary": explanation.get("summary"),
                "observations": list(explanation.get("observations", []))[:10]
                if isinstance(explanation.get("observations"), list)
                else None,
                "warnings": list(explanation.get("warnings", []))[:10]
                if isinstance(explanation.get("warnings"), list)
                else None,
            }
        )
    if isinstance(result.get("utterances"), list):
        compact["utterance_count"] = len(result["utterances"])
        compact["filters"] = result.get("filters")
    if "error" in result:
        compact["error"] = result.get("error")
    return _compact_dict(compact)


def _compact_validation(validation: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(validation, dict):
        return None
    return _compact_dict(
        {
            "ok": validation.get("ok"),
            "errorCount": len(validation.get("errors", []) or []),
            "warningCount": len(validation.get("warnings", []) or []),
            "errors": list(validation.get("errors", []))[:10]
            if isinstance(validation.get("errors"), list)
            else None,
            "warnings": list(validation.get("warnings", []))[:10]
            if isinstance(validation.get("warnings"), list)
            else None,
        }
    )


def _live_start_pending(run: DesktopBlueprintRun) -> bool:
    future = run.live_start_future
    return future is not None and not future.done()


def _starting_runtime_status(*, status_pending: bool = False) -> Dict[str, Any]:
    run_status: Dict[str, Any] = {
        "status": "starting",
        "final_status": None,
        "ended_at": None,
    }
    if status_pending:
        run_status["statusPending"] = True
    return {
        "run": run_status,
        "agents": {
            "by_node": {},
            "counts": {},
        },
        "jobs": {
            "items": [],
            "counts": {},
        },
        "queues": {
            "by_agent": {},
            "pending": 0,
        },
        "recent_events": [],
        "workspace": {
            "changesets": [],
            "artifacts": [],
            "reports": [],
        },
    }


def _compact_start_response(started: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(started, dict):
        return None
    return _compact_dict(
        {
            "ok": started.get("ok"),
            "queuedMessageCount": len(started.get("queuedMessages", started.get("queued_messages", [])) or []),
            "runId": started.get("runId"),
        }
    )


def _project_message_record(record: Dict[str, Any]) -> Dict[str, Any]:
    metadata = _record_dict(record.get("metadata"))
    projected = {
        "id": record.get("record_id"),
        "recordType": record.get("record_type"),
        "time": _iso_time(record.get("recorded_at")),
        "from": _endpoint_label(record.get("sender")),
        "to": _endpoint_label(record.get("receiver")),
        "status": record.get("status"),
        "summary": _message_summary(record.get("payload")),
        "messageId": record.get("message_id"),
        "batchId": record.get("batch_id"),
        "targetNodeId": metadata.get("target_node_id"),
        "targetAgentId": metadata.get("target_agent_id"),
    }
    return _compact_dict(projected)


def _message_record_involves_node(record: Dict[str, Any], node_id: str) -> bool:
    sender = _record_dict(record.get("sender"))
    receiver = _record_dict(record.get("receiver"))
    metadata = _record_dict(record.get("metadata"))
    return node_id in {
        str(sender.get("node_id") or ""),
        str(receiver.get("node_id") or ""),
        str(metadata.get("target_node_id") or ""),
    }


def _event_matches_agent(payload: Dict[str, Any], node_id: str, agent_id: str) -> bool:
    return node_id in {
        str(payload.get("node_id") or ""),
        str(payload.get("source_node_id") or ""),
    } or agent_id == str(payload.get("agent_id") or "")


def _record_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _endpoint_label(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    record = _record_dict(value)
    for key in ("node_id", "agent_id", "type"):
        raw = record.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _message_summary(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if not isinstance(value, dict):
        return None
    for key in ("text", "prompt", "message", "summary", "content"):
        raw = value.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    body = value.get("body")
    if isinstance(body, dict):
        return _message_summary(body)
    return None


def _agent_reply_text(reply: Any) -> str:
    if isinstance(reply, dict):
        body = reply.get("body")
        if isinstance(body, dict):
            codex = body.get("codex")
            if isinstance(codex, dict):
                for key in ("final_text", "last_message", "text"):
                    value = codex.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
            for key in ("answer", "result", "text", "message"):
                value = body.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        for key in ("answer", "result", "text", "message"):
            value = reply.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return json.dumps(reply, ensure_ascii=False)
    return str(reply)


def _compact_top_agent_result(result: Any) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {"type": type(result).__name__}
    compact: Dict[str, Any] = {}
    for key in ("ok", "top_agent"):
        if key in result:
            compact[key] = result[key]
    reply = result.get("reply")
    if isinstance(reply, dict):
        compact["reply"] = {
            "type": reply.get("type"),
            "bodyKeys": sorted(str(item) for item in reply.get("body", {}).keys())
            if isinstance(reply.get("body"), dict)
            else [],
        }
    elif reply is not None:
        compact["reply"] = {"type": type(reply).__name__}
    return compact


def _iso_time(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return None


def _compact_dict(value: Dict[str, Any]) -> Dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None and item != ""}


def coerce_event_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        raise BlueprintServiceError("BAD_REQUEST", "limit must be an integer") from None
    return max(0, min(200, limit))


def _desktop_skill_catalog_from_document(
    document: Dict[str, Any],
    project_dir: Path,
) -> DesktopBlueprintSkillCatalog:
    config = _blueprint_common_config(document)
    skill_dirs = _configured_skill_dirs_from_config(config)
    return DesktopBlueprintSkillCatalog(skill_dirs or [default_codex_skill_dir()])


def _request_path_list(args: Dict[str, Any], plural_key: str, legacy_key: str) -> list[Path]:
    raw_paths = args.get(plural_key)
    values = _string_list(raw_paths)
    if not values:
        values = _string_list(args.get(legacy_key))
    return _dedupe_paths(values)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        raw_values = value
    else:
        raw_values = [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        text = str(item).strip() if item is not None else ""
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _dedupe_paths(paths: Sequence[str]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for value in paths:
        text = str(value).strip()
        if not text:
            continue
        key = os.path.normcase(text)
        if key in seen:
            continue
        seen.add(key)
        result.append(Path(text))
    return result


def _configured_path_strings_from_config(config: Dict[str, Any], plural_key: str, legacy_key: str) -> list[str]:
    values = _string_list(config.get(plural_key))
    if not values:
        values = _string_list(config.get(legacy_key))
    return values


def _configured_skill_dirs_from_config(config: Dict[str, Any]) -> list[Path]:
    return _dedupe_paths(_configured_path_strings_from_config(config, "skill_dirs", "skill_dir"))


def _configured_rule_dirs_from_config(config: Dict[str, Any]) -> list[Path]:
    return _dedupe_paths(_configured_path_strings_from_config(config, "rule_dirs", "rule_dir"))


def _description_from_skill_md(skill_md: Path) -> str:
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return ""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            lines = parts[1].splitlines()
            for index, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("description:"):
                    value = stripped.split(":", 1)[1].strip().strip("\"'")
                    if value in {">", ">-", "|", "|-"}:
                        block_lines: list[str] = []
                        for continuation in lines[index + 1 :]:
                            if continuation and not continuation[0].isspace():
                                break
                            text_value = continuation.strip()
                            if text_value:
                                block_lines.append(text_value)
                        return " ".join(block_lines).strip()
                    return value
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("# ").strip()[:120]
    return ""


def validate_project_dir(project_dir: Path) -> Path:
    resolved = project_dir.expanduser().resolve()
    if not resolved.is_dir():
        raise BlueprintServiceError("PROJECT_NOT_FOUND", f"projectDir is not a directory: {project_dir}")
    return resolved


def validate_blueprint_id(blueprint_id: str) -> str:
    value = str(blueprint_id).strip()
    if not valid_blueprint_id(value):
        raise BlueprintServiceError(
            "INVALID_BLUEPRINT_ID",
            "blueprint id must match [A-Za-z0-9._-]+",
        )
    return value


def blueprint_dir(project_dir: Path) -> Path:
    return validate_project_dir(project_dir) / ".multi_agent_workspace" / "blueprints"


def blueprint_path(project_dir: Path, blueprint_id: str) -> Path:
    return blueprint_dir(project_dir) / f"{validate_blueprint_id(blueprint_id)}.json"


def blueprint_session_key_path_component(session_key: str) -> str:
    value = str(session_key or "").strip()
    if re.fullmatch(r"bps_[0-9a-f]{24}", value):
        return value
    if re.fullmatch(r"bps_popo_[A-Za-z0-9._-]{1,96}_[0-9a-f]{24}", value):
        return value
    if value.startswith(BLUEPRINT_POPO_SESSION_PREFIX):
        tail = value[len(BLUEPRINT_POPO_SESSION_PREFIX):]
        if "+" in tail:
            label, blueprint_name = tail.split("+", 1)
            if (
                re.fullmatch(r"[A-Za-z0-9._-]{1,96}", label)
                and _valid_blueprint_session_name_slug(blueprint_name)
            ):
                return value
    if value.startswith(BLUEPRINT_MAIN_SESSION_PREFIX):
        blueprint_id = value[len(BLUEPRINT_MAIN_SESSION_PREFIX):]
        if valid_blueprint_id(blueprint_id):
            return f"{BLUEPRINT_MAIN_SESSION_PREFIX}{validate_blueprint_id(blueprint_id)}"
    raise BlueprintServiceError(
        "INVALID_BLUEPRINT_SESSION",
        "sessionKey must match bps_[0-9a-f]{24}, bps_popo_<label>_<hash>, bps_popo_<label>+<blueprintName>, or main+<blueprintId>",
    )
    return value


def blueprint_main_session_key(blueprint_id: str) -> str:
    return f"{BLUEPRINT_MAIN_SESSION_PREFIX}{validate_blueprint_id(blueprint_id)}"


def canonical_blueprint_structure_id(graph: Dict[str, Any]) -> str:
    if not isinstance(graph, dict):
        raise BlueprintServiceError("INVALID_DOCUMENT", "blueprint document graph must be a JSON object")
    structure = {
        "terminal_nodes": graph.get("terminal_nodes") or {},
        "agent_nodes": graph.get("agent_nodes") or {},
        "route_nodes": graph.get("route_nodes") or {},
        "common_nodes": graph.get("common_nodes") or {},
        "script_nodes": graph.get("script_nodes") or {},
        "prompt_nodes": graph.get("prompt_nodes") or {},
        "edges": graph.get("edges") or [],
    }
    raw = json.dumps(structure, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def normalize_popo_entry(value: Any = None) -> Dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    return {
        "enabled": bool(value.get("enabled", False)),
        "robot_app_key": str(value.get("robot_app_key") or value.get("robotAppKey") or "").strip(),
        "robot_name": str(value.get("robot_name") or value.get("robotName") or "").strip(),
        "robot_app_secret": str(value.get("robot_app_secret") or value.get("robotAppSecret") or "").strip(),
        "callback_token": str(value.get("callback_token") or value.get("callbackToken") or "").strip(),
        "aes_key": str(value.get("aes_key") or value.get("aesKey") or "").strip(),
    }


def normalize_popo_robot_route(value: Any = None) -> Dict[str, Any]:
    entry = normalize_popo_entry(value)
    if not isinstance(value, dict):
        value = {}
    return {
        **entry,
        "updated_at": float(value.get("updated_at") or value.get("updatedAt") or 0.0),
    }


def popo_callback_robot_missing_fields(entry: Dict[str, Any]) -> list[str]:
    required = ("robot_app_key", "robot_app_secret", "callback_token", "aes_key")
    return [field for field in required if not str(entry.get(field) or "").strip()]


def popo_entry_has_values(entry: Dict[str, Any]) -> bool:
    return bool(entry.get("enabled")) or any(
        str(entry.get(field) or "").strip()
        for field in POPO_ENTRY_REQUIRED_FIELDS
    )


def _agent_node_type(raw_node: Any) -> str:
    if not isinstance(raw_node, dict):
        return "worker_agent"
    return "agent" if str(raw_node.get("node_type") or "").strip() == "agent" else "worker_agent"


def _agent_node_popo_entry(raw_node: Any) -> Dict[str, Any]:
    if not isinstance(raw_node, dict):
        return normalize_popo_entry()
    return normalize_popo_entry(raw_node.get("popo_entry") or raw_node.get("popoEntry"))


def _document_enabled_popo_agent_entries(document: Dict[str, Any]) -> list[tuple[str, Dict[str, Any]]]:
    enabled: list[tuple[str, Dict[str, Any]]] = []
    graph = document.get("graph", {})
    agent_nodes = graph.get("agent_nodes", {}) if isinstance(graph, dict) else {}
    if not isinstance(agent_nodes, dict):
        return enabled
    for node_id, raw_node in agent_nodes.items():
        if _agent_node_type(raw_node) != "agent":
            continue
        entry = _agent_node_popo_entry(raw_node)
        if entry.get("enabled"):
            enabled.append((str(node_id), entry))
    return enabled


def document_popo_agent_entry(document: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    start_node_id = document_start_node_id(document)
    graph = document.get("graph", {})
    agent_nodes = graph.get("agent_nodes", {}) if isinstance(graph, dict) else {}
    start_entry = normalize_popo_entry()
    if isinstance(agent_nodes, dict) and start_node_id:
        raw_start = agent_nodes.get(start_node_id)
        if _agent_node_type(raw_start) == "agent":
            start_entry = _agent_node_popo_entry(raw_start)
    if popo_entry_has_values(start_entry):
        return start_node_id, start_entry
    runtime = document.get("runtime", {})
    if isinstance(runtime, dict):
        legacy = normalize_popo_entry(runtime.get("popo_entry") or runtime.get("popoEntry"))
        if popo_entry_has_values(legacy):
            return start_node_id, legacy
    return start_node_id, start_entry


def document_popo_entry(document: Dict[str, Any]) -> Dict[str, Any]:
    return document_popo_agent_entry(document)[1]


def popo_entry_missing_fields(entry: Dict[str, Any]) -> list[str]:
    return [field for field in POPO_ENTRY_REQUIRED_FIELDS if not str(entry.get(field) or "").strip()]


def require_complete_popo_entry(document: Dict[str, Any]) -> Dict[str, Any]:
    start_node_id = document_start_node_id(document)
    enabled_entries = _document_enabled_popo_agent_entries(document)
    if len(enabled_entries) > 1:
        raise BlueprintServiceError(
            "BLUEPRINT_POPO_ROBOT_STRUCTURE_CONFLICT",
            "only one full Agent in a blueprint can enable POPO message forwarding",
            details={
                "blueprintId": str(document.get("id") or ""),
                "enabledAgentNodeIds": [node_id for node_id, _entry in enabled_entries],
            },
        )
    if enabled_entries and enabled_entries[0][0] != start_node_id:
        raise BlueprintServiceError(
            "BLUEPRINT_POPO_START_AGENT_REQUIRED",
            "POPO message forwarding must be enabled on the saved start full Agent",
            details={
                "blueprintId": str(document.get("id") or ""),
                "startNodeId": start_node_id,
                "enabledAgentNodeId": enabled_entries[0][0],
            },
        )
    _node_id, entry = document_popo_agent_entry(document)
    missing = popo_entry_missing_fields(entry)
    if not entry.get("enabled") or missing:
        raise BlueprintServiceError(
            "BLUEPRINT_POPO_ENTRY_REQUIRED",
            "the saved start full Agent popo_entry must be enabled and complete before POPO routing",
            details={
                "blueprintId": str(document.get("id") or ""),
                "startNodeId": start_node_id,
                "missing": ["enabled"] if not entry.get("enabled") else missing,
            },
        )
    return entry


def blueprint_slot_pool_key(
    *,
    project_dir: Path,
    source: str,
    source_binding: str,
    blueprint_structure_id: str,
) -> str:
    parts = [
        str(validate_project_dir(project_dir)).casefold(),
        str(source or "ui").strip().lower(),
        str(source_binding or "").strip(),
        str(blueprint_structure_id or "").strip(),
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]


def blueprint_session_key_for_pool(
    *,
    pool_key: str,
    source: str,
    popo_user_id: str = "",
    popo_session_id: str = "",
    popo_group_id: str = "",
) -> str:
    digest = blueprint_session_key_digest_for_pool(
        pool_key=pool_key,
        source=source,
        popo_user_id=popo_user_id,
        popo_session_id=popo_session_id,
        popo_group_id=popo_group_id,
    )
    if str(source or "").strip().lower() == "popo":
        label = blueprint_popo_session_key_label(
            popo_user_id=popo_user_id,
            popo_session_id=popo_session_id,
            popo_group_id=popo_group_id,
        )
        return f"{BLUEPRINT_POPO_SESSION_PREFIX}{label}_{digest}"
    return "bps_" + digest


def blueprint_popo_named_session_key(
    *,
    blueprint_name: str,
    blueprint_id: str = "",
    popo_user_id: str = "",
    popo_session_id: str = "",
    popo_group_id: str = "",
) -> str:
    label = blueprint_popo_session_key_label(
        popo_user_id=popo_user_id,
        popo_session_id=popo_session_id,
        popo_group_id=popo_group_id,
    )
    name = _blueprint_session_name_slug(blueprint_name, fallback=blueprint_id)
    return f"{BLUEPRINT_POPO_SESSION_PREFIX}{label}+{name}"


def blueprint_legacy_session_key_for_pool(
    *,
    pool_key: str,
    source: str,
    popo_user_id: str = "",
    popo_session_id: str = "",
    popo_group_id: str = "",
) -> str:
    return "bps_" + blueprint_session_key_digest_for_pool(
        pool_key=pool_key,
        source=source,
        popo_user_id=popo_user_id,
        popo_session_id=popo_session_id,
        popo_group_id=popo_group_id,
    )


def blueprint_session_key_digest_for_pool(
    *,
    pool_key: str,
    source: str,
    popo_user_id: str = "",
    popo_session_id: str = "",
    popo_group_id: str = "",
) -> str:
    parts = [
        str(pool_key or "").strip(),
        str(source or "ui").strip().lower(),
        str(popo_user_id or "").strip(),
        str(popo_session_id or "").strip(),
        str(popo_group_id or "").strip(),
    ]
    raw = "\x1f".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def blueprint_popo_session_key_label(
    *,
    popo_user_id: str = "",
    popo_session_id: str = "",
    popo_group_id: str = "",
) -> str:
    user = _blueprint_session_label_slug(popo_user_id)
    group = _blueprint_session_label_slug(popo_group_id)
    session = _blueprint_session_label_slug(popo_session_id)
    if group and user:
        return f"group-{group[:32]}-user-{user[:32]}".strip("-")[:96]
    if user:
        return user[:96]
    if group:
        return f"group-{group}"[:96]
    if session:
        return f"session-{session}"[:96]
    return "unknown"


def blueprint_popo_session_display_name(
    *,
    popo_user_id: str = "",
    popo_session_id: str = "",
    popo_group_id: str = "",
) -> str:
    user = str(popo_user_id or "").strip()
    group = str(popo_group_id or "").strip()
    session = str(popo_session_id or "").strip()
    if group and user:
        return f"POPO {user} @ {group}"
    if user:
        return f"POPO {user}"
    if group:
        return f"POPO group {group}"
    if session:
        return f"POPO session {session}"
    return "POPO session"


def blueprint_session_key(
    *,
    project_dir: Path,
    blueprint_id: str,
    blueprint_structure_id: str,
    source: str,
    popo_user_id: str = "",
    popo_session_id: str = "",
    popo_group_id: str = "",
) -> str:
    pool_key = blueprint_slot_pool_key(
        project_dir=project_dir,
        source=source,
        source_binding=validate_blueprint_id(blueprint_id),
        blueprint_structure_id=blueprint_structure_id,
    )
    return blueprint_session_key_for_pool(
        pool_key=pool_key,
        source=source,
        popo_user_id=popo_user_id,
        popo_session_id=popo_session_id,
        popo_group_id=popo_group_id,
    )


def document_start_node_id(document: Dict[str, Any]) -> str:
    runtime = document.get("runtime", {})
    if not isinstance(runtime, dict):
        return ""
    return str(runtime.get("start_node_id") or runtime.get("startNodeId") or "").strip()


def normalize_document(data: Dict[str, Any], *, fallback_id: Optional[str] = None) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise BlueprintServiceError("INVALID_DOCUMENT", "blueprint document must be a JSON object")
    blueprint_id = validate_blueprint_id(str(data.get("id") or fallback_id or DEFAULT_BLUEPRINT_ID))
    graph = data.get("graph")
    if not isinstance(graph, dict):
        raise BlueprintServiceError("INVALID_DOCUMENT", "blueprint document graph must be a JSON object")
    ui = data.get("ui", {})
    if not isinstance(ui, dict):
        raise BlueprintServiceError("INVALID_DOCUMENT", "blueprint document ui must be a JSON object")
    runtime = data.get("runtime", {})
    if runtime is None:
        runtime = {}
    if not isinstance(runtime, dict):
        raise BlueprintServiceError("INVALID_DOCUMENT", "blueprint document runtime must be a JSON object")
    start_node_id = str(runtime.get("start_node_id") or runtime.get("startNodeId") or "").strip()
    schema_version = int(data.get("schema_version", 1))
    if schema_version != 1:
        raise BlueprintServiceError("INVALID_DOCUMENT", "unsupported blueprint document schema_version")
    legacy_popo_entry = normalize_popo_entry(runtime.get("popo_entry") or runtime.get("popoEntry"))
    normalized_graph = dict(graph)
    agent_nodes_raw = normalized_graph.get("agent_nodes", {})
    if isinstance(agent_nodes_raw, dict):
        agent_nodes: Dict[str, Any] = {}
        agent_entries_with_values = 0
        for node_id, raw_node in agent_nodes_raw.items():
            if not isinstance(raw_node, dict):
                agent_nodes[node_id] = raw_node
                continue
            node = dict(raw_node)
            if _agent_node_type(node) == "agent":
                entry = _agent_node_popo_entry(node)
                if popo_entry_has_values(entry):
                    agent_entries_with_values += 1
                node["popo_entry"] = entry
            else:
                node.pop("popo_entry", None)
                node.pop("popoEntry", None)
            agent_nodes[node_id] = node
        if (
            popo_entry_has_values(legacy_popo_entry)
            and start_node_id
            and agent_entries_with_values == 0
            and isinstance(agent_nodes.get(start_node_id), dict)
            and _agent_node_type(agent_nodes[start_node_id]) == "agent"
        ):
            migrated_start = dict(agent_nodes[start_node_id])
            migrated_start["popo_entry"] = legacy_popo_entry
            agent_nodes[start_node_id] = migrated_start
        normalized_graph["agent_nodes"] = agent_nodes
    return {
        "schema_version": 1,
        "id": blueprint_id,
        "name": str(data.get("name") or DEFAULT_BLUEPRINT_NAME),
        "graph": normalized_graph,
        "ui": ui,
        "runtime": {
            "start_node_id": start_node_id,
            "popo_entry": normalize_popo_entry(),
        },
    }


def default_blueprint_document(project_dir: Path, blueprint_id: str, name: str) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "id": validate_blueprint_id(blueprint_id),
        "name": str(name or DEFAULT_BLUEPRINT_NAME),
        "graph": {
            "terminal_nodes": {},
            "route_nodes": {},
            "prompt_nodes": {},
            "script_nodes": {},
            "common_nodes": {},
            "agent_nodes": {
                "planner": {
                    "node_id": "planner",
                    "node_type": "agent",
                    "agent_id": "agent-planner",
                    "prompt": "Break down the user goal and dispatch implementation work.",
                    "popo_entry": normalize_popo_entry(),
                    "write_scope": ["shared/reports/planning/**"],
                },
                "coder": {
                    "node_id": "coder",
                    "node_type": "worker_agent",
                    "agent_id": "agent-coder",
                    "prompt": "Implement the requested changes.",
                    "write_scope": ["src/**"],
                    "artifact_scope": ["shared/artifacts/code/**"],
                },
                "review": {
                    "node_id": "review",
                    "node_type": "worker_agent",
                    "agent_id": "agent-review",
                    "prompt": "Review implementation output and identify required fixes.",
                    "write_scope": ["shared/reports/review/**"],
                },
                "summary": {
                    "node_id": "summary",
                    "node_type": "worker_agent",
                    "agent_id": "agent-summary",
                    "prompt": "Summarize the run and prepare final records.",
                    "write_scope": ["shared/reports/**"],
                },
            },
            "edges": [
                {"from": "planner", "to": "coder", "edge_type": "exec"},
                {"from": "coder", "to": "review", "edge_type": "exec"},
                {"from": "review", "to": "summary", "edge_type": "exec"},
            ],
        },
        "ui": {
            "config": {
                "python_path": sys.executable,
                "project_workdir": str(project_dir),
                "skill_dir": "",
                "rule_dir": "",
            },
            "nodes": {
                "planner": {"x": 0, "y": 96},
                "coder": {"x": 240, "y": 96},
                "review": {"x": 480, "y": 96},
                "summary": {"x": 720, "y": 96},
            },
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
        "runtime": {
            "start_node_id": "planner",
            "popo_entry": normalize_popo_entry(),
        },
    }


def _slug_blueprint_id(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip().lower()).strip("-._")
    return slug or DEFAULT_BLUEPRINT_ID


def _blueprint_session_label_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip().lower()).strip("-._")
    return slug


def _blueprint_session_name_slug(value: str, *, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    result: list[str] = []
    pending_dash = False
    for char in text:
        if char.isspace():
            pending_dash = bool(result)
            continue
        if char.isalnum() or char in "._-":
            if pending_dash and result and result[-1] != "-":
                result.append("-")
            result.append(char)
            pending_dash = False
        else:
            pending_dash = bool(result)
    slug = "".join(result).strip("-._")
    if not slug:
        slug = _slug_blueprint_id(fallback)
    return slug[:96].strip("-._") or DEFAULT_BLUEPRINT_ID


def _valid_blueprint_session_name_slug(value: str) -> bool:
    text = str(value or "").strip()
    return 0 < len(text) <= 160 and all(char.isalnum() or char in "._-" for char in text)


def coerce_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise BlueprintServiceError("BAD_REQUEST", f"{field_name} must be a list")
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_plan_payload(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise BlueprintServiceError("BAD_START_PLAN", "plan must be a complete start plan JSON object")
    plan = dict(value)
    aliases = {
        "agentDescriptions": "agent_descriptions",
        "startNodes": "start_nodes",
        "runPolicy": "run_policy",
    }
    for source_key, target_key in aliases.items():
        if source_key in plan and target_key not in plan:
            plan[target_key] = plan.pop(source_key)
    return plan


def blueprint_runtime_start_node_ids(graph: Any) -> list[str]:
    return sorted(
        str(node_id)
        for node_id, node in getattr(graph, "agent_nodes", {}).items()
        if str(getattr(node, "node_type", "worker_agent")) == "agent"
    )


def start_plan_validation_context(graph: Any) -> Dict[str, Any]:
    return {
        "required_start_groups": graph.required_start_groups(),
        "valid_start_nodes": blueprint_runtime_start_node_ids(graph),
        "tick_source_allowed": graph.has_tick_source(),
    }


def default_start_plan_for_graph(graph: Any, task: str, start_nodes: list[str]) -> Dict[str, Any]:
    descriptions: Dict[str, str] = {}
    for node_id, node in sorted(graph.agent_nodes.items()):
        prompt = str(getattr(node, "prompt", "") or "").strip()
        agent_id = str(getattr(node, "agent_id", "") or "").strip()
        if prompt and agent_id:
            descriptions[node_id] = f"{agent_id}: {prompt}"
        else:
            descriptions[node_id] = prompt or agent_id or node_id

    task_text = str(task).strip()
    return {
        "user_goal": task_text,
        "agent_descriptions": descriptions,
        "start_nodes": list(start_nodes),
        "tasks": {
            node_id: {
                "goal": task_text,
                "context_refs": [],
                "expected_output": "Complete the assigned blueprint work and report the result.",
                "acceptance": "The requested work is complete, or blockers are reported clearly.",
                "metadata": {"source": "gulicode-bp-plugin"},
            }
            for node_id in dict.fromkeys(start_nodes)
        },
        "run_policy": {
            "allow_parallel": True,
            "requires_confirmation": True,
            "source": "gulicode-bp-plugin",
        },
    }


def apply_start_plan_overrides(plan: Dict[str, Any], overrides: Any) -> Dict[str, Any]:
    if not isinstance(overrides, dict):
        raise BlueprintServiceError("BAD_REQUEST", "planOverrides must be a JSON object")
    allowed = {"user_goal", "agent_descriptions", "tasks", "run_policy"}
    rejected = sorted(str(key) for key in overrides if str(key) not in allowed)
    if rejected:
        raise BlueprintServiceError(
            "START_PLAN_OVERRIDE_REJECTED",
            "planOverrides may only set user_goal, agent_descriptions, tasks, and run_policy",
            details={"rejected": rejected},
        )
    next_plan = dict(plan)
    for key, value in overrides.items():
        normalized_key = str(key)
        if normalized_key == "run_policy":
            if not isinstance(value, dict):
                raise BlueprintServiceError("BAD_REQUEST", "planOverrides.run_policy must be an object")
            merged = dict(next_plan.get("run_policy", {}))
            merged.update(value)
            next_plan["run_policy"] = merged
            continue
        next_plan[normalized_key] = value
    return next_plan


def document_with_project_workdir(
    document: Dict[str, Any],
    project_workdir: Path,
    *,
    blueprint_id: Optional[str] = None,
) -> Dict[str, Any]:
    normalized = normalize_document(document, fallback_id=blueprint_id)
    if blueprint_id is not None:
        normalized["id"] = validate_blueprint_id(blueprint_id)
    ui = dict(normalized["ui"])
    raw_config = ui.get("config", {})
    config = dict(raw_config) if isinstance(raw_config, dict) else {}
    config["project_workdir"] = str(project_workdir)
    ui["config"] = config
    return {
        **normalized,
        "ui": ui,
    }


def blueprint_common_config_issues(document: Dict[str, Any]) -> list[Dict[str, str]]:
    config = _blueprint_common_config(document)
    required = {"python_path", "project_workdir"}

    issues: list[Dict[str, str]] = []
    for field_name in ("python_path", "project_workdir"):
        raw_value = config.get(field_name) if isinstance(config, dict) else None
        value = raw_value.strip() if isinstance(raw_value, str) else ""
        if not value:
            if field_name in required:
                issues.append({"field": field_name, "reason": "missing"})
            continue
        if not _is_absolute_blueprint_path(value):
            issues.append({"field": field_name, "reason": "not_absolute"})
    skill_dirs = _configured_path_strings_from_config(config, "skill_dirs", "skill_dir")
    if any(not _is_absolute_blueprint_path(value) for value in skill_dirs):
        issues.append({"field": "skill_dir", "reason": "not_absolute"})
    rule_dirs = _configured_path_strings_from_config(config, "rule_dirs", "rule_dir")
    if _document_uses_rule_dir(document) and not rule_dirs:
        issues.append({"field": "rule_dir", "reason": "missing"})
    elif any(not _is_absolute_blueprint_path(value) for value in rule_dirs):
        issues.append({"field": "rule_dir", "reason": "not_absolute"})
    return issues


def document_with_common_config_paths(document: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_document(document)
    config = _blueprint_common_config(normalized)
    project_workdir = str(config.get("project_workdir") or "").strip()
    rule_dirs = _configured_rule_dirs_from_config(config)
    graph = dict(normalized["graph"])
    agent_nodes = graph.get("agent_nodes")
    if isinstance(agent_nodes, dict):
        updated_nodes: Dict[str, Any] = {}
        for node_id, raw_node in agent_nodes.items():
            if not isinstance(raw_node, dict):
                updated_nodes[node_id] = raw_node
                continue
            node = dict(raw_node)
            if project_workdir:
                node["cwd"] = project_workdir
            if rule_dirs and isinstance(node.get("rule_paths"), list):
                node["rule_paths"] = [
                    _rule_path_from_common_config(raw_rule_path, rule_dirs)
                    for raw_rule_path in node["rule_paths"]
                ]
            updated_nodes[node_id] = node
        graph["agent_nodes"] = updated_nodes
    return {
        **normalized,
        "graph": graph,
    }


def _blueprint_common_config(document: Dict[str, Any]) -> Dict[str, Any]:
    ui = document.get("ui", {})
    if not isinstance(ui, dict):
        return {}
    config = ui.get("config", {})
    return config if isinstance(config, dict) else {}


def _document_agent_nodes(document: Dict[str, Any]) -> Dict[str, Any]:
    graph = document.get("graph", {})
    if not isinstance(graph, dict):
        return {}
    agent_nodes = graph.get("agent_nodes", {})
    return agent_nodes if isinstance(agent_nodes, dict) else {}


def _document_uses_rule_dir(document: Dict[str, Any]) -> bool:
    for raw_node in _document_agent_nodes(document).values():
        if not isinstance(raw_node, dict):
            continue
        rule_paths = raw_node.get("rule_paths")
        if isinstance(rule_paths, list) and any(str(item).strip() for item in rule_paths):
            return True
    return False


def _is_absolute_blueprint_path(value: str) -> bool:
    raw = str(value).strip()
    if not raw:
        return False
    return Path(raw).expanduser().is_absolute() or bool(WINDOWS_ABSOLUTE_PATH_RE.match(raw))


def _rule_path_from_common_config(raw_rule_path: Any, rule_dirs: Sequence[Path]) -> str:
    value = str(raw_rule_path).strip()
    if not value:
        return value
    roots = [_resolve_catalog_dir(path) for path in rule_dirs if str(path).strip()]
    source = Path(value).expanduser()
    if not _is_absolute_blueprint_path(value):
        if not roots:
            return value
        source = roots[0] / value
    source = source.resolve()
    if roots and not _path_is_under_any(source, roots):
        raise BlueprintServiceError(
            "BLUEPRINT_RULE_PATH_OUTSIDE_CONFIG",
            f"rule path is outside configured rule_dirs: {value}",
            details={"rulePath": value, "ruleDirs": [str(root) for root in roots]},
        )
    return str(source)


class DesktopBlueprintHTTPServer:
    """Small HTTP server wrapper used by Electron and tests."""

    def __init__(
        self,
        service: Optional[DesktopBlueprintService] = None,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        token: Optional[str] = None,
    ) -> None:
        self.service = service or DesktopBlueprintService()
        self.host = host
        self.port = port
        self.token = token or secrets.token_urlsafe(24)
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("desktop blueprint service is not started")
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/blueprint"

    def start(self) -> None:
        if self._server is not None:
            return
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def _write_json(self, payload: Dict[str, Any], *, status: int = 200) -> None:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path.rstrip("/") != "/blueprint":
                    self._write_json({"ok": False, "code": "NOT_FOUND", "error": "not found"}, status=404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise BlueprintServiceError("BAD_REQUEST", "request body must be a JSON object")
                    if payload.get("token") != owner.token:
                        raise BlueprintServiceError("INVALID_TOKEN", "invalid desktop blueprint token", status=403)
                    response = owner.service.handle_request(payload)
                    status = 200
                except BlueprintServiceError as exc:
                    response = {"ok": False, "code": exc.code, "error": str(exc)}
                    if exc.details:
                        response["details"] = exc.details
                    status = exc.status
                except Exception as exc:  # pragma: no cover - defensive boundary
                    response = {"ok": False, "code": "INTERNAL_ERROR", "error": str(exc)}
                    status = 500
                self._write_json(response, status=status)

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path.rstrip("/") != "/agent-stream":
                    self._write_json({"ok": False, "code": "NOT_FOUND", "error": "not found"}, status=404)
                    return
                try:
                    query = parse_qs(parsed.query)
                    run_id = owner.service.accept_stream_token(
                        str((query.get("streamToken") or [""])[0])
                    )
                    key = self.headers.get("Sec-WebSocket-Key", "")
                    if self.headers.get("Upgrade", "").lower() != "websocket" or not key:
                        raise BlueprintServiceError("BAD_REQUEST", "websocket upgrade required")
                    accept = base64.b64encode(
                        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
                    ).decode("ascii")
                    self.send_response(101, "Switching Protocols")
                    self.send_header("Upgrade", "websocket")
                    self.send_header("Connection", "Upgrade")
                    self.send_header("Sec-WebSocket-Accept", accept)
                    self.end_headers()

                    def send(event: Dict[str, Any]) -> None:
                        _write_ws_text(self.wfile, json.dumps(event, ensure_ascii=False, default=str))

                    owner.service.stream_agent_events(
                        run_id,
                        cursor=int((query.get("cursor") or ["0"])[0] or 0),
                        send=send,
                    )
                except BlueprintServiceError as exc:
                    if not self.wfile.closed:
                        self._write_json({"ok": False, "code": exc.code, "error": str(exc)}, status=exc.status)
                except (BrokenPipeError, ConnectionError, OSError):
                    return
                except Exception as exc:  # pragma: no cover - defensive boundary
                    if not self.wfile.closed:
                        self._write_json({"ok": False, "code": "INTERNAL_ERROR", "error": str(exc)}, status=500)

            def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
                return

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self.service.close()
        self._server = None
        self._thread = None


def serve_forever(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Run the GuLiCode desktop blueprint service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--token", default=None)
    args = parser.parse_args(argv)
    server = DesktopBlueprintHTTPServer(host=args.host, port=args.port, token=args.token)
    server.start()
    print(
        json.dumps({"ok": True, "url": server.url, "token": server.token}, ensure_ascii=False),
        flush=True,
    )
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()


def main(argv: Optional[list[str]] = None) -> None:
    serve_forever(argv)


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
