"""Headless graph runtime primitives for persistent Agent nodes."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .client import AgentTCPClient
from .cluster import WorkerConfig

log = logging.getLogger(__name__)


EnvelopeKind = str
EnvelopeEncoding = str
AgentExecutionMode = str
GraphEventType = str
SkillSelectionMode = str
BlueprintTerminalKind = str

_VALID_ENVELOPE_KINDS = {"text", "image", "audio", "file", "blob"}
_VALID_ENVELOPE_ENCODINGS = {"inline", "fileref", "blobref"}
_VALID_EXECUTION_MODES = {"blocking", "nonblocking"}
_VALID_ROUTE_KINDS = {"sequence", "parallel", "parallel_reduce"}
_VALID_SKILL_SELECTION_MODES = {"none", "all", "selected", "upstream"}
_VALID_BLUEPRINT_TERMINAL_KINDS = {"start", "end"}


def generate_agent_node_id() -> str:
    """Generate a framework-owned AgentNode id."""
    return f"agent-node-{uuid.uuid4().hex[:12]}"


@dataclass
class MultiModalEnvelope:
    """Serializable payload passed over graph ports.

    The envelope gives graph edges one stable container for text, images,
    files, and future blob references. It intentionally does not prescribe
    every adapter's internal attachment format.
    """

    kind: EnvelopeKind
    value: Any
    mime: Optional[str] = None
    encoding: EnvelopeEncoding = "inline"
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in _VALID_ENVELOPE_KINDS:
            raise ValueError(f"unsupported envelope kind: {self.kind!r}")
        if self.encoding not in _VALID_ENVELOPE_ENCODINGS:
            raise ValueError(f"unsupported envelope encoding: {self.encoding!r}")
        if not isinstance(self.meta, dict):
            raise ValueError("MultiModalEnvelope.meta must be an object")

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "kind": self.kind,
            "encoding": self.encoding,
            "value": self.value,
            "meta": dict(self.meta),
        }
        if self.mime is not None:
            data["mime"] = self.mime
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MultiModalEnvelope":
        if not isinstance(data, dict):
            raise ValueError("MultiModalEnvelope data must be an object")
        if "kind" not in data:
            raise ValueError("MultiModalEnvelope.kind is required")
        return cls(
            kind=str(data["kind"]),
            value=data.get("value"),
            mime=str(data["mime"]) if data.get("mime") is not None else None,
            encoding=str(data.get("encoding", "inline")),
            meta=dict(data.get("meta", {})),
        )

    @classmethod
    def text(cls, value: str, *, meta: Optional[Dict[str, Any]] = None) -> "MultiModalEnvelope":
        return cls(kind="text", mime="text/plain", value=value, meta=meta or {})


def normalize_envelope(value: Any) -> MultiModalEnvelope:
    """Convert common graph values into a MultiModalEnvelope."""
    if isinstance(value, MultiModalEnvelope):
        return value
    if isinstance(value, dict) and "kind" in value and "value" in value:
        return MultiModalEnvelope.from_dict(value)
    if isinstance(value, Path):
        return MultiModalEnvelope(
            kind="file",
            encoding="fileref",
            value=str(value),
            meta={"path": str(value)},
        )
    if isinstance(value, str):
        return MultiModalEnvelope.text(value)
    return MultiModalEnvelope(
        kind="blob",
        value=json.dumps(value, ensure_ascii=False),
        mime="application/json",
        encoding="inline",
        meta={"python_type": type(value).__name__},
    )


@dataclass
class GraphEvent:
    """Runtime event emitted by graph execution primitives."""

    event_type: GraphEventType
    job_id: Optional[str] = None
    node_id: Optional[str] = None
    agent_id: Optional[str] = None
    status: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"event_type": self.event_type}
        if self.job_id is not None:
            data["job_id"] = self.job_id
        if self.node_id is not None:
            data["node_id"] = self.node_id
        if self.agent_id is not None:
            data["agent_id"] = self.agent_id
        if self.status is not None:
            data["status"] = self.status
        if self.payload:
            data["payload"] = dict(self.payload)
        return data


@dataclass
class WorkspaceManifest:
    """Append-only manifest for graph jobs sharing a workspace."""

    workspace_id: str
    workspace_root: Path
    jobs: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root).expanduser()

    def _path_within_root(self, raw_path: str) -> bool:
        root = self.workspace_root.resolve()
        path = Path(raw_path)
        if not path.is_absolute():
            path = root / path
        try:
            path.resolve().relative_to(root)
            return True
        except ValueError:
            return False

    def validate_scopes(
        self,
        *,
        read_scope: Optional[Sequence[str]] = None,
        write_scope: Optional[Sequence[str]] = None,
        artifact_scope: Optional[Sequence[str]] = None,
    ) -> None:
        for scope_name, scope in (
            ("read_scope", read_scope or []),
            ("write_scope", write_scope or []),
            ("artifact_scope", artifact_scope or []),
        ):
            for raw in scope:
                if not self._path_within_root(str(raw)):
                    raise ValueError(f"{scope_name} path escapes workspace_root: {raw}")

    def record_job(self, job: "GraphJob") -> None:
        self.validate_scopes(
            read_scope=job.read_scope,
            write_scope=job.write_scope,
            artifact_scope=job.artifact_scope,
        )
        self.jobs[job.job_id] = job.to_manifest_entry()

    def update_job(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        result: Any = None,
        error: Optional[str] = None,
        changed_files: Optional[Sequence[str]] = None,
        artifacts: Optional[Sequence[str]] = None,
    ) -> None:
        if job_id not in self.jobs:
            raise KeyError(f"unknown job_id: {job_id}")
        entry = self.jobs[job_id]
        if status is not None:
            entry["status"] = status
        if result is not None:
            entry["result"] = result
        if error is not None:
            entry["error"] = error
        if changed_files is not None:
            entry["changed_files"] = [str(p) for p in changed_files]
        if artifacts is not None:
            entry["artifacts"] = [str(p) for p in artifacts]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "workspace_root": str(self.workspace_root),
            "jobs": dict(self.jobs),
        }

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


@dataclass
class GraphJob:
    """Background job submitted by a nonblocking AgentNode."""

    job_id: str
    node_id: str
    agent_id: str
    body: Any
    status: str = "queued"
    workspace_id: Optional[str] = None
    workspace_root: Optional[Path] = None
    read_scope: List[str] = field(default_factory=list)
    write_scope: List[str] = field(default_factory=list)
    artifact_scope: List[str] = field(default_factory=list)

    def to_manifest_entry(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "job_id": self.job_id,
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "status": self.status,
            "read_scope": list(self.read_scope),
            "write_scope": list(self.write_scope),
            "artifact_scope": list(self.artifact_scope),
        }
        if self.workspace_id is not None:
            data["workspace_id"] = self.workspace_id
        if self.workspace_root is not None:
            data["workspace_root"] = str(self.workspace_root)
        return data


@dataclass
class AgentSkillSelection:
    """User-facing skill choice for an AgentNode.

    Modes:
    - ``none``: no skills are exposed.
    - ``all``: expose every skill visible in the current SkillSpace.
    - ``selected``: expose the explicitly selected skill hashes.
    - ``upstream``: accept hashes assigned by an upstream super agent.
    """

    mode: SkillSelectionMode = "none"
    skill_hashes: List[str] = field(default_factory=list)
    assigned_by: Optional[str] = None

    def __post_init__(self) -> None:
        self.mode = str(self.mode or "none").strip().lower()
        if self.mode not in _VALID_SKILL_SELECTION_MODES:
            raise ValueError(
                "AgentSkillSelection.mode must be one of "
                + ", ".join(sorted(_VALID_SKILL_SELECTION_MODES))
            )
        self.skill_hashes = [str(h).strip() for h in self.skill_hashes if str(h).strip()]
        if self.mode in {"none", "all"} and self.skill_hashes:
            raise ValueError(f"AgentSkillSelection.{self.mode} must not set skill_hashes")
        if self.mode == "selected" and not self.skill_hashes:
            raise ValueError("AgentSkillSelection.selected requires non-empty skill_hashes")

    @classmethod
    def from_value(cls, value: Any, *, legacy_skills: Optional[Sequence[str]] = None) -> "AgentSkillSelection":
        legacy = [str(s) for s in (legacy_skills or [])]
        if value is None:
            if legacy:
                return cls(mode="selected", skill_hashes=legacy)
            return cls()
        if isinstance(value, str):
            return cls(mode=value)
        if not isinstance(value, dict):
            raise ValueError("AgentNode.skill_selection must be an object or string")
        raw_hashes = value.get("skill_hashes", value.get("skills", []))
        if raw_hashes is None:
            raw_hashes = []
        if not isinstance(raw_hashes, list):
            raise ValueError("AgentSkillSelection.skill_hashes must be a list")
        return cls(
            mode=str(value.get("mode", "selected" if raw_hashes else "none")),
            skill_hashes=[str(h) for h in raw_hashes],
            assigned_by=(
                str(value["assigned_by"]).strip()
                if value.get("assigned_by") is not None
                else None
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"mode": self.mode}
        if self.skill_hashes:
            data["skill_hashes"] = list(self.skill_hashes)
        if self.assigned_by is not None:
            data["assigned_by"] = self.assigned_by
        return data

    def resolve_hashes(
        self,
        skill_space: Any,
        *,
        upstream_super_agent: Any = None,
        upstream_skill_hashes: Optional[Sequence[str]] = None,
    ) -> List[str]:
        """Resolve selected skill hashes and validate them against SkillSpace.

        ``upstream`` mode requires an upstream super-agent profile with
        ``validate_assignment``. This keeps ordinary upstream agents from
        assigning downstream skills.
        """
        if self.mode == "none":
            return []
        if self.mode == "all":
            return sorted(skill_space.records().keys())
        if self.mode == "selected":
            skill_space.resolve_hashes(self.skill_hashes)
            return list(self.skill_hashes)
        if self.mode == "upstream":
            if upstream_super_agent is None or not hasattr(upstream_super_agent, "validate_assignment"):
                raise PermissionError(
                    "upstream skill assignment requires a SuperAgentProfile"
                )
            hashes = [str(h) for h in (upstream_skill_hashes or self.skill_hashes)]
            upstream_super_agent.validate_assignment(hashes, skill_space)
            return hashes
        raise ValueError(f"unsupported skill selection mode: {self.mode!r}")


@dataclass
class AgentNode:
    """Serializable configuration for one blueprint Agent node."""

    node_id: str = field(default_factory=generate_agent_node_id)
    agent_id: Optional[str] = None
    execution_mode: AgentExecutionMode = "blocking"
    cli_kind: str = "codemaker"
    model: str = "netease-codemaker/kimi-k2.5"
    cwd: Path = Path(".")
    skills: List[str] = field(default_factory=list)
    skill_selection: AgentSkillSelection = field(default_factory=AgentSkillSelection)
    timeout_sec: float = 1800.0
    prompt_via_file: str = "auto"
    command: str = "codemaker"
    adapter_options: Dict[str, Any] = field(default_factory=dict)
    extra_env: Dict[str, str] = field(default_factory=dict)
    external: bool = False
    workspace_id: Optional[str] = None
    workspace_root: Optional[Path] = None
    read_scope: List[str] = field(default_factory=list)
    write_scope: List[str] = field(default_factory=list)
    artifact_scope: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not str(self.node_id).strip():
            self.node_id = generate_agent_node_id()
        else:
            self.node_id = str(self.node_id).strip()
        if self.execution_mode not in _VALID_EXECUTION_MODES:
            raise ValueError(
                "AgentNode.execution_mode must be 'blocking' or 'nonblocking'"
            )
        if not isinstance(self.skill_selection, AgentSkillSelection):
            self.skill_selection = AgentSkillSelection.from_value(
                self.skill_selection,
                legacy_skills=self.skills,
            )
        if not self.skills and self.skill_selection.mode == "selected":
            self.skills = list(self.skill_selection.skill_hashes)
        self.cwd = Path(self.cwd).expanduser()
        if self.workspace_root is not None:
            self.workspace_root = Path(self.workspace_root).expanduser()

    @property
    def runtime_agent_id(self) -> str:
        return self.agent_id or self.node_id

    def to_worker_config(self) -> WorkerConfig:
        return WorkerConfig(
            agent_id=self.runtime_agent_id,
            cwd=self.cwd,
            model=self.model,
            timeout_sec=self.timeout_sec,
            prompt_via_file=self.prompt_via_file,
            command=self.command,
            cli_kind=self.cli_kind,
            adapter_options=dict(self.adapter_options),
            extra_env=dict(self.extra_env),
        )

    def resolve_skill_hashes(
        self,
        skill_space: Any,
        *,
        upstream_super_agent: Any = None,
        upstream_skill_hashes: Optional[Sequence[str]] = None,
    ) -> List[str]:
        return self.skill_selection.resolve_hashes(
            skill_space,
            upstream_super_agent=upstream_super_agent,
            upstream_skill_hashes=upstream_skill_hashes,
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "node_id": self.node_id,
            "execution_mode": self.execution_mode,
            "cli_kind": self.cli_kind,
            "model": self.model,
            "cwd": str(self.cwd),
            "skills": list(self.skills),
            "skill_selection": self.skill_selection.to_dict(),
            "timeout_sec": self.timeout_sec,
            "prompt_via_file": self.prompt_via_file,
            "command": self.command,
            "adapter_options": dict(self.adapter_options),
            "extra_env": dict(self.extra_env),
            "external": self.external,
            "read_scope": list(self.read_scope),
            "write_scope": list(self.write_scope),
            "artifact_scope": list(self.artifact_scope),
        }
        if self.agent_id is not None:
            data["agent_id"] = self.agent_id
        if self.workspace_id is not None:
            data["workspace_id"] = self.workspace_id
        if self.workspace_root is not None:
            data["workspace_root"] = str(self.workspace_root)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentNode":
        node_id = data.get("node_id")
        if node_id is not None and (not isinstance(node_id, str) or not node_id.strip()):
            raise ValueError("AgentNode.node_id must be a non-empty string when set")
        raw_cwd = data.get("cwd", ".")
        skills = data.get("skills", [])
        if not isinstance(skills, list):
            raise ValueError("AgentNode.skills must be a list")
        skill_selection = AgentSkillSelection.from_value(
            data.get("skill_selection"),
            legacy_skills=skills,
        )
        adapter_options = data.get("adapter_options", {})
        if not isinstance(adapter_options, dict):
            raise ValueError("AgentNode.adapter_options must be an object")
        extra_env = data.get("extra_env", {})
        if not isinstance(extra_env, dict):
            raise ValueError("AgentNode.extra_env must be an object")
        for scope_key in ("read_scope", "write_scope", "artifact_scope"):
            if not isinstance(data.get(scope_key, []), list):
                raise ValueError(f"AgentNode.{scope_key} must be a list")
        return cls(
            node_id=node_id.strip() if isinstance(node_id, str) else generate_agent_node_id(),
            agent_id=str(data["agent_id"]).strip() if data.get("agent_id") else None,
            execution_mode=str(data.get("execution_mode", "blocking")),
            cli_kind=str(data.get("cli_kind", "codemaker")),
            model=str(data.get("model", "netease-codemaker/kimi-k2.5")),
            cwd=Path(str(raw_cwd)).expanduser(),
            skills=[str(s) for s in skills],
            skill_selection=skill_selection,
            timeout_sec=float(data.get("timeout_sec", 1800.0)),
            prompt_via_file=str(data.get("prompt_via_file", "auto")),
            command=str(data.get("command", "codemaker")),
            adapter_options=dict(adapter_options),
            extra_env={str(k): str(v) for k, v in extra_env.items()},
            external=bool(data.get("external", False)),
            workspace_id=(
                str(data["workspace_id"]) if data.get("workspace_id") is not None else None
            ),
            workspace_root=(
                Path(str(data["workspace_root"])).expanduser()
                if data.get("workspace_root") is not None
                else None
            ),
            read_scope=[str(s) for s in data.get("read_scope", [])],
            write_scope=[str(s) for s in data.get("write_scope", [])],
            artifact_scope=[str(s) for s in data.get("artifact_scope", [])],
        )


@dataclass
class AgentInstance:
    """Runtime binding between an AgentNode and a broker-registered agent."""

    node: AgentNode
    agent_id: str
    external: bool = False
    messages_sent: int = 0


class GraphRuntime:
    """Maintain AgentNode instance bindings for one blueprint run.

    This class deliberately treats cluster methods as message dispatch
    primitives. It does not imply that an Agent node is spawned and torn down
    for each traversal.
    """

    def __init__(
        self,
        cluster: Any,
        *,
        workspace: Optional[WorkspaceManifest] = None,
    ) -> None:
        self.cluster = cluster
        self.workspace = workspace
        self._instances: Dict[str, AgentInstance] = {}
        self._jobs: Dict[str, GraphJob] = {}
        self._events: List[GraphEvent] = []
        self._closed = False

    @property
    def instances(self) -> Dict[str, AgentInstance]:
        return dict(self._instances)

    @property
    def jobs(self) -> Dict[str, GraphJob]:
        return dict(self._jobs)

    @property
    def events(self) -> List[GraphEvent]:
        return list(self._events)

    def _emit(self, event: GraphEvent) -> GraphEvent:
        self._events.append(event)
        return event

    async def ensure_agent(self, node: AgentNode) -> AgentInstance:
        if self._closed:
            raise RuntimeError("GraphRuntime is closed")
        if node.node_id in self._instances:
            return self._instances[node.node_id]

        agent_id = node.runtime_agent_id
        ensure_worker = getattr(self.cluster, "ensure_worker", None)
        if callable(ensure_worker) and not node.external:
            await ensure_worker(node.to_worker_config())
        self._instances[node.node_id] = AgentInstance(
            node=node,
            agent_id=agent_id,
            external=node.external,
        )
        log.info(
            "[graph] bound node_id=%s agent_id=%s cli_kind=%s external=%s",
            node.node_id,
            agent_id,
            node.cli_kind,
            node.external,
        )
        return self._instances[node.node_id]

    async def send_agent_message(
        self,
        node: AgentNode,
        body: Any,
        *,
        timeout_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        if node.execution_mode == "nonblocking":
            job = await self.submit_agent_job(node, body, timeout_sec=timeout_sec)
            return {
                "type": "graph_job_submitted",
                "job_id": job.job_id,
                "node_id": job.node_id,
                "agent_id": job.agent_id,
                "status": job.status,
            }
        inst = await self.ensure_agent(node)
        reply = await self.cluster.run_single(
            inst.agent_id,
            body,
            timeout_sec=timeout_sec if timeout_sec is not None else node.timeout_sec,
        )
        inst.messages_sent += 1
        return reply

    async def submit_agent_job(
        self,
        node: AgentNode,
        body: Any,
        *,
        timeout_sec: Optional[float] = None,
        job_id: Optional[str] = None,
        start: bool = True,
    ) -> GraphJob:
        """Submit a nonblocking AgentNode job and return immediately.

        The first implementation records a manifest entry and schedules an
        asyncio task in the current process. It provides the event/job contract
        without introducing distributed leases or worktree merging yet.
        """
        inst = await self.ensure_agent(node)
        job = GraphJob(
            job_id=job_id or f"job-{uuid.uuid4().hex[:12]}",
            node_id=node.node_id,
            agent_id=inst.agent_id,
            body=body,
            workspace_id=node.workspace_id,
            workspace_root=node.workspace_root,
            read_scope=list(node.read_scope),
            write_scope=list(node.write_scope),
            artifact_scope=list(node.artifact_scope),
        )
        if self.workspace is not None:
            self.workspace.record_job(job)
        self._jobs[job.job_id] = job
        self._emit(
            GraphEvent(
                "TaskStarted",
                job_id=job.job_id,
                node_id=node.node_id,
                agent_id=inst.agent_id,
                status=job.status,
                payload={"execution_mode": "nonblocking"},
            )
        )
        if start:
            asyncio.create_task(self._run_agent_job(job, node, body, timeout_sec=timeout_sec))
        return job

    async def _run_agent_job(
        self,
        job: GraphJob,
        node: AgentNode,
        body: Any,
        *,
        timeout_sec: Optional[float] = None,
    ) -> None:
        job.status = "running"
        if self.workspace is not None:
            self.workspace.update_job(job.job_id, status=job.status)
        self._emit(
            GraphEvent(
                "TaskProgress",
                job_id=job.job_id,
                node_id=job.node_id,
                agent_id=job.agent_id,
                status=job.status,
            )
        )
        try:
            reply = await self.cluster.run_single(
                job.agent_id,
                body,
                timeout_sec=timeout_sec if timeout_sec is not None else node.timeout_sec,
            )
        except Exception as exc:  # pragma: no cover - defensive event contract
            job.status = "failed"
            if self.workspace is not None:
                self.workspace.update_job(job.job_id, status=job.status, error=str(exc))
            self._emit(
                GraphEvent(
                    "TaskFailed",
                    job_id=job.job_id,
                    node_id=job.node_id,
                    agent_id=job.agent_id,
                    status=job.status,
                    payload={"error": str(exc)},
                )
            )
            return

        job.status = "completed"
        inst = self._instances.get(node.node_id)
        if inst is not None:
            inst.messages_sent += 1
        if self.workspace is not None:
            self.workspace.update_job(job.job_id, status=job.status, result=reply)
        self._emit(
            GraphEvent(
                "TaskCompleted",
                job_id=job.job_id,
                node_id=job.node_id,
                agent_id=job.agent_id,
                status=job.status,
                payload={"result": reply},
            )
        )

    async def close(self) -> None:
        """Detach runtime bindings.

        Process teardown is delegated to the owning cluster. External agent
        bindings are never killed here.
        """
        if self._closed:
            return
        log.info("[graph] closing runtime instances=%s", list(self._instances))
        self._instances.clear()
        self._closed = True

    async def __aenter__(self) -> "GraphRuntime":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()


class BrokerAgentRuntime:
    """Lightweight runtime for graphs that talk to an existing broker."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        self_id: Optional[str] = None,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.self_id = self_id or f"graph-runtime-{uuid.uuid4().hex[:8]}"
        self._client: Optional[AgentTCPClient] = None

    async def _ensure_client(self) -> AgentTCPClient:
        if self._client is not None:
            return self._client
        client = AgentTCPClient(self.self_id, self.host, self.port, role="graph-runtime")
        await client.connect()
        self._client = client
        return client

    async def run_single(
        self,
        worker_id: str,
        body: Any,
        *,
        timeout_sec: float = 600.0,
        _skip_skill_inject: bool = False,
    ) -> Dict[str, Any]:
        client = await self._ensure_client()
        await client.send_to(worker_id, body)
        return await client.wait_for_message(expect_from=worker_id, timeout_sec=timeout_sec)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None


@dataclass
class RouteNode:
    """Minimal declarative route node for DAG compilation."""

    node_id: str
    route_kind: str
    targets: List[str] = field(default_factory=list)
    reduce_target: Optional[str] = None
    reduce_prompt: Optional[str] = None

    def __post_init__(self) -> None:
        if self.route_kind not in _VALID_ROUTE_KINDS:
            raise ValueError(f"unsupported route_kind: {self.route_kind!r}")
        if self.route_kind == "parallel_reduce" and not self.reduce_target:
            raise ValueError("parallel_reduce RouteNode requires reduce_target")


@dataclass
class BlueprintTerminalNode:
    """Start/end marker node for runnable visual blueprints."""

    node_id: str
    terminal_kind: BlueprintTerminalKind

    def __post_init__(self) -> None:
        self.node_id = str(self.node_id).strip()
        self.terminal_kind = str(self.terminal_kind).strip().lower()
        if not self.node_id:
            raise ValueError("BlueprintTerminalNode.node_id must be non-empty")
        if self.terminal_kind not in _VALID_BLUEPRINT_TERMINAL_KINDS:
            raise ValueError(
                "BlueprintTerminalNode.terminal_kind must be 'start' or 'end'"
            )


@dataclass
class GraphEdge:
    """Directed edge between graph nodes."""

    source: str
    target: str
    output_port: Optional[str] = None
    input_port: Optional[str] = None
    edge_type: Optional[str] = None

    def __post_init__(self) -> None:
        self.source = str(self.source).strip()
        self.target = str(self.target).strip()
        if not self.source:
            raise ValueError("GraphEdge.source must be non-empty")
        if not self.target:
            raise ValueError("GraphEdge.target must be non-empty")
        if self.output_port is not None:
            self.output_port = str(self.output_port).strip() or None
        if self.input_port is not None:
            self.input_port = str(self.input_port).strip() or None
        if self.edge_type is not None:
            self.edge_type = str(self.edge_type).strip().lower() or None

    @property
    def is_exec_edge(self) -> bool:
        """Return whether this edge participates in control-flow execution."""

        return self.edge_type in (None, "exec")


@dataclass
class GraphDefinition:
    """Small DAG container used before a visual editor exists."""

    agent_nodes: Dict[str, AgentNode] = field(default_factory=dict)
    route_nodes: Dict[str, RouteNode] = field(default_factory=dict)
    terminal_nodes: Dict[str, BlueprintTerminalNode] = field(default_factory=dict)
    edges: List[GraphEdge] = field(default_factory=list)

    def _node_ids(self) -> set[str]:
        agent_ids = set()
        for key, node in self.agent_nodes.items():
            if key != node.node_id:
                raise ValueError(
                    f"agent node key {key!r} does not match node_id {node.node_id!r}"
                )
            agent_ids.add(node.node_id)

        route_ids = set()
        for key, node in self.route_nodes.items():
            if key != node.node_id:
                raise ValueError(
                    f"route node key {key!r} does not match node_id {node.node_id!r}"
                )
            route_ids.add(node.node_id)

        terminal_ids = set()
        for key, node in self.terminal_nodes.items():
            if key != node.node_id:
                raise ValueError(
                    f"terminal node key {key!r} does not match node_id {node.node_id!r}"
                )
            terminal_ids.add(node.node_id)
        return agent_ids | route_ids | terminal_ids

    def _adjacency(self, node_ids: set[str], *, exec_only: bool = False) -> Dict[str, List[str]]:
        adjacency: Dict[str, List[str]] = {node_id: [] for node_id in node_ids}
        for edge in self.edges:
            if exec_only and not edge.is_exec_edge:
                continue
            adjacency[edge.source].append(edge.target)
        return adjacency

    def validate_dag(self) -> None:
        node_ids = self._node_ids()
        for edge in self.edges:
            if edge.source not in node_ids:
                raise ValueError(f"unknown edge source: {edge.source}")
            if edge.target not in node_ids:
                raise ValueError(f"unknown edge target: {edge.target}")

        adjacency = self._adjacency(node_ids)
        indegree: Dict[str, int] = {node_id: 0 for node_id in node_ids}
        for edge in self.edges:
            indegree[edge.target] += 1

        ready = [node_id for node_id, degree in indegree.items() if degree == 0]
        visited = 0
        while ready:
            node_id = ready.pop()
            visited += 1
            for target in adjacency[node_id]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
        if visited != len(node_ids):
            raise ValueError("graph contains a cycle; DAG execution requires acyclic edges")

    def validate_runnable(self) -> None:
        """Validate the stricter visual-blueprint run contract.

        A runnable blueprint must be a DAG, must contain exactly one start
        terminal and one end terminal, and must have a directed path from start
        to end.
        """

        self.validate_dag()

        starts = [
            node.node_id
            for node in self.terminal_nodes.values()
            if node.terminal_kind == "start"
        ]
        ends = [
            node.node_id
            for node in self.terminal_nodes.values()
            if node.terminal_kind == "end"
        ]
        if len(starts) != 1:
            raise ValueError("runnable graph requires exactly one start node")
        if len(ends) != 1:
            raise ValueError("runnable graph requires exactly one end node")

        start_id = starts[0]
        end_id = ends[0]
        adjacency = self._adjacency(self._node_ids(), exec_only=True)
        seen = {start_id}
        stack = [start_id]
        while stack:
            node_id = stack.pop()
            if node_id == end_id:
                return
            for target in adjacency[node_id]:
                if target not in seen:
                    seen.add(target)
                    stack.append(target)

        raise ValueError("runnable graph requires a directed path from start to end")


class GraphExecutor:
    """Minimal DAG/route executor over existing cluster primitives."""

    def __init__(self, runtime: GraphRuntime) -> None:
        self.runtime = runtime

    async def run_route(
        self,
        route: RouteNode,
        tasks: Sequence[tuple[str, Any]],
        *,
        timeout_sec: float = 600.0,
    ) -> Any:
        if route.route_kind == "sequence":
            if hasattr(self.runtime.cluster, "run_chain"):
                return await self.runtime.cluster.run_chain(
                    list(tasks),
                    timeout_sec=timeout_sec,
                )
            results = []
            for worker_id, body in tasks:
                results.append(
                    await self.runtime.cluster.run_single(
                        worker_id,
                        body,
                        timeout_sec=timeout_sec,
                    )
                )
            return results

        if route.route_kind == "parallel":
            if not hasattr(self.runtime.cluster, "run_parallel"):
                raise RuntimeError("cluster does not provide run_parallel")
            return await self.runtime.cluster.run_parallel(
                list(tasks),
                timeout_sec=timeout_sec,
            )

        if route.route_kind == "parallel_reduce":
            if not hasattr(self.runtime.cluster, "run_parallel_reduce"):
                raise RuntimeError("cluster does not provide run_parallel_reduce")
            assert route.reduce_target is not None
            return await self.runtime.cluster.run_parallel_reduce(
                list(tasks),
                reduce_worker=route.reduce_target,
                reduce_prompt=route.reduce_prompt or "",
                timeout_sec=timeout_sec,
            )

        raise ValueError(f"unsupported route_kind: {route.route_kind!r}")
