#!/usr/bin/env python
"""Install the repo-local GuLiCode Blueprint plugin into the personal marketplace."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any


PLUGIN_NAME = "gulicode-bp"
RUNTIME_REQUIRED_WHEEL_MEMBERS = (
    "multi_agent_tcp/desktop_blueprint_service.py",
    "multi_agent_tcp/blueprint_mcp_runtime.py",
    "multi_agent_tcp/graph_control.py",
    "multi_agent_tcp/excel_audit.py",
)
MARKETPLACE_ENTRY = {
    "name": PLUGIN_NAME,
    "source": {
        "source": "local",
        "path": f"./plugins/{PLUGIN_NAME}",
    },
    "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    },
    "category": "Productivity",
}


def source_plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def plugin_version(plugin_root: Path) -> str:
    manifest = read_json(plugin_root / ".codex-plugin" / "plugin.json")
    version = str(manifest.get("version") or "").strip()
    if not version:
        raise RuntimeError("plugin manifest is missing version")
    return version


def runtime_package_dir(source_root: Path) -> Path:
    for parent in [source_root, *source_root.parents]:
        if (parent / "desktop_blueprint_service.py").is_file():
            return parent
    raise RuntimeError("could not locate desktop_blueprint_service.py")


def _gulicode_workspace_root(app_root: Path) -> Path:
    return app_root.parents[1]


def _vite_installed(workspace_root: Path) -> bool:
    bin_dir = workspace_root / "node_modules" / ".bin"
    return any(path.name.lower().startswith("vite") for path in bin_dir.glob("vite*"))


def _is_full_gulicode_app_dist(app_dist: Path) -> bool:
    return (app_dist / "index.html").is_file() and (app_dist / "assets").is_dir()


def _ensure_gulicode_app_dependencies(app_root: Path, bun: str) -> None:
    workspace_root = _gulicode_workspace_root(app_root)
    if _vite_installed(workspace_root):
        return
    if not (workspace_root / "bun.lock").is_file():
        raise RuntimeError(f"GuLiCode workspace lockfile is missing: {workspace_root / 'bun.lock'}")
    subprocess.run([bun, "install"], cwd=workspace_root, check=True)
    if not _vite_installed(workspace_root):
        raise RuntimeError(
            "GuLiCode dependencies were installed but vite is still missing. "
            f"Check {workspace_root / 'node_modules'}."
        )


def build_gulicode_app(app_root: Path, *, skip_build: bool) -> None:
    if skip_build:
        return
    bun = shutil.which("bun")
    if bun is None:
        if _is_full_gulicode_app_dist(app_root / "dist"):
            return
        raise RuntimeError("bun was not found and GuLiCode app dist is missing")
    _ensure_gulicode_app_dependencies(app_root, bun)
    subprocess.run([bun, "run", "build"], cwd=app_root, check=True)


def copy_web_dist(plugin_root: Path, package_dir: Path, *, skip_build: bool) -> str:
    web_root = plugin_root / "web"
    dist = web_root / "dist"
    app_root = package_dir / "GuLiCode" / "packages" / "app"
    app_dist = app_root / "dist"

    if app_root.is_dir():
        build_gulicode_app(app_root, skip_build=skip_build)
        if not _is_full_gulicode_app_dist(app_dist):
            if skip_build:
                raise RuntimeError(
                    "GuLiCode app dist is missing or incomplete while --skip-web-build was used. "
                    "Run `bun install` under GuLiCode and `bun run build` under GuLiCode/packages/app, "
                    "or rerun without --skip-web-build so the installer can build it. "
                    "Refusing to install the fallback web UI as the plugin Workbench."
                )
            raise RuntimeError(f"GuLiCode app build did not produce a complete dist: {app_dist}")
        if dist.exists():
            shutil.rmtree(dist)
        shutil.copytree(app_dist, dist, ignore=shutil.ignore_patterns(".vite"))
        return str(app_dist)

    if app_dist.is_dir() and _is_full_gulicode_app_dist(app_dist):
        if dist.exists():
            shutil.rmtree(dist)
        shutil.copytree(app_dist, dist, ignore=shutil.ignore_patterns(".vite"))
        return str(app_dist)

    dist.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "styles.css", "app.js"):
        shutil.copy2(web_root / name, dist / name)
    return str(web_root)


def _copy_plugin_tree(source_root: Path, dest_root: Path, *, force: bool, preserve_runtime: bool) -> None:
    dest = dest_root.resolve()
    if dest.exists():
        if not force:
            raise FileExistsError(f"{dest} already exists; pass --force to replace it")
        for child in dest.iterdir():
            if preserve_runtime and child.name == ".runtime":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "node_modules", ".runtime")
    shutil.copytree(source_root, dest, ignore=ignore, dirs_exist_ok=True)


def mirror_plugin(source_root: Path, dest_root: Path, *, force: bool) -> None:
    home_plugins = Path.home().resolve() / "plugins"
    dest = dest_root.resolve()
    try:
        dest.relative_to(home_plugins)
    except ValueError as exc:
        raise RuntimeError(f"destination must stay under {home_plugins}") from exc
    _copy_plugin_tree(source_root, dest, force=force, preserve_runtime=True)


def runtime_venv_python(runtime_home: Path) -> Path:
    if sys.platform == "win32":
        return runtime_home / "venv" / "Scripts" / "python.exe"
    return runtime_home / "venv" / "bin" / "python"


def _pip_available(python: Path) -> bool:
    return (
        subprocess.run(
            [str(python), "-m", "pip", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def _repair_runtime_pip(python: Path) -> None:
    subprocess.run([str(python), "-m", "ensurepip", "--upgrade", "--default-pip"], check=True)
    if _pip_available(python):
        return

    site_paths_raw = subprocess.check_output(
        [
            str(python),
            "-c",
            "import json, site; print(json.dumps(site.getsitepackages()))",
        ],
        text=True,
    )
    for site_path in json.loads(site_paths_raw):
        site_dir = Path(site_path)
        shutil.rmtree(site_dir / "pip", ignore_errors=True)
        for dist_info in site_dir.glob("pip-*.dist-info"):
            shutil.rmtree(dist_info, ignore_errors=True)

    subprocess.run([str(python), "-m", "ensurepip", "--upgrade", "--default-pip"], check=True)
    if not _pip_available(python):
        raise RuntimeError(f"failed to repair pip in plugin runtime venv: {python}")


def _runtime_site_packages(python: Path) -> list[Path]:
    site_paths_raw = subprocess.check_output(
        [
            str(python),
            "-c",
            "import json, site; print(json.dumps(site.getsitepackages()))",
        ],
        text=True,
    )
    return [Path(site_path) for site_path in json.loads(site_paths_raw)]


def _remove_broken_runtime_dist_infos(python: Path) -> list[str]:
    repaired: list[str] = []
    for site_dir in _runtime_site_packages(python):
        if not site_dir.is_dir():
            continue
        for dist_info in site_dir.glob("*.dist-info"):
            if (dist_info / "METADATA").is_file() and (dist_info / "RECORD").is_file():
                continue
            repaired.append(str(dist_info))
            shutil.rmtree(dist_info, ignore_errors=True)
            if dist_info.exists():
                raise RuntimeError(
                    "failed to remove broken runtime package metadata. Stop any running "
                    f"gulicode-bp MCP process and retry: {dist_info}"
                )
    return repaired


def build_runtime_wheel(package_dir: Path, wheelhouse: Path) -> Path:
    wheelhouse.mkdir(parents=True, exist_ok=True)
    for path in wheelhouse.glob("multi_agent_tcp-*.whl"):
        path.unlink()
    with tempfile.TemporaryDirectory(prefix="gulicode-bp-wheel-") as temp_dir:
        temp_wheelhouse = Path(temp_dir)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--wheel-dir",
                str(temp_wheelhouse),
                str(package_dir),
            ],
            check=True,
        )
        wheels = sorted(temp_wheelhouse.glob("multi_agent_tcp-*.whl"), key=lambda item: item.stat().st_mtime)
        if not wheels:
            raise RuntimeError("runtime wheel build completed but produced no multi_agent_tcp wheel")
        target = wheelhouse / wheels[-1].name
        shutil.copy2(wheels[-1], target)
        validate_runtime_wheel(target)
        return target


def validate_runtime_wheel(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    missing = [name for name in RUNTIME_REQUIRED_WHEEL_MEMBERS if name not in names]
    if missing:
        raise RuntimeError(f"runtime wheel is missing required package files: {missing}")


def _install_runtime_wheel(python: Path, wheel: Path) -> None:
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--upgrade",
            str(wheel),
        ],
        check=True,
    )
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--force-reinstall",
            "--no-deps",
            str(wheel),
        ],
        check=True,
    )


def ensure_runtime_venv(plugin_root: Path, wheel: Path) -> Path:
    runtime_home = plugin_root / ".runtime"
    runtime_home.mkdir(parents=True, exist_ok=True)
    python = runtime_venv_python(runtime_home)
    if not python.is_file():
        subprocess.run([sys.executable, "-m", "venv", str(runtime_home / "venv")], check=True)
    if not python.is_file():
        raise RuntimeError(f"failed to create plugin runtime Python at {python}")
    if not _pip_available(python):
        _repair_runtime_pip(python)
    try:
        _install_runtime_wheel(python, wheel)
    except subprocess.CalledProcessError as first_exc:
        repaired = _remove_broken_runtime_dist_infos(python)
        if not repaired:
            raise RuntimeError(
                "failed to install gulicode-bp runtime dependencies into the plugin runtime venv. "
                "Stop any running gulicode-bp MCP process, then rerun "
                "`python plugins\\gulicode-bp\\scripts\\install_personal_plugin.py --force`."
            ) from first_exc
        try:
            _install_runtime_wheel(python, wheel)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "failed to install gulicode-bp runtime dependencies after repairing broken package "
                "metadata in the plugin runtime venv. Stop any running gulicode-bp MCP process, "
                "then rerun `python plugins\\gulicode-bp\\scripts\\install_personal_plugin.py --force`."
            ) from exc
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            "failed to install gulicode-bp runtime dependencies into the plugin runtime venv. "
            "Stop any running gulicode-bp MCP process, then rerun "
            "`python plugins\\gulicode-bp\\scripts\\install_personal_plugin.py --force`."
        ) from exc
    validate_runtime_imports(python, plugin_root)
    return python


def validate_runtime_imports(python: Path, plugin_root: Path) -> None:
    runtime_home = plugin_root / ".runtime"
    env = dict(os.environ)
    env["GULICODE_BP_PLUGIN_ROOT"] = str(plugin_root)
    env["GULICODE_BP_RUNTIME_HOME"] = str(runtime_home)
    env["GULICODE_BP_DATA_DIR"] = str(runtime_home / "state")
    env["GULICODE_BP_DISABLE_REPO_FALLBACK"] = "1"
    env.pop("GULICODE_BP_REPO_ROOT", None)
    env.pop("PYTHONPATH", None)
    code = (
        "import flask\n"
        "import multi_agent_tcp\n"
        "import multi_agent_tcp.excel_audit\n"
        "import requests\n"
        "from Crypto.Cipher import AES\n"
        "from mcp.server.fastmcp import FastMCP\n"
        "from multi_agent_tcp.desktop_blueprint_service import DesktopBlueprintService\n"
        "import multi_agent_tcp.popo_agent_bot_run\n"
        "print(multi_agent_tcp.__file__)\n"
    )
    result = subprocess.run(
        [str(python), "-c", code],
        cwd=str(plugin_root),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode == 0:
        return
    diagnostics = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part and part.strip()
    )
    raise RuntimeError(
        "gulicode-bp runtime import validation failed. Reinstall or repair the plugin with "
        "`python plugins\\gulicode-bp\\scripts\\install_personal_plugin.py --force`, and stop any "
        "running gulicode-bp MCP process if the runtime venv is locked."
        + (f"\n{diagnostics}" if diagnostics else "")
    )


def build_mcp_payload(plugin_root: Path | str) -> dict[str, Any]:
    root = str(plugin_root)
    runtime_home = str(Path(root) / ".runtime") if root != "." else ".runtime"
    runtime_data_dir = str(Path(runtime_home) / "state")
    return {
        "mcpServers": {
            "gulicode-bp": {
                "type": "stdio",
                "command": "python",
                "args": ["scripts/bootstrap_mcp.py"],
                "cwd": root,
                "env": {
                    "GULICODE_BP_PLUGIN_ROOT": root,
                    "GULICODE_BP_RUNTIME_HOME": runtime_home,
                    "GULICODE_BP_DATA_DIR": runtime_data_dir,
                    "GULICODE_BP_DISABLE_REPO_FALLBACK": "1",
                },
            }
        }
    }


def rewrite_personal_mcp(plugin_root: Path, *, payload_root: Path | str | None = None) -> None:
    payload = build_mcp_payload(payload_root if payload_root is not None else plugin_root)
    write_json(plugin_root / ".mcp.json", payload)


def rewrite_cache_mcp(cache_plugin_root: Path, installed_plugin_root: Path) -> None:
    payload = build_mcp_payload(installed_plugin_root)
    write_json(cache_plugin_root / ".mcp.json", payload)


def validate_release_package(plugin_root: Path) -> None:
    required = [
        ".codex-plugin/plugin.json",
        ".mcp.json",
        "mcp/gulicode_bp_mcp.py",
        "scripts/bootstrap_mcp.py",
        "scripts/bootstrap_runtime.py",
        "skills/blueprint/SKILL.md",
        "web/dist/index.html",
    ]
    missing = [item for item in required if not (plugin_root / item).is_file()]
    if missing:
        raise RuntimeError(f"release package is missing required files: {missing}")
    wheels = list((plugin_root / "runtime" / "wheels").glob("multi_agent_tcp-*.whl"))
    if not wheels:
        raise RuntimeError(f"release package is missing runtime wheel under {plugin_root / 'runtime' / 'wheels'}")
    validate_runtime_wheel(sorted(wheels, key=lambda item: item.stat().st_mtime)[-1])
    if (plugin_root / ".runtime").exists():
        raise RuntimeError(f"release package must not include runtime state: {plugin_root / '.runtime'}")


def prepare_release_package(
    source_root: Path,
    package_dir: Path,
    dest_root: Path,
    *,
    force: bool,
    skip_build: bool,
    preserve_runtime: bool = False,
) -> dict[str, str]:
    web_source = copy_web_dist(source_root, package_dir, skip_build=skip_build)
    _copy_plugin_tree(source_root, dest_root, force=force, preserve_runtime=preserve_runtime)
    dest = dest_root.resolve()
    runtime_wheel = build_runtime_wheel(package_dir, dest / "runtime" / "wheels")
    rewrite_personal_mcp(dest, payload_root=dest if preserve_runtime else ".")
    if not preserve_runtime:
        validate_release_package(dest)
    else:
        required = [".codex-plugin/plugin.json", ".mcp.json", "mcp/gulicode_bp_mcp.py", "scripts/bootstrap_mcp.py"]
        missing = [item for item in required if not (dest / item).is_file()]
        if missing:
            raise RuntimeError(f"installed plugin is missing required files: {missing}")
    return {
        "plugin": str(dest),
        "runtimeWheel": str(runtime_wheel),
        "webSource": web_source,
        "mcpMode": "bootstrap",
    }


def sync_codex_cache(
    installed_plugin_root: Path,
    *,
    version: str,
    cache_root: Path,
    force: bool,
) -> list[str]:
    cache_root = cache_root.expanduser().resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    target = cache_root / version

    if target.exists() and force:
        for child in target.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    if not target.exists():
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "node_modules", ".runtime")
        shutil.copytree(installed_plugin_root, target, ignore=ignore)
    else:
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "node_modules", ".runtime")
        shutil.copytree(installed_plugin_root, target, ignore=ignore, dirs_exist_ok=True)

    updated: list[str] = []
    for child in sorted(cache_root.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        rewrite_cache_mcp(child, installed_plugin_root)
        updated.append(str(child))
    return updated


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "name": "personal",
            "interface": {"displayName": "Personal"},
            "plugins": [],
        }
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def update_marketplace(path: Path, *, force: bool) -> None:
    payload = read_json(path)
    payload.setdefault("name", "personal")
    interface = payload.setdefault("interface", {"displayName": "Personal"})
    if not isinstance(interface, dict):
        raise ValueError("marketplace interface must be an object")
    interface.setdefault("displayName", "Personal")

    plugins = payload.setdefault("plugins", [])
    if not isinstance(plugins, list):
        raise ValueError("marketplace plugins must be an array")

    for index, entry in enumerate(plugins):
        if isinstance(entry, dict) and entry.get("name") == PLUGIN_NAME:
            if not force:
                raise FileExistsError(f"{PLUGIN_NAME} already exists in {path}; pass --force to replace it")
            plugins[index] = MARKETPLACE_ENTRY
            break
    else:
        plugins.append(MARKETPLACE_ENTRY)

    write_json(path, payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install gulicode-bp as a personal Codex plugin")
    parser.add_argument("--force", action="store_true", help="replace existing personal plugin and marketplace entry")
    parser.add_argument(
        "--skip-web-build",
        action="store_true",
        help="copy the existing GuLiCode app dist instead of rebuilding it",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path.home() / "plugins" / PLUGIN_NAME,
        help="personal plugin destination",
    )
    parser.add_argument(
        "--marketplace",
        type=Path,
        default=Path.home() / ".agents" / "plugins" / "marketplace.json",
        help="personal marketplace.json path",
    )
    parser.add_argument(
        "--codex-cache-root",
        type=Path,
        default=Path.home() / ".codex" / "plugins" / "cache" / "personal" / PLUGIN_NAME,
        help="Codex personal plugin cache root to synchronize",
    )
    parser.add_argument(
        "--skip-codex-cache-sync",
        action="store_true",
        help="do not synchronize the Codex plugin cache copy",
    )
    parser.add_argument(
        "--release-dir",
        type=Path,
        help="also build a standalone release package at this directory",
    )
    parser.add_argument(
        "--only-release",
        action="store_true",
        help="build --release-dir and skip personal plugin installation",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_root = source_plugin_root()
    version = plugin_version(source_root)
    package_dir = runtime_package_dir(source_root)
    release_payload: dict[str, str] | None = None
    if args.release_dir is not None:
        release_payload = prepare_release_package(
            source_root,
            package_dir,
            args.release_dir,
            force=args.force,
            skip_build=args.skip_web_build,
        )
        if args.only_release:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "version": version,
                        "release": release_payload,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
    elif args.only_release:
        raise RuntimeError("--only-release requires --release-dir")

    dest_payload = prepare_release_package(
        source_root,
        package_dir,
        args.dest,
        force=args.force,
        skip_build=args.skip_web_build,
        preserve_runtime=True,
    )
    dest_root = Path(dest_payload["plugin"])
    runtime_python = ensure_runtime_venv(dest_root, Path(dest_payload["runtimeWheel"]))
    update_marketplace(args.marketplace.resolve(), force=args.force)
    cache_updated: list[str] = []
    if not args.skip_codex_cache_sync:
        cache_updated = sync_codex_cache(
            dest_root,
            version=version,
            cache_root=args.codex_cache_root,
            force=args.force,
        )
    print(
        json.dumps(
            {
                "ok": True,
                "version": version,
                "plugin": str(dest_root),
                "marketplace": str(args.marketplace.resolve()),
                "runtimeWheel": dest_payload["runtimeWheel"],
                "runtimePython": str(runtime_python),
                "mcpMode": dest_payload["mcpMode"],
                "webSource": dest_payload["webSource"],
                "release": release_payload,
                "codexCacheRoot": str(args.codex_cache_root.resolve()),
                "codexCacheUpdated": cache_updated,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
