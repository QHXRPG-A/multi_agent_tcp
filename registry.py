"""Agents registry: load / query / resolve agents & skills configuration.

The registry is a JSON file (``agents_registry.json``) that lists available
agent profiles. Each profile specifies model, cwd, skills, etc.

**Skill loading strategy** — *catalog + on-demand read*:

Instead of stuffing full SKILL.md contents into every prompt (expensive,
doesn't scale), we inject a lightweight **skill catalog** (~50 chars/skill)
into the prompt. The catalog tells the agent the skill name, one-line
description, and absolute file path.  The agent uses its ``read`` tool to
load any skill it actually needs during execution.

Typical usage::

    reg = AgentsRegistry.load()
    prompt = reg.inject_skills_into_prompt("agent-1", "Fix the export bug")
    # prompt now has ~500-char catalog, not 12K of full skill content
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cluster import WorkerConfig
from .graph_runtime import AgentSkillSelection

log = logging.getLogger(__name__)

_MODULE_DIR = Path(__file__).resolve().parent
_DEFAULT_REGISTRY = _MODULE_DIR / "agents_registry.json"
_DEFAULT_SKILL_LIST = _MODULE_DIR / "skill_list"
_SESSIONS_DIR = _MODULE_DIR / "sessions"
_SESSION_TTL_SEC = 3600.0  # 1 hour


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------

@dataclass
class SkillInfo:
    """Lightweight metadata for one skill (no full content)."""

    name: str
    description: str
    skill_md_path: Path
    file_count: int = 1

    @property
    def skill_dir(self) -> Path:
        return self.skill_md_path.parent


@dataclass
class AgentProfile:
    """One entry in the agents registry."""

    agent_id: str
    display_name: str
    model: str
    cwd: str
    skills: List[str] = field(default_factory=list)
    skill_selection: AgentSkillSelection = field(default_factory=AgentSkillSelection)
    timeout_sec: float = 1800.0
    enabled: bool = True
    cli_kind: str = "codemaker"
    adapter_options: Dict[str, Any] = field(default_factory=dict)
    extra_env: Dict[str, str] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.skills = [str(s).strip() for s in self.skills if str(s).strip()]
        if not isinstance(self.skill_selection, AgentSkillSelection):
            self.skill_selection = AgentSkillSelection.from_value(
                self.skill_selection,
                legacy_skills=self.skills,
            )
        elif self.skills and self.skill_selection.mode == "none":
            self.skill_selection = AgentSkillSelection.from_value(
                None,
                legacy_skills=self.skills,
            )
        if self.skill_selection.mode == "selected":
            self.skills = list(self.skill_selection.skill_hashes)
        else:
            self.skills = []

    def to_worker_config(self) -> WorkerConfig:
        return WorkerConfig(
            agent_id=self.agent_id,
            cwd=Path(self.cwd),
            model=self.model,
            timeout_sec=self.timeout_sec,
            cli_kind=self.cli_kind,
            adapter_options=dict(self.adapter_options),
            extra_env=dict(self.extra_env),
        )


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------

class AgentsRegistry:
    """Load and query the agents configuration table."""

    def __init__(
        self,
        agents: Dict[str, AgentProfile],
        skill_list_dir: Path,
        skill_manifest: Dict[str, SkillInfo],
        raw: Dict[str, Any],
    ) -> None:
        self.agents = agents
        self.skill_list_dir = skill_list_dir
        self.skill_manifest = skill_manifest
        self._raw = raw
        self._skill_cache: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "AgentsRegistry":
        path = path or _DEFAULT_REGISTRY
        if not path.is_file():
            raise FileNotFoundError(f"agents registry not found: {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        skill_dir_str = raw.get("skill_list_dir", "skill_list")
        skill_list_dir = (_MODULE_DIR / skill_dir_str).resolve()

        manifest = cls._load_manifest(skill_list_dir)

        agents: Dict[str, AgentProfile] = {}
        for aid, cfg in raw.get("agents", {}).items():
            skill_selection = AgentSkillSelection.from_value(
                cfg.get("skill_selection"),
                legacy_skills=cfg.get("skills", []),
            )
            selected_skills = (
                list(skill_selection.skill_hashes)
                if skill_selection.mode == "selected"
                else []
            )
            agents[aid] = AgentProfile(
                agent_id=aid,
                display_name=cfg.get("display_name", aid),
                model=cfg.get("model", "netease-codemaker/kimi-k2.5"),
                cwd=cfg.get("cwd", str(_MODULE_DIR.parent)),
                skills=selected_skills,
                skill_selection=skill_selection,
                timeout_sec=cfg.get("timeout_sec", 1800.0),
                enabled=cfg.get("enabled", True),
                cli_kind=cfg.get("cli_kind", "codemaker"),
                adapter_options=cfg.get("adapter_options", {}),
                extra_env={str(k): str(v) for k, v in cfg.get("extra_env", {}).items()},
                extra={k: v for k, v in cfg.items()
                       if k not in ("display_name", "model", "cwd", "skills",
                                    "skill_selection", "timeout_sec", "enabled",
                                    "cli_kind", "adapter_options", "extra_env")},
            )
        return cls(agents, skill_list_dir, manifest, raw)

    @staticmethod
    def _load_manifest(skill_list_dir: Path) -> Dict[str, SkillInfo]:
        """Build SkillInfo dict from manifest.json + filesystem."""
        manifest_path = skill_list_dir / "manifest.json"
        meta: Dict[str, Any] = {}
        if manifest_path.is_file():
            meta = json.loads(manifest_path.read_text(encoding="utf-8"))

        result: Dict[str, SkillInfo] = {}
        if not skill_list_dir.is_dir():
            return result
        for child in sorted(skill_list_dir.iterdir()):
            skill_md = child / "SKILL.md"
            if not child.is_dir() or not skill_md.is_file():
                continue
            entry = meta.get(child.name, {})
            desc = entry.get("description", "")
            if not desc:
                for line in skill_md.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        desc = stripped.lstrip("# ").strip()[:120]
                        break
            result[child.name] = SkillInfo(
                name=child.name,
                description=desc,
                skill_md_path=skill_md.resolve(),
                file_count=entry.get("file_count", 1),
            )
        return result

    # ------------------------------------------------------------------
    # Skill queries
    # ------------------------------------------------------------------

    def read_skill(self, skill_name: str) -> str:
        """Read the SKILL.md content for a skill name. Cached."""
        if skill_name in self._skill_cache:
            return self._skill_cache[skill_name]
        info = self.skill_manifest.get(skill_name)
        if info is None:
            raise FileNotFoundError(f"skill not found in manifest: {skill_name}")
        content = info.skill_md_path.read_text(encoding="utf-8")
        self._skill_cache[skill_name] = content
        return content

    def get_skill_info(self, skill_name: str) -> SkillInfo:
        info = self.skill_manifest.get(skill_name)
        if info is None:
            raise KeyError(f"skill {skill_name!r} not in manifest")
        return info

    def list_available_skills(self) -> List[str]:
        """Return sorted list of skill names in skill_list/."""
        return sorted(self.skill_manifest.keys())

    def resolve_agent_skill_names(self, agent_id: str) -> List[str]:
        """Resolve an agent's skill selection to registry skill names.

        Registry skill identifiers are the names in ``skill_list/manifest.json``.
        They are stored in ``AgentSkillSelection.skill_hashes`` for parity with
        the graph runtime model, which uses hashes inside ``SkillSpace``.
        ``upstream`` is resolved by the graph runtime, so it has no static
        registry prompt injection.
        """
        prof = self.agents.get(agent_id)
        if prof is None:
            return []
        selection = prof.skill_selection
        if selection.mode == "none":
            return []
        if selection.mode == "all":
            return self.list_available_skills()
        if selection.mode == "selected":
            return list(selection.skill_hashes or prof.skills)
        if selection.mode == "upstream":
            return []
        return []

    # ------------------------------------------------------------------
    # Catalog-based skill preamble (lightweight, agent reads on-demand)
    # ------------------------------------------------------------------

    def build_skill_catalog(self, agent_id: str) -> str:
        """Build a compact skill catalog for prompt injection.

        Instead of embedding full SKILL.md content (~3-10K chars each),
        this produces a table (~50 chars/skill) with file paths so the
        agent can ``read`` any skill it needs on-demand.
        """
        skills = self.resolve_agent_skill_names(agent_id)
        if not skills:
            return ""

        lines: List[str] = [
            "# Your Registered Skills\n",
            "You have the following skills available. **Before starting a task, "
            "check if any skill is relevant. If so, read the SKILL.md file first, "
            "then follow its instructions.**\n",
            "| Skill | Description | SKILL.md Path |",
            "|-------|-------------|---------------|",
        ]

        valid_count = 0
        for sname in skills:
            info = self.skill_manifest.get(sname)
            if info is None:
                log.warning("skill %r not in manifest, skipping", sname)
                continue
            path_str = str(info.skill_md_path).replace("\\", "/")
            lines.append(f"| `{sname}` | {info.description} | `{path_str}` |")
            valid_count += 1

        if valid_count == 0:
            return ""

        lines.append("")
        lines.append(
            f"Total: {valid_count} skill(s). "
            "Use the `read` tool to load the full SKILL.md when needed. "
            "Skills may reference additional files in their directory."
        )
        return "\n".join(lines)

    def build_skill_preamble_full(self, agent_id: str) -> str:
        """Build a full-content preamble (legacy, for small skill counts).

        Prefer ``build_skill_catalog()`` for >=2 skills.
        """
        skills = self.resolve_agent_skill_names(agent_id)
        if not skills:
            return ""
        sep = "\n\n" + "=" * 60 + "\n"
        parts: List[str] = [
            "# Registered Skills",
            "The following skills are loaded for this session. "
            "Use them when relevant to the task.\n",
        ]
        for sname in skills:
            try:
                content = self.read_skill(sname)
                parts.append(f"## Skill: {sname}{sep}{content}")
            except FileNotFoundError:
                log.warning("skill %r not found in skill_list, skipping", sname)
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Agent / worker queries
    # ------------------------------------------------------------------

    def build_worker_configs(
        self,
        agent_ids: Optional[List[str]] = None,
    ) -> List[WorkerConfig]:
        """Convert selected (or all enabled) agents to WorkerConfig list."""
        if agent_ids is None:
            agent_ids = [aid for aid, p in self.agents.items() if p.enabled]
        configs: List[WorkerConfig] = []
        for aid in agent_ids:
            prof = self.agents.get(aid)
            if prof is None:
                raise KeyError(f"agent_id {aid!r} not in registry")
            if not prof.enabled:
                log.warning("agent %r is disabled, skipping", aid)
                continue
            configs.append(prof.to_worker_config())
        return configs

    def get_agent(self, agent_id: str) -> AgentProfile:
        prof = self.agents.get(agent_id)
        if prof is None:
            raise KeyError(f"agent_id {agent_id!r} not in registry")
        return prof

    def list_agents(self, enabled_only: bool = True) -> List[AgentProfile]:
        agents = list(self.agents.values())
        if enabled_only:
            agents = [a for a in agents if a.enabled]
        return agents

    # ------------------------------------------------------------------
    # Prompt helpers
    # ------------------------------------------------------------------

    def inject_skills_into_prompt(
        self,
        agent_id: str,
        task_prompt: str,
        *,
        mode: str = "catalog",
    ) -> str:
        """Prepend skill info to a task prompt.

        Args:
            mode: ``"catalog"`` (default) — lightweight table + file paths,
                  agent reads on-demand.
                  ``"full"`` — embed full SKILL.md content (legacy, expensive).
        """
        if mode == "full":
            preamble = self.build_skill_preamble_full(agent_id)
        else:
            preamble = self.build_skill_catalog(agent_id)

        if not preamble:
            return task_prompt
        return f"{preamble}\n\n{'=' * 60}\n# Task\n\n{task_prompt}"

    # ------------------------------------------------------------------
    # Session-gated agent dispatch
    # ------------------------------------------------------------------

    def create_session(self) -> "AgentSession":
        """Generate a 5-digit session ID, snapshot available agents, persist to disk.

        The LLM must call this (via ``list-agents``) before ``run-agent``.
        The returned session_id proves it actually checked the registry.
        """
        _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self._cleanup_expired_sessions()

        session_id = str(random.randint(10000, 99999))
        while (_SESSIONS_DIR / f"{session_id}.json").exists():
            session_id = str(random.randint(10000, 99999))

        enabled = [a for a in self.agents.values() if a.enabled]
        snapshot: Dict[str, Any] = {}
        for a in enabled:
            skill_descs = []
            for sname in self.resolve_agent_skill_names(a.agent_id):
                info = self.skill_manifest.get(sname)
                skill_descs.append({
                    "name": sname,
                    "description": info.description if info else "(unknown)",
                })
            snapshot[a.agent_id] = {
                "display_name": a.display_name,
                "cli_kind": a.cli_kind,
                "model": a.model,
                "skill_selection": a.skill_selection.to_dict(),
                "skills": skill_descs,
                "cwd": a.cwd,
                "timeout_sec": a.timeout_sec,
            }

        session = AgentSession(
            session_id=session_id,
            created_at=time.time(),
            available_agents=snapshot,
        )
        session.save()
        log.info("session created: %s with %d agents", session_id, len(snapshot))
        return session

    @staticmethod
    def validate_session(session_id: str, agent_id: str) -> "AgentSession":
        """Load a session file, verify it's valid and the agent_id is in it.

        Raises ``ValueError`` on any validation failure.
        """
        path = _SESSIONS_DIR / f"{session_id}.json"
        if not path.is_file():
            raise ValueError(
                f"Session {session_id} not found. "
                f"You must call `list-agents` first to get a valid session_id."
            )
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            raise ValueError(f"Session file corrupted: {e}") from e

        session = AgentSession(
            session_id=raw["session_id"],
            created_at=raw["created_at"],
            available_agents=raw["available_agents"],
        )

        age = time.time() - session.created_at
        if age > _SESSION_TTL_SEC:
            path.unlink(missing_ok=True)
            raise ValueError(
                f"Session {session_id} expired ({age:.0f}s old, TTL={_SESSION_TTL_SEC:.0f}s). "
                f"Call `list-agents` again to get a fresh session_id."
            )

        if agent_id not in session.available_agents:
            valid = list(session.available_agents.keys())
            raise ValueError(
                f"Agent '{agent_id}' is not in session {session_id}. "
                f"Available agents: {valid}"
            )

        return session

    @staticmethod
    def _cleanup_expired_sessions() -> None:
        """Remove session files older than TTL."""
        if not _SESSIONS_DIR.is_dir():
            return
        now = time.time()
        for f in _SESSIONS_DIR.glob("*.json"):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                if now - raw.get("created_at", 0) > _SESSION_TTL_SEC:
                    f.unlink(missing_ok=True)
            except (json.JSONDecodeError, OSError, KeyError):
                f.unlink(missing_ok=True)


@dataclass
class AgentSession:
    """A session token generated by ``list-agents``, consumed by ``run-agent``."""

    session_id: str
    created_at: float
    available_agents: Dict[str, Any]

    def save(self) -> Path:
        _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        path = _SESSIONS_DIR / f"{self.session_id}.json"
        path.write_text(
            json.dumps({
                "session_id": self.session_id,
                "created_at": self.created_at,
                "available_agents": self.available_agents,
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def to_list_response(self) -> Dict[str, Any]:
        """Format the response for LLM consumption."""
        agents_list = []
        for aid, info in self.available_agents.items():
            agents_list.append({
                "agent_id": aid,
                **info,
            })
        return {
            "session_id": self.session_id,
            "message": (
                f"Found {len(agents_list)} available agent(s). "
                f"Use session_id '{self.session_id}' with `run-agent` to launch one."
            ),
            "agents": agents_list,
        }


def show_registry_response(reg: "AgentsRegistry") -> Dict[str, Any]:
    """Build a read-only response listing all enabled agents.

    Unlike ``list-agents`` this creates **no** session file and has no
    side-effects.  Designed for the LLM to discover available agents
    before calling ``dispatch``.
    """
    agents_out: List[Dict[str, Any]] = []
    for prof in reg.list_agents(enabled_only=True):
        skill_descs = []
        for sname in reg.resolve_agent_skill_names(prof.agent_id):
            info = reg.skill_manifest.get(sname)
            skill_descs.append({
                "name": sname,
                "description": info.description if info else "(unknown)",
            })
        agents_out.append({
            "agent_id": prof.agent_id,
            "display_name": prof.display_name,
            "cli_kind": prof.cli_kind,
            "model": prof.model,
            "skill_selection": prof.skill_selection.to_dict(),
            "skills": skill_descs,
            "cwd": prof.cwd,
            "timeout_sec": prof.timeout_sec,
        })
    return {
        "count": len(agents_out),
        "message": (
            f"{len(agents_out)} agent(s) available. "
            "Use `dispatch` with agent_id + prompt pairs to run tasks."
        ),
        "agents": agents_out,
    }
