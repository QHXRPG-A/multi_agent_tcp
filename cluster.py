"""High-level backend for orchestrating multiple CLI-backed Agent workers.

Two creation modes:

* ``CLIWorkerBackend.create(workers, ...)`` — start broker + worker subprocesses
  (persistent backend, accepts many task submissions).
* ``CLIWorkerBackend.connect(...)`` — attach to an already-running broker/backend.

Typical usage::

    from multi_agent_tcp import CLIWorkerBackend, WorkerConfig

    async with await CLIWorkerBackend.create(
        workers=[
            WorkerConfig("cm1", cwd=Path("F:/src")),
            WorkerConfig("cm2", cwd=Path("F:/src")),
        ],
        port=9140,
    ) as backend:
        result = await backend.run_parallel([
            ("cm1", {"prompt": "Task A"}),
            ("cm2", {"prompt": "Task B"}),
        ])
        for wr in result.succeeded:
            print(wr.worker, wr.answer[:200])
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Tuple

from .client import AgentTCPClient
from ._proc_utils import terminate_and_wait

if TYPE_CHECKING:
    from .registry import AgentsRegistry

log = logging.getLogger(__name__)

_IS_WIN = sys.platform == "win32"


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

@dataclass
class WorkerConfig:
    """Configuration for one CLI-backed worker process."""

    agent_id: str
    cwd: Path
    model: str = "netease-codemaker/kimi-k2.5"
    timeout_sec: float = 1800.0
    prompt_via_file: str = "auto"
    command: str = "codemaker"
    cli_kind: str = "codemaker"
    adapter_options: Dict[str, Any] = field(default_factory=dict)
    extra_env: Dict[str, str] = field(default_factory=dict)

    def to_agent_json(self, host: str, port: int) -> Dict[str, Any]:
        """Serialize to the JSON config consumed by ``__main__.py agent``."""
        cli_kind = str(self.cli_kind or "codemaker").strip().lower()
        command = str(self.command or "").strip()
        if cli_kind == "codex" and (not command or command == "codemaker"):
            command = "codex"
        elif not command:
            command = "codemaker"

        codemaker_cfg = {
            "command": command,
            "cwd": str(self.cwd),
            "model": self.model,
            "base_args": ["run", "--format", "json"],
            "prompt_via_file": self.prompt_via_file,
            "timeout_sec": self.timeout_sec,
        }
        codex_cfg = {
            "command": command,
            "cwd": str(self.cwd),
            "model": self.model,
            "base_args": ["exec"],
            "timeout_sec": self.timeout_sec,
            "json": True,
            "output_last_message": True,
            "ephemeral": True,
        }
        adapter_options = dict(self.adapter_options or {})
        if cli_kind == "codex":
            codex_cfg.update(adapter_options)
        else:
            codemaker_cfg.update(adapter_options)
        return {
            "agent_id": self.agent_id,
            "broker_host": host,
            "broker_port": port,
            "role": cli_kind,
            "mode": f"{cli_kind}-worker" if cli_kind != "codemaker" else "codemaker-worker",
            "cli_kind": cli_kind,
            "codemaker": codemaker_cfg,
            "codex": codex_cfg,
            "adapter_options": adapter_options,
            "extra_env": self.extra_env or {},
        }


# ---------------------------------------------------------------------------
# Structured result types
# ---------------------------------------------------------------------------

@dataclass
class WorkerResult:
    """Structured result from a single CLI worker execution."""

    worker: str
    status: str  # "success" | "error" | "timeout" | "empty"
    answer: str
    raw_stdout: str = ""
    stderr: str = ""
    elapsed_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """LLM-friendly: only status + answer."""
        return {"status": self.status, "answer": self.answer}

    def to_raw_dict(self) -> Dict[str, Any]:
        """Full dict including raw_stdout / stderr / elapsed for debugging."""
        d: Dict[str, Any] = {
            "worker": self.worker,
            "status": self.status,
            "answer": self.answer,
        }
        if self.raw_stdout:
            d["raw_stdout"] = self.raw_stdout
        if self.stderr:
            d["stderr"] = self.stderr
        if self.elapsed_sec > 0:
            d["elapsed_sec"] = self.elapsed_sec
        return d


class ParallelResult:
    """Structured result from :meth:`CLIWorkerBackend.run_parallel`.

    Attributes:
        succeeded: workers that finished successfully.
        failed: workers that errored, timed out, or returned empty.
        all: every worker keyed by ``agent_id``.
        summary: human-readable text suitable for an upstream LLM.
        ok: True if every worker succeeded.
        raw: the original ``gather_result`` dict from the broker.
    """

    def __init__(
        self,
        raw: Dict[str, Any],
        workers: Dict[str, WorkerResult],
    ) -> None:
        self._raw = raw
        self._workers = workers

    @property
    def succeeded(self) -> List[WorkerResult]:
        return [w for w in self._workers.values() if w.status == "success"]

    @property
    def failed(self) -> List[WorkerResult]:
        return [w for w in self._workers.values() if w.status != "success"]

    @property
    def all(self) -> Dict[str, WorkerResult]:
        return dict(self._workers)

    @property
    def ok(self) -> bool:
        return bool(self._workers) and all(
            w.status == "success" for w in self._workers.values()
        )

    @property
    def raw(self) -> Dict[str, Any]:
        return self._raw

    @property
    def summary(self) -> str:
        lines: List[str] = []
        for wr in self._workers.values():
            tag = "OK" if wr.status == "success" else wr.status.upper()
            snippet = wr.answer[:300].replace("\n", " ") if wr.answer else "(no answer)"
            lines.append(f"[{tag}] {wr.worker}: {snippet}")
        total = len(self._workers)
        ok_n = len(self.succeeded)
        lines.insert(0, f"Parallel result: {ok_n}/{total} succeeded")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """LLM-friendly: ok + per-worker status/answer + summary."""
        return {
            "ok": self.ok,
            "workers": {wid: wr.to_dict() for wid, wr in self._workers.items()},
            "summary": self.summary,
        }

    def to_raw_dict(self) -> Dict[str, Any]:
        """Full dict including raw_stdout / stderr / elapsed for debugging."""
        return {
            "ok": self.ok,
            "workers": {wid: wr.to_raw_dict() for wid, wr in self._workers.items()},
            "summary": self.summary,
        }

    def __repr__(self) -> str:
        return (
            f"ParallelResult(ok={self.ok}, "
            f"succeeded={len(self.succeeded)}, "
            f"failed={len(self.failed)})"
        )


@dataclass
class ReduceResult:
    """Result from :meth:`CLIWorkerBackend.run_parallel_reduce`.

    Combines a ``ParallelResult`` (fan-out) with a final ``WorkerResult``
    (reduce step).
    """

    parallel: ParallelResult
    reduce: WorkerResult

    @property
    def answer(self) -> str:
        return self.reduce.answer

    @property
    def ok(self) -> bool:
        return self.reduce.status == "success"

    def to_dict(self) -> Dict[str, Any]:
        """LLM-friendly: ok + parallel summary + reduce answer."""
        return {
            "ok": self.ok,
            "parallel": self.parallel.to_dict(),
            "reduce": self.reduce.to_dict(),
            "answer": self.answer,
        }

    def to_raw_dict(self) -> Dict[str, Any]:
        """Full dict including raw_stdout / stderr / elapsed for debugging."""
        return {
            "ok": self.ok,
            "parallel": self.parallel.to_raw_dict(),
            "reduce": self.reduce.to_raw_dict(),
            "answer": self.answer,
        }

    def __repr__(self) -> str:
        return (
            f"ReduceResult(ok={self.ok}, "
            f"parallel={self.parallel!r}, "
            f"reduce_worker={self.reduce.worker!r})"
        )


# ---------------------------------------------------------------------------
# Result helpers (extracted from demo_gclient_three_search)
# ---------------------------------------------------------------------------

def extract_final_text(stdout: str) -> str:
    """Parse CodeMaker NDJSON stdout, return concatenated ``type: "text"`` entries."""
    parts: List[str] = []
    for line in stdout.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "text":
            text = obj.get("part", {}).get("text", "")
            if text:
                parts.append(text)
    return "\n".join(parts) if parts else ""


def summarize_gather_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce a full ``gather_result`` to agent ids + final answer text.

    .. deprecated:: 0.3.0
        Use :meth:`ParallelResult.to_dict` or iterate
        :attr:`ParallelResult.all` instead.
    """
    summary: Dict[str, Any] = {
        "id": result.get("id"),
        "ok": result.get("ok"),
        "agents": {},
        "errors": result.get("errors", {}),
    }
    for agent_id, reply in result.get("replies", {}).items():
        body = reply.get("body", {})
        cm = body.get("codemaker", {})
        stdout = cm.get("stdout", "")
        summary["agents"][agent_id] = {
            "ok": body.get("ok"),
            "returncode": cm.get("returncode"),
            "timeout": cm.get("timeout", False),
            "answer": extract_final_text(stdout),
        }
    return summary


def _parse_worker_result(agent_id: str, reply: Dict[str, Any]) -> WorkerResult:
    """Build a :class:`WorkerResult` from one entry in ``gather_result.replies``."""
    body = reply.get("body", {})
    if isinstance(body, str):
        return WorkerResult(
            worker=agent_id, status="error", answer="",
            stderr=body,
        )

    codex = body.get("codex", {})
    if isinstance(codex, dict) and codex:
        stdout = codex.get("stdout", "")
        stderr = codex.get("stderr", "")
        answer = str(codex.get("final_text") or codex.get("last_message") or "")
        is_timeout = codex.get("timeout", False)
        ok = body.get("ok", False)
        if is_timeout:
            status = "timeout"
        elif not ok:
            status = "error"
        elif not answer.strip():
            status = "empty"
        else:
            status = "success"
        return WorkerResult(
            worker=agent_id,
            status=status,
            answer=answer,
            raw_stdout=stdout,
            stderr=stderr,
            elapsed_sec=codex.get("elapsed_sec", 0.0),
        )

    cm = body.get("codemaker", {})
    stdout = cm.get("stdout", "")
    stderr = cm.get("stderr", "")
    answer = extract_final_text(stdout)
    is_timeout = cm.get("timeout", False)
    returncode = cm.get("returncode")
    ok = body.get("ok", False)

    if is_timeout:
        status = "timeout"
    elif not ok:
        status = "error"
    elif not answer.strip():
        status = "empty"
    else:
        status = "success"

    return WorkerResult(
        worker=agent_id,
        status=status,
        answer=answer,
        raw_stdout=stdout,
        stderr=stderr,
        elapsed_sec=cm.get("elapsed_sec", 0.0),
    )


def _parse_single_reply_to_worker_result(
    worker_id: str, reply: Dict[str, Any],
) -> WorkerResult:
    """Build a :class:`WorkerResult` from a ``run_single`` reply message."""
    return _parse_worker_result(worker_id, reply)


def _build_parallel_result(raw: Dict[str, Any]) -> ParallelResult:
    """Build a :class:`ParallelResult` from a raw ``gather_result`` dict."""
    workers: Dict[str, WorkerResult] = {}
    for agent_id, reply in raw.get("replies", {}).items():
        workers[agent_id] = _parse_worker_result(agent_id, reply)
    for agent_id, err in raw.get("errors", {}).items():
        if agent_id not in workers:
            workers[agent_id] = WorkerResult(
                worker=agent_id,
                status="error",
                answer="",
                stderr=err.get("message", str(err)),
            )
    return ParallelResult(raw, workers)


# ---------------------------------------------------------------------------
# Retryable error detection
# ---------------------------------------------------------------------------

_RETRYABLE_PATTERNS = [
    "database is locked",
    "resource temporarily unavailable",
]


def is_retryable_error(reply: Dict[str, Any]) -> bool:
    """Return True if a worker reply indicates a transient, retryable failure.

    Checks ``body.codemaker.stderr`` for known patterns like SQLite lock
    contention that resolve on retry.
    """
    body = reply.get("body", {})
    if isinstance(body, str):
        return False
    if body.get("ok"):
        return False
    cm = body.get("codemaker", {})
    stderr = cm.get("stderr", "").lower()
    return any(pat in stderr for pat in _RETRYABLE_PATTERNS)


def _format_results_for_reduce(par: ParallelResult) -> str:
    """Format parallel results into a text block for the reduce prompt."""
    sections: List[str] = []
    for wid, wr in par.all.items():
        header = f"=== Worker: {wid} | Status: {wr.status} ==="
        body = wr.answer if wr.answer else "(no answer)"
        sections.append(f"{header}\n{body}")
    return "\n\n".join(sections)


def _reply_body_to_context(reply_msg: Dict[str, Any]) -> str:
    """Extract a text string from a worker reply suitable for chain injection.

    .. deprecated:: 0.3.0
        Prefer :func:`_reply_to_structured_context`.
    """
    body = reply_msg.get("body", {})
    if isinstance(body, str):
        return body
    cm = body.get("codemaker", {})
    stdout = cm.get("stdout", "")
    text = extract_final_text(stdout)
    if text:
        return text
    return json.dumps(body, ensure_ascii=False)


def _reply_to_structured_context(
    worker_id: str, reply_msg: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a structured context dict from a worker reply for chain injection.

    The downstream worker's prompt template can reference ``context.answer``.
    """
    wr = _parse_single_reply_to_worker_result(worker_id, reply_msg)
    return {
        "worker": wr.worker,
        "status": wr.status,
        "answer": wr.answer,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _wait_broker_tcp(host: str, port: int, seconds: float = 25.0) -> None:
    deadline = time.monotonic() + seconds
    last: Optional[BaseException] = None
    while time.monotonic() < deadline:
        try:
            r, w = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=1.0,
            )
            w.close()
            await w.wait_closed()
            return
        except (asyncio.TimeoutError, OSError, ConnectionError) as e:
            last = e
            await asyncio.sleep(0.2)
    raise RuntimeError(f"broker not reachable at {host}:{port}: {last!r}")


def _spawn(cmd: List[str], title: str, *, verbose: bool, env: Dict[str, str]) -> subprocess.Popen:
    log.info("spawn [%s] cmd=%s", title, cmd)
    kwargs: Dict[str, Any] = {"env": env}
    if _IS_WIN:
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
        si = subprocess.STARTUPINFO()
        si.lpTitle = title  # type: ignore[attr-defined]
        kwargs["startupinfo"] = si
    else:
        kwargs["stdout"] = None if verbose else subprocess.DEVNULL
        kwargs["stderr"] = None if verbose else subprocess.DEVNULL
    return subprocess.Popen(cmd, **kwargs)


# ---------------------------------------------------------------------------
# CLIWorkerBackend
# ---------------------------------------------------------------------------

class CLIWorkerBackend:
    """Manage a broker plus N CLI-backed worker processes and submit tasks.

    The historical public name was ``CodeMakerCluster``. The implementation is
    now CLI-agnostic: each worker chooses its adapter via ``WorkerConfig.cli_kind``
    and can point at CodeMaker, Codex, or another compatible CLI command.
    """

    def __init__(self) -> None:
        self._host: str = "127.0.0.1"
        self._port: int = 9140
        self._workers: List[WorkerConfig] = []
        self._broker_proc: Optional[subprocess.Popen] = None
        self._agent_procs: List[subprocess.Popen] = []
        self._agent_proc_by_id: Dict[str, subprocess.Popen] = {}
        self._tmp_files: List[Path] = []
        self._work_dir: Optional[Path] = None
        self._owns_processes: bool = False
        self._client: Optional[AgentTCPClient] = None
        self._self_id: str = "orchestrator"
        self._verbose: bool = False
        self._started: bool = False
        self._registry: Optional["AgentsRegistry"] = None
        self._skill_mode: str = "catalog"

    # ---- Factory methods ---------------------------------------------------

    @classmethod
    async def create(
        cls,
        workers: List[WorkerConfig],
        *,
        host: str = "127.0.0.1",
        port: int = 9140,
        verbose: bool = False,
        allow_empty: bool = False,
    ) -> "CLIWorkerBackend":
        """Start a broker + N worker subprocesses.

        The returned backend owns the processes; call ``stop()`` (or use as
        async context manager) to tear them down.
        """
        if not workers and not allow_empty:
            raise ValueError("workers list must be non-empty")
        inst = cls()
        inst._host = host
        inst._port = int(port)
        inst._workers = list(workers)
        inst._owns_processes = True
        inst._verbose = verbose
        await inst._start_processes()
        return inst

    @classmethod
    async def connect(
        cls,
        *,
        host: str = "127.0.0.1",
        port: int = 9140,
        self_id: str = "orchestrator",
        worker_ids: Optional[List[str]] = None,
    ) -> "CLIWorkerBackend":
        """Connect to an already-running broker and externally managed workers."""
        inst = cls()
        inst._host = host
        inst._port = int(port)
        inst._self_id = self_id
        inst._owns_processes = False
        if worker_ids:
            inst._workers = [WorkerConfig(wid, cwd=Path(".")) for wid in worker_ids]
        await _wait_broker_tcp(host, port, seconds=10.0)
        inst._started = True
        return inst

    @classmethod
    async def create_from_registry(
        cls,
        registry: "AgentsRegistry",
        *,
        agent_ids: Optional[List[str]] = None,
        host: str = "127.0.0.1",
        port: int = 9140,
        verbose: bool = False,
        skill_mode: str = "catalog",
    ) -> "CLIWorkerBackend":
        """Start a backend whose workers are defined in ``agents_registry.json``.

        This is the **recommended** creation method.  It reads model, cwd,
        timeout, and skills from the registry so that ``run_parallel`` /
        ``run_chain`` / ``run_parallel_reduce`` automatically inject skills
        into every task prompt.

        Args:
            registry: A loaded :class:`AgentsRegistry`.
            agent_ids: Subset of registry agents to start.  ``None`` means
                all *enabled* agents.
            skill_mode: ``"catalog"`` (default, lightweight table) or
                ``"full"`` (embed entire SKILL.md contents).
        """
        workers = registry.build_worker_configs(agent_ids)
        if not workers:
            raise ValueError("no enabled agents found in registry")
        inst = await cls.create(workers, host=host, port=port, verbose=verbose)
        inst._registry = registry
        inst._skill_mode = skill_mode
        return inst

    # ---- Skill injection ---------------------------------------------------

    def _inject_skills(
        self,
        tasks: List[Tuple[str, Any]],
    ) -> List[Tuple[str, Any]]:
        """If a registry is bound, prepend skill catalog to each task prompt.

        Leaves tasks unchanged when no registry is set or the target agent
        has no skills configured.
        """
        if self._registry is None:
            return tasks

        result: List[Tuple[str, Any]] = []
        for worker_id, body in tasks:
            agent_id = self._resolve_agent_id(worker_id)
            if agent_id and isinstance(body, dict) and "prompt" in body:
                enriched_prompt = self._registry.inject_skills_into_prompt(
                    agent_id, body["prompt"], mode=self._skill_mode,
                )
                body = {**body, "prompt": enriched_prompt}
            result.append((worker_id, body))
        return result

    def set_registry(
        self,
        registry: "AgentsRegistry",
        skill_mode: str = "catalog",
    ) -> None:
        """Attach a registry to an existing cluster for skill injection.

        Useful for backends created via ``create()`` or ``connect()`` that
        should also benefit from automatic skill injection.
        """
        self._registry = registry
        self._skill_mode = skill_mode

    def _resolve_agent_id(self, worker_id: str) -> Optional[str]:
        """Map a worker_id back to a registry agent_id.

        When created via ``create_from_registry``, workers keep the same
        agent_id as in the registry.  For ``create`` / ``connect`` modes
        we check if the worker_id happens to exist in the registry.
        """
        if self._registry is None:
            return None
        if worker_id in self._registry.agents:
            return worker_id
        return None

    # ---- Process lifecycle -------------------------------------------------

    async def _start_processes(self) -> None:
        import tempfile

        work = Path(tempfile.gettempdir()) / "multi_agent_tcp_cluster"
        work.mkdir(parents=True, exist_ok=True)
        self._work_dir = work

        py = sys.executable
        env = {**os.environ, "PYTHONUTF8": "1"}
        extra_v = ["-v"] if self._verbose else []

        broker_cfg_path = work / f"broker_{self._port}.json"
        broker_cfg_path.write_text(
            json.dumps({"host": self._host, "port": self._port}, indent=2),
            encoding="utf-8",
        )
        self._tmp_files.append(broker_cfg_path)

        broker_cmd = [
            py, "-m", "multi_agent_tcp", *extra_v,
            "broker", "--config", str(broker_cfg_path),
        ]
        self._broker_proc = _spawn(
            broker_cmd, f"BROKER :{self._port}",
            verbose=self._verbose, env=env,
        )

        await _wait_broker_tcp(self._host, self._port)
        if self._broker_proc.poll() is not None:
            raise RuntimeError(
                f"Broker process exited (rc={self._broker_proc.returncode}) — "
                f"port {self._port} likely occupied by a stale broker. "
                f"Kill old processes or use a different port."
            )

        initial_workers = list(self._workers)
        self._workers = []
        for w in initial_workers:
            await self.ensure_worker(w)

        settle = 4.0 if _IS_WIN else 1.5
        await asyncio.sleep(settle)
        self._started = True
        log.info(
            "CLI worker backend ready host=%s port=%s workers=%s",
            self._host, self._port, [w.agent_id for w in self._workers],
        )

    async def ensure_worker(self, worker: WorkerConfig) -> None:
        """Ensure a worker process is registered for this cluster.

        For graph execution this provides lazy AgentNode startup: the first
        traversal can call this method, and later traversals reuse the same
        broker-registered worker process.
        """
        if worker.agent_id in self.worker_ids:
            return
        if not self._owns_processes:
            raise RuntimeError(
                f"cannot start worker {worker.agent_id!r}: backend does not own processes"
            )
        if self._broker_proc is None or self._broker_proc.poll() is not None:
            raise RuntimeError("cannot start worker: broker process is not running")

        work = self._work_dir or (Path(tempfile.gettempdir()) / "multi_agent_tcp_cluster")
        work.mkdir(parents=True, exist_ok=True)
        cfg_path = work / f"agent_{worker.agent_id}_{self._port}.json"
        cfg_path.write_text(
            json.dumps(
                worker.to_agent_json(self._host, self._port),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._tmp_files.append(cfg_path)
        extra_v = ["-v"] if self._verbose else []
        acmd = [
            sys.executable, "-m", "multi_agent_tcp", *extra_v,
            "agent", "--config", str(cfg_path),
        ]
        env = {**os.environ, "PYTHONUTF8": "1"}
        env.update(worker.extra_env or {})
        self._agent_procs.append(
            _spawn(acmd, f"AGENT {worker.agent_id}", verbose=self._verbose, env=env)
        )
        self._agent_proc_by_id[worker.agent_id] = self._agent_procs[-1]
        self._workers.append(worker)
        settle = 4.0 if _IS_WIN else 1.5
        await asyncio.sleep(settle)
        log.info("worker ready agent_id=%s cli_kind=%s", worker.agent_id, worker.cli_kind)

    async def restart_worker(self, worker: WorkerConfig) -> None:
        """Kill and relaunch one owned worker with the supplied config."""
        if not self._owns_processes:
            raise RuntimeError("cannot restart worker: backend does not own processes")
        proc = self._agent_proc_by_id.pop(worker.agent_id, None)
        if proc is not None:
            terminate_and_wait(proc, timeout=10)
            self._agent_procs = [p for p in self._agent_procs if p is not proc]
        self._workers = [w for w in self._workers if w.agent_id != worker.agent_id]
        await self.ensure_worker(worker)

    async def _ensure_client(self) -> AgentTCPClient:
        """Return a connected orchestrator client, creating one if needed."""
        if self._client is not None:
            return self._client
        cid = f"{self._self_id}-{uuid.uuid4().hex[:8]}"
        client = AgentTCPClient(cid, self._host, self._port, role="cli-worker-backend")
        await client.connect()
        self._client = client
        return client

    async def _release_client(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except (ConnectionError, OSError):
                pass
            self._client = None

    # ---- Task methods ------------------------------------------------------

    @property
    def worker_ids(self) -> List[str]:
        return [w.agent_id for w in self._workers]

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    async def run_parallel(
        self,
        tasks: List[Tuple[str, Any]],
        *,
        timeout_sec: float = 1800.0,
        gather_id: Optional[str] = None,
        summarize: bool = True,
        max_retries: int = 0,
        retry_delay_sec: float = 5.0,
    ) -> ParallelResult:
        """Send different tasks to different workers in parallel (batch_gather).

        Returns a :class:`ParallelResult` with structured per-worker results.
        Use ``result.succeeded``, ``result.failed``, ``result.all``,
        ``result.summary`` to inspect; ``result.raw`` for the original broker
        ``gather_result`` dict; ``result.to_dict()`` for JSON serialization.

        When *summarize* is True (default), the legacy
        ``summarize_gather_result`` dict is **not** returned — use
        ``result.to_dict()`` instead.  *summarize* is kept for signature
        compatibility but no longer changes the return type.

        When *max_retries* > 0, failed tasks whose error matches a known
        retryable pattern (e.g. ``database is locked``) are re-submitted
        **sequentially** with *retry_delay_sec* between each, avoiding the
        concurrency that caused the original failure.  Results are merged
        back into the original gather_result.
        """
        if not tasks:
            raise ValueError("tasks list must be non-empty")
        tasks = self._inject_skills(tasks)
        gid = gather_id or f"parallel-{uuid.uuid4().hex[:12]}"
        client = await self._ensure_client()
        log.info(
            "run_parallel id=%s targets=%s timeout_sec=%s max_retries=%s",
            gid, [t for t, _ in tasks], timeout_sec, max_retries,
        )
        result = await client.batch_gather(gid, tasks, timeout_sec=timeout_sec)

        if max_retries > 0:
            result = await self._retry_failed(
                result, tasks,
                timeout_sec=timeout_sec,
                max_retries=max_retries,
                retry_delay_sec=retry_delay_sec,
            )

        return _build_parallel_result(result)

    async def _retry_failed(
        self,
        result: Dict[str, Any],
        original_tasks: List[Tuple[str, Any]],
        *,
        timeout_sec: float,
        max_retries: int,
        retry_delay_sec: float,
    ) -> Dict[str, Any]:
        """Retry retryable failures sequentially to avoid lock contention."""
        task_map = {wid: body for wid, body in original_tasks}

        for attempt in range(1, max_retries + 1):
            retryable = [
                aid for aid, reply in result.get("replies", {}).items()
                if is_retryable_error(reply) and aid in task_map
            ]
            if not retryable:
                break

            log.info(
                "[retry] attempt=%s/%s retryable_workers=%s delay=%.1fs",
                attempt, max_retries, retryable, retry_delay_sec,
            )

            for i, agent_id in enumerate(retryable):
                await asyncio.sleep(retry_delay_sec)
                log.info(
                    "[retry] attempt=%s worker=%s (%s/%s) sending task",
                    attempt, agent_id, i + 1, len(retryable),
                )
                try:
                    reply = await self.run_single(
                        agent_id, task_map[agent_id],
                        timeout_sec=timeout_sec,
                        _skip_skill_inject=True,
                    )
                    result["replies"][agent_id] = reply
                    body = reply.get("body", {})
                    ok = body.get("ok", False) if isinstance(body, dict) else False
                    log.info(
                        "[retry] attempt=%s worker=%s result ok=%s",
                        attempt, agent_id, ok,
                    )
                except Exception as e:
                    log.warning(
                        "[retry] attempt=%s worker=%s exception: %s",
                        attempt, agent_id, e,
                    )

            all_ok = all(
                (r.get("body", {}).get("ok", False) if isinstance(r.get("body"), dict) else False)
                for r in result.get("replies", {}).values()
            )
            result["ok"] = all_ok
            if all_ok:
                log.info("[retry] all workers succeeded after attempt %s", attempt)
                break

        return result

    async def run_single(
        self,
        worker_id: str,
        body: Any,
        *,
        timeout_sec: float = 600.0,
        _skip_skill_inject: bool = False,
    ) -> Dict[str, Any]:
        """Send one task to one worker, wait for its reply."""
        if not _skip_skill_inject:
            injected = self._inject_skills([(worker_id, body)])
            _, body = injected[0]
        client = await self._ensure_client()
        log.info("run_single worker=%s timeout_sec=%s", worker_id, timeout_sec)
        await client.send_to(worker_id, body)
        reply = await client.wait_for_message(
            expect_from=worker_id, timeout_sec=timeout_sec,
        )
        return reply

    async def run_chain(
        self,
        tasks: List[Tuple[str, Any]],
        *,
        timeout_sec: float = 600.0,
        inject_prev: bool = True,
    ) -> List[Dict[str, Any]]:
        """Serial chain: task1->worker1->result1 injected into task2->worker2->...

        When *inject_prev* is True and the body is a dict, the previous
        worker's structured result is set as ``body["context"]`` for the
        next step::

            body["context"] = {"worker": "cm1", "status": "success", "answer": "..."}

        The downstream worker's prompt template can reference
        ``context.answer``.  The ``_body_to_prompt_and_context`` helper in
        ``__main__.py`` serialises dict contexts to JSON automatically.

        Returns a list of reply messages, one per step.
        """
        if not tasks:
            raise ValueError("tasks list must be non-empty")
        tasks = self._inject_skills(tasks)
        client = await self._ensure_client()
        results: List[Dict[str, Any]] = []
        prev_context: Optional[Dict[str, Any]] = None
        for i, (worker_id, body) in enumerate(tasks):
            if inject_prev and prev_context and isinstance(body, dict):
                body = {**body, "context": prev_context}
            log.info("run_chain step=%s/%s worker=%s", i + 1, len(tasks), worker_id)
            await client.send_to(worker_id, body)
            reply = await client.wait_for_message(
                expect_from=worker_id, timeout_sec=timeout_sec,
            )
            results.append(reply)
            if reply.get("type") == "error":
                log.warning("run_chain step %s got error, stopping chain: %s", i + 1, reply)
                break
            prev_context = _reply_to_structured_context(worker_id, reply)
        return results

    async def run_parallel_reduce(
        self,
        tasks: List[Tuple[str, Any]],
        *,
        reduce_worker: str,
        reduce_prompt: str,
        timeout_sec: float = 1800.0,
        reduce_timeout_sec: float = 600.0,
        max_retries: int = 0,
        retry_delay_sec: float = 5.0,
    ) -> ReduceResult:
        """Fan-out tasks in parallel, then reduce (summarise) results via one worker.

        This is syntactic sugar for ``run_parallel`` + ``run_single``::

            result = await cluster.run_parallel_reduce(
                tasks=[
                    ("cm1", {"prompt": "Search module A"}),
                    ("cm2", {"prompt": "Search module B"}),
                ],
                reduce_worker="cm1",
                reduce_prompt="Merge results and deduplicate:\\n{results}",
            )
            print(result.answer)      # final merged answer
            print(result.parallel)    # per-worker fan-out results

        The ``{results}`` placeholder in *reduce_prompt* is replaced with a
        structured text block containing each worker's status and answer.
        """
        par = await self.run_parallel(
            tasks,
            timeout_sec=timeout_sec,
            max_retries=max_retries,
            retry_delay_sec=retry_delay_sec,
        )

        results_block = _format_results_for_reduce(par)
        filled_prompt = reduce_prompt.replace("{results}", results_block)

        log.info(
            "run_parallel_reduce reduce_worker=%s prompt_chars=%s",
            reduce_worker, len(filled_prompt),
        )
        reply = await self.run_single(
            reduce_worker,
            {"prompt": filled_prompt},
            timeout_sec=reduce_timeout_sec,
            _skip_skill_inject=True,
        )
        reduce_wr = _parse_single_reply_to_worker_result(reduce_worker, reply)
        return ReduceResult(parallel=par, reduce=reduce_wr)

    # ---- Lifecycle ---------------------------------------------------------

    async def stop(self) -> None:
        """Stop all managed subprocesses (only meaningful for owned backends)."""
        await self._release_client()
        if not self._owns_processes:
            return
        for proc in self._agent_procs:
            terminate_and_wait(proc, timeout=10)
        self._agent_procs.clear()
        self._agent_proc_by_id.clear()
        if self._broker_proc is not None:
            terminate_and_wait(self._broker_proc, timeout=10)
            self._broker_proc = None
        for tmp in self._tmp_files:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        self._tmp_files.clear()
        self._started = False
        log.info("CLI worker backend stopped port=%s", self._port)

    async def close(self) -> None:
        """Close TCP connection without stopping subprocesses."""
        await self._release_client()

    async def __aenter__(self) -> "CLIWorkerBackend":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._owns_processes:
            await self.stop()
        else:
            await self.close()

    # ---- JSON config loading -----------------------------------------------

    @classmethod
    def workers_from_json(cls, data: Dict[str, Any]) -> List[WorkerConfig]:
        """Parse a ``cluster.json`` config into a list of ``WorkerConfig``."""
        raw = data.get("workers")
        if not isinstance(raw, list) or not raw:
            raise ValueError("cluster config needs non-empty 'workers' list")
        out: List[WorkerConfig] = []
        for i, w in enumerate(raw):
            if not isinstance(w, dict):
                raise ValueError(f"workers[{i}] must be an object")
            aid = w.get("agent_id")
            if not isinstance(aid, str) or not aid.strip():
                raise ValueError(f"workers[{i}].agent_id required")
            cwd = w.get("cwd")
            if not cwd:
                raise ValueError(f"workers[{i}].cwd required")
            out.append(WorkerConfig(
                agent_id=aid.strip(),
                cwd=Path(str(cwd)).expanduser().resolve(),
                model=str(w.get("model", "netease-codemaker/kimi-k2.5")),
                timeout_sec=float(w.get("timeout_sec", 1800.0)),
                prompt_via_file=str(w.get("prompt_via_file", "auto")),
                command=str(w.get("command", "codemaker")),
                cli_kind=str(w.get("cli_kind", "codemaker")),
                adapter_options=dict(w.get("adapter_options", {})),
                extra_env={str(k): str(v) for k, v in w.get("extra_env", {}).items()},
            ))
        return out

    @classmethod
    def host_port_from_json(cls, data: Dict[str, Any]) -> Tuple[str, int]:
        """Extract host/port from a ``cluster.json`` config."""
        return str(data.get("host", "127.0.0.1")), int(data.get("port", 9140))


# Backward-compatible alias. New code should import CLIWorkerBackend.
CodeMakerCluster = CLIWorkerBackend
