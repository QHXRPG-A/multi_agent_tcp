"""Headless graph runtime primitives for persistent Agent nodes."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from .blueprint_script_nodes import ScriptNodePort
from .client import AgentTCPClient
from .cluster import WorkerConfig

log = logging.getLogger(__name__)


EnvelopeKind = str
EnvelopeEncoding = str
AgentExecutionMode = str
GraphEventType = str
SkillSelectionMode = str
BlueprintTerminalKind = str
AgentRuntimeState = str
TopAgentRunPermission = str
JoinPolicy = str
RunLifecycleStatus = str
RunFinalStatus = str
AgentNodeType = str
CommonNodeKind = str
BlueprintPortDataType = str
PromptNodeTrigger = str

_VALID_ENVELOPE_KINDS = {"text", "image", "audio", "file", "blob"}
_VALID_ENVELOPE_ENCODINGS = {"inline", "fileref", "blobref"}
_VALID_EXECUTION_MODES = {"blocking", "nonblocking"}
_VALID_ROUTE_KINDS = {"sequence", "parallel", "parallel_reduce"}
_VALID_COMMON_NODE_KINDS = {"branch", "tick"}
_VALID_BLUEPRINT_PORT_DATA_TYPES = {"message", "bool", "tick", "str"}
_VALID_PROMPT_NODE_TRIGGERS = {"once", "always"}
_VALID_SKILL_SELECTION_MODES = {"none", "all", "selected", "upstream"}
_VALID_BLUEPRINT_TERMINAL_KINDS = {"start", "end"}
_VALID_TOP_AGENT_RUN_PERMISSIONS = {"ask", "start", "status", "end", "utterances", "fixture"}
_VALID_JOIN_POLICIES = {"wait-all", "wait-any", "quorum"}
_VALID_RUN_END_ACTIONS = {"complete", "cancel", "fail", "pause", "archive_only"}
_VALID_AGENT_NODE_TYPES = {"agent", "worker_agent"}
_AGENT_CAN_ACCEPT_STATES = {"idle", "queued", "timed_out"}
_VALID_AGENT_TASK_STATUSES = {"not_started", "working", "completed", "blocked", "needs_input", "failed"}
_TERMINAL_AGENT_TASK_STATUSES = {"completed", "blocked", "needs_input", "failed"}
DEFAULT_AGENT_WRITE_SCOPE = ["**"]
LEGACY_REPORT_ONLY_WRITE_SCOPE = ["shared/reports/**"]
COMPLETION_IDLE_THRESHOLD_SEC = 30.0
AGENT_RUN_PROMPT_HEADER = "# Agent Run Prompt"
BLUEPRINT_PROMPT_HEADER_PREFIX = "# Blueprint Prompt:"
AGENT_PROMPT_INPUT_PORT = "prompt"
DEFAULT_OUTPUT_PORT = "out"
DEFAULT_AGENT_ACCESS_POLICY = {
    "direct_project_io": True,
    "outside_project_io": True,
    "unrestricted_commands": True,
    "disable_sandbox": True,
    "framework_message_tools": True,
}
DEFAULT_WORKER_AGENT_ACCESS_POLICY = {
    "direct_project_io": False,
    "outside_project_io": False,
    "unrestricted_commands": False,
    "disable_sandbox": False,
    "framework_message_tools": True,
}
_VALID_AGENT_RUNTIME_STATES = {
    "created",
    "starting",
    "idle",
    "queued",
    "dispatching",
    "running",
    "waiting_for_reply",
    "processing_reply",
    "completed",
    "failed",
    "timed_out",
    "cancelled",
    "disconnected",
    "restarting",
    "stopping",
    "stopped",
}


def _default_agent_write_scope() -> List[str]:
    return list(DEFAULT_AGENT_WRITE_SCOPE)


def _normalize_agent_write_scope(value: Any, *, default: Optional[Sequence[str]] = None) -> List[str]:
    scope = [str(s) for s in (value if value is not None else (default or []))]
    if scope == LEGACY_REPORT_ONLY_WRITE_SCOPE:
        return _default_agent_write_scope()
    return scope


def _normalize_agent_node_type(value: Any) -> AgentNodeType:
    return "agent" if str(value or "").strip() == "agent" else "worker_agent"


def _normalize_agent_access_policy(value: Any, node_type: AgentNodeType) -> Dict[str, bool]:
    defaults = (
        DEFAULT_AGENT_ACCESS_POLICY
        if node_type == "agent"
        else DEFAULT_WORKER_AGENT_ACCESS_POLICY
    )
    if not isinstance(value, dict):
        return dict(defaults)
    return {
        key: bool(value.get(key, default))
        for key, default in defaults.items()
    }


def is_dispatch_no_op_body(body: Any) -> bool:
    """Return whether a structured dispatch body is an explicit target no-op."""
    return body == "" or (type(body) is int and body == 0)


def _prepend_prompt_sections_to_body(
    body: Any,
    sections: Sequence[tuple[str, str]],
) -> tuple[Any, bool]:
    prompt_sections = [
        (str(header).strip(), str(text or "").strip())
        for header, text in sections
        if str(header).strip() and str(text or "").strip()
    ]
    if not prompt_sections or is_dispatch_no_op_body(body):
        return body, False
    prefix = "\n\n".join(f"{header}\n\n{text}" for header, text in prompt_sections)
    if isinstance(body, dict):
        prompt = body.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return body, False
        return {
            **body,
            "prompt": f"{prefix}\n\n---\n\n{prompt}",
        }, True
    if isinstance(body, str) and body.strip():
        return f"{prefix}\n\n---\n\n{body}", True
    return body, False


def _prepend_agent_run_prompt_to_body(body: Any, run_prompt: str) -> tuple[Any, bool]:
    return _prepend_prompt_sections_to_body(body, [(AGENT_RUN_PROMPT_HEADER, run_prompt)])


def is_framework_summary_request_body(body: Any) -> bool:
    return isinstance(body, dict) and body.get("type") == "framework_summary_request"


def _reply_failure_reason(reply: Any) -> Optional[str]:
    """Return a concise failure reason when a worker reply is explicitly failed."""
    if not isinstance(reply, dict):
        return None
    if reply.get("type") == "error":
        return str(reply.get("error") or reply.get("message") or "worker returned error")
    body = reply.get("body")
    if not isinstance(body, dict):
        return None
    if body.get("ok") is not False:
        return None
    for key in ("error", "message"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("codex",):
        payload = body.get(key)
        if not isinstance(payload, dict):
            continue
        if payload.get("timeout"):
            return f"{key} timed out"
        for nested_key in ("stderr", "final_text", "last_message", "stdout"):
            value = payload.get(nested_key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return f"{key} returned non-zero exit status"
    return "worker returned ok=false"


class AgentMessageFailed(RuntimeError):
    """A worker handled the message but reported this turn as failed."""


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
class AgentUtterance:
    """Framework-private minimal record extracted from a worker reply."""

    utterance_id: str
    agent_id: str
    node_id: str
    said: str
    received_at: float
    task_id: Optional[str] = None
    message_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "utterance_id": self.utterance_id,
            "agent_id": self.agent_id,
            "node_id": self.node_id,
            "said": self.said,
            "received_at": self.received_at,
        }
        if self.task_id is not None:
            data["task_id"] = self.task_id
        if self.message_id is not None:
            data["message_id"] = self.message_id
        return data


@dataclass
class RuntimeMessageRecord:
    """Durable audit record for framework/Agent message IO."""

    record_id: str
    record_type: str
    sender: Dict[str, Any]
    receiver: Dict[str, Any]
    payload: Any = None
    message_id: Optional[str] = None
    batch_id: Optional[str] = None
    join_id: Optional[str] = None
    utterance_id: Optional[str] = None
    status: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    recorded_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "record_id": self.record_id,
            "record_type": self.record_type,
            "sender": dict(self.sender),
            "receiver": dict(self.receiver),
            "recorded_at": self.recorded_at,
        }
        if self.payload is not None:
            data["payload"] = self.payload
        if self.message_id is not None:
            data["message_id"] = self.message_id
        if self.batch_id is not None:
            data["batch_id"] = self.batch_id
        if self.join_id is not None:
            data["join_id"] = self.join_id
        if self.utterance_id is not None:
            data["utterance_id"] = self.utterance_id
        if self.status is not None:
            data["status"] = self.status
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data


@dataclass
class WorkspaceManifest:
    """Append-only manifest for graph jobs sharing a workspace."""

    workspace_id: str
    workspace_root: Path
    jobs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    run: Dict[str, Any] = field(default_factory=dict)

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

    def record_run_start(
        self,
        *,
        top_agent: Dict[str, Any],
        start_plan: Dict[str, Any],
        organization: Dict[str, Any],
        queued_messages: Sequence[Dict[str, Any]],
    ) -> None:
        self.run["start"] = {
            "top_agent": dict(top_agent),
            "start_plan": dict(start_plan),
            "organization": dict(organization),
            "queued_messages": [dict(message) for message in queued_messages],
            "started_at": time.monotonic(),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "workspace_root": str(self.workspace_root),
            "run": dict(self.run),
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
    node_type: AgentNodeType = "worker_agent"
    agent_id: Optional[str] = None
    prompt: str = ""
    run_prompt: str = ""
    execution_mode: AgentExecutionMode = "blocking"
    cli_kind: str = "codex"
    model: str = "gpt-5.4"
    cwd: Path = Path(".")
    skills: List[str] = field(default_factory=list)
    skill_selection: AgentSkillSelection = field(default_factory=AgentSkillSelection)
    rule_paths: List[str] = field(default_factory=list)
    timeout_sec: float = 1800.0
    prompt_via_file: str = "auto"
    command: str = "codex"
    adapter_options: Dict[str, Any] = field(default_factory=dict)
    extra_env: Dict[str, str] = field(default_factory=dict)
    external: bool = False
    workspace_id: Optional[str] = None
    workspace_root: Optional[Path] = None
    read_scope: List[str] = field(default_factory=list)
    write_scope: List[str] = field(default_factory=list)
    artifact_scope: List[str] = field(default_factory=list)
    access_policy: Dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.node_id).strip():
            self.node_id = generate_agent_node_id()
        else:
            self.node_id = str(self.node_id).strip()
        self.node_type = _normalize_agent_node_type(self.node_type)
        if self.execution_mode not in _VALID_EXECUTION_MODES:
            raise ValueError(
                "AgentNode.execution_mode must be 'blocking' or 'nonblocking'"
            )
        self.access_policy = _normalize_agent_access_policy(self.access_policy, self.node_type)
        if not isinstance(self.skill_selection, AgentSkillSelection):
            self.skill_selection = AgentSkillSelection.from_value(
                self.skill_selection,
                legacy_skills=self.skills,
            )
        if not self.skills and self.skill_selection.mode == "selected":
            self.skills = list(self.skill_selection.skill_hashes)
        self.rule_paths = [str(path).strip() for path in self.rule_paths if str(path).strip()]
        self.cwd = Path(self.cwd).expanduser()
        if self.workspace_root is not None:
            self.workspace_root = Path(self.workspace_root).expanduser()

    @property
    def runtime_agent_id(self) -> str:
        return self.agent_id or self.node_id

    def to_worker_config(self) -> WorkerConfig:
        adapter_options = dict(self.adapter_options)
        adapter_options["node_type"] = self.node_type
        adapter_options["access_policy"] = dict(self.access_policy)
        return WorkerConfig(
            agent_id=self.runtime_agent_id,
            cwd=self.cwd,
            model=self.model,
            timeout_sec=self.timeout_sec,
            prompt_via_file=self.prompt_via_file,
            command=self.command,
            cli_kind=self.cli_kind,
            adapter_options=adapter_options,
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
            "node_type": self.node_type,
            "prompt": self.prompt,
            "run_prompt": self.run_prompt,
            "execution_mode": self.execution_mode,
            "cli_kind": self.cli_kind,
            "model": self.model,
            "cwd": str(self.cwd),
            "skills": list(self.skills),
            "skill_selection": self.skill_selection.to_dict(),
            "rule_paths": list(self.rule_paths),
            "timeout_sec": self.timeout_sec,
            "prompt_via_file": self.prompt_via_file,
            "command": self.command,
            "adapter_options": dict(self.adapter_options),
            "extra_env": dict(self.extra_env),
            "external": self.external,
            "read_scope": list(self.read_scope),
            "write_scope": list(self.write_scope),
            "artifact_scope": list(self.artifact_scope),
            "access_policy": dict(self.access_policy),
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
        node_type = _normalize_agent_node_type(data.get("node_type"))
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
        raw_cli_kind = data.get("cli_kind")
        if raw_cli_kind is None:
            cli_kind = "codex"
        else:
            cli_kind = str(raw_cli_kind)
        raw_model = data.get("model")
        if raw_model is None:
            model = "gpt-5.4"
        else:
            model = str(raw_model)
        raw_command = data.get("command")
        if raw_command is None:
            command = "codex"
        else:
            command = str(raw_command)
        return cls(
            node_id=node_id.strip() if isinstance(node_id, str) else generate_agent_node_id(),
            node_type=node_type,
            agent_id=str(data["agent_id"]).strip() if data.get("agent_id") else None,
            prompt=str(data.get("prompt", "")),
            run_prompt=str(data.get("run_prompt", "")),
            execution_mode=str(data.get("execution_mode", "blocking")),
            cli_kind=cli_kind,
            model=model,
            cwd=Path(str(raw_cwd)).expanduser(),
            skills=[str(s) for s in skills],
            skill_selection=skill_selection,
            rule_paths=[str(s) for s in data.get("rule_paths", [])],
            timeout_sec=float(data.get("timeout_sec", 1800.0)),
            prompt_via_file=str(data.get("prompt_via_file", "auto")),
            command=command,
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
            write_scope=_normalize_agent_write_scope(
                data.get("write_scope"),
                default=DEFAULT_AGENT_WRITE_SCOPE,
            ),
            artifact_scope=[str(s) for s in data.get("artifact_scope", [])],
            access_policy=_normalize_agent_access_policy(data.get("access_policy"), node_type),
        )


@dataclass
class TopAgentTask:
    """Structured task assigned by the top-level agent to one AgentNode."""

    goal: str
    context_refs: List[str] = field(default_factory=list)
    expected_output: str = ""
    acceptance: str = ""
    downstream_collaboration: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.goal = str(self.goal).strip()
        self.context_refs = [str(ref).strip() for ref in self.context_refs if str(ref).strip()]
        self.expected_output = str(self.expected_output).strip()
        self.acceptance = str(self.acceptance).strip()
        self.downstream_collaboration = str(self.downstream_collaboration).strip()
        if not isinstance(self.metadata, dict):
            raise ValueError("TopAgentTask.metadata must be an object")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TopAgentTask":
        if not isinstance(data, dict):
            raise ValueError("TopAgentTask data must be an object")
        refs = data.get("context_refs", [])
        if refs is None:
            refs = []
        if not isinstance(refs, list):
            raise ValueError("TopAgentTask.context_refs must be a list")
        return cls(
            goal=str(data.get("goal", "")),
            context_refs=[str(ref) for ref in refs],
            expected_output=str(data.get("expected_output", "")),
            acceptance=str(data.get("acceptance", "")),
            downstream_collaboration=str(data.get("downstream_collaboration", "")),
            metadata=dict(data.get("metadata", {})),
        )

    def missing_required_fields(self) -> List[str]:
        missing: List[str] = []
        if not self.goal:
            missing.append("goal")
        if not self.expected_output:
            missing.append("expected_output")
        if not self.acceptance:
            missing.append("acceptance")
        return missing

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "goal": self.goal,
            "context_refs": list(self.context_refs),
            "expected_output": self.expected_output,
            "acceptance": self.acceptance,
        }
        if self.downstream_collaboration:
            data["downstream_collaboration"] = self.downstream_collaboration
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data


@dataclass
class TopAgentStartPlan:
    """Start plan proposed by GuLiCode/top-level agent."""

    user_goal: str
    agent_descriptions: Dict[str, str]
    start_nodes: List[str]
    tasks: Dict[str, TopAgentTask]
    run_policy: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.user_goal = str(self.user_goal).strip()
        self.agent_descriptions = {
            str(node_id).strip(): str(description).strip()
            for node_id, description in self.agent_descriptions.items()
            if str(node_id).strip()
        }
        self.start_nodes = [str(node_id).strip() for node_id in self.start_nodes if str(node_id).strip()]
        self.tasks = {
            str(node_id).strip(): (
                task if isinstance(task, TopAgentTask) else TopAgentTask.from_dict(task)
            )
            for node_id, task in self.tasks.items()
            if str(node_id).strip()
        }
        if not isinstance(self.run_policy, dict):
            raise ValueError("TopAgentStartPlan.run_policy must be an object")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TopAgentStartPlan":
        if not isinstance(data, dict):
            raise ValueError("TopAgentStartPlan data must be an object")
        descriptions = data.get("agent_descriptions", {})
        if not isinstance(descriptions, dict):
            raise ValueError("TopAgentStartPlan.agent_descriptions must be an object")
        start_nodes = data.get("start_nodes", [])
        if not isinstance(start_nodes, list):
            raise ValueError("TopAgentStartPlan.start_nodes must be a list")
        tasks = data.get("tasks", {})
        if not isinstance(tasks, dict):
            raise ValueError("TopAgentStartPlan.tasks must be an object")
        return cls(
            user_goal=str(data.get("user_goal", "")),
            agent_descriptions={str(k): str(v) for k, v in descriptions.items()},
            start_nodes=[str(node_id) for node_id in start_nodes],
            tasks={
                str(node_id): TopAgentTask.from_dict(task)
                for node_id, task in tasks.items()
            },
            run_policy=dict(data.get("run_policy", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_goal": self.user_goal,
            "agent_descriptions": dict(self.agent_descriptions),
            "start_nodes": list(self.start_nodes),
            "tasks": {
                node_id: task.to_dict()
                for node_id, task in self.tasks.items()
            },
            "run_policy": dict(self.run_policy),
        }


@dataclass
class TopAgentPlanValidation:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    normalized_plan: Optional[Dict[str, Any]] = None
    required_start_groups: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "required_start_groups": [dict(group) for group in self.required_start_groups],
        }
        if self.normalized_plan is not None:
            data["normalized_plan"] = dict(self.normalized_plan)
        return data


@dataclass
class GuLiCodeTopAgentProfile:
    """Rule/skill contract for the global GuLiCode coordinator."""

    agent_id: str = "gulicode"
    display_name: str = "GuLiCode"
    cli_kind: str = "codex"
    model: str = "gpt-5.4"
    cwd: Path = Path(".")
    timeout_sec: float = 1800.0
    prompt_via_file: str = "auto"
    command: str = "codex"
    adapter_options: Dict[str, Any] = field(default_factory=dict)
    extra_env: Dict[str, str] = field(default_factory=dict)
    external: bool = False
    allowed_run_permissions: List[TopAgentRunPermission] = field(
        default_factory=lambda: ["ask", "start", "status", "end", "utterances"]
    )
    rule: Optional[str] = None
    skill: Optional[str] = None

    def __post_init__(self) -> None:
        self.agent_id = str(self.agent_id).strip() or "gulicode"
        self.display_name = str(self.display_name).strip() or "GuLiCode"
        self.cli_kind = str(self.cli_kind).strip() or "codex"
        self.model = str(self.model).strip() or "gpt-5.4"
        self.cwd = Path(self.cwd).expanduser()
        self.timeout_sec = float(self.timeout_sec)
        self.prompt_via_file = str(self.prompt_via_file).strip() or "auto"
        self.command = str(self.command).strip() or self.cli_kind
        if not isinstance(self.adapter_options, dict):
            raise ValueError("GuLiCodeTopAgentProfile.adapter_options must be an object")
        if not isinstance(self.extra_env, dict):
            raise ValueError("GuLiCodeTopAgentProfile.extra_env must be an object")
        self.extra_env = {str(k): str(v) for k, v in self.extra_env.items()}
        permissions: List[str] = []
        for permission in self.allowed_run_permissions:
            value = str(permission).strip().lower()
            if value not in _VALID_TOP_AGENT_RUN_PERMISSIONS:
                raise ValueError(f"unsupported top-agent permission: {permission!r}")
            if value not in permissions:
                permissions.append(value)
        self.allowed_run_permissions = permissions
        if self.rule is not None:
            self.rule = str(self.rule).strip() or None
        if self.skill is not None:
            self.skill = str(self.skill).strip() or None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GuLiCodeTopAgentProfile":
        if not isinstance(data, dict):
            raise ValueError("GuLiCodeTopAgentProfile data must be an object")
        raw_permissions = data.get("allowed_run_permissions", data.get("permissions"))
        if raw_permissions is not None and not isinstance(raw_permissions, list):
            raise ValueError("GuLiCodeTopAgentProfile.allowed_run_permissions must be a list")
        permissions = (
            [str(item) for item in raw_permissions]
            if raw_permissions is not None
            else ["ask", "start", "status", "end", "utterances"]
        )
        return cls(
            agent_id=str(data.get("agent_id", "gulicode")),
            display_name=str(data.get("display_name", "GuLiCode")),
            cli_kind=str(data.get("cli_kind", "codex")),
            model=str(data.get("model", "gpt-5.4")),
            cwd=Path(str(data.get("cwd", "."))).expanduser(),
            timeout_sec=float(data.get("timeout_sec", 1800.0)),
            prompt_via_file=str(data.get("prompt_via_file", "auto")),
            command=str(data.get("command", data.get("cli_kind", "codex"))),
            adapter_options=dict(data.get("adapter_options", {})),
            extra_env=dict(data.get("extra_env", {})),
            external=bool(data.get("external", False)),
            allowed_run_permissions=permissions,
            rule=(
                str(data["rule"])
                if data.get("rule") is not None
                else None
            ),
            skill=(
                str(data["skill"])
                if data.get("skill") is not None
                else None
            ),
        )

    @classmethod
    def load(cls, path: Path) -> "GuLiCodeTopAgentProfile":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def to_dict(self, *, include_text: bool = True) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "cli_kind": self.cli_kind,
            "model": self.model,
            "cwd": str(self.cwd),
            "timeout_sec": self.timeout_sec,
            "prompt_via_file": self.prompt_via_file,
            "command": self.command,
            "adapter_options": dict(self.adapter_options),
            "extra_env": dict(self.extra_env),
            "external": self.external,
            "allowed_run_permissions": list(self.allowed_run_permissions),
        }
        if include_text:
            data["rule"] = self.rule_text()
            data["skill"] = self.skill_text()
        else:
            if self.rule is not None:
                data["rule"] = self.rule
            if self.skill is not None:
                data["skill"] = self.skill
        return data

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def runtime_context(self) -> Dict[str, Any]:
        """Return the prompt-facing top-agent context without launch internals."""
        return {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "allowed_run_permissions": list(self.allowed_run_permissions),
            "rule": self.rule_text(),
            "skill": self.skill_text(),
        }

    def rule_text(self) -> str:
        if self.rule is not None:
            return self.rule
        return "\n".join(
            [
                "# GuLiCode Top Agent Rules",
                "",
                "- Read the latest organization view before proposing a start plan.",
                "- You operate inside GuLiCode desktop blueprint planning mode; the desktop app/current chat session is the Top Agent.",
                "- Do not assume, start, or ask for a separate bottom Top Agent CLI/worker.",
                "- Use framework MCP tools for runtime-control planning; do not bypass the GraphRuntimeControlPlane.",
                "- If required information is missing, call `top_agent_request_user_input` with short answerable questions before proposing a plan.",
                "- Produce one concise responsibility description for every AgentNode.",
                "- Choose start_nodes explicitly from the framework's required_start_groups: each source component needs exactly one selected AgentNode, and isolated AgentNodes must be selected.",
                "- Provide one task for every selected start node.",
                "- Each task must include goal, expected_output, and acceptance.",
                "- Validate candidate plans with `runtime_validate_start`, then stage the accepted proposal with `top_agent_stage_start_plan`.",
                "- Do not call `runtime_start`; GuLiCode desktop starts runs only after the user confirms the staged plan.",
                "- Do not modify, persist, or rewrite blueprint graph structure in v1.",
                "- Do not ask ordinary agents to bypass framework workspace, VCS, or message APIs.",
                "- Do not expose private scratch paths, real skill-space paths, tokens, or RPC internals to ordinary agents.",
                "- You may read framework-private Agent utterance records through the dedicated top-agent interface, but do not forward those records into ordinary Agent messages unless the user explicitly asks for a human-facing summary.",
                "- Treat worker reply utterances as private observability records, not as proof of submitted work.",
                "- Explain failures, conflicts, timeouts, or missing permissions instead of pretending success.",
                "- Request end/cancel/pause through the framework; final state aggregation belongs to the framework.",
            ]
        )

    def skill_text(self) -> str:
        if self.skill is not None:
            return self.skill
        return "\n".join(
            [
                "# GuLiCode Top Agent Framework Console",
                "",
                "- Desktop role: GuLiCode desktop/current chat session is the Top Agent; there is no separate bottom Top Agent CLI/worker.",
                "- Organization view: inspect graph, agents, edges, scopes, and agent_connections.",
                "- User input: call `top_agent_request_user_input(questions)` when the plan depends on missing choices or constraints.",
                "- Start plan: draft user_goal, agent_descriptions, start_nodes, tasks, and run_policy; use required_start_groups so every source component has exactly one start node, validate, then stage with `top_agent_stage_start_plan(plan, plan_markdown)`.",
                "- Approval boundary: never call `runtime_start`; the GuLiCode desktop app starts the run after the user approves the staged plan.",
                "- Blueprint boundary: do not edit or save blueprint graph structure in v1.",
                "- Status: read runtime events, agent states, queues, jobs, changesets, conflicts, artifacts, and reports.",
                "- Status explanation: use framework status summaries and recent events; do not infer hidden progress.",
                "- Utterance records: use the dedicated top-agent utterance interface to inspect who said what, when, and for which task/message.",
                "- Messaging: ordinary AgentNode communication is staged, validated, and queued by the framework.",
                "- Ordinary agents receive a per-message framework_context containing outgoing_batch_id, required_outgoing_targets, remaining_targets, scoped organization, and agent.dispatch usage.",
                "- Sending an empty string `\"\"` or numeric `0` with agent.dispatch marks that target as no-op and queues no downstream task.",
                "- Ordinary Agent worker replies are framework-private utterance records and are not automatically passed to other Agents.",
                "- Workspace: source edits use checkout/status/diff/submit/sync; reports and artifacts use publish APIs.",
                "- End control: request complete, cancel, fail, pause, or archive_only; unresolved work remains visible.",
            ]
        )

    def to_agent_node(self) -> AgentNode:
        """Return the framework-owned long-lived GuLiCode worker binding."""

        safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in self.agent_id)
        return AgentNode(
            node_id=f"top-agent-{safe_id}",
            agent_id=self.agent_id,
            prompt="",
            execution_mode="blocking",
            cli_kind=self.cli_kind,
            model=self.model,
            cwd=self.cwd,
            timeout_sec=self.timeout_sec,
            prompt_via_file=self.prompt_via_file,
            command=self.command,
            adapter_options=dict(self.adapter_options),
            extra_env=dict(self.extra_env),
            external=self.external,
        )

    def organization_context(self, graph: "GraphDefinition") -> Dict[str, Any]:
        return {
            "top_agent": self.runtime_context(),
            "organization": graph.agent_organization_summary(),
        }

    def validate_start_plan(
        self,
        graph: "GraphDefinition",
        plan: TopAgentStartPlan,
    ) -> TopAgentPlanValidation:
        errors: List[str] = []
        warnings: List[str] = []
        node_ids = set(graph.agent_nodes)

        if "start" not in self.allowed_run_permissions:
            errors.append(f"top agent {self.agent_id!r} is not allowed to start runs")
        if not plan.user_goal:
            errors.append("user_goal is required")

        description_ids = set(plan.agent_descriptions)
        missing_descriptions = sorted(node_ids - description_ids)
        unknown_descriptions = sorted(description_ids - node_ids)
        if missing_descriptions:
            errors.append(
                "agent_descriptions must cover every AgentNode; missing: "
                + ", ".join(missing_descriptions)
            )
        if unknown_descriptions:
            errors.append(
                "agent_descriptions contains unknown AgentNode ids: "
                + ", ".join(unknown_descriptions)
            )

        start_ids = set(plan.start_nodes)
        tick_source_allowed = not plan.start_nodes and graph.has_tick_source()
        if not plan.start_nodes:
            if not tick_source_allowed:
                errors.append("start_nodes must not be empty")
        unknown_starts = sorted(start_ids - node_ids)
        if unknown_starts:
            errors.append("start_nodes contains unknown AgentNode ids: " + ", ".join(unknown_starts))
        if len(start_ids) != len(plan.start_nodes):
            errors.append("start_nodes must not contain duplicates")
        required_start_groups = graph.required_start_groups()
        valid_source_starts = {
            node_id
            for group in required_start_groups
            for node_id in group.get("node_ids", [])
        }
        invalid_source_starts = sorted((start_ids & node_ids) - valid_source_starts)
        if invalid_source_starts:
            errors.append(
                "start_nodes contains nodes that are not valid source start nodes: "
                + ", ".join(invalid_source_starts)
            )
        for group in required_start_groups:
            if tick_source_allowed:
                break
            group_nodes = [str(node_id) for node_id in group.get("node_ids", [])]
            selected = [node_id for node_id in plan.start_nodes if node_id in set(group_nodes)]
            if not selected:
                errors.append(
                    "start_nodes missing required start group "
                    + str(group.get("group_id"))
                    + ": choose one of "
                    + ", ".join(group_nodes)
                )
            elif len(selected) > 1:
                errors.append(
                    "start_nodes contains multiple nodes from required start group "
                    + str(group.get("group_id"))
                    + ": "
                    + ", ".join(selected)
                )

        task_ids = set(plan.tasks)
        missing_tasks = sorted(start_ids - task_ids)
        extra_tasks = sorted(task_ids - start_ids)
        if missing_tasks:
            errors.append("tasks must include every start node; missing: " + ", ".join(missing_tasks))
        if extra_tasks:
            errors.append("tasks contains entries for non-start nodes: " + ", ".join(extra_tasks))
        for node_id, task in plan.tasks.items():
            missing_fields = task.missing_required_fields()
            if missing_fields:
                errors.append(
                    f"task {node_id!r} missing required fields: " + ", ".join(missing_fields)
                )

        if plan.run_policy.get("allow_parallel") is False and len(plan.start_nodes) > 1:
            warnings.append("run_policy.allow_parallel is false but multiple start_nodes were provided")

        return TopAgentPlanValidation(
            ok=not errors,
            errors=errors,
            warnings=warnings,
            normalized_plan=(
                {**plan.to_dict(), "required_start_groups": required_start_groups}
                if not errors
                else None
            ),
            required_start_groups=required_start_groups,
        )


@dataclass
class AgentInstance:
    """Runtime binding between an AgentNode and a broker-registered agent."""

    node: AgentNode
    agent_id: str
    external: bool = False
    messages_sent: int = 0
    busy_count: int = 0
    state: AgentRuntimeState = "created"
    current_message_id: Optional[str] = None
    last_error: Optional[str] = None
    started_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)
    state_history: List[Dict[str, Any]] = field(default_factory=list)
    has_received_flow: bool = False
    idle_since: Optional[float] = None
    task_status: str = "not_started"
    task_summary: str = ""
    task_status_updated_at: Optional[float] = None
    task_status_message_id: Optional[str] = None
    task_status_batch_id: Optional[str] = None
    task_status_reports: List[Dict[str, Any]] = field(default_factory=list)
    task_status_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    task_status_changesets: List[Dict[str, Any]] = field(default_factory=list)
    task_status_next_actions: List[str] = field(default_factory=list)
    task_status_metadata: Dict[str, Any] = field(default_factory=dict)
    summary_prompted_at: Optional[float] = None
    summary_prompt_message_id: Optional[str] = None
    run_prompt_injected: bool = False
    prompt_node_injected_ids: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.set_state(self.state)

    @property
    def can_accept_message(self) -> bool:
        return self.busy_count == 0 and self.state in _AGENT_CAN_ACCEPT_STATES

    def set_state(
        self,
        state: AgentRuntimeState,
        *,
        error: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> None:
        if state not in _VALID_AGENT_RUNTIME_STATES:
            raise ValueError(f"unsupported agent runtime state: {state!r}")
        old_state = self.state
        self.state = state
        self.updated_at = time.monotonic()
        self.last_error = error
        if message_id is not None or state == "idle":
            self.current_message_id = message_id
        if state == "idle":
            if old_state != "idle" or self.idle_since is None:
                self.idle_since = self.updated_at
        else:
            self.idle_since = None
        self.state_history.append(
            {
                "state": state,
                "at": self.updated_at,
                "message_id": self.current_message_id,
                "error": error,
            }
        )


@dataclass
class PendingAgentMessage:
    """Message held by the framework until a target agent can receive it."""

    message_id: str
    node_id: str
    agent_id: str
    body: Any
    source_node_id: Optional[str] = None
    source_agent_id: Optional[str] = None
    timeout_sec: Optional[float] = None
    queue_mode: str = "default"
    created_at: float = field(default_factory=time.monotonic)
    dispatched_at: Optional[float] = None
    completed_at: Optional[float] = None
    status: str = "queued"
    receipt: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self, *, include_receipt: bool = False) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "message_id": self.message_id,
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "body": self.body,
            "status": self.status,
            "queue_mode": self.queue_mode,
            "created_at": self.created_at,
        }
        if self.source_node_id is not None:
            data["source_node_id"] = self.source_node_id
        if self.source_agent_id is not None:
            data["source_agent_id"] = self.source_agent_id
        if self.timeout_sec is not None:
            data["timeout_sec"] = self.timeout_sec
        if self.dispatched_at is not None:
            data["dispatched_at"] = self.dispatched_at
        if self.completed_at is not None:
            data["completed_at"] = self.completed_at
        if include_receipt and self.receipt is not None:
            data["receipt"] = dict(self.receipt)
        elif self.receipt is not None:
            data["utterance_id"] = self.receipt.get("utterance_id")
        if self.error is not None:
            data["error"] = self.error
        return data


@dataclass
class StagedOutgoingMessage:
    """Message staged by one agent for a downstream target."""

    target_node_id: str
    target_agent_id: str
    body: Any
    target_node_kind: str = "agent"
    staged_at: float = field(default_factory=time.monotonic)
    overwrite_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_node_id": self.target_node_id,
            "target_agent_id": self.target_agent_id,
            "target_node_kind": self.target_node_kind,
            "body": self.body,
            "staged_at": self.staged_at,
            "overwrite_count": self.overwrite_count,
        }


@dataclass
class OutgoingMessageBatch:
    """Framework-owned one-to-many handoff for a single source agent step."""

    batch_id: str
    source_node_id: str
    source_agent_id: str
    required_target_node_ids: List[str]
    required_target_agent_ids: List[str]
    created_at: float = field(default_factory=time.monotonic)
    status: str = "staging"
    staged_messages: Dict[str, StagedOutgoingMessage] = field(default_factory=dict)
    dispatched_message_ids: List[str] = field(default_factory=list)
    no_op_target_node_ids: List[str] = field(default_factory=list)
    reminder_count: int = 0
    last_reminder_targets: List[str] = field(default_factory=list)
    ring_ids_by_target: Dict[str, List[str]] = field(default_factory=dict)
    closing_ring_ids_by_target: Dict[str, List[str]] = field(default_factory=dict)
    ring_recorded_target_node_ids: List[str] = field(default_factory=list)
    script_paths_by_target: Dict[str, List[str]] = field(default_factory=dict)
    script_calls: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_script_call_reminder_keys: List[str] = field(default_factory=list)
    target_node_kinds_by_target: Dict[str, str] = field(default_factory=dict)

    @property
    def remaining_targets(self) -> List[str]:
        return [
            target
            for target in self.required_target_node_ids
            if target not in self.staged_messages and target not in self.no_op_target_node_ids
        ]

    @property
    def ready_to_dispatch(self) -> bool:
        return not self.remaining_targets

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "source_node_id": self.source_node_id,
            "source_agent_id": self.source_agent_id,
            "required_target_node_ids": list(self.required_target_node_ids),
            "required_target_agent_ids": list(self.required_target_agent_ids),
            "remaining_targets": self.remaining_targets,
            "status": self.status,
            "created_at": self.created_at,
            "staged_messages": {
                target: message.to_dict()
                for target, message in self.staged_messages.items()
            },
            "dispatched_message_ids": list(self.dispatched_message_ids),
            "no_op_target_node_ids": list(self.no_op_target_node_ids),
            "reminder_count": self.reminder_count,
            "ring_ids_by_target": {
                target: list(ring_ids)
                for target, ring_ids in self.ring_ids_by_target.items()
            },
            "closing_ring_ids_by_target": {
                target: list(ring_ids)
                for target, ring_ids in self.closing_ring_ids_by_target.items()
            },
            "ring_recorded_target_node_ids": list(self.ring_recorded_target_node_ids),
            "script_paths_by_target": {
                target: list(script_ids)
                for target, script_ids in self.script_paths_by_target.items()
            },
            "script_calls": {
                script_node_id: _safe_script_call_record(record)
                for script_node_id, record in self.script_calls.items()
            },
            "last_script_call_reminder_keys": list(self.last_script_call_reminder_keys),
            "target_node_kinds_by_target": {
                target: str(kind)
                for target, kind in self.target_node_kinds_by_target.items()
            },
        }


def _safe_script_call_record(record: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(record)
    if isinstance(result.get("arguments"), dict):
        result["arguments"] = {
            str(key): value
            for key, value in list(result["arguments"].items())[:20]
        }
    if isinstance(result.get("result"), dict):
        result["result"] = dict(result["result"])
    return result


@dataclass
class PendingCommonNodeMessage:
    """Message queued for a framework-owned common node."""

    message_id: str
    node_id: str
    body: Any
    source_node_id: Optional[str] = None
    source_agent_id: Optional[str] = None
    status: str = "queued"
    queued_at: float = field(default_factory=time.monotonic)
    dispatched_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "message_id": self.message_id,
            "node_id": self.node_id,
            "body": self.body,
            "status": self.status,
            "queued_at": self.queued_at,
        }
        if self.source_node_id is not None:
            data["source_node_id"] = self.source_node_id
        if self.source_agent_id is not None:
            data["source_agent_id"] = self.source_agent_id
        if self.dispatched_at is not None:
            data["dispatched_at"] = self.dispatched_at
        if self.completed_at is not None:
            data["completed_at"] = self.completed_at
        if self.error is not None:
            data["error"] = self.error
        return data


@dataclass
class AgentRing:
    """One concrete simple AgentNode cycle with an independent circulation limit."""

    ring_id: str
    ordered_node_ids: List[str]
    max_circulations: int = 1
    topology_id: Optional[str] = None

    def __post_init__(self) -> None:
        self.ring_id = str(self.ring_id).strip()
        if not self.ring_id:
            raise ValueError("AgentRing.ring_id must be non-empty")
        self.ordered_node_ids = [
            str(node_id).strip()
            for node_id in self.ordered_node_ids
            if str(node_id).strip()
        ]
        if len(self.ordered_node_ids) < 2:
            raise ValueError("AgentRing requires at least two AgentNodes")
        if len(set(self.ordered_node_ids)) != len(self.ordered_node_ids):
            raise ValueError("AgentRing.ordered_node_ids must not contain duplicates")
        self.max_circulations = int(self.max_circulations)
        if self.max_circulations < 0:
            raise ValueError("AgentRing.max_circulations must be non-negative")
        if self.topology_id is not None:
            self.topology_id = str(self.topology_id).strip() or None

    @property
    def edge_node_pairs(self) -> List[tuple[str, str]]:
        nodes = self.ordered_node_ids
        return [
            (nodes[index], nodes[(index + 1) % len(nodes)])
            for index in range(len(nodes))
        ]

    @property
    def closing_edge(self) -> tuple[str, str]:
        return self.ordered_node_ids[-1], self.ordered_node_ids[0]

    def contains_edge(self, source_node_id: str, target_node_id: str) -> bool:
        return (source_node_id, target_node_id) in self.edge_node_pairs

    def to_dict(self, *, remaining_circulations: Optional[int] = None) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "ring_id": self.ring_id,
            "ordered_node_ids": list(self.ordered_node_ids),
            "edge_node_pairs": [
                {"from": source, "to": target}
                for source, target in self.edge_node_pairs
            ],
            "closing_edge": {
                "from": self.closing_edge[0],
                "to": self.closing_edge[1],
            },
            "max_circulations": self.max_circulations,
        }
        if self.topology_id is not None:
            data["topology_id"] = self.topology_id
        if remaining_circulations is not None:
            data["remaining_circulations"] = remaining_circulations
        return data


@dataclass
class JoinContribution:
    """One upstream source contribution captured by a fan-in barrier."""

    source_node_id: str
    source_agent_id: Optional[str] = None
    status: str = "completed"
    result: Any = None
    accepted_changesets: List[Dict[str, Any]] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    reports: List[Dict[str, Any]] = field(default_factory=list)
    test_results: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    submitted_at: float = field(default_factory=time.monotonic)
    overwrite_count: int = 0

    def __post_init__(self) -> None:
        self.source_node_id = str(self.source_node_id).strip()
        if not self.source_node_id:
            raise ValueError("JoinContribution.source_node_id must be non-empty")
        if self.source_agent_id is not None:
            self.source_agent_id = str(self.source_agent_id).strip() or None
        self.status = str(self.status or "completed").strip() or "completed"
        if not isinstance(self.metadata, dict):
            raise ValueError("JoinContribution.metadata must be an object")
        self.accepted_changesets = [dict(item) for item in self.accepted_changesets]
        self.conflicts = [dict(item) for item in self.conflicts]
        self.artifacts = [dict(item) for item in self.artifacts]
        self.reports = [dict(item) for item in self.reports]
        self.test_results = [dict(item) for item in self.test_results]

    @property
    def is_successful(self) -> bool:
        return self.status in {"completed", "success", "accepted", "passed"}

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "source_node_id": self.source_node_id,
            "status": self.status,
            "result": self.result,
            "accepted_changesets": list(self.accepted_changesets),
            "conflicts": list(self.conflicts),
            "artifacts": list(self.artifacts),
            "reports": list(self.reports),
            "test_results": list(self.test_results),
            "metadata": dict(self.metadata),
            "submitted_at": self.submitted_at,
            "overwrite_count": self.overwrite_count,
        }
        if self.source_agent_id is not None:
            data["source_agent_id"] = self.source_agent_id
        return data


@dataclass
class JoinBarrier:
    """Framework-owned multi-source fan-in barrier."""

    join_id: str
    target_node_id: Optional[str]
    required_source_node_ids: List[str]
    policy: JoinPolicy = "wait-all"
    quorum: Optional[int] = None
    timeout_sec: Optional[float] = None
    created_at: float = field(default_factory=time.monotonic)
    status: str = "waiting"
    contributions: Dict[str, JoinContribution] = field(default_factory=dict)
    completed_at: Optional[float] = None
    final_reason: Optional[str] = None
    aggregate_message_id: Optional[str] = None

    def __post_init__(self) -> None:
        self.join_id = str(self.join_id).strip()
        if not self.join_id:
            raise ValueError("JoinBarrier.join_id must be non-empty")
        if self.target_node_id is not None:
            self.target_node_id = str(self.target_node_id).strip() or None
        self.required_source_node_ids = [
            str(node_id).strip()
            for node_id in self.required_source_node_ids
            if str(node_id).strip()
        ]
        if not self.required_source_node_ids:
            raise ValueError("JoinBarrier.required_source_node_ids must not be empty")
        if len(set(self.required_source_node_ids)) != len(self.required_source_node_ids):
            raise ValueError("JoinBarrier.required_source_node_ids must not contain duplicates")
        if self.policy not in _VALID_JOIN_POLICIES:
            raise ValueError(f"unsupported join policy: {self.policy!r}")
        if self.policy == "quorum":
            if self.quorum is None:
                raise ValueError("quorum join policy requires quorum")
            if self.quorum < 1 or self.quorum > len(self.required_source_node_ids):
                raise ValueError("quorum must be between 1 and the number of required sources")
        elif self.quorum is not None and self.quorum < 1:
            raise ValueError("quorum must be positive when provided")

    @property
    def missing_sources(self) -> List[str]:
        return [
            source
            for source in self.required_source_node_ids
            if source not in self.contributions
        ]

    @property
    def contribution_count(self) -> int:
        return len(self.contributions)

    @property
    def successful_count(self) -> int:
        return sum(1 for item in self.contributions.values() if item.is_successful)

    def timed_out(self, *, now: Optional[float] = None) -> bool:
        if self.timeout_sec is None:
            return False
        return (now if now is not None else time.monotonic()) >= self.created_at + self.timeout_sec

    def aggregate(self) -> Dict[str, Any]:
        contributions = {
            source: contribution.to_dict()
            for source, contribution in self.contributions.items()
        }
        return {
            "join_id": self.join_id,
            "target_node_id": self.target_node_id,
            "required_source_node_ids": list(self.required_source_node_ids),
            "policy": self.policy,
            "quorum": self.quorum,
            "status": self.status,
            "final_reason": self.final_reason,
            "missing_sources": self.missing_sources,
            "contribution_count": self.contribution_count,
            "successful_count": self.successful_count,
            "source_statuses": {
                source: contribution.status
                for source, contribution in self.contributions.items()
            },
            "source_metadata": {
                source: dict(contribution.metadata)
                for source, contribution in self.contributions.items()
                if contribution.metadata
            },
            "accepted_changesets": [
                item
                for contribution in self.contributions.values()
                for item in contribution.accepted_changesets
            ],
            "conflicts": [
                item
                for contribution in self.contributions.values()
                for item in contribution.conflicts
            ],
            "artifacts": [
                item
                for contribution in self.contributions.values()
                for item in contribution.artifacts
            ],
            "reports": [
                item
                for contribution in self.contributions.values()
                for item in contribution.reports
            ],
            "test_results": [
                item
                for contribution in self.contributions.values()
                for item in contribution.test_results
            ],
            "contributions": contributions,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "aggregate_message_id": self.aggregate_message_id,
        }

    def to_dict(self) -> Dict[str, Any]:
        data = self.aggregate()
        data["timeout_sec"] = self.timeout_sec
        return data


@dataclass
class RunEndResult:
    """Structured result returned by GraphRuntime.end_run()."""

    ok: bool
    action: str
    run_status: RunLifecycleStatus
    final_status: Optional[RunFinalStatus]
    reason: str = ""
    summary: Dict[str, Any] = field(default_factory=dict)
    archived: bool = False
    ended_at: float = field(default_factory=time.monotonic)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "ok": self.ok,
            "action": self.action,
            "run_status": self.run_status,
            "reason": self.reason,
            "summary": dict(self.summary),
            "archived": self.archived,
            "ended_at": self.ended_at,
        }
        if self.final_status is not None:
            data["final_status"] = self.final_status
        return data


@dataclass
class WorkdirAssignmentResult:
    ok: bool
    agent_id: str
    node_id: str
    cwd: Optional[Path] = None
    error_code: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "ok": self.ok,
            "agent_id": self.agent_id,
            "node_id": self.node_id,
        }
        if self.cwd is not None:
            data["cwd"] = str(self.cwd)
        if self.error_code is not None:
            data["error_code"] = self.error_code
        if self.error is not None:
            data["error"] = self.error
        return data


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
        archive_manager: Any = None,
        archive_run: Any = None,
        enforce_private_agent_context: bool = False,
        private_context_manager: Any = None,
        private_context_run: Any = None,
        private_context_rpc_server: Any = None,
        skill_space: Any = None,
        private_context_mcp_provider: Any = None,
        tick_interval_sec: float = 0.5,
        message_journal_path: Optional[Path] = None,
    ) -> None:
        self.cluster = cluster
        self.workspace = workspace
        self.archive_manager = archive_manager
        self.archive_run = archive_run
        self.enforce_private_agent_context = bool(enforce_private_agent_context)
        self.private_context_manager = private_context_manager
        self.private_context_run = private_context_run
        self.private_context_rpc_server = private_context_rpc_server
        self.skill_space = skill_space
        self.private_context_mcp_provider = private_context_mcp_provider
        self.tick_interval_sec = float(tick_interval_sec)
        if message_journal_path is not None:
            self.message_journal_path: Optional[Path] = Path(message_journal_path).expanduser()
        elif workspace is not None:
            self.message_journal_path = (
                workspace.workspace_root / "shared" / "logs" / "message_journal.jsonl"
            )
        elif archive_run is not None and getattr(archive_run, "shared_dir", None) is not None:
            self.message_journal_path = (
                Path(getattr(archive_run, "shared_dir")) / "logs" / "message_journal.jsonl"
            )
        elif archive_run is not None and getattr(archive_run, "path", None) is not None:
            self.message_journal_path = (
                Path(getattr(archive_run, "path")) / "shared" / "logs" / "message_journal.jsonl"
            )
        else:
            self.message_journal_path = None
        self._instances: Dict[str, AgentInstance] = {}
        self._launch_nodes: Dict[str, AgentNode] = {}
        self._agent_message_queues: Dict[str, List[PendingAgentMessage]] = {}
        self._pending_messages: Dict[str, PendingAgentMessage] = {}
        self._prompt_nodes_by_agent: Dict[str, List[PromptNode]] = {}
        self._common_nodes: Dict[str, CommonNode] = {}
        self._common_graph: Optional["GraphDefinition"] = None
        self._common_node_message_queues: Dict[str, List[PendingCommonNodeMessage]] = {}
        self._pending_common_messages: Dict[str, PendingCommonNodeMessage] = {}
        self._common_tick_counters: Dict[str, int] = {}
        self._common_tick_last_emit_at: Dict[str, float] = {}
        self._agent_utterances: Dict[str, AgentUtterance] = {}
        self._utterances_by_task: Dict[str, List[str]] = {}
        self._message_journal: List[RuntimeMessageRecord] = []
        self._outgoing_batches: Dict[str, OutgoingMessageBatch] = {}
        self._agent_rings: Dict[str, AgentRing] = {}
        self._agent_ring_circulation_counts: Dict[str, Dict[str, int]] = {}
        self._join_barriers: Dict[str, JoinBarrier] = {}
        self._join_target_nodes: Dict[str, AgentNode] = {}
        self._dispatch_tasks: Dict[str, asyncio.Task[None]] = {}
        self._job_tasks: Dict[str, asyncio.Task[None]] = {}
        self._jobs: Dict[str, GraphJob] = {}
        self._events: List[GraphEvent] = []
        self._agent_stream_events: List[Dict[str, Any]] = []
        self._agent_stream_seq = 0
        self.agent_stream_run_id: Optional[str] = None
        self.agent_stream_event_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self.agent_message_context_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
        self._tick_task: Optional[asyncio.Task[None]] = None
        self._last_tick_at: Optional[float] = None
        self._run_status: RunLifecycleStatus = "created"
        self._final_status: Optional[RunFinalStatus] = None
        self._ended_at: Optional[float] = None
        self._end_reason: Optional[str] = None
        self._run_manifest: Dict[str, Any] = {}
        self._completion_agent_node_ids: List[str] = []
        self._completion_generation = 0
        self._ready_for_top_agent_summary = False
        self._ready_for_top_agent_summary_generation: Optional[int] = None
        self._closed = False

    def _ensure_private_context_runtime(self, node: AgentNode) -> None:
        if not self.enforce_private_agent_context:
            return
        if self.private_context_manager is not None and self.private_context_run is not None:
            if self.private_context_rpc_server is None:
                from .workspace_rpc import WorkspaceRPCServer

                self.private_context_rpc_server = WorkspaceRPCServer(
                    self.private_context_manager,
                    self.private_context_run,
                )
                self.private_context_rpc_server.start()
            return

        from .workspace_manager import DulwichWorkspaceManager
        from .workspace_rpc import WorkspaceRPCServer

        raw_cwd = Path(node.cwd).expanduser()
        project_root = raw_cwd if raw_cwd.is_absolute() else Path.cwd() / raw_cwd
        project_root = project_root.resolve()
        if not project_root.is_dir():
            raise FileNotFoundError(f"private agent context project root is not a directory: {project_root}")
        self.private_context_manager = DulwichWorkspaceManager.open_or_init(project_root)
        self.private_context_run = self.private_context_manager.create_run(
            code_mode="project_reference",
        )
        self.private_context_rpc_server = WorkspaceRPCServer(
            self.private_context_manager,
            self.private_context_run,
        )
        self.private_context_rpc_server.start()

    def _node_for_launch(self, node: AgentNode) -> AgentNode:
        if not self.enforce_private_agent_context or node.external:
            return node
        cached = self._launch_nodes.get(node.node_id)
        if cached is not None:
            return cached
        if node.node_type == "agent":
            from .agent_launch_context import materialize_full_agent_context

            launch_node = materialize_full_agent_context(
                node,
                project_root=(
                    Path(getattr(self.private_context_manager, "project_root"))
                    if self.private_context_manager is not None
                    and getattr(self.private_context_manager, "project_root", None) is not None
                    else None
                ),
                run=self.private_context_run,
                mcp_context_provider=self.private_context_mcp_provider,
            )
            self._launch_nodes[node.node_id] = launch_node
            return launch_node
        self._ensure_private_context_runtime(node)
        from .agent_launch_context import materialize_private_agent_context

        launch_node = materialize_private_agent_context(
            node,
            manager=self.private_context_manager,
            run=self.private_context_run,
            rpc_server=self.private_context_rpc_server,
            skill_space=self.skill_space,
            mcp_context_provider=self.private_context_mcp_provider,
        )
        self._launch_nodes[node.node_id] = launch_node
        return launch_node

    @property
    def instances(self) -> Dict[str, AgentInstance]:
        return dict(self._instances)

    @property
    def jobs(self) -> Dict[str, GraphJob]:
        return dict(self._jobs)

    @property
    def agent_message_queues(self) -> Dict[str, List[PendingAgentMessage]]:
        return {node_id: list(queue) for node_id, queue in self._agent_message_queues.items()}

    @property
    def pending_messages(self) -> Dict[str, PendingAgentMessage]:
        return dict(self._pending_messages)

    @property
    def common_node_message_queues(self) -> Dict[str, List[PendingCommonNodeMessage]]:
        return {node_id: list(queue) for node_id, queue in self._common_node_message_queues.items()}

    @property
    def pending_common_messages(self) -> Dict[str, PendingCommonNodeMessage]:
        return dict(self._pending_common_messages)

    @property
    def agent_utterances(self) -> Dict[str, AgentUtterance]:
        return dict(self._agent_utterances)

    def private_agent_utterances(
        self,
        *,
        task_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return framework-private worker reply utterances for audit/UI owners."""

        if task_id is not None:
            ids = self._utterances_by_task.get(str(task_id), [])
            return [self._agent_utterances[item].to_dict() for item in ids]
        return [utterance.to_dict() for utterance in self._agent_utterances.values()]

    @property
    def outgoing_batches(self) -> Dict[str, OutgoingMessageBatch]:
        return dict(self._outgoing_batches)

    @property
    def join_barriers(self) -> Dict[str, JoinBarrier]:
        return dict(self._join_barriers)

    @property
    def events(self) -> List[GraphEvent]:
        return list(self._events)

    @property
    def run_manifest(self) -> Dict[str, Any]:
        return dict(self._run_manifest)

    @property
    def message_journal(self) -> List[Dict[str, Any]]:
        return [record.to_dict() for record in self._message_journal]

    def _message_journal_summary(self) -> Dict[str, Any]:
        return {
            "path": str(self.message_journal_path) if self.message_journal_path is not None else None,
            "record_count": len(self._message_journal),
        }

    def _record_message_io(
        self,
        *,
        record_type: str,
        sender: Dict[str, Any],
        receiver: Dict[str, Any],
        payload: Any = None,
        message_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        join_id: Optional[str] = None,
        utterance_id: Optional[str] = None,
        status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RuntimeMessageRecord:
        record = RuntimeMessageRecord(
            record_id=f"msgio-{uuid.uuid4().hex[:12]}",
            record_type=record_type,
            sender=dict(sender),
            receiver=dict(receiver),
            payload=payload,
            message_id=message_id,
            batch_id=batch_id,
            join_id=join_id,
            utterance_id=utterance_id,
            status=status,
            metadata=dict(metadata or {}),
        )
        self._message_journal.append(record)
        summary = self._message_journal_summary()
        self._run_manifest["message_journal"] = summary
        if self.workspace is not None:
            self.workspace.run["message_journal"] = summary
        if self.message_journal_path is not None:
            self.message_journal_path.parent.mkdir(parents=True, exist_ok=True)
            with self.message_journal_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record.to_dict(), ensure_ascii=False, default=str) + "\n")
        return record

    def _emit(self, event: GraphEvent) -> GraphEvent:
        self._events.append(event)
        return event

    @property
    def agent_stream_events(self) -> List[Dict[str, Any]]:
        return [dict(event) for event in self._agent_stream_events]

    def agent_stream_events_after(
        self,
        cursor: Optional[int] = None,
        *,
        node_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        min_seq = int(cursor or 0)
        return [
            dict(event)
            for event in self._agent_stream_events
            if int(event.get("seq", 0)) > min_seq
            and (node_id is None or event.get("node_id") == node_id)
        ]

    def record_agent_stream_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        self._agent_stream_seq += 1
        data = dict(event)
        data.setdefault("event_id", f"agent-stream-{uuid.uuid4().hex[:12]}")
        data["seq"] = self._agent_stream_seq
        data.setdefault("created_at", time.time())
        if self.agent_stream_run_id is not None:
            data.setdefault("run_id", self.agent_stream_run_id)
        self._agent_stream_events.append(data)
        if len(self._agent_stream_events) > 1000:
            self._agent_stream_events = self._agent_stream_events[-1000:]
        callback = self.agent_stream_event_callback
        if callback is not None:
            try:
                callback(dict(data))
            except Exception:
                log.exception("[graph] agent stream callback failed")
        return data

    def _agent_stream_status_event(
        self,
        inst: AgentInstance,
        *,
        kind: str = "status",
        message_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "kind": kind,
            "node_id": inst.node.node_id,
            "agent_id": inst.agent_id,
            "message_id": message_id or inst.current_message_id,
            "agent_state": inst.state,
            "busy_count": inst.busy_count,
            "queue_size": len(self._agent_message_queues.get(inst.node.node_id, [])),
            "current_message_id": inst.current_message_id,
            "messages_sent": inst.messages_sent,
            "last_error": error if error is not None else inst.last_error,
            "has_received_flow": inst.has_received_flow,
            "idle_since": inst.idle_since,
            "task_status": inst.task_status,
            "task_summary": inst.task_summary,
            "task_status_updated_at": inst.task_status_updated_at,
            "summary_prompted_at": inst.summary_prompted_at,
            "summary_prompt_message_id": inst.summary_prompt_message_id,
        }

    def _extract_agent_said(self, reply: Any) -> str:
        if isinstance(reply, dict):
            body = reply.get("body")
            if isinstance(body, dict):
                codex = body.get("codex")
                if isinstance(codex, dict):
                    for key in ("final_text", "last_message"):
                        value = codex.get(key)
                        if isinstance(value, str) and value.strip():
                            return value.strip()
                for key in ("final_text", "message", "text", "answer", "content"):
                    value = body.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                if body:
                    return json.dumps(body, ensure_ascii=False, default=str)
            if isinstance(body, str) and body.strip():
                return body.strip()
        if isinstance(reply, str):
            return reply.strip()
        return ""

    def _record_agent_utterance(
        self,
        *,
        node_id: str,
        agent_id: str,
        reply: Any,
        message_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> AgentUtterance:
        utterance = AgentUtterance(
            utterance_id=f"utt-{uuid.uuid4().hex[:12]}",
            agent_id=agent_id,
            node_id=node_id,
            said=self._extract_agent_said(reply),
            received_at=time.monotonic(),
            task_id=task_id,
            message_id=message_id,
        )
        self._agent_utterances[utterance.utterance_id] = utterance
        if task_id:
            self._utterances_by_task.setdefault(task_id, []).append(utterance.utterance_id)
        self._record_message_io(
            record_type="agent.reply.received",
            sender={"type": "agent", "agent_id": agent_id, "node_id": node_id},
            receiver={"type": "framework"},
            payload=utterance.to_dict(),
            message_id=message_id,
            utterance_id=utterance.utterance_id,
            status="received",
            metadata={"task_id": task_id} if task_id is not None else {},
        )
        return utterance

    def _task_id_from_body(self, body: Any, *, message_id: Optional[str]) -> Optional[str]:
        if isinstance(body, dict):
            for key in ("task_id", "job_id", "run_task_id"):
                value = body.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            task = body.get("task")
            if isinstance(task, dict):
                for key in ("task_id", "id"):
                    value = task.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        if isinstance(message_id, str) and message_id.startswith("job-"):
            return message_id
        return None

    def _mark_run_running(self) -> None:
        if self._run_status in {"created", "paused"}:
            self._run_status = "running"

    def record_start_manifest(
        self,
        *,
        top_agent: Dict[str, Any],
        start_plan: Dict[str, Any],
        organization: Dict[str, Any],
        queued_messages: Sequence[Dict[str, Any]],
        manifest_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        self._mark_run_running()
        entry = {
            "top_agent": dict(top_agent),
            "start_plan": dict(start_plan),
            "organization": dict(organization),
            "queued_messages": [dict(message) for message in queued_messages],
            "started_at": time.monotonic(),
        }
        self._run_manifest["start"] = entry
        if self.workspace is not None:
            self.workspace.record_run_start(
                top_agent=top_agent,
                start_plan=start_plan,
                organization=organization,
                queued_messages=queued_messages,
            )
            if manifest_path is not None:
                self.workspace.write_json(manifest_path)
        self._emit(
            GraphEvent(
                "RunStarted",
                status=self._run_status,
                payload={
                    "top_agent": dict(top_agent),
                    "start_nodes": list(start_plan.get("start_nodes", [])),
                    "queued_message_ids": [
                        str(message.get("message_id"))
                        for message in queued_messages
                        if message.get("message_id") is not None
                    ],
                    "manifest_path": str(manifest_path) if manifest_path is not None else None,
                },
            )
        )
        return dict(entry)

    def _set_agent_state(
        self,
        inst: AgentInstance,
        state: AgentRuntimeState,
        *,
        error: Optional[str] = None,
        message_id: Optional[str] = None,
        emit: bool = False,
    ) -> None:
        old_state = inst.state
        inst.set_state(state, error=error, message_id=message_id)
        if old_state != state:
            self.record_agent_stream_event(
                self._agent_stream_status_event(
                    inst,
                    kind="status",
                    message_id=message_id,
                    error=error,
                )
            )
        if emit and old_state != state:
            self._emit(
                GraphEvent(
                    "AgentStateChanged",
                    node_id=inst.node.node_id,
                    agent_id=inst.agent_id,
                    status=state,
                    payload={
                        "from": old_state,
                        "to": state,
                        "busy_count": inst.busy_count,
                        "queue_size": len(self._agent_message_queues.get(inst.node.node_id, [])),
                        "message_id": inst.current_message_id,
                        "error": error,
                    },
                )
            )

    def configure_completion_tracking(self, graph: "GraphDefinition") -> None:
        self.reset_run_prompt_injections()
        self._completion_agent_node_ids = list(graph.agent_nodes)
        self.configure_prompt_nodes(graph)
        self.configure_agent_rings(graph)
        self.configure_common_nodes(graph)

    def configure_prompt_nodes(self, graph: "GraphDefinition") -> None:
        prompt_nodes_by_agent: Dict[str, List[PromptNode]] = {
            node_id: []
            for node_id in graph.agent_nodes
        }
        for edge in graph.edges:
            if edge.edge_type != "data":
                continue
            if edge.source not in graph.prompt_nodes:
                continue
            if edge.target not in graph.agent_nodes:
                continue
            if (edge.output_port or DEFAULT_OUTPUT_PORT) != DEFAULT_OUTPUT_PORT:
                continue
            if (edge.input_port or "in") != AGENT_PROMPT_INPUT_PORT:
                continue
            prompt_nodes_by_agent.setdefault(edge.target, []).append(graph.prompt_nodes[edge.source])
        self._prompt_nodes_by_agent = {
            node_id: prompts
            for node_id, prompts in prompt_nodes_by_agent.items()
            if prompts
        }

    def configure_common_nodes(self, graph: "GraphDefinition") -> None:
        self._common_graph = graph
        self._common_nodes = dict(graph.common_nodes)
        for node_id, node in self._common_nodes.items():
            self._common_node_message_queues.setdefault(node_id, [])
            if node.kind == "tick":
                self._common_tick_counters.setdefault(node_id, 0)
        for node_id in list(self._common_node_message_queues):
            if node_id not in self._common_nodes:
                self._common_node_message_queues.pop(node_id, None)
        for node_id in list(self._common_tick_counters):
            if node_id not in self._common_nodes or self._common_nodes[node_id].kind != "tick":
                self._common_tick_counters.pop(node_id, None)
        for node_id in list(self._common_tick_last_emit_at):
            if node_id not in self._common_nodes or self._common_nodes[node_id].kind != "tick":
                self._common_tick_last_emit_at.pop(node_id, None)

    def reset_run_prompt_injections(self) -> None:
        for inst in self._instances.values():
            inst.run_prompt_injected = False
            inst.prompt_node_injected_ids.clear()

    def _agent_prompt_sections(
        self,
        inst: AgentInstance,
    ) -> tuple[List[tuple[str, str]], bool, List[str]]:
        sections: List[tuple[str, str]] = []
        run_prompt_included = False
        prompt_node_ids: List[str] = []
        run_prompt = str(inst.node.run_prompt or "").strip()
        if run_prompt and not inst.run_prompt_injected:
            sections.append((AGENT_RUN_PROMPT_HEADER, run_prompt))
            run_prompt_included = True
        for prompt_node in self._prompt_nodes_by_agent.get(inst.node.node_id, []):
            text = str(prompt_node.text or "").strip()
            if not text:
                continue
            if prompt_node.trigger == "once" and prompt_node.node_id in inst.prompt_node_injected_ids:
                continue
            sections.append((f"{BLUEPRINT_PROMPT_HEADER_PREFIX} {prompt_node.node_id}", text))
            if prompt_node.trigger == "once":
                prompt_node_ids.append(prompt_node.node_id)
        return sections, run_prompt_included, prompt_node_ids

    def _mark_completion_activity(self) -> None:
        self._completion_generation += 1
        self._ready_for_top_agent_summary = False
        self._ready_for_top_agent_summary_generation = None

    def _mark_agent_flow_received(
        self,
        inst: AgentInstance,
        *,
        message_id: str,
        body: Any,
    ) -> None:
        inst.has_received_flow = True
        inst.task_status = "working"
        inst.task_summary = ""
        inst.task_status_updated_at = time.monotonic()
        inst.task_status_message_id = message_id
        inst.task_status_batch_id = None
        inst.task_status_reports = []
        inst.task_status_artifacts = []
        inst.task_status_changesets = []
        inst.task_status_next_actions = []
        inst.task_status_metadata = {}
        if not is_framework_summary_request_body(body):
            inst.summary_prompted_at = None
            inst.summary_prompt_message_id = None
            self._mark_completion_activity()

    def record_agent_task_status(
        self,
        node_id: str,
        *,
        agent_id: Optional[str] = None,
        status: str,
        summary: str = "",
        message_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        reports: Optional[Sequence[Dict[str, Any]]] = None,
        artifacts: Optional[Sequence[Dict[str, Any]]] = None,
        changesets: Optional[Sequence[Dict[str, Any]]] = None,
        next_actions: Optional[Sequence[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in _VALID_AGENT_TASK_STATUSES - {"not_started"}:
            raise ValueError(
                "agent task status must be one of: working, completed, blocked, needs_input, failed"
            )
        inst = self._instances.get(str(node_id))
        if inst is None:
            raise KeyError(f"unknown AgentNode instance: {node_id}")
        if agent_id is not None and str(agent_id) != inst.agent_id:
            raise PermissionError("agent task status cannot be reported as another agent")

        inst.has_received_flow = True
        inst.task_status = normalized_status
        inst.task_summary = str(summary or "").strip()
        inst.task_status_updated_at = time.monotonic()
        inst.task_status_message_id = str(message_id) if message_id is not None else inst.current_message_id
        inst.task_status_batch_id = str(batch_id) if batch_id is not None else None
        inst.task_status_reports = [dict(item) for item in (reports or []) if isinstance(item, dict)]
        inst.task_status_artifacts = [dict(item) for item in (artifacts or []) if isinstance(item, dict)]
        inst.task_status_changesets = [dict(item) for item in (changesets or []) if isinstance(item, dict)]
        inst.task_status_next_actions = [str(item) for item in (next_actions or [])]
        inst.task_status_metadata = dict(metadata or {})
        if normalized_status in _TERMINAL_AGENT_TASK_STATUSES:
            inst.summary_prompted_at = None
            inst.summary_prompt_message_id = None

        payload = {
            "node_id": inst.node.node_id,
            "agent_id": inst.agent_id,
            "status": inst.task_status,
            "summary": inst.task_summary,
            "message_id": inst.task_status_message_id,
            "batch_id": inst.task_status_batch_id,
            "reports": list(inst.task_status_reports),
            "artifacts": list(inst.task_status_artifacts),
            "changesets": list(inst.task_status_changesets),
            "next_actions": list(inst.task_status_next_actions),
            "metadata": dict(inst.task_status_metadata),
            "updated_at": inst.task_status_updated_at,
        }
        self._emit(
            GraphEvent(
                "AgentTaskStatusReported",
                node_id=inst.node.node_id,
                agent_id=inst.agent_id,
                status=inst.task_status,
                payload=payload,
            )
        )
        self.record_agent_stream_event({"kind": "agent.task_status", **payload})
        self._maybe_emit_top_agent_summary_ready()
        return {"ok": True, "task_status": dict(payload)}

    def _agent_has_waiting_outgoing_batch(self, inst: AgentInstance) -> bool:
        return any(
            batch.status == "staging"
            and batch.source_node_id == inst.node.node_id
            and bool(batch.remaining_targets)
            for batch in self._outgoing_batches.values()
        )

    def _agent_ring_counts_allow_summary(self, inst: AgentInstance) -> bool:
        counts = self.agent_ring_circulation_counts_for(inst.node.node_id)
        return not counts or all(int(value) <= 0 for value in counts.values())

    def _agent_should_receive_summary_prompt(self, inst: AgentInstance, now: float) -> bool:
        if not inst.has_received_flow:
            return False
        if inst.state != "idle" or inst.idle_since is None:
            return False
        if inst.task_status in _TERMINAL_AGENT_TASK_STATUSES:
            return False
        if inst.summary_prompted_at is not None:
            return False
        if self._agent_has_waiting_outgoing_batch(inst):
            return False
        if not self._agent_ring_counts_allow_summary(inst):
            return False
        return (now - inst.idle_since) >= COMPLETION_IDLE_THRESHOLD_SEC

    def _summary_request_body(self, inst: AgentInstance, *, now: float) -> Dict[str, Any]:
        ring_counts = self.agent_ring_circulation_counts_for(inst.node.node_id)
        return {
            "type": "framework_summary_request",
            "prompt": (
                "Summarize your own current task outcome for the framework. "
                "Do not summarize the ring or the whole blueprint. Call the "
                "`agent_task_status` MCP tool with completed, blocked, needs_input, or failed."
            ),
            "summary_request": {
                "reason": "idle_task_status_missing",
                "idle_seconds": max(0.0, now - float(inst.idle_since or now)),
                "ring_circulation_counts": dict(ring_counts),
            },
            "context": {
                "framework_context": {
                    "agent_node_id": inst.node.node_id,
                    "agent_id": inst.agent_id,
                    "message_envelope": {
                        "outgoing_batch_id": None,
                        "required_outgoing_targets": [],
                        "remaining_targets": [],
                    },
                }
            },
        }

    def _maybe_prompt_idle_agent_summaries(self, now: float) -> None:
        for inst in list(self._instances.values()):
            if not self._agent_should_receive_summary_prompt(inst, now):
                continue
            message_id = f"summary-msg-{inst.node.node_id}-{uuid.uuid4().hex[:8]}"
            pending = self.queue_agent_message(
                inst.node,
                self._summary_request_body(inst, now=now),
                source_node_id=None,
                source_agent_id="graph-runtime",
                message_id=message_id,
                queue_mode="top",
            )
            inst.summary_prompted_at = now
            inst.summary_prompt_message_id = pending.message_id
            self._emit(
                GraphEvent(
                    "AgentSummaryRequested",
                    node_id=inst.node.node_id,
                    agent_id=inst.agent_id,
                    status="queued",
                    payload={
                        "message_id": pending.message_id,
                        "reason": "idle_task_status_missing",
                    },
                )
            )

    def _completion_node_ids(self) -> List[str]:
        return list(self._completion_agent_node_ids or sorted(self._instances))

    def _has_visible_pending_runtime_work(self) -> bool:
        queued = any(
            message.status in {"queued", "dispatching"}
            for message in self._pending_messages.values()
        )
        dispatching = bool(self._dispatch_tasks)
        waiting_batches = any(batch.status == "staging" for batch in self._outgoing_batches.values())
        waiting_joins = any(barrier.status == "waiting" for barrier in self._join_barriers.values())
        running_jobs = any(job.status in {"queued", "running"} for job in self._jobs.values())
        conflicts = bool(self._workspace_state_snapshot().get("conflicts", []))
        return queued or dispatching or waiting_batches or waiting_joins or running_jobs or conflicts

    def _all_completion_agents_terminal(self) -> bool:
        node_ids = self._completion_node_ids()
        if not node_ids:
            return False
        for node_id in node_ids:
            inst = self._instances.get(node_id)
            if inst is None:
                return False
            if not inst.has_received_flow:
                return False
            if inst.task_status not in _TERMINAL_AGENT_TASK_STATUSES:
                return False
        return True

    def _maybe_emit_top_agent_summary_ready(self) -> None:
        if self._run_status != "running":
            return
        if self._ready_for_top_agent_summary:
            return
        if self._has_visible_pending_runtime_work():
            return
        if not self._all_completion_agents_terminal():
            return
        self._ready_for_top_agent_summary = True
        self._ready_for_top_agent_summary_generation = self._completion_generation
        payload = {
            "generation": self._completion_generation,
            "agent_node_ids": self._completion_node_ids(),
            "agent_task_statuses": {
                node_id: self._instances[node_id].task_status
                for node_id in self._completion_node_ids()
                if node_id in self._instances
            },
        }
        self._emit(GraphEvent("RunReadyForTopAgentSummary", status="ready", payload=payload))
        self.record_agent_stream_event({"kind": "run.ready_for_top_agent_summary", **payload})

    def start_tick_loop(self) -> None:
        """Start the framework tick loop if an event loop is running."""
        if self._closed or self._tick_task is not None:
            return
        self._tick_task = asyncio.create_task(self._tick_loop())

    async def stop_tick_loop(self) -> None:
        task = self._tick_task
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self._tick_task = None

    async def _process_common_nodes(self) -> None:
        graph = self._common_graph
        if graph is None or not self._common_nodes:
            return

        for node_id, node in list(self._common_nodes.items()):
            if node.kind != "tick":
                continue
            count = self._common_tick_counters.get(node_id, 0) + 1
            self._common_tick_counters[node_id] = count
            now = self._last_tick_at if self._last_tick_at is not None else time.monotonic()
            last_emit_at = self._common_tick_last_emit_at.get(node_id)
            if last_emit_at is None:
                self._common_tick_last_emit_at[node_id] = now
                continue
            if now - last_emit_at < node.every_n_seconds:
                continue
            self._common_tick_last_emit_at[node_id] = now
            await self._emit_common_node_output(
                graph,
                node_id,
                "tick",
                {
                    "type": "tick",
                    "tick_node_id": node_id,
                    "tick_count": count,
                    "every_n_seconds": node.every_n_seconds,
                    "created_at": time.time(),
                },
                tick_source_node_id=node_id,
            )

        for node_id, queue in list(self._common_node_message_queues.items()):
            node = self._common_nodes.get(node_id)
            if node is None or node.kind != "branch" or not queue:
                continue
            pending = queue.pop(0)
            pending.status = "dispatching"
            pending.dispatched_at = time.monotonic()
            self.record_agent_stream_event(
                {
                    "kind": "common.queue.updated",
                    "node_id": node_id,
                    "message_id": pending.message_id,
                    "status": pending.status,
                    "queue_size": len(queue),
                }
            )
            self._emit(
                GraphEvent(
                    "BranchNodeRunning",
                    node_id=node_id,
                    status="running",
                    payload=pending.to_dict(),
                )
            )
            try:
                branch_value = self._branch_condition_from_body(pending.body)
                output_port = "true" if branch_value else "false"
                await self._emit_common_node_output(
                    graph,
                    node_id,
                    output_port,
                    pending.body,
                    source_agent_id=pending.source_agent_id,
                )
                pending.status = "completed"
                self._emit(
                    GraphEvent(
                        "BranchNodeCompleted",
                        node_id=node_id,
                        status="completed",
                        payload={
                            **pending.to_dict(),
                            "condition": branch_value,
                            "output_port": output_port,
                        },
                    )
                )
            except Exception as exc:
                pending.status = "failed"
                pending.error = str(exc)
                self._emit(
                    GraphEvent(
                        "BranchNodeFailed",
                        node_id=node_id,
                        status="failed",
                        payload={**pending.to_dict(), "error": str(exc)},
                    )
                )
            finally:
                pending.completed_at = time.monotonic()
                self.record_agent_stream_event(
                    {
                        "kind": "common.queue.updated",
                        "node_id": node_id,
                        "message_id": pending.message_id,
                        "status": pending.status,
                        "queue_size": len(queue),
                        "last_error": pending.error,
                    }
                )

    @staticmethod
    def _branch_condition_from_body(body: Any) -> bool:
        if type(body) is bool:
            return body
        if isinstance(body, dict) and type(body.get("condition")) is bool:
            return bool(body["condition"])
        raise ValueError("Branch node requires a strict boolean condition")

    async def _emit_common_node_output(
        self,
        graph: "GraphDefinition",
        common_node_id: str,
        output_port: str,
        body: Any,
        *,
        source_agent_id: Optional[str] = None,
        tick_source_node_id: Optional[str] = None,
    ) -> List[str]:
        # ``common_node_id`` is the framework node that emits the output.
        emit_source = str(common_node_id)
        targets = graph._exec_successors_by_port(emit_source, output_port)
        if not targets:
            self._emit(
                GraphEvent(
                    "CommonNodeOutputNoOp",
                    node_id=emit_source,
                    status="skipped",
                    payload={"output_port": output_port, "body": body},
                )
            )
            return []

        queued_ids: List[str] = []
        for target_id in targets:
            if target_id in graph.agent_nodes:
                if tick_source_node_id is not None and self._has_pending_tick_message(
                    tick_source_node_id,
                    target_id,
                ):
                    self._emit(
                        GraphEvent(
                            "TickNodeSkipped",
                            node_id=tick_source_node_id,
                            status="skipped",
                            payload={
                                "target_node_id": target_id,
                                "reason": "target_has_pending_tick",
                            },
                        )
                    )
                    continue
                downstream = self.active_framework_connections(graph, target_id)
                downstream_batch = None
                if downstream:
                    downstream_batch = await self.create_outgoing_batch_from_graph(
                        graph,
                        target_id,
                        required_target_node_ids=downstream,
                    )
                queued_body = await self._body_with_agent_framework_context(
                    graph,
                    target_id,
                    body,
                    downstream_batch,
                )
                pending = self.queue_agent_message(
                    graph.agent_nodes[target_id],
                    queued_body,
                    source_node_id=emit_source,
                    source_agent_id=source_agent_id,
                )
                queued_ids.append(pending.message_id)
            elif target_id in graph.common_nodes:
                pending = self.queue_common_node_message(
                    target_id,
                    body,
                    source_node_id=emit_source,
                    source_agent_id=source_agent_id,
                )
                queued_ids.append(pending.message_id)
            else:
                self._emit(
                    GraphEvent(
                        "CommonNodeTargetUnsupported",
                        node_id=emit_source,
                        status="skipped",
                        payload={
                            "target_node_id": target_id,
                            "output_port": output_port,
                        },
                    )
                )
        event_type = "TickNodeEmitted" if tick_source_node_id is not None else "CommonNodeOutputEmitted"
        self._emit(
            GraphEvent(
                event_type,
                node_id=emit_source,
                status="queued",
                payload={
                    "output_port": output_port,
                    "target_node_ids": list(targets),
                    "queued_message_ids": list(queued_ids),
                },
            )
        )
        return queued_ids

    async def _body_with_agent_framework_context(
        self,
        graph: "GraphDefinition",
        target_node_id: str,
        body: Any,
        downstream_batch: Optional[OutgoingMessageBatch],
    ) -> Any:
        try:
            from .graph_control import inject_framework_context, ordinary_agent_framework_context

            return inject_framework_context(
                body,
                ordinary_agent_framework_context(
                    graph,
                    target_node_id,
                    batch=downstream_batch,
                    runtime=self,
                ),
            )
        except Exception:
            log.exception("failed to inject framework context for common node output")
            return body

    def _has_pending_tick_message(self, source_node_id: str, target_node_id: str) -> bool:
        for message in self._pending_messages.values():
            if message.source_node_id != source_node_id or message.node_id != target_node_id:
                continue
            if message.status not in {"queued", "dispatching"}:
                continue
            if isinstance(message.body, dict) and message.body.get("type") == "tick":
                return True
            if (
                isinstance(message.body, dict)
                and isinstance(message.body.get("payload"), dict)
                and message.body["payload"].get("type") == "tick"
            ):
                return True
        return False

    async def _tick_loop(self) -> None:
        while not self._closed:
            await self.tick()
            await asyncio.sleep(self.tick_interval_sec)

    async def tick(self) -> None:
        """Run one framework frame.

        The frame checks agent/job state and dispatches at most one queued
        message per idle agent. A queued agent message therefore advances in
        the same rhythm as the framework rather than bypassing the scheduler.
        """
        if self._closed:
            return
        self._last_tick_at = time.monotonic()
        self._check_join_timeouts(now=self._last_tick_at)
        await self._process_common_nodes()

        finished: List[str] = []
        for message_id, task in self._dispatch_tasks.items():
            if task.done():
                finished.append(message_id)
        for message_id in finished:
            self._dispatch_tasks.pop(message_id, None)

        self._maybe_prompt_idle_agent_summaries(self._last_tick_at)
        for node_id, inst in list(self._instances.items()):
            if inst.busy_count < 0:
                inst.busy_count = 0
            self._maybe_remind_script_calls(inst)
            self._maybe_remind_outgoing_targets(inst)
            queue = self._agent_message_queues.get(node_id, [])
            if not queue or not inst.can_accept_message:
                continue
            pending = queue[0]
            queue.pop(0)
            pending.status = "dispatching"
            pending.dispatched_at = time.monotonic()
            self.record_agent_stream_event(
                {
                    "kind": "queue.updated",
                    "node_id": pending.node_id,
                    "agent_id": pending.agent_id,
                    "message_id": pending.message_id,
                    "status": pending.status,
                    "queue_size": len(queue),
                    "queue_mode": pending.queue_mode,
                }
            )
            self._emit(
                GraphEvent(
                    "AgentQueuedMessageDispatched",
                    node_id=node_id,
                    agent_id=inst.agent_id,
                    status=pending.status,
                    payload=pending.to_dict(),
                )
            )
            self._dispatch_tasks[pending.message_id] = asyncio.create_task(
                self._dispatch_pending_message(inst.node, pending)
            )
        self._maybe_emit_top_agent_summary_ready()

    def _pending_script_call_records(self, batch: OutgoingMessageBatch) -> List[Dict[str, Any]]:
        return [
            record
            for record in batch.script_calls.values()
            if isinstance(record, dict)
            and str(record.get("status") or "pending") == "pending"
        ]

    def _script_call_reminder_body(
        self,
        inst: AgentInstance,
        batch: OutgoingMessageBatch,
        records: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        required_script_calls = [
            {
                "script_node_id": str(record.get("script_node_id") or ""),
                "function_name": str(record.get("function_name") or ""),
                "title": str(record.get("title") or record.get("function_name") or ""),
                "description": str(record.get("description") or ""),
                "inputs": [dict(item) for item in record.get("inputs", []) if isinstance(item, dict)],
                "outputs": [dict(item) for item in record.get("outputs", []) if isinstance(item, dict)],
                "batch_id": batch.batch_id,
                "downstream_target_node_ids": [
                    str(item) for item in record.get("required_target_node_ids", [])
                ],
                "status": str(record.get("status") or "pending"),
            }
            for record in records
        ]
        names = ", ".join(
            call["function_name"] or call["script_node_id"]
            for call in required_script_calls
        )
        return {
            "type": "blueprint_script_call_reminder",
            "prompt": (
                "Call the required Blueprint script function(s) before dispatching downstream work: "
                f"{names}. Use the `blueprint_script_call` MCP tool. The framework will deliver "
                "script output to connected downstream AgentNodes automatically."
            ),
            "script_calls": required_script_calls,
            "context": {
                "framework_context": {
                    "agent_node_id": inst.node.node_id,
                    "agent_id": inst.agent_id,
                    "message_envelope": {
                        "outgoing_batch_id": batch.batch_id,
                        "required_outgoing_targets": list(batch.required_target_node_ids),
                        "remaining_targets": list(batch.remaining_targets),
                        "required_script_calls": required_script_calls,
                    },
                }
            },
        }

    def _maybe_remind_script_calls(self, inst: AgentInstance) -> None:
        if not inst.can_accept_message:
            return
        if not inst.has_received_flow:
            return
        if self._agent_message_queues.get(inst.node.node_id):
            return
        for batch in self._outgoing_batches.values():
            if batch.status != "staging":
                continue
            if batch.source_node_id != inst.node.node_id:
                continue
            records = self._pending_script_call_records(batch)
            if not records:
                continue
            reminder_keys = sorted(str(record.get("script_node_id") or "") for record in records)
            if batch.last_script_call_reminder_keys == reminder_keys:
                continue
            batch.last_script_call_reminder_keys = list(reminder_keys)
            pending = self.queue_agent_message(
                inst.node,
                self._script_call_reminder_body(inst, batch, records),
                source_node_id=None,
                source_agent_id="graph-runtime",
                message_id=f"script-call-reminder-{inst.node.node_id}-{uuid.uuid4().hex[:8]}",
                queue_mode="top",
            )
            self._emit(
                GraphEvent(
                    "AgentScriptCallReminder",
                    node_id=inst.node.node_id,
                    agent_id=inst.agent_id,
                    status="queued",
                    payload={
                        "message_id": pending.message_id,
                        "batch_id": batch.batch_id,
                        "required_script_calls": [
                            {
                                "script_node_id": str(record.get("script_node_id") or ""),
                                "function_name": str(record.get("function_name") or ""),
                                "description": str(record.get("description") or ""),
                                "inputs": [dict(item) for item in record.get("inputs", []) if isinstance(item, dict)],
                                "downstream_target_node_ids": [
                                    str(item) for item in record.get("required_target_node_ids", [])
                                ],
                            }
                            for record in records
                        ],
                    },
                )
            )
            return

    def _outgoing_targets_reminder_body(
        self,
        inst: AgentInstance,
        batch: OutgoingMessageBatch,
        remaining: Sequence[str],
    ) -> Dict[str, Any]:
        return {
            "type": "framework_outgoing_targets_reminder",
            "prompt": (
                "This fan-out step is waiting for downstream target messages. "
                "Call the `agent_dispatch` MCP tool for every remaining target, "
                "or send an empty string or numeric 0 for a target that should be no-op. "
                "Do not report the task complete until every required outgoing target is handled."
            ),
            "outgoing_targets": {
                "batch_id": batch.batch_id,
                "required_outgoing_targets": list(batch.required_target_node_ids),
                "remaining_targets": list(remaining),
                "reminder_count": batch.reminder_count,
            },
            "context": {
                "framework_context": {
                    "agent_node_id": inst.node.node_id,
                    "agent_id": inst.agent_id,
                    "message_envelope": {
                        "outgoing_batch_id": batch.batch_id,
                        "required_outgoing_targets": list(batch.required_target_node_ids),
                        "remaining_targets": list(remaining),
                        "required_script_calls": [],
                    },
                }
            },
        }

    def _maybe_remind_outgoing_targets(self, inst: AgentInstance) -> None:
        if not inst.can_accept_message:
            return
        if not inst.has_received_flow:
            return
        if self._agent_message_queues.get(inst.node.node_id):
            return
        for batch in self._outgoing_batches.values():
            if batch.status != "staging":
                continue
            if batch.source_node_id != inst.node.node_id:
                continue
            remaining = batch.remaining_targets
            if not remaining:
                continue
            if batch.last_reminder_targets == remaining:
                continue
            batch.reminder_count += 1
            batch.last_reminder_targets = list(remaining)
            pending = self.queue_agent_message(
                inst.node,
                self._outgoing_targets_reminder_body(inst, batch, remaining),
                source_node_id=None,
                source_agent_id="graph-runtime",
                message_id=f"outgoing-targets-reminder-{inst.node.node_id}-{uuid.uuid4().hex[:8]}",
                queue_mode="top",
            )
            self._emit(
                GraphEvent(
                    "AgentOutgoingTargetsReminder",
                    node_id=inst.node.node_id,
                    agent_id=inst.agent_id,
                    status="queued",
                    payload={
                        "message_id": pending.message_id,
                        "batch_id": batch.batch_id,
                        "required_outgoing_targets": list(batch.required_target_node_ids),
                        "remaining_targets": list(remaining),
                    },
                )
            )

    def create_join_barrier(
        self,
        *,
        required_sources: Sequence[AgentNode | str],
        target_node: Optional[AgentNode | str] = None,
        policy: JoinPolicy = "wait-all",
        quorum: Optional[int] = None,
        timeout_sec: Optional[float] = None,
        join_id: Optional[str] = None,
    ) -> JoinBarrier:
        """Create a framework-owned fan-in barrier for upstream results."""

        if self._closed:
            raise RuntimeError("GraphRuntime is closed")
        self._mark_run_running()
        source_ids = [
            source.node_id if isinstance(source, AgentNode) else str(source)
            for source in required_sources
        ]
        target_id = (
            target_node.node_id if isinstance(target_node, AgentNode)
            else str(target_node) if target_node is not None
            else None
        )
        barrier = JoinBarrier(
            join_id=join_id or f"join-{uuid.uuid4().hex[:12]}",
            target_node_id=target_id,
            required_source_node_ids=source_ids,
            policy=policy,
            quorum=quorum,
            timeout_sec=timeout_sec,
        )
        self._join_barriers[barrier.join_id] = barrier
        if isinstance(target_node, AgentNode):
            self._join_target_nodes[barrier.join_id] = target_node
        elif target_id is not None and target_id in self._instances:
            self._join_target_nodes[barrier.join_id] = self._instances[target_id].node
        self._emit(
            GraphEvent(
                "JoinBarrierCreated",
                node_id=barrier.target_node_id,
                status=barrier.status,
                payload=barrier.to_dict(),
            )
        )
        return barrier

    def submit_join_contribution(
        self,
        join_id: str,
        source_node: AgentNode | str,
        *,
        status: str = "completed",
        result: Any = None,
        source_agent_id: Optional[str] = None,
        accepted_changesets: Optional[Sequence[Dict[str, Any]]] = None,
        conflicts: Optional[Sequence[Dict[str, Any]]] = None,
        artifacts: Optional[Sequence[Dict[str, Any]]] = None,
        reports: Optional[Sequence[Dict[str, Any]]] = None,
        test_results: Optional[Sequence[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record or overwrite one upstream contribution and evaluate the join."""

        barrier = self._join_barriers.get(join_id)
        if barrier is None:
            raise KeyError(f"unknown join barrier: {join_id}")
        if barrier.status in {"ready", "timed_out", "cancelled"}:
            raise RuntimeError(f"join barrier {join_id} is already {barrier.status}")
        source_id = source_node.node_id if isinstance(source_node, AgentNode) else str(source_node)
        if source_id not in barrier.required_source_node_ids:
            raise ValueError(f"source {source_id!r} is not required for join {join_id}")

        inst = self._instances.get(source_id)
        resolved_agent_id = source_agent_id or (inst.agent_id if inst is not None else None)
        previous = barrier.contributions.get(source_id)
        contribution = JoinContribution(
            source_node_id=source_id,
            source_agent_id=resolved_agent_id,
            status=status,
            result=result,
            accepted_changesets=list(accepted_changesets or []),
            conflicts=list(conflicts or []),
            artifacts=list(artifacts or []),
            reports=list(reports or []),
            test_results=list(test_results or []),
            metadata=dict(metadata or {}),
            overwrite_count=(previous.overwrite_count + 1) if previous is not None else 0,
        )
        barrier.contributions[source_id] = contribution
        self._emit(
            GraphEvent(
                "JoinContributionSubmitted",
                node_id=barrier.target_node_id,
                agent_id=resolved_agent_id,
                status=contribution.status,
                payload={
                    "join_id": barrier.join_id,
                    "source_node_id": source_id,
                    "overwritten": previous is not None,
                    "join_status": barrier.status,
                    "missing_sources": barrier.missing_sources,
                },
            )
        )
        self._evaluate_join_barrier(barrier)
        return {
            "join_id": barrier.join_id,
            "status": barrier.status,
            "ready": barrier.status == "ready",
            "missing_sources": barrier.missing_sources,
            "aggregate": barrier.aggregate(),
        }

    def _evaluate_join_barrier(self, barrier: JoinBarrier) -> None:
        if barrier.status != "waiting":
            return
        reason: Optional[str] = None
        if barrier.policy == "wait-all" and not barrier.missing_sources:
            reason = "all_sources_submitted"
        elif barrier.policy == "wait-any" and barrier.contribution_count >= 1:
            reason = "any_source_submitted"
        elif barrier.policy == "quorum" and barrier.successful_count >= int(barrier.quorum or 0):
            reason = "quorum_reached"
        elif barrier.timed_out():
            barrier.status = "timed_out"
            barrier.completed_at = time.monotonic()
            barrier.final_reason = "timeout"
            self._emit(
                GraphEvent(
                    "JoinBarrierTimedOut",
                    node_id=barrier.target_node_id,
                    status=barrier.status,
                    payload=barrier.aggregate(),
                )
            )
            return

        if reason is None:
            return
        barrier.status = "ready"
        barrier.completed_at = time.monotonic()
        barrier.final_reason = reason
        self._queue_join_aggregate_if_possible(barrier)
        self._emit(
            GraphEvent(
                "JoinBarrierReady",
                node_id=barrier.target_node_id,
                status=barrier.status,
                payload=barrier.aggregate(),
            )
        )

    def _check_join_timeouts(self, *, now: Optional[float] = None) -> None:
        for barrier in self._join_barriers.values():
            if barrier.status != "waiting" or not barrier.timed_out(now=now):
                continue
            barrier.status = "timed_out"
            barrier.completed_at = now if now is not None else time.monotonic()
            barrier.final_reason = "timeout"
            self._emit(
                GraphEvent(
                    "JoinBarrierTimedOut",
                    node_id=barrier.target_node_id,
                    status=barrier.status,
                    payload=barrier.aggregate(),
                )
            )

    def _queue_join_aggregate_if_possible(self, barrier: JoinBarrier) -> None:
        if barrier.aggregate_message_id is not None:
            return
        target = self._join_target_nodes.get(barrier.join_id)
        if target is None:
            return
        aggregate = barrier.aggregate()
        pending = self.queue_agent_message(
            target,
            {
                "type": "join_aggregate",
                "join_id": barrier.join_id,
                "prompt": f"Process fan-in join aggregate {barrier.join_id}.",
                "aggregate": aggregate,
            },
            source_node_id=None,
            source_agent_id="graph-runtime",
            message_id=f"join-msg-{barrier.join_id}",
        )
        barrier.aggregate_message_id = pending.message_id
        self._emit(
            GraphEvent(
                "JoinBarrierAggregateQueued",
                node_id=barrier.target_node_id,
                agent_id=pending.agent_id,
                status=pending.status,
                payload={
                    "join_id": barrier.join_id,
                    "message_id": pending.message_id,
                    "target_node_id": pending.node_id,
                    "target_agent_id": pending.agent_id,
                },
            )
        )

    async def dispatch_queued_message_now(self, message_id: str) -> PendingAgentMessage:
        """Synchronously dispatch one queued message and keep its result."""

        pending = self._pending_messages.get(message_id)
        if pending is None:
            raise KeyError(f"unknown queued message: {message_id}")
        if pending.status != "queued":
            raise RuntimeError(f"message {message_id} is {pending.status}, not queued")
        queue = self._agent_message_queues.get(pending.node_id, [])
        self._agent_message_queues[pending.node_id] = [
            item for item in queue if item.message_id != message_id
        ]
        pending.status = "dispatching"
        pending.dispatched_at = time.monotonic()
        self._emit(
            GraphEvent(
                "AgentQueuedMessageDispatched",
                node_id=pending.node_id,
                agent_id=pending.agent_id,
                status=pending.status,
                payload=pending.to_dict(),
            )
        )
        node = self._instances[pending.node_id].node
        try:
            pending.receipt = await self._dispatch_agent_message(
                node,
                pending.body,
                timeout_sec=pending.timeout_sec,
                message_id=pending.message_id,
            )
            pending.status = "completed"
        except Exception as exc:
            pending.status = "failed"
            pending.error = str(exc)
            raise
        finally:
            pending.completed_at = time.monotonic()
            self.record_agent_stream_event(
                {
                    "kind": "queue.updated",
                    "node_id": pending.node_id,
                    "agent_id": pending.agent_id,
                    "message_id": pending.message_id,
                    "status": pending.status,
                    "queue_size": len(self._agent_message_queues.get(pending.node_id, [])),
                    "queue_mode": pending.queue_mode,
                    "last_error": pending.error,
                }
            )
            self._emit(
                GraphEvent(
                    "AgentQueuedMessageCompleted",
                    node_id=pending.node_id,
                    agent_id=pending.agent_id,
                    status=pending.status,
                    payload=pending.to_dict(),
                )
            )
        return pending

    def _workspace_state_snapshot(self) -> Dict[str, Any]:
        workspace_run = self._workspace_run_for_snapshot()
        if self.workspace is None and workspace_run is None:
            return {
                "workspace_id": None,
                "workspace_root": None,
                "shared_root": None,
                "directories": {
                    "changesets": None,
                    "artifacts": None,
                    "reports": None,
                },
                "changesets": [],
                "conflicts": [],
                "artifacts": [],
                "reports": [],
                "jobs": {},
            }
        root = self.workspace.workspace_root if self.workspace is not None else Path(getattr(workspace_run, "path"))
        changesets: List[Dict[str, Any]] = []
        conflicts: List[Dict[str, Any]] = []
        artifacts: List[Dict[str, Any]] = []
        reports: List[Dict[str, Any]] = []

        for event in self._events:
            payload = event.payload
            event_type = event.event_type
            if event_type in {"ChangesetSubmitted", "ChangesetAccepted"}:
                changesets.append(dict(payload))
            elif event_type == "ConflictDetected":
                conflicts.append(dict(payload))
            elif event_type == "ArtifactPublished":
                artifacts.append(dict(payload))
            elif event_type == "AgentReportSubmitted":
                reports.append(dict(payload))

        run_directories: Dict[str, Optional[str]] = {
            "changesets": None,
            "artifacts": None,
            "reports": None,
        }
        shared_root: Optional[str] = None
        workspace_id = self.workspace.workspace_id if self.workspace is not None else None
        if workspace_run is not None:
            run_path = Path(getattr(workspace_run, "path"))
            run_manifest = self._read_workspace_json(run_path / "run_manifest.json")
            workspace_id = str(run_manifest.get("workspace_id") or workspace_id or "")
            if not workspace_id:
                workspace_id = None
            shared_dir = Path(getattr(workspace_run, "shared_dir", run_path / "shared"))
            shared_root = str(shared_dir.resolve())
            run_directories = {
                "changesets": str((run_path / "changesets").resolve()),
                "artifacts": str(Path(getattr(workspace_run, "shared_artifacts_dir", shared_dir / "artifacts")).resolve()),
                "reports": str(Path(getattr(workspace_run, "shared_reports_dir", shared_dir / "reports")).resolve()),
            }
            changesets = self._run_workspace_changesets(workspace_run)
            artifacts = self._run_workspace_shared_files(workspace_run, "artifacts")
            reports = self._run_workspace_shared_files(workspace_run, "reports")

        return {
            "workspace_id": workspace_id,
            "workspace_root": str(root.resolve()),
            "shared_root": shared_root,
            "directories": run_directories,
            "jobs": (
                {
                    job_id: dict(entry)
                    for job_id, entry in self.workspace.jobs.items()
                }
                if self.workspace is not None
                else {}
            ),
            "changesets": changesets,
            "conflicts": conflicts,
            "artifacts": artifacts,
            "reports": reports,
        }

    def _workspace_run_for_snapshot(self) -> Any:
        if self.archive_run is not None:
            return self.archive_run
        if self.private_context_run is not None:
            return self.private_context_run
        return None

    @staticmethod
    def _read_workspace_json(path: Path) -> Dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _shared_write_metadata_by_path(self, workspace_run: Any) -> Dict[str, Dict[str, Any]]:
        run_path = Path(getattr(workspace_run, "path"))
        shared_dir = Path(getattr(workspace_run, "shared_dir", run_path / "shared"))
        manifest = self._read_workspace_json(shared_dir / "manifest.json")
        metadata: Dict[str, Dict[str, Any]] = {}
        writes = manifest.get("writes", [])
        if not isinstance(writes, list):
            return metadata
        for record in writes:
            if not isinstance(record, dict) or record.get("event_type") != "write":
                continue
            rel_path = str(record.get("path") or "").replace("\\", "/").strip("/")
            if not rel_path:
                continue
            entry = metadata.setdefault(rel_path, {"version": 0})
            entry["version"] = int(entry.get("version") or 0) + 1
            for key in ("owner", "bytes", "updated_at", "lease_id"):
                if key in record:
                    entry[key] = record[key]
        return metadata

    def _run_workspace_shared_files(self, workspace_run: Any, area: str) -> List[Dict[str, Any]]:
        run_path = Path(getattr(workspace_run, "path"))
        shared_dir = Path(getattr(workspace_run, "shared_dir", run_path / "shared"))
        area_dir = Path(getattr(workspace_run, f"shared_{area}_dir", shared_dir / area))
        if not area_dir.exists():
            return []
        metadata = self._shared_write_metadata_by_path(workspace_run)
        items: List[Dict[str, Any]] = []
        for path in sorted(area_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.resolve().relative_to(area_dir.resolve()).as_posix()
            shared_rel = f"{area}/{rel}"
            item: Dict[str, Any] = {
                "area": area,
                "name": path.name,
                "path": rel,
                "absolute_path": str(path.resolve()),
            }
            item.update(metadata.get(shared_rel, {}))
            items.append(item)
        return items

    def _run_workspace_changesets(self, workspace_run: Any) -> List[Dict[str, Any]]:
        run_path = Path(getattr(workspace_run, "path"))
        changesets_dir = run_path / "changesets"
        if not changesets_dir.exists():
            return []
        items: List[Dict[str, Any]] = []
        for path in sorted(changesets_dir.iterdir()):
            if not path.is_dir():
                continue
            changeset = self._read_workspace_json(path / "changeset.json")
            submit_result = self._read_workspace_json(path / "submit_result.json")
            status = str(submit_result.get("status") or changeset.get("status") or "")
            if status != "accepted":
                continue
            changeset_id = str(
                submit_result.get("changeset_id")
                or changeset.get("changeset_id")
                or path.name
            )
            files = submit_result.get("merged_files")
            if not isinstance(files, list):
                raw_files = changeset.get("files", [])
                files = [
                    str(item.get("path") if isinstance(item, dict) else item)
                    for item in raw_files
                    if isinstance(item, (dict, str))
                ]
            item: Dict[str, Any] = {
                "changeset_id": changeset_id,
                "name": changeset_id,
                "path": path.name,
                "absolute_path": str(path.resolve()),
                "files": [str(file) for file in files],
                "agent_id": changeset.get("agent_id"),
                "status": status,
            }
            if submit_result.get("integration_ref") is not None:
                item["integration_ref"] = submit_result["integration_ref"]
            items.append({key: value for key, value in item.items() if value is not None})
        return items

    def status_snapshot(
        self,
        *,
        graph: Optional["GraphDefinition"] = None,
        recent_events_limit: int = 20,
    ) -> Dict[str, Any]:
        """Return a top-agent/UI-friendly runtime status snapshot."""

        self._check_join_timeouts()
        if graph is not None:
            self.configure_common_nodes(graph)
        agents: Dict[str, Dict[str, Any]] = {}
        for node_id, inst in self._instances.items():
            agents[node_id] = {
                "node_id": node_id,
                "agent_id": inst.agent_id,
                "external": inst.external,
                "state": inst.state,
                "busy_count": inst.busy_count,
                "messages_sent": inst.messages_sent,
                "current_message_id": inst.current_message_id,
                "last_error": inst.last_error,
                "queue_size": len(self._agent_message_queues.get(node_id, [])),
                "started_at": inst.started_at,
                "updated_at": inst.updated_at,
                "has_received_flow": inst.has_received_flow,
                "idle_since": inst.idle_since,
                "task_status": inst.task_status,
                "task_summary": inst.task_summary,
                "task_status_updated_at": inst.task_status_updated_at,
                "task_status_message_id": inst.task_status_message_id,
                "task_status_batch_id": inst.task_status_batch_id,
                "task_status_reports": list(inst.task_status_reports),
                "task_status_artifacts": list(inst.task_status_artifacts),
                "task_status_changesets": list(inst.task_status_changesets),
                "task_status_next_actions": list(inst.task_status_next_actions),
                "task_status_metadata": dict(inst.task_status_metadata),
                "summary_prompted_at": inst.summary_prompted_at,
                "summary_prompt_message_id": inst.summary_prompt_message_id,
            }

        queue_state = {
            node_id: [message.to_dict() for message in queue]
            for node_id, queue in self._agent_message_queues.items()
        }
        pending_state = {
            message_id: message.to_dict()
            for message_id, message in self._pending_messages.items()
        }
        common_queue_state = {
            node_id: [message.to_dict() for message in queue]
            for node_id, queue in self._common_node_message_queues.items()
        }
        pending_common_state = {
            message_id: message.to_dict()
            for message_id, message in self._pending_common_messages.items()
        }
        common_state = {
            node_id: {
                **node.to_dict(),
                "queue_size": len(self._common_node_message_queues.get(node_id, [])),
                "tick_count": self._common_tick_counters.get(node_id, 0),
                "last_emit_at": self._common_tick_last_emit_at.get(node_id),
            }
            for node_id, node in self._common_nodes.items()
        }
        outgoing_state = {
            batch_id: batch.to_dict()
            for batch_id, batch in self._outgoing_batches.items()
        }
        join_state = {
            join_id: barrier.to_dict()
            for join_id, barrier in self._join_barriers.items()
        }
        jobs_state = {
            job_id: job.to_dict()
            for job_id, job in self._jobs.items()
        }
        events = self._events[-recent_events_limit:] if recent_events_limit >= 0 else self._events

        snapshot: Dict[str, Any] = {
            "run": {
                "status": self._run_status,
                "final_status": self._final_status,
                "ended_at": self._ended_at,
                "end_reason": self._end_reason,
                "closed": self._closed,
                "last_tick_at": self._last_tick_at,
                "manifest": dict(self._run_manifest),
                "message_journal": self._message_journal_summary(),
                "ready_for_top_agent_summary": self._ready_for_top_agent_summary,
                "summary_generation": self._completion_generation,
                "ready_for_top_agent_summary_generation": self._ready_for_top_agent_summary_generation,
            },
            "agents": agents,
            "common_nodes": common_state,
            "queues": {
                "by_agent": queue_state,
                "by_common_node": common_queue_state,
                "pending_messages": pending_state,
                "pending_common_messages": pending_common_state,
                "dispatching_message_ids": list(self._dispatch_tasks),
            },
            "outgoing_batches": outgoing_state,
            "agent_rings": self.agent_ring_status(graph),
            "joins": join_state,
            "jobs": jobs_state,
            "recent_events": [event.to_dict() for event in events],
            "agent_stream_events": self.agent_stream_events_after(),
            "workspace": self._workspace_state_snapshot(),
        }
        if graph is not None:
            snapshot["organization"] = graph.agent_organization_view()
        return snapshot

    def explain_status(
        self,
        *,
        graph: Optional["GraphDefinition"] = None,
        recent_events_limit: int = 20,
    ) -> Dict[str, Any]:
        """Return a compact top-agent status explanation grounded in events."""

        snapshot = self.status_snapshot(
            graph=graph,
            recent_events_limit=recent_events_limit,
        )
        agents = snapshot["agents"]
        queues = snapshot["queues"]
        outgoing = snapshot["outgoing_batches"]
        joins = snapshot["joins"]
        jobs = snapshot["jobs"]
        workspace = snapshot.get("workspace") or {}

        agent_states: Dict[str, List[str]] = {}
        for node_id, info in agents.items():
            agent_states.setdefault(str(info.get("state", "unknown")), []).append(node_id)

        pending_message_count = sum(len(items) for items in queues["by_agent"].values())
        pending_common_message_count = sum(len(items) for items in queues.get("by_common_node", {}).values())
        dispatching_message_count = len(queues.get("dispatching_message_ids", []))
        waiting_batches = {
            batch_id: batch
            for batch_id, batch in outgoing.items()
            if batch.get("status") == "staging"
        }
        waiting_joins = {
            join_id: join
            for join_id, join in joins.items()
            if join.get("status") == "waiting"
        }
        failed_jobs = {
            job_id: job
            for job_id, job in jobs.items()
            if job.get("status") == "failed"
        }
        running_jobs = {
            job_id: job
            for job_id, job in jobs.items()
            if job.get("status") in {"queued", "running"}
        }
        conflicts = list(workspace.get("conflicts", []))
        reports = list(workspace.get("reports", []))
        artifacts = list(workspace.get("artifacts", []))

        observations: List[str] = []
        run = snapshot["run"]
        observations.append(f"run is {run['status']}")
        if run.get("final_status"):
            observations.append(f"final status is {run['final_status']}")
        if pending_message_count:
            observations.append(f"{pending_message_count} queued agent message(s)")
        if pending_common_message_count:
            observations.append(f"{pending_common_message_count} queued common node message(s)")
        if dispatching_message_count:
            observations.append(f"{dispatching_message_count} dispatch task(s) in flight")
        if waiting_batches:
            observations.append(f"{len(waiting_batches)} outgoing batch(es) waiting for targets")
        if waiting_joins:
            observations.append(f"{len(waiting_joins)} join barrier(s) waiting for sources")
        if running_jobs:
            observations.append(f"{len(running_jobs)} background job(s) still running")
        if failed_jobs:
            observations.append(f"{len(failed_jobs)} failed job(s)")
        if conflicts:
            observations.append(f"{len(conflicts)} conflict item(s) reported")
        if not any(
            [
                pending_message_count,
                pending_common_message_count,
                dispatching_message_count,
                waiting_batches,
                waiting_joins,
                running_jobs,
                failed_jobs,
                conflicts,
            ]
        ):
            observations.append("no pending runtime work is visible")

        recommendations: List[str] = []
        if conflicts:
            recommendations.append("review conflicts before completing the run")
        if waiting_batches:
            recommendations.append("ask source agents to fill remaining outgoing targets")
        if waiting_joins:
            recommendations.append("wait for missing join sources or end with a partial result")
        if failed_jobs:
            recommendations.append("inspect failed jobs and retry or fail the run")
        if not recommendations and run["status"] == "running":
            recommendations.append("continue monitoring or complete the run after acceptance checks")
        if run["status"] in {"ended", "cancelled", "failed", "completed", "archived"}:
            recommendations.append("read final report and archive index before reporting to the user")

        event_summaries = []
        for event in snapshot["recent_events"]:
            event_summaries.append(
                {
                    "event_type": event.get("event_type"),
                    "node_id": event.get("node_id"),
                    "agent_id": event.get("agent_id"),
                    "status": event.get("status"),
                    "job_id": event.get("job_id"),
                    "payload_keys": sorted((event.get("payload") or {}).keys()),
                }
            )

        return {
            "summary": "; ".join(observations),
            "run": dict(run),
            "agent_states": {
                state: sorted(node_ids)
                for state, node_ids in agent_states.items()
            },
            "pending": {
                "queued_messages": pending_message_count,
                "queued_common_messages": pending_common_message_count,
                "dispatching_messages": dispatching_message_count,
                "waiting_outgoing_batches": {
                    batch_id: {
                        "source_node_id": batch.get("source_node_id"),
                        "remaining_targets": list(batch.get("remaining_targets", [])),
                    }
                    for batch_id, batch in waiting_batches.items()
                },
                "waiting_joins": {
                    join_id: {
                        "target_node_id": join.get("target_node_id"),
                        "missing_sources": list(join.get("missing_sources", [])),
                    }
                    for join_id, join in waiting_joins.items()
                },
                "running_jobs": sorted(running_jobs),
            },
            "risks": {
                "failed_jobs": sorted(failed_jobs),
                "conflicts": conflicts,
            },
            "outputs": {
                "reports": reports,
                "artifacts": artifacts,
            },
            "recent_events": event_summaries,
            "recommended_actions": recommendations,
        }

    def _summarize_for_final_state(self) -> Dict[str, Any]:
        self._check_join_timeouts()
        agent_states = {
            node_id: inst.state
            for node_id, inst in self._instances.items()
        }
        pending_messages = [
            message.to_dict()
            for message in self._pending_messages.values()
            if message.status in {"queued", "dispatching"}
        ]
        pending_common_messages = [
            message.to_dict()
            for message in self._pending_common_messages.values()
            if message.status in {"queued", "dispatching"}
        ]
        failed_messages = [
            message.to_dict()
            for message in self._pending_messages.values()
            if message.status == "failed"
        ]
        timed_out_joins = [
            barrier.to_dict()
            for barrier in self._join_barriers.values()
            if barrier.status == "timed_out"
        ]
        waiting_joins = [
            barrier.to_dict()
            for barrier in self._join_barriers.values()
            if barrier.status == "waiting"
        ]
        conflict_items = [
            item
            for barrier in self._join_barriers.values()
            for item in barrier.aggregate()["conflicts"]
        ]
        for event in self._events:
            if event.event_type == "ConflictDetected":
                conflict_items.append(dict(event.payload))
        failed_jobs = [
            job.to_dict()
            for job in self._jobs.values()
            if job.status == "failed"
        ]
        running_jobs = [
            job.to_dict()
            for job in self._jobs.values()
            if job.status in {"queued", "running"}
        ]
        accepted_changesets = [
            item
            for barrier in self._join_barriers.values()
            for item in barrier.aggregate()["accepted_changesets"]
        ]
        completed_jobs = [
            job.to_dict()
            for job in self._jobs.values()
            if job.status == "completed"
        ]
        return {
            "agent_states": agent_states,
            "pending_messages": pending_messages,
            "pending_common_messages": pending_common_messages,
            "failed_messages": failed_messages,
            "failed_jobs": failed_jobs,
            "running_jobs": running_jobs,
            "waiting_joins": waiting_joins,
            "timed_out_joins": timed_out_joins,
            "conflicts": conflict_items,
            "accepted_changesets": accepted_changesets,
            "completed_jobs": completed_jobs,
            "event_count": len(self._events),
        }

    def compute_final_status(self) -> RunFinalStatus:
        """Derive a deterministic final status from runtime state."""

        summary = self._summarize_for_final_state()
        if self._run_status == "cancelled":
            return "cancelled"
        if summary["timed_out_joins"] or any(
            state == "timed_out" for state in summary["agent_states"].values()
        ):
            return "timed_out"
        if summary["conflicts"]:
            return "conflicted"
        if summary["failed_messages"] or summary["failed_jobs"] or any(
            state in {"failed", "disconnected"} for state in summary["agent_states"].values()
        ):
            return "failed"
        if summary["pending_messages"] or summary["pending_common_messages"] or summary["running_jobs"] or summary["waiting_joins"]:
            if summary["completed_jobs"] or summary["accepted_changesets"]:
                return "partial_success"
            return "failed"
        return "success"

    def _cancel_pending_runtime_work(self, *, reason: str) -> Dict[str, Any]:
        cancelled_messages: List[str] = []
        for task in self._dispatch_tasks.values():
            task.cancel()
        for queue in self._agent_message_queues.values():
            queue.clear()
        for message in self._pending_messages.values():
            if message.status not in {"queued", "dispatching"}:
                continue
            message.status = "cancelled"
            message.error = reason or "run ended"
            message.completed_at = time.monotonic()
            cancelled_messages.append(message.message_id)
            self._emit(
                GraphEvent(
                    "AgentQueuedMessageCompleted",
                    node_id=message.node_id,
                    agent_id=message.agent_id,
                    status=message.status,
                    payload=message.to_dict(),
                )
            )

        cancelled_common_messages: List[str] = []
        for queue in self._common_node_message_queues.values():
            queue.clear()
        for message in self._pending_common_messages.values():
            if message.status not in {"queued", "dispatching"}:
                continue
            message.status = "cancelled"
            message.error = reason or "run ended"
            message.completed_at = time.monotonic()
            cancelled_common_messages.append(message.message_id)
            self._emit(
                GraphEvent(
                    "CommonNodeMessageCompleted",
                    node_id=message.node_id,
                    status=message.status,
                    payload=message.to_dict(),
                )
            )

        cancelled_jobs: List[str] = []
        for task in self._job_tasks.values():
            task.cancel()
        for job in self._jobs.values():
            if job.status not in {"queued", "running"}:
                continue
            job.status = "cancelled"
            cancelled_jobs.append(job.job_id)
            if self.workspace is not None:
                self.workspace.update_job(job.job_id, status=job.status, error=reason or "run ended")
            self._emit(
                GraphEvent(
                    "TaskCancelled",
                    job_id=job.job_id,
                    node_id=job.node_id,
                    agent_id=job.agent_id,
                    status=job.status,
                    payload={"reason": reason},
                )
            )

        cancelled_joins: List[str] = []
        for barrier in self._join_barriers.values():
            if barrier.status != "waiting":
                continue
            barrier.status = "cancelled"
            barrier.completed_at = time.monotonic()
            barrier.final_reason = reason or "run ended"
            cancelled_joins.append(barrier.join_id)
            self._emit(
                GraphEvent(
                    "JoinBarrierCancelled",
                    node_id=barrier.target_node_id,
                    status=barrier.status,
                    payload=barrier.aggregate(),
                )
            )

        summary = {
            "messages": cancelled_messages,
            "common_messages": cancelled_common_messages,
            "jobs": cancelled_jobs,
            "joins": cancelled_joins,
            "dispatch_tasks": list(self._dispatch_tasks),
            "job_tasks": list(self._job_tasks),
        }
        if any(summary[key] for key in ("messages", "common_messages", "jobs", "joins", "dispatch_tasks", "job_tasks")):
            self._emit(
                GraphEvent(
                    "RunPendingWorkCancelled",
                    status="cancelled",
                    payload={"reason": reason, **summary},
                )
            )
        self._dispatch_tasks.clear()
        self._job_tasks.clear()
        return summary

    def _archive_status_for_final(self) -> str:
        if self._final_status == "cancelled" or self._run_status == "cancelled":
            return "cancelled"
        if self._final_status in {"failed", "conflicted", "timed_out"} or self._run_status == "failed":
            return "failed"
        return "completed"

    def _write_final_report(self, result: RunEndResult) -> Optional[Path]:
        report = {
            "run_status": result.run_status,
            "final_status": result.final_status,
            "action": result.action,
            "reason": result.reason,
            "ended_at": result.ended_at,
            "summary": result.summary,
            "status_snapshot": self.status_snapshot(recent_events_limit=50),
        }
        target: Optional[Path] = None
        if self.archive_run is not None:
            reports_dir = getattr(self.archive_run, "shared_reports_dir", None)
            if reports_dir is not None:
                target = Path(reports_dir) / "final_report.json"
        if target is None and self.workspace is not None:
            target = self.workspace.workspace_root / "reports" / "final_report.json"
        if target is None:
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self._emit(
            GraphEvent(
                "FinalReportPublished",
                status=result.final_status or result.run_status,
                payload={"path": str(target), "final_status": result.final_status},
            )
        )
        return target

    def _write_run_manifest_end_state(self, result: RunEndResult) -> None:
        self._run_manifest["status"] = result.run_status
        self._run_manifest["end_reason"] = result.reason
        self._run_manifest["ended_at"] = result.ended_at
        if result.final_status is not None:
            self._run_manifest["final_status"] = result.final_status
        elif "final_status" in self._run_manifest:
            self._run_manifest.pop("final_status", None)

        manifest_path: Optional[Path] = None
        if self.archive_run is not None and getattr(self.archive_run, "path", None) is not None:
            manifest_path = Path(getattr(self.archive_run, "path")) / "run_manifest.json"
        if manifest_path is None and self.private_context_run is not None and getattr(self.private_context_run, "path", None) is not None:
            manifest_path = Path(getattr(self.private_context_run, "path")) / "run_manifest.json"
        if manifest_path is None:
            return

        try:
            data: Dict[str, Any] = {}
            if manifest_path.is_file():
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    data = {}
            data.update(
                {
                    "status": result.run_status,
                    "end_reason": result.reason,
                    "ended_at": result.ended_at,
                }
            )
            if result.final_status is not None:
                data["final_status"] = result.final_status
            else:
                data.pop("final_status", None)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:  # pragma: no cover - best-effort persistence
            log.warning("[graph] failed to update run manifest end state: %s", exc)

    def _archive_run_if_available(self) -> Optional[Path]:
        if self.archive_manager is None or self.archive_run is None:
            return None
        archive_run = getattr(self.archive_manager, "archive_run", None)
        if not callable(archive_run):
            return None
        archive_path = archive_run(self.archive_run, status=self._archive_status_for_final())
        self._emit(
            GraphEvent(
                "RunArchiveIndexed",
                status=self._archive_status_for_final(),
                payload={"path": str(archive_path)},
            )
        )
        return Path(archive_path)

    def _archived_report_path(
        self,
        report_path: Optional[Path],
        archive_path: Optional[Path],
    ) -> Optional[Path]:
        if report_path is None:
            return None
        if archive_path is None or self.archive_run is None:
            return report_path
        run_paths = [
            Path(raw)
            for raw in (
                getattr(self.archive_run, "_pre_archive_path", None),
                getattr(self.archive_run, "path", None),
            )
            if raw
        ]
        for run_path in run_paths:
            try:
                return archive_path / report_path.resolve().relative_to(run_path.resolve())
            except ValueError:
                continue
        return report_path

    def end_run(
        self,
        action: str,
        *,
        reason: str = "",
        archive: bool = False,
    ) -> RunEndResult:
        """End, pause, or archive the run through the framework-owned gate."""

        action = str(action).strip().lower()
        if action not in _VALID_RUN_END_ACTIONS:
            raise ValueError(f"unsupported run end action: {action!r}")
        if action == "pause":
            self._run_status = "paused"
            self._end_reason = reason
            result = RunEndResult(
                ok=True,
                action=action,
                run_status=self._run_status,
                final_status=None,
                reason=reason,
                summary=self._summarize_for_final_state(),
                archived=archive,
            )
            self._write_run_manifest_end_state(result)
            self._emit(GraphEvent("RunPaused", status="paused", payload=result.to_dict()))
            return result

        if action == "archive_only":
            result = RunEndResult(
                ok=True,
                action=action,
                run_status=self._run_status,
                final_status=self._final_status,
                reason=reason,
                summary=self._summarize_for_final_state(),
                archived=True,
            )
            report_path = self._write_final_report(result)
            archive_path = self._archive_run_if_available()
            final_report_path = self._archived_report_path(report_path, archive_path)
            if final_report_path is not None:
                result.summary["final_report_path"] = str(final_report_path)
            if archive_path is not None:
                result.summary["archive_path"] = str(archive_path)
            self._emit(GraphEvent("RunArchived", status=self._run_status, payload=result.to_dict()))
            return result

        if action == "cancel":
            cleanup = self._cancel_pending_runtime_work(reason=reason)
            self._run_status = "cancelled"
            self._final_status = "cancelled"
        elif action == "fail":
            cleanup = self._cancel_pending_runtime_work(reason=reason)
            self._run_status = "failed"
            self._final_status = "failed"
        else:
            cleanup = {}
            self._run_status = "completed"
            self._final_status = self.compute_final_status()
        self._ended_at = time.monotonic()
        self._end_reason = reason
        result = RunEndResult(
            ok=True,
            action=action,
            run_status=self._run_status,
            final_status=self._final_status,
            reason=reason,
            summary=self._summarize_for_final_state(),
            archived=archive,
            ended_at=self._ended_at,
        )
        if cleanup:
            result.summary["cancelled"] = cleanup
        self._write_run_manifest_end_state(result)
        if action == "complete":
            report_path = self._write_final_report(result)
            archive_path = self._archive_run_if_available()
            final_report_path = self._archived_report_path(report_path, archive_path)
            if final_report_path is not None:
                result.summary["final_report_path"] = str(final_report_path)
            if archive_path is not None:
                result.summary["archive_path"] = str(archive_path)
                result.archived = True
        self._emit(GraphEvent("RunEnded", status=self._final_status, payload=result.to_dict()))
        return result

    async def ensure_agent(self, node: AgentNode) -> AgentInstance:
        if self._closed:
            raise RuntimeError("GraphRuntime is closed")
        if node.node_id in self._instances:
            return self._instances[node.node_id]

        node = self._node_for_launch(node)
        agent_id = node.runtime_agent_id
        inst = AgentInstance(
            node=node,
            agent_id=agent_id,
            external=node.external,
            state="starting",
        )
        self._instances[node.node_id] = inst
        self._agent_message_queues.setdefault(node.node_id, [])
        ensure_worker = getattr(self.cluster, "ensure_worker", None)
        if callable(ensure_worker) and not node.external:
            try:
                await ensure_worker(node.to_worker_config())
            except Exception as exc:
                self._set_agent_state(inst, "failed", error=str(exc))
                self._instances.pop(node.node_id, None)
                raise
        self._set_agent_state(inst, "idle")
        log.info(
            "[graph] bound node_id=%s agent_id=%s cli_kind=%s external=%s",
            node.node_id,
            agent_id,
            node.cli_kind,
            node.external,
        )
        return inst

    async def prestart_agents(self, nodes: Sequence[AgentNode]) -> None:
        """Bind and start every AgentNode before graph execution begins."""
        for node in nodes:
            await self.ensure_agent(node)

    def configure_agent_rings(self, graph: "GraphDefinition") -> List[AgentRing]:
        """Ensure runtime counters exist for every concrete ring in ``graph``."""

        rings = graph.agent_rings()
        current_ids = {ring.ring_id for ring in rings}
        for ring in rings:
            existing = self._agent_rings.get(ring.ring_id)
            self._agent_rings[ring.ring_id] = ring
            for node_id in ring.ordered_node_ids:
                counts = self._agent_ring_circulation_counts.setdefault(node_id, {})
                if ring.ring_id not in counts:
                    counts[ring.ring_id] = (
                        existing.max_circulations
                        if existing is not None
                        else ring.max_circulations
                    )
        for node_id, counts in list(self._agent_ring_circulation_counts.items()):
            for ring_id in list(counts):
                if ring_id not in current_ids:
                    counts.pop(ring_id, None)
            if not counts:
                self._agent_ring_circulation_counts.pop(node_id, None)
        return rings

    def agent_ring_circulation_counts_for(self, node_id: str) -> Dict[str, int]:
        return dict(self._agent_ring_circulation_counts.get(node_id, {}))

    def agent_ring_status(self, graph: Optional["GraphDefinition"] = None) -> Dict[str, Any]:
        if graph is not None:
            self.configure_agent_rings(graph)
        remaining_by_ring: Dict[str, int] = {}
        for ring_id, ring in self._agent_rings.items():
            remaining_by_ring[ring_id] = min(
                (
                    self._agent_ring_circulation_counts.get(node_id, {}).get(
                        ring_id,
                        ring.max_circulations,
                    )
                    for node_id in ring.ordered_node_ids
                ),
                default=ring.max_circulations,
            )
        return {
            "rings": {
                ring_id: ring.to_dict(
                    remaining_circulations=remaining_by_ring.get(
                        ring_id,
                        ring.max_circulations,
                    )
                )
                for ring_id, ring in sorted(self._agent_rings.items())
            },
            "counts_by_agent": {
                node_id: dict(sorted(counts.items()))
                for node_id, counts in sorted(self._agent_ring_circulation_counts.items())
            },
        }

    def _ring_ids_for_edge(
        self,
        source_node_id: str,
        target_node_id: str,
    ) -> List[str]:
        return [
            ring_id
            for ring_id, ring in sorted(self._agent_rings.items())
            if ring.contains_edge(source_node_id, target_node_id)
        ]

    def _closing_ring_ids_for_edge(
        self,
        source_node_id: str,
        target_node_id: str,
    ) -> List[str]:
        return [
            ring_id
            for ring_id, ring in sorted(self._agent_rings.items())
            if ring.closing_edge == (source_node_id, target_node_id)
        ]

    def _remaining_for_ring(self, ring_id: str) -> int:
        ring = self._agent_rings[ring_id]
        return min(
            (
                self._agent_ring_circulation_counts.get(node_id, {}).get(
                    ring_id,
                    ring.max_circulations,
                )
                for node_id in ring.ordered_node_ids
            ),
            default=ring.max_circulations,
        )

    def can_forward_agent_edge(
        self,
        graph: "GraphDefinition",
        source_node_id: str,
        target_node_id: str,
    ) -> bool:
        self.configure_agent_rings(graph)
        ring_ids = self._ring_ids_for_edge(source_node_id, target_node_id)
        if not ring_ids:
            return True
        return any(self._remaining_for_ring(ring_id) > 0 for ring_id in ring_ids)

    def active_agent_connections(
        self,
        graph: "GraphDefinition",
        source_node_id: str,
    ) -> List[str]:
        self.configure_agent_rings(graph)
        return [
            target_node_id
            for target_node_id in graph.agent_connections().get(source_node_id, [])
            if self.can_forward_agent_edge(graph, source_node_id, target_node_id)
        ]

    def active_framework_connections(
        self,
        graph: "GraphDefinition",
        source_node_id: str,
    ) -> List[str]:
        self.configure_agent_rings(graph)
        self.configure_common_nodes(graph)
        if source_node_id not in graph.agent_nodes:
            return list(graph.framework_connections().get(source_node_id, []))
        targets: List[str] = []
        for target_node_id in graph.framework_targets_for_agent(source_node_id):
            if target_node_id in graph.agent_nodes and not self.can_forward_agent_edge(
                graph,
                source_node_id,
                target_node_id,
            ):
                continue
            targets.append(target_node_id)
        return targets

    def record_outgoing_edge_from_batch(
        self,
        batch_id: str,
        target_node_id: str,
    ) -> Dict[str, Any]:
        """Record a real dispatch over one batch edge and consume closing rings."""

        batch = self._outgoing_batches.get(batch_id)
        if batch is None:
            raise KeyError(f"unknown outgoing batch: {batch_id}")
        if target_node_id not in batch.required_target_node_ids:
            raise ValueError(
                f"target {target_node_id!r} is not required for batch {batch_id}"
            )
        if target_node_id in batch.ring_recorded_target_node_ids:
            return {"recorded": False, "consumed_ring_ids": []}

        ring_ids = list(batch.ring_ids_by_target.get(target_node_id, []))
        if ring_ids and not any(self._remaining_for_ring(ring_id) > 0 for ring_id in ring_ids):
            raise RuntimeError(
                "ring circulation limit reached for edge "
                f"{batch.source_node_id}->{target_node_id}: {', '.join(ring_ids)}"
            )

        consumed_ring_ids: List[str] = []
        exhausted_ring_ids: List[str] = []
        for ring_id in batch.closing_ring_ids_by_target.get(target_node_id, []):
            remaining = self._remaining_for_ring(ring_id)
            if remaining <= 0:
                continue
            ring = self._agent_rings[ring_id]
            next_remaining = max(remaining - 1, 0)
            for node_id in ring.ordered_node_ids:
                self._agent_ring_circulation_counts.setdefault(node_id, {})[ring_id] = next_remaining
            consumed_ring_ids.append(ring_id)
            if next_remaining == 0:
                exhausted_ring_ids.append(ring_id)

        batch.ring_recorded_target_node_ids.append(target_node_id)
        if consumed_ring_ids:
            payload = {
                "batch_id": batch.batch_id,
                "source_node_id": batch.source_node_id,
                "target_node_id": target_node_id,
                "consumed_ring_ids": list(consumed_ring_ids),
                "exhausted_ring_ids": list(exhausted_ring_ids),
                "counts_by_agent": self.agent_ring_status()["counts_by_agent"],
            }
            self._emit(
                GraphEvent(
                    "AgentRingCirculationAdvanced",
                    node_id=batch.source_node_id,
                    agent_id=batch.source_agent_id,
                    status="advanced",
                    payload=payload,
                )
            )
            for ring_id in exhausted_ring_ids:
                self._emit(
                    GraphEvent(
                        "AgentRingCirculationExhausted",
                        node_id=batch.source_node_id,
                        agent_id=batch.source_agent_id,
                        status="exhausted",
                        payload={
                            "batch_id": batch.batch_id,
                            "ring_id": ring_id,
                            "edge": {
                                "from": batch.source_node_id,
                                "to": target_node_id,
                            },
                            "ordered_node_ids": list(
                                self._agent_rings[ring_id].ordered_node_ids
                            ),
                        },
                    )
                )
        return {
            "recorded": True,
            "ring_ids": ring_ids,
            "consumed_ring_ids": consumed_ring_ids,
            "exhausted_ring_ids": exhausted_ring_ids,
        }

    async def create_outgoing_batch(
        self,
        source_node: AgentNode,
        required_targets: Sequence[AgentNode],
        *,
        batch_id: Optional[str] = None,
        allowed_targets: Optional[Sequence[AgentNode]] = None,
        ring_ids_by_target: Optional[Dict[str, Sequence[str]]] = None,
        closing_ring_ids_by_target: Optional[Dict[str, Sequence[str]]] = None,
        script_paths_by_target: Optional[Dict[str, Sequence[str]]] = None,
    ) -> OutgoingMessageBatch:
        """Start a framework-owned one-to-many handoff.

        ``required_targets`` is the exact set the source agent must cover in
        this control-flow step. Messages are staged until every target has an
        entry or an explicit no-op marker.
        """
        if self._closed:
            raise RuntimeError("GraphRuntime is closed")
        self._mark_run_running()
        if not required_targets:
            raise ValueError("required_targets must not be empty")
        source_inst = await self.ensure_agent(source_node)
        allowed_node_ids = (
            {node.node_id for node in allowed_targets}
            if allowed_targets is not None
            else {node.node_id for node in required_targets}
        )
        seen_targets: set[str] = set()
        target_node_ids: List[str] = []
        target_agent_ids: List[str] = []
        for target in required_targets:
            if target.node_id not in allowed_node_ids:
                raise ValueError(
                    f"required target {target.node_id!r} is not reachable from {source_node.node_id!r}"
                )
            if target.node_id in seen_targets:
                raise ValueError(f"duplicate required target: {target.node_id}")
            seen_targets.add(target.node_id)
            target_inst = await self.ensure_agent(target)
            target_node_ids.append(target.node_id)
            target_agent_ids.append(target_inst.agent_id)

        batch = OutgoingMessageBatch(
            batch_id=batch_id or f"out-{uuid.uuid4().hex[:12]}",
            source_node_id=source_node.node_id,
            source_agent_id=source_inst.agent_id,
            required_target_node_ids=target_node_ids,
            required_target_agent_ids=target_agent_ids,
            ring_ids_by_target={
                target: [str(ring_id) for ring_id in ring_ids]
                for target, ring_ids in (ring_ids_by_target or {}).items()
            },
            closing_ring_ids_by_target={
                target: [str(ring_id) for ring_id in ring_ids]
                for target, ring_ids in (closing_ring_ids_by_target or {}).items()
            },
            script_paths_by_target={
                target: [str(script_id) for script_id in script_ids]
                for target, script_ids in (script_paths_by_target or {}).items()
            },
            target_node_kinds_by_target={
                target_id: "agent"
                for target_id in target_node_ids
            },
        )
        self._outgoing_batches[batch.batch_id] = batch
        self._emit(
            GraphEvent(
                "AgentOutgoingBatchCreated",
                node_id=source_node.node_id,
                agent_id=source_inst.agent_id,
                status=batch.status,
                payload=batch.to_dict(),
            )
        )
        return batch

    async def create_outgoing_batch_from_graph(
        self,
        graph: "GraphDefinition",
        source_node_id: str,
        *,
        required_target_node_ids: Optional[Sequence[str]] = None,
        batch_id: Optional[str] = None,
    ) -> OutgoingMessageBatch:
        """Create an outgoing batch using graph-derived agent connections."""
        if source_node_id not in graph.agent_nodes:
            raise KeyError(f"unknown source AgentNode: {source_node_id}")
        self.configure_agent_rings(graph)
        self.configure_common_nodes(graph)
        allowed_target_ids = self.active_framework_connections(graph, source_node_id)
        if required_target_node_ids is None:
            required_ids = list(allowed_target_ids)
        else:
            required_ids = [str(node_id) for node_id in required_target_node_ids]
        graph_node_ids = graph._node_ids()
        missing = [node_id for node_id in required_ids if node_id not in graph_node_ids]
        if missing:
            raise KeyError(f"unknown target node(s): {', '.join(missing)}")
        disallowed = [node_id for node_id in required_ids if node_id not in allowed_target_ids]
        if disallowed:
            raise ValueError(
                f"target node(s) not reachable from {source_node_id!r}: "
                + ", ".join(disallowed)
            )
        if not required_ids:
            raise ValueError("required_targets must not be empty")

        source_inst = await self.ensure_agent(graph.agent_nodes[source_node_id])
        seen_targets: set[str] = set()
        target_agent_ids: List[str] = []
        target_node_kinds: Dict[str, str] = {}
        for target_id in required_ids:
            if target_id in seen_targets:
                raise ValueError(f"duplicate required target: {target_id}")
            seen_targets.add(target_id)
            if target_id in graph.agent_nodes:
                target_inst = await self.ensure_agent(graph.agent_nodes[target_id])
                target_agent_ids.append(target_inst.agent_id)
                target_node_kinds[target_id] = "agent"
            elif target_id in graph.common_nodes:
                target_agent_ids.append(target_id)
                target_node_kinds[target_id] = f"common:{graph.common_nodes[target_id].kind}"
            else:
                target_agent_ids.append(target_id)
                target_node_kinds[target_id] = "node"

        script_paths_by_target = {
            target_id: self.graph_script_path(graph, source_node_id, target_id)
            for target_id in required_ids
            if target_id in graph.agent_nodes
        }
        batch = OutgoingMessageBatch(
            batch_id=batch_id or f"out-{uuid.uuid4().hex[:12]}",
            source_node_id=source_node_id,
            source_agent_id=source_inst.agent_id,
            required_target_node_ids=list(required_ids),
            required_target_agent_ids=target_agent_ids,
            ring_ids_by_target={
                target_id: self._ring_ids_for_edge(source_node_id, target_id)
                for target_id in required_ids
                if target_id in graph.agent_nodes
            },
            closing_ring_ids_by_target={
                target_id: self._closing_ring_ids_for_edge(source_node_id, target_id)
                for target_id in required_ids
                if target_id in graph.agent_nodes
            },
            script_paths_by_target=script_paths_by_target,
            script_calls=self.script_calls_from_paths(graph, script_paths_by_target),
            target_node_kinds_by_target=target_node_kinds,
        )
        self._outgoing_batches[batch.batch_id] = batch
        self._emit(
            GraphEvent(
                "AgentOutgoingBatchCreated",
                node_id=source_node_id,
                agent_id=source_inst.agent_id,
                status=batch.status,
                payload=batch.to_dict(),
            )
        )
        return batch

    @staticmethod
    def graph_script_path(graph: "GraphDefinition", source_node_id: str, target_node_id: str) -> List[str]:
        if hasattr(graph, "script_path_between_agents"):
            return graph.script_path_between_agents(source_node_id, target_node_id)
        return []

    @staticmethod
    def script_calls_from_paths(
        graph: "GraphDefinition",
        script_paths_by_target: Dict[str, Sequence[str]],
    ) -> Dict[str, Dict[str, Any]]:
        calls: Dict[str, Dict[str, Any]] = {}
        for target_id, script_path in script_paths_by_target.items():
            for script_node_id in script_path:
                node = graph.script_nodes.get(str(script_node_id))
                if node is None:
                    continue
                record = calls.setdefault(
                    node.node_id,
                    {
                        "script_node_id": node.node_id,
                        "script_id": node.script_id,
                        "module_path": node.module_path,
                        "function_name": node.function_name,
                        "title": node.title,
                        "description": node.description,
                        "inputs": [port.to_dict() for port in node.inputs],
                        "outputs": [port.to_dict() for port in node.outputs],
                        "required_target_node_ids": [],
                        "delivered_target_node_ids": [],
                        "status": "pending",
                    },
                )
                targets = record["required_target_node_ids"]
                if target_id not in targets:
                    targets.append(str(target_id))
        return calls

    def stage_outgoing_message(
        self,
        batch_id: str,
        target_node: AgentNode,
        body: Any,
    ) -> Dict[str, Any]:
        """Stage or overwrite a source agent's message for one required target."""
        inst = self._instances.get(target_node.node_id)
        target_agent_id = inst.agent_id if inst is not None else target_node.runtime_agent_id
        return self._stage_outgoing_message_to_target(
            batch_id,
            target_node.node_id,
            target_agent_id,
            body,
            target_node_kind="agent",
        )

    def stage_outgoing_common_node_message(
        self,
        batch_id: str,
        target_node: CommonNode,
        body: Any,
    ) -> Dict[str, Any]:
        return self._stage_outgoing_message_to_target(
            batch_id,
            target_node.node_id,
            target_node.node_id,
            body,
            target_node_kind=f"common:{target_node.kind}",
        )

    def _stage_outgoing_message_to_target(
        self,
        batch_id: str,
        target_node_id: str,
        target_agent_id: str,
        body: Any,
        *,
        target_node_kind: str,
    ) -> Dict[str, Any]:
        batch = self._outgoing_batches.get(batch_id)
        if batch is None:
            raise KeyError(f"unknown outgoing batch: {batch_id}")
        if batch.status != "staging":
            raise RuntimeError(f"outgoing batch {batch_id} is already {batch.status}")
        if target_node_id not in batch.required_target_node_ids:
            raise ValueError(
                f"target {target_node_id!r} is not required for batch {batch_id}"
            )

        previous = batch.staged_messages.get(target_node_id)
        overwritten = previous is not None
        overwrite_count = (previous.overwrite_count + 1) if previous is not None else 0
        is_no_op = is_dispatch_no_op_body(body)
        ring_record: Dict[str, Any] = {"recorded": False, "consumed_ring_ids": []}
        if is_no_op:
            batch.staged_messages.pop(target_node_id, None)
            if target_node_id not in batch.no_op_target_node_ids:
                batch.no_op_target_node_ids.append(target_node_id)
        else:
            if str(target_node_kind) == "agent":
                ring_record = self.record_outgoing_edge_from_batch(batch.batch_id, target_node_id)
            if target_node_id in batch.no_op_target_node_ids:
                batch.no_op_target_node_ids.remove(target_node_id)
            batch.staged_messages[target_node_id] = StagedOutgoingMessage(
                target_node_id=target_node_id,
                target_agent_id=target_agent_id,
                body=body,
                target_node_kind=target_node_kind,
                overwrite_count=overwrite_count,
            )
        batch.last_reminder_targets = []
        remaining = batch.remaining_targets
        ready = not remaining
        self._emit(
            GraphEvent(
                "AgentMessageStaged",
                node_id=batch.source_node_id,
                agent_id=batch.source_agent_id,
                status="staged",
                payload={
                    "batch_id": batch.batch_id,
                    "target_node_id": target_node_id,
                    "target_agent_id": target_agent_id,
                    "target_node_kind": target_node_kind,
                    "overwritten": overwritten,
                    "no_op": is_no_op,
                    "ready_to_dispatch": ready,
                    "remaining_targets": list(remaining),
                    "ring_record": dict(ring_record),
                },
            )
        )
        if is_no_op:
            self._emit(
                GraphEvent(
                    "AgentOutgoingTargetNoOp",
                    node_id=batch.source_node_id,
                    agent_id=batch.source_agent_id,
                    status="staged",
                    payload={
                        "batch_id": batch.batch_id,
                        "target_node_id": target_node_id,
                        "target_agent_id": target_agent_id,
                        "target_node_kind": target_node_kind,
                        "remaining_targets": list(remaining),
                    },
                )
            )
        self._record_message_io(
            record_type="agent.outgoing.no_op" if is_no_op else "agent.outgoing.staged",
            sender={
                "type": "agent",
                "agent_id": batch.source_agent_id,
                "node_id": batch.source_node_id,
            },
            receiver={"type": "framework"},
            payload=body,
            batch_id=batch.batch_id,
            status="staged",
            metadata={
                "target_node_id": target_node_id,
                "target_agent_id": target_agent_id,
                "target_node_kind": target_node_kind,
                "overwritten": overwritten,
                "no_op": is_no_op,
                "ready_to_dispatch": ready,
                "remaining_targets": list(remaining),
                "ring_record": dict(ring_record),
            },
        )
        if ready:
            dispatched = self.dispatch_outgoing_batch(batch.batch_id)
            remaining = dispatched["remaining_targets"]
        return {
            "staged": True,
            "overwritten": overwritten,
            "no_op": is_no_op,
            "ready_to_dispatch": ready,
            "remaining_targets": list(remaining),
            "batch_id": batch.batch_id,
            "ring_record": dict(ring_record),
        }

    def dispatch_outgoing_batch(self, batch_id: str) -> Dict[str, Any]:
        """Queue a complete staged batch into downstream agent queues."""
        batch = self._outgoing_batches.get(batch_id)
        if batch is None:
            raise KeyError(f"unknown outgoing batch: {batch_id}")
        if batch.status != "staging":
            raise RuntimeError(f"outgoing batch {batch_id} is already {batch.status}")
        remaining = batch.remaining_targets
        if remaining:
            raise RuntimeError(
                f"outgoing batch {batch_id} is missing target messages: {', '.join(remaining)}"
            )

        message_ids: List[str] = []
        for target_node_id in batch.required_target_node_ids:
            if target_node_id in batch.no_op_target_node_ids:
                continue
            staged = batch.staged_messages[target_node_id]
            target_kind = batch.target_node_kinds_by_target.get(target_node_id, staged.target_node_kind)
            if target_kind.startswith("common:"):
                pending = self.queue_common_node_message(
                    target_node_id,
                    staged.body,
                    source_node_id=batch.source_node_id,
                    source_agent_id=batch.source_agent_id,
                )
                message_ids.append(pending.message_id)
                continue
            target_inst = self._instances.get(target_node_id)
            if target_inst is None:
                raise KeyError(f"target agent is not started: {target_node_id}")
            body = staged.body
            pending = self.queue_agent_message(
                target_inst.node,
                body,
                source_node_id=batch.source_node_id,
                source_agent_id=batch.source_agent_id,
            )
            message_ids.append(pending.message_id)

        batch.status = "dispatched"
        batch.dispatched_message_ids = message_ids
        self._emit(
            GraphEvent(
                "AgentOutgoingBatchDispatched",
                node_id=batch.source_node_id,
                agent_id=batch.source_agent_id,
                status=batch.status,
                payload=batch.to_dict(),
            )
        )
        return {
            "batch_id": batch.batch_id,
            "status": batch.status,
            "ready_to_dispatch": True,
            "remaining_targets": [],
            "message_ids": list(message_ids),
        }

    async def send_agent_message(
        self,
        node: AgentNode,
        body: Any,
        *,
        timeout_sec: Optional[float] = None,
        source_node_id: Optional[str] = None,
        source_agent_id: Optional[str] = None,
        queue_mode: str = "default",
    ) -> Dict[str, Any]:
        self._mark_run_running()
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
        if not inst.can_accept_message:
            pending = self.queue_agent_message(
                node,
                body,
                timeout_sec=timeout_sec,
                source_node_id=source_node_id,
                source_agent_id=source_agent_id,
                queue_mode=queue_mode,
            )
            return {
                "type": "graph_message_queued",
                "message_id": pending.message_id,
                "node_id": pending.node_id,
                "agent_id": pending.agent_id,
                "status": pending.status,
                "queue_size": len(self._agent_message_queues.get(node.node_id, [])),
            }
        return await self._dispatch_agent_message(
            node,
            body,
            timeout_sec=timeout_sec,
            message_id=f"msg-{uuid.uuid4().hex[:12]}",
        )

    def queue_agent_message(
        self,
        node: AgentNode,
        body: Any,
        *,
        timeout_sec: Optional[float] = None,
        source_node_id: Optional[str] = None,
        source_agent_id: Optional[str] = None,
        message_id: Optional[str] = None,
        queue_mode: str = "default",
    ) -> PendingAgentMessage:
        """Store a message until the target agent returns to an idle state."""
        if self._closed:
            raise RuntimeError("GraphRuntime is closed")
        normalized_queue_mode = str(queue_mode or "default").strip().lower()
        if normalized_queue_mode not in {"default", "top"}:
            raise ValueError("queue_mode must be 'default' or 'top'")
        self._mark_run_running()
        inst = self._instances.get(node.node_id)
        agent_id = inst.agent_id if inst is not None else node.runtime_agent_id
        pending = PendingAgentMessage(
            message_id=message_id or f"msg-{uuid.uuid4().hex[:12]}",
            node_id=node.node_id,
            agent_id=agent_id,
            body=body,
            source_node_id=source_node_id,
            source_agent_id=source_agent_id,
            timeout_sec=timeout_sec,
            queue_mode=normalized_queue_mode,
        )
        if inst is not None:
            self._mark_agent_flow_received(inst, message_id=pending.message_id, body=body)
        queue = self._agent_message_queues.setdefault(node.node_id, [])
        if normalized_queue_mode == "top":
            queue.insert(0, pending)
        else:
            queue.append(pending)
        self._pending_messages[pending.message_id] = pending
        if inst is not None and inst.state == "idle":
            self._set_agent_state(inst, "queued")
        self.record_agent_stream_event(
            {
                "kind": "queue.updated",
                "node_id": node.node_id,
                "agent_id": agent_id,
                "message_id": pending.message_id,
                "status": pending.status,
                "queue_size": len(queue),
                "queue_mode": normalized_queue_mode,
            }
        )
        self._record_message_io(
            record_type="framework.message.queued",
            sender={
                "type": "agent" if source_agent_id else "framework",
                "agent_id": source_agent_id,
                "node_id": source_node_id,
            },
            receiver={"type": "agent", "agent_id": agent_id, "node_id": node.node_id},
            payload=body,
            message_id=pending.message_id,
            status=pending.status,
        )
        self._emit(
            GraphEvent(
                "AgentMessageQueued",
                node_id=node.node_id,
                agent_id=agent_id,
                status=pending.status,
                payload=pending.to_dict(),
            )
        )
        return pending

    def queue_common_node_message(
        self,
        node_id: str,
        body: Any,
        *,
        source_node_id: Optional[str] = None,
        source_agent_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> PendingCommonNodeMessage:
        if self._closed:
            raise RuntimeError("GraphRuntime is closed")
        node_id = str(node_id).strip()
        if node_id not in self._common_nodes:
            raise KeyError(f"unknown CommonNode: {node_id}")
        self._mark_run_running()
        pending = PendingCommonNodeMessage(
            message_id=message_id or f"cmsg-{uuid.uuid4().hex[:12]}",
            node_id=node_id,
            body=body,
            source_node_id=source_node_id,
            source_agent_id=source_agent_id,
        )
        queue = self._common_node_message_queues.setdefault(node_id, [])
        queue.append(pending)
        self._pending_common_messages[pending.message_id] = pending
        self.record_agent_stream_event(
            {
                "kind": "common.queue.updated",
                "node_id": node_id,
                "message_id": pending.message_id,
                "status": pending.status,
                "queue_size": len(queue),
            }
        )
        self._record_message_io(
            record_type="framework.common_message.queued",
            sender={
                "type": "agent" if source_agent_id else "framework",
                "agent_id": source_agent_id,
                "node_id": source_node_id,
            },
            receiver={"type": "common_node", "node_id": node_id},
            payload=body,
            message_id=pending.message_id,
            status=pending.status,
        )
        self._emit(
            GraphEvent(
                "CommonNodeMessageQueued",
                node_id=node_id,
                status=pending.status,
                payload=pending.to_dict(),
            )
        )
        return pending

    async def _dispatch_pending_message(
        self,
        node: AgentNode,
        pending: PendingAgentMessage,
    ) -> None:
        try:
            pending.receipt = await self._dispatch_agent_message(
                node,
                pending.body,
                timeout_sec=pending.timeout_sec,
                message_id=pending.message_id,
            )
            pending.status = "completed"
        except asyncio.CancelledError:
            pending.status = "cancelled"
            raise
        except Exception as exc:  # pragma: no cover - defensive queued event contract
            pending.status = "failed"
            pending.error = str(exc)
        finally:
            pending.completed_at = time.monotonic()
            self.record_agent_stream_event(
                {
                    "kind": "queue.updated",
                    "node_id": pending.node_id,
                    "agent_id": pending.agent_id,
                    "message_id": pending.message_id,
                    "status": pending.status,
                    "queue_size": len(self._agent_message_queues.get(pending.node_id, [])),
                    "queue_mode": pending.queue_mode,
                    "last_error": pending.error,
                }
            )
            self._emit(
                GraphEvent(
                    "AgentQueuedMessageCompleted",
                    node_id=pending.node_id,
                    agent_id=pending.agent_id,
                    status=pending.status,
                    payload=pending.to_dict(),
                )
            )

    async def _dispatch_agent_message(
        self,
        node: AgentNode,
        body: Any,
        *,
        timeout_sec: Optional[float] = None,
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        message_id = message_id or f"msg-{uuid.uuid4().hex[:12]}"
        inst = await self.ensure_agent(node)
        sections, run_prompt_included, prompt_node_ids = self._agent_prompt_sections(inst)
        body, injected = _prepend_prompt_sections_to_body(body, sections)
        if injected:
            if run_prompt_included:
                inst.run_prompt_injected = True
            inst.prompt_node_injected_ids.update(prompt_node_ids)
        inst.busy_count += 1
        busy_released = False

        def release_busy() -> None:
            nonlocal busy_released
            if busy_released:
                return
            inst.busy_count = max(0, inst.busy_count - 1)
            busy_released = True

        self._mark_agent_flow_received(inst, message_id=message_id, body=body)
        self.record_agent_stream_event(
            self._agent_stream_status_event(
                inst,
                kind="message.started",
                message_id=message_id,
            )
        )
        self._record_message_io(
            record_type="framework.message.sent",
            sender={"type": "framework"},
            receiver={"type": "agent", "agent_id": inst.agent_id, "node_id": node.node_id},
            payload=body,
            message_id=message_id,
            status="dispatching",
        )
        self._set_agent_state(inst, "dispatching", message_id=message_id)
        try:
            self._set_agent_state(inst, "running", message_id=message_id)
            self._set_agent_state(inst, "waiting_for_reply", message_id=message_id)
            stream_meta = {
                "run_id": self.agent_stream_run_id,
                "node_id": node.node_id,
                "agent_id": inst.agent_id,
                "message_id": message_id,
            }
            effective_timeout = timeout_sec if timeout_sec is not None else node.timeout_sec
            callback = self.agent_message_context_callback
            if callback is not None:
                try:
                    result = callback(
                        {
                            "run_id": self.agent_stream_run_id,
                            "node_id": node.node_id,
                            "agent_id": inst.agent_id,
                            "message_id": message_id,
                            "body": body,
                            "timeout_sec": effective_timeout,
                        }
                    )
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    log.exception("agent message context callback failed")
            try:
                reply = await self.cluster.run_single(
                    inst.agent_id,
                    body,
                    timeout_sec=effective_timeout,
                    meta={"framework_stream": stream_meta},
                    stream_callback=self.record_agent_stream_event,
                )
            except TypeError as exc:
                if "unexpected keyword" not in str(exc):
                    raise
                reply = await self.cluster.run_single(
                    inst.agent_id,
                    body,
                    timeout_sec=effective_timeout,
                )
            failure_reason = _reply_failure_reason(reply)
            if failure_reason is not None:
                raise AgentMessageFailed(f"agent reply failed: {failure_reason}")
            self._set_agent_state(inst, "processing_reply", message_id=message_id)
        except asyncio.TimeoutError:
            release_busy()
            self._set_agent_state(inst, "timed_out", error="timeout", message_id=message_id)
            self._record_message_io(
                record_type="framework.message.failed",
                sender={"type": "framework"},
                receiver={"type": "agent", "agent_id": inst.agent_id, "node_id": node.node_id},
                message_id=message_id,
                status="timed_out",
                metadata={"error": "timeout"},
            )
            raise
        except asyncio.CancelledError:
            release_busy()
            self._set_agent_state(inst, "cancelled", message_id=message_id)
            self._record_message_io(
                record_type="framework.message.failed",
                sender={"type": "framework"},
                receiver={"type": "agent", "agent_id": inst.agent_id, "node_id": node.node_id},
                message_id=message_id,
                status="cancelled",
            )
            raise
        except AgentMessageFailed as exc:
            release_busy()
            self._set_agent_state(inst, "idle", error=str(exc), message_id=message_id)
            self._record_message_io(
                record_type="framework.message.failed",
                sender={"type": "framework"},
                receiver={"type": "agent", "agent_id": inst.agent_id, "node_id": node.node_id},
                message_id=message_id,
                status="failed",
                metadata={"error": str(exc)},
            )
            raise
        except Exception as exc:
            release_busy()
            self._set_agent_state(inst, "failed", error=str(exc), message_id=message_id)
            self._record_message_io(
                record_type="framework.message.failed",
                sender={"type": "framework"},
                receiver={"type": "agent", "agent_id": inst.agent_id, "node_id": node.node_id},
                message_id=message_id,
                status="failed",
                metadata={"error": str(exc)},
            )
            raise
        finally:
            release_busy()
        inst.messages_sent += 1
        self._set_agent_state(inst, "idle")
        task_id = self._task_id_from_body(body, message_id=message_id)
        utterance = self._record_agent_utterance(
            node_id=node.node_id,
            agent_id=inst.agent_id,
            reply=reply,
            message_id=message_id,
            task_id=task_id,
        )
        self.record_agent_stream_event(
            {
                "kind": "message.completed",
                "node_id": node.node_id,
                "agent_id": inst.agent_id,
                "message_id": message_id,
                "part_id": utterance.utterance_id,
                "part_type": "text",
                "field": "text",
                "text": utterance.said,
                "status": "completed",
                "agent_state": inst.state,
                "busy_count": inst.busy_count,
                "queue_size": len(self._agent_message_queues.get(node.node_id, [])),
                "current_message_id": inst.current_message_id,
                "messages_sent": inst.messages_sent,
                "last_error": inst.last_error,
            }
        )
        return utterance.to_dict()

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
        self._mark_run_running()
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
            self._job_tasks[job.job_id] = asyncio.create_task(
                self._run_agent_job(job, node, body, timeout_sec=timeout_sec)
            )
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
            receipt = await self._dispatch_agent_message(
                node,
                body,
                timeout_sec=timeout_sec,
                message_id=job.job_id,
            )
        except asyncio.CancelledError:
            job.status = "cancelled"
            if self.workspace is not None:
                self.workspace.update_job(job.job_id, status=job.status, error="cancelled")
            self._emit(
                GraphEvent(
                    "TaskCancelled",
                    job_id=job.job_id,
                    node_id=job.node_id,
                    agent_id=job.agent_id,
                    status=job.status,
                )
            )
            self._job_tasks.pop(job.job_id, None)
            return
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
            self._job_tasks.pop(job.job_id, None)
            return

        job.status = "completed"
        inst = self._instances.get(node.node_id)
        if inst is not None:
            inst.messages_sent += 1
        if self.workspace is not None:
            self.workspace.update_job(job.job_id, status=job.status, result=receipt)
        self._emit(
            GraphEvent(
                "TaskCompleted",
                job_id=job.job_id,
                node_id=job.node_id,
                agent_id=job.agent_id,
                status=job.status,
                payload={"receipt": receipt},
            )
        )
        self._job_tasks.pop(job.job_id, None)

    async def assign_agent_workdir(
        self,
        *,
        super_agent: Any,
        target_node_id: str,
        cwd: Path,
    ) -> WorkdirAssignmentResult:
        if self._closed:
            raise RuntimeError("GraphRuntime is closed")
        if not hasattr(super_agent, "validate_workdir_assignment"):
            raise PermissionError("workdir assignment requires a SuperAgentProfile")
        inst = self._instances.get(target_node_id)
        if inst is None:
            raise KeyError(f"unknown or unstarted AgentNode: {target_node_id}")
        if inst.busy_count > 0:
            return WorkdirAssignmentResult(
                ok=False,
                agent_id=inst.agent_id,
                node_id=target_node_id,
                error_code="AGENT_BUSY",
                error="target agent is currently executing a task",
            )
        resolved = super_agent.validate_workdir_assignment(cwd)
        restart_worker = getattr(self.cluster, "restart_worker", None)
        if not callable(restart_worker):
            return WorkdirAssignmentResult(
                ok=False,
                agent_id=inst.agent_id,
                node_id=target_node_id,
                error_code="RESTART_UNSUPPORTED",
                error="cluster does not support worker restart",
            )
        new_node = AgentNode.from_dict(inst.node.to_dict())
        new_node.cwd = resolved
        self._set_agent_state(inst, "restarting")
        try:
            await restart_worker(new_node.to_worker_config())
        except Exception as exc:
            self._set_agent_state(inst, "failed", error=str(exc))
            raise
        inst.node = new_node
        inst.busy_count = 0
        self._set_agent_state(inst, "idle")
        self._emit(
            GraphEvent(
                "AgentWorkdirAssigned",
                node_id=target_node_id,
                agent_id=inst.agent_id,
                status="completed",
                payload={"cwd": str(resolved), "assigned_by": getattr(super_agent, "agent_id", None)},
            )
        )
        return WorkdirAssignmentResult(
            ok=True,
            agent_id=inst.agent_id,
            node_id=target_node_id,
            cwd=resolved,
        )

    async def close(self) -> None:
        """Detach runtime bindings.

        Process teardown is delegated to the owning cluster. External agent
        bindings are never killed here.
        """
        if self._closed:
            return
        log.info("[graph] closing runtime instances=%s", list(self._instances))
        await self.stop_tick_loop()
        for task in self._dispatch_tasks.values():
            task.cancel()
        if self._dispatch_tasks:
            await asyncio.gather(*self._dispatch_tasks.values(), return_exceptions=True)
        self._dispatch_tasks.clear()
        for inst in self._instances.values():
            self._set_agent_state(inst, "stopped")
        self._instances.clear()
        self._launch_nodes.clear()
        rpc_server = self.private_context_rpc_server
        if rpc_server is not None and self.enforce_private_agent_context:
            close = getattr(rpc_server, "close", None)
            if callable(close):
                close()
            self.private_context_rpc_server = None
        self._closed = True

    async def __aenter__(self) -> "GraphRuntime":
        self.start_tick_loop()
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
        meta: Optional[Dict[str, Any]] = None,
        stream_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Dict[str, Any]:
        client = await self._ensure_client()
        await client.send_to(worker_id, body, meta=meta)

        async def _stream(event: Dict[str, Any]) -> None:
            if stream_callback is not None:
                result = stream_callback(event)
                if asyncio.iscoroutine(result):
                    await result

        return await client.wait_for_message(
            expect_from=worker_id,
            timeout_sec=timeout_sec,
            stream_callback=_stream if stream_callback is not None else None,
        )

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
class CommonNode:
    """Framework-owned built-in blueprint node."""

    node_id: str
    kind: CommonNodeKind
    every_n_seconds: float = 1.0
    every_n_ticks: Optional[int] = None

    def __post_init__(self) -> None:
        self.node_id = str(self.node_id).strip()
        self.kind = str(self.kind or "").strip().lower()
        if not self.node_id:
            raise ValueError("CommonNode.node_id must be non-empty")
        if self.kind not in _VALID_COMMON_NODE_KINDS:
            raise ValueError(
                "CommonNode.kind must be one of "
                + ", ".join(sorted(_VALID_COMMON_NODE_KINDS))
            )
        try:
            legacy_ticks = self.every_n_ticks
            raw_seconds = legacy_ticks if legacy_ticks is not None and self.every_n_seconds == 1.0 else self.every_n_seconds
            self.every_n_seconds = max(1.0, float(raw_seconds))
        except (TypeError, ValueError):
            raise ValueError("Tick CommonNode.every_n_seconds must be a number") from None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "node_id": self.node_id,
            "kind": self.kind,
        }
        if self.kind == "tick":
            data["every_n_seconds"] = int(self.every_n_seconds) if self.every_n_seconds.is_integer() else self.every_n_seconds
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommonNode":
        if not isinstance(data, dict):
            raise ValueError("CommonNode data must be an object")
        return cls(
            node_id=str(data.get("node_id", "")).strip(),
            kind=str(data.get("kind", "")),
            every_n_seconds=float(data.get("every_n_seconds", data.get("every_n_ticks", 1)) or 1),
        )


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
class PromptNode:
    """Canvas prompt text node connected to Agent prompt data inputs."""

    node_id: str
    text: str = ""
    trigger: PromptNodeTrigger = "once"
    expanded: bool = False

    def __post_init__(self) -> None:
        self.node_id = str(self.node_id).strip()
        if not self.node_id:
            raise ValueError("PromptNode.node_id must be non-empty")
        self.text = str(self.text or "")
        self.trigger = str(self.trigger or "once").strip().lower()
        if self.trigger not in _VALID_PROMPT_NODE_TRIGGERS:
            raise ValueError("PromptNode.trigger must be 'once' or 'always'")
        self.expanded = bool(self.expanded)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "text": self.text,
            "trigger": self.trigger,
            "expanded": self.expanded,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptNode":
        if not isinstance(data, dict):
            raise ValueError("PromptNode data must be an object")
        return cls(
            node_id=str(data.get("node_id", "")).strip(),
            text=str(data.get("text", data.get("prompt", ""))),
            trigger=str(data.get("trigger", data.get("mode", "once"))),
            expanded=bool(data.get("expanded", False)),
        )


@dataclass
class ScriptNode:
    """User-authored Python function node compiled into a blueprint graph."""

    node_id: str
    script_id: str
    module_path: str
    function_name: str
    title: str = ""
    description: str = ""
    inputs: List[ScriptNodePort] = field(default_factory=list)
    outputs: List[ScriptNodePort] = field(default_factory=list)
    collapsed: bool = True

    def __post_init__(self) -> None:
        self.node_id = str(self.node_id).strip()
        if not self.node_id:
            raise ValueError("ScriptNode.node_id must be non-empty")
        self.script_id = str(self.script_id or f"{self.module_path}:{self.function_name}").strip()
        self.module_path = str(self.module_path).replace("\\", "/").strip()
        self.function_name = str(self.function_name).strip()
        self.title = str(self.title or self.function_name or self.node_id).strip()
        self.description = str(self.description or "")
        self.inputs = [ScriptNodePort.from_value(port) for port in self.inputs]
        self.outputs = [
            ScriptNodePort.from_value(port, default_name="result" if index == 0 else f"out{index + 1}")
            for index, port in enumerate(self.outputs or [ScriptNodePort("result", "Any")])
        ]
        self.collapsed = bool(self.collapsed)
        if not self.module_path:
            raise ValueError("ScriptNode.module_path must be non-empty")
        if not self.function_name:
            raise ValueError("ScriptNode.function_name must be non-empty")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "script_id": self.script_id,
            "module_path": self.module_path,
            "function_name": self.function_name,
            "title": self.title,
            "description": self.description,
            "inputs": [port.to_dict() for port in self.inputs],
            "outputs": [port.to_dict() for port in self.outputs],
            "collapsed": self.collapsed,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScriptNode":
        if not isinstance(data, dict):
            raise ValueError("ScriptNode data must be an object")
        return cls(
            node_id=str(data.get("node_id", "")).strip(),
            script_id=str(data.get("script_id") or ""),
            module_path=str(data.get("module_path") or ""),
            function_name=str(data.get("function_name") or ""),
            title=str(data.get("title") or ""),
            description=str(data.get("description") or ""),
            inputs=[
                ScriptNodePort.from_value(item)
                for item in data.get("inputs", [])
            ],
            outputs=[
                ScriptNodePort.from_value(item, default_name="result" if index == 0 else f"out{index + 1}")
                for index, item in enumerate(data.get("outputs", []))
            ],
            collapsed=bool(data.get("collapsed", True)),
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
    prompt_nodes: Dict[str, PromptNode] = field(default_factory=dict)
    script_nodes: Dict[str, ScriptNode] = field(default_factory=dict)
    common_nodes: Dict[str, CommonNode] = field(default_factory=dict)
    edges: List[GraphEdge] = field(default_factory=list)
    agent_ring_max_circulations: Dict[str, int] = field(default_factory=dict)

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

        prompt_ids = set()
        for key, node in self.prompt_nodes.items():
            if key != node.node_id:
                raise ValueError(
                    f"prompt node key {key!r} does not match node_id {node.node_id!r}"
                )
            prompt_ids.add(node.node_id)

        script_ids = set()
        for key, node in self.script_nodes.items():
            if key != node.node_id:
                raise ValueError(
                    f"script node key {key!r} does not match node_id {node.node_id!r}"
                )
            script_ids.add(node.node_id)

        common_ids = set()
        for key, node in self.common_nodes.items():
            if key != node.node_id:
                raise ValueError(
                    f"common node key {key!r} does not match node_id {node.node_id!r}"
                )
            common_ids.add(node.node_id)
        return agent_ids | route_ids | terminal_ids | prompt_ids | script_ids | common_ids

    def _adjacency(self, node_ids: set[str], *, exec_only: bool = False) -> Dict[str, List[str]]:
        adjacency: Dict[str, List[str]] = {node_id: [] for node_id in node_ids}
        for edge in self.edges:
            if exec_only and not edge.is_exec_edge:
                continue
            if edge.source not in adjacency or edge.target not in node_ids:
                continue
            adjacency[edge.source].append(edge.target)
        return adjacency

    def _exec_successors_by_port(self, source_id: str, output_port: Optional[str] = None) -> List[str]:
        targets: List[str] = []
        requested = str(output_port).strip() if output_port is not None else None
        for edge in self.edges:
            if edge.source != source_id or not edge.is_exec_edge:
                continue
            actual = edge.output_port or "out"
            if requested is not None and actual != requested:
                continue
            targets.append(edge.target)
        return targets

    def framework_targets_for_agent(self, source_node_id: str) -> List[str]:
        """Return immediate framework dispatch targets for an AgentNode.

        ScriptNodes remain transparent transformation steps. CommonNodes are
        not transparent because the framework must execute their built-in
        control-flow semantics before choosing downstream targets.
        """

        source = str(source_node_id)
        if source not in self.agent_nodes:
            return []
        successors = self._adjacency(self._node_ids(), exec_only=True)
        targets: List[str] = []
        queue = list(successors.get(source, []))
        seen: set[str] = {source}
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            if current in self.agent_nodes or current in self.common_nodes:
                if current not in targets:
                    targets.append(current)
                continue
            if current not in self.script_nodes and current not in self.common_nodes:
                continue
            queue.extend(successors.get(current, []))
        return targets

    def framework_connections(self) -> Dict[str, List[str]]:
        """Return dispatchable node-to-node framework flow connections."""

        connections: Dict[str, List[str]] = {
            node_id: self.framework_targets_for_agent(node_id)
            for node_id in self.agent_nodes
        }
        for node_id in self.common_nodes:
            connections[node_id] = list(self._exec_successors_by_port(node_id))
        return connections

    def has_tick_source(self) -> bool:
        return any(node.kind == "tick" for node in self.common_nodes.values())

    def node_port_data_type(
        self,
        node_id: str,
        *,
        side: str,
        port_name: Optional[str] = None,
    ) -> Optional[BlueprintPortDataType]:
        """Return a port data type or ``None`` for unchecked Agent/Script ports."""

        node = str(node_id)
        if node in self.agent_nodes:
            port = str(port_name or ("out" if side == "output" else "in")).strip()
            if side == "input" and port == AGENT_PROMPT_INPUT_PORT:
                return "str"
            return None
        if node in self.script_nodes:
            return None
        port = str(port_name or ("out" if side == "output" else "in")).strip()
        if node in self.prompt_nodes:
            if side == "output" and port == DEFAULT_OUTPUT_PORT:
                return "str"
            raise ValueError(f"unknown PromptNode port: {node}.{port}")
        if node in self.common_nodes:
            common = self.common_nodes[node]
            if common.kind == "branch":
                if side == "input" and port == "condition":
                    return "bool"
                if side == "output" and port in {"true", "false"}:
                    return "message"
                raise ValueError(f"unknown Branch port: {node}.{port}")
            if common.kind == "tick":
                if side == "output" and port == "tick":
                    return "tick"
                raise ValueError(f"unknown Tick port: {node}.{port}")
        if node in self.route_nodes or node in self.terminal_nodes:
            return "message"
        raise KeyError(f"unknown graph node: {node}")

    def validate_port_types(self) -> None:
        for edge in self.edges:
            source_prompt = edge.source in self.prompt_nodes
            target_prompt_input = (
                edge.target in self.agent_nodes
                and (edge.input_port or "in") == AGENT_PROMPT_INPUT_PORT
            )
            if source_prompt or target_prompt_input:
                if not source_prompt or not target_prompt_input:
                    raise ValueError(
                        "PromptNode edges must connect PromptNode:out to AgentNode:prompt"
                    )
                if edge.edge_type != "data":
                    raise ValueError("PromptNode edges must use edge_type='data'")
            source_type = self.node_port_data_type(
                edge.source,
                side="output",
                port_name=edge.output_port,
            )
            target_type = self.node_port_data_type(
                edge.target,
                side="input",
                port_name=edge.input_port,
            )
            if source_type is None or target_type is None:
                continue
            if source_type != target_type:
                raise ValueError(
                    "edge port type mismatch: "
                    f"{edge.source}:{edge.output_port or 'out'} is {source_type}, "
                    f"{edge.target}:{edge.input_port or 'in'} is {target_type}"
                )

    def agent_connections(self) -> Dict[str, List[str]]:
        """Return downstream AgentNodes over exec edges, crossing ScriptNodes."""
        connections: Dict[str, List[str]] = {
            node_id: [] for node_id in self.agent_nodes
        }
        successors = self._adjacency(self._node_ids(), exec_only=True)
        for source_id in self.agent_nodes:
            for target_id in self._agent_targets_through_scripts(source_id, successors):
                if target_id not in connections[source_id]:
                    connections[source_id].append(target_id)
        return connections

    def agent_flow_connections(self) -> Dict[str, List[str]]:
        """Return AgentNode-to-AgentNode lines that can carry framework flow."""

        connections: Dict[str, List[str]] = {
            node_id: [] for node_id in self.agent_nodes
        }
        successors: Dict[str, List[str]] = {node_id: [] for node_id in self._node_ids()}
        for edge in self.edges:
            if edge.edge_type == "data":
                continue
            successors.setdefault(edge.source, []).append(edge.target)
        for source_id in self.agent_nodes:
            for target_id in self._agent_targets_through_scripts(source_id, successors):
                if target_id not in connections[source_id]:
                    connections[source_id].append(target_id)
        return connections

    def script_path_between_agents(self, source_node_id: str, target_node_id: str) -> List[str]:
        """Return ScriptNode ids on the first exec path between two agents."""

        source = str(source_node_id)
        target = str(target_node_id)
        if source not in self.agent_nodes or target not in self.agent_nodes:
            return []
        successors = self._adjacency(self._node_ids(), exec_only=True)
        queue: List[tuple[str, List[str]]] = [
            (node_id, [])
            for node_id in successors.get(source, [])
        ]
        seen: set[str] = {source}
        while queue:
            current, path = queue.pop(0)
            if current == target:
                return path
            if current in seen:
                continue
            seen.add(current)
            if current in self.script_nodes:
                for next_id in successors.get(current, []):
                    queue.append((next_id, [*path, current]))
        return []

    def _agent_targets_through_scripts(
        self,
        source_node_id: str,
        successors: Dict[str, List[str]],
    ) -> List[str]:
        targets: List[str] = []
        queue = list(successors.get(source_node_id, []))
        seen: set[str] = {source_node_id}
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            if current in self.agent_nodes:
                targets.append(current)
                continue
            if current not in self.script_nodes:
                continue
            queue.extend(successors.get(current, []))
        return targets

    def required_start_groups(self) -> List[Dict[str, Any]]:
        """Return source SCCs that must be covered by a start node."""

        connections = self.agent_flow_connections()
        index = 0
        stack: List[str] = []
        on_stack: set[str] = set()
        indices: Dict[str, int] = {}
        lowlinks: Dict[str, int] = {}
        components: List[List[str]] = []

        def strongconnect(node_id: str) -> None:
            nonlocal index
            indices[node_id] = index
            lowlinks[node_id] = index
            index += 1
            stack.append(node_id)
            on_stack.add(node_id)
            for target in connections.get(node_id, []):
                if target not in indices:
                    strongconnect(target)
                    lowlinks[node_id] = min(lowlinks[node_id], lowlinks[target])
                elif target in on_stack:
                    lowlinks[node_id] = min(lowlinks[node_id], indices[target])
            if lowlinks[node_id] != indices[node_id]:
                return
            component: List[str] = []
            while stack:
                item = stack.pop()
                on_stack.remove(item)
                component.append(item)
                if item == node_id:
                    break
            components.append(sorted(component))

        for node_id in sorted(self.agent_nodes):
            if node_id not in indices:
                strongconnect(node_id)

        component_by_node: Dict[str, int] = {}
        for component_index, component in enumerate(components):
            for node_id in component:
                component_by_node[node_id] = component_index

        incoming_component_counts = {component_index: 0 for component_index in range(len(components))}
        for source, targets in connections.items():
            source_component = component_by_node[source]
            for target in targets:
                target_component = component_by_node[target]
                if target_component != source_component:
                    incoming_component_counts[target_component] += 1

        groups: List[Dict[str, Any]] = []
        for component in sorted(
            (
                component
                for component_index, component in enumerate(components)
                if incoming_component_counts[component_index] == 0
            ),
            key=lambda item: (item[0] if item else "", len(item), tuple(item)),
        ):
            group_id = "start-group-" + "-".join(component)
            groups.append(
                {
                    "group_id": group_id,
                    "node_ids": list(component),
                    "required_count": 1,
                    "kind": "source_component" if len(component) > 1 else "source_agent",
                }
            )
        return groups

    def agent_rings(self) -> List[AgentRing]:
        """Return concrete simple AgentNode rings over direct exec edges.

        A ring must contain at least two AgentNodes. Each simple directed cycle
        is returned independently, so nested or edge-overlapping rings keep
        separate circulation counters at runtime.
        """

        node_ids = self._node_ids()
        for edge in self.edges:
            if edge.source not in node_ids:
                raise ValueError(f"unknown edge source: {edge.source}")
            if edge.target not in node_ids:
                raise ValueError(f"unknown edge target: {edge.target}")

        connections = self.agent_connections()
        cycles: List[List[str]] = []
        seen: set[tuple[str, ...]] = set()
        ordered_agent_ids = sorted(self.agent_nodes)

        def visit(start: str, current: str, path: List[str]) -> None:
            for target in connections.get(current, []):
                if target == start:
                    if len(path) >= 2:
                        key = tuple(path)
                        if key not in seen:
                            seen.add(key)
                            cycles.append(list(path))
                    continue
                if target in path:
                    continue
                if target < start:
                    continue
                visit(start, target, [*path, target])

        for start in ordered_agent_ids:
            visit(start, start, [start])

        cycles.sort(key=lambda cycle: (len(cycle), tuple(cycle)))
        rings: List[AgentRing] = []
        for index, cycle in enumerate(cycles, start=1):
            ring_id = f"ring{index}"
            topology_id = "ring-" + "-".join(cycle)
            max_circulations = int(
                self.agent_ring_max_circulations.get(
                    topology_id,
                    self.agent_ring_max_circulations.get(
                        ring_id,
                        self.agent_ring_max_circulations.get(str(index), 1),
                    ),
                )
            )
            rings.append(
                AgentRing(
                    ring_id=ring_id,
                    ordered_node_ids=cycle,
                    max_circulations=max_circulations,
                    topology_id=topology_id,
                )
            )
        return rings

    def agent_cycle_groups(self) -> List[List[str]]:
        """Return AgentNode groups that participate in exec-edge cycles.

        Each returned inner list is one concrete simple ring. The minimum
        valid ring contains two AgentNodes that point at each other; self-loops
        are ignored for ring circulation control.
        """
        return [ring.ordered_node_ids for ring in self.agent_rings()]

    def agent_organization_view(self) -> Dict[str, Any]:
        """Return a framework-readable organization view for agents and UI."""
        connections = self.agent_connections()
        upstreams: Dict[str, List[str]] = {node_id: [] for node_id in self.agent_nodes}
        for source, targets in connections.items():
            for target in targets:
                upstreams.setdefault(target, []).append(source)

        agents: Dict[str, Dict[str, Any]] = {}
        for node_id, node in self.agent_nodes.items():
            agents[node_id] = {
                "node_id": node_id,
                "node_type": node.node_type,
                "agent_id": node.runtime_agent_id,
                "cli_kind": node.cli_kind,
                "execution_mode": node.execution_mode,
                "skill_selection": node.skill_selection.to_dict(),
                "skills": list(node.skills),
                "rule_paths": list(node.rule_paths),
                "read_scope": list(node.read_scope),
                "write_scope": list(node.write_scope),
                "artifact_scope": list(node.artifact_scope),
                "access_policy": dict(node.access_policy),
                "upstream_agents": list(upstreams.get(node_id, [])),
                "downstream_agents": list(connections.get(node_id, [])),
            }

        return {
            "graph": {
                "nodes": sorted(self._node_ids()),
                "agent_nodes": list(self.agent_nodes),
                "route_nodes": list(self.route_nodes),
                "common_nodes": {
                    node_id: node.to_dict()
                    for node_id, node in self.common_nodes.items()
                },
                "prompt_nodes": {
                    node_id: node.to_dict()
                    for node_id, node in self.prompt_nodes.items()
                },
                "script_nodes": {
                    node_id: node.to_dict()
                    for node_id, node in self.script_nodes.items()
                },
                "terminal_nodes": {
                    node_id: node.terminal_kind
                    for node_id, node in self.terminal_nodes.items()
                },
                "edges": [
                    {
                        "from": edge.source,
                        "to": edge.target,
                        "edge_type": edge.edge_type or "exec",
                        "output_port": edge.output_port,
                        "input_port": edge.input_port,
                    }
                    for edge in self.edges
                ],
            },
            "agent_connections": connections,
            "framework_connections": self.framework_connections(),
            "cycle_groups": self.agent_cycle_groups(),
            "agent_rings": [ring.to_dict() for ring in self.agent_rings()],
            "agents": agents,
            "start_policy": {
                "selected_by": "top_agent",
                "framework_role": "validate_only",
                "valid_start_nodes": list(self.agent_nodes),
                "required_start_groups": self.required_start_groups(),
            },
        }

    def agent_organization_summary(self, *, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Return a compact organization view for prompt injection."""
        full = self.agent_organization_view()
        if agent_id is None:
            return {
                "scope": "top_agent",
                "graph": full["graph"],
                "agent_connections": full["agent_connections"],
                "framework_connections": full["framework_connections"],
                "agents": {
                    node_id: {
                        "node_id": agent["node_id"],
                        "node_type": agent["node_type"],
                        "agent_id": agent["agent_id"],
                        "upstream_agents": list(agent["upstream_agents"]),
                        "downstream_agents": list(agent["downstream_agents"]),
                        "read_scope": list(agent["read_scope"]),
                        "write_scope": list(agent["write_scope"]),
                        "artifact_scope": list(agent["artifact_scope"]),
                        "access_policy": dict(agent["access_policy"]),
                        "skill_selection_mode": agent["skill_selection"].get("mode"),
                    }
                    for node_id, agent in full["agents"].items()
                },
                "start_policy": full["start_policy"],
                "cycle_groups": full["cycle_groups"],
                "agent_rings": full["agent_rings"],
            }

        if agent_id not in full["agents"]:
            raise KeyError(f"unknown AgentNode: {agent_id}")
        agent = full["agents"][agent_id]
        related = (
            set(agent.get("upstream_agents", []))
            | set(agent.get("downstream_agents", []))
            | set(full["framework_connections"].get(agent_id, []))
            | {agent_id}
        )
        return {
            "scope": "agent",
            "graph": {
                "nodes": sorted(related),
                "agent_nodes": [agent_id],
                "common_nodes": {
                    node_id: node
                    for node_id, node in full["graph"].get("common_nodes", {}).items()
                    if node_id in related
                },
                "edges": [
                    edge
                    for edge in full["graph"]["edges"]
                    if edge["from"] in related and edge["to"] in related
                ],
            },
            "agent": {
                "node_id": agent["node_id"],
                "node_type": agent["node_type"],
                "agent_id": agent["agent_id"],
                "upstream_agents": list(agent["upstream_agents"]),
                "downstream_agents": list(agent["downstream_agents"]),
                "read_scope": list(agent["read_scope"]),
                "write_scope": list(agent["write_scope"]),
                "artifact_scope": list(agent["artifact_scope"]),
                "access_policy": dict(agent["access_policy"]),
                "skill_selection_mode": agent["skill_selection"].get("mode"),
            },
            "agent_connections": {
                agent_id: list(full["agent_connections"].get(agent_id, [])),
            },
            "framework_connections": {
                agent_id: list(full["framework_connections"].get(agent_id, [])),
            },
            "cycle_groups": [
                group for group in full["cycle_groups"] if agent_id in group
            ],
            "agent_rings": [
                ring
                for ring in full["agent_rings"]
                if agent_id in ring["ordered_node_ids"]
            ],
        }

    def validate_dag(self) -> None:
        node_ids = self._node_ids()
        for edge in self.edges:
            if edge.source not in node_ids:
                raise ValueError(f"unknown edge source: {edge.source}")
            if edge.target not in node_ids:
                raise ValueError(f"unknown edge target: {edge.target}")
        self.validate_port_types()

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

    @staticmethod
    def _reply_text(reply: Any) -> str:
        if isinstance(reply, dict):
            body = reply.get("body")
            if isinstance(body, dict):
                codex = body.get("codex")
                if isinstance(codex, dict):
                    text = codex.get("final_text") or codex.get("last_message")
                    if isinstance(text, str) and text.strip():
                        return text.strip()
                for key in ("answer", "result", "text", "echo_prompt"):
                    text = body.get(key)
                    if isinstance(text, str) and text.strip():
                        return text.strip()
            for key in ("answer", "result", "text"):
                text = reply.get(key)
                if isinstance(text, str) and text.strip():
                    return text.strip()
            return json.dumps(reply, ensure_ascii=False)
        return str(reply)

    @staticmethod
    def _start_end_ids(graph: GraphDefinition) -> tuple[str, str]:
        starts = [
            node.node_id
            for node in graph.terminal_nodes.values()
            if node.terminal_kind == "start"
        ]
        ends = [
            node.node_id
            for node in graph.terminal_nodes.values()
            if node.terminal_kind == "end"
        ]
        if len(starts) != 1 or len(ends) != 1:
            graph.validate_runnable()
        return starts[0], ends[0]

    @staticmethod
    def _exec_successors(graph: GraphDefinition) -> Dict[str, List[str]]:
        successors: Dict[str, List[str]] = {node_id: [] for node_id in graph._node_ids()}
        for edge in graph.edges:
            if edge.is_exec_edge:
                successors.setdefault(edge.source, []).append(edge.target)
        return successors

    @staticmethod
    def _exec_predecessors(graph: GraphDefinition) -> Dict[str, List[str]]:
        predecessors: Dict[str, List[str]] = {node_id: [] for node_id in graph._node_ids()}
        for edge in graph.edges:
            if edge.is_exec_edge:
                predecessors.setdefault(edge.target, []).append(edge.source)
        return predecessors

    @staticmethod
    def _data_inputs(graph: GraphDefinition) -> Dict[str, List[GraphEdge]]:
        inputs: Dict[str, List[GraphEdge]] = {}
        for edge in graph.edges:
            if edge.edge_type == "data":
                inputs.setdefault(edge.target, []).append(edge)
        return inputs

    def _emit_executor_event(
        self,
        event: GraphEvent,
        event_callback: Optional[Callable[[GraphEvent], None]],
    ) -> None:
        self.runtime._emit(event)
        if event_callback is not None:
            event_callback(event)

    def _first_queued_message_id(self, node_id: str) -> Optional[str]:
        queue = self.runtime.agent_message_queues.get(node_id, [])
        if not queue:
            return None
        return queue[0].message_id

    def _staging_batch_for_source(self, source_node_id: str) -> Optional[OutgoingMessageBatch]:
        for batch in self.runtime.outgoing_batches.values():
            if batch.source_node_id == source_node_id and batch.status == "staging":
                return batch
        return None

    async def _execute_agent_node(
        self,
        node: AgentNode,
        *,
        prompt: Optional[str] = None,
        event_callback: Optional[Callable[[GraphEvent], None]] = None,
    ) -> Dict[str, Any]:
        self._emit_executor_event(
            GraphEvent(
                "NodeQueued",
                node_id=node.node_id,
                agent_id=node.runtime_agent_id,
                status="queued",
            ),
            event_callback,
        )
        self._emit_executor_event(
            GraphEvent(
                "NodeRunning",
                node_id=node.node_id,
                agent_id=node.runtime_agent_id,
                status="running",
            ),
            event_callback,
        )
        queued_message_id = self._first_queued_message_id(node.node_id)
        if queued_message_id is not None:
            pending = await self.runtime.dispatch_queued_message_now(queued_message_id)
            reply = dict(pending.receipt or {})
        else:
            reply = await self.runtime.send_agent_message(
                node,
                {"prompt": prompt or node.prompt or f"Run AgentNode {node.node_id}."},
            )
        self._emit_executor_event(
            GraphEvent(
                "NodeCompleted",
                node_id=node.node_id,
                agent_id=node.runtime_agent_id,
                status="completed",
                payload={"result": reply, "text": self._reply_text(reply)},
            ),
            event_callback,
        )
        return reply

    async def _stage_and_queue_targets(
        self,
        graph: GraphDefinition,
        source_node_id: str,
        target_node_ids: Sequence[str],
    ) -> Dict[str, Any]:
        targets = [graph.agent_nodes[node_id] for node_id in target_node_ids]
        batch = self._staging_batch_for_source(source_node_id)
        if batch is None:
            batch = await self.runtime.create_outgoing_batch(
                graph.agent_nodes[source_node_id],
                targets,
            )
        result: Dict[str, Any] = {
            "batch_id": batch.batch_id,
            "ready_to_dispatch": batch.ready_to_dispatch,
            "remaining_targets": batch.remaining_targets,
        }
        for target in targets:
            if target.node_id in batch.staged_messages:
                continue
            result = self.runtime.stage_outgoing_message(
                batch.batch_id,
                target,
                {
                    "prompt": (
                        f"Continue complex blueprint work from {source_node_id} "
                        f"to {target.node_id}."
                    )
                },
            )
        return result

    def _scenario_decisions(self, runtime_scenarios: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        scenarios = runtime_scenarios or {}
        decisions = dict(scenarios.get("decisions", {}))
        decisions.setdefault("risk", "high")
        decisions.setdefault("review", "failed_once")
        decisions.setdefault("integration", "failed_once")
        decisions.setdefault("max_integration_retries", 1)
        return decisions

    def _join_spec_by_id(
        self,
        runtime_scenarios: Optional[Dict[str, Any]],
        join_id: str,
    ) -> Optional[Dict[str, Any]]:
        for spec in (runtime_scenarios or {}).get("joins", []):
            if str(spec.get("join_id")) == join_id:
                return dict(spec)
        return None

    def _contribution_for_source(self, source_node_id: str) -> Dict[str, Any]:
        if source_node_id.endswith("_impl"):
            prefix = source_node_id.replace("_impl", "")
            return {
                "accepted_changesets": [{"changeset_id": f"{source_node_id}-changeset"}],
                "artifacts": [{"path": f"{prefix}/build.log"}],
                "reports": [{"path": f"{prefix}/report.md"}],
            }
        if source_node_id.endswith("_tests"):
            suite = source_node_id.replace("_tests", "")
            return {
                "test_results": [{"suite": suite, "status": "passed"}],
                "artifacts": [{"path": f"tests/{suite}.log"}],
            }
        return {"reports": [{"path": f"{source_node_id}/report.md"}]}

    def _submit_fixture_join(
        self,
        graph: GraphDefinition,
        runtime_scenarios: Optional[Dict[str, Any]],
        join_id: str,
    ) -> Dict[str, Any]:
        spec = self._join_spec_by_id(runtime_scenarios, join_id)
        if spec is None:
            raise KeyError(f"complex blueprint fixture is missing join spec: {join_id}")
        target_id = str(spec["target"])
        barrier = self.runtime.create_join_barrier(
            required_sources=[str(item) for item in spec.get("required_sources", [])],
            target_node=graph.agent_nodes[target_id],
            policy=str(spec.get("policy", "wait-all")),
            quorum=(int(spec["quorum"]) if spec.get("quorum") is not None else None),
            join_id=join_id,
        )
        result: Dict[str, Any] = {}
        for source_id in barrier.required_source_node_ids:
            source_node = graph.agent_nodes[source_id]
            result = self.runtime.submit_join_contribution(
                join_id,
                source_id,
                source_agent_id=source_node.runtime_agent_id,
                result={"node_id": source_id, "status": "completed"},
                **self._contribution_for_source(source_id),
            )
        return result

    async def run_complex_blueprint_scenario(
        self,
        graph: GraphDefinition,
        *,
        runtime_scenarios: Optional[Dict[str, Any]] = None,
        initial_prompt: str = "",
        event_callback: Optional[Callable[[GraphEvent], None]] = None,
    ) -> Dict[str, Any]:
        """Execute the fixed complex blueprint fixture through runtime APIs.

        This is the product-shaped smoke path for the current complex fixture:
        top-agent start queues are consumed, fan-out uses outgoing batches,
        fan-in uses join barriers, condition/retry routes are driven by the
        fixture scenario, side-channel nodes run without blocking the main
        path, and all message IO flows through the runtime journal.
        """

        graph.validate_runnable()
        self.runtime.configure_completion_tracking(graph)
        await self.runtime.prestart_agents(list(graph.agent_nodes.values()))
        decisions = self._scenario_decisions(runtime_scenarios)
        executed: List[str] = []
        route_history: List[Dict[str, Any]] = []

        async def run_node(node_id: str, *, prompt: Optional[str] = None) -> Dict[str, Any]:
            reply = await self._execute_agent_node(
                graph.agent_nodes[node_id],
                prompt=prompt or initial_prompt,
                event_callback=event_callback,
            )
            executed.append(node_id)
            return reply

        def emit_route(
            event_type: str,
            source: str,
            target: str,
            *,
            condition: str,
            attempt: Optional[int] = None,
        ) -> None:
            payload: Dict[str, Any] = {
                "from": source,
                "to": target,
                "condition": condition,
            }
            if attempt is not None:
                payload["attempt"] = attempt
            route_history.append(dict(payload, event_type=event_type))
            self._emit_executor_event(
                GraphEvent(event_type, node_id=target, status="taken", payload=payload),
                event_callback,
            )

        self._emit_executor_event(GraphEvent("BlueprintStarted", status="running"), event_callback)
        try:
            await run_node("requirements", prompt=initial_prompt)
            await self._stage_and_queue_targets(
                graph,
                "requirements",
                ["risk_scan", "architecture", "test_planner"],
            )

            await run_node("risk_scan")
            if str(decisions.get("risk")).lower() == "high":
                emit_route("ConditionalRouteTaken", "risk_scan", "security_review", condition="risk == high")
                await self._stage_and_queue_targets(graph, "risk_scan", ["security_review"])
                await run_node("security_review")
            else:
                emit_route("ConditionalRouteTaken", "risk_scan", "review", condition="risk in ['low', 'medium']")

            await run_node("architecture")
            await self._stage_and_queue_targets(
                graph,
                "architecture",
                ["backend_impl", "frontend_impl"],
            )
            await run_node("test_planner")
            await self._stage_and_queue_targets(
                graph,
                "test_planner",
                ["unit_tests", "e2e_tests"],
            )

            await run_node("backend_impl")
            await run_node("frontend_impl")
            self._submit_fixture_join(graph, runtime_scenarios, "join-implementation-ready")
            await run_node("review")

            if str(decisions.get("review")).lower() in {"failed", "failed_once"}:
                emit_route("ConditionalRouteTaken", "review", "patch", condition="review == failed")
                await self._stage_and_queue_targets(graph, "review", ["patch"])
                await run_node("patch")

            await run_node("unit_tests")
            await run_node("e2e_tests")
            self._submit_fixture_join(graph, runtime_scenarios, "join-test-ready")

            integration_attempts = 0
            await run_node("integration")
            integration_attempts += 1
            if (
                str(decisions.get("integration")).lower() in {"failed", "failed_once"}
                and integration_attempts <= int(decisions.get("max_integration_retries", 1))
            ):
                emit_route(
                    "RetryRouteTaken",
                    "integration",
                    "failure_analysis",
                    condition="integration == failed",
                    attempt=integration_attempts,
                )
                await self._stage_and_queue_targets(graph, "integration", ["failure_analysis"])
                await run_node("failure_analysis")
                emit_route(
                    "RetryRouteTaken",
                    "failure_analysis",
                    "patch",
                    condition="retry_allowed",
                    attempt=integration_attempts,
                )
                await self._stage_and_queue_targets(graph, "failure_analysis", ["patch"])
                await run_node("patch")
                await self._stage_and_queue_targets(graph, "patch", ["integration"])
                await run_node("integration")
                integration_attempts += 1

            await self._stage_and_queue_targets(graph, "integration", ["summary"])
            await run_node("summary")

            for side_node_id in (runtime_scenarios or {}).get("side_channels", []):
                side_id = str(side_node_id)
                if side_id in graph.agent_nodes and side_id not in executed:
                    await run_node(side_id)

        except asyncio.CancelledError:
            self._emit_executor_event(GraphEvent("BlueprintCancelled", status="cancelled"), event_callback)
            raise
        except Exception as exc:
            self._emit_executor_event(
                GraphEvent("BlueprintFailed", status="failed", payload={"error": str(exc)}),
                event_callback,
            )
            raise

        result = {
            "ok": True,
            "status": "completed",
            "executed_nodes": list(executed),
            "route_history": route_history,
            "integration_attempts": integration_attempts,
        }
        self._emit_executor_event(GraphEvent("BlueprintCompleted", status="completed", payload=result), event_callback)
        return result

    async def run_blueprint(
        self,
        graph: GraphDefinition,
        *,
        initial_prompt: str = "",
        event_callback: Optional[Callable[[GraphEvent], None]] = None,
    ) -> Dict[str, Any]:
        """Run a runnable blueprint along exec edges.

        The runner is intentionally deterministic and sequential for now. A
        node becomes ready when all exec predecessors have completed. If an
        AgentNode has multiple upstream AgentNode predecessors, the executor
        creates a runtime join barrier, submits upstream contributions, and
        dispatches the generated ``join_aggregate`` envelope to the node.
        """

        graph.validate_runnable()
        self.runtime.configure_completion_tracking(graph)
        await self.runtime.prestart_agents(list(graph.agent_nodes.values()))

        def emit(event: GraphEvent) -> None:
            self.runtime._emit(event)
            if event_callback is not None:
                event_callback(event)

        start_id, end_id = self._start_end_ids(graph)
        successors = self._exec_successors(graph)
        predecessors = self._exec_predecessors(graph)
        data_inputs = self._data_inputs(graph)
        values: Dict[tuple[str, str], Any] = {}
        executed: List[str] = []
        completed: set[str] = {start_id}
        queued: List[str] = list(successors.get(start_id, []))
        seen_ready: set[str] = set(queued)
        last_reply: Any = None
        emit(GraphEvent("BlueprintStarted", status="running"))

        try:
            while queued:
                current = queued.pop(0)
                if current in completed:
                    continue
                if any(pred not in completed for pred in predecessors.get(current, [])):
                    continue
                if current == end_id:
                    completed.add(current)
                    break
                node = graph.agent_nodes.get(current)
                if node is None:
                    raise ValueError(
                        f"blueprint runner only supports AgentNode on exec path: {current!r}"
                    )
                if node.execution_mode != "blocking":
                    raise ValueError("blueprint runner only supports blocking AgentNode")

                prompt = node.prompt.strip() or initial_prompt.strip()
                context: Optional[str] = None
                for edge in data_inputs.get(node.node_id, []):
                    port = edge.input_port or ""
                    value = values.get((edge.source, edge.output_port or "result"))
                    if value is None:
                        continue
                    text = self._reply_text(value)
                    if port == "prompt":
                        prompt = text
                    else:
                        context = text if context is None else f"{context}\n\n{text}"
                if not prompt:
                    prompt = f"Run AgentNode {node.node_id}."

                emit(
                    GraphEvent(
                        "NodeQueued",
                        node_id=node.node_id,
                        agent_id=node.runtime_agent_id,
                        status="queued",
                    )
                )
                emit(
                    GraphEvent(
                        "NodeRunning",
                        node_id=node.node_id,
                        agent_id=node.runtime_agent_id,
                        status="running",
                    )
                )
                body: Dict[str, Any] = {"prompt": prompt}
                if context:
                    body["context"] = context

                upstream_agents = [
                    pred for pred in predecessors.get(node.node_id, [])
                    if pred in graph.agent_nodes
                ]
                if len(upstream_agents) > 1:
                    barrier = self.runtime.create_join_barrier(
                        required_sources=upstream_agents,
                        target_node=node,
                        join_id=f"join-{node.node_id}-{len(executed) + 1}",
                    )
                    for pred in upstream_agents:
                        pred_node = graph.agent_nodes[pred]
                        self.runtime.submit_join_contribution(
                            barrier.join_id,
                            pred,
                            source_agent_id=pred_node.runtime_agent_id,
                            result=values.get((pred, "result")),
                        )
                    assert barrier.aggregate_message_id is not None
                    pending = await self.runtime.dispatch_queued_message_now(
                        barrier.aggregate_message_id
                    )
                    reply = pending.receipt
                else:
                    reply = await self.runtime.send_agent_message(node, body)
                last_reply = reply
                executed.append(node.node_id)
                values[(node.node_id, "result")] = reply
                values[(node.node_id, "out")] = reply
                completed.add(node.node_id)
                emit(
                    GraphEvent(
                        "NodeCompleted",
                        node_id=node.node_id,
                        agent_id=node.runtime_agent_id,
                        status="completed",
                        payload={"result": reply, "text": self._reply_text(reply)},
                    )
                )
                for target in successors.get(node.node_id, []):
                    if target not in seen_ready and all(
                        pred in completed for pred in predecessors.get(target, [])
                    ):
                        queued.append(target)
                        seen_ready.add(target)
            if end_id not in completed:
                raise ValueError("blueprint runner did not reach end node")
        except asyncio.CancelledError:
            emit(GraphEvent("BlueprintCancelled", status="cancelled"))
            raise
        except Exception as exc:
            emit(
                GraphEvent(
                    "BlueprintFailed",
                    node_id=current if current != start_id else None,
                    status="failed",
                    payload={"error": str(exc)},
                )
            )
            raise

        result = {
            "ok": True,
            "status": "completed",
            "executed_nodes": executed,
            "result": last_reply,
            "text": self._reply_text(last_reply),
        }
        emit(GraphEvent("BlueprintCompleted", status="completed", payload=result))
        return result

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
