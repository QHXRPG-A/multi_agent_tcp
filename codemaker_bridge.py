"""Run `codemaker run` from asyncio (non-interactive CodeMaker CLI for TCP workers).

See project doc: multi_agent_tcp/codemaker_cli.md (codemaker run, --format json, -m model).
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import os
import time
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._proc_utils import async_kill_process_tree

log = logging.getLogger(__name__)

# Short ASCII only: first positional is required by `codemaker run` ("message or command").
_DEFAULT_RUN_STUB = "Task in attachment."

def _needs_file_for_unicode(text: str) -> bool:
    return any(ord(c) > 127 for c in text)


def _parse_codemaker_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    raw = cfg.get("codemaker")
    if not isinstance(raw, dict):
        raise ValueError("config missing object 'codemaker' for codemaker-worker mode")
    cwd = raw.get("cwd")
    if not cwd or not str(cwd).strip():
        raise ValueError("codemaker.cwd is required (project root with codemaker.json recommended)")
    command = str(raw.get("command", "codemaker")).strip() or "codemaker"
    base_args = raw.get("base_args")
    if base_args is None:
        base_args = ["run", "--format", "json"]
    if not isinstance(base_args, list) or not all(isinstance(x, str) for x in base_args):
        raise ValueError("codemaker.base_args must be a list of strings")
    model = raw.get("model")
    if model is not None and (not isinstance(model, str) or not str(model).strip()):
        raise ValueError("codemaker.model must be a non-empty string when set")
    if isinstance(model, str):
        model = model.strip()
        if not model.startswith("netease-codemaker/"):
            log.warning(
                "codemaker.model %r does not start with 'netease-codemaker/' — "
                "the official CLI requires this prefix (see codemaker_cli.md §model list)",
                model,
            )
    else:
        model = None
    timeout = raw.get("timeout_sec")
    if timeout is None:
        timeout_sec: Optional[float] = None
    else:
        timeout_sec = float(timeout)
    pvf = raw.get("prompt_via_file", "auto")
    if pvf not in ("never", "always", "auto"):
        raise ValueError("codemaker.prompt_via_file must be 'never', 'always', or 'auto'")
    anchor = raw.get("anchor_message")
    anchor_prefix: Optional[str] = None
    if anchor is not None:
        if not isinstance(anchor, str) or not str(anchor).strip():
            raise ValueError("codemaker.anchor_message must be a non-empty string when set")
        anchor_prefix = str(anchor).strip()
    stub = raw.get("run_stub_message")
    if stub is None:
        run_stub = _DEFAULT_RUN_STUB
    elif not isinstance(stub, str) or not str(stub).strip():
        raise ValueError("codemaker.run_stub_message must be a non-empty string when set")
    else:
        run_stub = str(stub).strip()
    extra_env = raw.get("extra_env")
    if extra_env is None:
        extra_env = cfg.get("extra_env")
    if extra_env is None:
        extra_env_dict: Dict[str, str] = {}
    elif isinstance(extra_env, dict):
        extra_env_dict = {str(k): str(v) for k, v in extra_env.items()}
    else:
        raise ValueError("codemaker.extra_env must be an object when set")
    execution_context = raw.get("execution_context")
    if execution_context is not None and not isinstance(execution_context, dict):
        raise ValueError("codemaker.execution_context must be an object when set")
    return {
        "command": command,
        "base_args": list(base_args),
        "cwd": Path(str(cwd)).expanduser().resolve(),
        "model": model,
        "timeout_sec": timeout_sec,
        "prompt_via_file": str(pvf),
        "anchor_message": anchor_prefix,
        "run_stub_message": run_stub,
        "extra_env": extra_env_dict,
        "prompt_preamble": raw.get("prompt_preamble"),
        "execution_context": dict(execution_context or {}),
    }


def _format_execution_context(context: Dict[str, Any]) -> str:
    if not context:
        return ""
    return (
        "# Agent Execution Context\n\n"
        "The framework provided this execution context for the current agent run.\n\n"
        "```json\n"
        f"{_json.dumps(context, ensure_ascii=False, indent=2, default=str)}\n"
        "```"
    )


def _merge_prompt(prompt: str, stdin_context: Optional[str], rt: Dict[str, Any]) -> str:
    parts: List[str] = []
    preamble = rt.get("prompt_preamble")
    if isinstance(preamble, str) and preamble.strip():
        parts.append(preamble.strip())
    context_block = _format_execution_context(rt.get("execution_context", {}))
    if context_block:
        parts.append(context_block)
    parts.append(prompt)
    if stdin_context:
        parts.append(f"# Upstream Context\n\n{stdin_context}")
    return "\n\n---\n\n".join(parts)


def _build_cmd_argv_only(prompt: str, rt: Dict[str, Any]) -> List[str]:
    parts: List[str] = [rt["command"], *rt["base_args"]]
    m = rt.get("model")
    if m:
        parts += ["-m", m]
    parts.append(prompt)
    return parts


def _build_cmd_with_prompt_file(path: Path, rt: Dict[str, Any]) -> List[str]:
    """``codemaker run`` requires at least one message; full UTF-8 task lives in ``-f`` file.

    Order: ``... [-m M] <stub message> -f <path>``. A trailing positional *after* ``-f`` is
    treated as another file path (see earlier ``File not found: ...`` errors).
    """
    parts: List[str] = [rt["command"], *rt["base_args"]]
    m = rt.get("model")
    if m:
        parts += ["-m", m]
    parts.append(rt["run_stub_message"])
    parts += ["-f", str(path.resolve())]
    return parts


def _write_prompt_utf8_file(text: str) -> Path:
    fd, name = tempfile.mkstemp(prefix="cm_prompt_", suffix=".md", text=False)
    try:
        data = text.encode("utf-8")
        os.write(fd, data)
    finally:
        os.close(fd)
    return Path(name)


_permission_warned: set[Path] = set()


def _check_permission_config(cwd: Path) -> None:
    """Warn once if the project's codemaker.json permission != 'allow'."""
    if cwd in _permission_warned:
        return
    _permission_warned.add(cwd)
    for rel in ("codemaker.json", ".codemaker/codemaker.json"):
        p = cwd / rel
        if p.is_file():
            try:
                cfg = _json.loads(p.read_text(encoding="utf-8"))
                perm = cfg.get("permission")
                if perm != "allow":
                    log.warning(
                        '[cil] %s has permission=%r (not "allow"); '
                        "non-interactive codemaker run may hang waiting for approval prompts",
                        p, perm,
                    )
            except Exception:
                pass
            return


async def codemaker_run(
    prompt: str,
    *,
    stdin_context: Optional[str] = None,
    codemaker_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Run one non-interactive `codemaker run ...`; return stdout/stderr/returncode."""
    text = _merge_prompt(prompt, stdin_context, codemaker_cfg)
    mode = codemaker_cfg.get("prompt_via_file", "auto")
    use_file = mode == "always" or (mode == "auto" and _needs_file_for_unicode(text))
    if mode == "never" and _needs_file_for_unicode(text):
        log.warning(
            "[cil] prompt contains non-ASCII but prompt_via_file='never'; "
            "Windows argv encoding may corrupt the prompt — consider 'auto'",
        )

    prompt_path: Optional[Path] = None
    if use_file:
        prefix = codemaker_cfg.get("anchor_message")
        file_body = f"{prefix}\n\n{text}" if isinstance(prefix, str) and prefix.strip() else text
        prompt_path = _write_prompt_utf8_file(file_body)
        cmd = _build_cmd_with_prompt_file(prompt_path, codemaker_cfg)
    else:
        cmd = _build_cmd_argv_only(text, codemaker_cfg)

    cwd: Path = codemaker_cfg["cwd"]
    if not cwd.is_dir():
        if prompt_path:
            try:
                prompt_path.unlink(missing_ok=True)  # type: ignore[arg-type]
            except OSError:
                pass
        raise FileNotFoundError(f"codemaker.cwd is not a directory: {cwd}")
    _check_permission_config(cwd)
    exe = cmd[0]
    if not Path(exe).is_file() and not shutil.which(exe):
        if prompt_path:
            try:
                prompt_path.unlink(missing_ok=True)  # type: ignore[arg-type]
            except OSError:
                pass
        raise FileNotFoundError(f"codemaker command not found on PATH: {exe}")

    cmd_preview = " ".join(cmd[:6]) + (" ..." if len(cmd) > 6 else "")
    if use_file:
        log.info(
            "[cil] spawn cwd=%s prompt_file=%s preview_argv=%s",
            cwd,
            prompt_path,
            cmd_preview,
        )
    else:
        log.info(
            "[cil] spawn cwd=%s prompt_chars=%s preview_argv=%s",
            cwd,
            len(text.encode("utf-8")),
            cmd_preview,
        )

    child_env = {**os.environ, "PYTHONUTF8": "1"}
    extra_env = codemaker_cfg.get("extra_env")
    if isinstance(extra_env, dict):
        child_env.update({str(k): str(v) for k, v in extra_env.items()})
    t0 = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=child_env,
    )
    log.info("[cil] subprocess started pid=%s", proc.pid)
    timeout = codemaker_cfg.get("timeout_sec")

    async def _communicate() -> tuple[bytes, bytes]:
        assert proc.stdout and proc.stderr
        return await proc.communicate()

    try:
        if timeout:
            out_b, err_b = await asyncio.wait_for(_communicate(), timeout=timeout)
        else:
            out_b, err_b = await _communicate()
    except asyncio.TimeoutError:
        log.warning(
            "[cil] TIMEOUT after %ss killing pid=%s tree (CLI still running, no stdout yet)",
            timeout,
            proc.pid,
        )
        await async_kill_process_tree(proc.pid, timeout=10.0)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass
        out_b, err_b = b"", b""
        rc_timeout = -9
        if prompt_path:
            try:
                prompt_path.unlink(missing_ok=True)  # type: ignore[arg-type]
            except OSError:
                pass
            prompt_path = None
        return {
            "returncode": rc_timeout,
            "stdout": "",
            "stderr": f"codemaker run timeout after {timeout}s",
            "timeout": True,
        }
    finally:
        if prompt_path:
            try:
                prompt_path.unlink(missing_ok=True)  # type: ignore[arg-type]
            except OSError:
                pass

    rc = proc.returncode if proc.returncode is not None else -1
    elapsed = time.monotonic() - t0
    log.info(
        "[cil] subprocess EXIT pid=%s returncode=%s elapsed_sec=%.2f stdout_chars=%s stderr_chars=%s",
        proc.pid,
        rc,
        elapsed,
        len(out_b),
        len(err_b),
    )
    if log.isEnabledFor(logging.DEBUG) and err_b:
        log.debug("[cil] stderr_head=%s", err_b[:800].decode("utf-8", errors="replace"))
    return {
        "returncode": rc,
        "stdout": out_b.decode("utf-8", errors="replace"),
        "stderr": err_b.decode("utf-8", errors="replace"),
        "timeout": False,
    }


def load_codemaker_runtime(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return _parse_codemaker_cfg(cfg)
