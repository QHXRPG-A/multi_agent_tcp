#!/usr/bin/env python
"""Machine/user-level singleton helpers for the gulicode-bp Codex plugin."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest


SERVICE_LOCK_FILENAME = "service.lock"
SERVICE_INFO_FILENAME = "service.json"
SERVICE_LOG_FILENAME = "service.log.jsonl"
SERVICE_HEARTBEAT_INTERVAL_SECONDS = 5.0
SERVICE_STALE_AFTER_SECONDS = 20.0
SERVICE_START_TIMEOUT_SECONDS = 20.0
SERVICE_SETTLE_TIMEOUT_SECONDS = 5.0


class SingletonServiceError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def service_lock_path(runtime_data_dir: Path) -> Path:
    return runtime_data_dir / SERVICE_LOCK_FILENAME


def service_info_path(runtime_data_dir: Path) -> Path:
    return runtime_data_dir / SERVICE_INFO_FILENAME


def service_log_path(runtime_data_dir: Path) -> Path:
    return runtime_data_dir / "logs" / SERVICE_LOG_FILENAME


def append_service_log(runtime_data_dir: Path, event: str, **details: Any) -> None:
    try:
        path = service_log_path(runtime_data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": utc_now(),
            "event": event,
            "pid": os.getpid(),
            **{key: json_safe(value) for key, value in details.items()},
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass


def read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def read_service_info(runtime_data_dir: Path) -> dict[str, Any] | None:
    return read_json_file(service_info_path(runtime_data_dir))


def write_service_info(runtime_data_dir: Path, payload: dict[str, Any]) -> None:
    runtime_data_dir.mkdir(parents=True, exist_ok=True)
    with service_info_path(runtime_data_dir).open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def hidden_creationflags() -> int:
    if sys.platform == "win32":
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return 0


def runtime_venv_root(runtime_python: Path) -> Path:
    if sys.platform == "win32" and runtime_python.parent.name.lower() == "scripts":
        return runtime_python.parent.parent
    if runtime_python.parent.name == "bin":
        return runtime_python.parent.parent
    return runtime_python.parent.parent


def runtime_site_packages(runtime_python: Path) -> Path | None:
    root = runtime_venv_root(runtime_python)
    if sys.platform == "win32":
        site_packages = root / "Lib" / "site-packages"
    else:
        version = f"python{sys.version_info.major}.{sys.version_info.minor}"
        site_packages = root / "lib" / version / "site-packages"
    return site_packages if site_packages.is_dir() else None


def base_python_for_runtime(runtime_python: Path) -> Path:
    if sys.platform != "win32":
        return runtime_python
    root = runtime_venv_root(runtime_python)
    config = root / "pyvenv.cfg"
    try:
        lines = config.read_text(encoding="utf-8").splitlines()
    except OSError:
        return runtime_python
    home = ""
    for line in lines:
        if line.strip().lower().startswith("home"):
            _, _, value = line.partition("=")
            home = value.strip()
            break
    if not home:
        return runtime_python
    candidate = Path(home) / "python.exe"
    return candidate if candidate.is_file() else runtime_python


def prepare_runtime_import_env(env: dict[str, str], runtime_python: Path) -> None:
    site_packages = runtime_site_packages(runtime_python)
    if site_packages is not None:
        existing = env.get("PYTHONPATH", "")
        parts = [str(site_packages)]
        if existing:
            parts.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(parts)
    root = runtime_venv_root(runtime_python)
    env.setdefault("VIRTUAL_ENV", str(root))
    scripts_dir = root / "Scripts" if sys.platform == "win32" else root / "bin"
    if scripts_dir.is_dir():
        env["PATH"] = str(scripts_dir) + os.pathsep + env.get("PATH", "")


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                creationflags=hidden_creationflags(),
                timeout=3,
            )
        except Exception:
            return False
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def terminate_process_tree(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=hidden_creationflags(),
                timeout=5,
            )
            return True
        os.kill(pid, 15)
        return True
    except Exception:
        return False


def _timestamp_age_seconds(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())


def service_heartbeat_stale(info: dict[str, Any]) -> bool:
    stale_after = float(info.get("staleAfterSeconds") or SERVICE_STALE_AFTER_SECONDS)
    age = _timestamp_age_seconds(info.get("heartbeatAt"))
    return age is None or age > stale_after


def _service_url(info: dict[str, Any]) -> str:
    return str(info.get("url") or "").rstrip("/")


def service_health_ok(info: dict[str, Any], *, timeout: float = 1.5) -> bool:
    if not isinstance(info, dict) or str(info.get("status") or "") != "running":
        return False
    url = _service_url(info)
    token = str(info.get("token") or "")
    if not url or not token:
        return False
    try:
        request = urlrequest.Request(
            f"{url}/health",
            headers={"Accept": "application/json", "X-Gulicode-Bp-Token": token},
        )
        with urlrequest.urlopen(request, timeout=timeout) as response:
            return 200 <= int(getattr(response, "status", 200)) < 300
    except Exception:
        return False


def wait_for_service_health(
    runtime_data_dir: Path,
    *,
    timeout: float = SERVICE_SETTLE_TIMEOUT_SECONDS,
    poll_interval: float = 0.2,
) -> dict[str, Any] | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = read_service_info(runtime_data_dir)
        if info and service_health_ok(info):
            return info
        time.sleep(poll_interval)
    return None


def _read_error_body(exc: urlerror.HTTPError) -> dict[str, Any] | None:
    try:
        raw = exc.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def service_rpc(
    runtime_data_dir: Path,
    command: str,
    args: dict[str, Any] | None = None,
    *,
    thread_id: str | None = None,
    request_kind: str = "read",
    timeout: float = 60.0,
) -> dict[str, Any]:
    info = read_service_info(runtime_data_dir)
    if not info or not service_health_ok(info):
        raise SingletonServiceError("SERVICE_UNAVAILABLE", "gulicode-bp singleton service is not running")
    token = str(info.get("token") or "")
    payload = {
        "token": token,
        "command": command,
        "args": args or {},
        "threadId": thread_id or "",
        "requestKind": request_kind,
    }
    request = urlrequest.Request(
        f"{_service_url(info)}/rpc",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Gulicode-Bp-Token": token,
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urlerror.HTTPError as exc:
        body = _read_error_body(exc)
        if body:
            raise SingletonServiceError(
                str(body.get("code") or "SERVICE_ERROR"),
                str(body.get("error") or body.get("message") or exc),
                status=int(getattr(exc, "code", 500) or 500),
                details=body.get("details") if isinstance(body.get("details"), dict) else {},
            ) from exc
        raise SingletonServiceError("SERVICE_ERROR", str(exc), status=int(getattr(exc, "code", 500) or 500)) from exc
    except Exception as exc:
        raise SingletonServiceError("SERVICE_ERROR", str(exc)) from exc
    try:
        decoded = json.loads(raw)
    except Exception as exc:
        raise SingletonServiceError("BAD_SERVICE_RESPONSE", "singleton service returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise SingletonServiceError("BAD_SERVICE_RESPONSE", "singleton service returned a non-object response")
    return decoded


class _ServiceStartLock:
    def __init__(self, runtime_data_dir: Path, *, timeout: float = SERVICE_START_TIMEOUT_SECONDS) -> None:
        self.runtime_data_dir = runtime_data_dir
        self.path = service_lock_path(runtime_data_dir)
        self.timeout = timeout
        self.fd: int | None = None

    def __enter__(self) -> "_ServiceStartLock":
        self.runtime_data_dir.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + self.timeout
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                payload = {
                    "pid": os.getpid(),
                    "createdAt": utc_now(),
                    "runtimeDataDir": str(self.runtime_data_dir),
                }
                os.write(self.fd, json.dumps(payload).encode("utf-8"))
                return self
            except FileExistsError:
                info = read_service_info(self.runtime_data_dir)
                if info and service_health_ok(info):
                    raise SingletonServiceError("SERVICE_ALREADY_RUNNING", "singleton service already started")
                lock_info = read_json_file(self.path) or {}
                lock_pid = int(lock_info.get("pid") or 0)
                lock_age = _timestamp_age_seconds(lock_info.get("createdAt"))
                if (lock_pid and not pid_is_running(lock_pid)) or (lock_age is not None and lock_age > self.timeout):
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                    except OSError:
                        pass
                    else:
                        append_service_log(self.runtime_data_dir, "stale-lock-cleaned", lockPid=lock_pid)
                        continue
                if time.time() >= deadline:
                    raise SingletonServiceError("SERVICE_LOCK_TIMEOUT", f"timed out acquiring {self.path}")
                time.sleep(0.2)

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.fd is not None:
            try:
                os.close(self.fd)
            finally:
                self.fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def _service_process_env(
    plugin_root: Path,
    runtime_python: Path,
    runtime_home: Path,
    runtime_data_dir: Path,
    *,
    token: str,
    extra_env: dict[str, str] | None = None,
) -> dict[str, str]:
    env = os.environ.copy()
    if extra_env:
        env.update({str(key): str(value) for key, value in extra_env.items()})
    env["GULICODE_BP_PLUGIN_ROOT"] = str(plugin_root)
    env["GULICODE_BP_RUNTIME_HOME"] = str(runtime_home)
    env["GULICODE_BP_DATA_DIR"] = str(runtime_data_dir)
    env["GULICODE_BP_SINGLETON_ROLE"] = "service"
    env["GULICODE_BP_SERVICE_TOKEN"] = token
    env["GULICODE_BP_RUNTIME_REEXECED"] = "1"
    env["GULICODE_BP_RUNTIME_PYTHON"] = str(runtime_python)
    prepare_runtime_import_env(env, runtime_python)
    env.setdefault("GULICODE_BP_DISABLE_REPO_FALLBACK", "1")
    return env


def ensure_singleton_service(
    plugin_root: Path,
    runtime_python: Path | str,
    runtime_home: Path,
    runtime_data_dir: Path,
    *,
    extra_env: dict[str, str] | None = None,
    timeout: float = SERVICE_START_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    plugin_root = plugin_root.expanduser().resolve()
    runtime_home = runtime_home.expanduser().resolve()
    runtime_data_dir = runtime_data_dir.expanduser().resolve()
    runtime_python = Path(runtime_python).expanduser().resolve()
    runtime_data_dir.mkdir(parents=True, exist_ok=True)

    info = read_service_info(runtime_data_dir)
    if info and service_health_ok(info):
        append_service_log(runtime_data_dir, "attach", servicePid=info.get("pid"), url=info.get("url"))
        return info

    try:
        with _ServiceStartLock(runtime_data_dir, timeout=timeout):
            info = read_service_info(runtime_data_dir)
            if info and service_health_ok(info):
                append_service_log(runtime_data_dir, "attach-after-lock", servicePid=info.get("pid"), url=info.get("url"))
                return info
            if info and not service_heartbeat_stale(info):
                settled = wait_for_service_health(runtime_data_dir)
                if settled:
                    append_service_log(
                        runtime_data_dir,
                        "attach-after-settle",
                        servicePid=settled.get("pid"),
                        url=settled.get("url"),
                    )
                    return settled
                append_service_log(
                    runtime_data_dir,
                    "unhealthy-service-cleanup",
                    servicePid=info.get("pid"),
                    url=info.get("url"),
                    heartbeatAt=info.get("heartbeatAt"),
                )

            if info:
                stale_pid = int(info.get("pid") or 0)
                if pid_is_running(stale_pid):
                    terminate_process_tree(stale_pid)
                    append_service_log(runtime_data_dir, "stale-service-terminated", stalePid=stale_pid)
                try:
                    service_info_path(runtime_data_dir).unlink()
                except FileNotFoundError:
                    pass
                append_service_log(runtime_data_dir, "stale-service-cleaned", stalePid=stale_pid)

            target = plugin_root / "mcp" / "gulicode_bp_mcp.py"
            if not target.is_file():
                raise SingletonServiceError("SERVICE_TARGET_MISSING", f"singleton service target is missing: {target}")
            if not runtime_python.is_file():
                raise SingletonServiceError("RUNTIME_PYTHON_MISSING", f"runtime Python is missing: {runtime_python}")

            token = secrets.token_urlsafe(32)
            logs = runtime_data_dir / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            stdout = (logs / "gulicode-bp-service.out.log").open("ab")
            stderr = (logs / "gulicode-bp-service.err.log").open("ab")
            launch_python = base_python_for_runtime(runtime_python)
            env = _service_process_env(
                plugin_root,
                runtime_python,
                runtime_home,
                runtime_data_dir,
                token=token,
                extra_env=extra_env,
            )
            subprocess.Popen(
                [str(launch_python), str(target), "--service"],
                cwd=str(runtime_data_dir),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                creationflags=hidden_creationflags(),
            )
            append_service_log(
                runtime_data_dir,
                "service-spawned",
                target=str(target),
                runtimePython=str(runtime_python),
                launchPython=str(launch_python),
            )

            deadline = time.time() + timeout
            last_info: dict[str, Any] | None = None
            while time.time() < deadline:
                last_info = read_service_info(runtime_data_dir)
                if last_info and service_health_ok(last_info):
                    append_service_log(
                        runtime_data_dir,
                        "service-ready",
                        servicePid=last_info.get("pid"),
                        url=last_info.get("url"),
                    )
                    return last_info
                time.sleep(0.2)
            details = last_info or {}
            raise SingletonServiceError(
                "SERVICE_START_TIMEOUT",
                "gulicode-bp singleton service did not become healthy",
                details=details,
            )
    except SingletonServiceError as exc:
        if exc.code == "SERVICE_ALREADY_RUNNING":
            info = read_service_info(runtime_data_dir)
            if info and service_health_ok(info):
                return info
        raise
