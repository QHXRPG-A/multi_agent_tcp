from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from multi_agent_tcp import DulwichWorkspaceManager, describe_dulwich_backend
import multi_agent_tcp.workspace_manager as workspace_manager


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


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
    assert run.path == archive
    assert run.integration_dir == archive / "shared" / "code"
    assert manager.open_run_any("run-1").path == archive


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


def test_run_snapshot_excludes_generated_dependency_trees(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    _write(tmp_path / "node_modules" / "pkg" / "index.js", "generated\n")
    _write(tmp_path / ".next" / "cache" / "page.js", "generated\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)

    run = manager.create_run(run_id="run-small-snapshot")

    assert (run.base_dir / "src" / "a.txt").is_file()
    assert not (run.base_dir / "node_modules").exists()
    assert not (run.base_dir / ".next").exists()
    assert not (run.integration_dir / "node_modules").exists()
    assert not (run.integration_dir / ".next").exists()


def test_run_snapshot_scope_limits_base_and_integration(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    _write(tmp_path / "docs" / "note.md", "docs\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)

    run = manager.create_run(run_id="run-scoped-snapshot", snapshot_scope=["src/**"])
    manifest = json.loads((run.path / "run_manifest.json").read_text(encoding="utf-8"))

    assert (run.base_dir / "src" / "a.txt").is_file()
    assert not (run.base_dir / "docs" / "note.md").exists()
    assert (run.integration_dir / "src" / "a.txt").is_file()
    assert not (run.integration_dir / "docs" / "note.md").exists()
    assert manifest["snapshot_scope"] == ["src/**"]


def test_project_reference_run_does_not_copy_project_code_to_shared_code(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    _write(tmp_path / "docs" / "note.md", "docs\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)

    run = manager.create_run(run_id="run-reference", code_mode="project_reference")
    manifest = json.loads((run.path / "run_manifest.json").read_text(encoding="utf-8"))

    assert manifest["code_mode"] == "project_reference"
    assert not (run.base_dir / "src" / "a.txt").exists()
    assert not (run.integration_dir / "src" / "a.txt").exists()
    assert (tmp_path / "src" / "a.txt").read_text(encoding="utf-8") == "base\n"


def test_project_reference_checkout_fetches_specific_paths_and_submits_to_project(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    _write(tmp_path / "src" / "b.txt", "base b\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-reference-submit", code_mode="project_reference")

    checkout = manager.checkout_agent(run, "agent-a", checkout_paths=["src/a.txt"])

    assert (checkout.checkout_dir / "src" / "a.txt").read_text(encoding="utf-8") == "base\n"
    assert not (checkout.checkout_dir / "src" / "b.txt").exists()
    _write(checkout.checkout_dir / "src" / "a.txt", "changed\n")
    result = manager.submit_checkout(run, checkout, task_id="task-1")

    assert result.ok is True
    assert result.merged_files == ["src/a.txt"]
    assert (tmp_path / "src" / "a.txt").read_text(encoding="utf-8") == "changed\n"
    assert not (run.integration_dir / "src" / "a.txt").exists()


def test_blueprint_changeset_rollback_and_restore_use_reversible_archive(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-rollback", code_mode="project_reference")

    first = manager.checkout_agent(run, "agent-a", checkout_paths=["src/a.txt"])
    _write(first.checkout_dir / "src" / "a.txt", "one\n")
    first_result = manager.submit_checkout(run, first, task_id="task-1", summary="one")
    second = manager.checkout_agent(run, "agent-b", checkout_paths=["src/a.txt"])
    _write(second.checkout_dir / "src" / "a.txt", "two\n")
    second_result = manager.submit_checkout(run, second, task_id="task-2", summary="two")

    assert (first_result.archive_path / "reversible.json").is_file()
    assert (tmp_path / "src" / "a.txt").read_text(encoding="utf-8") == "two\n"

    rollback = manager.rollback_changesets(run, second_result.changeset_id, actor="test").to_dict()
    diff = manager.blueprint_run_diff(run).to_dict()

    assert rollback["ok"] is True
    assert rollback["changesetIds"] == [second_result.changeset_id]
    assert (tmp_path / "src" / "a.txt").read_text(encoding="utf-8") == "one\n"
    assert diff["summary"]["accepted"] == 1
    assert diff["summary"]["rolledBack"] == 1
    assert [item["status"] for item in diff["changesets"]] == ["accepted", "rolled_back"]
    assert diff["changesets"][1]["restorable"] is True
    assert diff["acceptedDiffs"][0]["file"] == "src/a.txt"

    restore = manager.restore_latest_rollback(run, actor="test").to_dict()
    restored_diff = manager.blueprint_run_diff(run).to_dict()

    assert restore["ok"] is True
    assert restore["restoredRollbackId"] == rollback["rollbackId"]
    assert (tmp_path / "src" / "a.txt").read_text(encoding="utf-8") == "two\n"
    assert restored_diff["summary"]["accepted"] == 2
    assert restored_diff["summary"]["rolledBack"] == 0


def test_blueprint_changeset_rollback_handles_added_deleted_and_binary_files(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "delete.txt", "delete me\n")
    _write_bytes(tmp_path / "src" / "asset.bin", b"\x00base\xff")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-rollback-binary", code_mode="project_reference")
    checkout = manager.checkout_agent(run, "agent-a", checkout_paths=["src/delete.txt", "src/asset.bin", "src/add.txt"])

    (checkout.checkout_dir / "src" / "delete.txt").unlink()
    _write(checkout.checkout_dir / "src" / "add.txt", "added\n")
    _write_bytes(checkout.checkout_dir / "src" / "asset.bin", b"\x00changed\xff")
    result = manager.submit_checkout(run, checkout)

    assert result.ok is True
    assert not (tmp_path / "src" / "delete.txt").exists()
    assert (tmp_path / "src" / "add.txt").read_text(encoding="utf-8") == "added\n"
    assert (tmp_path / "src" / "asset.bin").read_bytes() == b"\x00changed\xff"

    rollback = manager.rollback_changesets(run, result.changeset_id).to_dict()

    assert rollback["ok"] is True
    assert (tmp_path / "src" / "delete.txt").read_text(encoding="utf-8") == "delete me\n"
    assert not (tmp_path / "src" / "add.txt").exists()
    assert (tmp_path / "src" / "asset.bin").read_bytes() == b"\x00base\xff"

    restore = manager.restore_latest_rollback(run).to_dict()

    assert restore["ok"] is True
    assert not (tmp_path / "src" / "delete.txt").exists()
    assert (tmp_path / "src" / "add.txt").read_text(encoding="utf-8") == "added\n"
    assert (tmp_path / "src" / "asset.bin").read_bytes() == b"\x00changed\xff"


def test_blueprint_changeset_rollback_hash_guard_rejects_external_edits(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-rollback-conflict", code_mode="project_reference")
    checkout = manager.checkout_agent(run, "agent-a", checkout_paths=["src/a.txt"])
    _write(checkout.checkout_dir / "src" / "a.txt", "changed\n")
    result = manager.submit_checkout(run, checkout)
    _write(tmp_path / "src" / "a.txt", "external\n")

    rollback = manager.rollback_changesets(run, result.changeset_id).to_dict()

    assert rollback["ok"] is False
    assert rollback["status"] == "conflict"
    assert rollback["conflicts"][0]["reason"] == "hash_mismatch"
    assert (tmp_path / "src" / "a.txt").read_text(encoding="utf-8") == "external\n"


def test_legacy_blueprint_changeset_without_reversible_manifest_is_not_rollbackable(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-rollback-legacy", code_mode="project_reference")
    checkout = manager.checkout_agent(run, "agent-a", checkout_paths=["src/a.txt"])
    _write(checkout.checkout_dir / "src" / "a.txt", "changed\n")
    result = manager.submit_checkout(run, checkout)
    assert result.archive_path is not None
    (result.archive_path / "reversible.json").unlink()

    diff = manager.blueprint_run_diff(run).to_dict()
    rollback = manager.rollback_changesets(run, result.changeset_id).to_dict()

    assert diff["changesets"][0]["reversible"] is False
    assert diff["changesets"][0]["rollbackable"] is False
    assert "reversible changeset manifest is missing" in diff["changesets"][0]["rollbackDisabledReason"]
    assert rollback["ok"] is False
    assert rollback["status"] == "conflict"
    assert rollback["conflicts"][0]["reason"] == "not_reversible"


def test_checkout_refresh_preserves_framework_agents_md(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-framework-file-refresh", code_mode="project_reference")

    checkout = manager.checkout_agent(run, "agent-a", write_scope=["src/a.txt"])
    _write(checkout.checkout_dir / "AGENTS.md", "framework rules\n")
    _write(checkout.base_dir / "AGENTS.md", "framework rules\n")

    refreshed = manager.checkout_agent(run, "agent-a", checkout_paths=["src/a.txt"])

    assert (refreshed.checkout_dir / "AGENTS.md").read_text(encoding="utf-8") == "framework rules\n"
    assert (refreshed.base_dir / "AGENTS.md").read_text(encoding="utf-8") == "framework rules\n"
    assert manager.status_checkout(run, refreshed) == []


def test_checkout_refresh_works_when_process_cwd_is_checkout_dir(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-refresh-from-cwd", code_mode="project_reference")
    checkout = manager.checkout_agent(run, "agent-a", write_scope=["src/a.txt"])
    _write(checkout.checkout_dir / "AGENTS.md", "framework rules\n")
    _write(checkout.base_dir / "AGENTS.md", "framework rules\n")

    old_cwd = Path.cwd()
    try:
        os.chdir(checkout.checkout_dir)
        refreshed = manager.checkout_agent(run, "agent-a", checkout_paths=["src/a.txt"])
    finally:
        os.chdir(old_cwd)

    assert (refreshed.checkout_dir / "src" / "a.txt").read_text(encoding="utf-8") == "base\n"
    assert (refreshed.checkout_dir / "AGENTS.md").read_text(encoding="utf-8") == "framework rules\n"
    assert manager.status_checkout(run, refreshed) == []


def test_project_reference_empty_scope_checkout_stays_empty_and_rejects_changes(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-reference-empty", code_mode="project_reference")

    checkout = manager.checkout_agent(run, "agent-a")
    assert not any(checkout.checkout_dir.iterdir())

    _write(checkout.checkout_dir / "src" / "a.txt", "changed\n")
    result = manager.submit_checkout(run, checkout)

    assert result.ok is False
    assert result.status == "rejected"
    assert result.scope_violations == ["src/a.txt"]
    assert (tmp_path / "src" / "a.txt").read_text(encoding="utf-8") == "base\n"


def test_project_reference_missing_static_scope_does_not_scan_project_root(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-reference-missing-scope", code_mode="project_reference")

    def fail_full_scan(*_args: object, **_kwargs: object) -> Dict[str, Path]:
        raise AssertionError("project root full scan should not be used for static scoped checkout")

    monkeypatch.setattr(workspace_manager, "_relative_files", fail_full_scan)

    checkout = manager.checkout_agent(run, "agent-a", write_scope=["shared/reports/**"])

    assert not any(checkout.checkout_dir.rglob("*"))
    assert checkout.write_scope == ["shared/reports/**"]


def test_project_reference_full_scope_prunes_workspace_root_during_checkout(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _write(tmp_path / "docs" / "a.txt", "base\n")
    _write(tmp_path / ".multi_agent_workspace" / "old" / "hidden.txt", "ignore\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-reference-full", code_mode="project_reference")

    seen_dirs: List[str] = []
    real_walk = workspace_manager.os.walk

    def tracked_walk(top: object, *args: object, **kwargs: object):
        for dir_path, dir_names, file_names in real_walk(top, *args, **kwargs):
            seen_dirs.append(Path(dir_path).resolve().relative_to(tmp_path.resolve()).as_posix())
            yield dir_path, dir_names, file_names

    monkeypatch.setattr(workspace_manager.os, "walk", tracked_walk)

    checkout = manager.checkout_agent(run, "agent-a", write_scope=["**"])

    assert (checkout.checkout_dir / "docs" / "a.txt").read_text(encoding="utf-8") == "base\n"
    assert not (checkout.checkout_dir / ".multi_agent_workspace").exists()
    assert ".multi_agent_workspace" not in seen_dirs


def test_windows_extended_path_prefix_is_stripped_for_copy_path_comparisons() -> None:
    if os.name != "nt":
        return

    assert workspace_manager._strip_windows_extended_path_prefix(
        "\\\\?\\F:\\repo\\GuLiCode\\node_modules"
    ) == "F:\\repo\\GuLiCode\\node_modules"
    assert workspace_manager._strip_windows_extended_path_prefix(
        "\\\\?\\UNC\\server\\share\\repo"
    ) == "\\\\server\\share\\repo"


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


def test_blueprint_run_diff_reads_accepted_changeset_summary_and_detail(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-blueprint-diff", code_mode="project_reference")
    checkout = manager.checkout_agent(run, "agent-a", checkout_paths=["src/a.txt"])

    _write(checkout.checkout_dir / "src" / "a.txt", "changed\n")
    result = manager.submit_checkout(run, checkout, task_id="task-1", summary="change a")
    summary = manager.blueprint_run_diff(run).to_dict()
    detail = manager.blueprint_changeset_detail(run, result.changeset_id).to_dict()

    assert summary["summary"]["accepted"] == 1
    assert summary["summary"]["files"] == 1
    assert summary["changesets"][0]["agentId"] == "agent-a"
    assert summary["changesets"][0]["taskId"] == "task-1"
    assert summary["acceptedDiffs"][0]["file"] == "src/a.txt"
    assert "changed" in summary["acceptedDiffs"][0]["patch"]
    assert detail["changesetId"] == result.changeset_id
    assert detail["status"] == "accepted"
    assert detail["diffs"][0]["file"] == "src/a.txt"


def test_blueprint_run_diff_reads_archived_changesets(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-blueprint-diff-archived", code_mode="project_reference")
    checkout = manager.checkout_agent(run, "agent-a", checkout_paths=["src/a.txt"])

    _write(checkout.checkout_dir / "src" / "a.txt", "changed\n")
    result = manager.submit_checkout(run, checkout, task_id="task-archived", summary="change archived")
    archive = manager.archive_run(run)

    summary = manager.blueprint_run_diff(run).to_dict()
    reopened = manager.open_run_any(run.run_id)
    detail = manager.blueprint_changeset_detail(reopened, result.changeset_id).to_dict()

    assert run.path == archive
    assert reopened.path == archive
    assert summary["summary"]["accepted"] == 1
    assert summary["changesets"][0]["changesetId"] == result.changeset_id
    assert summary["acceptedDiffs"][0]["file"] == "src/a.txt"
    assert detail["status"] == "accepted"
    assert detail["diffs"][0]["file"] == "src/a.txt"


def test_blueprint_run_diff_excludes_conflict_rejected_and_unsubmitted_checkout_from_accepted(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    _write(tmp_path / "secret.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-blueprint-diff-status", code_mode="project_reference")
    checkout_a = manager.checkout_agent(run, "agent-a", checkout_paths=["src/a.txt"])
    checkout_b = manager.checkout_agent(run, "agent-b", checkout_paths=["src/a.txt"])
    checkout_c = manager.checkout_agent(run, "agent-c", write_scope=["src/**"])
    checkout_d = manager.checkout_agent(run, "agent-d", checkout_paths=["src/a.txt"])

    _write(checkout_a.checkout_dir / "src" / "a.txt", "from a\n")
    _write(checkout_b.checkout_dir / "src" / "a.txt", "from b\n")
    _write(checkout_c.checkout_dir / "secret.txt", "changed\n")
    _write(checkout_d.checkout_dir / "src" / "a.txt", "unsubmitted\n")

    accepted = manager.submit_checkout(run, checkout_a)
    conflict = manager.submit_checkout(run, checkout_b)
    rejected = manager.submit_checkout(run, checkout_c)
    diff = manager.blueprint_run_diff(run).to_dict()

    assert accepted.status == "accepted"
    assert conflict.status == "conflict"
    assert rejected.status == "rejected"
    assert diff["summary"]["total"] == 3
    assert diff["summary"]["accepted"] == 1
    assert diff["summary"]["conflict"] == 1
    assert diff["summary"]["rejected"] == 1
    assert [item["file"] for item in diff["acceptedDiffs"]] == ["src/a.txt"]
    assert all(item["agentId"] != "agent-d" for item in diff["changesets"])


def test_blueprint_changeset_detail_reports_missing_patch(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-blueprint-diff-missing-patch", code_mode="project_reference")
    checkout = manager.checkout_agent(run, "agent-a", checkout_paths=["src/a.txt"])

    _write(checkout.checkout_dir / "src" / "a.txt", "changed\n")
    result = manager.submit_checkout(run, checkout)
    assert result.archive_path is not None
    (result.archive_path / "patch.diff").unlink()

    try:
        manager.blueprint_changeset_detail(run, result.changeset_id)
    except FileNotFoundError as exc:
        assert "patch.diff" in str(exc)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("expected missing patch.diff to fail")


def test_blueprint_run_diff_keeps_binary_files_out_of_text_renderer(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir(parents=True)
    (tmp_path / "assets" / "image.bin").write_bytes(b"base\x00data")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-blueprint-diff-binary", code_mode="project_reference")
    checkout = manager.checkout_agent(run, "agent-a", checkout_paths=["assets/image.bin"])

    (checkout.checkout_dir / "assets" / "image.bin").write_bytes(b"changed\x00data")
    result = manager.submit_checkout(run, checkout)
    diff = manager.blueprint_run_diff(run).to_dict()
    detail = manager.blueprint_changeset_detail(run, result.changeset_id).to_dict()

    assert diff["acceptedDiffs"] == []
    assert diff["binaryFiles"][0]["file"] == "assets/image.bin"
    assert detail["diffs"] == []
    assert detail["binaryFiles"][0]["file"] == "assets/image.bin"


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


def test_agent_checkout_line_merge_accepts_non_overlapping_same_file_without_dulwich(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(workspace_manager, "_DULWICH_AVAILABLE", False)
    monkeypatch.setattr(workspace_manager, "merge_blobs", None)
    _write(tmp_path / "src" / "shared.txt", "one\ntwo\nthree\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-line-merge")
    checkout_a = manager.checkout_agent(run, "agent-a", write_scope=["src/**"])
    checkout_b = manager.checkout_agent(run, "agent-b", write_scope=["src/**"])

    _write(checkout_a.checkout_dir / "src" / "shared.txt", "ONE\ntwo\nthree\n")
    _write(checkout_b.checkout_dir / "src" / "shared.txt", "one\ntwo\nTHREE\n")

    assert manager.submit_checkout(run, checkout_a).ok is True
    result_b = manager.submit_checkout(run, checkout_b)

    assert result_b.ok is True
    assert result_b.status == "accepted"
    assert (run.integration_dir / "src" / "shared.txt").read_text(encoding="utf-8") == "ONE\ntwo\nTHREE\n"


def test_agent_checkout_line_merge_accepts_non_overlapping_same_file_after_false_dulwich_conflict(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    class FakeBlob:
        @classmethod
        def from_string(cls, data: bytes) -> bytes:
            return data

    def fake_merge_blobs(*args: Any, **kwargs: Any) -> tuple[bytes, bool]:
        return b"<<<<<<< ours\n", True

    monkeypatch.setattr(workspace_manager, "_DULWICH_AVAILABLE", True)
    monkeypatch.setattr(workspace_manager, "Blob", FakeBlob)
    monkeypatch.setattr(workspace_manager, "merge_blobs", fake_merge_blobs)
    _write(tmp_path / "src" / "shared.txt", "one\ntwo\nthree\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-false-dulwich-conflict")
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
