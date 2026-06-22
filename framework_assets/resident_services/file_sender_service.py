from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gulicode_blueprint_service import blueprint_service, service_method


SERVICE_NAME = "file_sender"
SERVICE_TITLE = "传文件服务"
SERVICE_DESCRIPTION = "将相关路径下的文件或图片传给当前会话的用户"


ACTION_SCHEMAS: dict[str, dict[str, Any]] = {
    "help": {
        "action": "help",
        "description": "Return method schemas for this service.",
        "parameters": {
            "action": {
                "type": "str",
                "required": False,
                "description": "Optional method name: help, send, or history.",
            },
        },
    },
    "send": {
        "action": "send",
        "description": (
            "Send a local image or file path to the current POPO session user. "
            "Agent callers should prefer the framework MCP tool "
            "`blueprint_send_popo_file(path)`; `blueprint_service_call` for "
            "file_sender.send is delegated by the framework when available."
        ),
        "parameters": {
            "path": {
                "type": "str",
                "required": True,
                "description": "Local filesystem path to an existing image or file.",
            },
        },
        "returns": {
            "ok": "bool",
            "sent": "bool",
            "record": "dict",
        },
    },
    "history": {
        "action": "history",
        "description": "Return file/image send history when a framework history bridge is available.",
        "parameters": {
            "limit": {
                "type": "int",
                "required": False,
                "default": 50,
                "description": "Maximum number of records to return.",
            },
        },
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _schema_payload(action: str = "") -> dict[str, Any]:
    requested = str(action or "").strip()
    allowed = sorted(ACTION_SCHEMAS)
    if requested:
        schema = ACTION_SCHEMAS.get(requested)
        if schema is None:
            return {
                "ok": False,
                "code": "UNKNOWN_ACTION",
                "error": f"unknown file_sender action: {requested}",
                "service": SERVICE_NAME,
                "title": SERVICE_TITLE,
                "allowedActions": allowed,
                "hint": "Call help() without action to inspect all method schemas.",
                "time": _now_iso(),
            }
        return {
            "ok": True,
            "service": SERVICE_NAME,
            "title": SERVICE_TITLE,
            "description": SERVICE_DESCRIPTION,
            "action": requested,
            "schema": schema,
            "time": _now_iso(),
        }
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "title": SERVICE_TITLE,
        "description": SERVICE_DESCRIPTION,
        "allowedActions": allowed,
        "methods": {name: ACTION_SCHEMAS[name] for name in allowed},
        "usage": {
            "preferred": "blueprint_send_popo_file(path)",
            "residentService": {
                "service_name": SERVICE_NAME,
                "method_name": "send",
                "arguments": {"path": "C:/path/to/file.png"},
            },
        },
        "time": _now_iso(),
    }


@blueprint_service(
    name="file_sender",
    title="传文件服务",
    description="将相关路径下的文件或图片传给当前会话的用户",
)
class FileSenderService:
    @service_method(name="help", description="Return file sender service method schemas.")
    def help(self, action: str = "") -> dict:
        return _schema_payload(action)

    @service_method(name="send", description="Send a local image or file to the current POPO session user.")
    def send(self, path: str) -> dict:
        file_path = Path(str(path or "").strip().strip('"').strip("'"))
        return {
            "ok": False,
            "code": "FRAMEWORK_TOOL_REQUIRED",
            "error": (
                "file_sender.send must be delegated by the Blueprint framework "
                "or replaced with a direct blueprint_send_popo_file(path) MCP call."
            ),
            "service": SERVICE_NAME,
            "action": "send",
            "path": str(file_path),
            "preferredTool": "blueprint_send_popo_file",
            "preferredArguments": {"path": str(file_path)},
            "time": _now_iso(),
        }

    @service_method(name="history", description="Return recent file/image send records when available.")
    def history(self, limit: int = 50) -> dict:
        safe_limit = max(1, min(int(limit or 50), 200))
        return {
            "ok": False,
            "code": "FRAMEWORK_HISTORY_API_REQUIRED",
            "error": "file send history is exposed through the Workbench session history API.",
            "service": SERVICE_NAME,
            "action": "history",
            "limit": safe_limit,
            "time": _now_iso(),
        }
