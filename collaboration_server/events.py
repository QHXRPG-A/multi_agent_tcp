from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator

from fastapi import Request

from .observability import log_event
from .projection import event_key, runtime_event_from_raw, runtime_event_from_row, scrub_payload
from .schemas import RuntimeEvent
from .store import CollaborationStore, now_ts


def mirror_runtime_events(
    store: CollaborationStore,
    run: dict[str, Any],
    raw_events: list[dict[str, Any]],
) -> list[RuntimeEvent]:
    mirrored: list[RuntimeEvent] = []
    run_id = str(run["id"])
    for raw in raw_events:
        if not isinstance(raw, dict):
            continue
        projected = runtime_event_from_raw(run_id, raw)
        row = store.append_event(
            run_id,
            event_key=event_key(raw),
            event_type=projected.type,
            occurred_at=_event_time(raw),
            node_id=projected.nodeId,
            agent_id=projected.agentId,
            payload=scrub_payload(raw),
        )
        if row is not None:
            mirrored.append(runtime_event_from_row(row))
    log_event(
        "info",
        "events.replay",
        run_id=run_id,
        raw_count=len(raw_events),
        mirrored_count=len(mirrored),
    )
    return mirrored


def events_after(store: CollaborationStore, run_id: str, cursor: int = 0, *, limit: int = 100) -> list[RuntimeEvent]:
    return [runtime_event_from_row(row) for row in store.events_after(run_id, cursor, limit=limit)]


async def sse_event_stream(
    request: Request,
    *,
    store: CollaborationStore,
    run: dict[str, Any],
    sync_events: Any,
    cursor: int = 0,
    poll_seconds: float = 2.0,
    heartbeat_seconds: float = 15.0,
    request_id: str | None = None,
    user_id: str | None = None,
) -> AsyncIterator[str]:
    last_cursor = int(cursor or 0)
    last_heartbeat = time.monotonic()
    run_id = str(run["id"])
    log_event("info", "events.sse.connect", request_id=request_id, user_id=user_id, path=str(request.url.path), run_id=run_id, cursor=cursor)
    try:
        while True:
            sync_events()
            rows = events_after(store, run_id, last_cursor, limit=100)
            if rows:
                log_event(
                    "info",
                    "events.replay",
                    request_id=request_id,
                    user_id=user_id,
                    path=str(request.url.path),
                    run_id=run_id,
                    cursor=last_cursor,
                    returned_count=len(rows),
                    last_cursor=rows[-1].cursor,
                )
            for event in rows:
                last_cursor = max(last_cursor, int(event.cursor))
                yield format_sse(event)
            if await request.is_disconnected():
                log_event(
                    "info",
                    "events.sse.disconnect",
                    request_id=request_id,
                    user_id=user_id,
                    path=str(request.url.path),
                    run_id=run_id,
                    cursor=last_cursor,
                )
                return
            if time.monotonic() - last_heartbeat >= heartbeat_seconds:
                last_heartbeat = time.monotonic()
                log_event(
                    "debug",
                    "events.sse.heartbeat",
                    request_id=request_id,
                    user_id=user_id,
                    path=str(request.url.path),
                    run_id=run_id,
                    cursor=last_cursor,
                )
                yield ": heartbeat\n\n"
            await asyncio.sleep(poll_seconds)
    except Exception as exc:
        log_event(
            "error",
            "events.sse.error",
            request_id=request_id,
            user_id=user_id,
            path=str(request.url.path),
            run_id=run_id,
            cursor=last_cursor,
            error_type=type(exc).__name__,
            message=str(exc),
        )
        raise


def format_sse(event: RuntimeEvent) -> str:
    data = json.dumps(event.model_dump(exclude_none=True), ensure_ascii=False)
    return f"id: {event.cursor}\nevent: {event.type}\ndata: {data}\n\n"


def _event_time(raw: dict[str, Any]) -> float:
    value = raw.get("timestamp") or raw.get("time") or raw.get("occurredAt") or raw.get("created_at")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return now_ts()
    return now_ts()
