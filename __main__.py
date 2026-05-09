"""
CLI — CodeMaker CLI multi-worker orchestration framework.

Low-level (broker / agent plumbing):
  python -m multi_agent_tcp broker --config path/to/broker.json
  python -m multi_agent_tcp agent --config path/to/agent.json [--mode echo|listen|codemaker-worker|codex-worker]
  python -m multi_agent_tcp spawn --config path/to/spawn.json

High-level (CLIWorkerBackend):
  python -m multi_agent_tcp cluster start --config cluster.json
  python -m multi_agent_tcp run-parallel --config cluster.json --tasks tasks.json [-o result.json]
  python -m multi_agent_tcp run-chain   --config cluster.json --tasks tasks.json [-o result.json]

GUI:
  python -m multi_agent_tcp registry-ui
  python -m multi_agent_tcp ryven

Config files are JSON (UTF-8). See multi_agent_tcp/examples/*.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import request as urlrequest

from .broker import Broker
from .client import AgentTCPClient
from .adapters import CLIAdapter, adapter_from_agent_config, body_to_agent_message
from .log_setup import setup_logging
from ._proc_utils import terminate_and_wait

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Async dispatch — job tracking helpers
# ---------------------------------------------------------------------------

DISPATCH_JOBS_DIR = Path(__file__).parent / "logs" / "dispatch_jobs"


def _generate_job_id() -> str:
    return secrets.token_hex(4)


def _job_file(job_id: str) -> Path:
    return DISPATCH_JOBS_DIR / f"{job_id}.json"


def _write_job_status(job_id: str, data: dict) -> None:
    DISPATCH_JOBS_DIR.mkdir(parents=True, exist_ok=True)
    _job_file(job_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def _read_job_status(job_id: str) -> Optional[dict]:
    path = _job_file(job_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _is_process_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        return exit_code.value == STILL_ACTIVE
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


async def _cmd_broker(host: str, port: int) -> None:
    b = Broker(host, port)
    await b.start()
    await b.serve_forever()


def _gather_reply_id(msg: Dict[str, Any]) -> Optional[str]:
    g = msg.get("gather")
    if isinstance(g, dict):
        gid = g.get("id")
        if isinstance(gid, str) and gid.strip():
            return gid.strip()
    return None


async def _agent_loop_echo(client: AgentTCPClient) -> None:
    async for msg in client.incoming():
        t = msg.get("type")
        if t == "error":
            log.warning("broker error: %s", msg)
            continue
        if t in ("ping", "pong"):
            continue
        if t == "registered":
            continue
        if t in ("message", "broadcast"):
            sender = msg.get("from")
            body = msg.get("body")
            reply = {"echo_of": body, "via": t}
            gr = _gather_reply_id(msg)
            if isinstance(sender, str) and sender:
                try:
                    await client.send_to(sender, reply, gather_reply=gr)
                except (ConnectionError, OSError, RuntimeError) as e:
                    log.warning("echo send failed: %s", e)
        else:
            log.info("recv %s", msg)


async def _agent_loop_listen(client: AgentTCPClient) -> None:
    async for msg in client.incoming():
        t = msg.get("type")
        if t == "error":
            log.warning("broker error: %s", msg)
            continue
        if t in ("ping", "pong"):
            continue
        log.info("recv %s", msg)


async def _agent_loop_adapter(client: AgentTCPClient, adapter: CLIAdapter) -> None:
    aid = client.agent_id
    await adapter.start()
    async for msg in client.incoming():
        t = msg.get("type")
        if t == "error":
            log.warning("broker error: %s", msg)
            continue
        if t in ("ping", "pong"):
            continue
        if t not in ("message", "broadcast"):
            log.info("recv %s", msg)
            continue
        sender = msg.get("from")
        body = msg.get("body")
        gid = _gather_reply_id(msg)
        try:
            message = body_to_agent_message(body)
            if not message.prompt:
                raise ValueError("empty prompt")
            log.info(
                "[chain] agent=%s recv type=%s from=%s gather_reply=%s prompt_chars=%s has_context=%s adapter=%s",
                aid,
                t,
                sender,
                gid,
                len(message.prompt.encode("utf-8")),
                bool(message.context),
                adapter.cli_kind,
            )
            log.info("[chain] agent=%s -> adapter.send_message START", aid)
            result = await adapter.send_message(message)
            log.info(
                "[chain] agent=%s <- adapter.send_message END ok=%s status=%s",
                aid,
                result.ok,
                result.status,
            )
            reply = {**result.payload, "via": t}
        except (FileNotFoundError, ValueError, OSError, RuntimeError) as e:
            log.error("[chain] agent=%s adapter FAILED: %s", aid, e)
            reply = {"ok": False, "error": str(e), "via": t}
        if isinstance(sender, str) and sender:
            try:
                log.info(
                    "[chain] agent=%s -> broker SEND reply to=%s gather_reply=%s reply_keys=%s",
                    aid,
                    sender,
                    gid,
                    list(reply.keys()) if isinstance(reply, dict) else type(reply).__name__,
                )
                await client.send_to(sender, reply, gather_reply=gid)
            except (ConnectionError, OSError, RuntimeError) as e:
                log.warning("[chain] agent=%s reply send_to FAILED: %s", aid, e)
    await adapter.close()


async def _agent_loop_codemaker(client: AgentTCPClient, adapter: CLIAdapter) -> None:
    await _agent_loop_adapter(client, adapter)


async def _agent_loop_codex(client: AgentTCPClient, adapter: CLIAdapter) -> None:
    await _agent_loop_adapter(client, adapter)


async def _cmd_agent(cfg: Dict[str, Any], mode: str) -> None:
    agent_id = str(cfg["agent_id"])
    br = cfg.get("broker")
    if not isinstance(br, dict):
        br = {}
    host = str(cfg.get("broker_host", br.get("host", "127.0.0.1")))
    port = int(cfg.get("broker_port", br.get("port", 9123)))
    role = cfg.get("role")
    if role is not None:
        role = str(role)
    client = AgentTCPClient(agent_id, host, port, role=role)
    await client.connect()
    log.info("connected agent_id=%s -> %s:%s mode=%s", agent_id, host, port, mode)
    adapter: Optional[CLIAdapter] = None
    if mode in ("codemaker-worker", "codex-worker"):
        adapter = adapter_from_agent_config({**cfg, "mode": mode})
    try:
        if mode == "echo":
            await _agent_loop_echo(client)
        elif mode == "codemaker-worker":
            assert adapter is not None
            await _agent_loop_codemaker(client, adapter)
        elif mode == "codex-worker":
            assert adapter is not None
            await _agent_loop_codex(client, adapter)
        else:
            await _agent_loop_listen(client)
    finally:
        if adapter is not None:
            await adapter.close()
        await client.close()


def _broker_from_cfg(cfg: Dict[str, Any]) -> tuple[str, int]:
    host = str(cfg.get("host", "127.0.0.1"))
    port = int(cfg.get("port", 9123))
    return host, port


def _cmd_spawn(cfg_path: Path, verbose: bool) -> None:
    cfg = _load_json(cfg_path)
    br = cfg.get("broker")
    if not isinstance(br, dict):
        br = {}
    broker_host = str(cfg.get("broker_host", br.get("host", "127.0.0.1")))
    broker_port = int(cfg.get("broker_port", br.get("port", 9123)))
    agents: List[Dict[str, Any]] = list(cfg.get("agents") or [])
    if not agents:
        raise SystemExit("spawn config needs non-empty 'agents' list")
    py = str(cfg.get("python", sys.executable))
    module = "multi_agent_tcp"
    procs: List[subprocess.Popen] = []
    tmp_cfgs: List[Path] = []
    root = cfg_path.parent
    for a in agents:
        agent_cfg: Dict[str, Any] = {
            "agent_id": a["agent_id"],
            "broker_host": broker_host,
            "broker_port": broker_port,
            "role": a.get("role"),
            "mode": a.get("mode", "echo"),
            "cli_kind": a.get("cli_kind", "codemaker"),
        }
        if "codemaker" in a:
            agent_cfg["codemaker"] = a["codemaker"]
        if "codex" in a:
            agent_cfg["codex"] = a["codex"]
        if "adapter_options" in a:
            agent_cfg["adapter_options"] = a["adapter_options"]
        if "extra_env" in a:
            agent_cfg["extra_env"] = a["extra_env"]
        tmp = root / f"_spawn_agent_{agent_cfg['agent_id']}.json"
        tmp_cfgs.append(tmp)
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(agent_cfg, f, ensure_ascii=False, indent=2)
        cmd = [py, "-m", module]
        if verbose:
            cmd.append("-v")
        cmd.extend(
            [
                "agent",
                "--config",
                str(tmp.resolve()),
                "--mode",
                str(agent_cfg.get("mode", "echo")),
            ]
        )
        log.info("spawn %s", " ".join(cmd))
        kwargs: Dict[str, Any] = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
        procs.append(subprocess.Popen(cmd, **kwargs))
    try:
        while True:
            time.sleep(0.5)
            dead = [p for p in procs if p.poll() is not None]
            if dead:
                codes = [p.returncode for p in dead]
                log.warning("some agent processes exited: %s", codes)
                break
    except KeyboardInterrupt:
        log.info("stopping spawn children")
    finally:
        for p in procs:
            terminate_and_wait(p, timeout=8)
        for tmp in tmp_cfgs:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# High-level CLI: cluster / run-parallel / run-chain
# ---------------------------------------------------------------------------

async def _cmd_cluster_start(cfg_path: Path, verbose: bool) -> None:
    from .cli_worker_backend import CLIWorkerBackend, WorkerConfig

    data = _load_json(cfg_path)
    host, port = CLIWorkerBackend.host_port_from_json(data)
    workers = CLIWorkerBackend.workers_from_json(data)
    backend = await CLIWorkerBackend.create(workers, host=host, port=port, verbose=verbose)
    log.info("CLI worker backend running — press Ctrl+C to stop")
    try:
        while True:
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        pass
    finally:
        await backend.stop()


def _load_tasks(path: Path) -> List[tuple]:
    """Load ``tasks.json``: ``[{"to": "cm1", "body": {...}}, ...]``."""
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list) or not raw:
        raise ValueError("tasks file must be a non-empty JSON array")
    out: List[tuple] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"tasks[{i}] must be an object")
        to = item.get("to")
        if not isinstance(to, str) or not to.strip():
            raise ValueError(f"tasks[{i}].to required")
        if "body" not in item:
            raise ValueError(f"tasks[{i}].body required")
        out.append((to.strip(), item["body"]))
    return out


async def _create_cluster_from_args(args: argparse.Namespace):
    """Build a CLIWorkerBackend from --config, --registry, or --port args.

    Returns ``(backend, owns)`` where *owns* is True when the backend manages
    its own subprocesses (caller should use ``stop()`` / async-with).
    """
    from .cli_worker_backend import CLIWorkerBackend

    if getattr(args, "registry", False):
        from .registry import AgentsRegistry

        reg = AgentsRegistry.load()
        agent_ids = None
        if getattr(args, "agent_ids", None):
            agent_ids = [a.strip() for a in args.agent_ids.split(",") if a.strip()]
        skill_mode = getattr(args, "skill_mode", "catalog")
        backend = await CLIWorkerBackend.create_from_registry(
            reg,
            agent_ids=agent_ids,
            host=getattr(args, "host", "127.0.0.1"),
            port=getattr(args, "registry_port", 9140),
            verbose=args.verbose,
            skill_mode=skill_mode,
        )
        return backend, True

    if args.config:
        data = _load_json(args.config)
        host, port = CLIWorkerBackend.host_port_from_json(data)
        workers = CLIWorkerBackend.workers_from_json(data)
        backend = await CLIWorkerBackend.create(
            workers, host=host, port=port, verbose=args.verbose,
        )
        return backend, True

    backend = await CLIWorkerBackend.connect(
        host=args.host, port=args.port,
    )
    return backend, False


async def _cmd_run_parallel(args: argparse.Namespace) -> None:
    tasks = _load_tasks(args.tasks)
    cluster, owns = await _create_cluster_from_args(args)
    try:
        par = await cluster.run_parallel(
            tasks,
            timeout_sec=args.timeout,
            max_retries=args.max_retries,
            retry_delay_sec=args.retry_delay_sec,
        )
    finally:
        if owns:
            await cluster.stop()
        else:
            await cluster.close()
    result = par.raw if args.raw else par.to_dict()
    _write_result(result, args.output)
    if args.raw_output:
        _write_result(par.to_raw_dict(), args.raw_output)


async def _cmd_run_parallel_reduce(args: argparse.Namespace) -> None:
    tasks = _load_tasks(args.tasks)
    reduce_prompt = args.reduce_prompt
    if args.reduce_prompt_file:
        reduce_prompt = args.reduce_prompt_file.read_text(encoding="utf-8")
    if not reduce_prompt:
        raise SystemExit("--reduce-prompt or --reduce-prompt-file required")
    if "{results}" not in reduce_prompt:
        log.warning("reduce_prompt does not contain {results} placeholder")

    cluster, owns = await _create_cluster_from_args(args)
    try:
        rr = await cluster.run_parallel_reduce(
            tasks,
            reduce_worker=args.reduce_worker,
            reduce_prompt=reduce_prompt,
            timeout_sec=args.timeout,
            reduce_timeout_sec=args.reduce_timeout,
            max_retries=args.max_retries,
            retry_delay_sec=args.retry_delay_sec,
        )
    finally:
        if owns:
            await cluster.stop()
        else:
            await cluster.close()
    _write_result(rr.to_dict(), args.output)
    if hasattr(args, "raw_output") and args.raw_output:
        _write_result(rr.to_raw_dict(), args.raw_output)


async def _cmd_run_chain(args: argparse.Namespace) -> None:
    tasks = _load_tasks(args.tasks)
    cluster, owns = await _create_cluster_from_args(args)
    try:
        result = await cluster.run_chain(
            tasks,
            timeout_sec=args.timeout,
            inject_prev=not args.no_inject,
        )
    finally:
        if owns:
            await cluster.stop()
        else:
            await cluster.close()
    _write_result(result, args.output)


def _write_result(result: Any, output: Optional[Path]) -> None:
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if output:
        output.write_text(text, encoding="utf-8")
        log.info("result written to %s", output)
    else:
        try:
            print(text)
        except UnicodeEncodeError:
            sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
            sys.stdout.buffer.write(b"\n")
            sys.stdout.buffer.flush()


# ---------------------------------------------------------------------------
# show-registry / dispatch (recommended LLM two-step flow)
# ---------------------------------------------------------------------------

def _cmd_show_registry(args: argparse.Namespace) -> None:
    from .registry import AgentsRegistry, show_registry_response

    reg = AgentsRegistry.load()
    resp = show_registry_response(reg)
    _write_result(resp, args.output)


def _runtime_rpc_request(
    rpc_url: str,
    token: str,
    command: str,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    payload = json.dumps(
        {"token": token, "command": command, "args": args},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urlrequest.Request(
        rpc_url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=30) as resp:  # noqa: S310 - user-provided local RPC URL
        return json.loads(resp.read().decode("utf-8"))


def _read_json_arg(*, path: Optional[Path] = None, inline: Optional[str] = None) -> Any:
    if path is not None:
        return json.loads(path.read_text(encoding="utf-8"))
    if inline is not None:
        return json.loads(inline)
    return None


def _cmd_organization(args: argparse.Namespace) -> None:
    from .graph_control import load_graph_definition, scoped_organization_view

    if args.rpc_url:
        result = _runtime_rpc_request(
            args.rpc_url,
            args.token,
            "organization.read",
            {"agent_id": args.agent_id},
        )
    else:
        graph = load_graph_definition(args.graph)
        result = {
            "ok": True,
            "organization": scoped_organization_view(graph, agent_id=args.agent_id),
        }
    _write_result(result, args.output)


def _cmd_runtime(args: argparse.Namespace) -> None:
    command = str(args.runtime_cmd)
    if command == "validate-start":
        from .graph_control import load_graph_definition, load_top_agent_profile
        from .graph_runtime import GuLiCodeTopAgentProfile, TopAgentStartPlan

        graph = load_graph_definition(args.graph)
        plan = TopAgentStartPlan.from_dict(_read_json_arg(path=args.plan))
        profile = (
            load_top_agent_profile(args.top_agent_profile)
            if args.top_agent_profile
            else GuLiCodeTopAgentProfile()
        )
        result = profile.validate_start_plan(graph, plan).to_dict()
        _write_result(result, args.output)
        return

    if command == "top-agent-context":
        from .graph_control import load_graph_definition, load_top_agent_profile
        from .graph_runtime import GuLiCodeTopAgentProfile

        graph = load_graph_definition(args.graph)
        profile = (
            load_top_agent_profile(args.top_agent_profile)
            if args.top_agent_profile
            else GuLiCodeTopAgentProfile()
        )
        result = {"ok": True, "context": profile.organization_context(graph)}
        _write_result(result, args.output)
        return

    rpc_url = str(args.rpc_url)
    token = str(args.token)
    rpc_args: Dict[str, Any]
    rpc_command: str

    if command == "start":
        rpc_command = "run.start"
        rpc_args = {
            "plan": _read_json_arg(path=args.plan),
            "manifest_path": str(args.manifest_path) if args.manifest_path else None,
        }
    elif command == "status":
        rpc_command = "run.status"
        rpc_args = {"recent_events_limit": args.recent_events_limit}
    elif command == "explain-status":
        rpc_command = "top_agent.explain_status"
        rpc_args = {"recent_events_limit": args.recent_events_limit}
    elif command == "top-agent-start-session":
        rpc_command = "top_agent.start_session"
        rpc_args = {}
    elif command == "top-agent-ask":
        rpc_command = "top_agent.ask"
        rpc_args = {
            "prompt": args.prompt,
            "include_status": not args.no_status,
            "recent_events_limit": args.recent_events_limit,
        }
    elif command == "top-agent-utterances":
        rpc_command = "top_agent.utterances"
        rpc_args = {
            "task_id": args.task_id,
            "agent_id": args.agent_id,
            "node_id": args.node_id,
        }
    elif command == "end":
        rpc_command = "run.end"
        rpc_args = {"action": args.action, "reason": args.reason, "archive": args.archive}
    elif command == "message-batch":
        rpc_command = "message.create_batch"
        rpc_args = {
            "source_node_id": args.source_node_id,
            "required_target_node_ids": [
                item.strip()
                for item in (args.required_targets or "").split(",")
                if item.strip()
            ],
            "batch_id": args.batch_id,
        }
    elif command == "message-stage":
        rpc_command = "message.stage"
        rpc_args = {
            "batch_id": args.batch_id,
            "target_node_id": args.target_node_id,
            "body": _read_json_arg(path=args.body, inline=args.body_json),
        }
    elif command == "agent-context":
        rpc_command = "agent.context"
        rpc_args = {
            "source_node_id": args.source_node_id,
            "batch_id": args.batch_id,
        }
    elif command == "agent-dispatch":
        rpc_command = "agent.dispatch"
        rpc_args = {
            "source_node_id": args.source_node_id,
            "target_node_id": args.target_node_id,
            "body": _read_json_arg(path=args.body, inline=args.body_json),
            "batch_id": args.batch_id,
        }
    elif command == "join-create":
        rpc_command = "join.create"
        rpc_args = {
            "join_id": args.join_id,
            "target_node_id": args.target_node_id,
            "required_source_node_ids": [
                item.strip()
                for item in args.required_sources.split(",")
                if item.strip()
            ],
            "policy": args.policy,
            "quorum": args.quorum,
            "timeout_sec": args.timeout_sec,
        }
    elif command == "join-contribute":
        rpc_command = "join.contribute"
        contribution = _read_json_arg(path=args.contribution, inline=args.contribution_json)
        if not isinstance(contribution, dict):
            raise ValueError("join contribution must be a JSON object")
        rpc_args = contribution
    else:  # pragma: no cover - argparse prevents this
        raise ValueError(f"unsupported runtime command: {command}")

    result = _runtime_rpc_request(rpc_url, token, rpc_command, rpc_args)
    _write_result(result, args.output)


def _load_dispatch_tasks(raw: Any) -> List[Dict[str, str]]:
    """Validate dispatch task list: ``[{"agent_id": "...", "prompt": "..."}, ...]``."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("dispatch tasks must be a non-empty JSON array")
    out: List[Dict[str, str]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"tasks[{i}] must be an object")
        aid = item.get("agent_id")
        if not isinstance(aid, str) or not aid.strip():
            raise ValueError(f"tasks[{i}].agent_id required")
        prompt = item.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"tasks[{i}].prompt required")
        out.append({"agent_id": aid.strip(), "prompt": prompt.strip()})
    return out


async def _cmd_dispatch(args: argparse.Namespace) -> None:
    from .registry import AgentsRegistry
    from .cli_worker_backend import CLIWorkerBackend

    reg = AgentsRegistry.load()

    if args.tasks:
        raw = json.loads(args.tasks.read_text(encoding="utf-8"))
    elif args.tasks_json:
        raw = json.loads(args.tasks_json)
    else:
        raise SystemExit("--tasks or --tasks-json required")

    dispatch_items = _load_dispatch_tasks(raw)

    needed_ids = list(dict.fromkeys(item["agent_id"] for item in dispatch_items))
    for aid in needed_ids:
        prof = reg.agents.get(aid)
        if prof is None:
            raise SystemExit(
                f"agent_id '{aid}' not found in agents_registry.json. "
                f"Available: {[a.agent_id for a in reg.list_agents()]}"
            )
        if not prof.enabled:
            raise SystemExit(f"agent_id '{aid}' is disabled in agents_registry.json")

    cluster_tasks = [
        (item["agent_id"], {"prompt": item["prompt"]})
        for item in dispatch_items
    ]

    skill_mode = getattr(args, "skill_mode", "catalog")
    async with await CLIWorkerBackend.create_from_registry(
        reg,
        agent_ids=needed_ids,
        port=args.port,
        verbose=args.verbose,
        skill_mode=skill_mode,
    ) as cluster:
        par = await cluster.run_parallel(
            cluster_tasks,
            timeout_sec=args.timeout,
            max_retries=args.max_retries,
            retry_delay_sec=args.retry_delay_sec,
        )

    result = par.to_dict()
    result["dispatched_agents"] = needed_ids
    _write_result(result, args.output)
    if args.raw_output:
        _write_result(par.to_raw_dict(), args.raw_output)


def _launch_async_dispatch(args: argparse.Namespace) -> dict:
    """Spawn dispatch in a detached background process, return job info."""
    job_id = _generate_job_id()
    DISPATCH_JOBS_DIR.mkdir(parents=True, exist_ok=True)

    output_file = args.output or (DISPATCH_JOBS_DIR / f"{job_id}_result.json")
    output_file = Path(output_file).resolve()

    # Inline JSON → temp file so subprocess can use --tasks (avoids quoting)
    if args.tasks_json:
        tasks_file = DISPATCH_JOBS_DIR / f"{job_id}_tasks.json"
        tasks_file.write_text(args.tasks_json, encoding="utf-8")
    else:
        tasks_file = Path(args.tasks).resolve()

    started_at = time.time()
    _write_job_status(job_id, {
        "status": "running",
        "job_id": job_id,
        "pid": None,
        "started_at": started_at,
        "output_file": str(output_file),
    })

    cmd = [sys.executable, "-m", "multi_agent_tcp"]
    if args.verbose:
        cmd.append("-v")
    cmd.extend(["dispatch", "--_job-id", job_id])
    cmd.extend(["--tasks", str(tasks_file)])
    cmd.extend(["-o", str(output_file)])
    if args.raw_output:
        cmd.extend(["--raw-output", str(Path(args.raw_output).resolve())])
    cmd.extend(["--port", str(args.port)])
    cmd.extend(["--timeout", str(args.timeout)])
    cmd.extend(["--max-retries", str(args.max_retries)])
    cmd.extend(["--retry-delay-sec", str(args.retry_delay_sec)])
    cmd.extend(["--skill-mode", args.skill_mode])

    log_path = DISPATCH_JOBS_DIR / f"{job_id}.log"
    spawn_kwargs: Dict[str, Any] = {}
    if sys.platform == "win32":
        DETACHED_PROCESS = 0x00000008
        CREATE_NO_WINDOW = 0x08000000
        spawn_kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NO_WINDOW

    with open(log_path, "w", encoding="utf-8") as lf:
        proc = subprocess.Popen(
            cmd, stdout=lf, stderr=subprocess.STDOUT, **spawn_kwargs,
        )

    _write_job_status(job_id, {
        "status": "running",
        "job_id": job_id,
        "pid": proc.pid,
        "started_at": started_at,
        "output_file": str(output_file),
        "log_file": str(log_path.resolve()),
    })

    status_file = str(_job_file(job_id).resolve())
    poll_cmd = f"python -m multi_agent_tcp dispatch-status --job-id {job_id}"
    return {
        "job_id": job_id,
        "status": "running",
        "pid": proc.pid,
        "message": (
            "Dispatch job started in background. "
            "Use the `read` tool to poll status_file until status becomes "
            "'completed' or 'failed'. The result will be embedded in the "
            "status file when done."
        ),
        "status_file": status_file,
        "poll_command": poll_cmd,
        "output_file": str(output_file),
    }


def _check_job_once(job_id: str) -> dict:
    """Read job status, detect crashes, compute elapsed, attach result."""
    status = _read_job_status(job_id)
    if status is None:
        return {
            "job_id": job_id,
            "status": "not_found",
            "error": f"Job '{job_id}' not found. Check the job ID.",
        }

    if status.get("status") == "running":
        pid = status.get("pid")
        if pid and not _is_process_alive(pid):
            log_hint = status.get("log_file", "N/A")
            status["status"] = "failed"
            status["error"] = (
                f"Process (PID {pid}) exited unexpectedly. "
                f"Check log: {log_hint}"
            )
            status["failed_at"] = time.time()
            _write_job_status(job_id, status)

    started_at = status.get("started_at")
    if started_at:
        end = (
            status.get("completed_at")
            or status.get("failed_at")
            or time.time()
        )
        status["elapsed_sec"] = round(end - started_at, 1)

    if status["status"] == "completed":
        output_file = status.get("output_file")
        if output_file:
            p = Path(output_file)
            if p.exists():
                try:
                    status["result"] = json.loads(
                        p.read_text(encoding="utf-8"),
                    )
                except (json.JSONDecodeError, OSError):
                    status["result_read_error"] = f"Failed to read {output_file}"
        status["message"] = "Job completed successfully."
    elif status["status"] == "running":
        status["message"] = "Job is still running. Poll again in a few seconds."
    elif status["status"] == "failed":
        status["message"] = f"Job failed: {status.get('error', 'unknown error')}"

    status["job_id"] = job_id
    return status


def _cmd_dispatch_status(args: argparse.Namespace) -> None:
    job_id = args.job_id
    wait_sec = getattr(args, "wait", 0) or 0
    poll_interval = 3.0
    deadline = time.time() + wait_sec

    while True:
        status = _check_job_once(job_id)
        if status["status"] != "running" or time.time() >= deadline:
            break
        remaining = deadline - time.time()
        time.sleep(min(poll_interval, max(remaining, 0.1)))

    _write_result(status, getattr(args, "output", None))


# ---------------------------------------------------------------------------
# Session-gated agent dispatch: list-agents / run-agent (legacy)
# ---------------------------------------------------------------------------

def _cmd_list_agents(args: argparse.Namespace) -> None:
    from .registry import AgentsRegistry

    reg = AgentsRegistry.load()
    session = reg.create_session()
    resp = session.to_list_response()
    _write_result(resp, args.output)


async def _cmd_run_agent(args: argparse.Namespace) -> None:
    from .registry import AgentsRegistry
    from .cli_worker_backend import CLIWorkerBackend, WorkerConfig, extract_final_text

    session_id: str = args.session_id
    agent_id: str = args.agent_id
    prompt: str = args.prompt

    if args.prompt_file:
        prompt = args.prompt_file.read_text(encoding="utf-8")
    if not prompt or not prompt.strip():
        raise SystemExit("--prompt or --prompt-file required (non-empty)")

    session = AgentsRegistry.validate_session(session_id, agent_id)
    log.info(
        "session %s validated — launching agent %r",
        session_id, agent_id,
    )

    reg = AgentsRegistry.load()
    agent = reg.get_agent(agent_id)
    final_prompt = reg.inject_skills_into_prompt(
        agent_id, prompt.strip(), mode=args.skill_mode,
    )

    wc = WorkerConfig(
        agent_id=agent.agent_id,
        cwd=Path(agent.cwd),
        model=agent.model,
        timeout_sec=agent.timeout_sec,
    )

    async with await CLIWorkerBackend.create(
        workers=[wc], port=args.port, verbose=args.verbose,
    ) as cluster:
        log.info("cluster up — sending prompt (%d chars)", len(final_prompt))
        result = await cluster.run_single(
            agent.agent_id,
            {"prompt": final_prompt},
        )

    body = result.get("body", {})
    cm = body.get("codemaker", {})
    stdout_raw = cm.get("stdout", "")
    stderr_raw = cm.get("stderr", "")
    rc = cm.get("returncode", -1)
    answer = extract_final_text(stdout_raw)

    out = {
        "session_id": session_id,
        "agent_id": agent_id,
        "model": agent.model,
        "skills": agent.skills,
        "returncode": rc,
        "answer": answer,
    }
    if rc != 0 and stderr_raw.strip():
        out["stderr_head"] = stderr_raw[:500]

    _write_result(out, args.output)


def _add_connect_args(p: argparse.ArgumentParser) -> None:
    """Shared args for connecting to an existing cluster vs starting one."""
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--config", type=Path,
        help="cluster.json — starts a one-shot cluster (broker+workers)",
    )
    g.add_argument(
        "--registry", action="store_true",
        help="use agents_registry.json to build workers (model/cwd/skills)",
    )
    g.add_argument(
        "--port", type=int,
        help="connect to an already-running cluster on this port",
    )
    p.add_argument("--host", default="127.0.0.1", help="broker host (default 127.0.0.1)")
    p.add_argument(
        "--registry-port", type=int, default=9140,
        help="broker port when using --registry (default 9140)",
    )
    p.add_argument(
        "--skill-mode", choices=["catalog", "full"], default="catalog",
        help="skill injection mode when using --registry (default: catalog)",
    )
    p.add_argument(
        "--agent-ids", type=str, default=None,
        help="comma-separated agent IDs to use from registry (default: all enabled)",
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        description="CodeMaker CLI multi-worker orchestration framework",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # -- low-level -----------------------------------------------------------
    p_broker = sub.add_parser("broker", help="run message broker")
    p_broker.add_argument("--config", type=Path, help="JSON: {host, port}")
    p_broker.add_argument("--host", default="127.0.0.1")
    p_broker.add_argument("--port", type=int, default=9123)

    p_agent = sub.add_parser("agent", help="run one agent process")
    p_agent.add_argument("--config", type=Path, required=True)
    p_agent.add_argument(
        "--mode",
        choices=("echo", "listen", "codemaker-worker", "codex-worker"),
        default="echo",
    )

    p_spawn = sub.add_parser("spawn", help="start multiple agent subprocesses from one JSON")
    p_spawn.add_argument("--config", type=Path, required=True)

    # -- high-level: cluster -------------------------------------------------
    p_cluster = sub.add_parser("cluster", help="manage a CodeMaker worker cluster")
    cluster_sub = p_cluster.add_subparsers(dest="cluster_cmd", required=True)

    p_cs = cluster_sub.add_parser("start", help="start broker + workers (foreground, Ctrl+C to stop)")
    p_cs.add_argument("--config", type=Path, required=True, help="cluster.json")

    # -- GUI -----------------------------------------------------------------
    sub.add_parser("registry-ui", help="open the graphical agents registry editor")
    p_ryven = sub.add_parser("ryven", help="launch the vendored Ryven node editor")
    p_ryven.add_argument("ryven_args", nargs=argparse.REMAINDER, help="arguments forwarded to Ryven")

    # -- show-registry / dispatch (recommended LLM flow) ---------------------
    p_sr = sub.add_parser(
        "show-registry",
        help="read-only: list available agents from registry (no session)",
    )
    p_sr.add_argument("-o", "--output", type=Path, help="write JSON to file")

    p_org = sub.add_parser(
        "organization",
        help="read graph organization view from a graph JSON or runtime RPC",
    )
    org_src = p_org.add_mutually_exclusive_group(required=True)
    org_src.add_argument("--graph", type=Path, help="graph definition JSON")
    org_src.add_argument("--rpc-url", help="live GraphRuntime RPC URL")
    p_org.add_argument("--token", default="", help="GraphRuntime RPC token")
    p_org.add_argument("--agent-id", help="return ordinary-agent scoped view")
    p_org.add_argument("-o", "--output", type=Path, help="write JSON to file")

    p_runtime = sub.add_parser(
        "runtime",
        help="call graph runtime control-plane commands",
    )
    runtime_sub = p_runtime.add_subparsers(dest="runtime_cmd", required=True)

    p_validate = runtime_sub.add_parser("validate-start", help="dry-run validate a top-agent start plan")
    p_validate.add_argument("--graph", type=Path, required=True)
    p_validate.add_argument("--plan", type=Path, required=True)
    p_validate.add_argument("--top-agent-profile", type=Path, help="JSON GuLiCode top-agent profile")
    p_validate.add_argument("-o", "--output", type=Path, help="write JSON to file")

    p_top_context = runtime_sub.add_parser(
        "top-agent-context",
        help="render top-agent rule/skill plus graph organization context",
    )
    p_top_context.add_argument("--graph", type=Path, required=True)
    p_top_context.add_argument("--top-agent-profile", type=Path, help="JSON GuLiCode top-agent profile")
    p_top_context.add_argument("-o", "--output", type=Path, help="write JSON to file")

    def _add_runtime_rpc_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--rpc-url", required=True, help="live GraphRuntime RPC URL")
        p.add_argument("--token", required=True, help="GraphRuntime RPC token")
        p.add_argument("-o", "--output", type=Path, help="write JSON to file")

    p_rt_start = runtime_sub.add_parser("start", help="submit a top-agent start plan to runtime RPC")
    _add_runtime_rpc_args(p_rt_start)
    p_rt_start.add_argument("--plan", type=Path, required=True)
    p_rt_start.add_argument("--manifest-path", type=Path, help="optional WorkspaceManifest JSON output path")

    p_rt_status = runtime_sub.add_parser("status", help="read runtime status snapshot")
    _add_runtime_rpc_args(p_rt_status)
    p_rt_status.add_argument("--recent-events-limit", type=int, default=20)

    p_rt_explain = runtime_sub.add_parser(
        "explain-status",
        help="summarize runtime status for the top-level agent",
    )
    _add_runtime_rpc_args(p_rt_explain)
    p_rt_explain.add_argument("--recent-events-limit", type=int, default=20)

    p_top_start = runtime_sub.add_parser(
        "top-agent-start-session",
        help="bind the long-lived GuLiCode top-agent worker",
    )
    _add_runtime_rpc_args(p_top_start)

    p_top_ask = runtime_sub.add_parser(
        "top-agent-ask",
        help="send a user message to the long-lived GuLiCode top-agent worker",
    )
    _add_runtime_rpc_args(p_top_ask)
    p_top_ask.add_argument("--prompt", required=True)
    p_top_ask.add_argument("--no-status", action="store_true", help="omit status explanation context")
    p_top_ask.add_argument("--recent-events-limit", type=int, default=20)

    p_top_utterances = runtime_sub.add_parser(
        "top-agent-utterances",
        help="read framework-private Agent utterance records for the top-level agent",
    )
    _add_runtime_rpc_args(p_top_utterances)
    p_top_utterances.add_argument("--task-id")
    p_top_utterances.add_argument("--agent-id")
    p_top_utterances.add_argument("--node-id")

    p_rt_end = runtime_sub.add_parser("end", help="end, pause, cancel, fail, or archive a run")
    _add_runtime_rpc_args(p_rt_end)
    p_rt_end.add_argument(
        "--action",
        required=True,
        choices=["complete", "cancel", "fail", "pause", "archive_only"],
    )
    p_rt_end.add_argument("--reason", default="")
    p_rt_end.add_argument("--archive", action="store_true")

    p_msg_batch = runtime_sub.add_parser("message-batch", help="create an outgoing message batch")
    _add_runtime_rpc_args(p_msg_batch)
    p_msg_batch.add_argument("--source-node-id", required=True)
    p_msg_batch.add_argument("--required-targets", default="", help="comma-separated target node ids")
    p_msg_batch.add_argument("--batch-id")

    p_msg_stage = runtime_sub.add_parser("message-stage", help="stage one outgoing target message")
    _add_runtime_rpc_args(p_msg_stage)
    p_msg_stage.add_argument("--batch-id", required=True)
    p_msg_stage.add_argument("--target-node-id", required=True)
    body_g = p_msg_stage.add_mutually_exclusive_group(required=True)
    body_g.add_argument("--body", type=Path, help="JSON body file")
    body_g.add_argument("--body-json", help="inline JSON body")

    p_agent_context = runtime_sub.add_parser(
        "agent-context",
        help="read the ordinary AgentNode framework_context for a current batch",
    )
    _add_runtime_rpc_args(p_agent_context)
    p_agent_context.add_argument("--source-node-id", required=True)
    p_agent_context.add_argument("--batch-id")

    p_agent_dispatch = runtime_sub.add_parser(
        "agent-dispatch",
        help="ordinary AgentNode API: validate and dispatch one downstream message",
    )
    _add_runtime_rpc_args(p_agent_dispatch)
    p_agent_dispatch.add_argument("--source-node-id", required=True)
    p_agent_dispatch.add_argument("--target-node-id", required=True)
    p_agent_dispatch.add_argument("--batch-id")
    dispatch_body_g = p_agent_dispatch.add_mutually_exclusive_group(required=True)
    dispatch_body_g.add_argument("--body", type=Path, help="JSON body file")
    dispatch_body_g.add_argument("--body-json", help="inline JSON body")

    p_join_create = runtime_sub.add_parser("join-create", help="create a fan-in join barrier")
    _add_runtime_rpc_args(p_join_create)
    p_join_create.add_argument("--join-id")
    p_join_create.add_argument("--target-node-id")
    p_join_create.add_argument("--required-sources", required=True, help="comma-separated source node ids")
    p_join_create.add_argument("--policy", choices=["wait-all", "wait-any", "quorum"], default="wait-all")
    p_join_create.add_argument("--quorum", type=int)
    p_join_create.add_argument("--timeout-sec", type=float)

    p_join_contribute = runtime_sub.add_parser("join-contribute", help="submit one join contribution")
    _add_runtime_rpc_args(p_join_contribute)
    contrib_g = p_join_contribute.add_mutually_exclusive_group(required=True)
    contrib_g.add_argument("--contribution", type=Path, help="JSON contribution file")
    contrib_g.add_argument("--contribution-json", help="inline JSON contribution")

    p_disp = sub.add_parser(
        "dispatch",
        help="run tasks on registry agents: auto load config + inject skills + parallel",
    )
    disp_tasks_g = p_disp.add_mutually_exclusive_group(required=True)
    disp_tasks_g.add_argument(
        "--tasks", type=Path,
        help='JSON file: [{"agent_id":"...","prompt":"..."}, ...]',
    )
    disp_tasks_g.add_argument(
        "--tasks-json", type=str,
        help='inline JSON string: [{"agent_id":"...","prompt":"..."}, ...]',
    )
    p_disp.add_argument("-o", "--output", type=Path, help="write result JSON to file")
    p_disp.add_argument("--raw-output", type=Path, help="write debug dict to file")
    p_disp.add_argument("--port", type=int, default=9140, help="broker port (default 9140)")
    p_disp.add_argument("--timeout", type=float, default=1800.0)
    p_disp.add_argument("--max-retries", type=int, default=2)
    p_disp.add_argument("--retry-delay-sec", type=float, default=5.0)
    p_disp.add_argument(
        "--skill-mode", choices=["catalog", "full"], default="catalog",
        help="skill injection mode (default: catalog)",
    )
    p_disp.add_argument(
        "--async", dest="async_mode", action="store_true",
        help="run in background, return job_id for polling via dispatch-status",
    )
    p_disp.add_argument(
        "--_job-id", dest="job_id", type=str, default=None,
        help=argparse.SUPPRESS,
    )

    p_ds = sub.add_parser(
        "dispatch-status",
        help="check status of an async dispatch job",
    )
    p_ds.add_argument("--job-id", required=True, help="job ID from dispatch --async")
    p_ds.add_argument(
        "--wait", type=float, default=0,
        help="block up to N seconds for job to finish (0 = instant check)",
    )
    p_ds.add_argument("-o", "--output", type=Path, help="write status JSON to file")

    # -- session-gated agent dispatch (legacy) -------------------------------
    p_la = sub.add_parser(
        "list-agents",
        help="list available agents from registry + generate session_id",
    )
    p_la.add_argument("-o", "--output", type=Path, help="write JSON to file")

    p_ra = sub.add_parser(
        "run-agent",
        help="launch one agent (requires session_id from list-agents)",
    )
    p_ra.add_argument(
        "--session-id", required=True,
        help="5-digit session ID from list-agents",
    )
    p_ra.add_argument(
        "--agent-id", required=True,
        help="agent key from the list-agents output",
    )
    prompt_g = p_ra.add_mutually_exclusive_group(required=True)
    prompt_g.add_argument("--prompt", type=str, help="task prompt text")
    prompt_g.add_argument("--prompt-file", type=Path, help="file containing prompt")
    p_ra.add_argument(
        "--skill-mode", choices=["catalog", "full"], default="catalog",
        help="how to inject skills: catalog (default) or full",
    )
    p_ra.add_argument("--port", type=int, default=9160, help="broker port (default 9160)")
    p_ra.add_argument("-o", "--output", type=Path, help="write result JSON to file")

    # -- high-level: run-parallel / run-chain --------------------------------
    p_rp = sub.add_parser("run-parallel", help="parallel tasks via batch_gather")
    _add_connect_args(p_rp)
    p_rp.add_argument("--tasks", type=Path, required=True, help="tasks.json")
    p_rp.add_argument("-o", "--output", type=Path, help="write result JSON to file")
    p_rp.add_argument("--timeout", type=float, default=1800.0)
    p_rp.add_argument("--raw", action="store_true", help="output raw gather_result instead of summary")
    p_rp.add_argument("--raw-output", type=Path, help="write full debug dict (with raw_stdout/stderr) to file")
    p_rp.add_argument("--max-retries", type=int, default=2, help="retry retryable failures (default 2)")
    p_rp.add_argument("--retry-delay-sec", type=float, default=5.0, help="seconds between retries (default 5)")

    p_rpr = sub.add_parser("run-parallel-reduce", help="parallel fan-out + reduce via one worker")
    _add_connect_args(p_rpr)
    p_rpr.add_argument("--tasks", type=Path, required=True, help="tasks.json")
    p_rpr.add_argument("--reduce-worker", required=True, help="worker id for the reduce step")
    reduce_g = p_rpr.add_mutually_exclusive_group(required=True)
    reduce_g.add_argument("--reduce-prompt", type=str, help="reduce prompt with {results} placeholder")
    reduce_g.add_argument("--reduce-prompt-file", type=Path, help="file containing reduce prompt")
    p_rpr.add_argument("-o", "--output", type=Path, help="write result JSON to file")
    p_rpr.add_argument("--timeout", type=float, default=1800.0)
    p_rpr.add_argument("--reduce-timeout", type=float, default=600.0, help="timeout for reduce step")
    p_rpr.add_argument("--raw-output", type=Path, help="write full debug dict (with raw_stdout/stderr) to file")
    p_rpr.add_argument("--max-retries", type=int, default=2)
    p_rpr.add_argument("--retry-delay-sec", type=float, default=5.0)

    p_rc = sub.add_parser("run-chain", help="serial chain of tasks")
    _add_connect_args(p_rc)
    p_rc.add_argument("--tasks", type=Path, required=True, help="tasks.json")
    p_rc.add_argument("-o", "--output", type=Path, help="write result JSON to file")
    p_rc.add_argument("--timeout", type=float, default=600.0)
    p_rc.add_argument("--no-inject", action="store_true", help="disable automatic context injection")

    args = parser.parse_args(argv)
    setup_logging(args.verbose, name=args.cmd or "multi_agent_tcp")

    # -- dispatch ------------------------------------------------------------
    if args.cmd == "broker":
        if args.config:
            c = _load_json(args.config)
            host, port = _broker_from_cfg(c)
        else:
            host, port = args.host, int(args.port)
        try:
            asyncio.run(_cmd_broker(host, port))
        except KeyboardInterrupt:
            pass
        return

    if args.cmd == "agent":
        cfg = _load_json(args.config)
        mode = str(cfg.get("mode", args.mode))
        if mode not in ("echo", "listen", "codemaker-worker", "codex-worker"):
            mode = "echo"
        try:
            asyncio.run(_cmd_agent(cfg, mode))
        except KeyboardInterrupt:
            pass
        return

    if args.cmd == "spawn":
        _cmd_spawn(args.config, args.verbose)
        return

    if args.cmd == "cluster":
        if args.cluster_cmd == "start":
            try:
                asyncio.run(_cmd_cluster_start(args.config, args.verbose))
            except KeyboardInterrupt:
                pass
            return

    if args.cmd == "registry-ui":
        from .registry_ui import main as _ui_main
        _ui_main()
        return

    if args.cmd == "ryven":
        from .ryven_launcher import run as _run_ryven
        _run_ryven(args.ryven_args)
        return

    if args.cmd == "show-registry":
        _cmd_show_registry(args)
        return

    if args.cmd == "organization":
        try:
            _cmd_organization(args)
        except (ValueError, KeyError, OSError) as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False, indent=2))
            sys.exit(1)
        return

    if args.cmd == "runtime":
        try:
            _cmd_runtime(args)
        except (ValueError, KeyError, OSError) as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False, indent=2))
            sys.exit(1)
        return

    if args.cmd == "dispatch-status":
        _cmd_dispatch_status(args)
        return

    if args.cmd == "dispatch":
        if getattr(args, "async_mode", False):
            info = _launch_async_dispatch(args)
            _write_result(info, None)
            return

        job_id = getattr(args, "job_id", None)
        if job_id:
            saved = _read_job_status(job_id) or {}
            try:
                asyncio.run(_cmd_dispatch(args))
                result_data = None
                if args.output and args.output.exists():
                    try:
                        result_data = json.loads(
                            args.output.read_text(encoding="utf-8"),
                        )
                    except Exception:
                        pass
                _write_job_status(job_id, {
                    **saved,
                    "status": "completed",
                    "completed_at": time.time(),
                    "result": result_data,
                })
            except KeyboardInterrupt:
                _write_job_status(job_id, {
                    **saved, "status": "failed",
                    "failed_at": time.time(), "error": "KeyboardInterrupt",
                })
            except Exception as e:
                _write_job_status(job_id, {
                    **saved, "status": "failed",
                    "failed_at": time.time(), "error": str(e),
                })
            return

        try:
            asyncio.run(_cmd_dispatch(args))
        except KeyboardInterrupt:
            pass
        except (ValueError, SystemExit) as e:
            print(json.dumps({"error": str(e)}, ensure_ascii=False, indent=2))
            sys.exit(1)
        return

    if args.cmd == "list-agents":
        _cmd_list_agents(args)
        return

    if args.cmd == "run-agent":
        try:
            asyncio.run(_cmd_run_agent(args))
        except KeyboardInterrupt:
            pass
        except ValueError as e:
            print(json.dumps({"error": str(e)}, ensure_ascii=False, indent=2))
            sys.exit(1)
        return

    if args.cmd == "run-parallel":
        try:
            asyncio.run(_cmd_run_parallel(args))
        except KeyboardInterrupt:
            pass
        return

    if args.cmd == "run-parallel-reduce":
        try:
            asyncio.run(_cmd_run_parallel_reduce(args))
        except KeyboardInterrupt:
            pass
        return

    if args.cmd == "run-chain":
        try:
            asyncio.run(_cmd_run_chain(args))
        except KeyboardInterrupt:
            pass
        return


if __name__ == "__main__":
    main()
