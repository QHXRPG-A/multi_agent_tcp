from __future__ import annotations

import json
import shutil
import subprocess


def _installed_cli() -> str:
    cli = shutil.which("multi-agent-tcp")
    assert cli is not None, "multi-agent-tcp is not installed on PATH"
    return cli


def test_installed_cli_help_works_from_outside_source_tree(tmp_path) -> None:
    result = subprocess.run(
        [_installed_cli(), "--help"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        cwd=tmp_path,
    )

    assert "doctor" in result.stdout
    assert "show-registry" in result.stdout
    assert "dispatch" in result.stdout


def test_installed_cli_doctor_json_works_from_outside_source_tree(tmp_path) -> None:
    result = subprocess.run(
        [_installed_cli(), "doctor", "--json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        cwd=tmp_path,
    )
    data = json.loads(result.stdout)

    assert data["tool"] == "multi-agent-tcp"
    assert data["command"]["on_path"] is True
    assert data["registry"]["exists"] is True
