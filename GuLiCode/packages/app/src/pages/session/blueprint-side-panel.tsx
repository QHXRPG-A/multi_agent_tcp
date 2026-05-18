import { Button } from "@opencode-ai/ui/button"
import { Collapsible } from "@opencode-ai/ui/collapsible"
import { ContextMenu } from "@opencode-ai/ui/context-menu"
import { useDialog } from "@opencode-ai/ui/context/dialog"
import { Dialog } from "@opencode-ai/ui/dialog"
import { DropdownMenu } from "@opencode-ai/ui/dropdown-menu"
import { Icon } from "@opencode-ai/ui/icon"
import { IconButton } from "@opencode-ai/ui/icon-button"
import { Popover } from "@opencode-ai/ui/popover"
import { TextField, type TextFieldProps } from "@opencode-ai/ui/text-field"
import { Tooltip } from "@opencode-ai/ui/tooltip"
import { For, Match, Show, Switch, createEffect, createMemo, createSignal, onCleanup, onMount, splitProps, untrack, type JSX } from "solid-js"
import { createStore, reconcile, type SetStoreFunction } from "solid-js/store"
import { useLanguage } from "@/context/language"
import { Persist, persisted } from "@/utils/persist"
import { decode64 } from "@/utils/base64"
import { useSessionLayout } from "@/pages/session/session-layout"
import {
  DEFAULT_INPUT_PORT,
  DEFAULT_OUTPUT_PORT,
  GRID_SIZE,
  addEdge,
  addNode,
  CLI_KIND_OPTIONS,
  DEFAULT_BLUEPRINT_ID,
  DEFAULT_BLUEPRINT_NAME,
  TEST_AGENT_NODE_FLAG,
  createBlueprintStartPlan,
  createDefaultBlueprintDraft,
  defaultCommandForCliKind,
  defaultModelForCliKind,
  deleteEdge,
  deleteNode,
  deleteSelection,
  jsonText,
  nodeIds,
  nodeKind,
  parseJsonObject,
  parseScopeText,
  parseStringRecord,
  scopeText,
  setInspector,
  setSelection,
  snapPosition,
  fromBlueprintDocument,
  toBlueprintDocument,
  toRuntimeGraphDraft,
  updateEdge,
  validateBlueprintConfigForStart,
  type BlueprintAddNodeKind,
  type BlueprintAgentNode,
  type BlueprintCliKind,
  type BlueprintConfig,
  type BlueprintConfigValidationIssue,
  type BlueprintDraft,
  type BlueprintEdge,
  type BlueprintNodeLayout,
  type BlueprintRouteNode,
  type BlueprintTerminalKind,
} from "@/pages/session/blueprint-model"
import { createTestAgentPanelSnapshot } from "@/pages/session/blueprint-test-agent-snapshot"
import { usePlatform, type BlueprintCatalogItem, type BlueprintRunEndAction } from "@/context/platform"

const NODE_WIDTH = 172
const NODE_HEIGHT = 72
const TERMINAL_WIDTH = 92
const TERMINAL_HEIGHT = 44
const MIN_ZOOM = 0.35
const MAX_ZOOM = 1.8
const AGENT_PANEL_LONG_PRESS_MS = 800
const AGENT_PANEL_LONG_PRESS_CANCEL_PX = 8
const AGENT_PANEL_PROGRESS_RADIUS = 8
const AGENT_PANEL_PROGRESS_CIRCUMFERENCE = 2 * Math.PI * AGENT_PANEL_PROGRESS_RADIUS
const AGENT_PANEL_DEFAULT_WIDTH = 374
const AGENT_PANEL_DEFAULT_HEIGHT = 410
const AGENT_PANEL_MIN_WIDTH = 320
const AGENT_PANEL_MIN_HEIGHT = 300
const AGENT_PANEL_MARGIN = 8
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
  "--background-base": "#f8fafc",
  "--background-strong": "#ffffff",
  "--background-stronger": "#eef2f7",
  "--surface-base-hover": "rgba(14, 116, 144, 0.08)",
  "--surface-base-active": "rgba(14, 116, 144, 0.14)",
  "--border-weaker-base": "rgba(15, 23, 42, 0.12)",
  "--border-weak-base": "rgba(15, 23, 42, 0.18)",
  "--text-strong": "#0f172a",
  "--text-base": "#1f2937",
  "--text-weak": "#475569",
  "--text-weaker": "#64748b",
  "--icon-base": "#0f172a",
  "--icon-weak": "#475569",
  "--icon-strong-base": "#020617",
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
  skills: BlueprintCatalogItem[]
  rules: BlueprintCatalogItem[]
  skillError?: string
  ruleError?: string
}

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

type RuntimePanelMode = "runtime" | "inspector"

type BlueprintRuntimeState = {
  runId?: string
  runs: Record<string, unknown>[]
  status?: Record<string, unknown>
  explanation?: Record<string, unknown>
  events: Record<string, unknown>[]
  loading: boolean
  action?: string
  error?: string
  lastUpdatedAt?: number
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
}

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
      type: "agent"
      id: string
      node: BlueprintAgentNode
    }

export function BlueprintSidePanel() {
  const language = useLanguage()
  const platform = usePlatform()
  const dialog = useDialog()
  const { params, view } = useSessionLayout()
  const projectDirectory = decode64(params.dir) ?? "global"
  const [draft, setDraft, _, draftReady] = persisted(
    Persist.workspace(projectDirectory, "blueprint-draft.v1"),
    createStore<BlueprintDraft>(createDefaultBlueprintDraft(projectDirectory)),
  )
  const [drag, setDrag] = createSignal<DragState>()
  const [connection, setConnection] = createSignal<ConnectionState>()
  const [agentPanelPress, setAgentPanelPress] = createSignal<AgentPanelPressState>()
  const [addMenuOpen, setAddMenuOpen] = createSignal(false)
  const [catalog, setCatalog] = createSignal<CatalogState>({
    skillDir: "",
    ruleDir: "",
    skills: [],
    rules: [],
  })
  const [modelCatalog, setModelCatalog] = createSignal<ModelCatalogState>({
    cliKind: "",
    models: [],
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
  const [agentPanel, setAgentPanel] = createStore<AgentPanelState>({
    panels: {},
    streamEvents: {},
    streamCursor: 0,
  })
  const [panelMode, setPanelMode] = createSignal<RuntimePanelMode>("runtime")
  let canvasRef: HTMLDivElement | undefined
  let saveTimer: ReturnType<typeof setTimeout> | undefined
  const testAgentPersistTimers: Record<string, ReturnType<typeof setTimeout> | undefined> = {}
  const testAgentPersistRunning: Record<string, boolean | undefined> = {}
  const testAgentPersistQueued: Record<string, boolean | undefined> = {}
  let agentPanelPressFrame: number | undefined
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
    for (const timer of Object.values(testAgentPersistTimers)) {
      if (timer) clearTimeout(timer)
    }
  })

  const addOptions = createMemo(() => [
    {
      kind: "agent" as const,
      label: language.t("blueprint.node.agent"),
      description: language.t("blueprint.add.agent.description"),
    },
    {
      kind: "test-agent" as const,
      label: "测试节点",
      description: "实时记录 Agent 信息面板数据",
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
    {
      kind: "start" as const,
      label: language.t("blueprint.node.start"),
      description: language.t("blueprint.add.start.description"),
    },
    {
      kind: "end" as const,
      label: language.t("blueprint.node.end"),
      description: language.t("blueprint.add.end.description"),
    },
  ])

  const nodes = createMemo<NodeItem[]>(() => [
    ...Object.entries(draft.graph.terminal_nodes).map(([id, kind]) => ({
      id,
      kind,
      type: "terminal" as const,
    })),
    ...Object.entries(draft.graph.route_nodes ?? {}).map(([id, node]) => ({
      id,
      node,
      type: "route" as const,
    })),
    ...Object.entries(draft.graph.agent_nodes).map(([id, node]) => ({
      id,
      node,
      type: "agent" as const,
    })),
  ])

  const selectedNodeId = createMemo(() => (draft.selection?.type === "node" ? draft.selection.id : undefined))
  const selectedEdge = createMemo(() => {
    if (draft.selection?.type !== "edge") return
    return draft.graph.edges.find((edge) => edge.id === draft.selection?.id)
  })
  const inspectedAgent = createMemo(() => {
    if (draft.inspector?.type !== "node") return
    return draft.graph.agent_nodes[draft.inspector.id]
  })
  const inspectedRoute = createMemo(() => {
    if (draft.inspector?.type !== "node") return
    return draft.graph.route_nodes?.[draft.inspector.id]
  })
  const inspectedTerminal = createMemo(() => {
    if (draft.inspector?.type !== "node") return
    return draft.graph.terminal_nodes[draft.inspector.id]
  })
  const inspectedEdge = createMemo(() => {
    if (draft.inspector?.type !== "edge") return
    return draft.graph.edges.find((edge) => edge.id === draft.inspector?.id)
  })
  const inspectorOpen = createMemo(
    () => !!inspectedAgent() || !!inspectedRoute() || !!inspectedTerminal() || !!inspectedEdge(),
  )
  const runtimeGraph = createMemo(() => toRuntimeGraphDraft(draft))
  const currentConfig = createMemo(() => ({
    project_workdir: draft.config?.project_workdir ?? projectDirectory ?? ".",
    skill_dir: draft.config?.skill_dir ?? "",
    rule_dir: draft.config?.rule_dir ?? "",
  }))

  const updateConfigField = <K extends keyof BlueprintConfig>(field: K, value: BlueprintConfig[K]) => {
    setDraft("config", field, value as never)
  }

  const replaceDraft = (next: BlueprintDraft) => {
    setDraft(reconcile(next))
  }

  const persistProjectDraft = async (next: BlueprintDraft) => {
    if (!platform.saveBlueprint) return
    await platform.saveBlueprint(projectDirectory, toBlueprintDocument(next, DEFAULT_BLUEPRINT_ID, DEFAULT_BLUEPRINT_NAME))
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

  createEffect(() => {
    const skillDir = currentConfig().skill_dir
    const ruleDir = currentConfig().rule_dir
    let cancelled = false

    void Promise.allSettled([listSkills(skillDir), listRules(ruleDir)]).then(([skills, rules]) => {
      if (cancelled) return
      setCatalog({
        skillDir,
        ruleDir,
        skills: skills.status === "fulfilled" ? skills.value : [],
        rules: rules.status === "fulfilled" ? rules.value : [],
        skillError: skills.status === "rejected" ? readableError(skills.reason) : undefined,
        ruleError: rules.status === "rejected" ? readableError(rules.reason) : undefined,
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
        const document = await openBlueprint(projectDirectory, DEFAULT_BLUEPRINT_ID)
        applyingRemote = true
        replaceDraft(fromBlueprintDocument(document as Parameters<typeof fromBlueprintDocument>[0], projectDirectory))
        queueMicrotask(() => {
          applyingRemote = false
        })
        setPersistence({ loaded: true, loading: false, saving: false, source: "project" })
      } catch (error) {
        const code = typeof error === "object" && error !== null ? (error as { code?: string }).code : undefined
        if (code === "NOT_FOUND" || readableError(error).includes("NOT_FOUND")) {
          await saveProjectDraft(draft)
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
    draft.schema_version
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
        ? nodeIds(draft).includes(inspector.id)
        : draft.graph.edges.some((edge) => edge.id === inspector.id)
    if (!valid) replaceDraft(setInspector(draft, undefined))
  })

  createEffect(() => {
    if (!persistence().loaded || !platform.listBlueprintRuns || runtime().runId || runtime().runs.length) return
    let cancelled = false
    void platform
      .listBlueprintRuns(projectDirectory, DEFAULT_BLUEPRINT_ID)
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
    const status = runtimeStatus(runtime().status)
    if (!runId || isTerminalRuntimeStatus(status)) return
    const interval = setInterval(() => {
      void refreshBlueprintRuntime(runId, { quiet: true })
    }, 2000)
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

  async function startBlueprintRuntime() {
    if (!platform.saveBlueprint || !platform.startBlueprintRun) {
      setRuntime((current) => ({ ...current, error: language.t("blueprint.runtime.unavailable") }))
      return
    }
    const configIssues = validateBlueprintConfigForStart(draft)
    if (configIssues.length) {
      dialog.show(() => <BlueprintConfigRequiredDialog issues={configIssues} />)
      return
    }
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = undefined
    }
    setPanelMode("runtime")
    setPersistence((current) => ({ ...current, saving: true, error: undefined }))
    setRuntime((current) => ({ ...current, loading: true, action: "start", error: undefined }))
    try {
      await persistProjectDraft(draft)
      setPersistence({ loaded: true, loading: false, saving: false, source: "project" })
      const started = await platform.startBlueprintRun(
        projectDirectory,
        DEFAULT_BLUEPRINT_ID,
        createBlueprintStartPlan(draft),
        "live",
      )
      const runId = typeof started.runId === "string" ? started.runId : undefined
      setRuntime((current) => ({
        ...current,
        runId,
        runs: mergeRuntimeRunsWithStatus(current.runs, started),
        status: asRecord(started.status),
        events: arrayOfRecords(asRecord(started.status)?.recent_events),
        loading: false,
        action: undefined,
        error: undefined,
        lastUpdatedAt: Date.now(),
      }))
      scheduleOpenTestAgentPanelPersists()
      if (platform.listBlueprintRuns) {
        const runs = await platform.listBlueprintRuns(projectDirectory, DEFAULT_BLUEPRINT_ID)
        setRuntime((current) => ({ ...current, runs }))
      }
      if (runId) void refreshBlueprintRuntime(runId, { quiet: true })
    } catch (error) {
      const message = readableError(error)
      setPersistence((current) => ({ ...current, saving: false, error: message }))
      setRuntime((current) => ({ ...current, loading: false, action: undefined, error: message }))
    }
  }

  async function endBlueprintRuntime(action: BlueprintRunEndAction) {
    const runId = runtime().runId
    if (!runId || !platform.endBlueprintRun) return
    setRuntime((current) => ({ ...current, loading: true, action, error: undefined }))
    try {
      const ended = await platform.endBlueprintRun(runId, action, `blueprint UI ${action}`)
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
    } catch (error) {
      setRuntime((current) => ({ ...current, loading: false, action: undefined, error: readableError(error) }))
    }
  }

  function scheduleOpenTestAgentPanelPersists() {
    for (const panel of Object.values(agentPanel.panels)) {
      if (isTestAgentNode(draft.graph.agent_nodes[panel.nodeId])) scheduleTestAgentPanelPersist(panel.nodeId)
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
    if (!platform.saveBlueprintAgentPanelTest) return
    const node = draft.graph.agent_nodes[nodeId]
    if (!isTestAgentNode(node)) return
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
    if (!node || !panel || !isTestAgentNode(node) || !platform.saveBlueprintAgentPanelTest) return
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
    const testAgent = isTestAgentNode(node)
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
      testJsonPending: testAgent && Boolean(platform.saveBlueprintAgentPanelTest),
      testJsonError: undefined,
    })
    if (testAgent) scheduleTestAgentPanelPersist(nodeId, { immediate: true })
    await refreshAgentPanelInfo(runtime().runId, nodeId)
    if (testAgent) scheduleTestAgentPanelPersist(nodeId, { immediate: true })
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
      if (!nodeId || !runtimeMessageId || !isTestAgentNode(draft.graph.agent_nodes[nodeId])) continue
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
    for (const nodeId of changedNodes) scheduleTestAgentPanelPersist(nodeId, { immediate: true })
  }

  function syncAgentPanelUserMessageFromStreamEvent(nodeId: string, event: AgentStreamEvent) {
    if (!isTestAgentNode(draft.graph.agent_nodes[nodeId])) return
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
    if (patch) updateAgentPanelUserMessageByRuntimeMessageId(nodeId, runtimeMessageId, patch)
  }

  async function sendAgentPanelMessage(nodeId: string) {
    const panel = agentPanel.panels[nodeId]
    const runId = runtime().runId
    if (!panel || !runId || !platform.queueBlueprintAgentMessage) return
    const text = panel.input
    const testAgent = isTestAgentNode(draft.graph.agent_nodes[nodeId])
    const messageId = `user-msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    if (testAgent) {
      appendAgentPanelUserMessage({
        id: messageId,
        runId,
        nodeId,
        mode: panel.mode,
        text,
        status: "queued",
        created_at: new Date().toISOString(),
      })
      scheduleTestAgentPanelPersist(nodeId, { immediate: true })
    }
    setAgentPanel("panels", nodeId, "sending", true)
    setAgentPanel("panels", nodeId, "error", undefined)
    try {
      const queued = await platform.queueBlueprintAgentMessage(runId, nodeId, text, panel.mode)
      const runtimeMessageId = runtimeMessageIdFromQueueResponse(queued)
      if (testAgent) {
        updateAgentPanelUserMessage(nodeId, messageId, {
          status: "sent",
          runtimeStatus: "queued",
          runtimeMessageId,
          sent_at: new Date().toISOString(),
        })
        syncAgentPanelUserMessagesFromRuntimeEvents(arrayOfRecords(asRecord(queued.status)?.recent_events))
        scheduleTestAgentPanelPersist(nodeId, { immediate: true })
      }
      setAgentPanel("panels", nodeId, "input", "")
      void refreshBlueprintRuntime(runId, { quiet: true })
    } catch (error) {
      const message = readableError(error)
      if (testAgent) {
        updateAgentPanelUserMessage(nodeId, messageId, {
          status: "failed",
          failed_at: new Date().toISOString(),
          error: message,
        })
        scheduleTestAgentPanelPersist(nodeId, { immediate: true })
      }
      setAgentPanel("panels", nodeId, "error", message)
    } finally {
      setAgentPanel("panels", nodeId, "sending", false)
      if (testAgent) scheduleTestAgentPanelPersist(nodeId)
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

  const addNodeAtCenter = (kind: BlueprintAddNodeKind) => {
    replaceDraft(addNode(draft, { kind, position: positionAtCenter(kind) }))
    setConnection(undefined)
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
    if (event.button === 0) {
      replaceDraft(setInspector(setSelection(draft, undefined), undefined))
      return
    }
    if (event.button !== 2) return
    event.preventDefault()
    replaceDraft(setSelection(draft, undefined))
    setDrag({
      type: "pan",
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

  const handleCanvasDrop = (event: DragEvent) => {
    const kind = event.dataTransfer?.getData("application/x-gulicode-blueprint-node") as BlueprintAddNodeKind
    if (!kind) return
    event.preventDefault()
    replaceDraft(addNode(draft, { kind, position: positionForClient(kind, event.clientX, event.clientY) }))
  }

  const isAddNodeDrag = (dataTransfer?: DataTransfer | null) =>
    !!dataTransfer?.types.includes("application/x-gulicode-blueprint-node")

  const clientInsideCanvas = (clientX: number, clientY: number) => {
    const rect = canvasRef?.getBoundingClientRect()
    if (!rect) return false
    return clientX >= rect.left && clientX <= rect.right && clientY >= rect.top && clientY <= rect.bottom
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
    replaceDraft(addNode(draft, { kind, position: positionForClient(kind, event.clientX, event.clientY) }))
    setConnection(undefined)
  }

  const handleNodePointerDown = (event: PointerEvent, item: NodeItem) => {
    const id = item.id
    closeFloatingAgentPanels()
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

  const handleOutputPortPointerDown = (event: PointerEvent, id: string) => {
    if (event.button !== 0) return
    cancelAgentPanelLongPress()
    event.preventDefault()
    event.stopPropagation()
    selectNode(id)
    setConnection({
      source: id,
      output_port: DEFAULT_OUTPUT_PORT,
      pointer: worldPointFromClient(event.clientX, event.clientY),
    })
  }

  const handleInputPortPointerUp = (event: PointerEvent, id: string) => {
    const current = connection()
    if (!current) return
    cancelAgentPanelLongPress()
    event.preventDefault()
    event.stopPropagation()
    if (current.source !== id) {
      replaceDraft(addEdge(draft, current.source, id, "exec", current.output_port, DEFAULT_INPUT_PORT))
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

    const currentConnection = connection()
    if (currentConnection) {
      const target = document.elementFromPoint(event.clientX, event.clientY) as HTMLElement | null
      const inputPort = target?.closest("[data-blueprint-port='input']") as HTMLElement | null
      const targetNode = inputPort?.dataset.blueprintNodeId
      if (targetNode && targetNode !== currentConnection.source) {
        replaceDraft(addEdge(draft, currentConnection.source, targetNode, "exec", currentConnection.output_port, DEFAULT_INPUT_PORT))
      }
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
    if (event.key !== "Delete" && event.key !== "Backspace") return
    if (!draft.selection) return
    const target = event.target as HTMLElement | null
    const tagName = target?.tagName.toLowerCase()
    if (target?.isContentEditable || tagName === "input" || tagName === "textarea" || tagName === "select") return
    event.preventDefault()
    deleteCurrent()
  }

  onMount(() => {
    window.addEventListener("pointermove", handlePointerMove)
    window.addEventListener("pointerup", handlePointerUp)
    window.addEventListener("pointercancel", handlePointerCancel)
    window.addEventListener("dragover", handleWindowDragOver, true)
    window.addEventListener("drop", handleWindowDrop, true)
    onCleanup(() => {
      window.removeEventListener("pointermove", handlePointerMove)
      window.removeEventListener("pointerup", handlePointerUp)
      window.removeEventListener("pointercancel", handlePointerCancel)
      window.removeEventListener("dragover", handleWindowDragOver, true)
      window.removeEventListener("drop", handleWindowDrop, true)
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
      id="blueprint-panel"
      class="size-full min-w-0 h-full flex flex-col bg-background-base"
      style={BLUEPRINT_THEME}
      tabIndex={0}
      onKeyDown={handleKeyDown}
    >
      <div
        class="h-10 shrink-0 flex items-center justify-between gap-3 border-b border-border-weaker-base bg-background-strong px-3"
        style={BLUEPRINT_CHROME_THEME}
      >
        <div class="flex min-w-0 items-center gap-2">
          <Icon size="small" name="blueprint" class="text-[var(--blueprint-edge-active)]" />
          <div class="min-w-0 truncate text-13-medium text-text-strong">
            {language.t("session.header.blueprint")}
          </div>
          <Show when={!draftReady()}>
            <div class="text-11-regular text-text-weaker">{language.t("common.loading")}</div>
          </Show>
          <Show when={persistence().loading || persistence().saving || persistence().error}>
            <div class="max-w-80 truncate text-11-regular text-text-weaker">
              {persistence().loading
                ? language.t("common.loading")
                : persistence().saving
                  ? language.t("common.save")
                  : persistence().error}
            </div>
          </Show>
        </div>
        <Tooltip placement="bottom" value={language.t("common.close")}>
          <IconButton
            icon="close-small"
            variant="ghost"
            class="h-6 w-6 shrink-0"
            onClick={() => view().blueprintPanel.close()}
            aria-label={language.t("common.close")}
          />
        </Tooltip>
      </div>

      <div
        class="h-10 shrink-0 flex items-center justify-between gap-2 border-b border-border-weaker-base bg-background-base px-2"
        style={BLUEPRINT_CHROME_THEME}
      >
        <div class="flex min-w-0 items-center gap-1">
          <DropdownMenu open={addMenuOpen()} onOpenChange={setAddMenuOpen}>
            <DropdownMenu.Trigger as={Button} size="small" variant="ghost" icon="plus-small" class="h-7 px-2">
              <span class="hidden lg:inline">{language.t("blueprint.toolbar.addNode")}</span>
              <Icon size="small" name="chevron-down" class="text-icon-weak" />
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content class="mt-1 w-56">
                <For each={addOptions()}>
                  {(option) => (
                    <DropdownMenu.Item
                      draggable
                      onDragStart={(event: DragEvent) => {
                        event.dataTransfer?.setData("application/x-gulicode-blueprint-node", option.kind)
                        event.dataTransfer?.setData("text/plain", option.label)
                        setAddMenuOpen(false)
                      }}
                      onSelect={() => addNodeAtCenter(option.kind)}
                    >
                      <Icon size="small" name={addNodeIcon(option.kind)} />
                      <div class="flex min-w-0 flex-col">
                        <DropdownMenu.ItemLabel>{option.label}</DropdownMenu.ItemLabel>
                        <DropdownMenu.ItemDescription>{option.description}</DropdownMenu.ItemDescription>
                      </div>
                    </DropdownMenu.Item>
                  )}
                </For>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu>
        </div>
        <div class="flex shrink-0 items-center gap-1">
          <Tooltip placement="bottom" value={language.t("blueprint.runtime.start")}>
            <Button
              size="small"
              variant="ghost"
              icon="terminal"
              class="h-7 px-2"
              disabled={runtime().loading || !persistence().loaded}
              onClick={() => void startBlueprintRuntime()}
            >
              <span class="hidden lg:inline">{language.t("blueprint.runtime.start")}</span>
            </Button>
          </Tooltip>
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
          <Tooltip placement="bottom" value={language.t("blueprint.runtime.panel")}>
            <IconButton
              icon="status"
              variant={panelMode() === "runtime" ? "secondary" : "ghost"}
              class="h-7 w-7"
              onClick={() => setPanelMode("runtime")}
              aria-label={language.t("blueprint.runtime.panel")}
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
          <BlueprintGlobalConfigPanel
            config={currentConfig()}
            onConfigChange={updateConfigField}
            skillCount={catalog().skills.length}
            ruleCount={catalog().rules.length}
            skillError={catalog().skillError}
            ruleError={catalog().ruleError}
          />
          <div
            class="absolute left-0 top-0"
            style={{
              transform: `translate3d(${draft.layout.viewport.x}px, ${draft.layout.viewport.y}px, 0) scale(${draft.layout.viewport.zoom})`,
              "transform-origin": "0 0",
            }}
          >
            <svg class="absolute left-0 top-0 overflow-visible" width="1" height="1" aria-hidden="true">
              <For each={draft.graph.edges}>
                {(edge) => {
                  const path = () => edgePath(draft, edge)
                  const selected = () => draft.selection?.type === "edge" && draft.selection.id === edge.id
                  return (
                    <g>
                      <path
                        d={path()}
                        fill="none"
                        stroke="transparent"
                        stroke-width="14"
                        style={{ "pointer-events": "stroke" }}
                        class="cursor-pointer"
                        onPointerDown={(event) => {
                          event.stopPropagation()
                          inspectEdge(edge.id)
                        }}
                      />
                      <path
                        d={path()}
                        fill="none"
                        stroke={selected() ? "var(--blueprint-edge-active)" : "var(--blueprint-edge)"}
                        stroke-width={selected() ? 2 : 1.5}
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        marker-end="url(#blueprint-arrow)"
                        style={{ "pointer-events": "none" }}
                      />
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
                  agentPanelProgress={agentPanelPress()?.nodeId === item.id ? (agentPanelPress()?.progress ?? 0) : 0}
                  layout={draft.layout.nodes[item.id]}
                  onPointerDown={(event) => handleNodePointerDown(event, item)}
                  onDoubleClick={() => inspectNode(item.id)}
                  onDelete={() => replaceDraft(deleteNode(draft, item.id))}
                  onEdit={() => inspectNode(item.id)}
                  onInfoPanel={() => void openAgentPanel(item.id, false)}
                  onOutputPointerDown={(event) => handleOutputPortPointerDown(event, item.id)}
                  onInputPointerUp={(event) => handleInputPortPointerUp(event, item.id)}
                />
              )}
            </For>
          </div>
          <For each={agentPanelEntries()}>
            {(panel) => (
              <AgentInfoPanel
                panel={panel}
                node={draft.graph.agent_nodes[panel.nodeId]}
                runId={runtime().runId}
                runtimeStatus={runtimeStatus(runtime().status)}
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
        </div>

        <Show when={panelMode() === "runtime" || inspectorOpen()}>
          <div
            class="w-[340px] max-w-[44%] min-w-[282px] shrink-0 border-l border-[rgba(103,232,249,0.16)] bg-[#071019] shadow-[-20px_0_48px_rgba(0,0,0,0.42)]"
            style={BLUEPRINT_INSPECTOR_THEME}
          >
            <Switch>
              <Match when={panelMode() === "runtime"}>
                <BlueprintRuntimePanel
                  state={runtime()}
                  onStart={() => void startBlueprintRuntime()}
                  onRefresh={() => void refreshBlueprintRuntime()}
                  onEnd={(action) => void endBlueprintRuntime(action)}
                />
              </Match>
              <Match when={inspectorOpen()}>
                <BlueprintInspector
                  draft={draft}
                  selectedAgent={inspectedAgent()}
                  selectedRoute={inspectedRoute()}
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
                />
              </Match>
            </Switch>
          </div>
        </Show>
      </div>
    </div>
  )
}

function BlueprintRuntimePanel(props: {
  state: BlueprintRuntimeState
  onStart: () => void
  onRefresh: () => void
  onEnd: (action: BlueprintRunEndAction) => void
}) {
  const language = useLanguage()
  const status = createMemo(() => asRecord(props.state.status))
  const run = createMemo(() => asRecord(status()?.run))
  const agents = createMemo(() => recordEntries(asRecord(status()?.agents)))
  const queues = createMemo(() => asRecord(status()?.queues))
  const pendingMessages = createMemo(() => recordEntries(asRecord(queues()?.pending_messages)))
  const queueByAgent = createMemo(() => recordEntries(asRecord(queues()?.by_agent)))
  const outgoing = createMemo(() => recordEntries(asRecord(status()?.outgoing_batches)))
  const joins = createMemo(() => recordEntries(asRecord(status()?.joins)))
  const jobs = createMemo(() => recordEntries(asRecord(status()?.jobs)))
  const workspace = createMemo(() => asRecord(status()?.workspace))
  const explanation = createMemo(() => asRecord(props.state.explanation))
  const summary = createMemo(() => asRecord(explanation()?.summary))
  const runStatus = createMemo(() => runtimeStatus(props.state.status) || "idle")
  const terminal = createMemo(() => isTerminalRuntimeStatus(runStatus()))

  return (
    <div class="size-full min-h-0 flex flex-col bg-[#071019] text-[#d6e9f5]">
      <div class="h-10 shrink-0 flex items-center justify-between border-b border-[rgba(103,232,249,0.14)] bg-[#0b1522] px-3">
        <div class="min-w-0 truncate text-12-medium text-[#f8fdff]">{language.t("blueprint.runtime.panel")}</div>
        <div class="flex shrink-0 items-center gap-1">
          <IconButton
            icon="terminal"
            variant="ghost"
            class="h-6 w-6 text-[#f8fdff]"
            disabled={props.state.loading}
            onClick={props.onStart}
            aria-label={language.t("blueprint.runtime.start")}
          />
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
        <div class="flex flex-col gap-3">
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
            <div class="mt-3 grid grid-cols-4 gap-1">
              <RuntimeActionButton label={language.t("blueprint.runtime.complete")} disabled={!props.state.runId || props.state.loading} onClick={() => props.onEnd("complete")} />
              <RuntimeActionButton label={language.t("blueprint.runtime.pause")} disabled={!props.state.runId || props.state.loading || terminal()} onClick={() => props.onEnd("pause")} />
              <RuntimeActionButton label={language.t("blueprint.runtime.cancel")} disabled={!props.state.runId || props.state.loading || terminal()} onClick={() => props.onEnd("cancel")} />
              <RuntimeActionButton label={language.t("blueprint.runtime.fail")} disabled={!props.state.runId || props.state.loading || terminal()} onClick={() => props.onEnd("fail")} />
            </div>
          </div>

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

          <RuntimeSection title={language.t("blueprint.runtime.agents")}>
            <RuntimeEmpty when={agents().length === 0} />
            <For each={agents()}>
              {([id, agent]) => (
                <RuntimeRow
                  title={id}
                  meta={`${String(agent.state ?? "unknown")} · ${language.t("blueprint.runtime.queue")}: ${String(agent.queue_size ?? 0)}`}
                  detail={String(agent.last_error ?? agent.agent_id ?? "")}
                />
              )}
            </For>
          </RuntimeSection>

          <RuntimeSection title={language.t("blueprint.runtime.queues")}>
            <RuntimeEmpty when={pendingMessages().length === 0 && queueByAgent().length === 0} />
            <For each={queueByAgent()}>
              {([id, messages]) => (
                <RuntimeRow title={id} meta={`${arrayOfRecords(messages).length} ${language.t("blueprint.runtime.messages")}`} />
              )}
            </For>
            <For each={pendingMessages()}>
              {([id, message]) => <RuntimeRow title={id} meta={String(message.status ?? "")} detail={String(message.node_id ?? "")} />}
            </For>
          </RuntimeSection>

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

          <RuntimeSection title={language.t("blueprint.runtime.workspace")}>
            <div class="grid grid-cols-3 gap-2">
              <RuntimeMetric label={language.t("blueprint.runtime.changes")} value={arrayOfRecords(workspace()?.changesets).length} />
              <RuntimeMetric label={language.t("blueprint.runtime.artifacts")} value={arrayOfRecords(workspace()?.artifacts).length} />
              <RuntimeMetric label={language.t("blueprint.runtime.reports")} value={arrayOfRecords(workspace()?.reports).length} />
            </div>
            <RuntimeJsonPreview value={workspace() ?? {}} />
          </RuntimeSection>

          <RuntimeSection title={language.t("blueprint.runtime.events")}>
            <RuntimeEmpty when={props.state.events.length === 0} />
            <For each={props.state.events}>
              {(event) => (
                <RuntimeRow
                  title={String(event.type ?? event.record_type ?? "event")}
                  meta={String(event.status ?? "")}
                  detail={String(event.message ?? event.event ?? event.node_id ?? "")}
                />
              )}
            </For>
          </RuntimeSection>
        </div>
      </div>
    </div>
  )
}

function RuntimeActionButton(props: { label: string; disabled: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      disabled={props.disabled}
      class="h-7 min-w-0 rounded-sm border border-[rgba(103,232,249,0.22)] px-1 text-10-medium text-[#d6e9f5] transition-colors hover:border-[#67e8f9] disabled:cursor-not-allowed disabled:opacity-45"
      onClick={props.onClick}
    >
      <span class="block truncate">{props.label}</span>
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
  return (
    <div class="min-w-0 rounded-sm border border-[rgba(103,232,249,0.12)] bg-[#06101a] p-2">
      <div class="truncate text-10-regular text-[#95afc4]">{props.label}</div>
      <div class="mt-0.5 truncate text-14-medium text-[#f8fdff]">{props.value}</div>
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
  const latestStatusRecord = createMemo(() => asRecord(latestStatus()))
  const statusField = (key: string) => latestStatusRecord()?.[key] ?? runtime()?.[key]
  const testMode = createMemo(() => Boolean(props.panel.info?.testMode))
  const testAgentRecording = createMemo(
    () => isTestAgentNode(props.node) || testMode() || Boolean(props.panel.testJsonPath) || Boolean(props.panel.testJsonPending),
  )
  const testJsonPath = createMemo(() => {
    const path = props.panel.testJsonPath ?? props.panel.info?.jsonPath
    return typeof path === "string" && path ? path : undefined
  })
  const live = createMemo(() => !!props.runId && !isTerminalRuntimeStatus(props.runtimeStatus))
  const state = createMemo(() =>
    String(statusField("agent_state") ?? runtime()?.state ?? (props.runId ? props.runtimeStatus ?? "running" : "未运行")),
  )
  const queueSize = createMemo(() => String(statusField("queue_size") ?? 0))
  const messagesSent = createMemo(() => String(statusField("messages_sent") ?? 0))
  const busyCount = createMemo(() => String(statusField("busy_count") ?? 0))
  const currentMessageId = createMemo(() => stringValue(statusField("current_message_id")) ?? stringValue(statusField("message_id")))
  const statusUpdatedAt = createMemo(() => formatAgentStreamEventTime(statusField("created_at")))
  const lastError = createMemo(() => stringValue(statusField("last_error")))
  const visibleEvents = createMemo(() => visibleAgentPanelEvents(props.events))
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
      <div class="grid grid-cols-4 gap-2 border-b border-[rgba(103,232,249,0.12)] p-3 text-11-regular">
        <RuntimeMetric label="状态" value={state()} />
        <RuntimeMetric label="队列" value={queueSize()} />
        <RuntimeMetric label="消息" value={messagesSent()} />
        <RuntimeMetric label="忙碌" value={busyCount()} />
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto px-3 py-2" onWheel={(event) => event.stopPropagation()}>
        <Show when={latestStatus() || currentMessageId() || statusUpdatedAt() || lastError()}>
          <div class="mb-2 rounded-md border border-[rgba(103,232,249,0.14)] bg-[#08131f] p-2">
            <div class="mb-2 text-10-medium uppercase text-[#67e8f9]">运行状态</div>
            <div class="flex flex-col gap-1">
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
        </Show>
        <Show when={testAgentRecording()}>
          <div class="mb-2 rounded-md border border-[rgba(250,204,21,0.22)] bg-[rgba(250,204,21,0.06)] p-2">
            <div class="mb-1 text-10-medium uppercase text-[#facc15]">JSON 位置</div>
            <div class="break-all font-mono text-[11px] leading-4 text-[#fde68a]">
              {testJsonPath() ?? (props.panel.testJsonPending ? "写入中..." : "未生成")}
            </div>
            <Show when={props.panel.testJsonError}>
              {(error) => <div class="mt-1 break-all text-10-regular text-[#fca5a5]">JSON 保存失败: {error()}</div>}
            </Show>
          </div>
        </Show>
        <Show
          when={visibleEvents().length}
          fallback={<div class="py-8 text-center text-11-regular text-[#7fa4ba]">暂无 agent 输出</div>}
        >
          <For each={visibleEvents()}>
            {(event) => (
              <div class="mb-2 rounded-md border border-[rgba(103,232,249,0.12)] bg-[#071019] p-2">
                <div class="mb-1 flex items-center justify-between gap-2 text-10-regular text-[#7fa4ba]">
                  <span>{event.kind}</span>
                  <span>#{String(event.seq ?? "—")}</span>
                </div>
                <pre class="select-text whitespace-pre-wrap break-words font-mono text-[11px] leading-4 text-[#d6e9f5]">
                  {event.text}
                </pre>
              </div>
            )}
          </For>
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

function BlueprintNodeView(props: {
  item: NodeItem
  title: string
  subtitle: string
  selected: boolean
  inspecting: boolean
  connecting: boolean
  agentPanelProgress: number
  layout?: BlueprintNodeLayout
  onPointerDown: (event: PointerEvent) => void
  onDoubleClick: () => void
  onDelete: () => void
  onEdit: () => void
  onInfoPanel: () => void
  onOutputPointerDown: (event: PointerEvent) => void
  onInputPointerUp: (event: PointerEvent) => void
}) {
  const language = useLanguage()
  const width = () => (props.item.type === "terminal" ? TERMINAL_WIDTH : NODE_WIDTH)
  const height = () => (props.item.type === "terminal" ? TERMINAL_HEIGHT : NODE_HEIGHT)
  const showInput = () => props.item.type !== "terminal" || props.item.kind === "end"
  const showOutput = () => props.item.type !== "terminal" || props.item.kind === "start"
  const agentPanelProgress = () => clamp(props.agentPanelProgress, 0, 1)
  const nodeTone = createMemo(() => {
    if (props.item.type === "terminal") {
      return props.item.kind === "start"
        ? {
            background: "linear-gradient(135deg, rgba(15, 82, 70, 0.96), rgba(8, 36, 45, 0.96))",
            border: props.selected ? "rgba(45, 212, 191, 0.92)" : "rgba(45, 212, 191, 0.48)",
            glow: "0 12px 36px rgba(20, 184, 166, 0.18)",
            icon: "#5eead4",
          }
        : {
            background: "linear-gradient(135deg, rgba(72, 36, 89, 0.96), rgba(22, 22, 44, 0.96))",
            border: props.selected ? "rgba(216, 180, 254, 0.92)" : "rgba(192, 132, 252, 0.48)",
            glow: "0 12px 36px rgba(168, 85, 247, 0.18)",
            icon: "#d8b4fe",
          }
    }
    if (props.item.type === "route") {
      return {
        background: "linear-gradient(135deg, rgba(18, 46, 66, 0.98), rgba(8, 24, 36, 0.98))",
        border: props.selected ? "rgba(125, 211, 252, 0.94)" : "rgba(56, 189, 248, 0.5)",
        glow: "0 16px 42px rgba(14, 165, 233, 0.18)",
        icon: "#7dd3fc",
      }
    }
    if (props.item.type === "agent" && isTestAgentNode(props.item.node)) {
      return {
        background: "linear-gradient(135deg, rgba(51, 48, 25, 0.98), rgba(13, 28, 30, 0.98))",
        border: props.selected ? "rgba(250, 204, 21, 0.94)" : "rgba(250, 204, 21, 0.5)",
        glow: "0 16px 42px rgba(250, 204, 21, 0.14)",
        icon: "#facc15",
      }
    }
    return {
      background: "linear-gradient(135deg, rgba(25, 39, 62, 0.98), rgba(10, 20, 34, 0.98))",
      border: props.selected ? "rgba(103, 232, 249, 0.96)" : "rgba(99, 179, 215, 0.46)",
      glow: "0 16px 42px rgba(34, 211, 238, 0.16)",
      icon: "#67e8f9",
    }
  })

  return (
    <ContextMenu>
      <ContextMenu.Trigger class="contents">
        <div
          data-blueprint-node
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
            "box-shadow": props.selected
              ? `${nodeTone().glow}, inset 0 1px 0 rgba(255, 255, 255, 0.08), 0 0 0 1px rgba(103, 232, 249, 0.18)`
              : "0 10px 28px rgba(0, 0, 0, 0.24), inset 0 1px 0 rgba(255, 255, 255, 0.06)",
          }}
          onPointerDown={props.onPointerDown}
          onDblClick={(event) => {
            event.stopPropagation()
            props.onDoubleClick()
          }}
          aria-pressed={props.selected}
        >
          <Show when={showInput()}>
            <PortButton
              nodeId={props.item.id}
              side="input"
              title="Input"
              onPointerUp={props.onInputPointerUp}
              onPointerDown={(event) => event.stopPropagation()}
            />
          </Show>
          <Show when={showOutput()}>
            <PortButton nodeId={props.item.id} side="output" title="Output" onPointerDown={props.onOutputPointerDown} />
          </Show>
          <div class="flex w-full min-w-0 items-center gap-2">
            <Icon
              size="small"
              name={props.item.type === "terminal" ? "selector" : props.item.type === "route" ? "branch" : "blueprint"}
              class="shrink-0"
              style={{ color: nodeTone().icon }}
            />
            <div class="min-w-0 truncate text-12-medium text-[#f8fdff]">{props.title}</div>
          </div>
          <Show when={props.item.type !== "terminal"}>
            <div class="w-full truncate text-11-regular text-[#d6e9f5]">{props.subtitle}</div>
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
  title: string
  onPointerDown?: (event: PointerEvent) => void
  onPointerUp?: (event: PointerEvent) => void
}) {
  return (
    <button
      type="button"
      title={props.title}
      data-blueprint-port={props.side}
      data-blueprint-node-id={props.nodeId}
      class="absolute top-1/2 z-10 size-3 -translate-y-1/2 rounded-full border border-[rgba(103,232,249,0.82)] bg-[var(--blueprint-canvas-base)] shadow-[0_0_0_3px_rgba(8,24,36,0.92),0_0_12px_rgba(103,232,249,0.38)] transition-colors hover:bg-[rgba(103,232,249,0.22)]"
      classList={{
        "-left-1.5 cursor-crosshair": props.side === "input",
        "-right-1.5 cursor-crosshair": props.side === "output",
      }}
      onPointerDown={props.onPointerDown}
      onPointerUp={props.onPointerUp}
    />
  )
}

export function BlueprintInspector(props: {
  draft: BlueprintDraft
  selectedAgent?: BlueprintAgentNode
  selectedRoute?: BlueprintRouteNode
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
}) {
  const language = useLanguage()

  const updateAgentField = <K extends keyof BlueprintAgentNode>(field: K, value: BlueprintAgentNode[K]) => {
    const id = props.selectedNodeId
    if (!id || !props.selectedAgent) return
    props.setStore("graph", "agent_nodes", id, field, value as never)
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
                  onChange={(value) => props.setDraft(updateEdge(props.draft, edge().id, { edge_type: value }))}
                />
                <InspectorTextField
                  tip="outputPort"
                  label={language.t("blueprint.field.outputPort")}
                  value={edge().output_port ?? DEFAULT_OUTPUT_PORT}
                  onChange={(value) => props.setDraft(updateEdge(props.draft, edge().id, { output_port: value }))}
                />
                <InspectorTextField
                  tip="inputPort"
                  label={language.t("blueprint.field.inputPort")}
                  value={edge().input_port ?? DEFAULT_INPUT_PORT}
                  onChange={(value) => props.setDraft(updateEdge(props.draft, edge().id, { input_port: value }))}
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
  skillCount: number
  ruleCount: number
  skillError?: string
  ruleError?: string
}) {
  const language = useLanguage()
  const platform = usePlatform()

  const pickDirectory = async (field: keyof BlueprintConfig, title: string, defaultPath?: string) => {
    const result = await platform.openDirectoryPickerDialog?.({
      title,
      multiple: false,
      defaultPath,
    })
    if (typeof result === "string" && result.trim()) props.onConfigChange(field, result)
  }

  return (
    <div
      data-blueprint-global-config
      class="absolute left-3 top-3 z-20 w-[266px] rounded-md border border-[rgba(103,232,249,0.22)] bg-[rgba(7,16,25,0.88)] p-3 text-[#d6e9f5] shadow-[0_18px_48px_rgba(0,0,0,0.34)] backdrop-blur"
    >
      <div class="mb-2 flex items-center justify-between gap-2">
        <div class="text-12-medium text-[#f8fdff]">{language.t("blueprint.globalConfig.title")}</div>
        <div class="text-11-regular text-[#95afc4]">
          {props.skillCount} / {props.ruleCount}
        </div>
      </div>
      <div class="flex flex-col gap-2">
        <DirectoryConfigField
          label={language.t("blueprint.field.projectWorkdir")}
          tip="projectWorkdir"
          value={props.config.project_workdir}
          onChange={(value) => props.onConfigChange("project_workdir", value)}
          onBrowse={() =>
            void pickDirectory("project_workdir", language.t("blueprint.directory.pickProject"), props.config.project_workdir)
          }
        />
        <DirectoryConfigField
          label={language.t("blueprint.field.skillDir")}
          tip="skillDir"
          value={props.config.skill_dir}
          note={props.skillError ? language.t("blueprint.catalog.loadFailed") : language.t("blueprint.catalog.count", { count: props.skillCount })}
          onChange={(value) => props.onConfigChange("skill_dir", value)}
          onBrowse={() => void pickDirectory("skill_dir", language.t("blueprint.directory.pickSkill"), props.config.skill_dir)}
        />
        <DirectoryConfigField
          label={language.t("blueprint.field.ruleDir")}
          tip="ruleDir"
          value={props.config.rule_dir}
          note={props.ruleError ? language.t("blueprint.catalog.loadFailed") : language.t("blueprint.catalog.count", { count: props.ruleCount })}
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

function DirectoryConfigField(props: {
  label: string
  tip?: InspectorTipKey
  value: string
  note?: string
  onChange: (value: string) => void
  onBrowse: () => void
}) {
  return (
    <div class="flex min-w-0 flex-col gap-1">
      <InspectorFieldHeader label={props.label} tip={props.tip} placement="right-start" />
      <div class="flex min-w-0 gap-1">
        <input
          class="h-7 min-w-0 flex-1 rounded-md border border-[rgba(103,232,249,0.22)] bg-[#06101a] px-2 text-11-regular text-[#f8fdff] outline-none transition-colors placeholder:text-[#95afc4] focus:border-[#67e8f9]"
          value={props.value}
          onInput={(event) => props.onChange(event.currentTarget.value)}
        />
        <IconButton
          icon="folder"
          variant="ghost"
          size="small"
          class="h-7 w-7 shrink-0 text-[#d7f7ff] hover:text-[#67e8f9]"
          onClick={props.onBrowse}
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
  if (item.type === "agent" && isTestAgentNode(item.node)) return "测试节点"
  return item.id
}

function nodeSubtitle(t: (key: never, params?: Record<string, string | number | boolean>) => string, item: NodeItem) {
  if (item.type === "agent") return item.node.agent_id || item.node.cli_kind
  if (item.type === "route") return t(`blueprint.route.${routeLabelKey(item.node.route_kind)}` as never)
  return t("blueprint.node.terminal" as never)
}

function routeLabelKey(routeKind: string) {
  if (routeKind === "parallel_reduce") return "parallelReduce"
  return routeKind
}

function isTestAgentNode(node?: BlueprintAgentNode) {
  return node?.adapter_options?.[TEST_AGENT_NODE_FLAG] === true
}

function addNodeIcon(kind: BlueprintAddNodeKind): "blueprint" | "branch" | "selector" {
  if (kind === "agent" || kind === "test-agent") return "blueprint"
  if (kind === "start" || kind === "end") return "selector"
  return "branch"
}

function fallbackModels(cliKind: string) {
  return MODEL_LIST_FALLBACKS[cliKind] ?? MODEL_LIST_FALLBACKS.codemaker
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

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined
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

function visibleAgentPanelEvents(events: AgentStreamEvent[]): AgentPanelDisplayEvent[] {
  const replies = new Map<string, AgentPanelDisplayEvent>()
  const display: AgentPanelDisplayEvent[] = []

  for (const event of events) {
    const kind = stringValue(event.kind) ?? "event"
    if (isHiddenAgentPanelStreamKind(kind)) continue

    if (kind === "part.delta" || kind === "message.completed") {
      if (!isAgentReplyTextEvent(event, kind)) continue
      const text = cleanAgentPanelReplyText(agentStreamEventContentText(event))
      const messageId = stringValue(event.message_id)
      if (!messageId) {
        if (text) display.push(agentPanelDisplayEventFromStream(event, kind, text))
        continue
      }

      const current = replies.get(messageId)
      if (!text) {
        if (current && kind === "message.completed") {
          current.status = stringValue(event.status) ?? "completed"
          current.seq = event.seq ?? current.seq
        }
        continue
      }

      if (!current) {
        const reply = agentPanelDisplayEventFromStream(event, "Agent 回复", text, `reply-${messageId}`)
        replies.set(messageId, reply)
        display.push(reply)
        continue
      }

      current.text =
        kind === "message.completed" || shouldReplaceAgentReplyDraft(current.text, text)
          ? text
          : `${current.text}${text}`
      current.status = stringValue(event.status) ?? current.status
      current.seq = event.seq ?? current.seq
      continue
    }

    const text = cleanAgentPanelReplyText(agentStreamEventContentText(event))
    if (text) display.push(agentPanelDisplayEventFromStream(event, kind, text))
  }

  return display
}

function isHiddenAgentPanelStreamKind(kind: string) {
  return (
    kind === "status" ||
    kind === "message.started" ||
    kind === "queue.updated" ||
    kind === "tool.started" ||
    kind === "tool.completed"
  )
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
): AgentPanelDisplayEvent {
  return {
    id: stringValue(event.event_id) ?? stringValue(event.part_id) ?? stringValue(event.message_id) ?? fallbackId,
    kind,
    seq: event.seq,
    status: stringValue(event.status),
    text,
  }
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
  const source = portPoint(draft, edge.from, "output")
  const target = portPoint(draft, edge.to, "input")
  if (!source || !target) return ""

  const bend = Math.max(64, Math.abs(target.x - source.x) / 2)
  return `M ${source.x} ${source.y} C ${source.x + bend} ${source.y}, ${target.x - bend} ${target.y}, ${target.x} ${target.y}`
}

function connectionPath(draft: BlueprintDraft, connection: ConnectionState) {
  const source = portPoint(draft, connection.source, "output")
  const target = connection.pointer
  if (!source || !target) return ""
  const bend = Math.max(64, Math.abs(target.x - source.x) / 2)
  return `M ${source.x} ${source.y} C ${source.x + bend} ${source.y}, ${target.x - bend} ${target.y}, ${target.x} ${target.y}`
}

function portPoint(draft: BlueprintDraft, id: string, side: "input" | "output") {
  const layout = draft.layout.nodes[id]
  if (!layout) return
  const size = nodeSize(draft, id)
  return {
    x: side === "output" ? layout.x + size.width : layout.x,
    y: layout.y + size.height / 2,
  }
}

function nodeSize(draft: BlueprintDraft, id: string) {
  return nodeKind(draft, id) === "terminal"
    ? { width: TERMINAL_WIDTH, height: TERMINAL_HEIGHT }
    : { width: NODE_WIDTH, height: NODE_HEIGHT }
}

function sizeForAddKind(kind: BlueprintAddNodeKind) {
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
