from __future__ import annotations

from pathlib import Path

import pytest

from multi_agent_tcp import DulwichWorkspaceManager, SkillSpace, SuperAgentProfile


def _make_skill(root: Path, name: str, description: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n# {name}\n",
        encoding="utf-8",
    )
    (skill_dir / "notes.txt").write_text("private skill data\n", encoding="utf-8")
    return skill_dir


def test_skill_space_maps_hashes_and_materializes_agent_view(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    skill_a = _make_skill(source_root, "pytest-debug", "Debug pytest failures")
    _make_skill(source_root, "secret-admin", "Internal framework control")

    space = SkillSpace.open_or_init(tmp_path / "skill-space")
    rec_a = space.add_skill_copy(skill_a)

    view = space.materialize_for_agent(
        agent_id="agent-1",
        agent_root=tmp_path / "run" / "agents" / "agent-1",
        skill_hashes=[rec_a.skill_hash],
    )

    assert view.skill_hashes == [rec_a.skill_hash]
    assert (view.skills_dir / rec_a.skill_hash / "SKILL.md").is_file()
    assert not (view.skills_dir / "pytest-debug").exists()
    assert "pytest-debug" in view.catalog_prompt()
    assert str(skill_a) not in view.catalog_prompt()
    assert view.context()["agent_workspace"] == str(view.root)
    codex_options = view.codex_adapter_options()
    assert codex_options["execution_context"]["agent_workspace"] == str(view.root)
    assert codex_options["execution_context"]["skill_hashes"] == [rec_a.skill_hash]
    assert "pytest-debug" in codex_options["prompt_preamble"]
    assert str(skill_a) not in codex_options["prompt_preamble"]


def test_skill_space_rejects_unknown_hash(tmp_path: Path) -> None:
    space = SkillSpace.open_or_init(tmp_path / "skill-space")

    with pytest.raises(KeyError):
        space.resolve_hashes(["missing"])


def test_super_agent_can_assign_only_allowed_hashes(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    skill_a = _make_skill(source_root, "a", "A")
    skill_b = _make_skill(source_root, "b", "B")
    space = SkillSpace.open_or_init(tmp_path / "skill-space")
    rec_a = space.add_skill_copy(skill_a)
    rec_b = space.add_skill_copy(skill_b)
    super_agent = SuperAgentProfile(
        agent_id="super",
        assignable_skill_hashes=[rec_a.skill_hash],
    )

    super_agent.validate_assignment([rec_a.skill_hash], space)
    with pytest.raises(PermissionError):
        super_agent.validate_assignment([rec_b.skill_hash], space)


def test_agent_workspace_dir_integrates_with_skill_space(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    manager = DulwichWorkspaceManager.open_or_init(project)
    run = manager.create_run(run_id="run-1")
    skill = _make_skill(tmp_path / "source", "worker-skill", "Worker skill")
    space = SkillSpace.open_or_init(manager.workspace_root / "skill_space")
    rec = space.add_skill_copy(skill)

    agent_root = manager.agent_workspace_dir(run, "agent/1")
    view = space.materialize_for_agent(
        agent_id="agent/1",
        agent_root=agent_root,
        skill_hashes=[rec.skill_hash],
    )

    assert agent_root.name == "private"
    assert agent_root.parent.name == "agent_1"
    assert view.root == agent_root
    assert (agent_root.parent / "agent_workspace.json").is_file()
