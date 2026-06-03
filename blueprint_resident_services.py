"""Global resident Python services for GuLiCode Blueprint."""

from __future__ import annotations

import argparse
import ast
import asyncio
import importlib.util
import inspect
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError


RESIDENT_SERVICES_DIRNAME = "resident_services"
RESIDENT_SERVICE_API_FILENAME = "gulicode_blueprint_service.py"
RESIDENT_SERVICE_STATE_DIRNAME = ".state"
RESIDENT_SERVICE_LOG_DIRNAME = ".logs"
PYRIGHT_CONFIG_FILENAME = "pyrightconfig.json"
VSCODE_SETTINGS_DIR = ".vscode"
VSCODE_SETTINGS_FILENAME = "settings.json"
RESIDENT_SERVICE_WORKSPACE_FILENAME = "blueprint-resident-services.code-workspace"
SUPPORTED_JSON_TYPES = {"int", "float", "str", "bool", "dict", "list", "Any"}
SERVICE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

RESIDENT_SERVICE_API_SHIM = '''"""Public helpers for GuLiCode Blueprint resident services.

Resident service files import these decorators from this local module so
editor navigation stays inside the resident service workspace.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def blueprint_service(
    cls: type[Any] | None = None,
    *,
    name: str | None = None,
    title: str | None = None,
    description: str = "",
) -> Callable[[type[Any]], type[Any]] | type[Any]:
    """Mark a class as a Blueprint resident service."""

    def decorate(target: type[Any]) -> type[Any]:
        target.__blueprint_service__ = {
            "name": name,
            "title": title,
            "description": description,
        }
        return target

    if cls is None:
        return decorate
    return decorate(cls)


def service_method(
    func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str = "",
) -> Callable[..., Any]:
    """Expose a method on a Blueprint resident service."""

    def decorate(target: Callable[..., Any]) -> Callable[..., Any]:
        target.__blueprint_service_method__ = {
            "name": name,
            "description": description,
        }
        return target

    if func is None:
        return decorate
    return decorate(func)
'''


@dataclass
class ResidentServiceParameter:
    name: str
    type: str = "Any"
    required: bool = True

    def __post_init__(self) -> None:
        self.name = str(self.name).strip()
        if not self.name:
            raise ValueError("resident service parameter name must be non-empty")
        self.type = _normalize_json_type(self.type)
        self.required = bool(self.required)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "type": self.type, "required": self.required}


@dataclass
class ResidentServiceMethod:
    name: str
    python_name: str
    description: str = ""
    parameters: List[ResidentServiceParameter] = field(default_factory=list)
    returns: str = "Any"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "python_name": self.python_name,
            "description": self.description,
            "parameters": [param.to_dict() for param in self.parameters],
            "returns": {"type": _normalize_json_type(self.returns)},
        }


@dataclass
class ResidentServiceCatalogItem:
    service_name: str
    title: str
    description: str
    module_path: str
    class_name: str
    methods: List[ResidentServiceMethod] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_name": self.service_name,
            "title": self.title,
            "description": self.description,
            "module_path": self.module_path,
            "class_name": self.class_name,
            "methods": [method.to_dict() for method in self.methods],
        }


@dataclass
class ResidentServiceDiagnostic:
    path: str
    message: str
    line: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"path": self.path, "message": self.message}
        if self.line is not None:
            data["line"] = self.line
        return data


def blueprint_service(
    cls: Optional[type[Any]] = None,
    *,
    name: Optional[str] = None,
    title: Optional[str] = None,
    description: str = "",
) -> Callable[[type[Any]], type[Any]] | type[Any]:
    """Mark a Python class as a GuLiCode Blueprint resident service."""

    def decorate(target: type[Any]) -> type[Any]:
        setattr(
            target,
            "__blueprint_service__",
            {"name": name, "title": title, "description": description},
        )
        return target

    if cls is None:
        return decorate
    return decorate(cls)


def service_method(
    func: Optional[Callable[..., Any]] = None,
    *,
    name: Optional[str] = None,
    description: str = "",
) -> Callable[..., Any]:
    """Expose a resident service method to Blueprint agents."""

    def decorate(target: Callable[..., Any]) -> Callable[..., Any]:
        setattr(
            target,
            "__blueprint_service_method__",
            {"name": name, "description": description},
        )
        return target

    if func is None:
        return decorate
    return decorate(func)


def resident_services_dir(data_dir: Path) -> Path:
    return Path(data_dir).expanduser().resolve() / RESIDENT_SERVICES_DIRNAME


def ensure_resident_services_dir(data_dir: Path) -> Path:
    root = resident_services_dir(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_resident_services_dev_environment(data_dir: Path) -> Dict[str, Any]:
    root = ensure_resident_services_dir(data_dir)
    api_path = root / RESIDENT_SERVICE_API_FILENAME
    pyright_path = root / PYRIGHT_CONFIG_FILENAME
    vscode_dir = root / VSCODE_SETTINGS_DIR
    vscode_settings_path = vscode_dir / VSCODE_SETTINGS_FILENAME
    workspace_path = root / RESIDENT_SERVICE_WORKSPACE_FILENAME

    _write_text_if_changed(api_path, RESIDENT_SERVICE_API_SHIM)
    _write_json_if_changed(
        pyright_path,
        _merged_pyright_config(_read_json_object(pyright_path)),
    )
    vscode_dir.mkdir(parents=True, exist_ok=True)
    _write_json_if_changed(
        vscode_settings_path,
        _merged_vscode_settings(_read_json_object(vscode_settings_path)),
    )
    _write_json_if_changed(
        workspace_path,
        {
            "folders": [{"name": "Blueprint Resident Services", "path": "."}],
            "settings": {
                "python.analysis.extraPaths": ["."],
                "python.defaultInterpreterPath": sys.executable,
            },
        },
    )
    return {
        "service_dir": str(root.resolve()),
        "service_api_module": "gulicode_blueprint_service",
        "service_api_path": str(api_path.resolve()),
        "pyright_config": str(pyright_path.resolve()),
        "vscode_settings": str(vscode_settings_path.resolve()),
        "workspace_file": str(workspace_path.resolve()),
        "python": sys.executable,
    }


def discover_resident_services(data_dir: Path) -> Dict[str, Any]:
    root = ensure_resident_services_dir(data_dir)
    dev_environment = ensure_resident_services_dev_environment(data_dir)
    items: List[ResidentServiceCatalogItem] = []
    diagnostics: List[ResidentServiceDiagnostic] = []

    for path in sorted(root.rglob("*.py")):
        if not path.is_file():
            continue
        rel_path = _relative_module_path(root, path)
        if rel_path == RESIDENT_SERVICE_API_FILENAME or rel_path.startswith(f"{RESIDENT_SERVICE_STATE_DIRNAME}/"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            diagnostics.append(ResidentServiceDiagnostic(rel_path, exc.msg, exc.lineno))
            continue
        except UnicodeDecodeError as exc:
            diagnostics.append(ResidentServiceDiagnostic(rel_path, str(exc)))
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                item, node_diagnostics = _catalog_item_from_class(root, rel_path, node)
                diagnostics.extend(node_diagnostics)
                if item is not None:
                    items.append(item)

    states = _state_summary_by_service(root, items)
    return {
        "service_dir": str(root),
        "dev_environment": dev_environment,
        "services": [
            {
                **item.to_dict(),
                **states.get(item.service_name, {}),
            }
            for item in items
        ],
        "diagnostics": [diag.to_dict() for diag in diagnostics],
    }


def create_resident_service(data_dir: Path, name: str, description: str = "") -> Dict[str, Any]:
    display_name = str(name or "").strip()
    if not display_name:
        raise ValueError("resident service name must be non-empty")
    service_name = _service_name(display_name)
    display_description = str(description or "").strip()

    root = ensure_resident_services_dir(data_dir)
    ensure_resident_services_dev_environment(data_dir)
    module_path = _unique_service_module_path(root, service_name)
    path = root / module_path
    class_name = _service_class_name(service_name)
    template = "\n".join(
        [
            "from gulicode_blueprint_service import blueprint_service, service_method",
            "",
            "",
            f"@blueprint_service(name={json.dumps(service_name)}, description={json.dumps(display_description)})",
            f"class {class_name}:",
            "    def on_start(self) -> None:",
            "        pass",
            "",
            "    def on_stop(self) -> None:",
            "        pass",
            "",
            '    @service_method(name="echo", description="Echo a message")',
            "    def echo(self, message: str) -> dict:",
            '        return {"message": message}',
            "",
        ]
    )
    path.write_text(template, encoding="utf-8")
    discovered = discover_resident_services(data_dir)
    service = next(
        (
            item
            for item in discovered["services"]
            if item.get("module_path") == module_path and item.get("service_name") == service_name
        ),
        None,
    )
    return {
        "service_dir": discovered["service_dir"],
        "dev_environment": discovered.get("dev_environment"),
        "file_path": str(path.resolve()),
        "module_path": module_path,
        "service_name": service_name,
        "service": service,
        "diagnostics": discovered["diagnostics"],
    }


class ResidentServiceManager:
    """Discover, run, and call global resident services."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir).expanduser().resolve()

    @property
    def root(self) -> Path:
        return ensure_resident_services_dir(self.data_dir)

    def discover(self) -> Dict[str, Any]:
        return discover_resident_services(self.data_dir)

    def create(self, name: str, description: str = "") -> Dict[str, Any]:
        return create_resident_service(self.data_dir, name, description)

    def docs(self, service_name: str) -> Dict[str, Any]:
        item = self._catalog_item(service_name)
        if item is None:
            return {
                "ok": False,
                "code": "RESIDENT_SERVICE_NOT_FOUND",
                "error": f"resident service not found: {service_name}",
                "service_name": str(service_name),
            }
        return {
            "ok": True,
            "service": item.to_dict(),
            "methods": [method.to_dict() for method in item.methods],
        }

    def start(self, service_name: str, *, wait_seconds: float = 10.0) -> Dict[str, Any]:
        item = self._require_catalog_item(service_name)
        state = self._state_for(item.service_name)
        if _state_is_running(state):
            return {"ok": True, "alreadyRunning": True, "service": self._service_with_state(item, state)}

        root = self.root
        state_path = self._state_path(item.service_name)
        log_path = self._log_path(item.service_name)
        token = secrets.token_urlsafe(24)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            state_path.unlink()
        except FileNotFoundError:
            pass

        package_parent = Path(__file__).resolve().parent.parent
        env = dict(os.environ)
        existing_pythonpath = env.get("PYTHONPATH", "")
        pythonpath_parts = [str(package_parent), str(root)]
        if existing_pythonpath:
            pythonpath_parts.append(existing_pythonpath)
        env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
        env["PYTHONUNBUFFERED"] = "1"

        command = [
            sys.executable,
            "-m",
            "multi_agent_tcp.blueprint_resident_services",
            "run",
            "--data-dir",
            str(self.data_dir),
            "--service-name",
            item.service_name,
            "--state-path",
            str(state_path),
            "--log-path",
            str(log_path),
            "--token",
            token,
        ]
        popen_kwargs: Dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": open(log_path, "ab"),
            "stderr": subprocess.STDOUT,
            "cwd": str(root),
            "env": env,
            "close_fds": True,
        }
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
        else:
            popen_kwargs["start_new_session"] = True
        stdout_handle = popen_kwargs["stdout"]
        try:
            process = subprocess.Popen(command, **popen_kwargs)
        finally:
            try:
                stdout_handle.close()
            except Exception:
                pass

        deadline = time.time() + max(0.1, float(wait_seconds))
        last_state: Dict[str, Any] = {}
        while time.time() < deadline:
            if state_path.exists():
                last_state = _read_json_object(state_path)
                if str(last_state.get("status") or "") == "running":
                    return {
                        "ok": True,
                        "alreadyRunning": False,
                        "service": self._service_with_state(item, last_state),
                    }
            if process.poll() is not None:
                break
            time.sleep(0.05)

        if process.poll() is None:
            _terminate_process_tree(process.pid)
        return {
            "ok": False,
            "code": "RESIDENT_SERVICE_START_FAILED",
            "error": f"resident service failed to start: {item.service_name}",
            "service_name": item.service_name,
            "state": last_state,
            "logs": self.logs(item.service_name, limit=80).get("logs", ""),
        }

    def stop(self, service_name: str) -> Dict[str, Any]:
        item = self._require_catalog_item(service_name)
        state = self._state_for(item.service_name)
        pid = int(state.get("pid") or 0)
        was_running = _state_is_running(state)
        if was_running:
            _request_service_shutdown(state)
            deadline = time.time() + 2.0
            while time.time() < deadline and _pid_is_running(pid):
                time.sleep(0.05)
        if pid > 0 and _pid_is_running(pid):
            _terminate_process_tree(pid)
        stopped = {
            **state,
            "service_name": item.service_name,
            "status": "stopped",
            "stopped_at": time.time(),
            "log_path": str(self._log_path(item.service_name)),
        }
        self._write_state(item.service_name, stopped)
        return {"ok": True, "wasRunning": was_running, "service": self._service_with_state(item, stopped)}

    def logs(self, service_name: str, *, limit: int = 200) -> Dict[str, Any]:
        item = self._require_catalog_item(service_name)
        log_path = self._log_path(item.service_name)
        return {
            "ok": True,
            "service_name": item.service_name,
            "log_path": str(log_path),
            "logs": _tail_text(log_path, limit=max(1, int(limit or 200))),
        }

    def stop_all(self) -> Dict[str, Any]:
        stopped: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        for raw in self.discover().get("services", []):
            if not isinstance(raw, dict):
                continue
            service_name = str(raw.get("service_name") or "").strip()
            if not service_name:
                continue
            try:
                stopped.append(self.stop(service_name))
            except Exception as exc:
                errors.append({"service_name": service_name, "error": str(exc)})
        return {"ok": not errors, "stopped": stopped, "errors": errors}

    def call(self, service_name: str, method_name: str, arguments: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        item = self._catalog_item(service_name)
        if item is None:
            return {
                "ok": False,
                "code": "RESIDENT_SERVICE_NOT_FOUND",
                "error": f"resident service not found: {service_name}",
                "service_name": str(service_name),
            }
        state = self._state_for(item.service_name)
        if not _state_is_running(state):
            return {
                "ok": False,
                "code": "RESIDENT_SERVICE_NOT_RUNNING",
                "error": f"resident service is not running: {item.service_name}",
                "service_name": item.service_name,
                "status": str(state.get("status") or "stopped"),
            }
        if not isinstance(arguments, Mapping):
            return {
                "ok": False,
                "code": "BAD_ARGUMENTS",
                "error": "arguments must be a JSON object",
                "service_name": item.service_name,
            }
        payload = {
            "method_name": str(method_name),
            "arguments": dict(arguments or {}),
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urlrequest.Request(
            f"http://127.0.0.1:{int(state['port'])}/rpc",
            data=data,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {state.get('token') or ''}",
            },
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=20) as response:
                response_data = response.read().decode("utf-8")
                result = json.loads(response_data) if response_data else {}
        except HTTPError as exc:
            response_data = exc.read().decode("utf-8", errors="replace")
            try:
                result = json.loads(response_data)
            except Exception:
                result = {"ok": False, "code": "RESIDENT_SERVICE_HTTP_ERROR", "error": response_data}
        except (OSError, URLError) as exc:
            result = {"ok": False, "code": "RESIDENT_SERVICE_CALL_FAILED", "error": str(exc)}
        if isinstance(result, dict):
            result.setdefault("service_name", item.service_name)
            result.setdefault("method_name", str(method_name))
            return result
        return {
            "ok": False,
            "code": "RESIDENT_SERVICE_BAD_RESPONSE",
            "error": "resident service returned a non-object response",
            "service_name": item.service_name,
            "method_name": str(method_name),
        }

    def summary(self) -> List[Dict[str, Any]]:
        discovered = self.discover()
        services = discovered.get("services", [])
        if not isinstance(services, list):
            return []
        return [
            {
                "service_name": str(item.get("service_name") or ""),
                "title": str(item.get("title") or item.get("service_name") or ""),
                "description": str(item.get("description") or ""),
                "status": str(item.get("status") or "stopped"),
            }
            for item in services
            if isinstance(item, dict)
        ]

    def _catalog_item(self, service_name: str) -> Optional[ResidentServiceCatalogItem]:
        needle = str(service_name or "").strip()
        discovered = discover_resident_services(self.data_dir)
        for raw in discovered.get("services", []):
            if not isinstance(raw, dict):
                continue
            if str(raw.get("service_name") or "") == needle:
                return ResidentServiceCatalogItem(
                    service_name=str(raw.get("service_name") or ""),
                    title=str(raw.get("title") or raw.get("service_name") or ""),
                    description=str(raw.get("description") or ""),
                    module_path=str(raw.get("module_path") or ""),
                    class_name=str(raw.get("class_name") or ""),
                    methods=[
                        ResidentServiceMethod(
                            name=str(method.get("name") or ""),
                            python_name=str(method.get("python_name") or method.get("name") or ""),
                            description=str(method.get("description") or ""),
                            parameters=[
                                ResidentServiceParameter(
                                    str(param.get("name") or ""),
                                    str(param.get("type") or "Any"),
                                    bool(param.get("required", True)),
                                )
                                for param in method.get("parameters", [])
                                if isinstance(param, dict)
                            ],
                            returns=str((method.get("returns") or {}).get("type") if isinstance(method.get("returns"), dict) else method.get("returns") or "Any"),
                        )
                        for method in raw.get("methods", [])
                        if isinstance(method, dict)
                    ],
                )
        return None

    def _require_catalog_item(self, service_name: str) -> ResidentServiceCatalogItem:
        item = self._catalog_item(service_name)
        if item is None:
            raise ValueError(f"resident service not found: {service_name}")
        return item

    def _state_path(self, service_name: str) -> Path:
        return self.root / RESIDENT_SERVICE_STATE_DIRNAME / f"{_state_file_name(service_name)}.json"

    def _log_path(self, service_name: str) -> Path:
        return self.root / RESIDENT_SERVICE_LOG_DIRNAME / f"{_state_file_name(service_name)}.log"

    def _state_for(self, service_name: str) -> Dict[str, Any]:
        path = self._state_path(service_name)
        state = _read_json_object(path)
        if not state:
            return {
                "service_name": service_name,
                "status": "stopped",
                "log_path": str(self._log_path(service_name)),
            }
        if str(state.get("status") or "") == "running" and not _pid_is_running(int(state.get("pid") or 0)):
            state["status"] = "stale"
            state["stale_at"] = time.time()
            state["log_path"] = str(self._log_path(service_name))
            self._write_state(service_name, state)
        return state

    def _write_state(self, service_name: str, state: Mapping[str, Any]) -> None:
        path = self._state_path(service_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_if_changed(path, dict(state))

    def _service_with_state(self, item: ResidentServiceCatalogItem, state: Mapping[str, Any]) -> Dict[str, Any]:
        data = item.to_dict()
        data.update(
            {
                "status": str(state.get("status") or "stopped"),
                "pid": state.get("pid"),
                "port": state.get("port"),
                "started_at": state.get("started_at"),
                "stopped_at": state.get("stopped_at"),
                "log_path": str(state.get("log_path") or self._log_path(item.service_name)),
            }
        )
        return data


def run_resident_service_server(
    *,
    data_dir: Path,
    service_name: str,
    state_path: Path,
    log_path: Path,
    token: str,
) -> None:
    manager = ResidentServiceManager(data_dir)
    item = manager._require_catalog_item(service_name)
    root = ensure_resident_services_dir(data_dir)
    service_path = _resolve_service_path(root, item.module_path)
    sys.path.insert(0, str(root))
    module = _load_module_from_path(service_path, root)
    service_class = _service_class_from_module(module, item)
    service = service_class()
    method_map = _runtime_method_map(service)

    def call_lifecycle(name: str) -> None:
        hook = getattr(service, name, None)
        if callable(hook):
            value = hook()
            if inspect.isawaitable(value):
                asyncio.run(value)

    call_lifecycle("on_start")

    class Handler(BaseHTTPRequestHandler):
        def _write_json(self, payload: Dict[str, Any], *, status: int = 200) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:  # noqa: N802
            try:
                path = self.path.rstrip("/")
                if path == "/shutdown":
                    auth = self.headers.get("Authorization", "")
                    if auth != f"Bearer {token}":
                        self._write_json({"ok": False, "code": "INVALID_TOKEN", "error": "invalid resident service token"}, status=403)
                        return
                    self._write_json({"ok": True, "service_name": item.service_name, "status": "stopping"})
                    threading.Thread(target=server.shutdown, name="resident-service-shutdown", daemon=True).start()
                    return
                if path != "/rpc":
                    self._write_json({"ok": False, "code": "NOT_FOUND", "error": "not found"}, status=404)
                    return
                auth = self.headers.get("Authorization", "")
                if auth != f"Bearer {token}":
                    self._write_json({"ok": False, "code": "INVALID_TOKEN", "error": "invalid resident service token"}, status=403)
                    return
                length = int(self.headers.get("Content-Length", "0") or "0")
                payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                if not isinstance(payload, dict):
                    raise ValueError("request body must be a JSON object")
                method_name = str(payload.get("method_name") or "").strip()
                arguments = payload.get("arguments", {})
                if not isinstance(arguments, dict):
                    raise ValueError("arguments must be a JSON object")
                method = method_map.get(method_name)
                if method is None:
                    self._write_json(
                        {
                            "ok": False,
                            "code": "RESIDENT_SERVICE_METHOD_NOT_FOUND",
                            "error": f"resident service method not found: {method_name}",
                            "service_name": item.service_name,
                            "method_name": method_name,
                        },
                        status=404,
                    )
                    return
                value = method(**arguments)
                if inspect.isawaitable(value):
                    value = asyncio.run(value)
                self._write_json(
                    {
                        "ok": True,
                        "service_name": item.service_name,
                        "method_name": method_name,
                        "result": value,
                    }
                )
            except Exception as exc:
                traceback.print_exc()
                self._write_json(
                    {
                        "ok": False,
                        "code": "RESIDENT_SERVICE_EXCEPTION",
                        "error": str(exc),
                        "service_name": item.service_name,
                    },
                    status=500,
                )

        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    host, port = server.server_address[:2]
    _write_json_if_changed(
        state_path,
        {
            "service_name": item.service_name,
            "status": "running",
            "pid": os.getpid(),
            "host": host,
            "port": int(port),
            "token": token,
            "module_path": item.module_path,
            "class_name": item.class_name,
            "started_at": time.time(),
            "log_path": str(Path(log_path).resolve()),
        },
    )
    print(f"Resident service {item.service_name} listening on 127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        try:
            call_lifecycle("on_stop")
        finally:
            server.server_close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run a GuLiCode Blueprint resident service")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--data-dir", required=True)
    run_parser.add_argument("--service-name", required=True)
    run_parser.add_argument("--state-path", required=True)
    run_parser.add_argument("--log-path", required=True)
    run_parser.add_argument("--token", required=True)
    args = parser.parse_args(argv)
    if args.command == "run":
        try:
            run_resident_service_server(
                data_dir=Path(args.data_dir),
                service_name=str(args.service_name),
                state_path=Path(args.state_path),
                log_path=Path(args.log_path),
                token=str(args.token),
            )
            return 0
        except KeyboardInterrupt:
            return 0
        except Exception:
            traceback.print_exc()
            return 1
    return 2


def _catalog_item_from_class(
    root: Path,
    rel_path: str,
    node: ast.ClassDef,
) -> tuple[Optional[ResidentServiceCatalogItem], List[ResidentServiceDiagnostic]]:
    decorator = _decorator_named(node.decorator_list, "blueprint_service")
    if decorator is None:
        return None, []
    diagnostics: List[ResidentServiceDiagnostic] = []
    service_name = _decorator_string_kw(decorator, "name") or _snake_case(node.name)
    title = _decorator_string_kw(decorator, "title") or service_name
    description = _decorator_string_kw(decorator, "description") or ast.get_docstring(node) or ""
    if not SERVICE_NAME_RE.match(service_name):
        diagnostics.append(
            ResidentServiceDiagnostic(
                rel_path,
                f"resident service name {service_name!r} must match {SERVICE_NAME_RE.pattern}; using generated name",
                getattr(node, "lineno", None),
            )
        )
        service_name = _service_name(service_name)
    methods: List[ResidentServiceMethod] = []
    for child in node.body:
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        method_decorator = _decorator_named(child.decorator_list, "service_method")
        if method_decorator is None:
            continue
        methods.append(_method_from_ast(rel_path, child, method_decorator, diagnostics))
    return (
        ResidentServiceCatalogItem(
            service_name=service_name,
            title=title,
            description=description,
            module_path=rel_path,
            class_name=node.name,
            methods=methods,
        ),
        diagnostics,
    )


def _method_from_ast(
    rel_path: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    decorator: ast.AST,
    diagnostics: List[ResidentServiceDiagnostic],
) -> ResidentServiceMethod:
    method_name = _decorator_string_kw(decorator, "name") or node.name
    description = _decorator_string_kw(decorator, "description") or ast.get_docstring(node) or ""
    positional = list(node.args.posonlyargs) + list(node.args.args)
    if positional and positional[0].arg in {"self", "cls"}:
        positional = positional[1:]
    defaults = list(node.args.defaults)
    required_cutoff = len(positional) - len(defaults)
    parameters: List[ResidentServiceParameter] = []
    for index, arg in enumerate(positional):
        raw_type = _annotation_name(arg.annotation)
        parameter_type = _normalize_json_type(raw_type)
        if parameter_type == "Any" and raw_type not in {"Any", "typing.Any", "any"}:
            diagnostics.append(
                ResidentServiceDiagnostic(
                    rel_path,
                    f"unsupported parameter type {raw_type!r} on {node.name}.{arg.arg}; using Any",
                    getattr(arg, "lineno", getattr(node, "lineno", None)),
                )
            )
        parameters.append(ResidentServiceParameter(arg.arg, parameter_type, required=index < required_cutoff))
    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        raw_type = _annotation_name(arg.annotation)
        parameter_type = _normalize_json_type(raw_type)
        parameters.append(ResidentServiceParameter(arg.arg, parameter_type, required=default is None))
    return_type = _normalize_json_type(_annotation_name(node.returns))
    return ResidentServiceMethod(
        name=method_name,
        python_name=node.name,
        description=description,
        parameters=parameters,
        returns=return_type,
    )


def _decorator_named(decorators: Sequence[ast.AST], name: str) -> Optional[ast.AST]:
    for decorator in decorators:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id == name:
            return decorator
        if isinstance(target, ast.Attribute) and target.attr == name:
            return decorator
    return None


def _decorator_string_kw(decorator: ast.AST, name: str) -> str:
    if not isinstance(decorator, ast.Call):
        return ""
    for keyword in decorator.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant):
            return str(keyword.value.value or "").strip()
    return ""


def _annotation_name(annotation: ast.AST | None) -> str:
    if annotation is None:
        return "Any"
    raw = _raw_annotation_name(annotation)
    return _normalize_json_type(raw)


def _raw_annotation_name(annotation: ast.AST) -> str:
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute):
        base = _raw_annotation_name(annotation.value)
        return f"{base}.{annotation.attr}" if base else annotation.attr
    if isinstance(annotation, ast.Subscript):
        return _raw_annotation_name(annotation.value)
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return annotation.value
    return "Any"


def _normalize_json_type(value: Any) -> str:
    raw = str(value or "Any").strip()
    aliases = {
        "integer": "int",
        "number": "float",
        "string": "str",
        "boolean": "bool",
        "object": "dict",
        "array": "list",
        "typing.Any": "Any",
        "any": "Any",
    }
    raw = aliases.get(raw, raw)
    if raw.startswith("typing."):
        raw = raw.split(".", 1)[1]
    base = raw.split("[", 1)[0]
    if base in {"List", "Sequence", "MutableSequence", "tuple", "Tuple"}:
        return "list"
    if base in {"Dict", "Mapping", "MutableMapping"}:
        return "dict"
    return raw if raw in SUPPORTED_JSON_TYPES else "Any"


def _relative_module_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _state_file_name(service_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(service_name or "service")).strip("._") or "service"


def _service_name(value: str) -> str:
    raw = _snake_case(str(value or "service")).replace("-", "_")
    if not raw:
        raw = "service"
    if raw[0].isdigit():
        raw = f"service_{raw}"
    return raw


def _snake_case(value: str) -> str:
    raw = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", str(value or ""))
    raw = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw)
    raw = re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_").lower()
    raw = re.sub(r"_+", "_", raw)
    return raw


def _service_class_name(service_name: str) -> str:
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", service_name) if part]
    name = "".join(part[:1].upper() + part[1:] for part in parts) or "ResidentService"
    if name[0].isdigit():
        name = f"Service{name}"
    return name


def _unique_service_module_path(root: Path, service_name: str) -> str:
    stem = _service_name(service_name)
    candidate = f"{stem}.py"
    index = 2
    while (root / candidate).exists():
        candidate = f"{stem}_{index}.py"
        index += 1
    return candidate


def _resolve_service_path(root: Path, module_path: str) -> Path:
    normalized = str(module_path or "").replace("\\", "/").strip()
    parts = [part for part in normalized.split("/") if part]
    if (
        not normalized
        or normalized.startswith("/")
        or any(part == ".." for part in parts)
        or not normalized.endswith(".py")
    ):
        raise ValueError("resident service module_path must stay inside the service directory")
    target = root.joinpath(*parts).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("resident service module_path escapes the service directory") from exc
    return target


def _state_summary_by_service(root: Path, items: Sequence[ResidentServiceCatalogItem]) -> Dict[str, Dict[str, Any]]:
    summary: Dict[str, Dict[str, Any]] = {}
    for item in items:
        state_path = root / RESIDENT_SERVICE_STATE_DIRNAME / f"{_state_file_name(item.service_name)}.json"
        log_path = root / RESIDENT_SERVICE_LOG_DIRNAME / f"{_state_file_name(item.service_name)}.log"
        state = _read_json_object(state_path)
        if not state:
            summary[item.service_name] = {"status": "stopped", "log_path": str(log_path)}
            continue
        if str(state.get("status") or "") == "running" and not _pid_is_running(int(state.get("pid") or 0)):
            state["status"] = "stale"
            state["stale_at"] = time.time()
            _write_json_if_changed(state_path, state)
        summary[item.service_name] = {
            "status": str(state.get("status") or "stopped"),
            "pid": state.get("pid"),
            "port": state.get("port"),
            "started_at": state.get("started_at"),
            "stopped_at": state.get("stopped_at"),
            "log_path": str(state.get("log_path") or log_path),
        }
    return summary


def _runtime_method_map(service: Any) -> Dict[str, Callable[..., Any]]:
    methods: Dict[str, Callable[..., Any]] = {}
    for _, member in inspect.getmembers(service, predicate=callable):
        meta = getattr(member, "__blueprint_service_method__", None)
        if not isinstance(meta, dict):
            continue
        exposed = str(meta.get("name") or getattr(member, "__name__", "")).strip()
        if exposed:
            methods[exposed] = member
    return methods


def _service_class_from_module(module: Any, item: ResidentServiceCatalogItem) -> type[Any]:
    service_class = getattr(module, item.class_name, None)
    if isinstance(service_class, type):
        return service_class
    for _, candidate in inspect.getmembers(module, inspect.isclass):
        meta = getattr(candidate, "__blueprint_service__", None)
        if isinstance(meta, dict) and str(meta.get("name") or "") == item.service_name:
            return candidate
    raise ValueError(f"resident service class not found: {item.class_name}")


def _load_module_from_path(path: Path, root: Path) -> Any:
    module_name = f"_gulicode_resident_service_{uuid.uuid4().hex}"
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load resident service module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _state_is_running(state: Mapping[str, Any]) -> bool:
    return str(state.get("status") or "") == "running" and _pid_is_running(int(state.get("pid") or 0))


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.OpenProcess(0x00100000, False, wintypes.DWORD(pid))
            if not handle:
                return False
            kernel32.CloseHandle(handle)
            return True
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _terminate_process_tree(pid: int) -> None:
    if pid <= 0:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass


def _request_service_shutdown(state: Mapping[str, Any]) -> None:
    try:
        port = int(state.get("port") or 0)
    except Exception:
        port = 0
    token = str(state.get("token") or "")
    if port <= 0 or not token:
        return
    req = urlrequest.Request(
        f"http://127.0.0.1:{port}/shutdown",
        data=b"{}",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=1.0):
            return
    except Exception:
        return


def _tail_text(path: Path, *, limit: int) -> str:
    if not Path(path).exists():
        return ""
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-limit:])


def _read_json_object(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_text_if_changed(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            if path.read_text(encoding="utf-8") == text:
                return
        except UnicodeDecodeError:
            pass
    path.write_text(text, encoding="utf-8")


def _write_json_if_changed(path: Path, payload: Mapping[str, Any]) -> None:
    text = json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _write_text_if_changed(path, text)


def _merged_pyright_config(existing: Mapping[str, Any]) -> Dict[str, Any]:
    merged = dict(existing or {})
    extra_paths = list(merged.get("extraPaths") or [])
    if "." not in extra_paths:
        extra_paths.insert(0, ".")
    merged.update(
        {
            "extraPaths": extra_paths,
            "typeCheckingMode": merged.get("typeCheckingMode") or "basic",
        }
    )
    return merged


def _merged_vscode_settings(existing: Mapping[str, Any]) -> Dict[str, Any]:
    merged = dict(existing or {})
    extra_paths = list(merged.get("python.analysis.extraPaths") or [])
    if "." not in extra_paths:
        extra_paths.insert(0, ".")
    merged["python.analysis.extraPaths"] = extra_paths
    merged["python.defaultInterpreterPath"] = str(merged.get("python.defaultInterpreterPath") or sys.executable)
    return merged


if __name__ == "__main__":  # pragma: no cover - exercised by subprocess lifecycle tests
    raise SystemExit(main())
