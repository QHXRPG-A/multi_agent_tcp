import { contextBridge, ipcRenderer } from "electron"
import type {
  BlueprintWindowContext,
  BlueprintWindowPlanningSubmitRequest,
  DesktopControlBridgeCommandRequest,
  ElectronAPI,
  InitStep,
  SqliteMigrationProgress,
} from "./types"

const api: ElectronAPI = {
  killSidecar: () => ipcRenderer.invoke("kill-sidecar"),
  installCli: () => ipcRenderer.invoke("install-cli"),
  awaitInitialization: (onStep) => {
    const handler = (_: unknown, step: InitStep) => onStep(step)
    ipcRenderer.on("init-step", handler)
    return ipcRenderer.invoke("await-initialization").finally(() => {
      ipcRenderer.removeListener("init-step", handler)
    })
  },
  getWindowConfig: () => ipcRenderer.invoke("get-window-config"),
  consumeInitialDeepLinks: () => ipcRenderer.invoke("consume-initial-deep-links"),
  getDefaultServerUrl: () => ipcRenderer.invoke("get-default-server-url"),
  setDefaultServerUrl: (url) => ipcRenderer.invoke("set-default-server-url", url),
  getWslConfig: () => ipcRenderer.invoke("get-wsl-config"),
  setWslConfig: (config) => ipcRenderer.invoke("set-wsl-config", config),
  getDisplayBackend: () => ipcRenderer.invoke("get-display-backend"),
  setDisplayBackend: (backend) => ipcRenderer.invoke("set-display-backend", backend),
  parseMarkdownCommand: (markdown) => ipcRenderer.invoke("parse-markdown", markdown),
  checkAppExists: (appName) => ipcRenderer.invoke("check-app-exists", appName),
  wslPath: (path, mode) => ipcRenderer.invoke("wsl-path", path, mode),
  resolveAppPath: (appName) => ipcRenderer.invoke("resolve-app-path", appName),
  storeGet: (name, key) => ipcRenderer.invoke("store-get", name, key),
  storeSet: (name, key, value) => ipcRenderer.invoke("store-set", name, key, value),
  storeDelete: (name, key) => ipcRenderer.invoke("store-delete", name, key),
  storeClear: (name) => ipcRenderer.invoke("store-clear", name),
  storeKeys: (name) => ipcRenderer.invoke("store-keys", name),
  storeLength: (name) => ipcRenderer.invoke("store-length", name),
  blueprintListDirectories: (dir) => ipcRenderer.invoke("blueprint-list-directories", dir),
  blueprintListSkills: (dir) => ipcRenderer.invoke("blueprint-list-skills", dir),
  blueprintListRules: (dir) => ipcRenderer.invoke("blueprint-list-rules", dir),
  blueprintListModels: (cliKind) => ipcRenderer.invoke("blueprint-list-models", cliKind),
  blueprintDetectPython: (projectDir, pythonCommand) => ipcRenderer.invoke("blueprint-detect-python", projectDir, pythonCommand),
  blueprintConfigureRuntime: (pythonPath) => ipcRenderer.invoke("blueprint-configure-runtime", pythonPath),
  blueprintList: (projectDir) => ipcRenderer.invoke("blueprint-list", projectDir),
  blueprintOpen: (projectDir, blueprintId) => ipcRenderer.invoke("blueprint-open", projectDir, blueprintId),
  blueprintSave: (projectDir, document) => ipcRenderer.invoke("blueprint-save", projectDir, document),
  blueprintScriptNodes: (projectDir) => ipcRenderer.invoke("blueprint-script-nodes", projectDir),
  blueprintCreateScriptNode: (projectDir, name, description) =>
    ipcRenderer.invoke("blueprint-create-script-node", projectDir, name, description),
  blueprintListEditors: () => ipcRenderer.invoke("blueprint-list-editors"),
  blueprintOpenScriptInEditor: (projectDir, modulePath, editorId) =>
    ipcRenderer.invoke("blueprint-open-script-in-editor", projectDir, modulePath, editorId),
  blueprintResidentServices: () => ipcRenderer.invoke("blueprint-resident-services"),
  blueprintCreateResidentService: (name, description) =>
    ipcRenderer.invoke("blueprint-create-resident-service", name, description),
  blueprintOpenResidentServiceInEditor: (modulePath, editorId) =>
    ipcRenderer.invoke("blueprint-open-resident-service-in-editor", modulePath, editorId),
  blueprintStartResidentService: (serviceName) => ipcRenderer.invoke("blueprint-start-resident-service", serviceName),
  blueprintStopResidentService: (serviceName) => ipcRenderer.invoke("blueprint-stop-resident-service", serviceName),
  blueprintResidentServiceLogs: (serviceName, limit) =>
    ipcRenderer.invoke("blueprint-resident-service-logs", serviceName, limit),
  blueprintResidentServiceDocs: (serviceName) => ipcRenderer.invoke("blueprint-resident-service-docs", serviceName),
  blueprintRelocateProjectWorkdir: (projectDir, blueprintId, document, targetProjectWorkdir, conflictPolicy) =>
    ipcRenderer.invoke(
      "blueprint-relocate-project-workdir",
      projectDir,
      blueprintId,
      document,
      targetProjectWorkdir,
      conflictPolicy,
    ),
  blueprintValidate: (projectDir, blueprintId, document) =>
    ipcRenderer.invoke("blueprint-validate", projectDir, blueprintId, document),
  blueprintListRuns: (projectDir, blueprintId) => ipcRenderer.invoke("blueprint-list-runs", projectDir, blueprintId),
  blueprintListSessions: (projectDir, blueprintId) =>
    ipcRenderer.invoke("blueprint-list-sessions", projectDir, blueprintId),
  blueprintSessionTimeline: (sessionKey, limit) => ipcRenderer.invoke("blueprint-session-timeline", sessionKey, limit),
  blueprintDeleteSession: (sessionKey) => ipcRenderer.invoke("blueprint-delete-session", sessionKey),
  blueprintTerminateSession: (sessionKey, reason) =>
    ipcRenderer.invoke("blueprint-terminate-session", sessionKey, reason),
  blueprintSessionMessage: (projectDir, blueprintId, message, input) =>
    ipcRenderer.invoke("blueprint-session-message", projectDir, blueprintId, message, input),
  blueprintStart: (projectDir, blueprintId, plan, executionMode) =>
    ipcRenderer.invoke("blueprint-start", projectDir, blueprintId, plan, executionMode),
  blueprintStatus: (runId) => ipcRenderer.invoke("blueprint-status", runId),
  blueprintRunDiff: (runId) => ipcRenderer.invoke("blueprint-run-diff", runId),
  blueprintChangesetDiff: (runId, changesetId) => ipcRenderer.invoke("blueprint-changeset-diff", runId, changesetId),
  blueprintRollbackChangesets: (runId, toChangesetId, reason) =>
    ipcRenderer.invoke("blueprint-rollback-changesets", runId, toChangesetId, reason),
  blueprintRestoreRollback: (runId, rollbackId, reason) =>
    ipcRenderer.invoke("blueprint-restore-rollback", runId, rollbackId, reason),
  blueprintEnd: (runId, action, reason) => ipcRenderer.invoke("blueprint-end", runId, action, reason),
  blueprintRecentEvents: (runId, limit) => ipcRenderer.invoke("blueprint-recent-events", runId, limit),
  blueprintAgentInfo: (runId, nodeId) => ipcRenderer.invoke("blueprint-agent-info", runId, nodeId),
  blueprintQueueAgentMessage: (runId, nodeId, text, mode) =>
    ipcRenderer.invoke("blueprint-queue-agent-message", runId, nodeId, text, mode),
  blueprintAgentStreamToken: (runId, cursor) => ipcRenderer.invoke("blueprint-agent-stream-token", runId, cursor),
  blueprintPlanningEnsureContext: (projectDir, blueprintId, desktopSessionId) =>
    ipcRenderer.invoke("blueprint-planning-ensure-context", projectDir, blueprintId, desktopSessionId),
  blueprintPlanningAnswerQuestion: (sessionId, questionId, answers, opts) =>
    ipcRenderer.invoke("blueprint-planning-answer-question", sessionId, questionId, answers, opts),
  blueprintPlanningRejectPlan: (sessionId, reason) =>
    ipcRenderer.invoke("blueprint-planning-reject-plan", sessionId, reason),
  blueprintPlanningMarkPlanStarted: (sessionId, runId, started) =>
    ipcRenderer.invoke("blueprint-planning-mark-plan-started", sessionId, runId, started),
  blueprintPlanningStatus: (sessionId) => ipcRenderer.invoke("blueprint-planning-status", sessionId),
  blueprintPlanningEndSession: (sessionId, reason) =>
    ipcRenderer.invoke("blueprint-planning-end-session", sessionId, reason),
  blueprintSaveAgentPanelTest: (payload) => ipcRenderer.invoke("blueprint-save-agent-panel-test", payload),
  getBlueprintWindowContext: () => ipcRenderer.invoke("blueprint-window-context"),
  openBlueprintWindow: (projectDir, sessionId, rect) =>
    ipcRenderer.invoke("blueprint-window-open", projectDir, sessionId, rect),
  dockBlueprintWindow: (projectDir, sessionId) =>
    ipcRenderer.invoke("blueprint-window-dock", projectDir, sessionId),
  closeBlueprintWindow: () => ipcRenderer.invoke("blueprint-window-close"),
  submitBlueprintWindowPlanning: (projectDir, sessionId, input) =>
    ipcRenderer.invoke("blueprint-window-submit-planning", projectDir, sessionId, input),
  respondBlueprintWindowPlanningSubmit: (requestId, accepted) =>
    ipcRenderer.invoke("blueprint-window-planning-submit-response", requestId, accepted),

  getWindowCount: () => ipcRenderer.invoke("get-window-count"),
  onSqliteMigrationProgress: (cb) => {
    const handler = (_: unknown, progress: SqliteMigrationProgress) => cb(progress)
    ipcRenderer.on("sqlite-migration-progress", handler)
    return () => ipcRenderer.removeListener("sqlite-migration-progress", handler)
  },
  onMenuCommand: (cb) => {
    const handler = (_: unknown, id: string) => cb(id)
    ipcRenderer.on("menu-command", handler)
    return () => ipcRenderer.removeListener("menu-command", handler)
  },
  onDeepLink: (cb) => {
    const handler = (_: unknown, urls: string[]) => cb(urls)
    ipcRenderer.on("deep-link", handler)
    return () => ipcRenderer.removeListener("deep-link", handler)
  },
  onBlueprintWindowDock: (cb) => {
    const handler = (_: unknown, context: BlueprintWindowContext) => cb(context)
    ipcRenderer.on("blueprint-window-dock-request", handler)
    return () => ipcRenderer.removeListener("blueprint-window-dock-request", handler)
  },
  onBlueprintWindowClosed: (cb) => {
    const handler = (_: unknown, context: BlueprintWindowContext) => cb(context)
    ipcRenderer.on("blueprint-window-closed", handler)
    return () => ipcRenderer.removeListener("blueprint-window-closed", handler)
  },
  onBlueprintWindowPlanningSubmitRequest: (cb) => {
    const handler = (_: unknown, request: BlueprintWindowPlanningSubmitRequest) => cb(request)
    ipcRenderer.on("blueprint-window-planning-submit-request", handler)
    return () => ipcRenderer.removeListener("blueprint-window-planning-submit-request", handler)
  },

  openDirectoryPicker: (opts) => ipcRenderer.invoke("open-directory-picker", opts),
  openFilePicker: (opts) => ipcRenderer.invoke("open-file-picker", opts),
  saveFilePicker: (opts) => ipcRenderer.invoke("save-file-picker", opts),
  openLink: (url) => ipcRenderer.send("open-link", url),
  openPath: (path, app) => ipcRenderer.invoke("open-path", path, app),
  revealPathInFileManager: (path) => ipcRenderer.invoke("reveal-path-in-file-manager", path),
  readClipboardImage: () => ipcRenderer.invoke("read-clipboard-image"),
  showNotification: (title, body) => ipcRenderer.send("show-notification", title, body),
  getWindowFocused: () => ipcRenderer.invoke("get-window-focused"),
  setWindowFocus: () => ipcRenderer.invoke("set-window-focus"),
  showWindow: () => ipcRenderer.invoke("show-window"),
  relaunch: () => ipcRenderer.send("relaunch"),
  getZoomFactor: () => ipcRenderer.invoke("get-zoom-factor"),
  setZoomFactor: (factor) => ipcRenderer.invoke("set-zoom-factor", factor),
  setTitlebar: (theme) => ipcRenderer.invoke("set-titlebar", theme),
  loadingWindowComplete: () => ipcRenderer.send("loading-window-complete"),
  runUpdater: (alertOnFail) => ipcRenderer.invoke("run-updater", alertOnFail),
  checkUpdate: () => ipcRenderer.invoke("check-update"),
  installUpdate: () => ipcRenderer.invoke("install-update"),
  setBackgroundColor: (color: string) => ipcRenderer.invoke("set-background-color", color),
  getDesktopControlBridge: () => ipcRenderer.invoke("desktop-control-bridge-info"),
  respondDesktopControlBridgeCommand: (requestId, response) =>
    ipcRenderer.invoke("desktop-control-bridge-command-response", requestId, response),
  onDesktopControlBridgeCommand: (cb) => {
    const handler = (_: unknown, request: DesktopControlBridgeCommandRequest) => cb(request)
    ipcRenderer.on("desktop-control-bridge-command", handler)
    return () => ipcRenderer.removeListener("desktop-control-bridge-command", handler)
  },
}

contextBridge.exposeInMainWorld("api", api)
