#!/usr/bin/env python
"""Bootstrap the plugin runtime, then exec the GuLiCode Blueprint MCP server."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from bootstrap_runtime import _append_bootstrap_log, _write_mcp_status, prepare_runtime, resolve_plugin_root, runtime_data_dir


def parse_args(argv: list[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="Start the gulicode-bp MCP server through its private runtime")
    parser.add_argument("--plugin-root", type=Path, help="installed gulicode-bp plugin root")
    parser.add_argument("--force-bootstrap", action="store_true", help="force reinstalling the runtime wheel")
    parser.add_argument(
        "--print-runtime-json",
        action="store_true",
        help="prepare the runtime and print JSON instead of starting MCP",
    )
    return parser.parse_known_args(argv)


def main(argv: list[str] | None = None) -> int:
    args, remaining = parse_args(argv)
    bootstrap_root = resolve_plugin_root(args.plugin_root)
    data_dir = runtime_data_dir(bootstrap_root)
    try:
        payload = prepare_runtime(bootstrap_root, force=args.force_bootstrap, status_component="mcp-bootstrap")
        data_dir = Path(payload["runtimeDataDir"]).resolve()
        if args.print_runtime_json:
            _write_mcp_status(
                data_dir,
                "exited",
                component="mcp-bootstrap",
                phase="print-runtime-json",
                pluginRoot=str(payload["pluginRoot"]),
                runtimePython=str(payload["runtimePython"]),
            )
            _append_bootstrap_log(data_dir, "print-runtime-json", runtimePython=str(payload["runtimePython"]))
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        plugin_root = Path(payload["pluginRoot"]).resolve()
        runtime_python = str(payload["runtimePython"])
        target = plugin_root / "mcp" / "gulicode_bp_mcp.py"
        env = os.environ.copy()
        env["GULICODE_BP_PLUGIN_ROOT"] = str(plugin_root)
        env["GULICODE_BP_RUNTIME_HOME"] = str(payload["runtimeHome"])
        env["GULICODE_BP_DATA_DIR"] = str(data_dir)
        env["GULICODE_BP_DISABLE_REPO_FALLBACK"] = "1"
        env.pop("GULICODE_BP_REPO_ROOT", None)
        env.pop("PYTHONPATH", None)
        env["GULICODE_BP_RUNTIME_REEXECED"] = "1"
        mcp_dir = str(plugin_root / "mcp")
        if mcp_dir not in sys.path:
            sys.path.insert(0, mcp_dir)
        from gulicode_bp_singleton import ensure_singleton_service

        service_info = ensure_singleton_service(
            plugin_root,
            Path(runtime_python),
            Path(payload["runtimeHome"]),
            data_dir,
            extra_env={
                "GULICODE_BP_DISABLE_REPO_FALLBACK": "1",
            },
        )
        env["GULICODE_BP_SINGLETON_ROLE"] = "proxy"
        _write_mcp_status(
            data_dir,
            "starting",
            component="mcp-bootstrap",
            phase="start-mcp-proxy",
            pluginRoot=str(plugin_root),
            runtimePython=runtime_python,
            target=str(target),
            servicePid=service_info.get("pid"),
            serviceUrl=service_info.get("url"),
        )
        _append_bootstrap_log(
            data_dir,
            "start-mcp-proxy",
            runtimePython=runtime_python,
            target=str(target),
            args=remaining,
            servicePid=service_info.get("pid"),
            serviceUrl=service_info.get("url"),
        )
        if sys.platform == "win32":
            code = subprocess.call([runtime_python, str(target), *remaining], env=env)
            if code == 0:
                _write_mcp_status(data_dir, "exited", component="mcp-bootstrap", phase="mcp-exited", exitCode=code)
                _append_bootstrap_log(data_dir, "mcp-exited", exitCode=code)
            else:
                _write_mcp_status(
                    data_dir,
                    "error",
                    component="mcp-bootstrap",
                    phase="mcp-exited",
                    exitCode=code,
                    lastError=f"MCP server exited with code {code}",
                )
                _append_bootstrap_log(data_dir, "mcp-exited", exitCode=code)
            return code
        os.execve(runtime_python, [runtime_python, str(target), *remaining], env)
        return 1
    except Exception as exc:
        _write_mcp_status(data_dir, "error", component="mcp-bootstrap", phase="bootstrap-mcp", lastError=str(exc))
        _append_bootstrap_log(data_dir, "bootstrap-mcp-error", error=str(exc))
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
