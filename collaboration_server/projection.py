from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from .schemas import (
    AgentPanelSnapshot,
    ArtifactIndexItem,
    BlueprintStructureEdge,
    BlueprintStructureNode,
    BlueprintStructureProjection,
    ProjectAdminSummary,
    ProjectSummary,
    ReportIndexItem,
    RunDiffChangeset,
    RunDiffSummary,
    RunStatusProjection,
    RunSummary,
    RuntimeBindingSummary,
    RuntimeEvent,
    UserSummary,
)
from .store import iso_time, normalize_status, row_bool


SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "bearer",
    "rpc",
    "codex_home",
    "private_checkout",
    "service_token",
)
SENSITIVE_PATH_KEYS = (
    "projectdir",
    "project_dir",
    "workspace_root",
    "workspacepath",
    "absolute_path",
    "checkout_dir",
    "codex_home",
    "cwd",
)


def scrub_payload(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                result[str(key)] = "[redacted]"
            elif any(part in lowered for part in SENSITIVE_PATH_KEYS):
                result[str(key)] = "[redacted]"
            else:
                result[str(key)] = scrub_payload(item)
        return result
    if isinstance(value, list):
        return [scrub_payload(item) for item in value]
    return value


def event_key(raw: dict[str, Any]) -> str:
    data = json.dumps(scrub_payload(raw), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def user_summary(row: dict[str, Any]) -> UserSummary:
    return UserSummary(
        id=str(row["id"]),
        username=str(row["username"]),
        role=str(row["role"]),
        active=row_bool(row, "active"),
        createdAt=iso_time(row.get("created_at")),
        updatedAt=iso_time(row.get("updated_at")),
    )


def project_admin_summary(row: dict[str, Any]) -> ProjectAdminSummary:
    return ProjectAdminSummary(
        id=str(row["id"]),
        name=str(row["name"]),
        archived=row_bool(row, "archived"),
        createdAt=iso_time(row.get("created_at")),
        updatedAt=iso_time(row.get("updated_at")),
    )


def binding_summary(row: dict[str, Any]) -> RuntimeBindingSummary:
    return RuntimeBindingSummary(
        id=str(row["id"]),
        projectId=str(row["project_id"]),
        blueprintId=str(row["blueprint_id"]),
        bridgeUrl=str(row["bridge_url"]),
        active=row_bool(row, "active"),
        createdAt=iso_time(row.get("created_at")),
        updatedAt=iso_time(row.get("updated_at")),
    )


def run_summary(row: dict[str, Any], *, current_node_ids: Optional[list[str]] = None) -> RunSummary:
    return RunSummary(
        id=str(row["id"]),
        projectId=str(row["project_id"]),
        blueprintId=str(row["blueprint_id"]),
        title=str(row.get("title") or row.get("runtime_run_id") or row["id"]),
        status=normalize_status(row.get("status")),
        createdAt=iso_time(row.get("created_at")),
        updatedAt=iso_time(row.get("updated_at")),
        endedAt=iso_time(row.get("ended_at")) if row.get("ended_at") is not None else None,
        currentNodeIds=current_node_ids or [],
    )


def project_summary(row: dict[str, Any], role: str, capabilities: list[str], latest_run: Optional[RunSummary]) -> ProjectSummary:
    return ProjectSummary(
        id=str(row["id"]),
        name=str(row["name"]),
        role=role,  # type: ignore[arg-type]
        latestRun=latest_run,
        capabilities=capabilities,
    )


def runtime_event_from_row(row: dict[str, Any]) -> RuntimeEvent:
    payload = json.loads(str(row.get("payload_json") or "{}"))
    return RuntimeEvent(
        cursor=str(row["id"]),
        runId=str(row["run_id"]),
        type=normalize_event_type(row.get("type")),
        occurredAt=iso_time(row.get("occurred_at")),
        nodeId=str(row["node_id"]) if row.get("node_id") else None,
        agentId=str(row["agent_id"]) if row.get("agent_id") else None,
        payload=scrub_payload(payload),
    )


def normalize_event_type(value: Any) -> str:
    raw = str(value or "").lower()
    if raw in {
        "runtime.status",
        "agent.status",
        "agent.utterance",
        "agent.tool",
        "workspace.report",
        "workspace.artifact",
        "workspace.changeset",
        "workspace.conflict",
        "run.completed",
        "run.failed",
    }:
        return raw
    if "utterance" in raw or "message" in raw or "reply" in raw:
        return "agent.utterance"
    if "tool" in raw:
        return "agent.tool"
    if "report" in raw:
        return "workspace.report"
    if "artifact" in raw:
        return "workspace.artifact"
    if "changeset" in raw or "change" in raw:
        return "workspace.changeset"
    if "conflict" in raw:
        return "workspace.conflict"
    if "failed" in raw or "error" in raw:
        return "run.failed"
    if "completed" in raw or "complete" in raw:
        return "run.completed"
    if "agent" in raw:
        return "agent.status"
    return "runtime.status"


def runtime_event_from_raw(run_id: str, raw: dict[str, Any], *, cursor: str = "0") -> RuntimeEvent:
    node_id = raw.get("node_id") or raw.get("nodeId")
    agent_id = raw.get("agent_id") or raw.get("agentId")
    occurred = raw.get("timestamp") or raw.get("time") or raw.get("occurredAt") or raw.get("created_at")
    return RuntimeEvent(
        cursor=str(cursor),
        runId=run_id,
        type=normalize_event_type(raw.get("type") or raw.get("event") or raw.get("kind")),
        occurredAt=iso_time(occurred),
        nodeId=str(node_id) if node_id else None,
        agentId=str(agent_id) if agent_id else None,
        payload=scrub_payload(raw),
    )


def status_projection(run: RunSummary, status_payload: dict[str, Any], events: list[RuntimeEvent], diff: Optional[RunDiffSummary]) -> RunStatusProjection:
    status = _inner_status(status_payload)
    agents = _agent_snapshots(status, events)
    blueprint = _blueprint_projection(status)
    outputs = _outputs_projection(status, diff)
    return RunStatusProjection(
        run=run.model_copy(update={"currentNodeIds": [agent.nodeId for agent in agents if agent.state == "running"]}),
        blueprint=blueprint,
        agents=agents,
        pending={
            "queuedMessages": _queued_count(status),
            "waitingOutgoingBatches": _status_count(status.get("outgoing_batches"), {"staging", "waiting"}),
            "waitingJoins": _status_count(status.get("joins"), {"waiting"}),
            "runningJobs": _status_count(status.get("jobs"), {"queued", "running"}),
        },
        outputs=outputs,
        lastCursor=events[-1].cursor if events else "0",
    )


def diff_summary(payload: dict[str, Any]) -> RunDiffSummary:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    changesets = []
    for item in list(payload.get("changesets") or []):
        if not isinstance(item, dict):
            continue
        changesets.append(
            RunDiffChangeset(
                id=str(item.get("id") or item.get("changesetId") or item.get("changeset_id") or ""),
                status=str(item.get("status") or "unknown"),
                summary=str(item.get("summary") or item.get("message") or ""),
                files=[str(path) for path in list(item.get("files") or [])],
            )
        )
    return RunDiffSummary(
        total=int(summary.get("total") or len(changesets)),
        accepted=int(summary.get("accepted") or 0),
        conflict=int(summary.get("conflict") or 0),
        rejected=int(summary.get("rejected") or 0),
        pending=int(summary.get("pending") or 0),
        files=int(summary.get("files") or 0),
        additions=int(summary.get("additions") or 0),
        deletions=int(summary.get("deletions") or 0),
        changesets=changesets,
    )


def report_items(status_payload: dict[str, Any]) -> list[ReportIndexItem]:
    status = _inner_status(status_payload)
    return [_report_item(item, index) for index, item in enumerate(list((status.get("workspace") or {}).get("reports") or []))]


def artifact_items(status_payload: dict[str, Any]) -> list[ArtifactIndexItem]:
    status = _inner_status(status_payload)
    return [_artifact_item(item, index) for index, item in enumerate(list((status.get("workspace") or {}).get("artifacts") or []))]


def _inner_status(status_payload: dict[str, Any]) -> dict[str, Any]:
    status = status_payload.get("status") if isinstance(status_payload.get("status"), dict) else status_payload
    return status if isinstance(status, dict) else {}


def _agent_snapshots(status: dict[str, Any], events: list[RuntimeEvent]) -> list[AgentPanelSnapshot]:
    agents = status.get("agents") if isinstance(status.get("agents"), dict) else {}
    result = []
    for node_id, info in agents.items():
        if not isinstance(info, dict):
            continue
        recent = [event for event in events if event.nodeId == node_id or event.agentId == info.get("agent_id")][-20:]
        result.append(
            AgentPanelSnapshot(
                nodeId=str(node_id),
                agentId=str(info.get("agent_id") or node_id),
                cliKind=str(info.get("cli_kind")) if info.get("cli_kind") else None,
                state=str(info.get("state") or "unknown"),
                taskStatus=str(info.get("task_status")) if info.get("task_status") is not None else None,
                queueSize=int(info.get("queue_size") or 0),
                messagesSent=int(info.get("messages_sent") or 0),
                busyCount=int(info.get("busy_count") or 0),
                updatedAt=iso_time(info.get("updated_at")) if info.get("updated_at") is not None else None,
                recentEvents=recent,
            )
        )
    return result


def _blueprint_projection(status: dict[str, Any]) -> BlueprintStructureProjection:
    organization = status.get("organization") if isinstance(status.get("organization"), dict) else {}
    graph = organization.get("graph") if isinstance(organization.get("graph"), dict) else {}
    agents = organization.get("agents") if isinstance(organization.get("agents"), dict) else {}
    runtime_agents = status.get("agents") if isinstance(status.get("agents"), dict) else {}
    nodes = []
    for node_id, info in agents.items():
        if not isinstance(info, dict):
            continue
        runtime = runtime_agents.get(node_id) if isinstance(runtime_agents.get(node_id), dict) else {}
        nodes.append(
            BlueprintStructureNode(
                id=str(node_id),
                label=str(info.get("agent_id") or node_id),
                kind=_node_kind(info.get("node_type") or info.get("kind")),
                role=str(info.get("cli_kind")) if info.get("cli_kind") else None,
                state=_node_state(runtime.get("state")),
                upstreamNodeIds=[str(item) for item in list(info.get("upstream_agents") or [])],
                downstreamNodeIds=[str(item) for item in list(info.get("downstream_agents") or [])],
            )
        )
    edges = []
    for edge in list(graph.get("edges") or []):
        if not isinstance(edge, dict):
            continue
        edges.append(
            BlueprintStructureEdge(
                source=str(edge.get("from") or edge.get("source") or ""),
                target=str(edge.get("to") or edge.get("target") or ""),
                kind=_edge_kind(edge.get("edge_type") or edge.get("kind")),
                outputPort=_optional_string(edge.get("output_port") or edge.get("outputPort")),
                inputPort=_optional_string(edge.get("input_port") or edge.get("inputPort")),
            )
        )
    return BlueprintStructureProjection(nodes=nodes, edges=edges)


def _outputs_projection(status: dict[str, Any], diff: Optional[RunDiffSummary]) -> dict[str, Any]:
    return {
        "reports": [item.model_dump() for item in report_items(status)],
        "artifacts": [item.model_dump() for item in artifact_items(status)],
        "diff": diff.model_dump() if diff else None,
    }


def _queued_count(status: dict[str, Any]) -> int:
    queues = status.get("queues") if isinstance(status.get("queues"), dict) else {}
    by_agent = queues.get("by_agent") if isinstance(queues.get("by_agent"), dict) else {}
    return sum(len(items) for items in by_agent.values() if isinstance(items, list))


def _status_count(value: Any, statuses: set[str]) -> int:
    items = value.values() if isinstance(value, dict) else []
    return sum(1 for item in items if isinstance(item, dict) and str(item.get("status", "")).lower() in statuses)


def _node_state(value: Any) -> str:
    state = str(value or "unknown").lower()
    if state in {"idle", "queued", "running", "completed", "failed"}:
        return state
    return "unknown"


def _node_kind(value: Any) -> str:
    kind = str(value or "worker_agent").lower()
    if kind in {"agent", "worker_agent", "script", "branch", "tick"}:
        return kind
    return "worker_agent"


def _edge_kind(value: Any) -> str:
    kind = str(value or "unknown").lower()
    if kind in {"exec", "data"}:
        return kind
    return "unknown"


def _optional_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _report_item(item: Any, index: int) -> ReportIndexItem:
    data = item if isinstance(item, dict) else {"path": str(item)}
    path = str(data.get("path") or data.get("name") or f"report-{index}")
    return ReportIndexItem(
        id=str(data.get("id") or data.get("report_id") or f"report-{index}"),
        title=str(data.get("title") or path.rsplit("/", 1)[-1]),
        path=path,
        mediaType=str(data.get("mediaType") or data.get("media_type") or "application/octet-stream"),
        createdAt=iso_time(data.get("created_at") or data.get("createdAt")) if data.get("created_at") or data.get("createdAt") else None,
        ownerNodeId=str(data.get("ownerNodeId") or data.get("owner_node_id") or data.get("node_id") or "") or None,
    )


def _artifact_item(item: Any, index: int) -> ArtifactIndexItem:
    data = item if isinstance(item, dict) else {"path": str(item)}
    path = str(data.get("path") or data.get("name") or f"artifact-{index}")
    bytes_value = data.get("bytes") or data.get("size")
    return ArtifactIndexItem(
        id=str(data.get("id") or data.get("artifact_id") or f"artifact-{index}"),
        title=str(data.get("title") or path.rsplit("/", 1)[-1]),
        path=path,
        mediaType=str(data.get("mediaType") or data.get("media_type") or "application/octet-stream"),
        bytes=int(bytes_value) if isinstance(bytes_value, (int, float)) else None,
        createdAt=iso_time(data.get("created_at") or data.get("createdAt")) if data.get("created_at") or data.get("createdAt") else None,
        ownerNodeId=str(data.get("ownerNodeId") or data.get("owner_node_id") or data.get("node_id") or "") or None,
    )
