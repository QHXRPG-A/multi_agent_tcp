from __future__ import annotations

import json
from pathlib import Path

from multi_agent_tcp import DulwichWorkspaceManager, describe_dulwich_backend


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_dulwich_backend_is_vendored() -> None:
    info = describe_dulwich_backend()

    assert info["backend"] == "dulwich"
    assert info["uses_git_cli"] is False
    assert info["version"] is not None


def test_workspace_lifecycle_archives_full_run_directory(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path, workspace_id="proj")

    run = manager.create_run(run_id="run-1")
    job = manager.prepare_job(run, job_id="job-1", write_scope=["src/**"])
    _write(job.worktree_dir / "src" / "a.txt", "job\n")

    result = manager.merge_job(run, job)
    archive = manager.archive_run(run)

    assert result.ok is True
    assert (archive / "base" / "src" / "a.txt").read_text(encoding="utf-8") == "base\n"
    assert (archive / "integration" / "src" / "a.txt").read_text(encoding="utf-8") == "job\n"
    assert (archive / "jobs" / "job-1" / "worktree" / "src" / "a.txt").read_text(encoding="utf-8") == "job\n"
    assert not (tmp_path / ".multi_agent_workspace" / "runs" / "active" / "run-1").exists()


def test_custom_long_term_workspace_inside_project_is_readonly_and_not_snapshotted(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    _write(tmp_path / ".agent_shared" / "notes.md", "shared notes\n")

    manager = DulwichWorkspaceManager.open_or_init(
        tmp_path,
        workspace_root=tmp_path / ".agent_shared",
        workspace_id="proj",
    )
    run = manager.create_run(run_id="run-1")
    job = manager.prepare_job(run, job_id="job-1", write_scope=["src/**"])

    context = manager.agent_access_context(job)

    assert manager.workspace_root == (tmp_path / ".agent_shared").resolve()
    assert not (run.base_dir / ".agent_shared" / "notes.md").exists()
    assert context["readonly_shared_workspaces"] == [str((tmp_path / ".agent_shared").resolve())]
    assert manager.is_agent_path_writable(job, job.worktree_dir / "src" / "a.txt") is True
    assert manager.is_agent_path_writable(job, tmp_path / ".agent_shared" / "notes.md") is False


def test_custom_long_term_workspace_outside_project_is_allowed(tmp_path: Path) -> None:
    project = tmp_path / "project"
    shared = tmp_path / "shared-workspace"
    _write(project / "src" / "a.txt", "base\n")

    manager = DulwichWorkspaceManager.open_or_init(project, workspace_root=shared)
    run = manager.create_run(run_id="run-1")

    assert manager.workspace_root == shared.resolve()
    assert (shared / "workspace.json").is_file()
    assert (run.base_dir / "src" / "a.txt").is_file()


def test_prepare_job_rejects_writable_scope_inside_long_term_workspace(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(
        tmp_path,
        workspace_root=tmp_path / ".agent_shared",
    )
    run = manager.create_run(run_id="run-1")

    try:
        manager.prepare_job(run, job_id="job-1", write_scope=[".agent_shared/**"])
    except ValueError as exc:
        assert "read-only" in str(exc)
    else:
        raise AssertionError("expected readonly workspace scope to be rejected")


def test_job_diff_and_scope_violation(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "allowed.txt", "base\n")
    _write(tmp_path / "secret.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-1")
    job = manager.prepare_job(run, job_id="job-1", write_scope=["src/**"])

    _write(job.worktree_dir / "src" / "allowed.txt", "changed\n")
    _write(job.worktree_dir / "secret.txt", "changed\n")

    changes = manager.diff_job(job)
    result = manager.merge_job(run, job)

    assert {change.path for change in changes} == {"secret.txt", "src/allowed.txt"}
    assert result.ok is False
    assert result.scope_violations == ["secret.txt"]


def test_disjoint_job_merges_do_not_conflict(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "a0\n")
    _write(tmp_path / "src" / "b.txt", "b0\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-1")
    job_a = manager.prepare_job(run, job_id="job-a", write_scope=["src/**"])
    job_b = manager.prepare_job(run, job_id="job-b", write_scope=["src/**"])

    _write(job_a.worktree_dir / "src" / "a.txt", "a1\n")
    _write(job_b.worktree_dir / "src" / "b.txt", "b1\n")

    assert manager.merge_job(run, job_a).ok is True
    assert manager.merge_job(run, job_b).ok is True
    assert (run.integration_dir / "src" / "a.txt").read_text(encoding="utf-8") == "a1\n"
    assert (run.integration_dir / "src" / "b.txt").read_text(encoding="utf-8") == "b1\n"


def test_same_file_conflict_is_detected(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-1")
    job_a = manager.prepare_job(run, job_id="job-a", write_scope=["src/**"])
    job_b = manager.prepare_job(run, job_id="job-b", write_scope=["src/**"])

    _write(job_a.worktree_dir / "src" / "a.txt", "from a\n")
    _write(job_b.worktree_dir / "src" / "a.txt", "from b\n")

    assert manager.merge_job(run, job_a).ok is True
    result_b = manager.merge_job(run, job_b)

    assert result_b.ok is False
    assert result_b.conflicts == ["src/a.txt"]
    content = (run.integration_dir / "src" / "a.txt").read_text(encoding="utf-8")
    assert "<<<<<<< CURRENT" in content
    assert ">>>>>>> JOB" in content


def test_archive_failed_run_goes_to_failed_directory(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-1")

    archive = manager.archive_run(run, status="failed")
    manifest = json.loads((archive / "run_manifest.json").read_text(encoding="utf-8"))

    assert archive.parent.name == "failed"
    assert manifest["status"] == "failed"
