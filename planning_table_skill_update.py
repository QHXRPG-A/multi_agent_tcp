"""Planning-table skill index update detection helpers."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence


DEFAULT_SKILL_ROOT = Path(os.environ.get("PLANNING_TABLE_SKILL_ROOT", r"F:\trunk_helper\AISkills"))
DEFAULT_INDEX_PATH = Path(
    os.environ.get("PLANNING_TABLE_SKILL_INDEX_PATH", r"F:\trunk_helper\AISkills\planning-table-skill-index.md")
)
DEFAULT_TARGET_PROJECT_DIR = Path(
    os.environ.get("PLANNING_TABLE_SKILL_TARGET_PROJECT_DIR", r"F:\src\Package\Script\Python\multi_agent_tcp")
)
DEFAULT_TARGET_BLUEPRINT_ID = os.environ.get("PLANNING_TABLE_SKILL_TARGET_BLUEPRINT_ID", "fill-planning-form")
DEFAULT_COMMIT_MESSAGE = os.environ.get(
    "PLANNING_TABLE_SKILL_COMMIT_MESSAGE",
    "#753970 Codex调试客户端1对多",
)
DEFAULT_SVN_UPDATE_TIMEOUT_SECONDS = float(
    os.environ.get("PLANNING_TABLE_SKILL_SVN_UPDATE_TIMEOUT_SECONDS", "180") or "180"
)
STATE_VERSION = 1
MAX_STDIO_CHARS = 8000


@dataclass(frozen=True)
class SkillCandidate:
    name: str
    skill_path: Path
    directory: Path
    file_kind: str
    description: str = ""
    indexed: bool = False

    @property
    def key(self) -> str:
        return skill_key(self.skill_path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "skillPath": str(self.skill_path),
            "directory": str(self.directory),
            "fileKind": self.file_kind,
            "description": self.description,
            "indexed": self.indexed,
            "key": self.key,
        }


def discover_skill_candidates(skill_root: Path | str, *, index_path: Path | str | None = None) -> list[SkillCandidate]:
    root = Path(skill_root).expanduser().resolve()
    indexed_paths = parse_indexed_skill_paths(index_path or root / "planning-table-skill-index.md")
    candidates: list[SkillCandidate] = []
    if not root.is_dir():
        return candidates
    for child in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
        if not child.is_dir():
            continue
        skill_path = child / "SKILL.md"
        file_kind = "SKILL.md"
        if not skill_path.is_file():
            legacy_files = sorted(child.glob("*.skill"), key=lambda item: item.name.casefold())
            if not legacy_files:
                continue
            skill_path = legacy_files[0]
            file_kind = "*.skill"
        resolved = skill_path.resolve()
        candidates.append(
            SkillCandidate(
                name=child.name,
                skill_path=resolved,
                directory=child.resolve(),
                file_kind=file_kind,
                description=description_from_skill_file(resolved),
                indexed=skill_key(resolved) in indexed_paths,
            )
        )
    return candidates


def parse_indexed_skill_paths(index_path: Path | str) -> set[str]:
    path = Path(index_path).expanduser()
    if not path.is_file():
        return set()
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="gb18030", errors="replace")
    except OSError:
        return set()
    matches = re.findall(r"[A-Za-z]:\\[^\r\n`]+?(?:SKILL\.md|[A-Za-z0-9._-]+\.skill)", text)
    return {skill_key(Path(match.strip().rstrip("。；;，,）)】]"))) for match in matches}


def load_state(state_path: Path | str) -> dict[str, Any]:
    path = Path(state_path)
    if not path.is_file():
        return {"version": STATE_VERSION, "knownSkillKeys": [], "pendingNotifications": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": STATE_VERSION, "knownSkillKeys": [], "pendingNotifications": {}}
    if not isinstance(payload, dict):
        return {"version": STATE_VERSION, "knownSkillKeys": [], "pendingNotifications": {}}
    payload.setdefault("version", STATE_VERSION)
    payload.setdefault("knownSkillKeys", [])
    payload.setdefault("pendingNotifications", {})
    if not isinstance(payload.get("knownSkillKeys"), list):
        payload["knownSkillKeys"] = []
    if not isinstance(payload.get("pendingNotifications"), dict):
        payload["pendingNotifications"] = {}
    return payload


def scan_for_updates(
    *,
    state_path: Path | str,
    notification_path: Path | str,
    skill_root: Path | str = DEFAULT_SKILL_ROOT,
    index_path: Path | str = DEFAULT_INDEX_PATH,
    target_project_dir: Path | str = DEFAULT_TARGET_PROJECT_DIR,
    target_blueprint_id: str = DEFAULT_TARGET_BLUEPRINT_ID,
    svn_update: bool = True,
    force: bool = False,
    run_command: Callable[..., Any] = subprocess.run,
    now: Optional[Callable[[], float]] = None,
    reason: str = "scheduled",
) -> dict[str, Any]:
    clock = now or time.time
    started = float(clock())
    root = Path(skill_root).expanduser().resolve()
    index = Path(index_path).expanduser().resolve()
    state = load_state(state_path)
    first_seed = not state.get("seededAt") and not state.get("knownSkillKeys")
    svn_result = _svn_update(root, run_command=run_command) if svn_update else {"ran": False}
    candidates = discover_skill_candidates(root, index_path=index)
    candidate_keys = {item.key for item in candidates}
    known_keys = {str(item) for item in state.get("knownSkillKeys", []) if str(item).strip()}
    pending = dict(state.get("pendingNotifications") or {})
    pending_keys = {
        str(key)
        for notification in pending.values()
        if isinstance(notification, dict)
        for key in notification.get("skillKeys", [])
        if str(key).strip()
    }

    created_notifications: list[dict[str, Any]] = []
    if first_seed and not force:
        known_keys.update(candidate_keys)
        state["seededAt"] = _iso_from_timestamp(started)
    else:
        if force:
            selected = [item for item in candidates if not item.indexed and item.key not in pending_keys]
        else:
            selected = [item for item in candidates if item.key not in known_keys and item.key not in pending_keys]
        if selected:
            notification = build_notification(
                candidates=selected,
                skill_root=root,
                index_path=index,
                target_project_dir=Path(target_project_dir).expanduser().resolve(),
                target_blueprint_id=target_blueprint_id,
                svn_result=svn_result,
                reason=reason,
                created_at=started,
            )
            append_notification(notification_path, notification)
            created_notifications.append(notification)
            pending[notification["notificationId"]] = {
                "notificationId": notification["notificationId"],
                "skillKeys": [item.key for item in selected],
                "createdAt": notification["createdAt"],
                "candidateCount": len(selected),
            }
            known_keys.update(item.key for item in selected)

    state.update(
        {
            "version": STATE_VERSION,
            "skillRoot": str(root),
            "indexPath": str(index),
            "knownSkillKeys": sorted(known_keys),
            "pendingNotifications": pending,
            "lastScan": {
                "reason": reason,
                "force": bool(force),
                "svnUpdate": bool(svn_update),
                "svn": svn_result,
                "candidateCount": len(candidates),
                "newNotificationCount": len(created_notifications),
                "scannedAt": _iso_from_timestamp(started),
            },
            "updatedAt": _iso_from_timestamp(float(clock())),
        }
    )
    save_state(state_path, state)
    return {
        "ok": not bool(svn_result.get("error")),
        "seeded": bool(first_seed and not force),
        "candidateCount": len(candidates),
        "pendingCount": len(pending),
        "notifications": [_notification_summary(item) for item in created_notifications],
        "statePath": str(Path(state_path)),
        "notificationPath": str(Path(notification_path)),
        "svn": svn_result,
    }


def mark_processed(
    *,
    state_path: Path | str,
    notification_id: str = "",
    skill_keys: Sequence[str] | None = None,
    now: Optional[Callable[[], float]] = None,
    note: str = "",
) -> dict[str, Any]:
    clock = now or time.time
    state = load_state(state_path)
    pending = dict(state.get("pendingNotifications") or {})
    removed: list[str] = []
    wanted_keys = {str(item) for item in skill_keys or [] if str(item).strip()}
    target_id = str(notification_id or "").strip()
    for key, value in list(pending.items()):
        record_keys = {str(item) for item in (value.get("skillKeys", []) if isinstance(value, dict) else [])}
        if (target_id and key == target_id) or (wanted_keys and record_keys.intersection(wanted_keys)):
            removed.append(key)
            pending.pop(key, None)
    state["pendingNotifications"] = pending
    state["lastProcessed"] = {
        "notificationId": target_id,
        "skillKeys": sorted(wanted_keys),
        "removedNotificationIds": removed,
        "note": str(note or ""),
        "processedAt": _iso_from_timestamp(float(clock())),
    }
    state["updatedAt"] = state["lastProcessed"]["processedAt"]
    save_state(state_path, state)
    return {"ok": True, "removedNotificationIds": removed, "pendingCount": len(pending)}


def build_notification(
    *,
    candidates: Sequence[SkillCandidate],
    skill_root: Path,
    index_path: Path,
    target_project_dir: Path,
    target_blueprint_id: str,
    svn_result: Mapping[str, Any],
    reason: str,
    created_at: float,
) -> dict[str, Any]:
    candidate_rows = [item.to_dict() for item in candidates]
    digest = hashlib.sha256(
        json.dumps(candidate_rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "version": 1,
        "notificationId": f"pts-{int(created_at)}-{digest}-{uuid.uuid4().hex[:8]}",
        "kind": "planning_table_skill_update",
        "reason": str(reason or "scheduled"),
        "createdAt": _iso_from_timestamp(created_at),
        "skillRoot": str(skill_root),
        "indexPath": str(index_path),
        "targetProjectDir": str(target_project_dir),
        "targetBlueprintId": str(target_blueprint_id or DEFAULT_TARGET_BLUEPRINT_ID),
        "commitMessage": DEFAULT_COMMIT_MESSAGE,
        "candidates": candidate_rows,
        "candidateCount": len(candidate_rows),
        "svn": dict(svn_result),
    }


def append_notification(notification_path: Path | str, notification: Mapping[str, Any]) -> None:
    path = Path(notification_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(dict(notification), ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def save_state(state_path: Path | str, state: Mapping[str, Any]) -> None:
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(dict(state), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def description_from_skill_file(path: Path | str) -> str:
    text = _read_skill_text(Path(path))
    if not text:
        return ""
    lines = text.splitlines()
    for index, line in enumerate(lines[:80]):
        stripped = line.strip()
        if stripped.startswith("description:"):
            value = stripped.split(":", 1)[1].strip()
            if value and value not in {">", ">-", "|", "|-"}:
                return value.strip("\"'")
            collected: list[str] = []
            for follow in lines[index + 1 : index + 12]:
                if follow.startswith((" ", "\t")):
                    part = follow.strip()
                    if part:
                        collected.append(part)
                    continue
                break
            return " ".join(collected).strip()
    for line in lines[:40]:
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("# ").strip()
    return ""


def skill_key(path: Path | str) -> str:
    return str(Path(path).expanduser().resolve()).casefold()


def _svn_update(root: Path, *, run_command: Callable[..., Any]) -> dict[str, Any]:
    try:
        completed = run_command(
            ["svn", "update", str(root)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=DEFAULT_SVN_UPDATE_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception as exc:
        return {"ran": True, "ok": False, "error": str(exc), "root": str(root)}
    return {
        "ran": True,
        "ok": getattr(completed, "returncode", 1) == 0,
        "returnCode": getattr(completed, "returncode", None),
        "stdout": _truncate(str(getattr(completed, "stdout", "") or "")),
        "stderr": _truncate(str(getattr(completed, "stderr", "") or "")),
        "root": str(root),
    }


def _read_skill_text(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if data.startswith(b"\x1f\x8b"):
        try:
            data = gzip.decompress(data)
        except OSError:
            return ""
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _truncate(text: str) -> str:
    value = str(text or "")
    if len(value) <= MAX_STDIO_CHARS:
        return value
    return value[:MAX_STDIO_CHARS] + "\n...[truncated]"


def _iso_from_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value).astimezone().isoformat()


def _notification_summary(notification: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "notificationId": notification.get("notificationId"),
        "candidateCount": notification.get("candidateCount"),
        "targetBlueprintId": notification.get("targetBlueprintId"),
        "createdAt": notification.get("createdAt"),
    }
