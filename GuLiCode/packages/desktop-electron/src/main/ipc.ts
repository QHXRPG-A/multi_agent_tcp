import { execFile, spawn } from "node:child_process"
import { randomUUID } from "node:crypto"
import { mkdir, readdir, rm, writeFile } from "node:fs/promises"
import { dirname, isAbsolute, join, relative, resolve } from "node:path"
import { BrowserWindow, Notification, app, clipboard, dialog, ipcMain, shell } from "electron"
import log from "electron-log/main.js"
import type { IpcMainEvent, IpcMainInvokeEvent } from "electron"

import type {
  BlueprintWindowRect,
  BlueprintWindowPlanningSubmitInput,
  DesktopControlBridgeCommandResponse,
  DesktopControlBridgeInfo,
  InitStep,
  ServerReadyData,
  SqliteMigrationProgress,
  TitlebarTheme,
  WindowConfig,
  WslConfig,
} from "../preload/types"
import {
  listBlueprintDirectories,
  listBlueprintModels,
  listBlueprintRules,
  listBlueprintSkills,
} from "./blueprint-catalog"
import type { BlueprintEditorCandidate } from "./apps"
import type { BlueprintDocument, BlueprintRelocateConflictPolicy, BlueprintRunEndAction, BlueprintRuntime } from "./blueprint-runtime"
import { getStore } from "./store"
import {
  closeBlueprintWindow,
  dockBlueprintWindow,
  findBlueprintMainWindow,
  getBlueprintWindowContext,
  openBlueprintWindow,
  setTitlebar,
} from "./windows"

const pickerFilters = (ext?: string[]) => {
  if (!ext || ext.length === 0) return undefined
  return [{ name: "Files", extensions: ext }]
}

const AGENT_PANEL_TEST_DIR = "agent-info-panel-tests"
const AGENT_PANEL_TEST_FILE_PREFIX = "agent-panel-test-"
const AGENT_PANEL_TEST_FILE_EXT = ".json"

let agentPanelTestResetPromise: Promise<void> | undefined
const pendingBlueprintPlanningSubmits = new Map<string, (accepted: boolean) => void>()

type Deps = {
  killSidecar: () => void
  awaitInitialization: (sendStep: (step: InitStep) => void) => Promise<ServerReadyData>
  getWindowConfig: () => Promise<WindowConfig> | WindowConfig
  consumeInitialDeepLinks: () => Promise<string[]> | string[]
  getDefaultServerUrl: () => Promise<string | null> | string | null
  setDefaultServerUrl: (url: string | null) => Promise<void> | void
  getWslConfig: () => Promise<WslConfig>
  setWslConfig: (config: WslConfig) => Promise<void> | void
  getDisplayBackend: () => Promise<string | null>
  setDisplayBackend: (backend: string | null) => Promise<void> | void
  parseMarkdown: (markdown: string) => Promise<string> | string
  checkAppExists: (appName: string) => Promise<boolean> | boolean
  wslPath: (path: string, mode: "windows" | "linux" | null) => Promise<string>
  resolveAppPath: (appName: string) => Promise<string | null>
  listBlueprintEditors?: () => Promise<BlueprintEditorCandidate[]> | BlueprintEditorCandidate[]
  resolveBlueprintEditor?: (editorId?: string) => Promise<BlueprintEditorCandidate> | BlueprintEditorCandidate
  loadingWindowComplete: () => void
  runUpdater: (alertOnFail: boolean) => Promise<void> | void
  checkUpdate: () => Promise<{ updateAvailable: boolean; version?: string }>
  installUpdate: () => Promise<void> | void
  setBackgroundColor: (color: string) => void
  getDesktopControlBridgeInfo?: () => Promise<DesktopControlBridgeInfo> | DesktopControlBridgeInfo
  respondDesktopControlBridgeCommand?: (requestId: string, response: DesktopControlBridgeCommandResponse) => void
  blueprintRuntime: BlueprintRuntime
  appId?: string
}

export function registerIpcHandlers(deps: Deps) {
  agentPanelTestResetPromise = resetAgentPanelTestDirectory().catch((error) => {
    log.warn("failed to reset agent panel test json", error)
  })

  ipcMain.handle("kill-sidecar", () => deps.killSidecar())
  ipcMain.handle("await-initialization", (event: IpcMainInvokeEvent) => {
    const send = (step: InitStep) => event.sender.send("init-step", step)
    return deps.awaitInitialization(send)
  })
  ipcMain.handle("get-window-config", () => deps.getWindowConfig())
  ipcMain.handle("consume-initial-deep-links", () => deps.consumeInitialDeepLinks())
  ipcMain.handle("get-default-server-url", () => deps.getDefaultServerUrl())
  ipcMain.handle("set-default-server-url", (_event: IpcMainInvokeEvent, url: string | null) =>
    deps.setDefaultServerUrl(url),
  )
  ipcMain.handle("get-wsl-config", () => deps.getWslConfig())
  ipcMain.handle("set-wsl-config", (_event: IpcMainInvokeEvent, config: WslConfig) => deps.setWslConfig(config))
  ipcMain.handle("get-display-backend", () => deps.getDisplayBackend())
  ipcMain.handle("set-display-backend", (_event: IpcMainInvokeEvent, backend: string | null) =>
    deps.setDisplayBackend(backend),
  )
  ipcMain.handle("parse-markdown", (_event: IpcMainInvokeEvent, markdown: string) => deps.parseMarkdown(markdown))
  ipcMain.handle("check-app-exists", (_event: IpcMainInvokeEvent, appName: string) => deps.checkAppExists(appName))
  ipcMain.handle("wsl-path", (_event: IpcMainInvokeEvent, path: string, mode: "windows" | "linux" | null) =>
    deps.wslPath(path, mode),
  )
  ipcMain.handle("resolve-app-path", (_event: IpcMainInvokeEvent, appName: string) => deps.resolveAppPath(appName))
  ipcMain.on("loading-window-complete", () => deps.loadingWindowComplete())
  ipcMain.handle("run-updater", (_event: IpcMainInvokeEvent, alertOnFail: boolean) => deps.runUpdater(alertOnFail))
  ipcMain.handle("check-update", () => deps.checkUpdate())
  ipcMain.handle("install-update", () => deps.installUpdate())
  ipcMain.handle("set-background-color", (_event: IpcMainInvokeEvent, color: string) => deps.setBackgroundColor(color))
  ipcMain.handle("desktop-control-bridge-info", () => {
    if (!deps.getDesktopControlBridgeInfo) throw new Error("desktop control bridge is unavailable")
    return deps.getDesktopControlBridgeInfo()
  })
  ipcMain.handle(
    "desktop-control-bridge-command-response",
    (_event: IpcMainInvokeEvent, requestId: string, response: DesktopControlBridgeCommandResponse) =>
      deps.respondDesktopControlBridgeCommand?.(requestId, response),
  )
  ipcMain.handle("store-get", (_event: IpcMainInvokeEvent, name: string, key: string) => {
    const store = getStore(name)
    const value = store.get(key)
    if (value === undefined || value === null) return null
    return typeof value === "string" ? value : JSON.stringify(value)
  })
  ipcMain.handle("store-set", (_event: IpcMainInvokeEvent, name: string, key: string, value: string) => {
    getStore(name).set(key, value)
  })
  ipcMain.handle("store-delete", (_event: IpcMainInvokeEvent, name: string, key: string) => {
    getStore(name).delete(key)
  })
  ipcMain.handle("store-clear", (_event: IpcMainInvokeEvent, name: string) => {
    getStore(name).clear()
  })
  ipcMain.handle("store-keys", (_event: IpcMainInvokeEvent, name: string) => {
    const store = getStore(name)
    return Object.keys(store.store)
  })
  ipcMain.handle("store-length", (_event: IpcMainInvokeEvent, name: string) => {
    const store = getStore(name)
    return Object.keys(store.store).length
  })
  ipcMain.handle("blueprint-list-directories", (_event: IpcMainInvokeEvent, dir: string) => listBlueprintDirectories(dir))
  ipcMain.handle("blueprint-list-skills", (_event: IpcMainInvokeEvent, dir: string) => listBlueprintSkills(dir))
  ipcMain.handle("blueprint-list-rules", (_event: IpcMainInvokeEvent, dir: string) => listBlueprintRules(dir))
  ipcMain.handle("blueprint-list-models", (_event: IpcMainInvokeEvent, cliKind: string) => listBlueprintModels(cliKind))
  ipcMain.handle("blueprint-detect-python", (_event: IpcMainInvokeEvent, projectDir?: string, pythonCommand?: string) =>
    deps.blueprintRuntime.detectPython(projectDir, pythonCommand),
  )
  ipcMain.handle("blueprint-configure-runtime", (_event: IpcMainInvokeEvent, pythonPath?: string) =>
    deps.blueprintRuntime.configure({ pythonCommand: pythonPath }),
  )
  ipcMain.handle("blueprint-list", (_event: IpcMainInvokeEvent, projectDir: string) =>
    deps.blueprintRuntime.list(projectDir),
  )
  ipcMain.handle("blueprint-open", (_event: IpcMainInvokeEvent, projectDir: string, blueprintId: string) =>
    deps.blueprintRuntime.open(projectDir, blueprintId),
  )
  ipcMain.handle("blueprint-save", (_event: IpcMainInvokeEvent, projectDir: string, document: BlueprintDocument) =>
    deps.blueprintRuntime.save(projectDir, document),
  )
  ipcMain.handle("blueprint-script-nodes", (_event: IpcMainInvokeEvent, projectDir: string) =>
    deps.blueprintRuntime.scriptNodes(projectDir),
  )
  ipcMain.handle(
    "blueprint-create-script-node",
    (_event: IpcMainInvokeEvent, projectDir: string, name: string, description?: string) =>
      deps.blueprintRuntime.createScriptNode(projectDir, name, description),
  )
  ipcMain.handle("blueprint-list-editors", () => deps.listBlueprintEditors?.() ?? [systemDefaultEditor()])
  ipcMain.handle(
    "blueprint-open-script-in-editor",
    async (_event: IpcMainInvokeEvent, projectDir: string, modulePath: string, editorId?: string) => {
      const { root: scriptRoot } = blueprintScriptModulePath(projectDir, modulePath)
      await mkdir(scriptRoot, { recursive: true })
      const editor = (await deps.resolveBlueprintEditor?.(editorId)) ?? systemDefaultEditor()
      if (editor.systemDefault || !editor.command) {
        const error = await shell.openPath(scriptRoot)
        if (error) throw new Error(error)
        return { ok: true, path: scriptRoot, editorId: "system" }
      }
      await launchEditor(editor, scriptRoot)
      return { ok: true, path: scriptRoot, editorId: editor.id }
    },
  )
  ipcMain.handle(
    "blueprint-relocate-project-workdir",
    (
      _event: IpcMainInvokeEvent,
      projectDir: string,
      blueprintId: string,
      document: BlueprintDocument,
      targetProjectWorkdir: string,
      conflictPolicy?: BlueprintRelocateConflictPolicy,
    ) =>
      deps.blueprintRuntime.relocateProjectWorkdir(
        projectDir,
        blueprintId,
        document,
        targetProjectWorkdir,
        conflictPolicy,
      ),
  )
  ipcMain.handle(
    "blueprint-validate",
    (_event: IpcMainInvokeEvent, projectDir: string, blueprintId: string, document?: BlueprintDocument) =>
      deps.blueprintRuntime.validate(projectDir, blueprintId, document),
  )
  ipcMain.handle(
    "blueprint-list-runs",
    (_event: IpcMainInvokeEvent, projectDir?: string, blueprintId?: string) =>
      deps.blueprintRuntime.listRuns(projectDir, blueprintId),
  )
  ipcMain.handle(
    "blueprint-start",
    async (
      _event: IpcMainInvokeEvent,
      projectDir: string,
      blueprintId: string,
      plan: Record<string, unknown>,
      executionMode,
    ) => {
      await resetAgentPanelTestDirectory()
      return deps.blueprintRuntime.start(projectDir, blueprintId, plan, executionMode)
    },
  )
  ipcMain.handle("blueprint-status", (_event: IpcMainInvokeEvent, runId: string) => deps.blueprintRuntime.status(runId))
  ipcMain.handle("blueprint-run-diff", (_event: IpcMainInvokeEvent, runId: string) =>
    deps.blueprintRuntime.runDiff(runId),
  )
  ipcMain.handle(
    "blueprint-changeset-diff",
    (_event: IpcMainInvokeEvent, runId: string, changesetId: string) =>
      deps.blueprintRuntime.changesetDiff(runId, changesetId),
  )
  ipcMain.handle(
    "blueprint-rollback-changesets",
    (_event: IpcMainInvokeEvent, runId: string, toChangesetId: string, reason?: string) =>
      deps.blueprintRuntime.rollbackChangesets(runId, toChangesetId, reason),
  )
  ipcMain.handle(
    "blueprint-restore-rollback",
    (_event: IpcMainInvokeEvent, runId: string, rollbackId?: string, reason?: string) =>
      deps.blueprintRuntime.restoreRollback(runId, rollbackId, reason),
  )
  ipcMain.handle(
    "blueprint-end",
    (_event: IpcMainInvokeEvent, runId: string, action: BlueprintRunEndAction, reason?: string) =>
      deps.blueprintRuntime.end(runId, action, reason),
  )
  ipcMain.handle("blueprint-recent-events", (_event: IpcMainInvokeEvent, runId: string, limit?: number) =>
    deps.blueprintRuntime.recentEvents(runId, limit),
  )
  ipcMain.handle("blueprint-agent-info", (_event: IpcMainInvokeEvent, runId: string | undefined, nodeId: string) =>
    deps.blueprintRuntime.agentInfo(runId, nodeId),
  )
  ipcMain.handle(
    "blueprint-queue-agent-message",
    (_event: IpcMainInvokeEvent, runId: string, nodeId: string, text: string, mode: "default" | "top") =>
      deps.blueprintRuntime.queueAgentMessage(runId, nodeId, text, mode),
  )
  ipcMain.handle("blueprint-agent-stream-token", (_event: IpcMainInvokeEvent, runId: string, cursor?: number) =>
    deps.blueprintRuntime.agentStreamToken(runId, cursor),
  )
  ipcMain.handle(
    "blueprint-planning-ensure-context",
    (_event: IpcMainInvokeEvent, projectDir: string, blueprintId: string, desktopSessionId: string) =>
      deps.blueprintRuntime.ensurePlanningContext(projectDir, blueprintId, desktopSessionId),
  )
  ipcMain.handle(
    "blueprint-planning-answer-question",
    (
      _event: IpcMainInvokeEvent,
      sessionId: string,
      questionId: string,
      answers: unknown,
      opts?: { rejected?: boolean; reason?: string },
    ) => deps.blueprintRuntime.answerPlanningQuestion(sessionId, questionId, answers, opts),
  )
  ipcMain.handle(
    "blueprint-planning-reject-plan",
    (_event: IpcMainInvokeEvent, sessionId: string, reason?: string) =>
      deps.blueprintRuntime.rejectPlanningPlan(sessionId, reason),
  )
  ipcMain.handle(
    "blueprint-planning-mark-plan-started",
    (_event: IpcMainInvokeEvent, sessionId: string, runId: string, started?: unknown) =>
      deps.blueprintRuntime.markPlanningPlanStarted(sessionId, runId, started),
  )
  ipcMain.handle("blueprint-planning-status", (_event: IpcMainInvokeEvent, sessionId: string) =>
    deps.blueprintRuntime.planningStatus(sessionId),
  )
  ipcMain.handle("blueprint-planning-end-session", (_event: IpcMainInvokeEvent, sessionId: string, reason?: string) =>
    deps.blueprintRuntime.endPlanningSession(sessionId, reason),
  )
  ipcMain.handle("blueprint-save-agent-panel-test", (_event: IpcMainInvokeEvent, payload: Record<string, unknown>) =>
    saveAgentPanelTestSnapshot(recordValue(payload) ?? { value: payload }),
  )
  ipcMain.handle("blueprint-window-context", (event: IpcMainInvokeEvent) =>
    getBlueprintWindowContext(BrowserWindow.fromWebContents(event.sender)),
  )
  ipcMain.handle(
    "blueprint-window-open",
    (event: IpcMainInvokeEvent, projectDir: string, sessionId?: string, rect?: Record<string, unknown>) => {
      openBlueprintWindow(
        {
          projectDir,
          sessionId,
          rect: blueprintWindowRect(rect),
        },
        {
          appId: deps.appId,
          sourceWindow: BrowserWindow.fromWebContents(event.sender),
        },
      )
    },
  )
  ipcMain.handle("blueprint-window-dock", (event: IpcMainInvokeEvent, projectDir: string, sessionId?: string) => {
    dockBlueprintWindow(BrowserWindow.fromWebContents(event.sender), { projectDir, sessionId })
  })
  ipcMain.handle("blueprint-window-close", (event: IpcMainInvokeEvent) => {
    closeBlueprintWindow(BrowserWindow.fromWebContents(event.sender))
  })
  ipcMain.handle(
    "blueprint-window-submit-planning",
    async (
      event: IpcMainInvokeEvent,
      projectDir: string,
      sessionId: string | undefined,
      input: BlueprintWindowPlanningSubmitInput,
    ) => {
      const sourceContext = getBlueprintWindowContext(BrowserWindow.fromWebContents(event.sender))
      if (!sourceContext) return { accepted: false }
      const target = findBlueprintMainWindow()
      if (!target || target.isDestroyed()) return { accepted: false }
      const requestId = randomUUID()
      const accepted = await new Promise<boolean>((resolve) => {
        const timeout = globalThis.setTimeout(() => {
          pendingBlueprintPlanningSubmits.delete(requestId)
          resolve(false)
        }, 1000)
        pendingBlueprintPlanningSubmits.set(requestId, (next) => {
          globalThis.clearTimeout(timeout)
          resolve(next)
        })
        target.webContents.send("blueprint-window-planning-submit-request", {
          requestId,
          projectDir,
          sessionId,
          input,
        })
      })
      return { accepted }
    },
  )
  ipcMain.handle(
    "blueprint-window-planning-submit-response",
    (_event: IpcMainInvokeEvent, requestId: string, accepted: boolean) => {
      const resolve = pendingBlueprintPlanningSubmits.get(requestId)
      if (!resolve) return
      pendingBlueprintPlanningSubmits.delete(requestId)
      resolve(accepted === true)
    },
  )

  ipcMain.handle(
    "open-directory-picker",
    async (_event: IpcMainInvokeEvent, opts?: { multiple?: boolean; title?: string; defaultPath?: string }) => {
      const result = await dialog.showOpenDialog({
        properties: ["openDirectory", ...(opts?.multiple ? ["multiSelections" as const] : []), "createDirectory"],
        title: opts?.title ?? "Choose a folder",
        defaultPath: opts?.defaultPath,
      })
      if (result.canceled) return null
      return opts?.multiple ? result.filePaths : result.filePaths[0]
    },
  )

  ipcMain.handle(
    "open-file-picker",
    async (
      _event: IpcMainInvokeEvent,
      opts?: { multiple?: boolean; title?: string; defaultPath?: string; accept?: string[]; extensions?: string[] },
    ) => {
      const result = await dialog.showOpenDialog({
        properties: ["openFile", ...(opts?.multiple ? ["multiSelections" as const] : [])],
        title: opts?.title ?? "Choose a file",
        defaultPath: opts?.defaultPath,
        filters: pickerFilters(opts?.extensions),
      })
      if (result.canceled) return null
      return opts?.multiple ? result.filePaths : result.filePaths[0]
    },
  )

  ipcMain.handle(
    "save-file-picker",
    async (_event: IpcMainInvokeEvent, opts?: { title?: string; defaultPath?: string }) => {
      const result = await dialog.showSaveDialog({
        title: opts?.title ?? "Save file",
        defaultPath: opts?.defaultPath,
      })
      if (result.canceled) return null
      return result.filePath ?? null
    },
  )

  ipcMain.on("open-link", (_event: IpcMainEvent, url: string) => {
    void shell.openExternal(url)
  })

  ipcMain.handle("open-path", async (_event: IpcMainInvokeEvent, path: string, app?: string) => {
    if (!app) return shell.openPath(path)
    await new Promise<void>((resolve, reject) => {
      const [cmd, args] =
        process.platform === "darwin" ? (["open", ["-a", app, path]] as const) : ([app, [path]] as const)
      execFile(cmd, args, (err) => (err ? reject(err) : resolve()))
    })
  })

  ipcMain.handle("reveal-path-in-file-manager", (_event: IpcMainInvokeEvent, path: string) => {
    shell.showItemInFolder(path)
  })

  ipcMain.handle("read-clipboard-image", () => {
    const image = clipboard.readImage()
    if (image.isEmpty()) return null
    const buffer = image.toPNG().buffer
    const size = image.getSize()
    return { buffer, width: size.width, height: size.height }
  })

  ipcMain.on("show-notification", (_event: IpcMainEvent, title: string, body?: string) => {
    new Notification({ title, body }).show()
  })

  ipcMain.handle("get-window-count", () => BrowserWindow.getAllWindows().length)

  ipcMain.handle("get-window-focused", (event: IpcMainInvokeEvent) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    return win?.isFocused() ?? false
  })

  ipcMain.handle("set-window-focus", (event: IpcMainInvokeEvent) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    win?.focus()
  })

  ipcMain.handle("show-window", (event: IpcMainInvokeEvent) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    win?.show()
  })

  ipcMain.on("relaunch", () => {
    app.relaunch()
    app.exit(0)
  })

  ipcMain.handle("get-zoom-factor", (event: IpcMainInvokeEvent) => event.sender.getZoomFactor())
  ipcMain.handle("set-zoom-factor", (event: IpcMainInvokeEvent, factor: number) => event.sender.setZoomFactor(factor))
  ipcMain.handle("set-titlebar", (event: IpcMainInvokeEvent, theme: TitlebarTheme) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return
    setTitlebar(win, theme)
  })
}

export function sendSqliteMigrationProgress(win: BrowserWindow, progress: SqliteMigrationProgress) {
  win.webContents.send("sqlite-migration-progress", progress)
}

export function sendMenuCommand(win: BrowserWindow, id: string) {
  win.webContents.send("menu-command", id)
}

export function sendDeepLinks(win: BrowserWindow, urls: string[]) {
  win.webContents.send("deep-link", urls)
}

async function saveAgentPanelTestSnapshot(payload: Record<string, unknown>) {
  if (agentPanelTestResetPromise) await agentPanelTestResetPromise
  const dir = agentPanelTestDirectory()
  await mkdir(dir, { recursive: true })
  const now = new Date()
  const path = join(dir, agentPanelTestSnapshotFileName(payload))
  const document = {
    schema_version: 2,
    kind: "gulicode.agent_info_panel_test",
    saved_at: now.toISOString(),
    path,
    payload: {
      ...payload,
      jsonPath: path,
    },
  }
  await writeFile(path, JSON.stringify(document, null, 2), "utf8")
  return { ok: true, path }
}

function agentPanelTestSnapshotFileName(payload: Record<string, unknown>) {
  const rawNodeId = typeof payload.nodeId === "string" ? payload.nodeId.trim() : ""
  const safeNodeId = rawNodeId ? rawNodeId.replace(/[^A-Za-z0-9._-]/g, "-") : "unknown"
  return `${AGENT_PANEL_TEST_FILE_PREFIX}${safeNodeId}${AGENT_PANEL_TEST_FILE_EXT}`
}

async function resetAgentPanelTestDirectory() {
  const dir = agentPanelTestDirectory()
  await mkdir(dir, { recursive: true })
  await clearAgentPanelTestJsonFiles(dir)
}

function agentPanelTestDirectory() {
  const logFile = currentLogFilePath()
  if (logFile) return join(dirname(logFile), AGENT_PANEL_TEST_DIR)
  try {
    const getPath = (app as { getPath?: (name: "logs") => string }).getPath
    if (getPath) return join(getPath.call(app, "logs"), AGENT_PANEL_TEST_DIR)
  } catch {
    // fall through to the project-local debug log convention
  }
  return join(process.cwd(), "debug-logs", AGENT_PANEL_TEST_DIR)
}

function currentLogFilePath() {
  try {
    const path = log.transports.file.getFile().path
    return typeof path === "string" && path ? path : undefined
  } catch {
    return undefined
  }
}

async function clearAgentPanelTestJsonFiles(dir: string) {
  const entries = await readdir(dir, { withFileTypes: true }).catch(() => [])
  await Promise.all(
    entries
      .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".json"))
      .map((entry) => rm(join(dir, entry.name), { force: true })),
  )
}

function recordValue(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined
}

function blueprintWindowRect(value: Record<string, unknown> | undefined): BlueprintWindowRect | undefined {
  if (!value) return undefined
  const x = finiteNumber(value.x)
  const y = finiteNumber(value.y)
  const width = finiteNumber(value.width)
  const height = finiteNumber(value.height)
  if (x === undefined || y === undefined || width === undefined || height === undefined) return undefined
  return { x, y, width, height }
}

function finiteNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined
}

function systemDefaultEditor(): BlueprintEditorCandidate {
  return {
    id: "system",
    label: "System default",
    source: "system",
    systemDefault: true,
  }
}

function blueprintScriptRoot(projectDir: string) {
  if (!isAbsolute(projectDir)) throw new Error("projectDir must be an absolute path")
  return resolve(projectDir, ".multi_agent_workspace", "scripts")
}

function blueprintScriptModulePath(projectDir: string, modulePath: string) {
  const root = blueprintScriptRoot(projectDir)
  const normalizedModulePath = String(modulePath || "").replace(/\\/g, "/").trim()
  const parts = normalizedModulePath.split("/").filter(Boolean)
  if (!normalizedModulePath || isAbsolute(normalizedModulePath) || parts.some((part) => part === "..")) {
    throw new Error("modulePath must stay inside the script directory")
  }
  if (!normalizedModulePath.endsWith(".py")) throw new Error("modulePath must point to a .py file")
  const filePath = resolve(root, ...parts)
  const rel = relative(root, filePath)
  if (!rel || rel.startsWith("..") || isAbsolute(rel)) {
    throw new Error("modulePath escapes the script directory")
  }
  return { root, filePath }
}

function launchEditor(editor: BlueprintEditorCandidate, scriptRoot: string) {
  if (!editor.command) return Promise.reject(new Error("editor command is missing"))
  const args = [
    ...(editor.args ?? []).filter((arg) => arg !== "--wait" && arg !== "-w"),
    ...editorForegroundArgs(editor),
    scriptRoot,
  ]
  return new Promise<void>((resolveLaunch, rejectLaunch) => {
    const child = spawn(editor.command!, args, {
      detached: true,
      stdio: "ignore",
      windowsHide: false,
    })
    child.once("error", rejectLaunch)
    child.once("spawn", () => {
      child.unref()
      resolveLaunch()
    })
  })
}

function editorForegroundArgs(editor: BlueprintEditorCandidate) {
  if (process.platform !== "win32") return []
  const id = editor.id.toLowerCase()
  const command = String(editor.command ?? "").toLowerCase().replace(/\\/g, "/")
  const commandName = command.split("/").pop() ?? command
  if (
    id === "vscode" ||
    id === "cursor" ||
    id === "windsurf" ||
    commandName === "code.exe" ||
    commandName === "cursor.exe" ||
    commandName === "windsurf.exe"
  ) {
    return ["--reuse-window"]
  }
  return []
}
