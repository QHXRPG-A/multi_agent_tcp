import { beforeAll, describe, expect, mock, test } from "bun:test"

type Handler = (_event: unknown, ...args: unknown[]) => unknown

const handlers = new Map<string, Handler>()

beforeAll(() => {
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
      validate: (projectDir: string, blueprintId: string, document?: { id: string }) => {
        calls.push(`validate:${projectDir}:${blueprintId}:${document?.id ?? ""}`)
        return { ok: true, errors: [], warnings: [] }
      },
      listRuns: (projectDir?: string, blueprintId?: string) => {
        calls.push(`runs:${projectDir}:${blueprintId}`)
        return [{ runId: "run-1" }]
      },
      start: (projectDir: string, blueprintId: string, plan: Record<string, unknown>) => {
        calls.push(`start:${projectDir}:${blueprintId}:${plan.goal}`)
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
    await handlers.get("blueprint-validate")?.({}, "C:\\repo", "default", { id: "default" })
    await handlers.get("blueprint-list-runs")?.({}, "C:\\repo", "default")
    await handlers.get("blueprint-start")?.({}, "C:\\repo", "default", { goal: "ship" })
    await handlers.get("blueprint-status")?.({}, "run-1")
    await handlers.get("blueprint-end")?.({}, "run-1", "cancel", "user")
    await handlers.get("blueprint-recent-events")?.({}, "run-1", 10)

    expect(calls).toEqual([
      "list:C:\\repo",
      "open:C:\\repo:default",
      "save:C:\\repo:default",
      "validate:C:\\repo:default:default",
      "runs:C:\\repo:default",
      "start:C:\\repo:default:ship",
      "status:run-1",
      "end:run-1:cancel:user",
      "events:run-1:10",
    ])
  })
})
