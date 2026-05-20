import { afterAll, beforeAll, describe, expect, mock, test } from "bun:test"
import { readdir, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"

type Handler = (_event: unknown, ...args: unknown[]) => unknown

const handlers = new Map<string, Handler>()
const testLogDir = join(tmpdir(), "gulicode-ipc-blueprint-runtime-test")
const testLogPath = join(testLogDir, "main.log")

beforeAll(() => {
  mock.module("electron-log/main.js", () => ({
    default: {
      transports: {
        file: {
          getFile: () => ({ path: testLogPath }),
        },
      },
    },
  }))
  mock.module("./windows", () => ({
    setTitlebar: () => {},
  }))
  mock.module("./store", () => ({
    getStore: () => ({
      get: () => undefined,
      set: () => {},
      delete: () => {},
      clear: () => {},
      store: {},
    }),
  }))

  const electron = {
    ipcMain: {
      handle: (channel: string, handler: Handler) => handlers.set(channel, handler),
      on: () => {},
    },
    app: {
      isPackaged: false,
      getPath: () => testLogDir,
      relaunch: () => {},
      exit: () => {},
    },
    BrowserWindow: {
      getAllWindows: () => [],
      fromWebContents: () => undefined,
    },
    Notification: class {
      show() {}
    },
    clipboard: {
      readImage: () => ({
        isEmpty: () => true,
      }),
    },
    dialog: {
      showOpenDialog: async () => ({ canceled: true, filePaths: [] }),
      showSaveDialog: async () => ({ canceled: true }),
    },
    shell: {
      openExternal: () => {},
      openPath: async () => "",
    },
  }
  mock.module("electron", () => ({
    ...electron,
    default: electron,
  }))
})

afterAll(async () => {
  await rm(testLogDir, { recursive: true, force: true })
})

describe("blueprint runtime IPC handlers", () => {
  test("route renderer blueprint calls to the runtime facade", async () => {
    const calls: string[] = []
    const blueprintRuntime = {
      list: (projectDir: string) => {
        calls.push(`list:${projectDir}`)
        return ["listed"]
      },
      open: (projectDir: string, blueprintId: string) => {
        calls.push(`open:${projectDir}:${blueprintId}`)
        return { id: blueprintId }
      },
      save: (projectDir: string, document: { id: string }) => {
        calls.push(`save:${projectDir}:${document.id}`)
        return document
      },
      relocateProjectWorkdir: (
        projectDir: string,
        blueprintId: string,
        document: { id: string },
        targetProjectWorkdir: string,
        conflictPolicy?: string,
      ) => {
        calls.push(`relocate:${projectDir}:${blueprintId}:${document.id}:${targetProjectWorkdir}:${conflictPolicy ?? ""}`)
        return { ok: true, changed: true, targetProjectDir: targetProjectWorkdir, document }
      },
      validate: (projectDir: string, blueprintId: string, document?: { id: string }) => {
        calls.push(`validate:${projectDir}:${blueprintId}:${document?.id ?? ""}`)
        return { ok: true, errors: [], warnings: [] }
      },
      listRuns: (projectDir?: string, blueprintId?: string) => {
        calls.push(`runs:${projectDir}:${blueprintId}`)
        return [{ runId: "run-1" }]
      },
      detectPython: (projectDir?: string, pythonCommand?: string) => {
        calls.push(`detect-python:${projectDir}:${pythonCommand ?? ""}`)
        return { ok: true, pythonCommand: "C:\\Python\\python.exe" }
      },
      configure: (opts?: { pythonCommand?: string }) => {
        calls.push(`configure:${opts?.pythonCommand ?? ""}`)
        return { ok: true }
      },
      start: (projectDir: string, blueprintId: string, plan: Record<string, unknown>, executionMode?: string) => {
        calls.push(`start:${projectDir}:${blueprintId}:${plan.goal}:${executionMode}`)
        return { code: "NOT_IMPLEMENTED_FOR_UI" }
      },
      status: (runId: string) => {
        calls.push(`status:${runId}`)
        return { code: "NOT_STARTED" }
      },
      end: (runId: string, action: string, reason?: string) => {
        calls.push(`end:${runId}:${action}:${reason}`)
        return { ok: false }
      },
      recentEvents: (runId: string, limit?: number) => {
        calls.push(`events:${runId}:${limit}`)
        return { events: [] }
      },
      agentInfo: (runId: string | undefined, nodeId: string) => {
        calls.push(`agent-info:${runId}:${nodeId}`)
        return { nodeId }
      },
      queueAgentMessage: (runId: string, nodeId: string, text: string, mode: string) => {
        calls.push(`agent-message:${runId}:${nodeId}:${text}:${mode}`)
        return { ok: true }
      },
      agentStreamToken: (runId: string, cursor?: number) => {
        calls.push(`agent-stream:${runId}:${cursor}`)
        return { wsUrl: "ws://localhost/agent" }
      },
    }
    const { registerIpcHandlers } = await import("./ipc")
    registerIpcHandlers({
      killSidecar: () => {},
      awaitInitialization: async () => ({ serverUrl: "http://localhost" }),
      getWindowConfig: () => ({ appId: "test" }),
      consumeInitialDeepLinks: () => [],
      getDefaultServerUrl: () => null,
      setDefaultServerUrl: () => {},
      getWslConfig: async () => ({ enabled: false }),
      setWslConfig: () => {},
      getDisplayBackend: async () => null,
      setDisplayBackend: () => {},
      parseMarkdown: (markdown: string) => markdown,
      checkAppExists: () => false,
      wslPath: async (path: string) => path,
      resolveAppPath: async () => null,
      loadingWindowComplete: () => {},
      runUpdater: () => {},
      checkUpdate: async () => ({ updateAvailable: false }),
      installUpdate: () => {},
      setBackgroundColor: () => {},
      blueprintRuntime,
    })

    await handlers.get("blueprint-list")?.({}, "C:\\repo")
    await handlers.get("blueprint-open")?.({}, "C:\\repo", "default")
    await handlers.get("blueprint-save")?.({}, "C:\\repo", { id: "default" })
    await handlers.get("blueprint-relocate-project-workdir")?.(
      {},
      "C:\\repo",
      "default",
      { id: "default" },
      "D:\\repo",
      "overwrite",
    )
    await handlers.get("blueprint-validate")?.({}, "C:\\repo", "default", { id: "default" })
    await handlers.get("blueprint-list-runs")?.({}, "C:\\repo", "default")
    await handlers.get("blueprint-detect-python")?.({}, "C:\\repo", "C:\\Candidate\\python.exe")
    await handlers.get("blueprint-configure-runtime")?.({}, "C:\\Python\\python.exe")
    await handlers.get("blueprint-start")?.({}, "C:\\repo", "default", { goal: "ship" }, "live")
    await handlers.get("blueprint-status")?.({}, "run-1")
    await handlers.get("blueprint-end")?.({}, "run-1", "cancel", "user")
    await handlers.get("blueprint-recent-events")?.({}, "run-1", 10)
    await handlers.get("blueprint-agent-info")?.({}, "run-1", "coder")
    await handlers.get("blueprint-queue-agent-message")?.({}, "run-1", "coder", "hello", "top")
    await handlers.get("blueprint-agent-stream-token")?.({}, "run-1", 18)
    const saved = (await handlers.get("blueprint-save-agent-panel-test")?.(
      {},
      { nodeId: "test-agent", streamEvents: [{ seq: 1 }] },
    )) as Record<string, unknown>
    await writeFile(join(testLogDir, "agent-info-panel-tests", "agent-panel-test-test-agent-legacy.json"), "{}", "utf8")
    const updated = (await handlers.get("blueprint-save-agent-panel-test")?.(
      {},
      {
        schema_version: 2,
        kind: "gulicode.blueprint.test_agent_messages",
        nodeId: "test-agent",
        jsonPath: saved.path,
        agentReplies: [],
        userMessages: [{ text: "hello", status: "sent" }],
        frameworkMessages: [],
      },
    )) as Record<string, unknown>
    const savedDocument = JSON.parse(await readFile(String(saved.path), "utf8")) as Record<string, unknown>
    const savedPayload = savedDocument.payload as Record<string, unknown>
    const testJsonFiles = await readdir(join(testLogDir, "agent-info-panel-tests"))

    expect(saved.ok).toBe(true)
    expect(String(saved.path)).toContain("agent-info-panel-tests")
    expect(String(saved.path).endsWith("agent-panel-test.json")).toBe(true)
    expect(updated.path).toBe(saved.path)
    expect(savedDocument.schema_version).toBe(2)
    expect(savedDocument.kind).toBe("gulicode.agent_info_panel_test")
    expect(savedDocument.path).toBe(saved.path)
    expect(savedPayload.schema_version).toBe(2)
    expect(savedPayload.kind).toBe("gulicode.blueprint.test_agent_messages")
    expect(JSON.stringify(savedDocument)).toContain("hello")
    expect(testJsonFiles).toEqual(["agent-panel-test.json"])
    expect(calls).toEqual([
      "list:C:\\repo",
      "open:C:\\repo:default",
      "save:C:\\repo:default",
      "relocate:C:\\repo:default:default:D:\\repo:overwrite",
      "validate:C:\\repo:default:default",
      "runs:C:\\repo:default",
      "detect-python:C:\\repo:C:\\Candidate\\python.exe",
      "configure:C:\\Python\\python.exe",
      "start:C:\\repo:default:ship:live",
      "status:run-1",
      "end:run-1:cancel:user",
      "events:run-1:10",
      "agent-info:run-1:coder",
      "agent-message:run-1:coder:hello:top",
      "agent-stream:run-1:18",
    ])
  })
})
