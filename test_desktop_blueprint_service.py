from __future__ import annotations

import json
import asyncio
import inspect
from pathlib import Path
from urllib import request

from multi_agent_tcp.desktop_blueprint_service import (
    BlueprintServiceError,
    DesktopBlueprintHTTPServer,
    DesktopBlueprintNoopBackend,
    DesktopBlueprintService,
)
from multi_agent_tcp.codex_bridge import codex_jsonl_event_to_agent_stream_events
from multi_agent_tcp.client import AgentTCPClient


def _document() -> dict:
    return {
        "schema_version": 1,
        "id": "default",
        "name": "Default Blueprint",
        "graph": {
            "terminal_nodes": {"start": "start", "end": "end"},
            "agent_nodes": {
                "planner": {
                    "node_id": "planner",
                    "agent_id": "agent-planner",
                    "prompt": "Plan.",
                }
            },
            "route_nodes": {},
            "edges": [
                {"from": "start", "to": "planner", "edge_type": "exec"},
                {"from": "planner", "to": "end", "edge_type": "exec"},
            ],
        },
        "ui": {
            "nodes": {"planner": {"x": 120, "y": 96}},
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    }


def _plan() -> dict:
    return {
        "user_goal": "Ship the plan.",
        "agent_descriptions": {
            "planner": "Plans the work.",
        },
        "start_nodes": ["planner"],
        "tasks": {
            "planner": {
                "goal": "Plan the work.",
                "expected_output": "A clear implementation plan.",
                "acceptance": "The plan is actionable.",
            },
        },
        "run_policy": {},
    }


def test_blueprint_service_save_open_list_and_validate(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()

    saved = service.save_blueprint(project, _document())

    assert (project / ".multi_agent_workspace" / "blueprints" / "default.json").is_file()
    assert saved["id"] == "default"
    assert service.open_blueprint(project, "default")["graph"]["agent_nodes"]["planner"]["prompt"] == "Plan."

    listed = service.list_blueprints(project)
    assert listed == [
        {
            "id": "default",
            "name": "Default Blueprint",
            "path": str(project / ".multi_agent_workspace" / "blueprints" / "default.json"),
            "updated_at": listed[0]["updated_at"],
        }
    ]

    assert service.validate_blueprint(saved) == {"ok": True, "errors": [], "warnings": []}


def test_blueprint_service_rejects_invalid_id_and_invalid_graph(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()

    bad_id = _document()
    bad_id["id"] = "../escape"
    try:
        service.save_blueprint(project, bad_id)
    except Exception as exc:
        assert "blueprint id must match" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("invalid blueprint id should fail")

    bad_graph = _document()
    bad_graph["graph"] = {
        "terminal_nodes": {"start": "start", "end": "end"},
        "agent_nodes": {},
        "route_nodes": {},
        "edges": [],
    }
    validation = service.validate_blueprint(bad_graph)
    assert validation["ok"] is False
    assert "directed path" in validation["errors"][0]


def test_blueprint_http_server_round_trip(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    server = DesktopBlueprintHTTPServer(token="secret")
    server.start()
    try:
        saved = _post(
            server.url,
            "secret",
            "blueprint.save",
            {"projectDir": str(project), "document": _document()},
        )
        assert saved["ok"] is True

        opened = _post(
            server.url,
            "secret",
            "blueprint.open",
            {"projectDir": str(project), "blueprintId": "default"},
        )
        assert opened["document"]["id"] == "default"
    finally:
        server.close()


def test_blueprint_service_starts_tracks_events_and_ends_run(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()
    service.save_blueprint(project, _document())

    started = service.handle_request(
        {
            "command": "blueprint.start",
            "args": {
                "projectDir": str(project),
                "blueprintId": "default",
                "plan": _plan(),
            },
        }
    )

    assert started["ok"] is True
    assert started["runId"].startswith("run-")
    assert started["run"]["projectDir"] == str(project.resolve())
    assert started["run"]["blueprintId"] == "default"
    assert started["run"]["executionMode"] == "status"
    assert started["validation"]["ok"] is True
    assert started["queuedMessages"][0]["node_id"] == "planner"
    assert started["status"]["run"]["status"] == "running"
    assert started["status"]["queues"]["by_agent"]["planner"][0]["status"] == "queued"
    run = service._runs[started["runId"]]
    assert isinstance(run.runtime.cluster, DesktopBlueprintNoopBackend)
    assert sorted(run.runtime.cluster.worker_configs) == ["agent-planner"]

    status = service.handle_request(
        {"command": "blueprint.status", "args": {"runId": started["runId"]}}
    )
    assert status["status"]["run"]["status"] == "running"
    assert status["status"]["organization"]["agents"]["planner"]["agent_id"] == "agent-planner"
    assert status["explanation"]["pending"]["queued_messages"] == 1

    runs = service.handle_request(
        {
            "command": "blueprint.listRuns",
            "args": {"projectDir": str(project), "blueprintId": "default"},
        }
    )
    assert runs["ok"] is True
    assert runs["runs"][0]["runId"] == started["runId"]
    assert runs["runs"][0]["status"] == "running"

    events = service.handle_request(
        {
            "command": "blueprint.recentEvents",
            "args": {"runId": started["runId"], "limit": 1},
        }
    )
    assert events["ok"] is True
    assert events["limit"] == 1
    assert len(events["events"]) == 1

    ended = service.handle_request(
        {
            "command": "blueprint.end",
            "args": {
                "runId": started["runId"],
                "action": "cancel",
                "reason": "user cancelled",
            },
        }
    )
    assert ended["end"]["run_status"] == "cancelled"
    assert ended["status"]["run"]["final_status"] == "cancelled"

    repeated = service.handle_request(
        {
            "command": "blueprint.end",
            "args": {
                "runId": started["runId"],
                "action": "cancel",
                "reason": "again",
            },
        }
    )
    assert repeated["alreadyEnded"] is True
    assert repeated["status"]["run"]["status"] == "cancelled"

    terminal_status = service.handle_request(
        {"command": "blueprint.status", "args": {"runId": started["runId"]}}
    )
    assert terminal_status["status"]["run"]["status"] == "cancelled"
    assert terminal_status["explanation"]["pending"]["queued_messages"] == 0


def test_blueprint_service_agent_info_projects_message_audit_for_node(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()
    service.save_blueprint(project, _document())
    started = service.handle_request(
        {
            "command": "blueprint.start",
            "args": {"projectDir": str(project), "blueprintId": "default", "plan": _plan()},
        }
    )
    run = service._runs[started["runId"]]
    run.runtime._record_message_io(
        record_type="agent.outgoing.staged",
        sender={"type": "agent", "agent_id": "agent-planner", "node_id": "planner"},
        receiver={"type": "framework"},
        payload={"prompt": "handoff to reviewer"},
        batch_id="out-1",
        status="staged",
        metadata={"target_node_id": "reviewer", "target_agent_id": "agent-reviewer"},
    )

    info = service.handle_request(
        {"command": "blueprint.agentInfo", "args": {"runId": started["runId"], "nodeId": "planner"}}
    )

    assert info["messageJournal"][-1] == {
        "id": info["messageJournal"][-1]["id"],
        "recordType": "agent.outgoing.staged",
        "time": info["messageJournal"][-1]["time"],
        "from": "planner",
        "to": "framework",
        "status": "staged",
        "summary": "handoff to reviewer",
        "batchId": "out-1",
        "targetNodeId": "reviewer",
        "targetAgentId": "agent-reviewer",
    }
    assert info["frameworkApiCalls"][-1]["api"] == "agent.dispatch"
    assert info["frameworkApiCalls"][-1]["summary"] == "handoff to reviewer"
    assert info["frameworkApiCalls"][-1]["batchId"] == "out-1"


def test_blueprint_service_start_rejects_invalid_graph_and_plan(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()

    bad_graph = _document()
    bad_graph["graph"] = {
        "terminal_nodes": {"start": "start", "end": "end"},
        "agent_nodes": {},
        "route_nodes": {},
        "edges": [],
    }
    service.save_blueprint(project, bad_graph)
    try:
        service.handle_request(
            {
                "command": "blueprint.start",
                "args": {
                    "projectDir": str(project),
                    "blueprintId": "default",
                    "plan": _plan(),
                },
            }
        )
    except BlueprintServiceError as exc:
        assert exc.code == "INVALID_BLUEPRINT_GRAPH"
    else:  # pragma: no cover
        raise AssertionError("invalid graph should fail start")

    service.save_blueprint(project, _document())
    try:
        service.handle_request(
            {
                "command": "blueprint.start",
                "args": {
                    "projectDir": str(project),
                    "blueprintId": "default",
                },
            }
        )
    except BlueprintServiceError as exc:
        assert exc.code == "BAD_START_PLAN"
    else:  # pragma: no cover
        raise AssertionError("missing start plan should fail")

    invalid_plan = _plan()
    invalid_plan["tasks"] = {}
    try:
        service.handle_request(
            {
                "command": "blueprint.start",
                "args": {
                    "projectDir": str(project),
                    "blueprintId": "default",
                    "plan": invalid_plan,
                },
            }
        )
    except BlueprintServiceError as exc:
        assert exc.code == "START_PLAN_INVALID"
        assert "validation" in exc.details
    else:  # pragma: no cover
        raise AssertionError("invalid start plan should fail")


def test_blueprint_service_rejects_unknown_run_and_bad_end_action(tmp_path: Path) -> None:
    service = DesktopBlueprintService()
    try:
        service.handle_request({"command": "blueprint.status", "args": {"runId": "run-missing"}})
    except BlueprintServiceError as exc:
        assert exc.code == "RUN_NOT_FOUND"
        assert exc.status == 404
    else:  # pragma: no cover
        raise AssertionError("unknown run should fail")

    project = tmp_path / "project"
    project.mkdir()
    service.save_blueprint(project, _document())
    started = service.handle_request(
        {
            "command": "blueprint.start",
            "args": {"projectDir": str(project), "blueprintId": "default", "plan": _plan()},
        }
    )
    try:
        service.handle_request(
            {
                "command": "blueprint.end",
                "args": {"runId": started["runId"], "action": "archive_only"},
            }
        )
    except BlueprintServiceError as exc:
        assert exc.code == "UNSUPPORTED_RUN_ACTION"
    else:  # pragma: no cover
        raise AssertionError("unsupported end action should fail")

    try:
        service.handle_request(
            {
                "command": "blueprint.start",
                "args": {
                    "projectDir": str(project),
                    "blueprintId": "default",
                    "plan": _plan(),
                    "executionMode": "preview",
                },
            }
        )
    except BlueprintServiceError as exc:
        assert exc.code == "UNSUPPORTED_EXECUTION_MODE"
    else:  # pragma: no cover
        raise AssertionError("unsupported execution mode should fail")


def test_blueprint_service_live_mode_starts_tick_and_streams_agent_events(tmp_path: Path, monkeypatch) -> None:
    class FakeLiveBackend:
        instances = []

        def __init__(self, workers) -> None:
            self.workers = workers
            self.worker_configs = {}
            self.stopped = False
            FakeLiveBackend.instances.append(self)

        @classmethod
        async def create(cls, workers, *, port=9140, verbose=False, allow_empty=False):
            return cls(workers)

        async def ensure_worker(self, worker) -> None:
            self.worker_configs[str(worker.agent_id)] = worker

        async def run_single(self, worker_id, body, *, timeout_sec=600.0, _skip_skill_inject=False, meta=None, stream_callback=None):
            if stream_callback is not None:
                result = stream_callback(
                    {
                        **dict((meta or {}).get("framework_stream") or {}),
                        "kind": "part.delta",
                        "part_id": "fake",
                        "part_type": "text",
                        "field": "text",
                        "delta": "streamed",
                        "text": "streamed",
                    }
                )
                if inspect.isawaitable(result):
                    await result
            return {"type": "message", "body": {"ok": True, "text": "done"}}

        async def stop(self) -> None:
            self.stopped = True

    monkeypatch.setattr("multi_agent_tcp.desktop_blueprint_service.CLIWorkerBackend", FakeLiveBackend)
    service = DesktopBlueprintService()
    project = tmp_path / "project"
    project.mkdir()
    service.save_blueprint(project, _document())

    started = service.handle_request(
        {
            "command": "blueprint.start",
            "args": {
                "projectDir": str(project),
                "blueprintId": "default",
                "plan": _plan(),
                "executionMode": "live",
            },
        }
    )
    assert started["run"]["executionMode"] == "live"
    service._async_loop.run(asyncio.sleep(0.2))

    info = service.handle_request(
        {"command": "blueprint.agentInfo", "args": {"runId": started["runId"], "nodeId": "planner"}}
    )
    assert info["runtime"]["state"] in {"idle", "queued", "waiting_for_reply", "processing_reply"}
    assert any(event.get("kind") == "part.delta" for event in info["streamEvents"])

    queued = service.handle_request(
        {
            "command": "blueprint.queueAgentMessage",
            "args": {"runId": started["runId"], "nodeId": "planner", "text": "urgent", "mode": "top"},
        }
    )
    assert queued["result"]["queue_mode"] == "top"

    ended = service.handle_request(
        {"command": "blueprint.end", "args": {"runId": started["runId"], "action": "cancel"}}
    )
    assert ended["status"]["run"]["final_status"] == "cancelled"
    assert FakeLiveBackend.instances[-1].stopped is True
    service.close()


def test_codex_jsonl_event_to_agent_stream_events_maps_public_parts() -> None:
    events = codex_jsonl_event_to_agent_stream_events(
        {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "hello"}},
        stream_context={"run_id": "run-1", "node_id": "planner", "agent_id": "agent-planner", "message_id": "msg-1"},
    )

    assert events == [
        {
            "kind": "part.delta",
            "run_id": "run-1",
            "node_id": "planner",
            "agent_id": "agent-planner",
            "message_id": "msg-1",
            "raw": {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "hello"}},
            "part_id": "item_1",
            "part_type": "text",
            "field": "text",
            "delta": "hello",
            "text": "hello",
            "status": "completed",
        }
    ]


def test_agent_tcp_client_stream_messages_do_not_satisfy_final_reply() -> None:
    async def scenario() -> None:
        client = AgentTCPClient("orchestrator", "127.0.0.1", 0)
        events = []
        await client._recv_queue.put(
            {
                "type": "message",
                "from": "agent-planner",
                "body": {"type": "agent.stream", "event": {"kind": "part.delta", "delta": "hello"}},
            }
        )
        await client._recv_queue.put(
            {
                "type": "message",
                "from": "agent-planner",
                "body": {"ok": True, "text": "final"},
            }
        )

        async def stream_callback(event: dict) -> None:
            events.append(event)

        reply = await client.wait_for_message(
            expect_from="agent-planner",
            timeout_sec=1,
            stream_callback=stream_callback,
        )
        assert reply["body"]["text"] == "final"
        assert events == [{"kind": "part.delta", "delta": "hello"}]

    asyncio.run(scenario())


def test_blueprint_http_server_returns_error_details(tmp_path: Path) -> None:
    server = DesktopBlueprintHTTPServer(token="secret")
    server.start()
    try:
        response = _post(
            server.url,
            "secret",
            "blueprint.status",
            {"runId": "run-missing"},
            expect_error=True,
        )
        assert response["ok"] is False
        assert response["code"] == "RUN_NOT_FOUND"
    finally:
        server.close()


def _post(url: str, token: str, command: str, args: dict, *, expect_error: bool = False) -> dict:
    body = json.dumps({"token": token, "command": command, "args": args}).encode("utf-8")
    req = request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=5) as response:  # noqa: S310 - local test server
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        if not expect_error:
            raise
        payload = getattr(exc, "read", lambda: b"")()
        return json.loads(payload.decode("utf-8"))
