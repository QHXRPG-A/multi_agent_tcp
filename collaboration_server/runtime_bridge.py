from __future__ import annotations

import time
from typing import Any, Protocol

import httpx

from .auth import APIError
from .observability import log_event


class RuntimeBridge(Protocol):
    def list_runs(self, binding: dict[str, Any]) -> list[dict[str, Any]]: ...

    def status(self, binding: dict[str, Any], runtime_run_id: str) -> dict[str, Any]: ...

    def recent_events(self, binding: dict[str, Any], runtime_run_id: str, *, limit: int = 100) -> list[dict[str, Any]]: ...

    def agent_info(self, binding: dict[str, Any], runtime_run_id: str, node_id: str) -> dict[str, Any]: ...

    def run_diff(self, binding: dict[str, Any], runtime_run_id: str) -> dict[str, Any]: ...

    def changeset_diff(self, binding: dict[str, Any], runtime_run_id: str, changeset_id: str) -> dict[str, Any]: ...

    def start_run(self, binding: dict[str, Any], plan: dict[str, Any], *, execution_mode: str = "live") -> dict[str, Any]: ...

    def queue_agent_message(
        self,
        binding: dict[str, Any],
        runtime_run_id: str,
        node_id: str,
        text: str,
        *,
        mode: str = "default",
    ) -> dict[str, Any]: ...

    def end_run(self, binding: dict[str, Any], runtime_run_id: str, *, action: str, reason: str = "") -> dict[str, Any]: ...

    def rollback_changesets(
        self,
        binding: dict[str, Any],
        runtime_run_id: str,
        changeset_id: str,
        *,
        reason: str = "",
    ) -> dict[str, Any]: ...

    def mark_planning_plan_started(
        self,
        binding: dict[str, Any],
        planning_session_id: str,
        runtime_run_id: str,
        started: dict[str, Any],
    ) -> dict[str, Any]: ...


class DesktopControlBridgeProtocol(Protocol):
    def request(self, bridge: dict[str, Any], command: str, args: dict[str, Any]) -> dict[str, Any]: ...


class DesktopRuntimeBridge:
    def __init__(self, *, timeout: float = 15.0, transport: httpx.BaseTransport | None = None) -> None:
        self.timeout = timeout
        self.transport = transport

    def request(self, binding: dict[str, Any], command: str, args: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        url = str(binding.get("bridge_url") or "").strip()
        token = str(binding.get("bridge_token") or "")
        runtime_run_id = str(args.get("runId") or args.get("run_id") or "") or None
        base_context = {
            "command": command,
            "binding_id": binding.get("id"),
            "project_id": binding.get("project_id"),
            "blueprint_id": binding.get("blueprint_id"),
            "runtime_run_id": runtime_run_id,
            "args": args,
        }
        log_event("info", "runtime.bridge.request", **base_context)
        if not url or not token:
            log_event(
                "warning",
                "runtime.bridge.failure",
                duration_ms=_elapsed_ms(started),
                code="RUNTIME_UNAVAILABLE",
                **base_context,
            )
            raise APIError(503, "RUNTIME_UNAVAILABLE", "runtime binding is not configured")
        payload = {"token": token, "command": command, "args": args}
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.post(url, json=payload)
        except httpx.HTTPError as exc:
            log_event(
                "warning",
                "runtime.bridge.failure",
                duration_ms=_elapsed_ms(started),
                code="RUNTIME_UNAVAILABLE",
                error_type=type(exc).__name__,
                **base_context,
            )
            raise APIError(503, "RUNTIME_UNAVAILABLE", "Python runtime is not reachable", details={"bridge": type(exc).__name__}) from exc
        try:
            data = response.json()
        except ValueError as exc:
            log_event(
                "error",
                "runtime.bridge.failure",
                duration_ms=_elapsed_ms(started),
                status=response.status_code,
                code="RUNTIME_BAD_RESPONSE",
                **base_context,
            )
            raise APIError(502, "RUNTIME_BAD_RESPONSE", "Python runtime returned invalid JSON") from exc
        if response.status_code >= 400 or not data.get("ok", True):
            code = str(data.get("code") or "RUNTIME_ERROR")
            message = str(data.get("error") or data.get("message") or "Python runtime request failed")
            status = int(response.status_code) if response.status_code >= 400 else 502
            log_event(
                "warning",
                "runtime.bridge.failure",
                duration_ms=_elapsed_ms(started),
                status=status,
                code=code,
                message=message,
                details=data.get("details") if isinstance(data.get("details"), dict) else None,
                **base_context,
            )
            raise APIError(status, code, message, details=data.get("details") if isinstance(data.get("details"), dict) else None)
        log_event(
            "info",
            "runtime.bridge.success",
            duration_ms=_elapsed_ms(started),
            status=response.status_code,
            **base_context,
        )
        return data

    def list_runs(self, binding: dict[str, Any]) -> list[dict[str, Any]]:
        data = self.request(
            binding,
            "blueprint.listRuns",
            {
                "projectDir": binding.get("project_dir"),
                "blueprintId": binding.get("blueprint_id"),
            },
        )
        return [dict(item) for item in list(data.get("runs") or []) if isinstance(item, dict)]

    def status(self, binding: dict[str, Any], runtime_run_id: str) -> dict[str, Any]:
        return self.request(binding, "blueprint.status", {"runId": runtime_run_id})

    def recent_events(self, binding: dict[str, Any], runtime_run_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        data = self.request(binding, "blueprint.recentEvents", {"runId": runtime_run_id, "limit": limit})
        return [dict(item) for item in list(data.get("events") or []) if isinstance(item, dict)]

    def agent_info(self, binding: dict[str, Any], runtime_run_id: str, node_id: str) -> dict[str, Any]:
        return self.request(binding, "blueprint.agentInfo", {"runId": runtime_run_id, "nodeId": node_id})

    def run_diff(self, binding: dict[str, Any], runtime_run_id: str) -> dict[str, Any]:
        return self.request(binding, "blueprint.runDiff", {"runId": runtime_run_id})

    def changeset_diff(self, binding: dict[str, Any], runtime_run_id: str, changeset_id: str) -> dict[str, Any]:
        return self.request(binding, "blueprint.changesetDiff", {"runId": runtime_run_id, "changesetId": changeset_id})

    def start_run(self, binding: dict[str, Any], plan: dict[str, Any], *, execution_mode: str = "live") -> dict[str, Any]:
        return self.request(
            binding,
            "blueprint.start",
            {
                "projectDir": binding.get("project_dir"),
                "blueprintId": binding.get("blueprint_id"),
                "plan": plan,
                "executionMode": execution_mode,
            },
        )

    def queue_agent_message(
        self,
        binding: dict[str, Any],
        runtime_run_id: str,
        node_id: str,
        text: str,
        *,
        mode: str = "default",
    ) -> dict[str, Any]:
        return self.request(
            binding,
            "blueprint.queueAgentMessage",
            {"runId": runtime_run_id, "nodeId": node_id, "text": text, "mode": mode},
        )

    def end_run(self, binding: dict[str, Any], runtime_run_id: str, *, action: str, reason: str = "") -> dict[str, Any]:
        return self.request(binding, "blueprint.end", {"runId": runtime_run_id, "action": action, "reason": reason})

    def rollback_changesets(
        self,
        binding: dict[str, Any],
        runtime_run_id: str,
        changeset_id: str,
        *,
        reason: str = "",
    ) -> dict[str, Any]:
        return self.request(
            binding,
            "blueprint.rollbackChangesets",
            {"runId": runtime_run_id, "toChangesetId": changeset_id, "reason": reason},
        )

    def mark_planning_plan_started(
        self,
        binding: dict[str, Any],
        planning_session_id: str,
        runtime_run_id: str,
        started: dict[str, Any],
    ) -> dict[str, Any]:
        return self.request(
            binding,
            "blueprint.planning.markPlanStarted",
            {"sessionId": planning_session_id, "runId": runtime_run_id, "started": started},
        )


class DesktopControlBridge:
    def __init__(self, *, timeout: float = 10.0, transport: httpx.BaseTransport | None = None) -> None:
        self.timeout = timeout
        self.transport = transport

    def request(self, bridge: dict[str, Any], command: str, args: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        url = str(bridge.get("bridge_url") or "").strip()
        token = str(bridge.get("bridge_token") or "")
        base_context = {
            "command": command,
            "user_id": bridge.get("user_id"),
            "desktop_session_id": bridge.get("session_id"),
            "args": args,
        }
        log_event("info", "desktop.bridge.request", **base_context)
        if not url or not token:
            log_event(
                "warning",
                "desktop.bridge.failure",
                duration_ms=_elapsed_ms(started),
                code="DESKTOP_UNAVAILABLE",
                **base_context,
            )
            raise APIError(503, "DESKTOP_UNAVAILABLE", "desktop bridge is not registered")
        payload = {"token": token, "command": command, "args": args}
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.post(url, json=payload)
        except httpx.HTTPError as exc:
            log_event(
                "warning",
                "desktop.bridge.failure",
                duration_ms=_elapsed_ms(started),
                code="DESKTOP_UNAVAILABLE",
                error_type=type(exc).__name__,
                **base_context,
            )
            raise APIError(503, "DESKTOP_UNAVAILABLE", "desktop bridge is not reachable", details={"bridge": type(exc).__name__}) from exc
        try:
            data = response.json()
        except ValueError as exc:
            log_event(
                "error",
                "desktop.bridge.failure",
                duration_ms=_elapsed_ms(started),
                status=response.status_code,
                code="DESKTOP_BAD_RESPONSE",
                **base_context,
            )
            raise APIError(502, "DESKTOP_BAD_RESPONSE", "desktop bridge returned invalid JSON") from exc
        if response.status_code >= 400 or not data.get("ok", True):
            code = str(data.get("code") or "DESKTOP_ERROR")
            message = str(data.get("error") or data.get("message") or "desktop bridge request failed")
            status = int(response.status_code) if response.status_code >= 400 else 502
            log_event(
                "warning",
                "desktop.bridge.failure",
                duration_ms=_elapsed_ms(started),
                status=status,
                code=code,
                message=message,
                **base_context,
            )
            raise APIError(status, code, message, details=data.get("details") if isinstance(data.get("details"), dict) else None)
        log_event("info", "desktop.bridge.success", duration_ms=_elapsed_ms(started), status=response.status_code, **base_context)
        return data


def _elapsed_ms(started: float) -> float:
    return (time.monotonic() - started) * 1000
