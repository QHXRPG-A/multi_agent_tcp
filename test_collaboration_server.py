from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from multi_agent_tcp.collaboration_server.auth import APIError
from multi_agent_tcp.collaboration_server.app import create_app
from multi_agent_tcp.collaboration_server.observability import configure_observability
from multi_agent_tcp.collaboration_server.runtime_bridge import DesktopRuntimeBridge


class FakeBridge:
    def __init__(self) -> None:
        self.write_calls: list[dict[str, Any]] = []

    def list_runs(self, binding: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "runId": "runtime-run-1",
                "title": "Runtime Run 1",
                "status": "running",
                "createdAt": 1000,
                "updatedAt": 1005,
            }
        ]

    def status(self, binding: dict[str, Any], runtime_run_id: str) -> dict[str, Any]:
        return {
            "ok": True,
            "runId": runtime_run_id,
            "status": {
                "run": {"status": "running", "final_status": None, "ended_at": None},
                "agents": {
                    "planner": {
                        "node_id": "planner",
                        "agent_id": "Planner",
                        "state": "completed",
                        "queue_size": 0,
                        "messages_sent": 2,
                        "busy_count": 0,
                        "updated_at": 1004,
                    },
                    "coder": {
                        "node_id": "coder",
                        "agent_id": "Coder",
                        "state": "running",
                        "queue_size": 1,
                        "messages_sent": 3,
                        "busy_count": 1,
                        "updated_at": 1005,
                    },
                },
                "queues": {"by_agent": {"coder": [{"id": "msg-1"}]}},
                "outgoing_batches": {"batch-1": {"status": "staging"}},
                "joins": {"join-1": {"status": "waiting"}},
                "jobs": {"job-1": {"status": "running"}},
                "workspace": {
                    "reports": [{"id": "rep-1", "path": "reports/summary.md", "mediaType": "text/markdown"}],
                    "artifacts": [{"id": "art-1", "path": "artifacts/log.txt", "bytes": 7}],
                },
                "organization": {
                    "graph": {"edges": [{"from": "planner", "to": "coder", "edge_type": "exec"}]},
                    "agents": {
                        "planner": {"agent_id": "Planner", "cli_kind": "codex", "upstream_agents": [], "downstream_agents": ["coder"]},
                        "coder": {"agent_id": "Coder", "cli_kind": "codex", "upstream_agents": ["planner"], "downstream_agents": []},
                    },
                },
            },
        }

    def recent_events(self, binding: dict[str, Any], runtime_run_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return [
            {
                "type": "agent.status",
                "node_id": "coder",
                "agent_id": "Coder",
                "timestamp": 1005,
                "payload": "running",
                "bearer_token": "secret-token",
                "private_checkout_path": "C:\\private\\checkout",
            }
        ]

    def agent_info(self, binding: dict[str, Any], runtime_run_id: str, node_id: str) -> dict[str, Any]:
        return {
            "ok": True,
            "nodeId": node_id,
            "runtime": {"state": "running", "workspace_rpc_token": "rpc-secret"},
            "node": {"cwd": "C:\\project\\real"},
        }

    def run_diff(self, binding: dict[str, Any], runtime_run_id: str) -> dict[str, Any]:
        return {
            "summary": {"total": 1, "accepted": 1, "files": 1, "additions": 3, "deletions": 1},
            "changesets": [{"id": "chg-1", "status": "accepted", "summary": "Edited app", "files": ["src/app.py"]}],
        }

    def changeset_diff(self, binding: dict[str, Any], runtime_run_id: str, changeset_id: str) -> dict[str, Any]:
        return {"id": changeset_id, "patch": "diff --git", "service_token": "server-secret"}

    def start_run(self, binding: dict[str, Any], plan: dict[str, Any], *, execution_mode: str = "live") -> dict[str, Any]:
        self.write_calls.append({"command": "start", "plan": plan, "executionMode": execution_mode})
        return {
            "ok": True,
            "runId": "runtime-run-started",
            "status": {"run": {"status": "running"}, "agents": {}, "queues": {"by_agent": {}}},
        }

    def queue_agent_message(
        self,
        binding: dict[str, Any],
        runtime_run_id: str,
        node_id: str,
        text: str,
        *,
        mode: str = "default",
    ) -> dict[str, Any]:
        self.write_calls.append({"command": "message", "runId": runtime_run_id, "nodeId": node_id, "text": text, "mode": mode})
        return {"ok": True, "queued": True, "nodeId": node_id}

    def end_run(self, binding: dict[str, Any], runtime_run_id: str, *, action: str, reason: str = "") -> dict[str, Any]:
        self.write_calls.append({"command": "end", "runId": runtime_run_id, "action": action, "reason": reason})
        return {"ok": True, "end": {"run_status": "cancelled"}, "status": {"run": {"status": "cancelled"}}}

    def rollback_changesets(
        self,
        binding: dict[str, Any],
        runtime_run_id: str,
        changeset_id: str,
        *,
        reason: str = "",
    ) -> dict[str, Any]:
        self.write_calls.append({"command": "rollback", "runId": runtime_run_id, "changesetId": changeset_id, "reason": reason})
        return {"ok": True, "rollback": {"status": "rolled_back", "changesetIds": [changeset_id]}}

    def mark_planning_plan_started(
        self,
        binding: dict[str, Any],
        planning_session_id: str,
        runtime_run_id: str,
        started: dict[str, Any],
    ) -> dict[str, Any]:
        self.write_calls.append({"command": "markPlanStarted", "sessionId": planning_session_id, "runId": runtime_run_id})
        return {"ok": True, "activeRun": {"runId": runtime_run_id}}


class FakeDesktopBridge:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail = False

    def request(self, bridge: dict[str, Any], command: str, args: dict[str, Any]) -> dict[str, Any]:
        if self.fail:
            raise APIError(503, "DESKTOP_UNAVAILABLE", "desktop offline")
        self.calls.append({"bridge": bridge, "command": command, "args": args})
        return {"ok": True, "accepted": True, "command": command}


def make_client(tmp_path: Path) -> TestClient:
    seed = {
        "admin": {"id": "admin", "username": "admin", "password": "admin-pass-123", "role": "admin"},
        "users": [
            {"id": "viewer", "username": "viewer", "password": "viewer-pass-123", "role": "user"},
        ],
        "projects": [
            {
                "id": "proj-1",
                "name": "Project One",
                "members": [{"userId": "admin", "role": "owner"}, {"userId": "viewer", "role": "viewer"}],
                "runtimeBinding": {
                    "id": "binding-1",
                    "blueprintId": "default",
                    "projectDir": "C:\\secret\\project",
                    "bridgeUrl": "http://127.0.0.1:1/blueprint",
                    "bridgeToken": "desktop-secret",
                },
            }
        ],
    }
    bridge = FakeBridge()
    desktop_bridge = FakeDesktopBridge()
    app = create_app(
        db_path=tmp_path / "collab.sqlite3",
        bridge_factory=lambda: bridge,
        desktop_bridge_factory=lambda: desktop_bridge,
        log_dir=tmp_path / "logs",
    )
    app.state.fake_bridge = bridge
    app.state.fake_desktop_bridge = desktop_bridge
    app.state.store.seed(seed)
    return TestClient(app)


def login(
    client: TestClient,
    username: str = "admin",
    password: str = "admin-pass-123",
    client_kind: str | None = None,
) -> str:
    payload = {"username": username, "password": password}
    if client_kind:
        payload["clientKind"] = client_kind
    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 200, response.text
    return str(response.json()["csrfToken"])


def _json_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for item in value.values():
            keys.update(_json_keys(item))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for item in value:
            keys.update(_json_keys(item))
        return keys
    return set()


def test_register_login_and_project_access_boundaries(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    assert client.get("/api/projects").status_code == 401

    registered = client.post("/api/auth/register", json={"username": "alice", "password": "alice-pass-123"})
    assert registered.status_code == 200
    csrf = login(client, "alice", "alice-pass-123")
    assert csrf
    assert client.get("/api/projects").json()["projects"] == []

    # Alice is active but has no project membership, so a known run is still forbidden.
    admin_csrf = login(client)
    runs = client.get("/api/projects/proj-1/runs").json()["runs"]
    run_id = runs[0]["id"]
    login(client, "alice", "alice-pass-123")
    forbidden = client.get(f"/api/runs/{run_id}")
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "PROJECT_FORBIDDEN"
    assert admin_csrf


def test_admin_management_and_redacted_runtime_binding(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    csrf = login(client)
    headers = {"x-csrf-token": csrf}

    created = client.post(
        "/api/admin/users",
        json={"username": "bob", "password": "bob-pass-123", "role": "user"},
        headers=headers,
    )
    assert created.status_code == 200
    user_id = created.json()["user"]["id"]

    member = client.post(
        "/api/admin/projects/proj-1/members",
        json={"userId": user_id, "role": "viewer"},
        headers=headers,
    )
    assert member.status_code == 200

    bindings = client.get("/api/admin/projects/proj-1/runtime-bindings")
    body = bindings.json()
    assert body["runtimeBindings"][0]["bridgeToken"] == "[redacted]"
    assert body["runtimeBindings"][0]["projectDir"] == "[redacted]"
    assert "desktop-secret" not in bindings.text
    assert "C:\\secret\\project" not in bindings.text


def test_admin_user_monitor_requires_admin_and_summarizes_presence(tmp_path: Path) -> None:
    anonymous = make_client(tmp_path)

    assert anonymous.get("/api/admin/monitor/users").status_code == 401

    viewer = TestClient(anonymous.app)
    login(viewer, "viewer", "viewer-pass-123", client_kind="mobile")
    assert viewer.get("/api/admin/monitor/users").status_code == 403

    admin_console = TestClient(anonymous.app)
    admin_mobile = TestClient(anonymous.app)
    admin_desktop = TestClient(anonymous.app)
    login(admin_console)
    login(admin_mobile, client_kind="mobile")
    login(admin_desktop, client_kind="desktop")
    mobile_session_id = str(admin_mobile.cookies.get("gulicode_collab_session"))

    logged = admin_mobile.post(
        "/api/client-logs",
        json={"logs": [{"level": "info", "event": "mobile.load.success", "message": "loaded"}]},
    )
    assert logged.status_code == 200

    response = admin_console.get("/api/admin/monitor/users")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["totals"]["totalUsers"] == 2
    assert body["totals"]["activeUsers"] == 2
    assert body["totals"]["activeSessions"] == 4
    assert body["totals"]["mobileOnline"] == 2
    assert body["totals"]["desktopOnline"] == 1

    admin = next(item for item in body["users"] if item["user"]["id"] == "admin")
    assert admin["clients"] == {"mobile": True, "desktop": True}
    assert admin["activeSessionCount"] == 3
    assert admin["lastLoginAt"]
    assert admin["lastClientLogAt"]
    assert {session["clientKind"] for session in admin["sessions"]} == {None, "mobile", "desktop"}
    assert any(session["idSuffix"] == mobile_session_id[-8:] for session in admin["sessions"])

    text = response.text
    assert mobile_session_id not in text
    assert "csrf_token" not in text
    assert "password_hash" not in text
    assert "desktop-secret" not in text


def test_desktop_login_takes_over_previous_desktop_without_revoking_mobile(tmp_path: Path) -> None:
    mobile_one = make_client(tmp_path)
    mobile_two = TestClient(mobile_one.app)
    desktop_one = TestClient(mobile_one.app)
    desktop_two = TestClient(mobile_one.app)

    login(mobile_one, client_kind="mobile")
    login(mobile_two, client_kind="mobile")
    login(desktop_one, client_kind="desktop")
    login(desktop_two, client_kind="desktop")

    assert desktop_one.get("/api/me").status_code == 401
    assert mobile_one.get("/api/me").status_code == 200
    assert mobile_two.get("/api/me").status_code == 200
    me = mobile_one.get("/api/me").json()
    assert me["clients"] == {"mobile": True, "desktop": True}
    assert me["syncReady"] is True


def test_desktop_bridge_and_snapshot_require_active_desktop_session(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    mobile = TestClient(client.app)
    desktop_old = TestClient(client.app)
    desktop_new = TestClient(client.app)
    login(mobile, client_kind="mobile")
    old_csrf = login(desktop_old, client_kind="desktop")
    old_headers = {"x-csrf-token": old_csrf}

    registered = desktop_old.post(
        "/api/desktop/bridge",
        json={"bridgeUrl": "http://127.0.0.1:39999/desktop-control", "bridgeToken": "desktop-token-secret"},
        headers=old_headers,
    )
    assert registered.status_code == 200, registered.text

    snapshot = desktop_old.post(
        "/api/desktop/session-snapshot",
        json={
            "activeSessionId": "session-1",
            "sessions": [{"id": "session-1", "title": "Work", "messageCount": 2}],
            "currentMessages": [{"id": "msg-1", "role": "user", "body": "hello"}],
            "updatedAt": "2026-05-29T00:00:00Z",
        },
        headers=old_headers,
    )
    assert snapshot.status_code == 200, snapshot.text

    new_csrf = login(desktop_new, client_kind="desktop")
    assert desktop_old.post(
        "/api/desktop/bridge",
        json={"bridgeUrl": "http://127.0.0.1:39998/desktop-control", "bridgeToken": "stale"},
        headers=old_headers,
    ).status_code == 401

    active = desktop_new.post(
        "/api/desktop/bridge",
        json={"bridgeUrl": "http://127.0.0.1:39997/desktop-control", "bridgeToken": "new-token-secret"},
        headers={"x-csrf-token": new_csrf},
    )
    assert active.status_code == 200, active.text


def test_mobile_desktop_sessions_and_submit_use_registered_desktop_bridge(tmp_path: Path) -> None:
    mobile = make_client(tmp_path)
    desktop = TestClient(mobile.app)
    login(mobile, client_kind="mobile")
    desktop_csrf = login(desktop, client_kind="desktop")
    desktop_headers = {"x-csrf-token": desktop_csrf}
    mobile_csrf = mobile.get("/api/me").json()["csrfToken"]
    mobile_headers = {"x-csrf-token": mobile_csrf}

    unavailable = mobile.post("/api/mobile/desktop-submit", json={"text": "hello desktop"}, headers=mobile_headers)
    assert unavailable.status_code == 200, unavailable.text
    assert unavailable.json()["status"] == "desktop_unavailable"
    assert unavailable.json()["accepted"] is False
    pre_bridge_sessions = mobile.get("/api/mobile/desktop-sessions")
    assert pre_bridge_sessions.status_code == 200, pre_bridge_sessions.text
    assert pre_bridge_sessions.json()["desktop"]["loggedIn"] is True
    assert pre_bridge_sessions.json()["desktop"]["online"] is False

    desktop.post(
        "/api/desktop/bridge",
        json={"bridgeUrl": "http://127.0.0.1:39999/desktop-control", "bridgeToken": "desktop-token-secret"},
        headers=desktop_headers,
    )
    desktop.post(
        "/api/desktop/session-snapshot",
        json={
            "activeSessionId": "session-1",
            "sessions": [{"id": "session-1", "title": "Desktop Session", "messageCount": 2}],
            "currentMessages": [
                {"id": "msg-1", "role": "user", "label": "User", "body": "hi"},
                {
                    "id": "msg-2",
                    "role": "assistant",
                    "label": "Assistant",
                    "body": "hello",
                    "segments": [
                        {"id": "seg-1", "type": "text", "body": "hello"},
                        {"id": "seg-2", "type": "reasoning", "title": "思考过程", "body": "checking context"},
                        {"id": "seg-3", "type": "tool", "title": "工具调用 · read", "toolName": "read", "status": "completed", "body": "Output\nok"},
                    ],
                },
            ],
            "composer": {
                "modes": [
                    {"id": "Build", "label": "Build", "kind": "agent"},
                    {"id": "Plan", "label": "Plan", "kind": "agent"},
                    {"id": "blueprintPlanning", "label": "蓝图规划", "kind": "blueprintPlanning"},
                ],
                "activeModeId": "Build",
            },
        },
        headers=desktop_headers,
    )

    sessions = mobile.get("/api/mobile/desktop-sessions")
    assert sessions.status_code == 200, sessions.text
    assert sessions.json()["desktop"]["online"] is True
    assert sessions.json()["desktop"]["loggedIn"] is True
    assert sessions.json()["activeSessionId"] == "session-1"
    assert sessions.json()["sessions"][0]["title"] == "Desktop Session"
    assert sessions.json()["composer"]["activeModeId"] == "Build"
    assert [mode["label"] for mode in sessions.json()["composer"]["modes"]] == ["Build", "Plan", "蓝图规划"]
    assistant_message = sessions.json()["currentMessages"][1]
    assert [segment["type"] for segment in assistant_message["segments"]] == ["text", "reasoning", "tool"]
    assert "desktop-token-secret" not in sessions.text

    submitted = mobile.post(
        "/api/mobile/desktop-submit",
        json={"text": "continue", "sessionId": "session-1", "promptMode": "normal", "agentName": "Build"},
        headers=mobile_headers,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["accepted"] is True
    bridge = mobile.app.state.fake_desktop_bridge
    assert bridge.calls[-1]["command"] == "desktop.session.submit"
    assert bridge.calls[-1]["args"]["text"] == "continue"
    assert bridge.calls[-1]["args"]["promptMode"] == "normal"
    assert bridge.calls[-1]["args"]["agentName"] == "Build"
    assert "desktop-token-secret" not in submitted.text

    legacy_submitted = mobile.post(
        "/api/mobile/desktop-submit",
        json={"text": "legacy", "sessionId": "session-1", "mode": "default"},
        headers=mobile_headers,
    )
    assert legacy_submitted.status_code == 200, legacy_submitted.text
    assert bridge.calls[-1]["args"]["text"] == "legacy"
    assert bridge.calls[-1]["args"]["promptMode"] == "normal"

    deleted = mobile.post("/api/mobile/desktop-session-delete", json={"sessionId": "session-1"}, headers=mobile_headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["accepted"] is True
    assert bridge.calls[-1]["command"] == "desktop.session.delete"
    assert bridge.calls[-1]["args"]["sessionId"] == "session-1"
    assert "desktop-token-secret" not in deleted.text


def test_mobile_planning_request_pushes_to_desktop_bridge_when_registered(tmp_path: Path) -> None:
    mobile = make_client(tmp_path)
    desktop = TestClient(mobile.app)
    login(mobile, client_kind="mobile")
    desktop_csrf = login(desktop, client_kind="desktop")
    desktop.post(
        "/api/desktop/bridge",
        json={"bridgeUrl": "http://127.0.0.1:39999/desktop-control", "bridgeToken": "desktop-token-secret"},
        headers={"x-csrf-token": desktop_csrf},
    )
    mobile_csrf = mobile.get("/api/me").json()["csrfToken"]

    created = mobile.post(
        "/api/projects/proj-1/planning-requests",
        json={"goal": "plan from mobile"},
        headers={"x-csrf-token": mobile_csrf},
    )

    assert created.status_code == 200, created.text
    assert created.json()["desktopDelivery"] == {"status": "accepted", "accepted": True}
    bridge = mobile.app.state.fake_desktop_bridge
    assert bridge.calls[-1]["command"] == "desktop.mobilePlanning.submit"
    assert bridge.calls[-1]["args"]["planningRequest"]["goal"] == "plan from mobile"
    assert "desktop-token-secret" not in created.text


def test_read_only_runtime_projection_events_and_scrubbing(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    login(client)

    projects = client.get("/api/projects").json()["projects"]
    assert projects[0]["latestRun"]["status"] == "running"
    run_id = projects[0]["latestRun"]["id"]

    status = client.get(f"/api/runs/{run_id}/status")
    assert status.status_code == 200
    body = status.json()
    assert body["status"]["pending"] == {
        "queuedMessages": 1,
        "waitingOutgoingBatches": 1,
        "waitingJoins": 1,
        "runningJobs": 1,
    }
    assert body["status"]["run"]["currentNodeIds"] == ["coder"]
    assert "secret-token" not in status.text
    assert "C:\\private\\checkout" not in status.text

    events = client.get(f"/api/runs/{run_id}/events?cursor=0").json()["events"]
    assert events[0]["type"] == "agent.status"
    assert events[0]["payload"]["bearer_token"] == "[redacted]"

    agent = client.get(f"/api/runs/{run_id}/agents/coder")
    assert agent.status_code == 200
    assert "rpc-secret" not in agent.text
    assert "C:\\project\\real" not in agent.text

    diff = client.get(f"/api/runs/{run_id}/diff").json()["diff"]
    assert diff["accepted"] == 1
    assert diff["changesets"][0]["id"] == "chg-1"

    changeset = client.get(f"/api/runs/{run_id}/changesets/chg-1/diff")
    assert changeset.status_code == 200
    assert "server-secret" not in changeset.text


def test_mobile_tick_requires_login(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/api/mobile/tick")

    assert response.status_code == 401


def test_mobile_tick_waits_for_desktop_presence(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    login(client, client_kind="mobile")

    me = client.get("/api/me")
    tick = client.get("/api/mobile/tick")

    assert me.status_code == 200
    assert me.json()["clients"] == {"mobile": True, "desktop": False}
    assert me.json()["syncReady"] is False
    assert tick.status_code == 200
    assert tick.json()["clients"] == {"mobile": True, "desktop": False}
    assert tick.json()["syncReady"] is False
    assert tick.json()["project"] is None
    assert tick.json()["run"] is None
    assert tick.json()["status"] is None


def test_mobile_tick_returns_light_runtime_projection_when_both_clients_online(tmp_path: Path) -> None:
    mobile = make_client(tmp_path)
    desktop = TestClient(mobile.app)
    login(mobile, client_kind="mobile")
    login(desktop, client_kind="desktop")

    response = mobile.get("/api/mobile/tick")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["clients"] == {"mobile": True, "desktop": True}
    assert body["syncReady"] is True
    assert body["project"]["id"] == "proj-1"
    assert body["run"]["status"] == "running"
    status = body["status"]
    assert sorted(status.keys()) == ["agents", "blueprint", "pending", "run"]
    assert status["pending"] == {
        "queuedMessages": 1,
        "waitingOutgoingBatches": 1,
        "waitingJoins": 1,
        "runningJobs": 1,
    }
    assert status["blueprint"]["nodes"] == [
        {
            "id": "planner",
            "label": "Planner",
            "role": "codex",
            "state": "completed",
            "upstreamNodeIds": [],
            "downstreamNodeIds": ["coder"],
        },
        {
            "id": "coder",
            "label": "Coder",
            "role": "codex",
            "state": "running",
            "upstreamNodeIds": ["planner"],
            "downstreamNodeIds": [],
        },
    ]
    assert status["blueprint"]["edges"] == [{"source": "planner", "target": "coder", "kind": "exec"}]
    assert status["agents"] == [
        {
            "nodeId": "planner",
            "agentId": "Planner",
            "cliKind": None,
            "state": "completed",
            "taskStatus": None,
            "queueSize": 0,
            "messagesSent": 2,
            "busyCount": 0,
            "updatedAt": "1970-01-01T00:16:44Z",
        },
        {
            "nodeId": "coder",
            "agentId": "Coder",
            "cliKind": None,
            "state": "running",
            "taskStatus": None,
            "queueSize": 1,
            "messagesSent": 3,
            "busyCount": 1,
            "updatedAt": "1970-01-01T00:16:45Z",
        },
    ]
    forbidden_keys = {"planningRequests", "diff", "events", "reports", "artifacts", "outputs", "lastCursor", "recentEvents"}
    assert not forbidden_keys.intersection(_json_keys(body))


def test_mobile_tick_projects_runtime_blueprint_structure_changes(tmp_path: Path) -> None:
    mobile = make_client(tmp_path)
    desktop = TestClient(mobile.app)
    login(mobile, client_kind="mobile")
    login(desktop, client_kind="desktop")
    bridge = mobile.app.state.fake_bridge

    def changed_status(binding: dict[str, Any], runtime_run_id: str) -> dict[str, Any]:
        base = FakeBridge().status(binding, runtime_run_id)
        status = base["status"]
        status["agents"] = {
            "planner": {
                "node_id": "planner",
                "agent_id": "Planner",
                "state": "completed",
                "task_status": "done",
                "queue_size": 0,
                "messages_sent": 2,
                "busy_count": 0,
                "updated_at": 1004,
            },
            "review": {
                "node_id": "review",
                "agent_id": "Reviewer",
                "cli_kind": "codex",
                "state": "running",
                "task_status": "reviewing",
                "queue_size": 2,
                "messages_sent": 5,
                "busy_count": 1,
                "updated_at": 1008,
            },
        }
        status["organization"] = {
            "graph": {"edges": [{"from": "planner", "to": "review", "edge_type": "data"}]},
            "agents": {
                "planner": {"agent_id": "Planner Prime", "cli_kind": "codex", "upstream_agents": [], "downstream_agents": ["review"]},
                "review": {"agent_id": "Reviewer", "cli_kind": "codex", "upstream_agents": ["planner"], "downstream_agents": []},
            },
        }
        return base

    bridge.status = changed_status

    response = mobile.get("/api/mobile/tick")

    assert response.status_code == 200, response.text
    blueprint = response.json()["status"]["blueprint"]
    assert [node["id"] for node in blueprint["nodes"]] == ["planner", "review"]
    assert [node["label"] for node in blueprint["nodes"]] == ["Planner Prime", "Reviewer"]
    assert blueprint["edges"] == [{"source": "planner", "target": "review", "kind": "data"}]
    agents = response.json()["status"]["agents"]
    assert [agent["nodeId"] for agent in agents] == ["planner", "review"]
    assert agents[1] == {
        "nodeId": "review",
        "agentId": "Reviewer",
        "cliKind": "codex",
        "state": "running",
        "taskStatus": "reviewing",
        "queueSize": 2,
        "messagesSent": 5,
        "busyCount": 1,
        "updatedAt": "1970-01-01T00:16:48Z",
    }


def test_mobile_tick_uses_desktop_blueprint_snapshot_without_runtime_run(tmp_path: Path) -> None:
    mobile = make_client(tmp_path)
    desktop = TestClient(mobile.app)
    login(mobile, client_kind="mobile")
    desktop_csrf = login(desktop, client_kind="desktop")
    headers = {"x-csrf-token": desktop_csrf}
    bridge = mobile.app.state.fake_bridge

    def unavailable_runs(binding: dict[str, Any]) -> list[dict[str, Any]]:
        raise APIError(503, "RUNTIME_UNAVAILABLE", "runtime offline")

    bridge.list_runs = unavailable_runs

    posted = desktop.post(
        "/api/desktop/blueprint-snapshot",
        json={
            "projectDir": "C:\\secret\\project",
            "blueprintId": "default",
            "title": "当前蓝图",
            "nodes": [
                {
                    "id": "agent-a",
                    "label": "测试节点 A",
                    "role": "codex",
                    "state": "idle",
                    "x": 120,
                    "y": 240,
                    "downstreamNodeIds": ["agent-b"],
                    "agentId": "agent-a",
                    "cliKind": "codex",
                },
                {
                    "id": "agent-b",
                    "label": "测试节点 B",
                    "role": "codex",
                    "state": "idle",
                    "x": 120,
                    "y": 384,
                    "upstreamNodeIds": ["agent-a"],
                    "agentId": "agent-b",
                    "cliKind": "codex",
                },
            ],
            "edges": [{"source": "agent-a", "target": "agent-b", "kind": "exec"}],
        },
        headers=headers,
    )
    assert posted.status_code == 200, posted.text

    response = mobile.get("/api/mobile/tick")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run"] is None
    assert body["status"]["run"]["title"] == "当前蓝图"
    assert body["status"]["blueprint"]["nodes"] == [
        {
            "id": "agent-a",
            "label": "测试节点 A",
            "role": "codex",
            "state": "idle",
            "x": 120.0,
            "y": 240.0,
            "upstreamNodeIds": [],
            "downstreamNodeIds": ["agent-b"],
        },
        {
            "id": "agent-b",
            "label": "测试节点 B",
            "role": "codex",
            "state": "idle",
            "x": 120.0,
            "y": 384.0,
            "upstreamNodeIds": ["agent-a"],
            "downstreamNodeIds": [],
        },
    ]
    assert body["status"]["blueprint"]["edges"] == [{"source": "agent-a", "target": "agent-b", "kind": "exec"}]
    forbidden_keys = {"planningRequests", "diff", "events", "reports", "artifacts", "outputs", "lastCursor", "recentEvents"}
    assert not forbidden_keys.intersection(_json_keys(body))


def test_phase_two_run_writes_bridge_audit_and_capabilities(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    csrf = login(client)
    headers = {"x-csrf-token": csrf}
    run_id = client.get("/api/projects/proj-1/runs").json()["runs"][0]["id"]
    bridge = client.app.state.fake_bridge

    message = client.post(
        f"/api/runs/{run_id}/messages",
        json={"nodeId": "coder", "text": "please continue", "mode": "top"},
        headers=headers,
    )
    assert message.status_code == 200, message.text
    assert bridge.write_calls[-1] == {
        "command": "message",
        "runId": "runtime-run-1",
        "nodeId": "coder",
        "text": "please continue",
        "mode": "top",
    }

    approve = client.post(
        f"/api/runs/{run_id}/approvals",
        json={"action": "approve_diff", "changesetId": "chg-1"},
        headers=headers,
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["approval"]["status"] == "approved"
    assert bridge.write_calls[-1]["command"] == "message"

    rollback = client.post(
        f"/api/runs/{run_id}/approvals",
        json={"action": "rollback_diff", "changesetId": "chg-1", "reason": "mobile undo"},
        headers=headers,
    )
    assert rollback.status_code == 200, rollback.text
    assert bridge.write_calls[-1] == {
        "command": "rollback",
        "runId": "runtime-run-1",
        "changesetId": "chg-1",
        "reason": "mobile undo",
    }

    ended = client.post(f"/api/runs/{run_id}/end", json={"action": "cancel"}, headers=headers)
    assert ended.status_code == 200, ended.text
    assert bridge.write_calls[-1]["command"] == "end"
    assert bridge.write_calls[-1]["action"] == "cancel"

    logs = client.app.state.store.list_audit_logs()
    actions = [row["action"] for row in logs]
    assert "run.message" in actions
    assert "run.approve_diff" in actions
    assert "run.rollback_diff" in actions
    assert "run.end" in actions

    missing_csrf = client.post(f"/api/runs/{run_id}/messages", json={"nodeId": "coder", "text": "blocked"})
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["code"] == "CSRF_REQUIRED"

    viewer_csrf = login(client, "viewer", "viewer-pass-123")
    viewer_headers = {"x-csrf-token": viewer_csrf}
    denied = client.post(
        f"/api/runs/{run_id}/messages",
        json={"nodeId": "coder", "text": "viewer blocked"},
        headers=viewer_headers,
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "CAPABILITY_DISABLED"


def test_mobile_planning_request_flow_starts_live_run(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    csrf = login(client)
    headers = {"x-csrf-token": csrf}
    bridge = client.app.state.fake_bridge

    created = client.post(
        "/api/projects/proj-1/planning-requests",
        json={"goal": "build a mobile writable flow"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    planning_request_id = created.json()["planningRequest"]["id"]
    assert created.json()["planningRequest"]["status"] == "pending_desktop"

    claimed = client.post(
        f"/api/planning-requests/{planning_request_id}/desktop-claim",
        json={"desktopSessionId": "desktop-session-1"},
        headers=headers,
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["planningRequest"]["status"] == "planning"

    question = client.post(
        f"/api/planning-requests/{planning_request_id}/desktop-state",
        json={
            "planningSessionId": "planning-session-1",
            "pendingQuestion": {"id": "q1", "text": "Need scope?"},
        },
        headers=headers,
    )
    assert question.status_code == 200, question.text
    assert question.json()["planningRequest"]["status"] == "question_pending"

    answered = client.post(
        f"/api/planning-requests/{planning_request_id}/answer",
        json={"questionId": "q1", "answers": {"scope": "full"}},
        headers=headers,
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["planningRequest"]["mobileAnswer"]["answers"] == {"scope": "full"}

    plan = {
        "goal": "[来自移动端] build a mobile writable flow",
        "nodes": [{"id": "top", "agent": "Top Agent"}],
    }
    ready = client.post(
        f"/api/planning-requests/{planning_request_id}/desktop-state",
        json={
            "planningSessionId": "planning-session-1",
            "pendingPlan": {"plan": plan, "summary": "ready"},
        },
        headers=headers,
    )
    assert ready.status_code == 200, ready.text
    assert ready.json()["planningRequest"]["status"] == "plan_ready"

    approved = client.post(f"/api/planning-requests/{planning_request_id}/approve-plan", headers=headers)
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["planningRequest"]["status"] == "started"
    assert body["run"]["status"] == "running"
    assert bridge.write_calls[-2] == {"command": "start", "plan": plan, "executionMode": "live"}
    assert bridge.write_calls[-1] == {
        "command": "markPlanStarted",
        "sessionId": "planning-session-1",
        "runId": "runtime-run-started",
    }

    logs = client.app.state.store.list_audit_logs()
    actions = [row["action"] for row in logs]
    assert "planning_request.create" in actions
    assert "planning_request.claim" in actions
    assert "planning_request.desktop_state" in actions
    assert "planning_request.answer" in actions
    assert "planning_request.approve_plan" in actions


def test_request_and_permission_denied_logs_are_written(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/api/projects", headers={"x-request-id": "req-test-denied"})
    assert response.status_code == 401

    log_text = (tmp_path / "logs" / "collaboration_server.log").read_text(encoding="utf-8")
    assert "api.permission_denied" in log_text
    assert "api.request" in log_text
    assert "req-test-denied" in log_text


def test_client_logs_are_sanitized_and_admin_queryable(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    login(client)

    posted = client.post(
        "/api/client-logs",
        json={
            "logs": [
                {
                    "level": "error",
                    "event": "mobile.api.failure",
                    "message": "failed with token desktop-secret",
                    "context": {
                        "bridgeToken": "desktop-secret",
                        "cookie": "session-secret",
                        "path": "C:\\secret\\project\\file.py",
                        "status": 503,
                    },
                    "requestId": "client-req-1",
                    "createdAt": "2026-05-28T09:50:00Z",
                }
            ]
        },
    )
    assert posted.status_code == 200
    assert posted.json()["accepted"] == 1

    logs = client.get("/api/admin/logs/client?level=error")
    assert logs.status_code == 200
    body = logs.json()
    assert body["logs"][0]["event"] == "mobile.api.failure"
    assert body["logs"][0]["sessionUserId"] == "admin"
    assert "desktop-secret" not in logs.text
    assert "session-secret" not in logs.text
    assert "C:\\secret\\project" not in logs.text

    client.post("/api/auth/register", json={"username": "charlie", "password": "charlie-pass-123"})
    login(client, "charlie", "charlie-pass-123")
    denied = client.get("/api/admin/logs/client")
    assert denied.status_code == 403


def test_desktop_runtime_bridge_structured_logs_and_redaction(tmp_path: Path) -> None:
    configure_observability(log_dir=tmp_path / "bridge-logs", log_level="DEBUG")

    def ok_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        assert body["token"] == "desktop-secret"
        return httpx.Response(200, json={"ok": True, "status": {"run": {"status": "running"}}})

    binding = {
        "id": "binding-1",
        "project_id": "proj-1",
        "blueprint_id": "default",
        "bridge_url": "http://runtime.local/bridge",
        "bridge_token": "desktop-secret",
    }
    bridge = DesktopRuntimeBridge(transport=httpx.MockTransport(ok_handler))
    result = bridge.request(
        binding,
        "blueprint.status",
        {"runId": "runtime-run-1", "projectDir": "C:\\secret\\project", "bearerToken": "runtime-secret"},
    )
    assert result["ok"] is True

    def bad_json_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    bad_bridge = DesktopRuntimeBridge(transport=httpx.MockTransport(bad_json_handler))
    with pytest.raises(APIError) as raised:
        bad_bridge.request(binding, "blueprint.status", {"runId": "runtime-run-1"})
    assert raised.value.code == "RUNTIME_BAD_RESPONSE"

    log_text = (tmp_path / "bridge-logs" / "collaboration_server.log").read_text(encoding="utf-8")
    assert "runtime.bridge.request" in log_text
    assert "runtime.bridge.success" in log_text
    assert "runtime.bridge.failure" in log_text
    assert "RUNTIME_BAD_RESPONSE" in log_text
    assert "desktop-secret" not in log_text
    assert "runtime-secret" not in log_text
    assert "C:\\secret\\project" not in log_text
