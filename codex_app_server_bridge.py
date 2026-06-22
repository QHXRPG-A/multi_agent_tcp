"""Persistent Codex app-server client for CLI-backed workers."""

from __future__ import annotations

import asyncio
import codecs
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ._proc_utils import async_kill_process_tree, hidden_subprocess_kwargs
from .codex_bridge import _merge_prompt

log = logging.getLogger(__name__)

AgentStreamCallback = Callable[[Dict[str, Any]], Awaitable[None]]
APP_SERVER_STDERR_MAX_CHARS = 64 * 1024
APP_SERVER_PROTOCOL_LOG_MAX_CHARS = 256 * 1024


class CodexAppServerError(RuntimeError):
    """Raised when the app-server transport or request fails."""


def _append_limited(parts: List[str], value: str, *, limit: int) -> None:
    if not value:
        return
    current = sum(len(item) for item in parts)
    if current >= limit:
        return
    remaining = limit - current
    parts.append(value[:remaining])


def _json_rpc_error_message(payload: Dict[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        message = str(error.get("message") or "").strip()
        data = error.get("data")
        if data is not None:
            try:
                suffix = json.dumps(data, ensure_ascii=False, default=str)
            except TypeError:
                suffix = str(data)
            if suffix:
                message = f"{message}: {suffix}" if message else suffix
        return message or str(error)
    return str(error or payload)


def _sandbox_mode_for_thread(raw: Any) -> Optional[str]:
    value = str(raw or "").strip().lower()
    if not value:
        return None
    if value in {"danger-full-access", "danger_full_access", "dangerfullaccess", "full"}:
        return "danger-full-access"
    if value in {"workspace-write", "workspace_write", "workspacewrite", "workspace"}:
        return "workspace-write"
    if value in {"read-only", "read_only", "readonly", "read"}:
        return "read-only"
    return value


def _sandbox_policy_for_turn(raw: Any, cwd: Path) -> Optional[Dict[str, Any]]:
    value = str(raw or "").strip().lower()
    if not value:
        return None
    if value in {"danger-full-access", "danger_full_access", "dangerfullaccess", "full"}:
        return {"type": "dangerFullAccess"}
    if value in {"workspace-write", "workspace_write", "workspacewrite", "workspace"}:
        return {
            "type": "workspaceWrite",
            "writableRoots": [str(cwd)],
            "networkAccess": True,
        }
    if value in {"read-only", "read_only", "readonly", "read"}:
        return {"type": "readOnly", "networkAccess": True}
    return None


def _merge_turn_prompt(
    prompt: str,
    stdin_context: Optional[str],
    codex_cfg: Dict[str, Any],
    *,
    include_runtime_preamble: bool,
) -> str:
    if include_runtime_preamble:
        return _merge_prompt(prompt, stdin_context, codex_cfg)
    parts = [str(prompt or "").strip()]
    if stdin_context:
        parts.append(f"# Upstream Context\n\n{stdin_context}")
    return "\n\n---\n\n".join(part for part in parts if part.strip())


def _attachment_image_input(raw: Any, cwd: Path) -> Optional[Dict[str, Any]]:
    if isinstance(raw, str):
        path_text = raw.strip()
        kind = ""
        mime = ""
        url = ""
    elif isinstance(raw, dict):
        path_text = str(raw.get("path") or raw.get("file") or raw.get("file_path") or "").strip()
        url = str(raw.get("url") or "").strip()
        kind = str(raw.get("kind") or "").strip().lower()
        mime = str(raw.get("mime") or "").strip().lower()
    else:
        return None

    image_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    if url and (kind == "image" or mime.startswith("image/")):
        return {"type": "image", "url": url}

    if not path_text:
        return None
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = cwd / path
    suffix = path.suffix.lower()
    if kind != "image" and not mime.startswith("image/") and suffix not in image_suffixes:
        return None
    return {"type": "localImage", "path": str(path.resolve())}


class CodexAppServerSession:
    """One long-lived ``codex app-server`` process and Codex thread."""

    def __init__(self, codex_cfg: Dict[str, Any]) -> None:
        self.codex_cfg = codex_cfg
        self.thread_id: Optional[str] = None
        self.active_turn_id: Optional[str] = None
        self.messages_handled = 0
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task[None]] = None
        self._stderr_task: Optional[asyncio.Task[None]] = None
        self._request_id = 0
        self._pending: Dict[int, asyncio.Future[Dict[str, Any]]] = {}
        self._turn_events: Dict[str, asyncio.Event] = {}
        self._completed_turns: Dict[str, Dict[str, Any]] = {}
        self._turn_text: Dict[str, str] = {}
        self._turn_status: Dict[str, str] = {}
        self._turn_error: Dict[str, str] = {}
        self._active_stream_callback: Optional[AgentStreamCallback] = None
        self._active_stream_context: Dict[str, Any] = {}
        self._stderr_parts: List[str] = []
        self._protocol_log: List[str] = []
        self._started_at = 0.0

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self) -> None:
        if self.running:
            return
        cwd: Path = self.codex_cfg["cwd"]
        if not cwd.is_dir():
            raise FileNotFoundError(f"codex.cwd is not a directory: {cwd}")
        exe = str(self.codex_cfg["command"])
        if not Path(exe).is_file() and not shutil.which(exe):
            raise FileNotFoundError(f"codex command not found on PATH: {exe}")

        cmd = [exe, "app-server", "--listen", "stdio://"]
        for override in self.codex_cfg.get("config_overrides", []) or []:
            cmd.extend(["--config", str(override)])
        for feature in self.codex_cfg.get("enable_features", []) or []:
            cmd.extend(["--enable", str(feature)])
        for feature in self.codex_cfg.get("disable_features", []) or []:
            cmd.extend(["--disable", str(feature)])

        child_env = {**os.environ, "PYTHONUTF8": "1"}
        extra_env = self.codex_cfg.get("extra_env")
        if isinstance(extra_env, dict):
            child_env.update({str(k): str(v) for k, v in extra_env.items()})
        codex_home = self.codex_cfg.get("codex_home")
        if codex_home:
            home = Path(str(codex_home)).expanduser().resolve()
            home.mkdir(parents=True, exist_ok=True)
            child_env["CODEX_HOME"] = str(home)

        log.info("[codex-app-server] spawn cwd=%s cmd=%s", cwd, cmd)
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=child_env,
            **hidden_subprocess_kwargs(),
        )
        self._started_at = time.monotonic()
        self._reader_task = asyncio.create_task(self._read_stdout_loop(), name="codex-app-server-stdout")
        self._stderr_task = asyncio.create_task(self._read_stderr_loop(), name="codex-app-server-stderr")
        await self._initialize()

    async def _initialize(self) -> None:
        response = await self._request(
            "initialize",
            {
                "clientInfo": {
                    "name": "gulicode_blueprint_popo_agent",
                    "title": "GuLiCode Blueprint POPO Agent",
                    "version": "0.1.0",
                },
                "capabilities": {"experimentalApi": True},
            },
            timeout=30.0,
        )
        if not isinstance(response, dict):
            raise CodexAppServerError("initialize returned a non-object response")
        await self._notify("initialized", {})

    async def ensure_thread(self) -> str:
        if self.thread_id:
            return self.thread_id
        await self.start()
        cwd: Path = self.codex_cfg["cwd"]
        params: Dict[str, Any] = {
            "cwd": str(cwd),
            "ephemeral": bool(self.codex_cfg.get("ephemeral", True)),
            "serviceName": "gulicode_blueprint",
            "approvalPolicy": "never",
        }
        model = self.codex_cfg.get("model")
        if isinstance(model, str) and model.strip():
            params["model"] = model.strip()
        sandbox = _sandbox_mode_for_thread(self.codex_cfg.get("sandbox"))
        if sandbox:
            params["sandbox"] = sandbox
        response = await self._request("thread/start", params, timeout=60.0)
        thread = response.get("thread") if isinstance(response, dict) else None
        thread_id = str(thread.get("id") or "").strip() if isinstance(thread, dict) else ""
        if not thread_id:
            raise CodexAppServerError(f"thread/start returned no thread id: {response!r}")
        self.thread_id = thread_id
        return thread_id

    async def start_turn(
        self,
        *,
        prompt: str,
        context: Optional[str],
        attachments: List[Any],
        stream_callback: Optional[AgentStreamCallback],
        stream_context: Optional[Dict[str, Any]],
        client_user_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        thread_id = await self.ensure_thread()
        first_turn = self.messages_handled == 0
        text = _merge_turn_prompt(
            prompt,
            context,
            self.codex_cfg,
            include_runtime_preamble=first_turn,
        )
        inputs = self._user_inputs(text, attachments)
        params: Dict[str, Any] = {
            "threadId": thread_id,
            "input": inputs,
        }
        if client_user_message_id:
            params["clientUserMessageId"] = client_user_message_id
        model = self.codex_cfg.get("model")
        if isinstance(model, str) and model.strip():
            params["model"] = model.strip()
        cwd: Path = self.codex_cfg["cwd"]
        params["cwd"] = str(cwd)
        params["approvalPolicy"] = "never"
        sandbox_policy = _sandbox_policy_for_turn(self.codex_cfg.get("sandbox"), cwd)
        if sandbox_policy is not None:
            params["sandboxPolicy"] = sandbox_policy

        self._active_stream_callback = stream_callback
        self._active_stream_context = dict(stream_context or {})
        response = await self._request("turn/start", params, timeout=60.0)
        turn = response.get("turn") if isinstance(response, dict) else None
        turn_id = str(turn.get("id") or "").strip() if isinstance(turn, dict) else ""
        if not turn_id:
            self._active_stream_callback = None
            self._active_stream_context = {}
            raise CodexAppServerError(f"turn/start returned no turn id: {response!r}")
        self.active_turn_id = turn_id
        self._turn_events.setdefault(turn_id, asyncio.Event())
        timeout = self.codex_cfg.get("timeout_sec")
        try:
            if turn_id not in self._completed_turns:
                waiter = self._turn_events[turn_id].wait()
                await (asyncio.wait_for(waiter, timeout=timeout) if timeout else waiter)
        except asyncio.TimeoutError:
            self._turn_status[turn_id] = "timeout"
            self._turn_error[turn_id] = f"turn timed out after {timeout}s"
            await self.close()
            return self._turn_result(turn_id, timeout=True)
        finally:
            if self.active_turn_id == turn_id:
                self.active_turn_id = None
            self._active_stream_callback = None
            self._active_stream_context = {}
        self.messages_handled += 1
        return self._turn_result(turn_id)

    async def steer_turn(
        self,
        *,
        prompt: str,
        context: Optional[str],
        attachments: List[Any],
        client_user_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.thread_id:
            return {"ok": False, "status": "not_started", "error": "no active Codex thread"}
        if not self.active_turn_id:
            return {"ok": False, "status": "not_running", "error": "no active Codex turn"}
        text = _merge_turn_prompt(
            prompt,
            context,
            self.codex_cfg,
            include_runtime_preamble=False,
        )
        params: Dict[str, Any] = {
            "threadId": self.thread_id,
            "expectedTurnId": self.active_turn_id,
            "input": self._user_inputs(text, attachments),
        }
        if client_user_message_id:
            params["clientUserMessageId"] = client_user_message_id
        try:
            response = await self._request("turn/steer", params, timeout=15.0)
        except CodexAppServerError as exc:
            return {
                "ok": False,
                "status": "rejected",
                "error": str(exc),
                "thread_id": self.thread_id,
                "turn_id": self.active_turn_id,
            }
        accepted_turn_id = str(response.get("turnId") or response.get("turn_id") or "").strip()
        ok = bool(accepted_turn_id and accepted_turn_id == self.active_turn_id)
        return {
            "ok": ok,
            "status": "steered" if ok else "rejected",
            "thread_id": self.thread_id,
            "turn_id": accepted_turn_id or self.active_turn_id,
            "response": response,
            "error": "" if ok else "turn/steer did not accept the active turn",
        }

    async def close(self) -> None:
        proc = self._proc
        self._proc = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(CodexAppServerError("app-server closed"))
        self._pending.clear()
        tasks = [task for task in (self._reader_task, self._stderr_task) if task is not None]
        for task in tasks:
            if task and not task.done():
                task.cancel()
        self._reader_task = None
        self._stderr_task = None
        if proc is None:
            return
        if proc.stdin is not None:
            try:
                proc.stdin.close()
                await proc.stdin.wait_closed()
            except (AttributeError, BrokenPipeError, ConnectionError, OSError):
                pass
        if proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError, OSError):
                if proc.pid:
                    await async_kill_process_tree(proc.pid, timeout=10.0)
        else:
            try:
                await asyncio.wait_for(proc.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _user_inputs(self, text: str, attachments: List[Any]) -> List[Dict[str, Any]]:
        inputs: List[Dict[str, Any]] = [{"type": "text", "text": text, "textElements": []}]
        cwd: Path = self.codex_cfg["cwd"]
        for attachment in attachments or []:
            image_input = _attachment_image_input(attachment, cwd)
            if image_input is not None:
                inputs.append(image_input)
        return inputs

    def _turn_result(self, turn_id: str, *, timeout: bool = False) -> Dict[str, Any]:
        status = self._turn_status.get(turn_id) or "completed"
        error = self._turn_error.get(turn_id) or ""
        ok = not timeout and status == "completed" and not error
        final_text = self._turn_text.get(turn_id, "")
        elapsed = max(0.0, time.monotonic() - self._started_at) if self._started_at else 0.0
        return {
            "ok": ok,
            "returncode": 0 if ok else 1,
            "timeout": bool(timeout),
            "elapsed_sec": elapsed,
            "final_text": final_text,
            "last_message": final_text,
            "stderr": "".join(self._stderr_parts),
            "stdout": "".join(self._protocol_log),
            "thread_id": self.thread_id or "",
            "turn_id": turn_id,
            "turn_status": status,
            "error": error,
        }

    async def _request(self, method: str, params: Dict[str, Any], *, timeout: float) -> Dict[str, Any]:
        await self.start() if self._proc is None else None
        if self._proc is None or self._proc.stdin is None or self._proc.returncode is not None:
            raise CodexAppServerError("app-server is not running")
        self._request_id += 1
        rid = self._request_id
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Dict[str, Any]] = loop.create_future()
        self._pending[rid] = fut
        payload = {"id": rid, "method": method, "params": params}
        try:
            await self._write_payload(payload)
            response = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(rid, None)
            raise CodexAppServerError(f"{method} timed out after {timeout}s") from None
        finally:
            self._pending.pop(rid, None)
        if "error" in response:
            raise CodexAppServerError(_json_rpc_error_message(response))
        result = response.get("result")
        return result if isinstance(result, dict) else {}

    async def _notify(self, method: str, params: Dict[str, Any]) -> None:
        await self._write_payload({"method": method, "params": params})

    async def _write_payload(self, payload: Dict[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise CodexAppServerError("app-server stdin is closed")
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        _append_limited(self._protocol_log, raw, limit=APP_SERVER_PROTOCOL_LOG_MAX_CHARS)
        self._proc.stdin.write(raw.encode("utf-8"))
        await self._proc.stdin.drain()

    async def _read_stdout_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        pending = ""
        try:
            while True:
                chunk = await self._proc.stdout.read(65536)
                if not chunk:
                    break
                pending += decoder.decode(chunk)
                while True:
                    index = pending.find("\n")
                    if index < 0:
                        break
                    line = pending[:index]
                    pending = pending[index + 1 :]
                    await self._handle_stdout_line(line)
            tail = decoder.decode(b"", final=True)
            if tail:
                pending += tail
            if pending.strip():
                await self._handle_stdout_line(pending)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("[codex-app-server] stdout loop failed: %s", exc)
        finally:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(CodexAppServerError("app-server stdout closed"))

    async def _read_stderr_loop(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            while True:
                chunk = await self._proc.stderr.read(65536)
                if not chunk:
                    break
                text = decoder.decode(chunk)
                _append_limited(self._stderr_parts, text, limit=APP_SERVER_STDERR_MAX_CHARS)
            tail = decoder.decode(b"", final=True)
            if tail:
                _append_limited(self._stderr_parts, tail, limit=APP_SERVER_STDERR_MAX_CHARS)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.debug("[codex-app-server] stderr loop failed: %s", exc)

    async def _handle_stdout_line(self, line: str) -> None:
        text = line.strip()
        if not text:
            return
        _append_limited(self._protocol_log, text + "\n", limit=APP_SERVER_PROTOCOL_LOG_MAX_CHARS)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            log.debug("[codex-app-server] ignoring non-json stdout: %s", text[:200])
            return
        if not isinstance(payload, dict):
            return
        rid = payload.get("id")
        if isinstance(rid, int) and ("result" in payload or "error" in payload):
            fut = self._pending.get(rid)
            if fut is not None and not fut.done():
                fut.set_result(payload)
            return
        if "method" in payload and "id" in payload:
            await self._reject_server_request(payload)
            return
        method = str(payload.get("method") or "").strip()
        if method:
            await self._handle_notification(method, payload.get("params") if isinstance(payload.get("params"), dict) else {})

    async def _reject_server_request(self, payload: Dict[str, Any]) -> None:
        rid = payload.get("id")
        method = str(payload.get("method") or "").strip()
        response = {
            "id": rid,
            "error": {
                "code": -32601,
                "message": f"server request is not supported by this adapter: {method}",
            },
        }
        try:
            await self._write_payload(response)
        except Exception:
            log.debug("[codex-app-server] failed to reject server request", exc_info=True)

    async def _handle_notification(self, method: str, params: Dict[str, Any]) -> None:
        turn_id = str(params.get("turnId") or params.get("turn_id") or "").strip()
        if not turn_id and isinstance(params.get("turn"), dict):
            turn_id = str(params["turn"].get("id") or "").strip()
        if method == "item/agentMessage/delta":
            delta = str(params.get("delta") or "")
            if turn_id and delta:
                self._turn_text[turn_id] = self._turn_text.get(turn_id, "") + delta
            await self._emit_stream(
                {
                    "kind": "part.delta",
                    "part_id": str(params.get("itemId") or params.get("item_id") or "agent"),
                    "part_type": "text",
                    "field": "text",
                    "delta": delta,
                    "text": delta,
                    "status": "running",
                    "thread_id": str(params.get("threadId") or self.thread_id or ""),
                    "turn_id": turn_id,
                }
            )
            return
        if method == "item/completed":
            item = params.get("item")
            if isinstance(item, dict) and str(item.get("type") or "") == "agentMessage":
                item_text = str(item.get("text") or "")
                if turn_id and item_text:
                    self._turn_text[turn_id] = item_text
            return
        if method == "turn/completed":
            turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
            if not turn_id:
                turn_id = str(turn.get("id") or "").strip()
            status = str(turn.get("status") or "completed").strip() or "completed"
            self._turn_status[turn_id] = status
            error = turn.get("error")
            if isinstance(error, dict):
                self._turn_error[turn_id] = str(error.get("message") or error).strip()
            elif error:
                self._turn_error[turn_id] = str(error)
            self._completed_turns[turn_id] = params
            self._turn_events.setdefault(turn_id, asyncio.Event()).set()
            await self._emit_stream(
                {
                    "kind": "message.completed",
                    "status": status,
                    "thread_id": str(params.get("threadId") or self.thread_id or ""),
                    "turn_id": turn_id,
                    "error": self._turn_error.get(turn_id),
                }
            )
            return
        if method == "error":
            error = params.get("error")
            message = str(error.get("message") if isinstance(error, dict) else error or "app-server error")
            if self.active_turn_id:
                self._turn_error[self.active_turn_id] = message
            await self._emit_stream({"kind": "error", "status": "error", "error": message})

    async def _emit_stream(self, event: Dict[str, Any]) -> None:
        callback = self._active_stream_callback
        if callback is None:
            return
        data = {**self._active_stream_context, **event}
        result = callback(data)
        if asyncio.iscoroutine(result):
            await result
