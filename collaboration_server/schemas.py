from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


ClientKind = Literal["mobile", "desktop"]
ProjectRole = Literal["owner", "operator", "viewer"]
SystemRole = Literal["admin", "user"]
RunStatus = Literal["running", "completed", "cancelled", "failed", "paused", "unknown"]
NodeState = Literal["idle", "queued", "running", "completed", "failed", "unknown"]
BlueprintNodeKind = Literal["agent", "worker_agent", "script", "branch", "tick"]
PlanningRequestStatus = Literal[
    "pending_desktop",
    "planning",
    "question_pending",
    "question_answered",
    "plan_ready",
    "plan_rejected",
    "starting",
    "started",
    "failed",
    "cancelled",
]
RuntimeEventType = Literal[
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
]


class ErrorResponse(BaseModel):
    ok: bool = False
    code: str
    message: str
    requestId: str
    details: Optional[dict[str, Any]] = None


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=4096)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=4096)
    clientKind: Optional[ClientKind] = None


class UserSummary(BaseModel):
    id: str
    username: str
    role: SystemRole
    active: bool
    createdAt: str
    updatedAt: str


class MeResponse(BaseModel):
    ok: bool = True
    user: UserSummary
    csrfToken: str


class HealthResponse(BaseModel):
    ok: bool = True
    service: str = "gulicode-collaboration-server"


class RunSummary(BaseModel):
    id: str
    projectId: str
    blueprintId: str
    title: str
    status: RunStatus
    createdAt: str
    updatedAt: str
    endedAt: Optional[str] = None
    currentNodeIds: list[str] = Field(default_factory=list)
    unreadEventCount: Optional[int] = None


class ProjectSummary(BaseModel):
    id: str
    name: str
    role: ProjectRole
    latestRun: Optional[RunSummary] = None
    capabilities: list[str] = Field(default_factory=list)


class BlueprintStructureNode(BaseModel):
    id: str
    label: str
    kind: BlueprintNodeKind = "worker_agent"
    role: Optional[str] = None
    state: NodeState
    summary: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    upstreamNodeIds: list[str] = Field(default_factory=list)
    downstreamNodeIds: list[str] = Field(default_factory=list)
    inputPorts: list[str] = Field(default_factory=list)
    outputPorts: list[str] = Field(default_factory=list)
    everyNTicks: Optional[int] = None


class BlueprintStructureEdge(BaseModel):
    source: str
    target: str
    kind: Literal["exec", "data", "unknown"] = "unknown"
    outputPort: Optional[str] = None
    inputPort: Optional[str] = None


class BlueprintStructureProjection(BaseModel):
    nodes: list[BlueprintStructureNode] = Field(default_factory=list)
    edges: list[BlueprintStructureEdge] = Field(default_factory=list)


class DesktopBlueprintSnapshotNode(BaseModel):
    id: str = Field(min_length=1, max_length=256)
    label: str = Field(min_length=1, max_length=512)
    kind: BlueprintNodeKind = "worker_agent"
    role: Optional[str] = None
    state: NodeState = "idle"
    summary: Optional[str] = Field(default=None, max_length=2048)
    x: Optional[float] = None
    y: Optional[float] = None
    upstreamNodeIds: list[str] = Field(default_factory=list)
    downstreamNodeIds: list[str] = Field(default_factory=list)
    inputPorts: list[str] = Field(default_factory=list, max_length=80)
    outputPorts: list[str] = Field(default_factory=list, max_length=80)
    everyNTicks: Optional[int] = Field(default=None, ge=1)
    agentId: Optional[str] = None
    cliKind: Optional[str] = None
    taskStatus: Optional[str] = None
    queueSize: int = 0
    messagesSent: int = 0
    busyCount: int = 0
    updatedAt: Optional[str] = None


class DesktopBlueprintSnapshotEdge(BaseModel):
    source: str = Field(min_length=1, max_length=256)
    target: str = Field(min_length=1, max_length=256)
    kind: Literal["exec", "data", "unknown"] = "unknown"
    outputPort: Optional[str] = Field(default=None, max_length=128)
    inputPort: Optional[str] = Field(default=None, max_length=128)


class DesktopBlueprintSnapshotRequest(BaseModel):
    projectId: Optional[str] = Field(default=None, min_length=1, max_length=128)
    projectDir: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    blueprintId: str = Field(default="default", min_length=1, max_length=128)
    title: Optional[str] = Field(default=None, max_length=512)
    description: Optional[str] = Field(default=None, max_length=1024)
    nodes: list[DesktopBlueprintSnapshotNode] = Field(default_factory=list)
    edges: list[DesktopBlueprintSnapshotEdge] = Field(default_factory=list)


class DesktopBridgeRegistrationRequest(BaseModel):
    bridgeUrl: str = Field(min_length=1, max_length=2048)
    bridgeToken: str = Field(min_length=1, max_length=4096)


class DesktopSessionSummaryRequest(BaseModel):
    id: str = Field(min_length=1, max_length=256)
    title: Optional[str] = Field(default=None, max_length=512)
    parentId: Optional[str] = Field(default=None, max_length=256)
    createdAt: Optional[str] = Field(default=None, max_length=64)
    updatedAt: Optional[str] = Field(default=None, max_length=64)
    messageCount: int = Field(default=0, ge=0)


class DesktopSessionMessageSegmentRequest(BaseModel):
    id: str = Field(min_length=1, max_length=256)
    type: Literal["text", "reasoning", "tool"] = "text"
    title: Optional[str] = Field(default=None, max_length=256)
    body: str = Field(default="", max_length=8192)
    status: Optional[str] = Field(default=None, max_length=64)
    toolName: Optional[str] = Field(default=None, max_length=256)


class DesktopSessionMessageRequest(BaseModel):
    id: str = Field(min_length=1, max_length=256)
    sessionId: Optional[str] = Field(default=None, max_length=256)
    role: str = Field(default="assistant", max_length=64)
    label: Optional[str] = Field(default=None, max_length=256)
    body: str = Field(default="", max_length=8192)
    segments: list[DesktopSessionMessageSegmentRequest] = Field(default_factory=list, max_length=80)
    createdAt: Optional[str] = Field(default=None, max_length=64)


class DesktopComposerModeRequest(BaseModel):
    id: str = Field(min_length=1, max_length=256)
    label: str = Field(min_length=1, max_length=256)
    kind: Literal["agent", "blueprintPlanning"] = "agent"


class DesktopComposerSnapshotRequest(BaseModel):
    modes: list[DesktopComposerModeRequest] = Field(default_factory=list, max_length=50)
    activeModeId: Optional[str] = Field(default=None, max_length=256)


class DesktopSessionSnapshotRequest(BaseModel):
    activeSessionId: Optional[str] = Field(default=None, max_length=256)
    sessions: list[DesktopSessionSummaryRequest] = Field(default_factory=list, max_length=100)
    currentMessages: list[DesktopSessionMessageRequest] = Field(default_factory=list, max_length=100)
    composer: Optional[DesktopComposerSnapshotRequest] = None
    updatedAt: Optional[str] = Field(default=None, max_length=64)


class MobileDesktopSubmitRequest(BaseModel):
    sessionId: Optional[str] = Field(default=None, max_length=256)
    mode: Literal["default", "top"] = "default"
    promptMode: Literal["normal", "blueprintPlanning"] = "normal"
    agentName: Optional[str] = Field(default=None, max_length=256)
    text: str = Field(min_length=1, max_length=8192)


class MobileDesktopSessionDeleteRequest(BaseModel):
    sessionId: Optional[str] = Field(default=None, max_length=256)


class RuntimeEvent(BaseModel):
    cursor: str
    runId: str
    type: RuntimeEventType
    occurredAt: str
    nodeId: Optional[str] = None
    agentId: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentPanelSnapshot(BaseModel):
    nodeId: str
    agentId: str
    cliKind: Optional[str] = None
    state: str
    taskStatus: Optional[str] = None
    queueSize: int = 0
    messagesSent: int = 0
    busyCount: int = 0
    updatedAt: Optional[str] = None
    recentEvents: list[RuntimeEvent] = Field(default_factory=list)


class RunDiffChangeset(BaseModel):
    id: str
    status: str
    summary: str
    files: list[str] = Field(default_factory=list)


class RunDiffSummary(BaseModel):
    total: int = 0
    accepted: int = 0
    conflict: int = 0
    rejected: int = 0
    pending: int = 0
    files: int = 0
    additions: int = 0
    deletions: int = 0
    changesets: list[RunDiffChangeset] = Field(default_factory=list)


class ReportIndexItem(BaseModel):
    id: str
    title: str
    path: str
    mediaType: str
    createdAt: Optional[str] = None
    ownerNodeId: Optional[str] = None


class ArtifactIndexItem(BaseModel):
    id: str
    title: str
    path: str
    mediaType: str
    bytes: Optional[int] = None
    createdAt: Optional[str] = None
    ownerNodeId: Optional[str] = None


class RunStatusProjection(BaseModel):
    run: RunSummary
    blueprint: BlueprintStructureProjection
    agents: list[AgentPanelSnapshot] = Field(default_factory=list)
    pending: dict[str, int] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    lastCursor: str


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=4096)
    role: SystemRole = "user"
    active: bool = True


class UserUpdateRequest(BaseModel):
    username: Optional[str] = Field(default=None, min_length=1, max_length=128)
    role: Optional[SystemRole] = None
    active: Optional[bool] = None


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=8, max_length=4096)


class ProjectCreateRequest(BaseModel):
    id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    archived: Optional[bool] = None


class ProjectAdminSummary(BaseModel):
    id: str
    name: str
    archived: bool
    createdAt: str
    updatedAt: str


class MemberRequest(BaseModel):
    userId: str = Field(min_length=1, max_length=128)
    role: ProjectRole


class MemberUpdateRequest(BaseModel):
    role: ProjectRole


class MemberSummary(BaseModel):
    projectId: str
    userId: str
    username: str
    role: ProjectRole


class RuntimeBindingRequest(BaseModel):
    blueprintId: str = Field(default="default", min_length=1, max_length=128)
    projectDir: str = Field(min_length=1)
    bridgeUrl: str = Field(min_length=1)
    bridgeToken: str = Field(min_length=1)
    active: bool = True


class RuntimeBindingUpdateRequest(BaseModel):
    blueprintId: Optional[str] = Field(default=None, min_length=1, max_length=128)
    projectDir: Optional[str] = Field(default=None, min_length=1)
    bridgeUrl: Optional[str] = Field(default=None, min_length=1)
    bridgeToken: Optional[str] = Field(default=None, min_length=1)
    active: Optional[bool] = None


class RuntimeBindingSummary(BaseModel):
    id: str
    projectId: str
    blueprintId: str
    projectDir: str = "[redacted]"
    bridgeUrl: str
    bridgeToken: str = "[redacted]"
    active: bool
    createdAt: str
    updatedAt: str


ClientLogLevel = Literal["debug", "info", "warning", "error"]


class ClientLogEntryRequest(BaseModel):
    level: ClientLogLevel = "info"
    event: str = Field(min_length=1, max_length=128)
    message: Optional[str] = Field(default=None, max_length=1024)
    context: dict[str, Any] = Field(default_factory=dict)
    requestId: Optional[str] = Field(default=None, max_length=128)
    createdAt: Optional[str] = Field(default=None, max_length=64)


class ClientLogBatchRequest(BaseModel):
    logs: list[ClientLogEntryRequest] = Field(min_length=1, max_length=100)


class ClientLogSummary(BaseModel):
    id: int
    createdAt: str
    sessionUserId: Optional[str] = None
    level: ClientLogLevel
    event: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)
    requestId: Optional[str] = None
    clientCreatedAt: Optional[str] = None


class ClientPresenceSummary(BaseModel):
    mobile: bool = False
    desktop: bool = False


class UserSessionMonitorSummary(BaseModel):
    clientKind: Optional[ClientKind] = None
    createdAt: str
    expiresAt: str
    userAgent: Optional[str] = None
    idSuffix: str


class UserMonitorSummary(BaseModel):
    user: UserSummary
    clients: ClientPresenceSummary
    activeSessionCount: int
    lastLoginAt: Optional[str] = None
    lastClientLogAt: Optional[str] = None
    sessions: list[UserSessionMonitorSummary] = Field(default_factory=list)


class UserMonitorTotals(BaseModel):
    totalUsers: int
    activeUsers: int
    activeSessions: int
    mobileOnline: int
    desktopOnline: int


class UserMonitorResponse(BaseModel):
    ok: bool = True
    totals: UserMonitorTotals
    users: list[UserMonitorSummary] = Field(default_factory=list)


class RunStartRequest(BaseModel):
    projectId: str = Field(min_length=1, max_length=128)
    blueprintId: Optional[str] = Field(default=None, min_length=1, max_length=128)
    plan: dict[str, Any] = Field(default_factory=dict)
    executionMode: Literal["live", "status"] = "live"


class RunMessageRequest(BaseModel):
    nodeId: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4096)
    mode: Literal["default", "top"] = "default"


class RunEndRequest(BaseModel):
    action: Literal["cancel"] = "cancel"
    reason: Optional[str] = Field(default=None, max_length=1024)


class RunApprovalRequest(BaseModel):
    action: Literal["approve_diff", "rollback_diff"]
    changesetId: Optional[str] = Field(default=None, min_length=1, max_length=128)
    reason: Optional[str] = Field(default=None, max_length=1024)


class PlanningRequestCreate(BaseModel):
    goal: str = Field(min_length=1, max_length=4096)
    blueprintId: Optional[str] = Field(default=None, min_length=1, max_length=128)


class PlanningRequestClaim(BaseModel):
    desktopSessionId: str = Field(min_length=1, max_length=128)


class PlanningRequestDesktopState(BaseModel):
    status: Optional[PlanningRequestStatus] = None
    planningSessionId: Optional[str] = Field(default=None, min_length=1, max_length=256)
    pendingQuestion: Optional[dict[str, Any]] = None
    pendingPlan: Optional[dict[str, Any]] = None
    activeRun: Optional[dict[str, Any]] = None
    error: Optional[str] = Field(default=None, max_length=2048)


class PlanningQuestionAnswerRequest(BaseModel):
    questionId: str = Field(min_length=1, max_length=128)
    answers: dict[str, Any] = Field(default_factory=dict)
    rejected: bool = False
    reason: Optional[str] = Field(default=None, max_length=1024)


class PlanningPlanRejectRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=1024)
