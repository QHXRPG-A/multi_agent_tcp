import { afterEach, beforeEach, describe, expect, test } from "bun:test"
import {
  applyMobileTickToData,
  createMobileTickGuard,
  createMobilePlanningRequest,
  deleteMobileDesktopSession,
  loadMobileCollaborationData,
  loadMobileTick,
  loginMobileCollaboration,
  logoutMobileCollaboration,
  serverStateToMobile,
  sendMobileAgentMessage,
  sendMobileDesktopMessage,
} from "./mobile-api"
import { flushMobileLogs, getMobileLogs, logMobileEvent, resetMobileLoggerForTests } from "./mobile-logger"

const project = { id: "proj-1", name: "Project One" }

const status = {
  run: {
    id: "run-1",
    projectId: "proj-1",
    blueprintId: "default",
    title: "Runtime Run",
    status: "running",
    updatedAt: "2026-05-28T09:48:00Z",
    currentNodeIds: ["coder"],
  },
  blueprint: {
    nodes: [
      { id: "planner", label: "Planner", state: "completed", x: 120, y: 240, upstreamNodeIds: [], downstreamNodeIds: ["coder"] },
      { id: "coder", label: "Coder", state: "running", x: 120, y: 384, upstreamNodeIds: ["planner"], downstreamNodeIds: [] },
    ],
    edges: [{ source: "planner", target: "coder", kind: "exec" }],
  },
  agents: [
    {
      nodeId: "planner",
      agentId: "Planner",
      cliKind: "codex",
      state: "completed",
      taskStatus: "done",
      queueSize: 0,
      messagesSent: 1,
      busyCount: 0,
      updatedAt: "2026-05-28T09:44:00Z",
      recentEvents: [],
    },
    {
      nodeId: "coder",
      agentId: "Coder",
      cliKind: "codex",
      state: "running",
      taskStatus: "running",
      queueSize: 1,
      messagesSent: 3,
      busyCount: 1,
      updatedAt: "2026-05-28T09:48:00Z",
      recentEvents: [],
    },
  ],
}

const diff = {
  total: 1,
  accepted: 1,
  conflict: 0,
  rejected: 0,
  pending: 0,
  files: 1,
  additions: 3,
  deletions: 1,
  changesets: [{ id: "chg-1", status: "accepted", summary: "Edited app", files: ["src/app.ts"] }],
}

const events = [
  {
    cursor: "1",
    type: "agent.status",
    occurredAt: "2026-05-28T09:48:00Z",
    nodeId: "coder",
    agentId: "Coder",
    payload: { message: "Coder running" },
  },
]

describe("mobile collaboration API projection", () => {
  beforeEach(() => {
    resetMobileLoggerForTests()
  })

  afterEach(() => {
    resetMobileLoggerForTests()
  })

  test("converts server status into the existing display shape", () => {
    const data = serverStateToMobile(project, status, diff, events, {
      csrfToken: "csrf-1",
      projectId: "proj-1",
      runId: "run-1",
      capabilities: ["run:create", "run:message"],
      planningRequests: [],
    })
    expect(data.blueprint.title).toBe("Runtime Run")
    expect(data.blueprint.nodes.map((node) => node.state)).toEqual(["done", "running"])
    expect(data.blueprint.nodes[0]?.layout).toEqual({ x: 120, y: 240 })
    expect(data.blueprint.edges).toEqual([{ source: "planner", target: "coder", kind: "exec" }])
    expect(data.blueprint.run.currentNode).toBe("Coder")
    expect(data.blueprint.diff.fileCount).toBe(1)
    expect(data.blueprint.diff.files[0]?.path).toBe("src/app.ts")
    expect(data.blueprint.diff.files[0]?.changesetId).toBe("chg-1")
    expect(data.server?.csrfToken).toBe("csrf-1")
    expect(data.messages[0]?.body).toBe("Coder running")
  })

  test("keeps backend blueprint structure authoritative when no edges are present", () => {
    const data = serverStateToMobile(
      project,
      {
        ...status,
        blueprint: {
          nodes: [
            { id: "agent-1", label: "Agent 1", state: "idle", x: 120, y: 120, upstreamNodeIds: [], downstreamNodeIds: [] },
            { id: "agent-2", label: "Agent 2", state: "idle", x: 120, y: 264, upstreamNodeIds: [], downstreamNodeIds: [] },
          ],
          edges: [],
        },
        agents: [],
      },
      undefined,
      [],
      { csrfToken: "csrf-1", capabilities: [], planningRequests: [] },
    )

    expect(data.blueprint.nodes.map((node) => node.layout)).toEqual([
      { x: 120, y: 120 },
      { x: 120, y: 264 },
    ])
    expect(data.blueprint.edges).toEqual([])
  })

  test("projects full desktop blueprint nodes and edge ports", () => {
    const data = serverStateToMobile(
      project,
      {
        ...status,
        blueprint: {
          nodes: [
            {
              id: "agent-1",
              label: "Agent 1",
              kind: "worker_agent",
              state: "running",
              x: 96,
              y: 120,
              upstreamNodeIds: [],
              downstreamNodeIds: ["script-1"],
            },
            {
              id: "script-1",
              label: "Format Result",
              kind: "script",
              role: "Script Function",
              state: "idle",
              summary: "format_result(payload: dict) -> {summary: str}",
              x: 280,
              y: 120,
              upstreamNodeIds: ["agent-1"],
              downstreamNodeIds: ["branch-1"],
              inputPorts: ["payload: dict"],
              outputPorts: ["summary: str"],
            },
            {
              id: "branch-1",
              label: "Branch",
              kind: "branch",
              state: "idle",
              x: 464,
              y: 120,
              upstreamNodeIds: ["script-1"],
              downstreamNodeIds: ["agent-2"],
              inputPorts: ["condition: bool"],
              outputPorts: ["true: message", "false: message"],
            },
            {
              id: "tick-1",
              label: "Tick",
              kind: "tick",
              state: "idle",
              x: 96,
              y: 264,
              upstreamNodeIds: [],
              downstreamNodeIds: ["agent-1"],
              outputPorts: ["tick: tick"],
              everyNSeconds: 3,
            },
          ],
          edges: [
            { source: "agent-1", target: "script-1", kind: "data", outputPort: "out", inputPort: "payload" },
            { source: "script-1", target: "branch-1", kind: "data", outputPort: "summary", inputPort: "condition" },
            { source: "tick-1", target: "agent-1", kind: "data", outputPort: "tick", inputPort: "in" },
          ],
        },
        agents: [
          {
            nodeId: "agent-1",
            agentId: "Agent 1",
            cliKind: "codex",
            state: "running",
            taskStatus: "running",
            queueSize: 1,
            messagesSent: 2,
            busyCount: 1,
            updatedAt: "2026-05-28T09:48:00Z",
            recentEvents: [],
          },
        ],
      },
      undefined,
      [],
      { csrfToken: "csrf-1", capabilities: [], planningRequests: [] },
    )

    expect(data.blueprint.nodes.map((node) => node.kind)).toEqual(["worker_agent", "script", "branch", "tick"])
    expect(data.blueprint.nodes.find((node) => node.id === "script-1")?.summary).toContain("format_result")
    expect(data.blueprint.nodes.find((node) => node.id === "branch-1")?.outputPorts).toContain("true: message")
    expect(data.blueprint.nodes.find((node) => node.id === "tick-1")?.everyNSeconds).toBe(3)
    expect(data.blueprint.edges[0]).toEqual({
      source: "agent-1",
      target: "script-1",
      kind: "data",
      outputPort: "out",
      inputPort: "payload",
    })
  })

  test("recovers typed nodes from legacy desktop snapshots", () => {
    const data = serverStateToMobile(
      project,
      {
        ...status,
        blueprint: {
          nodes: [
            {
              id: "agent-3",
              label: "agent-agent-3",
              kind: "worker_agent",
              role: "Agent",
              state: "idle",
              upstreamNodeIds: [],
              downstreamNodeIds: [],
            },
            {
              id: "branch-1",
              label: "Branch",
              kind: "worker_agent",
              state: "idle",
              upstreamNodeIds: [],
              downstreamNodeIds: [],
              inputPorts: ["condition: bool"],
              outputPorts: ["true: message", "false: message"],
            },
            {
              id: "tick-1",
              label: "Tick",
              kind: "worker_agent",
              state: "idle",
              upstreamNodeIds: [],
              downstreamNodeIds: [],
              outputPorts: ["tick: tick"],
              everyNSeconds: 3,
            },
          ],
          edges: [],
        },
        agents: [],
      },
      undefined,
      [],
      { csrfToken: "csrf-1", capabilities: [], planningRequests: [] },
    )

    expect(data.blueprint.nodes.map((node) => node.kind)).toEqual(["agent", "branch", "tick"])
  })

  test("loads /mobile data through the read-only API sequence", async () => {
    const calls: string[] = []
    const fetcher = async (input: RequestInfo | URL) => {
      const path = String(input)
      calls.push(path)
      if (path === "/api/me") return json({ ok: true, csrfToken: "csrf-1" })
      if (path === "/api/projects")
        return json({ projects: [{ ...project, capabilities: ["run:create", "run:message"], latestRun: status.run }] })
      if (path === "/api/projects/proj-1/planning-requests")
        return json({
          planningRequests: [
            {
              id: "pln-1",
              projectId: "proj-1",
              blueprintId: "default",
              goal: "mobile goal",
              status: "pending_desktop",
            },
          ],
        })
      if (path === "/api/mobile/desktop-sessions")
        return json({
          desktop: { online: true, stale: false, updatedAt: "2026-05-29T00:00:00Z" },
          activeSessionId: "desktop-session-1",
          sessions: [{ id: "desktop-session-1", title: "Desktop Chat", messageCount: 2 }],
          composer: {
            modes: [
              { id: "Build", label: "Build", kind: "agent" },
              { id: "blueprintPlanning", label: "蓝图规划", kind: "blueprintPlanning" },
            ],
            activeModeId: "Build",
          },
          currentMessages: [
            { id: "desktop-msg-1", role: "user", label: "User", body: "from desktop user", createdAt: "2026-05-29T00:00:00Z" },
            {
              id: "desktop-msg-2",
              role: "assistant",
              label: "Assistant",
              body: "from desktop assistant",
              createdAt: "2026-05-29T00:00:01Z",
              segments: [
                { id: "seg-1", type: "text", body: "from desktop assistant" },
                { id: "seg-2", type: "reasoning", title: "思考过程", body: "checking context" },
                { id: "seg-3", type: "tool", title: "工具调用 · read", toolName: "read", status: "completed", body: "Output\nok" },
              ],
            },
            { id: "desktop-msg-3", role: "assistant", label: "Assistant", body: "[reasoning]", createdAt: "2026-05-29T00:00:02Z" },
          ],
        })
      if (path === "/api/runs/run-1/status") return json({ status })
      if (path === "/api/runs/run-1/diff") return json({ diff })
      if (path === "/api/runs/run-1/events?cursor=0") return json({ events })
      if (path === "/api/client-logs") return json({ ok: true, accepted: 1 })
      return json({ ok: false, code: "NOT_FOUND", message: path }, 404)
    }

    const result = await loadMobileCollaborationData(fetcher as unknown as typeof fetch)
    expect(result.source).toBe("api")
    expect(result.status).toBe("ready")
    expect(result.data.blueprint.nodes).toHaveLength(2)
    expect(result.data.messages.map((message) => message.body)).toEqual(["from desktop user", "from desktop assistant", ""])
    expect(result.data.messages[1]?.segments?.map((segment) => segment.type)).toEqual(["text", "reasoning", "tool"])
    expect(result.data.messages[2]?.segments?.[0]?.type).toBe("reasoning")
    expect(result.data.server?.desktopSessions?.currentMessages[1]?.segments?.[2]?.toolName).toBe("read")
    expect(result.data.server?.desktopSessions?.activeSessionId).toBe("desktop-session-1")
    expect(result.data.server?.desktopSessions?.composer?.activeModeId).toBe("Build")
    expect(result.data.server?.desktopSessions?.composer?.modes.map((mode) => mode.label)).toEqual(["Build", "蓝图规划"])
    expect(result.data.server?.planningRequests[0]?.id).toBe("pln-1")
    expect(calls).toContain("/api/me")
    expect(calls).toContain("/api/projects")
    expect(calls).toContain("/api/projects/proj-1/planning-requests")
    expect(getMobileLogs().some((entry) => entry.event === "mobile.load.success")).toBe(true)
    expect(await flushMobileLogs(fetcher as unknown as typeof fetch)).toBeGreaterThan(0)
    expect(calls).toContain("/api/client-logs")
  })

  test("keeps mock fallback when login is required", async () => {
    const fetcher = async () => json({ ok: false, code: "UNAUTHORIZED", message: "login required" }, 401)
    const result = await loadMobileCollaborationData(fetcher as unknown as typeof fetch)
    expect(result.source).toBe("mock")
    expect(result.status).toBe("logged-out")
    expect(result.message).toBe("Login required")
    expect(getMobileLogs().some((entry) => entry.event === "mobile.api.fallback")).toBe(true)
  })

  test("keeps initial load in waiting-peer state when desktop is not online", async () => {
    const calls: string[] = []
    const fetcher = async (input: RequestInfo | URL) => {
      const path = String(input)
      calls.push(path)
      if (path === "/api/me") {
        return json({
          ok: true,
          csrfToken: "csrf-1",
          clients: { mobile: true, desktop: false },
          syncReady: false,
        })
      }
      return json({ ok: false, code: "NOT_FOUND", message: path }, 404)
    }

    const result = await loadMobileCollaborationData(fetcher as unknown as typeof fetch)

    expect(result.source).toBe("api")
    expect(result.status).toBe("waiting-peer")
    expect(result.data.server?.syncReady).toBe(false)
    expect(result.data.server?.clients).toEqual({ mobile: true, desktop: false })
    expect(calls).toEqual(["/api/me"])
  })

  test("keeps API state when no run is available and the runtime bridge is offline", async () => {
    const calls: string[] = []
    const fetcher = async (input: RequestInfo | URL) => {
      const path = String(input)
      calls.push(path)
      if (path === "/api/me") return json({ ok: true, csrfToken: "csrf-1" })
      if (path === "/api/projects")
        return json({ projects: [{ ...project, capabilities: ["run:create"], latestRun: null }] })
      if (path === "/api/projects/proj-1/runs")
        return json({ ok: false, code: "RUNTIME_UNAVAILABLE", message: "runtime binding is not configured" }, 503)
      if (path === "/api/projects/proj-1/planning-requests") return json({ planningRequests: [] })
      if (path === "/api/client-logs") return json({ ok: true, accepted: 1 })
      return json({ ok: false, code: "NOT_FOUND", message: path }, 404)
    }

    const result = await loadMobileCollaborationData(fetcher as unknown as typeof fetch)

    expect(result.source).toBe("api")
    expect(result.status).toBe("empty")
    expect(result.message).toBe("No blueprint run")
    expect(result.data.server?.csrfToken).toBe("csrf-1")
    expect(result.data.server?.capabilities).toContain("run:create")
    expect(calls).toContain("/api/projects/proj-1/runs")
  })

  test("keeps mobile logs local and sanitized when upload fails", async () => {
    const fetcher = async () => json({ ok: false }, 503)
    logMobileEvent(
      "error",
      "mobile.api.failure",
      "failed with token desktop-secret",
      { bridgeToken: "desktop-secret", path: "C:\\secret\\project\\file.ts" },
      { fetcher: fetcher as unknown as typeof fetch },
    )

    expect(await flushMobileLogs(fetcher as unknown as typeof fetch)).toBe(0)
    const text = JSON.stringify(getMobileLogs())
    expect(text).toContain("mobile.api.failure")
    expect(text).not.toContain("desktop-secret")
    expect(text).not.toContain("C:\\secret\\project")
  })

  test("posts mobile write actions with credentials and CSRF", async () => {
    const requests: Array<{ path: string; init?: RequestInit }> = []
    const fetcher = async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ path: String(input), init })
      return json({ ok: true, planningRequest: { id: "pln-1" }, result: { queued: true } })
    }
    const server = {
      csrfToken: "csrf-1",
      projectId: "proj-1",
      runId: "run-1",
      capabilities: ["run:create", "run:message"],
      planningRequests: [],
    }

    await createMobilePlanningRequest(server, "plan from phone", fetcher as unknown as typeof fetch)
    await sendMobileAgentMessage(server, "coder", "continue", "top", fetcher as unknown as typeof fetch)
    await sendMobileDesktopMessage(
      server,
      "ask desktop",
      { promptMode: "normal", agentName: "Build" },
      fetcher as unknown as typeof fetch,
    )
    await deleteMobileDesktopSession(server, "session-1", fetcher as unknown as typeof fetch)

    expect(requests[0]?.path).toBe("/api/projects/proj-1/planning-requests")
    expect(requests[0]?.init?.method).toBe("POST")
    expect(requests[0]?.init?.credentials).toBe("include")
    expect((requests[0]?.init?.headers as Record<string, string>)["x-csrf-token"]).toBe("csrf-1")
    expect(requests[0]?.init?.body).toBe(JSON.stringify({ goal: "plan from phone" }))
    expect(requests[1]?.path).toBe("/api/runs/run-1/messages")
    expect(requests[1]?.init?.body).toBe(JSON.stringify({ nodeId: "coder", text: "continue", mode: "top" }))
    expect(requests[2]?.path).toBe("/api/mobile/desktop-submit")
    expect(requests[2]?.init?.body).toBe(JSON.stringify({ text: "ask desktop", promptMode: "normal", agentName: "Build" }))
    expect(requests[3]?.path).toBe("/api/mobile/desktop-session-delete")
    expect(requests[3]?.init?.body).toBe(JSON.stringify({ sessionId: "session-1" }))
  })

  test("logs in through the Collaboration Server with cookie credentials", async () => {
    const requests: Array<{ path: string; init?: RequestInit }> = []
    const fetcher = async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ path: String(input), init })
      return json({ ok: true, csrfToken: "csrf-login" })
    }

    const result = await loginMobileCollaboration("debug", "debug-pass-123", "mobile", fetcher as unknown as typeof fetch)

    expect(result.csrfToken).toBe("csrf-login")
    expect(requests[0]?.path).toBe("/api/auth/login")
    expect(requests[0]?.init?.method).toBe("POST")
    expect(requests[0]?.init?.credentials).toBe("include")
    expect(requests[0]?.init?.body).toBe(
      JSON.stringify({ username: "debug", password: "debug-pass-123", clientKind: "mobile" }),
    )
  })

  test("logs out through the Collaboration Server with cookie credentials", async () => {
    const requests: Array<{ path: string; init?: RequestInit }> = []
    const fetcher = async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ path: String(input), init })
      return json({ ok: true })
    }

    const result = await logoutMobileCollaboration(fetcher as unknown as typeof fetch)

    expect(result.ok).toBe(true)
    expect(requests[0]?.path).toBe("/api/auth/logout")
    expect(requests[0]?.init?.method).toBe("POST")
    expect(requests[0]?.init?.credentials).toBe("include")
  })

  test("loads mobile tick through the narrow polling endpoint", async () => {
    const requests: Array<{ path: string; init?: RequestInit }> = []
    const fetcher = async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ path: String(input), init })
      return json({
        ok: true,
        csrfToken: "csrf-1",
        clients: { mobile: true, desktop: true },
        syncReady: true,
        project,
        run: status.run,
        status,
      })
    }

    const tick = await loadMobileTick(fetcher as unknown as typeof fetch)

    expect(tick.syncReady).toBe(true)
    expect(tick.status?.blueprint.nodes).toHaveLength(2)
    expect(requests[0]?.path).toBe("/api/mobile/tick")
    expect(requests[0]?.init?.method).toBe("GET")
    expect(requests[0]?.init?.credentials).toBe("include")
  })

  test("skips overlapping mobile tick executions", async () => {
    let executions = 0
    const releases: Array<() => void> = []
    const guarded = createMobileTickGuard(
      () =>
        new Promise<void>((resolve) => {
          executions += 1
          releases.push(resolve)
        }),
    )

    const first = guarded()
    const second = await guarded()
    releases.shift()?.()
    const firstResult = await first
    const third = guarded()
    releases.shift()?.()
    const thirdResult = await third

    expect(second).toBe(false)
    expect(firstResult).toBe(true)
    expect(thirdResult).toBe(true)
    expect(executions).toBe(2)
  })

  test("does not update blueprint run state while syncReady is false", () => {
    const current = serverStateToMobile(project, status, diff, events, {
      csrfToken: "csrf-old",
      projectId: "proj-1",
      runId: "run-1",
      clients: { mobile: true, desktop: false },
      syncReady: false,
      capabilities: ["run:create"],
      planningRequests: [{ id: "pln-1", projectId: "proj-1", blueprintId: "default", goal: "keep me", status: "pending_desktop" }],
    })

    const next = applyMobileTickToData(current, {
      ok: true,
      csrfToken: "csrf-new",
      clients: { mobile: true, desktop: false },
      syncReady: false,
      project: { ...project, capabilities: [] },
      run: { ...status.run, status: "completed" },
      status: {
        ...status,
        blueprint: { nodes: [{ id: "review", label: "Review", state: "running" }], edges: [] },
      },
    })

    expect(next.blueprint.nodes.map((node) => node.id)).toEqual(["planner", "coder"])
    expect(next.server?.csrfToken).toBe("csrf-new")
    expect(next.server?.syncReady).toBe(false)
    expect(next.server?.planningRequests[0]?.id).toBe("pln-1")
  })

  test("clears waiting placeholder when syncReady true but no run is available", () => {
    const current = {
      ...serverStateToMobile(project, status, diff, [], {
        csrfToken: "csrf-old",
        clients: { mobile: true, desktop: false },
        syncReady: false,
        capabilities: [],
        planningRequests: [],
      }),
      messages: [
        {
          id: "mobile-empty",
          speaker: "top-agent" as const,
          label: "Collaboration Server",
          body: "Waiting for desktop login",
          time: "--",
        },
      ],
    }

    const next = applyMobileTickToData(current, {
      ok: true,
      csrfToken: "csrf-new",
      clients: { mobile: true, desktop: true },
      syncReady: true,
      project,
      run: null,
      status: null,
    })

    expect(next.messages[0]?.body).toBe("No blueprint run")
    expect(next.blueprint.nodes).toEqual([])
    expect(next.blueprint.edges).toEqual([])
    expect(next.blueprint.diff.fileCount).toBe(0)
    expect(next.server?.runId).toBeUndefined()
    expect(next.server?.syncReady).toBe(true)
  })

  test("shows desktop chat messages from tick when no blueprint run is available", () => {
    const current = {
      ...serverStateToMobile(project, status, diff, [], {
        csrfToken: "csrf-old",
        clients: { mobile: true, desktop: true },
        syncReady: true,
        capabilities: [],
        planningRequests: [],
      }),
      messages: [
        {
          id: "mobile-empty",
          speaker: "top-agent" as const,
          label: "Collaboration Server",
          body: "Default Blueprint is unknown.",
          time: "--",
        },
      ],
    }

    const next = applyMobileTickToData(current, {
      ok: true,
      csrfToken: "csrf-new",
      clients: { mobile: true, desktop: true },
      syncReady: true,
      project,
      run: null,
      status: null,
      desktopSessions: {
        desktop: { online: true, loggedIn: true, stale: false, updatedAt: "2026-05-29T00:00:00Z" },
        activeSessionId: "desktop-session-1",
        sessions: [{ id: "desktop-session-1", title: "问候", messageCount: 2 }],
        currentMessages: [
          { id: "desktop-msg-1", role: "user", label: "User", body: "您好", createdAt: "2026-05-29T00:00:00Z" },
          { id: "desktop-msg-2", role: "assistant", label: "Assistant", body: "你好！有什么我可以帮你的吗？", createdAt: "2026-05-29T00:00:01Z" },
        ],
      },
    })

    expect(next.messages.map((message) => message.body)).toEqual(["您好", "你好！有什么我可以帮你的吗？"])
    expect(next.server?.desktopSessions?.sessions[0]?.title).toBe("问候")
  })

  test("uses desktop blueprint snapshot status when syncReady true but no live run exists", () => {
    const current = serverStateToMobile(project, status, diff, events, {
      csrfToken: "csrf-old",
      runId: "run-old",
      capabilities: ["run:create"],
      planningRequests: [],
    })

    const next = applyMobileTickToData(current, {
      ok: true,
      csrfToken: "csrf-new",
      clients: { mobile: true, desktop: true },
      syncReady: true,
      project,
      run: null,
      status: {
        run: {
          id: "",
          projectId: "proj-1",
          blueprintId: "default",
          title: "当前蓝图",
          status: "unknown",
          updatedAt: "2026-05-28T10:01:00Z",
          currentNodeIds: [],
        },
        blueprint: {
          nodes: [
            { id: "agent-a", label: "测试节点 A", state: "idle", x: 96, y: 144, upstreamNodeIds: [], downstreamNodeIds: ["agent-b"] },
            { id: "agent-b", label: "测试节点 B", state: "idle", x: 96, y: 288, upstreamNodeIds: ["agent-a"], downstreamNodeIds: [] },
          ],
          edges: [{ source: "agent-a", target: "agent-b", kind: "exec" }],
        },
        agents: [
          {
            nodeId: "agent-a",
            agentId: "测试节点 A",
            cliKind: "codex",
            state: "idle",
            taskStatus: "idle",
            queueSize: 0,
            messagesSent: 0,
            busyCount: 0,
            updatedAt: "2026-05-28T10:01:00Z",
          },
        ],
      },
    })

    expect(next.blueprint.nodes.map((node) => node.label)).toEqual(["测试节点 A", "测试节点 B"])
    expect(next.blueprint.nodes[0]?.state).toBe("idle")
    expect(next.blueprint.nodes[0]?.layout).toEqual({ x: 96, y: 144 })
    expect(next.blueprint.edges).toEqual([{ source: "agent-a", target: "agent-b", kind: "exec" }])
    expect(next.blueprint.run.label).toBe("未运行")
    expect(next.server?.runId).toBeUndefined()
  })

  test("replaces blueprint nodes, edges, and agent status from syncReady tick payload", () => {
    const current = serverStateToMobile(project, status, diff, events, {
      csrfToken: "csrf-1",
      projectId: "proj-1",
      runId: "run-1",
      capabilities: ["run:create"],
      planningRequests: [{ id: "pln-1", projectId: "proj-1", blueprintId: "default", goal: "keep me", status: "pending_desktop" }],
    })
    const nextStatus = {
      ...status,
      run: { ...status.run, status: "running", updatedAt: "2026-05-28T09:50:00Z" },
      blueprint: {
        nodes: [
          { id: "planner", label: "Planner Prime", state: "completed", upstreamNodeIds: [], downstreamNodeIds: ["review"] },
          { id: "review", label: "Reviewer", state: "running", upstreamNodeIds: ["planner"], downstreamNodeIds: [] },
        ],
        edges: [{ source: "planner", target: "review", kind: "data" }],
      },
      agents: [
        {
          nodeId: "planner",
          agentId: "Planner Prime",
          cliKind: "codex",
          state: "completed",
          taskStatus: "done",
          queueSize: 0,
          messagesSent: 2,
          busyCount: 0,
          updatedAt: "2026-05-28T09:49:00Z",
        },
        {
          nodeId: "review",
          agentId: "Reviewer",
          cliKind: "codex",
          state: "running",
          taskStatus: "reviewing",
          queueSize: 2,
          messagesSent: 4,
          busyCount: 1,
          updatedAt: "2026-05-28T09:50:00Z",
        },
      ],
    }

    const next = applyMobileTickToData(current, {
      ok: true,
      csrfToken: "csrf-2",
      clients: { mobile: true, desktop: true },
      syncReady: true,
      project: { ...project, capabilities: ["run:create", "run:message"] },
      run: nextStatus.run,
      status: nextStatus,
    })

    expect(next.blueprint.nodes.map((node) => node.id)).toEqual(["planner", "review"])
    expect(next.blueprint.nodes[0]?.label).toBe("Planner Prime")
    expect(next.blueprint.nodes[1]?.agentPanel.taskStatus).toBe("reviewing")
    expect(next.blueprint.edges).toEqual([{ source: "planner", target: "review", kind: "data" }])
    expect(next.blueprint.diff).toEqual(current.blueprint.diff)
    expect(next.messages).toEqual(current.messages)
    expect(next.server?.planningRequests[0]?.id).toBe("pln-1")
    expect(next.server?.capabilities).toEqual(["run:create", "run:message"])
    expect(next.server?.syncReady).toBe(true)
  })

  test("refreshes desktop chat messages from tick even after the placeholder was replaced", () => {
    const current = {
      ...serverStateToMobile(project, status, diff, events, {
        csrfToken: "csrf-1",
        projectId: "proj-1",
        runId: "run-1",
        clients: { mobile: true, desktop: true },
        syncReady: true,
        capabilities: [],
        planningRequests: [],
      }),
      messages: [
        {
          id: "desktop-old",
          speaker: "top-agent" as const,
          label: "Assistant",
          body: "旧消息",
          time: "00:00",
        },
      ],
    }

    const next = applyMobileTickToData(current, {
      ok: true,
      csrfToken: "csrf-2",
      clients: { mobile: true, desktop: true },
      syncReady: true,
      project,
      run: status.run,
      status,
      desktopSessions: {
        desktop: { online: true, loggedIn: true, stale: false, updatedAt: "2026-05-29T00:00:02Z" },
        activeSessionId: "desktop-session-1",
        sessions: [{ id: "desktop-session-1", title: "问候", messageCount: 2 }],
        currentMessages: [
          { id: "desktop-msg-1", role: "user", label: "User", body: "您好", createdAt: "2026-05-29T00:00:00Z" },
          { id: "desktop-msg-2", role: "assistant", label: "Assistant", body: "你好！有什么我可以帮你的吗？", createdAt: "2026-05-29T00:00:01Z" },
        ],
      },
    })

    expect(next.messages.map((message) => message.body)).toEqual(["您好", "你好！有什么我可以帮你的吗？"])
  })
})

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  })
}
