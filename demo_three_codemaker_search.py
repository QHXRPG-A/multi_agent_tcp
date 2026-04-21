"""
Start broker + three ``codemaker-worker`` agents (cm1/cm2/cm3), then run **one**
``batch_gather`` with three independent search-style prompts (parallel CodeMaker runs).

From repo root ``f:\\src\\Package\\Script\\Python``::

    python -m multi_agent_tcp.demo_three_codemaker_search
    python -m multi_agent_tcp.demo_three_codemaker_search --port 9134 --cwd .

Requires ``codemaker`` on PATH and valid CodeMaker auth (see codemaker_cli.md).
Stop with Ctrl+C; children are terminated in ``finally``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from multi_agent_tcp.client import AgentTCPClient

REPO_ROOT = Path(__file__).resolve().parents[1]


def _agent_config(agent_id: str, host: str, port: int, cwd: Path, model: str) -> Dict[str, Any]:
    return {
        "agent_id": agent_id,
        "broker_host": host,
        "broker_port": port,
        "role": "codemaker",
        "mode": "codemaker-worker",
        "codemaker": {
            "command": "codemaker",
            "cwd": str(cwd),
            "model": model,
            "base_args": ["run", "--format", "json"],
            "prompt_via_file": "auto",
            "timeout_sec": 600,
        },
    }


def _search_tasks() -> List[tuple[str, Dict[str, Any]]]:
    """Three distinct tasks; each body matches codemaker-worker ``prompt`` (+ optional ``context``)."""
    return [
        (
            "cm1",
            {
                "prompt": (
                    "【搜索任务 A】请根据你掌握的知识或可用工具（如网络检索），用中文简要说明："
                    "Rust 语言所有权（ownership）要解决的核心问题是什么？给出 2～4 句话即可。"
                )
            },
        ),
        (
            "cm2",
            {
                "prompt": (
                    "【搜索任务 B】请根据你掌握的知识或可用工具（如网络检索），用中文简要说明："
                    "HTTP/3 相对 HTTP/2 的主要变化是什么？给出 2～4 句话即可。"
                )
            },
        ),
        (
            "cm3",
            {
                "prompt": (
                    "【搜索任务 C】请根据你掌握的知识或可用工具（如网络检索），用中文简要说明："
                    "向量数据库（vector DB）常见用途是什么？给出 2～4 句话即可。"
                )
            },
        ),
    ]


async def _wait_broker_tcp(host: str, port: int, seconds: float = 20.0) -> None:
    deadline = time.monotonic() + seconds
    last: Optional[BaseException] = None
    while time.monotonic() < deadline:
        try:
            r, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=1.0)
            w.close()
            await w.wait_closed()
            return
        except (asyncio.TimeoutError, OSError, ConnectionError) as e:
            last = e
            await asyncio.sleep(0.2)
    raise RuntimeError(f"broker not reachable at {host}:{port}: {last!r}")


async def _run_batch_search(host: str, port: int, gather_id: str) -> Dict[str, Any]:
    orch = AgentTCPClient("orchestrator", host, port, role="search-driver")
    await orch.connect()
    try:
        return await orch.batch_gather(gather_id, _search_tasks(), timeout_sec=600.0)
    finally:
        await orch.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Broker + 3 codemaker workers + parallel search batch_gather")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9134, help="avoid clash with demo_three_codemakers 9133")
    p.add_argument(
        "--cwd",
        type=Path,
        default=REPO_ROOT,
        help="codemaker subprocess cwd (project root; current code dir recommended)",
    )
    p.add_argument(
        "--model",
        default="netease-codemaker/kimi-k2.5",
        help='codemaker -m "netease-codemaker/..."',
    )
    p.add_argument(
        "--gather-id",
        default="search-batch-demo-1",
        help="batch_gather id (must be unique per in-flight gather on broker)",
    )
    args = p.parse_args()
    host, port = args.host, int(args.port)
    cwd: Path = args.cwd.expanduser().resolve()
    if not cwd.is_dir():
        raise SystemExit(f"--cwd is not a directory: {cwd}")

    work = Path(tempfile.gettempdir()) / "multi_agent_tcp_demo_search"
    work.mkdir(parents=True, exist_ok=True)
    broker_cfg = work / "broker.json"
    broker_cfg.write_text(json.dumps({"host": host, "port": port}, indent=2), encoding="utf-8")

    agent_ids = ["cm1", "cm2", "cm3"]
    cfg_paths: List[Path] = []
    for aid in agent_ids:
        path = work / f"agent_{aid}.json"
        path.write_text(
            json.dumps(_agent_config(aid, host, port, cwd, args.model), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        cfg_paths.append(path)

    py = sys.executable
    out = subprocess.DEVNULL
    if os.environ.get("MULTI_AGENT_TCP_VERBOSE"):
        out = None
    child_env = {**os.environ, "PYTHONUTF8": "1"}

    broker_p = subprocess.Popen(
        [py, "-m", "multi_agent_tcp", "broker", "--config", str(broker_cfg)],
        stdout=out,
        stderr=out,
        env=child_env,
    )
    agent_ps: List[subprocess.Popen] = []
    try:
        asyncio.run(_wait_broker_tcp(host, port))
        for path in cfg_paths:
            agent_ps.append(
                subprocess.Popen(
                    [py, "-m", "multi_agent_tcp", "agent", "--config", str(path)],
                    stdout=out,
                    stderr=out,
                    env=child_env,
                )
            )
        time.sleep(1.0)
        result = asyncio.run(_run_batch_search(host, port, str(args.gather_id).strip()))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            raise SystemExit(1)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
    finally:
        for proc in agent_ps:
            if proc.poll() is None:
                proc.terminate()
        for proc in agent_ps:
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
        if broker_p.poll() is None:
            broker_p.terminate()
        try:
            broker_p.wait(timeout=8)
        except subprocess.TimeoutExpired:
            broker_p.kill()


if __name__ == "__main__":
    main()
