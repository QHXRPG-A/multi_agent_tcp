"""Desktop-facing blueprint service for GuLiCode.

This module is intentionally a thin HTTP/JSON facade around project blueprint
files and the runtime control-plane data model. It keeps renderer and Electron
code away from Python package paths, runtime tokens, and direct file writes.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from .graph_control import GraphRuntimeControlPlane, graph_definition_from_dict
from .graph_runtime import GraphRuntime, GuLiCodeTopAgentProfile, TopAgentStartPlan

BLUEPRINT_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
DEFAULT_BLUEPRINT_ID = "default"
DEFAULT_BLUEPRINT_NAME = "Default Blueprint"


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

    def summary(self) -> Dict[str, Any]:
        return {
            "runId": self.run_id,
            "projectDir": str(self.project_dir),
            "blueprintId": self.blueprint_id,
            "executionMode": self.execution_mode,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


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
    ) -> Dict[str, Any]:
        raise RuntimeError(
            "desktop blueprint runtime v1 does not execute CLI workers; "
            "only run registration, initial queueing, status, events, and end are available"
        )


@dataclass
class DesktopBlueprintService:
    """Project blueprint persistence and validation facade."""

    now: Any = time.time
    _lock: Any = field(default_factory=threading.RLock, init=False, repr=False)
    _runs: Dict[str, DesktopBlueprintRun] = field(default_factory=dict, init=False, repr=False)

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
            return {
                "ok": True,
                "document": self.open_blueprint(
                    project_dir,
                    str(args.get("blueprintId", DEFAULT_BLUEPRINT_ID)),
                ),
            }
        if command == "blueprint.save":
            project_dir = request_project_dir(args)
            document = args.get("document")
            if not isinstance(document, dict):
                raise BlueprintServiceError("BAD_REQUEST", "document must be a JSON object")
            saved = self.save_blueprint(project_dir, document)
            return {"ok": True, "document": saved}
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
            return self.validate_blueprint(document)
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

        raise BlueprintServiceError("UNKNOWN_COMMAND", f"unsupported desktop blueprint command: {command!r}")

    def list_blueprints(self, project_dir: Path) -> list[Dict[str, Any]]:
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

    def validate_blueprint(self, document: Dict[str, Any]) -> Dict[str, Any]:
        errors: list[str] = []
        warnings: list[str] = []
        try:
            normalized = normalize_document(document)
            graph = graph_definition_from_dict(dict(normalized["graph"]))
            graph.validate_runnable()
        except Exception as exc:
            errors.append(str(exc))
        return {"ok": not errors, "errors": errors, "warnings": warnings}

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
            status = run.runtime.status_snapshot()["run"]
            summary = run.summary()
            summary["status"] = status["status"]
            summary["finalStatus"] = status.get("final_status")
            summary["endedAt"] = status.get("ended_at")
            filtered.append(summary)
        return sorted(filtered, key=lambda item: float(item.get("updatedAt", 0)), reverse=True)

    def start_blueprint_run(
        self,
        project_dir: Path,
        blueprint_id: str = DEFAULT_BLUEPRINT_ID,
        plan_data: Any = None,
        *,
        execution_mode: str = "status",
    ) -> Dict[str, Any]:
        execution_mode = str(execution_mode).strip().lower() or "status"
        if execution_mode != "status":
            raise BlueprintServiceError(
                "UNSUPPORTED_EXECUTION_MODE",
                "desktop blueprint runtime currently supports executionMode='status' only",
                details={"supported": ["status"]},
            )
        document = self.open_blueprint(project_dir, blueprint_id)
        try:
            graph = graph_definition_from_dict(dict(document["graph"]))
            graph.validate_runnable()
        except Exception as exc:
            raise BlueprintServiceError(
                "INVALID_BLUEPRINT_GRAPH",
                str(exc),
                details={"blueprintId": str(document["id"])},
            ) from exc

        if not isinstance(plan_data, dict):
            raise BlueprintServiceError(
                "BAD_START_PLAN",
                "plan must be a complete TopAgentStartPlan JSON object",
            )
        try:
            plan = TopAgentStartPlan.from_dict(plan_data)
        except Exception as exc:
            raise BlueprintServiceError(
                "BAD_START_PLAN",
                str(exc),
                details={"blueprintId": str(document["id"])},
            ) from exc

        runtime = GraphRuntime(DesktopBlueprintNoopBackend())
        control = GraphRuntimeControlPlane(runtime, graph, top_agent=GuLiCodeTopAgentProfile())
        started = control.handle_request({"command": "run.start", "args": {"plan": plan.to_dict()}})
        if not started.get("ok"):
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
                run_id=self._generate_run_id_locked(),
                project_dir=validate_project_dir(project_dir),
                blueprint_id=str(document["id"]),
                document=document,
                graph=graph,
                runtime=runtime,
                control=control,
                execution_mode=execution_mode,
                created_at=now,
                updated_at=now,
            )
            self._runs[run.run_id] = run
        status = runtime.status_snapshot(graph=graph)
        return {
            "ok": True,
            "runId": run.run_id,
            "run": run.summary(),
            "validation": started.get("validation"),
            "queuedMessages": started.get("queued_messages", []),
            "startManifest": started.get("start_manifest", {}),
            "status": status,
        }

    def status_blueprint_run(self, run_id: str) -> Dict[str, Any]:
        with self._lock:
            run = self._get_run(run_id)
            run.updated_at = float(self.now())
            return {
                "ok": True,
                "runId": run.run_id,
                "run": run.summary(),
                "status": run.runtime.status_snapshot(graph=run.graph),
                "explanation": run.runtime.explain_status(graph=run.graph),
            }

    def recent_blueprint_events(self, run_id: str, *, limit: int = 20) -> Dict[str, Any]:
        with self._lock:
            run = self._get_run(run_id)
            run.updated_at = float(self.now())
            status = run.runtime.status_snapshot(graph=run.graph, recent_events_limit=limit)
            return {
                "ok": True,
                "runId": run.run_id,
                "limit": limit,
                "events": status["recent_events"],
            }

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
            run_status = run.runtime.status_snapshot()["run"]
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
                end_result = run.runtime.end_run(action, reason=reason, archive=False).to_dict()
            run.updated_at = float(self.now())
            response: Dict[str, Any] = {
                "ok": True,
                "runId": run.run_id,
                "run": run.summary(),
                "end": end_result,
                "status": run.runtime.status_snapshot(graph=run.graph),
            }
            if already_ended:
                response["alreadyEnded"] = True
            return response

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


def coerce_event_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        raise BlueprintServiceError("BAD_REQUEST", "limit must be an integer") from None
    return max(0, min(200, limit))


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
    schema_version = int(data.get("schema_version", 1))
    if schema_version != 1:
        raise BlueprintServiceError("INVALID_DOCUMENT", "unsupported blueprint document schema_version")
    return {
        "schema_version": 1,
        "id": blueprint_id,
        "name": str(data.get("name") or DEFAULT_BLUEPRINT_NAME),
        "graph": graph,
        "ui": ui,
    }


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
