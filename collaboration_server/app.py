from __future__ import annotations

import uuid
import time
import json
import math
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse

from . import admin
from .auth import (
    APIError,
    SESSION_COOKIE,
    CurrentUser,
    admin_user,
    authenticate,
    client_ip,
    current_user,
    get_store,
    request_id,
    require_csrf,
    role_capabilities,
)
from .events import events_after, mirror_runtime_events, sse_event_stream
from .observability import (
    clamp_message,
    client_log_context,
    configure_observability,
    log_event,
    reset_log_context,
    set_log_context,
)
from .projection import (
    artifact_items,
    diff_summary,
    project_summary,
    report_items,
    run_summary,
    runtime_event_from_row,
    scrub_payload,
    status_projection,
    user_summary,
)
from .runtime_bridge import DesktopRuntimeBridge, RuntimeBridge
from .runtime_bridge import DesktopControlBridge, DesktopControlBridgeProtocol
from .schemas import (
    ClientLogBatchRequest,
    DesktopBridgeRegistrationRequest,
    DesktopBlueprintSnapshotRequest,
    DesktopSessionSnapshotRequest,
    HealthResponse,
    LoginRequest,
    MobileDesktopSessionDeleteRequest,
    MobileDesktopSubmitRequest,
    PlanningPlanRejectRequest,
    PlanningQuestionAnswerRequest,
    PlanningRequestClaim,
    PlanningRequestCreate,
    PlanningRequestDesktopState,
    RegisterRequest,
    RunApprovalRequest,
    RunEndRequest,
    RunMessageRequest,
    RunStartRequest,
)
from .store import CollaborationStore, iso_time, normalize_status


BridgeFactory = Callable[[], RuntimeBridge]
DesktopBridgeFactory = Callable[[], DesktopControlBridgeProtocol]


def create_app(
    *,
    db_path: str | Path = "logs/collaboration_server.sqlite3",
    seed_config: str | Path | None = None,
    bridge_factory: Optional[BridgeFactory] = None,
    desktop_bridge_factory: Optional[DesktopBridgeFactory] = None,
    secure_cookies: bool = False,
    log_dir: str | Path | None = None,
    log_level: str = "INFO",
) -> FastAPI:
    if log_dir is not None:
        configure_observability(log_dir=log_dir, log_level=log_level)
    store = CollaborationStore(db_path)
    store.seed_from_file(seed_config)
    app = FastAPI(title="GuLiCode Collaboration Server", version="0.1.0")
    app.state.store = store
    app.state.bridge_factory = bridge_factory or (lambda: DesktopRuntimeBridge())
    app.state.desktop_bridge_factory = desktop_bridge_factory or (lambda: DesktopControlBridge())
    app.state.secure_cookies = secure_cookies
    app.middleware("http")(_request_id_middleware)
    app.add_exception_handler(APIError, _api_error_handler)
    app.add_exception_handler(KeyError, _key_error_handler)
    app.include_router(admin.router)
    _register_routes(app)
    return app


async def _request_id_middleware(request: Request, call_next: Any) -> Response:
    rid = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:12]}"
    request.state.request_id = rid
    started = time.monotonic()
    token = set_log_context(request_id=rid, path=str(request.url.path))
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = (time.monotonic() - started) * 1000
        log_event(
            "error",
            "api.error",
            request_id=rid,
            user_id=_request_user_id(request),
            path=str(request.url.path),
            duration_ms=duration_ms,
            method=request.method,
            error_type=type(exc).__name__,
            message=str(exc),
        )
        raise
    finally:
        reset_log_context(token)
    response.headers["x-request-id"] = rid
    duration_ms = (time.monotonic() - started) * 1000
    log_event(
        "info" if response.status_code < 400 else "warning",
        "api.request",
        request_id=rid,
        user_id=_request_user_id(request),
        path=str(request.url.path),
        status=response.status_code,
        duration_ms=duration_ms,
        method=request.method,
    )
    return response


async def _api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    event = "api.permission_denied" if exc.status_code in {401, 403} else "api.error"
    log_event(
        "warning" if exc.status_code < 500 else "error",
        event,
        request_id=request_id(request),
        user_id=_request_user_id(request),
        path=str(request.url.path),
        status=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )
    request.app.state.store.audit(
        action="api.error",
        status="error",
        request_id=request_id(request),
        code=exc.code,
        summary={"message": exc.message, "path": request.url.path},
    )
    payload: dict[str, Any] = {
        "ok": False,
        "code": exc.code,
        "message": exc.message,
        "requestId": request_id(request),
    }
    if exc.details:
        payload["details"] = scrub_payload(exc.details)
    return JSONResponse(payload, status_code=exc.status_code)


async def _key_error_handler(request: Request, exc: KeyError) -> JSONResponse:
    log_event(
        "warning",
        "api.error",
        request_id=request_id(request),
        user_id=_request_user_id(request),
        path=str(request.url.path),
        status=404,
        code="NOT_FOUND",
        message=str(exc),
    )
    payload = {
        "ok": False,
        "code": "NOT_FOUND",
        "message": str(exc),
        "requestId": request_id(request),
    }
    return JSONResponse(payload, status_code=404)


def _register_routes(app: FastAPI) -> None:
    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.post("/api/auth/register")
    def register(payload: RegisterRequest, request: Request, store: CollaborationStore = Depends(get_store)) -> dict[str, Any]:
        try:
            row = store.create_user(payload.username, payload.password, role="user", active=True)
        except Exception as exc:
            raise APIError(400, "REGISTER_FAILED", str(exc)) from exc
        store.audit(action="auth.register", status="ok", request_id=request_id(request), user_id=row["id"])
        request.state.user_id = str(row["id"])
        return {"ok": True, "user": user_summary(row)}

    @app.post("/api/auth/login")
    def login(payload: LoginRequest, request: Request, response: Response, store: CollaborationStore = Depends(get_store)) -> dict[str, Any]:
        user = authenticate(store, payload.username, payload.password, ip=client_ip(request))
        session = store.create_session(
            str(user["id"]),
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
            client_kind=payload.clientKind,
        )
        response.set_cookie(
            SESSION_COOKIE,
            str(session["id"]),
            httponly=True,
            secure=bool(request.app.state.secure_cookies),
            samesite="lax",
            max_age=30 * 24 * 60 * 60,
            path="/",
        )
        request.state.user_id = str(user["id"])
        store.audit(action="auth.login", status="ok", request_id=request_id(request), user_id=str(user["id"]))
        return {
            "ok": True,
            "user": user_summary(user),
            "csrfToken": session["csrf_token"],
            **_client_sync_payload(store, str(user["id"])),
        }

    @app.post("/api/auth/logout")
    def logout(
        response: Response,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        store.revoke_session(user.session_id)
        response.delete_cookie(SESSION_COOKIE, path="/")
        store.audit(action="auth.logout", status="ok", user_id=user.id)
        return {"ok": True}

    @app.get("/api/me")
    def me(user: CurrentUser = Depends(current_user), store: CollaborationStore = Depends(get_store)) -> dict[str, Any]:
        row = store.get_user(user.id)
        if not row:
            raise APIError(401, "UNAUTHORIZED", "login required")
        return {"ok": True, "user": user_summary(row), "csrfToken": user.csrf_token, **_client_sync_payload(store, user.id)}

    @app.get("/api/mobile/tick")
    def mobile_tick(
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        row = store.get_user(user.id)
        if not row:
            raise APIError(401, "UNAUTHORIZED", "login required")
        payload: dict[str, Any] = {
            "ok": True,
            "user": user_summary(row),
            "csrfToken": user.csrf_token,
            **_client_sync_payload(store, user.id),
            "project": None,
            "run": None,
            "status": None,
            "desktopSessions": _mobile_desktop_sessions_payload(store, user.id),
        }
        if not payload["syncReady"]:
            return payload

        projects = store.list_projects_for_user(user.id)
        if not projects:
            return payload
        project = projects[0]
        role = str(project["member_role"])
        latest = _latest_project_run(request, project, store)
        payload["project"] = project_summary(project, role, role_capabilities(role), latest)
        if not latest:
            binding = store.get_active_binding(str(project["id"]))
            blueprint_id = str(binding["blueprint_id"]) if binding else "default"
            snapshot = store.get_desktop_blueprint_snapshot(str(project["id"]), blueprint_id)
            if not snapshot:
                snapshot = store.get_desktop_blueprint_snapshot(str(project["id"]), "default")
            if snapshot:
                payload["status"] = _desktop_snapshot_tick_status(project, snapshot)
            return payload

        run = store.get_run(latest.id)
        if not run:
            return payload
        try:
            binding = _binding_for_run(store, run)
            status_payload = _bridge(request).status(binding, str(run["runtime_run_id"]))
        except APIError:
            payload["run"] = run_summary(run)
            snapshot = store.get_desktop_blueprint_snapshot(str(project["id"]), str(run["blueprint_id"]))
            if snapshot:
                payload["status"] = _desktop_snapshot_tick_status(project, snapshot, run=payload["run"])
            return payload
        updated = store.upsert_run_from_runtime(
            str(run["project_id"]),
            str(run["blueprint_id"]),
            str(run["runtime_run_id"]),
            _runtime_run_payload(str(run["runtime_run_id"]), status_payload, run),
        )
        projection = status_projection(run_summary(updated), status_payload, [], None)
        payload["run"] = run_summary(updated)
        runtime_status = _mobile_tick_status_projection(projection)
        snapshot = store.get_desktop_blueprint_snapshot(str(project["id"]), str(updated["blueprint_id"]))
        if snapshot:
            snapshot_status = _desktop_snapshot_tick_status(project, snapshot, run=payload["run"])
            payload["status"] = _merge_desktop_snapshot_runtime_status(snapshot_status, runtime_status)
        else:
            payload["status"] = runtime_status
        return payload

    @app.get("/api/mobile/desktop-sessions")
    def mobile_desktop_sessions(
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        return {"ok": True, **_mobile_desktop_sessions_payload(store, user.id)}

    @app.post("/api/mobile/desktop-submit", dependencies=[Depends(require_csrf)])
    def mobile_desktop_submit(
        payload: MobileDesktopSubmitRequest,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        request_payload = {
            "sessionId": payload.sessionId,
            "mode": payload.mode,
            "promptMode": payload.promptMode,
            "agentName": payload.agentName,
            "text": payload.text,
        }
        bridge = store.get_active_desktop_bridge(user.id)
        interaction = store.create_desktop_interaction(
            user_id=user.id,
            mobile_session_id=user.session_id,
            desktop_session_id=str(bridge["session_id"]) if bridge else None,
            interaction_type="session.submit",
            status="pending" if bridge else "desktop_unavailable",
            request_payload=scrub_payload(request_payload),
        )
        if not bridge:
            store.audit(
                action="mobile.desktop_submit",
                status="desktop_unavailable",
                request_id=request_id(request),
                user_id=user.id,
                summary={"interactionId": interaction["id"]},
            )
            return {
                "ok": True,
                "interaction": _desktop_interaction_summary(interaction),
                "accepted": False,
                "status": "desktop_unavailable",
            }
        try:
            result = _desktop_bridge(request).request(
                bridge,
                "desktop.session.submit",
                {
                    "interactionId": str(interaction["id"]),
                    "sessionId": payload.sessionId,
                    "mode": payload.mode,
                    "promptMode": payload.promptMode,
                    "agentName": payload.agentName,
                    "text": payload.text,
                    "createIfMissing": True,
                },
            )
        except APIError as exc:
            failed = store.update_desktop_interaction(str(interaction["id"]), status="failed", error=exc.message)
            store.audit(
                action="mobile.desktop_submit",
                status="error",
                request_id=request_id(request),
                user_id=user.id,
                code=exc.code,
                summary={"interactionId": interaction["id"]},
            )
            return {
                "ok": True,
                "interaction": _desktop_interaction_summary(failed),
                "accepted": False,
                "status": "failed",
                "error": exc.message,
            }
        accepted = result.get("accepted", result.get("ok", True)) is not False
        updated = store.update_desktop_interaction(
            str(interaction["id"]),
            status="accepted" if accepted else "rejected",
            response_payload=scrub_payload(result),
        )
        store.audit(
            action="mobile.desktop_submit",
            status="ok" if accepted else "rejected",
            request_id=request_id(request),
            user_id=user.id,
            summary={"interactionId": interaction["id"], "accepted": accepted},
        )
        return {
            "ok": True,
            "interaction": _desktop_interaction_summary(updated),
            "accepted": accepted,
            "status": "accepted" if accepted else "rejected",
            "result": scrub_payload(result),
        }

    @app.post("/api/mobile/desktop-session-delete", dependencies=[Depends(require_csrf)])
    def mobile_desktop_session_delete(
        payload: MobileDesktopSessionDeleteRequest,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        request_payload = {"sessionId": payload.sessionId}
        bridge = store.get_active_desktop_bridge(user.id)
        interaction = store.create_desktop_interaction(
            user_id=user.id,
            mobile_session_id=user.session_id,
            desktop_session_id=str(bridge["session_id"]) if bridge else None,
            interaction_type="session.delete",
            status="pending" if bridge else "desktop_unavailable",
            request_payload=scrub_payload(request_payload),
        )
        if not bridge:
            store.audit(
                action="mobile.desktop_session_delete",
                status="desktop_unavailable",
                request_id=request_id(request),
                user_id=user.id,
                summary={"interactionId": interaction["id"]},
            )
            return {
                "ok": True,
                "interaction": _desktop_interaction_summary(interaction),
                "accepted": False,
                "status": "desktop_unavailable",
            }
        try:
            result = _desktop_bridge(request).request(
                bridge,
                "desktop.session.delete",
                {
                    "interactionId": str(interaction["id"]),
                    "sessionId": payload.sessionId,
                },
            )
        except APIError as exc:
            failed = store.update_desktop_interaction(str(interaction["id"]), status="failed", error=exc.message)
            store.audit(
                action="mobile.desktop_session_delete",
                status="error",
                request_id=request_id(request),
                user_id=user.id,
                code=exc.code,
                summary={"interactionId": interaction["id"]},
            )
            return {
                "ok": True,
                "interaction": _desktop_interaction_summary(failed),
                "accepted": False,
                "status": "failed",
                "error": exc.message,
            }
        accepted = result.get("accepted", result.get("ok", True)) is not False
        updated = store.update_desktop_interaction(
            str(interaction["id"]),
            status="accepted" if accepted else "rejected",
            response_payload=scrub_payload(result),
        )
        store.audit(
            action="mobile.desktop_session_delete",
            status="ok" if accepted else "rejected",
            request_id=request_id(request),
            user_id=user.id,
            summary={"interactionId": interaction["id"], "accepted": accepted},
        )
        return {
            "ok": True,
            "interaction": _desktop_interaction_summary(updated),
            "accepted": accepted,
            "status": "accepted" if accepted else "rejected",
            "result": scrub_payload(result),
        }

    @app.post("/api/desktop/blueprint-snapshot", dependencies=[Depends(require_csrf)])
    def desktop_blueprint_snapshot(
        payload: DesktopBlueprintSnapshotRequest,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        project = _desktop_snapshot_project(store, user, payload)
        role = _require_project_access(store, user, str(project["id"]))
        _require_capability(role, "run:create")
        snapshot_payload = scrub_payload(payload.model_dump())
        title = payload.title or str(project["name"])
        row = store.upsert_desktop_blueprint_snapshot(
            project_id=str(project["id"]),
            blueprint_id=payload.blueprintId,
            user_id=user.id,
            title=title,
            payload=snapshot_payload,
        )
        store.audit(
            action="desktop.blueprint_snapshot",
            status="ok",
            request_id=request_id(request),
            user_id=user.id,
            project_id=str(project["id"]),
            summary={"blueprintId": payload.blueprintId, "nodes": len(payload.nodes), "edges": len(payload.edges)},
        )
        return {
            "ok": True,
            "snapshot": {
                "projectId": str(row["project_id"]),
                "blueprintId": str(row["blueprint_id"]),
                "title": str(row["title"]),
                "updatedAt": iso_time(row["updated_at"]),
            },
        }

    @app.post("/api/desktop/bridge", dependencies=[Depends(require_csrf)])
    def desktop_bridge_registration(
        payload: DesktopBridgeRegistrationRequest,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        _require_desktop_session(user)
        bridge_url = _require_loopback_bridge_url(payload.bridgeUrl)
        row = store.upsert_desktop_bridge(
            user_id=user.id,
            session_id=user.session_id,
            bridge_url=bridge_url,
            bridge_token=payload.bridgeToken,
        )
        store.audit(
            action="desktop.bridge_register",
            status="ok",
            request_id=request_id(request),
            user_id=user.id,
            summary={"desktopSessionId": _id_suffix(user.session_id), "bridgeUrl": bridge_url},
        )
        return {
            "ok": True,
            "desktopBridge": {
                "desktopSessionId": _id_suffix(str(row["session_id"])),
                "bridgeUrl": str(row["bridge_url"]),
                "updatedAt": iso_time(row["updated_at"]),
            },
        }

    @app.post("/api/desktop/session-snapshot", dependencies=[Depends(require_csrf)])
    def desktop_session_snapshot(
        payload: DesktopSessionSnapshotRequest,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        _require_desktop_session(user)
        snapshot_payload = {
            "activeSessionId": payload.activeSessionId,
            "sessions": [item.model_dump() for item in payload.sessions],
            "currentMessages": [item.model_dump() for item in payload.currentMessages],
            "composer": payload.composer.model_dump() if payload.composer else None,
            "updatedAt": payload.updatedAt,
        }
        row = store.upsert_desktop_session_snapshot(
            user_id=user.id,
            desktop_session_id=user.session_id,
            active_session_id=payload.activeSessionId,
            payload=scrub_payload(snapshot_payload),
        )
        store.audit(
            action="desktop.session_snapshot",
            status="ok",
            request_id=request_id(request),
            user_id=user.id,
            summary={
                "activeSessionId": payload.activeSessionId,
                "sessions": len(payload.sessions),
                "messages": len(payload.currentMessages),
                "composerModes": len(payload.composer.modes) if payload.composer else 0,
            },
        )
        return {
            "ok": True,
            "desktopSessions": {
                "activeSessionId": row.get("active_session_id"),
                "updatedAt": iso_time(row["updated_at"]),
            },
        }

    @app.get("/api/projects")
    def projects(request: Request, user: CurrentUser = Depends(current_user), store: CollaborationStore = Depends(get_store)) -> dict[str, Any]:
        result = []
        for row in store.list_projects_for_user(user.id):
            role = str(row["member_role"])
            latest = _latest_project_run(request, row, store)
            result.append(project_summary(row, role, role_capabilities(role), latest))
        return {"ok": True, "projects": result}

    @app.get("/api/projects/{project_id}/runs")
    def project_runs(
        project_id: str,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        _require_project_access(store, user, project_id)
        _sync_project_runs(request, project_id, store)
        runs = [run_summary(row) for row in store.list_runs_for_project(project_id)]
        return {"ok": True, "runs": runs}

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str, user: CurrentUser = Depends(current_user), store: CollaborationStore = Depends(get_store)) -> dict[str, Any]:
        run = _run_for_user(store, user, run_id)
        return {"ok": True, "run": run_summary(run)}

    @app.get("/api/runs/{run_id}/status")
    def run_status(
        run_id: str,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        run = _run_for_user(store, user, run_id)
        binding = _binding_for_run(store, run)
        bridge = _bridge(request)
        status_payload = bridge.status(binding, str(run["runtime_run_id"]))
        raw_events = bridge.recent_events(binding, str(run["runtime_run_id"]), limit=100)
        mirror_runtime_events(store, run, raw_events)
        events = events_after(store, str(run["id"]), 0, limit=200)
        try:
            diff = diff_summary(bridge.run_diff(binding, str(run["runtime_run_id"])))
        except APIError:
            diff = None
        updated = store.upsert_run_from_runtime(
            str(run["project_id"]),
            str(run["blueprint_id"]),
            str(run["runtime_run_id"]),
            _runtime_run_payload(str(run["runtime_run_id"]), status_payload, run),
        )
        return {"ok": True, "status": status_projection(run_summary(updated), status_payload, events, diff)}

    @app.get("/api/runs/{run_id}/events")
    def run_events(
        run_id: str,
        request: Request,
        cursor: int = 0,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        run = _run_for_user(store, user, run_id)
        _sync_run_events(request, run, store)
        events = events_after(store, run_id, cursor, limit=100)
        log_event(
            "info",
            "events.replay",
            request_id=request_id(request),
            user_id=user.id,
            path=str(request.url.path),
            run_id=run_id,
            cursor=cursor,
            returned_count=len(events),
            last_cursor=events[-1].cursor if events else str(cursor or 0),
        )
        return {"ok": True, "events": events, "lastCursor": events[-1].cursor if events else str(cursor or 0)}

    @app.get("/api/runs/{run_id}/stream")
    def run_stream(
        run_id: str,
        request: Request,
        cursor: int = 0,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> StreamingResponse:
        run = _run_for_user(store, user, run_id)

        def sync_events() -> None:
            _sync_run_events(request, run, store)

        return StreamingResponse(
            sse_event_stream(
                request,
                store=store,
                run=run,
                sync_events=sync_events,
                cursor=cursor,
                request_id=request_id(request),
                user_id=user.id,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/runs/{run_id}/agents/{node_id}")
    def agent_snapshot(
        run_id: str,
        node_id: str,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        run = _run_for_user(store, user, run_id)
        binding = _binding_for_run(store, run)
        payload = _bridge(request).agent_info(binding, str(run["runtime_run_id"]), node_id)
        return {"ok": True, "agent": scrub_payload(payload)}

    @app.get("/api/runs/{run_id}/diff")
    def run_diff(
        run_id: str,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        run = _run_for_user(store, user, run_id)
        binding = _binding_for_run(store, run)
        payload = _bridge(request).run_diff(binding, str(run["runtime_run_id"]))
        return {"ok": True, "diff": diff_summary(payload)}

    @app.get("/api/runs/{run_id}/changesets/{changeset_id}/diff")
    def changeset_diff(
        run_id: str,
        changeset_id: str,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        if ".." in changeset_id or "/" in changeset_id or "\\" in changeset_id:
            raise APIError(400, "BAD_CHANGESET_ID", "changeset id is invalid")
        run = _run_for_user(store, user, run_id)
        binding = _binding_for_run(store, run)
        payload = _bridge(request).changeset_diff(binding, str(run["runtime_run_id"]), changeset_id)
        return {"ok": True, "changeset": scrub_payload(payload)}

    @app.get("/api/runs/{run_id}/reports")
    def reports(
        run_id: str,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        run = _run_for_user(store, user, run_id)
        binding = _binding_for_run(store, run)
        payload = _bridge(request).status(binding, str(run["runtime_run_id"]))
        return {"ok": True, "reports": report_items(payload)}

    @app.get("/api/runs/{run_id}/artifacts")
    def artifacts(
        run_id: str,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        run = _run_for_user(store, user, run_id)
        binding = _binding_for_run(store, run)
        payload = _bridge(request).status(binding, str(run["runtime_run_id"]))
        return {"ok": True, "artifacts": artifact_items(payload)}

    @app.post("/api/runs", dependencies=[Depends(require_csrf)])
    def start_run(
        payload: RunStartRequest,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        role = _require_project_access(store, user, payload.projectId)
        _require_capability(role, "run:create")
        binding = _binding_for_project(store, payload.projectId)
        plan = dict(payload.plan or {})
        if not plan:
            raise APIError(400, "BAD_START_PLAN", "plan must be a complete TopAgentStartPlan JSON object")
        started = _bridge(request).start_run(binding, plan, execution_mode=payload.executionMode)
        runtime_run_id = str(started.get("runId") or started.get("run_id") or "")
        if not runtime_run_id:
            raise APIError(502, "RUNTIME_BAD_RESPONSE", "runtime start did not return a runId")
        run = store.upsert_run_from_runtime(
            payload.projectId,
            str(payload.blueprintId or binding["blueprint_id"]),
            runtime_run_id,
            _runtime_run_payload(runtime_run_id, started, {"title": runtime_run_id}),
        )
        store.audit(
            action="run.start",
            status="ok",
            request_id=request_id(request),
            user_id=user.id,
            project_id=payload.projectId,
            run_id=str(run["id"]),
            summary={"runtimeRunId": runtime_run_id, "executionMode": payload.executionMode},
        )
        return {"ok": True, "run": run_summary(run), "started": scrub_payload(started)}

    @app.post("/api/runs/{run_id}/messages", dependencies=[Depends(require_csrf)])
    def run_message(
        run_id: str,
        payload: RunMessageRequest,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        run = _run_for_user(store, user, run_id)
        role = _require_project_access(store, user, str(run["project_id"]))
        _require_capability(role, "run:message")
        binding = _binding_for_run(store, run)
        result = _bridge(request).queue_agent_message(
            binding,
            str(run["runtime_run_id"]),
            payload.nodeId,
            payload.text,
            mode=payload.mode,
        )
        store.record_message(run_id, user.id, direction="mobile_to_agent", body=payload.text)
        store.audit(
            action="run.message",
            status="ok",
            request_id=request_id(request),
            user_id=user.id,
            project_id=str(run["project_id"]),
            run_id=run_id,
            summary={"nodeId": payload.nodeId, "mode": payload.mode},
        )
        return {"ok": True, "result": scrub_payload(result)}

    @app.post("/api/runs/{run_id}/end", dependencies=[Depends(require_csrf)])
    def run_end(
        run_id: str,
        payload: RunEndRequest,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        run = _run_for_user(store, user, run_id)
        role = _require_project_access(store, user, str(run["project_id"]))
        _require_capability(role, "run:end")
        binding = _binding_for_run(store, run)
        result = _bridge(request).end_run(
            binding,
            str(run["runtime_run_id"]),
            action=payload.action,
            reason=payload.reason or "cancelled from mobile",
        )
        updated = store.upsert_run_from_runtime(
            str(run["project_id"]),
            str(run["blueprint_id"]),
            str(run["runtime_run_id"]),
            _runtime_run_payload(str(run["runtime_run_id"]), result, run),
        )
        store.audit(
            action="run.end",
            status="ok",
            request_id=request_id(request),
            user_id=user.id,
            project_id=str(run["project_id"]),
            run_id=run_id,
            summary={"action": payload.action},
        )
        return {"ok": True, "run": run_summary(updated), "result": scrub_payload(result)}

    @app.post("/api/runs/{run_id}/approvals", dependencies=[Depends(require_csrf)])
    def run_approval(
        run_id: str,
        payload: RunApprovalRequest,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        run = _run_for_user(store, user, run_id)
        role = _require_project_access(store, user, str(run["project_id"]))
        _require_capability(role, "run:approve")
        reason = payload.reason or ""
        if payload.action == "approve_diff":
            record = store.record_approval(
                run_id,
                user.id,
                action=payload.action,
                changeset_id=payload.changesetId,
                status="approved",
                reason=reason,
            )
            store.audit(
                action="run.approve_diff",
                status="ok",
                request_id=request_id(request),
                user_id=user.id,
                project_id=str(run["project_id"]),
                run_id=run_id,
                summary={"changesetId": payload.changesetId},
            )
            return {"ok": True, "approval": _approval_summary(record)}

        changeset_id = str(payload.changesetId or "").strip()
        if not changeset_id:
            raise APIError(400, "CHANGESET_REQUIRED", "changesetId is required for rollback_diff")
        if ".." in changeset_id or "/" in changeset_id or "\\" in changeset_id:
            raise APIError(400, "BAD_CHANGESET_ID", "changeset id is invalid")
        binding = _binding_for_run(store, run)
        rollback = _bridge(request).rollback_changesets(
            binding,
            str(run["runtime_run_id"]),
            changeset_id,
            reason=reason or "rollback requested from mobile",
        )
        record = store.record_approval(
            run_id,
            user.id,
            action=payload.action,
            changeset_id=changeset_id,
            status="rolled_back" if rollback.get("ok") else "failed",
            reason=reason,
            payload=scrub_payload(rollback),
        )
        store.audit(
            action="run.rollback_diff",
            status="ok" if rollback.get("ok") else "error",
            request_id=request_id(request),
            user_id=user.id,
            project_id=str(run["project_id"]),
            run_id=run_id,
            summary={"changesetId": changeset_id},
        )
        return {"ok": bool(rollback.get("ok", True)), "approval": _approval_summary(record), "rollback": scrub_payload(rollback)}

    @app.post("/api/projects/{project_id}/planning-requests", dependencies=[Depends(require_csrf)])
    def create_planning_request(
        project_id: str,
        payload: PlanningRequestCreate,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        role = _require_project_access(store, user, project_id)
        _require_capability(role, "run:create")
        binding = _binding_for_project(store, project_id)
        row = store.create_planning_request(
            project_id=project_id,
            blueprint_id=str(payload.blueprintId or binding["blueprint_id"]),
            user_id=user.id,
            goal=payload.goal,
        )
        desktop_delivery = _try_send_mobile_planning_to_desktop(
            request,
            store,
            user,
            _planning_request_summary(row),
        )
        store.audit(
            action="planning_request.create",
            status="ok",
            request_id=request_id(request),
            user_id=user.id,
            project_id=project_id,
            summary={"planningRequestId": row["id"], "desktopDelivery": desktop_delivery.get("status")},
        )
        return {"ok": True, "planningRequest": _planning_request_summary(row), "desktopDelivery": desktop_delivery}

    @app.get("/api/projects/{project_id}/planning-requests")
    def list_planning_requests(
        project_id: str,
        status: str | None = None,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        _require_project_access(store, user, project_id)
        rows = store.list_planning_requests(project_id, status=status)
        return {"ok": True, "planningRequests": [_planning_request_summary(row) for row in rows]}

    @app.get("/api/planning-requests/{planning_request_id}")
    def get_planning_request(
        planning_request_id: str,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        row = _planning_request_for_user(store, user, planning_request_id)
        return {"ok": True, "planningRequest": _planning_request_summary(row)}

    @app.post("/api/planning-requests/{planning_request_id}/desktop-claim", dependencies=[Depends(require_csrf)])
    def claim_planning_request(
        planning_request_id: str,
        payload: PlanningRequestClaim,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        row = _planning_request_for_user(store, user, planning_request_id)
        role = _require_project_access(store, user, str(row["project_id"]))
        _require_capability(role, "run:create")
        updated = store.update_planning_request(
            planning_request_id,
            status="planning",
            desktop_session_id=payload.desktopSessionId,
            claimed_by_user_id=user.id,
        )
        store.audit(
            action="planning_request.claim",
            status="ok",
            request_id=request_id(request),
            user_id=user.id,
            project_id=str(row["project_id"]),
            summary={"planningRequestId": planning_request_id},
        )
        return {"ok": True, "planningRequest": _planning_request_summary(updated)}

    @app.post("/api/planning-requests/{planning_request_id}/desktop-state", dependencies=[Depends(require_csrf)])
    def update_planning_request_state(
        planning_request_id: str,
        payload: PlanningRequestDesktopState,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        row = _planning_request_for_user(store, user, planning_request_id)
        role = _require_project_access(store, user, str(row["project_id"]))
        _require_capability(role, "run:create")
        status = payload.status or _planning_status_from_snapshot(payload.pendingQuestion, payload.pendingPlan, payload.activeRun, payload.error)
        updated = store.update_planning_request(
            planning_request_id,
            status=status,
            planning_session_id=payload.planningSessionId,
            pending_question_json=payload.pendingQuestion,
            pending_plan_json=payload.pendingPlan,
            active_run_id=_run_id_from_active_run(payload.activeRun),
            error=payload.error,
        )
        store.audit(
            action="planning_request.desktop_state",
            status="ok",
            request_id=request_id(request),
            user_id=user.id,
            project_id=str(row["project_id"]),
            summary={"planningRequestId": planning_request_id, "status": status},
        )
        return {"ok": True, "planningRequest": _planning_request_summary(updated)}

    @app.post("/api/planning-requests/{planning_request_id}/answer", dependencies=[Depends(require_csrf)])
    def answer_planning_question(
        planning_request_id: str,
        payload: PlanningQuestionAnswerRequest,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        row = _planning_request_for_user(store, user, planning_request_id)
        role = _require_project_access(store, user, str(row["project_id"]))
        _require_capability(role, "run:create")
        answer = {
            "questionId": payload.questionId,
            "answers": payload.answers,
            "rejected": payload.rejected,
            "reason": payload.reason or "",
        }
        updated = store.update_planning_request(
            planning_request_id,
            status="question_answered",
            mobile_answer_json=answer,
        )
        store.audit(
            action="planning_request.answer",
            status="ok",
            request_id=request_id(request),
            user_id=user.id,
            project_id=str(row["project_id"]),
            summary={"planningRequestId": planning_request_id, "questionId": payload.questionId},
        )
        return {"ok": True, "planningRequest": _planning_request_summary(updated)}

    @app.post("/api/planning-requests/{planning_request_id}/reject-plan", dependencies=[Depends(require_csrf)])
    def reject_planning_plan(
        planning_request_id: str,
        payload: PlanningPlanRejectRequest,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        row = _planning_request_for_user(store, user, planning_request_id)
        role = _require_project_access(store, user, str(row["project_id"]))
        _require_capability(role, "run:create")
        updated = store.update_planning_request(
            planning_request_id,
            status="plan_rejected",
            error=payload.reason or "rejected from mobile",
        )
        store.audit(
            action="planning_request.reject_plan",
            status="ok",
            request_id=request_id(request),
            user_id=user.id,
            project_id=str(row["project_id"]),
            summary={"planningRequestId": planning_request_id},
        )
        return {"ok": True, "planningRequest": _planning_request_summary(updated)}

    @app.post("/api/planning-requests/{planning_request_id}/approve-plan", dependencies=[Depends(require_csrf)])
    def approve_planning_plan(
        planning_request_id: str,
        request: Request,
        user: CurrentUser = Depends(current_user),
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        row = _planning_request_for_user(store, user, planning_request_id)
        role = _require_project_access(store, user, str(row["project_id"]))
        _require_capability(role, "run:create")
        pending_plan = _json_field(row, "pending_plan_json")
        plan = pending_plan.get("plan") if isinstance(pending_plan, dict) else None
        if not isinstance(plan, dict) or not plan:
            raise APIError(400, "PLAN_NOT_READY", "no staged plan is ready for this planning request")
        planning_session_id = str(row.get("planning_session_id") or "")
        if not planning_session_id:
            raise APIError(400, "PLANNING_SESSION_REQUIRED", "planning session id is missing")
        binding = _binding_for_project(store, str(row["project_id"]))
        started = _bridge(request).start_run(binding, plan, execution_mode="live")
        runtime_run_id = str(started.get("runId") or started.get("run_id") or "")
        if not runtime_run_id:
            raise APIError(502, "RUNTIME_BAD_RESPONSE", "runtime start did not return a runId")
        marked = _bridge(request).mark_planning_plan_started(binding, planning_session_id, runtime_run_id, started)
        run = store.upsert_run_from_runtime(
            str(row["project_id"]),
            str(row["blueprint_id"]),
            runtime_run_id,
            _runtime_run_payload(runtime_run_id, started, {"title": runtime_run_id}),
        )
        updated = store.update_planning_request(
            planning_request_id,
            status="started",
            active_run_id=str(run["id"]),
            pending_plan_json=pending_plan,
        )
        store.audit(
            action="planning_request.approve_plan",
            status="ok",
            request_id=request_id(request),
            user_id=user.id,
            project_id=str(row["project_id"]),
            run_id=str(run["id"]),
            summary={"planningRequestId": planning_request_id, "runtimeRunId": runtime_run_id},
        )
        return {
            "ok": True,
            "planningRequest": _planning_request_summary(updated),
            "run": run_summary(run),
            "started": scrub_payload(started),
            "marked": scrub_payload(marked),
        }

    @app.post("/api/client-logs")
    def client_logs(
        payload: ClientLogBatchRequest,
        request: Request,
        store: CollaborationStore = Depends(get_store),
    ) -> dict[str, Any]:
        user_id = _optional_session_user_id(request, store)
        entries = [_client_log_entry(item.model_dump()) for item in payload.logs]
        accepted = store.record_client_logs(entries, session_user_id=user_id)
        log_event(
            "info",
            "client_logs.received",
            request_id=request_id(request),
            user_id=user_id,
            path=str(request.url.path),
            status=200,
            accepted=accepted,
        )
        return {"ok": True, "accepted": accepted}


def _bridge(request: Request) -> RuntimeBridge:
    return request.app.state.bridge_factory()


def _desktop_bridge(request: Request) -> DesktopControlBridgeProtocol:
    return request.app.state.desktop_bridge_factory()


def now_seconds() -> float:
    return time.time()


def _require_desktop_session(user: CurrentUser) -> None:
    if user.client_kind != "desktop":
        raise APIError(403, "DESKTOP_SESSION_REQUIRED", "desktop login is required")


def _require_loopback_bridge_url(value: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise APIError(400, "BAD_BRIDGE_URL", "desktop bridge must use a loopback http URL")
    return value


def _id_suffix(value: str) -> str:
    return value[-8:] if value else ""


def _desktop_interaction_summary(row: dict[str, Any]) -> dict[str, Any]:
    response = _json_field(row, "response_json")
    return {
        "id": str(row["id"]),
        "type": str(row["interaction_type"]),
        "status": str(row["status"]),
        "desktopSessionId": _id_suffix(str(row["desktop_session_id"])) if row.get("desktop_session_id") else None,
        "response": scrub_payload(response) or None,
        "error": str(row["error"]) if row.get("error") else None,
        "createdAt": iso_time(row["created_at"]),
        "updatedAt": iso_time(row["updated_at"]),
    }


def _try_send_mobile_planning_to_desktop(
    request: Request,
    store: CollaborationStore,
    user: CurrentUser,
    planning_request: dict[str, Any],
) -> dict[str, Any]:
    bridge = store.get_active_desktop_bridge(user.id)
    if not bridge:
        return {"status": "desktop_unavailable", "accepted": False}
    try:
        result = _desktop_bridge(request).request(
            bridge,
            "desktop.mobilePlanning.submit",
            {
                "planningRequest": planning_request,
                "projectId": planning_request.get("projectId"),
                "blueprintId": planning_request.get("blueprintId"),
                "goal": planning_request.get("goal"),
            },
        )
    except APIError as exc:
        return {"status": "failed", "accepted": False, "error": exc.message}
    accepted = result.get("accepted", result.get("ok", True)) is not False
    return {"status": "accepted" if accepted else "rejected", "accepted": accepted}


def _mobile_desktop_sessions_payload(store: CollaborationStore, user_id: str) -> dict[str, Any]:
    snapshot = store.get_desktop_session_snapshot(user_id)
    bridge = store.get_active_desktop_bridge(user_id)
    desktop_session = store.get_active_desktop_session(user_id)
    logged_in = bool(bridge or desktop_session)
    if not snapshot:
        return {
            "desktop": {
                "online": bool(bridge),
                "loggedIn": logged_in,
                "stale": True,
                "updatedAt": None,
            },
            "activeSessionId": None,
            "sessions": [],
            "currentMessages": [],
            "composer": {"modes": [], "activeModeId": None},
        }
    payload = _json_field(snapshot, "payload_json")
    updated_at = float(snapshot.get("updated_at") or 0)
    return {
        "desktop": {
            "online": bool(bridge),
            "loggedIn": logged_in,
            "stale": now_seconds() - updated_at > 15,
            "updatedAt": iso_time(updated_at),
        },
        "activeSessionId": str(snapshot["active_session_id"]) if snapshot.get("active_session_id") else payload.get("activeSessionId"),
        "sessions": list(payload.get("sessions") or []),
        "currentMessages": list(payload.get("currentMessages") or []),
        "composer": payload.get("composer") or {"modes": [], "activeModeId": None},
    }


def _require_capability(role: str, capability: str) -> None:
    if capability not in role_capabilities(role):
        raise APIError(403, "CAPABILITY_DISABLED", f"capability is not available: {capability}")


def _approval_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "runId": str(row["run_id"]),
        "action": str(row["action"]),
        "changesetId": str(row["changeset_id"]) if row.get("changeset_id") else None,
        "status": str(row["status"]),
        "createdAt": row.get("created_at"),
    }


def _planning_request_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "projectId": str(row["project_id"]),
        "blueprintId": str(row["blueprint_id"]),
        "goal": str(row.get("goal") or ""),
        "status": str(row.get("status") or "pending_desktop"),
        "desktopSessionId": str(row["desktop_session_id"]) if row.get("desktop_session_id") else None,
        "planningSessionId": str(row["planning_session_id"]) if row.get("planning_session_id") else None,
        "pendingQuestion": scrub_payload(_json_field(row, "pending_question_json")) or None,
        "pendingPlan": scrub_payload(_json_field(row, "pending_plan_json")) or None,
        "mobileAnswer": scrub_payload(_json_field(row, "mobile_answer_json")) or None,
        "activeRunId": str(row["active_run_id"]) if row.get("active_run_id") else None,
        "error": str(row["error"]) if row.get("error") else None,
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }


def _json_field(row: dict[str, Any], key: str) -> dict[str, Any]:
    value = row.get(key)
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value))
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _planning_status_from_snapshot(
    pending_question: dict[str, Any] | None,
    pending_plan: dict[str, Any] | None,
    active_run: dict[str, Any] | None,
    error: str | None,
) -> str:
    if error:
        return "failed"
    if active_run:
        return "started"
    if pending_plan:
        return "plan_ready"
    if pending_question:
        return "question_pending"
    return "planning"


def _run_id_from_active_run(active_run: dict[str, Any] | None) -> str | None:
    if not isinstance(active_run, dict):
        return None
    value = active_run.get("runId") or active_run.get("id")
    return str(value) if value else None


def _latest_project_run(request: Request, project: dict[str, Any], store: CollaborationStore) -> Any:
    try:
        _sync_project_runs(request, str(project["id"]), store)
    except APIError:
        return None
    rows = store.list_runs_for_project(str(project["id"]))
    return run_summary(rows[0]) if rows else None


def _desktop_snapshot_project(
    store: CollaborationStore,
    user: CurrentUser,
    payload: DesktopBlueprintSnapshotRequest,
) -> dict[str, Any]:
    if payload.projectId:
        project = store.get_project(payload.projectId)
        if not project:
            raise APIError(404, "PROJECT_NOT_FOUND", "project not found")
        return project

    requested_dir = _normalize_snapshot_path(payload.projectDir)
    candidates = store.list_projects_for_user(user.id)
    if user.is_admin and not candidates:
        candidates = store.list_projects()

    if requested_dir:
        for project in candidates:
            binding = store.get_active_binding(str(project["id"]))
            if binding and _normalize_snapshot_path(str(binding.get("project_dir") or "")) == requested_dir:
                return project

    for project in candidates:
        role = "owner" if user.is_admin else str(project.get("member_role") or "")
        if "run:create" in role_capabilities(role):
            return project

    raise APIError(400, "PROJECT_UNAVAILABLE", "no writable project is available for desktop blueprint sync")


def _normalize_snapshot_path(value: str | None) -> str:
    return str(value or "").strip().replace("\\", "/").rstrip("/").lower()


def _sync_project_runs(request: Request, project_id: str, store: CollaborationStore) -> list[dict[str, Any]]:
    binding = store.get_active_binding(project_id)
    if not binding:
        return store.list_runs_for_project(project_id)
    bridge = _bridge(request)
    runtime_runs = bridge.list_runs(binding)
    for item in runtime_runs:
        runtime_run_id = str(item.get("runId") or item.get("id") or "").strip()
        if not runtime_run_id:
            continue
        store.upsert_run_from_runtime(project_id, str(binding["blueprint_id"]), runtime_run_id, item)
    return store.list_runs_for_project(project_id)


def _sync_run_events(request: Request, run: dict[str, Any], store: CollaborationStore) -> None:
    binding = _binding_for_run(store, run)
    raw_events = _bridge(request).recent_events(binding, str(run["runtime_run_id"]), limit=100)
    mirror_runtime_events(store, run, raw_events)


def _run_for_user(store: CollaborationStore, user: CurrentUser, run_id: str) -> dict[str, Any]:
    run = store.get_run(run_id)
    if not run:
        raise APIError(404, "RUN_NOT_FOUND", "run not found")
    _require_project_access(store, user, str(run["project_id"]))
    return run


def _require_project_access(store: CollaborationStore, user: CurrentUser, project_id: str) -> str:
    if user.is_admin:
        project = store.get_project(project_id)
        if project:
            return "owner"
    role = store.get_project_role(project_id, user.id)
    if not role:
        raise APIError(403, "PROJECT_FORBIDDEN", "project access denied")
    return role


def _binding_for_run(store: CollaborationStore, run: dict[str, Any]) -> dict[str, Any]:
    binding = store.get_active_binding(str(run["project_id"]))
    if not binding:
        raise APIError(503, "RUNTIME_UNAVAILABLE", "runtime binding is not configured")
    return binding


def _binding_for_project(store: CollaborationStore, project_id: str) -> dict[str, Any]:
    binding = store.get_active_binding(project_id)
    if not binding:
        raise APIError(503, "RUNTIME_UNAVAILABLE", "runtime binding is not configured")
    return binding


def _planning_request_for_user(store: CollaborationStore, user: CurrentUser, planning_request_id: str) -> dict[str, Any]:
    row = store.get_planning_request(planning_request_id)
    if not row:
        raise APIError(404, "PLANNING_REQUEST_NOT_FOUND", "planning request not found")
    _require_project_access(store, user, str(row["project_id"]))
    return row


def _runtime_run_payload(runtime_run_id: str, status_payload: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    inner = status_payload.get("status") if isinstance(status_payload.get("status"), dict) else status_payload
    run = inner.get("run") if isinstance(inner, dict) and isinstance(inner.get("run"), dict) else {}
    status = normalize_status(run.get("status") or run.get("final_status") or existing.get("status"))
    return {
        "runId": runtime_run_id,
        "title": existing.get("title") or runtime_run_id,
        "status": status,
        "createdAt": existing.get("created_at"),
        "updatedAt": inner.get("updated_at") if isinstance(inner, dict) else existing.get("updated_at"),
        "endedAt": run.get("ended_at") or existing.get("ended_at"),
    }


def _client_sync_payload(store: CollaborationStore, user_id: str) -> dict[str, Any]:
    client_kinds = store.active_client_kinds(user_id)
    clients = {
        "mobile": "mobile" in client_kinds,
        "desktop": "desktop" in client_kinds,
    }
    return {"clients": clients, "syncReady": clients["mobile"] and clients["desktop"]}


def _mobile_tick_status_projection(projection: Any) -> dict[str, Any]:
    data = projection.model_dump(exclude_none=True) if hasattr(projection, "model_dump") else dict(projection)
    return {
        "run": data.get("run"),
        "blueprint": data.get("blueprint"),
        "agents": [_mobile_tick_agent_projection(agent) for agent in list(data.get("agents") or [])],
        "pending": data.get("pending") or {},
    }


def _desktop_snapshot_tick_status(
    project: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    run: Any = None,
) -> dict[str, Any]:
    payload = _json_field(snapshot, "payload_json")
    raw_nodes = [item for item in list(payload.get("nodes") or []) if isinstance(item, dict)]
    nodes = [_desktop_snapshot_node_projection(item) for item in raw_nodes]
    node_ids = {str(item["id"]) for item in nodes if item.get("id")}
    edges = [
        _desktop_snapshot_edge_projection(item)
        for item in list(payload.get("edges") or [])
        if isinstance(item, dict) and str(item.get("source") or "") in node_ids and str(item.get("target") or "") in node_ids
    ]
    current_node_ids = [str(item["id"]) for item in nodes if item.get("state") == "running"]
    run_payload = run.model_dump() if hasattr(run, "model_dump") else (dict(run) if isinstance(run, dict) else None)
    if not run_payload:
        run_payload = {
            "id": "",
            "projectId": str(project["id"]),
            "blueprintId": str(payload.get("blueprintId") or snapshot.get("blueprint_id") or "default"),
            "title": str(payload.get("title") or snapshot.get("title") or project.get("name") or "Blueprint"),
            "status": "unknown",
            "createdAt": iso_time(snapshot.get("created_at")),
            "updatedAt": iso_time(snapshot.get("updated_at")),
            "endedAt": None,
        }
    run_payload["currentNodeIds"] = current_node_ids
    return {
        "run": run_payload,
        "blueprint": {"nodes": nodes, "edges": edges},
        "agents": [
            _desktop_snapshot_agent_projection(item)
            for item in raw_nodes
            if _snapshot_node_kind(item.get("kind")) in {"agent", "worker_agent"}
        ],
        "pending": {
            "queuedMessages": 0,
            "waitingOutgoingBatches": 0,
            "waitingJoins": 0,
            "runningJobs": sum(1 for item in nodes if item.get("state") == "running"),
        },
    }


def _desktop_snapshot_node_projection(item: dict[str, Any]) -> dict[str, Any]:
    node = {
        "id": str(item.get("id") or ""),
        "label": str(item.get("label") or item.get("agentId") or item.get("id") or ""),
        "kind": _snapshot_node_kind(item.get("kind")),
        "role": str(item.get("role") or item.get("cliKind") or "") or None,
        "state": _snapshot_node_state(item.get("state")),
        "upstreamNodeIds": [str(value) for value in list(item.get("upstreamNodeIds") or [])],
        "downstreamNodeIds": [str(value) for value in list(item.get("downstreamNodeIds") or [])],
        "inputPorts": _snapshot_port_names(item.get("inputPorts")),
        "outputPorts": _snapshot_port_names(item.get("outputPorts")),
    }
    if not node["role"]:
        node["role"] = _snapshot_node_role(str(node["kind"]))
    summary = _snapshot_optional_string(item.get("summary"))
    if summary:
        node["summary"] = summary
    x = _snapshot_optional_number(item.get("x"))
    y = _snapshot_optional_number(item.get("y"))
    if x is not None and y is not None:
        node["x"] = x
        node["y"] = y
    every_n_ticks = _snapshot_optional_int(item.get("everyNTicks"))
    if every_n_ticks is not None and every_n_ticks >= 1:
        node["everyNTicks"] = every_n_ticks
    return node


def _snapshot_optional_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _desktop_snapshot_edge_projection(item: dict[str, Any]) -> dict[str, Any]:
    edge = {
        "source": str(item.get("source") or ""),
        "target": str(item.get("target") or ""),
        "kind": _snapshot_edge_kind(item.get("kind")),
    }
    output_port = _snapshot_optional_string(item.get("outputPort"))
    input_port = _snapshot_optional_string(item.get("inputPort"))
    if output_port:
        edge["outputPort"] = output_port
    if input_port:
        edge["inputPort"] = input_port
    return edge


def _desktop_snapshot_agent_projection(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "nodeId": str(item.get("id") or ""),
        "agentId": str(item.get("agentId") or item.get("label") or item.get("id") or ""),
        "cliKind": item.get("cliKind") if item.get("cliKind") else item.get("role"),
        "state": str(item.get("state") or "idle"),
        "taskStatus": item.get("taskStatus"),
        "queueSize": _snapshot_optional_int(item.get("queueSize")) or 0,
        "messagesSent": _snapshot_optional_int(item.get("messagesSent")) or 0,
        "busyCount": _snapshot_optional_int(item.get("busyCount")) or 0,
        "updatedAt": item.get("updatedAt"),
    }


def _snapshot_node_state(value: Any) -> str:
    state = str(value or "idle").lower()
    if state in {"idle", "queued", "running", "completed", "failed", "unknown"}:
        return state
    return "idle"


def _snapshot_node_kind(value: Any) -> str:
    kind = str(value or "worker_agent").lower()
    if kind in {"agent", "worker_agent", "script", "branch", "tick"}:
        return kind
    return "worker_agent"


def _snapshot_node_role(kind: str) -> str:
    if kind == "agent":
        return "Agent"
    if kind == "worker_agent":
        return "Worker Agent"
    if kind == "script":
        return "Script Function"
    if kind == "branch":
        return "Branch"
    if kind == "tick":
        return "Tick"
    return "Node"


def _snapshot_edge_kind(value: Any) -> str:
    kind = str(value or "unknown").lower()
    if kind in {"exec", "data", "unknown"}:
        return kind
    return "unknown"


def _snapshot_optional_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _snapshot_port_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        name = str(item or "").strip()
        if name:
            names.append(name[:128])
    return names


def _snapshot_optional_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _merge_desktop_snapshot_runtime_status(snapshot_status: dict[str, Any], runtime_status: dict[str, Any]) -> dict[str, Any]:
    runtime_blueprint = runtime_status.get("blueprint") if isinstance(runtime_status.get("blueprint"), dict) else {}
    runtime_nodes = {
        str(item.get("id")): item
        for item in list(runtime_blueprint.get("nodes") or [])
        if isinstance(item, dict) and item.get("id")
    }
    runtime_agents = {
        str(item.get("nodeId")): item
        for item in list(runtime_status.get("agents") or [])
        if isinstance(item, dict) and item.get("nodeId")
    }

    seen_nodes: set[str] = set()
    merged_nodes: list[dict[str, Any]] = []
    snapshot_blueprint = snapshot_status.get("blueprint") if isinstance(snapshot_status.get("blueprint"), dict) else {}
    for item in list(snapshot_blueprint.get("nodes") or []):
        if not isinstance(item, dict):
            continue
        node = dict(item)
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        seen_nodes.add(node_id)
        runtime_node = runtime_nodes.get(node_id)
        runtime_agent = runtime_agents.get(node_id)
        state = None
        if isinstance(runtime_node, dict):
            state = runtime_node.get("state")
        if state is None and isinstance(runtime_agent, dict):
            state = runtime_agent.get("state")
        if state is not None:
            node["state"] = _snapshot_node_state(state)
        merged_nodes.append(node)

    for node_id, item in runtime_nodes.items():
        if node_id in seen_nodes:
            continue
        node = dict(item)
        node.setdefault("kind", "worker_agent")
        merged_nodes.append(node)

    snapshot_agents = [
        dict(item)
        for item in list(snapshot_status.get("agents") or [])
        if isinstance(item, dict) and item.get("nodeId")
    ]
    merged_agents_by_id = {str(item["nodeId"]): item for item in snapshot_agents}
    for node_id, item in runtime_agents.items():
        if node_id in merged_agents_by_id:
            merged_agents_by_id[node_id].update(item)
        else:
            merged_agents_by_id[node_id] = dict(item)

    return {
        "run": runtime_status.get("run") or snapshot_status.get("run"),
        "blueprint": {
            "nodes": merged_nodes,
            "edges": list(snapshot_blueprint.get("edges") or []),
        },
        "agents": list(merged_agents_by_id.values()),
        "pending": runtime_status.get("pending") or snapshot_status.get("pending") or {},
    }


def _mobile_tick_agent_projection(agent: Any) -> dict[str, Any]:
    item = agent.model_dump() if hasattr(agent, "model_dump") else dict(agent)
    return {
        "nodeId": item.get("nodeId"),
        "agentId": item.get("agentId"),
        "cliKind": item.get("cliKind"),
        "state": item.get("state"),
        "taskStatus": item.get("taskStatus"),
        "queueSize": item.get("queueSize", 0),
        "messagesSent": item.get("messagesSent", 0),
        "busyCount": item.get("busyCount", 0),
        "updatedAt": item.get("updatedAt"),
    }


def _request_user_id(request: Request) -> str | None:
    value = getattr(request.state, "user_id", None)
    return str(value) if value else None


def _optional_session_user_id(request: Request, store: CollaborationStore) -> str | None:
    session_id = request.cookies.get(SESSION_COOKIE, "")
    if not session_id:
        return None
    session = store.get_session(session_id)
    if not session:
        return None
    user_id = str(session["user_id"])
    request.state.user_id = user_id
    return user_id


def _client_log_entry(item: dict[str, Any]) -> dict[str, Any]:
    context = client_log_context(item.get("context") or {})
    context_json = json.dumps(context, ensure_ascii=False, default=str)
    if len(context_json.encode("utf-8")) > 4096:
        context = {"truncated": True, "originalBytes": len(context_json.encode("utf-8"))}
    return {
        "level": str(item.get("level") or "info").lower(),
        "event": str(item.get("event") or "mobile.unknown")[:128],
        "message": clamp_message(item.get("message")),
        "context": context,
        "request_id": str(item.get("requestId") or item.get("request_id") or "")[:128],
        "client_created_at": str(item.get("createdAt") or item.get("created_at") or "")[:64],
    }
