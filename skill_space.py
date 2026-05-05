"""Hashed skill-space and per-agent skill view primitives."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.is_file():
        return dict(default)
    return json.loads(path.read_text(encoding="utf-8"))


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _skill_hash(skill_name: str, skill_dir: Path) -> str:
    skill_md = skill_dir / "SKILL.md"
    h = hashlib.sha256()
    h.update(skill_name.encode("utf-8"))
    h.update(b"\0")
    h.update(str(skill_dir.resolve()).encode("utf-8"))
    h.update(b"\0")
    if skill_md.is_file():
        h.update(skill_md.read_bytes())
    return h.hexdigest()[:16]


def _description_from_skill(skill_md: Path) -> str:
    if not skill_md.is_file():
        return ""
    text = _read_text(skill_md)
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                stripped = line.strip()
                if stripped.startswith("description:"):
                    return stripped.split(":", 1)[1].strip().strip("\"'")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("# ").strip()[:120]
    return ""


@dataclass
class SkillRecord:
    """Private skill-space record known to the framework."""

    skill_hash: str
    name: str
    description: str
    skill_dir: Path
    skill_md_path: Path

    def to_private_dict(self) -> Dict[str, Any]:
        return {
            "hash": self.skill_hash,
            "name": self.name,
            "description": self.description,
            "skill_dir": str(self.skill_dir),
            "skill_md_path": str(self.skill_md_path),
        }

    def to_agent_catalog_row(self, exposed_path: Path) -> Dict[str, str]:
        return {
            "hash": self.skill_hash,
            "name": self.name,
            "description": self.description,
            "skill_md_path": str(exposed_path),
        }


@dataclass
class AgentSkillView:
    """Per-agent independent directory with copied authorized skills."""

    agent_id: str
    root: Path
    skills_dir: Path
    cache_dir: Path
    skill_hashes: List[str] = field(default_factory=list)
    catalog: List[Dict[str, str]] = field(default_factory=list)

    def context(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_workspace": str(self.root),
            "agent_cache_dir": str(self.cache_dir),
            "agent_skills_dir": str(self.skills_dir),
            "skill_hashes": list(self.skill_hashes),
            "skills": list(self.catalog),
        }

    def catalog_prompt(self) -> str:
        if not self.catalog:
            return ""
        lines = [
            "# Authorized Skills",
            "",
            "Only the skills listed here are available for this agent. "
            "Use the listed SKILL.md paths; do not infer or search for other skills.",
            "",
            "| Hash | Skill | Description | SKILL.md Path |",
            "|------|-------|-------------|---------------|",
        ]
        for row in self.catalog:
            lines.append(
                f"| `{row['hash']}` | `{row['name']}` | {row['description']} | `{row['skill_md_path']}` |"
            )
        return "\n".join(lines)

    def codex_execution_context(self) -> Dict[str, Any]:
        """Return the Codex-facing context for this isolated skill view."""
        return {
            **self.context(),
            "skill_catalog": list(self.catalog),
        }

    def codex_adapter_options(self) -> Dict[str, Any]:
        """Build adapter options that expose only this agent's authorized skills."""
        options: Dict[str, Any] = {
            "execution_context": self.codex_execution_context(),
        }
        prompt = self.catalog_prompt()
        if prompt:
            options["prompt_preamble"] = prompt
        return options


class SkillSpace:
    """Project skill-space that maps opaque hashes to real skill directories."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.skills_root = self.root / "skills"
        self.manifest_path = self.root / "manifest.json"
        self._records: Dict[str, SkillRecord] = {}

    @classmethod
    def open_or_init(cls, root: Path) -> "SkillSpace":
        space = cls(root)
        space.root.mkdir(parents=True, exist_ok=True)
        space.skills_root.mkdir(parents=True, exist_ok=True)
        space.refresh()
        return space

    def refresh(self) -> Dict[str, SkillRecord]:
        records: Dict[str, SkillRecord] = {}
        if self.skills_root.is_dir():
            for child in sorted(self.skills_root.iterdir()):
                skill_md = child / "SKILL.md"
                if not child.is_dir() or not skill_md.is_file():
                    continue
                name = child.name
                skill_hash = _skill_hash(name, child)
                records[skill_hash] = SkillRecord(
                    skill_hash=skill_hash,
                    name=name,
                    description=_description_from_skill(skill_md),
                    skill_dir=child.resolve(),
                    skill_md_path=skill_md.resolve(),
                )
        self._records = records
        _write_json(
            self.manifest_path,
            {
                "schema_version": 1,
                "records": {
                    h: rec.to_private_dict()
                    for h, rec in sorted(records.items())
                },
            },
        )
        return dict(records)

    def records(self) -> Dict[str, SkillRecord]:
        if not self._records:
            self.refresh()
        return dict(self._records)

    def add_skill_copy(self, source_skill_dir: Path, *, name: Optional[str] = None) -> SkillRecord:
        source = Path(source_skill_dir).resolve()
        skill_md = source / "SKILL.md"
        if not skill_md.is_file():
            raise FileNotFoundError(f"skill directory missing SKILL.md: {source}")
        skill_name = name or source.name
        target = self.skills_root / skill_name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        self.refresh()
        for rec in self._records.values():
            if rec.name == skill_name:
                return rec
        raise RuntimeError(f"failed to add skill to skill space: {skill_name}")

    def resolve_hashes(self, skill_hashes: Sequence[str]) -> List[SkillRecord]:
        records = self.records()
        out: List[SkillRecord] = []
        for h in skill_hashes:
            key = str(h).strip()
            rec = records.get(key)
            if rec is None:
                raise KeyError(f"skill hash not found in skill space: {key}")
            if not _path_within(rec.skill_dir, self.skills_root):
                raise ValueError(f"skill path escapes skill space: {rec.skill_dir}")
            out.append(rec)
        return out

    def materialize_for_agent(
        self,
        *,
        agent_id: str,
        agent_root: Path,
        skill_hashes: Sequence[str],
    ) -> AgentSkillView:
        root = Path(agent_root).resolve()
        skills_dir = root / "skills"
        cache_dir = root / "cache"
        root.mkdir(parents=True, exist_ok=True)
        if skills_dir.exists():
            shutil.rmtree(skills_dir)
        skills_dir.mkdir(parents=True)
        cache_dir.mkdir(parents=True, exist_ok=True)

        catalog: List[Dict[str, str]] = []
        resolved = self.resolve_hashes(skill_hashes)
        for rec in resolved:
            exposed_dir = skills_dir / rec.skill_hash
            shutil.copytree(rec.skill_dir, exposed_dir)
            exposed_skill_md = exposed_dir / "SKILL.md"
            catalog.append(rec.to_agent_catalog_row(exposed_skill_md))

        view = AgentSkillView(
            agent_id=agent_id,
            root=root,
            skills_dir=skills_dir,
            cache_dir=cache_dir,
            skill_hashes=[rec.skill_hash for rec in resolved],
            catalog=catalog,
        )
        _write_json(root / "agent_workspace.json", view.context())
        return view


@dataclass
class SuperAgentProfile:
    """Minimal super-agent permission model."""

    agent_id: str
    can_view_skill_space: bool = True
    can_assign_downstream_skills: bool = True
    assignable_skill_hashes: Optional[List[str]] = None

    def validate_assignment(self, skill_hashes: Sequence[str], skill_space: SkillSpace) -> None:
        if not self.can_assign_downstream_skills:
            raise PermissionError(f"super agent {self.agent_id!r} cannot assign skills")
        skill_space.resolve_hashes(skill_hashes)
        if self.assignable_skill_hashes is None:
            return
        allowed = set(self.assignable_skill_hashes)
        denied = [str(h) for h in skill_hashes if str(h) not in allowed]
        if denied:
            raise PermissionError(
                f"super agent {self.agent_id!r} cannot assign skill hashes: {denied}"
            )

    def visible_skill_catalog(self, skill_space: SkillSpace) -> List[Dict[str, str]]:
        if not self.can_view_skill_space:
            return []
        records = skill_space.records()
        allowed = set(self.assignable_skill_hashes or records.keys())
        return [
            {
                "hash": rec.skill_hash,
                "name": rec.name,
                "description": rec.description,
            }
            for h, rec in sorted(records.items())
            if h in allowed
        ]
