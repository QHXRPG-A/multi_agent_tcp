export type MobileProject = {
  id: string
  name: string
  description: string
  owner: string
  activeRunCount: number
}

export type MobileRunStatus = "running" | "needs-review" | "paused" | "completed" | "canceled" | "archived"

export type MobileRunPriority = "normal" | "high"

export type MobileRunEventKind = "status" | "agent" | "tool" | "report" | "action"

export type MobileRunEvent = {
  id: string
  kind: MobileRunEventKind
  title: string
  body: string
  time: string
}

export type MobileToolCard = {
  id: string
  title: string
  state: "pending" | "running" | "done" | "blocked"
  description: string
}

export type MobileReport = {
  id: string
  title: string
  kind: "summary" | "changeset" | "artifact"
  ready: boolean
}

export type MobileRun = {
  id: string
  projectId: string
  title: string
  instruction: string
  blueprint: string
  status: MobileRunStatus
  priority: MobileRunPriority
  progress: number
  cursor: number
  updatedAt: string
  agents: string[]
  events: MobileRunEvent[]
  tools: MobileToolCard[]
  reports: MobileReport[]
}

export type MobileRunAction = "confirm" | "reject" | "pause" | "cancel" | "archive"

export type MobileState = {
  projects: MobileProject[]
  runs: MobileRun[]
  selectedProjectId: string
  selectedRunId: string
}

type CreateRunInput = {
  projectId: string
  title: string
  instruction: string
  blueprint: string
  priority?: MobileRunPriority
}

const cloneEvent = (event: MobileRunEvent): MobileRunEvent => ({ ...event })
const cloneTool = (tool: MobileToolCard): MobileToolCard => ({ ...tool })
const cloneReport = (report: MobileReport): MobileReport => ({ ...report })

export function cloneRun(run: MobileRun): MobileRun {
  return {
    ...run,
    agents: [...run.agents],
    events: run.events.map(cloneEvent),
    tools: run.tools.map(cloneTool),
    reports: run.reports.map(cloneReport),
  }
}

export function cloneMobileState(state: MobileState): MobileState {
  return {
    projects: state.projects.map((project) => ({ ...project })),
    runs: state.runs.map(cloneRun),
    selectedProjectId: state.selectedProjectId,
    selectedRunId: state.selectedRunId,
  }
}

export function createMobileState(projects: MobileProject[], runs: MobileRun[]): MobileState {
  const selectedProjectId = projects[0]?.id ?? ""
  const selectedRunId = runs.find((run) => run.projectId === selectedProjectId)?.id ?? runs[0]?.id ?? ""
  return {
    projects: projects.map((project) => ({ ...project })),
    runs: runs.map(cloneRun),
    selectedProjectId,
    selectedRunId,
  }
}

export function getProjectRuns(state: MobileState, projectId = state.selectedProjectId) {
  return state.runs.filter((run) => run.projectId === projectId)
}

export function getSelectedRun(state: MobileState) {
  return state.runs.find((run) => run.id === state.selectedRunId)
}

export function getSelectedProject(state: MobileState) {
  return state.projects.find((project) => project.id === state.selectedProjectId)
}

export function selectProject(state: MobileState, projectId: string): MobileState {
  const next = cloneMobileState(state)
  const fallbackRun = next.runs.find((run) => run.projectId === projectId) ?? next.runs[0]
  next.selectedProjectId = projectId
  next.selectedRunId = fallbackRun?.id ?? ""
  return next
}

export function selectRun(state: MobileState, runId: string): MobileState {
  const next = cloneMobileState(state)
  const run = next.runs.find((item) => item.id === runId)
  if (!run) return next
  next.selectedRunId = run.id
  next.selectedProjectId = run.projectId
  return next
}

export function createRun(state: MobileState, input: CreateRunInput, now = new Date()): MobileState {
  const next = cloneMobileState(state)
  const projectRuns = next.runs.filter((run) => run.projectId === input.projectId)
  const id = `run-${input.projectId}-${projectRuns.length + 1}`
  const timestamp = now.toISOString()
  const run: MobileRun = {
    id,
    projectId: input.projectId,
    title: input.title.trim() || "Untitled mobile run",
    instruction: input.instruction.trim(),
    blueprint: input.blueprint,
    status: "running",
    priority: input.priority ?? "normal",
    progress: 8,
    cursor: 1,
    updatedAt: timestamp,
    agents: ["top-agent"],
    events: [
      {
        id: `${id}-event-1`,
        kind: "status",
        title: "Run created",
        body: "Mock top-agent accepted the mobile instruction.",
        time: timestamp,
      },
    ],
    tools: [
      {
        id: `${id}-tool-1`,
        title: "Runtime start",
        state: "running",
        description: "Waiting for the future Collaboration Server bridge.",
      },
    ],
    reports: [],
  }

  next.runs = [run, ...next.runs]
  next.selectedProjectId = input.projectId
  next.selectedRunId = id
  return next
}

export function applyRunAction(state: MobileState, runId: string, action: MobileRunAction, now = new Date()): MobileState {
  const next = cloneMobileState(state)
  const timestamp = now.toISOString()
  next.runs = next.runs.map((run) => {
    if (run.id !== runId) return run
    const status = statusForAction(run.status, action)
    const cursor = run.cursor + 1
    return {
      ...run,
      status,
      progress: progressForStatus(status, run.progress),
      cursor,
      updatedAt: timestamp,
      events: [
        {
          id: `${run.id}-event-${cursor}`,
          kind: "action",
          title: actionTitle(action),
          body: actionBody(action),
          time: timestamp,
        },
        ...run.events,
      ],
      tools: run.tools.map((tool) =>
        action === "pause" && tool.state === "running" ? { ...tool, state: "blocked" as const } : tool,
      ),
      reports: reportsForAction(run, action),
    }
  })
  return next
}

function statusForAction(current: MobileRunStatus, action: MobileRunAction): MobileRunStatus {
  if (current === "archived") return current
  if (action === "archive") return "archived"
  if (action === "confirm") return "completed"
  if (action === "reject" || action === "cancel") return "canceled"
  if (action === "pause") return "paused"
  return current
}

function progressForStatus(status: MobileRunStatus, current: number) {
  if (status === "completed" || status === "archived") return 100
  if (status === "canceled") return current
  if (status === "paused") return Math.max(current, 35)
  return current
}

function reportsForAction(run: MobileRun, action: MobileRunAction) {
  if (action !== "confirm") return run.reports
  if (run.reports.some((report) => report.kind === "summary")) return run.reports
  return [
    {
      id: `${run.id}-report-summary`,
      title: "Mock final report",
      kind: "summary" as const,
      ready: true,
    },
    ...run.reports,
  ]
}

function actionTitle(action: MobileRunAction) {
  switch (action) {
    case "confirm":
      return "Approved"
    case "reject":
      return "Rejected"
    case "pause":
      return "Paused"
    case "cancel":
      return "Canceled"
    case "archive":
      return "Archived"
  }
}

function actionBody(action: MobileRunAction) {
  switch (action) {
    case "confirm":
      return "User approved the current run result."
    case "reject":
      return "User rejected the current run result."
    case "pause":
      return "User paused the run for later review."
    case "cancel":
      return "User canceled the run from the mobile control surface."
    case "archive":
      return "User archived the run from the mobile control surface."
  }
}

export function statusLabel(status: MobileRunStatus) {
  switch (status) {
    case "running":
      return "Running"
    case "needs-review":
      return "Needs review"
    case "paused":
      return "Paused"
    case "completed":
      return "Completed"
    case "canceled":
      return "Canceled"
    case "archived":
      return "Archived"
  }
}

export function statusTone(status: MobileRunStatus) {
  switch (status) {
    case "running":
      return "text-text-interactive-base bg-surface-info-weak border-border-base"
    case "needs-review":
      return "text-icon-warning-base bg-surface-warning-weak border-border-warning-base"
    case "paused":
      return "text-text-weak bg-surface-raised-base border-border-subtle"
    case "completed":
      return "text-icon-success-base bg-surface-base border-border-base"
    case "canceled":
      return "text-icon-critical-base bg-surface-critical-weak border-border-base"
    case "archived":
      return "text-text-muted bg-surface-base border-border-subtle"
  }
}
