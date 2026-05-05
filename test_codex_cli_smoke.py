from __future__ import annotations

import shutil
import subprocess

import pytest


def test_codex_cli_is_available_and_reports_version() -> None:
    codex = shutil.which("codex")
    if codex is None:
        pytest.skip("codex CLI is not installed on PATH")

    result = subprocess.run(
        [codex, "--version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert "codex-cli" in result.stdout.lower()


def test_codex_cli_help_exposes_exec_command() -> None:
    codex = shutil.which("codex")
    if codex is None:
        pytest.skip("codex CLI is not installed on PATH")

    result = subprocess.run(
        [codex, "--help"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert "exec" in result.stdout
    assert "Run Codex non-interactively" in result.stdout

