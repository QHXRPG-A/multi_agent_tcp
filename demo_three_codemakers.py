"""
Three ``codemaker-worker`` agents in a serial chain via :class:`CodeMakerCluster`.

cm1 → cm2 → cm3, each step's answer is injected as ``context`` into the next.

Usage (from ``f:\\src\\Package\\Script\\Python``)::

    python -m multi_agent_tcp.demo_three_codemakers
    python -m multi_agent_tcp.demo_three_codemakers --port 9133 --trace

Requires ``codemaker`` on PATH and CodeMaker auth. See codemaker_cli.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from multi_agent_tcp.cluster import CodeMakerCluster, WorkerConfig
from multi_agent_tcp.log_setup import setup_logging

REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_workers(cwd: Path, model: str) -> list[WorkerConfig]:
    return [
        WorkerConfig("cm1", cwd=cwd, model=model),
        WorkerConfig("cm2", cwd=cwd, model=model),
        WorkerConfig("cm3", cwd=cwd, model=model),
    ]


async def _run(host: str, port: int, cwd: Path, model: str, verbose: bool) -> None:
    workers = _make_workers(cwd, model)
    async with await CodeMakerCluster.create(
        workers, host=host, port=port, verbose=verbose,
    ) as cluster:
        results = await cluster.run_chain([
            ("cm1", {"prompt": "你是多智能体演示里的 cm1。请用一两句中文自我介绍，并随便说一个整数。"}),
            ("cm2", {"prompt": "你是 cm2。下面是 cm1 经 TCP 传给你的上游输出。请用一两句中文接话并换一个整数。"}),
            ("cm3", {"prompt": "你是 cm3，链路最后一环。根据下面 cm2 的输出用一两句中文收尾。"}),
        ])
        for i, r in enumerate(results):
            worker = ("cm1", "cm2", "cm3")[i]
            body = r.get("body", {})
            print(f"--- {worker} 回复 ---")
            print(json.dumps(body, ensure_ascii=False, indent=2)[:4000])


def main() -> None:
    p = argparse.ArgumentParser(description="Broker + 3 codemaker-worker chain demo (CodeMakerCluster)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9133)
    p.add_argument("--cwd", type=Path, default=REPO_ROOT)
    p.add_argument("--model", default="netease-codemaker/kimi-k2.5")
    p.add_argument("--trace", action="store_true")
    args = p.parse_args()
    setup_logging(args.trace, name="demo_three_codemakers")
    try:
        asyncio.run(_run(args.host, args.port, args.cwd.expanduser().resolve(), args.model, args.trace))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)


if __name__ == "__main__":
    main()
