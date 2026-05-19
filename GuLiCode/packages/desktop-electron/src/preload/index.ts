import { contextBridge, ipcRenderer } from "electron"
import type { ElectronAPI, InitStep, SqliteMigrationProgress } from "./types"

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
  blueprintValidate: (projectDir, blueprintId, document) =>
    ipcRenderer.invoke("blueprint-validate", projectDir, blueprintId, document),
  blueprintListRuns: (projectDir, blueprintId) => ipcRenderer.invoke("blueprint-list-runs", projectDir, blueprintId),
  blueprintStart: (projectDir, blueprintId, plan, executionMode) =>
    ipcRenderer.invoke("blueprint-start", projectDir, blueprintId, plan, executionMode),
  blueprintStatus: (runId) => ipcRenderer.invoke("blueprint-status", runId),
  blueprintEnd: (runId, action, reason) => ipcRenderer.invoke("blueprint-end", runId, action, reason),
  blueprintRecentEvents: (runId, limit) => ipcRenderer.invoke("blueprint-recent-events", runId, limit),
  blueprintAgentInfo: (runId, nodeId) => ipcRenderer.invoke("blueprint-agent-info", runId, nodeId),
  blueprintQueueAgentMessage: (runId, nodeId, text, mode) =>
    ipcRenderer.invoke("blueprint-queue-agent-message", runId, nodeId, text, mode),
  blueprintAgentStreamToken: (runId, cursor) => ipcRenderer.invoke("blueprint-agent-stream-token", runId, cursor),
  blueprintSaveAgentPanelTest: (payload) => ipcRenderer.invoke("blueprint-save-agent-panel-test", payload),

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

  openDirectoryPicker: (opts) => ipcRenderer.invoke("open-directory-picker", opts),
  openFilePicker: (opts) => ipcRenderer.invoke("open-file-picker", opts),
  saveFilePicker: (opts) => ipcRenderer.invoke("save-file-picker", opts),
  openLink: (url) => ipcRenderer.send("open-link", url),
  openPath: (path, app) => ipcRenderer.invoke("open-path", path, app),
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
}

contextBridge.exposeInMainWorld("api", api)
