import { Button } from "@opencode-ai/ui/button"
import { ContextMenu } from "@opencode-ai/ui/context-menu"
import { DropdownMenu } from "@opencode-ai/ui/dropdown-menu"
import { Icon } from "@opencode-ai/ui/icon"
import { IconButton } from "@opencode-ai/ui/icon-button"
import { Popover } from "@opencode-ai/ui/popover"
import { TextField, type TextFieldProps } from "@opencode-ai/ui/text-field"
import { Tooltip } from "@opencode-ai/ui/tooltip"
import { For, Match, Show, Switch, createEffect, createMemo, createSignal, onCleanup, onMount, splitProps, type JSX } from "solid-js"
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
  createDefaultBlueprintDraft,
  defaultCommandForCliKind,
  defaultModelForCliKind,
  DEFAULT_RULE_DIR,
  DEFAULT_SKILL_DIR,
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
  toRuntimeGraphDraft,
  updateEdge,
  type BlueprintAddNodeKind,
  type BlueprintAgentNode,
  type BlueprintCliKind,
  type BlueprintConfig,
  type BlueprintDraft,
  type BlueprintEdge,
  type BlueprintNodeLayout,
  type BlueprintRouteNode,
  type BlueprintTerminalKind,
} from "@/pages/session/blueprint-model"
import { usePlatform, type BlueprintCatalogItem } from "@/context/platform"

const NODE_WIDTH = 172
const NODE_HEIGHT = 72
const TERMINAL_WIDTH = 92
const TERMINAL_HEIGHT = 44
const MIN_ZOOM = 0.35
const MAX_ZOOM = 1.8
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

const DEFAULT_SKILL_CATALOG: BlueprintCatalogItem[] = [
  {
    value: "multi-agent-tcp",
    label: "multi-agent-tcp",
    description: "GuLiCode desktop blueprint and multi-agent runtime work.",
  },
]

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

type ConnectionState = {
  source: string
  output_port: string
  pointer?: BlueprintNodeLayout
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
  const { params, view } = useSessionLayout()
  const projectDirectory = decode64(params.dir) ?? "global"
  const [draft, setDraft, _, draftReady] = persisted(
    Persist.workspace(projectDirectory, "blueprint-draft.v1"),
    createStore<BlueprintDraft>(createDefaultBlueprintDraft(projectDirectory)),
  )
  const [drag, setDrag] = createSignal<DragState>()
  const [connection, setConnection] = createSignal<ConnectionState>()
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
  let canvasRef: HTMLDivElement | undefined

  const addOptions = createMemo(() => [
    {
      kind: "agent" as const,
      label: language.t("blueprint.node.agent"),
      description: language.t("blueprint.add.agent.description"),
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
    project_workdir: draft.config?.project_workdir || projectDirectory || ".",
    skill_dir: draft.config?.skill_dir || DEFAULT_SKILL_DIR,
    rule_dir: draft.config?.rule_dir || DEFAULT_RULE_DIR,
  }))

  const updateConfigField = <K extends keyof BlueprintConfig>(field: K, value: BlueprintConfig[K]) => {
    setDraft("config", field, value as never)
  }

  const replaceDraft = (next: BlueprintDraft) => {
    setDraft(reconcile(next))
  }

  const listSkills = async (skillDir: string) => {
    if (!skillDir) return [] as BlueprintCatalogItem[]
    const items = await platform.listBlueprintSkills?.(skillDir)
    return items ?? (skillDir === DEFAULT_SKILL_DIR ? DEFAULT_SKILL_CATALOG : [])
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

  const selectNode = (id: string) => {
    replaceDraft(setSelection(draft, { type: "node", id }))
  }

  const inspectNode = (id: string) => {
    replaceDraft(setInspector(setSelection(draft, { type: "node", id }), { type: "node", id }))
  }

  const inspectEdge = (id: string) => {
    replaceDraft(setInspector(setSelection(draft, { type: "edge", id }), { type: "edge", id }))
  }

  const closeInspector = () => {
    replaceDraft(setInspector(draft, undefined))
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

  const handleNodePointerDown = (event: PointerEvent, id: string) => {
    if (event.button === 2) {
      event.stopPropagation()
      selectNode(id)
      return
    }
    if (event.button !== 0) return
    event.stopPropagation()

    selectNode(id)
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

  const handleOutputPortPointerDown = (event: PointerEvent, id: string) => {
    if (event.button !== 0) return
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
    event.preventDefault()
    event.stopPropagation()
    if (current.source !== id) {
      replaceDraft(addEdge(draft, current.source, id, "exec", current.output_port, DEFAULT_INPUT_PORT))
    }
    setConnection(undefined)
  }

  const handlePointerMove = (event: PointerEvent) => {
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

    if (!draft.layout.nodes[current.id]) return
    const snapped = snapPosition({
      x: current.startX + (event.clientX - current.startClientX) / current.zoom,
      y: current.startY + (event.clientY - current.startClientY) / current.zoom,
    })
    setDraft("layout", "nodes", current.id, snapped)
  }

  const handlePointerUp = (event: PointerEvent) => {
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
    window.addEventListener("dragover", handleWindowDragOver, true)
    window.addEventListener("drop", handleWindowDrop, true)
    onCleanup(() => {
      window.removeEventListener("pointermove", handlePointerMove)
      window.removeEventListener("pointerup", handlePointerUp)
      window.removeEventListener("dragover", handleWindowDragOver, true)
      window.removeEventListener("drop", handleWindowDrop, true)
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
                      <Icon size="small" name={option.kind === "agent" ? "blueprint" : "branch"} />
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
            "cursor-grabbing": drag()?.type === "pan",
            "cursor-default": drag()?.type !== "pan",
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
                  const path = createMemo(() => edgePath(draft, edge))
                  const selected = createMemo(() => draft.selection?.type === "edge" && draft.selection.id === edge.id)
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
                {(current) => {
                  const path = createMemo(() => connectionPath(draft, current()))
                  return (
                    <path
                      d={path()}
                      fill="none"
                      stroke="var(--blueprint-edge-active)"
                      stroke-width="1.5"
                      stroke-dasharray="4 4"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      marker-end="url(#blueprint-arrow-active)"
                      style={{ "pointer-events": "none" }}
                    />
                  )
                }}
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
                  layout={draft.layout.nodes[item.id]}
                  onPointerDown={(event) => handleNodePointerDown(event, item.id)}
                  onDoubleClick={() => inspectNode(item.id)}
                  onDelete={() => replaceDraft(deleteNode(draft, item.id))}
                  onEdit={() => inspectNode(item.id)}
                  onOutputPointerDown={(event) => handleOutputPortPointerDown(event, item.id)}
                  onInputPointerUp={(event) => handleInputPortPointerUp(event, item.id)}
                />
              )}
            </For>
          </div>
        </div>

        <Show when={inspectorOpen()}>
          <div
            class="w-[300px] max-w-[40%] min-w-[252px] shrink-0 border-l border-[rgba(103,232,249,0.16)] bg-[#071019] shadow-[-20px_0_48px_rgba(0,0,0,0.42)]"
            style={BLUEPRINT_INSPECTOR_THEME}
          >
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
          </div>
        </Show>
      </div>
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
  layout?: BlueprintNodeLayout
  onPointerDown: (event: PointerEvent) => void
  onDoubleClick: () => void
  onDelete: () => void
  onEdit: () => void
  onOutputPointerDown: (event: PointerEvent) => void
  onInputPointerUp: (event: PointerEvent) => void
}) {
  const language = useLanguage()
  const width = () => (props.item.type === "terminal" ? TERMINAL_WIDTH : NODE_WIDTH)
  const height = () => (props.item.type === "terminal" ? TERMINAL_HEIGHT : NODE_HEIGHT)
  const showInput = () => props.item.type !== "terminal" || props.item.kind === "end"
  const showOutput = () => props.item.type !== "terminal" || props.item.kind === "start"
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
        </div>
      </ContextMenu.Trigger>
      <ContextMenu.Portal>
        <ContextMenu.Content>
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
          value={props.config.project_workdir}
          onChange={(value) => props.onConfigChange("project_workdir", value)}
          onBrowse={() =>
            void pickDirectory("project_workdir", language.t("blueprint.directory.pickProject"), props.config.project_workdir)
          }
        />
        <DirectoryConfigField
          label={language.t("blueprint.field.skillDir")}
          value={props.config.skill_dir}
          note={props.skillError ? language.t("blueprint.catalog.loadFailed") : language.t("blueprint.catalog.count", { count: props.skillCount })}
          onChange={(value) => props.onConfigChange("skill_dir", value)}
          onBrowse={() => void pickDirectory("skill_dir", language.t("blueprint.directory.pickSkill"), props.config.skill_dir)}
        />
        <DirectoryConfigField
          label={language.t("blueprint.field.ruleDir")}
          value={props.config.rule_dir}
          note={props.ruleError ? language.t("blueprint.catalog.loadFailed") : language.t("blueprint.catalog.count", { count: props.ruleCount })}
          onChange={(value) => props.onConfigChange("rule_dir", value)}
          onBrowse={() => void pickDirectory("rule_dir", language.t("blueprint.directory.pickRule"), props.config.rule_dir)}
        />
      </div>
    </div>
  )
}

function DirectoryConfigField(props: {
  label: string
  value: string
  note?: string
  onChange: (value: string) => void
  onBrowse: () => void
}) {
  return (
    <label class="flex min-w-0 flex-col gap-1">
      <span class="text-11-medium text-[#f8fdff]">{props.label}</span>
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
    </label>
  )
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

function InspectorFieldHeader(props: { label: string; tip?: InspectorTipKey }) {
  return (
    <div class="flex min-w-0 items-center gap-1 text-12-medium text-[#f8fdff]">
      <span class="min-w-0 truncate">{props.label}</span>
      <Show when={props.tip}>
        {(tip) => <InspectorTipButton label={props.label} tip={tip()} />}
      </Show>
    </div>
  )
}

function InspectorTipButton(props: { label: string; tip: InspectorTipKey }) {
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
      placement="left-start"
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
