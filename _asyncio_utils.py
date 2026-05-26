from __future__ import annotations

import asyncio
import sys
from typing import Any


def _should_suppress_asyncio_connection_reset(context: dict[str, Any]) -> bool:
    """Return True for benign Windows Proactor connection-lost reset noise."""
    if sys.platform != "win32":
        return False
    exc = context.get("exception")
    if not isinstance(exc, ConnectionResetError):
        return False
    message = str(context.get("message") or "")
    handle = str(context.get("handle") or "")
    source = f"{message} {handle}"
    return "_call_connection_lost" in source or "_ProactorBasePipeTransport" in source


def install_asyncio_connection_reset_filter(loop: asyncio.AbstractEventLoop) -> None:
    previous = loop.get_exception_handler()

    def handler(event_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        if _should_suppress_asyncio_connection_reset(context):
            return
        if previous is not None:
            previous(event_loop, context)
        else:
            event_loop.default_exception_handler(context)

    loop.set_exception_handler(handler)


def windows_proactor_connection_reset_loop() -> asyncio.AbstractEventLoop:
    """Uvicorn custom loop entry that keeps Windows Proactor resets quiet."""
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.SelectorEventLoop()
    install_asyncio_connection_reset_filter(loop)
    return loop
