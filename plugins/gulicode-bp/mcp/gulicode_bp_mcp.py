#!/usr/bin/env python
"""Codex MCP bridge for the GuLiCode Blueprint runtime."""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import parse_qs, urlparse

PLUGIN_ROOT = Path(os.environ.get("GULICODE_BP_PLUGIN_ROOT") or Path(__file__).resolve().parents[1]).expanduser().resolve()
RUNTIME_HOME = Path(os.environ.get("GULICODE_BP_RUNTIME_HOME") or PLUGIN_ROOT / ".runtime").expanduser().resolve()
RUNTIME_DATA_DIR = Path(os.environ.get("GULICODE_BP_DATA_DIR") or RUNTIME_HOME / "state").expanduser().resolve()


def _repo_fallback_disabled() -> bool:
    return os.environ.get("GULICODE_BP_DISABLE_REPO_FALLBACK", "").strip().lower() in {"1", "true", "yes"}


def _runtime_venv_python() -> Path:
    if sys.platform == "win32":
        return RUNTIME_HOME / "venv" / "Scripts" / "python.exe"
    return RUNTIME_HOME / "venv" / "bin" / "python"


def _same_python(left: Path, right: Path) -> bool:
    try:
        return left.resolve().samefile(right.resolve())
    except OSError:
        return str(left.resolve()).casefold() == str(right.resolve()).casefold()


def _maybe_reexec_runtime_python() -> None:
    if os.environ.get("GULICODE_BP_REPO_ROOT") and not _repo_fallback_disabled():
        return
    if os.environ.get("GULICODE_BP_RUNTIME_REEXECED") == "1":
        return
    runtime_python = _runtime_venv_python()
    if runtime_python.is_file() and not _same_python(Path(sys.executable), runtime_python):
        env = os.environ.copy()
        env.setdefault("GULICODE_BP_PLUGIN_ROOT", str(PLUGIN_ROOT))
        env.setdefault("GULICODE_BP_RUNTIME_HOME", str(RUNTIME_HOME))
        env.setdefault("GULICODE_BP_DATA_DIR", str(RUNTIME_DATA_DIR))
        env["GULICODE_BP_RUNTIME_REEXECED"] = "1"
        if sys.platform == "win32":
            raise SystemExit(subprocess.call([str(runtime_python), *sys.argv], env=env))
        os.execve(str(runtime_python), [str(runtime_python), *sys.argv], env)
    if _repo_fallback_disabled() and not runtime_python.is_file():
        raise RuntimeError(
            "gulicode-bp standalone runtime is missing. Reinstall or repair the plugin with "
            "`python plugins\\gulicode-bp\\scripts\\install_personal_plugin.py --force`."
        )


_maybe_reexec_runtime_python()

MCP_DIR = Path(__file__).resolve().parent
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

from gulicode_bp_singleton import (  # noqa: E402
    SERVICE_HEARTBEAT_INTERVAL_SECONDS,
    SERVICE_STALE_AFTER_SECONDS,
    SingletonServiceError,
    append_service_log,
    ensure_singleton_service,
    hidden_creationflags as _singleton_hidden_creationflags,
    read_service_info,
    service_rpc,
    utc_now as _singleton_utc_now,
    write_service_info,
)
from mcp.server.fastmcp import Context, FastMCP


WEB_ROOT = PLUGIN_ROOT / "web"
WEB_DIST = WEB_ROOT / "dist"
DEFAULT_BLUEPRINT_ID = "default"
DEFAULT_COLLABORATION_URL = os.environ.get("GULICODE_BP_COLLABORATION_URL", "http://127.0.0.1:8787").rstrip("/")
PLANNING_REQUEST_TTL_SECONDS = 24 * 60 * 60
PLANNING_REQUESTS_PATH = RUNTIME_DATA_DIR / "planning_requests.json"
PERSISTENT_WORKBENCH_READY_PATH = RUNTIME_DATA_DIR / "workbench_ready.json"
PERSISTENT_WORKBENCH_LOG_DIR = RUNTIME_DATA_DIR / "logs"
MCP_STATUS_PATH = RUNTIME_DATA_DIR / "mcp_status.json"
MCP_LOG_PATH = PERSISTENT_WORKBENCH_LOG_DIR / "gulicode-bp-mcp.log"
MCP_HEARTBEAT_INTERVAL_SECONDS = 5.0
MCP_HEARTBEAT_STALE_AFTER_SECONDS = 20.0
HOP_BY_HOP_HEADERS = {
    "connection",
    "content-encoding",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

ALLOWED_COMMANDS = {
    "blueprint.list",
    "blueprint.open",
    "blueprint.create",
    "blueprint.delete",
    "blueprint.save",
    "blueprint.detectPython",
    "blueprint.scriptNodes",
    "blueprint.createScriptNode",
    "blueprint.listEditors",
    "blueprint.openScriptInEditor",
    "blueprint.pickDirectory",
    "blueprint.pickFile",
    "blueprint.relocateProjectWorkdir",
    "blueprint.validate",
    "blueprint.planning.submit",
    "blueprint.planning.status",
    "blueprint.planning.cancel",
    "blueprint.plan.create",
    "blueprint.plan.validate",
    "blueprint.listRuns",
    "blueprint.start",
    "blueprint.status",
    "blueprint.runDiff",
    "blueprint.changesetDiff",
    "blueprint.rollbackChangesets",
    "blueprint.restoreRollback",
    "blueprint.end",
    "blueprint.recentEvents",
    "blueprint.agentInfo",
    "blueprint.queueAgentMessage",
    "blueprint.agentStreamToken",
}

WRITE_COMMANDS = {
    "blueprint.create",
    "blueprint.delete",
    "blueprint.save",
    "blueprint.createScriptNode",
    "blueprint.relocateProjectWorkdir",
    "blueprint.planning.submit",
    "blueprint.planning.cancel",
    "blueprint.start",
    "blueprint.rollbackChangesets",
    "blueprint.restoreRollback",
    "blueprint.end",
    "blueprint.queueAgentMessage",
}

CONTROL_COMMANDS = {
    "blueprint.start",
    "blueprint.rollbackChangesets",
    "blueprint.restoreRollback",
    "blueprint.end",
    "blueprint.queueAgentMessage",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _append_mcp_log(event: str, **details: Any) -> None:
    try:
        MCP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": _utc_now(),
            "event": event,
            "pid": os.getpid(),
            **{key: _json_safe(value) for key, value in details.items()},
        }
        with MCP_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass


def _write_mcp_status(status: str, **details: Any) -> None:
    try:
        RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)
        now = _utc_now()
        payload = {
            "status": status,
            "timestamp": now,
            "pid": os.getpid(),
            "heartbeatAt": details.pop("heartbeatAt", now) if status == "running" else details.pop("heartbeatAt", None),
            "staleAfterSeconds": MCP_HEARTBEAT_STALE_AFTER_SECONDS if status == "running" else None,
            **{key: _json_safe(value) for key, value in details.items()},
        }
        if payload["heartbeatAt"] is None:
            payload.pop("heartbeatAt", None)
        if payload["staleAfterSeconds"] is None:
            payload.pop("staleAfterSeconds", None)
        with MCP_STATUS_PATH.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
    except Exception:
        pass


def _start_mcp_status_heartbeat(**details: Any) -> threading.Event:
    stop_event = threading.Event()

    def run() -> None:
        while not stop_event.wait(MCP_HEARTBEAT_INTERVAL_SECONDS):
            _write_mcp_status("running", **details)

    thread = threading.Thread(target=run, name="gulicode-bp-mcp-heartbeat", daemon=True)
    thread.start()
    return stop_event


def _json_default(value: Any) -> str:
    return str(value)


def _route_slug(value: str) -> str:
    raw = value or "global"
    encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _model_extra(value: Any) -> dict[str, Any] | None:
    extra = getattr(value, "model_extra", None)
    return extra if isinstance(extra, dict) else None


def _dictish_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    extra = _model_extra(value)
    if extra and key in extra:
        return extra.get(key)
    if hasattr(value, key):
        return getattr(value, key)
    return None


def _thread_id_from_meta(value: Any, *, depth: int = 0) -> str | None:
    if value is None or depth > 4:
        return None
    for key in ("threadId", "thread_id", "targetThreadId", "target_thread_id"):
        thread_id = _string_or_none(_dictish_value(value, key))
        if thread_id:
            return thread_id
    for key in ("_meta", "meta"):
        nested = _dictish_value(value, key)
        thread_id = _thread_id_from_meta(nested, depth=depth + 1)
        if thread_id:
            return thread_id
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
        except Exception:
            dumped = None
        if isinstance(dumped, dict):
            thread_id = _thread_id_from_meta(dumped, depth=depth + 1)
            if thread_id:
                return thread_id
    return None


def _planning_thread_id_from_context(ctx: Context | None) -> str | None:
    if ctx is None:
        return None
    candidates: list[Any] = []
    try:
        request_context = ctx.request_context
    except Exception:
        request_context = getattr(ctx, "request_context", None)
    candidates.append(getattr(request_context, "meta", None))
    request = getattr(request_context, "request", None)
    candidates.append(request)
    candidates.append(getattr(request, "params", None))
    candidates.append(getattr(request_context, "experimental", None))
    candidates.append(ctx)
    for candidate in candidates:
        thread_id = _thread_id_from_meta(candidate)
        if thread_id:
            return thread_id
    return None


def _current_planning_thread_id(ctx: Context | None) -> str | None:
    return _planning_thread_id_from_context(ctx) or _string_or_none(os.environ.get("CODEX_THREAD_ID"))


def _find_runtime_package_dir() -> Path:
    env_root = os.environ.get("GULICODE_BP_REPO_ROOT", "").strip()
    if env_root and not _repo_fallback_disabled():
        root = Path(env_root).expanduser().resolve()
        if (root / "desktop_blueprint_service.py").is_file():
            return root

    if not _repo_fallback_disabled():
        for parent in [PLUGIN_ROOT, *PLUGIN_ROOT.parents]:
            if (parent / "desktop_blueprint_service.py").is_file():
                return parent

    try:
        import multi_agent_tcp as runtime_package
    except Exception as exc:
        raise RuntimeError(
            "Could not import the plugin-owned multi_agent_tcp runtime. Reinstall or repair "
            "gulicode-bp so its .runtime venv contains the runtime package."
        ) from exc

    package_dir = Path(runtime_package.__file__).resolve().parent
    if (package_dir / "desktop_blueprint_service.py").is_file():
        return package_dir
    raise RuntimeError(f"multi_agent_tcp runtime package is incomplete: {package_dir}")


RUNTIME_PACKAGE_DIR = _find_runtime_package_dir()
RUNTIME_IMPORT_ROOT = RUNTIME_PACKAGE_DIR.parent
if str(RUNTIME_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_IMPORT_ROOT))

from multi_agent_tcp.desktop_blueprint_service import (  # noqa: E402
    BlueprintServiceError,
    DesktopBlueprintService,
)


def _repo_runtime_active() -> bool:
    return (RUNTIME_PACKAGE_DIR / "pyproject.toml").is_file() and (RUNTIME_PACKAGE_DIR / "plugins").is_dir()


def _default_project_dir() -> Path:
    env_project = os.environ.get("GULICODE_BP_DEFAULT_PROJECT_DIR", "").strip()
    if env_project:
        return Path(env_project).expanduser().resolve()
    if _repo_runtime_active():
        return RUNTIME_PACKAGE_DIR
    project_dir = RUNTIME_DATA_DIR / "projects" / "default"
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


def _write_ws_text(stream: Any, text: str) -> None:
    data = text.encode("utf-8")
    header = bytearray([0x81])
    length = len(data)
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.extend([126, (length >> 8) & 0xFF, length & 0xFF])
    else:
        header.append(127)
        header.extend(length.to_bytes(8, "big"))
    stream.write(bytes(header) + data)
    stream.flush()


def _picker_default_dir(args: dict[str, Any]) -> str:
    default_path = str(args.get("defaultPath") or args.get("projectDir") or "").strip()
    if default_path:
        candidate = Path(default_path).expanduser()
        if candidate.is_file():
            candidate = candidate.parent
        if candidate.exists():
            return str(candidate.resolve())
    return str(_default_project_dir())


def _filetypes_from_extensions(args: dict[str, Any]) -> list[tuple[str, str]]:
    raw_extensions = args.get("extensions") or args.get("accept") or []
    if isinstance(raw_extensions, str):
        extensions = [raw_extensions]
    elif isinstance(raw_extensions, list):
        extensions = [str(item) for item in raw_extensions if str(item).strip()]
    else:
        extensions = []
    patterns: list[str] = []
    for extension in extensions:
        item = extension.strip()
        if not item:
            continue
        if item.startswith("."):
            patterns.append(f"*{item}")
        elif item.startswith("*"):
            patterns.append(item)
        else:
            patterns.append(f"*.{item}")
    if not patterns:
        return [("All files", "*.*")]
    return [("Requested files", " ".join(patterns)), ("All files", "*.*")]


def _open_directory_picker(args: dict[str, Any]) -> dict[str, Any]:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # pragma: no cover - environment boundary
        raise BlueprintServiceError("PICKER_UNAVAILABLE", f"local directory picker is unavailable: {exc}") from exc

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    try:
        path = filedialog.askdirectory(
            parent=root,
            title=str(args.get("title") or "Select directory"),
            initialdir=_picker_default_dir(args),
            mustexist=False,
        )
    finally:
        root.destroy()
    return {"ok": True, "path": path or None}


def _open_file_picker(args: dict[str, Any]) -> dict[str, Any]:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # pragma: no cover - environment boundary
        raise BlueprintServiceError("PICKER_UNAVAILABLE", f"local file picker is unavailable: {exc}") from exc

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    try:
        options = {
            "parent": root,
            "title": str(args.get("title") or "Select file"),
            "initialdir": _picker_default_dir(args),
            "filetypes": _filetypes_from_extensions(args),
        }
        if bool(args.get("multiple")):
            result = list(filedialog.askopenfilenames(**options))
            return {"ok": True, "path": result or None}
        path = filedialog.askopenfilename(**options)
    finally:
        root.destroy()
    return {"ok": True, "path": path or None}


def _hidden_creationflags() -> int:
    if sys.platform == "win32":
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return 0


def _workbench_url_alive(url: str) -> bool:
    try:
        request = urlrequest.Request(url, headers={"Accept": "text/html,application/json"})
        with urlrequest.urlopen(request, timeout=1.5) as response:
            return 200 <= int(getattr(response, "status", 200)) < 400
    except Exception:
        return False


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _same_text(left: str | None, right: str | None) -> bool:
    return str(left or "").strip() == str(right or "").strip()


def _terminate_process(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_hidden_creationflags(),
                timeout=5,
            )
            return True
        os.kill(pid, 15)
        return True
    except Exception:
        return False


class WorkbenchServer:
    def __init__(
        self,
        service: DesktopBlueprintService,
        request_fn: Callable[[str, dict[str, Any]], dict[str, Any]],
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        default_project_dir: str = "",
        default_blueprint_id: str = DEFAULT_BLUEPRINT_ID,
        collaboration_url: str = DEFAULT_COLLABORATION_URL,
        ensure_collaboration_fn: Callable[[], None] | None = None,
        planning_thread_id: str = "",
    ) -> None:
        self.service = service
        self.request_fn = request_fn
        self.host = host
        self.port = port
        self.default_project_dir = default_project_dir
        self.default_blueprint_id = default_blueprint_id or DEFAULT_BLUEPRINT_ID
        self.collaboration_url = collaboration_url.rstrip("/")
        self.ensure_collaboration_fn = ensure_collaboration_fn
        self.planning_thread_id = planning_thread_id
        self.token = secrets.token_urlsafe(24)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("workbench server is not started")
        host, port = self._server.server_address[:2]
        project = self.default_project_dir or "global"
        session = self.default_blueprint_id or DEFAULT_BLUEPRINT_ID
        return f"http://{host}:{port}/{_route_slug(project)}/blueprint-window/{session}"

    @property
    def origin(self) -> str:
        if self._server is None:
            raise RuntimeError("workbench server is not started")
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> None:
        if self._server is not None:
            return
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def _write_bytes(
                self,
                data: bytes,
                *,
                status: int = 200,
                content_type: str = "application/octet-stream",
                no_store: bool = False,
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                if no_store:
                    self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def _write_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
                self._write_bytes(
                    json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8"),
                    status=status,
                    content_type="application/json; charset=utf-8",
                    no_store=True,
                )

            def _redirect(self, location: str) -> None:
                data = b""
                self.send_response(302)
                self.send_header("Location", location)
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path.rstrip("/") == "/agent-stream":
                    self._serve_agent_stream(parsed)
                    return
                if self._is_collaboration_api(parsed.path):
                    self._proxy_collaboration(method="GET")
                    return
                self._serve_static(parsed.path)

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path.rstrip("/") != "/api/blueprint":
                    if self._is_collaboration_api(parsed.path):
                        self._proxy_collaboration(method="POST")
                        return
                    self._write_json({"ok": False, "code": "NOT_FOUND", "error": "not found"}, status=404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    body = self.rfile.read(length).decode("utf-8")
                    payload = json.loads(body or "{}")
                    if not isinstance(payload, dict):
                        raise BlueprintServiceError("BAD_REQUEST", "request body must be a JSON object")
                    if payload.get("token") != owner.token:
                        raise BlueprintServiceError("INVALID_TOKEN", "invalid workbench token", status=403)
                    command = str(payload.get("command", "")).strip()
                    args = payload.get("args", {})
                    if not isinstance(args, dict):
                        raise BlueprintServiceError("BAD_REQUEST", "args must be a JSON object")
                    if command == "blueprint.agentStreamToken" and not args.get("baseUrl"):
                        args = dict(args)
                        args["baseUrl"] = owner.url
                    response = owner.request_fn(command, args)
                    self._write_json(response)
                except BlueprintServiceError as exc:
                    response: dict[str, Any] = {"ok": False, "code": exc.code, "error": str(exc)}
                    if exc.details:
                        response["details"] = exc.details
                    self._write_json(response, status=exc.status)
                except Exception as exc:  # pragma: no cover - defensive server boundary
                    self._write_json({"ok": False, "code": "INTERNAL_ERROR", "error": str(exc)}, status=500)

            def do_PUT(self) -> None:  # noqa: N802
                self._proxy_or_404("PUT")

            def do_PATCH(self) -> None:  # noqa: N802
                self._proxy_or_404("PATCH")

            def do_DELETE(self) -> None:  # noqa: N802
                self._proxy_or_404("DELETE")

            def _proxy_or_404(self, method: str) -> None:
                parsed = urlparse(self.path)
                if self._is_collaboration_api(parsed.path):
                    self._proxy_collaboration(method=method)
                    return
                self._write_json({"ok": False, "code": "NOT_FOUND", "error": "not found"}, status=404)

            def _is_collaboration_api(self, path: str) -> bool:
                normalized = path.rstrip("/")
                return path.startswith("/api/") and normalized not in {"/api/blueprint", "/api/config"}

            def _proxy_collaboration(self, *, method: str) -> None:
                if owner.ensure_collaboration_fn is not None:
                    owner.ensure_collaboration_fn()
                length = int(self.headers.get("Content-Length", "0") or "0")
                body = self.rfile.read(length) if length > 0 else None
                target_url = f"{owner.collaboration_url}{self.path}"
                headers = {
                    key: value
                    for key, value in self.headers.items()
                    if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"
                }
                headers["X-Forwarded-Host"] = self.headers.get("Host", "")
                headers["X-Forwarded-Proto"] = "http"
                try:
                    request = urlrequest.Request(target_url, data=body, headers=headers, method=method)
                    upstream = urlrequest.urlopen(request, timeout=60)
                except urlerror.HTTPError as exc:
                    upstream = exc
                except Exception as exc:
                    self._write_json(
                        {
                            "ok": False,
                            "code": "COLLABORATION_PROXY_FAILED",
                            "message": str(exc),
                            "error": str(exc),
                        },
                        status=502,
                    )
                    return
                with upstream:
                    data = upstream.read()
                    status = int(getattr(upstream, "status", getattr(upstream, "code", 502)))
                    self.send_response(status)
                    for key, value in upstream.headers.items():
                        if key.lower() in HOP_BY_HOP_HEADERS:
                            continue
                        self.send_header(key, value)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)

            def _serve_static(self, raw_path: str) -> None:
                if raw_path in {"", "/"}:
                    self._redirect(owner.url)
                    return
                redirect = self._plugin_route_redirect(raw_path)
                if redirect:
                    self._redirect(redirect)
                    return
                path = raw_path if raw_path and raw_path != "/" else "/index.html"
                path = path.lstrip("/")
                if path in {"config.js", "api/config"}:
                    payload = {
                        "token": owner.token,
                        "projectDir": owner.default_project_dir,
                        "blueprintId": owner.default_blueprint_id,
                        "apiBase": owner.origin,
                        "planningThreadId": owner.planning_thread_id,
                    }
                    script = "window.__GULICODE_BP__ = " + json.dumps(payload, ensure_ascii=False) + ";\n"
                    self._write_bytes(script.encode("utf-8"), content_type="application/javascript; charset=utf-8", no_store=True)
                    return

                root = WEB_DIST if WEB_DIST.is_dir() else WEB_ROOT
                target = (root / path).resolve()
                try:
                    target.relative_to(root.resolve())
                except ValueError:
                    self._write_json({"ok": False, "code": "NOT_FOUND", "error": "not found"}, status=404)
                    return
                if not target.is_file():
                    target = root / "index.html"
                if not target.is_file():
                    self._write_json({"ok": False, "code": "WEB_NOT_BUILT", "error": "web assets are missing"}, status=500)
                    return
                content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                if target.suffix == ".js":
                    content_type = "application/javascript; charset=utf-8"
                elif target.suffix in {".html", ".css"}:
                    content_type = f"text/{target.suffix[1:]}; charset=utf-8"
                data = target.read_bytes()
                if target.name == "index.html":
                    payload = {
                        "token": owner.token,
                        "projectDir": owner.default_project_dir,
                        "blueprintId": owner.default_blueprint_id,
                        "apiBase": owner.origin,
                        "planningThreadId": owner.planning_thread_id,
                    }
                    script = (
                        "<script>window.__GULICODE_BP__ = "
                        + json.dumps(payload, ensure_ascii=False)
                        + ";</script>\n"
                    )
                    text = data.decode("utf-8")
                    if "window.__GULICODE_BP__" not in text:
                        text = text.replace("</head>", f"{script}</head>")
                    data = text.encode("utf-8")
                self._write_bytes(data, content_type=content_type)

            def _plugin_route_redirect(self, raw_path: str) -> str | None:
                parts = [part for part in raw_path.strip("/").split("/") if part]
                if len(parts) >= 2 and parts[1] == "session":
                    return f"/{parts[0]}/blueprint-window/{owner.default_blueprint_id or DEFAULT_BLUEPRINT_ID}"
                return None

            def _serve_agent_stream(self, parsed: Any) -> None:
                try:
                    query = parse_qs(parsed.query)
                    run_id = owner.service.accept_stream_token(str((query.get("streamToken") or [""])[0]))
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

                    def send(event: dict[str, Any]) -> None:
                        _write_ws_text(self.wfile, json.dumps(event, ensure_ascii=False, default=_json_default))

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
                except Exception as exc:  # pragma: no cover - defensive server boundary
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
        self._server = None
        self._thread = None


class PluginState:
    def __init__(self) -> None:
        self.service = DesktopBlueprintService()
        self.lock = threading.RLock()
        self.workbench: WorkbenchServer | None = None
        self.collaboration_url = DEFAULT_COLLABORATION_URL
        self.collaboration_process: subprocess.Popen[bytes] | None = None
        self._collaboration_stdout: Any = None
        self._collaboration_stderr: Any = None
        self.planning_requests_path = PLANNING_REQUESTS_PATH
        self._planning_requests_loaded = False
        self._planning_requests_file_signature: tuple[int, int] | None = None
        self._planning_requests: dict[str, dict[str, Any]] = {}
        self.persistent_workbench_ready_path = PERSISTENT_WORKBENCH_READY_PATH
        self._persistent_workbench_stdout: Any = None
        self._persistent_workbench_stderr: Any = None
        self.active_owner_thread_id: str | None = None
        self.owner_changed_at: float | None = None

    def attach_owner(self, thread_id: str | None, *, reason: str = "control") -> dict[str, Any] | None:
        thread_id = _string_or_none(thread_id)
        if not thread_id:
            return None
        with self.lock:
            previous = self.active_owner_thread_id
            if previous == thread_id:
                return None
            now = time.time()
            self.active_owner_thread_id = thread_id
            self.owner_changed_at = now
        event = {
            "previousThreadId": previous,
            "threadId": thread_id,
            "reason": reason,
            "changedAt": now,
        }
        _append_mcp_log("owner-changed", **event)
        append_service_log(RUNTIME_DATA_DIR, "owner_changed", **event)
        return event

    def _planning_request_takeover_allowed_locked(self, request: dict[str, Any], thread_id: str | None) -> bool:
        thread_id = _string_or_none(thread_id)
        if not thread_id or self.active_owner_thread_id != thread_id:
            return False
        return request.get("status") in {"pending", "claimed"}

    def _reassign_planning_request_locked(self, request: dict[str, Any], thread_id: str | None) -> bool:
        if not self._planning_request_takeover_allowed_locked(request, thread_id):
            return False
        thread_id = _string_or_none(thread_id) or ""
        previous = str(request.get("threadId") or "")
        if previous == thread_id:
            return False
        now = time.time()
        request["previousThreadId"] = previous
        request["threadId"] = thread_id
        request["reassignedAt"] = now
        request["updatedAt"] = now
        append_service_log(
            RUNTIME_DATA_DIR,
            "planning_request_reassigned",
            requestId=request.get("requestId"),
            previousThreadId=previous,
            threadId=thread_id,
        )
        return True

    def _planning_requests_signature(self) -> tuple[int, int] | None:
        try:
            stat = self.planning_requests_path.stat()
        except OSError:
            return None
        return (int(stat.st_mtime_ns), int(stat.st_size))

    def _load_planning_requests_locked(self) -> None:
        signature = self._planning_requests_signature()
        if self._planning_requests_loaded and signature == self._planning_requests_file_signature:
            return
        self._planning_requests_loaded = True
        self._planning_requests_file_signature = signature
        try:
            payload = json.loads(self.planning_requests_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self._planning_requests = {}
            self._planning_requests_file_signature = None
            return
        except Exception:
            self._planning_requests = {}
            return
        raw_requests = payload.get("requests") if isinstance(payload, dict) else None
        if not isinstance(raw_requests, dict):
            self._planning_requests = {}
            return
        self._planning_requests = {
            str(request_id): dict(request)
            for request_id, request in raw_requests.items()
            if isinstance(request, dict) and isinstance(request_id, str)
        }
        self._prune_planning_requests_locked()

    def _save_planning_requests_locked(self) -> None:
        self.planning_requests_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schemaVersion": 1, "requests": self._planning_requests}
        self.planning_requests_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._planning_requests_loaded = True
        self._planning_requests_file_signature = self._planning_requests_signature()

    def _prune_planning_requests_locked(self) -> None:
        now = time.time()
        expired = [
            request_id
            for request_id, request in self._planning_requests.items()
            if float(request.get("expiresAt") or 0) <= now
        ]
        for request_id in expired:
            self._planning_requests.pop(request_id, None)

    def _planning_request_public(self, request: dict[str, Any], *, include_result: bool = False) -> dict[str, Any]:
        keys = [
            "requestId",
            "threadId",
            "projectDir",
            "blueprintId",
            "blueprintName",
            "task",
            "startNodeIds",
            "message",
            "status",
            "summary",
            "reason",
            "createdAt",
            "updatedAt",
            "claimedAt",
            "completedAt",
            "failedAt",
            "cancelledAt",
            "previousThreadId",
            "reassignedAt",
            "expiresAt",
        ]
        public = {key: request[key] for key in keys if key in request}
        if include_result:
            for key in ("plan", "validation"):
                if key in request:
                    public[key] = request[key]
        return public

    def _planning_request_by_id_locked(self, request_id: str) -> dict[str, Any] | None:
        self._load_planning_requests_locked()
        self._prune_planning_requests_locked()
        request = self._planning_requests.get(request_id)
        return request if isinstance(request, dict) else None

    def submit_planning_request(self, args: dict[str, Any]) -> dict[str, Any]:
        thread_id = _string_or_none(args.get("threadId"))
        if not thread_id:
            return {
                "ok": True,
                "accepted": False,
                "code": "NO_PLANNING_THREAD",
                "message": "No current Codex thread is available for agent-assisted planning.",
            }
        project_dir = _string_or_none(args.get("projectDir")) or str(_default_project_dir())
        blueprint_id = _string_or_none(args.get("blueprintId")) or DEFAULT_BLUEPRINT_ID
        task = _string_or_none(args.get("task")) or ""
        raw_start_nodes = args.get("startNodeIds")
        start_node_ids = [str(item) for item in raw_start_nodes if _string_or_none(item)] if isinstance(raw_start_nodes, list) else []
        now = time.time()
        request_id = secrets.token_urlsafe(16)
        request = {
            "requestId": request_id,
            "threadId": thread_id,
            "projectDir": project_dir,
            "blueprintId": blueprint_id,
            "blueprintName": _string_or_none(args.get("blueprintName")) or blueprint_id,
            "task": task,
            "startNodeIds": start_node_ids,
            "message": _string_or_none(args.get("message")) or task,
            "status": "pending",
            "createdAt": now,
            "updatedAt": now,
            "expiresAt": now + PLANNING_REQUEST_TTL_SECONDS,
        }
        with self.lock:
            self._load_planning_requests_locked()
            self._prune_planning_requests_locked()
            self._planning_requests[request_id] = request
            self._save_planning_requests_locked()
        return {
            "ok": True,
            "accepted": True,
            "requestId": request_id,
            "request": self._planning_request_public(request),
        }

    def planning_status(self, args: dict[str, Any]) -> dict[str, Any]:
        request_id = _string_or_none(args.get("requestId"))
        if not request_id:
            raise BlueprintServiceError("BAD_REQUEST", "requestId is required")
        with self.lock:
            request = self._planning_request_by_id_locked(request_id)
            if request is None:
                return {"ok": True, "found": False, "requestId": request_id}
            self._save_planning_requests_locked()
            return {
                "ok": True,
                "found": True,
                "request": self._planning_request_public(request, include_result=True),
            }

    def cancel_planning_request(self, args: dict[str, Any]) -> dict[str, Any]:
        request_id = _string_or_none(args.get("requestId"))
        if not request_id:
            raise BlueprintServiceError("BAD_REQUEST", "requestId is required")
        with self.lock:
            request = self._planning_request_by_id_locked(request_id)
            if request is None:
                return {"ok": True, "cancelled": False, "requestId": request_id}
            if request.get("status") not in {"completed", "failed", "cancelled"}:
                now = time.time()
                request["status"] = "cancelled"
                request["cancelledAt"] = now
                request["updatedAt"] = now
                request["reason"] = _string_or_none(args.get("reason")) or "cancelled"
                self._save_planning_requests_locked()
            return {
                "ok": True,
                "cancelled": True,
                "request": self._planning_request_public(request, include_result=True),
            }

    def take_planning_request(
        self,
        args: dict[str, Any] | None = None,
        *,
        thread_id: str | None,
    ) -> dict[str, Any]:
        thread_id = _string_or_none(thread_id)
        if not thread_id:
            return {"ok": True, "request": None, "message": "No current Codex thread id was provided."}
        args = args or {}
        request_id = _string_or_none(args.get("requestId"))
        project_dir = _string_or_none(args.get("projectDir"))
        blueprint_id = _string_or_none(args.get("blueprintId"))
        with self.lock:
            self._load_planning_requests_locked()
            self._prune_planning_requests_locked()
            candidates = list(self._planning_requests.values())
            candidates.sort(key=lambda request: float(request.get("createdAt") or 0))
            for request in candidates:
                if request_id and request.get("requestId") != request_id:
                    continue
                if project_dir and str(request.get("projectDir") or "") != project_dir:
                    continue
                if blueprint_id and str(request.get("blueprintId") or "") != blueprint_id:
                    continue
                same_thread = str(request.get("threadId") or "") == thread_id
                takeover = not same_thread and self._planning_request_takeover_allowed_locked(request, thread_id)
                if not same_thread and not takeover:
                    continue
                if request.get("status") not in {"pending", "claimed"}:
                    continue
                now = time.time()
                if takeover:
                    self._reassign_planning_request_locked(request, thread_id)
                request["status"] = "claimed"
                request["claimedAt"] = request.get("claimedAt") or now
                request["updatedAt"] = now
                self._save_planning_requests_locked()
                return {"ok": True, "request": self._planning_request_public(request)}
        return {"ok": True, "request": None}

    def _assert_planning_request_thread(self, request: dict[str, Any], thread_id: str | None) -> None:
        thread_id = _string_or_none(thread_id)
        if not thread_id:
            raise BlueprintServiceError("NO_PLANNING_THREAD", "No current Codex thread id was provided")
        self._reassign_planning_request_locked(request, thread_id)
        if str(request.get("threadId") or "") != thread_id:
            raise BlueprintServiceError("PLANNING_THREAD_MISMATCH", "planning request belongs to a different thread")

    def complete_planning_request(
        self,
        request_id: str,
        plan: dict[str, Any],
        summary: str | None = None,
        *,
        thread_id: str | None,
    ) -> dict[str, Any]:
        request_id = _string_or_none(request_id) or ""
        if not request_id:
            raise BlueprintServiceError("BAD_REQUEST", "requestId is required")
        if not isinstance(plan, dict):
            raise BlueprintServiceError("BAD_REQUEST", "plan must be a JSON object")
        with self.lock:
            request = self._planning_request_by_id_locked(request_id)
            if request is None:
                raise BlueprintServiceError("PLANNING_REQUEST_NOT_FOUND", f"planning request not found: {request_id}")
            self._assert_planning_request_thread(request, thread_id)
            project_dir = str(request.get("projectDir") or "")
            blueprint_id = str(request.get("blueprintId") or DEFAULT_BLUEPRINT_ID)
        validation_response = self.service.handle_request(
            {
                "command": "blueprint.plan.validate",
                "args": {"projectDir": project_dir, "blueprintId": blueprint_id, "plan": plan},
            }
        )
        validation = validation_response.get("validation") if isinstance(validation_response, dict) else None
        if not isinstance(validation, dict):
            validation = validation_response if isinstance(validation_response, dict) else {"ok": False}
        with self.lock:
            request = self._planning_request_by_id_locked(request_id)
            if request is None:
                raise BlueprintServiceError("PLANNING_REQUEST_NOT_FOUND", f"planning request not found: {request_id}")
            self._assert_planning_request_thread(request, thread_id)
            now = time.time()
            request["status"] = "completed"
            request["plan"] = plan
            request["validation"] = validation
            request["summary"] = _string_or_none(summary) or request.get("summary") or ""
            request["completedAt"] = now
            request["updatedAt"] = now
            self._save_planning_requests_locked()
            return {
                "ok": True,
                "request": self._planning_request_public(request, include_result=True),
                "validation": validation,
            }

    def fail_planning_request(self, request_id: str, reason: str, *, thread_id: str | None) -> dict[str, Any]:
        request_id = _string_or_none(request_id) or ""
        if not request_id:
            raise BlueprintServiceError("BAD_REQUEST", "requestId is required")
        with self.lock:
            request = self._planning_request_by_id_locked(request_id)
            if request is None:
                raise BlueprintServiceError("PLANNING_REQUEST_NOT_FOUND", f"planning request not found: {request_id}")
            self._assert_planning_request_thread(request, thread_id)
            now = time.time()
            request["status"] = "failed"
            request["reason"] = _string_or_none(reason) or "failed"
            request["failedAt"] = now
            request["updatedAt"] = now
            self._save_planning_requests_locked()
            return {"ok": True, "request": self._planning_request_public(request, include_result=True)}

    def request(
        self,
        command: str,
        args: dict[str, Any] | None = None,
        *,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        command = str(command or "").strip()
        if command not in ALLOWED_COMMANDS:
            raise BlueprintServiceError("UNKNOWN_COMMAND", f"unsupported blueprint command: {command!r}")
        request_kind = _request_kind_for_command(command)
        if request_kind in {"write", "control"}:
            self.attach_owner(thread_id, reason=request_kind)
        if command == "blueprint.planning.submit":
            return self.submit_planning_request(args or {})
        if command == "blueprint.planning.status":
            return self.planning_status(args or {})
        if command == "blueprint.planning.cancel":
            return self.cancel_planning_request(args or {})
        if command == "blueprint.pickDirectory":
            return _open_directory_picker(args or {})
        if command == "blueprint.pickFile":
            return _open_file_picker(args or {})
        payload = {"command": command, "args": args or {}}
        return self.service.handle_request(payload)

    def _collaboration_health_ok(self) -> bool:
        try:
            request = urlrequest.Request(f"{self.collaboration_url}/api/health", headers={"Accept": "application/json"})
            with urlrequest.urlopen(request, timeout=1.5) as response:
                return 200 <= int(response.status) < 300
        except Exception:
            return False

    def ensure_collaboration_server(self) -> None:
        with self.lock:
            if self._collaboration_health_ok():
                return
            parsed = urlparse(self.collaboration_url)
            host = parsed.hostname or "127.0.0.1"
            port = int(parsed.port or 8787)
            if host not in {"127.0.0.1", "localhost"}:
                raise RuntimeError(f"Collaboration server is not reachable: {self.collaboration_url}")
            log_dir = RUNTIME_DATA_DIR / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            seed_config = RUNTIME_PACKAGE_DIR / "examples" / "collaboration_server_debug_seed.json"
            RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            import_root = str(RUNTIME_IMPORT_ROOT)
            if _repo_runtime_active() and env.get("PYTHONPATH"):
                env["PYTHONPATH"] = import_root + os.pathsep + env["PYTHONPATH"]
            else:
                env["PYTHONPATH"] = import_root
            args = [
                sys.executable,
                "-m",
                "multi_agent_tcp",
                "collaboration-server",
                "--host",
                host,
                "--port",
                str(port),
                "--db",
                str(log_dir / "collaboration_server.sqlite3"),
                "--log-dir",
                str(log_dir),
                "--log-level",
                "INFO",
            ]
            if seed_config.is_file():
                args.extend(["--seed-config", str(seed_config)])
            self._collaboration_stdout = (log_dir / "gulicode-bp-collaboration.out.log").open("ab")
            self._collaboration_stderr = (log_dir / "gulicode-bp-collaboration.err.log").open("ab")
            self.collaboration_process = subprocess.Popen(
                args,
                cwd=str(RUNTIME_DATA_DIR),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=self._collaboration_stdout,
                stderr=self._collaboration_stderr,
                creationflags=_hidden_creationflags(),
            )
            deadline = time.time() + 12
            while time.time() < deadline:
                if self.collaboration_process.poll() is not None:
                    break
                if self._collaboration_health_ok():
                    return
                time.sleep(0.25)
            if self._collaboration_health_ok():
                return
            raise RuntimeError(f"Collaboration server did not become ready at {self.collaboration_url}")

    def start_workbench(
        self,
        project_dir: str | None = None,
        blueprint_id: str | None = None,
        *,
        open_browser: bool = False,
        planning_thread_id: str | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            self.ensure_collaboration_server()
            if self.workbench is None:
                self.workbench = WorkbenchServer(
                    self.service,
                    self.request,
                    default_project_dir=str(project_dir or ""),
                    default_blueprint_id=str(blueprint_id or DEFAULT_BLUEPRINT_ID),
                    collaboration_url=self.collaboration_url,
                    ensure_collaboration_fn=self.ensure_collaboration_server,
                    planning_thread_id=str(planning_thread_id or ""),
                )
                self.workbench.start()
            else:
                if project_dir is not None:
                    self.workbench.default_project_dir = str(project_dir)
                if blueprint_id is not None:
                    self.workbench.default_blueprint_id = str(blueprint_id or DEFAULT_BLUEPRINT_ID)
                if planning_thread_id is not None:
                    self.workbench.planning_thread_id = str(planning_thread_id or "")
            url = self.workbench.url
        if open_browser:
            webbrowser.open(url)
        return {
            "ok": True,
            "url": url,
            "projectDir": str(project_dir or ""),
            "blueprintId": str(blueprint_id or DEFAULT_BLUEPRINT_ID),
            "planningThreadId": str(planning_thread_id or ""),
        }

    def _persistent_workbench_matches(
        self,
        ready: dict[str, Any],
        project_dir: str | None,
        blueprint_id: str | None,
        planning_thread_id: str | None,
    ) -> bool:
        url = _string_or_none(ready.get("url"))
        if not url or not _workbench_url_alive(url):
            return False
        expected_project = str(project_dir or "")
        expected_blueprint = str(blueprint_id or DEFAULT_BLUEPRINT_ID)
        if not _same_text(ready.get("projectDir"), expected_project):
            return False
        if not _same_text(ready.get("blueprintId"), expected_blueprint):
            return False
        return _same_text(ready.get("planningThreadId"), planning_thread_id or "")

    def _close_persistent_workbench_logs(self) -> None:
        for handle_name in ("_persistent_workbench_stdout", "_persistent_workbench_stderr"):
            handle = getattr(self, handle_name, None)
            if handle is not None:
                try:
                    handle.close()
                finally:
                    setattr(self, handle_name, None)

    def start_persistent_workbench(
        self,
        project_dir: str | None = None,
        blueprint_id: str | None = None,
        *,
        open_browser: bool = False,
        planning_thread_id: str | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            reused = self.workbench is not None
        result = self.start_workbench(
            project_dir,
            blueprint_id,
            open_browser=open_browser,
            planning_thread_id=planning_thread_id,
        )
        ready = {
            **result,
            "pid": os.getpid(),
            "servicePid": os.getpid(),
            "persistent": True,
            "singleton": _singleton_role() == "service",
            "reused": reused,
        }
        self.persistent_workbench_ready_path.parent.mkdir(parents=True, exist_ok=True)
        self.persistent_workbench_ready_path.write_text(
            json.dumps(ready, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return ready

    def stop_workbench(self) -> dict[str, Any]:
        with self.lock:
            stopped_persistent = False
            ready = _read_json_file(self.persistent_workbench_ready_path)
            if ready:
                stopped_persistent = _terminate_process(int(ready.get("pid") or 0))
                try:
                    self.persistent_workbench_ready_path.unlink()
                except FileNotFoundError:
                    pass
            self._close_persistent_workbench_logs()
            if self.workbench is None:
                return {"ok": True, "stopped": stopped_persistent}
            self.workbench.close()
            self.workbench = None
            return {"ok": True, "stopped": True}

    def close(self) -> None:
        with self.lock:
            if self.workbench is not None:
                self.workbench.close()
                self.workbench = None
            if self.collaboration_process is not None and self.collaboration_process.poll() is None:
                self.collaboration_process.terminate()
                try:
                    self.collaboration_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.collaboration_process.kill()
                    self.collaboration_process.wait(timeout=5)
            self.collaboration_process = None
            for handle_name in ("_collaboration_stdout", "_collaboration_stderr"):
                handle = getattr(self, handle_name, None)
                if handle is not None:
                    try:
                        handle.close()
                    finally:
                        setattr(self, handle_name, None)
            self._close_persistent_workbench_logs()
            self.service.close()


def _singleton_role() -> str:
    if "--service" in sys.argv:
        return "service"
    return str(os.environ.get("GULICODE_BP_SINGLETON_ROLE") or "").strip().lower()


def _runtime_python_for_singleton() -> Path:
    runtime_python = _runtime_venv_python()
    if runtime_python.is_file():
        return runtime_python
    return Path(sys.executable)


def _singleton_extra_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if _repo_runtime_active() and not _repo_fallback_disabled():
        env["GULICODE_BP_REPO_ROOT"] = str(RUNTIME_PACKAGE_DIR)
        env["PYTHONPATH"] = str(RUNTIME_IMPORT_ROOT)
    else:
        env["GULICODE_BP_DISABLE_REPO_FALLBACK"] = "1"
    return env


def _request_kind_for_command(command: str) -> str:
    if command in CONTROL_COMMANDS:
        return "control"
    if command in WRITE_COMMANDS:
        return "write"
    return "read"


def _raise_blueprint_service_error(exc: SingletonServiceError) -> None:
    raise BlueprintServiceError(exc.code, exc.message, status=exc.status, details=exc.details) from exc


class SingletonProxyState:
    """Stateless stdio MCP proxy that forwards all stateful work to the singleton service."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self._service_info: dict[str, Any] | None = None

    def _ensure_service(self) -> dict[str, Any]:
        with self.lock:
            if self._service_info:
                live = read_service_info(RUNTIME_DATA_DIR)
                if live and live.get("generation") == self._service_info.get("generation"):
                    return self._service_info
            try:
                self._service_info = ensure_singleton_service(
                    PLUGIN_ROOT,
                    _runtime_python_for_singleton(),
                    RUNTIME_HOME,
                    RUNTIME_DATA_DIR,
                    extra_env=_singleton_extra_env(),
                )
            except SingletonServiceError as exc:
                _raise_blueprint_service_error(exc)
            return self._service_info or {}

    def _rpc(
        self,
        command: str,
        args: dict[str, Any] | None = None,
        *,
        thread_id: str | None = None,
        request_kind: str = "read",
    ) -> dict[str, Any]:
        self._ensure_service()
        try:
            return service_rpc(
                RUNTIME_DATA_DIR,
                command,
                args or {},
                thread_id=thread_id or _current_planning_thread_id(None),
                request_kind=request_kind,
            )
        except SingletonServiceError as exc:
            self._service_info = None
            _raise_blueprint_service_error(exc)

    def start_persistent_workbench(
        self,
        project_dir: str | None = None,
        blueprint_id: str | None = None,
        *,
        open_browser: bool = False,
        planning_thread_id: str | None = None,
    ) -> dict[str, Any]:
        return self._rpc(
            "service.startWorkbench",
            {
                "projectDir": str(project_dir or ""),
                "blueprintId": str(blueprint_id or DEFAULT_BLUEPRINT_ID),
                "openBrowser": bool(open_browser),
                "planningThreadId": str(planning_thread_id or ""),
            },
            thread_id=planning_thread_id,
            request_kind="attach",
        )

    def stop_workbench(self, *, thread_id: str | None = None) -> dict[str, Any]:
        return self._rpc("service.stopWorkbench", {}, thread_id=thread_id, request_kind="control")

    def take_planning_request(
        self,
        args: dict[str, Any] | None = None,
        *,
        thread_id: str | None,
    ) -> dict[str, Any]:
        return self._rpc(
            "service.takePlanningRequest",
            args or {},
            thread_id=thread_id,
            request_kind="control",
        )

    def complete_planning_request(
        self,
        request_id: str,
        plan: dict[str, Any],
        summary: str | None = None,
        *,
        thread_id: str | None,
    ) -> dict[str, Any]:
        return self._rpc(
            "service.completePlanningRequest",
            {"requestId": request_id, "plan": plan, "summary": summary or ""},
            thread_id=thread_id,
            request_kind="control",
        )

    def fail_planning_request(self, request_id: str, reason: str, *, thread_id: str | None) -> dict[str, Any]:
        return self._rpc(
            "service.failPlanningRequest",
            {"requestId": request_id, "reason": reason},
            thread_id=thread_id,
            request_kind="control",
        )

    def request(
        self,
        command: str,
        args: dict[str, Any] | None = None,
        *,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        return self._rpc(command, args or {}, thread_id=thread_id, request_kind=_request_kind_for_command(command))

    def close(self) -> None:
        self._service_info = None


class SingletonServiceServer:
    def __init__(self, plugin_state: PluginState, *, host: str = "127.0.0.1", port: int = 0) -> None:
        self.state = plugin_state
        self.host = host
        self.port = port
        self.token = os.environ.get("GULICODE_BP_SERVICE_TOKEN") or secrets.token_urlsafe(32)
        self.generation = f"{int(time.time() * 1000)}-{secrets.token_hex(4)}"
        self.started_at = _singleton_utc_now()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._heartbeat_stop: threading.Event | None = None
        self._heartbeat_thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        if self._server is None:
            return f"http://{self.host}:{self.port}"
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def _service_info(self, status: str = "running") -> dict[str, Any]:
        payload = {
            "schemaVersion": 1,
            "status": status,
            "pid": os.getpid(),
            "url": self.url,
            "token": self.token,
            "generation": self.generation,
            "startedAt": self.started_at,
            "heartbeatAt": _singleton_utc_now(),
            "staleAfterSeconds": SERVICE_STALE_AFTER_SECONDS,
            "pluginRoot": str(PLUGIN_ROOT),
            "runtimeHome": str(RUNTIME_HOME),
            "runtimeDataDir": str(RUNTIME_DATA_DIR),
            "runtimePython": sys.executable,
        }
        if status != "running":
            payload.pop("heartbeatAt", None)
            payload["exitedAt"] = _singleton_utc_now()
        return payload

    def _write_info(self, status: str = "running") -> None:
        write_service_info(RUNTIME_DATA_DIR, self._service_info(status))

    def _valid_token(self, token: str | None) -> bool:
        return bool(token) and secrets.compare_digest(str(token), self.token)

    def _dispatch(self, command: str, args: dict[str, Any], *, thread_id: str | None, request_kind: str) -> dict[str, Any]:
        if request_kind in {"attach", "write", "control"}:
            self.state.attach_owner(thread_id, reason=request_kind)
        if command == "service.startWorkbench":
            planning_thread_id = _string_or_none(args.get("planningThreadId")) or thread_id
            result = self.state.start_workbench(
                _string_or_none(args.get("projectDir")),
                _string_or_none(args.get("blueprintId")) or DEFAULT_BLUEPRINT_ID,
                open_browser=bool(args.get("openBrowser")),
                planning_thread_id=planning_thread_id,
            )
            return {
                **result,
                "pid": os.getpid(),
                "servicePid": os.getpid(),
                "persistent": True,
                "singleton": True,
                "generation": self.generation,
            }
        if command == "service.stopWorkbench":
            return {**self.state.stop_workbench(), "servicePid": os.getpid(), "singleton": True}
        if command == "service.takePlanningRequest":
            return self.state.take_planning_request(args, thread_id=thread_id)
        if command == "service.completePlanningRequest":
            return self.state.complete_planning_request(
                str(args.get("requestId") or ""),
                args.get("plan") if isinstance(args.get("plan"), dict) else {},
                _string_or_none(args.get("summary")),
                thread_id=thread_id,
            )
        if command == "service.failPlanningRequest":
            return self.state.fail_planning_request(
                str(args.get("requestId") or ""),
                str(args.get("reason") or ""),
                thread_id=thread_id,
            )
        if command == "service.status":
            return {"ok": True, "service": self._service_info()}
        return self.state.request(command, args, thread_id=thread_id)

    def start(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _write_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
                raw = json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _read_json(self) -> dict[str, Any]:
                try:
                    length = int(self.headers.get("Content-Length") or "0")
                except ValueError:
                    length = 0
                raw = self.rfile.read(length) if length > 0 else b"{}"
                payload = json.loads(raw.decode("utf-8") or "{}")
                if not isinstance(payload, dict):
                    raise BlueprintServiceError("BAD_REQUEST", "request body must be a JSON object")
                return payload

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path != "/health":
                    self.send_error(404)
                    return
                if not outer._valid_token(self.headers.get("X-Gulicode-Bp-Token")):
                    self._write_json({"ok": False, "code": "INVALID_TOKEN", "error": "invalid singleton token"}, status=403)
                    return
                self._write_json({"ok": True, "service": outer._service_info()})

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path != "/rpc":
                    self.send_error(404)
                    return
                try:
                    payload = self._read_json()
                    token = str(payload.get("token") or self.headers.get("X-Gulicode-Bp-Token") or "")
                    if not outer._valid_token(token):
                        raise BlueprintServiceError("INVALID_TOKEN", "invalid singleton token", status=403)
                    command = str(payload.get("command") or "").strip()
                    args = payload.get("args") or {}
                    if not isinstance(args, dict):
                        raise BlueprintServiceError("BAD_REQUEST", "args must be a JSON object")
                    thread_id = _string_or_none(payload.get("threadId"))
                    request_kind = str(payload.get("requestKind") or "read").strip().lower()
                    result = outer._dispatch(command, args, thread_id=thread_id, request_kind=request_kind)
                    append_service_log(
                        RUNTIME_DATA_DIR,
                        "rpc",
                        command=command,
                        requestKind=request_kind,
                        threadId=thread_id,
                    )
                    self._write_json(result)
                except BlueprintServiceError as exc:
                    self._write_json(
                        {
                            "ok": False,
                            "code": exc.code,
                            "error": str(exc),
                            "details": getattr(exc, "details", {}),
                        },
                        status=getattr(exc, "status", 500),
                    )
                except Exception as exc:  # pragma: no cover - defensive service boundary
                    append_service_log(RUNTIME_DATA_DIR, "rpc-error", error=str(exc), traceback=traceback.format_exc())
                    self._write_json({"ok": False, "code": "INTERNAL_ERROR", "error": str(exc)}, status=500)

            def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
                return

        RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.port = int(self._server.server_address[1])
        self._write_info("running")
        self._heartbeat_stop = threading.Event()

        def heartbeat() -> None:
            assert self._heartbeat_stop is not None
            while not self._heartbeat_stop.wait(SERVICE_HEARTBEAT_INTERVAL_SECONDS):
                self._write_info("running")

        self._heartbeat_thread = threading.Thread(target=heartbeat, name="gulicode-bp-service-heartbeat", daemon=True)
        self._heartbeat_thread.start()
        self._thread = threading.Thread(target=self._server.serve_forever, name="gulicode-bp-singleton-service", daemon=True)
        self._thread.start()
        append_service_log(
            RUNTIME_DATA_DIR,
            "service_started",
            url=self.url,
            generation=self.generation,
            pluginRoot=str(PLUGIN_ROOT),
        )

    def close(self) -> None:
        if self._heartbeat_stop is not None:
            self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=2)
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._write_info("exited")
        append_service_log(RUNTIME_DATA_DIR, "service_stopped", generation=self.generation)
        self._server = None
        self._thread = None
        self._heartbeat_stop = None
        self._heartbeat_thread = None


def _create_state() -> PluginState | SingletonProxyState:
    return SingletonProxyState() if _singleton_role() == "proxy" else PluginState()


state = _create_state()
mcp = FastMCP(
    "gulicode-bp",
    instructions=(
        "Use these tools to open the local GuLiCode Blueprint workbench and "
        "control the existing DesktopBlueprintService / GraphRuntime runtime."
    ),
)


@mcp.tool()
def start_blueprint_workbench(
    projectDir: Optional[str] = None,
    blueprintId: Optional[str] = None,
    openBrowser: bool = False,
    ctx: Context = None,
) -> dict[str, Any]:
    """Start the local GuLiCode Blueprint web workbench."""
    return state.start_persistent_workbench(
        projectDir,
        blueprintId,
        open_browser=openBrowser,
        planning_thread_id=_current_planning_thread_id(ctx),
    )


@mcp.tool()
def stop_blueprint_workbench(ctx: Context = None) -> dict[str, Any]:
    """Stop the local GuLiCode Blueprint web workbench."""
    stop_fn = getattr(state, "stop_workbench")
    try:
        return stop_fn(thread_id=_current_planning_thread_id(ctx))
    except TypeError:
        return stop_fn()


@mcp.tool()
def blueprint_request(command: str, args: Optional[dict[str, Any]] = None, ctx: Context = None) -> dict[str, Any]:
    """Call a whitelisted DesktopBlueprintService command."""
    return state.request(command, args or {}, thread_id=_current_planning_thread_id(ctx))


@mcp.tool()
def blueprint_take_planning_request(
    projectDir: Optional[str] = None,
    blueprintId: Optional[str] = None,
    requestId: Optional[str] = None,
    ctx: Context = None,
) -> dict[str, Any]:
    """Claim the oldest pending Workbench planning request for the current Codex thread."""
    args: dict[str, Any] = {}
    if projectDir:
        args["projectDir"] = projectDir
    if blueprintId:
        args["blueprintId"] = blueprintId
    if requestId:
        args["requestId"] = requestId
    return state.take_planning_request(args, thread_id=_current_planning_thread_id(ctx))


@mcp.tool()
def blueprint_complete_planning_request(
    requestId: str,
    plan: dict[str, Any],
    summary: Optional[str] = None,
    ctx: Context = None,
) -> dict[str, Any]:
    """Complete a Workbench planning request with a validated blueprint start plan."""
    return state.complete_planning_request(requestId, plan, summary, thread_id=_current_planning_thread_id(ctx))


@mcp.tool()
def blueprint_fail_planning_request(
    requestId: str,
    reason: str,
    ctx: Context = None,
) -> dict[str, Any]:
    """Mark a Workbench planning request failed for the current Codex thread."""
    return state.fail_planning_request(requestId, reason, thread_id=_current_planning_thread_id(ctx))


@mcp.tool()
def blueprint_list(projectDir: str) -> dict[str, Any]:
    """List project blueprints."""
    return state.request("blueprint.list", {"projectDir": projectDir})


@mcp.tool()
def blueprint_open(projectDir: str, blueprintId: str = DEFAULT_BLUEPRINT_ID) -> dict[str, Any]:
    """Open one project blueprint document."""
    return state.request("blueprint.open", {"projectDir": projectDir, "blueprintId": blueprintId})


@mcp.tool()
def blueprint_create(
    projectDir: str,
    blueprintId: Optional[str] = None,
    name: Optional[str] = None,
    ctx: Context = None,
) -> dict[str, Any]:
    """Create one project blueprint document."""
    args: dict[str, Any] = {"projectDir": projectDir}
    if blueprintId:
        args["blueprintId"] = blueprintId
    if name:
        args["name"] = name
    return state.request("blueprint.create", args, thread_id=_current_planning_thread_id(ctx))


@mcp.tool()
def blueprint_delete(projectDir: str, blueprintId: str = DEFAULT_BLUEPRINT_ID, ctx: Context = None) -> dict[str, Any]:
    """Soft-delete one project blueprint document."""
    return state.request("blueprint.delete", {"projectDir": projectDir, "blueprintId": blueprintId}, thread_id=_current_planning_thread_id(ctx))


@mcp.tool()
def blueprint_save(projectDir: str, document: dict[str, Any], ctx: Context = None) -> dict[str, Any]:
    """Save one project blueprint document."""
    return state.request("blueprint.save", {"projectDir": projectDir, "document": document}, thread_id=_current_planning_thread_id(ctx))


@mcp.tool()
def blueprint_list_editors() -> dict[str, Any]:
    """Discover local IDE/editor launch candidates for blueprint scripts."""
    return state.request("blueprint.listEditors", {})


@mcp.tool()
def blueprint_open_script_in_editor(
    projectDir: str,
    modulePath: str,
    editorId: Optional[str] = None,
) -> dict[str, Any]:
    """Open the blueprint scripts folder in the selected IDE/editor."""
    args: dict[str, Any] = {"projectDir": projectDir, "modulePath": modulePath}
    if editorId:
        args["editorId"] = editorId
    return state.request("blueprint.openScriptInEditor", args)


@mcp.tool()
def blueprint_validate(
    projectDir: str,
    blueprintId: str = DEFAULT_BLUEPRINT_ID,
    document: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Validate one project blueprint document."""
    args: dict[str, Any] = {"projectDir": projectDir, "blueprintId": blueprintId}
    if document is not None:
        args["document"] = document
    return state.request("blueprint.validate", args)


@mcp.tool()
def blueprint_plan_create(
    projectDir: str,
    task: str,
    blueprintId: str = DEFAULT_BLUEPRINT_ID,
    startNodeIds: Optional[list[str]] = None,
    planOverrides: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Generate and validate a start plan for a blueprint without starting it."""
    args: dict[str, Any] = {
        "projectDir": projectDir,
        "blueprintId": blueprintId,
        "task": task,
    }
    if startNodeIds is not None:
        args["startNodeIds"] = startNodeIds
    if planOverrides is not None:
        args["planOverrides"] = planOverrides
    return state.request("blueprint.plan.create", args)


@mcp.tool()
def blueprint_plan_validate(
    projectDir: str,
    plan: dict[str, Any],
    blueprintId: str = DEFAULT_BLUEPRINT_ID,
) -> dict[str, Any]:
    """Validate a confirmed start plan for a blueprint."""
    return state.request(
        "blueprint.plan.validate",
        {"projectDir": projectDir, "blueprintId": blueprintId, "plan": plan},
    )


@mcp.tool()
def blueprint_list_runs(
    projectDir: Optional[str] = None,
    blueprintId: Optional[str] = None,
) -> dict[str, Any]:
    """List live blueprint runs owned by the plugin runtime service."""
    args: dict[str, Any] = {}
    if projectDir:
        args["projectDir"] = projectDir
    if blueprintId:
        args["blueprintId"] = blueprintId
    return state.request("blueprint.listRuns", args)


@mcp.tool()
def blueprint_start(
    projectDir: str,
    plan: dict[str, Any],
    blueprintId: str = DEFAULT_BLUEPRINT_ID,
    executionMode: str = "live",
    ctx: Context = None,
) -> dict[str, Any]:
    """Start a blueprint run."""
    return state.request(
        "blueprint.start",
        {
            "projectDir": projectDir,
            "blueprintId": blueprintId,
            "plan": plan,
            "executionMode": executionMode,
        },
        thread_id=_current_planning_thread_id(ctx),
    )


@mcp.tool()
def blueprint_status(runId: str) -> dict[str, Any]:
    """Read a blueprint run status snapshot."""
    return state.request("blueprint.status", {"runId": runId})


@mcp.tool()
def blueprint_end(runId: str, action: str, reason: str = "", ctx: Context = None) -> dict[str, Any]:
    """End a blueprint run with complete, cancel, fail, or pause."""
    return state.request("blueprint.end", {"runId": runId, "action": action, "reason": reason}, thread_id=_current_planning_thread_id(ctx))


@mcp.tool()
def blueprint_recent_events(runId: str, limit: int = 20) -> dict[str, Any]:
    """Read recent blueprint run events."""
    return state.request("blueprint.recentEvents", {"runId": runId, "limit": limit})


@mcp.tool()
def blueprint_run_diff(runId: str) -> dict[str, Any]:
    """Read the current run-scoped blueprint diff summary."""
    return state.request("blueprint.runDiff", {"runId": runId})


@mcp.tool()
def blueprint_changeset_diff(runId: str, changesetId: str) -> dict[str, Any]:
    """Read one blueprint changeset diff."""
    return state.request("blueprint.changesetDiff", {"runId": runId, "changesetId": changesetId})


@mcp.tool()
def blueprint_rollback_changesets(
    runId: str,
    toChangesetId: str,
    reason: str = "",
    ctx: Context = None,
) -> dict[str, Any]:
    """Roll back accepted blueprint changesets."""
    return state.request(
        "blueprint.rollbackChangesets",
        {"runId": runId, "toChangesetId": toChangesetId, "reason": reason},
        thread_id=_current_planning_thread_id(ctx),
    )


@mcp.tool()
def blueprint_restore_rollback(
    runId: str,
    rollbackId: Optional[str] = None,
    reason: str = "",
    ctx: Context = None,
) -> dict[str, Any]:
    """Restore the latest or selected blueprint rollback marker."""
    args: dict[str, Any] = {"runId": runId, "reason": reason}
    if rollbackId:
        args["rollbackId"] = rollbackId
    return state.request("blueprint.restoreRollback", args, thread_id=_current_planning_thread_id(ctx))


@mcp.tool()
def blueprint_agent_info(
    nodeId: str,
    runId: Optional[str] = None,
) -> dict[str, Any]:
    """Read one blueprint agent/node detail snapshot."""
    args: dict[str, Any] = {"nodeId": nodeId}
    if runId:
        args["runId"] = runId
    return state.request("blueprint.agentInfo", args)


@mcp.tool()
def blueprint_queue_agent_message(
    runId: str,
    nodeId: str,
    text: str,
    mode: str = "default",
    ctx: Context = None,
) -> dict[str, Any]:
    """Queue a user message to one live blueprint AgentNode."""
    return state.request(
        "blueprint.queueAgentMessage",
        {"runId": runId, "nodeId": nodeId, "text": text, "mode": mode},
        thread_id=_current_planning_thread_id(ctx),
    )


def _run_singleton_service() -> None:
    if not isinstance(state, PluginState):
        raise RuntimeError("singleton service role must own PluginState")
    server = SingletonServiceServer(state)
    server.start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return
    finally:
        try:
            server.close()
        finally:
            state.close()


def main() -> None:
    if _singleton_role() == "service":
        _run_singleton_service()
        return

    if isinstance(state, SingletonProxyState):
        state._ensure_service()
    status_details = {
        "component": "mcp-proxy" if isinstance(state, SingletonProxyState) else "mcp-server",
        "phase": "stdio",
        "pluginRoot": str(PLUGIN_ROOT),
        "runtimePython": sys.executable,
        "runtimeDataDir": str(RUNTIME_DATA_DIR),
        "serviceMode": "singleton-proxy" if isinstance(state, SingletonProxyState) else "direct",
    }
    _write_mcp_status("running", **status_details)
    heartbeat_stop = _start_mcp_status_heartbeat(**status_details)
    _append_mcp_log(
        "mcp-running",
        pluginRoot=str(PLUGIN_ROOT),
        runtimePython=sys.executable,
        runtimeDataDir=str(RUNTIME_DATA_DIR),
        role=_singleton_role() or "direct",
    )
    try:
        mcp.run("stdio")
    except Exception as exc:
        heartbeat_stop.set()
        _write_mcp_status(
            "error",
            component=status_details["component"],
            phase="stdio",
            pluginRoot=str(PLUGIN_ROOT),
            runtimePython=sys.executable,
            runtimeDataDir=str(RUNTIME_DATA_DIR),
            serviceMode=status_details["serviceMode"],
            lastError=str(exc),
        )
        _append_mcp_log("mcp-error", error=str(exc), traceback=traceback.format_exc())
        raise
    else:
        heartbeat_stop.set()
        _write_mcp_status(
            "exited",
            component=status_details["component"],
            phase="stdio",
            pluginRoot=str(PLUGIN_ROOT),
            runtimePython=sys.executable,
            runtimeDataDir=str(RUNTIME_DATA_DIR),
            serviceMode=status_details["serviceMode"],
        )
        _append_mcp_log("mcp-exited")
    finally:
        heartbeat_stop.set()
        try:
            state.close()
        finally:
            _append_mcp_log("mcp-closed")


if __name__ == "__main__":
    main()
