from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gulicode_blueprint_service import blueprint_service, service_method
from multi_agent_tcp.hyskills_service import (
    DEFAULT_BASE_URL,
    DEFAULT_CACHE_TTL_SECONDS,
    HyskillsClient,
    HyskillsError,
    VISIBLE_PROJECT_ID,
)


SERVICE_NAME = "skill_square"
SERVICE_TITLE = "Skill 广场服务"
SERVICE_DESCRIPTION = "在 G83US 边界内搜索、读取并安装 Skill 广场技能。"
SKILL_REPO_URL = "ssh://git@gitlab.nie.netease.com:32200/hyxd-ai/hyxd-skills"
DEFAULT_INSTALL_TIMEOUT_SEC = 180
COMMAND_OUTPUT_LIMIT = 4000


ACTION_SCHEMAS: dict[str, dict[str, Any]] = {
    "help": {
        "action": "help",
        "description": "Return method schemas for this service.",
        "parameters": {
            "action": {
                "type": "str",
                "required": False,
                "description": "Optional method name: health, preflight, search, read, or install.",
            },
        },
    },
    "health": {
        "action": "health",
        "description": "Return service configuration and cache status without leaking credentials.",
        "parameters": {},
    },
    "preflight": {
        "action": "preflight",
        "description": "Check npx, git, global CODEX_HOME/skills, and SSH access to the Skill repo.",
        "parameters": {},
    },
    "search": {
        "action": "search",
        "description": "Search Skill Square within the fixed G83US boundary.",
        "parameters": {
            "query": {"type": "str", "required": True, "description": "Search text."},
            "limit": {"type": "int", "required": False, "default": 20, "description": "Maximum results."},
        },
    },
    "read": {
        "action": "read",
        "description": "Read one G83US skill summary, README, and docs list.",
        "parameters": {
            "skill_id": {"type": "str", "required": True, "description": "Skill id or name."},
        },
    },
    "install": {
        "action": "install",
        "description": "Install one G83US skill into the global CODEX_HOME/skills directory.",
        "parameters": {
            "skill_id": {"type": "str", "required": True, "description": "G83US skill id or name."},
            "timeout_sec": {
                "type": "int",
                "required": False,
                "default": DEFAULT_INSTALL_TIMEOUT_SEC,
                "description": "Maximum seconds for the npx install command.",
            },
        },
    },
}


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _tail_text(value: str, limit: int = COMMAND_OUTPUT_LIMIT) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[-limit:]


def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")).expanduser().resolve()


def _skills_dir() -> Path:
    return _codex_home() / "skills"


def _find_executable(*names: str) -> str:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return ""


def _run_command(
    command: list[str],
    *,
    timeout_sec: int,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(1, int(timeout_sec or 1)),
            check=False,
        )
        return CommandResult(completed.returncode, completed.stdout or "", completed.stderr or "")
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            124,
            _tail_text(exc.stdout or ""),
            _tail_text(exc.stderr or f"command timed out after {timeout_sec} seconds"),
        )
    except OSError as exc:
        return CommandResult(127, "", str(exc))


def _install_command(npx_path: str, skill_id: str) -> list[str]:
    return [npx_path, "skills", "add", SKILL_REPO_URL, "--skill", skill_id, "--yes"]


def _schema_payload(action: str = "") -> dict[str, Any]:
    requested = str(action or "").strip()
    allowed = sorted(ACTION_SCHEMAS)
    if requested:
        schema = ACTION_SCHEMAS.get(requested)
        if schema is None:
            return {
                "ok": False,
                "code": "UNKNOWN_ACTION",
                "error": f"unknown skill_square action: {requested}",
                "service": SERVICE_NAME,
                "title": SERVICE_TITLE,
                "allowedActions": allowed,
                "hint": "Call help() without action to inspect all method schemas.",
                "time": _now_iso(),
            }
        return {
            "ok": True,
            "service": SERVICE_NAME,
            "title": SERVICE_TITLE,
            "description": SERVICE_DESCRIPTION,
            "action": requested,
            "schema": schema,
            "time": _now_iso(),
        }
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "title": SERVICE_TITLE,
        "description": SERVICE_DESCRIPTION,
        "visible_scope": VISIBLE_PROJECT_ID,
        "allowedActions": allowed,
        "methods": {name: ACTION_SCHEMAS[name] for name in allowed},
        "usage": {
            "search": {
                "service_name": SERVICE_NAME,
                "method_name": "search",
                "arguments": {"query": "枪皮", "limit": 10},
            },
            "read": {
                "service_name": SERVICE_NAME,
                "method_name": "read",
                "arguments": {"skill_id": "G83US-gun-academy-config"},
            },
            "install": {
                "service_name": SERVICE_NAME,
                "method_name": "install",
                "arguments": {"skill_id": "G83US-gun-academy-config"},
            },
        },
        "time": _now_iso(),
    }


def _error_payload(exc: HyskillsError, *, action: str) -> dict[str, Any]:
    payload = exc.to_payload()
    payload.update(
        {
            "service": SERVICE_NAME,
            "action": action,
            "visible_scope": VISIBLE_PROJECT_ID,
            "time": _now_iso(),
        }
    )
    return payload


@blueprint_service(
    name="skill_square",
    title="Skill 广场服务",
    description="在 G83US 边界内搜索、读取并安装 Skill 广场技能。",
)
class SkillSquareService:
    def __init__(self) -> None:
        cache_ttl = float(os.environ.get("HYSKILLS_CACHE_TTL_SEC") or DEFAULT_CACHE_TTL_SECONDS)
        self.client = HyskillsClient(
            base_url=os.environ.get("HYSKILLS_BASE_URL") or DEFAULT_BASE_URL,
            cache_ttl_sec=cache_ttl,
        )

    @service_method(name="help", description="Return Skill Square service method schemas.")
    def help(self, action: str = "") -> dict:
        return _schema_payload(action)

    @service_method(name="health", description="Return Skill Square service status.")
    def health(self) -> dict:
        client_health = self.client.health()
        npx_path = _find_executable("npx.cmd", "npx")
        git_path = _find_executable("git.exe", "git")
        return {
            "ok": True,
            "service": SERVICE_NAME,
            "title": SERVICE_TITLE,
            "description": SERVICE_DESCRIPTION,
            "visible_scope": VISIBLE_PROJECT_ID,
            "skill_repo_url": SKILL_REPO_URL,
            "codex_home": str(_codex_home()),
            "skills_dir": str(_skills_dir()),
            "install_scope": "global CODEX_HOME/skills",
            "npx_available": bool(npx_path),
            "git_available": bool(git_path),
            "npx_path": npx_path,
            "git_path": git_path,
            "hyskills": {
                "base_url": client_health.get("base_url"),
                "cookie_configured": bool(client_health.get("cookie_configured")),
                "auth_header_configured": bool(client_health.get("auth_header_configured")),
                "cache_entries": client_health.get("cache_entries"),
                "cache_ttl_sec": client_health.get("cache_ttl_sec"),
            },
            "time": _now_iso(),
        }

    @service_method(name="preflight", description="Check local install prerequisites and Git SSH access.")
    def preflight(self) -> dict:
        npx_path = _find_executable("npx.cmd", "npx")
        git_path = _find_executable("git.exe", "git")
        codex_home = _codex_home()
        skills_dir = _skills_dir()
        checks: dict[str, Any] = {
            "npx": {"ok": bool(npx_path), "path": npx_path},
            "git": {"ok": bool(git_path), "path": git_path},
            "codex_home": str(codex_home),
            "skills_dir": str(skills_dir),
            "skill_repo_url": SKILL_REPO_URL,
        }
        if not npx_path:
            return {
                "ok": False,
                "code": "NPX_NOT_FOUND",
                "error": "npx is required to install Skill Square skills.",
                "service": SERVICE_NAME,
                "checks": checks,
                "time": _now_iso(),
            }
        if not git_path:
            return {
                "ok": False,
                "code": "GIT_NOT_FOUND",
                "error": "git is required to access the Skill Square repository.",
                "service": SERVICE_NAME,
                "checks": checks,
                "time": _now_iso(),
            }

        env = dict(os.environ)
        env["CODEX_HOME"] = str(codex_home)
        started_at = time.monotonic()
        ssh_check = _run_command(
            [git_path, "ls-remote", SKILL_REPO_URL, "HEAD"],
            timeout_sec=20,
            cwd=str(codex_home if codex_home.exists() else Path.home()),
            env=env,
        )
        checks["ssh"] = {
            "ok": ssh_check.returncode == 0,
            "returncode": ssh_check.returncode,
            "stdout": _tail_text(ssh_check.stdout),
            "stderr": _tail_text(ssh_check.stderr),
            "elapsed_sec": round(time.monotonic() - started_at, 3),
        }
        if ssh_check.returncode != 0:
            return {
                "ok": False,
                "code": "SSH_PRECHECK_FAILED",
                "error": "git SSH access to the Skill Square repository failed.",
                "service": SERVICE_NAME,
                "checks": checks,
                "hint": "Fix GitLab SSH access or the SSH host key before running install().",
                "time": _now_iso(),
            }
        return {
            "ok": True,
            "service": SERVICE_NAME,
            "checks": checks,
            "time": _now_iso(),
        }

    @service_method(name="search", description="Search G83US skills in Skill Square.")
    def search(self, query: str, limit: int = 20) -> dict:
        safe_limit = max(1, min(int(limit or 20), 200))
        try:
            result = self.client.search(
                q=str(query or ""),
                project=VISIBLE_PROJECT_ID,
                limit=safe_limit,
                offset=0,
            )
        except HyskillsError as exc:
            return _error_payload(exc, action="search")
        result.update(
            {
                "service": SERVICE_NAME,
                "action": "search",
                "visible_scope": VISIBLE_PROJECT_ID,
                "time": _now_iso(),
            }
        )
        return result

    @service_method(name="read", description="Read a G83US skill from Skill Square.")
    def read(self, skill_id: str) -> dict:
        try:
            result = self.client.read_skill(str(skill_id or "").strip())
        except HyskillsError as exc:
            return _error_payload(exc, action="read")
        result.update(
            {
                "service": SERVICE_NAME,
                "action": "read",
                "visible_scope": VISIBLE_PROJECT_ID,
                "time": _now_iso(),
            }
        )
        return result

    @service_method(name="install", description="Install a G83US skill into global CODEX_HOME/skills.")
    def install(self, skill_id: str, timeout_sec: int = DEFAULT_INSTALL_TIMEOUT_SEC) -> dict:
        raw_skill_id = str(skill_id or "").strip()
        if not raw_skill_id:
            return {
                "ok": False,
                "code": "BAD_SKILL_ID",
                "error": "skill_id is required.",
                "service": SERVICE_NAME,
                "action": "install",
                "time": _now_iso(),
            }
        try:
            detail = self.client.read_skill(raw_skill_id)
        except HyskillsError as exc:
            return _error_payload(exc, action="install")

        skill = detail.get("skill") if isinstance(detail, dict) else {}
        resolved_skill_id = str((skill or {}).get("id") or raw_skill_id).strip()
        preflight = self.preflight()
        if not preflight.get("ok"):
            return {
                "ok": False,
                "code": "INSTALL_PRECHECK_FAILED",
                "error": "Skill Square install preflight failed.",
                "service": SERVICE_NAME,
                "action": "install",
                "skill_id": resolved_skill_id,
                "visible_scope": VISIBLE_PROJECT_ID,
                "preflight": preflight,
                "time": _now_iso(),
            }

        codex_home = _codex_home()
        skills_dir = _skills_dir()
        skills_dir.mkdir(parents=True, exist_ok=True)
        npx_path = str(preflight.get("checks", {}).get("npx", {}).get("path") or "npx")
        command = _install_command(npx_path, resolved_skill_id)
        env = dict(os.environ)
        env["CODEX_HOME"] = str(codex_home)
        started_at = time.monotonic()
        run = _run_command(
            command,
            timeout_sec=max(1, int(timeout_sec or DEFAULT_INSTALL_TIMEOUT_SEC)),
            cwd=str(codex_home),
            env=env,
        )
        ok = run.returncode == 0
        return {
            "ok": ok,
            "code": "OK" if ok else "INSTALL_COMMAND_FAILED",
            "error": "" if ok else "npx skills add failed.",
            "service": SERVICE_NAME,
            "action": "install",
            "skill_id": resolved_skill_id,
            "visible_scope": VISIBLE_PROJECT_ID,
            "command": command,
            "codex_home": str(codex_home),
            "skills_dir": str(skills_dir),
            "returncode": run.returncode,
            "stdout": _tail_text(run.stdout),
            "stderr": _tail_text(run.stderr),
            "elapsed_sec": round(time.monotonic() - started_at, 3),
            "time": _now_iso(),
        }
