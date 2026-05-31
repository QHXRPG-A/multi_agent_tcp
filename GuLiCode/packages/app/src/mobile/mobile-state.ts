export type MobileTab = "chat" | "blueprint" | "pending"

export type TopAgentMessage = {
  id: string
  speaker: "user" | "top-agent"
  label: string
  body: string
  segments?: MobileDesktopMessageSegment[]
  time: string
}

export type MobileDesktopMessageSegment = {
  id: string
  type: "text" | "reasoning" | "tool"
  title?: string | null
  body?: string
  status?: string | null
  toolName?: string | null
}

export type BlueprintNodeState = "done" | "running" | "queued" | "idle" | "failed"
export type BlueprintNodeKind = "agent" | "worker_agent" | "script" | "branch" | "tick"

export type BlueprintAgentPanelEventTone = "user" | "reply" | "reasoning" | "tool" | "error" | "event"

export type BlueprintAgentPanelEvent = {
  id: string
  title: string
  text: string
  tone: BlueprintAgentPanelEventTone
  status?: string
  detail?: string
  time?: string
}

export type BlueprintAgentPanel = {
  agentId: string
  cliKind: string
  taskStatus: string
  queueSize: number
  messagesSent: number
  busyCount: number
  updatedAt: string
  statusDetails: Array<{
    label: string
    value: string
  }>
  events: BlueprintAgentPanelEvent[]
  inputPlaceholder: string
  disabledNotice: string
  canMessage?: boolean
}

export type BlueprintNode = {
  id: string
  label: string
  kind: BlueprintNodeKind
  state: BlueprintNodeState
  role: string
  detail: string
  note: string
  summary?: string
  inputPorts?: string[]
  outputPorts?: string[]
  everyNTicks?: number
  layout?: {
    x: number
    y: number
  }
  agentPanel: BlueprintAgentPanel
}

export type BlueprintEdge = {
  source: string
  target: string
  kind?: string
  outputPort?: string
  inputPort?: string
}

export type BlueprintRunStatus = {
  label: string
  progress: number
  currentNode: string
  updatedAt: string
  agents: Array<{
    name: string
    state: BlueprintNodeState
  }>
}

export type BlueprintDiffFile = {
  path: string
  summary: string
  additions: number
  deletions: number
  changesetId?: string
  changesetStatus?: string
  rollbackable?: boolean
  previewLines: BlueprintDiffPreviewLine[]
}

export type BlueprintDiffPreviewLine = {
  type: "context" | "add" | "delete"
  text: string
}

export type BlueprintDiffSummary = {
  fileCount: number
  additions: number
  deletions: number
  files: BlueprintDiffFile[]
}

export type MobilePlanningRequest = {
  id: string
  projectId: string
  blueprintId: string
  goal: string
  status: string
  desktopSessionId?: string | null
  planningSessionId?: string | null
  pendingQuestion?: Record<string, unknown> | null
  pendingPlan?: Record<string, unknown> | null
  mobileAnswer?: Record<string, unknown> | null
  activeRunId?: string | null
  error?: string | null
  createdAt?: string | number | null
  updatedAt?: string | number | null
}

export type MobileDesktopSessionSummary = {
  id: string
  title?: string | null
  parentId?: string | null
  createdAt?: string | null
  updatedAt?: string | null
  messageCount?: number
}

export type MobileDesktopSessionMessage = {
  id: string
  sessionId?: string | null
  role: string
  label?: string | null
  body: string
  segments?: MobileDesktopMessageSegment[]
  createdAt?: string | null
}

export type MobileDesktopComposerMode = {
  id: string
  label: string
  kind: "agent" | "blueprintPlanning"
}

export type MobileDesktopComposerMirror = {
  modes: MobileDesktopComposerMode[]
  activeModeId?: string | null
}

export type MobileDesktopSessionMirror = {
  online: boolean
  loggedIn: boolean
  stale: boolean
  updatedAt?: string | null
  activeSessionId?: string | null
  sessions: MobileDesktopSessionSummary[]
  currentMessages: MobileDesktopSessionMessage[]
  composer?: MobileDesktopComposerMirror
}

export type MobileServerState = {
  csrfToken?: string
  projectId?: string
  runId?: string
  clients?: {
    mobile: boolean
    desktop: boolean
  }
  syncReady?: boolean
  capabilities: string[]
  planningRequests: MobilePlanningRequest[]
  desktopSessions?: MobileDesktopSessionMirror
}

export type MobileMockData = {
  messages: TopAgentMessage[]
  blueprint: {
    title: string
    description: string
    nodes: BlueprintNode[]
    edges: BlueprintEdge[]
    run: BlueprintRunStatus
    diff: BlueprintDiffSummary
  }
  server?: MobileServerState
}

export const mobileTabs: Array<{ id: MobileTab; label: string }> = [
  { id: "chat", label: "聊天" },
  { id: "blueprint", label: "蓝图" },
  { id: "pending", label: "待定" },
]

export function nodeStateLabel(state: BlueprintNodeState) {
  switch (state) {
    case "done":
      return "已完成"
    case "running":
      return "运行中"
    case "queued":
      return "排队中"
    case "idle":
      return "空闲"
    case "failed":
      return "失败"
  }
}

export function nodeStateTone(state: BlueprintNodeState) {
  switch (state) {
    case "done":
      return "border-emerald-200 bg-emerald-50 text-emerald-700"
    case "running":
      return "border-rose-200 bg-rose-50 text-rose-700"
    case "queued":
      return "border-stone-200 bg-stone-50 text-stone-500"
    case "idle":
      return "border-stone-200 bg-white text-stone-500"
    case "failed":
      return "border-red-200 bg-red-50 text-red-700"
  }
}

export function nodeKindLabel(kind: BlueprintNodeKind) {
  switch (kind) {
    case "agent":
      return "Agent"
    case "worker_agent":
      return "Worker Agent"
    case "script":
      return "Script"
    case "branch":
      return "Branch"
    case "tick":
      return "Tick"
  }
}
