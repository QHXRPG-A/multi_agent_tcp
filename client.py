from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, Tuple

from .protocol import read_frame, write_frame

log = logging.getLogger(__name__)


class AgentTCPClient:
    """One process: one connection to broker, register, then send/receive."""

    def __init__(self, agent_id: str, host: str, port: int, role: Optional[str] = None) -> None:
        self.agent_id = agent_id.strip()
        self.host = host
        self.port = int(port)
        self.role = role
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._inbox: List[Dict[str, Any]] = []
        self._inbox_changed = asyncio.Condition()
        self._read_closed = False
        self._reader_task: Optional[asyncio.Task] = None
        self._gather_futures: Dict[str, asyncio.Future[Dict[str, Any]]] = {}

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        await write_frame(
            self._writer,
            {"type": "register", "agent_id": self.agent_id, "role": self.role},
        )
        ack = await read_frame(self._reader)
        if ack.get("type") == "error":
            raise RuntimeError(f"register failed: {ack}")
        if ack.get("type") != "registered":
            raise RuntimeError(f"unexpected register ack: {ack}")
        async with self._inbox_changed:
            self._read_closed = False
            self._inbox_changed.notify_all()

        async def pump() -> None:
            assert self._reader is not None
            try:
                while True:
                    msg = await read_frame(self._reader)
                    mtype = msg.get("type")
                    if mtype == "ping":
                        if self._writer and not self._writer.is_closing():
                            try:
                                await write_frame(self._writer, {"type": "pong"})
                            except (ConnectionError, OSError):
                                pass
                        continue
                    if mtype == "gather_result":
                        gid = msg.get("id")
                        if isinstance(gid, str):
                            fut = self._gather_futures.get(gid)
                            if fut is not None and not fut.done():
                                fut.set_result(msg)
                                continue
                    await self._enqueue_received(msg)
            except (asyncio.IncompleteReadError, EOFError, ConnectionError, OSError) as e:
                log.debug("recv pump end: %s", e)
            finally:
                for fut in self._gather_futures.values():
                    if not fut.done():
                        fut.set_exception(ConnectionError("connection closed during batch_gather"))
                self._gather_futures.clear()
                async with self._inbox_changed:
                    self._read_closed = True
                    self._inbox_changed.notify_all()

        self._reader_task = asyncio.create_task(pump())

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except (ConnectionError, OSError):
                pass
            self._writer = None
        self._reader = None
        async with self._inbox_changed:
            self._read_closed = True
            self._inbox_changed.notify_all()

    async def send_to(
        self,
        to_agent_id: str,
        body: Any,
        *,
        gather_reply: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._writer:
            raise RuntimeError("not connected")
        payload: Dict[str, Any] = {"type": "send", "to": to_agent_id.strip(), "body": body}
        if gather_reply is not None and str(gather_reply).strip():
            payload["gather_reply"] = str(gather_reply).strip()
        if meta:
            payload["meta"] = dict(meta)
        await write_frame(self._writer, payload)

    async def broadcast(self, body: Any, exclude_self: bool = True) -> None:
        if not self._writer:
            raise RuntimeError("not connected")
        payload: Dict[str, Any] = {"type": "broadcast", "body": body}
        if exclude_self:
            payload["exclude"] = [self.agent_id]
        await write_frame(self._writer, payload)

    async def ping(self) -> None:
        if not self._writer:
            raise RuntimeError("not connected")
        await write_frame(self._writer, {"type": "ping"})

    async def batch_gather(
        self,
        gather_id: str,
        items: List[Tuple[str, Any]],
        *,
        timeout_sec: float = 300.0,
    ) -> Dict[str, Any]:
        """Send ``batch_gather`` to broker; block until matching ``gather_result`` or timeout."""
        if not self._writer:
            raise RuntimeError("not connected")
        gid = str(gather_id).strip()
        if not gid:
            raise ValueError("gather_id must be non-empty")
        if not items:
            raise ValueError("items must be non-empty")
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Dict[str, Any]] = loop.create_future()
        self._gather_futures[gid] = fut
        try:
            targets = [to.strip() for to, _ in items]
            log.info(
                "[orch] batch_gather SEND id=%s self=%s targets=%s broker_timeout_sec=%s",
                gid,
                self.agent_id,
                targets,
                float(timeout_sec),
            )
            await write_frame(
                self._writer,
                {
                    "type": "batch_gather",
                    "id": gid,
                    "timeout_sec": float(timeout_sec),
                    "items": [{"to": to.strip(), "body": body} for to, body in items],
                },
            )
            out = await asyncio.wait_for(fut, timeout=float(timeout_sec) + 30.0)
            log.info(
                "[orch] batch_gather RESULT id=%s ok=%s reply_agents=%s code=%s",
                gid,
                out.get("ok"),
                list((out.get("replies") or {}).keys()),
                out.get("code"),
            )
            return out
        except asyncio.TimeoutError:
            log.warning(
                "[orch] batch_gather NO_RESULT id=%s (broker did not deliver gather_result in time)",
                gid,
            )
            raise TimeoutError(f"batch_gather {gid!r}: no gather_result from broker") from None
        finally:
            self._gather_futures.pop(gid, None)

    async def wait_for_message(
        self,
        *,
        expect_from: Optional[str] = None,
        timeout_sec: float = 300.0,
        accept_broadcast: bool = False,
        stream_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Block until one ``message`` (or optional ``broadcast``) arrives; optional filter by ``from``."""

        async def _one() -> Dict[str, Any]:
            while True:
                msg = await self._pop_wait_message(
                    expect_from=expect_from,
                    accept_broadcast=accept_broadcast,
                )
                t = msg.get("type")
                if t == "error":
                    return msg
                if t in ("ping", "pong"):
                    continue
                if t == "gather_result":
                    continue
                if t == "message":
                    if expect_from is None or msg.get("from") == expect_from:
                        body = msg.get("body")
                        if isinstance(body, dict) and body.get("type") == "agent.stream":
                            event = body.get("event")
                            if stream_callback is not None and isinstance(event, dict):
                                result = stream_callback(event)
                                if asyncio.iscoroutine(result):
                                    await result
                            continue
                        return msg
                if accept_broadcast and t == "broadcast":
                    if expect_from is None or msg.get("from") == expect_from:
                        return msg

        return await asyncio.wait_for(_one(), timeout=timeout_sec)

    async def incoming(self) -> AsyncIterator[Dict[str, Any]]:
        while True:
            msg = await self._pop_incoming_message()
            if msg is None:
                break
            yield msg

    async def _enqueue_received(self, msg: Dict[str, Any]) -> None:
        async with self._inbox_changed:
            self._inbox.append(msg)
            self._inbox_changed.notify_all()

    async def _pop_incoming_message(self) -> Optional[Dict[str, Any]]:
        async with self._inbox_changed:
            while not self._inbox:
                if self._read_closed:
                    return None
                await self._inbox_changed.wait()
            return self._inbox.pop(0)

    async def _pop_wait_message(
        self,
        *,
        expect_from: Optional[str],
        accept_broadcast: bool,
    ) -> Dict[str, Any]:
        async with self._inbox_changed:
            while True:
                idx = self._find_wait_message_index(
                    expect_from=expect_from,
                    accept_broadcast=accept_broadcast,
                )
                if idx is not None:
                    return self._inbox.pop(idx)
                if self._read_closed:
                    raise ConnectionError("connection closed while waiting for message")
                await self._inbox_changed.wait()

    def _find_wait_message_index(
        self,
        *,
        expect_from: Optional[str],
        accept_broadcast: bool,
    ) -> Optional[int]:
        for idx, msg in enumerate(self._inbox):
            t = msg.get("type")
            if t in ("error", "ping", "pong", "gather_result"):
                return idx
            if t == "message" and (expect_from is None or msg.get("from") == expect_from):
                return idx
            if (
                accept_broadcast
                and t == "broadcast"
                and (expect_from is None or msg.get("from") == expect_from)
            ):
                return idx
        return None
