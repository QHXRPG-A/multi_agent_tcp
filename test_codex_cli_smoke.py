from __future__ import annotations

import shutil
import subprocess
import os
from pathlib import Path

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


def test_codex_cli_uses_private_codex_home_and_cwd_rules(tmp_path: Path) -> None:
    codex = shutil.which("codex")
    if codex is None:
        pytest.skip("codex CLI is not installed on PATH")

    codex_home = tmp_path / "codex_home"
    cwd = tmp_path / "agent_cwd"
    skill_dir = codex_home / "skills" / "private-probe"
    skill_dir.mkdir(parents=True)
    cwd.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: private-probe\n"
        "description: PRIVATE_CODEX_HOME_SKILL_DESCRIPTION\n"
        "---\n"
        "# Private Probe\n\n"
        "PRIVATE_CODEX_HOME_SKILL_BODY\n",
        encoding="utf-8",
    )
    (cwd / "AGENTS.md").write_text(
        "# Private Agent Rule\n\nPRIVATE_CODEX_CWD_RULE_MARKER\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [codex, "debug", "prompt-input", "probe"],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
        cwd=cwd,
        env={**os.environ, "CODEX_HOME": str(codex_home)},
    )

    assert "private-probe" in result.stdout
    assert "PRIVATE_CODEX_HOME_SKILL_DESCRIPTION" in result.stdout
    assert "PRIVATE_CODEX_HOME_SKILL_BODY" not in result.stdout
    assert "PRIVATE_CODEX_CWD_RULE_MARKER" in result.stdout

