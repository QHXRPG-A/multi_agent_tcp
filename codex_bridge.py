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
from typing import Any, Dict, List, Optional

from ._proc_utils import async_kill_process_tree

log = logging.getLogger(__name__)


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


def _parse_codex_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    raw = cfg.get("codex")
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("config field 'codex' must be an object for codex-worker mode")

    cwd = raw.get("cwd", cfg.get("cwd"))
    if not cwd or not str(cwd).strip():
        raise ValueError("codex.cwd is required")

    command = str(raw.get("command", cfg.get("command", "codex"))).strip() or "codex"
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

    return {
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
        "extra_env": extra_env_dict,
    }


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
    context_block = _format_execution_context(codex_cfg.get("execution_context", {}))
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

    try:
        out_b, err_b = await asyncio.wait_for(
            proc.communicate(text.encode("utf-8")),
            timeout=timeout,
        ) if timeout else await proc.communicate(text.encode("utf-8"))
    except asyncio.TimeoutError:
        log.warning("[codex] TIMEOUT after %ss killing pid=%s tree", timeout, proc.pid)
        await async_kill_process_tree(proc.pid, timeout=10.0)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass
        if last_message_path:
            try:
                last_message_path.unlink(missing_ok=True)
            except OSError:
                pass
        return {
            "returncode": -9,
            "stdout": "",
            "stderr": f"codex exec timeout after {timeout}s",
            "timeout": True,
        }

    rc = proc.returncode if proc.returncode is not None else -1
    elapsed = time.monotonic() - t0
    stdout = out_b.decode("utf-8", errors="replace")
    stderr = err_b.decode("utf-8", errors="replace")
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
