#!/usr/bin/env python
"""Smoke an installed gulicode-bp plugin without repository fallback."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


PLUGIN_NAME = "gulicode-bp"


SMOKE_CODE = r"""
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

plugin_root = Path(os.environ["GULICODE_BP_PLUGIN_ROOT"]).resolve()
sys.path.insert(0, str(plugin_root / "mcp"))
os.environ["GULICODE_BP_SINGLETON_ROLE"] = "proxy"

import flask
import gulicode_bp_mcp
import multi_agent_tcp
import multi_agent_tcp.popo_agent_bot_run
import requests
from Crypto.Cipher import AES


def agent_node_ids(document):
    agents = document.get("graph", {}).get("agent_nodes", {})
    if isinstance(agents, dict):
        return sorted(str(key) for key in agents if str(key).strip())
    if isinstance(agents, list):
        result = []
        for item in agents:
            if isinstance(item, dict) and str(item.get("node_id", "")).strip():
                result.append(str(item["node_id"]).strip())
        return sorted(result)
    return []


def start_node_candidates(document):
    agents = agent_node_ids(document)
    edges = document.get("graph", {}).get("edges", [])
    incoming = set()
    if isinstance(edges, list):
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            target = str(edge.get("to", "")).strip()
            if target:
                incoming.add(target)
    source_agents = [node_id for node_id in agents if node_id not in incoming]
    return source_agents or agents


project = Path(tempfile.mkdtemp(prefix="gulicode-bp-standalone-"))
run_id = ""
try:
    created = gulicode_bp_mcp.blueprint_create(str(project), "standalone-smoke", "Standalone Smoke")
    start_nodes = start_node_candidates(created["document"])
    if not start_nodes:
        raise RuntimeError("created blueprint has no AgentNode start candidate")
    start_node = start_nodes[0]

    listed = gulicode_bp_mcp.blueprint_list(str(project))
    opened = gulicode_bp_mcp.blueprint_open(str(project), "standalone-smoke")
    validated = gulicode_bp_mcp.blueprint_validate(str(project), "standalone-smoke")
    sessions = gulicode_bp_mcp.state.request(
        "blueprint.sessions.list",
        {"projectDir": str(project), "blueprintId": "standalone-smoke"},
    )
    popo_status_response = gulicode_bp_mcp.state.popo_service_status()
    popo_status = popo_status_response.get("popo", popo_status_response)
    health_url = str(popo_status.get("healthUrl") or "")
    with urllib.request.urlopen(health_url, timeout=5) as response:
        popo_health = json.loads(response.read().decode("utf-8"))

    output = {
        "ok": True,
        "runtimePackage": str(Path(multi_agent_tcp.__file__).resolve()),
        "dependencyModules": {
            "flask": str(Path(flask.__file__).resolve()),
            "requests": str(Path(requests.__file__).resolve()),
            "Crypto": str(Path(AES.__file__).resolve()),
            "popo": str(Path(multi_agent_tcp.popo_agent_bot_run.__file__).resolve()),
        },
        "popoStatus": popo_status,
        "popoHealth": popo_health,
        "projectDir": str(project.resolve()),
        "listedIds": [item.get("id") for item in listed.get("blueprints", [])],
        "startNodeIds": [start_node],
        "openedId": opened.get("document", {}).get("id"),
        "validateOk": validated.get("ok"),
        "sessionCount": len(sessions.get("sessions", [])),
    }
    if "standalone-smoke" not in output["listedIds"]:
        raise RuntimeError("created blueprint was not listed")
    if output["openedId"] != "standalone-smoke" or not output["validateOk"]:
        raise RuntimeError("standalone blueprint CRUD validation failed")
    if not popo_status.get("ok") or not popo_health.get("ok"):
        raise RuntimeError("standalone POPO callback service is not healthy")
    print(json.dumps(output, ensure_ascii=False, indent=2))
finally:
    gulicode_bp_mcp.state.close()
"""


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def load_mcp_server(plugin_root: Path) -> dict[str, Any]:
    payload = read_json(plugin_root / ".mcp.json")
    try:
        server = payload["mcpServers"][PLUGIN_NAME]
    except KeyError as exc:
        raise RuntimeError(f"{plugin_root / '.mcp.json'} does not define {PLUGIN_NAME!r}") from exc
    if not isinstance(server, dict):
        raise RuntimeError(f"{PLUGIN_NAME!r} MCP entry must be a JSON object")
    env = server.get("env", {})
    if not isinstance(env, dict):
        raise RuntimeError(f"{PLUGIN_NAME!r} MCP env must be a JSON object")
    forbidden = [key for key in ("GULICODE_BP_REPO_ROOT", "PYTHONPATH") if str(env.get(key) or "").strip()]
    if forbidden:
        raise RuntimeError(f"{plugin_root / '.mcp.json'} must not set standalone-forbidden env keys: {forbidden}")
    return server


def build_child_env(plugin_root: Path, server: dict[str, Any]) -> dict[str, str]:
    child_env = {key: value for key, value in os.environ.items()}
    server_env = server.get("env", {})
    if not isinstance(server_env, dict):
        raise RuntimeError(f"{PLUGIN_NAME!r} MCP env must be a JSON object")
    for key, value in server_env.items():
        if value is not None:
            text = str(value)
            if str(key) == "GULICODE_BP_PLUGIN_ROOT" and text == ".":
                text = str(plugin_root)
            child_env[str(key)] = text
    child_env.setdefault("GULICODE_BP_PLUGIN_ROOT", str(plugin_root))
    child_env.setdefault("GULICODE_BP_RUNTIME_HOME", str(plugin_root / ".runtime"))
    child_env.setdefault("GULICODE_BP_DATA_DIR", str(plugin_root / ".runtime" / "state"))
    child_env["GULICODE_BP_DISABLE_REPO_FALLBACK"] = "1"
    child_env["PYTHONPATH"] = ""
    child_env.pop("GULICODE_BP_REPO_ROOT", None)
    return child_env


def _same_or_child(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _server_args(server: dict[str, Any]) -> list[str]:
    raw_args = server.get("args", [])
    if raw_args is None:
        return []
    if not isinstance(raw_args, list):
        raise RuntimeError(f"{PLUGIN_NAME!r} MCP args must be an array")
    return [str(item) for item in raw_args]


def _server_cwd(plugin_root: Path, server: dict[str, Any]) -> Path:
    raw = str(server.get("cwd") or ".")
    if raw == ".":
        return plugin_root
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = plugin_root / path
    return path.resolve()


def _prepare_runtime_from_mcp_entry(
    plugin_root: Path,
    server: dict[str, Any],
    *,
    env: dict[str, str],
    cwd: Path,
    timeout: float,
) -> dict[str, Any]:
    command = str(server.get("command") or "").strip()
    if not command:
        raise RuntimeError(f"{PLUGIN_NAME!r} MCP command is missing")
    args = _server_args(server)
    if not any(arg.replace("\\", "/").endswith("scripts/bootstrap_mcp.py") for arg in args):
        return {
            "runtimePython": command,
            "runtimeHome": env["GULICODE_BP_RUNTIME_HOME"],
            "runtimeDataDir": env["GULICODE_BP_DATA_DIR"],
        }
    result = subprocess.run(
        [command, *args, "--print-runtime-json"],
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if result.returncode != 0:
        diagnostics = "\n".join(
            part.strip()
            for part in (result.stdout, result.stderr)
            if part and part.strip()
        )
        raise RuntimeError("standalone runtime bootstrap failed" + (f"\n{diagnostics}" if diagnostics else ""))
    payload = json.loads(result.stdout)
    env["GULICODE_BP_PLUGIN_ROOT"] = str(payload["pluginRoot"])
    env["GULICODE_BP_RUNTIME_HOME"] = str(payload["runtimeHome"])
    env["GULICODE_BP_DATA_DIR"] = str(payload["runtimeDataDir"])
    env["GULICODE_BP_DISABLE_REPO_FALLBACK"] = "1"
    return payload


def run_smoke(plugin_root: Path, *, timeout: float) -> dict[str, Any]:
    plugin_root = plugin_root.expanduser().resolve()
    server = load_mcp_server(plugin_root)
    cwd = _server_cwd(plugin_root, server)
    env = build_child_env(plugin_root, server)
    bootstrap = _prepare_runtime_from_mcp_entry(plugin_root, server, env=env, cwd=cwd, timeout=timeout)
    runtime_python = str(bootstrap["runtimePython"])
    result = subprocess.run(
        [runtime_python, "-c", SMOKE_CODE],
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if result.returncode != 0:
        diagnostics = "\n".join(
            part.strip()
            for part in (result.stdout, result.stderr)
            if part and part.strip()
        )
        raise RuntimeError("standalone gulicode-bp smoke failed" + (f"\n{diagnostics}" if diagnostics else ""))
    output = json.loads(result.stdout)
    runtime_package = Path(str(output.get("runtimePackage") or "")).expanduser()
    runtime_home = Path(env["GULICODE_BP_RUNTIME_HOME"]).expanduser()
    if not _same_or_child(runtime_package, runtime_home / "venv"):
        raise RuntimeError(f"runtime package did not load from plugin venv: {runtime_package}")
    dependency_modules = output.get("dependencyModules", {})
    if not isinstance(dependency_modules, dict):
        raise RuntimeError("standalone smoke did not report dependency modules")
    for name, raw_path in dependency_modules.items():
        module_path = Path(str(raw_path or "")).expanduser()
        if not _same_or_child(module_path, runtime_home / "venv"):
            raise RuntimeError(f"{name} did not load from plugin venv: {module_path}")
    output["bootstrap"] = bootstrap
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke an installed gulicode-bp plugin")
    parser.add_argument(
        "--plugin-root",
        type=Path,
        default=Path.home() / "plugins" / PLUGIN_NAME,
        help="installed gulicode-bp plugin root",
    )
    parser.add_argument("--timeout", type=float, default=180.0, help="child process timeout in seconds")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = run_smoke(args.plugin_root, timeout=args.timeout)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
