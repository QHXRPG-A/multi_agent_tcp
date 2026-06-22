"""CLI adapter abstractions for long-lived agent worker processes."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from .codex_app_server_bridge import CodexAppServerSession
from .codex_bridge import compact_codex_result_for_transport, codex_run, load_codex_runtime

log = logging.getLogger(__name__)


@dataclass
class AgentMessage:
    """Normalized message sent to a CLI-backed agent instance."""

    prompt: str
    context: Optional[str] = None
    attachments: List[Any] = field(default_factory=list)
    raw_body: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AdapterResult:
    """Normalized result returned by a CLI adapter."""

    ok: bool
    payload: Dict[str, Any]
    status: str = "success"
    error: Optional[str] = None


AgentStreamCallback = Callable[[Dict[str, Any]], Awaitable[None]]


def body_to_agent_message(body: Any) -> AgentMessage:
    """Normalize broker/graph body payloads into an AgentMessage.

    This intentionally mirrors the legacy ``_body_to_prompt_and_context``
    behavior while preserving attachments for adapters that can consume them.
    """
    attachments: List[Any] = []
    if isinstance(body, str):
        return AgentMessage(prompt=body.strip(), raw_body=body)
    if isinstance(body, dict):
        prompt = body.get("prompt")
        raw_attachments = body.get("attachments")
        if isinstance(raw_attachments, list):
            attachments = raw_attachments
        elif raw_attachments is not None:
            attachments = [raw_attachments]

        if isinstance(prompt, str) and prompt.strip():
            ctx = body.get("context")
            if ctx is not None and not isinstance(ctx, str):
                ctx = json.dumps(ctx, ensure_ascii=False)
            return AgentMessage(
                prompt=prompt.strip(),
                context=ctx if isinstance(ctx, str) else None,
                attachments=attachments,
                raw_body=body,
            )
        return AgentMessage(
            prompt=json.dumps(body, ensure_ascii=False),
            attachments=attachments,
            raw_body=body,
        )
    return AgentMessage(prompt=json.dumps(body, ensure_ascii=False), raw_body=body)


class CLIAdapter(ABC):
    """Base interface for one long-lived CLI agent instance.

    Adapter instances are created once per worker/AgentNode binding and reused
    for every message that reaches that node during a graph run. Individual
    adapters may still execute per-message subprocesses internally when the
    underlying CLI has no persistent-session mode yet.
    """

    cli_kind: str = "custom"

    def __init__(self, agent_id: str, runtime_config: Dict[str, Any]) -> None:
        self.agent_id = str(agent_id).strip()
        self.runtime_config = runtime_config
        self.messages_handled = 0
        self._started = False
        self.conversation_backend = "exec"
        self.conversation_id: Optional[str] = None
        self.active_turn_id: Optional[str] = None
        self.supports_steer = False

    async def start(self) -> None:
        self._started = True

    @abstractmethod
    async def send_message(
        self,
        message: AgentMessage,
        *,
        stream_callback: Optional[AgentStreamCallback] = None,
    ) -> AdapterResult:
        """Send one message to the bound CLI agent instance."""

    async def health_check(self) -> Dict[str, Any]:
        return {
            "ok": self._started,
            "agent_id": self.agent_id,
            "cli_kind": self.cli_kind,
            "messages_handled": self.messages_handled,
            "conversation_backend": self.conversation_backend,
            "conversation_id": self.conversation_id,
            "active_turn_id": self.active_turn_id,
            "supports_steer": self.supports_steer,
        }

    async def steer_message(
        self,
        message: AgentMessage,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AdapterResult:
        payload = {
            "ok": False,
            "error": "adapter does not support turn steering",
            "adapter": {
                "cli_kind": self.cli_kind,
                "agent_id": self.agent_id,
                "conversationBackend": self.conversation_backend,
                "conversationId": self.conversation_id,
                "activeTurnId": self.active_turn_id,
                "supportsSteer": self.supports_steer,
            },
        }
        return AdapterResult(
            ok=False,
            payload=payload,
            status="unsupported",
            error=payload["error"],
        )

    async def close(self) -> None:
        self._started = False


class CodexAdapter(CLIAdapter):
    """Adapter for non-interactive Codex CLI workers.

    Codex currently runs per message through ``codex exec`` while this adapter
    provides the same long-lived worker boundary as other CLI kinds.
    """

    cli_kind = "codex"

    @classmethod
    def from_agent_config(cls, cfg: Dict[str, Any]) -> "CodexAdapter":
        agent_id = str(cfg["agent_id"])
        return cls(agent_id, load_codex_runtime(cfg))

    async def send_message(
        self,
        message: AgentMessage,
        *,
        stream_callback: Optional[AgentStreamCallback] = None,
    ) -> AdapterResult:
        if not self._started:
            await self.start()
        if not message.prompt.strip():
            raise ValueError("empty prompt")

        log.info(
            "[adapter] agent=%s cli_kind=%s message_index=%s prompt_chars=%s has_context=%s attachments=%s",
            self.agent_id,
            self.cli_kind,
            self.messages_handled + 1,
            len(message.prompt.encode("utf-8")),
            bool(message.context),
            len(message.attachments),
        )
        result = await codex_run(
            message.prompt,
            stdin_context=message.context,
            attachments=message.attachments,
            codex_cfg=self.runtime_config,
            stream_callback=stream_callback,
            stream_context=message.metadata.get("framework_stream"),
        )
        self.messages_handled += 1
        ok = result.get("returncode") == 0
        status = "timeout" if result.get("timeout") else ("success" if ok else "error")
        payload = {
            "ok": ok,
            "codex": compact_codex_result_for_transport(result),
            "adapter": {
                "cli_kind": self.cli_kind,
                "agent_id": self.agent_id,
                "messages_handled": self.messages_handled,
                "persistent_instance": True,
                "per_message_subprocess": True,
                "conversationBackend": self.conversation_backend,
                "conversationId": self.conversation_id,
                "activeTurnId": self.active_turn_id,
                "supportsSteer": self.supports_steer,
            },
        }
        return AdapterResult(ok=ok, payload=payload, status=status)


class CodexAppServerAdapter(CLIAdapter):
    """Adapter for persistent Codex app-server workers."""

    cli_kind = "codex"

    def __init__(self, agent_id: str, runtime_config: Dict[str, Any]) -> None:
        super().__init__(agent_id, runtime_config)
        self.conversation_backend = "codex_app_server"
        self.supports_steer = True
        self._session = CodexAppServerSession(runtime_config)

    @classmethod
    def from_agent_config(cls, cfg: Dict[str, Any]) -> "CodexAppServerAdapter":
        agent_id = str(cfg["agent_id"])
        return cls(agent_id, load_codex_runtime(cfg))

    async def start(self) -> None:
        await super().start()
        await self._session.start()
        self.conversation_id = self._session.thread_id
        self.active_turn_id = self._session.active_turn_id

    async def send_message(
        self,
        message: AgentMessage,
        *,
        stream_callback: Optional[AgentStreamCallback] = None,
    ) -> AdapterResult:
        if not self._started:
            await self.start()
        if not message.prompt.strip():
            raise ValueError("empty prompt")

        log.info(
            "[adapter] agent=%s cli_kind=%s backend=%s message_index=%s prompt_chars=%s has_context=%s attachments=%s",
            self.agent_id,
            self.cli_kind,
            self.conversation_backend,
            self.messages_handled + 1,
            len(message.prompt.encode("utf-8")),
            bool(message.context),
            len(message.attachments),
        )
        result = await self._session.start_turn(
            prompt=message.prompt,
            context=message.context,
            attachments=message.attachments,
            stream_callback=stream_callback,
            stream_context=message.metadata.get("framework_stream"),
            client_user_message_id=str(message.metadata.get("message_id") or "").strip() or None,
        )
        self.messages_handled += 1
        self.conversation_id = self._session.thread_id
        self.active_turn_id = self._session.active_turn_id
        ok = bool(result.get("ok"))
        status = "timeout" if result.get("timeout") else ("success" if ok else "error")
        payload = {
            "ok": ok,
            "codex": compact_codex_result_for_transport(result),
            "adapter": {
                "cli_kind": self.cli_kind,
                "agent_id": self.agent_id,
                "messages_handled": self.messages_handled,
                "persistent_instance": True,
                "per_message_subprocess": False,
                "conversationBackend": self.conversation_backend,
                "conversationId": self.conversation_id,
                "activeTurnId": result.get("turn_id") or self.active_turn_id,
                "supportsSteer": self.supports_steer,
            },
        }
        return AdapterResult(
            ok=ok,
            payload=payload,
            status=status,
            error=str(result.get("error") or "") or None,
        )

    async def steer_message(
        self,
        message: AgentMessage,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AdapterResult:
        if not self._started:
            return await super().steer_message(message, metadata=metadata)
        metadata = dict(metadata or {})
        result = await self._session.steer_turn(
            prompt=message.prompt,
            context=message.context,
            attachments=message.attachments,
            client_user_message_id=str(metadata.get("message_id") or "").strip() or None,
        )
        self.conversation_id = self._session.thread_id
        self.active_turn_id = self._session.active_turn_id
        ok = bool(result.get("ok"))
        payload = {
            "ok": ok,
            "status": result.get("status"),
            "error": result.get("error") or "",
            "adapter": {
                "cli_kind": self.cli_kind,
                "agent_id": self.agent_id,
                "messages_handled": self.messages_handled,
                "persistent_instance": True,
                "per_message_subprocess": False,
                "conversationBackend": self.conversation_backend,
                "conversationId": self.conversation_id,
                "activeTurnId": self.active_turn_id,
                "supportsSteer": self.supports_steer,
            },
            "codex": {
                "thread_id": result.get("thread_id") or self.conversation_id,
                "turn_id": result.get("turn_id") or self.active_turn_id,
            },
        }
        return AdapterResult(
            ok=ok,
            payload=payload,
            status="steered" if ok else "rejected",
            error=str(result.get("error") or "") or None,
        )

    async def close(self) -> None:
        await self._session.close()
        self.conversation_id = self._session.thread_id
        self.active_turn_id = None
        await super().close()


def _codex_backend_from_config(cfg: Dict[str, Any]) -> str:
    raw_cfg = cfg.get("codex") if isinstance(cfg.get("codex"), dict) else {}
    adapter_options = cfg.get("adapter_options") if isinstance(cfg.get("adapter_options"), dict) else {}
    for source in (raw_cfg, adapter_options, cfg):
        value = source.get("codex_backend") or source.get("conversation_backend") or source.get("backend")
        if isinstance(value, str) and value.strip():
            return value.strip().lower().replace("-", "_")
    return "exec"


def adapter_from_agent_config(cfg: Dict[str, Any]) -> CLIAdapter:
    """Create the worker-side adapter for one agent config."""
    cli_kind = str(cfg.get("cli_kind") or cfg.get("adapter") or "codex").strip().lower()
    mode = str(cfg.get("mode", "")).strip().lower()
    if mode == "codex-worker":
        if _codex_backend_from_config(cfg) in {"app_server", "codex_app_server"}:
            return CodexAppServerAdapter.from_agent_config(cfg)
        return CodexAdapter.from_agent_config(cfg)
    if cli_kind == "codex":
        if _codex_backend_from_config(cfg) in {"app_server", "codex_app_server"}:
            return CodexAppServerAdapter.from_agent_config(cfg)
        return CodexAdapter.from_agent_config(cfg)
    raise ValueError(f"unsupported cli_kind for agent worker: {cli_kind!r}")
