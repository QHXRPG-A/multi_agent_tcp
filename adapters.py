"""CLI adapter abstractions for long-lived agent worker processes."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from .codex_bridge import codex_run, load_codex_runtime
from .codemaker_bridge import codemaker_run, load_codemaker_runtime

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
        }

    async def close(self) -> None:
        self._started = False


class CodeMakerAdapter(CLIAdapter):
    """Compatibility adapter for CodeMaker CLI workers.

    The adapter object is long-lived and owns the worker-side runtime config.
    Current CodeMaker CLI execution remains per-message ``codemaker run`` for
    compatibility, hidden behind this persistent adapter boundary.
    """

    cli_kind = "codemaker"

    @classmethod
    def from_agent_config(cls, cfg: Dict[str, Any]) -> "CodeMakerAdapter":
        agent_id = str(cfg["agent_id"])
        return cls(agent_id, load_codemaker_runtime(cfg))

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
        result = await codemaker_run(
            message.prompt,
            stdin_context=message.context,
            codemaker_cfg=self.runtime_config,
        )
        self.messages_handled += 1
        ok = result.get("returncode") == 0
        status = "timeout" if result.get("timeout") else ("success" if ok else "error")
        payload = {
            "ok": ok,
            "codemaker": result,
            "adapter": {
                "cli_kind": self.cli_kind,
                "agent_id": self.agent_id,
                "messages_handled": self.messages_handled,
                "persistent_instance": True,
                "per_message_subprocess": True,
            },
        }
        return AdapterResult(ok=ok, payload=payload, status=status)


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
            "codex": result,
            "adapter": {
                "cli_kind": self.cli_kind,
                "agent_id": self.agent_id,
                "messages_handled": self.messages_handled,
                "persistent_instance": True,
                "per_message_subprocess": True,
            },
        }
        return AdapterResult(ok=ok, payload=payload, status=status)


def adapter_from_agent_config(cfg: Dict[str, Any]) -> CLIAdapter:
    """Create the worker-side adapter for one agent config."""
    cli_kind = str(cfg.get("cli_kind") or cfg.get("adapter") or "codemaker").strip().lower()
    mode = str(cfg.get("mode", "")).strip().lower()
    if mode == "codex-worker":
        return CodexAdapter.from_agent_config(cfg)
    if mode == "codemaker-worker":
        return CodeMakerAdapter.from_agent_config(cfg)
    if cli_kind == "codex":
        return CodexAdapter.from_agent_config(cfg)
    if cli_kind == "codemaker":
        return CodeMakerAdapter.from_agent_config(cfg)
    raise ValueError(f"unsupported cli_kind for agent worker: {cli_kind!r}")
