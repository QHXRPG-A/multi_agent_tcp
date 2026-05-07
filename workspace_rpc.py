from __future__ import annotations

import base64
import json
import secrets
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from .workspace_manager import DulwichWorkspaceManager, RunWorkspace


VALID_AREAS = {"artifacts", "reports"}


def _area_path(area: str, rel_path: str = "") -> str:
    if area not in VALID_AREAS:
        raise ValueError(f"invalid area {area!r}; expected one of {sorted(VALID_AREAS)}")
    normalized = rel_path.replace("\\", "/").strip("/")
    if normalized:
        parts = normalized.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("path must be a relative path inside the selected area")
        if ":" in normalized:
            raise ValueError("path must not contain a drive or URI separator")
        return f"{area}/{normalized}"
    return area


@dataclass
class WorkspaceRPCResponse:
    ok: bool
    data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, **self.data}


class WorkspaceRPCServer:
    def __init__(
        self,
        manager: DulwichWorkspaceManager,
        run: RunWorkspace,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        self.manager = manager
        self.run = run
        self.host = host
        self.port = port
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._token_by_agent: Dict[str, str] = {}
        self._agent_by_token: Dict[str, str] = {}

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("workspace RPC server is not started")
        return f"http://{self._server.server_address[0]}:{self._server.server_address[1]}/workspace"

    def start(self) -> None:
        if self._server is not None:
            return
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _write_json(self, payload: Dict[str, Any], *, status: int = 200) -> None:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path.rstrip("/") != "/workspace":
                    self._write_json({"ok": False, "error": "not found"}, status=404)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                try:
                    payload = json.loads(raw.decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError("request body must be a JSON object")
                    response = server.handle_request(payload)
                except Exception as exc:  # pragma: no cover - defensive server boundary
                    response = {"ok": False, "error": str(exc)}
                self._write_json(response)

            def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
                return

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._server = None
        self._thread = None

    def token_for(self, agent_id: str) -> str:
        if agent_id in self._token_by_agent:
            return self._token_by_agent[agent_id]
        token = secrets.token_urlsafe(24)
        self._token_by_agent[agent_id] = token
        self._agent_by_token[token] = agent_id
        return token

    def context_for(self, agent_id: str) -> Dict[str, Any]:
        return {
            "transport": "rpc",
            "rpc_url": self.url,
            "rpc_token": self.token_for(agent_id),
            "run_id": self.run.run_id,
            "agent_id": agent_id,
            "areas": sorted(VALID_AREAS),
            "workspace_scopes": ["run"],
            "vcs_commands": ["checkout", "status", "diff", "submit", "sync"],
            "archive_commands": ["list-archives", "extract-archive"],
        }

    def _resolve_agent(self, token: Optional[str]) -> str:
        if not token:
            raise PermissionError("missing workspace RPC token")
        try:
            return self._agent_by_token[token]
        except KeyError as exc:
            raise PermissionError("invalid workspace RPC token") from exc

    def handle_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        token = payload.get("token")
        agent_id = self._resolve_agent(token if isinstance(token, str) else None)
        command = str(payload.get("command", "")).strip()
        args = payload.get("args", {})
        if not isinstance(args, dict):
            raise ValueError("args must be a JSON object")

        owner = str(args.get("owner") or agent_id)

        if command == "publish":
            rel = _area_path(str(args["area"]), str(args["path"]))
            self.manager.write_shared_text(
                self.run,
                rel,
                str(args.get("text", "")),
                owner=owner,
                expected_version=args.get("expected_version"),
            )
            return WorkspaceRPCResponse(
                True,
                {
                    "area": args["area"],
                    "path": args["path"],
                    "owner": owner,
                    "version": self.manager.shared_file_version(self.run, rel),
                },
            ).to_dict()

        if command == "publish-file":
            rel = _area_path(str(args["area"]), str(args["path"]))
            data = base64.b64decode(str(args.get("data_b64", "")).encode("ascii"))
            self.manager.write_shared_bytes(
                self.run,
                rel,
                data,
                owner=owner,
                expected_version=args.get("expected_version"),
            )
            return WorkspaceRPCResponse(
                True,
                {
                    "area": args["area"],
                    "path": args["path"],
                    "owner": owner,
                    "bytes": len(data),
                    "version": self.manager.shared_file_version(self.run, rel),
                },
            ).to_dict()

        if command == "read":
            rel = _area_path(str(args["area"]), str(args["path"]))
            text = self.manager.read_shared_text(self.run, rel, owner=owner)
            if args.get("json"):
                return WorkspaceRPCResponse(
                    True,
                    {
                        "area": args["area"],
                        "path": args["path"],
                        "version": self.manager.shared_file_version(self.run, rel),
                        "text": text,
                    },
                ).to_dict()
            return WorkspaceRPCResponse(True, {"text": text}).to_dict()

        if command == "list":
            rel = _area_path(str(args["area"]), str(args.get("path", "")))
            prefix = f"{args['area']}/"
            files = [
                item[len(prefix) :] if item.startswith(prefix) else item
                for item in self.manager.list_shared_files(self.run, rel)
            ]
            return WorkspaceRPCResponse(
                True,
                {"area": args["area"], "path": args.get("path", ""), "files": files},
            ).to_dict()

        if command == "checkout":
            checkout = self.manager.checkout_agent(
                self.run,
                owner,
                write_scope=[str(s) for s in args.get("write_scope", [])],
                mode=str(args.get("mode", "full")),
            )
            data = checkout.to_dict()
            data["checkout_path"] = str(checkout.checkout_dir)
            return WorkspaceRPCResponse(True, data).to_dict()

        if command == "status":
            checkout = self.manager.open_agent_checkout(self.run, owner)
            files = [
                change.to_dict(include_patch=False)
                for change in self.manager.status_checkout(self.run, checkout)
            ]
            return WorkspaceRPCResponse(
                True,
                {"base_ref": checkout.base_ref, "files": files},
            ).to_dict()

        if command == "diff":
            checkout = self.manager.open_agent_checkout(self.run, owner)
            changes = self.manager.diff_checkout(self.run, checkout)
            wanted = str(args.get("path") or "").replace("\\", "/").strip("/")
            if wanted:
                changes = [change for change in changes if change.path == wanted]
            if args.get("summary"):
                return WorkspaceRPCResponse(
                    True,
                    {
                        "base_ref": checkout.base_ref,
                        "files": [change.to_dict(include_patch=False) for change in changes],
                    },
                ).to_dict()
            return WorkspaceRPCResponse(
                True,
                {"patch": "\n".join(change.patch or "" for change in changes if change.patch)},
            ).to_dict()

        if command == "submit":
            checkout = self.manager.open_agent_checkout(self.run, owner)
            result = self.manager.submit_checkout(
                self.run,
                checkout,
                task_id=args.get("task_id"),
                summary=str(args.get("summary") or ""),
            )
            return result.to_dict()

        if command == "sync":
            checkout = self.manager.open_agent_checkout(self.run, owner)
            checkout = self.manager.sync_checkout(self.run, checkout)
            return WorkspaceRPCResponse(
                True,
                {"checkout_id": checkout.checkout_id, "base_ref": checkout.base_ref},
            ).to_dict()

        if command == "list-archives":
            return WorkspaceRPCResponse(
                True,
                {"archives": self.manager.list_long_term_archives()},
            ).to_dict()

        if command == "extract-archive":
            path = self.manager.extract_long_term_archive(
                self.run,
                owner,
                str(args["archive_id"]),
                path=str(args.get("path") or ""),
            )
            return WorkspaceRPCResponse(
                True,
                {"archive_id": args["archive_id"], "path": str(path)},
            ).to_dict()

        raise ValueError(f"unsupported workspace RPC command: {command!r}")
