"""Shared workspace lifecycle, isolation, diff, and merge primitives.

This module uses the vendored Dulwich checkout for Git repository detection
and future Git-object integration, but intentionally keeps the first merge
backend file-oriented and local. The runtime never shells out to git or svn.
"""

from __future__ import annotations

import filecmp
import fnmatch
import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .dulwich_vendor import ensure_dulwich_path, has_dulwich_vendor

_DULWICH_AVAILABLE = False
if has_dulwich_vendor():
    ensure_dulwich_path()
    try:
        from dulwich.repo import NotGitRepository, Repo  # type: ignore  # noqa: E402

        _DULWICH_AVAILABLE = True
    except Exception:  # pragma: no cover - fallback when vendored checkout is absent
        NotGitRepository = Exception  # type: ignore[assignment]
        Repo = None  # type: ignore[assignment]
else:
    NotGitRepository = Exception  # type: ignore[assignment]
    Repo = None  # type: ignore[assignment]


WORKSPACE_DIRNAME = ".multi_agent_workspace"
MANIFEST_NAME = "workspace.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.is_file():
        return dict(default)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
) -> Dict[str, Path]:
    root = root.resolve()
    excluded = [Path(p).resolve() for p in (excluded_roots or [])]
    out: Dict[str, Path] = {}
    if not root.is_dir():
        return out
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if any(resolved == ex or _path_within(resolved, ex) for ex in excluded):
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(f"{WORKSPACE_DIRNAME}/"):
            continue
        if "/.git/" in f"/{rel}/" or rel == ".git":
            continue
        out[rel] = path
    return out


def _copy_project_tree(
    src: Path,
    dst: Path,
    *,
    excluded_roots: Optional[Sequence[Path]] = None,
) -> None:
    src = Path(src).resolve()
    excluded = [Path(p).resolve() for p in (excluded_roots or [])]

    def ignore(dir_path: str, names: List[str]) -> set[str]:
        ignored: set[str] = set()
        base = Path(dir_path).resolve()
        pattern_ignore = shutil.ignore_patterns(
            ".git",
            WORKSPACE_DIRNAME,
            "__pycache__",
            ".pytest_cache",
            "*.pyc",
        )
        ignored.update(pattern_ignore(dir_path, names))
        for name in names:
            child = (base / name).resolve()
            if any(child == ex or _path_within(child, ex) for ex in excluded):
                ignored.add(name)
        return ignored

    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=ignore)


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


def _merge_text(base: str, current: str, job: str) -> tuple[bool, str]:
    """Small deterministic three-way merge for text files.

    This handles the reliable common cases first. When both current and job
    diverge differently from base, it returns conflict markers instead of
    trying to be clever.
    """
    if current == job:
        return True, current
    if current == base:
        return True, job
    if job == base:
        return True, current
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

    def to_dict(self) -> Dict[str, str]:
        return {"path": self.path, "status": self.status}


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

    def create_run(self, *, run_id: Optional[str] = None) -> RunWorkspace:
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
        _copy_project_tree(
            self.project_root,
            base_dir,
            excluded_roots=[self.workspace_root],
        )
        _copy_project_tree(base_dir, integration_dir)
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
        )

    def open_run(self, run_id: str) -> RunWorkspace:
        run_path = self.workspace_root / "runs" / "active" / run_id
        if not run_path.is_dir():
            raise FileNotFoundError(f"active run not found: {run_path}")
        return RunWorkspace(
            run_id=run_id,
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
            status=_read_json(run_path / "run_manifest.json", {}).get("status", "running"),
            long_term_workspace_root=self.workspace_root,
        )

    def agent_workspace_dir(self, run: RunWorkspace, agent_id: str) -> Path:
        """Return the per-agent private scratch directory for this run.

        This directory is intentionally not an outcome worktree. It is for
        cache, temporary files, authorized skill views, and CLI-local state.
        It is discarded before the run is archived.
        """
        safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in agent_id)
        if not safe:
            raise ValueError("agent_id must not be empty")
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

    def shared_access_context(self, run: RunWorkspace, *, agent_private_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Return the paths that define this run's collaboration workspace."""
        shared_dir = run.shared_dir or (run.path / "shared")
        return {
            "private_workspace": str(agent_private_dir) if agent_private_dir else None,
            "shared_workspace": str(shared_dir),
            "shared_code": str(run.integration_dir),
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
        if expected_version is not None:
            current_version = self.shared_file_version(run, rel_path)
            if current_version != int(expected_version):
                if owned_lease:
                    self.release_shared_lease(run, lease)
                raise FileExistsError(
                    f"shared path version conflict: expected {expected_version}, got {current_version}: {rel_path}"
                )
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
        if expected_version is not None:
            current_version = self.shared_file_version(run, rel_path)
            if current_version != int(expected_version):
                if owned_lease:
                    self.release_shared_lease(run, lease)
                raise FileExistsError(
                    f"shared path version conflict: expected {expected_version}, got {current_version}: {rel_path}"
                )
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

        target_parent = self.workspace_root / "runs" / (
            "archived" if status == "completed" else "failed"
        )
        target_parent.mkdir(parents=True, exist_ok=True)
        target = target_parent / run.run_id
        if target.exists():
            raise FileExistsError(f"archive target already exists: {target}")
        shutil.move(str(run.path), str(target))
        return target

    def _diff_dirs(self, left: Path, right: Path) -> List[FileChange]:
        left_files = _relative_files(left)
        right_files = _relative_files(right)
        changes: List[FileChange] = []
        for rel in sorted(set(left_files) | set(right_files)):
            if rel not in left_files:
                changes.append(FileChange(rel, "added"))
            elif rel not in right_files:
                changes.append(FileChange(rel, "deleted"))
            elif not filecmp.cmp(left_files[rel], right_files[rel], shallow=False):
                changes.append(FileChange(rel, "modified"))
        return changes

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
    }
