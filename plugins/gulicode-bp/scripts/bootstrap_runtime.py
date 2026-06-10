#!/usr/bin/env python
"""Prepare the plugin-owned GuLiCode Blueprint Python runtime."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


PLUGIN_NAME = "gulicode-bp"
STATE_FILENAME = "bootstrap.json"
LOCK_FILENAME = "bootstrap.lock"
MCP_STATUS_FILENAME = "mcp_status.json"
BOOTSTRAP_LOG_FILENAME = "gulicode-bp-bootstrap.log"


def resolve_plugin_root(value: str | Path | None = None) -> Path:
    raw = value if value is not None else os.environ.get("GULICODE_BP_PLUGIN_ROOT")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def runtime_home(plugin_root: Path) -> Path:
    return Path(os.environ.get("GULICODE_BP_RUNTIME_HOME") or plugin_root / ".runtime").expanduser().resolve()


def runtime_data_dir(plugin_root: Path) -> Path:
    return Path(os.environ.get("GULICODE_BP_DATA_DIR") or runtime_home(plugin_root) / "state").expanduser().resolve()


def runtime_venv_python(runtime_root: Path) -> Path:
    if sys.platform == "win32":
        return runtime_root / "venv" / "Scripts" / "python.exe"
    return runtime_root / "venv" / "bin" / "python"


def find_runtime_wheel(plugin_root: Path) -> Path:
    wheelhouse = plugin_root / "runtime" / "wheels"
    wheels = sorted(wheelhouse.glob("multi_agent_tcp-*.whl"), key=lambda path: (path.stat().st_mtime_ns, path.name))
    if not wheels:
        raise RuntimeError(
            f"{PLUGIN_NAME} runtime wheel is missing. Expected multi_agent_tcp-*.whl under {wheelhouse}."
        )
    return wheels[-1].resolve()


def _run_checked(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    label: str,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode == 0:
        return result
    diagnostics = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part and part.strip()
    )
    raise RuntimeError(
        f"{label} failed with exit code {result.returncode}: {' '.join(args)}"
        + (f"\n{diagnostics}" if diagnostics else "")
    )


def pip_available(python: Path) -> bool:
    return (
        subprocess.run(
            [str(python), "-m", "pip", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def repair_pip(python: Path) -> None:
    _run_checked(
        [str(python), "-m", "ensurepip", "--upgrade", "--default-pip"],
        label="plugin runtime ensurepip",
    )
    if pip_available(python):
        return

    site_paths = _runtime_site_packages(python)
    for site_dir in site_paths:
        _rmtree(site_dir / "pip")
        for dist_info in site_dir.glob("pip-*.dist-info"):
            _rmtree(dist_info)

    _run_checked(
        [str(python), "-m", "ensurepip", "--upgrade", "--default-pip"],
        label="plugin runtime ensurepip repair",
    )
    if not pip_available(python):
        raise RuntimeError(f"failed to repair pip in plugin runtime venv: {python}")


def _runtime_site_packages(python: Path) -> list[Path]:
    result = _run_checked(
        [
            str(python),
            "-c",
            "import json, site; print(json.dumps(site.getsitepackages()))",
        ],
        label="plugin runtime site-packages lookup",
    )
    return [Path(item) for item in json.loads(result.stdout)]


def _remove_broken_runtime_dist_infos(python: Path) -> list[str]:
    repaired: list[str] = []
    for site_dir in _runtime_site_packages(python):
        if not site_dir.is_dir():
            continue
        for dist_info in site_dir.glob("*.dist-info"):
            if (dist_info / "METADATA").is_file() and (dist_info / "RECORD").is_file():
                continue
            repaired.append(str(dist_info))
            _rmtree(dist_info)
            if dist_info.exists():
                raise RuntimeError(
                    "failed to remove broken runtime package metadata. Stop any running "
                    f"{PLUGIN_NAME} MCP process and retry: {dist_info}"
                )
    return repaired


def _rmtree(path: Path) -> None:
    if not path.exists():
        return
    import shutil

    shutil.rmtree(path, ignore_errors=True)


def install_runtime_wheel(python: Path, wheel: Path) -> None:
    args = [
        str(python),
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--force-reinstall",
        str(wheel),
    ]
    try:
        _run_checked(args, label="plugin runtime dependency install")
    except RuntimeError:
        repaired = _remove_broken_runtime_dist_infos(python)
        if not repaired:
            raise
        _run_checked(args, label="plugin runtime dependency install after metadata repair")


def validate_runtime_imports(python: Path, plugin_root: Path, runtime_root: Path) -> dict[str, Any]:
    data_dir = runtime_data_dir(plugin_root)
    env = dict(os.environ)
    env["GULICODE_BP_PLUGIN_ROOT"] = str(plugin_root)
    env["GULICODE_BP_RUNTIME_HOME"] = str(runtime_root)
    env["GULICODE_BP_DATA_DIR"] = str(data_dir)
    env["GULICODE_BP_DISABLE_REPO_FALLBACK"] = "1"
    env.pop("GULICODE_BP_REPO_ROOT", None)
    env.pop("PYTHONPATH", None)
    code = (
        "import json\n"
        "from pathlib import Path\n"
        "import flask\n"
        "import multi_agent_tcp\n"
        "import requests\n"
        "from Crypto.Cipher import AES\n"
        "from mcp.server.fastmcp import FastMCP\n"
        "from multi_agent_tcp.desktop_blueprint_service import DesktopBlueprintService\n"
        "import multi_agent_tcp.popo_agent_bot_run\n"
        "print(json.dumps({'runtimePackage': str(Path(multi_agent_tcp.__file__).resolve())}))\n"
    )
    result = _run_checked(
        [str(python), "-c", code],
        cwd=plugin_root,
        env=env,
        label="plugin runtime import validation",
    )
    payload = json.loads(result.stdout)
    package_path = Path(str(payload.get("runtimePackage") or "")).expanduser().resolve()
    if not _same_or_child(package_path, runtime_root / "venv"):
        raise RuntimeError(f"runtime package did not load from plugin venv: {package_path}")
    return {"runtimePackage": str(package_path)}


def _same_or_child(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _wheel_identity(wheel: Path) -> dict[str, Any]:
    stat = wheel.stat()
    return {
        "name": wheel.name,
        "path": str(wheel),
        "size": stat.st_size,
        "mtimeNs": stat.st_mtime_ns,
    }


def _state_path(plugin_root: Path) -> Path:
    return runtime_data_dir(plugin_root) / STATE_FILENAME


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _append_bootstrap_log(data_dir: Path, event: str, **details: Any) -> None:
    try:
        log_dir = data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": _utc_now(),
            "event": event,
            "pid": os.getpid(),
            **{key: _json_safe(value) for key, value in details.items()},
        }
        with (log_dir / BOOTSTRAP_LOG_FILENAME).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass


def _write_mcp_status(data_dir: Path, status: str, **details: Any) -> None:
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": status,
            "timestamp": _utc_now(),
            "pid": os.getpid(),
            **{key: _json_safe(value) for key, value in details.items()},
        }
        with (data_dir / MCP_STATUS_FILENAME).open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
    except Exception:
        pass


def _read_state(plugin_root: Path) -> dict[str, Any]:
    path = _state_path(plugin_root)
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _state_matches(plugin_root: Path, wheel: Path) -> bool:
    state = _read_state(plugin_root)
    return state.get("runtimeWheel") == _wheel_identity(wheel)


def _write_state(plugin_root: Path, payload: dict[str, Any]) -> None:
    path = _state_path(plugin_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _lock_command_name() -> str:
    raw = sys.argv[0] if sys.argv else ""
    return Path(raw).name or raw or "python"


def _read_lock_info(lock_path: Path) -> dict[str, str]:
    try:
        text = lock_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    info: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        info[key.strip()] = value.strip()
    return info


def _lock_pid(info: dict[str, str]) -> int | None:
    raw = info.get("pid")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _windows_pid_is_running(pid: int) -> bool:
    try:
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        return False


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        return _windows_pid_is_running(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@contextmanager
def _bootstrap_lock(
    runtime_root: Path,
    *,
    data_dir: Path | None = None,
    timeout: float = 600.0,
    poll_interval: float = 0.25,
) -> Iterator[None]:
    runtime_root.mkdir(parents=True, exist_ok=True)
    status_dir = data_dir or runtime_root / "state"
    lock_path = runtime_root / LOCK_FILENAME
    deadline = time.monotonic() + timeout
    fd: int | None = None
    last_wait_log = 0.0
    while fd is None:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            lock_text = "\n".join(
                [
                    f"pid={os.getpid()}",
                    f"created={_utc_now()}",
                    f"command={_lock_command_name()}",
                    "",
                ]
            )
            os.write(fd, lock_text.encode("utf-8"))
            _append_bootstrap_log(status_dir, "lock-acquired", lockPath=str(lock_path))
            break
        except FileExistsError:
            now = time.monotonic()
            try:
                age = time.time() - lock_path.stat().st_mtime
                info = _read_lock_info(lock_path)
                owner_pid = _lock_pid(info)
                if owner_pid is not None and not _pid_is_running(owner_pid):
                    lock_path.unlink()
                    _append_bootstrap_log(
                        status_dir,
                        "stale-lock-removed",
                        lockPath=str(lock_path),
                        ownerPid=owner_pid,
                        reason="dead-pid",
                    )
                    continue
                if owner_pid is None and age > timeout:
                    lock_path.unlink()
                    _append_bootstrap_log(
                        status_dir,
                        "stale-lock-removed",
                        lockPath=str(lock_path),
                        ownerPid=owner_pid,
                        reason="age-timeout",
                        ageSeconds=round(age, 3),
                    )
                    continue
            except OSError:
                continue
            if now - last_wait_log >= 5.0 or last_wait_log == 0.0:
                last_wait_log = now
                _append_bootstrap_log(
                    status_dir,
                    "lock-wait",
                    lockPath=str(lock_path),
                    ownerPid=_lock_pid(_read_lock_info(lock_path)),
                )
            if now >= deadline:
                _write_mcp_status(
                    status_dir,
                    "error",
                    phase="bootstrap-lock",
                    lastError=f"timed out waiting for {PLUGIN_NAME} runtime bootstrap lock: {lock_path}",
                )
                _append_bootstrap_log(status_dir, "lock-timeout", lockPath=str(lock_path))
                raise RuntimeError(f"timed out waiting for {PLUGIN_NAME} runtime bootstrap lock: {lock_path}")
            time.sleep(poll_interval)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock_path.unlink()
            _append_bootstrap_log(status_dir, "lock-released", lockPath=str(lock_path))
        except FileNotFoundError:
            pass


def prepare_runtime(
    plugin_root: str | Path | None = None,
    *,
    force: bool = False,
    status_component: str = "runtime-bootstrap",
) -> dict[str, Any]:
    root = resolve_plugin_root(plugin_root)
    runtime_root = runtime_home(root)
    data_dir = runtime_data_dir(root)
    _write_mcp_status(
        data_dir,
        "starting",
        component=status_component,
        phase="prepare-runtime",
        pluginRoot=str(root),
        runtimeHome=str(runtime_root),
    )
    _append_bootstrap_log(
        data_dir,
        "prepare-start",
        component=status_component,
        pluginRoot=str(root),
        runtimeHome=str(runtime_root),
        force=force,
    )
    try:
        wheel = find_runtime_wheel(root)
        python = runtime_venv_python(runtime_root)
        created_venv = False
        installed_runtime = False

        with _bootstrap_lock(runtime_root, data_dir=data_dir):
            install_needed = force or not python.is_file() or not _state_matches(root, wheel)
            _append_bootstrap_log(
                data_dir,
                "runtime-check",
                runtimePython=str(python),
                wheel=str(wheel),
                installNeeded=install_needed,
            )
            if not python.is_file():
                _append_bootstrap_log(data_dir, "venv-create-start", runtimePython=str(python))
                _run_checked(
                    [sys.executable, "-m", "venv", str(runtime_root / "venv")],
                    label="plugin runtime venv creation",
                )
                created_venv = True
                install_needed = True
                _append_bootstrap_log(data_dir, "venv-create-complete", runtimePython=str(python))
            if not python.is_file():
                raise RuntimeError(f"failed to create plugin runtime Python at {python}")

            if not pip_available(python):
                _append_bootstrap_log(data_dir, "pip-repair-start", runtimePython=str(python))
                repair_pip(python)
                install_needed = True
                _append_bootstrap_log(data_dir, "pip-repair-complete", runtimePython=str(python))

            validation: dict[str, Any] | None = None
            if not install_needed:
                try:
                    validation = validate_runtime_imports(python, root, runtime_root)
                    _append_bootstrap_log(data_dir, "runtime-validation-complete", runtimePython=str(python))
                except Exception as exc:
                    install_needed = True
                    _append_bootstrap_log(
                        data_dir,
                        "runtime-validation-failed",
                        runtimePython=str(python),
                        error=str(exc),
                    )

            if install_needed:
                _append_bootstrap_log(data_dir, "runtime-install-start", runtimePython=str(python), wheel=str(wheel))
                install_runtime_wheel(python, wheel)
                installed_runtime = True
                _append_bootstrap_log(data_dir, "runtime-install-complete", runtimePython=str(python), wheel=str(wheel))
                validation = validate_runtime_imports(python, root, runtime_root)
                _append_bootstrap_log(data_dir, "runtime-validation-complete", runtimePython=str(python))

            if validation is None:
                validation = validate_runtime_imports(python, root, runtime_root)
                _append_bootstrap_log(data_dir, "runtime-validation-complete", runtimePython=str(python))

            payload = {
                "ok": True,
                "pluginRoot": str(root),
                "runtimeHome": str(runtime_root),
                "runtimeDataDir": str(data_dir),
                "runtimePython": str(python),
                "runtimeWheel": _wheel_identity(wheel),
                "runtimePackage": validation["runtimePackage"],
                "createdVenv": created_venv,
                "installedRuntime": installed_runtime,
                "timestamp": _utc_now(),
            }
            _write_state(root, payload)
            _write_mcp_status(
                data_dir,
                "starting",
                component=status_component,
                phase="runtime-ready",
                pluginRoot=str(root),
                runtimeHome=str(runtime_root),
                runtimePython=str(python),
            )
            _append_bootstrap_log(data_dir, "prepare-complete", runtimePython=str(python), installedRuntime=installed_runtime)
            return payload
    except Exception as exc:
        _write_mcp_status(
            data_dir,
            "error",
            component=status_component,
            phase="prepare-runtime",
            pluginRoot=str(root),
            runtimeHome=str(runtime_root),
            lastError=str(exc),
        )
        _append_bootstrap_log(data_dir, "prepare-error", component=status_component, error=str(exc))
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare the gulicode-bp plugin runtime")
    parser.add_argument("--plugin-root", type=Path, help="installed gulicode-bp plugin root")
    parser.add_argument("--force", action="store_true", help="reinstall runtime wheel even if the state looks current")
    parser.add_argument("--print-json", action="store_true", help="print runtime bootstrap result JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = prepare_runtime(args.plugin_root, force=args.force)
    if args.print_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
