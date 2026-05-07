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
    assert "available" in info
    assert "merge3_available" in info


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
    assert (archive / "shared" / "code" / "src" / "a.txt").read_text(encoding="utf-8") == "job\n"
    assert (archive / "jobs" / "job-1" / "worktree" / "src" / "a.txt").read_text(encoding="utf-8") == "job\n"
    assert (manager.workspace_root / "shared" / "archives" / "run-1-completed.zip").is_file()
    archives = manager.list_long_term_archives()
    assert archives[0]["archive_id"] == "run-1-completed"
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


def test_run_has_private_scratch_and_shared_outcome_space(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-1")
    private = manager.agent_workspace_dir(run, "agent-a")
    _write(private / "scratch.txt", "private temp\n")
    manager.write_shared_text(
        run,
        "reports/result.md",
        "shared result\n",
        owner="agent-a",
    )

    archive = manager.archive_run(run)

    assert (archive / "shared" / "code" / "src" / "a.txt").is_file()
    assert (archive / "shared" / "reports" / "result.md").read_text(encoding="utf-8") == "shared result\n"
    assert not (archive / "agents" / "agent-a" / "private" / "scratch.txt").exists()


def test_long_term_archive_extracts_into_agent_private_workspace(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    old_run = manager.create_run(run_id="run-old")
    manager.write_shared_text(old_run, "reports/result.md", "shared result\n", owner="framework")
    manager.archive_run(old_run)

    run = manager.create_run(run_id="run-new")
    extracted = manager.extract_long_term_archive(
        run,
        "agent-a",
        "run-old-completed",
        path="reports",
    )

    private = manager.agent_workspace_dir(run, "agent-a")
    assert extracted == private / "extracted_archives" / "run-old-completed" / "reports"
    assert (extracted / "result.md").read_text(encoding="utf-8") == "shared result\n"
    assert not (manager.workspace_root / "shared" / "archives" / "reports").exists()


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
    assert "<<<<<<<" in content
    assert ">>>>>>>" in content


def test_agent_checkout_submit_accepts_and_archives_changeset(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-vcs")
    checkout = manager.checkout_agent(run, "agent-a", write_scope=["src/**"])

    _write(checkout.checkout_dir / "src" / "a.txt", "changed\n")
    status = manager.status_checkout(run, checkout)
    result = manager.submit_checkout(run, checkout, task_id="task-1", summary="change a")

    assert [(change.path, change.status) for change in status] == [("src/a.txt", "modified")]
    assert result.ok is True
    assert result.status == "accepted"
    assert result.merged_files == ["src/a.txt"]
    assert (run.integration_dir / "src" / "a.txt").read_text(encoding="utf-8") == "changed\n"
    assert result.archive_path is not None
    assert (result.archive_path / "changeset.json").is_file()
    submit_result = json.loads((result.archive_path / "submit_result.json").read_text(encoding="utf-8"))
    assert submit_result["status"] == "accepted"


def test_agent_checkout_pulls_scoped_files_from_integration_workspace(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    _write(tmp_path / "docs" / "note.md", "base docs\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-vcs-pull")
    _write(run.integration_dir / "src" / "a.txt", "current integration\n")

    checkout = manager.checkout_agent(run, "agent-a", write_scope=["src/**"])

    assert (checkout.checkout_dir / "src" / "a.txt").read_text(encoding="utf-8") == "current integration\n"
    assert not (checkout.checkout_dir / "docs" / "note.md").exists()
    assert (checkout.base_dir / "src" / "a.txt").read_text(encoding="utf-8") == "current integration\n"
    assert not (checkout.base_dir / "docs" / "note.md").exists()


def test_agent_checkout_submit_rejects_scope_violation(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    _write(tmp_path / "secret.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-vcs-scope")
    checkout = manager.checkout_agent(run, "agent-a", write_scope=["src/**"])

    _write(checkout.checkout_dir / "secret.txt", "changed\n")
    result = manager.submit_checkout(run, checkout)

    assert result.ok is False
    assert result.status == "rejected"
    assert result.scope_violations == ["secret.txt"]
    assert (run.integration_dir / "secret.txt").read_text(encoding="utf-8") == "base\n"


def test_agent_checkout_submit_reports_structured_conflict(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-vcs-conflict")
    checkout_a = manager.checkout_agent(run, "agent-a", write_scope=["src/**"])
    checkout_b = manager.checkout_agent(run, "agent-b", write_scope=["src/**"])

    _write(checkout_a.checkout_dir / "src" / "a.txt", "from a\n")
    _write(checkout_b.checkout_dir / "src" / "a.txt", "from b\n")

    assert manager.submit_checkout(run, checkout_a).ok is True
    result_b = manager.submit_checkout(run, checkout_b)

    assert result_b.ok is False
    assert result_b.status == "conflict"
    assert result_b.conflicts[0]["path"] == "src/a.txt"
    assert result_b.conflicts[0]["reason"] == "stale_base"
    assert "<<<<<<<" in result_b.conflicts[0]["merge_preview"]
    assert (run.integration_dir / "src" / "a.txt").read_text(encoding="utf-8") == "from a\n"


def test_agent_checkout_dulwich_merge_accepts_non_overlapping_same_file_changes(tmp_path: Path) -> None:
    info = describe_dulwich_backend()
    if not info.get("merge3_available"):
        return
    _write(tmp_path / "src" / "shared.txt", "one\ntwo\nthree\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-vcs-dulwich-merge")
    checkout_a = manager.checkout_agent(run, "agent-a", write_scope=["src/**"])
    checkout_b = manager.checkout_agent(run, "agent-b", write_scope=["src/**"])

    _write(checkout_a.checkout_dir / "src" / "shared.txt", "ONE\ntwo\nthree\n")
    _write(checkout_b.checkout_dir / "src" / "shared.txt", "one\ntwo\nTHREE\n")

    assert manager.submit_checkout(run, checkout_a).ok is True
    result_b = manager.submit_checkout(run, checkout_b)

    assert result_b.ok is True
    assert result_b.status == "accepted"
    assert (run.integration_dir / "src" / "shared.txt").read_text(encoding="utf-8") == "ONE\ntwo\nTHREE\n"


def test_agent_checkout_sync_uses_latest_integration_as_base(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    _write(tmp_path / "src" / "b.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-vcs-sync")
    checkout_a = manager.checkout_agent(run, "agent-a", write_scope=["src/**"])
    checkout_b = manager.checkout_agent(run, "agent-b", write_scope=["src/**"])

    _write(checkout_a.checkout_dir / "src" / "a.txt", "from a\n")
    assert manager.submit_checkout(run, checkout_a).ok is True

    manager.sync_checkout(run, checkout_b)
    _write(checkout_b.checkout_dir / "src" / "b.txt", "from b\n")
    status = manager.status_checkout(run, checkout_b)

    assert [(change.path, change.status) for change in status] == [("src/b.txt", "modified")]
    assert manager.submit_checkout(run, checkout_b).ok is True
    assert (run.integration_dir / "src" / "a.txt").read_text(encoding="utf-8") == "from a\n"
    assert (run.integration_dir / "src" / "b.txt").read_text(encoding="utf-8") == "from b\n"


def test_agent_checkout_conflict_repair_loop_blocks_then_accepts_resubmit(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "shared.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-vcs-loop")
    checkout_a = manager.checkout_agent(run, "agent-a", write_scope=["src/**"])
    checkout_b = manager.checkout_agent(run, "agent-b", write_scope=["src/**"])

    _write(checkout_a.checkout_dir / "src" / "shared.txt", "from a\n")
    _write(checkout_b.checkout_dir / "src" / "shared.txt", "from b\n")

    accepted_a = manager.submit_checkout(run, checkout_a)
    blocked_b = manager.submit_checkout(run, checkout_b)

    assert accepted_a.ok is True
    assert blocked_b.ok is False
    assert blocked_b.status == "conflict"
    assert (run.integration_dir / "src" / "shared.txt").read_text(encoding="utf-8") == "from a\n"

    manager.sync_checkout(run, checkout_b)
    assert (checkout_b.checkout_dir / "src" / "shared.txt").read_text(encoding="utf-8") == "from a\n"
    _write(checkout_b.checkout_dir / "src" / "shared.txt", "from a\nfrom b after sync\n")
    repaired_b = manager.submit_checkout(run, checkout_b)

    assert repaired_b.ok is True
    assert repaired_b.status == "accepted"
    assert (run.integration_dir / "src" / "shared.txt").read_text(encoding="utf-8") == "from a\nfrom b after sync\n"


def test_shared_workspace_lease_blocks_competing_writer(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-lease")
    lease = manager.acquire_shared_lease(
        run,
        "reports/result.md",
        owner="agent-a",
        ttl_sec=60,
    )

    try:
        try:
            manager.acquire_shared_lease(
                run,
                "reports/result.md",
                owner="agent-b",
                ttl_sec=60,
            )
        except FileExistsError as exc:
            assert "locked" in str(exc)
        else:
            raise AssertionError("expected competing lease to fail")
    finally:
        manager.release_shared_lease(run, lease)

    lease_b = manager.acquire_shared_lease(
        run,
        "reports/result.md",
        owner="agent-b",
        ttl_sec=60,
    )
    manager.release_shared_lease(run, lease_b)


def test_shared_workspace_allows_concurrent_readers_and_blocks_writer(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-rw")
    manager.write_shared_text(run, "reports/result.md", "done", owner="agent-a")
    read_a = manager.acquire_shared_read_lease(
        run,
        "reports/result.md",
        owner="agent-a",
        ttl_sec=60,
    )
    read_b = manager.acquire_shared_read_lease(
        run,
        "reports/result.md",
        owner="agent-b",
        ttl_sec=60,
    )

    try:
        assert read_a.lease_id != read_b.lease_id
        try:
            manager.acquire_shared_lease(
                run,
                "reports/result.md",
                owner="agent-c",
                ttl_sec=60,
            )
        except FileExistsError as exc:
            assert "active readers" in str(exc)
        else:
            raise AssertionError("expected writer to be blocked by readers")
    finally:
        manager.release_shared_read_lease(run, read_a)
        manager.release_shared_read_lease(run, read_b)

    write = manager.acquire_shared_lease(
        run,
        "reports/result.md",
        owner="agent-c",
        ttl_sec=60,
    )
    manager.release_shared_lease(run, write)


def test_shared_workspace_writer_blocks_readers(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-rw")
    manager.write_shared_text(run, "reports/result.md", "done", owner="agent-a")
    write = manager.acquire_shared_lease(
        run,
        "reports/result.md",
        owner="agent-a",
        ttl_sec=60,
    )

    try:
        try:
            manager.acquire_shared_read_lease(
                run,
                "reports/result.md",
                owner="agent-b",
                ttl_sec=60,
            )
        except FileExistsError as exc:
            assert "write-locked" in str(exc)
        else:
            raise AssertionError("expected reader to be blocked by writer")
    finally:
        manager.release_shared_lease(run, write)


def test_blueprint_style_agent_worktrees_merge_and_detect_conflict(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "shared.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="blueprint-run")
    agent_a = manager.agent_workspace_dir(run, "agent-a")
    agent_b = manager.agent_workspace_dir(run, "agent-b")
    job_a = manager.prepare_job(run, job_id="job-agent-a", write_scope=["src/**"])
    job_b = manager.prepare_job(run, job_id="job-agent-b", write_scope=["src/**"])

    assert agent_a.is_dir()
    assert agent_b.is_dir()
    assert str(manager.workspace_root) in job_a.readonly_shared_paths

    _write(job_a.worktree_dir / "src" / "shared.txt", "from agent a\n")
    _write(job_b.worktree_dir / "src" / "shared.txt", "from agent b\n")

    assert manager.merge_job(run, job_a).ok is True
    conflict = manager.merge_job(run, job_b)

    assert conflict.ok is False
    assert conflict.conflicts == ["src/shared.txt"]


def test_archive_failed_run_goes_to_failed_directory(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-1")

    archive = manager.archive_run(run, status="failed")
    manifest = json.loads((archive / "run_manifest.json").read_text(encoding="utf-8"))

    assert archive.parent.name == "failed"
    assert manifest["status"] == "failed"
