from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from .security import hash_password, new_token, stable_digest


SESSION_TTL_SECONDS = 30 * 24 * 60 * 60


def now_ts() -> float:
    return time.time()


def iso_time(value: Any) -> str:
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        timestamp = now_ts()
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class CollaborationStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if self.path.parent:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def migrate(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    csrf_token TEXT NOT NULL,
                    client_kind TEXT,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    revoked_at REAL,
                    ip_hash TEXT,
                    user_agent TEXT
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_members (
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('owner', 'operator', 'viewer')),
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (project_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS runtime_bindings (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    blueprint_id TEXT NOT NULL,
                    project_dir TEXT NOT NULL,
                    bridge_url TEXT NOT NULL,
                    bridge_token TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS desktop_blueprint_snapshots (
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    blueprint_id TEXT NOT NULL,
                    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                    title TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (project_id, blueprint_id)
                );
                CREATE TABLE IF NOT EXISTS desktop_bridges (
                    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    bridge_url TEXT NOT NULL,
                    bridge_token TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS desktop_session_snapshots (
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    desktop_session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    active_session_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS desktop_interactions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    mobile_session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
                    desktop_session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
                    interaction_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    response_json TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    runtime_run_id TEXT NOT NULL,
                    blueprint_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'unknown',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    ended_at REAL,
                    runtime_payload_json TEXT,
                    UNIQUE (project_id, runtime_run_id)
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                    direction TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approval_records (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                    action TEXT NOT NULL,
                    changeset_id TEXT,
                    status TEXT NOT NULL,
                    reason TEXT,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS planning_requests (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    blueprint_id TEXT NOT NULL,
                    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    desktop_session_id TEXT,
                    planning_session_id TEXT,
                    claimed_by_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                    pending_question_json TEXT,
                    pending_plan_json TEXT,
                    mobile_answer_json TEXT,
                    active_run_id TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_planning_requests_project_status ON planning_requests(project_id, status, updated_at);
                CREATE TABLE IF NOT EXISTS runtime_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    event_key TEXT NOT NULL,
                    type TEXT NOT NULL,
                    occurred_at REAL NOT NULL,
                    node_id TEXT,
                    agent_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE (run_id, event_key)
                );
                CREATE TABLE IF NOT EXISTS report_indexes (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifact_indexes (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS changeset_indexes (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT,
                    user_id TEXT,
                    action TEXT NOT NULL,
                    project_id TEXT,
                    run_id TEXT,
                    status TEXT NOT NULL,
                    code TEXT,
                    summary_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS client_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                    level TEXT NOT NULL CHECK (level IN ('debug', 'info', 'warning', 'error')),
                    event TEXT NOT NULL,
                    message TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    request_id TEXT,
                    client_created_at TEXT,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_client_logs_created_at ON client_logs(created_at);
                CREATE INDEX IF NOT EXISTS idx_client_logs_event ON client_logs(event);
                CREATE INDEX IF NOT EXISTS idx_client_logs_level ON client_logs(level);
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    ip_hash TEXT,
                    success INTEGER NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )
            columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
            if "client_kind" not in columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN client_kind TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_client ON sessions(user_id, client_kind)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_desktop_bridges_user ON desktop_bridges(user_id, updated_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_desktop_interactions_user ON desktop_interactions(user_id, updated_at)")

    def seed_from_file(self, path: str | Path | None) -> None:
        if not path:
            return
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("seed config must be a JSON object")
        self.seed(data)

    def seed(self, data: dict[str, Any]) -> None:
        admin = data.get("admin")
        users = list(data.get("users") or [])
        if isinstance(admin, dict):
            admin_user = dict(admin)
            admin_user.setdefault("role", "admin")
            users.insert(0, admin_user)
        for user in users:
            if not isinstance(user, dict):
                continue
            username = str(user.get("username", "")).strip()
            password_hash = str(user.get("passwordHash") or user.get("password_hash") or "")
            password = user.get("password")
            if not username or (not password_hash and not isinstance(password, str)):
                continue
            self.upsert_user(
                user_id=str(user.get("id") or username),
                username=username,
                password_hash=password_hash or hash_password(password),
                role=str(user.get("role") or "user"),
                active=bool(user.get("active", True)),
            )
        for project in list(data.get("projects") or []):
            if not isinstance(project, dict):
                continue
            project_id = str(project.get("id") or new_id("proj"))
            self.upsert_project(project_id, str(project.get("name") or project_id), archived=bool(project.get("archived", False)))
            for member in list(project.get("members") or []):
                if not isinstance(member, dict):
                    continue
                self.upsert_project_member(project_id, str(member.get("userId") or member.get("user_id") or ""), str(member.get("role") or "viewer"))
            binding = project.get("runtimeBinding") or project.get("runtime_binding")
            if isinstance(binding, dict):
                self.create_or_update_runtime_binding(
                    project_id=project_id,
                    binding_id=str(binding.get("id") or f"{project_id}_default"),
                    blueprint_id=str(binding.get("blueprintId") or binding.get("blueprint_id") or "default"),
                    project_dir=str(binding.get("projectDir") or binding.get("project_dir") or ""),
                    bridge_url=str(binding.get("bridgeUrl") or binding.get("bridge_url") or ""),
                    bridge_token=str(binding.get("bridgeToken") or binding.get("bridge_token") or ""),
                    active=bool(binding.get("active", True)),
                )

    def create_user(self, username: str, password: str, *, role: str = "user", active: bool = True) -> dict[str, Any]:
        return self.upsert_user(new_id("usr"), username, hash_password(password), role=role, active=active, create_only=True)

    def upsert_user(
        self,
        user_id: str,
        username: str,
        password_hash: str,
        *,
        role: str = "user",
        active: bool = True,
        create_only: bool = False,
    ) -> dict[str, Any]:
        if role not in {"admin", "user"}:
            raise ValueError("role must be admin or user")
        timestamp = now_ts()
        with self.connect() as conn:
            if create_only:
                conn.execute(
                    """
                    INSERT INTO users (id, username, password_hash, role, active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, username, password_hash, role, int(active), timestamp, timestamp),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO users (id, username, password_hash, role, active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        username=excluded.username,
                        password_hash=excluded.password_hash,
                        role=excluded.role,
                        active=excluded.active,
                        updated_at=excluded.updated_at
                    """,
                    (user_id, username, password_hash, role, int(active), timestamp, timestamp),
                )
            return self._user_row(conn, user_id)

    def update_user(self, user_id: str, *, username: Optional[str] = None, role: Optional[str] = None, active: Optional[bool] = None) -> dict[str, Any]:
        updates: list[str] = []
        values: list[Any] = []
        if username is not None:
            updates.append("username = ?")
            values.append(username)
        if role is not None:
            if role not in {"admin", "user"}:
                raise ValueError("role must be admin or user")
            updates.append("role = ?")
            values.append(role)
        if active is not None:
            updates.append("active = ?")
            values.append(int(active))
        updates.append("updated_at = ?")
        values.append(now_ts())
        values.append(user_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", values)
            return self._user_row(conn, user_id)

    def reset_password(self, user_id: str, password: str) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (hash_password(password), now_ts(), user_id),
            )
            return self._user_row(conn, user_id)

    def get_user_by_username(self, username: str) -> Optional[dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            return dict(row) if row else None

    def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def list_users(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM users ORDER BY created_at, username")]

    def create_session(self, user_id: str, *, ip: str = "", user_agent: str = "", client_kind: Optional[str] = None) -> dict[str, Any]:
        session_id = new_token()
        csrf_token = new_token()
        timestamp = now_ts()
        normalized_client_kind = client_kind if client_kind in {"mobile", "desktop"} else None
        with self.connect() as conn:
            if normalized_client_kind == "desktop":
                conn.execute(
                    """
                    UPDATE sessions
                    SET revoked_at = ?
                    WHERE user_id = ?
                      AND client_kind = 'desktop'
                      AND revoked_at IS NULL
                      AND expires_at >= ?
                    """,
                    (timestamp, user_id, timestamp),
                )
            conn.execute(
                """
                INSERT INTO sessions (id, user_id, csrf_token, client_kind, created_at, expires_at, ip_hash, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    csrf_token,
                    normalized_client_kind,
                    timestamp,
                    timestamp + SESSION_TTL_SECONDS,
                    stable_digest(ip) if ip else None,
                    user_agent[:512],
                ),
            )
        return {
            "id": session_id,
            "user_id": user_id,
            "csrf_token": csrf_token,
            "client_kind": normalized_client_kind,
            "expires_at": timestamp + SESSION_TTL_SECONDS,
        }

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT sessions.*, users.username, users.role, users.active
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.id = ?
                """,
                (session_id,),
            ).fetchone()
            if not row:
                return None
            session = dict(row)
            if session.get("revoked_at") is not None or float(session["expires_at"]) < now_ts() or not bool(session["active"]):
                return None
            return session

    def revoke_session(self, session_id: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE sessions SET revoked_at = ? WHERE id = ?", (now_ts(), session_id))

    def get_active_desktop_session(self, user_id: str) -> Optional[dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM sessions
                WHERE user_id = ?
                  AND client_kind = 'desktop'
                  AND revoked_at IS NULL
                  AND expires_at >= ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id, now_ts()),
            ).fetchone()
            return dict(row) if row else None

    def active_client_kinds(self, user_id: str) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT client_kind FROM sessions
                WHERE user_id = ?
                  AND revoked_at IS NULL
                  AND expires_at >= ?
                  AND client_kind IN ('mobile', 'desktop')
                """,
                (user_id, now_ts()),
            ).fetchall()
            return {str(row["client_kind"]) for row in rows if row["client_kind"]}

    def user_monitor(self, *, sessions_per_user: int = 5) -> dict[str, Any]:
        timestamp = now_ts()
        session_limit = max(1, min(int(sessions_per_user), 20))
        with self.connect() as conn:
            users = [dict(row) for row in conn.execute("SELECT * FROM users ORDER BY created_at, username")]
            active_rows = conn.execute(
                """
                SELECT user_id, client_kind
                FROM sessions
                WHERE revoked_at IS NULL
                  AND expires_at >= ?
                """,
                (timestamp,),
            ).fetchall()
            active_sessions = [dict(row) for row in active_rows]
            active_by_user: dict[str, int] = {}
            clients_by_user: dict[str, set[str]] = {}
            for session in active_sessions:
                user_id = str(session["user_id"])
                active_by_user[user_id] = active_by_user.get(user_id, 0) + 1
                client_kind = session.get("client_kind")
                if client_kind in {"mobile", "desktop"}:
                    clients_by_user.setdefault(user_id, set()).add(str(client_kind))

            user_rows = []
            for user in users:
                user_id = str(user["id"])
                last_login = conn.execute(
                    "SELECT MAX(created_at) AS value FROM sessions WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                last_client_log = conn.execute(
                    "SELECT MAX(created_at) AS value FROM client_logs WHERE session_user_id = ?",
                    (user_id,),
                ).fetchone()
                sessions = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT id, client_kind, created_at, expires_at, user_agent
                        FROM sessions
                        WHERE user_id = ?
                          AND revoked_at IS NULL
                          AND expires_at >= ?
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (user_id, timestamp, session_limit),
                    ).fetchall()
                ]
                user_rows.append(
                    {
                        "user": user,
                        "clients": clients_by_user.get(user_id, set()),
                        "active_session_count": active_by_user.get(user_id, 0),
                        "last_login_at": last_login["value"] if last_login else None,
                        "last_client_log_at": last_client_log["value"] if last_client_log else None,
                        "sessions": sessions,
                    }
                )

            return {
                "totals": {
                    "total_users": len(users),
                    "active_users": sum(1 for user in users if bool(user.get("active"))),
                    "active_sessions": len(active_sessions),
                    "mobile_online": sum(1 for clients in clients_by_user.values() if "mobile" in clients),
                    "desktop_online": sum(1 for clients in clients_by_user.values() if "desktop" in clients),
                },
                "users": user_rows,
            }

    def record_login_attempt(self, username: str, *, ip: str = "", success: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO login_attempts (username, ip_hash, success, created_at) VALUES (?, ?, ?, ?)",
                (username, stable_digest(ip) if ip else None, int(success), now_ts()),
            )

    def failed_login_count(self, username: str, *, ip: str = "", window_seconds: int = 300) -> int:
        since = now_ts() - window_seconds
        ip_hash = stable_digest(ip) if ip else None
        with self.connect() as conn:
            if ip_hash:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM login_attempts
                    WHERE username = ? AND ip_hash = ? AND success = 0 AND created_at >= ?
                    """,
                    (username, ip_hash, since),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM login_attempts
                    WHERE username = ? AND success = 0 AND created_at >= ?
                    """,
                    (username, since),
                ).fetchone()
            return int(row["count"] if row else 0)

    def upsert_project(self, project_id: str, name: str, *, archived: bool = False) -> dict[str, Any]:
        timestamp = now_ts()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, archived, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    archived=excluded.archived,
                    updated_at=excluded.updated_at
                """,
                (project_id, name, int(archived), timestamp, timestamp),
            )
            return self._project_row(conn, project_id)

    def create_project(self, name: str, *, project_id: Optional[str] = None) -> dict[str, Any]:
        return self.upsert_project(project_id or new_id("proj"), name)

    def update_project(self, project_id: str, *, name: Optional[str] = None, archived: Optional[bool] = None) -> dict[str, Any]:
        updates: list[str] = []
        values: list[Any] = []
        if name is not None:
            updates.append("name = ?")
            values.append(name)
        if archived is not None:
            updates.append("archived = ?")
            values.append(int(archived))
        updates.append("updated_at = ?")
        values.append(now_ts())
        values.append(project_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", values)
            return self._project_row(conn, project_id)

    def get_project(self, project_id: str) -> Optional[dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            return dict(row) if row else None

    def list_projects_for_user(self, user_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT projects.*, project_members.role AS member_role
                FROM projects
                JOIN project_members ON project_members.project_id = projects.id
                WHERE project_members.user_id = ? AND projects.archived = 0
                ORDER BY projects.created_at, projects.name
                """,
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM projects ORDER BY created_at, name")]

    def get_project_role(self, project_id: str, user_id: str) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            ).fetchone()
            return str(row["role"]) if row else None

    def upsert_project_member(self, project_id: str, user_id: str, role: str) -> dict[str, Any]:
        if role not in {"owner", "operator", "viewer"}:
            raise ValueError("role must be owner, operator, or viewer")
        timestamp = now_ts()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO project_members (project_id, user_id, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_id, user_id) DO UPDATE SET
                    role=excluded.role,
                    updated_at=excluded.updated_at
                """,
                (project_id, user_id, role, timestamp, timestamp),
            )
            return self._member_row(conn, project_id, user_id)

    def remove_project_member(self, project_id: str, user_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM project_members WHERE project_id = ? AND user_id = ?", (project_id, user_id))

    def list_project_members(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT project_members.project_id, project_members.user_id, project_members.role, users.username
                FROM project_members
                JOIN users ON users.id = project_members.user_id
                WHERE project_members.project_id = ?
                ORDER BY users.username
                """,
                (project_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_or_update_runtime_binding(
        self,
        *,
        project_id: str,
        binding_id: Optional[str] = None,
        blueprint_id: str,
        project_dir: str,
        bridge_url: str,
        bridge_token: str,
        active: bool = True,
    ) -> dict[str, Any]:
        binding_id = binding_id or new_id("rtb")
        timestamp = now_ts()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO runtime_bindings (id, project_id, blueprint_id, project_dir, bridge_url, bridge_token, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project_id=excluded.project_id,
                    blueprint_id=excluded.blueprint_id,
                    project_dir=excluded.project_dir,
                    bridge_url=excluded.bridge_url,
                    bridge_token=excluded.bridge_token,
                    active=excluded.active,
                    updated_at=excluded.updated_at
                """,
                (binding_id, project_id, blueprint_id, project_dir, bridge_url, bridge_token, int(active), timestamp, timestamp),
            )
            return self._binding_row(conn, binding_id)

    def update_runtime_binding(self, binding_id: str, **updates: Any) -> dict[str, Any]:
        allowed = {
            "blueprint_id": "blueprint_id",
            "project_dir": "project_dir",
            "bridge_url": "bridge_url",
            "bridge_token": "bridge_token",
            "active": "active",
        }
        clauses: list[str] = []
        values: list[Any] = []
        for key, column in allowed.items():
            if key not in updates or updates[key] is None:
                continue
            clauses.append(f"{column} = ?")
            value = updates[key]
            values.append(int(value) if key == "active" else value)
        clauses.append("updated_at = ?")
        values.append(now_ts())
        values.append(binding_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE runtime_bindings SET {', '.join(clauses)} WHERE id = ?", values)
            return self._binding_row(conn, binding_id)

    def list_runtime_bindings(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM runtime_bindings WHERE project_id = ? ORDER BY created_at", (project_id,))]

    def get_active_binding(self, project_id: str) -> Optional[dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM runtime_bindings WHERE project_id = ? AND active = 1 ORDER BY updated_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_binding(self, binding_id: str) -> Optional[dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM runtime_bindings WHERE id = ?", (binding_id,)).fetchone()
            return dict(row) if row else None

    def upsert_desktop_blueprint_snapshot(
        self,
        *,
        project_id: str,
        blueprint_id: str,
        user_id: str,
        title: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        timestamp = now_ts()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM desktop_blueprint_snapshots WHERE project_id = ? AND blueprint_id = ?",
                (project_id, blueprint_id),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO desktop_blueprint_snapshots
                    (project_id, blueprint_id, user_id, title, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, blueprint_id) DO UPDATE SET
                    user_id=excluded.user_id,
                    title=excluded.title,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    project_id,
                    blueprint_id,
                    user_id,
                    title,
                    json.dumps(payload, ensure_ascii=False),
                    float(existing["created_at"]) if existing else timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                "SELECT * FROM desktop_blueprint_snapshots WHERE project_id = ? AND blueprint_id = ?",
                (project_id, blueprint_id),
            ).fetchone()
            return dict(row)

    def get_desktop_blueprint_snapshot(self, project_id: str, blueprint_id: str) -> Optional[dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM desktop_blueprint_snapshots WHERE project_id = ? AND blueprint_id = ?",
                (project_id, blueprint_id),
            ).fetchone()
            return dict(row) if row else None

    def upsert_desktop_bridge(self, *, user_id: str, session_id: str, bridge_url: str, bridge_token: str) -> dict[str, Any]:
        timestamp = now_ts()
        with self.connect() as conn:
            session = conn.execute(
                """
                SELECT id
                FROM sessions
                WHERE id = ?
                  AND user_id = ?
                  AND client_kind = 'desktop'
                  AND revoked_at IS NULL
                  AND expires_at >= ?
                """,
                (session_id, user_id, timestamp),
            ).fetchone()
            if not session:
                raise KeyError(f"active desktop session not found: {session_id}")
            existing = conn.execute("SELECT created_at FROM desktop_bridges WHERE session_id = ?", (session_id,)).fetchone()
            conn.execute(
                """
                INSERT INTO desktop_bridges (session_id, user_id, bridge_url, bridge_token, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    user_id=excluded.user_id,
                    bridge_url=excluded.bridge_url,
                    bridge_token=excluded.bridge_token,
                    updated_at=excluded.updated_at
                """,
                (
                    session_id,
                    user_id,
                    bridge_url,
                    bridge_token,
                    float(existing["created_at"]) if existing else timestamp,
                    timestamp,
                ),
            )
            row = conn.execute("SELECT * FROM desktop_bridges WHERE session_id = ?", (session_id,)).fetchone()
            return dict(row)

    def get_active_desktop_bridge(self, user_id: str) -> Optional[dict[str, Any]]:
        timestamp = now_ts()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT desktop_bridges.*, sessions.created_at AS session_created_at, sessions.expires_at AS session_expires_at
                FROM desktop_bridges
                JOIN sessions ON sessions.id = desktop_bridges.session_id
                WHERE desktop_bridges.user_id = ?
                  AND sessions.user_id = desktop_bridges.user_id
                  AND sessions.client_kind = 'desktop'
                  AND sessions.revoked_at IS NULL
                  AND sessions.expires_at >= ?
                ORDER BY sessions.created_at DESC, desktop_bridges.updated_at DESC
                LIMIT 1
                """,
                (user_id, timestamp),
            ).fetchone()
            return dict(row) if row else None

    def upsert_desktop_session_snapshot(
        self,
        *,
        user_id: str,
        desktop_session_id: str,
        active_session_id: Optional[str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        timestamp = now_ts()
        with self.connect() as conn:
            session = conn.execute(
                """
                SELECT id
                FROM sessions
                WHERE id = ?
                  AND user_id = ?
                  AND client_kind = 'desktop'
                  AND revoked_at IS NULL
                  AND expires_at >= ?
                """,
                (desktop_session_id, user_id, timestamp),
            ).fetchone()
            if not session:
                raise KeyError(f"active desktop session not found: {desktop_session_id}")
            existing = conn.execute("SELECT created_at FROM desktop_session_snapshots WHERE user_id = ?", (user_id,)).fetchone()
            conn.execute(
                """
                INSERT INTO desktop_session_snapshots
                    (user_id, desktop_session_id, active_session_id, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    desktop_session_id=excluded.desktop_session_id,
                    active_session_id=excluded.active_session_id,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    user_id,
                    desktop_session_id,
                    active_session_id,
                    json.dumps(payload, ensure_ascii=False),
                    float(existing["created_at"]) if existing else timestamp,
                    timestamp,
                ),
            )
            row = conn.execute("SELECT * FROM desktop_session_snapshots WHERE user_id = ?", (user_id,)).fetchone()
            return dict(row)

    def get_desktop_session_snapshot(self, user_id: str) -> Optional[dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM desktop_session_snapshots WHERE user_id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def create_desktop_interaction(
        self,
        *,
        user_id: str,
        mobile_session_id: str,
        desktop_session_id: Optional[str],
        interaction_type: str,
        status: str,
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        interaction_id = new_id("int")
        timestamp = now_ts()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO desktop_interactions
                    (id, user_id, mobile_session_id, desktop_session_id, interaction_type, status, request_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    interaction_id,
                    user_id,
                    mobile_session_id,
                    desktop_session_id,
                    interaction_type,
                    status,
                    json.dumps(request_payload, ensure_ascii=False),
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute("SELECT * FROM desktop_interactions WHERE id = ?", (interaction_id,)).fetchone()
            return dict(row)

    def update_desktop_interaction(
        self,
        interaction_id: str,
        *,
        status: str,
        response_payload: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE desktop_interactions
                SET status = ?, response_json = ?, error = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    json.dumps(response_payload, ensure_ascii=False) if response_payload is not None else None,
                    error,
                    now_ts(),
                    interaction_id,
                ),
            )
            row = conn.execute("SELECT * FROM desktop_interactions WHERE id = ?", (interaction_id,)).fetchone()
            if not row:
                raise KeyError(f"desktop interaction not found: {interaction_id}")
            return dict(row)

    def upsert_run_from_runtime(self, project_id: str, blueprint_id: str, runtime_run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        timestamp = now_ts()
        status = normalize_status(payload.get("status") or payload.get("finalStatus") or "unknown")
        created_at = _coerce_timestamp(payload.get("createdAt"), timestamp)
        updated_at = _coerce_timestamp(payload.get("updatedAt"), timestamp)
        ended_at = _optional_timestamp(payload.get("endedAt"))
        title = str(payload.get("title") or payload.get("runId") or runtime_run_id)
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM runs WHERE project_id = ? AND runtime_run_id = ?",
                (project_id, runtime_run_id),
            ).fetchone()
            run_id = str(existing["id"]) if existing else new_id("run")
            conn.execute(
                """
                INSERT INTO runs (id, project_id, runtime_run_id, blueprint_id, title, status, created_at, updated_at, ended_at, runtime_payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, runtime_run_id) DO UPDATE SET
                    blueprint_id=excluded.blueprint_id,
                    title=excluded.title,
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    ended_at=excluded.ended_at,
                    runtime_payload_json=excluded.runtime_payload_json
                """,
                (
                    run_id,
                    project_id,
                    runtime_run_id,
                    blueprint_id,
                    title,
                    status,
                    created_at,
                    updated_at,
                    ended_at,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            return self._run_row(conn, run_id)

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            return dict(row) if row else None

    def list_runs_for_project(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM runs WHERE project_id = ? ORDER BY updated_at DESC", (project_id,))]

    def record_message(self, run_id: str, user_id: Optional[str], *, direction: str, body: str) -> dict[str, Any]:
        message_id = new_id("msg")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (id, run_id, user_id, direction, body, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, run_id, user_id, direction, body, now_ts()),
            )
            row = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
            return dict(row) if row else {"id": message_id}

    def record_approval(
        self,
        run_id: str,
        user_id: Optional[str],
        *,
        action: str,
        changeset_id: Optional[str] = None,
        status: str = "recorded",
        reason: str = "",
        payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        approval_id = new_id("apr")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO approval_records
                    (id, run_id, user_id, action, changeset_id, status, reason, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval_id,
                    run_id,
                    user_id,
                    action,
                    changeset_id,
                    status,
                    reason,
                    json.dumps(payload or {}, ensure_ascii=False),
                    now_ts(),
                ),
            )
            row = conn.execute("SELECT * FROM approval_records WHERE id = ?", (approval_id,)).fetchone()
            return dict(row) if row else {"id": approval_id}

    def create_planning_request(
        self,
        *,
        project_id: str,
        blueprint_id: str,
        user_id: str,
        goal: str,
    ) -> dict[str, Any]:
        request_id = new_id("pln")
        timestamp = now_ts()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO planning_requests
                    (id, project_id, blueprint_id, user_id, goal, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (request_id, project_id, blueprint_id, user_id, goal, "pending_desktop", timestamp, timestamp),
            )
            return self._planning_request_row(conn, request_id)

    def get_planning_request(self, request_id: str) -> Optional[dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM planning_requests WHERE id = ?", (request_id,)).fetchone()
            return dict(row) if row else None

    def list_planning_requests(self, project_id: str, *, status: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        values: list[Any] = [project_id]
        clause = "WHERE project_id = ?"
        if status:
            clause += " AND status = ?"
            values.append(status)
        values.append(max(1, min(int(limit), 100)))
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM planning_requests
                {clause}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                values,
            ).fetchall()
            return [dict(row) for row in rows]

    def update_planning_request(self, request_id: str, **updates: Any) -> dict[str, Any]:
        allowed = {
            "status": "status",
            "desktop_session_id": "desktop_session_id",
            "planning_session_id": "planning_session_id",
            "claimed_by_user_id": "claimed_by_user_id",
            "pending_question_json": "pending_question_json",
            "pending_plan_json": "pending_plan_json",
            "mobile_answer_json": "mobile_answer_json",
            "active_run_id": "active_run_id",
            "error": "error",
        }
        clauses: list[str] = []
        values: list[Any] = []
        for key, column in allowed.items():
            if key not in updates:
                continue
            value = updates[key]
            if key.endswith("_json") and value is not None and not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False)
            clauses.append(f"{column} = ?")
            values.append(value)
        clauses.append("updated_at = ?")
        values.append(now_ts())
        values.append(request_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE planning_requests SET {', '.join(clauses)} WHERE id = ?", values)
            return self._planning_request_row(conn, request_id)

    def append_event(
        self,
        run_id: str,
        *,
        event_key: str,
        event_type: str,
        occurred_at: float,
        node_id: Optional[str],
        agent_id: Optional[str],
        payload: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        timestamp = now_ts()
        with self.connect() as conn:
            try:
                cur = conn.execute(
                    """
                    INSERT INTO runtime_events (run_id, event_key, type, occurred_at, node_id, agent_id, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, event_key, event_type, occurred_at, node_id, agent_id, json.dumps(payload, ensure_ascii=False), timestamp),
                )
            except sqlite3.IntegrityError:
                return None
            row = conn.execute("SELECT * FROM runtime_events WHERE id = ?", (cur.lastrowid,)).fetchone()
            return dict(row) if row else None

    def events_after(self, run_id: str, cursor: int = 0, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM runtime_events
                WHERE run_id = ? AND id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (run_id, int(cursor or 0), limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def last_event_cursor(self, run_id: str) -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT MAX(id) AS cursor FROM runtime_events WHERE run_id = ?", (run_id,)).fetchone()
            return str(row["cursor"] or "0")

    def audit(
        self,
        *,
        action: str,
        status: str,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        run_id: Optional[str] = None,
        code: Optional[str] = None,
        summary: Optional[dict[str, Any]] = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (request_id, user_id, action, project_id, run_id, status, code, summary_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (request_id, user_id, action, project_id, run_id, status, code, json.dumps(summary or {}, ensure_ascii=False), now_ts()),
            )

    def list_audit_logs(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM audit_logs ORDER BY id ASC")]

    def record_client_logs(self, entries: list[dict[str, Any]], *, session_user_id: Optional[str] = None) -> int:
        if not entries:
            return 0
        timestamp = now_ts()
        with self.connect() as conn:
            for entry in entries:
                conn.execute(
                    """
                    INSERT INTO client_logs
                        (session_user_id, level, event, message, context_json, request_id, client_created_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_user_id,
                        str(entry.get("level") or "info"),
                        str(entry.get("event") or "mobile.unknown")[:128],
                        str(entry.get("message") or "")[:1024],
                        json.dumps(entry.get("context") or {}, ensure_ascii=False),
                        str(entry.get("request_id") or "")[:128] or None,
                        str(entry.get("client_created_at") or "")[:64] or None,
                        timestamp,
                    ),
                )
        return len(entries)

    def list_client_logs(
        self,
        *,
        level: Optional[str] = None,
        event: Optional[str] = None,
        user_id: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if level:
            clauses.append("level = ?")
            values.append(level)
        if event:
            clauses.append("event = ?")
            values.append(event)
        if user_id:
            clauses.append("session_user_id = ?")
            values.append(user_id)
        if since is not None:
            clauses.append("created_at >= ?")
            values.append(float(since))
        if until is not None:
            clauses.append("created_at <= ?")
            values.append(float(until))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(max(1, min(int(limit), 500)))
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM client_logs
                {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                values,
            ).fetchall()
            return [dict(row) for row in rows]

    def _user_row(self, conn: sqlite3.Connection, user_id: str) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise KeyError(f"user not found: {user_id}")
        return dict(row)

    def _project_row(self, conn: sqlite3.Connection, project_id: str) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            raise KeyError(f"project not found: {project_id}")
        return dict(row)

    def _member_row(self, conn: sqlite3.Connection, project_id: str, user_id: str) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT project_members.project_id, project_members.user_id, project_members.role, users.username
            FROM project_members
            JOIN users ON users.id = project_members.user_id
            WHERE project_members.project_id = ? AND project_members.user_id = ?
            """,
            (project_id, user_id),
        ).fetchone()
        if not row:
            raise KeyError(f"member not found: {project_id}/{user_id}")
        return dict(row)

    def _binding_row(self, conn: sqlite3.Connection, binding_id: str) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM runtime_bindings WHERE id = ?", (binding_id,)).fetchone()
        if not row:
            raise KeyError(f"runtime binding not found: {binding_id}")
        return dict(row)

    def _run_row(self, conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            raise KeyError(f"run not found: {run_id}")
        return dict(row)

    def _planning_request_row(self, conn: sqlite3.Connection, request_id: str) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM planning_requests WHERE id = ?", (request_id,)).fetchone()
        if not row:
            raise KeyError(f"planning request not found: {request_id}")
        return dict(row)


def row_bool(row: dict[str, Any], key: str) -> bool:
    return bool(int(row.get(key) or 0))


def normalize_status(value: Any) -> str:
    status = str(value or "unknown").lower()
    if status in {"running", "completed", "cancelled", "failed", "paused"}:
        return status
    if status in {"success", "partial_success"}:
        return "completed"
    return "unknown"


def _coerce_timestamp(value: Any, fallback: float) -> float:
    parsed = _optional_timestamp(value)
    return fallback if parsed is None else parsed


def _optional_timestamp(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            try:
                from datetime import datetime

                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return None
    return None
