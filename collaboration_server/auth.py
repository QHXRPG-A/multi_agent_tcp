from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from fastapi import Depends, Request

from .observability import set_log_context
from .security import verify_password
from .store import CollaborationStore


SESSION_COOKIE = "gulicode_collab_session"
CSRF_HEADER = "x-csrf-token"
LOGIN_RATE_LIMIT = 8


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str, *, details: Optional[dict[str, Any]] = None) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    username: str
    role: str
    csrf_token: str
    session_id: str
    client_kind: Optional[str] = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def get_store(request: Request) -> CollaborationStore:
    return request.app.state.store


def request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", ""))


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else ""


def authenticate(store: CollaborationStore, username: str, password: str, *, ip: str = "") -> dict[str, Any]:
    if store.failed_login_count(username, ip=ip) >= LOGIN_RATE_LIMIT:
        store.record_login_attempt(username, ip=ip, success=False)
        raise APIError(429, "LOGIN_RATE_LIMITED", "too many failed login attempts")
    user = store.get_user_by_username(username)
    if not user or not bool(user.get("active")) or not verify_password(password, str(user.get("password_hash", ""))):
        store.record_login_attempt(username, ip=ip, success=False)
        raise APIError(401, "INVALID_CREDENTIALS", "invalid username or password")
    store.record_login_attempt(username, ip=ip, success=True)
    return user


def current_user(request: Request, store: CollaborationStore = Depends(get_store)) -> CurrentUser:
    session_id = request.cookies.get(SESSION_COOKIE, "")
    if not session_id:
        raise APIError(401, "UNAUTHORIZED", "login required")
    session = store.get_session(session_id)
    if not session:
        raise APIError(401, "UNAUTHORIZED", "login required")
    request.state.user_id = str(session["user_id"])
    set_log_context(user_id=str(session["user_id"]))
    return CurrentUser(
        id=str(session["user_id"]),
        username=str(session["username"]),
        role=str(session["role"]),
        csrf_token=str(session["csrf_token"]),
        session_id=session_id,
        client_kind=str(session["client_kind"]) if session.get("client_kind") else None,
    )


def admin_user(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not user.is_admin:
        raise APIError(403, "ADMIN_REQUIRED", "admin privileges required")
    return user


def require_csrf(request: Request, user: CurrentUser = Depends(current_user)) -> None:
    token = request.headers.get(CSRF_HEADER, "")
    if not token or token != user.csrf_token:
        raise APIError(403, "CSRF_REQUIRED", "valid CSRF token required")


def role_capabilities(role: str) -> list[str]:
    base = ["project:read", "run:read"]
    if role in {"owner", "operator"}:
        return [*base, "run:create", "run:message", "run:end", "run:approve"]
    return base
