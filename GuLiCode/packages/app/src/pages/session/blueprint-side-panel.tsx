import { Button } from "@opencode-ai/ui/button"
import { Collapsible } from "@opencode-ai/ui/collapsible"
import { ContextMenu } from "@opencode-ai/ui/context-menu"
import { useDialog } from "@opencode-ai/ui/context/dialog"
import { Dialog } from "@opencode-ai/ui/dialog"
import { DropdownMenu } from "@opencode-ai/ui/dropdown-menu"
import { Icon } from "@opencode-ai/ui/icon"
import { IconButton } from "@opencode-ai/ui/icon-button"
import { Markdown } from "@opencode-ai/ui/markdown"
import { Popover } from "@opencode-ai/ui/popover"
import { Switch as ToggleSwitch } from "@opencode-ai/ui/switch"
import { TextField, type TextFieldProps } from "@opencode-ai/ui/text-field"
import { Tooltip } from "@opencode-ai/ui/tooltip"
import { showToast } from "@opencode-ai/ui/toast"
import { For, Index, Match, Show, Switch, createEffect, createMemo, createSignal, on, onCleanup, onMount, splitProps, untrack, type JSX } from "solid-js"
import { useNavigate, useParams } from "@solidjs/router"
import { base64Encode } from "@opencode-ai/shared/util/encode"
import { createStore, reconcile, type SetStoreFunction } from "solid-js/store"
import { useLanguage } from "@/context/language"
import { useLayout, type BlueprintFloatingRect } from "@/context/layout"
import { BlueprintCollaborationAuthPanel, postDesktopBlueprintSnapshot, type DesktopBlueprintSnapshotPayload } from "@/components/collaboration-auth"
import { Persist, persisted } from "@/utils/persist"
import { decode64 } from "@/utils/base64"
import {
  DEFAULT_INPUT_PORT,
  DEFAULT_OUTPUT_PORT,
  GRID_SIZE,
  addEdge,
  addNode,
  addScriptNode,
  canConnectPorts,
  CLI_KIND_OPTIONS,
  DEFAULT_BLUEPRINT_ID,
  DEFAULT_BLUEPRINT_NAME,
  compileScriptNodesFromCatalog,
  createBlueprintStartPlan,
  createDefaultBlueprintDraft,
  defaultCommandForCliKind,
  defaultModelForCliKind,
  deleteEdge,
  deleteNode,
  deleteSelection,
  fanEdgeGroup,
  jsonText,
  nodeKind,
  hasTickSourceNode,
  parseJsonObject,
  parseScopeText,
  parseStringRecord,
  scopeText,
  setInspector,
  setSelection,
  snapPosition,
  fromBlueprintDocument,
  isAbsoluteBlueprintPath,
  toBlueprintDocument,
  toRuntimeGraphDraft,
  updateEdge,
  updateScriptNode,
  validateBlueprintConfigForStart,
  type BlueprintAddNodeKind,
  type BlueprintAgentNode,
  type BlueprintCliKind,
  type BlueprintConfig,
  type BlueprintConfigField,
  type BlueprintConfigValidationIssue,
  type BlueprintCommonNode,
  type BlueprintDraft,
  type BlueprintEdge,
  type BlueprintNodeLayout,
  type BlueprintRouteNode,
  type BlueprintScriptCompileResult,
  type BlueprintScriptNode,
  type BlueprintScriptPort,
  type BlueprintTerminalKind,
} from "@/pages/session/blueprint-model"
import { createTestAgentPanelSnapshot } from "@/pages/session/blueprint-test-agent-snapshot"
import {
  usePlatform,
  type BlueprintCatalogItem,
  type BlueprintEditorCandidate,
  type BlueprintRelocateConflictPolicy,
  type BlueprintRunEndAction,
  type BlueprintSummary,
} from "@/context/platform"

const NODE_WIDTH = 172
const NODE_HEIGHT = 72
const SCRIPT_NODE_WIDTH = 228
const SCRIPT_NODE_HEADER_HEIGHT = 48
const SCRIPT_NODE_PORT_ROW_HEIGHT = 22
const SCRIPT_NODE_MIN_EXPANDED_HEIGHT = 102
const COMMON_BRANCH_WIDTH = SCRIPT_NODE_WIDTH
const COMMON_BRANCH_HEIGHT = SCRIPT_NODE_MIN_EXPANDED_HEIGHT
const SCRIPT_NODE_BLUE_CLIP_PATH = "polygon(0 0, 42% 0, 55% 30%, 47% 30%, 60% 58%, 52% 58%, 64% 100%, 0 100%)"
const SCRIPT_NODE_SPLIT_LINE_POINTS = "42,0 55,30 47,30 60,58 52,58 64,100"
const TERMINAL_WIDTH = 92
const TERMINAL_HEIGHT = 44
const MIN_ZOOM = 0.35
const MAX_ZOOM = 1.8
const AGENT_PANEL_LONG_PRESS_MS = 500
const AGENT_PANEL_LONG_PRESS_CANCEL_PX = 8
const AGENT_PANEL_PROGRESS_RADIUS = 8
const AGENT_PANEL_PROGRESS_CIRCUMFERENCE = 2 * Math.PI * AGENT_PANEL_PROGRESS_RADIUS
const AGENT_PANEL_DEFAULT_WIDTH = 420
const AGENT_PANEL_DEFAULT_HEIGHT = 620
const AGENT_PANEL_MIN_WIDTH = 320
const AGENT_PANEL_MIN_HEIGHT = 300
const AGENT_PANEL_MARGIN = 8
const BLUEPRINT_FLOAT_DRAG_THRESHOLD = 8
const RIGHT_CLICK_PAN_THRESHOLD = 5
const NODE_SEARCH_CARD_WIDTH = 320
const NODE_SEARCH_CARD_MAX_HEIGHT = 360
const RUNTIME_WORKING_AGENT_STATES = new Set(["dispatching", "running", "waiting_for_reply", "processing_reply"])
const RUNTIME_FLOW_MESSAGE_STATUSES = new Set(["queued", "dispatching"])
const BLUEPRINT_RUNTIME_FLOW_DOTS = [0, 1, 2, 3, 4]
const AUTO_RUNTIME_COMPLETE_REASON = "blueprint UI auto complete after all agents reached terminal task status"
const BLUEPRINT_FLOW_LOCK_PENDING_GRACE_MS = 10_000
let projectWorkdirAutoPromptShownThisApp = false
const BLUEPRINT_THEME = {
  "--background-base": "#0b111b",
  "--background-strong": "#0e1724",
  "--background-stronger": "#071019",
  "--input-base": "rgba(7, 16, 25, 0.96)",
  "--surface-base-hover": "rgba(56, 214, 244, 0.12)",
  "--surface-base-active": "rgba(56, 214, 244, 0.18)",
  "--surface-raised-stronger-non-alpha": "#101a28",
  "--button-secondary-base": "rgba(14, 26, 40, 0.96)",
  "--button-secondary-hover": "rgba(21, 42, 62, 1)",
  "--border-weaker-base": "rgba(91, 141, 171, 0.18)",
  "--border-weak-base": "rgba(106, 164, 199, 0.28)",
  "--border-base": "rgba(112, 191, 225, 0.36)",
  "--border-strong-base": "#37d7f7",
  "--border-weak-selected": "rgba(55, 215, 247, 0.22)",
  "--border-selected": "#37d7f7",
  "--text-strong": "#e8f7ff",
  "--text-base": "#c7d8e5",
  "--text-weak": "#9fb6c8",
  "--text-weaker": "#6f8799",
  "--icon-base": "#78c7e8",
  "--icon-weak": "#557086",
  "--icon-strong-base": "#b9efff",
  "--blueprint-canvas-base": "#071019",
  "--blueprint-grid": "rgba(86, 172, 210, 0.14)",
  "--blueprint-edge": "rgba(125, 211, 252, 0.56)",
  "--blueprint-edge-active": "#67e8f9",
} as JSX.CSSProperties

const BLUEPRINT_CHROME_THEME = {
  "--color-background-base": "#071019",
  "--color-background-strong": "#0b1522",
  "--color-background-stronger": "#0d1826",
  "--color-surface-base-hover": "rgba(56, 214, 244, 0.12)",
  "--color-surface-base-active": "rgba(56, 214, 244, 0.18)",
  "--color-surface-disabled": "rgba(8, 19, 31, 0.72)",
  "--color-button-secondary-base": "rgba(13, 24, 38, 0.98)",
  "--color-button-secondary-hover": "rgba(18, 36, 54, 1)",
  "--color-border-weaker-base": "rgba(103, 232, 249, 0.14)",
  "--color-border-weak-base": "rgba(103, 232, 249, 0.22)",
  "--color-border-disabled": "rgba(103, 232, 249, 0.12)",
  "--color-text-strong": "#f8fdff",
  "--color-text-base": "#d6e9f5",
  "--color-text-weak": "#b8cede",
  "--color-text-weaker": "#95afc4",
  "--color-icon-base": "#d7f7ff",
  "--color-icon-weak": "#a5d8e9",
  "--color-icon-strong-base": "#ffffff",
  "--color-icon-invert-base": "#b8cede",
  "--color-icon-disabled": "#7f9db2",
  "--color-icon-strong-disabled": "rgba(127, 157, 178, 0.28)",
  "--background-base": "#071019",
  "--background-strong": "#0b1522",
  "--background-stronger": "#0d1826",
  "--surface-base-hover": "rgba(56, 214, 244, 0.12)",
  "--surface-base-active": "rgba(56, 214, 244, 0.18)",
  "--surface-disabled": "rgba(8, 19, 31, 0.72)",
  "--button-secondary-base": "rgba(13, 24, 38, 0.98)",
  "--button-secondary-hover": "rgba(18, 36, 54, 1)",
  "--border-weaker-base": "rgba(103, 232, 249, 0.14)",
  "--border-weak-base": "rgba(103, 232, 249, 0.22)",
  "--border-disabled": "rgba(103, 232, 249, 0.12)",
  "--text-strong": "#f8fdff",
  "--text-base": "#d6e9f5",
  "--text-weak": "#b8cede",
  "--text-weaker": "#95afc4",
  "--icon-base": "#d7f7ff",
  "--icon-weak": "#a5d8e9",
  "--icon-strong-base": "#ffffff",
  "--icon-invert-base": "#b8cede",
  "--icon-disabled": "#7f9db2",
  "--icon-strong-disabled": "rgba(127, 157, 178, 0.28)",
} as JSX.CSSProperties

const BLUEPRINT_INSPECTOR_THEME = {
  "--color-background-base": "#071019",
  "--color-background-strong": "#0b1522",
  "--color-background-stronger": "#0d1826",
  "--color-input-base": "rgba(6, 14, 23, 0.98)",
  "--color-surface-base-hover": "rgba(56, 214, 244, 0.12)",
  "--color-surface-base-active": "rgba(56, 214, 244, 0.18)",
  "--color-border-weaker-base": "rgba(103, 232, 249, 0.14)",
  "--color-border-weak-base": "rgba(103, 232, 249, 0.22)",
  "--color-border-base": "rgba(103, 232, 249, 0.34)",
  "--color-border-strong-base": "#67e8f9",
  "--color-text-strong": "#f8fdff",
  "--color-text-base": "#d6e9f5",
  "--color-text-weak": "#b8cede",
  "--color-text-weaker": "#95afc4",
  "--color-icon-base": "#d7f7ff",
  "--color-icon-weak": "#a5d8e9",
  "--color-icon-strong-base": "#ffffff",
  "--background-base": "#071019",
  "--background-strong": "#0b1522",
  "--background-stronger": "#0d1826",
  "--input-base": "rgba(6, 14, 23, 0.98)",
  "--surface-base-hover": "rgba(56, 214, 244, 0.12)",
  "--surface-base-active": "rgba(56, 214, 244, 0.18)",
  "--button-secondary-base": "rgba(13, 24, 38, 0.98)",
  "--button-secondary-hover": "rgba(18, 36, 54, 1)",
  "--border-weaker-base": "rgba(103, 232, 249, 0.14)",
  "--border-weak-base": "rgba(103, 232, 249, 0.22)",
  "--border-base": "rgba(103, 232, 249, 0.34)",
  "--border-strong-base": "#67e8f9",
  "--border-weak-selected": "rgba(103, 232, 249, 0.22)",
  "--border-selected": "#67e8f9",
  "--text-strong": "#f8fdff",
  "--text-base": "#d6e9f5",
  "--text-weak": "#b8cede",
  "--text-weaker": "#95afc4",
  "--icon-base": "#d7f7ff",
  "--icon-weak": "#a5d8e9",
  "--icon-strong-base": "#ffffff",
} as JSX.CSSProperties

const MODEL_LIST_FALLBACKS: Record<string, string[]> = {
  codemaker: ["netease-codemaker/kimi-k2.5"],
  codex: ["gpt-5.4"],
}

export type CatalogState = {
  skillDir: string
  ruleDir: string
  scriptDir: string
  skills: BlueprintCatalogItem[]
  rules: BlueprintCatalogItem[]
  scriptNodes: BlueprintScriptCatalogNode[]
  skillError?: string
  ruleError?: string
  scriptError?: string
}

export type BlueprintScriptCatalogNode = BlueprintScriptNode

export type ModelCatalogState = {
  cliKind: string
  models: string[]
  loading: boolean
  error?: string
}

type PersistenceState = {
  loaded: boolean
  loading: boolean
  saving: boolean
  source: "local" | "project"
  error?: string
}

type BlueprintHeaderStatusState = {
  tone: "loading" | "saving" | "error"
  title: string
  label: string
  detail: string
}

type RuntimePanelMode = "runtime" | "inspector"

export type BlueprintPlanningSubmitInput = {
  task: string
  blueprintId: string
  blueprintName: string
  startNodeIds: string[]
  message: string
  silentBlocked?: boolean
}

export type BlueprintPlanningSubmitResult =
  | boolean
  | {
      accepted: boolean
      requestId?: string
      status?: string
      message?: string
    }

export type BlueprintPlanningProgressPhase = "planning" | "start"
export type BlueprintPlanningProgressState = {
  active: boolean
  phase?: BlueprintPlanningProgressPhase
}

type BlueprintProgressPhase = BlueprintPlanningProgressPhase | "summary" | "ending"
type BlueprintFlowLockState = {
  active: boolean
  planningSeen?: boolean
  startSeen?: boolean
  submittedAt?: number
}

type BlueprintDocumentPickerState = {
  id: string
  name: string
  items: BlueprintSummary[]
  loading: boolean
  error?: string
}

const blueprintFlowLockStore = new Map<string, BlueprintFlowLockState>()
const blueprintRuntimeManualUnlockKeys = new Set<string>()
const autoCompletedRuntimeKeys = new Set<string>()

type BlueprintRuntimeStartNodeOption = {
  id: string
  label: string
  description: string
}

type RuntimePanelId = "planning" | "status" | "overview" | "agents" | "queues" | "outgoing" | "workspace" | "events"
type WorkspacePanelArea = "changesets" | "artifacts" | "reports"

type WorkspacePanelItem = {
  name: string
  path?: string
  absolutePath?: string
  detail?: string
}

const DEFAULT_RUNTIME_PANEL_ORDER: RuntimePanelId[] = [
  "planning",
  "status",
  "overview",
  "agents",
  "queues",
  "outgoing",
  "workspace",
  "events",
]

type RuntimePanelDragState = {
  id: RuntimePanelId
  pointerId: number
  x: number
  y: number
  offsetX: number
  offsetY: number
  width: number
  height: number
}

type BlueprintRuntimeState = {
  runId?: string
  runs: Record<string, unknown>[]
  status?: Record<string, unknown>
  explanation?: Record<string, unknown>
  events: Record<string, unknown>[]
  plan?: Record<string, unknown>
  planValidation?: Record<string, unknown>
  planningRequest?: {
    requestId: string
    status: string
    summary?: string
    message?: string
  }
  loading: boolean
  action?: string
  error?: string
  lastUpdatedAt?: number
}

export type BlueprintDiffFile = {
  file: string
  patch: string
  additions: number
  deletions: number
  status?: "added" | "deleted" | "modified"
}

export type BlueprintDiffSyncPayload = {
  runId: string
  changesetIds: string[]
  acceptedDiffs: BlueprintDiffFile[]
}

type BlueprintDiffChangeset = {
  changesetId: string
  status: string
  agentId?: string
  taskId?: string
  summary?: string
  fileCount: number
  textFileCount: number
  binaryFileCount: number
  additions: number
  deletions: number
  patchExists: boolean
  reversible: boolean
  restorable: boolean
  rollbackable: boolean
  rollbackId?: string
  rolledBackAt?: string
  rollbackDisabledReason?: string
}

type BlueprintChangesetDiffDetail = {
  changesetId: string
  status: string
  diffs: BlueprintDiffFile[]
  binaryFiles: Record<string, unknown>[]
  metadata: Record<string, unknown>
}

type BlueprintDiffState = {
  loading: boolean
  error?: string
  summary: Record<string, unknown>
  changesets: BlueprintDiffChangeset[]
  acceptedDiffs: BlueprintDiffFile[]
  binaryFiles: Record<string, unknown>[]
  detailLoading?: string
  rollingBack?: string
  restoringRollback?: boolean
  details: Record<string, BlueprintChangesetDiffDetail | undefined>
}

function emptyBlueprintDiffState(): BlueprintDiffState {
  return {
    loading: false,
    summary: {},
    changesets: [],
    acceptedDiffs: [],
    binaryFiles: [],
    details: {},
  }
}

type AgentStreamEvent = Record<string, unknown> & {
  seq?: number
  kind?: string
  node_id?: string
  message_id?: string
  part_type?: string
  delta?: string
  text?: string
  status?: string
}

type AgentPanelDisplayEvent = {
  id: string
  kind: string
  seq?: number
  status?: string
  text: string
  tone?: "user" | "reply" | "reasoning" | "tool" | "error" | "event"
  collapsible?: boolean
  detail?: string
  order?: number
  toolCategory?: AgentPanelToolCategory
  toolItems?: AgentPanelDisplayEvent[]
}

type AgentPanelToolCategory = "mcp" | "command" | "codex" | "mixed"

type AgentPanelUserMessage = {
  id: string
  runId?: string
  runtimeMessageId?: string
  nodeId: string
  mode: "default" | "top"
  text: string
  status: "queued" | "sent" | "dispatching" | "running" | "succeeded" | "failed"
  runtimeStatus?: string
  created_at: string
  sent_at?: string
  completed_at?: string
  failed_at?: string
  error?: string
}

type AgentPanelTimelineItem =
  | { type: "user"; message: AgentPanelUserMessage; order: number; index: number }
  | { type: "event"; event: AgentStreamEvent; order: number; index: number }

type AgentPanelToolGroup = {
  id: string
  order: number
  tools: AgentPanelDisplayEvent[]
  toolIds: Set<string>
}

type AgentPanelEntry = {
  nodeId: string
  pinned: boolean
  x: number
  y: number
  width: number
  height: number
  input: string
  mode: "default" | "top"
  sending: boolean
  error?: string
  info?: Record<string, unknown>
  userMessages?: AgentPanelUserMessage[]
  testJsonPath?: string
  testJsonPending?: boolean
  testJsonError?: string
}

type AgentPanelState = {
  panels: Record<string, AgentPanelEntry>
  streamEvents: Record<string, AgentStreamEvent[]>
  streamCursor: number
  streamError?: string
}

const INSPECTOR_TIPS = {
  nodeId: {
    what: "blueprint.tip.nodeId.what",
    usage: "blueprint.tip.nodeId.usage",
  },
  agentId: {
    what: "blueprint.tip.agentId.what",
    usage: "blueprint.tip.agentId.usage",
  },
  prompt: {
    what: "blueprint.tip.prompt.what",
    usage: "blueprint.tip.prompt.usage",
  },
  runPrompt: {
    what: "blueprint.tip.runPrompt.what",
    usage: "blueprint.tip.runPrompt.usage",
  },
  executionMode: {
    what: "blueprint.tip.executionMode.what",
    usage: "blueprint.tip.executionMode.usage",
  },
  cliKind: {
    what: "blueprint.tip.cliKind.what",
    usage: "blueprint.tip.cliKind.usage",
  },
  command: {
    what: "blueprint.tip.command.what",
    usage: "blueprint.tip.command.usage",
  },
  model: {
    what: "blueprint.tip.model.what",
    usage: "blueprint.tip.model.usage",
  },
  cwd: {
    what: "blueprint.tip.cwd.what",
    usage: "blueprint.tip.cwd.usage",
  },
  pythonPath: {
    what: "blueprint.tip.pythonPath.what",
    usage: "blueprint.tip.pythonPath.usage",
  },
  projectWorkdir: {
    what: "blueprint.tip.projectWorkdir.what",
    usage: "blueprint.tip.projectWorkdir.usage",
  },
  skillDir: {
    what: "blueprint.tip.skillDir.what",
    usage: "blueprint.tip.skillDir.usage",
  },
  ruleDir: {
    what: "blueprint.tip.ruleDir.what",
    usage: "blueprint.tip.ruleDir.usage",
  },
  timeoutSec: {
    what: "blueprint.tip.timeoutSec.what",
    usage: "blueprint.tip.timeoutSec.usage",
  },
  promptViaFile: {
    what: "blueprint.tip.promptViaFile.what",
    usage: "blueprint.tip.promptViaFile.usage",
  },
  external: {
    what: "blueprint.tip.external.what",
    usage: "blueprint.tip.external.usage",
  },
  directProjectIo: {
    what: "blueprint.tip.directProjectIo.what",
    usage: "blueprint.tip.directProjectIo.usage",
  },
  outsideProjectIo: {
    what: "blueprint.tip.outsideProjectIo.what",
    usage: "blueprint.tip.outsideProjectIo.usage",
  },
  unrestrictedCommands: {
    what: "blueprint.tip.unrestrictedCommands.what",
    usage: "blueprint.tip.unrestrictedCommands.usage",
  },
  disableSandbox: {
    what: "blueprint.tip.disableSandbox.what",
    usage: "blueprint.tip.disableSandbox.usage",
  },
  frameworkMessageTools: {
    what: "blueprint.tip.frameworkMessageTools.what",
    usage: "blueprint.tip.frameworkMessageTools.usage",
  },
  skills: {
    what: "blueprint.tip.skills.what",
    usage: "blueprint.tip.skills.usage",
  },
  skillSelection: {
    what: "blueprint.tip.skillSelection.what",
    usage: "blueprint.tip.skillSelection.usage",
  },
  rulePaths: {
    what: "blueprint.tip.rulePaths.what",
    usage: "blueprint.tip.rulePaths.usage",
  },
  readScope: {
    what: "blueprint.tip.readScope.what",
    usage: "blueprint.tip.readScope.usage",
  },
  writeScope: {
    what: "blueprint.tip.writeScope.what",
    usage: "blueprint.tip.writeScope.usage",
  },
  artifactScope: {
    what: "blueprint.tip.artifactScope.what",
    usage: "blueprint.tip.artifactScope.usage",
  },
  workspaceId: {
    what: "blueprint.tip.workspaceId.what",
    usage: "blueprint.tip.workspaceId.usage",
  },
  workspaceRoot: {
    what: "blueprint.tip.workspaceRoot.what",
    usage: "blueprint.tip.workspaceRoot.usage",
  },
  adapterOptions: {
    what: "blueprint.tip.adapterOptions.what",
    usage: "blueprint.tip.adapterOptions.usage",
  },
  extraEnv: {
    what: "blueprint.tip.extraEnv.what",
    usage: "blueprint.tip.extraEnv.usage",
  },
  routeKind: {
    what: "blueprint.tip.routeKind.what",
    usage: "blueprint.tip.routeKind.usage",
  },
  targets: {
    what: "blueprint.tip.targets.what",
    usage: "blueprint.tip.targets.usage",
  },
  reduceTarget: {
    what: "blueprint.tip.reduceTarget.what",
    usage: "blueprint.tip.reduceTarget.usage",
  },
  reducePrompt: {
    what: "blueprint.tip.reducePrompt.what",
    usage: "blueprint.tip.reducePrompt.usage",
  },
  everyNSeconds: {
    what: "blueprint.tip.everyNSeconds.what",
    usage: "blueprint.tip.everyNSeconds.usage",
  },
  edge: {
    what: "blueprint.tip.edge.what",
    usage: "blueprint.tip.edge.usage",
  },
  edgeType: {
    what: "blueprint.tip.edgeType.what",
    usage: "blueprint.tip.edgeType.usage",
  },
  outputPort: {
    what: "blueprint.tip.outputPort.what",
    usage: "blueprint.tip.outputPort.usage",
  },
  inputPort: {
    what: "blueprint.tip.inputPort.what",
    usage: "blueprint.tip.inputPort.usage",
  },
  terminalKind: {
    what: "blueprint.tip.terminalKind.what",
    usage: "blueprint.tip.terminalKind.usage",
  },
} as const

type InspectorTipKey = keyof typeof INSPECTOR_TIPS

type DragState =
  | {
      type: "pan-pending"
      startClientX: number
      startClientY: number
      startX: number
      startY: number
    }
  | {
      type: "pan"
      startClientX: number
      startClientY: number
      startX: number
      startY: number
    }
  | {
      type: "node"
      id: string
      startClientX: number
      startClientY: number
      startX: number
      startY: number
      zoom: number
    }
  | {
      type: "agent-panel-move"
      nodeId: string
      startClientX: number
      startClientY: number
      startX: number
      startY: number
      width: number
      height: number
    }
  | {
      type: "agent-panel-resize"
      nodeId: string
      startClientX: number
      startClientY: number
      startX: number
      startY: number
      startWidth: number
      startHeight: number
    }

type ConnectionState = {
  source: string
  output_port: string
  pointer?: BlueprintNodeLayout
}

type AgentPanelPressState = {
  nodeId: string
  progress: number
}

type NodeSearchState = {
  clientX: number
  clientY: number
}

type ScriptEditorPreferences = {
  editorId: string
}

type EditorCatalogState = {
  items: BlueprintEditorCandidate[]
  loading: boolean
  error?: string
}

type NodeItem =
  | {
      type: "terminal"
      id: string
      kind: BlueprintTerminalKind
    }
  | {
      type: "route"
      id: string
      node: BlueprintRouteNode
    }
  | {
      type: "common"
      id: string
      node: BlueprintCommonNode
    }
  | {
      type: "agent"
      id: string
      node: BlueprintAgentNode
    }
  | {
      type: "script"
      id: string
      node: BlueprintScriptNode
    }

type AddNodeOption =
  | {
      kind: Exclude<BlueprintAddNodeKind, "script">
      label: string
      description: string
    }
  | {
      kind: "script"
      label: string
      description: string
      script: BlueprintScriptCatalogNode
    }

type RuntimeNodeVisualState = "idle" | "active" | "working"
type BlueprintPanelLayoutView = Pick<ReturnType<ReturnType<typeof useLayout>["view"]>, "blueprintPanel">

export function BlueprintSidePanel(props: {
  floating?: boolean
  initialBlueprintId?: string
  floatingRect?: BlueprintFloatingRect
  onFloat?: (rect?: Partial<BlueprintFloatingRect>) => void
  onDock?: () => void
  onFloatingRectChange?: (rect: Partial<BlueprintFloatingRect>) => void
  blueprintPlanningProgress?: BlueprintPlanningProgressState
  blueprintPlanningActiveRun?: Record<string, unknown>
  onBlueprintPlanningSubmit?: (input: BlueprintPlanningSubmitInput) => BlueprintPlanningSubmitResult | Promise<BlueprintPlanningSubmitResult>
  onBlueprintDiffChanged?: (payload: BlueprintDiffSyncPayload) => void
} = {}) {
  const language = useLanguage()
  const platform = usePlatform()
  const layout = props.floating ? undefined : useLayout()
  const navigate = useNavigate()
  const dialog = useDialog()
  const params = useParams()
  const sessionKey = createMemo(() => `${params.dir}${params.id ? "/" + params.id : ""}`)
  const standaloneView = {
    blueprintPanel: {
      opened: () => true,
      floating: () => true,
      floatingRect: () => props.floatingRect ?? { x: 0, y: 0, width: 0, height: 0 },
      open: () => undefined,
      close: () => undefined,
      toggle: () => undefined,
      float: () => undefined,
      dock: () => undefined,
      move: () => undefined,
    },
  } satisfies BlueprintPanelLayoutView
  const view = createMemo<BlueprintPanelLayoutView>(
    () =>
      layout?.view(sessionKey) ?? standaloneView,
  )
  const projectDirectory = decode64(params.dir) ?? "global"
  const routeInitialBlueprintId = () => props.initialBlueprintId?.trim() || ""
  const initialBlueprintId = () => routeInitialBlueprintId() || DEFAULT_BLUEPRINT_ID
  const initialBlueprintName = () =>
    initialBlueprintId() === DEFAULT_BLUEPRINT_ID ? DEFAULT_BLUEPRINT_NAME : initialBlueprintId()
  const [blueprintPicker, setBlueprintPicker] = createSignal<BlueprintDocumentPickerState>({
    id: initialBlueprintId(),
    name: initialBlueprintName(),
    items: [],
    loading: false,
  })
  const currentBlueprintId = () => blueprintPicker().id || DEFAULT_BLUEPRINT_ID
  const currentBlueprintName = () => blueprintPicker().name || DEFAULT_BLUEPRINT_NAME
  const blueprintFlowLockKey = () => `${projectDirectory}:${currentBlueprintId()}`
  const [draft, setDraft, _, draftReady] = persisted(
    Persist.workspace(projectDirectory, "blueprint-draft.v1"),
    createStore<BlueprintDraft>(createDefaultBlueprintDraft(projectDirectory)),
  )
  const [testLogPreferences, setTestLogPreferences] = persisted(
    Persist.global("blueprint-agent-panel-test-log.v1"),
    createStore({ enabled: true }),
  )
  const [scriptEditorPreferences, setScriptEditorPreferences] = persisted(
    Persist.global("blueprint.scriptEditor.v1"),
    createStore<ScriptEditorPreferences>({ editorId: "" }),
  )
  const [drag, setDrag] = createSignal<DragState>()
  const [connection, setConnection] = createSignal<ConnectionState>()
  const [agentPanelPress, setAgentPanelPress] = createSignal<AgentPanelPressState>()
  const [nodeSearch, setNodeSearch] = createSignal<NodeSearchState>()
  const [nodeSearchQuery, setNodeSearchQuery] = createSignal("")
  const [scriptEditorMenuOpen, setScriptEditorMenuOpen] = createSignal(false)
  const [globalConfigOpen, setGlobalConfigOpen] = createSignal(false)
  const [catalogRefreshVersion, setCatalogRefreshVersion] = createSignal(0)
  const [scriptCompiling, setScriptCompiling] = createSignal(false)
  const [configIssues, setConfigIssues] = createSignal<BlueprintConfigValidationIssue[]>([])
  const [pythonDetecting, setPythonDetecting] = createSignal(false)
  const [pythonDetectFailed, setPythonDetectFailed] = createSignal(false)
  const [projectWorkdirRelocating, setProjectWorkdirRelocating] = createSignal(false)
  const [blueprintFlowLock, writeBlueprintFlowLock] = createSignal<BlueprintFlowLockState>(
    blueprintFlowLockStore.get(blueprintFlowLockKey()) ?? { active: false },
  )
  const [autoCompletingRuntimeKey, setAutoCompletingRuntimeKey] = createSignal<string>()
  const [progressAnchorVersion, setProgressAnchorVersion] = createSignal(0)
  const [runtimeManualUnlockVersion, setRuntimeManualUnlockVersion] = createSignal(0)
  const [catalog, setCatalog] = createSignal<CatalogState>({
    skillDir: "",
    ruleDir: "",
    scriptDir: "",
    skills: [],
    rules: [],
    scriptNodes: [],
  })
  const [modelCatalog, setModelCatalog] = createSignal<ModelCatalogState>({
    cliKind: "",
    models: [],
    loading: false,
  })
  const [editorCatalog, setEditorCatalog] = createSignal<EditorCatalogState>({
    items: [
      {
        id: "system",
        label: language.t("blueprint.editor.systemDefault" as never),
        source: language.t("blueprint.editor.systemDefaultDescription" as never),
        systemDefault: true,
      },
    ],
    loading: false,
  })
  const [persistence, setPersistence] = createSignal<PersistenceState>({
    loaded: false,
    loading: false,
    saving: false,
    source: "local",
  })
  const [runtime, setRuntime] = createSignal<BlueprintRuntimeState>({
    runs: [],
    events: [],
    loading: false,
  })
  const [planningCancelPending, setPlanningCancelPending] = createSignal(false)
  const planningCancelledRequestIds = new Set<string>()
  const [blueprintDiffOpen, setBlueprintDiffOpen] = createSignal(false)
  const [blueprintDiffSelectedChangesetId, setBlueprintDiffSelectedChangesetId] = createSignal<string>()
  const [blueprintDiff, setBlueprintDiff] = createStore<BlueprintDiffState>(emptyBlueprintDiffState())
  const [runtimeTask, setRuntimeTask] = createSignal("")
  const [runtimeStartNodeIds, setRuntimeStartNodeIds] = createSignal<string[]>([])
  const [hoveredEdgeGroupId, setHoveredEdgeGroupId] = createSignal<string>()
  const [agentPanel, setAgentPanel] = createStore<AgentPanelState>({
    panels: {},
    streamEvents: {},
    streamCursor: 0,
  })
  const agentPanelTestLogActive = () => testLogPreferences.enabled !== false && Boolean(platform.saveBlueprintAgentPanelTest)
  const [panelMode, setPanelMode] = createSignal<RuntimePanelMode | undefined>("runtime")
  const runtimePanelOpen = () => panelMode() === "runtime"
  const [workspacePanelArea, setWorkspacePanelArea] = createSignal<WorkspacePanelArea>()
  const runtimeWorkspace = createMemo(() => asRecord(asRecord(runtime().status)?.workspace))
  const blueprintDiffAvailable = createMemo(() => !!runtime().runId && !!platform.blueprintRunDiff)
  const blueprintDiffButtonLabel = createMemo(() => {
    const conflict = blueprintDiffSummaryCount(blueprintDiff.summary, "conflict")
    const pending = blueprintDiffSummaryCount(blueprintDiff.summary, "pending")
    const total = blueprintDiffSummaryCount(blueprintDiff.summary, "total")
    const accepted = blueprintDiffSummaryCount(blueprintDiff.summary, "accepted")
    if (conflict > 0) return language.t("blueprint.diff.conflictCount" as never, { count: conflict } as never)
    if (pending > 0) return language.t("blueprint.diff.pendingCount" as never, { count: pending } as never)
    if (accepted > 0 || total > 0) {
      return language.t("blueprint.diff.buttonCount" as never, { count: accepted || total } as never)
    }
    return language.t("blueprint.diff.button" as never)
  })
  let rootRef: HTMLDivElement | undefined
  let canvasRef: HTMLDivElement | undefined
  let nodeSearchInputRef: HTMLInputElement | undefined
  let runtimeTaskInputRef: HTMLTextAreaElement | undefined
  let saveTimer: ReturnType<typeof setTimeout> | undefined
  const testAgentPersistTimers: Record<string, ReturnType<typeof setTimeout> | undefined> = {}
  const testAgentPersistRunning: Record<string, boolean | undefined> = {}
  const testAgentPersistQueued: Record<string, boolean | undefined> = {}
  let agentPanelPressFrame: number | undefined
  let previousBlueprintDiffRunId: string | undefined
  let previousAcceptedDiffSignature: string | undefined
  let syncedAcceptedDiffSignature: string | undefined
  let agentPanelLongPress:
    | {
        nodeId: string
        pointerId: number
        startClientX: number
        startClientY: number
        startedAt: number
      }
    | undefined
  let applyingRemote = false

  onCleanup(() => {
    clearAgentPanelTestPersistTimers()
  })

  createEffect(
    on(nodeSearch, (state) => {
      if (!state) return
      queueMicrotask(() => nodeSearchInputRef?.focus())
    }),
  )

  createEffect(() => {
    if (agentPanelTestLogActive()) return
    clearAgentPanelTestPersistTimers()
    for (const nodeId of Object.keys(agentPanel.panels)) {
      if (agentPanel.panels[nodeId]?.testJsonPending) setAgentPanel("panels", nodeId, "testJsonPending", false)
    }
  })

  function setBlueprintFlowLock(
    next: BlueprintFlowLockState | ((current: BlueprintFlowLockState) => BlueprintFlowLockState),
  ) {
    writeBlueprintFlowLock((current) => {
      const resolved = typeof next === "function" ? next(current) : next
      const key = blueprintFlowLockKey()
      if (resolved.active) blueprintFlowLockStore.set(key, resolved)
      else blueprintFlowLockStore.delete(key)
      return resolved
    })
  }

  createEffect(() => {
    currentBlueprintId()
    writeBlueprintFlowLock(blueprintFlowLockStore.get(blueprintFlowLockKey()) ?? { active: false })
  })

  function unlockRuntimeForManualControl(runId: string) {
    blueprintRuntimeManualUnlockKeys.add(runId)
    setRuntimeManualUnlockVersion((version) => version + 1)
  }

  function clearRuntimeManualUnlock(runId: string) {
    if (!blueprintRuntimeManualUnlockKeys.delete(runId)) return
    setRuntimeManualUnlockVersion((version) => version + 1)
  }

  function clearRuntimeStartPlan() {
    setRuntime((current) => ({
      ...current,
      plan: undefined,
      planValidation: undefined,
      planningRequest: undefined,
    }))
  }

  function planningProgressActive() {
    return props.blueprintPlanningProgress?.active === true
  }

  const addOptions = createMemo<AddNodeOption[]>(() => [
    {
      kind: "agent" as const,
      label: language.t("blueprint.node.agent"),
      description: language.t("blueprint.add.agent.description"),
    },
    {
      kind: "worker-agent" as const,
      label: language.t("blueprint.node.workerAgent" as never),
      description: language.t("blueprint.add.workerAgent.description" as never),
    },
    {
      kind: "branch" as const,
      label: language.t("blueprint.node.branch" as never),
      description: language.t("blueprint.add.branch.description" as never),
    },
    {
      kind: "tick" as const,
      label: language.t("blueprint.node.tick" as never),
      description: language.t("blueprint.add.tick.description" as never),
    },
    {
      kind: "route-sequence" as const,
      label: language.t("blueprint.node.route.sequence"),
      description: language.t("blueprint.add.route.sequence.description"),
    },
    {
      kind: "route-parallel" as const,
      label: language.t("blueprint.node.route.parallel"),
      description: language.t("blueprint.add.route.parallel.description"),
    },
    {
      kind: "route-parallel-reduce" as const,
      label: language.t("blueprint.node.route.parallelReduce"),
      description: language.t("blueprint.add.route.parallelReduce.description"),
    },
    ...catalog().scriptNodes.map((script) => ({
      kind: "script" as const,
      label: script.title || script.function_name || language.t("blueprint.node.script" as never),
      description: scriptSignature(script),
      script,
    })),
  ])

  const scriptEditorCandidates = createMemo(() => {
    const fallback: BlueprintEditorCandidate = {
      id: "system",
      label: language.t("blueprint.editor.systemDefault" as never),
      source: language.t("blueprint.editor.systemDefaultDescription" as never),
      systemDefault: true,
    }
    const items = editorCatalog().items.length ? editorCatalog().items : [fallback]
    const selectedId = scriptEditorPreferences.editorId
    if (!selectedId) return items
    const selected = items.find((item) => item.id === selectedId)
    if (!selected) return items
    return [selected, ...items.filter((item) => item.id !== selectedId)]
  })

  const selectedScriptEditor = createMemo(() => {
    const items = editorCatalog().items
    const selectedId = scriptEditorPreferences.editorId
    return (
      items.find((item) => item.id === selectedId) ??
      items.find((item) => !item.systemDefault) ??
      items[0] ?? {
        id: "system",
        label: language.t("blueprint.editor.systemDefault" as never),
        source: language.t("blueprint.editor.systemDefaultDescription" as never),
        systemDefault: true,
      }
    )
  })

  const filteredAddOptions = createMemo(() => {
    const query = nodeSearchQuery().trim().toLowerCase()
    if (!query) return addOptions()
    return addOptions().filter((option) => {
      const haystack = [
        option.label,
        option.description,
        option.kind === "script" ? option.script.function_name : "",
        option.kind === "script" ? option.script.module_path : "",
        option.kind === "script" ? option.script.description : "",
      ]
        .join(" ")
        .toLowerCase()
      return haystack.includes(query)
    })
  })

  const nodes = createMemo<NodeItem[]>(() => [
    ...Object.entries(draft.graph.route_nodes ?? {}).map(([id, node]) => ({
      id,
      node,
      type: "route" as const,
    })),
    ...Object.entries(draft.graph.common_nodes ?? {}).map(([id, node]) => ({
      id,
      node,
      type: "common" as const,
    })),
    ...Object.entries(draft.graph.script_nodes ?? {}).map(([id, node]) => ({
      id,
      node,
      type: "script" as const,
    })),
    ...Object.entries(draft.graph.agent_nodes).map(([id, node]) => ({
      id,
      node,
      type: "agent" as const,
    })),
  ])
  const visibleNodeIds = createMemo(() => new Set(nodes().map((node) => node.id)))
  const visibleEdges = createMemo(() =>
    draft.graph.edges.filter((edge) => visibleNodeIds().has(edge.from) && visibleNodeIds().has(edge.to)),
  )
  const visibleEdgeGroups = createMemo(() => {
    const visible = visibleEdges()
    const visibleIds = new Set(visible.map((edge) => edge.id))
    const seen = new Set<string>()
    const groups: Array<{ id: string; edges: BlueprintEdge[] }> = []
    for (const edge of visible) {
      if (seen.has(edge.id)) continue
      const group = fanEdgeGroup(draft, edge).filter((item) => visibleIds.has(item.id))
      const edges = group.length ? group : [edge]
      for (const item of edges) seen.add(item.id)
      groups.push({
        id: edges.map((item) => item.id).sort().join("|"),
        edges,
      })
    }
    return groups
  })
  const incomingNodeIds = createMemo(() => new Set(visibleEdges().map((edge) => edge.to)))
  const outgoingNodeIds = createMemo(() => new Set(visibleEdges().map((edge) => edge.from)))
  const runtimeRunActive = createMemo(() => {
    const status = runtimeStatus(runtime().status)
    return status === "running" && !isTerminalRuntimeStatus(status)
  })
  const runtimeRunRecord = createMemo(() => asRecord(asRecord(runtime().status)?.run))
  const runtimeSummaryReady = createMemo(() => runtimeRunRecord()?.ready_for_top_agent_summary === true)
  const runtimeSummaryKey = createMemo(() => {
    const runId = runtime().runId
    const run = runtimeRunRecord()
    if (!runId || run?.ready_for_top_agent_summary !== true) return
    const generation = run.ready_for_top_agent_summary_generation ?? run.summary_generation ?? "latest"
    return `${runId}:${String(generation)}`
  })
  const runtimeStarted = createMemo(() => {
    const status = runtimeStatus(runtime().status)
    return !!runtime().runId && status === "running"
  })
  const runtimeSummaryLockActive = createMemo(() => {
    runtimeManualUnlockVersion()
    const runId = runtime().runId
    const status = runtimeStatus(runtime().status)
    return runtimeSummaryReady() && !!runId && !!status && !isTerminalRuntimeStatus(status) && !blueprintRuntimeManualUnlockKeys.has(runId)
  })
  const blueprintFlowLockActive = createMemo(
    () => blueprintFlowLock().active || runtimeSummaryLockActive() || !!autoCompletingRuntimeKey() || runtime().action === "complete",
  )
  const externalBlueprintProgressPhase = createMemo(() =>
    props.blueprintPlanningProgress?.active ? props.blueprintPlanningProgress.phase : undefined,
  )
  const blueprintProgressPhase = createMemo<BlueprintProgressPhase | undefined>(() => {
    if (!blueprintFlowLockActive()) return undefined
    const action = runtime().action
    if (autoCompletingRuntimeKey() || action === "complete") return "ending"
    if (runtimeSummaryReady()) return "summary"
    if (runtimeStarted()) return undefined
    const external = externalBlueprintProgressPhase()
    if (external) return external
    if (action === "plan") return "planning"
    return "planning"
  })
  const blueprintPlanningRequestCancelAvailable = createMemo(() => {
    const request = runtime().planningRequest
    return (
      blueprintProgressPhase() === "planning" &&
      !!request?.requestId &&
      isBlueprintPlanningRequestActive(request.status) &&
      !!platform.cancelBlueprintWindowPlanning
    )
  })
  const blueprintProgressHudStyle = createMemo<JSX.CSSProperties>(() => {
    progressAnchorVersion()
    const rootRect = rootRef?.getBoundingClientRect()
    const canvasRect = canvasRef?.getBoundingClientRect()
    if (!rootRect || !canvasRect) {
      return {
        left: "50%",
        bottom: "2rem",
        transform: "translateX(-50%)",
      }
    }
    return {
      left: `${canvasRect.left - rootRect.left + canvasRect.width / 2}px`,
      bottom: `${Math.max(24, rootRect.bottom - canvasRect.bottom + 24)}px`,
      transform: "translateX(-50%)",
      "max-width": `${Math.max(260, Math.min(680, canvasRect.width - 48))}px`,
    }
  })
  const runtimeAgents = createMemo(() => asRecord(asRecord(runtime().status)?.agents))
  const runtimeNodeVisualStates = createMemo<Record<string, RuntimeNodeVisualState>>(() => {
    if (!runtimeRunActive()) return {}
    const agents = runtimeAgents()
    const states: Record<string, RuntimeNodeVisualState> = {}
    for (const item of nodes()) {
      let state: RuntimeNodeVisualState = "active"
      if (item.type === "agent") {
        const agent = asRecord(agents?.[item.id])
        const agentState = stringValue(agent?.state)
        const busyCount = Number(agent?.busy_count ?? 0)
        if ((agentState && RUNTIME_WORKING_AGENT_STATES.has(agentState)) || busyCount > 0) state = "working"
      }
      states[item.id] = state
    }
    return states
  })
  const runtimeEdgeFlowIds = createMemo(() =>
    runtimeRunActive() ? runtimeEdgeFlows(runtime().status, visibleEdges()) : new Set<string>(),
  )
  const desktopBlueprintSnapshot = createMemo<DesktopBlueprintSnapshotPayload>(() =>
    createDesktopBlueprintSnapshot(
      projectDirectory,
      currentBlueprintId(),
      currentBlueprintName(),
      draft,
      runtimeRunActive() ? runtimeAgents() : undefined,
    ),
  )
  let desktopBlueprintSnapshotTimer: number | undefined
  createEffect(
    on(
      () => (draftReady() ? JSON.stringify(desktopBlueprintSnapshot()) : ""),
      (payloadText) => {
        if (!payloadText || platform.platform !== "desktop") return
        if (desktopBlueprintSnapshotTimer) window.clearTimeout(desktopBlueprintSnapshotTimer)
        desktopBlueprintSnapshotTimer = window.setTimeout(() => {
          void postDesktopBlueprintSnapshot(JSON.parse(payloadText) as DesktopBlueprintSnapshotPayload).catch(() => undefined)
        }, 400)
      },
      { defer: true },
    ),
  )
  onCleanup(() => {
    if (desktopBlueprintSnapshotTimer) window.clearTimeout(desktopBlueprintSnapshotTimer)
  })

  const inspectedAgent = createMemo(() => {
    if (draft.inspector?.type !== "node") return
    return draft.graph.agent_nodes[draft.inspector.id]
  })
  const inspectedRoute = createMemo(() => {
    if (draft.inspector?.type !== "node") return
    return draft.graph.route_nodes?.[draft.inspector.id]
  })
  const inspectedCommon = createMemo(() => {
    if (draft.inspector?.type !== "node") return
    return draft.graph.common_nodes?.[draft.inspector.id]
  })
  const inspectedScript = createMemo(() => {
    if (draft.inspector?.type !== "node") return
    return draft.graph.script_nodes?.[draft.inspector.id]
  })
  const inspectedTerminal = createMemo(() => undefined as BlueprintTerminalKind | undefined)
  const inspectedEdge = createMemo(() => {
    if (draft.inspector?.type !== "edge") return
    return visibleEdges().find((edge) => edge.id === draft.inspector?.id)
  })
  const inspectorOpen = createMemo(
    () => !!inspectedAgent() || !!inspectedRoute() || !!inspectedCommon() || !!inspectedScript() || !!inspectedEdge(),
  )
  const runtimeGraph = createMemo(() => toRuntimeGraphDraft(draft))
  const currentConfig = createMemo(() => ({
    python_path: draft.config?.python_path ?? "",
    project_workdir: draft.config?.project_workdir ?? projectDirectory ?? ".",
    skill_dir: draft.config?.skill_dir ?? "",
    rule_dir: draft.config?.rule_dir ?? "",
  }))
  const runtimeStartNodeOptions = createMemo<BlueprintRuntimeStartNodeOption[]>(() =>
    Object.entries(draft.graph.agent_nodes).map(([id, node]) => {
      const agentName = node.agent_id?.trim()
      return {
        id,
        label: agentName ? `${agentName} (${id})` : id,
        description: node.prompt?.trim() || id,
      }
    }),
  )
  const runtimeBusy = createMemo(
    () => runtime().loading || (!!runtime().runId && !isTerminalRuntimeStatus(runtimeStatus(runtime().status))),
  )
  const runtimeStartPlanReady = createMemo(() => !!runtime().plan && asRecord(runtime().planValidation)?.ok === true)
  const blueprintPlanningBridgeAvailable = createMemo(() => !!props.onBlueprintPlanningSubmit)
  const scriptCompileDisabled = createMemo(
    () => scriptCompiling() || runtimeBusy() || !draftReady() || !platform.listBlueprintScriptNodes,
  )
  const scriptCompileTooltip = createMemo(() => {
    if (scriptCompiling()) return language.t("blueprint.script.compiling" as never)
    if (!platform.listBlueprintScriptNodes || runtimeBusy()) return language.t("blueprint.script.compileUnavailable" as never)
    return language.t("blueprint.script.compile" as never)
  })
  const blueprintConfigLocked = createMemo(() => {
    if (projectWorkdirRelocating() || runtime().loading || persistence().loading) return true
    const runId = runtime().runId
    if (!runId) return false
    return !isTerminalRuntimeStatus(runtimeStatus(runtime().status))
  })
  const headerStatus = createMemo<BlueprintHeaderStatusState | undefined>(() => {
    const state = persistence()
    if (state.loading) {
      const label = language.t("common.loading")
      return {
        tone: "loading",
        title: language.t("blueprint.headerStatus.loadingTitle" as never),
        label,
        detail: language.t("blueprint.headerStatus.loadingDetail" as never),
      }
    }
    if (state.saving) {
      const label = language.t("common.save")
      return {
        tone: "saving",
        title: language.t("blueprint.headerStatus.savingTitle" as never),
        label,
        detail: language.t("blueprint.headerStatus.savingDetail" as never),
      }
    }
    if (state.error) {
      return {
        tone: "error",
        title: language.t("blueprint.headerStatus.errorTitle" as never),
        label: state.error,
        detail: state.error,
      }
    }
    if (blueprintPicker().error) {
      return {
        tone: "error",
        title: language.t("blueprint.headerStatus.errorTitle" as never),
        label: blueprintPicker().error ?? "",
        detail: blueprintPicker().error ?? "",
      }
    }
    return undefined
  })

  const updateConfigField = <K extends keyof BlueprintConfig>(field: K, value: BlueprintConfig[K]) => {
    setConfigIssues((issues) => issues.filter((issue) => issue.field !== field))
    if (field === "python_path") setPythonDetectFailed(false)
    setDraft("config", field, value as never)
  }

  const replaceDraft = (next: BlueprintDraft) => {
    setDraft(reconcile(next))
  }

  const syncWorkbenchBlueprintRoute = (blueprintId: string) => {
    if (!routeInitialBlueprintId()) return
    const targetId = blueprintId.trim()
    if (!targetId || params.id === targetId) return
    navigate(`/${base64Encode(projectDirectory)}/blueprint-window/${encodeURIComponent(targetId)}`, { replace: true })
  }

  const persistProjectDraft = async (next: BlueprintDraft) => {
    if (!platform.saveBlueprint) return
    await platform.saveBlueprint(projectDirectory, toBlueprintDocument(next, currentBlueprintId(), currentBlueprintName()))
  }

  const resetBlueprintRunState = () => {
    previousBlueprintDiffRunId = undefined
    previousAcceptedDiffSignature = undefined
    syncedAcceptedDiffSignature = undefined
    setRuntime({ runs: [], events: [], loading: false })
    setBlueprintDiffOpen(false)
    setBlueprintDiffSelectedChangesetId(undefined)
    setBlueprintDiff(reconcile(emptyBlueprintDiffState()))
    setRuntimeTask("")
    setRuntimeStartNodeIds([])
    setAgentPanel("panels", reconcile({}))
    setAgentPanel("streamEvents", reconcile({}))
    setAgentPanel("streamCursor", 0)
    setAgentPanel("streamError", undefined)
    setWorkspacePanelArea(undefined)
    setPanelMode("runtime")
  }

  const upsertBlueprintItem = (items: BlueprintSummary[], id: string, name: string): BlueprintSummary[] => {
    const existing = items.find((item) => item.id === id)
    const next = {
      id,
      name,
      path: existing?.path ?? "",
      updated_at: Date.now(),
    }
    return [next, ...items.filter((item) => item.id !== id)]
  }

  const blueprintNameForId = (blueprintId: string) =>
    blueprintPicker().items.find((item) => item.id === blueprintId)?.name || blueprintId || DEFAULT_BLUEPRINT_NAME

  const refreshProjectBlueprints = async (selectedId = currentBlueprintId()) => {
    if (!platform.listBlueprints) return blueprintPicker().items
    setBlueprintPicker((current) => ({ ...current, loading: true, error: undefined }))
    try {
      const items = await platform.listBlueprints(projectDirectory)
      const selected = items.find((item) => item.id === selectedId) ?? items[0]
      setBlueprintPicker((current) => ({
        ...current,
        id: selected?.id ?? current.id,
        name: selected?.name ?? current.name,
        items,
        loading: false,
        error: undefined,
      }))
      return items
    } catch (error) {
      const message = readableError(error)
      setBlueprintPicker((current) => ({ ...current, loading: false, error: message }))
      return blueprintPicker().items
    }
  }

  const loadProjectBlueprint = async (blueprintId: string, fallbackName = blueprintNameForId(blueprintId)) => {
    const openBlueprint = platform.openBlueprint
    if (!openBlueprint) return
    resetBlueprintRunState()
    setBlueprintPicker((current) => ({
      ...current,
      id: blueprintId,
      name: fallbackName,
      loading: true,
      error: undefined,
    }))
    setPersistence({ loaded: false, loading: true, saving: false, source: "local" })
    try {
      const document = await openBlueprint(projectDirectory, blueprintId)
      const documentRecord = document as { id?: string; name?: string }
      const documentId = typeof documentRecord.id === "string" && documentRecord.id.trim() ? documentRecord.id.trim() : blueprintId
      const documentName =
        typeof documentRecord.name === "string" && documentRecord.name.trim() ? documentRecord.name.trim() : fallbackName
      applyingRemote = true
      replaceDraft(fromBlueprintDocument(document as Parameters<typeof fromBlueprintDocument>[0], projectDirectory))
      queueMicrotask(() => {
        applyingRemote = false
      })
      setBlueprintPicker((current) => ({
        ...current,
        id: documentId,
        name: documentName,
        items: upsertBlueprintItem(current.items, documentId, documentName),
        loading: false,
        error: undefined,
      }))
      syncWorkbenchBlueprintRoute(documentId)
      setPersistence({ loaded: true, loading: false, saving: false, source: "project" })
    } catch (error) {
      const message = readableError(error)
      setBlueprintPicker((current) => ({ ...current, loading: false, error: message }))
      setPersistence({ loaded: true, loading: false, saving: false, source: "local", error: message })
      throw error
    }
  }

  const saveProjectDraft = async (next: BlueprintDraft) => {
    if (!platform.saveBlueprint) return
    setPersistence((current) => ({ ...current, saving: true, error: undefined }))
    try {
      await persistProjectDraft(next)
      setPersistence({ loaded: true, loading: false, saving: false, source: "project" })
    } catch (error) {
      setPersistence((current) => ({
        ...current,
        saving: false,
        source: current.source,
        error: readableError(error),
      }))
    }
  }

  const scheduleProjectSave = () => {
    const current = untrack(persistence)
    if (applyingRemote || !current.loaded || !platform.saveBlueprint) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      void saveProjectDraft(draft)
    }, 450)
  }

  const listSkills = async (skillDir: string) => {
    if (!skillDir) return [] as BlueprintCatalogItem[]
    const items = await platform.listBlueprintSkills?.(skillDir)
    return items ?? []
  }

  const listRules = async (ruleDir: string) => {
    if (!ruleDir) return [] as BlueprintCatalogItem[]
    const items = await platform.listBlueprintRules?.(ruleDir)
    return items ?? []
  }

  const listScriptNodes = async () => {
    const result = await platform.listBlueprintScriptNodes?.(projectDirectory)
    const nodes = Array.isArray(result?.nodes) ? result.nodes : []
    return {
      scriptDir: typeof result?.script_dir === "string" ? result.script_dir : "",
      nodes: nodes.map(normalizeScriptCatalogNode).filter(Boolean) as BlueprintScriptCatalogNode[],
    }
  }

  const refreshScriptCatalog = () => setCatalogRefreshVersion((version) => version + 1)

  const scriptCompileSummary = (result: BlueprintScriptCompileResult) =>
    [
      `${language.t("blueprint.script.compileUpdated" as never)}: ${result.updated}`,
      `${language.t("blueprint.script.compileMissing" as never)}: ${result.missing}`,
      `${language.t("blueprint.script.compileRemovedEdges" as never)}: ${result.removedEdges}`,
    ].join(" · ")

  const compileBlueprintScripts = async () => {
    if (scriptCompiling()) return
    if (!platform.listBlueprintScriptNodes || runtimeBusy()) {
      showToast({
        variant: "error",
        title: language.t("blueprint.script.compileFailed" as never),
        description: language.t("blueprint.script.compileUnavailable" as never),
      })
      return
    }
    setScriptCompiling(true)
    try {
      const scripts = await listScriptNodes()
      setCatalog((current) => ({
        ...current,
        scriptDir: scripts.scriptDir,
        scriptNodes: scripts.nodes,
        scriptError: undefined,
      }))
      const result = compileScriptNodesFromCatalog(draft, scripts.nodes)
      replaceDraft(result.draft)
      showToast({
        variant: result.missing > 0 ? "default" : "success",
        title: language.t((result.missing > 0 ? "blueprint.script.compileWarning" : "blueprint.script.compileSuccess") as never),
        description: scriptCompileSummary(result),
      })
    } catch (error) {
      const message = readableError(error)
      setCatalog((current) => ({ ...current, scriptError: message }))
      showToast({
        variant: "error",
        title: language.t("blueprint.script.compileFailed" as never),
        description: message,
      })
    } finally {
      setScriptCompiling(false)
    }
  }

  const refreshEditorCatalog = async () => {
    if (!platform.listBlueprintEditors) return
    setEditorCatalog((current) => ({ ...current, loading: true, error: undefined }))
    try {
      const items = await platform.listBlueprintEditors()
      const normalized = items.filter((item) => item.id && item.label).map((item) =>
        item.systemDefault
          ? {
              ...item,
              label: language.t("blueprint.editor.systemDefault" as never),
              source: language.t("blueprint.editor.systemDefaultDescription" as never),
            }
          : item,
      )
      setEditorCatalog({
        items: normalized.length
          ? normalized
          : [
              {
                id: "system",
                label: language.t("blueprint.editor.systemDefault" as never),
                source: language.t("blueprint.editor.systemDefaultDescription" as never),
                systemDefault: true,
              },
            ],
        loading: false,
      })
    } catch (error) {
      setEditorCatalog((current) => ({ ...current, loading: false, error: readableError(error) }))
    }
  }

  let attemptedCommonConfigBackfill = false
  const joinProjectPath = (root: string, child: string) => {
    const separator = root.includes("\\") ? "\\" : "/"
    return `${root.replace(/[\\/]+$/, "")}${separator}${child}`
  }
  const blankCommonPath = (value?: string) => {
    const trimmed = value?.trim() ?? ""
    return !trimmed || trimmed === "."
  }
  const samePath = (left?: string, right?: string) =>
    (left ?? "").trim().replace(/[\\/]+$/, "").toLowerCase() === (right ?? "").trim().replace(/[\\/]+$/, "").toLowerCase()

  const detectBlueprintPythonPath = async (projectRoot?: string, pythonCommand?: string) => {
    const root = projectRoot?.trim()
    const result = await platform.detectBlueprintPython?.(root && isAbsoluteBlueprintPath(root) ? root : undefined, pythonCommand)
    const pythonPath = typeof result?.pythonCommand === "string" ? result.pythonCommand.trim() : ""
    return pythonPath && isAbsoluteBlueprintPath(pythonPath) ? pythonPath : ""
  }

  const draftSnapshotWithPythonPath = (pythonPath: string): BlueprintDraft => ({
    ...draft,
    config: {
      ...draft.config,
      python_path: pythonPath,
    },
  })

  const ensureDetectedPythonPath = async () => {
    const currentPython = draft.config.python_path.trim()
    if (currentPython) return draft
    const projectRoot = draft.config.project_workdir.trim() || projectDirectory.trim()
    const detectedPython = await detectBlueprintPythonPath(projectRoot, currentPython).catch(() => "")
    if (!detectedPython) return draft
    setDraft("config", "python_path", detectedPython)
    setConfigIssues((issues) => issues.filter((issue) => issue.field !== "python_path"))
    setPythonDetectFailed(false)
    return draftSnapshotWithPythonPath(detectedPython)
  }

  const openProjectSession = (targetProjectDir: string) => {
    layout?.projects.open(targetProjectDir)
    const route = props.floating
      ? `/${base64Encode(targetProjectDir)}/blueprint-window/${encodeURIComponent(currentBlueprintId())}`
      : `/${base64Encode(targetProjectDir)}/session`
    navigate(route, { replace: true })
  }

  function showProjectWorkdirConflictDialog(targetProjectDir: string) {
    dialog.show(() => (
      <BlueprintProjectWorkdirConflictDialog
        targetProjectDir={targetProjectDir}
        onResolve={(policy) => void relocateProjectWorkdir(targetProjectDir, policy)}
      />
    ))
  }

  async function relocateProjectWorkdir(targetProjectWorkdir: string, conflictPolicy?: BlueprintRelocateConflictPolicy) {
    const target = targetProjectWorkdir.trim()
    if (!target) return
    const relocate = platform.relocateBlueprintProjectWorkdir
    if (!relocate) {
      updateConfigField("project_workdir", target)
      return
    }
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = undefined
    }
    setProjectWorkdirRelocating(true)
    setPersistence((current) => ({ ...current, saving: true, error: undefined }))
    try {
      const document = toBlueprintDocument(draft, currentBlueprintId(), currentBlueprintName())
      const result = await relocate(projectDirectory, currentBlueprintId(), document, target, conflictPolicy)
      if (result.conflict === "target_exists") {
        setPersistence((current) => ({ ...current, saving: false, error: undefined }))
        showProjectWorkdirConflictDialog(result.targetProjectDir || target)
        return
      }
      if (!result.changed) {
        applyingRemote = true
        replaceDraft(fromBlueprintDocument(result.document as Parameters<typeof fromBlueprintDocument>[0], projectDirectory))
        queueMicrotask(() => {
          applyingRemote = false
        })
        setPersistence({ loaded: true, loading: false, saving: false, source: "project" })
        return
      }
      openProjectSession(result.targetProjectDir || target)
    } catch (error) {
      setPersistence((current) => ({
        ...current,
        saving: false,
        source: current.source,
        error: readableError(error),
      }))
    } finally {
      setProjectWorkdirRelocating(false)
    }
  }

  async function pickProjectWorkdir(defaultPath?: string) {
    if (blueprintConfigLocked()) return
    const result = await platform.openDirectoryPickerDialog?.({
      title: language.t("blueprint.directory.pickProject"),
      multiple: false,
      defaultPath,
    })
    if (typeof result === "string" && result.trim()) await relocateProjectWorkdir(result)
  }

  function openCreateBlueprintDialog() {
    dialog.show(() => (
      <BlueprintCreateDialog
        existingIds={blueprintPicker().items.map((item) => item.id)}
        onCreate={(name) => void createProjectBlueprint(name)}
      />
    ))
  }

  async function selectProjectBlueprint(blueprintId: string) {
    const targetId = blueprintId.trim()
    if (!targetId || targetId === currentBlueprintId() || runtimeBusy() || blueprintPicker().loading || persistence().saving) return
    if (!platform.openBlueprint || !platform.saveBlueprint) {
      setBlueprintPicker((current) => ({ ...current, error: language.t("blueprint.runtime.unavailable" as never) }))
      return
    }
    const previous = blueprintPicker()
    const targetName = blueprintNameForId(targetId)
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = undefined
    }
    setPersistence((current) => ({ ...current, saving: true, error: undefined }))
    try {
      await persistProjectDraft(draft)
      setPersistence((current) => ({ ...current, saving: false, source: "project" }))
      await loadProjectBlueprint(targetId, targetName)
    } catch (error) {
      const message = readableError(error)
      setBlueprintPicker({ ...previous, loading: false, error: message })
      setPersistence((current) => ({ ...current, loading: false, saving: false, error: message }))
    }
  }

  async function createProjectBlueprint(name: string) {
    if (runtimeBusy() || blueprintPicker().loading || persistence().saving) return
    if (!platform.saveBlueprint) {
      setBlueprintPicker((current) => ({ ...current, error: language.t("blueprint.runtime.unavailable" as never) }))
      return
    }
    const blueprintName = name.trim() || language.t("blueprint.document.new" as never)
    const blueprintId = uniqueBlueprintId(blueprintName, blueprintPicker().items.map((item) => item.id))
    const next = createDefaultBlueprintDraft(projectDirectory)
    next.config = { ...currentConfig() }
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = undefined
    }
    setPersistence((current) => ({ ...current, saving: true, error: undefined }))
    setBlueprintPicker((current) => ({ ...current, loading: true, error: undefined }))
    try {
      await persistProjectDraft(draft)
      await platform.saveBlueprint(projectDirectory, toBlueprintDocument(next, blueprintId, blueprintName))
      resetBlueprintRunState()
      applyingRemote = true
      replaceDraft(next)
      queueMicrotask(() => {
        applyingRemote = false
      })
      setBlueprintPicker((current) => ({
        ...current,
        id: blueprintId,
        name: blueprintName,
        items: upsertBlueprintItem(current.items, blueprintId, blueprintName),
        loading: false,
        error: undefined,
      }))
      syncWorkbenchBlueprintRoute(blueprintId)
      setPersistence({ loaded: true, loading: false, saving: false, source: "project" })
      void refreshProjectBlueprints(blueprintId)
    } catch (error) {
      const message = readableError(error)
      setBlueprintPicker((current) => ({ ...current, loading: false, error: message }))
      setPersistence((current) => ({ ...current, saving: false, error: message }))
      showToast({
        variant: "error",
        title: language.t("blueprint.document.createFailed" as never),
        description: message,
      })
    }
  }

  const detectAndApplyPythonPath = async () => {
    if (pythonDetecting()) return
    setPythonDetecting(true)
    setPythonDetectFailed(false)
    try {
      const currentPython = draft.config.python_path.trim()
      const projectRoot = draft.config.project_workdir.trim() || projectDirectory.trim()
      const detectedPython = await detectBlueprintPythonPath(projectRoot, currentPython).catch(() => "")
      if (!detectedPython) {
        const reason: BlueprintConfigValidationIssue["reason"] =
          currentPython && !isAbsoluteBlueprintPath(currentPython) ? "not_absolute" : "missing"
        setConfigIssues((issues) => [{ field: "python_path", reason }, ...issues.filter((issue) => issue.field !== "python_path")])
        setPythonDetectFailed(true)
        return
      }
      setDraft("config", "python_path", detectedPython)
      setConfigIssues((issues) => issues.filter((issue) => issue.field !== "python_path"))
      setPythonDetectFailed(false)
    } finally {
      setPythonDetecting(false)
    }
  }

  const backfillCommonConfigPaths = async () => {
    if (attemptedCommonConfigBackfill) return
    attemptedCommonConfigBackfill = true
    const projectRoot = projectDirectory.trim()
    if (!projectRoot || projectRoot === "global" || !isAbsoluteBlueprintPath(projectRoot)) return

    const config = untrack(currentConfig)
    const updates: Partial<BlueprintConfig> = {}
    if (blankCommonPath(config.python_path)) {
      const detectedPython = await detectBlueprintPythonPath(projectRoot, config.python_path).catch(() => "")
      if (detectedPython) updates.python_path = detectedPython
    }
    if (blankCommonPath(config.project_workdir)) updates.project_workdir = projectRoot

    const skillDirCandidate = joinProjectPath(projectRoot, "skill_list")
    if (blankCommonPath(config.skill_dir) || samePath(config.skill_dir, projectRoot)) {
      const skills = await listSkills(skillDirCandidate).catch(() => [] as BlueprintCatalogItem[])
      if (skills.length > 0) updates.skill_dir = skillDirCandidate
    }

    const ruleDirCandidate = joinProjectPath(projectRoot, "rules")
    if (blankCommonPath(config.rule_dir)) {
      const rules = await listRules(ruleDirCandidate).catch(() => [] as BlueprintCatalogItem[])
      if (rules.length > 0) updates.rule_dir = ruleDirCandidate
    }

    for (const [field, value] of Object.entries(updates) as Array<[keyof BlueprintConfig, string]>) {
      setDraft("config", field, value as never)
    }
  }

  createEffect(() => {
    if (!draftReady() || !persistence().loaded) return
    void backfillCommonConfigPaths()
  })

  createEffect(() => {
    const skillDir = currentConfig().skill_dir
    const ruleDir = currentConfig().rule_dir
    catalogRefreshVersion()
    let cancelled = false

    void Promise.allSettled([listSkills(skillDir), listRules(ruleDir), listScriptNodes()]).then(([skills, rules, scripts]) => {
      if (cancelled) return
      setCatalog({
        skillDir,
        ruleDir,
        scriptDir: scripts.status === "fulfilled" ? scripts.value.scriptDir : "",
        skills: skills.status === "fulfilled" ? skills.value : [],
        rules: rules.status === "fulfilled" ? rules.value : [],
        scriptNodes: scripts.status === "fulfilled" ? scripts.value.nodes : [],
        skillError: skills.status === "rejected" ? readableError(skills.reason) : undefined,
        ruleError: rules.status === "rejected" ? readableError(rules.reason) : undefined,
        scriptError: scripts.status === "rejected" ? readableError(scripts.reason) : undefined,
      })
    })

    onCleanup(() => {
      cancelled = true
    })
  })

  createEffect(() => {
    if (!draftReady()) return
    if (persistence().loaded || persistence().loading) return
    const openBlueprint = platform.openBlueprint
    const saveBlueprint = platform.saveBlueprint
    if (!openBlueprint || !saveBlueprint) {
      setPersistence({ loaded: true, loading: false, saving: false, source: "local" })
      return
    }
    setPersistence({ loaded: false, loading: true, saving: false, source: "local" })
    void (async () => {
      try {
        await platform.configureBlueprintRuntime?.(currentConfig().python_path)
        const requestedBlueprintId = initialBlueprintId()
        const items = platform.listBlueprints ? await refreshProjectBlueprints(requestedBlueprintId) : []
        const selected = items.find((item) => item.id === requestedBlueprintId) ?? items[0]
        const targetBlueprintId = selected?.id ?? requestedBlueprintId
        const targetBlueprintName = selected?.name ?? initialBlueprintName()
        await loadProjectBlueprint(targetBlueprintId, targetBlueprintName)
      } catch (error) {
        const code = typeof error === "object" && error !== null ? (error as { code?: string }).code : undefined
        if (code === "NOT_FOUND" || readableError(error).includes("NOT_FOUND")) {
          await saveProjectDraft(draft)
          void refreshProjectBlueprints(currentBlueprintId())
          return
        }
        setPersistence({
          loaded: true,
          loading: false,
          saving: false,
          source: "local",
          error: readableError(error),
        })
      }
    })()
  })

  createEffect(() => {
    if (blueprintConfigLocked() && globalConfigOpen()) setGlobalConfigOpen(false)
  })

  createEffect(() => {
    if (projectWorkdirAutoPromptShownThisApp) return
    if (!draftReady() || !persistence().loaded || blueprintConfigLocked()) return
    projectWorkdirAutoPromptShownThisApp = true
    queueMicrotask(() => {
      dialog.show(() => (
        <BlueprintProjectWorkdirConfirmDialog
          currentProjectWorkdir={currentConfig().project_workdir || projectDirectory}
          onConfirm={(target) => void relocateProjectWorkdir(target)}
        />
      ))
    })
  })

  createEffect(() => {
    const available = new Set(runtimeStartNodeOptions().map((option) => option.id))
    setRuntimeStartNodeIds((current) => current.filter((nodeId) => available.has(nodeId)))
  })

  createEffect(() => {
    draft.schema_version
    draft.config.python_path
    draft.config.project_workdir
    draft.config.skill_dir
    draft.config.rule_dir
    JSON.stringify(draft.graph)
    JSON.stringify(draft.layout)
    JSON.stringify(draft.selection)
    JSON.stringify(draft.inspector)
    scheduleProjectSave()
  })

  onCleanup(() => {
    if (saveTimer) clearTimeout(saveTimer)
  })

  async function refreshModelCatalog(cliKind: string) {
    const current = modelCatalog()
    if (current.loading && current.cliKind === cliKind) return
    setModelCatalog({
      cliKind,
      models: current.cliKind === cliKind && current.models.length ? current.models : fallbackModels(cliKind),
      loading: true,
    })
    try {
      const models = await platform.listBlueprintModels?.(cliKind)
      setModelCatalog({
        cliKind,
        models: models?.length ? models : fallbackModels(cliKind),
        loading: false,
      })
    } catch (error) {
      setModelCatalog({
        cliKind,
        models: current.cliKind === cliKind && current.models.length ? current.models : fallbackModels(cliKind),
        loading: false,
        error: readableError(error),
      })
    }
  }

  createEffect(() => {
    const cliKinds = Array.from(new Set(Object.values(draft.graph.agent_nodes).map((node) => node.cli_kind || "codemaker")))
    queueMicrotask(() => {
      for (const cliKind of cliKinds) void refreshModelCatalog(cliKind)
    })
  })

  createEffect(() => {
    const inspector = draft.inspector
    if (!inspector) return
    const valid =
      inspector.type === "node"
        ? visibleNodeIds().has(inspector.id)
        : visibleEdges().some((edge) => edge.id === inspector.id)
    if (!valid) replaceDraft(setInspector(draft, undefined))
  })

  createEffect(() => {
    const phase = externalBlueprintProgressPhase()
    if (!phase) return
    setBlueprintFlowLock((current) => ({
      ...current,
      active: true,
      planningSeen: true,
      startSeen: current.startSeen || phase === "start",
      submittedAt: current.submittedAt ?? Date.now(),
    }))
  })

  createEffect(() => {
    const lock = blueprintFlowLock()
    const runId = runtime().runId
    const status = runtimeStatus(runtime().status)
    if (runId && isTerminalRuntimeStatus(status)) {
      clearRuntimeManualUnlock(runId)
      setAutoCompletingRuntimeKey(undefined)
      if (lock.active && !externalBlueprintProgressPhase() && runtime().action !== "plan") {
        setBlueprintFlowLock({ active: false })
      }
      return
    }
    if (runId && status === "running" && !runtimeSummaryReady()) {
      if (lock.active) setBlueprintFlowLock({ active: false })
      return
    }
    if (!lock.active) return
    if (
      lock.planningSeen &&
      !lock.startSeen &&
      !planningProgressActive() &&
      !runId &&
      !runtime().loading
    ) {
      setBlueprintFlowLock({ active: false })
    }
  })

  createEffect(() => {
    const lock = blueprintFlowLock()
    if (!lock.active || lock.planningSeen || planningProgressActive() || runtime().runId || runtime().loading) return
    const submittedAt = lock.submittedAt ?? Date.now()
    const delay = Math.max(0, BLUEPRINT_FLOW_LOCK_PENDING_GRACE_MS - (Date.now() - submittedAt))
    const timer = window.setTimeout(() => {
      const current = blueprintFlowLock()
      if (current.active && !current.planningSeen && !planningProgressActive() && !runtime().runId && !runtime().loading) {
        setBlueprintFlowLock({ active: false })
      }
    }, delay)
    onCleanup(() => window.clearTimeout(timer))
  })

  createEffect(() => {
    if (!blueprintProgressPhase()) return
    requestAnimationFrame(() => setProgressAnchorVersion((version) => version + 1))
  })

  createEffect(() => {
    if (!persistence().loaded || !platform.listBlueprintRuns || runtime().runId || runtime().runs.length) return
    let cancelled = false
    const blueprintId = currentBlueprintId()
    void platform
      .listBlueprintRuns(projectDirectory, blueprintId)
      .then((runs) => {
        if (cancelled) return
        const latest = runs[0]
        const runId = typeof latest?.runId === "string" ? latest.runId : undefined
        setRuntime((current) => ({ ...current, runs, runId: current.runId ?? runId }))
        if (runId) void refreshBlueprintRuntime(runId)
      })
      .catch((error) => {
        if (!cancelled) setRuntime((current) => ({ ...current, error: readableError(error) }))
      })
    onCleanup(() => {
      cancelled = true
    })
  })

  createEffect(() => {
    const runId = runtime().runId
    if (runId === previousBlueprintDiffRunId) return
    previousBlueprintDiffRunId = runId
    previousAcceptedDiffSignature = undefined
    syncedAcceptedDiffSignature = undefined
    setBlueprintDiffOpen(false)
    setBlueprintDiffSelectedChangesetId(undefined)
    setBlueprintDiff({
      loading: false,
      error: undefined,
      summary: {},
      changesets: [],
      acceptedDiffs: [],
      binaryFiles: [],
      detailLoading: undefined,
      details: {},
    })
    if (runId) void refreshBlueprintRunDiff(runId, { quiet: true })
  })

  onMount(() => {
    const handleWorkspaceDiffChanged = (event: Event) => {
      const detail = asRecord((event as CustomEvent).detail)
      if (detail?.source === "blueprint") return
      const runId = stringValue(detail?.runId)
      if (!runId || runId !== runtime().runId) return
      void refreshBlueprintRunDiff(runId, { quiet: true })
    }
    window.addEventListener("workspace.diff.changed", handleWorkspaceDiffChanged)
    onCleanup(() => window.removeEventListener("workspace.diff.changed", handleWorkspaceDiffChanged))
  })

  createEffect(() => {
    const runId = runtime().runId
    const status = runtimeStatus(runtime().status)
    if (!runId || isTerminalRuntimeStatus(status)) return
    const interval = setInterval(() => {
      void refreshBlueprintRuntime(runId, { quiet: true })
    }, 2000)
    onCleanup(() => clearInterval(interval))
  })

  createEffect(() => {
    const request = runtime().planningRequest
    if (!request?.requestId || !isBlueprintPlanningRequestActive(request.status) || !platform.blueprintWindowPlanningStatus) return
    void refreshBlueprintPlanningRequest(request.requestId, { quiet: true })
    const interval = setInterval(() => {
      void refreshBlueprintPlanningRequest(request.requestId, { quiet: true })
    }, 1500)
    onCleanup(() => clearInterval(interval))
  })

  createEffect(() => {
    const runId = runtime().runId
    const status = runtimeStatus(runtime().status)
    if (!runId || isTerminalRuntimeStatus(status) || !platform.blueprintAgentStreamToken) return
    let socket: WebSocket | undefined
    let cancelled = false
    void platform
      .blueprintAgentStreamToken(runId, untrack(() => agentPanel.streamCursor))
      .then((response) => {
        if (cancelled) return
        const wsUrl = typeof response.wsUrl === "string" ? response.wsUrl : undefined
        if (!wsUrl) return
        socket = new WebSocket(wsUrl)
        socket.onmessage = (event) => {
          try {
            appendAgentStreamEvent(JSON.parse(String(event.data)))
          } catch (error) {
            setAgentPanel("streamError", readableError(error))
          }
        }
        socket.onerror = () => setAgentPanel("streamError", "agent stream disconnected")
      })
      .catch((error) => setAgentPanel("streamError", readableError(error)))
    onCleanup(() => {
      cancelled = true
      socket?.close()
    })
  })

  createEffect(() => {
    const activeRun = asRecord(props.blueprintPlanningActiveRun)
    const runId = stringValue(activeRun?.runId)
    if (!runId) return
    const activeRunResponse = activeRun ?? { runId }
    const status = asRecord(activeRun?.status)
    const runStatusValue = runtimeStatus(status)
    if (runStatusValue && isTerminalRuntimeStatus(runStatusValue)) return
    setRuntime((current) => ({
      ...current,
      runId,
      runs: mergeRuntimeRunsWithStatus(current.runs, activeRunResponse),
      status: status ?? current.status,
      events: arrayOfRecords(status?.recent_events),
      loading: false,
      action: undefined,
      error: undefined,
      lastUpdatedAt: Date.now(),
    }))
    setPanelMode("runtime")
    void refreshBlueprintRuntime(runId, { quiet: true })
  })

  createEffect(() => {
    if (!blueprintFlowLockActive()) return
    const runId = runtime().runId
    const status = runtimeStatus(runtime().status)
    const key = runtimeSummaryKey()
    if (!runId || !key || isTerminalRuntimeStatus(status) || !platform.endBlueprintRun) return
    if (autoCompletedRuntimeKeys.has(key) || autoCompletingRuntimeKey() === key) return
    autoCompletedRuntimeKeys.add(key)
    setAutoCompletingRuntimeKey(key)
    queueMicrotask(async () => {
      const completed = await endBlueprintRuntime("complete", {
        auto: true,
        reason: AUTO_RUNTIME_COMPLETE_REASON,
      })
      if (!completed) {
        unlockRuntimeForManualControl(runId)
        setBlueprintFlowLock({ active: false })
      }
      if (autoCompletingRuntimeKey() === key) setAutoCompletingRuntimeKey(undefined)
    })
  })

  async function refreshBlueprintPlanningRequest(
    requestId = runtime().planningRequest?.requestId,
    opts: { quiet?: boolean } = {},
  ) {
    if (!requestId || !platform.blueprintWindowPlanningStatus) return
    if (!opts.quiet) setRuntime((current) => ({ ...current, loading: true, action: "plan", error: undefined }))
    try {
      const response = await platform.blueprintWindowPlanningStatus(requestId)
      if (response.found === false) {
        setBlueprintFlowLock({ active: false })
        setRuntime((current) => ({
          ...current,
          planningRequest: {
            requestId,
            status: "missing",
            message: "planning request expired",
          },
          loading: false,
          action: undefined,
          error: "planning request expired",
        }))
        return
      }
      const request = asRecord(response.request) ?? asRecord(response)
      const status = stringValue(request?.status) ?? "pending"
      const plan = asRecord(request?.plan)
      const validation = asRecord(request?.validation)
      const summary = stringValue(request?.summary)
      const message =
        stringValue(request?.message) ??
        stringValue(request?.reason) ??
        stringValue(response.message) ??
        stringValue(response.error)
      const cancelledByThisPanel = planningCancelledRequestIds.has(requestId)
      const effectiveStatus = cancelledByThisPanel && isBlueprintPlanningRequestActive(status) ? "cancelled" : status
      const active = isBlueprintPlanningRequestActive(effectiveStatus)
      const errors = validationErrors(validation)
      if (!active) setBlueprintFlowLock({ active: false })
      setRuntime((current) => ({
        ...current,
        planningRequest: {
          requestId,
          status: effectiveStatus,
          summary,
          message,
        },
        plan: plan ?? current.plan,
        planValidation: validation ?? current.planValidation,
        loading: active,
        action: active ? "plan" : undefined,
        error:
          effectiveStatus === "failed" || (effectiveStatus === "cancelled" && !cancelledByThisPanel)
            ? message ?? status
            : validation?.ok === false
              ? errors[0] ?? "start plan validation failed"
              : undefined,
        lastUpdatedAt: Date.now(),
      }))
    } catch (error) {
      const message = readableError(error)
      setBlueprintFlowLock({ active: false })
      setRuntime((current) => ({ ...current, loading: false, action: undefined, error: message }))
    }
  }

  async function cancelBlueprintPlanningRequest() {
    const requestId = runtime().planningRequest?.requestId
    if (!requestId || !platform.cancelBlueprintWindowPlanning || planningCancelPending()) return
    setPlanningCancelPending(true)
    try {
      const response = await platform.cancelBlueprintWindowPlanning(
        requestId,
        "cancelled from blueprint progress HUD",
      )
      const request = asRecord(response.request) ?? asRecord(response)
      const status = stringValue(request?.status) ?? (response.cancelled === false ? "missing" : "cancelled")
      const summary = stringValue(request?.summary)
      const message =
        stringValue(request?.message) ??
        stringValue(request?.reason) ??
        stringValue(response.message) ??
        stringValue(response.error) ??
        (status === "missing" ? "planning request expired" : undefined)
      const plan = asRecord(request?.plan)
      const validation = asRecord(request?.validation)
      const errors = validationErrors(validation)
      if (status === "cancelled" || status === "missing") planningCancelledRequestIds.add(requestId)
      setBlueprintFlowLock({ active: false })
      setRuntime((current) => ({
        ...current,
        planningRequest: {
          requestId,
          status,
          summary,
          message,
        },
        plan: plan ?? current.plan,
        planValidation: validation ?? current.planValidation,
        loading: false,
        action: undefined,
        error:
          status === "failed" || status === "missing"
            ? message ?? status
            : validation?.ok === false
              ? errors[0] ?? "start plan validation failed"
              : undefined,
        lastUpdatedAt: Date.now(),
      }))
    } catch (error) {
      setRuntime((current) => ({ ...current, error: readableError(error) }))
    } finally {
      setPlanningCancelPending(false)
    }
  }

  async function refreshBlueprintRuntime(runId = runtime().runId, opts: { quiet?: boolean } = {}) {
    if (!runId || !platform.blueprintRunStatus) return
    if (!opts.quiet) setRuntime((current) => ({ ...current, loading: true, error: undefined }))
    try {
      const [statusResponse, eventsResponse] = await Promise.all([
        platform.blueprintRunStatus(runId),
        platform.blueprintRecentEvents?.(runId, 50),
      ])
      const runtimeStatusSnapshot = asRecord(statusResponse.status)
      const recentEvents = arrayOfRecords(eventsResponse?.events)
      syncAgentPanelUserMessagesFromRuntimeEvents(recentEvents)
      setRuntime((current) => ({
        ...current,
        runId,
        runs: mergeRuntimeRunsWithStatus(current.runs, statusResponse),
        status: runtimeStatusSnapshot,
        explanation: asRecord(statusResponse.explanation),
        events: recentEvents,
        loading: false,
        error: undefined,
        lastUpdatedAt: Date.now(),
      }))
      await refreshBlueprintRunDiff(runId, { quiet: true })
      await refreshOpenAgentPanelInfos(runId)
      scheduleOpenTestAgentPanelPersists()
    } catch (error) {
      setRuntime((current) => ({
        ...current,
        loading: false,
        error: readableError(error),
      }))
    }
  }

  async function refreshBlueprintRunDiff(runId = runtime().runId, opts: { quiet?: boolean } = {}) {
    if (!runId || !platform.blueprintRunDiff) return
    if (!opts.quiet) setBlueprintDiff("loading", true)
    try {
      const response = await platform.blueprintRunDiff(runId)
      const next = normalizeBlueprintRunDiff(response)
      setBlueprintDiff({
        loading: false,
        error: undefined,
        summary: next.summary,
        changesets: next.changesets,
        acceptedDiffs: next.acceptedDiffs,
        binaryFiles: next.binaryFiles,
        detailLoading: undefined,
        rollingBack: undefined,
        restoringRollback: false,
        details: blueprintDiff.details,
      })
      emitWorkspaceDiffChangedIfNeeded(runId, next.changesets, next.acceptedDiffs)
    } catch (error) {
      setBlueprintDiff("loading", false)
      setBlueprintDiff("error", readableError(error))
    }
  }

  async function loadBlueprintChangesetDiff(changesetId: string) {
    const runId = runtime().runId
    if (!runId || !platform.blueprintChangesetDiff) return
    if (blueprintDiff.details[changesetId]) return
    setBlueprintDiff("detailLoading", changesetId)
    try {
      const response = await platform.blueprintChangesetDiff(runId, changesetId)
      setBlueprintDiff("details", changesetId, normalizeBlueprintChangesetDetail(response))
      setBlueprintDiff("detailLoading", undefined)
    } catch (error) {
      setBlueprintDiff("detailLoading", undefined)
      setBlueprintDiff("error", readableError(error))
    }
  }

  async function rollbackBlueprintChangesets(toChangesetId: string) {
    const runId = runtime().runId
    if (!runId || !platform.rollbackBlueprintChangesets) return
    setBlueprintDiff("rollingBack", toChangesetId)
    setBlueprintDiff("error", undefined)
    try {
      const response = await platform.rollbackBlueprintChangesets(
        runId,
        toChangesetId,
        "requested from Blueprint Diff overlay",
      )
      const record = asRecord(response)
      const rollback = asRecord(record?.rollback)
      if (record?.ok === false || rollback?.ok === false) {
        throw new Error(stringValue(rollback?.status) ?? stringValue(record?.status) ?? "rollback failed")
      }
      setBlueprintDiff("details", {})
      setBlueprintDiffSelectedChangesetId(undefined)
      await refreshBlueprintRunDiff(runId, { quiet: true })
    } catch (error) {
      setBlueprintDiff("error", readableError(error))
    } finally {
      setBlueprintDiff("rollingBack", undefined)
    }
  }

  async function restoreBlueprintRollback(rollbackId?: string) {
    const runId = runtime().runId
    if (!runId || !platform.restoreBlueprintRollback) return
    setBlueprintDiff("restoringRollback", true)
    setBlueprintDiff("error", undefined)
    try {
      const response = await platform.restoreBlueprintRollback(
        runId,
        rollbackId,
        "requested from Blueprint Diff overlay",
      )
      const record = asRecord(response)
      const restore = asRecord(record?.restore)
      if (record?.ok === false || restore?.ok === false) {
        throw new Error(stringValue(restore?.status) ?? stringValue(record?.status) ?? "restore failed")
      }
      setBlueprintDiff("details", {})
      setBlueprintDiffSelectedChangesetId(undefined)
      await refreshBlueprintRunDiff(runId, { quiet: true })
    } catch (error) {
      setBlueprintDiff("error", readableError(error))
    } finally {
      setBlueprintDiff("restoringRollback", false)
    }
  }

  function emitWorkspaceDiffChangedIfNeeded(
    runId: string,
    changesets: BlueprintDiffChangeset[],
    acceptedDiffs: BlueprintDiffFile[],
  ) {
    const signature = changesets
      .filter((changeset) => changeset.status === "accepted")
      .map((changeset) => changeset.changesetId)
      .sort()
      .join("|")
    const changed = previousAcceptedDiffSignature !== signature
    const shouldSync = signature
      ? syncedAcceptedDiffSignature !== signature
      : changed && previousAcceptedDiffSignature !== undefined && syncedAcceptedDiffSignature !== signature
    if (shouldSync) {
      const payload: BlueprintDiffSyncPayload = {
        runId,
        changesetIds: signature ? signature.split("|") : [],
        acceptedDiffs,
      }
      props.onBlueprintDiffChanged?.(payload)
      window.dispatchEvent(
        new CustomEvent("workspace.diff.changed", {
          detail: {
            source: "blueprint",
            ...payload,
          },
        }),
      )
      syncedAcceptedDiffSignature = signature
    }
    previousAcceptedDiffSignature = signature
  }

  function openRuntimePlanningPanel() {
    setPanelMode("runtime")
    requestAnimationFrame(() => runtimeTaskInputRef?.focus())
  }

  function currentBlueprintFloatingRect(): BlueprintFloatingRect {
    const rect = rootRef?.getBoundingClientRect()
    return {
      x: rect?.left ?? props.floatingRect?.x ?? 96,
      y: rect?.top ?? props.floatingRect?.y ?? 64,
      width: rect?.width ?? props.floatingRect?.width ?? 980,
      height: rect?.height ?? props.floatingRect?.height ?? 680,
    }
  }

  async function floatBlueprintToWindow(rect: BlueprintFloatingRect) {
    if (!platform.openBlueprintWindow) {
      ;(props.onFloat ?? view().blueprintPanel.float)(rect)
      return
    }
    view().blueprintPanel.float(rect)
    try {
      await platform.openBlueprintWindow(projectDirectory, params.id, rect)
    } catch (error) {
      view().blueprintPanel.dock()
      showToast({
        variant: "error",
        title: language.t("common.requestFailed"),
        description: readableError(error),
      })
    }
  }

  async function dockBlueprintWindow() {
    if (props.floating && platform.dockBlueprintWindow) {
      await platform.dockBlueprintWindow(projectDirectory, params.id)
      return
    }
    ;(props.onDock ?? view().blueprintPanel.dock)()
  }

  async function closeBlueprintPanel() {
    if (props.floating && platform.closeBlueprintWindow) {
      await platform.closeBlueprintWindow()
      return
    }
    view().blueprintPanel.close()
  }

  async function openWorkspaceDirectory(area: WorkspacePanelArea) {
    const directory = workspaceAreaDirectory(runtimeWorkspace(), area)
    if (!directory || !platform.openPath) return
    try {
      await platform.openPath(directory)
    } catch (error) {
      showToast({
        variant: "error",
        title: language.t("common.requestFailed"),
        description: readableError(error),
      })
    }
  }

  async function revealWorkspaceItem(path: string | undefined) {
    if (!path) return
    try {
      if (platform.revealPathInFileManager) {
        await platform.revealPathInFileManager(path)
        return
      }
      if (platform.openPath) await platform.openPath(parentDirectory(path))
    } catch (error) {
      showToast({
        variant: "error",
        title: language.t("common.requestFailed"),
        description: readableError(error),
      })
    }
  }

  function handleBlueprintHeaderPointerDown(event: PointerEvent) {
    if (props.floating) return
    if (!platform.openBlueprintWindow && !props.onFloat) return
    if (event.button !== 0) return
    const target = event.target
    if (
      target instanceof HTMLElement &&
      target.closest("button,a,input,textarea,select,[role='button'],[data-blueprint-header-status-trigger]")
    ) {
      return
    }
    const handle = event.currentTarget
    if (!(handle instanceof HTMLElement)) return
    event.preventDefault()
    const origin = props.floatingRect ?? currentBlueprintFloatingRect()
    const offsetX = event.clientX - origin.x
    const offsetY = event.clientY - origin.y
    const startClientX = event.clientX
    const startClientY = event.clientY
    let dragging = false
    handle.setPointerCapture?.(event.pointerId)

    const move = (moveEvent: PointerEvent) => {
      if (moveEvent.pointerId !== event.pointerId) return
      const dx = moveEvent.clientX - startClientX
      const dy = moveEvent.clientY - startClientY
      if (!dragging) {
        if (Math.hypot(dx, dy) < BLUEPRINT_FLOAT_DRAG_THRESHOLD) return
        dragging = true
        const next = {
          ...origin,
          x: moveEvent.clientX - offsetX,
          y: moveEvent.clientY - offsetY,
        }
        cleanup()
        void floatBlueprintToWindow(next)
        return
      }
      ;(props.onFloatingRectChange ?? view().blueprintPanel.move)({
        ...origin,
        x: moveEvent.clientX - offsetX,
        y: moveEvent.clientY - offsetY,
      })
    }
    const end = (endEvent: PointerEvent) => {
      if (endEvent.pointerId !== event.pointerId) return
      cleanup()
    }
    const cleanup = () => {
      window.removeEventListener("pointermove", move)
      window.removeEventListener("pointerup", end)
      window.removeEventListener("pointercancel", end)
    }
    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", end)
    window.addEventListener("pointercancel", end)
  }

  function toggleRuntimeStartNode(nodeId: string) {
    clearRuntimeStartPlan()
    setRuntimeStartNodeIds((current) => {
      if (current.includes(nodeId)) return current.filter((id) => id !== nodeId)
      return [...current, nodeId]
    })
  }

  function buildBlueprintPlanningMessage(task: string, startNodeIds: string[]) {
    const startConstraint = startNodeIds.length
      ? [
          "Use these AgentNode ids as the preferred start_nodes unless the graph makes them invalid:",
          ...startNodeIds.map((nodeId) => {
            const node = draft.graph.agent_nodes[nodeId]
            const agentName = node?.agent_id?.trim()
            const prompt = node?.prompt?.trim()
            return `- ${nodeId}${agentName ? ` (${agentName})` : ""}${prompt ? `: ${prompt}` : ""}`
          }),
        ].join("\n")
      : "No start AgentNode was manually selected. Inspect the current blueprint and choose valid start_nodes yourself."

    return [
      "Please create one start plan for the current blueprint.",
      "",
      "User task:",
      task,
      "",
      "Start node guidance:",
      startConstraint,
      "",
      "Use blueprint_take_planning_request to claim the request for this thread, then call blueprint_complete_planning_request with the validated start plan. Do not start the run.",
    ].join("\n")
  }

  async function submitBlueprintPlanningTask() {
    const task = runtimeTask().trim()
    if (!task) {
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.taskRequired" as never) }))
      openRuntimePlanningPanel()
      return
    }
    if (runtimeBusy()) {
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.busy" as never) }))
      return
    }
    if (!platform.saveBlueprint || !props.onBlueprintPlanningSubmit) {
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.unavailable") }))
      return
    }
    const startDraft = await ensureDetectedPythonPath()
    const configIssues = validateBlueprintConfigForStart(startDraft)
    if (configIssues.length) {
      setConfigIssues(configIssues)
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.configMissing" as never) }))
      dialog.show(() => <BlueprintConfigRequiredDialog issues={configIssues} />)
      return
    }
    setConfigIssues([])
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = undefined
    }
    setPanelMode("runtime")
    setPersistence((current) => ({ ...current, saving: true, error: undefined }))
    setRuntime((current) => ({ ...current, loading: true, action: "plan", error: undefined }))
    setBlueprintFlowLock({
      active: true,
      planningSeen: planningProgressActive(),
      startSeen: props.blueprintPlanningProgress?.phase === "start",
      submittedAt: Date.now(),
    })
    try {
      await platform.configureBlueprintRuntime?.(startDraft.config.python_path)
      await persistProjectDraft(startDraft)
      setPersistence({ loaded: true, loading: false, saving: false, source: "project" })
      const startNodeIds = runtimeStartNodeIds().slice()
      const submitted = await props.onBlueprintPlanningSubmit({
        task,
        blueprintId: currentBlueprintId(),
        blueprintName: currentBlueprintName(),
        startNodeIds,
        message: buildBlueprintPlanningMessage(task, startNodeIds),
      })
      const submitResult = normalizeBlueprintPlanningSubmitResult(submitted)
      if (!submitResult.accepted) {
        setBlueprintFlowLock({ active: false })
        setRuntime((current) => ({ ...current, loading: false, action: undefined, error: submitResult.message }))
        return
      }
      setRuntimeTask("")
      if (submitResult.requestId) {
        const status = submitResult.status ?? "pending"
        setRuntime((current) => ({
          ...current,
          planningRequest: {
            requestId: submitResult.requestId!,
            status,
            message: submitResult.message,
          },
          loading: isBlueprintPlanningRequestActive(status),
          action: isBlueprintPlanningRequestActive(status) ? "plan" : undefined,
          error: undefined,
          plan: undefined,
          planValidation: undefined,
        }))
        void refreshBlueprintPlanningRequest(submitResult.requestId)
        return
      }
      setBlueprintFlowLock({ active: false })
      setRuntime((current) => ({ ...current, loading: false, action: undefined, error: undefined }))
    } catch (error) {
      const message = readableError(error)
      setPersistence((current) => ({ ...current, saving: false, error: message }))
      setBlueprintFlowLock({ active: false })
      setRuntime((current) => ({ ...current, loading: false, action: undefined, error: message }))
    }
  }

  async function generateBlueprintStartPlan() {
    const task = runtimeTask().trim()
    if (!task) {
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.taskRequired" as never) }))
      openRuntimePlanningPanel()
      return
    }
    const startNodes = runtimeStartNodeIds().slice()
    if (!startNodes.length && !hasTickSourceNode(draft)) {
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.startNodeRequired" as never) }))
      openRuntimePlanningPanel()
      return
    }
    if (runtimeBusy()) {
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.busy" as never) }))
      return
    }
    if (!platform.saveBlueprint || !platform.createBlueprintStartPlan) {
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.unavailable") }))
      return
    }
    const startDraft = await ensureDetectedPythonPath()
    const configIssues = validateBlueprintConfigForStart(startDraft)
    if (configIssues.length) {
      setConfigIssues(configIssues)
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.configMissing" as never) }))
      dialog.show(() => <BlueprintConfigRequiredDialog issues={configIssues} />)
      return
    }
    setConfigIssues([])
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = undefined
    }
    setPanelMode("runtime")
    setPersistence((current) => ({ ...current, saving: true, error: undefined }))
    setRuntime((current) => ({
      ...current,
      loading: true,
      action: "plan",
      error: undefined,
      plan: undefined,
      planValidation: undefined,
      planningRequest: undefined,
    }))
    try {
      await platform.configureBlueprintRuntime?.(startDraft.config.python_path)
      await persistProjectDraft(startDraft)
      setPersistence({ loaded: true, loading: false, saving: false, source: "project" })
      const created = await platform.createBlueprintStartPlan(projectDirectory, currentBlueprintId(), {
        task,
        startNodeIds: startNodes,
      })
      const plan = asRecord(created.plan)
      const validation = asRecord(created.validation)
      const errors = validationErrors(validation)
      setRuntime((current) => ({
        ...current,
        plan,
        planValidation: validation,
        loading: false,
        action: undefined,
        error: validation?.ok === false ? errors[0] ?? "start plan validation failed" : undefined,
      }))
    } catch (error) {
      const message = readableError(error)
      setPersistence((current) => ({ ...current, saving: false, error: message }))
      setRuntime((current) => ({ ...current, loading: false, action: undefined, error: message }))
    }
  }

  async function confirmBlueprintStartPlan() {
    if (runtimeBusy()) {
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.busy" as never) }))
      return
    }
    const plan = asRecord(runtime().plan)
    if (!plan || asRecord(runtime().planValidation)?.ok !== true) {
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.startPlanRequired" as never) }))
      openRuntimePlanningPanel()
      return
    }
    if (!platform.saveBlueprint || !platform.startBlueprintRun) {
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.unavailable") }))
      return
    }
    const startDraft = await ensureDetectedPythonPath()
    const configIssues = validateBlueprintConfigForStart(startDraft)
    if (configIssues.length) {
      setConfigIssues(configIssues)
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.configMissing" as never) }))
      dialog.show(() => <BlueprintConfigRequiredDialog issues={configIssues} />)
      return
    }
    setConfigIssues([])
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = undefined
    }
    setPanelMode("runtime")
    setPersistence((current) => ({ ...current, saving: true, error: undefined }))
    setRuntime((current) => ({ ...current, loading: true, action: "start", error: undefined }))
    try {
      await platform.configureBlueprintRuntime?.(startDraft.config.python_path)
      await persistProjectDraft(startDraft)
      setPersistence({ loaded: true, loading: false, saving: false, source: "project" })
      if (platform.validateBlueprintStartPlan) {
        const validated = await platform.validateBlueprintStartPlan(projectDirectory, currentBlueprintId(), plan)
        const validation = asRecord(validated.validation)
        if (validation?.ok !== true) {
          setRuntime((current) => ({
            ...current,
            planValidation: validation,
            loading: false,
            action: undefined,
            error: validationErrors(validation)[0] ?? "start plan validation failed",
          }))
          return
        }
      }
      const started = await platform.startBlueprintRun(projectDirectory, currentBlueprintId(), plan, "live")
      const status = asRecord(started.status)
      const recentEvents = arrayOfRecords(status?.recent_events)
      const runId = stringValue(started.runId) ?? stringValue(asRecord(started.run)?.runId) ?? stringValue(asRecord(status?.run)?.runId)
      syncAgentPanelUserMessagesFromRuntimeEvents(recentEvents)
      setRuntime((current) => ({
        ...current,
        runId,
        runs: mergeRuntimeRunsWithStatus(current.runs, started),
        status,
        explanation: asRecord(started.explanation),
        events: recentEvents,
        plan: undefined,
        planValidation: undefined,
        planningRequest: undefined,
        loading: false,
        action: undefined,
        error: undefined,
        lastUpdatedAt: Date.now(),
      }))
      setRuntimeTask("")
      scheduleOpenTestAgentPanelPersists()
      if (runId) void refreshBlueprintRuntime(runId, { quiet: true })
    } catch (error) {
      const message = readableError(error)
      setPersistence((current) => ({ ...current, saving: false, error: message }))
      setRuntime((current) => ({ ...current, loading: false, action: undefined, error: message }))
    }
  }

  async function startBlueprintRunDirect() {
    const startNodes = runtimeStartNodeIds().slice()
    const taskText = runtimeTask().trim()
    if (!startNodes.length && !hasTickSourceNode(draft)) {
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.startNodeRequired" as never) }))
      openRuntimePlanningPanel()
      return
    }
    if (runtimeBusy()) {
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.busy" as never) }))
      return
    }
    if (!platform.saveBlueprint || !platform.startBlueprintRun) {
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.unavailable") }))
      return
    }
    const startDraft = await ensureDetectedPythonPath()
    const configIssues = validateBlueprintConfigForStart(startDraft)
    if (configIssues.length) {
      setConfigIssues(configIssues)
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.configMissing" as never) }))
      dialog.show(() => <BlueprintConfigRequiredDialog issues={configIssues} />)
      return
    }
    const plan = createBlueprintStartPlan(startDraft, { startNodes, taskText })
    if (!plan.start_nodes.length && !hasTickSourceNode(startDraft)) {
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.startNodeRequired" as never) }))
      return
    }
    setConfigIssues([])
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = undefined
    }
    setPanelMode("runtime")
    setPersistence((current) => ({ ...current, saving: true, error: undefined }))
    setRuntime((current) => ({ ...current, loading: true, action: "start", error: undefined }))
    try {
      await platform.configureBlueprintRuntime?.(startDraft.config.python_path)
      await persistProjectDraft(startDraft)
      setPersistence({ loaded: true, loading: false, saving: false, source: "project" })
      const started = await platform.startBlueprintRun(projectDirectory, currentBlueprintId(), plan, "live")
      const status = asRecord(started.status)
      const recentEvents = arrayOfRecords(status?.recent_events)
      const runId = stringValue(started.runId) ?? stringValue(asRecord(started.run)?.runId) ?? stringValue(asRecord(status?.run)?.runId)
      syncAgentPanelUserMessagesFromRuntimeEvents(recentEvents)
      setRuntime((current) => ({
        ...current,
        runId,
        runs: mergeRuntimeRunsWithStatus(current.runs, started),
        status,
        explanation: asRecord(started.explanation),
        events: recentEvents,
        plan: undefined,
        planValidation: undefined,
        planningRequest: undefined,
        loading: false,
        action: undefined,
        error: undefined,
        lastUpdatedAt: Date.now(),
      }))
      setRuntimeTask("")
      scheduleOpenTestAgentPanelPersists()
      if (runId) void refreshBlueprintRuntime(runId, { quiet: true })
    } catch (error) {
      const message = readableError(error)
      setPersistence((current) => ({ ...current, saving: false, error: message }))
      setRuntime((current) => ({ ...current, loading: false, action: undefined, error: message }))
    }
  }

  async function endBlueprintRuntime(
    action: BlueprintRunEndAction,
    opts: { auto?: boolean; reason?: string } = {},
  ): Promise<boolean> {
    const runId = runtime().runId
    if (!runId || !platform.endBlueprintRun) return false
    setRuntime((current) => ({ ...current, loading: true, action, error: undefined }))
    try {
      const ended = await platform.endBlueprintRun(runId, action, opts.reason ?? `blueprint UI ${action}`)
      syncAgentPanelUserMessagesFromRuntimeEvents(arrayOfRecords(asRecord(ended.status)?.recent_events))
      setRuntime((current) => ({
        ...current,
        runs: mergeRuntimeRunsWithStatus(current.runs, ended),
        status: asRecord(ended.status),
        events: arrayOfRecords(asRecord(ended.status)?.recent_events),
        loading: false,
        action: undefined,
        lastUpdatedAt: Date.now(),
      }))
      scheduleOpenTestAgentPanelPersists()
      void refreshBlueprintRuntime(runId, { quiet: true })
      return true
    } catch (error) {
      const message = readableError(error)
      setRuntime((current) => ({ ...current, loading: false, action: undefined, error: message }))
      if (opts.auto) {
        showToast({
          variant: "error",
          title: language.t("common.requestFailed"),
          description: message,
        })
      }
      return false
    }
  }

  function scheduleOpenTestAgentPanelPersists() {
    if (!agentPanelTestLogActive()) return
    for (const panel of Object.values(agentPanel.panels)) {
      if (draft.graph.agent_nodes[panel.nodeId]) scheduleTestAgentPanelPersist(panel.nodeId)
    }
  }

  function setAgentPanelTestLogEnabled(enabled: boolean) {
    setTestLogPreferences("enabled", enabled)
    if (enabled) scheduleOpenTestAgentPanelPersists()
    else clearAgentPanelTestPersistTimers()
  }

  function clearAgentPanelTestPersistTimer(nodeId: string) {
    const timer = testAgentPersistTimers[nodeId]
    if (!timer) return
    clearTimeout(timer)
    testAgentPersistTimers[nodeId] = undefined
  }

  function clearAgentPanelTestPersistTimers() {
    for (const nodeId of Object.keys(testAgentPersistTimers)) {
      clearAgentPanelTestPersistTimer(nodeId)
    }
  }

  async function refreshOpenAgentPanelInfos(runId: string) {
    if (!platform.blueprintAgentInfo) return
    const panels = Object.values(agentPanel.panels)
    if (!panels.length) return
    await Promise.all(panels.map((panel) => refreshAgentPanelInfo(runId, panel.nodeId)))
  }

  async function refreshAgentPanelInfo(runId: string | undefined, nodeId: string) {
    if (!platform.blueprintAgentInfo) return
    try {
      const info = await platform.blueprintAgentInfo(runId, nodeId)
      setAgentPanel("panels", nodeId, "info", info)
      const events = arrayOfRecords(asRecord(info)?.streamEvents) as AgentStreamEvent[]
      if (events.length) setAgentPanel("streamEvents", nodeId, events.slice(-240))
    } catch (error) {
      setAgentPanel("panels", nodeId, "error", readableError(error))
    }
  }

  function scheduleTestAgentPanelPersist(nodeId: string, opts: { immediate?: boolean } = {}) {
    if (!agentPanelTestLogActive()) {
      clearAgentPanelTestPersistTimer(nodeId)
      return
    }
    const node = draft.graph.agent_nodes[nodeId]
    if (!node) return
    const panel = agentPanel.panels[nodeId]
    if (!panel) return
    if (testAgentPersistTimers[nodeId]) {
      clearTimeout(testAgentPersistTimers[nodeId])
      testAgentPersistTimers[nodeId] = undefined
    }
    const persist = () => {
      testAgentPersistTimers[nodeId] = undefined
      void persistTestAgentPanelSnapshot(nodeId)
    }
    if (opts.immediate) {
      persist()
      return
    }
    testAgentPersistTimers[nodeId] = setTimeout(persist, 180)
  }

  async function persistTestAgentPanelSnapshot(nodeId: string) {
    const node = draft.graph.agent_nodes[nodeId]
    const panel = agentPanel.panels[nodeId]
    if (!node || !panel || !agentPanelTestLogActive() || !platform.saveBlueprintAgentPanelTest) return
    if (testAgentPersistRunning[nodeId]) {
      testAgentPersistQueued[nodeId] = true
      return
    }
    testAgentPersistRunning[nodeId] = true
    setAgentPanel("panels", nodeId, "testJsonPending", true)
    setAgentPanel("panels", nodeId, "testJsonError", undefined)
    try {
      const saved = await platform.saveBlueprintAgentPanelTest(
        createTestAgentPanelSnapshot({
          node,
          panel,
          events: agentPanel.streamEvents[nodeId] ?? [],
          runId: runtime().runId,
          jsonPath: panel.testJsonPath,
        }),
      )
      const jsonPath = typeof saved.path === "string" ? saved.path : undefined
      setAgentPanel("panels", nodeId, "testJsonPending", false)
      if (jsonPath) setAgentPanel("panels", nodeId, "testJsonPath", jsonPath)
    } catch (error) {
      setAgentPanel("panels", nodeId, "testJsonPending", false)
      setAgentPanel("panels", nodeId, "testJsonError", readableError(error))
    } finally {
      testAgentPersistRunning[nodeId] = false
      if (testAgentPersistQueued[nodeId]) {
        testAgentPersistQueued[nodeId] = false
        scheduleTestAgentPanelPersist(nodeId, { immediate: true })
      }
    }
  }

  function appendAgentStreamEvent(value: unknown) {
    const event = asRecord(value) as AgentStreamEvent | undefined
    if (!event) return
    const nodeId = typeof event.node_id === "string" ? event.node_id : undefined
    const seq = typeof event.seq === "number" ? event.seq : Number(event.seq ?? 0)
    if (Number.isFinite(seq)) setAgentPanel("streamCursor", Math.max(agentPanel.streamCursor, seq))
    if (!nodeId) return
    const current = agentPanel.streamEvents[nodeId] ?? []
    if (seq && current.some((entry) => Number(entry.seq ?? 0) === seq)) return
    setAgentPanel("streamEvents", nodeId, [...current, event].slice(-240))
    syncAgentPanelUserMessageFromStreamEvent(nodeId, event)
    scheduleTestAgentPanelPersist(nodeId)
  }

  function closeFloatingAgentPanels() {
    replaceAgentPanels(Object.fromEntries(Object.entries(agentPanel.panels).filter(([, panel]) => panel.pinned)))
  }

  function closeAgentPanel(nodeId: string) {
    replaceAgentPanels(Object.fromEntries(Object.entries(agentPanel.panels).filter(([id]) => id !== nodeId)))
  }

  function replaceAgentPanels(panels: Record<string, AgentPanelEntry>) {
    setAgentPanel("panels", reconcile(panels))
  }

  function normalizeAgentPanelFrame(frame: { x: number; y: number; width: number; height: number }) {
    return {
      x: frame.x,
      y: frame.y,
      width: Math.max(AGENT_PANEL_MIN_WIDTH, frame.width),
      height: Math.max(AGENT_PANEL_MIN_HEIGHT, frame.height),
    }
  }

  function clampAgentPanelInitialFrame(frame: { x: number; y: number; width: number; height: number }) {
    const rect = canvasRef?.getBoundingClientRect()
    const canvasWidth = rect?.width ?? 900
    const canvasHeight = rect?.height ?? 640
    const width = clamp(frame.width, AGENT_PANEL_MIN_WIDTH, Math.max(AGENT_PANEL_MIN_WIDTH, canvasWidth - AGENT_PANEL_MARGIN * 2))
    const height = clamp(
      frame.height,
      AGENT_PANEL_MIN_HEIGHT,
      Math.max(AGENT_PANEL_MIN_HEIGHT, canvasHeight - AGENT_PANEL_MARGIN * 2),
    )
    return {
      x: clamp(frame.x, AGENT_PANEL_MARGIN, Math.max(AGENT_PANEL_MARGIN, canvasWidth - width - AGENT_PANEL_MARGIN)),
      y: clamp(frame.y, AGENT_PANEL_MARGIN, Math.max(AGENT_PANEL_MARGIN, canvasHeight - height - AGENT_PANEL_MARGIN)),
      width,
      height,
    }
  }

  function updateAgentPanelFrame(nodeId: string, frame: { x: number; y: number; width: number; height: number }) {
    const next = normalizeAgentPanelFrame(frame)
    if (!agentPanel.panels[nodeId]) return
    setAgentPanel("panels", nodeId, (panel) => ({ ...panel, ...next }))
  }

  function agentPanelSize(panel?: AgentPanelEntry) {
    return {
      width: panel?.width ?? AGENT_PANEL_DEFAULT_WIDTH,
      height: panel?.height ?? AGENT_PANEL_DEFAULT_HEIGHT,
    }
  }

  function agentPanelPosition(nodeId: string, width = AGENT_PANEL_DEFAULT_WIDTH, height = AGENT_PANEL_DEFAULT_HEIGHT) {
    const layout = draft.layout.nodes[nodeId]
    const viewport = draft.layout.viewport
    const x = (layout?.x ?? 0) * viewport.zoom + viewport.x + NODE_WIDTH * viewport.zoom + 16
    const y = (layout?.y ?? 0) * viewport.zoom + viewport.y - 18
    return clampAgentPanelInitialFrame({ x, y, width, height })
  }

  async function openAgentPanel(nodeId: string, pinned = false) {
    const existing = agentPanel.panels[nodeId]
    const node = draft.graph.agent_nodes[nodeId]
    const testLogActive = agentPanelTestLogActive() && Boolean(node)
    const size = agentPanelSize(existing)
    const position = agentPanelPosition(nodeId, size.width, size.height)
    setAgentPanel("panels", nodeId, {
      nodeId,
      pinned: pinned || existing?.pinned || false,
      x: position.x,
      y: position.y,
      width: position.width,
      height: position.height,
      input: existing?.input ?? "",
      mode: existing?.mode ?? "default",
      sending: false,
      info: existing?.info,
      userMessages: existing?.userMessages ?? [],
      testJsonPath: existing?.testJsonPath,
      testJsonPending: testLogActive,
      testJsonError: undefined,
    })
    if (testLogActive) scheduleTestAgentPanelPersist(nodeId, { immediate: true })
    await refreshAgentPanelInfo(runtime().runId, nodeId)
    if (testLogActive) scheduleTestAgentPanelPersist(nodeId, { immediate: true })
  }

  function cancelAgentPanelLongPress() {
    if (agentPanelPressFrame !== undefined) {
      cancelAnimationFrame(agentPanelPressFrame)
      agentPanelPressFrame = undefined
    }
    agentPanelLongPress = undefined
    setAgentPanelPress(undefined)
  }

  function tickAgentPanelLongPress() {
    const current = agentPanelLongPress
    if (!current) return
    const progress = clamp((performance.now() - current.startedAt) / AGENT_PANEL_LONG_PRESS_MS, 0, 1)
    setAgentPanelPress({ nodeId: current.nodeId, progress })
    if (progress >= 1) {
      agentPanelLongPress = undefined
      agentPanelPressFrame = undefined
      setAgentPanelPress(undefined)
      setDrag(undefined)
      void openAgentPanel(current.nodeId, false)
      return
    }
    agentPanelPressFrame = requestAnimationFrame(tickAgentPanelLongPress)
  }

  function startAgentPanelLongPress(event: PointerEvent, item: NodeItem) {
    if (item.type !== "agent") return
    cancelAgentPanelLongPress()
    agentPanelLongPress = {
      nodeId: item.id,
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startedAt: performance.now(),
    }
    setAgentPanelPress({ nodeId: item.id, progress: 0 })
    agentPanelPressFrame = requestAnimationFrame(tickAgentPanelLongPress)
  }

  function cancelAgentPanelLongPressOnMove(event: PointerEvent) {
    const current = agentPanelLongPress
    if (!current || current.pointerId !== event.pointerId) return
    const distance = Math.hypot(event.clientX - current.startClientX, event.clientY - current.startClientY)
    if (distance >= AGENT_PANEL_LONG_PRESS_CANCEL_PX) cancelAgentPanelLongPress()
  }

  function endAgentPanelLongPress(event: PointerEvent) {
    const current = agentPanelLongPress
    if (!current || current.pointerId !== event.pointerId) return
    cancelAgentPanelLongPress()
  }

  function appendAgentPanelUserMessage(message: AgentPanelUserMessage) {
    const current = agentPanel.panels[message.nodeId]?.userMessages ?? []
    setAgentPanel("panels", message.nodeId, "userMessages", [...current, message].slice(-120))
  }

  function updateAgentPanelUserMessage(nodeId: string, id: string, patch: Partial<AgentPanelUserMessage>) {
    const current = agentPanel.panels[nodeId]?.userMessages ?? []
    setAgentPanel(
      "panels",
      nodeId,
      "userMessages",
      current.map((message) => (message.id === id ? { ...message, ...patch } : message)),
    )
  }

  function updateAgentPanelUserMessageByRuntimeMessageId(
    nodeId: string,
    runtimeMessageId: string,
    patch: Partial<AgentPanelUserMessage>,
  ) {
    const current = agentPanel.panels[nodeId]?.userMessages ?? []
    if (!current.length) return false
    let changed = false
    const next = current.map((message) => {
      if (message.runtimeMessageId !== runtimeMessageId) return message
      if (isTerminalUserMessageStatus(message.status) && !isTerminalUserMessageStatus(patch.status)) return message
      changed = true
      return { ...message, ...patch }
    })
    if (changed) setAgentPanel("panels", nodeId, "userMessages", next)
    return changed
  }

  function syncAgentPanelUserMessagesFromRuntimeEvents(events: Record<string, unknown>[]) {
    const changedNodes = new Set<string>()
    for (const event of events) {
      const payload = asRecord(event.payload)
      const nodeId = stringValue(event.node_id) ?? stringValue(payload?.node_id)
      const runtimeMessageId = stringValue(payload?.message_id)
      if (!nodeId || !runtimeMessageId) continue
      const eventType = stringValue(event.event_type)
      const runtimeStatus = stringValue(event.status) ?? stringValue(payload?.status)
      const error = stringValue(payload?.error)
      const now = new Date().toISOString()
      let patch: Partial<AgentPanelUserMessage> | undefined
      if (eventType === "AgentQueuedMessageDispatched") {
        patch = { status: "dispatching", runtimeStatus: runtimeStatus ?? "dispatching" }
      } else if (eventType === "AgentQueuedMessageCompleted") {
        patch =
          runtimeStatus === "failed" || error
            ? { status: "failed", runtimeStatus: runtimeStatus ?? "failed", failed_at: now, error }
            : { status: "succeeded", runtimeStatus: runtimeStatus ?? "completed", completed_at: now, error: undefined }
      }
      if (patch && updateAgentPanelUserMessageByRuntimeMessageId(nodeId, runtimeMessageId, patch)) changedNodes.add(nodeId)
    }
    for (const nodeId of changedNodes) {
      if (draft.graph.agent_nodes[nodeId]) scheduleTestAgentPanelPersist(nodeId, { immediate: true })
    }
  }

  function syncAgentPanelUserMessageFromStreamEvent(nodeId: string, event: AgentStreamEvent) {
    const runtimeMessageId = stringValue(event.message_id)
    if (!runtimeMessageId) return
    const kind = stringValue(event.kind)
    const runtimeStatus = stringValue(event.status)
    const agentState = stringValue(event.agent_state)
    const lastError = stringValue(event.last_error)
    const now = new Date().toISOString()
    let patch: Partial<AgentPanelUserMessage> | undefined
    if (lastError) {
      patch = { status: "failed", runtimeStatus: runtimeStatus ?? agentState ?? "failed", failed_at: now, error: lastError }
    } else if (kind === "queue.updated" && runtimeStatus === "dispatching") {
      patch = { status: "dispatching", runtimeStatus }
    } else if (agentState === "running" || agentState === "waiting_for_reply") {
      patch = { status: "running", runtimeStatus: agentState }
    }
    if (patch && updateAgentPanelUserMessageByRuntimeMessageId(nodeId, runtimeMessageId, patch)) {
      if (draft.graph.agent_nodes[nodeId]) scheduleTestAgentPanelPersist(nodeId)
    }
  }

  async function sendAgentPanelMessage(nodeId: string) {
    const panel = agentPanel.panels[nodeId]
    const runId = runtime().runId
    if (!panel || !runId || !platform.queueBlueprintAgentMessage) return
    const text = panel.input
    const testLogActive = agentPanelTestLogActive() && Boolean(draft.graph.agent_nodes[nodeId])
    const messageId = `user-msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    appendAgentPanelUserMessage({
      id: messageId,
      runId,
      nodeId,
      mode: panel.mode,
      text,
      status: "queued",
      created_at: new Date().toISOString(),
    })
    if (testLogActive) {
      scheduleTestAgentPanelPersist(nodeId, { immediate: true })
    }
    setAgentPanel("panels", nodeId, "sending", true)
    setAgentPanel("panels", nodeId, "error", undefined)
    try {
      const queued = await platform.queueBlueprintAgentMessage(runId, nodeId, text, panel.mode)
      const runtimeMessageId = runtimeMessageIdFromQueueResponse(queued)
      updateAgentPanelUserMessage(nodeId, messageId, {
        status: "sent",
        runtimeStatus: "queued",
        runtimeMessageId,
        sent_at: new Date().toISOString(),
      })
      syncAgentPanelUserMessagesFromRuntimeEvents(arrayOfRecords(asRecord(queued.status)?.recent_events))
      if (testLogActive) {
        scheduleTestAgentPanelPersist(nodeId, { immediate: true })
      }
      setAgentPanel("panels", nodeId, "input", "")
      void refreshBlueprintRuntime(runId, { quiet: true })
    } catch (error) {
      const message = readableError(error)
      updateAgentPanelUserMessage(nodeId, messageId, {
        status: "failed",
        failed_at: new Date().toISOString(),
        error: message,
      })
      if (testLogActive) {
        scheduleTestAgentPanelPersist(nodeId, { immediate: true })
      }
      setAgentPanel("panels", nodeId, "error", message)
    } finally {
      setAgentPanel("panels", nodeId, "sending", false)
      if (testLogActive) scheduleTestAgentPanelPersist(nodeId)
    }
  }

  const agentPanelEntries = createMemo(() => Object.values(agentPanel.panels))

  const selectNode = (id: string) => {
    replaceDraft(setSelection(draft, { type: "node", id }))
  }

  const inspectNode = (id: string) => {
    replaceDraft(setInspector(setSelection(draft, { type: "node", id }), { type: "node", id }))
    setPanelMode("inspector")
  }

  const inspectEdge = (id: string) => {
    replaceDraft(setInspector(setSelection(draft, { type: "edge", id }), { type: "edge", id }))
    setPanelMode("inspector")
  }

  const closeInspector = () => {
    replaceDraft(setInspector(draft, undefined))
    setPanelMode("runtime")
  }

  const worldPointFromClient = (clientX: number, clientY: number) => {
    const rect = canvasRef?.getBoundingClientRect()
    const viewport = draft.layout.viewport
    if (!rect) return { x: 0, y: 0 }
    return {
      x: (clientX - rect.left - viewport.x) / viewport.zoom,
      y: (clientY - rect.top - viewport.y) / viewport.zoom,
    }
  }

  const positionForClient = (kind: BlueprintAddNodeKind, clientX: number, clientY: number) => {
    const point = worldPointFromClient(clientX, clientY)
    const size = sizeForAddKind(kind)
    return snapPosition({
      x: point.x - size.width / 2,
      y: point.y - size.height / 2,
    })
  }

  const positionAtCenter = (kind: BlueprintAddNodeKind) => {
    const rect = canvasRef?.getBoundingClientRect()
    const viewport = draft.layout.viewport
    const size = sizeForAddKind(kind)
    if (!rect) return undefined
    return snapPosition({
      x: (rect.width / 2 - viewport.x) / viewport.zoom - size.width / 2,
      y: (rect.height / 2 - viewport.y) / viewport.zoom - size.height / 2,
    })
  }

  const addNodeFromOption = (option: AddNodeOption, position?: BlueprintNodeLayout) => {
    replaceDraft(
      option.kind === "script"
        ? addScriptNode(draft, { position, script: option.script })
        : addNode(draft, { kind: option.kind, position }),
    )
    setConnection(undefined)
    setNodeSearch(undefined)
  }

  const openNodeSearch = (clientX: number, clientY: number) => {
    setGlobalConfigOpen(false)
    setScriptEditorMenuOpen(false)
    setNodeSearchQuery("")
    setNodeSearch({ clientX, clientY })
  }

  const addNodeFromSearch = (option: AddNodeOption) => {
    const current = nodeSearch()
    addNodeFromOption(
      option,
      current ? positionForClient(option.kind, current.clientX, current.clientY) : positionAtCenter(option.kind),
    )
  }

  const openScriptNodeInEditor = async (script: Pick<BlueprintScriptNode, "module_path">) => {
    if (!script.module_path || !platform.openBlueprintScriptInEditor) return
    try {
      const result = await platform.openBlueprintScriptInEditor(projectDirectory, script.module_path, selectedScriptEditor().id)
      const path = typeof result?.path === "string" ? result.path : projectDirectory
      showToast({
        variant: "success",
        title: language.t("blueprint.script.openSuccess" as never),
        description: language.t("blueprint.script.openSuccessDescription" as never, { path }),
      })
    } catch (error) {
      showToast({
        variant: "error",
        title: language.t("blueprint.script.openFailed" as never),
        description: readableError(error),
      })
    }
  }

  const createScriptNodeAtSearch = async (name: string, description: string, anchor?: NodeSearchState) => {
    if (!platform.createBlueprintScriptNode) {
      showToast({
        variant: "error",
        title: language.t("blueprint.script.createFailed" as never),
        description: language.t("blueprint.runtime.unavailable" as never),
      })
      return
    }
    try {
      const result = await platform.createBlueprintScriptNode(projectDirectory, name, description)
      const discoveredScript =
        normalizeScriptCatalogNode(result?.node) ??
        normalizeScriptCatalogNode({
          module_path: result?.module_path,
          function_name: result?.function_name,
          title: name,
          description,
          inputs: [{ name: "payload", type: "dict", required: true }],
          outputs: [{ name: "result", type: "dict", required: true }],
        })
      const script =
        discoveredScript && description && !discoveredScript.description
          ? { ...discoveredScript, description }
          : discoveredScript
      refreshScriptCatalog()
      if (script) {
        addNodeFromOption(
          { kind: "script", label: script.title, description: scriptSignature(script), script },
          anchor ? positionForClient("script", anchor.clientX, anchor.clientY) : positionAtCenter("script"),
        )
        await openScriptNodeInEditor(script)
      }
    } catch (error) {
      showToast({
        variant: "error",
        title: language.t("blueprint.script.createFailed" as never),
        description: readableError(error),
      })
    }
  }

  const openCreateScriptNodeDialog = () => {
    if (!platform.createBlueprintScriptNode) {
      showToast({
        variant: "error",
        title: language.t("blueprint.script.createFailed" as never),
        description: language.t("blueprint.script.bridgeUnavailable" as never),
      })
      return
    }
    const anchor = nodeSearch()
    setNodeSearch(undefined)
    dialog.show(() => <BlueprintScriptCreateDialog onCreate={(name, description) => createScriptNodeAtSearch(name, description, anchor)} />)
  }

  const deleteCurrent = () => {
    replaceDraft(deleteSelection(draft))
    setConnection(undefined)
  }

  const resetDraft = () => {
    replaceDraft(createDefaultBlueprintDraft(projectDirectory))
    setConnection(undefined)
  }

  const resetViewport = () => {
    setDraft("layout", "viewport", { x: 48, y: 96, zoom: 1 })
  }

  const fitViewport = () => {
    const rect = canvasRef?.getBoundingClientRect()
    const layouts = Object.entries(draft.layout.nodes)
    if (!rect || layouts.length === 0) return

    const bounds = layouts.reduce(
      (acc, [id, layout]) => {
        const size = nodeSize(draft, id)
        return {
          left: Math.min(acc.left, layout.x),
          top: Math.min(acc.top, layout.y),
          right: Math.max(acc.right, layout.x + size.width),
          bottom: Math.max(acc.bottom, layout.y + size.height),
        }
      },
      {
        left: Number.POSITIVE_INFINITY,
        top: Number.POSITIVE_INFINITY,
        right: Number.NEGATIVE_INFINITY,
        bottom: Number.NEGATIVE_INFINITY,
      },
    )
    const width = Math.max(bounds.right - bounds.left, 1)
    const height = Math.max(bounds.bottom - bounds.top, 1)
    const zoom = clamp(Math.min((rect.width - 96) / width, (rect.height - 96) / height), MIN_ZOOM, MAX_ZOOM)

    setDraft("layout", "viewport", {
      zoom,
      x: rect.width / 2 - (bounds.left + width / 2) * zoom,
      y: rect.height / 2 - (bounds.top + height / 2) * zoom,
    })
  }

  const handleWheel = (event: WheelEvent) => {
    event.preventDefault()
    setNodeSearch(undefined)
    const rect = canvasRef?.getBoundingClientRect()
    if (!rect) return

    const viewport = draft.layout.viewport
    const localX = event.clientX - rect.left
    const localY = event.clientY - rect.top
    const worldX = (localX - viewport.x) / viewport.zoom
    const worldY = (localY - viewport.y) / viewport.zoom
    const zoom = clamp(viewport.zoom * (event.deltaY > 0 ? 0.9 : 1.1), MIN_ZOOM, MAX_ZOOM)

    setDraft("layout", "viewport", {
      zoom,
      x: localX - worldX * zoom,
      y: localY - worldY * zoom,
    })
  }

  const handleCanvasPointerDown = (event: PointerEvent) => {
    closeFloatingAgentPanels()
    cancelAgentPanelLongPress()
    setNodeSearch(undefined)
    if (event.button === 0) {
      replaceDraft(setInspector(setSelection(draft, undefined), undefined))
      return
    }
    if (event.button !== 2) return
    event.preventDefault()
    replaceDraft(setSelection(draft, undefined))
    setDrag({
      type: "pan-pending",
      startClientX: event.clientX,
      startClientY: event.clientY,
      startX: draft.layout.viewport.x,
      startY: draft.layout.viewport.y,
    })
  }

  const handleCanvasContextMenu = (event: MouseEvent) => {
    const target = event.target as HTMLElement | null
    if (target?.closest("[data-blueprint-node]")) return
    event.preventDefault()
  }

  const handleCanvasDragOver = (event: DragEvent) => {
    if (!event.dataTransfer?.types.includes("application/x-gulicode-blueprint-node")) return
    event.preventDefault()
  }

  const addNodeFromDragEvent = (event: DragEvent, position: BlueprintNodeLayout | undefined) => {
    const kind = event.dataTransfer?.getData("application/x-gulicode-blueprint-node") as BlueprintAddNodeKind
    if (!kind) return false
    if (kind === "script") {
      const scriptText = event.dataTransfer?.getData("application/x-gulicode-blueprint-script-node")
      const script = scriptText ? normalizeScriptCatalogNodeFromJson(scriptText) : undefined
      if (!script) return false
      addNodeFromOption({ kind: "script", label: script.title, description: scriptSignature(script), script }, position)
      return true
    }
    replaceDraft(addNode(draft, { kind, position }))
    setConnection(undefined)
    return true
  }

  const handleCanvasDrop = (event: DragEvent) => {
    const kind = event.dataTransfer?.getData("application/x-gulicode-blueprint-node") as BlueprintAddNodeKind
    if (!kind) return
    event.preventDefault()
    addNodeFromDragEvent(event, positionForClient(kind, event.clientX, event.clientY))
  }

  const isAddNodeDrag = (dataTransfer?: DataTransfer | null) =>
    !!dataTransfer?.types.includes("application/x-gulicode-blueprint-node")

  const clientInsideCanvas = (clientX: number, clientY: number) => {
    const rect = canvasRef?.getBoundingClientRect()
    if (!rect) return false
    return clientX >= rect.left && clientX <= rect.right && clientY >= rect.top && clientY <= rect.bottom
  }

  const nodeSearchStyle = () => {
    const current = nodeSearch()
    const rect = canvasRef?.getBoundingClientRect()
    if (!current || !rect) return {}
    const localX = current.clientX - rect.left
    const localY = current.clientY - rect.top
    const x = clamp(localX, 8, Math.max(8, rect.width - NODE_SEARCH_CARD_WIDTH - 8))
    const y = clamp(localY, 8, Math.max(8, rect.height - NODE_SEARCH_CARD_MAX_HEIGHT - 8))
    return {
      left: `${x}px`,
      top: `${y}px`,
      width: `${NODE_SEARCH_CARD_WIDTH}px`,
    } as JSX.CSSProperties
  }

  const handleWindowDragOver = (event: DragEvent) => {
    if (!isAddNodeDrag(event.dataTransfer)) return
    if (!clientInsideCanvas(event.clientX, event.clientY)) return
    event.preventDefault()
  }

  const handleWindowDrop = (event: DragEvent) => {
    const kind = event.dataTransfer?.getData("application/x-gulicode-blueprint-node") as BlueprintAddNodeKind
    if (!kind || !clientInsideCanvas(event.clientX, event.clientY)) return
    event.preventDefault()
    event.stopPropagation()
    addNodeFromDragEvent(event, positionForClient(kind, event.clientX, event.clientY))
  }

  const handleNodePointerDown = (event: PointerEvent, item: NodeItem) => {
    const id = item.id
    closeFloatingAgentPanels()
    setNodeSearch(undefined)
    if (event.button === 2) {
      cancelAgentPanelLongPress()
      event.stopPropagation()
      selectNode(id)
      return
    }
    if (event.button !== 0) return
    event.stopPropagation()

    selectNode(id)
    startAgentPanelLongPress(event, item)
    const layout = draft.layout.nodes[id]
    if (!layout) return

    setDrag({
      type: "node",
      id,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startX: layout.x,
      startY: layout.y,
      zoom: draft.layout.viewport.zoom,
    })
  }

  const handleAgentPanelMovePointerDown = (event: PointerEvent, panel: AgentPanelEntry) => {
    if (event.button !== 0) return
    event.preventDefault()
    event.stopPropagation()
    cancelAgentPanelLongPress()
    setConnection(undefined)
    const size = agentPanelSize(panel)
    setDrag({
      type: "agent-panel-move",
      nodeId: panel.nodeId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startX: panel.x,
      startY: panel.y,
      width: size.width,
      height: size.height,
    })
  }

  const handleAgentPanelResizePointerDown = (event: PointerEvent, panel: AgentPanelEntry) => {
    if (event.button !== 0) return
    event.preventDefault()
    event.stopPropagation()
    cancelAgentPanelLongPress()
    setConnection(undefined)
    const size = agentPanelSize(panel)
    setDrag({
      type: "agent-panel-resize",
      nodeId: panel.nodeId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startX: panel.x,
      startY: panel.y,
      startWidth: size.width,
      startHeight: size.height,
    })
  }

  const handleOutputPortPointerDown = (event: PointerEvent, id: string, portName = DEFAULT_OUTPUT_PORT) => {
    if (event.button !== 0) return
    cancelAgentPanelLongPress()
    event.preventDefault()
    event.stopPropagation()
    selectNode(id)
    setConnection({
      source: id,
      output_port: portName,
      pointer: worldPointFromClient(event.clientX, event.clientY),
    })
  }

  const connectPorts = (source: string, outputPort: string, target: string, inputPort: string) => {
    const result = canConnectPorts(draft, source, outputPort, target, inputPort)
    if (!result.ok) {
      showToast({
        variant: "error",
        title: language.t("blueprint.connection.invalid" as never),
        description:
          result.reason === "type_mismatch"
            ? language.t("blueprint.connection.typeMismatch" as never, {
                source: result.sourceType ?? "?",
                target: result.targetType ?? "?",
              } as never)
            : language.t("blueprint.connection.unknownPort" as never),
      })
      return
    }
    replaceDraft(addEdge(draft, source, target, "exec", outputPort, inputPort))
  }

  const handleInputPortPointerUp = (event: PointerEvent, id: string, portName = DEFAULT_INPUT_PORT) => {
    const current = connection()
    if (!current) return
    cancelAgentPanelLongPress()
    event.preventDefault()
    event.stopPropagation()
    if (current.source !== id) {
      connectPorts(current.source, current.output_port, id, portName)
    }
    setConnection(undefined)
  }

  const handlePointerMove = (event: PointerEvent) => {
    cancelAgentPanelLongPressOnMove(event)

    const currentConnection = connection()
    if (currentConnection) {
      setConnection({ ...currentConnection, pointer: worldPointFromClient(event.clientX, event.clientY) })
    }

    const current = drag()
    if (!current) return

    if (current.type === "pan-pending") {
      const dx = event.clientX - current.startClientX
      const dy = event.clientY - current.startClientY
      if (Math.hypot(dx, dy) < RIGHT_CLICK_PAN_THRESHOLD) return
      setDrag({ ...current, type: "pan" })
      setDraft("layout", "viewport", "x", current.startX + dx)
      setDraft("layout", "viewport", "y", current.startY + dy)
      return
    }

    if (current.type === "pan") {
      setDraft("layout", "viewport", "x", current.startX + event.clientX - current.startClientX)
      setDraft("layout", "viewport", "y", current.startY + event.clientY - current.startClientY)
      return
    }

    if (current.type === "agent-panel-move") {
      updateAgentPanelFrame(current.nodeId, {
        x: current.startX + event.clientX - current.startClientX,
        y: current.startY + event.clientY - current.startClientY,
        width: current.width,
        height: current.height,
      })
      return
    }

    if (current.type === "agent-panel-resize") {
      updateAgentPanelFrame(current.nodeId, {
        x: current.startX,
        y: current.startY,
        width: current.startWidth + event.clientX - current.startClientX,
        height: current.startHeight + event.clientY - current.startClientY,
      })
      return
    }

    if (!draft.layout.nodes[current.id]) return
    const snapped = snapPosition({
      x: current.startX + (event.clientX - current.startClientX) / current.zoom,
      y: current.startY + (event.clientY - current.startClientY) / current.zoom,
    })
    setDraft("layout", "nodes", current.id, snapped)
  }

  const handlePointerUp = (event: PointerEvent) => {
    endAgentPanelLongPress(event)
    const currentDrag = drag()

    const currentConnection = connection()
    if (currentConnection) {
      const target = document.elementFromPoint(event.clientX, event.clientY) as HTMLElement | null
      const inputPort = target?.closest("[data-blueprint-port='input']") as HTMLElement | null
      const targetNode = inputPort?.dataset.blueprintNodeId
      const targetPort = inputPort?.dataset.blueprintPortName || DEFAULT_INPUT_PORT
      if (targetNode && targetNode !== currentConnection.source) {
        connectPorts(currentConnection.source, currentConnection.output_port, targetNode, targetPort)
      }
    }
    if (currentDrag?.type === "pan-pending") {
      event.preventDefault()
      setDrag(undefined)
      setConnection(undefined)
      openNodeSearch(currentDrag.startClientX, currentDrag.startClientY)
      return
    }
    setDrag(undefined)
    setConnection(undefined)
  }

  const handlePointerCancel = (event: PointerEvent) => {
    endAgentPanelLongPress(event)
    setDrag(undefined)
    setConnection(undefined)
  }

  const handleKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape" && nodeSearch()) {
      event.preventDefault()
      setNodeSearch(undefined)
      return
    }
    if (event.key !== "Delete" && event.key !== "Backspace") return
    if (!draft.selection) return
    const target = event.target as HTMLElement | null
    const tagName = target?.tagName.toLowerCase()
    if (target?.isContentEditable || tagName === "input" || tagName === "textarea" || tagName === "select") return
    event.preventDefault()
    deleteCurrent()
  }

  const refreshProgressAnchor = () => setProgressAnchorVersion((version) => version + 1)

  onMount(() => {
    void refreshEditorCatalog()
    window.addEventListener("pointermove", handlePointerMove)
    window.addEventListener("pointerup", handlePointerUp)
    window.addEventListener("pointercancel", handlePointerCancel)
    window.addEventListener("dragover", handleWindowDragOver, true)
    window.addEventListener("drop", handleWindowDrop, true)
    window.addEventListener("resize", refreshProgressAnchor)
    const progressResizeObserver =
      typeof ResizeObserver === "undefined"
        ? undefined
        : new ResizeObserver(() => {
            refreshProgressAnchor()
          })
    if (rootRef) progressResizeObserver?.observe(rootRef)
    if (canvasRef) progressResizeObserver?.observe(canvasRef)
    onCleanup(() => {
      window.removeEventListener("pointermove", handlePointerMove)
      window.removeEventListener("pointerup", handlePointerUp)
      window.removeEventListener("pointercancel", handlePointerCancel)
      window.removeEventListener("dragover", handleWindowDragOver, true)
      window.removeEventListener("drop", handleWindowDrop, true)
      window.removeEventListener("resize", refreshProgressAnchor)
      progressResizeObserver?.disconnect()
      cancelAgentPanelLongPress()
    })
  })

  const gridSize = createMemo(() => `${GRID_SIZE * draft.layout.viewport.zoom}px ${GRID_SIZE * draft.layout.viewport.zoom}px`)
  const gridPosition = createMemo(() => {
    const size = GRID_SIZE * draft.layout.viewport.zoom
    return `${mod(draft.layout.viewport.x, size)}px ${mod(draft.layout.viewport.y, size)}px`
  })

  return (
    <div
      ref={rootRef}
      id="blueprint-panel"
      class="relative size-full min-w-0 h-full flex flex-col bg-background-base"
      style={BLUEPRINT_THEME}
      tabIndex={0}
      onKeyDown={handleKeyDown}
    >
      <div
        data-blueprint-float-handle
        class="h-10 shrink-0 flex items-center justify-between gap-3 border-b border-border-weaker-base bg-background-strong px-3"
        classList={{
          "cursor-grab active:cursor-grabbing": !props.floating,
        }}
        style={BLUEPRINT_CHROME_THEME}
        onPointerDown={handleBlueprintHeaderPointerDown}
      >
        <div class="flex min-w-0 items-center gap-2">
          <Icon size="small" name="blueprint" class="text-[var(--blueprint-edge-active)]" />
          <div class="min-w-0 truncate text-13-medium text-text-strong">
            {language.t("session.header.blueprint")}
          </div>
          <Show when={!draftReady()}>
            <div class="text-11-regular text-text-weaker">{language.t("common.loading")}</div>
          </Show>
          <Show when={headerStatus()}>
            {(status) => <BlueprintHeaderStatus status={status()} />}
          </Show>
        </div>
        <div class="flex items-center gap-1 shrink-0">
          <Show when={props.floating}>
            <Tooltip placement="bottom" value={language.t("blueprint.window.dock" as never)}>
              <IconButton
                data-blueprint-dock-button
                icon="layout-right"
                variant="ghost"
                class="h-6 w-6 shrink-0"
                onClick={() => {
                  void dockBlueprintWindow()
                }}
                aria-label={language.t("blueprint.window.dock" as never)}
              />
            </Tooltip>
          </Show>
          <Tooltip placement="bottom" value={language.t("common.close")}>
            <IconButton
              icon="close-small"
              variant="ghost"
              class="h-6 w-6 shrink-0"
              onClick={() => {
                void closeBlueprintPanel()
              }}
              aria-label={language.t("common.close")}
            />
          </Tooltip>
        </div>
      </div>

      <div
        class="h-10 shrink-0 flex items-center justify-between gap-2 border-b border-border-weaker-base bg-background-base px-2"
        style={BLUEPRINT_CHROME_THEME}
      >
        <div class="flex min-w-0 items-center gap-1">
          <BlueprintDocumentSelect
            items={blueprintPicker().items}
            selectedId={currentBlueprintId()}
            selectedName={currentBlueprintName()}
            loading={blueprintPicker().loading}
            disabled={runtimeBusy() || persistence().loading || persistence().saving || projectWorkdirRelocating() || blueprintPicker().loading}
            onSelect={(blueprintId) => void selectProjectBlueprint(blueprintId)}
            onCreate={openCreateBlueprintDialog}
          />
          <DropdownMenu
            open={scriptEditorMenuOpen()}
            onOpenChange={(open) => {
              setScriptEditorMenuOpen(open)
              if (open) {
                setGlobalConfigOpen(false)
                setNodeSearch(undefined)
                void refreshEditorCatalog()
              }
            }}
          >
            <DropdownMenu.Trigger
              data-blueprint-script-editor-select
              as={Button}
              size="small"
              variant="ghost"
              icon="code"
              class="h-7 max-w-56 px-2"
              title={language.t("blueprint.editor.select" as never)}
            >
              <span class="hidden min-w-0 truncate lg:inline">{selectedScriptEditor().label}</span>
              <Icon size="small" name="chevron-down" class="shrink-0 text-icon-weak" />
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content class="mt-1 w-60">
                <Show when={!editorCatalog().loading} fallback={<div class="px-2 py-2 text-12-regular text-text-weaker">{language.t("blueprint.editor.loading" as never)}</div>}>
                  <For each={scriptEditorCandidates()}>
                    {(editor) => (
                      <DropdownMenu.Item
                        onSelect={() => {
                          setScriptEditorPreferences("editorId", editor.id)
                          setScriptEditorMenuOpen(false)
                        }}
                      >
                        <Icon size="small" name={editor.id === selectedScriptEditor().id ? "check-small" : "code"} />
                        <div class="flex min-w-0 flex-col">
                          <DropdownMenu.ItemLabel class="truncate">{editor.label}</DropdownMenu.ItemLabel>
                          <DropdownMenu.ItemDescription class="truncate">{editor.source}</DropdownMenu.ItemDescription>
                        </div>
                      </DropdownMenu.Item>
                    )}
                  </For>
                </Show>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu>
          <div class="relative flex shrink-0">
            <Button
              data-blueprint-global-config-toggle
              size="small"
              variant="ghost"
              icon="blueprint"
              data-active={globalConfigOpen()}
              class="h-7 px-2"
              disabled={blueprintConfigLocked()}
              aria-expanded={globalConfigOpen()}
              title={
                blueprintConfigLocked()
                  ? language.t("blueprint.globalConfig.locked" as never)
                  : language.t("blueprint.globalConfig.title")
              }
              onClick={() => {
                if (blueprintConfigLocked()) return
                setNodeSearch(undefined)
                setScriptEditorMenuOpen(false)
                setGlobalConfigOpen((open) => !open)
              }}
            >
              <span class="hidden lg:inline">{language.t("blueprint.globalConfig.title")}</span>
              <Icon
                size="small"
                name="chevron-down"
                class={`text-icon-weak transition-transform ${globalConfigOpen() ? "rotate-180" : ""}`}
              />
            </Button>
            <Show when={globalConfigOpen() && !blueprintConfigLocked()}>
              <BlueprintGlobalConfigPanel
                config={currentConfig()}
                onConfigChange={updateConfigField}
                onProjectWorkdirBrowse={() => void pickProjectWorkdir(currentConfig().project_workdir)}
                locked={blueprintConfigLocked()}
                skillCount={catalog().skills.length}
                ruleCount={catalog().rules.length}
                skillError={catalog().skillError}
                ruleError={catalog().ruleError}
                invalidFields={configIssues().map((issue) => issue.field)}
                detectingPython={pythonDetecting()}
                pythonDetectFailed={pythonDetectFailed()}
                onDetectPython={detectAndApplyPythonPath}
              />
            </Show>
          </div>
          <Show when={platform.saveBlueprintAgentPanelTest}>
            <Tooltip
              placement="bottom"
              value={testLogPreferences.enabled !== false ? "Agent panel test log on" : "Agent panel test log off"}
            >
              <div
                data-blueprint-test-log-toggle
                data-enabled={testLogPreferences.enabled !== false}
                class="flex h-7 shrink-0 items-center gap-1 rounded-sm px-2 text-text-base hover:bg-surface-base-hover"
              >
                <Icon size="small" name="status" class="text-icon-weak" />
                <ToggleSwitch
                  checked={testLogPreferences.enabled !== false}
                  onChange={setAgentPanelTestLogEnabled}
                  hideLabel
                >
                  Agent panel test log
                </ToggleSwitch>
              </div>
            </Tooltip>
          </Show>
          <Tooltip placement="bottom" value={language.t("blueprint.diff.title" as never)}>
            <Button
              data-blueprint-diff-toggle
              size="small"
              variant={blueprintDiffOpen() ? "secondary" : "ghost"}
              icon="eye"
              class="h-7 px-2"
              disabled={!blueprintDiffAvailable()}
              aria-expanded={blueprintDiffOpen()}
              onClick={() => {
                if (!blueprintDiffAvailable()) return
                setNodeSearch(undefined)
                setGlobalConfigOpen(false)
                setBlueprintDiffOpen((open) => !open)
                void refreshBlueprintRunDiff(runtime().runId, { quiet: true })
              }}
            >
              <span class="hidden lg:inline">{blueprintDiffButtonLabel()}</span>
            </Button>
          </Tooltip>
        </div>
        <div class="flex shrink-0 items-center gap-1">
          <Tooltip placement="bottom" value={language.t("blueprint.runtime.refresh")}>
            <IconButton
              icon="reset"
              variant="ghost"
              class="h-7 w-7"
              disabled={!runtime().runId || runtime().loading}
              onClick={() => void refreshBlueprintRuntime()}
              aria-label={language.t("blueprint.runtime.refresh")}
            />
          </Tooltip>
          <Tooltip
            placement="bottom"
            value={language.t(runtimePanelOpen() ? ("blueprint.runtime.collapse" as never) : ("blueprint.runtime.expand" as never))}
          >
            <IconButton
              data-blueprint-runtime-toggle
              icon="status"
              variant={runtimePanelOpen() ? "secondary" : "ghost"}
              class="h-7 w-7"
              onClick={() => setPanelMode(runtimePanelOpen() ? undefined : "runtime")}
              aria-label={language.t(runtimePanelOpen() ? ("blueprint.runtime.collapse" as never) : ("blueprint.runtime.expand" as never))}
              aria-expanded={runtimePanelOpen()}
            />
          </Tooltip>
          <div class="hidden xl:block text-11-regular text-text-weaker">
            {runtimeGraph().edges.length} {language.t("blueprint.graph.edges")}
          </div>
          <Tooltip placement="bottom" value={language.t("blueprint.toolbar.fit")}>
            <IconButton
              icon="selector"
              variant="ghost"
              class="h-7 w-7"
              onClick={fitViewport}
              aria-label={language.t("blueprint.toolbar.fit")}
            />
          </Tooltip>
          <Tooltip placement="bottom" value={language.t("blueprint.toolbar.resetView")}>
            <IconButton
              icon="reset"
              variant="ghost"
              class="h-7 w-7"
              onClick={resetViewport}
              aria-label={language.t("blueprint.toolbar.resetView")}
            />
          </Tooltip>
          <Tooltip placement="bottom" value={language.t("blueprint.toolbar.resetDraft")}>
            <Button size="small" variant="ghost" class="h-7 px-2" onClick={resetDraft}>
              {language.t("common.reset")}
            </Button>
          </Tooltip>
        </div>
      </div>

      <div class="flex-1 min-h-0 min-w-0 flex bg-background-stronger">
        <div
          ref={canvasRef}
          class="relative flex-1 min-w-0 min-h-0 overflow-hidden touch-none outline-none"
          classList={{
            "cursor-grabbing": drag()?.type === "pan" || drag()?.type === "agent-panel-move",
            "cursor-nwse-resize": drag()?.type === "agent-panel-resize",
            "cursor-default":
              drag()?.type !== "pan" && drag()?.type !== "agent-panel-move" && drag()?.type !== "agent-panel-resize",
          }}
          style={{
            "background-color": "var(--blueprint-canvas-base)",
            "background-image":
              "linear-gradient(var(--blueprint-grid) 1px, transparent 1px), linear-gradient(90deg, var(--blueprint-grid) 1px, transparent 1px), radial-gradient(circle at 1px 1px, rgba(103, 232, 249, 0.22) 1px, transparent 1.5px), linear-gradient(135deg, rgba(37, 99, 235, 0.12), rgba(20, 184, 166, 0.04) 44%, transparent 72%)",
            "background-size": `${gridSize()}, ${gridSize()}, ${GRID_SIZE * draft.layout.viewport.zoom * 4}px ${
              GRID_SIZE * draft.layout.viewport.zoom * 4
            }px, 100% 100%`,
            "background-position": `${gridPosition()}, ${gridPosition()}, ${gridPosition()}, 0 0`,
          }}
          onWheel={handleWheel}
          onPointerDown={handleCanvasPointerDown}
          onContextMenu={handleCanvasContextMenu}
          onDragOver={handleCanvasDragOver}
          onDrop={handleCanvasDrop}
        >
          <div class="pointer-events-auto absolute left-3 top-3 z-30">
            <Tooltip placement="right" value={scriptCompileTooltip()}>
              <Button
                data-blueprint-script-compile
                size="small"
                variant="secondary"
                icon="code"
                class="h-8 border border-[rgba(103,232,249,0.34)] bg-[#071019]/92 px-3 text-[#e8f7ff] shadow-[0_10px_28px_rgba(0,0,0,0.28)] hover:bg-[#0d1b2a]"
                disabled={scriptCompileDisabled()}
                onPointerDown={(event: PointerEvent) => event.stopPropagation()}
                onClick={(event: MouseEvent) => {
                  event.stopPropagation()
                  void compileBlueprintScripts()
                }}
              >
                {language.t((scriptCompiling() ? "blueprint.script.compiling" : "blueprint.script.compile") as never)}
              </Button>
            </Tooltip>
          </div>
          <div
            class="absolute left-0 top-0"
            style={{
              transform: `translate3d(${draft.layout.viewport.x}px, ${draft.layout.viewport.y}px, 0) scale(${draft.layout.viewport.zoom})`,
              "transform-origin": "0 0",
            }}
          >
            <svg class="absolute left-0 top-0 overflow-visible" width="1" height="1" aria-hidden="true">
              <For each={visibleEdgeGroups()}>
                {(group) => {
                  const geometry = () => edgeGroupGeometry(draft, group.edges)
                  const primaryEdge = () => group.edges[0]
                  const selected = () =>
                    draft.selection?.type === "edge" && group.edges.some((edge) => edge.id === draft.selection?.id)
                  const flowing = () => group.edges.some((edge) => runtimeEdgeFlowIds().has(edge.id))
                  const hovered = () => hoveredEdgeGroupId() === group.id
                  const active = () => selected() || hovered() || flowing()
                  const strokeColor = () => (active() ? "var(--blueprint-edge-active)" : "var(--blueprint-edge)")
                  const marker = () => (active() ? "url(#blueprint-arrow-active)" : "url(#blueprint-arrow)")
                  return (
                    <g
                      data-blueprint-edge-group={group.id}
                      data-blueprint-edge-count={group.edges.length}
                      onPointerEnter={() => setHoveredEdgeGroupId(group.id)}
                      onPointerLeave={() => setHoveredEdgeGroupId((current) => (current === group.id ? undefined : current))}
                    >
                      <For each={geometry().segments}>
                        {(segment) => (
                          <>
                            <path
                              d={segment.d}
                              fill="none"
                              stroke="transparent"
                              stroke-width="14"
                              style={{ "pointer-events": "stroke" }}
                              class="cursor-pointer"
                              onPointerDown={(event) => {
                                event.stopPropagation()
                                const edge = primaryEdge()
                                if (edge) inspectEdge(edge.id)
                              }}
                            />
                            <path
                              d={segment.d}
                              fill="none"
                              stroke={strokeColor()}
                              stroke-width={active() ? 2 : 1.5}
                              stroke-linecap="round"
                              stroke-linejoin="round"
                              marker-end={segment.markerEnd ? marker() : undefined}
                              style={{ "pointer-events": "none" }}
                            />
                          </>
                        )}
                      </For>
                      <Show when={geometry().hub}>
                        {(hub) => (
                          <circle
                            data-blueprint-edge-fan-hub
                            cx={hub().x}
                            cy={hub().y}
                            r={3.2}
                            fill={strokeColor()}
                            stroke="#071019"
                            stroke-width="1.2"
                            style={{ "pointer-events": "none" }}
                          />
                        )}
                      </Show>
                      <Show when={flowing()}>
                        <g data-blueprint-runtime-flow style={{ "pointer-events": "none" }}>
                          <For each={group.edges}>
                            {(edge) => (
                              <For each={BLUEPRINT_RUNTIME_FLOW_DOTS}>
                                {(dot) => (
                                  <circle r="2.7" fill="#bbf7d0" opacity="0.95">
                                    <animateMotion
                                      path={edgePath(draft, edge)}
                                      dur="1.45s"
                                      begin={`-${dot * 0.16}s`}
                                      repeatCount="indefinite"
                                      calcMode="linear"
                                    />
                                  </circle>
                                )}
                              </For>
                            )}
                          </For>
                        </g>
                      </Show>
                    </g>
                  )
                }}
              </For>
              <Show when={connection()}>
                {(current) => (
                  <path
                    d={connectionPath(draft, current())}
                    fill="none"
                    stroke="var(--blueprint-edge-active)"
                    stroke-width="1.5"
                    stroke-dasharray="4 4"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    marker-end="url(#blueprint-arrow-active)"
                    style={{ "pointer-events": "none" }}
                  />
                )}
              </Show>
              <defs>
                <marker id="blueprint-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                  <path d="M1 1L7 4L1 7" fill="none" stroke="var(--blueprint-edge)" stroke-width="1.5" />
                </marker>
                <marker id="blueprint-arrow-active" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                  <path d="M1 1L7 4L1 7" fill="none" stroke="var(--blueprint-edge-active)" stroke-width="1.5" />
                </marker>
              </defs>
            </svg>

            <For each={nodes()}>
              {(item) => (
                <BlueprintNodeView
                  item={item}
                  title={nodeTitle(language.t, item)}
                  subtitle={nodeSubtitle(language.t, item)}
                  selected={draft.selection?.type === "node" && draft.selection.id === item.id}
                  inspecting={draft.inspector?.type === "node" && draft.inspector.id === item.id}
                  connecting={connection()?.source === item.id}
                  runtimeVisualState={runtimeNodeVisualState(runtimeNodeVisualStates(), item.id)}
                  hasIncomingEdge={incomingNodeIds().has(item.id)}
                  hasOutgoingEdge={outgoingNodeIds().has(item.id)}
                  isConnectTargetVisible={!!connection() && connection()?.source !== item.id}
                  agentPanelProgress={agentPanelPress()?.nodeId === item.id ? (agentPanelPress()?.progress ?? 0) : 0}
                  layout={draft.layout.nodes[item.id]}
                  onPointerDown={(event) => handleNodePointerDown(event, item)}
                  onDoubleClick={() => {
                    if (item.type === "script") {
                      void openScriptNodeInEditor(item.node)
                      return
                    }
                    inspectNode(item.id)
                  }}
                  onDelete={() => replaceDraft(deleteNode(draft, item.id))}
                  onEdit={() => inspectNode(item.id)}
                  onInfoPanel={() => void openAgentPanel(item.id, false)}
                  onScriptCollapsedChange={(collapsed) => replaceDraft(updateScriptNode(draft, item.id, { collapsed }))}
                  onOutputPointerDown={(event, portName) => handleOutputPortPointerDown(event, item.id, portName)}
                  onInputPointerUp={(event, portName) => handleInputPortPointerUp(event, item.id, portName)}
                />
              )}
            </For>
          </div>
          <Show when={nodeSearch()}>
            <div
              data-blueprint-node-search
              class="absolute z-40 flex max-h-[360px] flex-col overflow-hidden rounded-md border border-[rgba(103,232,249,0.28)] bg-[#071019]/98 shadow-[0_18px_48px_rgba(0,0,0,0.52)] backdrop-blur"
              style={nodeSearchStyle()}
              onPointerDown={(event) => event.stopPropagation()}
              onWheel={(event) => event.stopPropagation()}
              onContextMenu={(event) => {
                event.preventDefault()
                event.stopPropagation()
              }}
            >
              <div class="flex items-center gap-2 border-b border-[rgba(103,232,249,0.16)] p-2">
                <input
                  ref={nodeSearchInputRef}
                  data-blueprint-node-search-input
                  class="h-8 min-w-0 flex-1 rounded-sm border border-[rgba(103,232,249,0.18)] bg-[#020817] px-2 text-13-regular text-[#f8fdff] outline-none placeholder:text-[#6b879c] focus:border-[rgba(103,232,249,0.72)]"
                  value={nodeSearchQuery()}
                  placeholder={language.t("blueprint.nodeSearch.placeholder" as never)}
                  onInput={(event) => setNodeSearchQuery(event.currentTarget.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") {
                      event.preventDefault()
                      setNodeSearch(undefined)
                      return
                    }
                    if (event.key !== "Enter") return
                    const first = filteredAddOptions()[0]
                    if (!first) return
                    event.preventDefault()
                    addNodeFromSearch(first)
                  }}
                />
                <Tooltip placement="top" value={language.t("blueprint.script.create" as never)}>
                  <IconButton
                    data-blueprint-script-create
                    icon="plus-small"
                    variant="ghost"
                    class="h-8 w-8 shrink-0 text-[#67e8f9]"
                    onClick={openCreateScriptNodeDialog}
                    aria-label={language.t("blueprint.script.create" as never)}
                  />
                </Tooltip>
              </div>
              <div data-blueprint-node-search-list class="max-h-[264px] overflow-y-auto py-1">
                <Show
                  when={filteredAddOptions().length > 0}
                  fallback={<div class="px-3 py-3 text-12-regular text-[#95afc4]">{language.t("blueprint.nodeSearch.empty" as never)}</div>}
                >
                  <For each={filteredAddOptions()}>
                    {(option) => (
                      <button
                        type="button"
                        data-blueprint-node-search-option
                        data-kind={option.kind}
                        class="flex min-h-11 w-full items-center gap-2 px-3 py-2 text-left hover:bg-[rgba(103,232,249,0.10)] focus:bg-[rgba(103,232,249,0.14)] focus:outline-none"
                        onClick={() => addNodeFromSearch(option)}
                      >
                        <Icon size="small" name={addNodeIcon(option.kind)} class="shrink-0 text-[#67e8f9]" />
                        <span class="min-w-0 flex-1">
                          <span class="block truncate text-13-medium text-[#f8fdff]">{option.label}</span>
                          <span class="block truncate text-11-regular text-[#95afc4]">{option.description}</span>
                        </span>
                      </button>
                    )}
                  </For>
                </Show>
              </div>
            </div>
          </Show>
          <div class="pointer-events-auto absolute bottom-4 left-4 z-30">
            <BlueprintCollaborationAuthPanel defaultUsername="1" />
          </div>
          <Show when={runtimeRunActive()}>
            <div
              data-blueprint-runtime-frame
              class="pointer-events-none absolute inset-0 z-20 border-2 border-[#22c55e] shadow-[inset_0_0_0_1px_rgba(187,247,208,0.34),0_0_20px_rgba(34,197,94,0.34)]"
            />
          </Show>
          <For each={agentPanelEntries()}>
            {(panel) => (
              <AgentInfoPanel
                panel={panel}
                node={draft.graph.agent_nodes[panel.nodeId]}
                runId={runtime().runId}
                runtimeStatus={runtimeStatus(runtime().status)}
                testLogActive={agentPanelTestLogActive()}
                events={agentPanel.streamEvents[panel.nodeId] ?? []}
                onClose={() => closeAgentPanel(panel.nodeId)}
                onPin={() => setAgentPanel("panels", panel.nodeId, "pinned", !panel.pinned)}
                onMovePointerDown={(event) => handleAgentPanelMovePointerDown(event, panel)}
                onResizePointerDown={(event) => handleAgentPanelResizePointerDown(event, panel)}
                onInput={(value) => setAgentPanel("panels", panel.nodeId, "input", value)}
                onMode={(mode) => setAgentPanel("panels", panel.nodeId, "mode", mode)}
                onSend={() => void sendAgentPanelMessage(panel.nodeId)}
              />
            )}
          </For>
          <Show when={workspacePanelArea()}>
            {(area) => (
              <WorkspaceContentPanel
                area={area()}
                workspace={runtimeWorkspace()}
                onClose={() => setWorkspacePanelArea(undefined)}
                onOpenDirectory={() => void openWorkspaceDirectory(area())}
                onRevealItem={(path) => void revealWorkspaceItem(path)}
              />
            )}
          </Show>
          <Show when={blueprintDiffOpen()}>
            <BlueprintDiffOverlay
              state={blueprintDiff}
              selectedChangesetId={blueprintDiffSelectedChangesetId()}
              onClose={() => setBlueprintDiffOpen(false)}
              onRefresh={() => void refreshBlueprintRunDiff(runtime().runId)}
              onSelectChangeset={(changesetId) => {
                if (blueprintDiffSelectedChangesetId() === changesetId) {
                  setBlueprintDiffSelectedChangesetId(undefined)
                  return
                }
                setBlueprintDiffSelectedChangesetId(changesetId)
                void loadBlueprintChangesetDiff(changesetId)
              }}
              onRollbackChangeset={(changesetId) => void rollbackBlueprintChangesets(changesetId)}
              onRestoreRollback={(rollbackId) => void restoreBlueprintRollback(rollbackId)}
            />
          </Show>
        </div>

        <Show when={runtimePanelOpen() || (panelMode() === "inspector" && inspectorOpen())}>
          <div
            class="w-[340px] max-w-[44%] min-w-[282px] shrink-0 border-l border-[rgba(103,232,249,0.16)] bg-[#071019] shadow-[-20px_0_48px_rgba(0,0,0,0.42)]"
            style={BLUEPRINT_INSPECTOR_THEME}
          >
            <Switch>
              <Match when={panelMode() === "runtime"}>
                <BlueprintRuntimePanel
                  state={runtime()}
                  startNodeOptions={runtimeStartNodeOptions()}
                  selectedStartNodeIds={runtimeStartNodeIds()}
                  task={runtimeTask()}
                  taskDisabled={runtimeBusy() || projectWorkdirRelocating() || !persistence().loaded}
                  generatePlanDisabled={
                    runtimeBusy() ||
                    projectWorkdirRelocating() ||
                    persistence().saving ||
                    blueprintPicker().loading ||
                    !persistence().loaded ||
                    !platform.saveBlueprint ||
                    (!blueprintPlanningBridgeAvailable() && !platform.createBlueprintStartPlan)
                  }
                  confirmRunDisabled={
                    runtimeBusy() ||
                    projectWorkdirRelocating() ||
                    persistence().saving ||
                    blueprintPicker().loading ||
                    !persistence().loaded ||
                    !platform.startBlueprintRun ||
                    !runtimeStartPlanReady()
                  }
                  taskInputRef={(el) => {
                    runtimeTaskInputRef = el
                  }}
                  onTaskInput={(value) => {
                    setRuntimeTask(value)
                    clearRuntimeStartPlan()
                  }}
                  onStartNodeToggle={toggleRuntimeStartNode}
                  onGeneratePlan={() =>
                    void (blueprintPlanningBridgeAvailable()
                      ? submitBlueprintPlanningTask()
                      : generateBlueprintStartPlan())
                  }
                  onConfirmRun={() => void confirmBlueprintStartPlan()}
                  onRefresh={() => void refreshBlueprintRuntime()}
                  onEnd={(action) => void endBlueprintRuntime(action)}
                  workspacePanelArea={workspacePanelArea()}
                  onWorkspaceAreaOpen={setWorkspacePanelArea}
                  onWorkspaceAreaOpenInExplorer={(area) => void openWorkspaceDirectory(area)}
                />
              </Match>
              <Match when={inspectorOpen()}>
                <BlueprintInspector
                  draft={draft}
                  selectedAgent={inspectedAgent()}
                  selectedRoute={inspectedRoute()}
                  selectedCommon={inspectedCommon()}
                  selectedScript={inspectedScript()}
                  selectedTerminal={inspectedTerminal()}
                  selectedNodeId={draft.inspector?.type === "node" ? draft.inspector.id : undefined}
                  selectedEdge={inspectedEdge()}
                  closeInspector={closeInspector}
                  setDraft={replaceDraft}
                  setStore={setDraft}
                  config={currentConfig()}
                  catalog={catalog()}
                  modelCatalog={modelCatalog()}
                  refreshModelCatalog={refreshModelCatalog}
                  compileBlueprintScripts={compileBlueprintScripts}
                  scriptCompiling={scriptCompiling()}
                />
              </Match>
            </Switch>
          </div>
        </Show>
      </div>
      <Show when={blueprintProgressPhase()}>
        {(phase) => (
          <BlueprintProgressOverlay
            phase={phase()}
            style={blueprintProgressHudStyle()}
            onClose={blueprintPlanningRequestCancelAvailable() ? () => void cancelBlueprintPlanningRequest() : undefined}
            closeDisabled={planningCancelPending()}
            closeLabel={language.t("blueprint.progress.cancelPlanning" as never)}
          />
        )}
      </Show>
    </div>
  )
}

function BlueprintDiffOverlay(props: {
  state: BlueprintDiffState
  selectedChangesetId?: string
  onClose: () => void
  onRefresh: () => void
  onSelectChangeset: (changesetId: string) => void
  onRollbackChangeset: (changesetId: string) => void
  onRestoreRollback: (rollbackId?: string) => void
}) {
  const language = useLanguage()
  const groups = createMemo(() => groupBlueprintDiffChangesets(props.state.changesets))
  const selectedDetail = createMemo(() =>
    props.selectedChangesetId ? props.state.details[props.selectedChangesetId] : undefined,
  )
  const restorableRollbackId = createMemo(() => props.state.changesets.find((item) => item.restorable)?.rollbackId)
  const actionBusy = createMemo(() => !!props.state.rollingBack || !!props.state.restoringRollback)

  return (
    <div
      data-blueprint-diff-overlay
      class="absolute left-3 right-3 top-3 z-40 max-h-[calc(100%-24px)] overflow-hidden rounded-md border border-[rgba(103,232,249,0.24)] bg-[#071019]/95 shadow-[0_18px_48px_rgba(0,0,0,0.48)] backdrop-blur"
      onPointerDown={(event) => event.stopPropagation()}
      onWheel={(event) => event.stopPropagation()}
    >
      <div class="flex items-center justify-between gap-3 border-b border-[rgba(103,232,249,0.16)] px-3 py-2">
        <div class="min-w-0">
          <div class="truncate text-12-medium text-[#f8fdff]">{language.t("blueprint.diff.title" as never)}</div>
          <div class="text-10-regular text-[#95afc4]">
            {language.t("blueprint.diff.summary" as never, {
              count: blueprintDiffSummaryCount(props.state.summary, "total"),
              files: blueprintDiffSummaryCount(props.state.summary, "files"),
            } as never)}
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-1">
          <Show when={restorableRollbackId()}>
            {(rollbackId) => (
              <Button
                size="small"
                icon="arrow-right"
                variant="secondary"
                class="h-7 px-2"
                disabled={props.state.loading || actionBusy()}
                onClick={() => props.onRestoreRollback(rollbackId())}
              >
                {props.state.restoringRollback
                  ? language.t("common.loading")
                  : language.t("blueprint.diff.restoreRollback" as never)}
              </Button>
            )}
          </Show>
          <IconButton
            icon="reset"
            variant="ghost"
            class="h-7 w-7"
            disabled={props.state.loading || actionBusy()}
            onClick={props.onRefresh}
            aria-label={language.t("blueprint.diff.refresh" as never)}
          />
          <IconButton
            icon="close-small"
            variant="ghost"
            class="h-7 w-7"
            onClick={props.onClose}
            aria-label={language.t("common.close")}
          />
        </div>
      </div>
      <div class="max-h-[min(620px,calc(100vh-180px))] overflow-y-auto px-3 py-3">
        <Show when={props.state.error}>
          {(error) => <div class="mb-3 rounded border border-[#ef4444]/30 bg-[#450a0a]/40 px-3 py-2 text-12-regular text-[#fecaca]">{error()}</div>}
        </Show>
        <Show when={props.state.loading}>
          <div class="py-8 text-center text-12-regular text-[#95afc4]">{language.t("common.loading")}</div>
        </Show>
        <Show when={!props.state.loading && props.state.changesets.length === 0}>
          <div class="py-10 text-center text-12-regular text-[#95afc4]">{language.t("blueprint.diff.empty" as never)}</div>
        </Show>
        <div class="flex flex-col gap-3">
          <For each={groups()}>
            {(group) => (
              <section class="rounded border border-[rgba(148,163,184,0.16)] bg-[#0b1622]/80">
                <div class="flex items-center gap-2 border-b border-[rgba(148,163,184,0.12)] px-3 py-2">
                  <span
                    class="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ "background-color": blueprintAgentColor(group.agentId) }}
                  />
                  <div class="min-w-0 truncate text-11-medium text-[#f8fdff]">
                    {group.agentId || language.t("blueprint.diff.unknownAgent" as never)}
                  </div>
                  <Show when={group.taskId}>
                    {(taskId) => <div class="min-w-0 truncate text-10-regular text-[#95afc4]">{taskId()}</div>}
                  </Show>
                </div>
                <div class="divide-y divide-[rgba(148,163,184,0.12)]">
                  <For each={group.items}>
                    {(changeset) => (
                      <div data-blueprint-diff-changeset class="px-3 py-2">
                        <div class="flex items-center justify-between gap-3">
                          <div class="min-w-0">
                            <div class="flex min-w-0 items-center gap-2">
                              <span class={`rounded px-1.5 py-0.5 text-10-medium ${blueprintDiffStatusClass(changeset.status)}`}>
                                {blueprintDiffStatusLabel(language.t, changeset.status)}
                              </span>
                              <div class="truncate font-mono text-11-regular text-[#dbeafe]">{changeset.changesetId}</div>
                            </div>
                            <div class="mt-1 truncate text-11-regular text-[#95afc4]">
                              {changeset.summary || language.t("blueprint.diff.noSummary" as never)}
                            </div>
                            <div class="mt-1 text-10-regular text-[#7891a8]">
                              {language.t("blueprint.diff.fileStats" as never, {
                                files: changeset.fileCount,
                                additions: changeset.additions,
                                deletions: changeset.deletions,
                              } as never)}
                              <Show when={changeset.binaryFileCount > 0}>
                                {" "}
                                {language.t("blueprint.diff.binaryStats" as never, { count: changeset.binaryFileCount } as never)}
                              </Show>
                            </div>
                          </div>
                          <div class="flex shrink-0 items-center gap-1">
                            <Tooltip
                              value={
                                changeset.rollbackDisabledReason ||
                                (changeset.status !== "accepted"
                                  ? language.t("blueprint.diff.rollbackOnlyAccepted" as never)
                                  : "")
                              }
                              placement="top"
                              gutter={4}
                            >
                              <span>
                                <Button
                                  size="small"
                                  icon="reset"
                                  variant="ghost"
                                  class="h-7 px-2"
                                  disabled={
                                    props.state.loading ||
                                    actionBusy() ||
                                    changeset.status !== "accepted" ||
                                    !changeset.rollbackable
                                  }
                                  onClick={() => props.onRollbackChangeset(changeset.changesetId)}
                                >
                                  {props.state.rollingBack === changeset.changesetId
                                    ? language.t("common.loading")
                                    : language.t("blueprint.diff.rollback" as never)}
                                </Button>
                              </span>
                            </Tooltip>
                            <Button
                              size="small"
                              variant={props.selectedChangesetId === changeset.changesetId ? "secondary" : "ghost"}
                              class="h-7 px-2"
                              disabled={!changeset.patchExists || actionBusy()}
                              aria-expanded={props.selectedChangesetId === changeset.changesetId}
                              onClick={() => props.onSelectChangeset(changeset.changesetId)}
                            >
                              {props.state.detailLoading === changeset.changesetId
                                ? language.t("common.loading")
                                : language.t("blueprint.diff.view" as never)}
                            </Button>
                          </div>
                        </div>
                        <Show when={props.selectedChangesetId === changeset.changesetId}>
                          <Show when={selectedDetail()}>
                            {(detail) => (
                              <BlueprintDiffDetailView
                                detail={detail()}
                                tone={changeset.status === "rolled_back" ? "neutral" : "diff"}
                              />
                            )}
                          </Show>
                        </Show>
                      </div>
                    )}
                  </For>
                </div>
              </section>
            )}
          </For>
        </div>
      </div>
    </div>
  )
}

function BlueprintDiffDetailView(props: { detail: BlueprintChangesetDiffDetail; tone?: "diff" | "neutral" }) {
  const language = useLanguage()
  return (
    <div data-blueprint-diff-detail class="mt-3 rounded border border-[rgba(103,232,249,0.16)] bg-[#020617]/70">
      <Show when={props.detail.diffs.length === 0}>
        <div class="px-3 py-3 text-11-regular text-[#95afc4]">{language.t("blueprint.diff.noTextDiff" as never)}</div>
      </Show>
      <For each={props.detail.diffs}>
        {(diff) => (
          <div class="border-b border-[rgba(148,163,184,0.12)] last:border-b-0">
            <div class="flex items-center justify-between gap-2 px-3 py-2">
              <div class="min-w-0 truncate font-mono text-11-medium text-[#e0f2fe]">{diff.file}</div>
              <div class="shrink-0 text-10-regular text-[#95afc4]">
                +{diff.additions} / -{diff.deletions}
              </div>
            </div>
            <pre class="max-h-72 overflow-auto px-3 pb-3 font-mono text-[11px] leading-5 text-[#cbd5e1]">
              <For each={diff.patch.split("\n")}>
                {(line) => <div class={blueprintPatchLineClass(line, props.tone)}>{line || " "}</div>}
              </For>
            </pre>
          </div>
        )}
      </For>
      <Show when={props.detail.binaryFiles.length > 0}>
        <div class="border-t border-[rgba(148,163,184,0.12)] px-3 py-2 text-11-regular text-[#95afc4]">
          {language.t("blueprint.diff.binaryStats" as never, { count: props.detail.binaryFiles.length } as never)}
        </div>
      </Show>
    </div>
  )
}

function BlueprintDocumentSelect(props: {
  items: BlueprintSummary[]
  selectedId: string
  selectedName: string
  loading: boolean
  disabled: boolean
  onSelect: (blueprintId: string) => void
  onCreate: () => void
}) {
  const language = useLanguage()
  const selectedItem = () => props.items.find((item) => item.id === props.selectedId)
  const label = () => selectedItem()?.name || props.selectedName || props.selectedId

  return (
    <DropdownMenu placement="bottom-start">
      <DropdownMenu.Trigger
        data-blueprint-document-select
        as={Button}
        size="small"
        variant="ghost"
        icon="blueprint"
        class="h-7 max-w-[220px] px-2"
        disabled={props.disabled || props.loading}
        title={language.t("blueprint.document.select" as never)}
      >
        <span class="min-w-0 truncate">{props.loading ? language.t("common.loading") : label()}</span>
        <Icon size="small" name="chevron-down" class="shrink-0 text-icon-weak" />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content class="mt-1 max-h-72 w-72 overflow-y-auto">
          <Show
            when={props.items.length > 0}
            fallback={<div class="px-2 py-2 text-12-regular text-text-weaker">{language.t("blueprint.document.empty" as never)}</div>}
          >
            <For each={props.items}>
              {(item) => (
                <DropdownMenu.Item
                  onSelect={() => props.onSelect(item.id)}
                  class="gap-2"
                >
                  <Icon
                    size="small"
                    name={item.id === props.selectedId ? "check-small" : "blueprint"}
                    class={item.id === props.selectedId ? "text-icon-strong-base" : "text-icon-weak"}
                  />
                  <div class="flex min-w-0 flex-col">
                    <DropdownMenu.ItemLabel class="truncate">{item.name || item.id}</DropdownMenu.ItemLabel>
                    <DropdownMenu.ItemDescription class="truncate">{item.id}</DropdownMenu.ItemDescription>
                  </div>
                </DropdownMenu.Item>
              )}
            </For>
          </Show>
          <DropdownMenu.Separator />
          <DropdownMenu.Item data-blueprint-document-create onSelect={props.onCreate}>
            <Icon size="small" name="plus-small" />
            <DropdownMenu.ItemLabel>{language.t("blueprint.document.new" as never)}</DropdownMenu.ItemLabel>
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu>
  )
}

function BlueprintCreateDialog(props: {
  existingIds: string[]
  onCreate: (name: string) => void | Promise<void>
}) {
  const language = useLanguage()
  const dialog = useDialog()
  const [name, setName] = createSignal("")
  const previewId = () => uniqueBlueprintId(name() || language.t("blueprint.document.new" as never), props.existingIds)
  const submit = () => {
    const value = name().trim()
    if (!value) return
    dialog.close()
    void props.onCreate(value)
  }

  return (
    <Dialog title={language.t("blueprint.document.createTitle" as never)} action={<span aria-hidden="true" />} fit>
      <div data-blueprint-create-dialog class="flex w-[420px] max-w-[calc(100vw-2rem)] flex-col gap-4 px-6 pb-4">
        <label class="flex flex-col gap-1">
          <span class="text-12-medium text-text-strong">{language.t("blueprint.document.name" as never)}</span>
          <input
            data-blueprint-create-name
            class="h-9 rounded-md border border-border-weaker-base bg-background-stronger px-2 text-13-regular text-text-strong outline-none focus:border-border-selected"
            value={name()}
            autofocus
            onInput={(event) => setName(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") submit()
            }}
          />
        </label>
        <div class="rounded-sm border border-border-weaker-base bg-background-stronger px-2 py-1.5 font-mono text-11-regular text-text-weaker">
          {language.t("blueprint.document.id" as never)}: {previewId()}
        </div>
        <div class="flex justify-end gap-2">
          <Button variant="ghost" size="large" onClick={() => dialog.close()}>
            {language.t("common.cancel")}
          </Button>
          <Button variant="primary" size="large" disabled={!name().trim()} onClick={submit}>
            {language.t("blueprint.document.create" as never)}
          </Button>
        </div>
      </div>
    </Dialog>
  )
}

function BlueprintScriptCreateDialog(props: {
  onCreate: (name: string, description: string) => void | Promise<void>
}) {
  const language = useLanguage()
  const dialog = useDialog()
  const [name, setName] = createSignal("")
  const [description, setDescription] = createSignal("")
  const submit = () => {
    const value = name().trim()
    if (!value) return
    dialog.close()
    void props.onCreate(value, description().trim())
  }

  return (
    <Dialog title={language.t("blueprint.script.createTitle" as never)} action={<span aria-hidden="true" />} fit>
      <div data-blueprint-script-create-dialog class="flex w-[420px] max-w-[calc(100vw-2rem)] flex-col gap-4 px-6 pb-4">
        <label class="flex flex-col gap-1">
          <span class="text-12-medium text-text-strong">{language.t("blueprint.script.name" as never)}</span>
          <input
            data-blueprint-script-name
            class="h-9 rounded-md border border-border-weaker-base bg-background-stronger px-2 text-13-regular text-text-strong outline-none focus:border-border-selected"
            value={name()}
            autofocus
            onInput={(event) => setName(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") submit()
            }}
          />
        </label>
        <label class="flex flex-col gap-1">
          <span class="text-12-medium text-text-strong">{language.t("blueprint.script.description" as never)}</span>
          <textarea
            data-blueprint-script-description
            class="h-20 resize-none rounded-md border border-border-weaker-base bg-background-stronger px-2 py-1.5 text-13-regular text-text-strong outline-none placeholder:text-text-weaker focus:border-border-selected"
            value={description()}
            placeholder={language.t("blueprint.script.descriptionPlaceholder" as never)}
            onInput={(event) => setDescription(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) submit()
            }}
          />
        </label>
        <div class="rounded-sm border border-border-weaker-base bg-background-stronger px-2 py-1.5 text-12-regular text-text-weaker">
          {language.t("blueprint.script.templateHint" as never)}
        </div>
        <div class="flex justify-end gap-2">
          <Button variant="ghost" size="large" onClick={() => dialog.close()}>
            {language.t("common.cancel")}
          </Button>
          <Button variant="primary" size="large" disabled={!name().trim()} onClick={submit}>
            {language.t("blueprint.script.create" as never)}
          </Button>
        </div>
      </div>
    </Dialog>
  )
}

function BlueprintHeaderStatus(props: { status: BlueprintHeaderStatusState }) {
  const language = useLanguage()
  const [open, setOpen] = createSignal(false)
  const dotClass = () =>
    props.status.tone === "error"
      ? "bg-[#ef4444]"
      : props.status.tone === "saving"
        ? "bg-[#0284c7]"
        : "bg-[#64748b]"

  return (
    <Popover
      open={open()}
      onOpenChange={setOpen}
      triggerAs={Button}
      triggerProps={{
        size: "small",
        variant: "ghost",
        class: "h-6 min-w-0 max-w-80 px-1.5",
        "data-blueprint-header-status-trigger": "true",
        "aria-label": language.t("blueprint.headerStatus.expand" as never),
        type: "button",
      }}
      trigger={
        <div class="flex min-w-0 items-center gap-1.5 text-11-regular">
          <span class={`size-1.5 shrink-0 rounded-full ${dotClass()}`} />
          <span
            class="min-w-0 truncate"
            classList={{
              "text-[#b91c1c]": props.status.tone === "error",
              "text-text-weaker": props.status.tone !== "error",
            }}
          >
            {props.status.label}
          </span>
          <Icon name={open() ? "chevron-down" : "chevron-right"} size="small" class="shrink-0 text-icon-weak" />
        </div>
      }
      title={props.status.title}
      class="w-[420px] max-w-[calc(100vw-32px)] border-border-weak-base bg-background-strong shadow-[0_18px_48px_rgba(15,23,42,0.18)] [&_[data-slot=popover-body]]:pt-2"
      style={BLUEPRINT_CHROME_THEME}
      placement="bottom-start"
      gutter={6}
    >
      <div
        data-blueprint-header-status-details
        class="max-h-64 overflow-y-auto whitespace-pre-wrap break-words text-12-regular leading-5 text-text-base"
      >
        {props.status.detail}
      </div>
    </Popover>
  )
}

function BlueprintProgressOverlay(props: {
  phase: BlueprintProgressPhase
  style: JSX.CSSProperties
  onClose?: () => void
  closeDisabled?: boolean
  closeLabel?: string
}) {
  const language = useLanguage()
  const label = () => language.t(`blueprint.progress.${props.phase}` as never)
  const closeLabel = () => props.closeLabel ?? language.t("common.close")

  return (
    <div
      data-blueprint-progress-overlay
      role="status"
      aria-live="polite"
      aria-label={label()}
      class="absolute inset-0 z-50 pointer-events-auto"
    >
      <div data-blueprint-progress-mask class="absolute inset-0 bg-white/55 backdrop-blur-[1px]" />
      <div
        data-blueprint-progress-hud
        class="absolute w-[min(680px,calc(100%-48px))] rounded-md border border-[rgba(103,232,249,0.36)] bg-[#06101a]/95 px-4 py-3 shadow-[0_18px_60px_rgba(2,8,23,0.36)]"
        style={props.style}
      >
        <div class="mb-2 flex items-center justify-between gap-3">
          <div class="min-w-0 truncate text-12-medium text-[#f8fdff]">{label()}</div>
          <div class="flex shrink-0 items-center gap-1.5">
            <div class="text-10-medium uppercase text-[#67e8f9]">{language.t("blueprint.runtime.panel")}</div>
            <Show when={props.onClose}>
              <Tooltip placement="top" value={closeLabel()}>
                <IconButton
                  data-blueprint-progress-close
                  icon="close-small"
                  variant="ghost"
                  class="h-6 w-6 text-[#67e8f9] hover:text-[#f8fdff]"
                  disabled={props.closeDisabled}
                  onClick={(event) => {
                    event.stopPropagation()
                    props.onClose?.()
                  }}
                  aria-label={closeLabel()}
                />
              </Tooltip>
            </Show>
          </div>
        </div>
        <div data-blueprint-progress-track class="h-1.5 overflow-hidden rounded-full bg-[rgba(103,232,249,0.16)]">
          <div data-blueprint-progress-bar />
        </div>
      </div>
    </div>
  )
}

function BlueprintRuntimePanel(props: {
  state: BlueprintRuntimeState
  startNodeOptions: BlueprintRuntimeStartNodeOption[]
  selectedStartNodeIds: string[]
  task: string
  taskDisabled: boolean
  generatePlanDisabled: boolean
  confirmRunDisabled: boolean
  taskInputRef: (el: HTMLTextAreaElement) => void
  onTaskInput: (value: string) => void
  onStartNodeToggle: (nodeId: string) => void
  onGeneratePlan: () => void
  onConfirmRun: () => void
  onRefresh: () => void
  onEnd: (action: BlueprintRunEndAction) => void
  workspacePanelArea?: WorkspacePanelArea
  onWorkspaceAreaOpen: (area: WorkspacePanelArea) => void
  onWorkspaceAreaOpenInExplorer: (area: WorkspacePanelArea) => void
}) {
  const language = useLanguage()
  const status = createMemo(() => asRecord(props.state.status))
  const run = createMemo(() => asRecord(status()?.run))
  const agents = createMemo(() => recordEntries(asRecord(status()?.agents)))
  const queues = createMemo(() => asRecord(status()?.queues))
  const pendingMessages = createMemo(() => runtimePendingMessageEntries(queues()?.pending_messages))
  const queueByAgent = createMemo(() =>
    recordEntries(asRecord(queues()?.by_agent))
      .map(([id, messages]) => [id, runtimePendingMessages(messages)] as const)
      .filter(([, messages]) => messages.length > 0),
  )
  const outgoing = createMemo(() => recordEntries(asRecord(status()?.outgoing_batches)))
  const joins = createMemo(() => recordEntries(asRecord(status()?.joins)))
  const jobs = createMemo(() => recordEntries(asRecord(status()?.jobs)))
  const workspace = createMemo(() => asRecord(status()?.workspace))
  const workspaceChanges = createMemo(() => workspaceAreaItems(workspace(), "changesets"))
  const workspaceArtifacts = createMemo(() => workspaceAreaItems(workspace(), "artifacts"))
  const workspaceReports = createMemo(() => workspaceAreaItems(workspace(), "reports"))
  const explanation = createMemo(() => asRecord(props.state.explanation))
  const summary = createMemo(() => asRecord(explanation()?.summary))
  const runStatus = createMemo(() => runtimeStatus(props.state.status) || "idle")
  const terminal = createMemo(() => isTerminalRuntimeStatus(runStatus()))
  const startPlanValidation = createMemo(() => asRecord(props.state.planValidation))
  const startPlanErrors = createMemo(() => validationErrors(startPlanValidation()))
  const startPlanWarnings = createMemo(() => {
    const warnings = startPlanValidation()?.warnings
    return Array.isArray(warnings) ? warnings.map((item) => String(item).trim()).filter(Boolean) : []
  })
  const planningRequest = createMemo(() => props.state.planningRequest)
  const [runtimePanelOrder, setRuntimePanelOrder] = createSignal<RuntimePanelId[]>([...DEFAULT_RUNTIME_PANEL_ORDER])
  const [draggedRuntimePanel, setDraggedRuntimePanel] = createSignal<RuntimePanelId>()
  const [runtimePanelDrag, setRuntimePanelDrag] = createSignal<RuntimePanelDragState>()
  const [runtimeEventsPanelHeight, setRuntimeEventsPanelHeight] = createSignal(240)
  let runtimePanelListRef: HTMLDivElement | undefined

  const moveRuntimePanelAtPointer = (dragging: RuntimePanelId, clientY: number) => {
    if (!runtimePanelListRef) return
    const panels = Array.from(runtimePanelListRef.querySelectorAll<HTMLElement>("[data-blueprint-runtime-panel]"))
      .map((element) => ({
        id: element.dataset.blueprintRuntimePanel as RuntimePanelId | undefined,
        rect: element.getBoundingClientRect(),
      }))
      .filter((item): item is { id: RuntimePanelId; rect: DOMRect } => !!item.id && item.id !== dragging)
      .sort((left, right) => left.rect.top - right.rect.top)
    if (!panels.length) return
    const before = panels.find((panel) => clientY < panel.rect.top + panel.rect.height / 2)
    setRuntimePanelOrder((current) =>
      before
        ? reorderRuntimePanels(current, dragging, before.id, false)
        : reorderRuntimePanels(current, dragging, panels[panels.length - 1]!.id, true),
    )
  }

  const handleRuntimePanelPointerDown = (id: RuntimePanelId, event: PointerEvent) => {
    if (event.button !== 0) return
    const handle = event.currentTarget
    if (!(handle instanceof HTMLElement)) return
    const panel = handle.closest<HTMLElement>("[data-blueprint-runtime-panel]")
    if (!panel) return
    const rect = panel.getBoundingClientRect()
    event.preventDefault()
    handle.setPointerCapture?.(event.pointerId)
    setDraggedRuntimePanel(id)
    setRuntimePanelDrag({
      id,
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top,
      width: rect.width,
      height: rect.height,
    })
  }

  createEffect(() => {
    const dragging = draggedRuntimePanel()
    if (!dragging) return
    const handleMove = (event: PointerEvent) => {
      setRuntimePanelDrag((current) => {
        if (!current || current.pointerId !== event.pointerId) return current
        return { ...current, x: event.clientX, y: event.clientY }
      })
      moveRuntimePanelAtPointer(dragging, event.clientY)
    }
    const handleEnd = (event: PointerEvent) => {
      const current = runtimePanelDrag()
      if (current && current.pointerId !== event.pointerId) return
      setDraggedRuntimePanel(undefined)
      setRuntimePanelDrag(undefined)
    }
    const handleBlur = () => {
      setDraggedRuntimePanel(undefined)
      setRuntimePanelDrag(undefined)
    }
    window.addEventListener("pointermove", handleMove)
    window.addEventListener("pointerup", handleEnd)
    window.addEventListener("pointercancel", handleEnd)
    window.addEventListener("blur", handleBlur)
    onCleanup(() => {
      window.removeEventListener("pointermove", handleMove)
      window.removeEventListener("pointerup", handleEnd)
      window.removeEventListener("pointercancel", handleEnd)
      window.removeEventListener("blur", handleBlur)
    })
  })

  const runtimePanelShellProps = (id: RuntimePanelId) => ({
    id,
    order: runtimePanelOrder().indexOf(id),
    dragging: draggedRuntimePanel() === id,
    dragHeight: runtimePanelDrag()?.id === id ? runtimePanelDrag()?.height : undefined,
    ariaLabel: language.t("blueprint.runtime.dragPanel" as never),
    onPointerDown: (event: PointerEvent) => handleRuntimePanelPointerDown(id, event),
  })

  return (
    <div class="size-full min-h-0 flex flex-col bg-[#071019] text-[#d6e9f5]">
      <div class="h-10 shrink-0 flex items-center justify-between border-b border-[rgba(103,232,249,0.14)] bg-[#0b1522] px-3">
        <div class="min-w-0 truncate text-12-medium text-[#f8fdff]">{language.t("blueprint.runtime.panel")}</div>
        <div class="flex shrink-0 items-center gap-1">
          <IconButton
            icon="reset"
            variant="ghost"
            class="h-6 w-6 text-[#f8fdff]"
            disabled={!props.state.runId || props.state.loading}
            onClick={props.onRefresh}
            aria-label={language.t("blueprint.runtime.refresh")}
          />
        </div>
      </div>
      <div class="flex-1 min-h-0 overflow-y-auto p-3">
        <div
          ref={(el) => {
            runtimePanelListRef = el
          }}
          class="flex flex-col gap-3"
        >
          <RuntimePanelShell {...runtimePanelShellProps("planning")}>
          <RuntimeSection title={language.t("blueprint.runtime.planning" as never)}>
            <RuntimeStartNodeSelect
              options={props.startNodeOptions}
              selectedIds={props.selectedStartNodeIds}
              disabled={props.taskDisabled}
              onToggle={props.onStartNodeToggle}
            />
            <label class="flex min-w-0 flex-col gap-1">
              <span class="text-11-medium text-[#f8fdff]">{language.t("blueprint.runtime.task" as never)}</span>
              <textarea
                ref={props.taskInputRef}
                data-blueprint-runtime-task-input
                class="min-h-32 w-full min-w-0 resize-y rounded-sm border border-[rgba(103,232,249,0.22)] bg-[#06101a] px-3 py-2 text-12-regular leading-5 text-[#f8fdff] outline-none transition-colors placeholder:text-[#557086] focus:border-[#67e8f9] disabled:cursor-not-allowed disabled:opacity-55"
                value={props.task}
                disabled={props.taskDisabled}
                placeholder={language.t("blueprint.runtime.taskPlaceholder" as never)}
                onInput={(event) => props.onTaskInput(event.currentTarget.value)}
              />
            </label>
            <div class="flex justify-end gap-2">
              <Button
                data-blueprint-runtime-plan-create
                size="small"
                variant="secondary"
                class="h-8 px-3"
                disabled={props.generatePlanDisabled}
                onClick={props.onGeneratePlan}
              >
                {language.t("blueprint.runtime.generatePlan" as never)}
              </Button>
              <Button
                data-blueprint-runtime-confirm-run
                size="small"
                variant="secondary"
                class="h-8 px-3"
                disabled={props.confirmRunDisabled}
                onClick={props.onConfirmRun}
              >
                {language.t("blueprint.runtime.directRun" as never)}
              </Button>
            </div>
            <Show when={planningRequest()}>
              {(request) => (
                <div
                  data-blueprint-runtime-planning-request
                  class="rounded-sm border border-[rgba(103,232,249,0.18)] bg-[rgba(6,16,26,0.72)] px-2 py-1 text-11-regular text-[#9fb9ca]"
                >
                  <span class="text-[#f8fdff]">{request().status}</span>
                  <Show when={request().summary || request().message}>
                    {(detail) => <span class="ml-2">{detail()}</span>}
                  </Show>
                </div>
              )}
            </Show>
            <Show when={props.state.plan || props.state.planValidation}>
              <div class="rounded-sm border border-[rgba(103,232,249,0.18)] bg-[rgba(6,16,26,0.72)] p-2">
                <div class="mb-2 flex min-w-0 items-center justify-between gap-2">
                  <div class="truncate text-11-medium text-[#f8fdff]">{language.t("blueprint.runtime.planPreview" as never)}</div>
                  <div
                    class="shrink-0 rounded-sm border px-1.5 py-0.5 text-10-medium uppercase"
                    classList={{
                      "border-[rgba(45,212,191,0.42)] text-[#5eead4]": startPlanValidation()?.ok === true,
                      "border-[rgba(248,113,113,0.42)] text-[#fecaca]": startPlanValidation()?.ok === false,
                      "border-[rgba(103,232,249,0.34)] text-[#67e8f9]": startPlanValidation()?.ok !== true && startPlanValidation()?.ok !== false,
                    }}
                  >
                    {startPlanValidation()?.ok === true ? "OK" : startPlanValidation()?.ok === false ? "ERROR" : "DRAFT"}
                  </div>
                </div>
                <Show when={startPlanErrors().length > 0}>
                  <div class="mb-2 rounded-sm bg-[rgba(248,113,113,0.12)] px-2 py-1 text-11-regular text-[#fecaca]">
                    <For each={startPlanErrors()}>{(error) => <div>{error}</div>}</For>
                  </div>
                </Show>
                <Show when={startPlanWarnings().length > 0}>
                  <div class="mb-2 rounded-sm bg-[rgba(250,204,21,0.10)] px-2 py-1 text-11-regular text-[#fde68a]">
                    <For each={startPlanWarnings()}>{(warning) => <div>{warning}</div>}</For>
                  </div>
                </Show>
                <Show when={props.state.plan}>{(plan) => <RuntimeJsonPreview value={plan()} />}</Show>
              </div>
            </Show>
          </RuntimeSection>
          </RuntimePanelShell>
          <RuntimePanelShell {...runtimePanelShellProps("status")}>
          <div class="rounded-md border border-[rgba(103,232,249,0.18)] bg-[#06101a] p-3">
            <div class="flex min-w-0 items-center justify-between gap-2">
              <div class="min-w-0">
                <div class="truncate text-12-medium text-[#f8fdff]">{props.state.runId ?? language.t("blueprint.runtime.noRun")}</div>
                <div class="mt-0.5 truncate text-11-regular text-[#95afc4]">
                  {language.t("blueprint.runtime.status")}: {runStatus()}
                </div>
              </div>
              <div
                class="shrink-0 rounded-sm border px-2 py-1 text-10-medium uppercase"
                classList={{
                  "border-[rgba(45,212,191,0.42)] text-[#5eead4]": runStatus() === "running",
                  "border-[rgba(250,204,21,0.42)] text-[#fde68a]": runStatus() === "paused",
                  "border-[rgba(248,113,113,0.42)] text-[#fecaca]": runStatus() === "failed" || runStatus() === "cancelled",
                  "border-[rgba(103,232,249,0.34)] text-[#67e8f9]": !["running", "paused", "failed", "cancelled"].includes(runStatus()),
                }}
              >
                {runStatus()}
              </div>
            </div>
            <Show when={props.state.error}>
              {(error) => <div class="mt-2 rounded-sm bg-[rgba(248,113,113,0.12)] px-2 py-1 text-11-regular text-[#fecaca]">{error()}</div>}
            </Show>
            <Show when={props.state.lastUpdatedAt}>
              {(lastUpdatedAt) => (
                <div class="mt-2 text-10-regular text-[#95afc4]">
                  {language.t("blueprint.runtime.updated")}: {formatRuntimeTime(lastUpdatedAt())}
                </div>
              )}
            </Show>
            <Show when={run()?.ready_for_top_agent_summary}>
              <div class="mt-2 rounded-sm border border-[rgba(45,212,191,0.28)] bg-[rgba(45,212,191,0.08)] px-2 py-1 text-11-regular text-[#b8fff4]">
                {language.t("blueprint.runtime.readyForTopSummary" as never)}
              </div>
            </Show>
            <div class="mt-3 flex flex-col gap-2">
              <RuntimeActionButton
                label={language.t("blueprint.runtime.complete")}
                description={language.t("blueprint.runtime.completeDescription")}
                disabled={!props.state.runId || props.state.loading}
                onClick={() => props.onEnd("complete")}
              />
              <RuntimeActionButton
                label={language.t("blueprint.runtime.pause")}
                description={language.t("blueprint.runtime.pauseDescription")}
                disabled={!props.state.runId || props.state.loading || terminal()}
                onClick={() => props.onEnd("pause")}
              />
              <RuntimeActionButton
                label={language.t("blueprint.runtime.cancel")}
                description={language.t("blueprint.runtime.cancelDescription")}
                disabled={!props.state.runId || props.state.loading || terminal()}
                onClick={() => props.onEnd("cancel")}
              />
              <RuntimeActionButton
                label={language.t("blueprint.runtime.fail")}
                description={language.t("blueprint.runtime.failDescription")}
                disabled={!props.state.runId || props.state.loading || terminal()}
                onClick={() => props.onEnd("fail")}
              />
            </div>
          </div>
          </RuntimePanelShell>

          <RuntimePanelShell {...runtimePanelShellProps("overview")}>
          <RuntimeSection title={language.t("blueprint.runtime.overview")}>
            <div class="grid grid-cols-3 gap-2">
              <RuntimeMetric label={language.t("blueprint.runtime.agents")} value={agents().length} />
              <RuntimeMetric label={language.t("blueprint.runtime.pending")} value={pendingMessages().length} />
              <RuntimeMetric label={language.t("blueprint.runtime.events")} value={props.state.events.length} />
              <RuntimeMetric label={language.t("blueprint.runtime.outgoing")} value={outgoing().length} />
              <RuntimeMetric label={language.t("blueprint.runtime.joins")} value={joins().length} />
              <RuntimeMetric label={language.t("blueprint.runtime.jobs")} value={jobs().length} />
            </div>
            <Show when={summary()}>
              {(value) => <RuntimeJsonPreview value={value()} />}
            </Show>
          </RuntimeSection>
          </RuntimePanelShell>

          <RuntimePanelShell {...runtimePanelShellProps("agents")}>
          <RuntimeSection title={language.t("blueprint.runtime.agents")}>
            <RuntimeEmpty when={agents().length === 0} />
            <For each={agents()}>
              {([id, agent]) => (
                <RuntimeRow
                  title={id}
                  meta={`${String(agent.state ?? "unknown")} · ${language.t("blueprint.runtime.taskStatus" as never)}: ${String(agent.task_status ?? "not_started")} · ${language.t("blueprint.runtime.queue")}: ${String(agent.queue_size ?? 0)}`}
                  detail={runtimeAgentDetail(agent, language)}
                />
              )}
            </For>
          </RuntimeSection>
          </RuntimePanelShell>

          <RuntimePanelShell {...runtimePanelShellProps("queues")}>
          <RuntimeSection title={language.t("blueprint.runtime.queues")}>
            <RuntimeEmpty when={pendingMessages().length === 0 && queueByAgent().length === 0} />
            <For each={queueByAgent()}>
              {([id, messages]) => (
                <RuntimeRow title={id} meta={`${messages.length} ${language.t("blueprint.runtime.messages")}`} />
              )}
            </For>
            <For each={pendingMessages()}>
              {([id, message]) => <RuntimeRow title={id} meta={String(message.status ?? "")} detail={String(message.node_id ?? "")} />}
            </For>
          </RuntimeSection>
          </RuntimePanelShell>

          <RuntimePanelShell {...runtimePanelShellProps("outgoing")}>
          <RuntimeSection title={language.t("blueprint.runtime.outgoing")}>
            <RuntimeEmpty when={outgoing().length === 0 && joins().length === 0 && jobs().length === 0} />
            <For each={outgoing()}>
              {([id, batch]) => <RuntimeRow title={id} meta={String(batch.status ?? "")} detail={String(batch.source_node_id ?? "")} />}
            </For>
            <For each={joins()}>
              {([id, join]) => <RuntimeRow title={id} meta={String(join.status ?? "")} detail={String(join.target_node_id ?? "")} />}
            </For>
            <For each={jobs()}>
              {([id, job]) => <RuntimeRow title={id} meta={String(job.status ?? "")} detail={String(job.node_id ?? "")} />}
            </For>
          </RuntimeSection>
          </RuntimePanelShell>

          <RuntimePanelShell {...runtimePanelShellProps("workspace")}>
          <RuntimeSection title={language.t("blueprint.runtime.workspace")}>
            <div class="grid grid-cols-3 gap-2">
              <RuntimeWorkspaceMetric
                label={language.t("blueprint.runtime.changes")}
                value={workspaceChanges().length}
                active={props.workspacePanelArea === "changesets"}
                onOpen={() => props.onWorkspaceAreaOpen("changesets")}
                onOpenInExplorer={() => props.onWorkspaceAreaOpenInExplorer("changesets")}
              />
              <RuntimeWorkspaceMetric
                label={language.t("blueprint.runtime.artifacts")}
                value={workspaceArtifacts().length}
                active={props.workspacePanelArea === "artifacts"}
                onOpen={() => props.onWorkspaceAreaOpen("artifacts")}
                onOpenInExplorer={() => props.onWorkspaceAreaOpenInExplorer("artifacts")}
              />
              <RuntimeWorkspaceMetric
                label={language.t("blueprint.runtime.reports")}
                value={workspaceReports().length}
                active={props.workspacePanelArea === "reports"}
                onOpen={() => props.onWorkspaceAreaOpen("reports")}
                onOpenInExplorer={() => props.onWorkspaceAreaOpenInExplorer("reports")}
              />
            </div>
            <RuntimeJsonPreview value={workspace() ?? {}} />
          </RuntimeSection>
          </RuntimePanelShell>

          <RuntimePanelShell {...runtimePanelShellProps("events")}>
          <RuntimeSection title={language.t("blueprint.runtime.events")}>
            <div class="flex min-w-0 items-center gap-2 rounded-sm border border-[rgba(103,232,249,0.12)] bg-[#06101a] px-2 py-1">
              <span class="shrink-0 text-10-regular text-[#95afc4]">{language.t("blueprint.runtime.eventPanelLength" as never)}</span>
              <input
                data-blueprint-runtime-events-height-slider
                type="range"
                min="120"
                max="520"
                step="20"
                value={runtimeEventsPanelHeight()}
                class="min-w-0 flex-1 accent-[#67e8f9]"
                onPointerDown={(event) => event.stopPropagation()}
                onInput={(event) => setRuntimeEventsPanelHeight(Number(event.currentTarget.value))}
              />
              <span class="w-12 shrink-0 text-right font-mono text-10-regular text-[#95afc4]">{runtimeEventsPanelHeight()}</span>
            </div>
            <div
              data-blueprint-runtime-events-list
              class="min-h-0 overflow-y-auto pr-1"
              style={{ "max-height": `${runtimeEventsPanelHeight()}px` }}
            >
              <div class="flex flex-col gap-1">
                <RuntimeEmpty when={props.state.events.length === 0} />
                <For each={props.state.events}>
                  {(event) => (
                    <RuntimeEventRow
                      title={String(event.type ?? event.record_type ?? "event")}
                      meta={String(event.status ?? "")}
                      detail={String(event.message ?? event.event ?? event.node_id ?? "")}
                    />
                  )}
                </For>
              </div>
            </div>
          </RuntimeSection>
          </RuntimePanelShell>
        </div>
      </div>
      <Show when={runtimePanelDrag()}>
        {(drag) => (
          <div
            data-blueprint-runtime-panel-ghost={drag().id}
            class="pointer-events-none fixed z-[9999] rounded-md border border-dashed border-[#67e8f9] bg-[rgba(103,232,249,0.08)] shadow-[0_18px_42px_rgba(0,0,0,0.36)]"
            style={{
              left: `${drag().x - drag().offsetX}px`,
              top: `${drag().y - drag().offsetY}px`,
              width: `${drag().width}px`,
              height: `${drag().height}px`,
            }}
          >
            <div class="m-3 h-1 rounded-full bg-[#67e8f9] shadow-[0_0_12px_rgba(103,232,249,0.4)]" />
          </div>
        )}
      </Show>
    </div>
  )
}

function RuntimePanelShell(props: {
  id: RuntimePanelId
  order: number
  dragging: boolean
  dragHeight?: number
  ariaLabel: string
  children: JSX.Element
  onPointerDown: (event: PointerEvent) => void
}) {
  return (
    <div
      data-blueprint-runtime-panel={props.id}
      class="flex min-w-0 flex-col gap-1"
      style={{ order: props.order }}
    >
      <Show
        when={props.dragging}
        fallback={
          <>
            <div
              role="button"
              tabindex={0}
              data-blueprint-runtime-panel-handle={props.id}
              aria-label={props.ariaLabel}
              class="group flex h-3 cursor-grab touch-none items-center px-4 active:cursor-grabbing"
              onPointerDown={props.onPointerDown}
            >
              <div class="h-1 w-full rounded-full bg-[rgba(103,232,249,0.92)] shadow-[0_0_10px_rgba(103,232,249,0.24)] transition-colors group-hover:bg-[#67e8f9]" />
            </div>
            {props.children}
          </>
        }
      >
        <div
          data-blueprint-runtime-panel-placeholder={props.id}
          class="rounded-md border border-dashed border-[rgba(103,232,249,0.68)] bg-[rgba(103,232,249,0.05)]"
          style={{ height: `${props.dragHeight ?? 72}px` }}
        />
      </Show>
    </div>
  )
}

function reorderRuntimePanels(order: RuntimePanelId[], source: RuntimePanelId, target: RuntimePanelId, insertAfter: boolean) {
  if (source === target) return order
  const withoutSource = order.filter((id) => id !== source)
  const targetIndex = withoutSource.indexOf(target)
  if (targetIndex === -1) return order
  const insertIndex = targetIndex + (insertAfter ? 1 : 0)
  const next = [...withoutSource.slice(0, insertIndex), source, ...withoutSource.slice(insertIndex)]
  return next.every((id, index) => id === order[index]) ? order : next
}

function RuntimeStartNodeSelect(props: {
  options: BlueprintRuntimeStartNodeOption[]
  selectedIds: string[]
  disabled: boolean
  onToggle: (nodeId: string) => void
}) {
  const language = useLanguage()
  const selected = () => new Set(props.selectedIds)
  const selectedOptions = () => props.options.filter((option) => selected().has(option.id))
  const label = () => {
    if (props.selectedIds.length === 0) return language.t("blueprint.runtime.startNodesTopAgent" as never)
    if (props.selectedIds.length === 1) return selectedOptions()[0]?.label ?? props.selectedIds[0]
    return language.t("blueprint.runtime.startNodesSelected" as never, { count: props.selectedIds.length } as never)
  }

  return (
    <div class="flex min-w-0 flex-col gap-2">
      <div class="text-11-medium text-[#f8fdff]">{language.t("blueprint.runtime.startNodes" as never)}</div>
      <DropdownMenu placement="bottom-start">
        <DropdownMenu.Trigger
          data-blueprint-runtime-start-node-select
          disabled={props.disabled}
          class="flex h-8 min-w-0 items-center justify-between gap-2 rounded-sm border border-[rgba(103,232,249,0.22)] bg-[#06101a] px-2 text-left text-12-regular text-[#f8fdff] outline-none transition-colors hover:border-[rgba(103,232,249,0.34)] focus:border-[#67e8f9] disabled:cursor-not-allowed disabled:opacity-55"
        >
          <span class="min-w-0 truncate">{label()}</span>
          <Icon name="chevron-down" size="small" class="shrink-0 text-[#d7f7ff]" />
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            class="max-h-64 w-72 overflow-y-auto border-[rgba(103,232,249,0.26)] bg-[#101a28] text-[#f8fdff] shadow-[0_18px_48px_rgba(0,0,0,0.42)] [&_[data-slot=dropdown-menu-checkbox-item]]:items-start"
            style={BLUEPRINT_THEME}
          >
            <Show
              when={props.options.length > 0}
              fallback={<div class="px-2 py-2 text-12-regular text-[#95afc4]">{language.t("blueprint.runtime.noStartNodes" as never)}</div>}
            >
              <For each={props.options}>
                {(option) => (
                  <DropdownMenu.CheckboxItem
                    checked={selected().has(option.id)}
                    onChange={() => props.onToggle(option.id)}
                    class="gap-2"
                  >
                    <DropdownMenu.ItemIndicator>
                      <Icon name="check-small" size="small" class="mt-0.5 text-[#67e8f9]" />
                    </DropdownMenu.ItemIndicator>
                    <div class="min-w-0">
                      <DropdownMenu.ItemLabel class="truncate text-12-medium">{option.label}</DropdownMenu.ItemLabel>
                      <DropdownMenu.ItemDescription class="line-clamp-2 text-11-regular text-[#95afc4]">
                        {option.description}
                      </DropdownMenu.ItemDescription>
                    </div>
                  </DropdownMenu.CheckboxItem>
                )}
              </For>
            </Show>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu>
      <Show when={selectedOptions().length > 0}>
        <div class="flex flex-wrap gap-1.5">
          <For each={selectedOptions()}>
            {(option) => (
              <button
                type="button"
                disabled={props.disabled}
                class="max-w-full rounded-sm border border-[rgba(103,232,249,0.24)] bg-[rgba(103,232,249,0.08)] px-2 py-1 text-10-medium text-[#d7f7ff] disabled:cursor-not-allowed disabled:opacity-55"
                onClick={() => props.onToggle(option.id)}
                title={option.label}
              >
                <span class="inline-block max-w-48 truncate align-bottom">{option.label}</span>
              </button>
            )}
          </For>
        </div>
      </Show>
    </div>
  )
}

function RuntimeActionButton(props: { label: string; description: string; disabled: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      disabled={props.disabled}
      class="min-h-11 w-full min-w-0 rounded-sm border border-[rgba(103,232,249,0.22)] bg-[rgba(8,19,31,0.72)] px-3 py-2 text-left transition-colors hover:border-[#67e8f9] hover:bg-[rgba(103,232,249,0.08)] disabled:cursor-not-allowed disabled:opacity-45"
      onClick={props.onClick}
      title={`${props.label}: ${props.description}`}
    >
      <span class="flex min-w-0 items-center justify-between gap-3">
        <span class="shrink-0 text-13-medium text-[#f8fdff]">{props.label}</span>
        <span class="min-w-0 flex-1 text-right text-10-regular leading-4 text-[#95afc4]">{props.description}</span>
      </span>
    </button>
  )
}

function RuntimeSection(props: { title: string; children: JSX.Element }) {
  return (
    <section class="rounded-md border border-[rgba(103,232,249,0.14)] bg-[#08131f] p-3">
      <div class="mb-2 text-11-medium uppercase text-[#67e8f9]">{props.title}</div>
      <div class="flex flex-col gap-2">{props.children}</div>
    </section>
  )
}

function RuntimeMetric(props: { label: string; value: string | number }) {
  const value = () => String(props.value)
  return (
    <div class="min-w-0 rounded-sm border border-[rgba(103,232,249,0.12)] bg-[#06101a] p-2" title={`${props.label}: ${value()}`}>
      <div class="truncate text-10-regular text-[#95afc4]">{props.label}</div>
      <div class="mt-0.5 truncate text-14-medium text-[#f8fdff]">{value()}</div>
    </div>
  )
}

function RuntimeWorkspaceMetric(props: {
  label: string
  value: string | number
  active: boolean
  onOpen: () => void
  onOpenInExplorer: () => void
}) {
  const language = useLanguage()
  return (
    <ContextMenu>
      <ContextMenu.Trigger class="contents">
        <button
          type="button"
          data-blueprint-runtime-workspace-metric
          class="min-w-0 rounded-sm border bg-[#06101a] p-2 text-left outline-none transition-colors hover:border-[rgba(103,232,249,0.34)] focus:border-[#67e8f9]"
          classList={{
            "border-[#67e8f9] shadow-[0_0_0_1px_rgba(103,232,249,0.2)]": props.active,
            "border-[rgba(103,232,249,0.12)]": !props.active,
          }}
          onClick={props.onOpen}
        >
          <div class="truncate text-10-regular text-[#95afc4]">{props.label}</div>
          <div class="mt-0.5 truncate text-14-medium text-[#f8fdff]">{props.value}</div>
        </button>
      </ContextMenu.Trigger>
      <ContextMenu.Portal>
        <ContextMenu.Content>
          <ContextMenu.Item onSelect={props.onOpenInExplorer}>
            <Icon size="small" name="folder" />
            <ContextMenu.ItemLabel>{language.t("blueprint.runtime.openInExplorer" as never)}</ContextMenu.ItemLabel>
          </ContextMenu.Item>
        </ContextMenu.Content>
      </ContextMenu.Portal>
    </ContextMenu>
  )
}

function WorkspaceContentPanel(props: {
  area: WorkspacePanelArea
  workspace?: Record<string, unknown>
  onClose: () => void
  onOpenDirectory: () => void
  onRevealItem: (path: string | undefined) => void
}) {
  const language = useLanguage()
  const items = createMemo(() => workspaceAreaItems(props.workspace, props.area))
  const title = () => workspaceAreaTitle(language.t, props.area)
  return (
    <div
      data-blueprint-workspace-content-panel
      class="absolute right-3 top-3 z-30 flex max-h-[min(520px,calc(100%-24px))] w-[420px] max-w-[calc(100%-24px)] flex-col rounded-md border border-[rgba(103,232,249,0.28)] bg-[#08131f] shadow-[0_18px_52px_rgba(0,0,0,0.44)]"
      onPointerDown={(event) => event.stopPropagation()}
      onWheel={(event) => event.stopPropagation()}
      onContextMenu={(event) => event.stopPropagation()}
    >
      <div class="flex shrink-0 items-center justify-between gap-3 border-b border-[rgba(103,232,249,0.14)] px-3 py-2">
        <div class="min-w-0 truncate text-12-medium text-[#67e8f9]">{title()}</div>
        <div class="flex shrink-0 items-center gap-1">
          <IconButton
            icon="folder"
            variant="ghost"
            class="h-6 w-6 text-[#f8fdff]"
            onClick={props.onOpenDirectory}
            aria-label={language.t("blueprint.runtime.openInExplorer" as never)}
          />
          <IconButton
            icon="close"
            variant="ghost"
            class="h-6 w-6 text-[#f8fdff]"
            onClick={props.onClose}
            aria-label={language.t("blueprint.runtime.closeWorkspacePanel" as never)}
          />
        </div>
      </div>
      <div class="min-h-0 overflow-y-auto p-3">
        <Show
          when={items().length > 0}
          fallback={
            <div class="rounded-sm border border-dashed border-[rgba(103,232,249,0.18)] px-3 py-5 text-center text-12-regular text-[#95afc4]">
              {language.t("blueprint.runtime.emptyWorkspaceArea" as never)}
            </div>
          }
        >
          <div class="flex flex-col gap-2">
            <For each={items()}>
              {(item) => (
                <ContextMenu>
                  <ContextMenu.Trigger class="contents">
                    <div
                      data-blueprint-workspace-content-item
                      class="min-w-0 rounded-sm border border-[rgba(103,232,249,0.14)] bg-[#06101a] px-3 py-2"
                    >
                      <div class="truncate text-12-medium text-[#f8fdff]">{item.name}</div>
                      <Show when={item.absolutePath}>
                        {(path) => <div class="mt-1 break-all font-mono text-10-regular text-[#95afc4]">{path()}</div>}
                      </Show>
                      <Show when={item.detail}>
                        {(detail) => <div class="mt-1 line-clamp-2 text-10-regular text-[#7da0b8]">{detail()}</div>}
                      </Show>
                    </div>
                  </ContextMenu.Trigger>
                  <ContextMenu.Portal>
                    <ContextMenu.Content>
                      <ContextMenu.Item onSelect={() => props.onRevealItem(item.absolutePath)}>
                        <Icon size="small" name="open-file" />
                        <ContextMenu.ItemLabel>{language.t("blueprint.runtime.openInExplorer" as never)}</ContextMenu.ItemLabel>
                      </ContextMenu.Item>
                    </ContextMenu.Content>
                  </ContextMenu.Portal>
                </ContextMenu>
              )}
            </For>
          </div>
        </Show>
      </div>
    </div>
  )
}

function AgentStatusRow(props: { label: string; value: string; mono?: boolean; tone?: "danger" }) {
  return (
    <div class="min-w-0 rounded-sm border border-[rgba(103,232,249,0.1)] bg-[#06101a] px-2 py-1.5">
      <div class="text-10-regular text-[#95afc4]">{props.label}</div>
      <div
        class="mt-0.5 break-all text-11-regular leading-4"
        classList={{
          "font-mono": props.mono,
          "text-[#f8fdff]": props.tone !== "danger",
          "text-[#fecaca]": props.tone === "danger",
        }}
      >
        {props.value}
      </div>
    </div>
  )
}

function runtimeAgentDetail(agent: Record<string, unknown>, language: ReturnType<typeof useLanguage>) {
  const primary = String(agent.last_error ?? agent.task_summary ?? agent.agent_id ?? "")
  const flow = `${language.t("blueprint.runtime.flow" as never)}: ${agent.has_received_flow ? "yes" : "no"}`
  const prompted = agent.summary_prompted_at ? language.t("blueprint.runtime.summaryPrompt" as never) : ""
  return [primary, flow, prompted].filter(Boolean).join(" · ")
}

function RuntimeRow(props: { title: string; meta?: string; detail?: string }) {
  return (
    <div class="min-w-0 rounded-sm border border-[rgba(103,232,249,0.12)] bg-[#06101a] px-2 py-1.5">
      <div class="flex min-w-0 items-center justify-between gap-2">
        <div class="min-w-0 truncate text-12-medium text-[#f8fdff]">{props.title}</div>
        <Show when={props.meta}>
          {(meta) => <div class="shrink-0 truncate text-10-regular text-[#95afc4]">{meta()}</div>}
        </Show>
      </div>
      <Show when={props.detail}>
        {(detail) => <div class="mt-0.5 truncate text-11-regular text-[#95afc4]">{detail()}</div>}
      </Show>
    </div>
  )
}

function RuntimeEventRow(props: { title: string; meta?: string; detail?: string }) {
  return (
    <div class="min-w-0 rounded-sm border border-[rgba(103,232,249,0.1)] bg-[#06101a] px-2 py-0.5">
      <div class="flex min-w-0 items-center justify-between gap-2">
        <div class="min-w-0 truncate text-10-medium leading-4 text-[#f8fdff]">{props.title}</div>
        <Show when={props.meta}>
          {(meta) => <div class="shrink-0 truncate text-10-regular leading-4 text-[#95afc4]">{meta()}</div>}
        </Show>
      </div>
      <Show when={props.detail}>
        {(detail) => <div class="truncate text-10-regular leading-4 text-[#95afc4]">{detail()}</div>}
      </Show>
    </div>
  )
}

function RuntimeEmpty(props: { when: boolean }) {
  const language = useLanguage()
  return (
    <Show when={props.when}>
      <div class="rounded-sm border border-dashed border-[rgba(103,232,249,0.16)] px-2 py-3 text-center text-11-regular text-[#95afc4]">
        {language.t("blueprint.runtime.empty")}
      </div>
    </Show>
  )
}

function RuntimeJsonPreview(props: { value: Record<string, unknown> }) {
  return (
    <pre class="max-h-40 overflow-auto rounded-sm border border-[rgba(103,232,249,0.12)] bg-[#06101a] p-2 text-10-regular leading-4 text-[#b8cede]">
      {JSON.stringify(props.value, null, 2)}
    </pre>
  )
}

function AgentInfoPanel(props: {
  panel: AgentPanelEntry
  node?: BlueprintAgentNode
  runId?: string
  runtimeStatus?: string
  testLogActive: boolean
  events: AgentStreamEvent[]
  onClose: () => void
  onPin: () => void
  onMovePointerDown: (event: PointerEvent) => void
  onResizePointerDown: (event: PointerEvent) => void
  onInput: (value: string) => void
  onMode: (value: "default" | "top") => void
  onSend: () => void
}) {
  const runtime = createMemo(() => asRecord(props.panel.info?.runtime))
  const latestStatus = createMemo(() => latestAgentStatusEvent(props.events))
  const latestTaskStatus = createMemo(() => latestAgentTaskStatusEvent(props.events))
  const latestStatusRecord = createMemo(() => asRecord(latestStatus()))
  const latestTaskStatusRecord = createMemo(() => asRecord(latestTaskStatus()))
  const statusField = (key: string) => latestStatusRecord()?.[key] ?? runtime()?.[key]
  const testMode = createMemo(() => Boolean(props.panel.info?.testMode))
  const testAgentRecording = createMemo(
    () => props.testLogActive || testMode() || Boolean(props.panel.testJsonPath) || Boolean(props.panel.testJsonPending),
  )
  const testJsonPath = createMemo(() => {
    const path = props.panel.testJsonPath ?? props.panel.info?.jsonPath
    return typeof path === "string" && path ? path : undefined
  })
  const live = createMemo(() => !!props.runId && !isTerminalRuntimeStatus(props.runtimeStatus))
  const state = createMemo(() =>
    String(statusField("agent_state") ?? runtime()?.state ?? (props.runId ? props.runtimeStatus ?? "running" : "未运行")),
  )
  const taskStatus = createMemo(() =>
    String(latestTaskStatusRecord()?.status ?? statusField("task_status") ?? runtime()?.task_status ?? "not_started"),
  )
  const taskSummary = createMemo(() =>
    agentStreamStructuredText(latestTaskStatusRecord()?.summary ?? statusField("task_summary") ?? runtime()?.task_summary),
  )
  const taskMessageId = createMemo(
    () =>
      stringValue(latestTaskStatusRecord()?.message_id) ??
      stringValue(statusField("task_status_message_id")) ??
      stringValue(runtime()?.task_status_message_id),
  )
  const queueSize = createMemo(() => String(statusField("queue_size") ?? 0))
  const messagesSent = createMemo(() => String(statusField("messages_sent") ?? 0))
  const busyCount = createMemo(() => String(statusField("busy_count") ?? 0))
  const currentMessageId = createMemo(() => stringValue(statusField("current_message_id")) ?? stringValue(statusField("message_id")))
  const statusUpdatedAt = createMemo(() => formatAgentStreamEventTime(statusField("created_at")))
  const lastError = createMemo(() => stringValue(statusField("last_error")))
  const visibleEvents = createMemo<AgentPanelDisplayEvent[]>((previous) =>
    stabilizeAgentPanelDisplayEvents(previous, visibleAgentPanelEvents(props.events, props.panel.userMessages ?? [])),
  [])
  const statusDetails = createMemo(() =>
    [
      { label: "runId", value: stringValue(statusField("run_id")) ?? props.runId },
      { label: "eventId", value: stringValue(statusField("event_id")) },
      { label: "seq", value: agentStatusFieldText(statusField("seq")) },
      { label: "messageId", value: stringValue(statusField("message_id")) },
      { label: "currentMessageId", value: currentMessageId() },
    ].filter((item): item is { label: string; value: string } => Boolean(item.value)),
  )
  const sendDisabled = createMemo(() => testMode() || !live() || props.panel.sending || !props.panel.input.trim())
  const width = () => props.panel.width ?? AGENT_PANEL_DEFAULT_WIDTH
  const height = () => props.panel.height ?? AGENT_PANEL_DEFAULT_HEIGHT
  const [statusDetailsOpen, setStatusDetailsOpen] = createSignal(false)
  const [agentPanelEventOpen, setAgentPanelEventOpen] = createSignal<Record<string, boolean>>({})
  const isAgentPanelEventOpen = (eventId: string) => Boolean(agentPanelEventOpen()[eventId])
  const setAgentPanelEventOpenState = (eventId: string, open: boolean) => {
    setAgentPanelEventOpen((current) => ({ ...current, [eventId]: open }))
  }

  return (
    <div
      data-agent-info-panel
      class="absolute z-30 flex select-text flex-col overflow-hidden rounded-lg border border-[rgba(103,232,249,0.44)] bg-[rgba(6,16,26,0.98)] text-[#d6e9f5] shadow-[0_22px_80px_rgba(0,0,0,0.58),0_0_0_1px_rgba(103,232,249,0.14)] backdrop-blur"
      style={{
        left: `${props.panel.x}px`,
        top: `${props.panel.y}px`,
        width: `${width()}px`,
        height: `${height()}px`,
      }}
      onPointerDown={(event) => event.stopPropagation()}
      onWheel={(event) => event.stopPropagation()}
    >
      <div class="flex h-10 shrink-0 items-center justify-between border-b border-[rgba(103,232,249,0.16)] px-3">
        <div
          class="min-w-0 flex-1 cursor-move select-none"
          onPointerDown={props.onMovePointerDown}
          title="拖动移动信息面板"
        >
          <div class="truncate text-12-medium text-[#f8fdff]">{props.node?.agent_id || props.panel.nodeId}</div>
          <div class="truncate text-10-regular text-[#8fb4c8]">
            {props.node?.cli_kind ?? "agent"} · {state()}
          </div>
        </div>
        <div class="flex items-center gap-1">
          <IconButton
            icon="status"
            variant="ghost"
            class="h-7 w-7 text-[#d7f7ff]"
            classList={{ "bg-[rgba(103,232,249,0.16)]": props.panel.pinned }}
            onClick={props.onPin}
            aria-label="pin agent panel"
          />
          <IconButton
            icon="close-small"
            variant="ghost"
            class="h-7 w-7 text-[#d7f7ff]"
            onClick={props.onClose}
            aria-label="close agent panel"
          />
        </div>
      </div>
      <div data-agent-panel-status-summary class="shrink-0 border-b border-[rgba(103,232,249,0.12)] p-3 text-11-regular">
        <div class="flex items-stretch gap-2">
          <div class="grid min-w-0 flex-1 grid-cols-3 gap-2">
            <RuntimeMetric label="状态" value={state()} />
            <RuntimeMetric label="任务状态" value={taskStatus()} />
            <RuntimeMetric label="队列" value={queueSize()} />
            <RuntimeMetric label="消息" value={messagesSent()} />
            <RuntimeMetric label="忙碌" value={busyCount()} />
          </div>
          <Button
            size="small"
            variant="ghost"
            class="min-h-[60px] w-8 shrink-0 self-stretch px-0 text-[#d7f7ff]"
            classList={{ "bg-[rgba(103,232,249,0.12)]": statusDetailsOpen() }}
            onClick={() => setStatusDetailsOpen((open) => !open)}
            aria-expanded={statusDetailsOpen()}
            aria-label="toggle agent panel status details"
            title={statusDetailsOpen() ? "收起状态详情" : "展开状态详情"}
          >
            <Icon
              size="small"
              name="chevron-down"
              class={`text-[#8fb4c8] transition-transform ${statusDetailsOpen() ? "rotate-180" : ""}`}
            />
          </Button>
        </div>
        <Show when={statusDetailsOpen()}>
          <div data-agent-panel-status-details class="mt-2 flex flex-col gap-2">
            <div class="rounded-md border border-[rgba(103,232,249,0.14)] bg-[#08131f] p-2">
              <div class="mb-2 text-10-medium uppercase text-[#67e8f9]">运行状态</div>
              <div class="flex flex-col gap-1">
                <AgentStatusRow label="当前状态" value={state()} />
                <AgentStatusRow label="任务状态" value={taskStatus()} />
                <Show when={taskMessageId()}>
                  {(value) => <AgentStatusRow label="任务消息" value={value()} mono />}
                </Show>
                <Show when={taskSummary()}>
                  {(value) => <AgentStatusRow label="任务摘要" value={value()} />}
                </Show>
                <Show when={currentMessageId()}>
                  {(value) => <AgentStatusRow label="当前消息" value={value()} mono />}
                </Show>
                <Show when={statusUpdatedAt()}>
                  {(value) => <AgentStatusRow label="最后更新" value={value()} />}
                </Show>
                <Show when={lastError()}>
                  {(value) => <AgentStatusRow label="最后错误" value={value()} tone="danger" />}
                </Show>
              </div>
              <Show when={statusDetails().length}>
                <Collapsible variant="ghost" class="mt-2">
                  <Collapsible.Trigger class="flex w-full items-center justify-between rounded-sm border border-[rgba(103,232,249,0.12)] bg-[#06101a] px-2 py-1.5 text-left text-11-medium text-[#d6e9f5]">
                    <span>状态详情</span>
                    <Collapsible.Arrow class="text-[#7fa4ba]" />
                  </Collapsible.Trigger>
                  <Collapsible.Content>
                    <div class="mt-1 flex flex-col gap-1">
                      <For each={statusDetails()}>
                        {(item) => <AgentStatusRow label={item.label} value={item.value} mono />}
                      </For>
                    </div>
                  </Collapsible.Content>
                </Collapsible>
              </Show>
            </div>
            <Show when={testAgentRecording()}>
              <div class="rounded-md border border-[rgba(250,204,21,0.22)] bg-[rgba(250,204,21,0.06)] p-2">
                <div class="mb-1 text-10-medium uppercase text-[#facc15]">JSON 位置</div>
                <div class="break-all font-mono text-[11px] leading-4 text-[#fde68a]">
                  {testJsonPath() ?? (props.panel.testJsonPending ? "写入中..." : "未生成")}
                </div>
                <Show when={props.panel.testJsonError}>
                  {(error) => <div class="mt-1 break-all text-10-regular text-[#fca5a5]">JSON 保存失败: {error()}</div>}
                </Show>
              </div>
            </Show>
          </div>
        </Show>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto px-3 py-2 [overflow-anchor:none]" onWheel={(event) => event.stopPropagation()}>
        <Show
          when={visibleEvents().length}
          fallback={<div class="py-8 text-center text-11-regular text-[#7fa4ba]">暂无 agent 输出</div>}
        >
          <Index each={visibleEvents()}>
            {(event) => (
              <AgentPanelDisplayEventRow
                event={event()}
                open={isAgentPanelEventOpen(event().id)}
                onOpenChange={(open) => setAgentPanelEventOpenState(event().id, open)}
                isEventOpen={isAgentPanelEventOpen}
                onEventOpenChange={setAgentPanelEventOpenState}
              />
            )}
          </Index>
        </Show>
      </div>
      <div class="shrink-0 border-t border-[rgba(103,232,249,0.16)] p-3">
        <Show when={testAgentRecording()}>
          <div class="mb-2 rounded border border-[rgba(250,204,21,0.28)] bg-[rgba(250,204,21,0.08)] px-2 py-1.5 text-11-regular text-[#fde68a]">
            测试节点信息正在实时写入 JSON。
          </div>
        </Show>
        <Show when={!live() && !testMode()}>
          <div class="mb-2 rounded border border-[rgba(251,191,36,0.2)] bg-[rgba(251,191,36,0.08)] px-2 py-1.5 text-11-regular text-[#facc15]">
            蓝图未 live 运行，点击开始后可发送消息。
          </div>
        </Show>
        <Show when={props.panel.error}>
          <div class="mb-2 rounded border border-[rgba(248,113,113,0.28)] bg-[rgba(127,29,29,0.24)] px-2 py-1.5 text-11-regular text-[#fecaca]">
            {props.panel.error}
          </div>
        </Show>
        <textarea
          class="h-16 w-full resize-none rounded-md border border-[rgba(103,232,249,0.18)] bg-[#06101a] px-2 py-1.5 text-12-regular text-[#f8fdff] outline-none placeholder:text-[#607f92] focus:border-[rgba(103,232,249,0.52)]"
          value={props.panel.input}
          disabled={testMode() || !live() || props.panel.sending}
          placeholder={live() ? "发送给这个 agent…" : "等待 live runtime"}
          onInput={(event) => props.onInput(event.currentTarget.value)}
        />
        <div class="mt-2 flex items-center gap-2">
          <select
            class="h-8 rounded-md border border-[rgba(103,232,249,0.18)] bg-[#071019] px-2 text-11-regular text-[#d6e9f5]"
            value={props.panel.mode}
            disabled={testMode() || !live() || props.panel.sending}
            onInput={(event) => props.onMode(event.currentTarget.value === "top" ? "top" : "default")}
          >
            <option value="default">默认</option>
            <option value="top">置顶</option>
          </select>
          <Button size="small" onClick={props.onSend} disabled={sendDisabled()} class="ml-auto">
            {props.panel.sending ? "发送中" : "发送"}
          </Button>
        </div>
      </div>
      <button
        type="button"
        class="absolute bottom-0 right-0 z-10 size-5 cursor-nwse-resize rounded-tl-md border-l border-t border-[rgba(103,232,249,0.24)] bg-[rgba(7,16,25,0.76)] text-[#67e8f9] hover:bg-[rgba(103,232,249,0.16)]"
        onPointerDown={props.onResizePointerDown}
        aria-label="resize agent info panel"
        title="拖动缩放信息面板"
      >
        <span class="absolute bottom-1 right-1 h-2.5 w-2.5 border-b border-r border-current opacity-80" />
        <span class="absolute bottom-1 right-1 h-1.5 w-1.5 border-b border-r border-current opacity-60" />
      </button>
    </div>
  )
}

function AgentPanelDisplayEventBody(props: { event: AgentPanelDisplayEvent }) {
  const markdownClass =
    "select-text text-[12px] leading-[1.55] text-[#d6e9f5] [&_h1]:!mb-2 [&_h1]:!text-[12px] [&_h1]:!text-[#d6e9f5] [&_h2]:!mb-2 [&_h2]:!text-[12px] [&_h2]:!text-[#d6e9f5] [&_h3]:!mb-2 [&_h3]:!text-[12px] [&_h3]:!text-[#d6e9f5] [&_p]:mb-2 [&_ul]:my-2 [&_ol]:my-2 [&_li]:mb-1 [&_pre]:!my-2 [&_pre]:!bg-[#06101a] [&_.shiki]:!bg-[#06101a] [&_.shiki]:!p-2 [&_.shiki]:!text-[11px] [&_code]:text-[11px]"
  return (
    <Show
      when={props.event.tone === "reply"}
      fallback={
        <pre class="select-text whitespace-pre-wrap break-words font-mono text-[11px] leading-4 text-[#d6e9f5]">
          {props.event.text}
        </pre>
      }
    >
      <Markdown
        text={props.event.text}
        cacheKey={props.event.id}
        streaming={props.event.status !== "completed"}
        class={markdownClass}
      />
    </Show>
  )
}

function AgentPanelDisplayEventRow(props: {
  event: AgentPanelDisplayEvent
  open: boolean
  onOpenChange: (open: boolean) => void
  isEventOpen: (eventId: string) => boolean
  onEventOpenChange: (eventId: string, open: boolean) => void
  nested?: boolean
}) {
  const event = () => props.event
  const compact = () => event().tone === "tool"
  const toolCategory = () => (event().tone === "tool" ? event().toolCategory ?? "codex" : undefined)
  const nestedToolItems = () =>
    event().tone === "tool" && (event().toolItems?.length ?? 0) > 1 ? (event().toolItems ?? []) : []
  const hasNestedToolItems = () => nestedToolItems().length > 0
  return (
    <div
      class={`${compact() ? "mb-1 px-2 py-1" : "mb-2 p-2"} rounded-md border`}
      classList={{
        "ml-8 border-[rgba(103,232,249,0.20)] bg-[rgba(103,232,249,0.08)]": event().tone === "user",
        "border-[rgba(103,232,249,0.12)] bg-[#071019]": event().tone === "reply" || event().tone === "event" || !event().tone,
        "border-[rgba(168,85,247,0.20)] bg-[rgba(88,28,135,0.14)]": event().tone === "reasoning",
        "border-[rgba(59,130,246,0.36)] bg-[rgba(30,64,175,0.16)]": event().tone === "tool" && toolCategory() === "mcp",
        "border-[rgba(168,85,247,0.38)] bg-[rgba(88,28,135,0.18)]": event().tone === "tool" && toolCategory() === "command",
        "border-[rgba(34,211,238,0.34)] bg-[rgba(8,145,178,0.16)]": event().tone === "tool" && (toolCategory() === "codex" || toolCategory() === "mixed"),
        "border-[rgba(248,113,113,0.24)] bg-[rgba(127,29,29,0.22)]": event().tone === "error",
      }}
    >
      <Show
        when={event().collapsible}
        fallback={
          <>
            <div class="mb-1 flex items-center justify-between gap-2 text-10-regular text-[#7fa4ba]">
              <span>{event().kind}</span>
              <span>{event().status ?? (event().seq ? `#${event().seq}` : "")}</span>
            </div>
            <AgentPanelDisplayEventBody event={event()} />
          </>
        }
      >
        <Collapsible variant="ghost" open={props.open} onOpenChange={props.onOpenChange}>
          <Collapsible.Trigger
            class={`flex w-full items-center justify-between gap-2 rounded-sm text-left text-11-medium text-[#d6e9f5] ${
              compact() ? "!h-7 px-0 py-0" : "px-1 py-0.5"
            }`}
          >
            <span class="min-w-0 truncate">{event().kind}</span>
            <div class="flex shrink-0 items-center gap-2 text-10-regular text-[#7fa4ba]">
              <Show when={toolCategory()}>
                {(category) => (
                  <span class={agentPanelToolCategoryBadgeClass(category())} title={agentPanelToolCategoryTitle(category())}>
                    {agentPanelToolCategoryLabel(category())}
                  </span>
                )}
              </Show>
              <Show when={event().status}>{(status) => <span>{status()}</span>}</Show>
              <Collapsible.Arrow class="text-[#7fa4ba]" />
            </div>
          </Collapsible.Trigger>
          <Collapsible.Content>
            <Show when={event().detail}>
              {(detail) => <div class="mb-1 break-all text-10-regular text-[#95afc4]">{detail()}</div>}
            </Show>
            <Show
              when={hasNestedToolItems()}
              fallback={
                <AgentPanelDisplayEventBody event={event()} />
              }
            >
              <div class="mt-1 flex flex-col gap-1">
                <For each={nestedToolItems()}>
                  {(tool) => (
                    <AgentPanelDisplayEventRow
                      event={tool}
                      open={props.isEventOpen(tool.id)}
                      onOpenChange={(open) => props.onEventOpenChange(tool.id, open)}
                      isEventOpen={props.isEventOpen}
                      onEventOpenChange={props.onEventOpenChange}
                      nested
                    />
                  )}
                </For>
              </div>
            </Show>
          </Collapsible.Content>
        </Collapsible>
      </Show>
    </div>
  )
}

function BlueprintNodeView(props: {
  item: NodeItem
  title: string
  subtitle: string
  selected: boolean
  inspecting: boolean
  connecting: boolean
  runtimeVisualState: RuntimeNodeVisualState
  hasIncomingEdge: boolean
  hasOutgoingEdge: boolean
  isConnectTargetVisible: boolean
  agentPanelProgress: number
  layout?: BlueprintNodeLayout
  onPointerDown: (event: PointerEvent) => void
  onDoubleClick: () => void
  onDelete: () => void
  onEdit: () => void
  onInfoPanel: () => void
  onScriptCollapsedChange: (collapsed: boolean) => void
  onOutputPointerDown: (event: PointerEvent, portName: string) => void
  onInputPointerUp: (event: PointerEvent, portName: string) => void
}) {
  const language = useLanguage()
  const [hovering, setHovering] = createSignal(false)
  const size = () => nodeItemSize(props.item)
  const width = () => size().width
  const height = () => size().height
  const interactive = () => props.selected || props.inspecting || props.connecting || hovering()
  const supportsInput = () =>
    props.item.type === "common"
      ? props.item.node.kind !== "tick"
      : props.item.type !== "terminal" || props.item.kind === "end"
  const supportsOutput = () => props.item.type !== "terminal" || props.item.kind === "start"
  const expandedScript = () => props.item.type === "script" && !props.item.node.collapsed
  const portShape = (side: "input" | "output") =>
    props.item.type === "script" || (props.item.type === "common" && props.item.node.kind === "branch" && side === "input")
      ? "triangle"
      : "circle"
  const inputPorts = () => nodePorts(props.item, "input")
  const outputPorts = () => nodePorts(props.item, "output")
  const showBranchPortLabels = () => props.item.type === "common" && props.item.node.kind === "branch"
  const showInput = () => supportsInput() && (props.hasIncomingEdge || props.isConnectTargetVisible || interactive() || expandedScript())
  const showOutput = () => supportsOutput() && (props.hasOutgoingEdge || interactive() || expandedScript())
  const agentPanelProgress = () => clamp(props.agentPanelProgress, 0, 1)
  const nodeTone = createMemo(() => {
    if (props.item.type === "terminal") {
      return props.item.kind === "start"
        ? {
            background: "linear-gradient(135deg, rgba(15, 82, 70, 0.96), rgba(8, 36, 45, 0.96))",
            border: props.selected ? "rgba(45, 212, 191, 0.92)" : "rgba(45, 212, 191, 0.48)",
            icon: "#5eead4",
            text: "#f8fdff",
            subtitle: "#d6e9f5",
          }
        : {
            background: "linear-gradient(135deg, rgba(72, 36, 89, 0.96), rgba(22, 22, 44, 0.96))",
            border: props.selected ? "rgba(216, 180, 254, 0.92)" : "rgba(192, 132, 252, 0.48)",
            icon: "#d8b4fe",
            text: "#f8fdff",
            subtitle: "#d6e9f5",
          }
    }
    if (props.item.type === "route") {
      return {
        background: "linear-gradient(135deg, rgba(18, 46, 66, 0.98), rgba(8, 24, 36, 0.98))",
        border: props.selected ? "rgba(125, 211, 252, 0.94)" : "rgba(56, 189, 248, 0.5)",
        icon: "#7dd3fc",
        text: "#f8fdff",
        subtitle: "#d6e9f5",
      }
    }
    if (props.item.type === "common") {
      return props.item.node.kind === "tick"
        ? {
            background: "linear-gradient(135deg, rgba(22, 78, 99, 0.98), rgba(8, 47, 73, 0.98))",
            border: props.selected ? "rgba(103, 232, 249, 0.96)" : "rgba(34, 211, 238, 0.54)",
            icon: "#67e8f9",
            text: "#f8fdff",
            subtitle: "#d6e9f5",
          }
        : {
            background: "linear-gradient(135deg, rgba(63, 63, 70, 0.98), rgba(24, 24, 27, 0.98))",
            border: props.selected ? "rgba(245, 158, 11, 0.96)" : "rgba(245, 158, 11, 0.52)",
            icon: "#f59e0b",
            text: "#f8fdff",
            subtitle: "#e4e4e7",
          }
    }
    if (props.item.type === "script") {
      return {
        background: "linear-gradient(135deg, #ffe06a, #f6c945)",
        border: props.selected ? "#f8fafc" : "rgba(247, 210, 75, 0.88)",
        icon: "#1f4e79",
        text: "#082f49",
        subtitle: "#2f3a18",
      }
    }
    if (props.item.node.node_type === "agent") {
      return {
        background: "linear-gradient(135deg, #bbf7d0, #86efac)",
        border: props.selected ? "#dcfce7" : "#4ade80",
        icon: "#14532d",
        text: "#052e16",
        subtitle: "#14532d",
      }
    }
    return {
      background: "linear-gradient(135deg, rgba(25, 39, 62, 0.98), rgba(10, 20, 34, 0.98))",
      border: props.selected ? "rgba(103, 232, 249, 0.96)" : "rgba(99, 179, 215, 0.46)",
      icon: "#67e8f9",
      text: "#f8fdff",
      subtitle: "#d6e9f5",
    }
  })

  return (
    <ContextMenu>
      <ContextMenu.Trigger class="contents">
        <div
          data-blueprint-node
          data-runtime-state={props.runtimeVisualState}
          role="button"
          tabIndex={0}
          class="absolute flex flex-col items-start justify-center gap-1 rounded-md border px-3 text-left transition-[border-color,box-shadow,background-color]"
          classList={{
            "outline outline-2 outline-offset-2 outline-[rgba(103,232,249,0.52)]": props.connecting || props.inspecting,
          }}
          style={{
            width: `${width()}px`,
            height: `${height()}px`,
            transform: `translate3d(${props.layout?.x ?? 0}px, ${props.layout?.y ?? 0}px, 0)`,
            background: nodeTone().background,
            "border-color": nodeTone().border,
            "border-width": props.selected ? "2px" : "1px",
            "box-shadow": runtimeNodeBoxShadow(props.runtimeVisualState),
          }}
          onPointerDown={props.onPointerDown}
          onPointerEnter={() => setHovering(true)}
          onPointerLeave={() => setHovering(false)}
          onDblClick={(event) => {
            event.stopPropagation()
            props.onDoubleClick()
          }}
          aria-pressed={props.selected}
        >
          <Show when={showInput()}>
            <For each={inputPorts()}>
              {(port) => (
                <PortButton
                  nodeId={props.item.id}
                  side="input"
                  portName={port.name}
                  title={port.title}
                  top={port.top}
                  shape={portShape("input")}
                  onPointerUp={(event) => props.onInputPointerUp(event, port.name)}
                  onPointerDown={(event) => event.stopPropagation()}
                />
              )}
            </For>
          </Show>
          <Show when={showOutput()}>
            <For each={outputPorts()}>
              {(port) => (
                <PortButton
                  nodeId={props.item.id}
                  side="output"
                  portName={port.name}
                  title={port.title}
                  top={port.top}
                  shape={portShape("output")}
                  onPointerDown={(event) => props.onOutputPointerDown(event, port.name)}
                />
              )}
            </For>
          </Show>
          <Show
            when={props.item.type === "script" ? props.item : undefined}
            fallback={
              <Show
                when={showBranchPortLabels()}
                fallback={
                  <>
                    <div class="flex w-full min-w-0 items-center gap-2">
                      <Icon
                        size="small"
                        name={props.item.type === "terminal" ? "selector" : props.item.type === "route" || props.item.type === "common" ? "branch" : "blueprint"}
                        class="shrink-0"
                        style={{ color: nodeTone().icon }}
                      />
                      <div class="min-w-0 truncate text-12-medium" style={{ color: nodeTone().text }}>{props.title}</div>
                    </div>
                    <Show when={props.item.type !== "terminal"}>
                      <div class="w-full truncate text-11-regular" style={{ color: nodeTone().subtitle }}>{props.subtitle}</div>
                    </Show>
                  </>
                }
              >
                <div class="pointer-events-none absolute left-3 right-3 top-3 z-10 flex min-w-0 items-center gap-2">
                  <Icon
                    size="small"
                    name="branch"
                    class="shrink-0"
                    style={{ color: nodeTone().icon }}
                  />
                  <div class="min-w-0 truncate text-12-medium" style={{ color: nodeTone().text }}>{props.title}</div>
                </div>
                <For each={inputPorts()}>
                  {(port) => (
                    <div
                      data-blueprint-common-port-label="input"
                      class="pointer-events-none absolute left-4 z-10 h-[18px] max-w-[90px] truncate text-10-medium leading-[18px]"
                      style={{
                        top: `${(port.top ?? COMMON_BRANCH_HEIGHT / 2) - 9}px`,
                        color: nodeTone().text,
                      }}
                    >
                      {port.title}
                    </div>
                  )}
                </For>
                <For each={outputPorts()}>
                  {(port) => (
                    <div
                      data-blueprint-common-port-label="output"
                      class="pointer-events-none absolute right-4 z-10 h-[18px] max-w-[108px] truncate text-right text-10-medium leading-[18px]"
                      style={{
                        top: `${(port.top ?? COMMON_BRANCH_HEIGHT / 2) - 9}px`,
                        color: nodeTone().subtitle,
                      }}
                    >
                      {port.title}
                    </div>
                  )}
                </For>
              </Show>
            }
          >
            {(scriptItem) => (
              <>
                <div data-blueprint-script-background class="pointer-events-none absolute inset-0 z-0 overflow-hidden rounded-md">
                  <div class="absolute inset-0 bg-[linear-gradient(135deg,#ffe06a,#f6c945)]" />
                  <div
                    class="absolute inset-0 bg-[linear-gradient(135deg,#45b7ea,#2e9fd4)] drop-shadow-[3px_0_7px_rgba(8,47,73,0.18)]"
                    style={{ "clip-path": SCRIPT_NODE_BLUE_CLIP_PATH }}
                  />
                  <svg
                    data-blueprint-script-split-line
                    class="absolute inset-0 h-full w-full"
                    viewBox="0 0 100 100"
                    preserveAspectRatio="none"
                    aria-hidden="true"
                  >
                    <polyline
                      data-blueprint-script-split-shadow
                      points={SCRIPT_NODE_SPLIT_LINE_POINTS}
                      fill="none"
                      stroke="rgba(8,47,73,0.2)"
                      stroke-width="5.2"
                      stroke-linejoin="miter"
                      stroke-linecap="square"
                      vector-effect="non-scaling-stroke"
                      style={{ filter: "drop-shadow(2px 0 4px rgba(8,47,73,0.42))" }}
                    />
                    <polyline
                      points={SCRIPT_NODE_SPLIT_LINE_POINTS}
                      fill="none"
                      stroke="rgba(8,47,73,0.38)"
                      stroke-width="1.15"
                      stroke-linejoin="miter"
                      stroke-linecap="square"
                      vector-effect="non-scaling-stroke"
                    />
                    <polyline
                      points={SCRIPT_NODE_SPLIT_LINE_POINTS}
                      fill="none"
                      stroke="rgba(255,255,255,0.28)"
                      stroke-width="0.65"
                      stroke-linejoin="miter"
                      stroke-linecap="square"
                      vector-effect="non-scaling-stroke"
                      transform="translate(-0.45 0)"
                    />
                  </svg>
                  <div class="absolute inset-0 bg-[linear-gradient(155deg,rgba(255,255,255,0.14),transparent_36%,rgba(0,0,0,0.04)_100%)]" />
                </div>
                <div class="pointer-events-none absolute left-3 right-3 top-3 z-10 flex min-w-0 items-center gap-2">
                  <span
                    class="grid h-6 w-8 shrink-0 place-items-center rounded-sm text-13-medium"
                    style={{ color: "#1f4e79", background: "rgba(255,255,255,0.58)" }}
                  >
                    Py
                  </span>
                  <div class="min-w-0 truncate text-13-medium" style={{ color: nodeTone().text }}>{props.title}</div>
                </div>
                <Show
                  when={scriptItem().node.collapsed === false}
                  fallback={
                    <div
                      class="pointer-events-none absolute left-3 right-7 top-[42px] z-10 truncate text-12-regular"
                      style={{ color: nodeTone().subtitle }}
                    >
                      {scriptNodeDescription(language.t, scriptItem().node)}
                    </div>
                  }
                >
                  <For each={scriptItem().node.inputs}>
                    {(port) => (
                      <div
                        data-blueprint-script-port-label="input"
                        class="pointer-events-none absolute left-4 z-10 h-[18px] max-w-[calc(50%_-_28px)] truncate text-10-medium leading-[18px]"
                        style={{
                          top: `${scriptPortY(scriptItem().node, "input", port.name) - 9}px`,
                          color: nodeTone().text,
                        }}
                      >
                        {scriptPortLabel(port)}
                      </div>
                    )}
                  </For>
                  <For each={scriptItem().node.outputs}>
                    {(port) => (
                      <div
                        data-blueprint-script-port-label="output"
                        class="pointer-events-none absolute right-4 z-10 h-[18px] max-w-[calc(50%_-_28px)] truncate text-right text-10-medium leading-[18px]"
                        style={{
                          top: `${scriptPortY(scriptItem().node, "output", port.name) - 9}px`,
                          color: nodeTone().subtitle,
                        }}
                      >
                        {scriptPortLabel(port)}
                      </div>
                    )}
                  </For>
                </Show>
                <button
                  type="button"
                  data-blueprint-script-collapse-toggle
                  class="absolute bottom-0 left-1/2 z-20 grid size-4 -translate-x-1/2 translate-y-1/2 place-items-center rounded-full border border-[rgba(186,230,253,0.74)] bg-[#071019] text-[#bae6fd] shadow-[0_4px_12px_rgba(0,0,0,0.3)] hover:bg-[#0f2434]"
                  title={language.t((scriptItem().node.collapsed === false ? "blueprint.script.collapse" : "blueprint.script.expand") as never)}
                  aria-label={language.t((scriptItem().node.collapsed === false ? "blueprint.script.collapse" : "blueprint.script.expand") as never)}
                  aria-expanded={scriptItem().node.collapsed === false}
                  onPointerDown={(event: PointerEvent) => {
                    event.preventDefault()
                    event.stopPropagation()
                  }}
                  onClick={(event: MouseEvent) => {
                    event.preventDefault()
                    event.stopPropagation()
                    props.onScriptCollapsedChange(scriptItem().node.collapsed === false)
                  }}
                >
                  <Icon
                    size="small"
                    name="chevron-down"
                    class={scriptItem().node.collapsed === false ? "rotate-180" : ""}
                  />
                </button>
              </>
            )}
          </Show>
          <Show when={props.item.type === "agent" && agentPanelProgress() > 0}>
            <div class="pointer-events-none absolute right-2 top-2 size-5 rounded-full bg-[#071019]/80 shadow-[0_0_12px_rgba(103,232,249,0.28)]">
              <svg class="size-full -rotate-90" viewBox="0 0 20 20" aria-hidden="true">
                <circle
                  cx="10"
                  cy="10"
                  r={AGENT_PANEL_PROGRESS_RADIUS}
                  fill="none"
                  stroke="rgba(103,232,249,0.2)"
                  stroke-width="2"
                />
                <circle
                  cx="10"
                  cy="10"
                  r={AGENT_PANEL_PROGRESS_RADIUS}
                  fill="none"
                  stroke="#67e8f9"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-dasharray={`${AGENT_PANEL_PROGRESS_CIRCUMFERENCE}`}
                  stroke-dashoffset={`${AGENT_PANEL_PROGRESS_CIRCUMFERENCE * (1 - agentPanelProgress())}`}
                />
              </svg>
            </div>
          </Show>
        </div>
      </ContextMenu.Trigger>
      <ContextMenu.Portal>
        <ContextMenu.Content>
          <Show when={props.item.type === "agent"}>
            <ContextMenu.Item onSelect={props.onInfoPanel}>
              <Icon size="small" name="eye" />
              <ContextMenu.ItemLabel>{language.t("blueprint.context.infoPanel")}</ContextMenu.ItemLabel>
            </ContextMenu.Item>
          </Show>
          <ContextMenu.Item onSelect={props.onEdit}>
            <Icon size="small" name="edit" />
            <ContextMenu.ItemLabel>{language.t("blueprint.context.edit")}</ContextMenu.ItemLabel>
          </ContextMenu.Item>
          <ContextMenu.Item onSelect={props.onDelete} class="text-text-on-critical-base hover:bg-surface-critical-weak">
            <Icon size="small" name="trash" />
            <ContextMenu.ItemLabel>{language.t("common.delete")}</ContextMenu.ItemLabel>
          </ContextMenu.Item>
        </ContextMenu.Content>
      </ContextMenu.Portal>
    </ContextMenu>
  )
}

function PortButton(props: {
  nodeId: string
  side: "input" | "output"
  portName: string
  title: string
  shape: "circle" | "triangle"
  top?: number
  onPointerDown?: (event: PointerEvent) => void
  onPointerUp?: (event: PointerEvent) => void
}) {
  return (
    <button
      type="button"
      title={props.title}
      data-blueprint-port={props.side}
      data-blueprint-node-id={props.nodeId}
      data-blueprint-port-name={props.portName}
      data-blueprint-port-shape={props.shape}
      class="absolute z-10 grid size-4 -translate-y-1/2 place-items-center bg-transparent"
      classList={{
        "-left-2 cursor-crosshair": props.side === "input",
        "-right-2 cursor-crosshair": props.side === "output",
      }}
      style={{ top: props.top === undefined ? "50%" : `${props.top}px` }}
      onPointerDown={props.onPointerDown}
      onPointerUp={props.onPointerUp}
    >
      <span
        class="block"
        classList={{
          "h-0 w-0 border-y-[4px] border-r-[7px] border-y-transparent border-r-[#facc15] drop-shadow-[0_0_5px_rgba(250,204,21,0.58)]":
            props.shape === "triangle" && props.side === "input",
          "h-0 w-0 border-y-[4px] border-l-[7px] border-y-transparent border-l-[#7dd3fc] drop-shadow-[0_0_5px_rgba(103,232,249,0.46)]":
            props.shape === "triangle" && props.side === "output",
          "h-2.5 w-2.5 rounded-full border border-[#facc15] bg-[#facc15] shadow-[0_0_6px_rgba(250,204,21,0.48)]":
            props.shape === "circle" && props.side === "input",
          "h-2.5 w-2.5 rounded-full border border-[#7dd3fc] bg-[#7dd3fc] shadow-[0_0_6px_rgba(103,232,249,0.42)]":
            props.shape === "circle" && props.side === "output",
        }}
      />
    </button>
  )
}

export function BlueprintInspector(props: {
  draft: BlueprintDraft
  selectedAgent?: BlueprintAgentNode
  selectedRoute?: BlueprintRouteNode
  selectedCommon?: BlueprintCommonNode
  selectedScript?: BlueprintScriptNode
  selectedTerminal?: BlueprintTerminalKind
  selectedNodeId?: string
  selectedEdge?: BlueprintEdge
  closeInspector: () => void
  setDraft: (draft: BlueprintDraft) => void
  setStore: SetStoreFunction<BlueprintDraft>
  config: BlueprintConfig
  catalog: CatalogState
  modelCatalog: ModelCatalogState
  refreshModelCatalog: (cliKind: string) => Promise<void>
  compileBlueprintScripts: () => Promise<void>
  scriptCompiling: boolean
}) {
  const language = useLanguage()

  const updateAgentField = <K extends keyof BlueprintAgentNode>(field: K, value: BlueprintAgentNode[K]) => {
    const id = props.selectedNodeId
    if (!id || !props.selectedAgent) return
    props.setStore("graph", "agent_nodes", id, field, value as never)
  }

  const updateAgentAccessPolicy = (field: keyof BlueprintAgentNode["access_policy"], value: boolean) => {
    if (!props.selectedAgent) return
    updateAgentField("access_policy", {
      ...props.selectedAgent.access_policy,
      [field]: value,
    })
  }

  const updateAgentCliKind = (value: string) => {
    const cliKind = value as BlueprintCliKind
    const model = props.modelCatalog.cliKind === cliKind && props.modelCatalog.models.length
      ? props.modelCatalog.models[0]
      : defaultModelForCliKind(cliKind)
    updateAgentField("cli_kind", cliKind)
    updateAgentField("command", defaultCommandForCliKind(cliKind))
    updateAgentField("model", model)
    void props.refreshModelCatalog(cliKind)
  }

  const updateAgentSkills = (skills: string[]) => {
    updateAgentField("skills", skills)
    updateAgentField(
      "skill_selection",
      skills.length
        ? {
            mode: "selected",
            skill_hashes: skills,
          }
        : { mode: "none" },
    )
  }

  const updateRouteField = <K extends keyof BlueprintRouteNode>(field: K, value: BlueprintRouteNode[K]) => {
    const id = props.selectedNodeId
    if (!id || !props.selectedRoute) return
    props.setStore("graph", "route_nodes", id, field, value as never)
  }

  const updateCommonField = (field: string, value: unknown) => {
    const id = props.selectedNodeId
    if (!id || !props.selectedCommon) return
    props.setStore("graph", "common_nodes", id, field as never, value as never)
  }

  const updateSelectedEdge = (edge: BlueprintEdge, patch: Partial<BlueprintEdge>) => {
    const from = patch.from ?? edge.from
    const to = patch.to ?? edge.to
    const outputPort = patch.output_port ?? edge.output_port ?? DEFAULT_OUTPUT_PORT
    const inputPort = patch.input_port ?? edge.input_port ?? DEFAULT_INPUT_PORT
    const result = canConnectPorts(props.draft, from, outputPort, to, inputPort)
    if (!result.ok) {
      showToast({
        variant: "error",
        title: language.t("blueprint.connection.invalid" as never),
        description:
          result.reason === "type_mismatch"
            ? language.t("blueprint.connection.typeMismatch" as never, {
                source: result.sourceType ?? "?",
                target: result.targetType ?? "?",
              } as never)
            : language.t("blueprint.connection.unknownPort" as never),
      })
      return
    }
    props.setDraft(updateEdge(props.draft, edge.id, patch))
  }

  const updateScriptField = <K extends keyof BlueprintScriptNode>(field: K, value: BlueprintScriptNode[K]) => {
    const id = props.selectedNodeId
    if (!id || !props.selectedScript) return
    props.setDraft(updateScriptNode(props.draft, id, { [field]: value } as Partial<BlueprintScriptNode>))
  }

  const updateTerminal = (kind: BlueprintTerminalKind) => {
    const id = props.selectedNodeId
    if (!id || !props.selectedTerminal) return
    props.setStore("graph", "terminal_nodes", id, kind)
  }

  return (
    <div class="size-full min-h-0 flex flex-col bg-[#071019] text-[#d6e9f5]">
      <div class="h-10 shrink-0 flex items-center justify-between border-b border-[rgba(103,232,249,0.14)] bg-[#0b1522] px-3">
        <div class="min-w-0 truncate text-12-medium text-[#f8fdff]">{language.t("blueprint.inspector.title")}</div>
        <IconButton
          icon="close-small"
          variant="ghost"
          class="h-6 w-6 text-[#f8fdff]"
          onClick={props.closeInspector}
          aria-label={language.t("common.close")}
        />
      </div>
      <div class="flex-1 min-h-0 overflow-y-auto p-3">
        <Switch>
          <Match when={props.selectedAgent && props.selectedNodeId}>
            <div class="flex flex-col gap-3">
              <InspectorIdentity tip="nodeId" label={language.t("blueprint.field.nodeId")} value={props.selectedNodeId ?? ""} />
              <InspectorTextField
                tip="agentId"
                label={language.t("blueprint.field.agentId")}
                value={props.selectedAgent?.agent_id ?? ""}
                onChange={(value) => updateAgentField("agent_id", value || undefined)}
              />
              <InspectorTextField
                tip="prompt"
                label={language.t("blueprint.field.prompt")}
                value={props.selectedAgent?.prompt ?? ""}
                multiline
                onChange={(value) => updateAgentField("prompt", value)}
              />
              <InspectorTextField
                tip="runPrompt"
                label={language.t("blueprint.field.runPrompt")}
                value={props.selectedAgent?.run_prompt ?? ""}
                multiline
                onChange={(value) => updateAgentField("run_prompt", value)}
              />
              <SelectField
                tip="executionMode"
                label={language.t("blueprint.field.executionMode")}
                value={props.selectedAgent?.execution_mode ?? "blocking"}
                options={[
                  ["blocking", language.t("blueprint.execution.blocking")],
                  ["nonblocking", language.t("blueprint.execution.nonblocking")],
                ]}
                onChange={(value) => updateAgentField("execution_mode", value as BlueprintAgentNode["execution_mode"])}
              />
              <SelectField
                tip="cliKind"
                label={language.t("blueprint.field.cliKind")}
                value={props.selectedAgent?.cli_kind ?? "codemaker"}
                options={CLI_KIND_OPTIONS.map((kind) => [kind, kind])}
                onChange={updateAgentCliKind}
              />
              <SelectField
                tip="model"
                label={language.t("blueprint.field.model")}
                value={props.selectedAgent?.model ?? ""}
                options={modelOptions(props.modelCatalog, props.selectedAgent?.model)}
                status={
                  props.modelCatalog.cliKind === (props.selectedAgent?.cli_kind ?? "codemaker") && props.modelCatalog.loading
                    ? language.t("blueprint.model.loading")
                    : props.modelCatalog.cliKind === (props.selectedAgent?.cli_kind ?? "codemaker") && props.modelCatalog.error
                      ? language.t("blueprint.model.loadFailed")
                      : undefined
                }
                onFocus={() => void props.refreshModelCatalog(props.selectedAgent?.cli_kind ?? "codemaker")}
                onChange={(value) => updateAgentField("model", value)}
              />
              <div class="grid grid-cols-2 gap-2">
                <InspectorTextField
                  tip="timeoutSec"
                  label={language.t("blueprint.field.timeoutSec")}
                  type="number"
                  value={String(props.selectedAgent?.timeout_sec ?? 1800)}
                  onChange={(value) => updateAgentField("timeout_sec", Number(value) || 0)}
                />
                <SelectField
                  tip="promptViaFile"
                  label={language.t("blueprint.field.promptViaFile")}
                  value={props.selectedAgent?.prompt_via_file ?? "auto"}
                  options={[
                    ["auto", "auto"],
                    ["always", "always"],
                    ["never", "never"],
                  ]}
                  onChange={(value) => updateAgentField("prompt_via_file", value as BlueprintAgentNode["prompt_via_file"])}
                />
              </div>
              <CheckboxField
                tip="external"
                label={language.t("blueprint.field.external")}
                checked={!!props.selectedAgent?.external}
                onChange={(checked) => updateAgentField("external", checked)}
              />
              <Show when={props.selectedAgent?.node_type === "agent"}>
                <div class="flex flex-col gap-2 border-t border-[rgba(103,232,249,0.14)] pt-3">
                  <CheckboxField
                    tip="directProjectIo"
                    label={language.t("blueprint.field.directProjectIo" as never)}
                    checked={props.selectedAgent?.access_policy.direct_project_io !== false}
                    onChange={(checked) => updateAgentAccessPolicy("direct_project_io", checked)}
                  />
                  <CheckboxField
                    tip="outsideProjectIo"
                    label={language.t("blueprint.field.outsideProjectIo" as never)}
                    checked={props.selectedAgent?.access_policy.outside_project_io !== false}
                    onChange={(checked) => updateAgentAccessPolicy("outside_project_io", checked)}
                  />
                  <CheckboxField
                    tip="unrestrictedCommands"
                    label={language.t("blueprint.field.unrestrictedCommands" as never)}
                    checked={props.selectedAgent?.access_policy.unrestricted_commands !== false}
                    onChange={(checked) => updateAgentAccessPolicy("unrestricted_commands", checked)}
                  />
                  <CheckboxField
                    tip="disableSandbox"
                    label={language.t("blueprint.field.disableSandbox" as never)}
                    checked={props.selectedAgent?.access_policy.disable_sandbox !== false}
                    onChange={(checked) => updateAgentAccessPolicy("disable_sandbox", checked)}
                  />
                  <CheckboxField
                    tip="frameworkMessageTools"
                    label={language.t("blueprint.field.frameworkMessageTools" as never)}
                    checked={props.selectedAgent?.access_policy.framework_message_tools !== false}
                    onChange={(checked) => updateAgentAccessPolicy("framework_message_tools", checked)}
                  />
                </div>
              </Show>
              <MultiSelectField
                tip="skills"
                label={language.t("blueprint.field.skills")}
                values={props.selectedAgent?.skills ?? []}
                options={props.catalog.skills}
                emptyLabel={props.catalog.skillError ? language.t("blueprint.catalog.loadFailed") : language.t("blueprint.catalog.empty")}
                onChange={updateAgentSkills}
              />
              <MultiSelectField
                tip="rulePaths"
                label={language.t("blueprint.field.rulePaths")}
                values={props.selectedAgent?.rule_paths ?? []}
                options={props.catalog.rules}
                emptyLabel={props.catalog.ruleError ? language.t("blueprint.catalog.loadFailed") : language.t("blueprint.catalog.empty")}
                onChange={(value) => updateAgentField("rule_paths", value)}
              />
              <JsonObjectTextField
                tip="adapterOptions"
                label={language.t("blueprint.field.adapterOptions")}
                value={() => props.selectedAgent?.adapter_options ?? {}}
                onValue={(value) => updateAgentField("adapter_options", value)}
              />
              <JsonObjectTextField
                tip="extraEnv"
                label={language.t("blueprint.field.extraEnv")}
                value={() => props.selectedAgent?.extra_env ?? {}}
                stringValues
                onValue={(value) => updateAgentField("extra_env", value as Record<string, string>)}
              />
            </div>
          </Match>

          <Match when={props.selectedRoute && props.selectedNodeId}>
            <div class="flex flex-col gap-3">
              <InspectorIdentity tip="nodeId" label={language.t("blueprint.field.nodeId")} value={props.selectedNodeId ?? ""} />
              <SelectField
                tip="routeKind"
                label={language.t("blueprint.field.routeKind")}
                value={props.selectedRoute?.route_kind ?? "sequence"}
                options={[
                  ["sequence", language.t("blueprint.route.sequence")],
                  ["parallel", language.t("blueprint.route.parallel")],
                  ["parallel_reduce", language.t("blueprint.route.parallelReduce")],
                ]}
                onChange={(value) => updateRouteField("route_kind", value as BlueprintRouteNode["route_kind"])}
              />
              <InspectorTextField
                tip="targets"
                label={language.t("blueprint.field.targets")}
                value={scopeText(props.selectedRoute?.targets ?? [])}
                multiline
                onChange={(value) => updateRouteField("targets", parseScopeText(value))}
              />
              <InspectorTextField
                tip="reduceTarget"
                label={language.t("blueprint.field.reduceTarget")}
                value={props.selectedRoute?.reduce_target ?? ""}
                onChange={(value) => updateRouteField("reduce_target", value || undefined)}
              />
              <InspectorTextField
                tip="reducePrompt"
                label={language.t("blueprint.field.reducePrompt")}
                value={props.selectedRoute?.reduce_prompt ?? ""}
                multiline
                onChange={(value) => updateRouteField("reduce_prompt", value || undefined)}
              />
            </div>
          </Match>

          <Match when={props.selectedCommon && props.selectedNodeId}>
            <div class="flex flex-col gap-3">
              <InspectorIdentity tip="nodeId" label={language.t("blueprint.field.nodeId")} value={props.selectedNodeId ?? ""} />
              <ReadonlyInspectorField
                label={language.t("blueprint.field.commonKind" as never)}
                value={
                  props.selectedCommon?.kind === "tick"
                    ? language.t("blueprint.node.tick" as never)
                    : language.t("blueprint.node.branch" as never)
                }
              />
              <Show when={props.selectedCommon?.kind === "tick"}>
                <InspectorTextField
                  tip="everyNSeconds"
                  label={language.t("blueprint.field.everyNSeconds" as never)}
                  type="number"
                  value={String(props.selectedCommon?.kind === "tick" ? props.selectedCommon.every_n_seconds : 1)}
                  onChange={(value) => {
                    const next = Math.max(1, Math.floor(Number(value) || 1))
                    updateCommonField("every_n_seconds" as never, next as never)
                  }}
                />
              </Show>
            </div>
          </Match>

          <Match when={props.selectedScript && props.selectedNodeId}>
            <div class="flex flex-col gap-3">
              <InspectorIdentity tip="nodeId" label={language.t("blueprint.field.nodeId")} value={props.selectedNodeId ?? ""} />
              <ReadonlyInspectorField label={language.t("blueprint.field.scriptSignature" as never)} value={scriptSignature(props.selectedScript!)} />
              <ReadonlyInspectorField
                label={language.t("blueprint.field.scriptSource" as never)}
                value={`${props.selectedScript?.module_path ?? ""}:${props.selectedScript?.function_name ?? ""}`}
              />
              <ReadonlyInspectorField label={language.t("blueprint.field.scriptDir" as never)} value={props.catalog.scriptDir || ".multi_agent_workspace/scripts"} />
              <Show when={props.selectedScript?.description}>
                {(description) => (
                  <ReadonlyInspectorField label={language.t("blueprint.field.scriptDescription" as never)} value={description()} multiline />
                )}
              </Show>
              <ScriptPortsInspector
                label={language.t("blueprint.field.scriptInputs" as never)}
                ports={props.selectedScript?.inputs ?? []}
                emptyLabel={language.t("blueprint.catalog.empty")}
              />
              <ScriptPortsInspector
                label={language.t("blueprint.field.scriptOutputs" as never)}
                ports={props.selectedScript?.outputs ?? []}
                emptyLabel={language.t("blueprint.catalog.empty")}
              />
              <CheckboxField
                label={language.t("blueprint.field.collapsed" as never)}
                checked={props.selectedScript?.collapsed !== false}
                onChange={(checked) => updateScriptField("collapsed", checked)}
              />
              <Button
                size="small"
                variant="ghost"
                icon="reset"
                disabled={props.scriptCompiling}
                onClick={() => void props.compileBlueprintScripts()}
              >
                {language.t((props.scriptCompiling ? "blueprint.script.compiling" : "blueprint.script.compile") as never)}
              </Button>
            </div>
          </Match>

          <Match when={props.selectedEdge}>
            {(edge) => (
              <div class="flex flex-col gap-3">
                <InspectorIdentity
                  tip="edge"
                  label={language.t("blueprint.field.edge")}
                  value={`${edge().from}:${edge().output_port ?? DEFAULT_OUTPUT_PORT} -> ${edge().to}:${
                    edge().input_port ?? DEFAULT_INPUT_PORT
                  }`}
                />
                <InspectorTextField
                  tip="edgeType"
                  label={language.t("blueprint.field.edgeType")}
                  value={edge().edge_type}
                  onChange={(value) => updateSelectedEdge(edge(), { edge_type: value })}
                />
                <InspectorTextField
                  tip="outputPort"
                  label={language.t("blueprint.field.outputPort")}
                  value={edge().output_port ?? DEFAULT_OUTPUT_PORT}
                  onChange={(value) => updateSelectedEdge(edge(), { output_port: value })}
                />
                <InspectorTextField
                  tip="inputPort"
                  label={language.t("blueprint.field.inputPort")}
                  value={edge().input_port ?? DEFAULT_INPUT_PORT}
                  onChange={(value) => updateSelectedEdge(edge(), { input_port: value })}
                />
                <Button size="small" variant="ghost" icon="trash" onClick={() => props.setDraft(deleteEdge(props.draft, edge().id))}>
                  {language.t("common.delete")}
                </Button>
              </div>
            )}
          </Match>

          <Match when={props.selectedTerminal && props.selectedNodeId}>
            <div class="flex flex-col gap-3">
              <InspectorIdentity tip="nodeId" label={language.t("blueprint.field.nodeId")} value={props.selectedNodeId ?? ""} />
              <SelectField
                tip="terminalKind"
                label={language.t("blueprint.field.terminalKind")}
                value={props.selectedTerminal ?? "start"}
                options={[
                  ["start", language.t("blueprint.node.start")],
                  ["end", language.t("blueprint.node.end")],
                ]}
                onChange={(value) => updateTerminal(value as BlueprintTerminalKind)}
              />
            </div>
          </Match>
        </Switch>
      </div>
    </div>
  )
}

function BlueprintGlobalConfigPanel(props: {
  config: BlueprintConfig
  onConfigChange: <K extends keyof BlueprintConfig>(field: K, value: BlueprintConfig[K]) => void
  onProjectWorkdirBrowse: () => void
  locked?: boolean
  skillCount: number
  ruleCount: number
  skillError?: string
  ruleError?: string
  invalidFields: BlueprintConfigField[]
  detectingPython: boolean
  pythonDetectFailed: boolean
  onDetectPython: () => void | Promise<void>
}) {
  const language = useLanguage()
  const platform = usePlatform()
  const invalid = (field: BlueprintConfigField) => props.invalidFields.includes(field)

  const pickDirectory = async (field: keyof BlueprintConfig, title: string, defaultPath?: string) => {
    if (props.locked) return
    const result = await platform.openDirectoryPickerDialog?.({
      title,
      multiple: false,
      defaultPath,
    })
    if (typeof result === "string" && result.trim()) props.onConfigChange(field, result)
  }

  const pickFile = async (field: keyof BlueprintConfig, title: string, defaultPath?: string) => {
    if (props.locked) return
    const result = await platform.openFilePickerDialog?.({
      title,
      multiple: false,
      defaultPath,
      extensions: platform.os === "windows" ? ["exe"] : undefined,
    })
    if (typeof result === "string" && result.trim()) props.onConfigChange(field, result)
  }

  return (
    <div
      data-blueprint-global-config
      class="absolute left-0 top-8 z-40 max-h-[270px] w-[360px] max-w-[calc(100vw-1rem)] overflow-y-auto rounded-md border border-[rgba(103,232,249,0.22)] bg-[rgba(7,16,25,0.94)] p-3 text-[#d6e9f5] shadow-[0_18px_48px_rgba(0,0,0,0.34)] backdrop-blur"
      style={BLUEPRINT_INSPECTOR_THEME}
    >
      <div class="flex flex-col gap-2">
        <DirectoryConfigField
          label={language.t("blueprint.field.pythonPath")}
          tip="pythonPath"
          value={props.config.python_path}
          note={
            props.detectingPython
              ? language.t("blueprint.python.detecting")
              : props.pythonDetectFailed
                ? language.t("blueprint.python.detectFailed")
                : undefined
          }
          invalid={invalid("python_path")}
          disabled={props.locked}
          onChange={(value) => props.onConfigChange("python_path", value)}
          onBrowse={() => void pickFile("python_path", language.t("blueprint.directory.pickPython"), props.config.python_path)}
          onDetect={() => void props.onDetectPython()}
          detectLabel={language.t("blueprint.python.detect")}
          detectText={language.t("blueprint.python.detectShort")}
          detecting={props.detectingPython}
        />
        <DirectoryConfigField
          label={language.t("blueprint.field.projectWorkdir")}
          tip="projectWorkdir"
          value={props.config.project_workdir}
          invalid={invalid("project_workdir")}
          readOnly
          disabled={props.locked}
          onBrowse={props.onProjectWorkdirBrowse}
        />
        <DirectoryConfigField
          label={language.t("blueprint.field.skillDir")}
          tip="skillDir"
          value={props.config.skill_dir}
          note={props.skillError ? language.t("blueprint.catalog.loadFailed") : language.t("blueprint.catalog.count", { count: props.skillCount })}
          invalid={invalid("skill_dir")}
          disabled={props.locked}
          onChange={(value) => props.onConfigChange("skill_dir", value)}
          onBrowse={() => void pickDirectory("skill_dir", language.t("blueprint.directory.pickSkill"), props.config.skill_dir)}
        />
        <DirectoryConfigField
          label={language.t("blueprint.field.ruleDir")}
          tip="ruleDir"
          value={props.config.rule_dir}
          note={props.ruleError ? language.t("blueprint.catalog.loadFailed") : language.t("blueprint.catalog.count", { count: props.ruleCount })}
          invalid={invalid("rule_dir")}
          disabled={props.locked}
          onChange={(value) => props.onConfigChange("rule_dir", value)}
          onBrowse={() => void pickDirectory("rule_dir", language.t("blueprint.directory.pickRule"), props.config.rule_dir)}
        />
      </div>
    </div>
  )
}

function BlueprintConfigRequiredDialog(props: { issues: BlueprintConfigValidationIssue[] }) {
  const language = useLanguage()
  const dialog = useDialog()
  const label = (field: BlueprintConfigValidationIssue["field"]) => blueprintConfigFieldLabel(language.t, field)
  const message = (issue: BlueprintConfigValidationIssue) =>
    language.t(
      issue.reason === "missing" ? "blueprint.configRequired.issue.missing" : "blueprint.configRequired.issue.absolute",
      { field: label(issue.field) },
    )

  return (
    <Dialog title={language.t("blueprint.configRequired.title")} action={<span aria-hidden="true" />} fit>
      <div class="flex w-[420px] max-w-[calc(100vw-2rem)] flex-col gap-4 px-6 pb-4">
        <div class="text-14-regular leading-6 text-text-base">{language.t("blueprint.configRequired.description")}</div>
        <div class="flex flex-col gap-2 rounded-md border border-border-weaker-base bg-background-stronger p-3">
          <For each={props.issues}>
            {(issue) => <div class="text-13-regular leading-5 text-text-strong">{message(issue)}</div>}
          </For>
        </div>
        <div class="flex justify-end">
          <Button variant="primary" size="large" onClick={() => dialog.close()}>
            {language.t("blueprint.configRequired.ok")}
          </Button>
        </div>
      </div>
    </Dialog>
  )
}

function BlueprintProjectWorkdirConfirmDialog(props: {
  currentProjectWorkdir: string
  onConfirm: (targetProjectWorkdir: string) => void | Promise<void>
}) {
  const language = useLanguage()
  const platform = usePlatform()
  const dialog = useDialog()
  const [value, setValue] = createSignal(props.currentProjectWorkdir)

  const browse = async () => {
    const result = await platform.openDirectoryPickerDialog?.({
      title: language.t("blueprint.directory.pickProject"),
      multiple: false,
      defaultPath: value(),
    })
    if (typeof result === "string" && result.trim()) setValue(result)
  }

  const confirm = () => {
    const target = value().trim()
    if (!target) return
    dialog.close()
    void props.onConfirm(target)
  }

  return (
    <Dialog title={language.t("blueprint.projectWorkdir.confirmTitle" as never)} action={<span aria-hidden="true" />} fit>
      <div
        data-blueprint-project-workdir-dialog
        class="flex w-[460px] max-w-[calc(100vw-2rem)] flex-col gap-4 px-6 pb-4"
      >
        <div class="text-14-regular leading-6 text-text-base">
          {language.t("blueprint.projectWorkdir.confirmDescription" as never)}
        </div>
        <div class="flex min-w-0 items-stretch gap-2">
          <textarea
            class="h-11 min-w-0 flex-1 resize-none rounded-md border border-border-weaker-base bg-background-stronger px-2 py-1 font-mono text-11-regular leading-4 text-text-strong opacity-80 outline-none"
            value={value()}
            title={value()}
            readOnly
            aria-label={language.t("blueprint.field.projectWorkdir")}
            spellcheck={false}
            wrap="soft"
          />
          <IconButton
            icon="folder"
            variant="secondary"
            size="normal"
            iconSize="small"
            class="h-11 w-11 shrink-0"
            onClick={() => void browse()}
            aria-label={language.t("blueprint.directory.pickProject")}
          />
        </div>
        <div class="flex justify-end gap-2">
          <Button variant="ghost" size="large" onClick={() => dialog.close()}>
            {language.t("common.cancel")}
          </Button>
          <Button variant="primary" size="large" onClick={confirm}>
            {language.t("blueprint.projectWorkdir.confirmAction" as never)}
          </Button>
        </div>
      </div>
    </Dialog>
  )
}

function BlueprintProjectWorkdirConflictDialog(props: {
  targetProjectDir: string
  onResolve: (policy: BlueprintRelocateConflictPolicy) => void | Promise<void>
}) {
  const language = useLanguage()
  const dialog = useDialog()
  const resolve = (policy: BlueprintRelocateConflictPolicy) => {
    dialog.close()
    void props.onResolve(policy)
  }

  return (
    <Dialog title={language.t("blueprint.projectWorkdir.conflictTitle" as never)} action={<span aria-hidden="true" />} fit>
      <div
        data-blueprint-project-workdir-conflict-dialog
        class="flex w-[480px] max-w-[calc(100vw-2rem)] flex-col gap-4 px-6 pb-4"
      >
        <div class="text-14-regular leading-6 text-text-base">
          {language.t("blueprint.projectWorkdir.conflictDescription" as never, { path: props.targetProjectDir })}
        </div>
        <div class="rounded-md border border-border-weaker-base bg-background-stronger p-3 font-mono text-11-regular leading-5 text-text-strong">
          {props.targetProjectDir}
        </div>
        <div class="flex flex-wrap justify-end gap-2">
          <Button variant="ghost" size="large" onClick={() => dialog.close()}>
            {language.t("common.cancel")}
          </Button>
          <Button variant="secondary" size="large" onClick={() => resolve("load_existing")}>
            {language.t("blueprint.projectWorkdir.loadExisting" as never)}
          </Button>
          <Button variant="primary" size="large" onClick={() => resolve("overwrite")}>
            {language.t("blueprint.projectWorkdir.overwrite" as never)}
          </Button>
        </div>
      </div>
    </Dialog>
  )
}

function DirectoryConfigField(props: {
  label: string
  tip?: InspectorTipKey
  value: string
  note?: string
  invalid?: boolean
  readOnly?: boolean
  disabled?: boolean
  onChange?: (value: string) => void
  onBrowse?: () => void
  onDetect?: () => void
  detectLabel?: string
  detectText?: string
  detecting?: boolean
}) {
  const language = useLanguage()
  const sideButtonClass =
    "!h-11 !w-10 rounded-md border border-[rgba(103,232,249,0.24)] !bg-[#0d1826] !text-[#d7f7ff] shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] hover:!bg-[rgba(56,214,244,0.12)] disabled:opacity-50 [&_[data-slot=icon-svg]]:!text-[#d7f7ff]"
  const detectButtonClass =
    "!h-11 shrink-0 rounded-md border border-[rgba(103,232,249,0.24)] !bg-[#0d1826] !px-2 !text-[#d7f7ff] shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] hover:!bg-[rgba(56,214,244,0.12)] disabled:opacity-50 [&_[data-slot=icon-svg]]:!text-[#d7f7ff]"

  return (
    <div class="flex min-w-0 flex-col gap-1">
      <InspectorFieldHeader label={props.label} tip={props.tip} placement="right-start" />
      <div class="flex min-w-0 items-stretch gap-2">
        <textarea
          class={`h-11 min-w-0 flex-1 resize-none rounded-md border bg-[#06101a] px-2 py-1 font-mono text-[10.5px] leading-4 text-[#f8fdff] outline-none transition-colors placeholder:text-[#95afc4] disabled:cursor-not-allowed disabled:opacity-60 ${
            props.invalid ? "border-[#fb7185] focus:border-[#fb7185]" : "border-[rgba(103,232,249,0.22)] focus:border-[#67e8f9]"
          } ${props.readOnly ? "cursor-default opacity-70" : ""}`}
          value={props.value}
          title={props.value}
          placeholder={language.t("blueprint.globalConfig.unset")}
          aria-label={props.label}
          spellcheck={false}
          wrap="soft"
          readOnly={props.readOnly}
          disabled={props.disabled}
          onKeyDown={(event) => {
            if (event.key === "Enter") event.preventDefault()
          }}
          onInput={(event) => {
            if (props.readOnly || props.disabled) return
            props.onChange?.(event.currentTarget.value.replace(/\r?\n/g, ""))
          }}
        />
        <Show when={props.onDetect && props.detectLabel}>
          <Tooltip placement="top" value={props.detecting ? language.t("blueprint.python.detecting") : (props.detectLabel ?? "")}>
            <Button
              icon="magnifying-glass"
              variant="secondary"
              size="small"
              class={detectButtonClass}
              disabled={props.detecting || props.disabled}
              onClick={() => props.onDetect?.()}
              aria-label={props.detectLabel ?? ""}
              data-blueprint-detect-python
            >
              {props.detectText ?? props.detectLabel}
            </Button>
          </Tooltip>
        </Show>
        <IconButton
          icon="folder"
          variant="secondary"
          size="normal"
          iconSize="small"
          class={sideButtonClass}
          disabled={props.disabled || !props.onBrowse}
          onClick={() => props.onBrowse?.()}
          aria-label={props.label}
        />
      </div>
      <Show when={props.note}>
        {(note) => <span class="truncate text-10-regular text-[#95afc4]">{note()}</span>}
      </Show>
    </div>
  )
}

function blueprintConfigFieldLabel(
  t: (key: never, params?: Record<string, string | number | boolean>) => string,
  field: BlueprintConfigValidationIssue["field"],
) {
  if (field === "python_path") return t("blueprint.field.pythonPath" as never)
  if (field === "skill_dir") return t("blueprint.field.skillDir" as never)
  if (field === "rule_dir") return t("blueprint.field.ruleDir" as never)
  return t("blueprint.field.projectWorkdir" as never)
}

function InspectorIdentity(props: { label: string; value: string; tip?: InspectorTipKey }) {
  return (
    <div class="rounded-md border border-[rgba(103,232,249,0.22)] bg-[#0d1826] px-3 py-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_12px_28px_rgba(0,0,0,0.18)]">
      <InspectorFieldHeader label={props.label} tip={props.tip} />
      <div class="mt-0.5 truncate text-13-medium text-[#f8fdff]">{props.value}</div>
    </div>
  )
}

function ReadonlyInspectorField(props: { label: string; value: string; multiline?: boolean }) {
  return (
    <div class="rounded-md border border-[rgba(103,232,249,0.14)] bg-[#06101a] px-3 py-2">
      <InspectorFieldHeader label={props.label} />
      <div
        class={props.multiline ? "mt-1 whitespace-pre-wrap break-words text-12-regular text-[#d6e9f5]" : "mt-1 truncate font-mono text-11-regular text-[#95afc4]"}
        title={props.value}
      >
        {props.value}
      </div>
    </div>
  )
}

function ScriptPortsInspector(props: { label: string; ports: BlueprintScriptPort[]; emptyLabel: string }) {
  return (
    <div class="rounded-md border border-[rgba(103,232,249,0.14)] bg-[#06101a] px-3 py-2">
      <InspectorFieldHeader label={props.label} />
      <Show
        when={props.ports.length > 0}
        fallback={<div class="mt-1 text-11-regular text-[#95afc4]">{props.emptyLabel}</div>}
      >
        <div class="mt-2 flex flex-col gap-1">
          <For each={props.ports}>
            {(port) => (
              <div class="flex min-w-0 items-center justify-between gap-2 text-11-regular">
                <span class="min-w-0 truncate text-[#f8fdff]">{port.name}</span>
                <span class="shrink-0 rounded-sm bg-[rgba(103,232,249,0.12)] px-1.5 py-0.5 font-mono text-[#95afc4]">
                  {port.type}
                </span>
              </div>
            )}
          </For>
        </div>
      </Show>
    </div>
  )
}

function InspectorTextField(props: TextFieldProps & { tip?: InspectorTipKey }) {
  const [local, rest] = splitProps(props, ["label", "tip"])
  const fieldClass = () =>
    `text-13-regular !text-[#f8fdff] placeholder:!text-[#95afc4] ${rest.class ?? ""}`.trim()
  const fieldStyle = () => ({
    color: "#f8fdff",
    "-webkit-text-fill-color": "#f8fdff",
    "caret-color": "#67e8f9",
    ...(typeof rest.style === "object" ? rest.style : {}),
  })

  return (
    <InspectorFieldHeadered label={local.label ?? ""} tip={local.tip}>
      <TextField {...rest} class={fieldClass()} style={fieldStyle()} hideLabel label={local.label} />
    </InspectorFieldHeadered>
  )
}

function SelectField(props: {
  label: string
  tip?: InspectorTipKey
  value: string
  options: Array<[string, string]>
  status?: string
  onFocus?: () => void
  onChange: (value: string) => void
}) {
  return (
    <label class="flex flex-col gap-1">
      <InspectorFieldHeader label={props.label} tip={props.tip} />
      <select
        class="h-8 rounded-md border border-[rgba(103,232,249,0.22)] bg-[#06101a] px-2 text-12-regular text-[#f8fdff] outline-none transition-colors focus:border-[#67e8f9]"
        value={props.value}
        style={{ color: "#f8fdff", "background-color": "#06101a" }}
        onFocus={() => props.onFocus?.()}
        onChange={(event) => props.onChange(event.currentTarget.value)}
      >
        <For each={props.options}>
          {([value, label]) => (
            <option value={value} style={{ color: "#f8fdff", "background-color": "#0b1522" }}>
              {label}
            </option>
          )}
        </For>
      </select>
      <Show when={props.status}>
        {(status) => <span class="text-10-regular text-[#95afc4]">{status()}</span>}
      </Show>
    </label>
  )
}

function MultiSelectField(props: {
  label: string
  tip?: InspectorTipKey
  values: string[]
  options: BlueprintCatalogItem[]
  emptyLabel: string
  onChange: (values: string[]) => void
}) {
  const selected = () => new Set(props.values)
  const options = () => {
    const byValue = new Map(props.options.map((option) => [option.value, option]))
    for (const value of props.values) {
      if (!byValue.has(value)) byValue.set(value, { value, label: value })
    }
    return Array.from(byValue.values())
  }
  const label = () => {
    if (props.values.length === 0) return props.emptyLabel
    const byValue = new Map(options().map((option) => [option.value, option.label]))
    return props.values.map((value) => byValue.get(value) ?? value).join(", ")
  }
  const toggle = (value: string) => {
    const next = selected()
    if (next.has(value)) next.delete(value)
    else next.add(value)
    props.onChange(Array.from(next))
  }

  return (
    <div class="flex flex-col gap-1">
      <InspectorFieldHeader label={props.label} tip={props.tip} />
      <DropdownMenu placement="bottom-start">
        <DropdownMenu.Trigger class="flex h-8 min-w-0 items-center justify-between gap-2 rounded-md border border-[rgba(103,232,249,0.22)] bg-[#06101a] px-2 text-left text-12-regular text-[#f8fdff] outline-none transition-colors hover:border-[rgba(103,232,249,0.34)] focus:border-[#67e8f9]">
          <span class="min-w-0 truncate">{label()}</span>
          <Icon name="chevron-down" size="small" class="shrink-0 text-[#d7f7ff]" />
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            class="max-h-64 w-72 overflow-y-auto border-[rgba(103,232,249,0.26)] bg-[#101a28] text-[#f8fdff] shadow-[0_18px_48px_rgba(0,0,0,0.42)] [&_[data-slot=dropdown-menu-checkbox-item]]:items-start"
            style={BLUEPRINT_THEME}
          >
            <Show
              when={options().length > 0}
              fallback={<div class="px-2 py-2 text-12-regular text-[#95afc4]">{props.emptyLabel}</div>}
            >
              <For each={options()}>
                {(option) => (
                  <DropdownMenu.CheckboxItem
                    checked={selected().has(option.value)}
                    onChange={() => toggle(option.value)}
                    class="gap-2"
                  >
                    <DropdownMenu.ItemIndicator>
                      <Icon name="check-small" size="small" class="mt-0.5 text-[#67e8f9]" />
                    </DropdownMenu.ItemIndicator>
                    <div class="min-w-0">
                      <DropdownMenu.ItemLabel class="truncate text-12-medium">{option.label}</DropdownMenu.ItemLabel>
                      <Show when={option.description}>
                        {(description) => (
                          <DropdownMenu.ItemDescription class="line-clamp-2 text-11-regular text-[#95afc4]">
                            {description()}
                          </DropdownMenu.ItemDescription>
                        )}
                      </Show>
                    </div>
                  </DropdownMenu.CheckboxItem>
                )}
              </For>
            </Show>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu>
    </div>
  )
}

function CheckboxField(props: {
  label: string
  tip?: InspectorTipKey
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <div class="flex items-center justify-between gap-2 rounded-md border border-[rgba(103,232,249,0.22)] bg-[#06101a] px-2 py-1.5 text-12-medium text-[#f8fdff]">
      <label class="flex min-w-0 items-center gap-2">
        <input
          type="checkbox"
          class="size-4 accent-[#67e8f9]"
          checked={props.checked}
          onChange={(event) => props.onChange(event.currentTarget.checked)}
        />
        <span class="min-w-0 truncate">{props.label}</span>
      </label>
      <Show when={props.tip}>
        {(tip) => <InspectorTipButton label={props.label} tip={tip()} />}
      </Show>
    </div>
  )
}

function JsonObjectTextField(props: {
  label: string
  tip?: InspectorTipKey
  value: () => unknown
  stringValues?: boolean
  onValue: (value: Record<string, unknown> | Record<string, string>) => void
}) {
  const [text, setText] = createSignal(jsonText(props.value()))
  const [error, setError] = createSignal<string>()

  createEffect(() => {
    if (!error()) setText(jsonText(props.value()))
  })

  return (
    <InspectorFieldHeadered label={props.label} tip={props.tip}>
      <TextField
        class="text-13-regular !text-[#f8fdff] placeholder:!text-[#95afc4]"
        style={{
          color: "#f8fdff",
          "-webkit-text-fill-color": "#f8fdff",
          "caret-color": "#67e8f9",
        }}
        hideLabel
        label={props.label}
        value={text()}
        multiline
        validationState={error() ? "invalid" : "valid"}
        error={error()}
        onChange={(value) => {
          setText(value)
          try {
            const parsed = props.stringValues ? parseStringRecord(value) : parseJsonObject(value)
            setError(undefined)
            props.onValue(parsed)
          } catch (err) {
            setError(err instanceof Error ? err.message : "Invalid JSON object")
          }
        }}
      />
    </InspectorFieldHeadered>
  )
}

function InspectorFieldHeadered(props: { label: string; tip?: InspectorTipKey; children: JSX.Element }) {
  return (
    <div class="flex flex-col gap-1">
      <InspectorFieldHeader label={props.label} tip={props.tip} />
      {props.children}
    </div>
  )
}

function InspectorFieldHeader(props: { label: string; tip?: InspectorTipKey; placement?: "left-start" | "right-start" }) {
  return (
    <div class="flex min-w-0 items-center gap-1 text-12-medium text-[#f8fdff]">
      <span class="min-w-0 truncate">{props.label}</span>
      <Show when={props.tip}>
        {(tip) => <InspectorTipButton label={props.label} tip={tip()} placement={props.placement} />}
      </Show>
    </div>
  )
}

function InspectorTipButton(props: { label: string; tip: InspectorTipKey; placement?: "left-start" | "right-start" }) {
  const language = useLanguage()
  const [open, setOpen] = createSignal(false)
  const copy = () => INSPECTOR_TIPS[props.tip]

  return (
    <Popover
      open={open()}
      onOpenChange={setOpen}
      triggerAs={IconButton}
      triggerProps={{
        icon: "help",
        variant: "ghost",
        size: "small",
        class: "h-4 w-4 text-[#d7f7ff] hover:text-[#67e8f9]",
        "aria-label": language.t("blueprint.tip.open", { field: props.label }),
        type: "button",
      }}
      title={props.label}
      class="w-64 border-[rgba(103,232,249,0.26)] bg-[#101a28] shadow-[0_18px_48px_rgba(0,0,0,0.42)] [&_[data-slot=popover-body]]:pt-2"
      style={BLUEPRINT_THEME}
      placement={props.placement ?? "left-start"}
      gutter={8}
    >
      <div class="space-y-2">
        <div>
          <div class="text-11-medium text-[var(--blueprint-edge-active)]">{language.t("blueprint.tip.what")}</div>
          <div class="mt-0.5 text-12-regular leading-5 text-text-base">{language.t(copy().what as never)}</div>
        </div>
        <div>
          <div class="text-11-medium text-[var(--blueprint-edge-active)]">{language.t("blueprint.tip.usage")}</div>
          <div class="mt-0.5 text-12-regular leading-5 text-text-base">{language.t(copy().usage as never)}</div>
        </div>
      </div>
    </Popover>
  )
}

function nodeTitle(t: (key: never, params?: Record<string, string | number | boolean>) => string, item: NodeItem) {
  if (item.type === "terminal") return item.kind === "start" ? t("blueprint.node.start" as never) : t("blueprint.node.end" as never)
  if (item.type === "common") return item.node.kind === "tick" ? t("blueprint.node.tick" as never) : t("blueprint.node.branch" as never)
  if (item.type === "script") return item.node.title || item.node.function_name || t("blueprint.node.script" as never)
  return item.id
}

function nodeSubtitle(t: (key: never, params?: Record<string, string | number | boolean>) => string, item: NodeItem) {
  if (item.type === "agent") {
    const prefix = item.node.node_type === "agent" ? t("blueprint.node.agent" as never) : t("blueprint.node.workerAgent" as never)
    return `${prefix} · ${item.node.agent_id || item.node.cli_kind}`
  }
  if (item.type === "route") return t(`blueprint.route.${routeLabelKey(item.node.route_kind)}` as never)
  if (item.type === "common") {
    if (item.node.kind === "tick") return t("blueprint.common.tickSubtitle" as never, { n: item.node.every_n_seconds } as never)
    return t("blueprint.common.branchSubtitle" as never)
  }
  if (item.type === "script") return scriptNodeDescription(t, item.node)
  return t("blueprint.node.terminal" as never)
}

function routeLabelKey(routeKind: string) {
  if (routeKind === "parallel_reduce") return "parallelReduce"
  return routeKind
}

function addNodeIcon(kind: BlueprintAddNodeKind): "blueprint" | "branch" | "selector" {
  if (kind === "agent" || kind === "worker-agent" || kind === "test-agent" || kind === "script") return "blueprint"
  if (kind === "start" || kind === "end") return "selector"
  return "branch"
}

function scriptSignature(node: Pick<BlueprintScriptNode, "function_name" | "title" | "inputs" | "outputs">) {
  const name = node.function_name || node.title || "function"
  const inputs = node.inputs.map((port) => port.type || "Any").join(", ")
  const output =
    node.outputs.length === 1
      ? node.outputs[0].type || "Any"
      : `{${node.outputs.map((port) => `${port.name}: ${port.type || "Any"}`).join(", ")}}`
  return `${name}(${inputs}) -> ${output || "Any"}`
}

function scriptNodeDescription(
  t: (key: never, params?: Record<string, string | number | boolean>) => string,
  node: Pick<BlueprintScriptNode, "description">,
) {
  return node.description?.trim() || t("blueprint.script.noDescription" as never)
}

function scriptPortLabel(port: BlueprintScriptPort) {
  return `${port.name}: ${port.type || "Any"}`
}

function nodeItemSize(item: NodeItem) {
  if (item.type === "terminal") return { width: TERMINAL_WIDTH, height: TERMINAL_HEIGHT }
  if (item.type === "script") return scriptNodeSize(item.node)
  if (item.type === "common") return commonNodeSize(item.node)
  return { width: NODE_WIDTH, height: NODE_HEIGHT }
}

function scriptNodeSize(node: BlueprintScriptNode) {
  if (node.collapsed !== false) return { width: NODE_WIDTH, height: NODE_HEIGHT }
  const rows = Math.max(node.inputs.length, node.outputs.length, 1)
  return {
    width: SCRIPT_NODE_WIDTH,
    height: Math.max(SCRIPT_NODE_MIN_EXPANDED_HEIGHT, SCRIPT_NODE_HEADER_HEIGHT + rows * SCRIPT_NODE_PORT_ROW_HEIGHT + 14),
  }
}

function nodePorts(item: NodeItem, side: "input" | "output") {
  if (item.type === "common") return commonNodePorts(item.node, side)
  if (item.type !== "script" || item.node.collapsed !== false) {
    const name = side === "input" ? DEFAULT_INPUT_PORT : DEFAULT_OUTPUT_PORT
    return [{ name, title: side === "input" ? "Input" : "Output", top: undefined as number | undefined }]
  }
  const ports = side === "input" ? item.node.inputs : item.node.outputs
  return (ports.length ? ports : [{ name: side === "input" ? DEFAULT_INPUT_PORT : DEFAULT_OUTPUT_PORT, type: "Any" }]).map((port) => ({
    name: port.name,
    title: scriptPortLabel(port),
    top: scriptPortY(item.node, side, port.name),
  }))
}

function commonNodePorts(node: BlueprintCommonNode, side: "input" | "output") {
  const size = commonNodeSize(node)
  if (node.kind === "branch") {
    if (side === "input") return [{ name: "condition", title: "condition: bool", top: size.height * 0.56 }]
    return [
      { name: "true", title: "true: message", top: size.height * 0.4 },
      { name: "false", title: "false: message", top: size.height * 0.72 },
    ]
  }
  if (side === "input") return []
  return [{ name: "tick", title: "tick: tick", top: NODE_HEIGHT / 2 }]
}

function commonNodeSize(node: Pick<BlueprintCommonNode, "kind">) {
  return node.kind === "branch"
    ? { width: COMMON_BRANCH_WIDTH, height: COMMON_BRANCH_HEIGHT }
    : { width: NODE_WIDTH, height: NODE_HEIGHT }
}

function scriptPortY(node: BlueprintScriptNode, side: "input" | "output", portName?: string) {
  if (node.collapsed !== false) return scriptNodeSize(node).height / 2
  const ports = side === "input" ? node.inputs : node.outputs
  const fallback = side === "input" ? DEFAULT_INPUT_PORT : DEFAULT_OUTPUT_PORT
  const index = Math.max(
    0,
    ports.findIndex((port) => port.name === (portName || fallback)),
  )
  return SCRIPT_NODE_HEADER_HEIGHT + index * SCRIPT_NODE_PORT_ROW_HEIGHT + SCRIPT_NODE_PORT_ROW_HEIGHT / 2
}

function fallbackModels(cliKind: string) {
  return MODEL_LIST_FALLBACKS[cliKind] ?? MODEL_LIST_FALLBACKS.codemaker
}

function slugBlueprintId(name: string) {
  const slug = name
    .trim()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^[._-]+|[._-]+$/g, "")
    .slice(0, 64)
  return slug || "blueprint"
}

function uniqueBlueprintId(name: string, existingIds: string[]) {
  const base = slugBlueprintId(name)
  const used = new Set(existingIds.map((id) => id.toLowerCase()))
  if (!used.has(base.toLowerCase())) return base
  for (let index = 2; index < 10_000; index += 1) {
    const candidate = `${base}-${index}`
    if (!used.has(candidate.toLowerCase())) return candidate
  }
  return `${base}-${Date.now()}`
}

function modelOptions(modelCatalog: ModelCatalogState, currentModel?: string): Array<[string, string]> {
  const values = new Set(modelCatalog.models.length ? modelCatalog.models : fallbackModels(modelCatalog.cliKind || "codemaker"))
  if (currentModel) values.add(currentModel)
  return Array.from(values).map((model) => [model, model])
}

function readableError(error: unknown) {
  if (error instanceof Error) return error.message
  return String(error)
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined
}

function recordEntries(value: Record<string, unknown> | undefined): Array<[string, Record<string, unknown>]> {
  return Object.entries(value ?? {}).map(([key, entry]) => [key, asRecord(entry) ?? { value: entry }])
}

function arrayOfRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map((entry) => asRecord(entry) ?? { value: entry }) : []
}

function validationErrors(value: Record<string, unknown> | undefined): string[] {
  const errors = value?.errors
  return Array.isArray(errors) ? errors.map((item) => String(item).trim()).filter(Boolean) : []
}

function normalizeBlueprintPlanningSubmitResult(value: BlueprintPlanningSubmitResult): {
  accepted: boolean
  requestId?: string
  status?: string
  message?: string
} {
  if (typeof value === "boolean") return { accepted: value }
  const record = asRecord(value)
  return {
    accepted: record?.accepted !== false,
    requestId: stringValue(record?.requestId),
    status: stringValue(record?.status),
    message: stringValue(record?.message),
  }
}

function isBlueprintPlanningRequestActive(status: string | undefined) {
  const normalized = (status ?? "").trim().toLowerCase()
  return normalized === "pending" || normalized === "claimed"
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined
}

function numberValue(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return value
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value)
  return 0
}

function normalizeScriptCatalogNodeFromJson(text: string): BlueprintScriptCatalogNode | undefined {
  try {
    return normalizeScriptCatalogNode(JSON.parse(text))
  } catch {
    return undefined
  }
}

function normalizeScriptCatalogNode(value: unknown): BlueprintScriptCatalogNode | undefined {
  const record = asRecord(value)
  if (!record) return
  const modulePath = stringValue(record.module_path) ?? stringValue(record.modulePath) ?? ""
  const functionName = stringValue(record.function_name) ?? stringValue(record.functionName) ?? ""
  if (!modulePath || !functionName) return
  const title = stringValue(record.title) ?? stringValue(record.name) ?? functionName
  const inputs = arrayOfRecords(record.inputs).map((entry, index) => normalizeScriptCatalogPort(entry, `arg${index + 1}`))
  const outputs = arrayOfRecords(record.outputs).map((entry, index) => normalizeScriptCatalogPort(entry, index === 0 ? "result" : `out${index + 1}`))
  return {
    node_id: stringValue(record.node_id) ?? stringValue(record.nodeId) ?? functionName,
    script_id: stringValue(record.script_id) ?? stringValue(record.scriptId) ?? `${modulePath}:${functionName}`,
    module_path: modulePath.replace(/\\/g, "/"),
    function_name: functionName,
    title,
    description: stringValue(record.description) ?? "",
    inputs,
    outputs: outputs.length ? outputs : [{ name: "result", type: "Any", required: true }],
    collapsed: record.collapsed !== false,
  }
}

function normalizeScriptCatalogPort(value: Record<string, unknown>, fallbackName: string): BlueprintScriptPort {
  return {
    name: stringValue(value.name) ?? fallbackName,
    type: stringValue(value.type) ?? "Any",
    required: value.required !== false,
  }
}

function blueprintDiffSummaryCount(summary: Record<string, unknown> | undefined, key: string) {
  return numberValue(summary?.[key])
}

function normalizeBlueprintRunDiff(value: unknown): Omit<BlueprintDiffState, "loading" | "error" | "detailLoading" | "details"> {
  const record = asRecord(value)
  return {
    summary: asRecord(record?.summary) ?? {},
    changesets: arrayOfRecords(record?.changesets).map(normalizeBlueprintDiffChangeset),
    acceptedDiffs: arrayOfRecords(record?.acceptedDiffs).map(normalizeBlueprintDiffFile).filter((item) => item.patch),
    binaryFiles: arrayOfRecords(record?.binaryFiles),
  }
}

function normalizeBlueprintChangesetDetail(value: unknown): BlueprintChangesetDiffDetail {
  const record = asRecord(value)
  const metadata = asRecord(record?.metadata) ?? {}
  const changesetId =
    stringValue(record?.changesetId) ??
    stringValue(record?.changeset_id) ??
    stringValue(metadata.changesetId) ??
    stringValue(metadata.changeset_id) ??
    "changeset"
  return {
    changesetId,
    status: stringValue(record?.status) ?? stringValue(metadata.status) ?? "pending",
    diffs: arrayOfRecords(record?.diffs).map(normalizeBlueprintDiffFile).filter((item) => item.patch),
    binaryFiles: arrayOfRecords(record?.binaryFiles),
    metadata,
  }
}

function normalizeBlueprintDiffChangeset(value: Record<string, unknown>): BlueprintDiffChangeset {
  const changesetId = stringValue(value.changesetId) ?? stringValue(value.changeset_id) ?? "changeset"
  return {
    changesetId,
    status: stringValue(value.status) ?? "pending",
    agentId: stringValue(value.agentId) ?? stringValue(value.agent_id),
    taskId: stringValue(value.taskId) ?? stringValue(value.task_id),
    summary: stringValue(value.summary),
    fileCount: numberValue(value.fileCount),
    textFileCount: numberValue(value.textFileCount),
    binaryFileCount: numberValue(value.binaryFileCount),
    additions: numberValue(value.additions),
    deletions: numberValue(value.deletions),
    patchExists: value.patchExists !== false,
    reversible: value.reversible === true,
    restorable: value.restorable === true,
    rollbackable: value.rollbackable === true,
    rollbackId: stringValue(value.rollbackId) ?? stringValue(value.rollback_id),
    rolledBackAt: stringValue(value.rolledBackAt) ?? stringValue(value.rolled_back_at),
    rollbackDisabledReason: stringValue(value.rollbackDisabledReason) ?? stringValue(value.rollback_disabled_reason),
  }
}

function normalizeBlueprintDiffFile(value: Record<string, unknown>): BlueprintDiffFile {
  const status = stringValue(value.status)
  return {
    file: stringValue(value.file) ?? stringValue(value.path) ?? "file",
    patch: typeof value.patch === "string" ? value.patch : "",
    additions: numberValue(value.additions),
    deletions: numberValue(value.deletions),
    status: status === "added" || status === "deleted" || status === "modified" ? status : undefined,
  }
}

function groupBlueprintDiffChangesets(changesets: BlueprintDiffChangeset[]) {
  const groups: Array<{ id: string; agentId?: string; taskId?: string; items: BlueprintDiffChangeset[] }> = []
  const byKey = new Map<string, { id: string; agentId?: string; taskId?: string; items: BlueprintDiffChangeset[] }>()
  for (const changeset of changesets) {
    const key = `${changeset.agentId ?? ""}\u0000${changeset.taskId ?? ""}`
    let group = byKey.get(key)
    if (!group) {
      group = {
        id: key,
        agentId: changeset.agentId,
        taskId: changeset.taskId,
        items: [],
      }
      byKey.set(key, group)
      groups.push(group)
    }
    group.items.push(changeset)
  }
  return groups
}

function blueprintAgentColor(agentId?: string) {
  const input = agentId || "unknown"
  let hash = 0
  for (const ch of input) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  const hue = hash % 360
  return `hsl(${hue} 72% 58%)`
}

function blueprintDiffStatusClass(status: string) {
  if (status === "accepted") return "bg-[#064e3b] text-[#bbf7d0]"
  if (status === "rolled_back") return "bg-[#334155] text-[#cbd5e1]"
  if (status === "conflict") return "bg-[#7f1d1d] text-[#fecaca]"
  if (status === "rejected" || status === "failed") return "bg-[#3f1d1d] text-[#fca5a5]"
  return "bg-[#1e3a8a] text-[#bfdbfe]"
}

function blueprintDiffStatusLabel(t: (key: never) => string, status: string) {
  if (status === "accepted") return t("blueprint.diff.status.accepted" as never)
  if (status === "rolled_back") return t("blueprint.diff.status.rolledBack" as never)
  if (status === "conflict") return t("blueprint.diff.status.conflict" as never)
  if (status === "rejected") return t("blueprint.diff.status.rejected" as never)
  if (status === "failed") return t("blueprint.diff.status.failed" as never)
  return t("blueprint.diff.status.pending" as never)
}

function blueprintPatchLineClass(line: string, tone: "diff" | "neutral" = "diff") {
  if (tone === "neutral") return "text-[#cbd5e1]"
  if (line.startsWith("+++") || line.startsWith("---")) return "text-[#93c5fd]"
  if (line.startsWith("+")) return "bg-[#052e1c] text-[#86efac]"
  if (line.startsWith("-")) return "bg-[#3f1111] text-[#fca5a5]"
  if (line.startsWith("@@")) return "text-[#67e8f9]"
  return "text-[#cbd5e1]"
}

function createDesktopBlueprintSnapshot(
  projectDirectory: string,
  blueprintId: string,
  blueprintName: string,
  draft: BlueprintDraft,
  runtimeAgents?: Record<string, unknown>,
): DesktopBlueprintSnapshotPayload {
  const visibleIds = new Set([
    ...Object.keys(draft.graph.agent_nodes),
    ...Object.keys(draft.graph.script_nodes ?? {}),
    ...Object.keys(draft.graph.common_nodes ?? {}),
  ])
  const upstream = new Map<string, string[]>()
  const downstream = new Map<string, string[]>()
  const edges = draft.graph.edges
    .filter((edge) => visibleIds.has(edge.from) && visibleIds.has(edge.to))
    .map((edge) => {
      upstream.set(edge.to, [...(upstream.get(edge.to) ?? []), edge.from])
      downstream.set(edge.from, [...(downstream.get(edge.from) ?? []), edge.to])
      return {
        source: edge.from,
        target: edge.to,
        kind: desktopSnapshotEdgeKind(edge.edge_type),
        outputPort: edge.output_port,
        inputPort: edge.input_port,
      }
    })

  return {
    projectDir: projectDirectory,
    blueprintId,
    title: blueprintName,
    description: "Desktop blueprint structure snapshot.",
    nodes: [
      ...Object.entries(draft.graph.agent_nodes).map(([id, node]) => {
        const runtime = asRecord(runtimeAgents?.[id])
        const layout = draft.layout.nodes[id]
        return {
          id,
          label: node.agent_id?.trim() || id,
          kind: node.node_type,
          role: node.node_type === "agent" ? "Agent" : "Worker Agent",
          summary: node.prompt?.trim() || node.run_prompt?.trim() || undefined,
          state: desktopSnapshotNodeState(stringValue(runtime?.state)),
          x: layout?.x,
          y: layout?.y,
          upstreamNodeIds: upstream.get(id) ?? [],
          downstreamNodeIds: downstream.get(id) ?? [],
          inputPorts: [DEFAULT_INPUT_PORT],
          outputPorts: [DEFAULT_OUTPUT_PORT],
          agentId: node.agent_id?.trim() || id,
          cliKind: node.cli_kind || undefined,
          taskStatus: stringValue(runtime?.task_status),
          queueSize: numberValue(runtime?.queue_size),
          messagesSent: numberValue(runtime?.messages_sent),
          busyCount: numberValue(runtime?.busy_count),
          updatedAt: stringValue(runtime?.updated_at),
        }
      }),
      ...Object.entries(draft.graph.script_nodes ?? {}).map(([id, node]) => {
        const layout = draft.layout.nodes[id]
        return {
          id,
          label: node.title?.trim() || node.function_name || id,
          kind: "script" as const,
          role: "Script Function",
          summary: node.description?.trim() || scriptSignature(node),
          state: "idle" as const,
          x: layout?.x,
          y: layout?.y,
          upstreamNodeIds: upstream.get(id) ?? [],
          downstreamNodeIds: downstream.get(id) ?? [],
          inputPorts: node.inputs.length ? node.inputs.map(scriptPortLabel) : [DEFAULT_INPUT_PORT],
          outputPorts: node.outputs.length ? node.outputs.map(scriptPortLabel) : [DEFAULT_OUTPUT_PORT],
        }
      }),
      ...Object.entries(draft.graph.common_nodes ?? {}).map(([id, node]) => {
        const layout = draft.layout.nodes[id]
        return {
          id,
          label: node.kind === "branch" ? "Branch" : "Tick",
          kind: node.kind,
          role: "Common Node",
          summary:
            node.kind === "branch"
              ? "Routes a bool condition to true or false message outputs."
              : `Emits a tick every ${node.every_n_seconds} second(s).`,
          state: "idle" as const,
          x: layout?.x,
          y: layout?.y,
          upstreamNodeIds: upstream.get(id) ?? [],
          downstreamNodeIds: downstream.get(id) ?? [],
          inputPorts: commonNodePorts(node, "input").map((port) => port.title),
          outputPorts: commonNodePorts(node, "output").map((port) => port.title),
          everyNSeconds: node.kind === "tick" ? node.every_n_seconds : undefined,
        }
      }),
    ],
    edges,
  }
}

function desktopSnapshotNodeState(value?: string): DesktopBlueprintSnapshotPayload["nodes"][number]["state"] {
  const state = (value ?? "").toLowerCase()
  if (state === "completed" || state === "done" || state === "succeeded") return "completed"
  if (RUNTIME_WORKING_AGENT_STATES.has(state) || state === "active") return "running"
  if (state === "queued" || state === "pending") return "queued"
  if (state === "failed" || state === "error") return "failed"
  if (state === "unknown") return "unknown"
  return "idle"
}

function desktopSnapshotEdgeKind(value?: string): "exec" | "data" | "unknown" {
  const kind = (value ?? "").toLowerCase()
  if (kind === "exec" || kind === "data") return kind
  return "unknown"
}

function workspaceAreaTitle(t: (key: never) => string, area: WorkspacePanelArea) {
  if (area === "changesets") return t("blueprint.runtime.changes" as never)
  if (area === "artifacts") return t("blueprint.runtime.artifacts" as never)
  return t("blueprint.runtime.reports" as never)
}

function workspaceAreaItems(workspace: Record<string, unknown> | undefined, area: WorkspacePanelArea): WorkspacePanelItem[] {
  return arrayOfRecords(workspace?.[area]).map((item, index) => {
    const path = stringValue(item.path) ?? stringValue(item.changeset_id)
    const absolutePath = stringValue(item.absolute_path) ?? stringValue(item.absolutePath)
    const name = stringValue(item.name) ?? stringValue(item.changeset_id) ?? basename(path) ?? `${area}-${index + 1}`
    const files = Array.isArray(item.files) ? item.files.map((file) => String(file)).filter(Boolean) : []
    return {
      name,
      path,
      absolutePath,
      detail: files.length > 0 ? files.join(", ") : path,
    }
  })
}

function workspaceAreaDirectory(workspace: Record<string, unknown> | undefined, area: WorkspacePanelArea) {
  const directories = asRecord(workspace?.directories)
  const direct = stringValue(directories?.[area])
  if (direct) return direct
  const sharedRoot = stringValue(workspace?.shared_root)
  if (sharedRoot && area !== "changesets") return joinLocalPath(sharedRoot, area === "artifacts" ? "artifacts" : "reports")
  const workspaceRoot = stringValue(workspace?.workspace_root)
  if (workspaceRoot && area === "changesets") return joinLocalPath(workspaceRoot, "changesets")
  return undefined
}

function basename(path: string | undefined) {
  if (!path) return undefined
  const normalized = path.replace(/[\\/]+$/, "")
  const index = Math.max(normalized.lastIndexOf("\\"), normalized.lastIndexOf("/"))
  return index >= 0 ? normalized.slice(index + 1) : normalized
}

function parentDirectory(path: string) {
  const normalized = path.replace(/[\\/]+$/, "")
  const index = Math.max(normalized.lastIndexOf("\\"), normalized.lastIndexOf("/"))
  return index > 0 ? normalized.slice(0, index) : normalized
}

function joinLocalPath(base: string, child: string) {
  const separator = base.includes("\\") ? "\\" : "/"
  return `${base.replace(/[\\/]+$/, "")}${separator}${child.replace(/^[\\/]+/, "")}`
}

function isTerminalUserMessageStatus(status: AgentPanelUserMessage["status"] | undefined) {
  return status === "succeeded" || status === "failed"
}

function runtimeMessageIdFromQueueResponse(response: Record<string, unknown>) {
  return stringValue(asRecord(response.result)?.message_id)
}

function mergeRuntimeRunsWithStatus(
  runs: Record<string, unknown>[],
  response: Record<string, unknown>,
): Record<string, unknown>[] {
  const responseRun = asRecord(response.run)
  const statusRun = asRecord(asRecord(response.status)?.run)
  const runId = stringValue(response.runId) ?? stringValue(responseRun?.runId)
  if (!runId) return runs
  const existing = runs.find((run) => stringValue(run.runId) === runId)
  const merged: Record<string, unknown> = {
    ...(existing ?? {}),
    ...(responseRun ?? {}),
    runId,
  }
  const status = stringValue(statusRun?.status)
  if (status) merged.status = status
  if (statusRun?.final_status !== undefined) merged.finalStatus = statusRun.final_status
  if (statusRun?.ended_at !== undefined) merged.endedAt = statusRun.ended_at
  const rest = runs.filter((run) => stringValue(run.runId) !== runId)
  return [merged, ...rest]
}

function runtimeNodeVisualState(states: Record<string, RuntimeNodeVisualState>, nodeId: string): RuntimeNodeVisualState {
  return states[nodeId] ?? "idle"
}

function runtimeNodeBoxShadow(state: RuntimeNodeVisualState) {
  if (state === "working") {
    return "0 14px 36px rgba(0, 0, 0, 0.28), 0 0 34px rgba(34, 197, 94, 0.36), 0 0 0 1px rgba(187, 247, 208, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.08)"
  }
  if (state === "active") {
    return "0 12px 30px rgba(0, 0, 0, 0.26), 0 0 24px rgba(34, 197, 94, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.07)"
  }
  return "0 10px 28px rgba(0, 0, 0, 0.24), inset 0 1px 0 rgba(255, 255, 255, 0.06)"
}

function runtimeEdgeFlows(status: unknown, edges: BlueprintEdge[]) {
  const queues = asRecord(asRecord(status)?.queues)
  const flowPairs = new Set<string>()
  for (const message of runtimePendingMessages(queues?.pending_messages)) {
    const source = stringValue(message.source_node_id) ?? stringValue(message.sourceNodeId)
    const target = stringValue(message.node_id) ?? stringValue(message.nodeId)
    const messageStatus = stringValue(message.status)
    if (!source || !target || !messageStatus || !RUNTIME_FLOW_MESSAGE_STATUSES.has(messageStatus)) continue
    flowPairs.add(runtimeEdgeFlowKey(source, target))
  }
  return new Set(edges.filter((edge) => flowPairs.has(runtimeEdgeFlowKey(edge.from, edge.to))).map((edge) => edge.id))
}

function runtimePendingMessageEntries(value: unknown): Array<[string, Record<string, unknown>]> {
  return runtimeMessageEntries(value).filter(([, message]) => runtimeMessageIsActive(message))
}

function runtimePendingMessages(value: unknown) {
  return runtimePendingMessageEntries(value).map(([, message]) => message)
}

function runtimeMessageEntries(value: unknown): Array<[string, Record<string, unknown>]> {
  if (Array.isArray(value)) {
    return arrayOfRecords(value).map((message, index) => [stringValue(message.message_id) ?? String(index), message])
  }
  return recordEntries(asRecord(value))
}

function runtimeMessageIsActive(message: Record<string, unknown>) {
  const messageStatus = stringValue(message.status)
  return !!messageStatus && RUNTIME_FLOW_MESSAGE_STATUSES.has(messageStatus)
}

function runtimeEdgeFlowKey(source: string, target: string) {
  return `${source}\u0000${target}`
}

function runtimeStatus(status: unknown) {
  const snapshot = asRecord(status)
  const run = asRecord(snapshot?.run)
  return typeof run?.status === "string" ? run.status : undefined
}

function isTerminalRuntimeStatus(status: string | undefined) {
  return status === "completed" || status === "cancelled" || status === "failed" || status === "paused"
}

function latestAgentStatusEvent(events: AgentStreamEvent[]) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (events[index]?.kind === "status") return events[index]
  }
  return undefined
}

function latestAgentTaskStatusEvent(events: AgentStreamEvent[]) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (events[index]?.kind === "agent.task_status") return events[index]
  }
  return undefined
}

function stabilizeAgentPanelDisplayEvents(previous: AgentPanelDisplayEvent[], next: AgentPanelDisplayEvent[]) {
  if (!previous.length) return next
  const previousById = new Map(previous.map((event) => [event.id, event]))
  let changed = previous.length !== next.length
  const stable = next.map((event) => {
    const current = previousById.get(event.id)
    if (current && agentPanelDisplayEventEquals(current, event)) return current
    changed = true
    return event
  })
  return changed ? stable : previous
}

function agentPanelDisplayEventEquals(left: AgentPanelDisplayEvent, right: AgentPanelDisplayEvent) {
  return (
    left.id === right.id &&
    left.kind === right.kind &&
    left.seq === right.seq &&
    left.status === right.status &&
    left.text === right.text &&
    left.tone === right.tone &&
    left.collapsible === right.collapsible &&
    left.detail === right.detail &&
    left.toolCategory === right.toolCategory &&
    left.order === right.order
  )
}

function visibleAgentPanelEvents(events: AgentStreamEvent[], userMessages: AgentPanelUserMessage[] = []): AgentPanelDisplayEvent[] {
  const replies = new Map<string, AgentPanelDisplayEvent>()
  const reasoning = new Map<string, AgentPanelDisplayEvent>()
  const tools = new Map<string, AgentPanelDisplayEvent>()
  const display: AgentPanelDisplayEvent[] = []
  let currentToolGroup: AgentPanelToolGroup | undefined

  const flushAgentPanelToolGroup = () => {
    if (!currentToolGroup) return
    display.push(agentPanelToolGroupDisplayEvent(currentToolGroup))
    currentToolGroup = undefined
  }

  const appendAgentPanelTool = (key: string, entry: AgentPanelDisplayEvent, order: number) => {
    if (!currentToolGroup) {
      currentToolGroup = {
        id: key,
        order,
        tools: [],
        toolIds: new Set<string>(),
      }
    }
    currentToolGroup.order = Math.min(currentToolGroup.order, order)
    if (currentToolGroup.toolIds.has(key)) return
    currentToolGroup.toolIds.add(key)
    currentToolGroup.tools.push(entry)
  }

  for (const item of agentPanelTimelineItems(events, userMessages)) {
    if (item.type === "user") {
      flushAgentPanelToolGroup()
      display.push({
        id: `user-${item.message.id}`,
        kind: "用户",
        status: userMessageStatusLabel(item.message.status),
        text: item.message.text,
        tone: "user",
        detail: item.message.mode === "top" ? "置顶消息" : undefined,
        order: item.order,
      })
      continue
    }

    const event = item.event
    const kind = stringValue(event.kind) ?? "event"
    const order = item.order
    if (kind === "queue.updated") {
      const status = stringValue(event.status)
      const lastError = stringValue(event.last_error)
      if (lastError || status === "failed" || status === "cancelled") {
        flushAgentPanelToolGroup()
        display.push(
          agentPanelDisplayEventFromStream(event, "Agent error", lastError ?? `message ${status}`, undefined, {
            tone: "error",
            order,
          }),
        )
      }
      continue
    }
    if (isHiddenAgentPanelStreamKind(kind)) continue

    if (kind === "part.delta" || kind === "message.completed") {
      const partType = stringValue(event.part_type)
      if (partType === "reasoning") {
        const reasoningText = cleanAgentPanelReplyText(agentStreamEventContentText(event))
        if (reasoningText) flushAgentPanelToolGroup()
        upsertAgentPanelStreamingEntry({
          map: reasoning,
          display,
          event,
          keyPrefix: "reasoning",
          title: "Agent 思考",
          text: reasoningText,
          tone: "reasoning",
          collapsible: true,
          order,
        })
        continue
      }
      if (!isAgentReplyTextEvent(event, kind)) continue
      const text = cleanAgentPanelReplyText(agentStreamEventContentText(event))
      if (text) flushAgentPanelToolGroup()
      upsertAgentPanelStreamingEntry({
        map: replies,
        display,
        event,
        keyPrefix: "reply",
        title: "Agent 回复",
        text,
        tone: "reply",
        order,
      })
      continue
    }

    if (kind === "tool.started" || kind === "tool.completed") {
      const key = stringValue(event.part_id) ?? stringValue(event.message_id) ?? stringValue(event.event_id) ?? `tool-${event.seq ?? tools.size}`
      const text = agentPanelToolEventText(event)
      const title = `工具调用${agentPanelToolName(event) ? ` · ${agentPanelToolName(event)}` : ""}`
      const toolCategory = agentPanelToolCategory(event)
      const current = tools.get(key)
      if (!current) {
        const entry = agentPanelDisplayEventFromStream(event, title, text, `tool-${key}`, {
          tone: "tool",
          collapsible: true,
          detail: agentPanelToolDetail(event),
          toolCategory,
          order,
        })
        tools.set(key, entry)
        appendAgentPanelTool(key, entry, order)
        continue
      }
      current.kind = title
      current.text = text || current.text
      current.status = stringValue(event.status) ?? current.status
      current.seq = event.seq ?? current.seq
      current.detail = agentPanelToolDetail(event) ?? current.detail
      current.toolCategory = toolCategory
      appendAgentPanelTool(key, current, order)
      continue
    }

    const text = cleanAgentPanelReplyText(agentStreamEventContentText(event))
    if (text) {
      flushAgentPanelToolGroup()
      display.push(
        agentPanelDisplayEventFromStream(event, kind, text, undefined, {
          tone: "event",
          order,
        }),
      )
    }
  }

  flushAgentPanelToolGroup()
  return mergeAdjacentAgentPanelToolGroups(
    display.sort((left, right) => (left.order ?? 0) - (right.order ?? 0) || (left.seq ?? 0) - (right.seq ?? 0)),
  )
}

function agentPanelTimelineItems(events: AgentStreamEvent[], userMessages: AgentPanelUserMessage[]): AgentPanelTimelineItem[] {
  const timeline: AgentPanelTimelineItem[] = [
    ...userMessages.map((message, index) => ({
      type: "user" as const,
      message,
      index,
      order: agentPanelUserMessageOrder(message, index),
    })),
    ...events.map((event, index) => ({
      type: "event" as const,
      event,
      index,
      order: agentPanelStreamEventOrder(event),
    })),
  ]
  return timeline.sort((left, right) => left.order - right.order || left.index - right.index)
}

function mergeAdjacentAgentPanelToolGroups(events: AgentPanelDisplayEvent[]) {
  const merged: AgentPanelDisplayEvent[] = []
  let currentToolGroup: AgentPanelToolGroup | undefined

  const flush = () => {
    if (!currentToolGroup) return
    merged.push(agentPanelToolGroupDisplayEvent(currentToolGroup))
    currentToolGroup = undefined
  }

  for (const event of events) {
    if (event.tone !== "tool") {
      flush()
      merged.push(event)
      continue
    }
    const toolItems = event.toolItems ?? [event]
    for (const item of toolItems) {
      if (!currentToolGroup) {
        currentToolGroup = {
          id: item.id,
          order: item.order ?? event.order ?? 0,
          tools: [],
          toolIds: new Set<string>(),
        }
      }
      const key = item.id
      currentToolGroup.order = Math.min(currentToolGroup.order, item.order ?? event.order ?? currentToolGroup.order)
      if (currentToolGroup.toolIds.has(key)) continue
      currentToolGroup.toolIds.add(key)
      currentToolGroup.tools.push(item)
    }
  }
  flush()
  return merged
}

function agentPanelToolGroupDisplayEvent(group: AgentPanelToolGroup): AgentPanelDisplayEvent {
  const first = group.tools[0]
  if (!first) {
    return {
      id: `tool-group-${group.id}`,
      kind: "工具调用组",
      text: "",
      tone: "tool",
      collapsible: true,
      order: group.order,
      toolCategory: "mixed",
      toolItems: [],
    }
  }
  if (group.tools.length === 1) {
    return {
      ...first,
      id: `tool-group-${group.id}`,
      order: group.order,
      toolItems: [first],
    }
  }
  return {
    id: `tool-group-${group.id}`,
    kind: `工具调用组 · ${group.tools.length} 个工具`,
    seq: group.tools[group.tools.length - 1]?.seq,
    status: agentPanelToolGroupStatus(group.tools),
    text: group.tools.map(agentPanelToolGroupItemText).join("\n\n"),
    tone: "tool",
    collapsible: true,
    detail: agentPanelToolGroupDetail(group.tools),
    toolCategory: agentPanelToolGroupCategory(group.tools),
    order: group.order,
    toolItems: group.tools,
  }
}

function agentPanelToolGroupItemText(tool: AgentPanelDisplayEvent, index: number) {
  const name = tool.kind.replace(/^工具调用\s*·?\s*/, "") || tool.kind
  const status = tool.status ? ` · ${tool.status}` : ""
  const detail = tool.detail ? `\n${tool.detail}` : ""
  const text = tool.text ? `\n${tool.text}` : ""
  return `${index + 1}. ${name}${status}${detail}${text}`
}

function agentPanelToolGroupDetail(tools: AgentPanelDisplayEvent[]) {
  const names = tools.map((tool) => tool.kind.replace(/^工具调用\s*·?\s*/, "")).filter(Boolean)
  return names.length ? names.join(" · ") : undefined
}

function agentPanelToolGroupCategory(tools: AgentPanelDisplayEvent[]): AgentPanelToolCategory {
  const categories = new Set(tools.map((tool) => tool.toolCategory ?? "codex"))
  return categories.size === 1 ? [...categories][0] ?? "codex" : "mixed"
}

function agentPanelToolGroupStatus(tools: AgentPanelDisplayEvent[]) {
  if (tools.some((tool) => tool.status === "failed")) return "failed"
  if (tools.some((tool) => tool.status === "cancelled")) return "cancelled"
  if (tools.length > 0 && tools.every((tool) => tool.status === "completed")) return "completed"
  for (let index = tools.length - 1; index >= 0; index -= 1) {
    if (tools[index]?.status) return tools[index]?.status
  }
  return "running"
}

function isHiddenAgentPanelStreamKind(kind: string) {
  return kind === "status" || kind === "message.started" || kind === "queue.updated"
}

function isAgentReplyTextEvent(event: AgentStreamEvent, kind: string) {
  if (kind === "message.completed") return true
  const partType = stringValue(event.part_type)
  return partType === undefined || partType === "text" || partType === "agent_message"
}

function agentPanelDisplayEventFromStream(
  event: AgentStreamEvent,
  kind: string,
  text: string,
  fallbackId = `event-${event.seq ?? kind}`,
  opts: Partial<AgentPanelDisplayEvent> = {},
): AgentPanelDisplayEvent {
  return {
    id: stringValue(event.event_id) ?? stringValue(event.part_id) ?? stringValue(event.message_id) ?? fallbackId,
    kind,
    seq: event.seq,
    status: stringValue(event.status),
    text,
    ...opts,
  }
}

function upsertAgentPanelStreamingEntry(input: {
  map: Map<string, AgentPanelDisplayEvent>
  display: AgentPanelDisplayEvent[]
  event: AgentStreamEvent
  keyPrefix: string
  title: string
  text: string | undefined
  tone: AgentPanelDisplayEvent["tone"]
  collapsible?: boolean
  order: number
}) {
  const messageId = stringValue(input.event.message_id)
  const partId = stringValue(input.event.part_id)
  const key = messageId ?? partId ?? `${input.keyPrefix}-${input.event.seq ?? input.map.size}`
  const current = input.map.get(key)
  if (!current) {
    if (!input.text) return
    const entry = agentPanelDisplayEventFromStream(input.event, input.title, input.text, `${input.keyPrefix}-${key}`, {
      tone: input.tone,
      collapsible: input.collapsible,
      order: input.order,
    })
    input.map.set(key, entry)
    input.display.push(entry)
    return
  }
  if (input.text) {
    current.text =
      stringValue(input.event.kind) === "message.completed" || shouldReplaceAgentReplyDraft(current.text, input.text)
        ? input.text
        : `${current.text}${input.text}`
  }
  current.status = stringValue(input.event.status) ?? current.status
  current.seq = input.event.seq ?? current.seq
}

function userMessageStatusLabel(status: AgentPanelUserMessage["status"]) {
  if (status === "queued") return "排队中"
  if (status === "sent") return "已发送"
  if (status === "dispatching") return "分发中"
  if (status === "running") return "运行中"
  if (status === "succeeded") return "已完成"
  return "失败"
}

function agentPanelUserMessageOrder(message: AgentPanelUserMessage, index: number) {
  const value = Date.parse(message.created_at || message.sent_at || message.completed_at || message.failed_at || "")
  return Number.isFinite(value) ? value : index
}

function agentPanelStreamEventOrder(event: AgentStreamEvent) {
  const createdAt = event.created_at
  if (typeof createdAt === "number" && Number.isFinite(createdAt)) return createdAt > 10_000_000_000 ? createdAt : createdAt * 1000
  if (typeof createdAt === "string" && createdAt.trim()) {
    const parsed = Date.parse(createdAt)
    if (Number.isFinite(parsed)) return parsed
  }
  return 10_000_000_000_000 + Number(event.seq ?? 0)
}

function agentPanelToolName(event: AgentStreamEvent) {
  return stringValue(event.tool_name) ?? stringValue(event.tool_kind) ?? stringValue(event.part_id)
}

function agentPanelToolCategory(event: AgentStreamEvent): AgentPanelToolCategory {
  const kind = stringValue(event.tool_kind)
  if (kind === "mcp_tool_call") return "mcp"
  if (kind === "command_execution") return "command"
  if (stringValue(event.tool_server)) return "mcp"
  return "codex"
}

function agentPanelToolCategoryLabel(category: AgentPanelToolCategory) {
  if (category === "mcp") return "MCP"
  if (category === "command") return "Shell"
  if (category === "mixed") return "混合"
  return "Codex"
}

function agentPanelToolCategoryTitle(category: AgentPanelToolCategory) {
  if (category === "mcp") return "MCP tool"
  if (category === "command") return "Codex worker shell / command_execution"
  if (category === "mixed") return "Mixed tool types"
  return "Codex built-in tool"
}

function agentPanelToolCategoryBadgeClass(category: AgentPanelToolCategory) {
  const base =
    "rounded border px-1.5 py-0.5 text-[10px] leading-none tracking-normal"
  if (category === "mcp") return `${base} border-[rgba(96,165,250,0.55)] bg-[rgba(37,99,235,0.20)] text-[#93c5fd]`
  if (category === "command") return `${base} border-[rgba(192,132,252,0.58)] bg-[rgba(126,34,206,0.22)] text-[#d8b4fe]`
  return `${base} border-[rgba(34,211,238,0.55)] bg-[rgba(8,145,178,0.22)] text-[#67e8f9]`
}

function agentPanelToolDetail(event: AgentStreamEvent) {
  const values = [stringValue(event.tool_server), stringValue(event.tool_kind)].filter(Boolean)
  return values.length ? values.join(" · ") : undefined
}

function agentPanelToolEventText(event: AgentStreamEvent) {
  const input = agentStreamStructuredText(event["tool_input"])
  const output = agentStreamStructuredText(event["tool_output"])
  const error = agentStreamStructuredText(event["tool_error"])
  const sections: string[] = []
  if (input) sections.push(`输入\n${input}`)
  if (output) sections.push(`输出\n${output}`)
  if (error) sections.push(`错误\n${error}`)
  return sections.join("\n\n") || agentStreamEventText(event)
}

function shouldReplaceAgentReplyDraft(current: string, next: string) {
  return next.length >= current.length && (next.startsWith(current) || current.startsWith(next))
}

function cleanAgentPanelReplyText(value: string | undefined) {
  if (!value) return undefined
  const text = value
    .split(/\r?\n/)
    .filter((line) => !isCodexInternalLogLine(line))
    .join("\n")
    .trim()
  return text || undefined
}

function isCodexInternalLogLine(line: string) {
  const trimmed = line.trim()
  return (
    /^\d{4}-\d{2}-\d{2}T[^\s]+Z\s+(ERROR|WARN|INFO|DEBUG|TRACE)\s+codex_/.test(trimmed) ||
    trimmed.includes("codex_core::") ||
    trimmed.includes("windows sandbox: CreateProcessWithLogonW failed")
  )
}

function agentStatusFieldText(value: unknown) {
  if (typeof value === "string" && value.trim()) return value.trim()
  if (typeof value === "number" && Number.isFinite(value)) return String(value)
  if (typeof value === "boolean") return String(value)
  return undefined
}

function agentStreamEventContentText(event: AgentStreamEvent) {
  const text = event.delta ?? event.text ?? event["tool_output"] ?? event["tool_input"] ?? event.status
  if (typeof text === "string") return text
  if (text !== undefined) return JSON.stringify(text, null, 2)
  return undefined
}

function agentStreamStructuredText(value: unknown) {
  if (typeof value === "string") return value
  if (value !== undefined && value !== null) return JSON.stringify(value, null, 2)
  return undefined
}

function agentStreamEventText(event: AgentStreamEvent) {
  const text = agentStreamEventContentText(event)
  if (text !== undefined) return text
  return JSON.stringify(event["raw"] ?? event, null, 2)
}

function formatAgentStreamEventTime(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) {
    const milliseconds = value > 10_000_000_000 ? value : value * 1000
    return new Date(milliseconds).toLocaleTimeString()
  }
  if (typeof value === "string" && value.trim()) {
    const time = Date.parse(value)
    if (Number.isFinite(time)) return new Date(time).toLocaleTimeString()
    return value
  }
  return undefined
}

function formatRuntimeTime(value: number) {
  return new Date(value).toLocaleTimeString()
}

function edgePath(draft: BlueprintDraft, edge: BlueprintEdge) {
  const source = portPoint(draft, edge.from, "output", edge.output_port ?? DEFAULT_OUTPUT_PORT)
  const target = portPoint(draft, edge.to, "input", edge.input_port ?? DEFAULT_INPUT_PORT)
  if (!source || !target) return ""
  return edgePathBetween(source, target)
}

function edgePathBetween(source: BlueprintNodeLayout, target: BlueprintNodeLayout) {
  const bend = Math.max(64, Math.abs(target.x - source.x) / 2)
  return `M ${source.x} ${source.y} C ${source.x + bend} ${source.y}, ${target.x - bend} ${target.y}, ${target.x} ${target.y}`
}

function edgeGroupGeometry(draft: BlueprintDraft, edges: BlueprintEdge[]) {
  const fallback = {
    hub: undefined as BlueprintNodeLayout | undefined,
    segments: edges.map((edge) => ({ d: edgePath(draft, edge), markerEnd: true })).filter((segment) => segment.d),
  }
  if (edges.length <= 1) return fallback
  const first = edges[0]
  if (!first) return fallback

  const fanOut = !!draft.graph.agent_nodes[first.from] && !!draft.graph.script_nodes?.[first.to]
  const fanIn = !!draft.graph.script_nodes?.[first.from] && !!draft.graph.agent_nodes[first.to]
  if (fanOut) {
    const source = portPoint(draft, first.from, "output", first.output_port ?? DEFAULT_OUTPUT_PORT)
    const targets = edges
      .map((edge) => portPoint(draft, edge.to, "input", edge.input_port ?? DEFAULT_INPUT_PORT))
      .filter((point): point is BlueprintNodeLayout => !!point)
    if (!source || targets.length < 2) return fallback
    const minTargetX = Math.min(...targets.map((point) => point.x))
    const gap = Math.abs(minTargetX - source.x)
    const hub = {
      x: minTargetX >= source.x ? Math.max(source.x + 36, minTargetX - Math.min(72, Math.max(42, gap * 0.34))) : (source.x + minTargetX) / 2,
      y: targets.reduce((sum, point) => sum + point.y, 0) / targets.length,
    }
    return {
      hub,
      segments: [
        { d: edgePathBetween(source, hub), markerEnd: false },
        ...targets.map((target) => ({ d: edgePathBetween(hub, target), markerEnd: true })),
      ],
    }
  }

  if (fanIn) {
    const sources = edges
      .map((edge) => portPoint(draft, edge.from, "output", edge.output_port ?? DEFAULT_OUTPUT_PORT))
      .filter((point): point is BlueprintNodeLayout => !!point)
    const target = portPoint(draft, first.to, "input", first.input_port ?? DEFAULT_INPUT_PORT)
    if (!target || sources.length < 2) return fallback
    const maxSourceX = Math.max(...sources.map((point) => point.x))
    const gap = Math.abs(target.x - maxSourceX)
    const hub = {
      x: target.x >= maxSourceX ? Math.min(target.x - 36, maxSourceX + Math.min(72, Math.max(42, gap * 0.34))) : (target.x + maxSourceX) / 2,
      y: sources.reduce((sum, point) => sum + point.y, 0) / sources.length,
    }
    return {
      hub,
      segments: [
        ...sources.map((source) => ({ d: edgePathBetween(source, hub), markerEnd: false })),
        { d: edgePathBetween(hub, target), markerEnd: true },
      ],
    }
  }

  return fallback
}

function connectionPath(draft: BlueprintDraft, connection: ConnectionState) {
  const source = portPoint(draft, connection.source, "output", connection.output_port)
  const target = connection.pointer
  if (!source || !target) return ""
  const bend = Math.max(64, Math.abs(target.x - source.x) / 2)
  return `M ${source.x} ${source.y} C ${source.x + bend} ${source.y}, ${target.x - bend} ${target.y}, ${target.x} ${target.y}`
}

function portPoint(draft: BlueprintDraft, id: string, side: "input" | "output", portName?: string) {
  const layout = draft.layout.nodes[id]
  if (!layout) return
  const size = nodeSize(draft, id)
  const script = draft.graph.script_nodes?.[id]
  const common = draft.graph.common_nodes?.[id]
  const commonPort = common ? commonNodePorts(common, side).find((port) => port.name === portName) : undefined
  const portTop = script ? scriptPortY(script, side, portName) : (commonPort?.top ?? size.height / 2)
  return {
    x: side === "output" ? layout.x + size.width : layout.x,
    y: layout.y + portTop,
  }
}

function nodeSize(draft: BlueprintDraft, id: string) {
  const script = draft.graph.script_nodes?.[id]
  if (script) return scriptNodeSize(script)
  const common = draft.graph.common_nodes?.[id]
  if (common) return commonNodeSize(common)
  return nodeKind(draft, id) === "terminal"
    ? { width: TERMINAL_WIDTH, height: TERMINAL_HEIGHT }
    : { width: NODE_WIDTH, height: NODE_HEIGHT }
}

function sizeForAddKind(kind: BlueprintAddNodeKind) {
  if (kind === "branch") return { width: COMMON_BRANCH_WIDTH, height: COMMON_BRANCH_HEIGHT }
  return kind === "start" || kind === "end"
    ? { width: TERMINAL_WIDTH, height: TERMINAL_HEIGHT }
    : { width: NODE_WIDTH, height: NODE_HEIGHT }
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function mod(value: number, by: number) {
  return ((value % by) + by) % by
}
