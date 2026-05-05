from __future__ import annotations

from pathlib import Path

from multi_agent_tcp.graph_runtime import AgentSkillSelection
from multi_agent_tcp.registry import (
    AgentProfile,
    AgentsRegistry,
    SkillInfo,
    show_registry_response,
)


def _skill_info(tmp_path: Path, name: str) -> SkillInfo:
    skill_dir = tmp_path / "skill_list" / name
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"---\nname: {name}\ndescription: {name} description\n---\n# {name}\n",
        encoding="utf-8",
    )
    return SkillInfo(
        name=name,
        description=f"{name} description",
        skill_md_path=skill_md,
    )


def _registry(tmp_path: Path, agents: dict[str, AgentProfile]) -> AgentsRegistry:
    manifest = {
        "alpha": _skill_info(tmp_path, "alpha"),
        "beta": _skill_info(tmp_path, "beta"),
    }
    return AgentsRegistry(
        agents=agents,
        skill_list_dir=tmp_path / "skill_list",
        skill_manifest=manifest,
        raw={},
    )


def _agent(
    agent_id: str,
    *,
    skills: list[str] | None = None,
    skill_selection: AgentSkillSelection | dict[str, object] | None = None,
) -> AgentProfile:
    kwargs: dict[str, object] = {
        "agent_id": agent_id,
        "display_name": agent_id,
        "model": "test-model",
        "cwd": ".",
        "skills": skills or [],
    }
    if skill_selection is not None:
        kwargs["skill_selection"] = skill_selection
    return AgentProfile(**kwargs)


def test_agent_profile_legacy_skills_become_selected_skill_selection() -> None:
    profile = _agent("agent-a", skills=["alpha", "beta"])

    assert profile.skill_selection.mode == "selected"
    assert profile.skill_selection.skill_hashes == ["alpha", "beta"]
    assert profile.skills == ["alpha", "beta"]


def test_registry_resolves_skill_selection_modes(tmp_path: Path) -> None:
    reg = _registry(
        tmp_path,
        {
            "none": _agent("none"),
            "all": _agent("all", skill_selection={"mode": "all"}),
            "selected": _agent(
                "selected",
                skill_selection={"mode": "selected", "skill_hashes": ["beta"]},
            ),
            "upstream": _agent("upstream", skill_selection={"mode": "upstream"}),
        },
    )

    assert reg.resolve_agent_skill_names("none") == []
    assert reg.resolve_agent_skill_names("all") == ["alpha", "beta"]
    assert reg.resolve_agent_skill_names("selected") == ["beta"]
    assert reg.resolve_agent_skill_names("upstream") == []

    assert reg.build_skill_catalog("none") == ""
    assert "| `alpha` |" in reg.build_skill_catalog("all")
    assert "| `beta` |" in reg.build_skill_catalog("all")
    assert "| `beta` |" in reg.build_skill_catalog("selected")
    assert reg.build_skill_catalog("upstream") == ""


def test_show_registry_response_includes_skill_selection(tmp_path: Path) -> None:
    reg = _registry(
        tmp_path,
        {
            "all": _agent("all", skill_selection={"mode": "all"}),
            "upstream": _agent("upstream", skill_selection={"mode": "upstream"}),
        },
    )

    response = show_registry_response(reg)
    agents = {item["agent_id"]: item for item in response["agents"]}

    assert agents["all"]["skill_selection"] == {"mode": "all"}
    assert [item["name"] for item in agents["all"]["skills"]] == ["alpha", "beta"]
    assert agents["upstream"]["skill_selection"] == {"mode": "upstream"}
    assert agents["upstream"]["skills"] == []
