"""Run `codex exec` from asyncio for CLI-backed TCP workers."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ._proc_utils import async_kill_process_tree

log = logging.getLogger(__name__)

DANGEROUS_CODEX_SANDBOX = "danger-full-access"
AgentStreamCallback = Callable[[Dict[str, Any]], Awaitable[None]]


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _parse_str_list(raw: Any, *, field_name: str) -> List[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        raise ValueError(f"codex.{field_name} must be a list of strings")
    return [str(x) for x in raw]


def _normalize_sandbox(raw: Any) -> str:
    return str(raw or "").strip().lower()


def _resolve_cli_path(raw: str, *, cwd: Path) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = cwd / path
    return path.resolve()


def _resolve_windows_command_shim(raw: str) -> str:
    """Prefer Windows executable shims over PowerShell scripts.

    npm packages commonly install ``foo``, ``foo.cmd`` and ``foo.ps1``.  Python's
    direct subprocess APIs cannot execute a ``.ps1`` script through
    ``CreateProcess``; when a command resolves there, use the matching ``.cmd``
    shim if it exists.
    """
    if os.name != "nt":
        return raw

    command = str(raw).strip()
    if not command:
        return raw

    path = Path(command)
    if path.suffix.lower() == ".ps1":
        cmd_sibling = path.with_suffix(".cmd")
        if cmd_sibling.is_file():
            return str(cmd_sibling)
        return command

    if path.suffix:
        return command

    for suffix in (".cmd", ".exe", ".bat"):
        resolved = shutil.which(f"{command}{suffix}")
        if resolved:
            return resolved
    return command


def _paths_overlap(left: Path, right: Path) -> bool:
    left = left.resolve()
    right = right.resolve()
    return left == right or left in right.parents or right in left.parents


def _extra_arg_values(args: List[str], names: List[str]) -> List[str]:
    values: List[str] = []
    name_set = set(names)
    i = 0
    while i < len(args):
        item = args[i]
        matched = False
        for name in names:
            prefix = f"{name}="
            if item.startswith(prefix):
                values.append(item[len(prefix):])
                matched = True
                break
        if matched:
            i += 1
            continue
        if item in name_set and i + 1 < len(args):
            values.append(args[i + 1])
            i += 2
            continue
        i += 1
    return values


def validate_codex_launch_safety(
    *,
    cwd: Path,
    sandbox: Any,
    extra_args: List[str],
    protected_readonly_roots: Optional[List[Path]] = None,
) -> None:
    """Reject Codex launch options that would make read-only project roots writable."""
    normalized_sandbox = _normalize_sandbox(sandbox)
    if normalized_sandbox == DANGEROUS_CODEX_SANDBOX:
        raise ValueError("codex sandbox=danger-full-access is not allowed in strict blueprint runs")

    for value in _extra_arg_values(extra_args, ["--sandbox", "-s"]):
        if _normalize_sandbox(value) == DANGEROUS_CODEX_SANDBOX:
            raise ValueError("codex extra_args must not request sandbox=danger-full-access")

    if "--dangerously-bypass-approvals-and-sandbox" in extra_args:
        raise ValueError("codex extra_args must not bypass approvals and sandboxing")

    roots = [root.resolve() for root in (protected_readonly_roots or [])]
    if not roots:
        return

    for raw_dir in _extra_arg_values(extra_args, ["--add-dir"]):
        add_dir = _resolve_cli_path(raw_dir, cwd=cwd)
        for root in roots:
            if _paths_overlap(add_dir, root):
                raise ValueError(
                    "codex extra_args must not use --add-dir for the read-only project context"
                )


def _parse_codex_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    raw = cfg.get("codex")
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("config field 'codex' must be an object for codex-worker mode")

    cwd = raw.get("cwd", cfg.get("cwd"))
    if not cwd or not str(cwd).strip():
        raise ValueError("codex.cwd is required")

    command = _resolve_windows_command_shim(
        str(raw.get("command", cfg.get("command", "codex"))).strip() or "codex"
    )
    base_args = raw.get("base_args", raw.get("exec_args", ["exec"]))
    if not isinstance(base_args, list) or not all(isinstance(x, str) for x in base_args):
        raise ValueError("codex.base_args must be a list of strings")

    model = raw.get("model")
    if model is not None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("codex.model must be a non-empty string when set")
        model = model.strip()

    timeout = raw.get("timeout_sec")
    timeout_sec = None if timeout is None else float(timeout)

    extra_env = raw.get("extra_env")
    if extra_env is None:
        extra_env = cfg.get("extra_env")
    if extra_env is None:
        extra_env_dict: Dict[str, str] = {}
    elif isinstance(extra_env, dict):
        extra_env_dict = {str(k): str(v) for k, v in extra_env.items()}
    else:
        raise ValueError("codex.extra_env must be an object when set")

    execution_context = raw.get("execution_context")
    if execution_context is not None and not isinstance(execution_context, dict):
        raise ValueError("codex.execution_context must be an object when set")
    prompt_execution_context = raw.get("prompt_execution_context")
    if prompt_execution_context is not None and not isinstance(prompt_execution_context, dict):
        raise ValueError("codex.prompt_execution_context must be an object when set")

    parsed = {
        "command": command,
        "base_args": [str(x) for x in base_args],
        "cwd": Path(str(cwd)).expanduser().resolve(),
        "model": model,
        "timeout_sec": timeout_sec,
        "json": _as_bool(raw.get("json"), default=True),
        "output_last_message": _as_bool(raw.get("output_last_message"), default=True),
        "ephemeral": _as_bool(raw.get("ephemeral"), default=True),
        "ignore_user_config": _as_bool(raw.get("ignore_user_config"), default=False),
        "ignore_rules": _as_bool(raw.get("ignore_rules"), default=False),
        "skip_git_repo_check": _as_bool(raw.get("skip_git_repo_check"), default=False),
        "sandbox": raw.get("sandbox"),
        "profile": raw.get("profile"),
        "config_overrides": _parse_str_list(raw.get("config_overrides"), field_name="config_overrides"),
        "enable_features": _parse_str_list(raw.get("enable_features"), field_name="enable_features"),
        "disable_features": _parse_str_list(raw.get("disable_features"), field_name="disable_features"),
        "extra_args": _parse_str_list(raw.get("extra_args"), field_name="extra_args"),
        "image_paths": _parse_str_list(raw.get("image_paths"), field_name="image_paths"),
        "codex_home": raw.get("codex_home"),
        "prompt_preamble": raw.get("prompt_preamble"),
        "execution_context": dict(execution_context or {}),
        "prompt_execution_context": dict(prompt_execution_context or {}),
        "extra_env": extra_env_dict,
    }
    code_workspace = parsed["execution_context"].get("code_workspace")
    protected_roots: List[Path] = []
    if isinstance(code_workspace, dict) and code_workspace.get("project_context"):
        protected_roots.append(Path(str(code_workspace["project_context"])).expanduser())
    validate_codex_launch_safety(
        cwd=parsed["cwd"],
        sandbox=parsed.get("sandbox"),
        extra_args=parsed.get("extra_args", []),
        protected_readonly_roots=protected_roots,
    )
    return parsed


def load_codex_runtime(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return _parse_codex_cfg(cfg)


def _format_execution_context(context: Dict[str, Any]) -> str:
    if not context:
        return ""
    return (
        "# Codex Execution Context\n\n"
        "The framework provided this execution context for the current agent run.\n\n"
        "```json\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}\n"
        "```"
    )


def _merge_prompt(
    prompt: str,
    stdin_context: Optional[str],
    codex_cfg: Dict[str, Any],
) -> str:
    parts: List[str] = []
    preamble = codex_cfg.get("prompt_preamble")
    if isinstance(preamble, str) and preamble.strip():
        parts.append(preamble.strip())
    prompt_context = codex_cfg.get("prompt_execution_context")
    if not prompt_context:
        prompt_context = codex_cfg.get("execution_context", {})
    context_block = _format_execution_context(prompt_context)
    if context_block:
        parts.append(context_block)
    parts.append(prompt)
    if stdin_context:
        parts.append(f"# Upstream Context\n\n{stdin_context}")
    return "\n\n---\n\n".join(parts)


def _attachment_path(raw: Any) -> Optional[str]:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if not isinstance(raw, dict):
        return None

    value = raw.get("value")
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in ("path", "file", "file_path"):
            val = value.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

    for key in ("path", "file", "file_path"):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    meta = raw.get("meta")
    if isinstance(meta, dict):
        val = meta.get("path")
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _looks_like_image_attachment(raw: Any) -> bool:
    if isinstance(raw, str):
        return Path(raw).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    if not isinstance(raw, dict):
        return False
    kind = str(raw.get("kind", "")).lower()
    mime = str(raw.get("mime", "")).lower()
    return kind == "image" or mime.startswith("image/")


def _resolve_image_paths(
    attachments: List[Any],
    codex_cfg: Dict[str, Any],
) -> List[Path]:
    cwd: Path = codex_cfg["cwd"]
    raw_paths: List[str] = list(codex_cfg.get("image_paths") or [])
    for attachment in attachments:
        if not _looks_like_image_attachment(attachment):
            continue
        path = _attachment_path(attachment)
        if path:
            raw_paths.append(path)

    out: List[Path] = []
    for raw in raw_paths:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = cwd / path
        path = path.resolve()
        if not path.is_file():
            raise FileNotFoundError(f"codex image attachment not found: {path}")
        out.append(path)
    return out


def _build_codex_cmd(
    codex_cfg: Dict[str, Any],
    *,
    output_last_message_path: Optional[Path],
    image_paths: List[Path],
) -> List[str]:
    cwd: Path = codex_cfg["cwd"]
    cmd: List[str] = [codex_cfg["command"], *codex_cfg["base_args"]]

    for override in codex_cfg.get("config_overrides", []):
        cmd.extend(["--config", override])
    for feature in codex_cfg.get("enable_features", []):
        cmd.extend(["--enable", feature])
    for feature in codex_cfg.get("disable_features", []):
        cmd.extend(["--disable", feature])

    if codex_cfg.get("json"):
        cmd.append("--json")
    model = codex_cfg.get("model")
    if model:
        cmd.extend(["--model", str(model)])
    profile = codex_cfg.get("profile")
    if profile:
        cmd.extend(["--profile", str(profile)])
    sandbox = codex_cfg.get("sandbox")
    if sandbox:
        cmd.extend(["--sandbox", str(sandbox)])
    cmd.extend(["--cd", str(cwd)])
    if codex_cfg.get("skip_git_repo_check"):
        cmd.append("--skip-git-repo-check")
    if codex_cfg.get("ephemeral"):
        cmd.append("--ephemeral")
    if codex_cfg.get("ignore_user_config"):
        cmd.append("--ignore-user-config")
    if codex_cfg.get("ignore_rules"):
        cmd.append("--ignore-rules")
    if output_last_message_path is not None:
        cmd.extend(["--output-last-message", str(output_last_message_path)])
    for image_path in image_paths:
        cmd.extend(["--image", str(image_path)])
    cmd.extend(codex_cfg.get("extra_args", []))
    cmd.append("-")
    return cmd


def _parse_jsonl(stdout: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for line in stdout.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            events.append(obj)
    return events


def _extract_text_from_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [_extract_text_from_content(item) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        if isinstance(value.get("content"), (str, list, dict)):
            return _extract_text_from_content(value["content"])
        if isinstance(value.get("message"), (str, list, dict)):
            return _extract_text_from_content(value["message"])
    return ""


def codex_jsonl_event_to_agent_stream_events(
    event: Dict[str, Any],
    *,
    stream_context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Normalize public Codex JSONL events into blueprint agent stream events."""
    context = dict(stream_context or {})
    events: List[Dict[str, Any]] = []

    def base(kind: str) -> Dict[str, Any]:
        data = {
            "kind": kind,
            "run_id": context.get("run_id"),
            "node_id": context.get("node_id"),
            "agent_id": context.get("agent_id"),
            "message_id": context.get("message_id"),
            "raw": event,
        }
        return {key: value for key, value in data.items() if value is not None}

    item = event.get("item")
    if isinstance(item, dict):
        item_type = str(item.get("type", ""))
        item_id = str(item.get("id") or item.get("call_id") or item_type or "codex")
        if item_type in {"agent_message", "message"}:
            text = _extract_text_from_content(item.get("text") or item.get("content"))
            if text:
                data = base("part.delta")
                data.update(
                    {
                        "part_id": item_id,
                        "part_type": "text",
                        "field": "text",
                        "delta": text,
                        "text": text,
                        "status": "completed" if event.get("type") == "item.completed" else "running",
                    }
                )
                events.append(data)
        elif item_type in {"reasoning", "reasoning_summary", "thought"}:
            text = _extract_text_from_content(item.get("text") or item.get("content") or item.get("summary"))
            if text:
                data = base("part.delta")
                data.update(
                    {
                        "part_id": item_id,
                        "part_type": "reasoning",
                        "field": "text",
                        "delta": text,
                        "text": text,
                        "status": "completed" if event.get("type") == "item.completed" else "running",
                    }
                )
                events.append(data)
        elif "tool" in item_type or item_type in {"command_execution", "function_call"}:
            data = base("tool.completed" if event.get("type") == "item.completed" else "tool.started")
            data.update(
                {
                    "part_id": item_id,
                    "part_type": "tool",
                    "tool_name": item.get("name") or item.get("tool_name") or item_type,
                    "tool_input": item.get("arguments") or item.get("input") or item.get("command"),
                    "tool_output": item.get("output") or item.get("result"),
                    "status": "completed" if event.get("type") == "item.completed" else "running",
                }
            )
            events.append(data)

    message = event.get("message")
    if isinstance(message, (str, list, dict)):
        text = _extract_text_from_content(message)
        if text:
            data = base("part.delta")
            data.update(
                {
                    "part_id": str(event.get("message_id") or "message"),
                    "part_type": "text",
                    "field": "text",
                    "delta": text,
                    "text": text,
                    "status": "running",
                }
            )
            events.append(data)

    if event.get("type") == "turn.completed":
        data = base("message.completed")
        data.update({"status": "completed"})
        events.append(data)
    return events


def extract_codex_final_text(stdout: str) -> str:
    """Best-effort final assistant text extraction from `codex exec --json` stdout."""
    candidates: List[str] = []
    for event in _parse_jsonl(stdout):
        text = ""
        if isinstance(event.get("message"), (str, list, dict)):
            text = _extract_text_from_content(event["message"])
        if not text and isinstance(event.get("item"), dict):
            item = event["item"]
            if item.get("type") == "message" and item.get("role") == "assistant":
                text = _extract_text_from_content(item.get("content"))
        if not text and isinstance(event.get("content"), (str, list, dict)):
            text = _extract_text_from_content(event["content"])
        if text.strip():
            candidates.append(text.strip())
    return candidates[-1] if candidates else ""


async def codex_run(
    prompt: str,
    *,
    stdin_context: Optional[str] = None,
    attachments: Optional[List[Any]] = None,
    codex_cfg: Dict[str, Any],
    stream_callback: Optional[AgentStreamCallback] = None,
    stream_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run one non-interactive `codex exec` and return stdout/stderr/result metadata."""
    text = _merge_prompt(prompt, stdin_context, codex_cfg)
    cwd: Path = codex_cfg["cwd"]
    if not cwd.is_dir():
        raise FileNotFoundError(f"codex.cwd is not a directory: {cwd}")

    exe = str(codex_cfg["command"])
    if not Path(exe).is_file() and not shutil.which(exe):
        raise FileNotFoundError(f"codex command not found on PATH: {exe}")

    image_paths = _resolve_image_paths(list(attachments or []), codex_cfg)

    last_message_path: Optional[Path] = None
    if codex_cfg.get("output_last_message"):
        fd, name = tempfile.mkstemp(prefix="codex_last_", suffix=".md", text=False)
        os.close(fd)
        last_message_path = Path(name)

    cmd = _build_codex_cmd(
        codex_cfg,
        output_last_message_path=last_message_path,
        image_paths=image_paths,
    )
    cmd_preview = " ".join(cmd[:10]) + (" ..." if len(cmd) > 10 else "")
    log.info(
        "[codex] spawn cwd=%s prompt_chars=%s images=%s preview_argv=%s",
        cwd,
        len(text.encode("utf-8")),
        len(image_paths),
        cmd_preview,
    )

    child_env = {**os.environ, "PYTHONUTF8": "1"}
    extra_env = codex_cfg.get("extra_env")
    if isinstance(extra_env, dict):
        child_env.update({str(k): str(v) for k, v in extra_env.items()})
    codex_home = codex_cfg.get("codex_home")
    if codex_home:
        home = Path(str(codex_home)).expanduser().resolve()
        home.mkdir(parents=True, exist_ok=True)
        child_env["CODEX_HOME"] = str(home)

    t0 = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=child_env,
    )
    timeout = codex_cfg.get("timeout_sec")

    stdout_parts: List[str] = []
    stderr_parts: List[str] = []

    async def _emit(event: Dict[str, Any]) -> None:
        if stream_callback is not None:
            await stream_callback(event)

    async def _write_stdin() -> None:
        if proc.stdin is None:
            return
        proc.stdin.write(text.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()
        try:
            await proc.stdin.wait_closed()
        except (AttributeError, BrokenPipeError, ConnectionError):
            pass

    async def _read_stdout() -> None:
        if proc.stdout is None:
            return
        while True:
            chunk = await proc.stdout.readline()
            if not chunk:
                break
            line = chunk.decode("utf-8", errors="replace")
            stdout_parts.append(line)
            stripped = line.strip()
            if not stripped.startswith("{"):
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            for stream_event in codex_jsonl_event_to_agent_stream_events(
                event,
                stream_context=stream_context,
            ):
                await _emit(stream_event)

    async def _read_stderr() -> None:
        if proc.stderr is None:
            return
        while True:
            chunk = await proc.stderr.readline()
            if not chunk:
                break
            line = chunk.decode("utf-8", errors="replace")
            stderr_parts.append(line)
            await _emit(
                {
                    **dict(stream_context or {}),
                    "kind": "part.delta",
                    "part_id": "stderr",
                    "part_type": "stderr",
                    "field": "text",
                    "delta": line,
                    "text": line,
                    "status": "running",
                }
            )

    tasks = [
        asyncio.create_task(_write_stdin()),
        asyncio.create_task(_read_stdout()),
        asyncio.create_task(_read_stderr()),
        asyncio.create_task(proc.wait()),
    ]
    try:
        await (
            asyncio.wait_for(asyncio.gather(*tasks), timeout=timeout)
            if timeout
            else asyncio.gather(*tasks)
        )
    except asyncio.TimeoutError:
        log.warning("[codex] TIMEOUT after %ss killing pid=%s tree", timeout, proc.pid)
        await async_kill_process_tree(proc.pid, timeout=10.0)
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass
        if last_message_path:
            try:
                last_message = (
                    last_message_path.read_text(encoding="utf-8").strip()
                    if last_message_path.is_file()
                    else ""
                )
                last_message_path.unlink(missing_ok=True)
            except OSError:
                last_message = ""
        else:
            last_message = ""
        stdout = "".join(stdout_parts)
        stderr = "".join(stderr_parts)
        return {
            "returncode": -9,
            "stdout": stdout,
            "stderr": "\n".join(
                part
                for part in (stderr, f"codex exec timeout after {timeout}s")
                if part
            ),
            "timeout": True,
            "elapsed_sec": time.monotonic() - t0,
            "last_message": last_message,
            "final_text": last_message or extract_codex_final_text(stdout),
            "events": _parse_jsonl(stdout),
        }

    rc = proc.returncode if proc.returncode is not None else -1
    elapsed = time.monotonic() - t0
    stdout = "".join(stdout_parts)
    stderr = "".join(stderr_parts)
    last_message = ""
    if last_message_path and last_message_path.is_file():
        try:
            last_message = last_message_path.read_text(encoding="utf-8").strip()
        finally:
            try:
                last_message_path.unlink(missing_ok=True)
            except OSError:
                pass
    final_text = last_message or extract_codex_final_text(stdout)

    log.info(
        "[codex] subprocess EXIT pid=%s returncode=%s elapsed_sec=%.2f stdout_chars=%s stderr_chars=%s final_chars=%s",
        proc.pid,
        rc,
        elapsed,
        len(stdout),
        len(stderr),
        len(final_text),
    )
    return {
        "returncode": rc,
        "stdout": stdout,
        "stderr": stderr,
        "timeout": False,
        "elapsed_sec": elapsed,
        "last_message": last_message,
        "final_text": final_text,
        "events": _parse_jsonl(stdout),
    }
