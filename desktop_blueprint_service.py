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
import re
import secrets
import socket
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Callable, Dict, Optional, Sequence
from urllib.parse import parse_qs, urlparse

from .cluster import CLIWorkerBackend
from .blueprint_mcp_runtime import RunMCPRuntimeHandle
from .graph_control import GraphRuntimeControlPlane, graph_definition_from_dict
from .graph_runtime import GraphRuntime, GuLiCodeTopAgentProfile, TopAgentStartPlan
from .skill_space import SkillRecord
from .workspace_manager import DulwichWorkspaceManager
from .workspace_rpc import WorkspaceRPCServer

BLUEPRINT_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+)")
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
        loop = self._ensure_started()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

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
        if self.mcp is not None:
            data["mcp"] = self.mcp.summary()
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
    """SkillSpace-compatible view over the desktop blueprint skill directory."""

    def __init__(self, skill_dir: Optional[Path]) -> None:
        self.skill_dir = Path(skill_dir).expanduser().resolve() if skill_dir is not None else None
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
            if self.skill_dir is not None:
                try:
                    rec.skill_dir.resolve().relative_to(self.skill_dir.resolve())
                except ValueError as exc:
                    raise ValueError(f"skill path escapes desktop skill directory: {rec.skill_dir}") from exc
            resolved.append(rec)
        return resolved

    def _scan_records(self) -> Dict[str, SkillRecord]:
        if self.skill_dir is None or not self.skill_dir.is_dir():
            return {}
        records: Dict[str, SkillRecord] = {}
        for child in sorted(self.skill_dir.iterdir()):
            skill_md = child / "SKILL.md"
            if not child.is_dir() or not skill_md.is_file():
                continue
            name = child.name
            records[name] = SkillRecord(
                skill_hash=name,
                name=name,
                description=_description_from_skill_md(skill_md),
                skill_dir=child.resolve(),
                skill_md_path=skill_md.resolve(),
            )
        return records


@dataclass
class DesktopBlueprintService:
    """Project blueprint persistence and validation facade."""

    now: Any = time.time
    _lock: Any = field(default_factory=threading.RLock, init=False, repr=False)
    _runs: Dict[str, DesktopBlueprintRun] = field(default_factory=dict, init=False, repr=False)
    _async_loop: DesktopAsyncLoop = field(default_factory=DesktopAsyncLoop, init=False, repr=False)
    _stream_tokens: Dict[str, Dict[str, Any]] = field(default_factory=dict, init=False, repr=False)

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
            status = self._runtime_call(run, lambda: run.runtime.status_snapshot()["run"])
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

        with self._lock:
            run_id = self._generate_run_id_locked()

        if execution_mode == "live":
            backend, runtime, control, mcp, started = self._async_loop.run(
                self._start_live_runtime(run_id, validate_project_dir(project_dir), document, graph, plan)
            )
        else:
            backend = DesktopBlueprintNoopBackend()
            runtime = GraphRuntime(backend)
            control = GraphRuntimeControlPlane(runtime, graph, top_agent=GuLiCodeTopAgentProfile())
            mcp = None
            runtime.agent_stream_run_id = run_id
            started = control.handle_request({"command": "run.start", "args": {"plan": plan.to_dict()}})
        if not started.get("ok"):
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
            )
            self._attach_stream_notification(run)
            self._runs[run.run_id] = run
        status = self._runtime_call(run, lambda: runtime.status_snapshot(graph=graph))
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
                "status": self._runtime_call(run, lambda: run.runtime.status_snapshot(graph=run.graph)),
                "explanation": self._runtime_call(run, lambda: run.runtime.explain_status(graph=run.graph)),
            }

    def recent_blueprint_events(self, run_id: str, *, limit: int = 20) -> Dict[str, Any]:
        with self._lock:
            run = self._get_run(run_id)
            run.updated_at = float(self.now())
            status = self._runtime_call(
                run,
                lambda: run.runtime.status_snapshot(graph=run.graph, recent_events_limit=limit),
            )
            return {
                "ok": True,
                "runId": run.run_id,
                "limit": limit,
                "events": status["recent_events"],
            }

    async def _start_live_runtime(
        self,
        run_id: str,
        project_dir: Path,
        document: Dict[str, Any],
        graph: Any,
        plan: TopAgentStartPlan,
    ) -> tuple[Any, GraphRuntime, GraphRuntimeControlPlane, Optional[RunMCPRuntimeHandle], Dict[str, Any]]:
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
            rpc_server = WorkspaceRPCServer(manager, workspace_run)
            rpc_server.start()
            runtime = GraphRuntime(
                backend,
                enforce_private_agent_context=True,
                private_context_manager=manager,
                private_context_run=workspace_run,
                private_context_rpc_server=rpc_server,
                skill_space=_desktop_skill_catalog_from_document(document, project_dir),
                message_journal_path=workspace_run.shared_dir / "logs" / "message_journal.jsonl",
            )
            runtime.agent_stream_run_id = run_id
            control = GraphRuntimeControlPlane(runtime, graph, top_agent=GuLiCodeTopAgentProfile())
            top_agent_node = control.top_agent.to_agent_node()
            mcp = RunMCPRuntimeHandle(
                run_id=run_id,
                runtime=runtime,
                control=control,
                graph=graph,
                workspace_rpc_server=rpc_server,
                manager=manager,
                workspace_run=workspace_run,
                runtime_loop=self._async_loop,
                top_agent_node_id=top_agent_node.node_id,
                top_agent_id=top_agent_node.runtime_agent_id,
                close_run_callback=lambda **kwargs: self._end_live_run_from_mcp(run_id, **kwargs),
            )
            mcp.start()
            runtime.private_context_mcp_provider = mcp.provision_context_for_node
            runtime.agent_message_context_callback = mcp.refresh_message_context
            started = await control.start_run(plan, prestart_all_agents=True)
            if started.get("ok"):
                runtime.start_tick_loop()
            return backend, runtime, control, mcp, started
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
            status = self._runtime_call(run, lambda: run.runtime.status_snapshot(graph=run.graph))
            node = run.graph.agent_nodes[node_id]
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
            result = self._async_loop.call(
                lambda: run.runtime.queue_agent_message(
                    node,
                    {"prompt": text.strip(), "type": "user_message"},
                    queue_mode=normalized_mode,
                ).to_dict()
            )
            run.updated_at = float(self.now())
            return {
                "ok": True,
                "runId": run.run_id,
                "nodeId": node_id,
                "mode": normalized_mode,
                "result": result,
                "status": self._runtime_call(run, lambda: run.runtime.status_snapshot(graph=run.graph)),
            }

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
            events = self._runtime_call(run, lambda: run.runtime.agent_stream_events_after(next_cursor))
            for event in events:
                send(event)
                next_cursor = max(next_cursor, int(event.get("seq", next_cursor)))
            status = self._runtime_call(run, lambda: run.runtime.status_snapshot()["run"])
            if status.get("status") in {"completed", "cancelled", "failed"} and not events:
                return
            with run.stream_condition:
                run.stream_condition.wait(timeout=15.0)

    def _attach_stream_notification(self, run: DesktopBlueprintRun) -> None:
        def notify(_event: Dict[str, Any]) -> None:
            with run.stream_condition:
                run.stream_condition.notify_all()

        run.runtime.agent_stream_event_callback = notify

    def _runtime_call(self, run: DesktopBlueprintRun, fn: Callable[[], Any]) -> Any:
        if run.execution_mode == "live":
            return self._async_loop.call(fn)
        return fn()

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
            run.updated_at = float(self.now())
        if should_close_backend:
            self._async_loop.run(self._close_live_run_backend(run), timeout=10)
        with run.stream_condition:
            run.stream_condition.notify_all()
        return end_result

    def close(self) -> None:
        with self._lock:
            runs = list(self._runs.values())
        for run in runs:
            if run.execution_mode == "live":
                try:
                    self._async_loop.run(self._close_live_run(run), timeout=10)
                except Exception:
                    pass
            with run.stream_condition:
                run.stream_condition.notify_all()
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
    ui = document.get("ui", {})
    config = ui.get("config", {}) if isinstance(ui, dict) else {}
    raw_skill_dir = config.get("skill_dir") if isinstance(config, dict) else None
    if not isinstance(raw_skill_dir, str) or not raw_skill_dir.strip():
        return DesktopBlueprintSkillCatalog(None)
    skill_dir = Path(raw_skill_dir).expanduser()
    return DesktopBlueprintSkillCatalog(skill_dir)


def _description_from_skill_md(skill_md: Path) -> str:
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return ""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                stripped = line.strip()
                if stripped.startswith("description:"):
                    return stripped.split(":", 1)[1].strip().strip("\"'")
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
    if _document_uses_skill_dir(document):
        required.add("skill_dir")
    if _document_uses_rule_dir(document):
        required.add("rule_dir")

    issues: list[Dict[str, str]] = []
    for field_name in ("python_path", "project_workdir", "skill_dir", "rule_dir"):
        raw_value = config.get(field_name) if isinstance(config, dict) else None
        value = raw_value.strip() if isinstance(raw_value, str) else ""
        if not value:
            if field_name in required:
                issues.append({"field": field_name, "reason": "missing"})
            continue
        if not _is_absolute_blueprint_path(value):
            issues.append({"field": field_name, "reason": "not_absolute"})
    return issues


def document_with_common_config_paths(document: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_document(document)
    config = _blueprint_common_config(normalized)
    project_workdir = str(config.get("project_workdir") or "").strip()
    rule_dir = str(config.get("rule_dir") or "").strip()
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
            if rule_dir and isinstance(node.get("rule_paths"), list):
                node["rule_paths"] = [
                    _rule_path_from_common_config(raw_rule_path, rule_dir)
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


def _document_uses_skill_dir(document: Dict[str, Any]) -> bool:
    for raw_node in _document_agent_nodes(document).values():
        if not isinstance(raw_node, dict):
            continue
        skills = raw_node.get("skills")
        if isinstance(skills, list) and any(str(item).strip() for item in skills):
            return True
        selection = raw_node.get("skill_selection")
        if not isinstance(selection, dict):
            continue
        mode = str(selection.get("mode") or "").strip()
        if mode in {"all", "upstream"}:
            return True
        if mode == "selected":
            hashes = selection.get("skill_hashes")
            if not isinstance(hashes, list) or any(str(item).strip() for item in hashes):
                return True
    return False


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


def _rule_path_from_common_config(raw_rule_path: Any, rule_dir: str) -> str:
    value = str(raw_rule_path).strip()
    if not value:
        return value
    root = Path(rule_dir).expanduser().resolve()
    source = Path(value).expanduser()
    if not _is_absolute_blueprint_path(value):
        source = root / value
    source = source.resolve()
    try:
        source.relative_to(root)
    except ValueError as exc:
        raise BlueprintServiceError(
            "BLUEPRINT_RULE_PATH_OUTSIDE_CONFIG",
            f"rule path is outside configured rule_dir: {value}",
            details={"rulePath": value, "ruleDir": str(root)},
        ) from exc
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
