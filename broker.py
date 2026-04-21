from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .protocol import read_frame, write_frame

log = logging.getLogger(__name__)


@dataclass
class GatherState:
    gather_id: str
    initiator_id: str
    initiator_writer: asyncio.StreamWriter
    expected: Set[str]
    replies: Dict[str, Any] = field(default_factory=dict)
    done_event: asyncio.Event = field(default_factory=asyncio.Event)


class Broker:
    """TCP hub: agents register with agent_id; broker routes *send* / *broadcast* / *batch_gather*."""

    HEARTBEAT_INTERVAL_SEC = 30.0

    HEARTBEAT_STALE_FACTOR = 2.5

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = int(port)
        self._agents: Dict[str, asyncio.StreamWriter] = {}
        self._last_seen: Dict[str, float] = {}
        self._gathers: Dict[str, GatherState] = {}
        self._lock = asyncio.Lock()
        self._write_locks: Dict[asyncio.StreamWriter, asyncio.Lock] = {}
        self._server: Optional[asyncio.AbstractServer] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

    def _get_write_lock(self, writer: asyncio.StreamWriter) -> asyncio.Lock:
        lock = self._write_locks.get(writer)
        if lock is None:
            lock = asyncio.Lock()
            self._write_locks[writer] = lock
        return lock

    @staticmethod
    def _on_gather_task_done(task: asyncio.Task) -> None:  # type: ignore[type-arg]
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            log.error("gather task %s failed: %s", task.get_name(), exc)

    async def _safe_write_frame(self, writer: asyncio.StreamWriter, payload: Dict[str, Any]) -> None:
        """Write a frame with per-connection locking (safe for concurrent tasks)."""
        async with self._get_write_lock(writer):
            await write_frame(writer, payload)

    async def _write_gather_result(
        self,
        writer: asyncio.StreamWriter,
        *,
        gather_id: str,
        ok: bool,
        replies: Dict[str, Any],
        errors: Dict[str, Any],
        code: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        replies_out = {aid: {"body": body} for aid, body in replies.items()}
        payload: Dict[str, Any] = {
            "type": "gather_result",
            "id": gather_id,
            "ok": ok,
            "replies": replies_out,
            "errors": errors,
        }
        if code is not None:
            payload["code"] = code
        if message is not None:
            payload["message"] = message
        try:
            await self._safe_write_frame(writer, payload)
        except (ConnectionError, OSError) as e:
            log.warning("gather_result write failed id=%s: %s", gather_id, e)

    async def _pop_gather(self, gather_id: str) -> Optional[GatherState]:
        async with self._lock:
            return self._gathers.pop(gather_id, None)

    async def _fail_gather_with_state(
        self,
        st: GatherState,
        *,
        ok: bool,
        errors: Dict[str, Any],
        code: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        if st.initiator_writer.is_closing():
            return
        await self._write_gather_result(
            st.initiator_writer,
            gather_id=st.gather_id,
            ok=ok,
            replies=dict(st.replies),
            errors=errors,
            code=code,
            message=message,
        )

    async def _complete_gather_success(self, gather_id: str) -> None:
        st = await self._pop_gather(gather_id)
        if st is None:
            return
        log.info(
            "[gather] batch_gather COMPLETE id=%s replies_from=%s",
            gather_id,
            sorted(st.replies.keys()),
        )
        await self._fail_gather_with_state(st, ok=True, errors={})

    async def _fail_gather_by_id(
        self,
        gather_id: str,
        *,
        errors: Dict[str, Any],
        code: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        st = await self._pop_gather(gather_id)
        if st is None:
            return
        await self._fail_gather_with_state(
            st, ok=False, errors=errors, code=code, message=message
        )

    async def _on_gather_reply(
        self,
        from_agent: str,
        to_agent: str,
        gather_reply: str,
        body: Any,
    ) -> None:
        accepted = False
        progress: Optional[Tuple[int, int]] = None
        reason = ""
        async with self._lock:
            st = self._gathers.get(gather_reply)
            if st is None:
                reason = "no_such_gather"
            elif to_agent != st.initiator_id:
                reason = f"wrong_reply_to want={st.initiator_id!r} got={to_agent!r}"
            elif from_agent not in st.expected:
                reason = f"from_not_in_expected expected={sorted(st.expected)}"
            elif from_agent in st.replies:
                reason = "duplicate_reply"
            else:
                st.replies[from_agent] = body
                progress = (len(st.replies), len(st.expected))
                if len(st.replies) >= len(st.expected):
                    st.done_event.set()
                accepted = True
        if not accepted:
            log.warning(
                "[gather] gather_reply NOT_RECORDED id=%s from=%s to=%s reason=%s",
                gather_reply,
                from_agent,
                to_agent,
                reason,
            )
            return
        assert progress is not None
        log.info(
            "[gather] gather_reply RECORDED id=%s from=%s progress=%s/%s",
            gather_reply,
            from_agent,
            progress[0],
            progress[1],
        )

    async def _run_batch_gather(
        self,
        initiator_id: str,
        initiator_writer: asyncio.StreamWriter,
        msg: Dict[str, Any],
    ) -> None:
        gid_raw = msg.get("id")
        try:
            await self._run_batch_gather_inner(initiator_id, initiator_writer, msg)
        except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            log.exception("[gather] _run_batch_gather UNHANDLED id=%s initiator=%s", gid_raw, initiator_id)
            if isinstance(gid_raw, str) and gid_raw.strip():
                await self._pop_gather(gid_raw.strip())

    async def _run_batch_gather_inner(
        self,
        initiator_id: str,
        initiator_writer: asyncio.StreamWriter,
        msg: Dict[str, Any],
    ) -> None:
        gid_raw = msg.get("id")

        async def _reject(
            code: str,
            message: str,
            *,
            use_gather_result: bool,
            gather_id_for_result: Optional[str] = None,
        ) -> None:
            if use_gather_result and gather_id_for_result:
                await self._write_gather_result(
                    initiator_writer,
                    gather_id=gather_id_for_result,
                    ok=False,
                    replies={},
                    errors={},
                    code=code,
                    message=message,
                )
            else:
                await self._safe_write_frame(
                    initiator_writer,
                    {"type": "error", "code": code, "message": message},
                )

        if not isinstance(gid_raw, str) or not gid_raw.strip():
            await _reject(
                "bad_batch_gather",
                "field 'id' must be non-empty str",
                use_gather_result=False,
            )
            return
        gather_id = gid_raw.strip()
        timeout_sec = float(msg.get("timeout_sec", 300.0))
        if timeout_sec <= 0:
            timeout_sec = 300.0
        items = msg.get("items")
        if not isinstance(items, list) or not items:
            await _reject(
                "bad_batch_gather",
                "field 'items' must be a non-empty list",
                use_gather_result=True,
                gather_id_for_result=gather_id,
            )
            return

        parsed: List[Tuple[str, Any]] = []
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                await _reject(
                    "bad_batch_gather",
                    f"items[{i}] must be object",
                    use_gather_result=True,
                    gather_id_for_result=gather_id,
                )
                return
            to = it.get("to")
            if not isinstance(to, str) or not to.strip():
                await _reject(
                    "bad_batch_gather",
                    f"items[{i}].to required",
                    use_gather_result=True,
                    gather_id_for_result=gather_id,
                )
                return
            if "body" not in it:
                await _reject(
                    "bad_batch_gather",
                    f"items[{i}].body required",
                    use_gather_result=True,
                    gather_id_for_result=gather_id,
                )
                return
            parsed.append((to.strip(), it["body"]))

        expected: Set[str] = {t for t, _ in parsed}

        async with self._lock:
            if gather_id in self._gathers:
                await self._write_gather_result(
                    initiator_writer,
                    gather_id=gather_id,
                    ok=False,
                    replies={},
                    errors={},
                    code="duplicate_gather_id",
                    message=f"gather id already in use: {gather_id}",
                )
                return
            offline = [aid for aid in expected if aid not in self._agents or self._agents[aid].is_closing()]
            if offline:
                errs = {
                    aid: {"code": "unknown_target", "message": f"no active agent: {aid}"}
                    for aid in offline
                }
                await self._write_gather_result(
                    initiator_writer,
                    gather_id=gather_id,
                    ok=False,
                    replies={},
                    errors=errs,
                    code="pre_check_failed",
                    message="one or more targets offline; no messages sent",
                )
                return

            st = GatherState(
                gather_id=gather_id,
                initiator_id=initiator_id,
                initiator_writer=initiator_writer,
                expected=set(expected),
            )
            self._gathers[gather_id] = st

        log.info(
            "[gather] batch_gather START id=%s initiator=%s targets=%s timeout_sec=%s items=%s",
            gather_id,
            initiator_id,
            sorted(expected),
            timeout_sec,
            len(parsed),
        )

        for to_agent, body in parsed:
            async with self._lock:
                target = self._agents.get(to_agent)
            if target is None or target.is_closing():
                await self._fail_gather_by_id(
                    gather_id,
                    errors={
                        aid: {"code": "target_disconnected", "message": "target offline during dispatch"}
                        for aid in expected
                    },
                    code="target_disconnected",
                    message=f"target {to_agent} offline during dispatch",
                )
                return
            out: Dict[str, Any] = {
                "type": "message",
                "from": initiator_id,
                "body": body,
                "gather": {"id": gather_id, "reply_to": initiator_id},
            }
            try:
                await self._safe_write_frame(target, out)
                log.info(
                    "[gather] message DISPATCHED id=%s -> to=%s from=%s body_type=%s",
                    gather_id,
                    to_agent,
                    initiator_id,
                    type(body).__name__,
                )
            except (ConnectionError, OSError) as e:
                log.warning("batch_gather forward failed to=%s: %s", to_agent, e)
                await self._fail_gather_by_id(
                    gather_id,
                    errors={to_agent: {"code": "send_failed", "message": str(e)}},
                    code="dispatch_failed",
                    message=str(e),
                )
                return

        async with self._lock:
            st_wait = self._gathers.get(gather_id)
        if st_wait is None:
            return

        async def _wait_writer_closed(w: asyncio.StreamWriter) -> None:
            while not w.is_closing():
                await asyncio.sleep(1.0)

        done_task = asyncio.create_task(st_wait.done_event.wait())
        writer_closed_task = asyncio.create_task(
            _wait_writer_closed(initiator_writer)
        )
        try:
            finished, _pending = await asyncio.wait(
                {done_task, writer_closed_task},
                timeout=timeout_sec,
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            done_task.cancel()
            writer_closed_task.cancel()
            raise
        finally:
            done_task.cancel()
            writer_closed_task.cancel()

        if not finished:
            # timeout — neither done nor writer-closed within deadline
            async with self._lock:
                st_t = self._gathers.get(gather_id)
                if st_t is None:
                    return
                missing = [aid for aid in st_t.expected if aid not in st_t.replies]
                had = sorted(st_t.replies.keys())
            log.warning(
                "[gather] batch_gather TIMEOUT id=%s waited_sec=%s missing=%s had_replies_from=%s "
                "(no gather_reply in time — check [chain]/[cil] on workers)",
                gather_id,
                timeout_sec,
                missing,
                had,
            )
            st_removed = await self._pop_gather(gather_id)
            if st_removed is None:
                return
            errs: Dict[str, Any] = {
                aid: {"code": "timeout", "message": "no reply before deadline"} for aid in missing
            }
            await self._fail_gather_with_state(
                st_removed,
                ok=False,
                errors=errs,
                code="timeout",
                message="batch_gather deadline exceeded",
            )
            return

        if writer_closed_task in finished:
            log.warning(
                "[gather] batch_gather INITIATOR_DISCONNECTED id=%s initiator=%s",
                gather_id,
                initiator_id,
            )
            await self._pop_gather(gather_id)
            return

        async with self._lock:
            st_final = self._gathers.get(gather_id)
        if st_final and len(st_final.replies) >= len(st_final.expected):
            await self._complete_gather_success(gather_id)

    async def _agent_left(self, agent_id: str) -> None:
        """Cancel gathers owned by disconnecting initiator; fail gathers waiting on this target."""
        initiator_gathers: List[str] = []
        target_fail: List[str] = []
        async with self._lock:
            for gid, st in list(self._gathers.items()):
                if st.initiator_id == agent_id:
                    initiator_gathers.append(gid)
                elif agent_id in st.expected and agent_id not in st.replies:
                    target_fail.append(gid)

        for gid in initiator_gathers:
            await self._pop_gather(gid)
            log.info("gather %s dropped (initiator disconnected)", gid)

        for gid in target_fail:
            async with self._lock:
                st = self._gathers.get(gid)
                if st is None:
                    continue
                missing = [aid for aid in st.expected if aid not in st.replies]
            st_removed = await self._pop_gather(gid)
            if st_removed is None:
                continue
            errs: Dict[str, Any] = {
                aid: {"code": "target_disconnected", "message": f"agent {agent_id} disconnected"}
                for aid in missing
            }
            await self._fail_gather_with_state(
                st_removed,
                ok=False,
                errors=errs,
                code="target_disconnected",
                message=f"agent {agent_id} disconnected",
            )

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        agent_id: Optional[str] = None
        try:
            while True:
                msg = await read_frame(reader)
                mtype = msg.get("type")
                if mtype == "register":
                    aid = msg.get("agent_id")
                    if not isinstance(aid, str) or not aid.strip():
                        await self._safe_write_frame(
                            writer,
                            {"type": "error", "code": "bad_register", "message": "agent_id required"},
                        )
                        break
                    aid = aid.strip()
                    async with self._lock:
                        if aid in self._agents:
                            await self._safe_write_frame(
                                writer,
                                {
                                    "type": "error",
                                    "code": "duplicate_id",
                                    "message": f"agent_id already connected: {aid}",
                                },
                            )
                            break
                        self._agents[aid] = writer
                        self._last_seen[aid] = time.monotonic()
                    agent_id = aid
                    role = msg.get("role")
                    await self._safe_write_frame(
                        writer,
                        {"type": "registered", "agent_id": aid, "role": role},
                    )
                    log.info("registered agent_id=%s peer=%s role=%s", aid, peer, role)
                    continue

                if agent_id is None:
                    await self._safe_write_frame(
                        writer,
                        {"type": "error", "code": "not_registered", "message": "send register first"},
                    )
                    break

                self._last_seen[agent_id] = time.monotonic()

                if mtype == "pong":
                    continue

                if mtype == "ping":
                    await self._safe_write_frame(writer, {"type": "pong", "agent_id": agent_id})
                    continue

                if mtype == "batch_gather":
                    task = asyncio.create_task(
                        self._run_batch_gather(agent_id, writer, msg),
                        name=f"gather-{msg.get('id', '?')}",
                    )
                    task.add_done_callback(self._on_gather_task_done)
                    continue

                if mtype == "send":
                    to = msg.get("to")
                    body = msg.get("body")
                    if not isinstance(to, str) or not to.strip():
                        await self._safe_write_frame(
                            writer,
                            {"type": "error", "code": "bad_send", "message": "field 'to' must be non-empty str"},
                        )
                        continue
                    to = to.strip()
                    gr = msg.get("gather_reply")
                    if isinstance(gr, str) and gr.strip():
                        await self._on_gather_reply(agent_id, to, gr.strip(), body)
                        continue
                    async with self._lock:
                        target = self._agents.get(to)
                    if target is None or target.is_closing():
                        await self._safe_write_frame(
                            writer,
                            {
                                "type": "error",
                                "code": "unknown_target",
                                "message": f"no active agent: {to}",
                            },
                        )
                        continue
                    out = {"type": "message", "from": agent_id, "body": body}
                    try:
                        await self._safe_write_frame(target, out)
                    except (ConnectionError, OSError) as e:
                        log.warning("forward failed to=%s: %s", to, e)
                    continue

                if mtype == "broadcast":
                    body = msg.get("body")
                    exclude = msg.get("exclude")
                    exclude_set = set()
                    if isinstance(exclude, list):
                        exclude_set = {str(x) for x in exclude}
                    elif isinstance(exclude, str) and exclude.strip():
                        exclude_set = {exclude.strip()}
                    exclude_set.add(agent_id)
                    async with self._lock:
                        items: List[Tuple[str, asyncio.StreamWriter]] = list(self._agents.items())
                    for aid, w in items:
                        if aid in exclude_set or w.is_closing():
                            continue
                        try:
                            await self._safe_write_frame(
                                w,
                                {"type": "broadcast", "from": agent_id, "body": body},
                            )
                        except (ConnectionError, OSError):
                            pass
                    continue

                await self._safe_write_frame(
                    writer,
                    {"type": "error", "code": "unknown_type", "message": str(mtype)},
                )
        except (asyncio.IncompleteReadError, EOFError, ConnectionError, OSError):
            pass
        finally:
            if agent_id:
                await self._agent_left(agent_id)
                async with self._lock:
                    w = self._agents.get(agent_id)
                    if w is writer:
                        del self._agents[agent_id]
                    self._last_seen.pop(agent_id, None)
                log.info("unregistered agent_id=%s peer=%s", agent_id, peer)
            self._write_locks.pop(writer, None)
            try:
                writer.close()
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def _heartbeat_loop(self) -> None:
        """Ping all agents; evict those that never replied (no frame within stale threshold)."""
        stale_threshold = self.HEARTBEAT_INTERVAL_SEC * self.HEARTBEAT_STALE_FACTOR
        while True:
            await asyncio.sleep(self.HEARTBEAT_INTERVAL_SEC)
            now = time.monotonic()
            stale: List[Tuple[str, asyncio.StreamWriter]] = []
            async with self._lock:
                for aid, w in list(self._agents.items()):
                    if w.is_closing():
                        stale.append((aid, w))
                        continue
                    last = self._last_seen.get(aid, 0.0)
                    if now - last > stale_threshold:
                        log.warning(
                            "[heartbeat] agent_id=%s no frame for %.0fs (threshold %.0fs)",
                            aid, now - last, stale_threshold,
                        )
                        stale.append((aid, w))
                        continue
                    try:
                        await self._safe_write_frame(w, {"type": "ping"})
                    except (ConnectionError, OSError):
                        stale.append((aid, w))
                for aid, _ in stale:
                    if self._agents.get(aid) is _:
                        del self._agents[aid]
                    self._last_seen.pop(aid, None)
            for aid, _ in stale:
                log.info("[heartbeat] evicting stale agent_id=%s", aid)
                await self._agent_left(aid)

    async def start(self) -> None:
        try:
            self._server = await asyncio.start_server(
                self._handle_client,
                host=self.host,
                port=self.port,
            )
        except OSError as e:
            log.error(
                "Port %s already in use (or bind failed): %s  "
                "Kill the old broker or use --port <other>.",
                self.port,
                e,
            )
            raise SystemExit(1) from e
        addrs = ", ".join(str(s.getsockname()) for s in self._server.sockets or ())
        log.info("broker listening %s", addrs)
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        await self._server.serve_forever()

    async def stop(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
