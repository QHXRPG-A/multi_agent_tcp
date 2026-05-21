"""Run-scoped MCP adapter for desktop blueprint live runtimes."""

from __future__ import annotations

import asyncio
import base64
import contextvars
import json
import secrets
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence


ORDINARY_SERVER_NAME = "framework_ordinary"
CONTROL_SERVER_NAME = "framework_control"
ORDINARY_TOKEN_ENV = "MULTI_AGENT_MCP_ORDINARY_TOKEN"
CONTROL_TOKEN_ENV = "MULTI_AGENT_MCP_CONTROL_TOKEN"
MCP_TOOL_AUDIT_EVENT = "framework_mcp_tool_call"
_SENSITIVE_ARG_KEYS = {
    "authorization",
    "bearer_token",
    "bearer_token_env_var",
    "rpc_token",
    "secret",
    "token",
    "url",
}


class MCPUnauthorized(PermissionError):
    """Raised when a run MCP request fails local bearer-token authorization."""


@dataclass
class MCPCurrentMessageContext:
    current_message_id: str
    outgoing_batch_id: Optional[str]
    required_outgoing_targets: list[str]
    expires_at: float

    def to_safe_dict(self) -> Dict[str, Any]:
        return {
            "current_message_id": self.current_message_id,
            "outgoing_batch_id": self.outgoing_batch_id,
            "required_outgoing_targets": list(self.required_outgoing_targets),
            "expires_at": self.expires_at,
        }


@dataclass
class MCPTokenScope:
    token: str
    run_id: str
    server_kind: str
    allowed_tools: list[str]
    expires_at: float
    agent_node_id: Optional[str] = None
    agent_id: Optional[str] = None
    workspace_rpc_token: Optional[str] = None
    control_permissions: list[str] = field(default_factory=list)
    checkout_dir: Optional[Path] = None
    private_dir: Optional[Path] = None
    allowed_file_roots: list[Path] = field(default_factory=list)
    current_message_context: Optional[MCPCurrentMessageContext] = None

    def to_safe_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "run_id": self.run_id,
            "server_kind": self.server_kind,
            "allowed_tools": list(self.allowed_tools),
            "expires_at": self.expires_at,
        }
        if self.agent_node_id is not None:
            data["agent_node_id"] = self.agent_node_id
        if self.agent_id is not None:
            data["agent_id"] = self.agent_id
        if self.control_permissions:
            data["control_permissions"] = list(self.control_permissions)
        if self.current_message_context is not None:
            data["current_message_context"] = self.current_message_context.to_safe_dict()
        return data


class RunMCPTokenStore:
    """Opaque run-local bearer token store with MCP session binding."""

    def __init__(self, run_id: str, *, now: Callable[[], float] = time.time) -> None:
        self.run_id = run_id
        self.now = now
        self._lock = threading.RLock()
        self._closed = False
        self._scopes_by_token: Dict[str, MCPTokenScope] = {}
        self._ordinary_token_by_node: Dict[str, str] = {}
        self._control_token: Optional[str] = None
        self._session_token_by_id: Dict[str, str] = {}

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def close(self) -> None:
        with self._lock:
            self._closed = True

    def create_ordinary_scope(
        self,
        *,
        agent_node_id: str,
        agent_id: str,
        workspace_rpc_token: str,
        checkout_dir: Path,
        private_dir: Path,
        allowed_file_roots: Sequence[Path],
        ttl_sec: float = 24 * 60 * 60,
    ) -> MCPTokenScope:
        with self._lock:
            token = self._ordinary_token_by_node.get(agent_node_id)
            if token is None:
                token = secrets.token_urlsafe(32)
                self._ordinary_token_by_node[agent_node_id] = token
            scope = MCPTokenScope(
                token=token,
                run_id=self.run_id,
                server_kind="ordinary",
                agent_node_id=agent_node_id,
                agent_id=agent_id,
                workspace_rpc_token=workspace_rpc_token,
                allowed_tools=ORDINARY_TOOL_NAMES,
                checkout_dir=Path(checkout_dir),
                private_dir=Path(private_dir),
                allowed_file_roots=[Path(root) for root in allowed_file_roots],
                expires_at=float(self.now()) + float(ttl_sec),
            )
            self._scopes_by_token[token] = scope
            return scope

    def create_control_scope(
        self,
        *,
        agent_node_id: str,
        agent_id: str,
        workspace_rpc_token: Optional[str] = None,
        permissions: Optional[Sequence[str]] = None,
        allowed_tools: Optional[Sequence[str]] = None,
        ttl_sec: float = 24 * 60 * 60,
    ) -> MCPTokenScope:
        with self._lock:
            token = self._control_token
            if token is None:
                token = secrets.token_urlsafe(32)
                self._control_token = token
            scope = MCPTokenScope(
                token=token,
                run_id=self.run_id,
                server_kind="control",
                agent_node_id=agent_node_id,
                agent_id=agent_id,
                workspace_rpc_token=workspace_rpc_token,
                control_permissions=_normalized_control_permissions(permissions),
                allowed_tools=(
                    _normalized_control_tools(allowed_tools)
                    if allowed_tools is not None
                    else _control_tools_for_permissions(permissions)
                ),
                expires_at=float(self.now()) + float(ttl_sec),
            )
            self._scopes_by_token[token] = scope
            return scope

    def authenticate(
        self,
        *,
        server_kind: str,
        token: Optional[str],
        session_id: Optional[str],
    ) -> MCPTokenScope:
        with self._lock:
            if self._closed:
                raise MCPUnauthorized("run MCP server is closed")
            if not token:
                raise MCPUnauthorized("missing bearer token")
            scope = self._scopes_by_token.get(token)
            if scope is None:
                raise MCPUnauthorized("invalid bearer token")
            if scope.server_kind != server_kind:
                raise MCPUnauthorized("bearer token is not valid for this MCP server")
            if scope.expires_at < float(self.now()):
                raise MCPUnauthorized("bearer token has expired")
            normalized_session = str(session_id or "").strip()
            if normalized_session:
                bound = self._session_token_by_id.get(normalized_session)
                if bound is None:
                    self._session_token_by_id[normalized_session] = token
                elif bound != token:
                    raise MCPUnauthorized("Mcp-Session-Id is already bound to another token scope")
            return scope

    def update_message_context(
        self,
        *,
        agent_node_id: str,
        agent_id: str,
        current_message_id: str,
        outgoing_batch_id: Optional[str],
        required_outgoing_targets: Sequence[str],
        timeout_sec: Optional[float],
    ) -> None:
        with self._lock:
            token = self._ordinary_token_by_node.get(agent_node_id)
            if token is None:
                return
            scope = self._scopes_by_token.get(token)
            if scope is None or scope.agent_id != agent_id:
                return
            ttl = float(timeout_sec) if timeout_sec is not None else 1800.0
            scope.current_message_context = MCPCurrentMessageContext(
                current_message_id=current_message_id,
                outgoing_batch_id=outgoing_batch_id,
                required_outgoing_targets=[str(item) for item in required_outgoing_targets],
                expires_at=float(self.now()) + max(ttl, 0.0) + 30.0,
            )

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            ordinary = [
                scope.to_safe_dict()
                for scope in self._scopes_by_token.values()
                if scope.server_kind == "ordinary"
            ]
            control = [
                scope.to_safe_dict()
                for scope in self._scopes_by_token.values()
                if scope.server_kind == "control"
            ]
            return {
                "closed": self._closed,
                "ordinaryScopes": ordinary,
                "controlScopes": control,
                "sessionCount": len(self._session_token_by_id),
            }


_current_scope: contextvars.ContextVar[Optional[MCPTokenScope]] = contextvars.ContextVar(
    "multi_agent_tcp_mcp_scope",
    default=None,
)


class MCPBearerAuthMiddleware:
    """ASGI middleware that validates run-scoped opaque bearer tokens."""

    def __init__(self, app: Any, *, token_store: RunMCPTokenStore, server_kind: str) -> None:
        self.app = app
        self.token_store = token_store
        self.server_kind = server_kind

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in scope.get("headers", [])
        }
        try:
            token = _bearer_token(headers.get("authorization", ""))
            mcp_session_id = headers.get("mcp-session-id")
            token_scope = self.token_store.authenticate(
                server_kind=self.server_kind,
                token=token,
                session_id=mcp_session_id,
            )
        except Exception as exc:
            await _send_json(
                send,
                401,
                {"jsonrpc": "2.0", "error": {"code": -32001, "message": str(exc)}},
            )
            return
        reset = _current_scope.set(token_scope)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_scope.reset(reset)


def _is_absolute_path_like(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    if stripped.startswith("\\\\"):
        return True
    if len(stripped) >= 3 and stripped[1] == ":" and stripped[2] in {"\\", "/"}:
        return True
    try:
        return Path(stripped).expanduser().is_absolute()
    except (OSError, ValueError):
        return False


def _safe_path_name(value: str) -> str:
    try:
        return Path(value).name or "<root>"
    except (OSError, ValueError):
        return "<invalid>"


def _safe_mcp_arg_value(key: str, value: Any) -> Any:
    lower = str(key).lower()
    if any(part in lower for part in _SENSITIVE_ARG_KEYS):
        return "<redacted>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if _is_absolute_path_like(value):
            return {"type": "path", "absolute": True, "name": _safe_path_name(value)}
        if lower in {"text", "body", "content", "prompt"}:
            return {"type": "text", "chars": len(value)}
        return value if len(value) <= 200 else {"type": "text", "chars": len(value)}
    if isinstance(value, dict):
        if lower in {"body", "payload"}:
            return {
                "type": "object",
                "keys": sorted(str(item) for item in value.keys())[:20],
            }
        return {
            str(item_key): _safe_mcp_arg_value(str(item_key), item_value)
            for item_key, item_value in list(value.items())[:20]
        }
    if isinstance(value, (list, tuple)):
        return [_safe_mcp_arg_value(key, item) for item in list(value)[:20]]
    return {"type": type(value).__name__}


def _safe_mcp_args(args: Dict[str, Any]) -> Dict[str, Any]:
    return {
        str(key): _safe_mcp_arg_value(str(key), value)
        for key, value in args.items()
        if value is not None
    }


class RunMCPRuntimeHandle:
    """One ASGI/uvicorn MCP adapter instance for one live blueprint run."""

    def __init__(
        self,
        *,
        run_id: str,
        runtime: Any,
        control: Any,
        graph: Any,
        workspace_rpc_server: Any,
        manager: Any,
        workspace_run: Any,
        runtime_loop: Any = None,
        host: str = "127.0.0.1",
        port: int = 0,
        top_agent_node_id: Optional[str] = None,
        top_agent_id: Optional[str] = None,
        close_run_callback: Optional[Callable[..., Any]] = None,
        request_user_input_callback: Optional[Callable[[list[dict[str, Any]]], Any]] = None,
        stage_start_plan_callback: Optional[Callable[[dict[str, Any], str], Any]] = None,
        control_command_callback: Optional[Callable[..., Any]] = None,
        control_call_observer: Optional[Callable[..., Any]] = None,
        control_allowed_tools: Optional[Sequence[str]] = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.run_id = run_id
        self.runtime = runtime
        self.control = control
        self.graph = graph
        self.workspace_rpc_server = workspace_rpc_server
        self.manager = manager
        self.workspace_run = workspace_run
        self.runtime_loop = runtime_loop
        self.host = host
        self.port = int(port or _free_tcp_port())
        self.top_agent_node_id = top_agent_node_id
        self.top_agent_id = top_agent_id
        self.close_run_callback = close_run_callback
        self.request_user_input_callback = request_user_input_callback
        self.stage_start_plan_callback = stage_start_plan_callback
        self.control_command_callback = control_command_callback
        self.control_call_observer = control_call_observer
        self.control_allowed_tools = (
            _normalized_control_tools(control_allowed_tools)
            if control_allowed_tools is not None
            else None
        )
        self.token_store = RunMCPTokenStore(run_id, now=now)
        self._uvicorn_server: Any = None
        self._thread: Optional[threading.Thread] = None
        self._app: Any = None
        self._ordinary_mcp: Any = None
        self._control_mcp: Any = None
        self._state = "created"

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def ordinary_url(self) -> str:
        return f"{self.base_url}/ordinary/mcp"

    @property
    def control_url(self) -> str:
        return f"{self.base_url}/control/mcp"

    @property
    def state(self) -> str:
        return self._state

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        try:
            import uvicorn
        except Exception as exc:  # pragma: no cover - depends on install env
            raise RuntimeError("mcp>=1,<2 with uvicorn is required for blueprint MCP runtime") from exc

        self._app = self._build_app()
        config = uvicorn.Config(
            self._app,
            host=self.host,
            port=self.port,
            log_level="warning",
            lifespan="on",
            access_log=False,
        )
        self._uvicorn_server = uvicorn.Server(config)
        self._state = "starting"
        self._thread = threading.Thread(
            target=self._uvicorn_server.run,
            name=f"blueprint-mcp-{self.run_id}",
            daemon=True,
        )
        self._thread.start()
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if getattr(self._uvicorn_server, "started", False):
                self._state = "running"
                return
            if not self._thread.is_alive():
                break
            time.sleep(0.05)
        raise RuntimeError("blueprint MCP ASGI server failed to start")

    def close(self, *, timeout: float = 5.0) -> None:
        self.token_store.close()
        self._state = "stopping"
        if self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True
        if self._thread is not None and threading.current_thread() is not self._thread:
            self._thread.join(timeout=timeout)
        self._state = "closed"

    def summary(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "state": self._state,
            "port": self.port,
            "ordinaryUrl": self.ordinary_url,
            "controlUrl": self.control_url,
            "ordinaryServer": ORDINARY_SERVER_NAME,
            "controlServer": CONTROL_SERVER_NAME,
            "tokens": self.token_store.summary(),
        }

    def provision_context_for_node(
        self,
        *,
        node: Any,
        private_dir: Path,
        checkout_dir: Path,
        codex_home: Path,
    ) -> Dict[str, Any]:
        private_dir = Path(private_dir)
        checkout_dir = Path(checkout_dir)
        scratch_dir = private_dir / "scratch"
        artifact_tmp_dir = private_dir / "generated_artifacts"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        artifact_tmp_dir.mkdir(parents=True, exist_ok=True)
        node_id = str(getattr(node, "node_id", ""))
        agent_id = str(getattr(node, "runtime_agent_id", getattr(node, "agent_id", node_id)))
        if self._is_control_node(node_id, agent_id):
            token_for = getattr(self.workspace_rpc_server, "token_for", None)
            workspace_rpc_token = token_for(agent_id) if callable(token_for) else None
            scope = self.token_store.create_control_scope(
                agent_node_id=node_id,
                agent_id=agent_id,
                workspace_rpc_token=workspace_rpc_token,
                permissions=self._top_agent_permissions(),
                allowed_tools=self.control_allowed_tools,
            )
            return _mcp_private_context(
                server_kind="control",
                server_name=CONTROL_SERVER_NAME,
                url=self.control_url,
                token_env=CONTROL_TOKEN_ENV,
                token=scope.token,
                tools=scope.allowed_tools,
            )
        workspace_rpc_token = self.workspace_rpc_server.token_for(agent_id)
        scope = self.token_store.create_ordinary_scope(
            agent_node_id=node_id,
            agent_id=agent_id,
            workspace_rpc_token=workspace_rpc_token,
            checkout_dir=checkout_dir,
            private_dir=private_dir,
            allowed_file_roots=[checkout_dir, scratch_dir, artifact_tmp_dir],
        )
        return _mcp_private_context(
            server_kind="ordinary",
            server_name=ORDINARY_SERVER_NAME,
            url=self.ordinary_url,
            token_env=ORDINARY_TOKEN_ENV,
            token=scope.token,
            tools=ORDINARY_TOOL_NAMES,
        )

    def provision_control_context(
        self,
        *,
        agent_node_id: str = "desktop-blueprint-planning",
        agent_id: str = "gulicode-desktop",
        permissions: Optional[Sequence[str]] = None,
        allowed_tools: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        scope = self.token_store.create_control_scope(
            agent_node_id=str(agent_node_id),
            agent_id=str(agent_id),
            workspace_rpc_token=None,
            permissions=permissions if permissions is not None else self._top_agent_permissions(),
            allowed_tools=allowed_tools if allowed_tools is not None else self.control_allowed_tools,
        )
        return _mcp_private_context(
            server_kind="control",
            server_name=CONTROL_SERVER_NAME,
            url=self.control_url,
            token_env=CONTROL_TOKEN_ENV,
            token=scope.token,
            tools=scope.allowed_tools,
        )

    def refresh_message_context(self, event: Dict[str, Any]) -> None:
        body = event.get("body")
        framework_context = _framework_context_from_body(body)
        envelope = framework_context.get("message_envelope") if isinstance(framework_context, dict) else {}
        if not isinstance(envelope, dict):
            envelope = {}
        self.token_store.update_message_context(
            agent_node_id=str(event.get("node_id") or ""),
            agent_id=str(event.get("agent_id") or ""),
            current_message_id=str(event.get("message_id") or ""),
            outgoing_batch_id=(
                str(envelope["outgoing_batch_id"])
                if envelope.get("outgoing_batch_id") is not None
                else None
            ),
            required_outgoing_targets=[
                str(item) for item in envelope.get("required_outgoing_targets", [])
            ] if isinstance(envelope.get("required_outgoing_targets"), list) else [],
            timeout_sec=event.get("timeout_sec"),
        )

    def _is_control_node(self, node_id: str, agent_id: str) -> bool:
        if self.top_agent_node_id and node_id == self.top_agent_node_id:
            return True
        if self.top_agent_id and agent_id == self.top_agent_id:
            return True
        return node_id.startswith("top-agent-")

    def _top_agent_permissions(self) -> list[str]:
        top_agent = getattr(self.control, "top_agent", None)
        return _normalized_control_permissions(
            getattr(top_agent, "allowed_run_permissions", None)
        )

    def _build_app(self) -> Any:
        from contextlib import AsyncExitStack, asynccontextmanager

        from mcp.server.fastmcp import FastMCP
        from starlette.applications import Starlette
        from starlette.routing import Mount

        ordinary_mcp = FastMCP(
            name=f"{self.run_id}-ordinary",
            stateless_http=True,
            streamable_http_path="/mcp",
        )
        control_mcp = FastMCP(
            name=f"{self.run_id}-control",
            stateless_http=True,
            streamable_http_path="/mcp",
        )
        self._ordinary_mcp = ordinary_mcp
        self._control_mcp = control_mcp
        self._register_ordinary_tools(ordinary_mcp)
        self._register_control_tools(control_mcp)
        self._install_tool_filter(ordinary_mcp)
        self._install_tool_filter(control_mcp)
        ordinary_app = MCPBearerAuthMiddleware(
            ordinary_mcp.streamable_http_app(),
            token_store=self.token_store,
            server_kind="ordinary",
        )
        control_app = MCPBearerAuthMiddleware(
            control_mcp.streamable_http_app(),
            token_store=self.token_store,
            server_kind="control",
        )

        @asynccontextmanager
        async def lifespan(_app: Any) -> Any:
            async with AsyncExitStack() as stack:
                await stack.enter_async_context(ordinary_mcp.session_manager.run())
                await stack.enter_async_context(control_mcp.session_manager.run())
                yield

        return Starlette(
            routes=[
                Mount("/ordinary", app=ordinary_app),
                Mount("/control", app=control_app),
            ],
            lifespan=lifespan,
        )

    def _install_tool_filter(self, mcp: Any) -> None:
        original_list_tools = mcp.list_tools

        async def list_tools() -> list[Any]:
            tools = await original_list_tools()
            scope = _current_scope.get()
            if scope is None:
                return tools
            allowed = set(scope.allowed_tools)
            return [
                tool
                for tool in tools
                if str(getattr(tool, "name", "")) in allowed
            ]

        mcp.list_tools = list_tools

    def _register_ordinary_tools(self, mcp: Any) -> None:
        @mcp.tool()
        def workspace_checkout(
            paths: Optional[list[str]] = None,
            scope_paths: Optional[list[str]] = None,
            mode: str = "full",
        ) -> Dict[str, Any]:
            return self._workspace_request(
                _require_scope("ordinary"),
                "checkout",
                {
                    "checkout_paths": [str(item) for item in (paths or [])],
                    "write_scope": [str(item) for item in (scope_paths or [])],
                    "mode": mode,
                },
            )

        @mcp.tool()
        def workspace_status() -> Dict[str, Any]:
            return self._workspace_request(_require_scope("ordinary"), "status", {})

        @mcp.tool()
        def workspace_diff(path: Optional[str] = None, summary: bool = False) -> Dict[str, Any]:
            return self._workspace_request(
                _require_scope("ordinary"),
                "diff",
                {"path": path, "summary": bool(summary)},
            )

        @mcp.tool()
        def workspace_submit(task_id: Optional[str] = None, summary: str = "") -> Dict[str, Any]:
            return self._workspace_request(
                _require_scope("ordinary"),
                "submit",
                {"task_id": task_id, "summary": summary},
            )

        @mcp.tool()
        def workspace_sync() -> Dict[str, Any]:
            return self._workspace_request(_require_scope("ordinary"), "sync", {})

        @mcp.tool()
        def workspace_publish(
            area: str,
            path: str,
            text: str,
            expected_version: Optional[int] = None,
        ) -> Dict[str, Any]:
            return self._workspace_request(
                _require_scope("ordinary"),
                "publish",
                {
                    "area": area,
                    "path": path,
                    "text": text,
                    "expected_version": expected_version,
                },
            )

        @mcp.tool()
        def workspace_publish_file(
            area: str,
            path: str,
            file_path: str,
            expected_version: Optional[int] = None,
        ) -> Dict[str, Any]:
            scope = _require_scope("ordinary")
            resolved = resolve_allowed_publish_file(scope, file_path)
            return self._workspace_request(
                scope,
                "publish-file",
                {
                    "area": area,
                    "path": path,
                    "data_b64": base64.b64encode(resolved.read_bytes()).decode("ascii"),
                    "expected_version": expected_version,
                },
            )

        @mcp.tool()
        async def agent_dispatch(
            target_node_id: str,
            body: Any,
            batch_id: Optional[str] = None,
            source_node_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            scope = _require_scope("ordinary", "agent_dispatch")
            return await self._agent_dispatch(
                scope,
                target_node_id=target_node_id,
                body=body,
                batch_id=batch_id,
                source_node_id=source_node_id,
            )

        @mcp.tool()
        async def agent_context(batch_id: Optional[str] = None) -> Dict[str, Any]:
            scope = _require_scope("ordinary", "agent_context")
            return await self._ordinary_agent_context(scope, batch_id=batch_id)

        @mcp.tool()
        async def join_contribute(
            join_id: str,
            status: str = "completed",
            result: Any = None,
            source_node_id: Optional[str] = None,
            source_agent_id: Optional[str] = None,
            accepted_changesets: Optional[list[dict[str, Any]]] = None,
            conflicts: Optional[list[dict[str, Any]]] = None,
            artifacts: Optional[list[dict[str, Any]]] = None,
            reports: Optional[list[dict[str, Any]]] = None,
            test_results: Optional[list[dict[str, Any]]] = None,
            metadata: Optional[dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            scope = _require_scope("ordinary", "join_contribute")
            return await self._ordinary_join_contribute(
                scope,
                join_id=join_id,
                status=status,
                result=result,
                source_node_id=source_node_id,
                source_agent_id=source_agent_id,
                accepted_changesets=accepted_changesets,
                conflicts=conflicts,
                artifacts=artifacts,
                reports=reports,
                test_results=test_results,
                metadata=metadata,
            )

    def _register_control_tools(self, mcp: Any) -> None:
        @mcp.tool()
        async def organization_read(agent_id: Optional[str] = None) -> Dict[str, Any]:
            return await self._control_request(
                _require_scope("control", "organization_read"),
                tool_name="organization_read",
                command="organization.read",
                args={"agent_id": agent_id},
                permission="status",
            )

        @mcp.tool()
        async def top_agent_context() -> Dict[str, Any]:
            return await self._control_request(
                _require_scope("control", "top_agent_context"),
                tool_name="top_agent_context",
                command="top_agent.context",
                args={},
                permission="status",
            )

        @mcp.tool()
        async def runtime_agent_context(agent_id: Optional[str] = None) -> Dict[str, Any]:
            result = await self._control_request(
                _require_scope("control", "runtime_agent_context"),
                tool_name="runtime_agent_context",
                command="top_agent.context",
                args={"agent_id": agent_id},
                permission="status",
            )
            result.setdefault("agent_id", agent_id)
            return result

        @mcp.tool()
        async def top_agent_explain_status(recent_events_limit: int = 20) -> Dict[str, Any]:
            return await self._control_request(
                _require_scope("control", "top_agent_explain_status"),
                tool_name="top_agent_explain_status",
                command="top_agent.explain_status",
                args={"recent_events_limit": int(recent_events_limit)},
                permission="status",
            )

        @mcp.tool()
        async def runtime_explain_status(recent_events_limit: int = 20) -> Dict[str, Any]:
            return await self._control_request(
                _require_scope("control", "runtime_explain_status"),
                tool_name="runtime_explain_status",
                command="top_agent.explain_status",
                args={"recent_events_limit": int(recent_events_limit)},
                permission="status",
            )

        @mcp.tool()
        async def top_agent_utterances(
            task_id: Optional[str] = None,
            agent_id: Optional[str] = None,
            node_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            return await self._control_request(
                _require_scope("control", "top_agent_utterances"),
                tool_name="top_agent_utterances",
                command="top_agent.utterances",
                args={"task_id": task_id, "agent_id": agent_id, "node_id": node_id},
                permission="utterances",
            )

        @mcp.tool()
        async def runtime_top_agent_utterances(
            task_id: Optional[str] = None,
            agent_id: Optional[str] = None,
            node_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            return await self._control_request(
                _require_scope("control", "runtime_top_agent_utterances"),
                tool_name="runtime_top_agent_utterances",
                command="top_agent.utterances",
                args={"task_id": task_id, "agent_id": agent_id, "node_id": node_id},
                permission="utterances",
            )

        @mcp.tool()
        async def runtime_validate_start(plan: dict[str, Any]) -> Dict[str, Any]:
            return await self._control_request(
                _require_scope("control", "runtime_validate_start"),
                tool_name="runtime_validate_start",
                command="run.validate_start",
                args={"plan": plan},
                permission="start",
            )

        @mcp.tool()
        async def top_agent_request_user_input(
            questions: list[dict[str, Any]],
        ) -> Dict[str, Any]:
            scope = _require_scope("control", "top_agent_request_user_input")
            _require_control_permission(scope, "ask")
            clean_questions = [
                dict(item)
                for item in (questions or [])
                if isinstance(item, dict)
            ]
            self._record_mcp_tool_call(
                scope,
                "top_agent_request_user_input",
                {"questions": clean_questions},
            )
            if self.request_user_input_callback is None:
                result = {
                    "ok": False,
                    "status": "unsupported",
                    "error": "top-agent user input requests are not configured for this runtime",
                }
                await self._notify_control_call(
                    scope,
                    tool_name="top_agent_request_user_input",
                    command="top_agent.request_user_input",
                    args={"questions": clean_questions},
                    result=result,
                    error=None,
                )
                return result
            result = await asyncio.to_thread(self.request_user_input_callback, clean_questions)
            payload = dict(result) if isinstance(result, dict) else {"ok": True, "answers": result}
            await self._notify_control_call(
                scope,
                tool_name="top_agent_request_user_input",
                command="top_agent.request_user_input",
                args={"questions": clean_questions},
                result=payload,
                error=None,
            )
            return payload

        @mcp.tool()
        async def top_agent_stage_start_plan(
            plan: dict[str, Any],
            plan_markdown: str = "",
        ) -> Dict[str, Any]:
            scope = _require_scope("control", "top_agent_stage_start_plan")
            _require_control_permission(scope, "start")
            clean_plan = dict(plan or {})
            clean_markdown = str(plan_markdown or "")
            self._record_mcp_tool_call(
                scope,
                "top_agent_stage_start_plan",
                {"plan": clean_plan, "plan_markdown": clean_markdown},
            )
            if self.stage_start_plan_callback is None:
                result = {
                    "ok": False,
                    "status": "unsupported",
                    "error": "top-agent start plan staging is not configured for this runtime",
                }
                await self._notify_control_call(
                    scope,
                    tool_name="top_agent_stage_start_plan",
                    command="top_agent.stage_start_plan",
                    args={"plan": clean_plan, "plan_markdown": clean_markdown},
                    result=result,
                    error=None,
                )
                return result
            result = await asyncio.to_thread(
                self.stage_start_plan_callback,
                clean_plan,
                clean_markdown,
            )
            payload = dict(result) if isinstance(result, dict) else {"ok": True, "result": result}
            await self._notify_control_call(
                scope,
                tool_name="top_agent_stage_start_plan",
                command="top_agent.stage_start_plan",
                args={"plan": clean_plan, "plan_markdown": clean_markdown},
                result=payload,
                error=None,
            )
            return payload

        @mcp.tool()
        async def runtime_start(
            plan: dict[str, Any],
            manifest_path: Optional[str] = None,
            prestart_all_agents: bool = False,
        ) -> Dict[str, Any]:
            return await self._control_request(
                _require_scope("control", "runtime_start"),
                tool_name="runtime_start",
                command="run.start",
                args={
                    "plan": plan,
                    "manifest_path": manifest_path,
                    "prestart_all_agents": bool(prestart_all_agents),
                },
                permission="start",
            )

        @mcp.tool()
        async def runtime_execute_fixture(
            plan: dict[str, Any],
            runtime_scenarios: Optional[dict[str, Any]] = None,
            manifest_path: Optional[str] = None,
            archive: bool = True,
        ) -> Dict[str, Any]:
            return await self._control_request(
                _require_scope("control", "runtime_execute_fixture"),
                tool_name="runtime_execute_fixture",
                command="run.execute_fixture",
                args={
                    "plan": plan,
                    "runtime_scenarios": runtime_scenarios or {},
                    "manifest_path": manifest_path,
                    "archive": bool(archive),
                },
                permission="fixture",
            )

        @mcp.tool()
        async def runtime_status(recent_events_limit: int = 20) -> Dict[str, Any]:
            return await self._control_request(
                _require_scope("control", "runtime_status"),
                tool_name="runtime_status",
                command="run.status",
                args={"recent_events_limit": int(recent_events_limit)},
                permission="status",
            )

        @mcp.tool()
        async def runtime_end(
            action: str,
            reason: str = "",
            archive: bool = False,
        ) -> Dict[str, Any]:
            return await self._runtime_end(
                _require_scope("control", "runtime_end"),
                tool_name="runtime_end",
                action=action,
                reason=reason,
                archive=archive,
            )

        @mcp.tool()
        async def runtime_message_batch(
            source_node_id: str,
            required_target_node_ids: list[str],
            batch_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            return await self._control_request(
                _require_scope("control", "runtime_message_batch"),
                tool_name="runtime_message_batch",
                command="message.create_batch",
                args={
                    "source_node_id": source_node_id,
                    "required_target_node_ids": required_target_node_ids,
                    "batch_id": batch_id,
                },
                permission="start",
            )

        @mcp.tool()
        async def runtime_message_stage(
            batch_id: str,
            target_node_id: str,
            body: Any,
        ) -> Dict[str, Any]:
            return await self._control_request(
                _require_scope("control", "runtime_message_stage"),
                tool_name="runtime_message_stage",
                command="message.stage",
                args={"batch_id": batch_id, "target_node_id": target_node_id, "body": body},
                permission="start",
            )

        @mcp.tool()
        async def agent_context(
            source_node_id: str,
            batch_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            return await self._control_request(
                _require_scope("control", "agent_context"),
                tool_name="agent_context",
                command="agent.context",
                args={"source_node_id": source_node_id, "batch_id": batch_id},
                permission="status",
            )

        @mcp.tool()
        async def agent_dispatch(
            source_node_id: str,
            target_node_id: str,
            body: Any,
            batch_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            return await self._control_request(
                _require_scope("control", "agent_dispatch"),
                tool_name="agent_dispatch",
                command="agent.dispatch",
                args={
                    "source_node_id": source_node_id,
                    "target_node_id": target_node_id,
                    "body": body,
                    "batch_id": batch_id,
                },
                permission="start",
            )

        @mcp.tool()
        async def join_create(
            required_source_node_ids: list[str],
            target_node_id: Optional[str] = None,
            policy: str = "wait-all",
            quorum: Optional[int] = None,
            timeout_sec: Optional[float] = None,
            join_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            return await self._control_request(
                _require_scope("control", "join_create"),
                tool_name="join_create",
                command="join.create",
                args={
                    "join_id": join_id,
                    "target_node_id": target_node_id,
                    "required_source_node_ids": required_source_node_ids,
                    "policy": policy,
                    "quorum": quorum,
                    "timeout_sec": timeout_sec,
                },
                permission="start",
            )

        @mcp.tool()
        async def join_contribute(
            join_id: str,
            source_node_id: str,
            status: str = "completed",
            result: Any = None,
            source_agent_id: Optional[str] = None,
            accepted_changesets: Optional[list[dict[str, Any]]] = None,
            conflicts: Optional[list[dict[str, Any]]] = None,
            artifacts: Optional[list[dict[str, Any]]] = None,
            reports: Optional[list[dict[str, Any]]] = None,
            test_results: Optional[list[dict[str, Any]]] = None,
            metadata: Optional[dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            return await self._control_request(
                _require_scope("control", "join_contribute"),
                tool_name="join_contribute",
                command="join.contribute",
                args={
                    "join_id": join_id,
                    "source_node_id": source_node_id,
                    "status": status,
                    "result": result,
                    "source_agent_id": source_agent_id,
                    "accepted_changesets": accepted_changesets or [],
                    "conflicts": conflicts or [],
                    "artifacts": artifacts or [],
                    "reports": reports or [],
                    "test_results": test_results or [],
                    "metadata": metadata or {},
                },
                permission="start",
            )

        allowed = set(self.control_allowed_tools or _control_tools_for_permissions(self._top_agent_permissions()))
        for tool_name in CONTROL_TOOL_NAMES:
            if tool_name not in allowed:
                mcp.remove_tool(tool_name)

    async def _control_request(
        self,
        scope: MCPTokenScope,
        *,
        tool_name: str,
        command: str,
        args: Dict[str, Any],
        permission: str,
    ) -> Dict[str, Any]:
        _require_allowed_tool(scope, tool_name)
        _require_control_permission(scope, permission)
        clean_args = {
            key: value
            for key, value in args.items()
            if value is not None
        }
        self._record_mcp_tool_call(scope, tool_name, clean_args)
        try:
            result = await self._maybe_override_control_command(
                scope,
                tool_name=tool_name,
                command=command,
                args=clean_args,
            )
            if result is None:
                result = await self._dispatch_control_command(command, clean_args)
            payload = dict(result) if isinstance(result, dict) else {"ok": True, "result": result}
            await self._notify_control_call(
                scope,
                tool_name=tool_name,
                command=command,
                args=clean_args,
                result=payload,
                error=None,
            )
            return payload
        except Exception as exc:
            await self._notify_control_call(
                scope,
                tool_name=tool_name,
                command=command,
                args=clean_args,
                result=None,
                error=str(exc),
            )
            raise

    async def _maybe_override_control_command(
        self,
        scope: MCPTokenScope,
        *,
        tool_name: str,
        command: str,
        args: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        callback = self.control_command_callback
        if callback is None:
            return None
        result = callback(
            scope=scope,
            tool_name=tool_name,
            command=command,
            args=dict(args),
        )
        if asyncio.iscoroutine(result):
            result = await result
        return dict(result) if isinstance(result, dict) else result

    async def _notify_control_call(
        self,
        scope: MCPTokenScope,
        *,
        tool_name: str,
        command: str,
        args: Dict[str, Any],
        result: Optional[Dict[str, Any]],
        error: Optional[str],
    ) -> None:
        observer = self.control_call_observer
        if observer is None:
            return
        try:
            observed = observer(
                scope=scope,
                tool_name=tool_name,
                command=command,
                args=_safe_mcp_args(args),
                result=dict(result) if isinstance(result, dict) else result,
                error=error,
            )
            if asyncio.iscoroutine(observed):
                await observed
        except Exception:
            return

    async def _dispatch_control_command(self, command: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if command == "run.start":
            from .graph_runtime import TopAgentStartPlan

            return await self._runtime_coro(
                lambda: self.control.start_run(
                    TopAgentStartPlan.from_dict(dict(args["plan"])),
                    manifest_path=_control_manifest_path(self.workspace_run, args.get("manifest_path")),
                    prestart_all_agents=bool(args.get("prestart_all_agents", False)),
                )
            )
        if command == "run.execute_fixture":
            from .graph_runtime import TopAgentStartPlan

            return await self._runtime_coro(
                lambda: self.control.execute_fixture_to_archive(
                    TopAgentStartPlan.from_dict(dict(args["plan"])),
                    runtime_scenarios=dict(args.get("runtime_scenarios", {})),
                    manifest_path=_control_manifest_path(self.workspace_run, args.get("manifest_path")),
                    archive=bool(args.get("archive", True)),
                )
            )
        if command == "message.create_batch":
            return await self._runtime_coro(
                lambda: self.control._create_message_batch(
                    str(args["source_node_id"]),
                    [str(item) for item in args.get("required_target_node_ids", [])],
                    batch_id=args.get("batch_id"),
                )
            )
        if command == "agent.dispatch":
            return await self._runtime_coro(
                lambda: self.control.dispatch_agent_message(
                    str(args["source_node_id"]),
                    str(args["target_node_id"]),
                    args.get("body"),
                    batch_id=(
                        str(args["batch_id"])
                        if args.get("batch_id") is not None
                        else None
                    ),
                )
            )
        return await self._runtime_call(
            lambda: self.control.handle_request({"command": command, "args": args})
        )

    async def _runtime_end(
        self,
        scope: MCPTokenScope,
        *,
        tool_name: str,
        action: str,
        reason: str,
        archive: bool,
    ) -> Dict[str, Any]:
        _require_allowed_tool(scope, tool_name)
        _require_control_permission(scope, "end")
        self._record_mcp_tool_call(
            scope,
            tool_name,
            {"action": action, "reason": reason, "archive": bool(archive)},
        )
        callback = self.close_run_callback
        if callback is not None:
            result = callback(action=str(action), reason=str(reason), archive=bool(archive))
            if asyncio.iscoroutine(result):
                result = await result
        else:
            result = await self._runtime_call(
                lambda: self.runtime.end_run(
                    str(action),
                    reason=str(reason),
                    archive=bool(archive),
                ).to_dict()
            )
        self.token_store.close()
        return dict(result)

    async def _ordinary_agent_context(
        self,
        scope: MCPTokenScope,
        *,
        batch_id: Optional[str],
    ) -> Dict[str, Any]:
        if scope.agent_node_id is None:
            raise PermissionError("ordinary MCP token is not bound to an AgentNode")
        _require_allowed_tool(scope, "agent_context")
        context = scope.current_message_context
        if context is not None and context.expires_at < float(self.token_store.now()):
            raise PermissionError("active message context has expired")
        if batch_id is not None and context is not None and batch_id != context.outgoing_batch_id:
            raise PermissionError("ordinary agent_context cannot read another message batch")
        effective_batch_id = batch_id or (context.outgoing_batch_id if context is not None else None)
        args = {"source_node_id": scope.agent_node_id, "batch_id": effective_batch_id}
        self._record_mcp_tool_call(scope, "agent_context", args)
        return await self._runtime_call(
            lambda: self.control.handle_request({"command": "agent.context", "args": args})
        )

    async def _ordinary_join_contribute(
        self,
        scope: MCPTokenScope,
        *,
        join_id: str,
        status: str,
        result: Any,
        source_node_id: Optional[str],
        source_agent_id: Optional[str],
        accepted_changesets: Optional[list[dict[str, Any]]],
        conflicts: Optional[list[dict[str, Any]]],
        artifacts: Optional[list[dict[str, Any]]],
        reports: Optional[list[dict[str, Any]]],
        test_results: Optional[list[dict[str, Any]]],
        metadata: Optional[dict[str, Any]],
    ) -> Dict[str, Any]:
        if scope.agent_node_id is None:
            raise PermissionError("ordinary MCP token is not bound to an AgentNode")
        _require_allowed_tool(scope, "join_contribute")
        if source_node_id is not None and str(source_node_id) != scope.agent_node_id:
            raise PermissionError("ordinary MCP token cannot join_contribute as another AgentNode")
        if source_agent_id is not None and scope.agent_id is not None and str(source_agent_id) != scope.agent_id:
            raise PermissionError("ordinary MCP token cannot join_contribute as another agent_id")
        args = {
            "join_id": join_id,
            "source_node_id": scope.agent_node_id,
            "status": status,
            "result": result,
            "source_agent_id": scope.agent_id,
            "accepted_changesets": accepted_changesets or [],
            "conflicts": conflicts or [],
            "artifacts": artifacts or [],
            "reports": reports or [],
            "test_results": test_results or [],
            "metadata": metadata or {},
        }
        self._record_mcp_tool_call(scope, "join_contribute", args)
        return await self._runtime_call(
            lambda: self.control.handle_request({"command": "join.contribute", "args": args})
        )

    def _record_mcp_tool_call(
        self,
        scope: MCPTokenScope,
        tool_name: str,
        args: Dict[str, Any],
    ) -> None:
        payload = {
            "workspace_event": "FrameworkMCPToolCalled",
            "run_id": self.run_id,
            "server_kind": scope.server_kind,
            "agent_id": scope.agent_id,
            "node_id": scope.agent_node_id,
            "tool_name": str(tool_name),
            "args": _safe_mcp_args(args),
        }
        record = getattr(self.manager, "_record_shared_manifest", None)
        if not callable(record):
            return
        try:
            record(self.workspace_run, MCP_TOOL_AUDIT_EVENT, payload)
        except Exception:
            return

    def _workspace_request(
        self,
        scope: MCPTokenScope,
        command: str,
        args: Dict[str, Any],
    ) -> Dict[str, Any]:
        if scope.server_kind != "ordinary":
            raise PermissionError("workspace tools require an ordinary MCP token")
        if not scope.workspace_rpc_token or not scope.agent_id:
            raise PermissionError("ordinary MCP token is missing workspace RPC scope")
        tool_name = f"workspace_{command.replace('-', '_')}"
        _require_allowed_tool(scope, tool_name)
        clean_args = {
            key: value
            for key, value in args.items()
            if value is not None
        }
        self._record_mcp_tool_call(
            scope,
            tool_name,
            clean_args,
        )
        clean_args["owner"] = scope.agent_id
        return self.workspace_rpc_server.handle_request(
            {
                "token": scope.workspace_rpc_token,
                "command": command,
                "args": clean_args,
            }
        )

    async def _agent_dispatch(
        self,
        scope: MCPTokenScope,
        *,
        target_node_id: str,
        body: Any,
        batch_id: Optional[str],
        source_node_id: Optional[str],
    ) -> Dict[str, Any]:
        _require_allowed_tool(scope, "agent_dispatch")
        if scope.agent_node_id is None:
            raise PermissionError("ordinary MCP token is not bound to an AgentNode")
        if source_node_id is not None and str(source_node_id) != scope.agent_node_id:
            raise PermissionError("ordinary MCP token cannot dispatch as another AgentNode")
        context = scope.current_message_context
        if context is None:
            raise PermissionError("agent_dispatch requires an active message context")
        if context.expires_at < float(self.token_store.now()):
            raise PermissionError("active message context has expired")
        effective_batch_id = str(batch_id or context.outgoing_batch_id or "").strip()
        if not effective_batch_id:
            raise PermissionError("agent_dispatch requires the current outgoing batch_id")
        target = str(target_node_id).strip()
        if target not in context.required_outgoing_targets:
            raise PermissionError("target is not in current required_outgoing_targets")
        self._record_mcp_tool_call(
            scope,
            "agent_dispatch",
            {
                "target_node_id": target_node_id,
                "body": body,
                "batch_id": effective_batch_id,
                "source_node_id": source_node_id,
            },
        )
        return await self._runtime_coro(
            lambda: self.control.dispatch_agent_message(
                scope.agent_node_id,
                target,
                body,
                batch_id=effective_batch_id,
            )
        )

    async def _runtime_call(self, fn: Callable[[], Any]) -> Any:
        if self.runtime_loop is None:
            return fn()
        return await asyncio.to_thread(lambda: self.runtime_loop.call(fn))

    async def _runtime_coro(self, fn: Callable[[], Any]) -> Any:
        if self.runtime_loop is None:
            return await fn()
        return await asyncio.to_thread(lambda: self.runtime_loop.run(fn()))


ORDINARY_TOOL_NAMES = [
    "workspace_checkout",
    "workspace_status",
    "workspace_diff",
    "workspace_submit",
    "workspace_sync",
    "workspace_publish",
    "workspace_publish_file",
    "agent_dispatch",
    "agent_context",
    "join_contribute",
]

DEFAULT_CONTROL_PERMISSIONS = ["ask", "start", "status", "end", "utterances"]

CONTROL_TOOL_NAMES_BY_PERMISSION = {
    "ask": [],
    "start": [
        "runtime_validate_start",
        "runtime_start",
        "runtime_message_batch",
        "runtime_message_stage",
        "agent_dispatch",
        "join_create",
        "join_contribute",
    ],
    "status": [
        "organization_read",
        "top_agent_context",
        "runtime_agent_context",
        "top_agent_explain_status",
        "runtime_explain_status",
        "runtime_status",
        "agent_context",
    ],
    "end": [
        "runtime_end",
    ],
    "utterances": [
        "top_agent_utterances",
        "runtime_top_agent_utterances",
    ],
    "fixture": [
        "runtime_execute_fixture",
    ],
}

CONTROL_TOOL_NAMES = [
    tool
    for permission in ["ask", "start", "status", "end", "utterances", "fixture"]
    for tool in CONTROL_TOOL_NAMES_BY_PERMISSION[permission]
] + [
    "top_agent_request_user_input",
    "top_agent_stage_start_plan",
]

TOP_AGENT_PLANNING_CONTROL_TOOLS = [
    "organization_read",
    "top_agent_context",
    "runtime_agent_context",
    "top_agent_explain_status",
    "runtime_explain_status",
    "runtime_status",
    "top_agent_utterances",
    "runtime_top_agent_utterances",
    "runtime_validate_start",
    "top_agent_request_user_input",
    "top_agent_stage_start_plan",
]


def _normalized_control_permissions(permissions: Optional[Sequence[str]]) -> list[str]:
    raw = permissions if permissions is not None else DEFAULT_CONTROL_PERMISSIONS
    normalized: list[str] = []
    for item in raw:
        value = str(item).strip().lower()
        if not value:
            continue
        if value not in CONTROL_TOOL_NAMES_BY_PERMISSION:
            continue
        if value not in normalized:
            normalized.append(value)
    return normalized


def _control_tools_for_permissions(permissions: Optional[Sequence[str]]) -> list[str]:
    tools: list[str] = []
    for permission in _normalized_control_permissions(permissions):
        for tool in CONTROL_TOOL_NAMES_BY_PERMISSION[permission]:
            if tool not in tools:
                tools.append(tool)
    return tools


def _normalized_control_tools(tools: Optional[Sequence[str]]) -> list[str]:
    if tools is None:
        return []
    known = set(CONTROL_TOOL_NAMES)
    normalized: list[str] = []
    for item in tools:
        value = str(item).strip()
        if not value or value not in known or value in normalized:
            continue
        normalized.append(value)
    return normalized


def _require_allowed_tool(scope: MCPTokenScope, tool_name: str) -> None:
    if str(tool_name) not in set(scope.allowed_tools):
        raise PermissionError(f"MCP tool is not enabled for this token scope: {tool_name}")


def _require_control_permission(scope: MCPTokenScope, permission: str) -> None:
    if scope.server_kind != "control":
        raise PermissionError("control permission checks require a control MCP token")
    if str(permission).strip().lower() not in set(scope.control_permissions):
        raise PermissionError(f"control MCP token is missing permission: {permission}")


def _control_manifest_path(workspace_run: Any, raw_path: Any) -> Optional[Path]:
    if raw_path is None:
        return None
    value = str(raw_path).strip()
    if not value:
        return None
    shared_dir = getattr(workspace_run, "shared_dir", None)
    if shared_dir is None:
        raise PermissionError("control manifest_path requires a run shared directory")
    root = Path(shared_dir).resolve()
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PermissionError("control manifest_path must stay inside the run shared directory") from exc
    return resolved


def resolve_allowed_publish_file(scope: MCPTokenScope, raw_path: str) -> Path:
    if scope.server_kind != "ordinary":
        raise PermissionError("publish_file path validation requires an ordinary MCP token")
    value = str(raw_path or "").strip()
    if not value:
        raise ValueError("file_path is required")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        if ":" in value:
            raise PermissionError("relative file_path must not contain a drive or URI separator")
        if any(part in {"", ".", ".."} for part in candidate.parts):
            raise PermissionError("relative file_path must stay inside authorized private Agent roots")
        if scope.checkout_dir is None:
            raise PermissionError("relative file_path requires a private checkout root")
        candidate = scope.checkout_dir / candidate
    resolved = candidate.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"file_path is not a file: {raw_path}")
    for root in scope.allowed_file_roots:
        try:
            resolved.relative_to(Path(root).resolve())
            return resolved
        except ValueError:
            continue
    raise PermissionError("file_path is outside authorized private Agent roots")


def _require_scope(server_kind: str, tool_name: Optional[str] = None) -> MCPTokenScope:
    scope = _current_scope.get()
    if scope is None:
        raise PermissionError("MCP tool call is missing an authenticated token scope")
    if scope.server_kind != server_kind:
        raise PermissionError(f"MCP tool requires a {server_kind} token")
    if tool_name is not None:
        _require_allowed_tool(scope, tool_name)
    return scope


def _bearer_token(raw: str) -> Optional[str]:
    prefix = "Bearer "
    if not raw.startswith(prefix):
        return None
    value = raw[len(prefix) :].strip()
    return value or None


async def _send_json(send: Any, status: int, payload: Dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": int(status),
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(data)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": data})


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _mcp_private_context(
    *,
    server_kind: str,
    server_name: str,
    url: str,
    token_env: str,
    token: str,
    tools: Sequence[str],
) -> Dict[str, Any]:
    return {
        "enabled": True,
        "server_kind": server_kind,
        "server_name": server_name,
        "url": url,
        "bearer_token_env_var": token_env,
        "bearer_token": token,
        "tools": list(tools),
    }


def _framework_context_from_body(body: Any) -> Dict[str, Any]:
    if not isinstance(body, dict):
        return {}
    context = body.get("context")
    if isinstance(context, str):
        try:
            context = json.loads(context)
        except json.JSONDecodeError:
            return {}
    if not isinstance(context, dict):
        return {}
    framework_context = context.get("framework_context")
    return dict(framework_context) if isinstance(framework_context, dict) else {}
