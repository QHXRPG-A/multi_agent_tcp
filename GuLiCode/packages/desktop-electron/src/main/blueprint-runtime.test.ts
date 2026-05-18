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

  test("round-trips documents through the desktop blueprint service", async () => {
    const projectDir = await mkdtemp(join(tmpdir(), "gulicode-blueprint-"))
    const runtime = new BlueprintRuntime()
    try {
      const saved = await runtime.save(projectDir, document)
      expect(saved.id).toBe("default")

      const listed = await runtime.list(projectDir)
      expect(listed.map((item: { id: string }) => item.id)).toEqual(["default"])

      const opened = await runtime.open(projectDir, "default")
      expect(opened.graph.agent_nodes.planner.prompt).toBe("Plan")

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
      await runtime.save(projectDir, document)

      const started = (await runtime.start(projectDir, "default", plan)) as Record<string, unknown>
      expect(String(started.runId)).toStartWith("run-")
      expect((started.validation as { ok: boolean }).ok).toBe(true)
      expect(((started.queuedMessages as Array<{ node_id: string }>)[0]).node_id).toBe("planner")

      const status = (await runtime.status(String(started.runId))) as Record<string, unknown>
      expect(((status.status as { run: { status: string } }).run).status).toBe("running")
      expect(((status.explanation as { pending: { queued_messages: number } }).pending).queued_messages).toBe(1)

      const runs = (await runtime.listRuns(projectDir, "default")) as Array<{ runId: string }>
      expect(runs.map((run) => run.runId)).toEqual([started.runId])

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
    } finally {
      runtime.close()
      await rm(projectDir, { recursive: true, force: true })
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
})
