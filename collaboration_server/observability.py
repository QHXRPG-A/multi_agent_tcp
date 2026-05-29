from __future__ import annotations

import json
import logging
import re
import time
from contextvars import ContextVar, Token
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional


LOGGER_NAME = "multi_agent_tcp.collaboration_server"
LOG_FILE_NAME = "collaboration_server.log"
MAX_STRING_LENGTH = 1024
MAX_LIST_ITEMS = 50
MAX_DICT_ITEMS = 80
MAX_DEPTH = 6

SENSITIVE_KEY_PARTS = (
    "authorization",
    "bearer",
    "cookie",
    "csrf",
    "password",
    "secret",
    "session",
    "token",
)
SENSITIVE_PATH_KEY_PARTS = (
    "absolute_path",
    "checkout",
    "codex_home",
    "cwd",
    "path",
    "projectdir",
    "project_dir",
    "workspace",
)
WINDOWS_PATH_RE = re.compile(r"\b[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n]+\\?)+")
POSIX_PATH_RE = re.compile(r"(?<!:)\/(?:Users|home|tmp|var|opt|etc|mnt|src|workspace)\/[^\s\"']+")
INLINE_SECRET_RE = re.compile(r"(?i)\b(token|secret|password|cookie|csrf)\b\s*[:= ]+\s*[^,\s;]+")


logger = logging.getLogger(LOGGER_NAME)
logger.addHandler(logging.NullHandler())
_request_context: ContextVar[dict[str, Any]] = ContextVar("collaboration_request_context", default={})


def configure_observability(
    *,
    log_dir: str | Path,
    log_level: str = "INFO",
    max_bytes: int = 1_000_000,
    backup_count: int = 5,
) -> logging.Logger:
    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, str(log_level or "INFO").upper(), logging.INFO)

    target = directory / LOG_FILE_NAME
    for handler in list(logger.handlers):
        if getattr(handler, "_gulicode_collaboration_handler", False):
            logger.removeHandler(handler)
            handler.close()

    handler = RotatingFileHandler(target, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler._gulicode_collaboration_handler = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def log_event(
    level: str,
    event: str,
    *,
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    path: Optional[str] = None,
    status: Optional[int] = None,
    duration_ms: Optional[float] = None,
    message: Optional[str] = None,
    **context: Any,
) -> None:
    numeric_level = getattr(logging, str(level or "INFO").upper(), logging.INFO)
    active_context = _request_context.get()
    request_id = request_id if request_id is not None else active_context.get("request_id")
    user_id = user_id if user_id is not None else active_context.get("user_id")
    path = path if path is not None else active_context.get("path")
    record: dict[str, Any] = {
        "ts": _iso_now(),
        "level": logging.getLevelName(numeric_level).lower(),
        "event": event,
        "request_id": request_id,
        "user_id": user_id,
        "path": path,
        "status": status,
        "duration_ms": round(float(duration_ms), 2) if duration_ms is not None else None,
    }
    if message:
        record["message"] = scrub_log_value(message)
    for key, value in context.items():
        if value is not None:
            record[key] = scrub_log_value(value)
    logger.log(numeric_level, json.dumps(record, ensure_ascii=False, sort_keys=True, default=str))


def set_log_context(**context: Any) -> Token[dict[str, Any]]:
    active = dict(_request_context.get())
    for key, value in context.items():
        if value is not None:
            active[key] = value
    return _request_context.set(active)


def reset_log_context(token: Token[dict[str, Any]]) -> None:
    _request_context.reset(token)


def scrub_log_value(value: Any, *, _depth: int = 0) -> Any:
    if _depth >= MAX_DEPTH:
        return "[truncated]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_DICT_ITEMS:
                result["[truncated]"] = len(value) - MAX_DICT_ITEMS
                break
            key_text = str(key)
            lowered = key_text.lower().replace("-", "_")
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                result[key_text] = "[redacted]"
            elif any(part in lowered for part in SENSITIVE_PATH_KEY_PARTS):
                result[key_text] = _redact_path_value(item)
            else:
                result[key_text] = scrub_log_value(item, _depth=_depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        items = list(value)
        result = [scrub_log_value(item, _depth=_depth + 1) for item in items[:MAX_LIST_ITEMS]]
        if len(items) > MAX_LIST_ITEMS:
            result.append({"[truncated]": len(items) - MAX_LIST_ITEMS})
        return result
    if isinstance(value, str):
        text = INLINE_SECRET_RE.sub(lambda match: f"{match.group(1)}=[redacted]", value)
        text = WINDOWS_PATH_RE.sub("[redacted-path]", text)
        text = POSIX_PATH_RE.sub("[redacted-path]", text)
        if len(text) > MAX_STRING_LENGTH:
            return f"{text[:MAX_STRING_LENGTH]}...[truncated]"
        return text
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return scrub_log_value(str(value), _depth=_depth + 1)


def client_log_context(value: Any) -> dict[str, Any]:
    scrubbed = scrub_log_value(value if isinstance(value, dict) else {})
    return scrubbed if isinstance(scrubbed, dict) else {}


def clamp_message(value: Any, *, max_length: int = 1024) -> str:
    text = scrub_log_value("" if value is None else str(value))
    if not isinstance(text, str):
        text = str(text)
    return text[:max_length]


def _redact_path_value(value: Any) -> Any:
    if isinstance(value, str):
        if WINDOWS_PATH_RE.search(value) or POSIX_PATH_RE.search(value) or "\\" in value or "/" in value:
            return "[redacted]"
        return scrub_log_value(value)
    return "[redacted]"


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
