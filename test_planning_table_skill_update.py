from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from multi_agent_tcp.planning_table_skill_update import (
    discover_skill_candidates,
    mark_processed,
    scan_for_updates,
)


def _write_skill(path: Path, name: str, description: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                "---",
                "",
                f"# {name}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_discover_skill_candidates_supports_skill_md_and_legacy_skill(tmp_path: Path) -> None:
    root = tmp_path / "AISkills"
    _write_skill(root / "fill-one", "fill-one", "配置活动表。")
    legacy_dir = root / "table-occupy"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "table-occupy.skill").write_text(
        "---\nname: table-occupy\ndescription: 占用策划表格。\n---\n",
        encoding="utf-8",
    )
    (root / "not-skill").mkdir()
    index = root / "planning-table-skill-index.md"
    index.write_text(f"- existing：{root / 'fill-one' / 'SKILL.md'}\n", encoding="utf-8")

    candidates = discover_skill_candidates(root, index_path=index)

    by_name = {item.name: item for item in candidates}
    assert sorted(by_name) == ["fill-one", "table-occupy"]
    assert by_name["fill-one"].file_kind == "SKILL.md"
    assert by_name["fill-one"].indexed is True
    assert by_name["table-occupy"].file_kind == "*.skill"
    assert by_name["table-occupy"].description == "占用策划表格。"


def test_scan_first_seeds_then_notifies_new_skill_and_marks_processed(tmp_path: Path) -> None:
    root = tmp_path / "AISkills"
    _write_skill(root / "existing", "existing", "已存在 skill。")
    index = root / "planning-table-skill-index.md"
    index.write_text("# index\n", encoding="utf-8")
    state = tmp_path / "state.json"
    outbox = tmp_path / "notifications.jsonl"
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):  # noqa: ANN001, ANN003
        commands.append([str(item) for item in command])
        return SimpleNamespace(returncode=0, stdout="updated to revision 1", stderr="")

    first = scan_for_updates(
        state_path=state,
        notification_path=outbox,
        skill_root=root,
        index_path=index,
        svn_update=False,
        now=lambda: 1_780_000_100.0,
    )

    assert first["seeded"] is True
    assert first["notifications"] == []
    assert not outbox.exists()

    _write_skill(root / "new-fill", "new-fill", "新增填表 skill。")
    second = scan_for_updates(
        state_path=state,
        notification_path=outbox,
        skill_root=root,
        index_path=index,
        svn_update=True,
        run_command=fake_run,
        now=lambda: 1_780_000_200.0,
    )

    assert second["seeded"] is False
    assert second["pendingCount"] == 1
    assert commands == [["svn", "update", str(root.resolve())]]
    lines = outbox.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["candidateCount"] == 1
    assert event["candidates"][0]["name"] == "new-fill"

    processed = mark_processed(
        state_path=state,
        notification_id=event["notificationId"],
        now=lambda: 1_780_000_300.0,
    )
    assert processed["pendingCount"] == 0

    third = scan_for_updates(
        state_path=state,
        notification_path=outbox,
        skill_root=root,
        index_path=index,
        svn_update=False,
        now=lambda: 1_780_000_400.0,
    )
    assert third["notifications"] == []
    assert len(outbox.read_text(encoding="utf-8").splitlines()) == 1
