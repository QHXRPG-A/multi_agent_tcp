#!/usr/bin/env python
"""Run the GuLiCode Blueprint plugin workbench as a standalone debug service."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _source_plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _find_runtime_package_dir(plugin_root: Path) -> Path:
    env_root = os.environ.get("GULICODE_BP_REPO_ROOT", "").strip()
    if env_root and not _repo_fallback_disabled():
        root = Path(env_root).expanduser().resolve()
        if (root / "desktop_blueprint_service.py").is_file():
            return root

    if not _repo_fallback_disabled():
        for parent in [plugin_root, *plugin_root.parents]:
            if (parent / "desktop_blueprint_service.py").is_file():
                return parent

    raise RuntimeError(
        "Could not locate multi_agent_tcp runtime. Pass --repo-root or set "
        "GULICODE_BP_REPO_ROOT to the directory containing desktop_blueprint_service.py."
    )


def _repo_fallback_disabled() -> bool:
    return os.environ.get("GULICODE_BP_DISABLE_REPO_FALLBACK", "").strip().lower() in {"1", "true", "yes"}


def _runtime_home(plugin_root: Path) -> Path:
    return Path(os.environ.get("GULICODE_BP_RUNTIME_HOME") or plugin_root / ".runtime").expanduser().resolve()


def _runtime_data_dir(plugin_root: Path) -> Path:
    return Path(os.environ.get("GULICODE_BP_DATA_DIR") or _runtime_home(plugin_root) / "state").expanduser().resolve()


def _runtime_venv_python(plugin_root: Path) -> Path:
    runtime_home = _runtime_home(plugin_root)
    if sys.platform == "win32":
        return runtime_home / "venv" / "Scripts" / "python.exe"
    return runtime_home / "venv" / "bin" / "python"


def _same_python(left: Path, right: Path) -> bool:
    try:
        return left.resolve().samefile(right.resolve())
    except OSError:
        return str(left.resolve()).casefold() == str(right.resolve()).casefold()


def _maybe_reexec_runtime_python(plugin_root: Path, repo_root: Path | None) -> None:
    if repo_root is not None and not _repo_fallback_disabled():
        return
    if os.environ.get("GULICODE_BP_RUNTIME_REEXECED") == "1":
        return
    runtime_python = _runtime_venv_python(plugin_root)
    if runtime_python.is_file() and not _same_python(Path(sys.executable), runtime_python):
        env = os.environ.copy()
        env.setdefault("GULICODE_BP_PLUGIN_ROOT", str(plugin_root))
        env.setdefault("GULICODE_BP_RUNTIME_HOME", str(_runtime_home(plugin_root)))
        env.setdefault("GULICODE_BP_DATA_DIR", str(_runtime_data_dir(plugin_root)))
        env["GULICODE_BP_RUNTIME_REEXECED"] = "1"
        if sys.platform == "win32":
            raise SystemExit(subprocess.call([str(runtime_python), *sys.argv], env=env))
        os.execve(str(runtime_python), [str(runtime_python), *sys.argv], env)
    if _repo_fallback_disabled() and not runtime_python.is_file():
        raise RuntimeError(
            "gulicode-bp standalone runtime is missing. Reinstall or repair the plugin with "
            "`python plugins\\gulicode-bp\\scripts\\install_personal_plugin.py --force`."
        )


def _prepare_runtime_if_needed(plugin_root: Path, repo_root: Path | None) -> None:
    if repo_root is not None and not _repo_fallback_disabled():
        return
    scripts_dir = str(plugin_root / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from bootstrap_runtime import prepare_runtime

    prepare_runtime(plugin_root)


def _write_ready(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the local GuLiCode Blueprint workbench")
    parser.add_argument("--project-dir", type=Path, help="project directory opened by the workbench")
    parser.add_argument("--blueprint-id", default="default", help="blueprint id to open")
    parser.add_argument("--planning-thread-id", default="", help="Codex thread id allowed to claim Workbench planning requests")
    parser.add_argument("--repo-root", type=Path, help="multi_agent_tcp repository root")
    parser.add_argument("--ready-file", type=Path, help="write startup JSON to this file")
    parser.add_argument("--open", action="store_true", help="open the workbench URL in the default browser")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plugin_root = _source_plugin_root()
    try:
        repo_root = args.repo_root.resolve() if args.repo_root else None
        if repo_root is None:
            try:
                repo_root = _find_runtime_package_dir(plugin_root)
            except RuntimeError:
                repo_root = None
        _prepare_runtime_if_needed(plugin_root, repo_root)
        _maybe_reexec_runtime_python(plugin_root, repo_root)
        project_dir = args.project_dir.resolve() if args.project_dir else repo_root

        os.environ.setdefault("GULICODE_BP_PLUGIN_ROOT", str(plugin_root))
        os.environ.setdefault("GULICODE_BP_RUNTIME_HOME", str(_runtime_home(plugin_root)))
        os.environ.setdefault("GULICODE_BP_DATA_DIR", str(_runtime_data_dir(plugin_root)))
        if repo_root is not None and not _repo_fallback_disabled():
            os.environ.setdefault("GULICODE_BP_REPO_ROOT", str(repo_root))
            import_root = str(repo_root.parent)
            if import_root not in sys.path:
                sys.path.insert(0, import_root)

        mcp_dir = str(plugin_root / "mcp")
        if mcp_dir not in sys.path:
            sys.path.insert(0, mcp_dir)

        from gulicode_bp_singleton import ensure_singleton_service, service_rpc

        runtime_python = _runtime_venv_python(plugin_root)
        if not runtime_python.is_file():
            runtime_python = Path(sys.executable)
        extra_env: dict[str, str] = {}
        if repo_root is not None and not _repo_fallback_disabled():
            extra_env["GULICODE_BP_REPO_ROOT"] = str(repo_root)
            extra_env["PYTHONPATH"] = str(repo_root.parent)
        else:
            extra_env["GULICODE_BP_DISABLE_REPO_FALLBACK"] = "1"

        service_info = ensure_singleton_service(
            plugin_root,
            runtime_python,
            _runtime_home(plugin_root),
            _runtime_data_dir(plugin_root),
            extra_env=extra_env,
        )
        result = service_rpc(
            _runtime_data_dir(plugin_root),
            "service.startWorkbench",
            {
                "projectDir": str(project_dir) if project_dir is not None else "",
                "blueprintId": args.blueprint_id,
                "openBrowser": bool(args.open),
                "planningThreadId": args.planning_thread_id,
            },
            thread_id=args.planning_thread_id,
            request_kind="attach",
        )
        result["wrapperPid"] = os.getpid()
        result["servicePid"] = result.get("servicePid") or service_info.get("pid")
        result["persistent"] = True
        _write_ready(args.ready_file, result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        payload = {"ok": False, "error": str(exc)}
        _write_ready(args.ready_file, payload)
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
