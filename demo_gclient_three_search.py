"""
Three ``codex-worker`` agents searching gclient code **in parallel** via
:class:`CLIWorkerBackend`.

Usage (from ``f:\\src\\Package\\Script\\Python``)::

    python -m multi_agent_tcp.demo_gclient_three_search
    python -m multi_agent_tcp.demo_gclient_three_search --trace --port 9140

Requires ``codex`` on PATH.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

from multi_agent_tcp.cli_worker_backend import CLIWorkerBackend, WorkerConfig
from multi_agent_tcp.log_setup import setup_logging

REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_workers(cwd: Path, model: str, timeout_sec: float) -> list[WorkerConfig]:
    return [
        WorkerConfig("cm1", cwd=cwd, model=model, timeout_sec=timeout_sec),
        WorkerConfig("cm2", cwd=cwd, model=model, timeout_sec=timeout_sec),
        WorkerConfig("cm3", cwd=cwd, model=model, timeout_sec=timeout_sec),
    ]


def _gclient_tasks() -> list[tuple[str, dict]]:
    root = "gclient"
    return [
        ("cm1", {"prompt": (
            f"你在项目根目录下工作，客户端代码在子目录 `{root}/`。\n"
            "【任务1】大厅「新模式选择 / 选图」相关的 `GameChooseWindow`（2026 版 UI）"
            "主要在哪个（哪些）Python 文件里定义？请给出相对路径（从项目根开始），"
            "并一句话说明依据（例如类名、文件名）。不要编造路径；在仓库里搜索确认。贴出作答开始时间和结束时间。"
        )}),
        ("cm2", {"prompt": (
            f"你在项目根目录下工作，客户端代码在子目录 `{root}/`。\n"
            "【任务2】爆破玩法里客户端侧 `GameLogicBlasting` 类在哪个文件实现？"
            "请给出相对路径（从项目根开始）和一句说明。不要编造；在仓库里搜索确认。贴出作答开始时间和结束时间。"
        )}),
        ("cm3", {"prompt": (
            f"你在项目根目录下工作，客户端代码在子目录 `{root}/`。\n"
            "【任务3】地图上标记点 / Mark 相关 UI 组件里，`mapbase_mark_comp`（或同类地图标记）"
            "对应的主要 Python 文件路径是什么？给出相对路径（从项目根开始）和一句说明。"
            "不要编造；在仓库里搜索确认。贴出作答开始时间和结束时间。"
        )}),
    ]


async def _run(
    host: str, port: int, cwd: Path, model: str, verbose: bool,
    gather_timeout: float, worker_timeout: float,
    output: Path | None, raw_output: Path | None,
    max_retries: int = 2, retry_delay_sec: float = 5.0,
) -> None:
    workers = _make_workers(cwd, model, worker_timeout)
    work = Path(tempfile.gettempdir()) / "multi_agent_tcp_gclient_search"
    work.mkdir(parents=True, exist_ok=True)

    async with await CLIWorkerBackend.create(
        workers, host=host, port=port, verbose=verbose,
    ) as cluster:
        par = await cluster.run_parallel(
            _gclient_tasks(),
            timeout_sec=gather_timeout,
            max_retries=max_retries,
            retry_delay_sec=retry_delay_sec,
        )

    raw_out = raw_output or (work / "gclient_gather_raw.json")
    raw_out.write_text(json.dumps(par.to_raw_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    summary_out = output or (work / "gclient_gather_summary.json")
    summary_dict = par.to_dict()
    summary_text = json.dumps(summary_dict, ensure_ascii=False, indent=2)
    summary_out.write_text(summary_text, encoding="utf-8")

    log = __import__("logging").getLogger(__name__)
    log.info("raw result  -> %s", raw_out)
    log.info("summary     -> %s", summary_out)
    log.info("succeeded: %s  failed: %s", len(par.succeeded), len(par.failed))
    try:
        print(par.summary, file=sys.stderr)
        print("---", file=sys.stderr)
        print(summary_text, file=sys.stderr)
    except UnicodeEncodeError:
        sys.stderr.buffer.write(summary_text.encode("utf-8", errors="replace") + b"\n")
        sys.stderr.buffer.flush()

    if not par.ok:
        raise SystemExit(1)


def main() -> None:
    p = argparse.ArgumentParser(description="3 Codex workers parallel search (CLIWorkerBackend)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9140)
    p.add_argument("--cwd", type=Path, default=REPO_ROOT)
    p.add_argument("--model", default="gpt-5.4")
    p.add_argument("--trace", action="store_true")
    p.add_argument("--worker-timeout-sec", type=float, default=1800.0)
    p.add_argument("--gather-timeout-sec", type=float, default=1800.0)
    p.add_argument("--max-retries", type=int, default=2)
    p.add_argument("--retry-delay-sec", type=float, default=5.0)
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--raw-output", type=Path, default=None)
    args = p.parse_args()
    setup_logging(args.trace, name="demo_gclient_three_search")

    cwd = args.cwd.expanduser().resolve()
    if not cwd.is_dir():
        raise SystemExit(f"--cwd is not a directory: {cwd}")
    if not (cwd / "gclient").is_dir():
        raise SystemExit(f"--cwd must contain gclient/: {cwd}")

    try:
        asyncio.run(_run(
            args.host, args.port, cwd, args.model, args.trace,
            args.gather_timeout_sec, args.worker_timeout_sec,
            args.output, args.raw_output,
            max_retries=args.max_retries,
            retry_delay_sec=args.retry_delay_sec,
        ))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)


if __name__ == "__main__":
    main()
