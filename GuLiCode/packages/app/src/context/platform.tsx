import { createSimpleContext } from "@opencode-ai/ui/context"
import type { AsyncStorage, SyncStorage } from "@solid-primitives/storage"
import type { Accessor } from "solid-js"
import { ServerConnection } from "./server"

type PickerPaths = string | string[] | null
type OpenDirectoryPickerOptions = { title?: string; multiple?: boolean; defaultPath?: string }
type OpenFilePickerOptions = { title?: string; multiple?: boolean; defaultPath?: string; accept?: string[]; extensions?: string[] }
type SaveFilePickerOptions = { title?: string; defaultPath?: string }
type UpdateInfo = { updateAvailable: boolean; version?: string }

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

export type BlueprintRelocateConflictPolicy = "overwrite" | "load_existing"

export type BlueprintRelocateProjectWorkdirResult = {
  ok: boolean
  changed: boolean
  projectDir: string
  targetProjectDir: string
  document: BlueprintDocument
  conflict?: "target_exists"
}

export type BlueprintWindowRect = {
  x: number
  y: number
  width: number
  height: number
}

export type BlueprintWindowPlanningSubmitInput = {
  task: string
  startNodeIds: string[]
  message: string
  silentBlocked?: boolean
}

export type Platform = {
  /** Platform discriminator */
  platform: "web" | "desktop"

  /** Desktop OS (Tauri only) */
  os?: "macos" | "windows" | "linux"

  /** App version */
  version?: string

  /** Open a URL in the default browser */
  openLink(url: string): void

  /** Open a local path in a local app (desktop only) */
  openPath?(path: string, app?: string): Promise<void>

  /** Reveal a local file or directory in the platform file manager (desktop only) */
  revealPathInFileManager?(path: string): Promise<void>

  /** Restart the app  */
  restart(): Promise<void>

  /** Navigate back in history */
  back(): void

  /** Navigate forward in history */
  forward(): void

  /** Send a system notification (optional deep link) */
  notify(title: string, description?: string, href?: string): Promise<void>

  /** Open directory picker dialog (native on Tauri, server-backed on web) */
  openDirectoryPickerDialog?(opts?: OpenDirectoryPickerOptions): Promise<PickerPaths>

  /** Open native file picker dialog (Tauri only) */
  openFilePickerDialog?(opts?: OpenFilePickerOptions): Promise<PickerPaths>

  /** Save file picker dialog (Tauri only) */
  saveFilePickerDialog?(opts?: SaveFilePickerOptions): Promise<string | null>

  /** Blueprint directory candidates (desktop only) */
  listBlueprintDirectories?(dir: string): Promise<BlueprintCatalogItem[]>

  /** Blueprint skill candidates from a skill directory (desktop only) */
  listBlueprintSkills?(dir: string): Promise<BlueprintCatalogItem[]>

  /** Blueprint rule candidates from a rule directory (desktop only) */
  listBlueprintRules?(dir: string): Promise<BlueprintCatalogItem[]>

  /** Blueprint model candidates for the selected CLI adapter (desktop only) */
  listBlueprintModels?(cliKind: string): Promise<string[]>

  /** Detect a Python interpreter usable by the desktop blueprint runtime (desktop only) */
  detectBlueprintPython?(projectDir?: string, pythonCommand?: string): Promise<Record<string, unknown>>

  /** Configure the desktop blueprint Python runtime before project persistence/start calls (desktop only) */
  configureBlueprintRuntime?(pythonPath?: string): Promise<Record<string, unknown>>

  /** Project blueprint document list (desktop only) */
  listBlueprints?(projectDir: string): Promise<BlueprintSummary[]>

  /** Open one project blueprint document (desktop only) */
  openBlueprint?(projectDir: string, blueprintId: string): Promise<BlueprintDocument>

  /** Save one project blueprint document (desktop only) */
  saveBlueprint?(projectDir: string, document: BlueprintDocument): Promise<BlueprintDocument>

  /** Move the current blueprint document to a new project workdir and make that directory the blueprint root. */
  relocateBlueprintProjectWorkdir?(
    projectDir: string,
    blueprintId: string,
    document: BlueprintDocument,
    targetProjectWorkdir: string,
    conflictPolicy?: BlueprintRelocateConflictPolicy,
  ): Promise<BlueprintRelocateProjectWorkdirResult>

  /** Validate one project blueprint document against runtime graph rules (desktop only) */
  validateBlueprint?(projectDir: string, blueprintId: string, document?: BlueprintDocument): Promise<BlueprintValidationResult>

  /** List live blueprint runs owned by the desktop runtime service (desktop only) */
  listBlueprintRuns?(projectDir?: string, blueprintId?: string): Promise<Record<string, unknown>[]>

  /** Reserved runtime API for the next status UI pass (desktop only) */
  startBlueprintRun?(
    projectDir: string,
    blueprintId: string,
    plan: Record<string, unknown>,
    executionMode?: "status" | "live",
  ): Promise<Record<string, unknown>>

  /** Reserved runtime API for the next status UI pass (desktop only) */
  blueprintRunStatus?(runId: string): Promise<Record<string, unknown>>

  /** Read the current run-scoped blueprint changeset diff summary (desktop only) */
  blueprintRunDiff?(runId: string): Promise<Record<string, unknown>>

  /** Read one changeset's blueprint diff detail (desktop only) */
  blueprintChangesetDiff?(runId: string, changesetId: string): Promise<Record<string, unknown>>

  /** Roll back accepted blueprint changesets from the selected changeset through the latest one. */
  rollbackBlueprintChangesets?(runId: string, toChangesetId: string, reason?: string): Promise<Record<string, unknown>>

  /** Restore the latest blueprint rollback marker. */
  restoreBlueprintRollback?(runId: string, rollbackId?: string, reason?: string): Promise<Record<string, unknown>>

  /** Reserved runtime API for the next status UI pass (desktop only) */
  endBlueprintRun?(runId: string, action: BlueprintRunEndAction, reason?: string): Promise<Record<string, unknown>>

  /** Reserved runtime API for the next status UI pass (desktop only) */
  blueprintRecentEvents?(runId: string, limit?: number): Promise<Record<string, unknown>>

  /** Agent detail snapshot for the blueprint canvas hover panel (desktop only) */
  blueprintAgentInfo?(runId: string | undefined, nodeId: string): Promise<Record<string, unknown>>

  /** Queue a user message to one live blueprint AgentNode (desktop only) */
  queueBlueprintAgentMessage?(
    runId: string,
    nodeId: string,
    text: string,
    mode: "default" | "top",
  ): Promise<Record<string, unknown>>

  /** Return a one-time WebSocket URL for live blueprint agent stream events (desktop only) */
  blueprintAgentStreamToken?(runId: string, cursor?: number): Promise<Record<string, unknown>>

  /** Ensure one desktop-session-scoped blueprint planning context (desktop only) */
  ensureBlueprintPlanningContext?(
    projectDir: string,
    blueprintId: string,
    desktopSessionId: string,
  ): Promise<Record<string, unknown>>

  /** Answer or reject a pending blueprint planning question (desktop only) */
  answerBlueprintPlanningQuestion?(
    sessionId: string,
    questionId: string,
    answers: unknown,
    opts?: { rejected?: boolean; reason?: string },
  ): Promise<Record<string, unknown>>

  /** Reject a staged blueprint planning start plan without starting (desktop only) */
  rejectBlueprintPlanningPlan?(sessionId: string, reason?: string): Promise<Record<string, unknown>>

  /** Record that an app-mediated blueprint start consumed the staged plan (desktop only) */
  markBlueprintPlanningPlanStarted?(
    sessionId: string,
    runId: string,
    started?: unknown,
  ): Promise<Record<string, unknown>>

  /** Read the current desktop blueprint planning session snapshot (desktop only) */
  blueprintPlanningStatus?(sessionId: string): Promise<Record<string, unknown>>

  /** End the current desktop blueprint planning session (desktop only) */
  endBlueprintPlanningSession?(sessionId: string, reason?: string): Promise<Record<string, unknown>>

  /** Save a local Agent info panel test snapshot beside desktop logs (desktop only) */
  saveBlueprintAgentPanelTest?(payload: Record<string, unknown>): Promise<Record<string, unknown>>

  /** Open the blueprint panel in an independent desktop window (desktop only) */
  openBlueprintWindow?(projectDir: string, sessionId?: string, rect?: BlueprintWindowRect): Promise<void>

  /** Dock the current independent blueprint window back into the main sidebar (desktop only) */
  dockBlueprintWindow?(projectDir: string, sessionId?: string): Promise<void>

  /** Close the current independent blueprint window (desktop only) */
  closeBlueprintWindow?(): Promise<void>

  /** Forward a blueprint planning task from the independent window to the main session composer. */
  submitBlueprintWindowPlanning?(
    projectDir: string,
    sessionId: string | undefined,
    input: BlueprintWindowPlanningSubmitInput,
  ): Promise<{ accepted: boolean }>

  /** Storage mechanism, defaults to localStorage */
  storage?: (name?: string) => SyncStorage | AsyncStorage

  /** Check for updates (Tauri only) */
  checkUpdate?(): Promise<UpdateInfo>

  /** Install updates (Tauri only) */
  update?(): Promise<void>

  /** Fetch override */
  fetch?: typeof fetch

  /** Get the configured default server URL (platform-specific) */
  getDefaultServer?(): Promise<ServerConnection.Key | null>

  /** Set the default server URL to use on app startup (platform-specific) */
  setDefaultServer?(url: ServerConnection.Key | null): Promise<void> | void

  /** Get the configured WSL integration (desktop only) */
  getWslEnabled?(): Promise<boolean>

  /** Set the configured WSL integration (desktop only) */
  setWslEnabled?(config: boolean): Promise<void> | void

  /** Get the preferred display backend (desktop only) */
  getDisplayBackend?(): Promise<DisplayBackend | null> | DisplayBackend | null

  /** Set the preferred display backend (desktop only) */
  setDisplayBackend?(backend: DisplayBackend): Promise<void>

  /** Parse markdown to HTML using native parser (desktop only, returns unprocessed code blocks) */
  parseMarkdown?(markdown: string): Promise<string>

  /** Webview zoom level (desktop only) */
  webviewZoom?: Accessor<number>

  /** Check if an editor app exists (desktop only) */
  checkAppExists?(appName: string): Promise<boolean>

  /** Read image from clipboard (desktop only) */
  readClipboardImage?(): Promise<File | null>
}

export type DisplayBackend = "auto" | "wayland"

export const { use: usePlatform, provider: PlatformProvider } = createSimpleContext({
  name: "Platform",
  init: (props: { value: Platform }) => {
    return props.value
  },
})
