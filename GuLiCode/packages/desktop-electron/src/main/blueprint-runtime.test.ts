import { describe, expect, test } from "bun:test"
import { mkdtemp, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"

import { BlueprintRuntime, validateProjectDir } from "./blueprint-runtime"

const document = {
  schema_version: 1 as const,
  id: "default",
  name: "Default Blueprint",
  graph: {
    terminal_nodes: { start: "start", end: "end" },
    route_nodes: {},
    agent_nodes: {
      planner: {
        node_id: "planner",
        prompt: "Plan",
      },
    },
    edges: [
      { from: "start", to: "planner", edge_type: "exec" },
      { from: "planner", to: "end", edge_type: "exec" },
    ],
  },
  ui: {
    nodes: {},
    viewport: { x: 0, y: 0, zoom: 1 },
  },
}

const documentWithConfig = (projectDir: string) => ({
  ...document,
  ui: {
    ...document.ui,
    config: {
      python_path: join(projectDir, "python.exe"),
      project_workdir: projectDir,
      skill_dir: "",
      rule_dir: "",
    },
  },
})

const plan = {
  user_goal: "Ship the plan.",
  agent_descriptions: {
    planner: "Plans the work.",
  },
  start_nodes: ["planner"],
  tasks: {
    planner: {
      goal: "Plan the work.",
      expected_output: "A clear implementation plan.",
      acceptance: "The plan is actionable.",
    },
  },
  run_policy: {},
}

describe("blueprint runtime bridge", () => {
  test("validates project directories before calling Python", async () => {
    expect(() => validateProjectDir("relative")).toThrow("absolute")
  })

  test("stores the user configured Python command", () => {
    const runtime = new BlueprintRuntime()
    try {
      expect(runtime.configure({ pythonCommand: "C:\\Python\\python.exe" })).toEqual({
        ok: true,
        pythonCommand: "C:\\Python\\python.exe",
      })
      expect(runtime.configure({ pythonCommand: "" })).toEqual({
        ok: true,
        pythonCommand: null,
      })
    } finally {
      runtime.close()
    }
  })

  test("keeps a running service when configured Python is the active executable", () => {
    const runtime = new BlueprintRuntime()
    const detected = runtime.detectPython()
    expect(detected.ok).toBe(true)
    let killed = 0
    const ready = Promise.resolve({
      ok: true as const,
      url: "http://127.0.0.1:1/blueprint",
      token: "secret",
    })
    const internals = runtime as unknown as {
      child?: { kill: () => void }
      ready?: typeof ready
      activeLauncher?: { command: string; args: string[]; source: string; executable?: string }
    }
    internals.child = {
      kill: () => {
        killed += 1
      },
    }
    internals.ready = ready
    internals.activeLauncher = {
      command: "python",
      args: [],
      source: "PATH python",
      executable: String(detected.pythonCommand),
    }

    try {
      expect(runtime.configure({ pythonCommand: String(detected.pythonCommand) })).toEqual({
        ok: true,
        pythonCommand: String(detected.pythonCommand),
      })
      expect(killed).toBe(0)
      expect(internals.ready).toBe(ready)
    } finally {
      runtime.close()
    }
    expect(killed).toBe(1)
  })

  test("detects an absolute Python executable for common config autofill", () => {
    const runtime = new BlueprintRuntime()
    try {
      const detected = runtime.detectPython()
      expect(detected.ok).toBe(true)
      expect(String(detected.pythonCommand).toLowerCase()).toContain("python")
      expect(String(detected.source).length).toBeGreaterThan(0)
    } finally {
      runtime.close()
    }
  })

  test("manual detection can ignore a stale configured Python command", () => {
    const runtime = new BlueprintRuntime()
    try {
      runtime.configure({ pythonCommand: "Z:\\missing\\python.exe" })
      const detected = runtime.detectPython(undefined, "")
      expect(detected.ok).toBe(true)
      expect(String(detected.pythonCommand).toLowerCase()).toContain("python")
    } finally {
      runtime.close()
    }
  })

  test("round-trips documents through the desktop blueprint service", async () => {
    const projectDir = await mkdtemp(join(tmpdir(), "gulicode-blueprint-"))
    const runtime = new BlueprintRuntime()
    try {
      const saved = await runtime.save(projectDir, document)
      expect(saved.id).toBe("default")
      const alternateDocument = {
        ...document,
        id: "alternate",
        name: "Alternate Blueprint",
        graph: {
          ...document.graph,
          agent_nodes: {
            planner: {
              ...document.graph.agent_nodes.planner,
              prompt: "Alternate plan",
            },
          },
        },
      }
      const alternateSaved = await runtime.save(projectDir, alternateDocument)
      expect(alternateSaved.id).toBe("alternate")

      const listed = await runtime.list(projectDir)
      expect(listed.map((item: { id: string }) => item.id).sort()).toEqual(["alternate", "default"])

      const opened = await runtime.open(projectDir, "default")
      expect(opened.graph.agent_nodes.planner.prompt).toBe("Plan")
      const alternateOpened = await runtime.open(projectDir, "alternate")
      expect(alternateOpened.graph.agent_nodes.planner.prompt).toBe("Alternate plan")

      const validation = await runtime.validate(projectDir, "default", opened)
      expect(validation.ok).toBe(true)
    } finally {
      runtime.close()
      await rm(projectDir, { recursive: true, force: true })
    }
  })

  test("starts, polls, reads events, and ends a blueprint run", async () => {
    const projectDir = await mkdtemp(join(tmpdir(), "gulicode-blueprint-"))
    const runtime = new BlueprintRuntime()
    try {
      await runtime.save(projectDir, documentWithConfig(projectDir))
      await runtime.save(projectDir, {
        ...documentWithConfig(projectDir),
        id: "alternate",
        name: "Alternate Blueprint",
      })

      const started = (await runtime.start(projectDir, "default", plan)) as Record<string, unknown>
      const alternateStarted = (await runtime.start(projectDir, "alternate", plan)) as Record<string, unknown>
      expect(String(started.runId)).toStartWith("run-")
      expect(String(alternateStarted.runId)).toStartWith("run-")
      expect((started.validation as { ok: boolean }).ok).toBe(true)
      expect(((started.queuedMessages as Array<{ node_id: string }>)[0]).node_id).toBe("planner")

      const status = (await runtime.status(String(started.runId))) as Record<string, unknown>
      expect(((status.status as { run: { status: string } }).run).status).toBe("running")
      expect(((status.explanation as { pending: { queued_messages: number } }).pending).queued_messages).toBe(1)

      const runs = (await runtime.listRuns(projectDir, "default")) as Array<{ runId: string }>
      expect(runs.map((run) => run.runId)).toEqual([started.runId])
      const alternateRuns = (await runtime.listRuns(projectDir, "alternate")) as Array<{ runId: string }>
      expect(alternateRuns.map((run) => run.runId)).toEqual([alternateStarted.runId])

      const events = (await runtime.recentEvents(String(started.runId), 10)) as Record<string, unknown>
      expect(events.limit).toBe(10)
      expect((events.events as unknown[]).length).toBeGreaterThan(0)

      const agentInfo = (await runtime.agentInfo(String(started.runId), "planner")) as Record<string, unknown>
      expect((agentInfo.runtime as { state: string }).state).toBe("queued")
      await expect(runtime.queueAgentMessage(String(started.runId), "planner", "hello", "default")).rejects.toMatchObject({
        code: "RUN_NOT_LIVE",
      })
      await expect(runtime.agentStreamToken(String(started.runId), 0)).rejects.toMatchObject({
        code: "RUN_NOT_LIVE",
      })

      const ended = (await runtime.end(String(started.runId), "cancel", "user cancelled")) as Record<string, unknown>
      expect(((ended.end as { run_status: string }).run_status)).toBe("cancelled")
      expect(((ended.status as { run: { final_status: string } }).run).final_status).toBe("cancelled")
      await runtime.end(String(alternateStarted.runId), "cancel", "user cancelled")
    } finally {
      runtime.close()
      await rm(projectDir, { recursive: true, force: true })
    }
  })

  test("posts project workdir relocation requests to the desktop blueprint service", async () => {
    const sourceDir = await mkdtemp(join(tmpdir(), "gulicode-blueprint-source-"))
    const targetDir = await mkdtemp(join(tmpdir(), "gulicode-blueprint-target-"))
    const runtime = new BlueprintRuntime()
    const originalFetch = globalThis.fetch
    let captured: Record<string, unknown> | undefined
    try {
      ;(runtime as unknown as { ready: Promise<{ ok: true; url: string; token: string }> }).ready = Promise.resolve({
        ok: true,
        url: "http://127.0.0.1:1/blueprint",
        token: "secret",
      })
      globalThis.fetch = ((_: RequestInfo | URL, init?: RequestInit) => {
        captured = JSON.parse(String(init?.body)) as Record<string, unknown>
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ok: true,
              changed: true,
              projectDir: sourceDir,
              targetProjectDir: targetDir,
              document: documentWithConfig(targetDir),
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        )
      }) as typeof fetch

      const result = (await runtime.relocateProjectWorkdir(
        sourceDir,
        "default",
        documentWithConfig(sourceDir),
        targetDir,
        "overwrite",
      )) as Record<string, unknown>
      const args = captured?.args as Record<string, unknown>

      expect(captured?.command).toBe("blueprint.relocateProjectWorkdir")
      expect(args.projectDir).toBe(sourceDir)
      expect(args.blueprintId).toBe("default")
      expect(args.projectWorkdir).toBe(targetDir)
      expect(args.conflictPolicy).toBe("overwrite")
      expect(result.targetProjectDir).toBe(targetDir)
    } finally {
      globalThis.fetch = originalFetch
      runtime.close()
      await rm(sourceDir, { recursive: true, force: true })
      await rm(targetDir, { recursive: true, force: true })
    }
  })

  test("converts service error payloads into coded errors", async () => {
    const projectDir = await mkdtemp(join(tmpdir(), "gulicode-blueprint-"))
    const runtime = new BlueprintRuntime()
    const originalFetch = globalThis.fetch
    try {
      ;(runtime as unknown as { ready: Promise<{ ok: true; url: string; token: string }> }).ready = Promise.resolve({
        ok: true,
        url: "http://127.0.0.1:1/blueprint",
        token: "secret",
      })
      globalThis.fetch = (() =>
        Promise.resolve(
          new Response(JSON.stringify({ ok: false, code: "NOT_FOUND", error: "missing blueprint" }), {
            status: 404,
            headers: { "Content-Type": "application/json" },
          }),
        )) as typeof fetch

      await expect(runtime.open(projectDir, "default")).rejects.toMatchObject({
        code: "NOT_FOUND",
        message: "NOT_FOUND: missing blueprint",
      })
    } finally {
      globalThis.fetch = originalFetch
      runtime.close()
      await rm(projectDir, { recursive: true, force: true })
    }
  })

  test("includes service error details in thrown runtime errors", async () => {
    const projectDir = await mkdtemp(join(tmpdir(), "gulicode-blueprint-"))
    const runtime = new BlueprintRuntime()
    const originalFetch = globalThis.fetch
    try {
      ;(runtime as unknown as { ready: Promise<{ ok: true; url: string; token: string }> }).ready = Promise.resolve({
        ok: true,
        url: "http://127.0.0.1:1/blueprint",
        token: "secret",
      })
      globalThis.fetch = (() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              ok: false,
              code: "BLUEPRINT_PLANNING_CONTEXT_FAILED",
              error: "failed to prepare desktop blueprint planning context",
              details: { error: "project directory does not contain a default blueprint" },
            }),
            {
              status: 500,
              headers: { "Content-Type": "application/json" },
            },
          ),
        )) as typeof fetch

      await expect(runtime.ensurePlanningContext(projectDir, "default", "session-1")).rejects.toMatchObject({
        code: "BLUEPRINT_PLANNING_CONTEXT_FAILED",
        message:
          "BLUEPRINT_PLANNING_CONTEXT_FAILED: failed to prepare desktop blueprint planning context: project directory does not contain a default blueprint",
        details: { error: "project directory does not contain a default blueprint" },
      })
    } finally {
      globalThis.fetch = originalFetch
      runtime.close()
      await rm(projectDir, { recursive: true, force: true })
    }
  })
})
