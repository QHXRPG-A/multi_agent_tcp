"""Process-tree cleanup helpers (Windows ``taskkill /T`` + POSIX ``killpg``)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Any, Dict

log = logging.getLogger(__name__)

_IS_WIN = sys.platform == "win32"


def hidden_subprocess_kwargs(*, detached: bool = False) -> Dict[str, Any]:
    """Return Popen kwargs that keep Windows console subprocesses hidden."""
    if not _IS_WIN:
        return {}

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    if detached:
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0x00000008)

    startupinfo = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
    startupinfo.wShowWindow = subprocess.SW_HIDE  # type: ignore[attr-defined]
    return {
        "creationflags": flags,
        "startupinfo": startupinfo,
    }


def kill_process_tree(pid: int, timeout: float = 10.0) -> None:
    """Kill *pid* and all of its child processes.

    Windows: ``taskkill /T /F /PID``.
    POSIX:   ``os.killpg`` with SIGTERM then SIGKILL fallback.
    """
    if _IS_WIN:
        _kill_tree_windows(pid, timeout)
    else:
        _kill_tree_posix(pid, timeout)


def terminate_and_wait(proc: subprocess.Popen, timeout: float = 10.0) -> None:
    """Try a graceful terminate; fall back to killing the whole tree."""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        log.warning("pid %s did not exit after terminate(); killing process tree", proc.pid)
        kill_process_tree(proc.pid, timeout=timeout)
    except OSError as e:
        log.debug("terminate_and_wait OSError pid=%s: %s", proc.pid, e)


async def async_kill_process_tree(pid: int, timeout: float = 10.0) -> None:
    """Async-friendly wrapper — runs :func:`kill_process_tree` in the default executor."""
    import asyncio

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, kill_process_tree, pid, timeout)


# -- Windows ----------------------------------------------------------------

def _kill_tree_windows(pid: int, timeout: float) -> None:
    try:
        result = subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            capture_output=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            log.debug("taskkill /T /F /PID %s rc=%s stderr=%s", pid, result.returncode, stderr)
    except FileNotFoundError:
        log.warning("taskkill not found; falling back to TerminateProcess for pid=%s", pid)
        _terminate_single(pid)
    except subprocess.TimeoutExpired:
        log.warning("taskkill timed out for pid=%s", pid)
    except OSError as e:
        log.debug("taskkill OSError pid=%s: %s", pid, e)


def _terminate_single(pid: int) -> None:
    """Last-resort: kill only the direct process via os.kill (Windows TerminateProcess)."""
    import signal

    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError) as e:
        log.debug("os.kill(%s) failed: %s", pid, e)


# -- POSIX -------------------------------------------------------------------

def _kill_tree_posix(pid: int, timeout: float) -> None:
    import signal
    import time

    try:
        pgid = os.getpgid(pid)
    except (ProcessLookupError, PermissionError):
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError) as e:
        log.debug("killpg SIGTERM pgid=%s: %s", pgid, e)
        return

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except (ProcessLookupError, PermissionError):
            return
        time.sleep(0.2)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError) as e:
        log.debug("killpg SIGKILL pgid=%s: %s", pgid, e)
