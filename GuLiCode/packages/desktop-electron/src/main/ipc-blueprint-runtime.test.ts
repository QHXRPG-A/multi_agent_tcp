import { afterAll, beforeAll, describe, expect, mock, test } from "bun:test"
import { mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises"
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
    openBlueprintWindow: () => {},
    dockBlueprintWindow: () => true,
    closeBlueprintWindow: () => true,
    getBlueprintWindowContext: () => null,
    findBlueprintMainWindow: () => null,
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
      showItemInFolder: () => {},
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
  test("exposes independent blueprint window IPC hooks", async () => {
    const ipcSource = await Bun.file(new URL("./ipc.ts", import.meta.url)).text()
    const preloadSource = await Bun.file(new URL("../preload/index.ts", import.meta.url)).text()
    const rendererSource = await Bun.file(new URL("../renderer/index.tsx", import.meta.url)).text()
    const windowsSource = await Bun.file(new URL("./windows.ts", import.meta.url)).text()

    expect(ipcSource).toContain('"blueprint-window-open"')
    expect(ipcSource).toContain('"blueprint-window-dock"')
    expect(ipcSource).toContain('"blueprint-window-close"')
    expect(ipcSource).toContain('"blueprint-window-submit-planning"')
    expect(ipcSource).toContain('"blueprint-run-diff"')
    expect(ipcSource).toContain('"blueprint-changeset-diff"')
    expect(ipcSource).toContain('"blueprint-rollback-changesets"')
    expect(ipcSource).toContain('"blueprint-restore-rollback"')
    expect(ipcSource).toContain('"blueprint-create-script-node"')
    expect(ipcSource).toContain('"blueprint-list-editors"')
    expect(ipcSource).toContain('"blueprint-open-script-in-editor"')
    expect(ipcSource).toContain("shell.openPath(scriptRoot)")
    expect(ipcSource).toContain("await launchEditor(editor, scriptRoot)")
    expect(ipcSource).toContain("windowsHide: false")
    expect(ipcSource).toContain("editorForegroundArgs")
    expect(preloadSource).toContain("openBlueprintWindow")
    expect(preloadSource).toContain("blueprintCreateScriptNode")
    expect(preloadSource).toContain("blueprintListEditors")
    expect(preloadSource).toContain("blueprintOpenScriptInEditor")
    expect(preloadSource).toContain("blueprintRunDiff")
    expect(preloadSource).toContain("blueprintChangesetDiff")
    expect(preloadSource).toContain("blueprintRollbackChangesets")
    expect(preloadSource).toContain("blueprintRestoreRollback")
    expect(rendererSource).toContain("typeof api.blueprintRunDiff")
    expect(rendererSource).toContain("typeof blueprintCreateScriptNode === \"function\"")
    expect(rendererSource).toContain("typeof blueprintListEditors === \"function\"")
    expect(rendererSource).toContain("typeof blueprintOpenScriptInEditor === \"function\"")
    expect(rendererSource).toContain("typeof api.blueprintChangesetDiff")
    expect(rendererSource).toContain("typeof api.blueprintRollbackChangesets")
    expect(rendererSource).toContain("typeof api.blueprintRestoreRollback")
    expect(preloadSource).toContain("onBlueprintWindowDock")
    expect(preloadSource).toContain("onBlueprintWindowPlanningSubmitRequest")
    expect(ipcSource).toContain('"reveal-path-in-file-manager"')
    expect(ipcSource).toContain("shell.showItemInFolder")
    expect(preloadSource).toContain("revealPathInFileManager")
    expect(windowsSource).toContain("new BrowserWindow")
    expect(windowsSource).toContain("blueprintWindowContexts")
    expect(windowsSource).toContain('"blueprint-window-dock-request"')
  })

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
      scriptNodes: (projectDir: string) => {
        calls.push(`script-nodes:${projectDir}`)
        return { ok: true, nodes: [] }
      },
      createScriptNode: (projectDir: string, name: string, description?: string) => {
        calls.push(`script-create:${projectDir}:${name}:${description ?? ""}`)
        return { ok: true, module_path: "format_score.py", function_name: "format_score" }
      },
      start: (projectDir: string, blueprintId: string, plan: Record<string, unknown>, executionMode?: string) => {
        calls.push(`start:${projectDir}:${blueprintId}:${plan.goal}:${executionMode}`)
        return { code: "NOT_IMPLEMENTED_FOR_UI" }
      },
      status: (runId: string) => {
        calls.push(`status:${runId}`)
        return { code: "NOT_STARTED" }
      },
      runDiff: (runId: string) => {
        calls.push(`run-diff:${runId}`)
        return { changesets: [] }
      },
      changesetDiff: (runId: string, changesetId: string) => {
        calls.push(`changeset-diff:${runId}:${changesetId}`)
        return { changesetId }
      },
      rollbackChangesets: (runId: string, toChangesetId: string, reason?: string) => {
        calls.push(`rollback:${runId}:${toChangesetId}:${reason ?? ""}`)
        return { ok: true }
      },
      restoreRollback: (runId: string, rollbackId?: string, reason?: string) => {
        calls.push(`restore:${runId}:${rollbackId ?? ""}:${reason ?? ""}`)
        return { ok: true }
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
      ensurePlanningContext: (projectDir: string, blueprintId: string, desktopSessionId: string) => {
        calls.push(`planning-ensure:${projectDir}:${blueprintId}:${desktopSessionId}`)
        return { sessionId: "planning-1" }
      },
      answerPlanningQuestion: (
        sessionId: string,
        questionId: string,
        answers: unknown,
        opts?: { rejected?: boolean; reason?: string },
      ) => {
        calls.push(`planning-answer:${sessionId}:${questionId}:${JSON.stringify(answers)}:${opts?.rejected ?? false}`)
        return { ok: true }
      },
      rejectPlanningPlan: (sessionId: string, reason?: string) => {
        calls.push(`planning-reject:${sessionId}:${reason ?? ""}`)
        return { ok: true }
      },
      markPlanningPlanStarted: (sessionId: string, runId: string, started?: unknown) => {
        calls.push(`planning-started:${sessionId}:${runId}:${typeof started === "object"}`)
        return { ok: true }
      },
      planningStatus: (sessionId: string) => {
        calls.push(`planning-status:${sessionId}`)
        return { sessionId }
      },
      endPlanningSession: (sessionId: string, reason?: string) => {
        calls.push(`planning-end:${sessionId}:${reason ?? ""}`)
        return { ok: true }
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
    await handlers.get("blueprint-script-nodes")?.({}, "C:\\repo")
    await handlers.get("blueprint-create-script-node")?.({}, "C:\\repo", "Format Score", "Formats a score")
    const editors = (await handlers.get("blueprint-list-editors")?.({})) as Array<Record<string, unknown>>
    const scriptDir = join(testLogDir, ".multi_agent_workspace", "scripts")
    await mkdir(scriptDir, { recursive: true })
    await writeFile(join(scriptDir, "format_score.py"), "def format_score(payload):\n    return payload\n", "utf8")
    const openedScript = (await handlers.get("blueprint-open-script-in-editor")?.(
      {},
      testLogDir,
      "format_score.py",
      "system",
    )) as Record<string, unknown>
    await expect(
      handlers.get("blueprint-open-script-in-editor")?.({}, testLogDir, "../escape.py", "system"),
    ).rejects.toThrow("modulePath must stay inside the script directory")
    await handlers.get("blueprint-start")?.({}, "C:\\repo", "default", { goal: "ship" }, "live")
    await handlers.get("blueprint-status")?.({}, "run-1")
    await handlers.get("blueprint-run-diff")?.({}, "run-1")
    await handlers.get("blueprint-changeset-diff")?.({}, "run-1", "cs-1")
    await handlers.get("blueprint-rollback-changesets")?.({}, "run-1", "cs-1", "undo")
    await handlers.get("blueprint-restore-rollback")?.({}, "run-1", "rb-1", "redo")
    await handlers.get("blueprint-end")?.({}, "run-1", "cancel", "user")
    await handlers.get("blueprint-recent-events")?.({}, "run-1", 10)
    await handlers.get("blueprint-agent-info")?.({}, "run-1", "coder")
    await handlers.get("blueprint-queue-agent-message")?.({}, "run-1", "coder", "hello", "top")
    await handlers.get("blueprint-agent-stream-token")?.({}, "run-1", 18)
    await handlers.get("blueprint-planning-ensure-context")?.({}, "C:\\repo", "default", "session-1")
    await handlers.get("blueprint-planning-answer-question")?.(
      {},
      "planning-1",
      "question-1",
      { scope: "all" },
      { rejected: false },
    )
    await handlers.get("blueprint-planning-reject-plan")?.({}, "planning-1", "no")
    await handlers.get("blueprint-planning-mark-plan-started")?.({}, "planning-1", "run-2", { ok: true })
    await handlers.get("blueprint-planning-status")?.({}, "planning-1")
    await handlers.get("blueprint-planning-end-session")?.({}, "planning-1", "done")
    const savedFirst = (await handlers.get("blueprint-save-agent-panel-test")?.(
      {},
      { nodeId: "test-agent-1", streamEvents: [{ seq: 1 }] },
    )) as Record<string, unknown>
    const savedSecond = (await handlers.get("blueprint-save-agent-panel-test")?.(
      {},
      {
        schema_version: 2,
        kind: "gulicode.blueprint.test_agent_messages",
        nodeId: "test-agent-2",
        agentReplies: [],
        userMessages: [{ text: "second", status: "sent" }],
        frameworkMessages: [],
      },
    )) as Record<string, unknown>
    const updatedFirst = (await handlers.get("blueprint-save-agent-panel-test")?.(
      {},
      {
        schema_version: 2,
        kind: "gulicode.blueprint.test_agent_messages",
        nodeId: "test-agent-1",
        jsonPath: savedFirst.path,
        agentReplies: [],
        userMessages: [{ text: "hello", status: "sent" }],
        frameworkMessages: [],
      },
    )) as Record<string, unknown>
    const firstDocument = JSON.parse(await readFile(String(updatedFirst.path), "utf8")) as Record<string, unknown>
    const secondDocument = JSON.parse(await readFile(String(savedSecond.path), "utf8")) as Record<string, unknown>
    const firstPayload = firstDocument.payload as Record<string, unknown>
    const secondPayload = secondDocument.payload as Record<string, unknown>
    const testJsonFiles = (await readdir(join(testLogDir, "agent-info-panel-tests"))).sort()

    expect(editors[0]).toMatchObject({ id: "system", systemDefault: true })
    expect(openedScript.ok).toBe(true)
    expect(openedScript.editorId).toBe("system")
    expect(openedScript.path).toBe(scriptDir)
    expect(savedFirst.ok).toBe(true)
    expect(savedSecond.ok).toBe(true)
    expect(String(savedFirst.path)).toContain("agent-info-panel-tests")
    expect(String(savedFirst.path).endsWith("agent-panel-test-test-agent-1.json")).toBe(true)
    expect(String(savedSecond.path).endsWith("agent-panel-test-test-agent-2.json")).toBe(true)
    expect(updatedFirst.path).toBe(savedFirst.path)
    expect(firstDocument.schema_version).toBe(2)
    expect(firstDocument.kind).toBe("gulicode.agent_info_panel_test")
    expect(firstDocument.path).toBe(updatedFirst.path)
    expect(firstPayload.schema_version).toBe(2)
    expect(firstPayload.kind).toBe("gulicode.blueprint.test_agent_messages")
    expect(firstPayload.nodeId).toBe("test-agent-1")
    expect(firstPayload.jsonPath).toBe(updatedFirst.path)
    expect(secondDocument.path).toBe(savedSecond.path)
    expect(secondPayload.nodeId).toBe("test-agent-2")
    expect(secondPayload.jsonPath).toBe(savedSecond.path)
    expect(JSON.stringify(firstDocument)).toContain("hello")
    expect(JSON.stringify(secondDocument)).toContain("second")
    expect(testJsonFiles).toEqual(["agent-panel-test-test-agent-1.json", "agent-panel-test-test-agent-2.json"])
    expect(calls).toEqual([
      "list:C:\\repo",
      "open:C:\\repo:default",
      "save:C:\\repo:default",
      "relocate:C:\\repo:default:default:D:\\repo:overwrite",
      "validate:C:\\repo:default:default",
      "runs:C:\\repo:default",
      "detect-python:C:\\repo:C:\\Candidate\\python.exe",
      "configure:C:\\Python\\python.exe",
      "script-nodes:C:\\repo",
      "script-create:C:\\repo:Format Score:Formats a score",
      "start:C:\\repo:default:ship:live",
      "status:run-1",
      "run-diff:run-1",
      "changeset-diff:run-1:cs-1",
      "rollback:run-1:cs-1:undo",
      "restore:run-1:rb-1:redo",
      "end:run-1:cancel:user",
      "events:run-1:10",
      "agent-info:run-1:coder",
      "agent-message:run-1:coder:hello:top",
      "agent-stream:run-1:18",
      "planning-ensure:C:\\repo:default:session-1",
      'planning-answer:planning-1:question-1:{"scope":"all"}:false',
      "planning-reject:planning-1:no",
      "planning-started:planning-1:run-2:true",
      "planning-status:planning-1",
      "planning-end:planning-1:done",
    ])
  })
})
