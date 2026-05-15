from __future__ import annotations

import json
from pathlib import Path

from multi_agent_tcp.workspace_api import CONTEXT_ENV, main
from multi_agent_tcp.workspace_manager import DulwichWorkspaceManager
from multi_agent_tcp.workspace_rpc import WorkspaceRPCServer


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_api_context(tmp_path: Path, monkeypatch, agent_id: str = "agent-a"):
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-api")
    private = manager.agent_workspace_dir(run, agent_id)
    context_path = private / "workspace_api_context.json"
    context_path.write_text(
        json.dumps(
            {
                "project_root": str(tmp_path),
                "workspace_root": str(manager.workspace_root),
                "run_id": run.run_id,
                "agent_id": agent_id,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(CONTEXT_ENV, str(context_path))
    return manager, run, private


def test_workspace_api_publishes_without_exposing_physical_path(tmp_path: Path, monkeypatch, capsys) -> None:
    manager, run, _private = _make_api_context(tmp_path, monkeypatch)

    assert main(["publish", "--area", "reports", "--path", "result.md", "--text", "done"]) == 0
    out = json.loads(capsys.readouterr().out)

    assert out == {
        "ok": True,
        "area": "reports",
        "path": "result.md",
        "owner": "agent-a",
        "version": 1,
    }
    assert str(manager.workspace_root) not in json.dumps(out)
    assert manager.read_shared_text(run, "reports/result.md") == "done"


def test_workspace_api_lists_and_reads_area_files(tmp_path: Path, monkeypatch, capsys) -> None:
    manager, run, _private = _make_api_context(tmp_path, monkeypatch)
    manager.write_shared_text(run, "reports/result.md", "done", owner="agent-a")

    assert main(["list", "--area", "reports"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["files"] == ["result.md"]

    assert main(["read", "--area", "reports", "--path", "result.md"]) == 0
    assert capsys.readouterr().out == "done"


def test_workspace_api_publishes_binary_file(tmp_path: Path, monkeypatch, capsys) -> None:
    _manager, run, private = _make_api_context(tmp_path, monkeypatch)
    source = private / "result.bin"
    source.write_bytes(b"\x00\x01\x02")

    assert main(
        [
            "publish-file",
            "--area",
            "artifacts",
            "--path",
            "images/result.bin",
            "--file",
            str(source),
        ]
    ) == 0
    out = json.loads(capsys.readouterr().out)

    assert out == {
        "ok": True,
        "area": "artifacts",
        "path": "images/result.bin",
        "owner": "agent-a",
        "bytes": 3,
        "version": 1,
    }
    assert (run.shared_artifacts_dir / "images" / "result.bin").read_bytes() == b"\x00\x01\x02"


def test_workspace_api_expected_version_blocks_stale_write(tmp_path: Path, monkeypatch, capsys) -> None:
    manager, run, _private = _make_api_context(tmp_path, monkeypatch)

    assert main(["publish", "--area", "reports", "--path", "result.md", "--text", "v1"]) == 0
    capsys.readouterr()
    assert main(["read", "--area", "reports", "--path", "result.md", "--json"]) == 0
    read = json.loads(capsys.readouterr().out)
    assert read["version"] == 1

    assert main(
        [
            "publish",
            "--area",
            "reports",
            "--path",
            "result.md",
            "--text",
            "stale",
            "--expected-version",
            "0",
        ]
    ) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert "version conflict" in out["error"]
    assert manager.read_shared_text(run, "reports/result.md") == "v1"


def test_workspace_api_publish_file_expected_version_blocks_stale_binary(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    manager, run, private = _make_api_context(tmp_path, monkeypatch)
    source = private / "result.bin"
    source.write_bytes(b"v1")

    assert main(
        [
            "publish-file",
            "--area",
            "artifacts",
            "--path",
            "result.bin",
            "--file",
            str(source),
        ]
    ) == 0
    capsys.readouterr()
    source.write_bytes(b"stale")

    assert main(
        [
            "publish-file",
            "--area",
            "artifacts",
            "--path",
            "result.bin",
            "--file",
            str(source),
            "--expected-version",
            "0",
        ]
    ) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert "version conflict" in out["error"]
    assert (run.shared_artifacts_dir / "result.bin").read_bytes() == b"v1"
    assert manager.shared_file_version(run, "artifacts/result.bin") == 1


def test_workspace_api_read_is_blocked_by_active_writer(tmp_path: Path, monkeypatch, capsys) -> None:
    manager, run, _private = _make_api_context(tmp_path, monkeypatch)
    manager.write_shared_text(run, "reports/result.md", "done", owner="agent-a")
    lease = manager.acquire_shared_lease(
        run,
        "reports/result.md",
        owner="agent-b",
        ttl_sec=60,
    )

    try:
        assert main(["read", "--area", "reports", "--path", "result.md"]) == 1
        out = json.loads(capsys.readouterr().out)
        assert out["ok"] is False
        assert "write-locked" in out["error"]
    finally:
        manager.release_shared_lease(run, lease)


def test_workspace_api_publish_is_blocked_by_active_reader(tmp_path: Path, monkeypatch, capsys) -> None:
    manager, run, _private = _make_api_context(tmp_path, monkeypatch)
    manager.write_shared_text(run, "reports/result.md", "done", owner="agent-a")
    lease = manager.acquire_shared_read_lease(
        run,
        "reports/result.md",
        owner="agent-b",
        ttl_sec=60,
    )

    try:
        assert main(["publish", "--area", "reports", "--path", "result.md", "--text", "blocked"]) == 1
        out = json.loads(capsys.readouterr().out)
        assert out["ok"] is False
        assert "active readers" in out["error"]
        assert manager.read_shared_text(run, "reports/result.md") == "done"
    finally:
        manager.release_shared_read_lease(run, lease)


def test_workspace_api_rejects_paths_that_escape_area(tmp_path: Path, monkeypatch, capsys) -> None:
    manager, run, _private = _make_api_context(tmp_path, monkeypatch)

    assert main(["publish", "--area", "reports", "--path", "../escape.md", "--text", "nope"]) == 1
    out = json.loads(capsys.readouterr().out)

    assert out["ok"] is False
    assert "relative path inside the selected area" in out["error"]
    assert not (run.shared_dir / "escape.md").exists()
    assert manager.list_shared_files(run, "reports") == []


def test_workspace_api_rpc_context_does_not_need_physical_workspace_path(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-rpc")
    private = manager.agent_workspace_dir(run, "agent-a")
    server = WorkspaceRPCServer(manager, run)
    server.start()
    try:
        context_path = private / "workspace_api_context.json"
        context_path.write_text(
            json.dumps(server.context_for("agent-a"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        monkeypatch.setenv(CONTEXT_ENV, str(context_path))

        assert main(["publish", "--area", "reports", "--path", "result.md", "--text", "done"]) == 0
        out = json.loads(capsys.readouterr().out)

        assert out["ok"] is True
        assert out["version"] == 1
        assert manager.read_shared_text(run, "reports/result.md") == "done"
        context_json = context_path.read_text(encoding="utf-8")
        assert str(manager.workspace_root) not in context_json
        assert str(run.path) not in context_json
    finally:
        server.close()


def test_workspace_api_rpc_lists_and_extracts_long_term_archive(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    old_run = manager.create_run(run_id="run-done")
    manager.write_shared_text(old_run, "reports/result.md", "done\n", owner="framework")
    manager.archive_run(old_run)

    run = manager.create_run(run_id="run-reader")
    private = manager.agent_workspace_dir(run, "agent-a")
    server = WorkspaceRPCServer(manager, run)
    server.start()
    try:
        context_path = private / "workspace_api_context.json"
        context_path.write_text(
            json.dumps(server.context_for("agent-a"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        monkeypatch.setenv(CONTEXT_ENV, str(context_path))

        assert main(["list-archives"]) == 0
        listed = json.loads(capsys.readouterr().out)
        assert listed["archives"][0]["archive_id"] == "run-done-completed"

        assert main(["extract-archive", "--archive-id", "run-done-completed", "--path", "reports"]) == 0
        extracted = json.loads(capsys.readouterr().out)
        extracted_path = Path(extracted["path"])
        assert (extracted_path / "result.md").read_text(encoding="utf-8") == "done\n"
        assert extracted_path.is_relative_to(private)
    finally:
        server.close()


def test_workspace_api_local_checkout_status_diff_submit(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    manager, run, _private = _make_api_context(tmp_path, monkeypatch)

    assert main(["checkout", "--scope-path", "src/**"]) == 0
    out = json.loads(capsys.readouterr().out)
    checkout_path = Path(out["checkout_path"])
    _write(checkout_path / "src" / "a.txt", "changed\n")

    assert main(["status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["files"][0]["path"] == "src/a.txt"
    assert status["files"][0]["status"] == "modified"

    assert main(["diff"]) == 0
    patch = capsys.readouterr().out
    assert patch.startswith("--- a/src/a.txt\n+++ b/src/a.txt\n")
    assert "changed" in patch

    assert main(["submit", "--task-id", "task-api", "--summary", "change a"]) == 0
    submit = json.loads(capsys.readouterr().out)
    assert submit["ok"] is True
    assert submit["status"] == "accepted"
    assert (run.integration_dir / "src" / "a.txt").read_text(encoding="utf-8") == "changed\n"
    assert manager.shared_file_version(run, "src/a.txt") == 0


def test_workspace_api_rpc_checkout_submit(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-rpc-vcs")
    private = manager.agent_workspace_dir(run, "agent-a")
    server = WorkspaceRPCServer(manager, run)
    server.start()
    try:
        context_path = private / "workspace_api_context.json"
        context_path.write_text(
            json.dumps(server.context_for("agent-a"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        monkeypatch.setenv(CONTEXT_ENV, str(context_path))

        assert main(["checkout", "--scope-path", "src/**"]) == 0
        checkout = json.loads(capsys.readouterr().out)
        _write(Path(checkout["checkout_path"]) / "src" / "a.txt", "rpc changed\n")

        assert main(["submit"]) == 0
        submit = json.loads(capsys.readouterr().out)
        assert submit["ok"] is True
        assert submit["merged_files"] == ["src/a.txt"]
        assert (run.integration_dir / "src" / "a.txt").read_text(encoding="utf-8") == "rpc changed\n"
        manifest = json.loads((run.shared_dir / "manifest.json").read_text(encoding="utf-8"))
        api_calls = [
            item
            for item in manifest["writes"]
            if item.get("event_type") == "workspace_api_call"
        ]
        assert [item["command"] for item in api_calls] == ["checkout", "submit"]
        assert api_calls[0]["workspace_event"] == "WorkspaceAPICalled"
        assert api_calls[0]["agent_id"] == "agent-a"
        assert api_calls[0]["write_scope"] == ["src/**"]
        assert api_calls[1]["task_id"] is None
    finally:
        server.close()


def test_workspace_api_rpc_project_reference_checkout_path_submit(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    _write(tmp_path / "src" / "b.txt", "base b\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-rpc-reference", code_mode="project_reference")
    private = manager.agent_workspace_dir(run, "agent-a")
    server = WorkspaceRPCServer(manager, run)
    server.start()
    try:
        context_path = private / "workspace_api_context.json"
        context_path.write_text(
            json.dumps(server.context_for("agent-a"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        monkeypatch.setenv(CONTEXT_ENV, str(context_path))

        assert main(["checkout", "--path", "src/a.txt"]) == 0
        checkout = json.loads(capsys.readouterr().out)
        checkout_path = Path(checkout["checkout_path"])
        assert (checkout_path / "src" / "a.txt").read_text(encoding="utf-8") == "base\n"
        assert not (checkout_path / "src" / "b.txt").exists()
        _write(checkout_path / "src" / "a.txt", "rpc reference changed\n")

        assert main(["submit"]) == 0
        submit = json.loads(capsys.readouterr().out)
        assert submit["ok"] is True
        assert submit["merged_files"] == ["src/a.txt"]
        assert (tmp_path / "src" / "a.txt").read_text(encoding="utf-8") == "rpc reference changed\n"
        assert not (run.integration_dir / "src" / "a.txt").exists()
    finally:
        server.close()


def test_workspace_api_rpc_conflict_blocks_then_sync_resubmit(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write(tmp_path / "src" / "shared.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-rpc-vcs-loop")
    private_a = manager.agent_workspace_dir(run, "agent-a")
    private_b = manager.agent_workspace_dir(run, "agent-b")
    server = WorkspaceRPCServer(manager, run)
    server.start()
    try:
        context_a = private_a / "workspace_api_context.json"
        context_b = private_b / "workspace_api_context.json"
        context_a.write_text(
            json.dumps(server.context_for("agent-a"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        context_b.write_text(
            json.dumps(server.context_for("agent-b"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        monkeypatch.setenv(CONTEXT_ENV, str(context_a))
        assert main(["checkout", "--scope-path", "src/**"]) == 0
        checkout_a = json.loads(capsys.readouterr().out)

        monkeypatch.setenv(CONTEXT_ENV, str(context_b))
        assert main(["checkout", "--scope-path", "src/**"]) == 0
        checkout_b = json.loads(capsys.readouterr().out)

        _write(Path(checkout_a["checkout_path"]) / "src" / "shared.txt", "from a\n")
        _write(Path(checkout_b["checkout_path"]) / "src" / "shared.txt", "from b\n")

        monkeypatch.setenv(CONTEXT_ENV, str(context_a))
        assert main(["submit", "--task-id", "task-a"]) == 0
        accepted = json.loads(capsys.readouterr().out)
        assert accepted["status"] == "accepted"

        monkeypatch.setenv(CONTEXT_ENV, str(context_b))
        assert main(["submit", "--task-id", "task-b"]) == 0
        blocked = json.loads(capsys.readouterr().out)
        assert blocked["ok"] is False
        assert blocked["status"] == "conflict"
        assert blocked["conflicts"][0]["path"] == "src/shared.txt"
        assert (run.integration_dir / "src" / "shared.txt").read_text(encoding="utf-8") == "from a\n"

        assert main(["sync"]) == 0
        capsys.readouterr()
        _write(Path(checkout_b["checkout_path"]) / "src" / "shared.txt", "from a\nfrom b after sync\n")
        assert main(["submit", "--task-id", "task-b-resolved"]) == 0
        repaired = json.loads(capsys.readouterr().out)
        assert repaired["status"] == "accepted"
        assert (
            run.integration_dir / "src" / "shared.txt"
        ).read_text(encoding="utf-8") == "from a\nfrom b after sync\n"
    finally:
        server.close()
