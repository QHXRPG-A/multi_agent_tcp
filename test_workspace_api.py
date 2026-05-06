from __future__ import annotations

import json
from pathlib import Path

from multi_agent_tcp.workspace_api import CONTEXT_ENV, main
from multi_agent_tcp.workspace_manager import DulwichWorkspaceManager


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_workspace_api_publishes_without_exposing_physical_path(tmp_path: Path, monkeypatch, capsys) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-api")
    private = manager.agent_workspace_dir(run, "agent-a")
    context_path = private / "workspace_api_context.json"
    context_path.write_text(
        json.dumps(
            {
                "project_root": str(tmp_path),
                "workspace_root": str(manager.workspace_root),
                "run_id": run.run_id,
                "agent_id": "agent-a",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(CONTEXT_ENV, str(context_path))

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
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-api")
    private = manager.agent_workspace_dir(run, "agent-a")
    context_path = private / "workspace_api_context.json"
    context_path.write_text(
        json.dumps(
            {
                "project_root": str(tmp_path),
                "workspace_root": str(manager.workspace_root),
                "run_id": run.run_id,
                "agent_id": "agent-a",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(CONTEXT_ENV, str(context_path))
    manager.write_shared_text(run, "reports/result.md", "done", owner="agent-a")

    assert main(["list", "--area", "reports"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["files"] == ["result.md"]

    assert main(["read", "--area", "reports", "--path", "result.md"]) == 0
    assert capsys.readouterr().out == "done"


def test_workspace_api_publishes_binary_file(tmp_path: Path, monkeypatch, capsys) -> None:
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-api")
    private = manager.agent_workspace_dir(run, "agent-a")
    context_path = private / "workspace_api_context.json"
    context_path.write_text(
        json.dumps(
            {
                "project_root": str(tmp_path),
                "workspace_root": str(manager.workspace_root),
                "run_id": run.run_id,
                "agent_id": "agent-a",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(CONTEXT_ENV, str(context_path))
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
    _write(tmp_path / "src" / "a.txt", "base\n")
    manager = DulwichWorkspaceManager.open_or_init(tmp_path)
    run = manager.create_run(run_id="run-api")
    private = manager.agent_workspace_dir(run, "agent-a")
    context_path = private / "workspace_api_context.json"
    context_path.write_text(
        json.dumps(
            {
                "project_root": str(tmp_path),
                "workspace_root": str(manager.workspace_root),
                "run_id": run.run_id,
                "agent_id": "agent-a",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(CONTEXT_ENV, str(context_path))

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
