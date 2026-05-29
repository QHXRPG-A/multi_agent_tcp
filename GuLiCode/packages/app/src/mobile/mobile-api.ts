import { mobileMockData } from "./mock-data"
import { configureMobileLogger, logMobileEvent } from "./mobile-logger"
import type {
  BlueprintAgentPanelEvent,
  BlueprintEdge,
  BlueprintDiffFile,
  MobilePlanningRequest,
  MobileServerState,
  MobileDesktopSessionMirror,
  MobileDesktopComposerMirror,
  MobileDesktopMessageSegment,
  MobileDesktopSessionMessage,
  BlueprintNode,
  BlueprintNodeState,
  MobileMockData,
  TopAgentMessage,
} from "./mobile-state"

type ServerProject = {
  id: string
  name: string
  capabilities?: string[]
  latestRun?: ServerRun
}

type ServerRun = {
  id: string
  projectId: string
  blueprintId: string
  title: string
  status: string
  updatedAt: string
  currentNodeIds?: string[]
}

type ServerRuntimeEvent = {
  cursor: string
  type: string
  occurredAt: string
  nodeId?: string
  agentId?: string
  payload?: Record<string, unknown>
}

type ServerAgent = {
  nodeId: string
  agentId: string
  cliKind?: string
  state: string
  taskStatus?: string
  queueSize: number
  messagesSent: number
  busyCount: number
  updatedAt?: string
  recentEvents?: ServerRuntimeEvent[]
}

type ServerBlueprintNode = {
  id: string
  label: string
  role?: string
  state: string
  x?: number
  y?: number
  upstreamNodeIds?: string[]
  downstreamNodeIds?: string[]
}

type ServerBlueprintEdge = {
  source: string
  target: string
  kind?: string
}

type ServerDiff = {
  total: number
  accepted: number
  conflict: number
  rejected: number
  pending: number
  files: number
  additions: number
  deletions: number
  changesets: Array<{
    id: string
    status: string
    summary: string
    files: string[]
  }>
}

type ServerPlanningRequest = MobilePlanningRequest

type ServerDesktopSessions = {
  desktop: {
    online: boolean
    loggedIn?: boolean
    stale: boolean
    updatedAt?: string | null
  }
  activeSessionId?: string | null
  sessions: MobileDesktopSessionMirror["sessions"]
  currentMessages: MobileDesktopSessionMessage[]
  composer?: MobileDesktopComposerMirror | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}

type ServerStatus = {
  run: ServerRun
  blueprint: {
    nodes: ServerBlueprintNode[]
    edges?: ServerBlueprintEdge[]
  }
  agents: ServerAgent[]
  outputs?: {
    diff?: ServerDiff
  }
}

export type MobileLoadResult = {
  data: MobileMockData
  source: "api" | "mock"
  status: "ready" | "logged-out" | "waiting-peer" | "empty" | "error"
  message?: string
}

type ApiJsonOptions = {
  method?: "GET" | "POST"
  body?: unknown
  csrfToken?: string
}

export type MobileLoginResult = {
  ok: boolean
  csrfToken: string
  clients?: {
    mobile: boolean
    desktop: boolean
  }
  syncReady?: boolean
}

export type MobileTickResult = {
  ok: boolean
  csrfToken?: string
  clients?: {
    mobile: boolean
    desktop: boolean
  }
  syncReady: boolean
  project?: ServerProject | null
  run?: ServerRun | null
  status?: ServerStatus | null
  desktopSessions?: ServerDesktopSessions | null
}

class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message)
  }
}

export async function loadMobileCollaborationData(fetcher: typeof fetch = fetch): Promise<MobileLoadResult> {
  configureMobileLogger({ fetcher })
  logMobileEvent("info", "mobile.load.start", "Loading mobile collaboration data", {}, { fetcher })
  try {
    const me = await apiJson<{
      ok: boolean
      csrfToken?: string
      clients?: { mobile: boolean; desktop: boolean }
      syncReady?: boolean
    }>("/api/me", fetcher)
    if (me.syncReady === false) {
      return emptyResult(
        "Waiting for desktop login",
        {
          csrfToken: me.csrfToken,
          clients: me.clients,
          syncReady: false,
          capabilities: [],
          planningRequests: [],
        },
        "waiting-peer",
      )
    }
    const projects = await apiJson<{ projects: ServerProject[] }>("/api/projects", fetcher)
    if (!Array.isArray(projects.projects)) throw new Error("Collaboration Server unavailable")
    const project = projects.projects[0]
    if (!project) {
      logMobileEvent("info", "mobile.project.empty", "No project access", {}, { fetcher })
      return emptyResult("No project access")
    }

    const run = project.latestRun ?? (await firstProjectRun(project.id, fetcher))
    const planningRequests = await loadPlanningRequests(project.id, fetcher)
    const desktopSessions = await loadDesktopSessions(fetcher).catch(() => undefined)
    const server: MobileServerState = {
      csrfToken: me.csrfToken,
      projectId: project.id,
      runId: run?.id,
      clients: me.clients,
      syncReady: me.syncReady,
      capabilities: project.capabilities ?? [],
      planningRequests,
      desktopSessions: normalizeDesktopSessions(desktopSessions),
    }
    if (!run) {
      logMobileEvent("info", "mobile.run.empty", "No blueprint run", { projectId: project.id }, { fetcher })
      return emptyResult("No blueprint run", server)
    }

    const status = await apiJson<{ status: ServerStatus }>(`/api/runs/${encodeURIComponent(run.id)}/status`, fetcher)
    const diff = await apiJson<{ diff: ServerDiff }>(`/api/runs/${encodeURIComponent(run.id)}/diff`, fetcher).catch(() => null)
    const events = await apiJson<{ events: ServerRuntimeEvent[] }>(
      `/api/runs/${encodeURIComponent(run.id)}/events?cursor=0`,
      fetcher,
    ).catch(() => ({ events: [] }))

    logMobileEvent(
      "info",
      "mobile.load.success",
      "Loaded mobile collaboration data from API",
      { projectId: project.id, runId: run.id, eventCount: events.events.length, hasDiff: Boolean(diff?.diff) },
      { fetcher },
    )
    return {
      data: serverStateToMobile(project, status.status, diff?.diff ?? status.status.outputs?.diff, events.events, server),
      source: "api",
      status: "ready",
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      logMobileEvent("info", "mobile.api.fallback", "Using mock data because login is required", { status: 401, code: error.code }, { fetcher })
      return { data: mobileMockData, source: "mock", status: "logged-out", message: "Login required" }
    }
    logMobileEvent(
      "error",
      "mobile.api.fallback",
      "Using mock data because the Collaboration Server request failed",
      { error: error instanceof Error ? error.message : String(error) },
      { fetcher },
    )
    return {
      data: mobileMockData,
      source: "mock",
      status: "error",
      message: error instanceof Error ? error.message : String(error),
    }
  }
}

export async function loginMobileCollaboration(
  username: string,
  password: string,
  clientKind: "mobile" | "desktop" = "mobile",
  fetcher: typeof fetch = fetch,
) {
  configureMobileLogger({ fetcher })
  logMobileEvent("info", "mobile.login.start", "Logging in to mobile collaboration API", {}, { fetcher })
  const result = await apiJson<MobileLoginResult>("/api/auth/login", fetcher, {
    method: "POST",
    body: { username, password, clientKind },
  })
  logMobileEvent("info", "mobile.login.success", "Logged in to mobile collaboration API", {}, { fetcher })
  return result
}

export async function logoutMobileCollaboration(fetcher: typeof fetch = fetch) {
  configureMobileLogger({ fetcher })
  const result = await apiJson<{ ok: boolean }>("/api/auth/logout", fetcher, {
    method: "POST",
  })
  logMobileEvent("info", "mobile.logout.success", "Logged out of mobile collaboration API", {}, { fetcher })
  return result
}

export async function loadMobileTick(fetcher: typeof fetch = fetch) {
  configureMobileLogger({ fetcher })
  return apiJson<MobileTickResult>("/api/mobile/tick", fetcher)
}

export function isCollaborationUnauthorized(error: unknown) {
  return error instanceof ApiError && error.status === 401
}

export function createMobileTickGuard(task: () => Promise<void>) {
  let inFlight = false
  return async () => {
    if (inFlight) return false
    inFlight = true
    try {
      await task()
      return true
    } finally {
      inFlight = false
    }
  }
}

export function applyMobileTickToData(current: MobileMockData, tick: MobileTickResult): MobileMockData {
  const currentServer = current.server
  const server: MobileServerState = {
    csrfToken: tick.csrfToken ?? currentServer?.csrfToken,
    projectId: tick.project?.id ?? currentServer?.projectId,
    runId: tick.run === null ? undefined : (tick.run?.id ?? currentServer?.runId),
    clients: tick.clients ?? currentServer?.clients,
    syncReady: tick.syncReady,
    capabilities: tick.project?.capabilities ?? currentServer?.capabilities ?? [],
    planningRequests: currentServer?.planningRequests ?? [],
    desktopSessions: normalizeDesktopSessions(tick.desktopSessions) ?? currentServer?.desktopSessions,
  }

  if (!tick.syncReady) {
    return {
      ...current,
      server,
    }
  }

  if (!tick.status || !tick.project) {
    const message = tick.run ? `${tick.run.title || tick.run.id} is unavailable.` : "No blueprint run"
    const desktopMessages = messagesFromDesktopSessions(server.desktopSessions)
    return {
      ...emptyMobileData(message, server, tick.project ?? undefined),
      messages: desktopMessages ?? replaceTickPlaceholderMessages(current, message),
    }
  }

  const projected = serverStateToMobile(tick.project, tick.status, undefined, [], server)
  const desktopMessages = messagesFromDesktopSessions(server.desktopSessions)
  return {
    ...current,
    messages: desktopMessages ?? (shouldReplaceTickPlaceholder(current) ? projected.messages : current.messages),
    blueprint: {
      ...projected.blueprint,
      diff: current.blueprint.diff,
    },
    server,
  }
}

function replaceTickPlaceholderMessages(current: MobileMockData, body: string): TopAgentMessage[] {
  if (!shouldReplaceTickPlaceholder(current)) return current.messages
  return [
    {
      id: "mobile-empty",
      speaker: "top-agent",
      label: "Collaboration Server",
      body,
      time: "--",
    },
  ]
}

function shouldReplaceTickPlaceholder(current: MobileMockData) {
  return current.messages.length === 1 && current.messages[0]?.id === "mobile-empty"
}

function emptyMobileData(message: string, server?: MobileServerState, project?: ServerProject): MobileMockData {
  return {
    messages: messagesFromDesktopSessions(server?.desktopSessions) ?? [
      {
        id: "mobile-empty",
        speaker: "top-agent",
        label: "Collaboration Server",
        body: message,
        time: "--",
      },
    ],
    blueprint: {
      title: project?.name ?? "蓝图未同步",
      description: message,
      nodes: [],
      edges: [],
      run: {
        label: message,
        progress: 0,
        currentNode: "",
        updatedAt: "--",
        agents: [],
      },
      diff: { fileCount: 0, additions: 0, deletions: 0, files: [] },
    },
    server,
  }
}

export function serverStateToMobile(
  project: ServerProject,
  status: ServerStatus,
  diff: ServerDiff | undefined,
  events: ServerRuntimeEvent[],
  server?: MobileServerState,
): MobileMockData {
  const hasServerNodes = status.blueprint.nodes.length > 0
  const nodes = hasServerNodes ? status.blueprint.nodes.map((node) => serverNodeToMobile(node, status.agents, events)) : []
  const edges = status.blueprint.edges?.length ? status.blueprint.edges.map(serverEdgeToMobile) : []
  const running = nodes.find((node) => node.state === "running") ?? nodes.find((node) => node.state !== "done") ?? nodes[0]
  const completed = nodes.filter((node) => node.state === "done").length
  const progress = nodes.length ? Math.round((completed / nodes.length) * 100) : 0

  return {
    messages: messagesFromDesktopSessions(server?.desktopSessions) ?? eventsToMessages(events, status.run),
    blueprint: {
      title: status.run.title || project.name,
      description: nodes.length ? "来自桌面端蓝图的只读结构投影。" : "当前没有可同步的蓝图结构。",
      nodes,
      edges,
      run: {
        label: runStatusLabel(status.run.status),
        progress,
        currentNode: running?.label ?? "",
        updatedAt: shortTime(status.run.updatedAt),
        agents: nodes.map((node) => ({ name: node.label, state: node.state })),
      },
      diff: diffToMobile(diff),
    },
    server,
  }
}

function serverEdgeToMobile(edge: ServerBlueprintEdge): BlueprintEdge {
  return {
    source: edge.source,
    target: edge.target,
    kind: edge.kind,
  }
}

async function firstProjectRun(projectId: string, fetcher: typeof fetch) {
  const runs = await apiJson<{ runs: ServerRun[] }>(`/api/projects/${encodeURIComponent(projectId)}/runs`, fetcher).catch(
    () => ({ runs: [] }),
  )
  return runs.runs[0]
}

async function loadPlanningRequests(projectId: string, fetcher: typeof fetch) {
  const response = await apiJson<{ planningRequests: ServerPlanningRequest[] }>(
    `/api/projects/${encodeURIComponent(projectId)}/planning-requests`,
    fetcher,
  ).catch(() => ({ planningRequests: [] }))
  return Array.isArray(response.planningRequests) ? response.planningRequests : []
}

async function loadDesktopSessions(fetcher: typeof fetch) {
  return apiJson<ServerDesktopSessions & { ok?: boolean }>("/api/mobile/desktop-sessions", fetcher)
}

async function apiJson<T>(path: string, fetcher: typeof fetch, options: ApiJsonOptions = {}): Promise<T> {
  const method = options.method ?? "GET"
  const started = nowMs()
  logMobileEvent("debug", "mobile.api.start", "Starting mobile API request", { path, method }, { fetcher })
  try {
    const headers: Record<string, string> = { accept: "application/json" }
    let body: string | undefined
    if (options.body !== undefined) {
      headers["content-type"] = "application/json"
      body = JSON.stringify(options.body)
    }
    if (options.csrfToken) headers["x-csrf-token"] = options.csrfToken
    const response = await fetcher(collaborationApiPath(path), {
      method,
      credentials: "include",
      headers,
      body,
    })
    const requestId = response.headers.get("x-request-id") ?? undefined
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      const error = new ApiError(response.status, String(data.code ?? "REQUEST_FAILED"), String(data.message ?? response.statusText))
      logMobileEvent(
        response.status >= 500 ? "error" : "warning",
        "mobile.api.failure",
        error.message,
        { path, method, status: response.status, code: error.code, durationMs: Math.round(nowMs() - started) },
        { fetcher, requestId },
      )
      throw error
    }
    logMobileEvent(
      "debug",
      "mobile.api.success",
      "Completed mobile API request",
      { path, method, status: response.status, durationMs: Math.round(nowMs() - started) },
      { fetcher, requestId },
    )
    return data as T
  } catch (error) {
    if (!(error instanceof ApiError)) {
      logMobileEvent(
        "error",
        "mobile.api.failure",
        error instanceof Error ? error.message : String(error),
        { path, method, durationMs: Math.round(nowMs() - started) },
        { fetcher },
      )
    }
    throw error
  }
}

function collaborationApiPath(path: string) {
  const env = (import.meta as ImportMeta & { env?: { VITE_COLLABORATION_API_URL?: string } }).env
  const base = env?.VITE_COLLABORATION_API_URL?.trim().replace(/\/+$/, "")
  if (!base) return path
  return `${base}${path.startsWith("/") ? path : `/${path}`}`
}

export async function mobileApiPost<T>(
  path: string,
  body: unknown,
  server: MobileServerState | undefined,
  fetcher: typeof fetch = fetch,
): Promise<T> {
  if (!server?.csrfToken) throw new ApiError(403, "CSRF_UNAVAILABLE", "CSRF token is unavailable")
  return apiJson<T>(path, fetcher, { method: "POST", body, csrfToken: server.csrfToken })
}

export async function createMobilePlanningRequest(
  server: MobileServerState | undefined,
  goal: string,
  fetcher: typeof fetch = fetch,
) {
  const projectId = requiredServerValue(server?.projectId, "PROJECT_UNAVAILABLE", "Project id is unavailable")
  return mobileApiPost<{ planningRequest: MobilePlanningRequest }>(
    `/api/projects/${encodeURIComponent(projectId)}/planning-requests`,
    { goal },
    server,
    fetcher,
  )
}

export async function sendMobileAgentMessage(
  server: MobileServerState | undefined,
  nodeId: string,
  text: string,
  mode: "default" | "top" = "default",
  fetcher: typeof fetch = fetch,
) {
  const runId = requiredServerValue(server?.runId, "RUN_UNAVAILABLE", "Run id is unavailable")
  return mobileApiPost<{ result: unknown }>(
    `/api/runs/${encodeURIComponent(runId)}/messages`,
    { nodeId, text, mode },
    server,
    fetcher,
  )
}

export async function sendMobileDesktopMessage(
  server: MobileServerState | undefined,
  text: string,
  sessionIdOrOptions?:
    | string
    | {
        sessionId?: string
        promptMode?: "normal" | "blueprintPlanning"
        agentName?: string | null
        mode?: "default" | "top"
      },
  fetcher: typeof fetch = fetch,
) {
  const sessionId = typeof sessionIdOrOptions === "string" ? sessionIdOrOptions : sessionIdOrOptions?.sessionId
  const promptMode =
    typeof sessionIdOrOptions === "object" && sessionIdOrOptions.promptMode === "blueprintPlanning"
      ? "blueprintPlanning"
      : "normal"
  const agentName = typeof sessionIdOrOptions === "object" ? (sessionIdOrOptions.agentName ?? undefined) : undefined
  const legacyMode = typeof sessionIdOrOptions === "object" ? sessionIdOrOptions.mode : undefined
  const body: {
    text: string
    sessionId?: string
    promptMode: "normal" | "blueprintPlanning"
    agentName?: string | null
    mode?: "default" | "top"
  } = { text, sessionId, promptMode }
  if (agentName) body.agentName = agentName
  if (legacyMode) body.mode = legacyMode
  return mobileApiPost<{ accepted: boolean; status: string; interaction?: unknown }>(
    "/api/mobile/desktop-submit",
    body,
    server,
    fetcher,
  )
}

export async function deleteMobileDesktopSession(
  server: MobileServerState | undefined,
  sessionId?: string,
  fetcher: typeof fetch = fetch,
) {
  return mobileApiPost<{ accepted: boolean; status: string; interaction?: unknown }>(
    "/api/mobile/desktop-session-delete",
    { sessionId },
    server,
    fetcher,
  )
}

export async function cancelMobileRun(server: MobileServerState | undefined, fetcher: typeof fetch = fetch) {
  const runId = requiredServerValue(server?.runId, "RUN_UNAVAILABLE", "Run id is unavailable")
  return mobileApiPost<{ run: unknown }>(`/api/runs/${encodeURIComponent(runId)}/end`, { action: "cancel" }, server, fetcher)
}

export async function approveMobileDiff(
  server: MobileServerState | undefined,
  changesetId?: string,
  fetcher: typeof fetch = fetch,
) {
  const runId = requiredServerValue(server?.runId, "RUN_UNAVAILABLE", "Run id is unavailable")
  return mobileApiPost<{ approval: unknown }>(
    `/api/runs/${encodeURIComponent(runId)}/approvals`,
    { action: "approve_diff", changesetId },
    server,
    fetcher,
  )
}

export async function rollbackMobileDiff(server: MobileServerState | undefined, changesetId: string, fetcher: typeof fetch = fetch) {
  const runId = requiredServerValue(server?.runId, "RUN_UNAVAILABLE", "Run id is unavailable")
  return mobileApiPost<{ rollback: unknown }>(
    `/api/runs/${encodeURIComponent(runId)}/approvals`,
    { action: "rollback_diff", changesetId },
    server,
    fetcher,
  )
}

export async function answerMobilePlanningQuestion(
  server: MobileServerState | undefined,
  planningRequestId: string,
  questionId: string,
  answers: Record<string, unknown>,
  fetcher: typeof fetch = fetch,
) {
  return mobileApiPost<{ planningRequest: MobilePlanningRequest }>(
    `/api/planning-requests/${encodeURIComponent(planningRequestId)}/answer`,
    { questionId, answers },
    server,
    fetcher,
  )
}

export async function approveMobilePlanningPlan(
  server: MobileServerState | undefined,
  planningRequestId: string,
  fetcher: typeof fetch = fetch,
) {
  return mobileApiPost<{ planningRequest: MobilePlanningRequest; run: unknown }>(
    `/api/planning-requests/${encodeURIComponent(planningRequestId)}/approve-plan`,
    {},
    server,
    fetcher,
  )
}

export async function rejectMobilePlanningPlan(
  server: MobileServerState | undefined,
  planningRequestId: string,
  reason: string,
  fetcher: typeof fetch = fetch,
) {
  return mobileApiPost<{ planningRequest: MobilePlanningRequest }>(
    `/api/planning-requests/${encodeURIComponent(planningRequestId)}/reject-plan`,
    { reason },
    server,
    fetcher,
  )
}

function requiredServerValue(value: string | undefined, code: string, message: string) {
  if (!value) throw new ApiError(400, code, message)
  return value
}

function emptyResult(
  message: string,
  server?: MobileServerState,
  status: MobileLoadResult["status"] = "empty",
): MobileLoadResult {
  return {
    data: emptyMobileData(message, server),
    source: "api",
    status,
    message,
  }
}

function serverNodeToMobile(node: ServerBlueprintNode, agents: ServerAgent[], events: ServerRuntimeEvent[]): BlueprintNode {
  const agent = agents.find((item) => item.nodeId === node.id)
  const state = nodeState(node.state || agent?.state)
  const panelEvents = (agent?.recentEvents?.length ? agent.recentEvents : events.filter((event) => event.nodeId === node.id)).map(
    eventToPanelEvent,
  )

  return {
    id: node.id,
    label: node.label,
    state,
    role: node.role ?? agent?.cliKind ?? "Agent",
    detail: `Upstream ${node.upstreamNodeIds?.length ?? 0} / downstream ${node.downstreamNodeIds?.length ?? 0}`,
    note: "Read-only mobile projection.",
    layout: serverNodeLayout(node),
    agentPanel: {
      agentId: agent?.agentId ?? node.label,
      cliKind: agent?.cliKind ?? "unknown",
      taskStatus: agent?.taskStatus ?? agent?.state ?? node.state,
      queueSize: agent?.queueSize ?? 0,
      messagesSent: agent?.messagesSent ?? 0,
      busyCount: agent?.busyCount ?? 0,
      updatedAt: shortTime(agent?.updatedAt),
      statusDetails: [
        { label: "nodeId", value: node.id },
        { label: "agentId", value: agent?.agentId ?? node.label },
        { label: "state", value: agent?.state ?? node.state },
      ],
      events: panelEvents.length ? panelEvents : [fallbackPanelEvent(node.id)],
      inputPlaceholder: "Message this agent",
      disabledNotice: "Mobile writes require API access and run:message permission.",
    },
  }
}

function serverNodeLayout(node: ServerBlueprintNode) {
  const x = optionalNumber(node.x)
  const y = optionalNumber(node.y)
  return x === undefined || y === undefined ? undefined : { x, y }
}

function optionalNumber(value: unknown): number | undefined {
  const number = typeof value === "number" ? value : Number(value)
  return Number.isFinite(number) ? number : undefined
}

function eventsToMessages(events: ServerRuntimeEvent[], run: ServerRun): TopAgentMessage[] {
  const messages = events.filter((event) => event.type.includes("utterance") || event.type.includes("status")).slice(-8)
  if (!messages.length) {
    return [
      {
        id: `run-${run.id}`,
        speaker: "top-agent",
        label: "Collaboration Server",
        body: `${run.title || run.id} is ${run.status}.`,
        time: shortTime(run.updatedAt),
      },
    ]
  }
  return messages.map((event, index) => ({
    id: `event-${event.cursor || index}`,
    speaker: event.type.includes("utterance") ? "top-agent" : "user",
    label: event.agentId ?? event.nodeId ?? "Runtime",
    body: eventText(event),
    time: shortTime(event.occurredAt),
  }))
}

function normalizeDesktopMessageSegments(value: unknown): MobileDesktopMessageSegment[] | undefined {
  if (!Array.isArray(value)) return undefined
  const segments = value.flatMap((item, index): MobileDesktopMessageSegment[] => {
    if (!isRecord(item)) return []
    const type = item.type
    if (type !== "text" && type !== "reasoning" && type !== "tool") return []
    const id = typeof item.id === "string" && item.id.trim() ? item.id : `segment-${index}`
    const segment: MobileDesktopMessageSegment = { id, type }
    if (typeof item.title === "string") segment.title = item.title
    if (typeof item.body === "string") segment.body = item.body
    if (typeof item.status === "string") segment.status = item.status
    if (typeof item.toolName === "string") segment.toolName = item.toolName
    return [segment]
  })
  return segments.length ? segments : undefined
}

function internalDesktopMessagePlaceholder(value: string) {
  const normalized = value.trim().toLowerCase()
  if (normalized === "[reasoning]") return "reasoning"
  if (normalized === "[tool call]" || normalized === "[tool]") return "tool"
  return undefined
}

function desktopMessageSegmentsForDisplay(message: MobileDesktopSessionMessage): MobileDesktopMessageSegment[] | undefined {
  const segments = normalizeDesktopMessageSegments(message.segments)
  if (segments) return segments
  const placeholder = internalDesktopMessagePlaceholder(message.body)
  if (placeholder === "reasoning") {
    return [{ id: `${message.id || "message"}-reasoning-placeholder`, type: "reasoning", title: "思考过程", body: "" }]
  }
  if (placeholder === "tool") {
    return [{ id: `${message.id || "message"}-tool-placeholder`, type: "tool", title: "工具调用", body: "" }]
  }
  return undefined
}

function desktopMessageBodyForDisplay(message: MobileDesktopSessionMessage) {
  return internalDesktopMessagePlaceholder(message.body) ? "" : message.body
}

function normalizeDesktopComposer(value?: MobileDesktopComposerMirror | null): MobileDesktopComposerMirror {
  const modes = Array.isArray(value?.modes)
    ? value.modes
        .filter((mode) => {
          if (!mode || typeof mode.id !== "string" || typeof mode.label !== "string") return false
          return mode.kind === "agent" || mode.kind === "blueprintPlanning"
        })
        .map((mode) => ({ id: mode.id, label: mode.label, kind: mode.kind }))
    : []
  return {
    modes,
    activeModeId: typeof value?.activeModeId === "string" ? value.activeModeId : null,
  }
}

function normalizeDesktopSessions(value?: ServerDesktopSessions | null): MobileDesktopSessionMirror | undefined {
  if (!value) return undefined
  return {
    online: value.desktop?.online === true,
    loggedIn: value.desktop?.loggedIn === true || value.desktop?.online === true,
    stale: value.desktop?.stale !== false,
    updatedAt: value.desktop?.updatedAt ?? null,
    activeSessionId: value.activeSessionId ?? null,
    sessions: Array.isArray(value.sessions) ? value.sessions : [],
    currentMessages: Array.isArray(value.currentMessages)
      ? value.currentMessages.map((message) => ({
          ...message,
          body: desktopMessageBodyForDisplay(message),
          segments: desktopMessageSegmentsForDisplay(message),
        }))
      : [],
    composer: normalizeDesktopComposer(value.composer),
  }
}

function messagesFromDesktopSessions(mirror?: MobileDesktopSessionMirror): TopAgentMessage[] | undefined {
  const messages = mirror?.currentMessages ?? []
  if (!messages.length) return undefined
  return messages.slice(-12).map((message, index) => ({
    id: `desktop-${message.id || index}`,
    speaker: message.role === "user" ? "user" : "top-agent",
    label: message.label || (message.role === "user" ? "User" : "Desktop"),
    body: desktopMessageBodyForDisplay(message),
    segments: desktopMessageSegmentsForDisplay(message),
    time: shortTime(message.createdAt ?? undefined),
  }))
}

function eventToPanelEvent(event: ServerRuntimeEvent): BlueprintAgentPanelEvent {
  return {
    id: `event-${event.cursor}`,
    title: event.type,
    text: eventText(event),
    tone: eventTone(event.type),
    status: event.type,
    time: shortTime(event.occurredAt),
  }
}

function fallbackPanelEvent(nodeId: string): BlueprintAgentPanelEvent {
  return {
    id: `${nodeId}-status`,
    title: "Runtime status",
    text: "No recent visible events.",
    tone: "event",
  }
}

function eventText(event: ServerRuntimeEvent) {
  const payload = event.payload ?? {}
  if (typeof payload.message === "string") return payload.message
  if (typeof payload.text === "string") return payload.text
  if (typeof payload.payload === "string") return payload.payload
  return JSON.stringify(payload)
}

function eventTone(type: string): BlueprintAgentPanelEvent["tone"] {
  if (type.includes("tool")) return "tool"
  if (type.includes("failed") || type.includes("conflict")) return "error"
  if (type.includes("utterance")) return "reply"
  if (type.includes("status")) return "event"
  return "event"
}

function nodeState(value?: string): BlueprintNodeState {
  switch ((value ?? "").toLowerCase()) {
    case "completed":
    case "done":
    case "succeeded":
      return "done"
    case "running":
    case "dispatching":
    case "waiting_for_reply":
    case "processing_reply":
      return "running"
    case "idle":
      return "idle"
    case "failed":
    case "error":
      return "failed"
    case "queued":
    case "pending":
      return "queued"
    default:
      return "queued"
  }
}

function runStatusLabel(status: string) {
  if (status === "running") return "Running"
  if (status === "completed") return "Completed"
  if (status === "failed") return "Failed"
  if (status === "cancelled") return "Cancelled"
  if (status === "unknown") return "未运行"
  return "Unknown"
}

function diffToMobile(diff: ServerDiff | undefined): MobileMockData["blueprint"]["diff"] {
  if (!diff) return { fileCount: 0, additions: 0, deletions: 0, files: [] }
  const files: BlueprintDiffFile[] = []
  for (const changeset of diff.changesets) {
    for (const path of changeset.files) {
      files.push({
        path,
        summary: changeset.summary || changeset.status,
        additions: files.length === 0 ? diff.additions : 0,
        deletions: files.length === 0 ? diff.deletions : 0,
        changesetId: changeset.id,
        changesetStatus: changeset.status,
        rollbackable: changeset.status === "accepted",
        previewLines: [
          { type: "context", text: `${changeset.id} ${changeset.status}` },
          { type: "add", text: `+${diff.additions} additions` },
          { type: "delete", text: `-${diff.deletions} deletions` },
        ],
      })
    }
  }
  return {
    fileCount: diff.files || files.length,
    additions: diff.additions,
    deletions: diff.deletions,
    files,
  }
}

function shortTime(value?: string) {
  if (!value) return "--"
  const match = value.match(/T(\d\d:\d\d)/)
  return match?.[1] ?? value
}

function nowMs() {
  return typeof performance !== "undefined" ? performance.now() : Date.now()
}
