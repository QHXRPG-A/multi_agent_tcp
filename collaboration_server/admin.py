from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from .auth import APIError, CurrentUser, admin_user, get_store, require_csrf
from .projection import binding_summary, project_admin_summary, user_summary
from .schemas import (
    ClientLogSummary,
    ClientPresenceSummary,
    MemberRequest,
    MemberUpdateRequest,
    PasswordResetRequest,
    ProjectCreateRequest,
    ProjectUpdateRequest,
    RuntimeBindingRequest,
    RuntimeBindingUpdateRequest,
    UserCreateRequest,
    UserMonitorResponse,
    UserMonitorSummary,
    UserMonitorTotals,
    UserSessionMonitorSummary,
    UserUpdateRequest,
)
from .store import CollaborationStore
from .store import iso_time


router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def list_users(_: CurrentUser = Depends(admin_user), store: CollaborationStore = Depends(get_store)) -> dict[str, object]:
    return {"ok": True, "users": [user_summary(row) for row in store.list_users()]}


@router.get("/logs/client")
def list_client_logs(
    _: CurrentUser = Depends(admin_user),
    store: CollaborationStore = Depends(get_store),
    level: Optional[str] = Query(default=None, pattern="^(debug|info|warning|error)$"),
    event: Optional[str] = Query(default=None, min_length=1, max_length=128),
    user_id: Optional[str] = Query(default=None, alias="userId", min_length=1, max_length=128),
    since: Optional[float] = None,
    until: Optional[float] = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    rows = store.list_client_logs(level=level, event=event, user_id=user_id, since=since, until=until, limit=limit)
    return {"ok": True, "logs": [_client_log_summary(row) for row in rows]}


@router.get("/monitor/users")
def monitor_users(_: CurrentUser = Depends(admin_user), store: CollaborationStore = Depends(get_store)) -> UserMonitorResponse:
    data = store.user_monitor()
    totals = data["totals"]
    return UserMonitorResponse(
        totals=UserMonitorTotals(
            totalUsers=int(totals["total_users"]),
            activeUsers=int(totals["active_users"]),
            activeSessions=int(totals["active_sessions"]),
            mobileOnline=int(totals["mobile_online"]),
            desktopOnline=int(totals["desktop_online"]),
        ),
        users=[_user_monitor_summary(row) for row in list(data["users"])],
    )


@router.post("/users", dependencies=[Depends(require_csrf)])
def create_user(
    payload: UserCreateRequest,
    user: CurrentUser = Depends(admin_user),
    store: CollaborationStore = Depends(get_store),
) -> dict[str, object]:
    try:
        row = store.create_user(payload.username, payload.password, role=payload.role, active=payload.active)
    except Exception as exc:
        raise APIError(400, "USER_CREATE_FAILED", str(exc)) from exc
    store.audit(action="admin.user.create", status="ok", user_id=user.id, summary={"targetUserId": row["id"]})
    return {"ok": True, "user": user_summary(row)}


@router.patch("/users/{user_id}", dependencies=[Depends(require_csrf)])
def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    user: CurrentUser = Depends(admin_user),
    store: CollaborationStore = Depends(get_store),
) -> dict[str, object]:
    try:
        row = store.update_user(user_id, username=payload.username, role=payload.role, active=payload.active)
    except KeyError as exc:
        raise APIError(404, "USER_NOT_FOUND", "user not found") from exc
    except Exception as exc:
        raise APIError(400, "USER_UPDATE_FAILED", str(exc)) from exc
    store.audit(action="admin.user.update", status="ok", user_id=user.id, summary={"targetUserId": user_id})
    return {"ok": True, "user": user_summary(row)}


@router.post("/users/{user_id}/disable", dependencies=[Depends(require_csrf)])
def disable_user(
    user_id: str,
    user: CurrentUser = Depends(admin_user),
    store: CollaborationStore = Depends(get_store),
) -> dict[str, object]:
    row = store.update_user(user_id, active=False)
    store.audit(action="admin.user.disable", status="ok", user_id=user.id, summary={"targetUserId": user_id})
    return {"ok": True, "user": user_summary(row)}


@router.post("/users/{user_id}/reset-password", dependencies=[Depends(require_csrf)])
def reset_password(
    user_id: str,
    payload: PasswordResetRequest,
    user: CurrentUser = Depends(admin_user),
    store: CollaborationStore = Depends(get_store),
) -> dict[str, object]:
    row = store.reset_password(user_id, payload.password)
    store.audit(action="admin.user.reset_password", status="ok", user_id=user.id, summary={"targetUserId": user_id})
    return {"ok": True, "user": user_summary(row)}


@router.get("/projects")
def list_projects(_: CurrentUser = Depends(admin_user), store: CollaborationStore = Depends(get_store)) -> dict[str, object]:
    return {"ok": True, "projects": [project_admin_summary(row) for row in store.list_projects()]}


@router.post("/projects", dependencies=[Depends(require_csrf)])
def create_project(
    payload: ProjectCreateRequest,
    user: CurrentUser = Depends(admin_user),
    store: CollaborationStore = Depends(get_store),
) -> dict[str, object]:
    row = store.create_project(payload.name, project_id=payload.id)
    store.audit(action="admin.project.create", status="ok", user_id=user.id, project_id=row["id"])
    return {"ok": True, "project": project_admin_summary(row)}


@router.patch("/projects/{project_id}", dependencies=[Depends(require_csrf)])
def update_project(
    project_id: str,
    payload: ProjectUpdateRequest,
    user: CurrentUser = Depends(admin_user),
    store: CollaborationStore = Depends(get_store),
) -> dict[str, object]:
    row = store.update_project(project_id, name=payload.name, archived=payload.archived)
    store.audit(action="admin.project.update", status="ok", user_id=user.id, project_id=project_id)
    return {"ok": True, "project": project_admin_summary(row)}


@router.post("/projects/{project_id}/archive", dependencies=[Depends(require_csrf)])
def archive_project(
    project_id: str,
    user: CurrentUser = Depends(admin_user),
    store: CollaborationStore = Depends(get_store),
) -> dict[str, object]:
    row = store.update_project(project_id, archived=True)
    store.audit(action="admin.project.archive", status="ok", user_id=user.id, project_id=project_id)
    return {"ok": True, "project": project_admin_summary(row)}


@router.get("/projects/{project_id}/members")
def list_members(project_id: str, _: CurrentUser = Depends(admin_user), store: CollaborationStore = Depends(get_store)) -> dict[str, object]:
    return {"ok": True, "members": store.list_project_members(project_id)}


@router.post("/projects/{project_id}/members", dependencies=[Depends(require_csrf)])
def add_member(
    project_id: str,
    payload: MemberRequest,
    user: CurrentUser = Depends(admin_user),
    store: CollaborationStore = Depends(get_store),
) -> dict[str, object]:
    row = store.upsert_project_member(project_id, payload.userId, payload.role)
    store.audit(action="admin.member.upsert", status="ok", user_id=user.id, project_id=project_id, summary={"targetUserId": payload.userId})
    return {"ok": True, "member": row}


@router.patch("/projects/{project_id}/members/{user_id}", dependencies=[Depends(require_csrf)])
def update_member(
    project_id: str,
    user_id: str,
    payload: MemberUpdateRequest,
    user: CurrentUser = Depends(admin_user),
    store: CollaborationStore = Depends(get_store),
) -> dict[str, object]:
    row = store.upsert_project_member(project_id, user_id, payload.role)
    store.audit(action="admin.member.update", status="ok", user_id=user.id, project_id=project_id, summary={"targetUserId": user_id})
    return {"ok": True, "member": row}


@router.delete("/projects/{project_id}/members/{user_id}", dependencies=[Depends(require_csrf)])
def remove_member(
    project_id: str,
    user_id: str,
    user: CurrentUser = Depends(admin_user),
    store: CollaborationStore = Depends(get_store),
) -> dict[str, object]:
    store.remove_project_member(project_id, user_id)
    store.audit(action="admin.member.remove", status="ok", user_id=user.id, project_id=project_id, summary={"targetUserId": user_id})
    return {"ok": True}


@router.get("/projects/{project_id}/runtime-bindings")
def list_runtime_bindings(
    project_id: str,
    _: CurrentUser = Depends(admin_user),
    store: CollaborationStore = Depends(get_store),
) -> dict[str, object]:
    return {"ok": True, "runtimeBindings": [binding_summary(row) for row in store.list_runtime_bindings(project_id)]}


@router.post("/projects/{project_id}/runtime-bindings", dependencies=[Depends(require_csrf)])
def create_runtime_binding(
    project_id: str,
    payload: RuntimeBindingRequest,
    user: CurrentUser = Depends(admin_user),
    store: CollaborationStore = Depends(get_store),
) -> dict[str, object]:
    row = store.create_or_update_runtime_binding(
        project_id=project_id,
        blueprint_id=payload.blueprintId,
        project_dir=payload.projectDir,
        bridge_url=payload.bridgeUrl,
        bridge_token=payload.bridgeToken,
        active=payload.active,
    )
    store.audit(action="admin.runtime_binding.create", status="ok", user_id=user.id, project_id=project_id, summary={"bindingId": row["id"]})
    return {"ok": True, "runtimeBinding": binding_summary(row)}


@router.patch("/runtime-bindings/{binding_id}", dependencies=[Depends(require_csrf)])
def update_runtime_binding(
    binding_id: str,
    payload: RuntimeBindingUpdateRequest,
    user: CurrentUser = Depends(admin_user),
    store: CollaborationStore = Depends(get_store),
) -> dict[str, object]:
    existing = store.get_binding(binding_id)
    if not existing:
        raise APIError(404, "RUNTIME_BINDING_NOT_FOUND", "runtime binding not found")
    row = store.update_runtime_binding(
        binding_id,
        blueprint_id=payload.blueprintId,
        project_dir=payload.projectDir,
        bridge_url=payload.bridgeUrl,
        bridge_token=payload.bridgeToken,
        active=payload.active,
    )
    store.audit(action="admin.runtime_binding.update", status="ok", user_id=user.id, project_id=row["project_id"], summary={"bindingId": binding_id})
    return {"ok": True, "runtimeBinding": binding_summary(row)}


@router.post("/runtime-bindings/{binding_id}/disable", dependencies=[Depends(require_csrf)])
def disable_runtime_binding(
    binding_id: str,
    user: CurrentUser = Depends(admin_user),
    store: CollaborationStore = Depends(get_store),
) -> dict[str, object]:
    row = store.update_runtime_binding(binding_id, active=False)
    store.audit(action="admin.runtime_binding.disable", status="ok", user_id=user.id, project_id=row["project_id"], summary={"bindingId": binding_id})
    return {"ok": True, "runtimeBinding": binding_summary(row)}


def _client_log_summary(row: dict[str, Any]) -> ClientLogSummary:
    try:
        context = json.loads(str(row.get("context_json") or "{}"))
    except ValueError:
        context = {}
    return ClientLogSummary(
        id=int(row["id"]),
        createdAt=iso_time(row.get("created_at")),
        sessionUserId=str(row["session_user_id"]) if row.get("session_user_id") else None,
        level=str(row.get("level") or "info"),  # type: ignore[arg-type]
        event=str(row.get("event") or "mobile.unknown"),
        message=str(row.get("message") or ""),
        context=context if isinstance(context, dict) else {},
        requestId=str(row["request_id"]) if row.get("request_id") else None,
        clientCreatedAt=str(row["client_created_at"]) if row.get("client_created_at") else None,
    )


def _user_monitor_summary(row: dict[str, Any]) -> UserMonitorSummary:
    clients = set(row.get("clients") or set())
    return UserMonitorSummary(
        user=user_summary(row["user"]),
        clients=ClientPresenceSummary(
            mobile="mobile" in clients,
            desktop="desktop" in clients,
        ),
        activeSessionCount=int(row.get("active_session_count") or 0),
        lastLoginAt=iso_time(row.get("last_login_at")) if row.get("last_login_at") is not None else None,
        lastClientLogAt=iso_time(row.get("last_client_log_at")) if row.get("last_client_log_at") is not None else None,
        sessions=[_user_session_monitor_summary(item) for item in list(row.get("sessions") or [])],
    )


def _user_session_monitor_summary(row: dict[str, Any]) -> UserSessionMonitorSummary:
    session_id = str(row.get("id") or "")
    client_kind = row.get("client_kind")
    if client_kind not in {"mobile", "desktop"}:
        client_kind = None
    return UserSessionMonitorSummary(
        clientKind=client_kind,
        createdAt=iso_time(row.get("created_at")),
        expiresAt=iso_time(row.get("expires_at")),
        userAgent=str(row.get("user_agent") or "")[:512] or None,
        idSuffix=session_id[-8:] if session_id else "",
    )
