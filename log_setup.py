"""Centralised logging: stderr + RotatingFileHandler under ``multi_agent_tcp/logs/``."""

from __future__ import annotations

import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent / "logs"
_FMT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_MAX_BYTES = 20 * 1024 * 1024  # 20 MB
_BACKUP_COUNT = 5
_configured = False


def setup_logging(verbose: bool = False, name: str = "multi_agent_tcp") -> None:
    """Configure root logger with stderr + rotating file handler.

    Safe to call multiple times; only the first call takes effect.
    """
    global _configured
    if _configured:
        return
    _configured = True

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{name}_{ts}_{os.getpid()}.log"
    log_path = _LOG_DIR / filename

    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(_FMT)

    root = logging.getLogger()
    root.setLevel(level)

    stderr_h = logging.StreamHandler(sys.stderr)
    stderr_h.setLevel(level)
    stderr_h.setFormatter(formatter)
    root.addHandler(stderr_h)

    file_h = RotatingFileHandler(
        str(log_path), maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    file_h.setLevel(level)
    file_h.setFormatter(formatter)
    root.addHandler(file_h)

    logging.getLogger(__name__).debug("log file: %s", log_path)
