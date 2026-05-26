"""Shared workspace lifecycle, isolation, diff, and merge primitives.

This module uses the vendored Dulwich checkout for Git repository detection
and future Git-object integration, but intentionally keeps the first merge
backend file-oriented and local. The runtime never shells out to git or svn.
"""

from __future__ import annotations

import filecmp
import fnmatch
import difflib
import hashlib
import importlib.util
import json
import os
import shutil
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .dulwich_vendor import ensure_dulwich_path, has_dulwich_vendor

_DULWICH_AVAILABLE = False
if has_dulwich_vendor():
    ensure_dulwich_path()
    try:
        from dulwich.merge import merge_blobs  # type: ignore  # noqa: E402
        from dulwich.objects import Blob  # type: ignore  # noqa: E402
        from dulwich.repo import NotGitRepository, Repo  # type: ignore  # noqa: E402

        _DULWICH_AVAILABLE = True
    except Exception:  # pragma: no cover - fallback when vendored checkout is absent
        Blob = None  # type: ignore[assignment]
        merge_blobs = None  # type: ignore[assignment]
        NotGitRepository = Exception  # type: ignore[assignment]
        Repo = None  # type: ignore[assignment]
else:
    Blob = None  # type: ignore[assignment]
    merge_blobs = None  # type: ignore[assignment]
    NotGitRepository = Exception  # type: ignore[assignment]
    Repo = None  # type: ignore[assignment]


WORKSPACE_DIRNAME = ".multi_agent_workspace"
MANIFEST_NAME = "workspace.json"
BASIC_COPY_EXCLUDE_PATTERNS = (
    ".git",
    WORKSPACE_DIRNAME,
    "__pycache__",
    ".pytest_cache",
    "*.pyc",
)
DEFAULT_SNAPSHOT_EXCLUDE_PATTERNS = (
    *BASIC_COPY_EXCLUDE_PATTERNS,
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".next",
    ".nuxt",
    ".turbo",
    "target",
    "coverage",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.is_file():
        return dict(default)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_archive_id(raw: str) -> str:
    archive_id = str(raw).strip()
    if archive_id.endswith(".zip"):
        archive_id = archive_id[:-4]
    if not archive_id:
        raise ValueError("archive_id must be non-empty")
    if any(ch in archive_id for ch in ("/", "\\", ":", "\0")):
        raise ValueError("archive_id must be a file name, not a path")
    if archive_id in {".", ".."}:
        raise ValueError("archive_id must be a file name, not a path")
    return archive_id


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _relative_files(
    root: Path,
    *,
    excluded_roots: Optional[Sequence[Path]] = None,
    exclude_patterns: Optional[Sequence[str]] = None,
) -> Dict[str, Path]:
    root = root.resolve()
    excluded = [Path(p).resolve() for p in (excluded_roots or [])]
    patterns = [
        str(pattern).replace("\\", "/").strip()
        for pattern in (exclude_patterns or BASIC_COPY_EXCLUDE_PATTERNS)
        if str(pattern).strip()
    ]
    out: Dict[str, Path] = {}
    if not root.is_dir():
        return out
    for dir_path, dir_names, file_names in os.walk(root):
        base = Path(dir_path)
        dir_names[:] = [
            name
            for name in dir_names
            if not _path_is_copy_excluded(
                base / name,
                root,
                excluded_roots=excluded,
                exclude_patterns=patterns,
            )
        ]
        for name in file_names:
            path = base / name
            if not path.is_file():
                continue
            if _path_is_copy_excluded(
                path,
                root,
                excluded_roots=excluded,
                exclude_patterns=patterns,
            ):
                continue
            out[path.resolve().relative_to(root).as_posix()] = path
    return out


def _path_is_copy_excluded(
    path: Path,
    root: Path,
    *,
    excluded_roots: Optional[Sequence[Path]] = None,
    exclude_patterns: Optional[Sequence[str]] = None,
) -> bool:
    root = root.resolve()
    resolved = path.resolve()
    excluded = [Path(p).resolve() for p in (excluded_roots or [])]
    patterns = [
        str(pattern).replace("\\", "/").strip()
        for pattern in (exclude_patterns or BASIC_COPY_EXCLUDE_PATTERNS)
        if str(pattern).strip()
    ]
    if any(resolved == ex or _path_within(resolved, ex) for ex in excluded):
        return True
    rel = resolved.relative_to(root).as_posix()
    parts = rel.split("/")
    if any(_snapshot_pattern_matches(rel, part, patterns) for part in parts):
        return True
    return _snapshot_pattern_matches(rel, rel, patterns)


def _scope_static_prefix(scope: str) -> Optional[str]:
    normalized = str(scope).replace("\\", "/").strip().strip("/")
    if not normalized:
        return None
    parts: List[str] = []
    for part in normalized.split("/"):
        if not part or part in {".", ".."} or ":" in part:
            return None
        if any(ch in part for ch in ("*", "?", "[")):
            break
        parts.append(part)
    if not parts:
        return None
    return "/".join(parts)


def _scope_scan_roots(src: Path, scopes: Sequence[str]) -> Optional[List[Path]]:
    roots: List[Path] = []
    for scope in scopes:
        prefix = _scope_static_prefix(scope)
        if prefix is None:
            return None
        candidate = (src / Path(*prefix.split("/"))).resolve()
        if candidate != src and not _path_within(candidate, src):
            return None
        roots.append(candidate)

    deduped: List[Path] = []
    for root in sorted(set(roots), key=lambda item: len(item.parts)):
        if any(root == existing or _path_within(root, existing) for existing in deduped):
            continue
        deduped.append(root)
    return deduped


def _relative_files_from_candidates(
    root: Path,
    candidates: Sequence[Path],
    *,
    excluded_roots: Optional[Sequence[Path]] = None,
    exclude_patterns: Optional[Sequence[str]] = None,
) -> Dict[str, Path]:
    root = root.resolve()
    out: Dict[str, Path] = {}

    def record(path: Path) -> None:
        if not path.is_file():
            return
        try:
            rel = path.resolve().relative_to(root).as_posix()
        except ValueError:
            return
        if _path_is_copy_excluded(
            path,
            root,
            excluded_roots=excluded_roots,
            exclude_patterns=exclude_patterns,
        ):
            return
        out[rel] = path

    for candidate in candidates:
        if not candidate.exists():
            continue
        if _path_is_copy_excluded(
            candidate,
            root,
            excluded_roots=excluded_roots,
            exclude_patterns=exclude_patterns,
        ):
            continue
        if candidate.is_file():
            record(candidate)
            continue
        if candidate.is_dir():
            for dir_path, dir_names, file_names in os.walk(candidate):
                base = Path(dir_path)
                dir_names[:] = [
                    name
                    for name in dir_names
                    if not _path_is_copy_excluded(
                        base / name,
                        root,
                        excluded_roots=excluded_roots,
                        exclude_patterns=exclude_patterns,
                    )
                ]
                for name in file_names:
                    record(base / name)
    return out


def _snapshot_pattern_matches(rel_path: str, name: str, patterns: Sequence[str]) -> bool:
    rel_path = rel_path.replace("\\", "/").strip("/")
    name = name.strip("/")
    for pattern in patterns:
        normalized = pattern.replace("\\", "/").strip("/")
        if not normalized:
            continue
        if "/" not in normalized and fnmatch.fnmatch(name, normalized):
            return True
        if fnmatch.fnmatch(rel_path, normalized):
            return True
        if rel_path == normalized or rel_path.startswith(f"{normalized}/"):
            return True
    return False


def _copy_project_tree(
    src: Path,
    dst: Path,
    *,
    excluded_roots: Optional[Sequence[Path]] = None,
    exclude_patterns: Optional[Sequence[str]] = None,
    include_scopes: Optional[Sequence[str]] = None,
) -> None:
    src = Path(src).resolve()
    excluded = [Path(p).resolve() for p in (excluded_roots or [])]
    patterns = [
        str(pattern).replace("\\", "/").strip()
        for pattern in (exclude_patterns or BASIC_COPY_EXCLUDE_PATTERNS)
        if str(pattern).strip()
    ]
    scopes = [str(scope) for scope in (include_scopes or []) if str(scope).strip()]

    def ignore(dir_path: str, names: List[str]) -> set[str]:
        ignored: set[str] = set()
        base = Path(dir_path).resolve()
        pattern_ignore = shutil.ignore_patterns(*patterns)
        ignored.update(pattern_ignore(dir_path, names))
        for name in names:
            child = (base / name).resolve()
            try:
                child_rel = child.relative_to(src).as_posix()
            except ValueError:
                child_rel = name
            if any(child == ex or _path_within(child, ex) for ex in excluded):
                ignored.add(name)
                continue
            if _snapshot_pattern_matches(child_rel, name, patterns):
                ignored.add(name)
        return ignored

    _clear_directory_contents(dst)
    if scopes:
        scan_roots = _scope_scan_roots(src, scopes)
        files = (
            _relative_files(
                src,
                excluded_roots=excluded,
                exclude_patterns=patterns,
            )
            if scan_roots is None
            else _relative_files_from_candidates(
                src,
                scan_roots,
                excluded_roots=excluded,
                exclude_patterns=patterns,
            )
        )
        for rel, path in files.items():
            if not _scope_allows(rel, scopes):
                continue
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        return
    for item in src.iterdir():
        if item.name in ignore(str(src), [item.name]):
            continue
        target = dst / item.name
        if item.is_dir() and not item.is_symlink():
            shutil.copytree(item, target, ignore=ignore)
        else:
            shutil.copy2(item, target)


def _clear_directory_contents(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in list(path.iterdir()):
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def _scope_allows(path: str, scopes: Sequence[str]) -> bool:
    if not scopes:
        return True
    normalized = path.replace("\\", "/")
    for scope in scopes:
        pattern = str(scope).replace("\\", "/").strip()
        if not pattern:
            continue
        if pattern.endswith("/"):
            pattern = f"{pattern}**"
        if fnmatch.fnmatch(normalized, pattern):
            return True
        if normalized == pattern or normalized.startswith(f"{pattern}/"):
            return True
    return False


def _dedupe_scopes(scopes: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in scopes:
        scope = str(raw).replace("\\", "/").strip()
        if not scope or scope in seen:
            continue
        seen.add(scope)
        out.append(scope)
    return out


def _checkout_paths_to_scopes(paths: Sequence[str]) -> List[str]:
    scopes: List[str] = []
    for raw in paths:
        path = str(raw).replace("\\", "/").strip("/")
        if not path or path in {".", ".."} or ":" in path:
            raise ValueError(f"checkout path must be a safe relative path: {raw!r}")
        parts = path.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError(f"checkout path must be a safe relative path: {raw!r}")
        if any(ch in path for ch in ("*", "?", "[")):
            scopes.append(path)
        else:
            scopes.append(path)
            scopes.append(f"{path}/**")
    return _dedupe_scopes(scopes)


def _is_binary(path: Path) -> bool:
    try:
        data = path.read_bytes()[:4096]
    except OSError:
        return True
    return b"\x00" in data


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _safe_id(value: str, *, field_name: str = "id") -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value)
    if not safe:
        raise ValueError(f"{field_name} must not be empty")
    return safe


def _sha256_file(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _count_patch_lines(patch: str) -> tuple[int, int]:
    additions = 0
    deletions = 0
    for line in patch.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


def _unified_diff(base_file: Path, new_file: Path, rel_path: str) -> str:
    if (base_file.exists() and _is_binary(base_file)) or (new_file.exists() and _is_binary(new_file)):
        return ""
    try:
        base_lines = base_file.read_text(encoding="utf-8").splitlines() if base_file.exists() else []
        new_lines = new_file.read_text(encoding="utf-8").splitlines() if new_file.exists() else []
    except (OSError, UnicodeDecodeError):
        return ""
    lines = list(
        difflib.unified_diff(
            base_lines,
            new_lines,
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
            lineterm="",
        )
    )
    return "\n".join(lines) + ("\n" if lines else "")


def _is_text_diffable(path: Path) -> bool:
    if not path.exists():
        return True
    if _is_binary(path):
        return False
    try:
        path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return True


def _diff_is_binary(base_file: Path, new_file: Path) -> bool:
    return not _is_text_diffable(base_file) or not _is_text_diffable(new_file)


def _changed_line_regions(base_lines: List[str], other_lines: List[str]) -> List[tuple[int, int, List[str]]]:
    regions: List[tuple[int, int, List[str]]] = []
    matcher = difflib.SequenceMatcher(a=base_lines, b=other_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        regions.append((i1, i2, other_lines[j1:j2]))
    return regions


def _line_regions_overlap(left: tuple[int, int, List[str]], right: tuple[int, int, List[str]]) -> bool:
    left_start, left_end, left_replacement = left
    right_start, right_end, right_replacement = right
    if left_start == right_start and left_end == right_end:
        return left_replacement != right_replacement
    if left_start == left_end:
        return right_start <= left_start <= right_end
    if right_start == right_end:
        return left_start <= right_start <= left_end
    return max(left_start, right_start) < min(left_end, right_end)


def _merge_non_overlapping_line_changes(base: str, current: str, job: str) -> Optional[str]:
    base_lines = base.splitlines(keepends=True)
    current_changes = _changed_line_regions(base_lines, current.splitlines(keepends=True))
    job_changes = _changed_line_regions(base_lines, job.splitlines(keepends=True))

    for current_change in current_changes:
        for job_change in job_changes:
            if _line_regions_overlap(current_change, job_change):
                return None

    merged_changes: List[tuple[int, int, List[str]]] = []
    for change in [*current_changes, *job_changes]:
        if change not in merged_changes:
            merged_changes.append(change)
    merged_changes.sort(key=lambda item: (item[0], item[1]))

    merged_lines: List[str] = []
    cursor = 0
    for start, end, replacement in merged_changes:
        if start < cursor:
            return None
        merged_lines.extend(base_lines[cursor:start])
        merged_lines.extend(replacement)
        cursor = end
    merged_lines.extend(base_lines[cursor:])
    return "".join(merged_lines)


def _merge_text(base: str, current: str, job: str) -> tuple[bool, str]:
    """Three-way text merge, using Dulwich when its merge backend is available."""
    if current == job:
        return True, current
    if current == base:
        return True, job
    if job == base:
        return True, current
    conflict_preview: Optional[str] = None
    if _DULWICH_AVAILABLE and Blob is not None and merge_blobs is not None:
        try:
            merged, had_conflicts = merge_blobs(
                Blob.from_string(base.encode("utf-8")),
                Blob.from_string(current.encode("utf-8")),
                Blob.from_string(job.encode("utf-8")),
            )
            decoded = merged.decode("utf-8")
            if not had_conflicts:
                return True, decoded
            conflict_preview = decoded
        except Exception:
            pass
    merged = _merge_non_overlapping_line_changes(base, current, job)
    if merged is not None:
        return True, merged
    if conflict_preview is not None:
        return False, conflict_preview
    conflict = (
        "<<<<<<< CURRENT\n"
        f"{current}"
        "\n=======\n"
        f"{job}"
        "\n>>>>>>> JOB\n"
    )
    return False, conflict


@dataclass
class FileChange:
    path: str
    status: str
    additions: int = 0
    deletions: int = 0
    base_hash: Optional[str] = None
    new_hash: Optional[str] = None
    patch: Optional[str] = None
    binary: bool = False

    def to_dict(self, *, include_patch: bool = True) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "path": self.path,
            "status": self.status,
            "additions": self.additions,
            "deletions": self.deletions,
            "base_hash": self.base_hash,
            "new_hash": self.new_hash,
            "binary": self.binary,
            "has_patch": bool(self.patch),
        }
        if include_patch:
            data["patch"] = self.patch or ""
        return data


@dataclass
class MergeResult:
    ok: bool
    merged_files: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    scope_violations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "merged_files": list(self.merged_files),
            "conflicts": list(self.conflicts),
            "scope_violations": list(self.scope_violations),
        }


@dataclass
class ProjectWorkspace:
    project_root: Path
    workspace_root: Path
    workspace_id: str
    schema_version: int
    agent_access_mode: str = "readonly"


@dataclass
class RunWorkspace:
    run_id: str
    path: Path
    base_dir: Path
    integration_dir: Path
    jobs_dir: Path
    agents_dir: Path
    shared_dir: Optional[Path] = None
    shared_code_dir: Optional[Path] = None
    shared_artifacts_dir: Optional[Path] = None
    shared_reports_dir: Optional[Path] = None
    shared_locks_dir: Optional[Path] = None
    status: str = "created"
    long_term_workspace_root: Optional[Path] = None
    code_mode: str = "snapshot_copy"


@dataclass
class JobWorkspace:
    job_id: str
    path: Path
    worktree_dir: Path
    base_dir: Path
    status: str = "prepared"
    write_scope: List[str] = field(default_factory=list)
    artifact_scope: List[str] = field(default_factory=list)
    readonly_shared_paths: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "path": str(self.path),
            "worktree_dir": str(self.worktree_dir),
            "base_dir": str(self.base_dir),
            "write_scope": list(self.write_scope),
            "artifact_scope": list(self.artifact_scope),
            "readonly_shared_paths": list(self.readonly_shared_paths),
        }


@dataclass
class AgentCheckout:
    checkout_id: str
    run_id: str
    agent_id: str
    path: Path
    checkout_dir: Path
    state_dir: Path
    base_dir: Path
    base_ref: str
    write_scope: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkout_id": self.checkout_id,
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "path": str(self.path),
            "checkout_path": str(self.checkout_dir),
            "state_dir": str(self.state_dir),
            "base_dir": str(self.base_dir),
            "base_ref": self.base_ref,
            "write_scope": list(self.write_scope),
            "writable": True,
        }


@dataclass
class ChangesetSubmitResult:
    ok: bool
    status: str
    changeset_id: str
    merged_files: List[str] = field(default_factory=list)
    files: List[Dict[str, Any]] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    scope_violations: List[str] = field(default_factory=list)
    integration_ref: Optional[str] = None
    events: List[str] = field(default_factory=list)
    archive_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "ok": self.ok,
            "status": self.status,
            "changeset_id": self.changeset_id,
            "merged_files": list(self.merged_files),
            "files": list(self.files),
            "conflicts": list(self.conflicts),
            "scope_violations": list(self.scope_violations),
            "events": list(self.events),
        }
        if self.integration_ref is not None:
            data["integration_ref"] = self.integration_ref
        if self.archive_path is not None:
            data["archive_path"] = str(self.archive_path)
        return data


@dataclass
class BlueprintChangesetDetail:
    run_id: str
    changeset_id: str
    status: str
    diffs: List[Dict[str, Any]] = field(default_factory=list)
    binary_files: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "runId": self.run_id,
            "changesetId": self.changeset_id,
            "status": self.status,
            "diffs": list(self.diffs),
            "binaryFiles": list(self.binary_files),
            "metadata": dict(self.metadata),
        }


@dataclass
class BlueprintRunDiff:
    run_id: str
    summary: Dict[str, Any]
    changesets: List[Dict[str, Any]] = field(default_factory=list)
    accepted_diffs: List[Dict[str, Any]] = field(default_factory=list)
    binary_files: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def empty(cls, run_id: str) -> "BlueprintRunDiff":
        return cls(
            run_id=run_id,
            summary={
                "total": 0,
                "accepted": 0,
                "conflict": 0,
                "rejected": 0,
                "pending": 0,
                "failed": 0,
                "files": 0,
                "textFiles": 0,
                "binaryFiles": 0,
                "additions": 0,
                "deletions": 0,
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "runId": self.run_id,
            "summary": dict(self.summary),
            "changesets": list(self.changesets),
            "acceptedDiffs": list(self.accepted_diffs),
            "binaryFiles": list(self.binary_files),
        }


@dataclass
class SharedWriteLease:
    lease_id: str
    owner: str
    path: str
    lock_path: Path
    expires_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "owner": self.owner,
            "path": self.path,
            "lock_path": str(self.lock_path),
            "expires_at": self.expires_at,
            "mode": "write",
        }


@dataclass
class SharedReadLease:
    lease_id: str
    owner: str
    path: str
    lock_path: Path
    expires_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "owner": self.owner,
            "path": self.path,
            "lock_path": str(self.lock_path),
            "expires_at": self.expires_at,
            "mode": "read",
        }


class DulwichWorkspaceManager:
    """Manage long-term and per-run shared workspaces.

    The current model separates per-agent private scratch space from the
    per-run shared outcome space. Legacy job worktrees remain for compatibility
    with the earlier merge tests, but blueprint runs should publish outcomes
    into ``run.shared_dir`` rather than merging private scratch directories.
    """

    def __init__(
        self,
        project_root: Path,
        *,
        workspace_root: Optional[Path] = None,
        workspace_id: Optional[str] = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.workspace_root = (
            Path(workspace_root).expanduser().resolve()
            if workspace_root is not None
            else self.project_root / WORKSPACE_DIRNAME
        )
        if self.workspace_root == self.project_root:
            raise ValueError("workspace_root must not be the project root")
        self.workspace_id = workspace_id or self.project_root.name
        self.schema_version = 1

    @classmethod
    def open_or_init(
        cls,
        project_root: Path,
        *,
        workspace_root: Optional[Path] = None,
        workspace_id: Optional[str] = None,
        create: bool = True,
    ) -> "DulwichWorkspaceManager":
        mgr = cls(project_root, workspace_root=workspace_root, workspace_id=workspace_id)
        manifest = mgr.workspace_root / MANIFEST_NAME
        if not manifest.exists():
            if not create:
                raise FileNotFoundError(f"project workspace not initialized: {manifest}")
            mgr.init_project_workspace()
        else:
            data = _read_json(manifest, {})
            mgr.workspace_id = str(data.get("workspace_id", mgr.workspace_id))
            mgr.schema_version = int(data.get("schema_version", mgr.schema_version))
        return mgr

    def init_project_workspace(self) -> ProjectWorkspace:
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        for rel in ("runs/active", "runs/archived", "runs/failed"):
            (self.workspace_root / rel).mkdir(parents=True, exist_ok=True)
        git_detected = False
        if _DULWICH_AVAILABLE and Repo is not None:
            git_detected = True
            try:
                Repo(str(self.project_root))
            except NotGitRepository:
                git_detected = False
        _write_json(
            self.workspace_root / MANIFEST_NAME,
            {
                "workspace_id": self.workspace_id,
                "schema_version": self.schema_version,
                "project_root": str(self.project_root),
                "workspace_root": str(self.workspace_root),
                "created_at": _utc_now(),
                "backend": "dulwich",
                "git_detected": git_detected,
                "archive_mode": "full_directory",
                "archive_deletion_api": "reserved",
                "agent_access": {
                    "path": str(self.workspace_root),
                    "mode": "readonly",
                    "note": "Agents may read this long-term shared workspace but must not write it.",
                },
            },
        )
        return ProjectWorkspace(
            project_root=self.project_root,
            workspace_root=self.workspace_root,
            workspace_id=self.workspace_id,
            schema_version=self.schema_version,
            agent_access_mode="readonly",
        )

    def create_run(
        self,
        *,
        run_id: Optional[str] = None,
        code_mode: str = "snapshot_copy",
        snapshot_scope: Optional[Sequence[str]] = None,
        snapshot_exclude: Optional[Sequence[str]] = None,
    ) -> RunWorkspace:
        if code_mode not in {"snapshot_copy", "project_reference"}:
            raise ValueError("code_mode must be snapshot_copy or project_reference")
        run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
        run_path = self.workspace_root / "runs" / "active" / run_id
        if run_path.exists():
            raise FileExistsError(f"run workspace already exists: {run_path}")
        base_dir = run_path / "base"
        shared_dir = run_path / "shared"
        integration_dir = shared_dir / "code"
        shared_artifacts_dir = shared_dir / "artifacts"
        shared_reports_dir = shared_dir / "reports"
        shared_locks_dir = shared_dir / ".locks"
        jobs_dir = run_path / "jobs"
        agents_dir = run_path / "agents"
        run_path.mkdir(parents=True)
        scopes = [str(s) for s in (snapshot_scope or []) if str(s).strip()]
        exclude_patterns = [
            *DEFAULT_SNAPSHOT_EXCLUDE_PATTERNS,
            *[str(s) for s in (snapshot_exclude or []) if str(s).strip()],
        ]
        if code_mode == "snapshot_copy":
            _copy_project_tree(
                self.project_root,
                base_dir,
                excluded_roots=[self.workspace_root],
                exclude_patterns=exclude_patterns,
                include_scopes=scopes,
            )
            _copy_project_tree(base_dir, integration_dir)
        else:
            base_dir.mkdir(parents=True)
            integration_dir.mkdir(parents=True)
        shared_artifacts_dir.mkdir(parents=True)
        shared_reports_dir.mkdir(parents=True)
        shared_locks_dir.mkdir(parents=True)
        jobs_dir.mkdir()
        agents_dir.mkdir()
        _write_json(
            shared_dir / "manifest.json",
            {
                "run_id": run_id,
                "created_at": _utc_now(),
                "writes": [],
                "locks": [],
            },
        )
        data = {
            "run_id": run_id,
            "workspace_id": self.workspace_id,
            "long_term_workspace_root": str(self.workspace_root),
            "base_dir": str(base_dir),
            "shared_dir": str(shared_dir),
            "shared_code_dir": str(integration_dir),
            "shared_artifacts_dir": str(shared_artifacts_dir),
            "shared_reports_dir": str(shared_reports_dir),
            "agent_access": {
                "path": str(self.workspace_root),
                "mode": "readonly",
            },
            "status": "running",
            "created_at": _utc_now(),
            "archive_mode": "full_directory",
            "private_workspace_retention": "discard_on_archive",
            "code_mode": code_mode,
            "project_code_root": str(self.project_root),
            "snapshot_scope": list(scopes),
            "snapshot_exclude": list(exclude_patterns),
        }
        _write_json(run_path / "run_manifest.json", data)
        return RunWorkspace(
            run_id=run_id,
            path=run_path,
            base_dir=base_dir,
            integration_dir=integration_dir,
            jobs_dir=jobs_dir,
            agents_dir=agents_dir,
            shared_dir=shared_dir,
            shared_code_dir=integration_dir,
            shared_artifacts_dir=shared_artifacts_dir,
            shared_reports_dir=shared_reports_dir,
            shared_locks_dir=shared_locks_dir,
            status="running",
            long_term_workspace_root=self.workspace_root,
            code_mode=code_mode,
        )

    def open_run(self, run_id: str) -> RunWorkspace:
        run_path = self.workspace_root / "runs" / "active" / run_id
        if not run_path.is_dir():
            raise FileNotFoundError(f"active run not found: {run_path}")
        return self._open_run_at_path(run_id, run_path)

    def open_run_any(self, run_id: str) -> RunWorkspace:
        for bucket in ("active", "archived", "failed"):
            run_path = self.workspace_root / "runs" / bucket / run_id
            if run_path.is_dir():
                return self._open_run_at_path(run_id, run_path)
        raise FileNotFoundError(f"run not found: {run_id}")

    def _open_run_at_path(self, run_id: str, run_path: Path) -> RunWorkspace:
        manifest = _read_json(run_path / "run_manifest.json", {})
        return RunWorkspace(
            run_id=str(manifest.get("run_id") or run_id),
            path=run_path,
            base_dir=run_path / "base",
            integration_dir=run_path / "shared" / "code",
            jobs_dir=run_path / "jobs",
            agents_dir=run_path / "agents",
            shared_dir=run_path / "shared",
            shared_code_dir=run_path / "shared" / "code",
            shared_artifacts_dir=run_path / "shared" / "artifacts",
            shared_reports_dir=run_path / "shared" / "reports",
            shared_locks_dir=run_path / "shared" / ".locks",
            status=manifest.get("status", "running"),
            long_term_workspace_root=self.workspace_root,
            code_mode=str(manifest.get("code_mode", "snapshot_copy")),
        )

    def agent_workspace_dir(self, run: RunWorkspace, agent_id: str) -> Path:
        """Return the per-agent private scratch directory for this run.

        This directory is intentionally not an outcome worktree. It is for
        cache, temporary files, authorized skill views, and CLI-local state.
        It is discarded before the run is archived.
        """
        safe = _safe_id(agent_id, field_name="agent_id")
        path = run.agents_dir / safe / "private"
        path.mkdir(parents=True, exist_ok=True)
        _write_json(
            path.parent / "agent_workspace.json",
            {
                "agent_id": agent_id,
                "private_workspace": str(path),
                "shared_workspace": str(run.shared_dir or (run.path / "shared")),
                "retention": "discard_on_archive",
                "updated_at": _utc_now(),
            },
        )
        return path

    def _run_code_mode(self, run: RunWorkspace) -> str:
        mode = getattr(run, "code_mode", "") or ""
        if mode:
            return str(mode)
        data = _read_json(run.path / "run_manifest.json", {})
        return str(data.get("code_mode", "snapshot_copy"))

    def _run_code_source(self, run: RunWorkspace) -> Path:
        if self._run_code_mode(run) == "project_reference":
            return self.project_root
        return run.integration_dir

    def _run_code_target(self, run: RunWorkspace) -> Path:
        if self._run_code_mode(run) == "project_reference":
            return self.project_root
        return run.integration_dir

    def _checkout_scopes(self, write_scope: Optional[Sequence[str]]) -> List[str]:
        return [str(s) for s in (write_scope or []) if str(s).strip()]

    def _checkout_scope_allows(
        self,
        run: RunWorkspace,
        path: str,
        scopes: Sequence[str],
    ) -> bool:
        if self._run_code_mode(run) == "project_reference" and not scopes:
            return False
        return _scope_allows(path, scopes)

    def _restore_checkout_framework_files(self, checkout: AgentCheckout) -> None:
        """Keep framework-injected checkout files out of the agent changeset."""
        for name in ("AGENTS.md",):
            source = checkout.checkout_dir / name
            if source.is_file():
                target = checkout.base_dir / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

    def _capture_checkout_framework_files(self, checkout_dir: Path) -> Dict[str, str]:
        files: Dict[str, str] = {}
        for name in ("AGENTS.md",):
            path = checkout_dir / name
            if path.is_file():
                files[name] = path.read_text(encoding="utf-8")
        return files

    def _write_checkout_framework_files(
        self,
        checkout: AgentCheckout,
        files: Dict[str, str],
    ) -> None:
        for name, text in files.items():
            _write_text(checkout.checkout_dir / name, text)
            _write_text(checkout.base_dir / name, text)

    def checkout_agent(
        self,
        run: RunWorkspace,
        agent_id: str,
        *,
        write_scope: Optional[Sequence[str]] = None,
        checkout_paths: Optional[Sequence[str]] = None,
        mode: str = "full",
    ) -> AgentCheckout:
        """Create or refresh a VCS-style private checkout for an agent."""
        if mode != "full":
            raise ValueError("only full checkout mode is currently supported")
        self._validate_readonly_workspace_not_writable(write_scope or [])
        safe_agent = _safe_id(agent_id, field_name="agent_id")
        private = self.agent_workspace_dir(run, agent_id)
        checkout_dir = private / "checkout"
        state_dir = private / "state"
        checkout_base_dir = state_dir / "base"
        state_dir.mkdir(parents=True, exist_ok=True)
        scopes = _dedupe_scopes(
            [
                *self._checkout_scopes(write_scope),
                *_checkout_paths_to_scopes(checkout_paths or []),
            ]
        )
        source = self._run_code_source(run)
        framework_files = self._capture_checkout_framework_files(checkout_dir)
        if self._run_code_mode(run) == "project_reference" and not scopes:
            _clear_directory_contents(checkout_dir)
            _clear_directory_contents(checkout_base_dir)
        else:
            _copy_project_tree(source, checkout_dir, include_scopes=scopes)
            _copy_project_tree(source, checkout_base_dir, include_scopes=scopes)
        checkout_id = f"co-{uuid.uuid4().hex[:12]}"
        base_ref = f"int-{run.run_id}-checkout"
        checkout = AgentCheckout(
            checkout_id=checkout_id,
            run_id=run.run_id,
            agent_id=agent_id,
            path=run.agents_dir / safe_agent / "private",
            checkout_dir=checkout_dir,
            state_dir=state_dir,
            base_dir=checkout_base_dir,
            base_ref=base_ref,
            write_scope=scopes,
        )
        self._write_checkout_framework_files(checkout, framework_files)
        data = checkout.to_dict()
        data["created_at"] = _utc_now()
        _write_json(private / "checkout.json", data)
        self._record_workspace_event(
            run,
            "CheckoutCreated",
            {
                "agent_id": agent_id,
                "checkout_id": checkout_id,
                "base_ref": base_ref,
                "write_scope": list(checkout.write_scope),
                "code_mode": self._run_code_mode(run),
                "code_source": str(source),
            },
        )
        return checkout

    def open_agent_checkout(self, run: RunWorkspace, agent_id: str) -> AgentCheckout:
        private = self.agent_workspace_dir(run, agent_id)
        data = _read_json(private / "checkout.json", {})
        if not data:
            raise FileNotFoundError(f"agent checkout not found: {agent_id}")
        return AgentCheckout(
            checkout_id=str(data["checkout_id"]),
            run_id=str(data.get("run_id", run.run_id)),
            agent_id=str(data.get("agent_id", agent_id)),
            path=private,
            checkout_dir=Path(str(data["checkout_path"])),
            state_dir=Path(str(data["state_dir"])),
            base_dir=Path(str(data.get("base_dir") or Path(str(data["state_dir"])) / "base")),
            base_ref=str(data.get("base_ref", f"base-{run.run_id}")),
            write_scope=[str(s) for s in data.get("write_scope", [])],
        )

    def status_checkout(self, run: RunWorkspace, checkout: AgentCheckout) -> List[FileChange]:
        return self._diff_dirs(checkout.base_dir, checkout.checkout_dir, include_patch=False)

    def diff_checkout(self, run: RunWorkspace, checkout: AgentCheckout) -> List[FileChange]:
        return self._diff_dirs(checkout.base_dir, checkout.checkout_dir, include_patch=True)

    def blueprint_run_diff(self, run: RunWorkspace) -> BlueprintRunDiff:
        changesets_dir = run.path / "changesets"
        if not changesets_dir.exists():
            return BlueprintRunDiff.empty(run.run_id)

        summary = BlueprintRunDiff.empty(run.run_id).summary
        changesets: List[Dict[str, Any]] = []
        accepted_diffs: List[Dict[str, Any]] = []
        binary_files: List[Dict[str, Any]] = []

        for root in sorted(changesets_dir.iterdir()):
            if not root.is_dir():
                continue
            changeset = _read_json(root / "changeset.json", {})
            submit_result = _read_json(root / "submit_result.json", {})
            if not isinstance(changeset, dict):
                changeset = {}
            if not isinstance(submit_result, dict):
                submit_result = {}
            patch_path = root / "patch.diff"
            patch_exists = patch_path.is_file()
            detail = self._blueprint_changeset_from_archive(
                run,
                root,
                changeset,
                submit_result,
                patch_exists=patch_exists,
            )
            item = detail.metadata
            status = detail.status if detail.status in {"accepted", "conflict", "rejected", "pending", "failed"} else "pending"
            summary["total"] += 1
            summary[status] = int(summary.get(status, 0)) + 1
            summary["files"] += int(item.get("fileCount") or 0)
            summary["textFiles"] += int(item.get("textFileCount") or 0)
            summary["binaryFiles"] += int(item.get("binaryFileCount") or 0)
            summary["additions"] += int(item.get("additions") or 0)
            summary["deletions"] += int(item.get("deletions") or 0)
            changesets.append(item)
            binary_files.extend(detail.binary_files)
            if detail.status == "accepted" and patch_exists:
                accepted_diffs.extend(detail.diffs)

        return BlueprintRunDiff(
            run_id=run.run_id,
            summary=summary,
            changesets=changesets,
            accepted_diffs=accepted_diffs,
            binary_files=binary_files,
        )

    def blueprint_changeset_detail(self, run: RunWorkspace, changeset_id: str) -> BlueprintChangesetDetail:
        safe_changeset_id = _safe_id(str(changeset_id).strip(), field_name="changeset_id")
        root = run.path / "changesets" / safe_changeset_id
        if not root.is_dir():
            raise FileNotFoundError(f"changeset archive not found: {safe_changeset_id}")
        patch_path = root / "patch.diff"
        if not patch_path.is_file():
            raise FileNotFoundError(f"changeset patch.diff not found: {safe_changeset_id}")
        changeset = _read_json(root / "changeset.json", {})
        submit_result = _read_json(root / "submit_result.json", {})
        if not isinstance(changeset, dict):
            changeset = {}
        if not isinstance(submit_result, dict):
            submit_result = {}
        return self._blueprint_changeset_from_archive(
            run,
            root,
            changeset,
            submit_result,
            patch_exists=True,
        )

    def submit_checkout(
        self,
        run: RunWorkspace,
        checkout: AgentCheckout,
        *,
        task_id: Optional[str] = None,
        summary: str = "",
        test_results: Optional[Sequence[Dict[str, Any]]] = None,
        risks: Optional[Sequence[str]] = None,
    ) -> ChangesetSubmitResult:
        changes = self.diff_checkout(run, checkout)
        changeset_id = f"cs-{uuid.uuid4().hex[:12]}"
        allowed_scopes = list(checkout.write_scope)
        scope_violations = [
            change.path
            for change in changes
            if not self._checkout_scope_allows(run, change.path, allowed_scopes)
        ]
        file_dicts = [change.to_dict() for change in changes]
        self._record_workspace_event(
            run,
            "ChangesetSubmitted",
            {
                "changeset_id": changeset_id,
                "agent_id": checkout.agent_id,
                "task_id": task_id,
                "base_ref": checkout.base_ref,
                "files": [change.path for change in changes],
            },
        )

        conflicts: List[Dict[str, Any]] = []
        planned: List[tuple[FileChange, Optional[bytes], Optional[str]]] = []
        if not scope_violations:
            for change in changes:
                ok, merged_bytes, conflict = self._plan_checkout_change(run, checkout, change)
                if ok:
                    planned.append((change, merged_bytes, None))
                else:
                    conflicts.append(conflict or {"path": change.path, "reason": "conflict"})

        status = "accepted"
        ok = True
        events = ["ChangesetSubmitted"]
        merged_files: List[str] = []
        integration_ref: Optional[str] = None
        if scope_violations:
            ok = False
            status = "rejected"
        elif conflicts:
            ok = False
            status = "conflict"
            events.append("ConflictDetected")
            self._record_conflict(run, changeset_id, checkout, conflicts)
            self._record_workspace_event(
                run,
                "ConflictDetected",
                {
                    "changeset_id": changeset_id,
                    "agent_id": checkout.agent_id,
                    "files": [item.get("path") for item in conflicts],
                },
            )
        else:
            for change, merged_bytes, _ in planned:
                self._apply_checkout_change(run, change, merged_bytes)
                merged_files.append(change.path)
            integration_ref = f"int-{uuid.uuid4().hex[:12]}"
            if checkout.base_dir.exists():
                shutil.rmtree(checkout.base_dir)
            _copy_project_tree(
                self._run_code_source(run),
                checkout.base_dir,
                include_scopes=checkout.write_scope,
            )
            self._restore_checkout_framework_files(checkout)
            checkout.base_ref = integration_ref
            data = checkout.to_dict()
            data["submitted_at"] = _utc_now()
            _write_json(checkout.path / "checkout.json", data)
            events.extend(["ChangesetAccepted", "WorkspaceChanged"])
            self._record_workspace_event(
                run,
                "ChangesetAccepted",
                {
                    "changeset_id": changeset_id,
                    "agent_id": checkout.agent_id,
                    "merged_files": list(merged_files),
                    "integration_ref": integration_ref,
                },
            )
            self._record_workspace_event(
                run,
                "WorkspaceChanged",
                {
                    "changeset_id": changeset_id,
                    "agent_id": checkout.agent_id,
                    "paths": list(merged_files),
                },
            )

        result = ChangesetSubmitResult(
            ok=ok,
            status=status,
            changeset_id=changeset_id,
            merged_files=merged_files,
            files=file_dicts,
            conflicts=conflicts,
            scope_violations=scope_violations,
            integration_ref=integration_ref,
            events=events,
        )
        archive_path = self._archive_changeset(
            run,
            changeset_id,
            checkout,
            file_dicts,
            result,
            task_id=task_id,
            summary=summary,
            test_results=list(test_results or []),
            risks=list(risks or []),
        )
        result.archive_path = archive_path
        return result

    def sync_checkout(self, run: RunWorkspace, checkout: AgentCheckout) -> AgentCheckout:
        """Refresh a checkout from the latest integration state."""
        if checkout.checkout_dir.exists():
            framework_files = self._capture_checkout_framework_files(checkout.checkout_dir)
        else:
            framework_files = {}
        source = self._run_code_source(run)
        if self._run_code_mode(run) == "project_reference" and not checkout.write_scope:
            _clear_directory_contents(checkout.checkout_dir)
            _clear_directory_contents(checkout.base_dir)
        else:
            _copy_project_tree(source, checkout.checkout_dir, include_scopes=checkout.write_scope)
            _copy_project_tree(source, checkout.base_dir, include_scopes=checkout.write_scope)
        self._write_checkout_framework_files(checkout, framework_files)
        checkout.base_ref = f"int-{uuid.uuid4().hex[:12]}"
        data = checkout.to_dict()
        data["synced_at"] = _utc_now()
        _write_json(checkout.path / "checkout.json", data)
        self._record_workspace_event(
            run,
            "CheckoutSynced",
            {
                "agent_id": checkout.agent_id,
                "checkout_id": checkout.checkout_id,
                "base_ref": checkout.base_ref,
                "code_mode": self._run_code_mode(run),
                "code_source": str(source),
            },
        )
        return checkout

    def shared_access_context(self, run: RunWorkspace, *, agent_private_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Return the paths that define this run's collaboration workspace."""
        shared_dir = run.shared_dir or (run.path / "shared")
        return {
            "private_workspace": str(agent_private_dir) if agent_private_dir else None,
            "shared_workspace": str(shared_dir),
            "shared_code": str(run.integration_dir),
            "code_mode": self._run_code_mode(run),
            "project_code_root": str(self.project_root),
            "shared_artifacts": str(run.shared_artifacts_dir or (shared_dir / "artifacts")),
            "shared_reports": str(run.shared_reports_dir or (shared_dir / "reports")),
            "shared_manifest": str(shared_dir / "manifest.json"),
            "long_term_workspace": str(self.workspace_root),
        }

    def prepare_job(
        self,
        run: RunWorkspace,
        *,
        job_id: Optional[str] = None,
        write_scope: Optional[Sequence[str]] = None,
        artifact_scope: Optional[Sequence[str]] = None,
    ) -> JobWorkspace:
        job_id = job_id or f"job-{uuid.uuid4().hex[:12]}"
        job_path = run.jobs_dir / job_id
        worktree = job_path / "worktree"
        if job_path.exists():
            raise FileExistsError(f"job workspace already exists: {job_path}")
        self._validate_readonly_workspace_not_writable(
            [*(write_scope or []), *(artifact_scope or [])]
        )
        job_path.mkdir(parents=True)
        _copy_project_tree(run.base_dir, worktree)
        job = JobWorkspace(
            job_id=job_id,
            path=job_path,
            worktree_dir=worktree,
            base_dir=run.base_dir,
            write_scope=[str(s) for s in (write_scope or [])],
            artifact_scope=[str(s) for s in (artifact_scope or [])],
            readonly_shared_paths=[str(self.workspace_root)],
        )
        data = job.to_dict()
        data["created_at"] = _utc_now()
        _write_json(job_path / "job_manifest.json", data)
        return job

    def agent_access_context(self, job: JobWorkspace) -> Dict[str, Any]:
        """Return legacy job-worktree paths that may be exposed to an agent."""
        return {
            "writable_worktree": str(job.worktree_dir),
            "readonly_shared_workspaces": list(job.readonly_shared_paths),
            "write_scope": list(job.write_scope),
            "artifact_scope": list(job.artifact_scope),
        }

    def _shared_lock_name(self, rel_path: str) -> str:
        normalized = rel_path.replace("\\", "/").strip("/")
        safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in normalized)
        return safe or "root"

    def _shared_write_lock_path(self, run: RunWorkspace, rel_path: str) -> Path:
        shared_locks_dir = run.shared_locks_dir or ((run.shared_dir or run.path / "shared") / ".locks")
        return shared_locks_dir / f"{self._shared_lock_name(rel_path)}.write.lock"

    def _shared_readers_dir(self, run: RunWorkspace, rel_path: str) -> Path:
        shared_locks_dir = run.shared_locks_dir or ((run.shared_dir or run.path / "shared") / ".locks")
        return shared_locks_dir / f"{self._shared_lock_name(rel_path)}.readers"

    def _active_write_lock(self, lock_path: Path, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        now = time.time() if now is None else now
        if not lock_path.exists():
            return None
        data = _read_json(lock_path, {})
        expires_at = float(data.get("expires_at", 0.0))
        if expires_at > now:
            return data
        try:
            lock_path.unlink()
        except OSError:
            pass
        return None

    def _active_reader_locks(self, readers_dir: Path, now: Optional[float] = None) -> List[Dict[str, Any]]:
        now = time.time() if now is None else now
        if not readers_dir.is_dir():
            return []
        active: List[Dict[str, Any]] = []
        for lock_path in readers_dir.glob("*.read.lock"):
            data = _read_json(lock_path, {})
            expires_at = float(data.get("expires_at", 0.0))
            if expires_at > now:
                active.append(data)
                continue
            try:
                lock_path.unlink()
            except OSError:
                pass
        return active

    def _shared_target(self, run: RunWorkspace, rel_path: str) -> Path:
        shared_dir = run.shared_dir or (run.path / "shared")
        target = (shared_dir / rel_path).resolve()
        if not _path_within(target, shared_dir.resolve()):
            raise ValueError(f"shared path escapes run shared workspace: {rel_path}")
        if run.shared_locks_dir and _path_within(target, run.shared_locks_dir):
            raise ValueError("shared .locks directory is reserved")
        return target

    def acquire_shared_lease(
        self,
        run: RunWorkspace,
        rel_path: str,
        *,
        owner: str,
        ttl_sec: float = 300.0,
    ) -> SharedWriteLease:
        """Acquire an exclusive write lease for a shared workspace path."""
        shared_locks_dir = run.shared_locks_dir or ((run.shared_dir or run.path / "shared") / ".locks")
        shared_locks_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._shared_write_lock_path(run, rel_path)
        readers_dir = self._shared_readers_dir(run, rel_path)
        now = time.time()
        data = self._active_write_lock(lock_path, now)
        if data is not None:
            raise FileExistsError(
                f"shared path is write-locked by {data.get('owner')}: {rel_path}"
            )
        lease = SharedWriteLease(
            lease_id=f"lease-{uuid.uuid4().hex[:12]}",
            owner=str(owner),
            path=str(rel_path).replace("\\", "/").strip("/"),
            lock_path=lock_path,
            expires_at=now + float(ttl_sec),
        )
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(str(lock_path), flags)
        except FileExistsError as exc:
            raise FileExistsError(f"shared path is write-locked: {rel_path}") from exc
        try:
            payload = {**lease.to_dict(), "mode": "write"}
            os.write(fd, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
        finally:
            os.close(fd)
        active_readers = self._active_reader_locks(readers_dir, now)
        if active_readers:
            try:
                lock_path.unlink()
            except OSError:
                pass
            owners = ", ".join(str(item.get("owner")) for item in active_readers[:3])
            raise FileExistsError(f"shared path has active readers ({owners}): {rel_path}")
        self._record_shared_manifest(run, "lock_acquired", lease.to_dict())
        return lease

    def release_shared_lease(self, run: RunWorkspace, lease: SharedWriteLease) -> None:
        data = _read_json(lease.lock_path, {})
        if data.get("lease_id") == lease.lease_id:
            try:
                lease.lock_path.unlink()
            except OSError:
                pass
            self._record_shared_manifest(run, "lock_released", lease.to_dict())

    def acquire_shared_read_lease(
        self,
        run: RunWorkspace,
        rel_path: str,
        *,
        owner: str,
        ttl_sec: float = 300.0,
    ) -> SharedReadLease:
        """Acquire a shared read lease unless a writer owns the path."""
        shared_locks_dir = run.shared_locks_dir or ((run.shared_dir or run.path / "shared") / ".locks")
        shared_locks_dir.mkdir(parents=True, exist_ok=True)
        write_lock = self._shared_write_lock_path(run, rel_path)
        readers_dir = self._shared_readers_dir(run, rel_path)
        readers_dir.mkdir(parents=True, exist_ok=True)
        now = time.time()
        writer = self._active_write_lock(write_lock, now)
        if writer is not None:
            raise FileExistsError(
                f"shared path is write-locked by {writer.get('owner')}: {rel_path}"
            )
        lease = SharedReadLease(
            lease_id=f"lease-{uuid.uuid4().hex[:12]}",
            owner=str(owner),
            path=str(rel_path).replace("\\", "/").strip("/"),
            lock_path=readers_dir / f"lease-{uuid.uuid4().hex[:12]}.read.lock",
            expires_at=now + float(ttl_sec),
        )
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        fd = os.open(str(lease.lock_path), flags)
        try:
            os.write(fd, json.dumps(lease.to_dict(), ensure_ascii=False, indent=2).encode("utf-8"))
        finally:
            os.close(fd)
        writer = self._active_write_lock(write_lock)
        if writer is not None:
            try:
                lease.lock_path.unlink()
            except OSError:
                pass
            raise FileExistsError(
                f"shared path is write-locked by {writer.get('owner')}: {rel_path}"
            )
        self._record_shared_manifest(run, "lock_acquired", lease.to_dict())
        return lease

    def release_shared_read_lease(self, run: RunWorkspace, lease: SharedReadLease) -> None:
        data = _read_json(lease.lock_path, {})
        if data.get("lease_id") == lease.lease_id:
            try:
                lease.lock_path.unlink()
            except OSError:
                pass
            self._record_shared_manifest(run, "lock_released", lease.to_dict())

    def write_shared_text(
        self,
        run: RunWorkspace,
        rel_path: str,
        text: str,
        *,
        owner: str,
        lease: Optional[SharedWriteLease] = None,
        expected_version: Optional[int] = None,
    ) -> Path:
        """Write a text artifact to the shared workspace under a lease."""
        owned_lease = lease is None
        if lease is None:
            lease = self.acquire_shared_lease(run, rel_path, owner=owner)
        target = self._shared_target(run, rel_path)
        if lease.path != str(rel_path).replace("\\", "/").strip("/"):
            raise ValueError("lease path does not match write path")
        try:
            self._validate_shared_write_version(
                run,
                rel_path,
                owner=owner,
                expected_version=expected_version,
            )
        except Exception:
            if owned_lease:
                self.release_shared_lease(run, lease)
            raise
        tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(target)
            self._record_shared_manifest(
                run,
                "write",
                {
                    "owner": owner,
                    "path": str(rel_path).replace("\\", "/").strip("/"),
                    "lease_id": lease.lease_id,
                    "updated_at": _utc_now(),
                },
            )
            return target
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            if owned_lease:
                self.release_shared_lease(run, lease)

    def write_shared_bytes(
        self,
        run: RunWorkspace,
        rel_path: str,
        data: bytes,
        *,
        owner: str,
        lease: Optional[SharedWriteLease] = None,
        expected_version: Optional[int] = None,
    ) -> Path:
        """Write binary data to the shared workspace under a lease."""
        owned_lease = lease is None
        if lease is None:
            lease = self.acquire_shared_lease(run, rel_path, owner=owner)
        target = self._shared_target(run, rel_path)
        if lease.path != str(rel_path).replace("\\", "/").strip("/"):
            raise ValueError("lease path does not match write path")
        try:
            self._validate_shared_write_version(
                run,
                rel_path,
                owner=owner,
                expected_version=expected_version,
            )
        except Exception:
            if owned_lease:
                self.release_shared_lease(run, lease)
            raise
        tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(data)
            tmp.replace(target)
            self._record_shared_manifest(
                run,
                "write",
                {
                    "owner": owner,
                    "path": str(rel_path).replace("\\", "/").strip("/"),
                    "lease_id": lease.lease_id,
                    "bytes": len(data),
                    "updated_at": _utc_now(),
                },
            )
            return target
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            if owned_lease:
                self.release_shared_lease(run, lease)

    def read_shared_text(
        self,
        run: RunWorkspace,
        rel_path: str,
        *,
        owner: str = "framework",
        lease: Optional[SharedReadLease] = None,
    ) -> str:
        """Read a UTF-8 text file from the shared workspace."""
        owned_lease = lease is None
        if lease is None:
            lease = self.acquire_shared_read_lease(run, rel_path, owner=owner)
        target = self._shared_target(run, rel_path)
        try:
            if not target.is_file():
                raise FileNotFoundError(f"shared text file not found: {rel_path}")
            return target.read_text(encoding="utf-8")
        finally:
            if owned_lease:
                self.release_shared_read_lease(run, lease)

    def shared_file_version(self, run: RunWorkspace, rel_path: str) -> int:
        """Return the manifest write version for a shared workspace path."""
        shared_dir = run.shared_dir or (run.path / "shared")
        manifest_path = shared_dir / "manifest.json"
        normalized = str(rel_path).replace("\\", "/").strip("/")
        data = _read_json(manifest_path, {})
        writes = data.get("writes", [])
        if not isinstance(writes, list):
            return 0
        return sum(
            1
            for item in writes
            if isinstance(item, dict)
            and item.get("event_type") == "write"
            and item.get("path") == normalized
        )

    def _latest_shared_write(self, run: RunWorkspace, rel_path: str) -> Optional[Dict[str, Any]]:
        shared_dir = run.shared_dir or (run.path / "shared")
        manifest_path = shared_dir / "manifest.json"
        normalized = str(rel_path).replace("\\", "/").strip("/")
        data = _read_json(manifest_path, {})
        writes = data.get("writes", [])
        if not isinstance(writes, list):
            return None
        for item in reversed(writes):
            if (
                isinstance(item, dict)
                and item.get("event_type") == "write"
                and item.get("path") == normalized
            ):
                return item
        return None

    def _validate_shared_write_version(
        self,
        run: RunWorkspace,
        rel_path: str,
        *,
        owner: str,
        expected_version: Optional[int],
    ) -> None:
        current_version = self.shared_file_version(run, rel_path)
        if expected_version is not None:
            if current_version != int(expected_version):
                raise FileExistsError(
                    f"shared path version conflict: expected {expected_version}, got {current_version}: {rel_path}"
                )
            return
        if current_version <= 0:
            return
        latest = self._latest_shared_write(run, rel_path)
        latest_owner = str(latest.get("owner") or "") if latest else ""
        if latest_owner and latest_owner != str(owner):
            raise FileExistsError(
                "shared path version conflict: "
                f"{rel_path} already has version {current_version} from {latest_owner}; "
                f"pass expected_version={current_version} after reading the current shared file/manifest "
                "or publish to an agent-specific path"
            )

    def list_shared_files(self, run: RunWorkspace, rel_dir: str = "") -> List[str]:
        """List files under a shared workspace subdirectory."""
        root = self._shared_target(run, rel_dir or ".")
        if not root.exists():
            return []
        if root.is_file():
            return [str(rel_dir).replace("\\", "/").strip("/")]
        shared_dir = run.shared_dir or (run.path / "shared")
        files: List[str] = []
        for path in sorted(root.rglob("*")):
            if path.is_file():
                files.append(path.resolve().relative_to(shared_dir.resolve()).as_posix())
        return files
    def _record_shared_manifest(self, run: RunWorkspace, event_type: str, payload: Dict[str, Any]) -> None:
        shared_dir = run.shared_dir or (run.path / "shared")
        manifest_path = shared_dir / "manifest.json"
        data = _read_json(
            manifest_path,
            {"run_id": run.run_id, "created_at": _utc_now(), "writes": [], "locks": []},
        )
        record = {"event_type": event_type, **payload}
        if event_type.startswith("lock"):
            data.setdefault("locks", []).append(record)
        else:
            data.setdefault("writes", []).append(record)
        data["updated_at"] = _utc_now()
        _write_json(manifest_path, data)

    def discard_private_workspaces(self, run: RunWorkspace) -> None:
        if run.agents_dir.exists():
            shutil.rmtree(run.agents_dir)
        run.agents_dir.mkdir(parents=True, exist_ok=True)

    def is_agent_path_writable(self, job: JobWorkspace, path: Path) -> bool:
        """Policy helper for future tool/sandbox integrations."""
        resolved = Path(path).resolve()
        if not _path_within(resolved, job.worktree_dir):
            return False
        rel = resolved.relative_to(job.worktree_dir.resolve()).as_posix()
        return _scope_allows(rel, [*job.write_scope, *job.artifact_scope])

    def diff_job(self, job: JobWorkspace) -> List[FileChange]:
        return self._diff_dirs(job.base_dir, job.worktree_dir)

    def validate_job_scope(self, job: JobWorkspace) -> List[str]:
        changed = self.diff_job(job)
        allowed_scopes = [*job.write_scope, *job.artifact_scope]
        return [
            change.path
            for change in changed
            if not _scope_allows(change.path, allowed_scopes)
        ]

    def merge_job(self, run: RunWorkspace, job: JobWorkspace) -> MergeResult:
        changes = self.diff_job(job)
        scope_violations = self.validate_job_scope(job)
        if scope_violations:
            result = MergeResult(ok=False, scope_violations=scope_violations)
            self._record_job_merge(job, result)
            return result

        merged: List[str] = []
        conflicts: List[str] = []
        for change in changes:
            rel = Path(change.path)
            base_file = run.base_dir / rel
            current_file = run.integration_dir / rel
            job_file = job.worktree_dir / rel

            if change.status == "deleted":
                ok = self._merge_delete(base_file, current_file, job_file)
            elif change.status == "added":
                ok = self._merge_add(base_file, current_file, job_file)
            else:
                ok = self._merge_modify(base_file, current_file, job_file)

            if ok:
                merged.append(change.path)
            else:
                conflicts.append(change.path)

        result = MergeResult(
            ok=not conflicts,
            merged_files=merged,
            conflicts=conflicts,
        )
        self._record_job_merge(job, result)
        return result

    def archive_run(self, run: RunWorkspace, *, status: str = "completed") -> Path:
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError("archive status must be completed, failed, or cancelled")
        manifest_path = run.path / "run_manifest.json"
        data = _read_json(manifest_path, {})
        data["status"] = status
        data["archived_at"] = _utc_now()
        _write_json(manifest_path, data)
        self.discard_private_workspaces(run)
        self.archive_run_shared_workspace(run, status=status)

        target_parent = self.workspace_root / "runs" / (
            "archived" if status == "completed" else "failed"
        )
        target_parent.mkdir(parents=True, exist_ok=True)
        target = target_parent / run.run_id
        if target.exists():
            raise FileExistsError(f"archive target already exists: {target}")
        setattr(run, "_pre_archive_path", run.path)
        shutil.move(str(run.path), str(target))
        run.path = target
        run.base_dir = target / "base"
        run.integration_dir = target / "shared" / "code"
        run.jobs_dir = target / "jobs"
        run.agents_dir = target / "agents"
        run.shared_dir = target / "shared"
        run.shared_code_dir = target / "shared" / "code"
        run.shared_artifacts_dir = target / "shared" / "artifacts"
        run.shared_reports_dir = target / "shared" / "reports"
        run.shared_locks_dir = target / "shared" / ".locks"
        run.status = status
        return target

    def archive_run_shared_workspace(self, run: RunWorkspace, *, status: str = "completed") -> Path:
        """Compress the temporary shared workspace into the long-term archive area."""
        shared_dir = run.shared_dir or (run.path / "shared")
        if not shared_dir.is_dir():
            raise FileNotFoundError(f"run shared workspace not found: {shared_dir}")
        archives_dir = self.workspace_root / "shared" / "archives"
        archives_dir.mkdir(parents=True, exist_ok=True)
        archive_id = f"{run.run_id}-{status}"
        zip_path = archives_dir / f"{archive_id}.zip"
        if zip_path.exists():
            archive_id = f"{archive_id}-{uuid.uuid4().hex[:8]}"
            zip_path = archives_dir / f"{archive_id}.zip"

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(shared_dir.rglob("*")):
                if path.is_file():
                    zf.write(path, path.resolve().relative_to(shared_dir.resolve()).as_posix())

        manifest_path = archives_dir / "manifest.json"
        manifest = _read_json(manifest_path, {"archives": []})
        archives = manifest.setdefault("archives", [])
        if not isinstance(archives, list):
            archives = []
            manifest["archives"] = archives
        archives.append(
            {
                "archive_id": archive_id,
                "run_id": run.run_id,
                "status": status,
                "path": str(zip_path),
                "bytes": zip_path.stat().st_size,
                "created_at": _utc_now(),
                "format": "zip",
                "root": "shared",
            }
        )
        manifest["updated_at"] = _utc_now()
        _write_json(manifest_path, manifest)
        return zip_path

    def list_long_term_archives(self) -> List[Dict[str, Any]]:
        archives_dir = self.workspace_root / "shared" / "archives"
        manifest = _read_json(archives_dir / "manifest.json", {"archives": []})
        items = manifest.get("archives", [])
        if not isinstance(items, list):
            return []
        return [dict(item) for item in items if isinstance(item, dict)]

    def extract_long_term_archive(
        self,
        run: RunWorkspace,
        agent_id: str,
        archive_id: str,
        *,
        path: str = "",
    ) -> Path:
        """Extract a long-term run archive into an agent private read workspace."""
        safe_id = _safe_archive_id(archive_id)
        archive_path = self.workspace_root / "shared" / "archives" / f"{safe_id}.zip"
        if not archive_path.is_file():
            raise FileNotFoundError(f"long-term archive not found: {safe_id}")

        normalized = str(path or "").replace("\\", "/").strip("/")
        if normalized:
            parts = normalized.split("/")
            if any(part in {"", ".", ".."} for part in parts) or ":" in normalized:
                raise ValueError("archive path must be relative")

        private = self.agent_workspace_dir(run, agent_id)
        extract_root = private / "extracted_archives" / safe_id
        if extract_root.exists():
            shutil.rmtree(extract_root)
        extract_root.mkdir(parents=True)

        with zipfile.ZipFile(archive_path, "r") as zf:
            for info in zf.infolist():
                name = info.filename.replace("\\", "/").strip("/")
                if not name or name.endswith("/"):
                    continue
                parts = name.split("/")
                if any(part in {"", ".", ".."} for part in parts) or ":" in name:
                    raise ValueError(f"unsafe archive member path: {info.filename}")
                if normalized and name != normalized and not name.startswith(f"{normalized}/"):
                    continue
                target = extract_root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

        return extract_root / normalized if normalized else extract_root

    def _diff_dirs(self, left: Path, right: Path, *, include_patch: bool = False) -> List[FileChange]:
        left_files = _relative_files(left)
        right_files = _relative_files(right)
        changes: List[FileChange] = []
        for rel in sorted(set(left_files) | set(right_files)):
            if rel not in left_files:
                status = "added"
            elif rel not in right_files:
                status = "deleted"
            elif not filecmp.cmp(left_files[rel], right_files[rel], shallow=False):
                status = "modified"
            else:
                continue
            base_file = left / rel
            new_file = right / rel
            binary = _diff_is_binary(base_file, new_file)
            patch = _unified_diff(base_file, new_file, rel) if include_patch and not binary else ""
            additions, deletions = _count_patch_lines(patch)
            changes.append(
                FileChange(
                    rel,
                    status,
                    additions=additions,
                    deletions=deletions,
                    base_hash=_sha256_file(base_file),
                    new_hash=_sha256_file(new_file),
                    patch=patch,
                    binary=binary,
                )
            )
        return changes

    def _blueprint_changeset_from_archive(
        self,
        run: RunWorkspace,
        root: Path,
        changeset: Dict[str, Any],
        submit_result: Dict[str, Any],
        *,
        patch_exists: bool,
    ) -> BlueprintChangesetDetail:
        changeset_id = str(
            submit_result.get("changeset_id")
            or changeset.get("changeset_id")
            or root.name
        )
        status = str(submit_result.get("status") or changeset.get("status") or "pending").strip().lower()
        if status not in {"accepted", "conflict", "rejected", "pending", "failed"}:
            status = "failed" if status in {"error", "errored"} else "pending"
        raw_files = changeset.get("files", [])
        if not isinstance(raw_files, list):
            raw_files = []

        diffs: List[Dict[str, Any]] = []
        binary_files: List[Dict[str, Any]] = []
        file_paths: List[str] = []
        additions = 0
        deletions = 0

        for raw in raw_files:
            if not isinstance(raw, dict):
                continue
            path = str(raw.get("path") or "").replace("\\", "/").strip("/")
            if not path:
                continue
            file_paths.append(path)
            file_additions = int(raw.get("additions") or 0)
            file_deletions = int(raw.get("deletions") or 0)
            additions += file_additions
            deletions += file_deletions
            patch = raw.get("patch")
            patch_text = patch if isinstance(patch, str) else ""
            binary = bool(raw.get("binary")) or (not patch_text and not bool(raw.get("has_patch")))
            if patch_text:
                diffs.append(
                    {
                        "file": path,
                        "patch": patch_text,
                        "additions": file_additions,
                        "deletions": file_deletions,
                        "status": str(raw.get("status") or "modified"),
                    }
                )
            elif binary:
                binary_files.append(
                    {
                        "changesetId": changeset_id,
                        "file": path,
                        "path": path,
                        "status": str(raw.get("status") or "modified"),
                        "additions": file_additions,
                        "deletions": file_deletions,
                        "baseHash": raw.get("base_hash"),
                        "newHash": raw.get("new_hash"),
                    }
                )

        metadata = {
            "changesetId": changeset_id,
            "changeset_id": changeset_id,
            "runId": str(changeset.get("run_id") or run.run_id),
            "agentId": changeset.get("agent_id"),
            "agent_id": changeset.get("agent_id"),
            "taskId": changeset.get("task_id"),
            "task_id": changeset.get("task_id"),
            "summary": changeset.get("summary") or submit_result.get("summary") or "",
            "status": status,
            "path": root.name,
            "absolutePath": str(root.resolve()),
            "fileCount": len(file_paths),
            "textFileCount": len(diffs),
            "binaryFileCount": len(binary_files),
            "additions": additions,
            "deletions": deletions,
            "files": file_paths,
            "createdAt": changeset.get("created_at"),
            "created_at": changeset.get("created_at"),
            "patchExists": patch_exists,
            "hasDetail": patch_exists,
        }
        if submit_result.get("integration_ref") is not None:
            metadata["integrationRef"] = submit_result["integration_ref"]
            metadata["integration_ref"] = submit_result["integration_ref"]
        if submit_result.get("conflicts"):
            metadata["conflicts"] = submit_result.get("conflicts")
        if submit_result.get("scope_violations"):
            metadata["scopeViolations"] = submit_result.get("scope_violations")
            metadata["scope_violations"] = submit_result.get("scope_violations")
        return BlueprintChangesetDetail(
            run_id=run.run_id,
            changeset_id=changeset_id,
            status=status,
            diffs=diffs,
            binary_files=binary_files,
            metadata={key: value for key, value in metadata.items() if value is not None},
        )

    def _plan_checkout_change(
        self,
        run: RunWorkspace,
        checkout: AgentCheckout,
        change: FileChange,
    ) -> tuple[bool, Optional[bytes], Optional[Dict[str, Any]]]:
        rel = Path(change.path)
        base_file = checkout.base_dir / rel
        current_file = self._run_code_target(run) / rel
        checkout_file = checkout.checkout_dir / rel

        def conflict(reason: str, *, merge_preview: str = "", hint: str = "") -> Dict[str, Any]:
            data: Dict[str, Any] = {
                "path": change.path,
                "reason": reason,
                "base_hash": _sha256_file(base_file),
                "current_hash": _sha256_file(current_file),
                "agent_hash": _sha256_file(checkout_file),
            }
            if merge_preview:
                data["merge_preview"] = merge_preview
            if hint:
                data["hint"] = hint
            return data

        if change.status == "deleted":
            if not current_file.exists():
                return True, None, None
            if base_file.exists() and filecmp.cmp(base_file, current_file, shallow=False):
                return True, None, None
            return False, None, conflict("delete_modify", hint="Current integration changed this file after the checkout base.")

        if change.status == "added":
            if not checkout_file.exists():
                return True, None, None
            if current_file.exists():
                if filecmp.cmp(current_file, checkout_file, shallow=False):
                    return True, checkout_file.read_bytes(), None
                return False, None, conflict("add_add", hint="Another changeset already added this path differently.")
            return True, checkout_file.read_bytes(), None

        if not base_file.exists():
            return self._plan_checkout_change(run, checkout, FileChange(change.path, "added"))
        if not current_file.exists():
            return False, None, conflict("modify_deleted", hint="Current integration deleted this file.")
        if not checkout_file.exists():
            return self._plan_checkout_change(run, checkout, FileChange(change.path, "deleted"))
        if filecmp.cmp(current_file, checkout_file, shallow=False):
            return True, checkout_file.read_bytes(), None
        if filecmp.cmp(base_file, current_file, shallow=False):
            return True, checkout_file.read_bytes(), None
        if filecmp.cmp(base_file, checkout_file, shallow=False):
            return True, current_file.read_bytes(), None
        if _is_binary(base_file) or _is_binary(current_file) or _is_binary(checkout_file):
            return False, None, conflict("binary_conflict", hint="Binary files changed on both sides.")

        ok, merged = _merge_text(
            _read_text(base_file),
            _read_text(current_file),
            _read_text(checkout_file),
        )
        if ok:
            return True, merged.encode("utf-8"), None
        return False, None, conflict(
            "stale_base",
            merge_preview=merged,
            hint="Both changes modify the same text region.",
        )

    def _apply_checkout_change(
        self,
        run: RunWorkspace,
        change: FileChange,
        merged_bytes: Optional[bytes],
    ) -> None:
        rel = Path(change.path)
        target = self._run_code_target(run) / rel
        if merged_bytes is None:
            if target.exists():
                target.unlink()
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(merged_bytes)

    def _record_workspace_event(self, run: RunWorkspace, event_type: str, payload: Dict[str, Any]) -> None:
        self._record_shared_manifest(
            run,
            "workspace_event",
            {
                "workspace_event": event_type,
                **payload,
                "updated_at": _utc_now(),
            },
        )

    def _record_conflict(
        self,
        run: RunWorkspace,
        changeset_id: str,
        checkout: AgentCheckout,
        conflicts: List[Dict[str, Any]],
    ) -> Path:
        conflict_id = f"cf-{uuid.uuid4().hex[:12]}"
        path = run.path / "conflicts" / conflict_id / "conflict.json"
        _write_json(
            path,
            {
                "conflict_id": conflict_id,
                "changeset_id": changeset_id,
                "run_id": run.run_id,
                "agent_id": checkout.agent_id,
                "files": conflicts,
                "created_at": _utc_now(),
            },
        )
        return path

    def _archive_changeset(
        self,
        run: RunWorkspace,
        changeset_id: str,
        checkout: AgentCheckout,
        files: List[Dict[str, Any]],
        result: ChangesetSubmitResult,
        *,
        task_id: Optional[str],
        summary: str,
        test_results: List[Dict[str, Any]],
        risks: List[str],
    ) -> Path:
        root = run.path / "changesets" / changeset_id
        root.mkdir(parents=True, exist_ok=True)
        patch_text = "\n".join(str(item.get("patch") or "") for item in files if item.get("patch"))
        (root / "patch.diff").write_text(patch_text, encoding="utf-8")
        _write_json(
            root / "changeset.json",
            {
                "changeset_id": changeset_id,
                "run_id": run.run_id,
                "agent_id": checkout.agent_id,
                "task_id": task_id,
                "base_ref": checkout.base_ref,
                "files": files,
                "summary": summary,
                "test_results": test_results,
                "risks": risks,
                "created_at": _utc_now(),
            },
        )
        _write_json(root / "submit_result.json", result.to_dict())
        return root

    def _merge_add(self, base_file: Path, current_file: Path, job_file: Path) -> bool:
        if current_file.exists():
            if filecmp.cmp(current_file, job_file, shallow=False):
                return True
            return False
        current_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(job_file, current_file)
        return True

    def _merge_delete(self, base_file: Path, current_file: Path, job_file: Path) -> bool:
        if not current_file.exists():
            return True
        if base_file.exists() and filecmp.cmp(base_file, current_file, shallow=False):
            current_file.unlink()
            return True
        return False

    def _merge_modify(self, base_file: Path, current_file: Path, job_file: Path) -> bool:
        if not base_file.exists():
            return self._merge_add(base_file, current_file, job_file)
        if not current_file.exists():
            return False
        if filecmp.cmp(current_file, job_file, shallow=False):
            return True
        if filecmp.cmp(base_file, current_file, shallow=False):
            current_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(job_file, current_file)
            return True
        if filecmp.cmp(base_file, job_file, shallow=False):
            return True
        if _is_binary(base_file) or _is_binary(current_file) or _is_binary(job_file):
            return False

        ok, merged = _merge_text(
            _read_text(base_file),
            _read_text(current_file),
            _read_text(job_file),
        )
        _write_text(current_file, merged)
        return ok

    def _record_job_merge(self, job: JobWorkspace, result: MergeResult) -> None:
        manifest_path = job.path / "job_manifest.json"
        data = _read_json(manifest_path, {})
        data["status"] = "merged" if result.ok else "conflict"
        data["merge_result"] = result.to_dict()
        data["updated_at"] = _utc_now()
        _write_json(manifest_path, data)

    def _validate_readonly_workspace_not_writable(self, scopes: Sequence[str]) -> None:
        rel_workspace: Optional[str] = None
        if _path_within(self.workspace_root, self.project_root):
            rel_workspace = self.workspace_root.relative_to(self.project_root).as_posix()
        violations: List[str] = []
        for raw in scopes:
            scope = str(raw).strip()
            if not scope:
                continue
            path = Path(scope)
            if path.is_absolute():
                resolved = path.resolve()
                if resolved == self.workspace_root or _path_within(resolved, self.workspace_root):
                    violations.append(scope)
                continue
            normalized = scope.replace("\\", "/").rstrip("*").rstrip("/")
            if rel_workspace and (
                normalized == rel_workspace
                or normalized.startswith(f"{rel_workspace}/")
                or rel_workspace.startswith(f"{normalized}/")
            ):
                violations.append(scope)
        if violations:
            raise ValueError(
                "long-term shared workspace is read-only for agents: "
                + ", ".join(violations)
            )

def describe_dulwich_backend() -> Dict[str, Any]:
    """Return runtime information for diagnostics and tests."""
    return {
        "backend": "dulwich",
        "version": None if not _DULWICH_AVAILABLE else __import__("dulwich").__version__,  # type: ignore[attr-defined]
        "uses_git_cli": False,
        "available": _DULWICH_AVAILABLE,
        "merge3_available": importlib.util.find_spec("merge3") is not None,
    }
