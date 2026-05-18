export type InitStep = { phase: "server_waiting" } | { phase: "sqlite_waiting" } | { phase: "done" }

export type ServerReadyData = {
  url: string
  username: string | null
  password: string | null
}

export type SqliteMigrationProgress = { type: "InProgress"; value: number } | { type: "Done" }

export type WslConfig = { enabled: boolean }

export type LinuxDisplayBackend = "wayland" | "auto"
export type TitlebarTheme = {
  mode: "light" | "dark"
}

export type WindowConfig = {
  updaterEnabled: boolean
}

export type BlueprintCatalogItem = {
  value: string
  label: string
  description?: string
}

export type BlueprintDocument = {
  schema_version: 1
  id: string
  name: string
  graph: Record<string, unknown>
  ui: Record<string, unknown>
}

export type BlueprintSummary = {
  id: string
  name: string
  path: string
  updated_at: number
}

export type BlueprintValidationResult = {
  ok: boolean
  errors: string[]
  warnings: string[]
}

export type BlueprintRunEndAction = "complete" | "cancel" | "fail" | "pause"

export type ElectronAPI = {
  killSidecar: () => Promise<void>
  installCli: () => Promise<string>
  awaitInitialization: (onStep: (step: InitStep) => void) => Promise<ServerReadyData>
  getWindowConfig: () => Promise<WindowConfig>
  consumeInitialDeepLinks: () => Promise<string[]>
  getDefaultServerUrl: () => Promise<string | null>
  setDefaultServerUrl: (url: string | null) => Promise<void>
  getWslConfig: () => Promise<WslConfig>
  setWslConfig: (config: WslConfig) => Promise<void>
  getDisplayBackend: () => Promise<LinuxDisplayBackend | null>
  setDisplayBackend: (backend: LinuxDisplayBackend | null) => Promise<void>
  parseMarkdownCommand: (markdown: string) => Promise<string>
  checkAppExists: (appName: string) => Promise<boolean>
  wslPath: (path: string, mode: "windows" | "linux" | null) => Promise<string>
  resolveAppPath: (appName: string) => Promise<string | null>
  storeGet: (name: string, key: string) => Promise<string | null>
  storeSet: (name: string, key: string, value: string) => Promise<void>
  storeDelete: (name: string, key: string) => Promise<void>
  storeClear: (name: string) => Promise<void>
  storeKeys: (name: string) => Promise<string[]>
  storeLength: (name: string) => Promise<number>
  blueprintListDirectories: (dir: string) => Promise<BlueprintCatalogItem[]>
  blueprintListSkills: (dir: string) => Promise<BlueprintCatalogItem[]>
  blueprintListRules: (dir: string) => Promise<BlueprintCatalogItem[]>
  blueprintListModels: (cliKind: string) => Promise<string[]>
  blueprintList: (projectDir: string) => Promise<BlueprintSummary[]>
  blueprintOpen: (projectDir: string, blueprintId: string) => Promise<BlueprintDocument>
  blueprintSave: (projectDir: string, document: BlueprintDocument) => Promise<BlueprintDocument>
  blueprintValidate: (
    projectDir: string,
    blueprintId: string,
    document?: BlueprintDocument,
  ) => Promise<BlueprintValidationResult>
  blueprintListRuns: (projectDir?: string, blueprintId?: string) => Promise<Record<string, unknown>[]>
  blueprintStart: (
    projectDir: string,
    blueprintId: string,
    plan: Record<string, unknown>,
    executionMode?: "status" | "live",
  ) => Promise<Record<string, unknown>>
  blueprintStatus: (runId: string) => Promise<Record<string, unknown>>
  blueprintEnd: (runId: string, action: BlueprintRunEndAction, reason?: string) => Promise<Record<string, unknown>>
  blueprintRecentEvents: (runId: string, limit?: number) => Promise<Record<string, unknown>>
  blueprintAgentInfo: (runId: string | undefined, nodeId: string) => Promise<Record<string, unknown>>
  blueprintQueueAgentMessage: (
    runId: string,
    nodeId: string,
    text: string,
    mode: "default" | "top",
  ) => Promise<Record<string, unknown>>
  blueprintAgentStreamToken: (runId: string, cursor?: number) => Promise<Record<string, unknown>>
  blueprintSaveAgentPanelTest: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>

  getWindowCount: () => Promise<number>
  onSqliteMigrationProgress: (cb: (progress: SqliteMigrationProgress) => void) => () => void
  onMenuCommand: (cb: (id: string) => void) => () => void
  onDeepLink: (cb: (urls: string[]) => void) => () => void

  openDirectoryPicker: (opts?: {
    multiple?: boolean
    title?: string
    defaultPath?: string
  }) => Promise<string | string[] | null>
  openFilePicker: (opts?: {
    multiple?: boolean
    title?: string
    defaultPath?: string
    accept?: string[]
    extensions?: string[]
  }) => Promise<string | string[] | null>
  saveFilePicker: (opts?: { title?: string; defaultPath?: string }) => Promise<string | null>
  openLink: (url: string) => void
  openPath: (path: string, app?: string) => Promise<void>
  readClipboardImage: () => Promise<{ buffer: ArrayBuffer; width: number; height: number } | null>
  showNotification: (title: string, body?: string) => void
  getWindowFocused: () => Promise<boolean>
  setWindowFocus: () => Promise<void>
  showWindow: () => Promise<void>
  relaunch: () => void
  getZoomFactor: () => Promise<number>
  setZoomFactor: (factor: number) => Promise<void>
  setTitlebar: (theme: TitlebarTheme) => Promise<void>
  loadingWindowComplete: () => void
  runUpdater: (alertOnFail: boolean) => Promise<void>
  checkUpdate: () => Promise<{ updateAvailable: boolean; version?: string }>
  installUpdate: () => Promise<void>
  setBackgroundColor: (color: string) => Promise<void>
}
