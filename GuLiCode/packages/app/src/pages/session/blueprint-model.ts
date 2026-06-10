export const GRID_SIZE = 24
export const DEFAULT_OUTPUT_PORT = "out"
export const DEFAULT_INPUT_PORT = "in"
export const AGENT_PROMPT_INPUT_PORT = "prompt"
export const DEFAULT_BLUEPRINT_ID = "default"
export const DEFAULT_BLUEPRINT_NAME = "Default Blueprint"

export type BlueprintExecutionMode = "blocking" | "nonblocking"
export type BlueprintTerminalKind = "start" | "end"
export type BlueprintRouteKind = "sequence" | "parallel" | "parallel_reduce"
export type BlueprintCommonNodeKind = "branch" | "tick"
export type BlueprintPortDataType = "message" | "bool" | "tick" | "str"
export type BlueprintPromptViaFile = "auto" | "always" | "never"
export type BlueprintPromptTrigger = "once" | "always"
export type BlueprintAgentNodeType = "agent" | "worker_agent"
export type BlueprintNodeKind = "agent" | "route" | "terminal" | "script" | "common" | "prompt"
export type BlueprintAddNodeKind =
  | "agent"
  | "worker-agent"
  | "test-agent"
  | "prompt"
  | "script"
  | "branch"
  | "tick"
  | "route-sequence"
  | "route-parallel"
  | "route-parallel-reduce"
  | "start"
  | "end"
export type BlueprintCliKind = "codex"

export type BlueprintSkillSelection = {
  mode: "none" | "all" | "selected" | "upstream"
  skill_hashes?: string[]
  assigned_by?: string
}

export type BlueprintAgentAccessPolicy = {
  direct_project_io: boolean
  outside_project_io: boolean
  unrestricted_commands: boolean
  disable_sandbox: boolean
  framework_message_tools: boolean
  blueprint_monitor_tools: boolean
}

export type BlueprintConfig = {
  python_path: string
  project_workdir: string
  skill_dir: string
  skill_dirs: string[]
  rule_dir: string
  rule_dirs: string[]
}

export type BlueprintPopoEntry = {
  enabled: boolean
  robot_app_key: string
  robot_name: string
  robot_app_secret: string
  callback_token: string
  aes_key: string
}

export type BlueprintConfigField = keyof BlueprintConfig

export type BlueprintConfigValidationIssue = {
  field: BlueprintConfigField
  reason: "missing" | "not_absolute"
}

export type BlueprintAgentNode = {
  node_id: string
  node_type: BlueprintAgentNodeType
  agent_id?: string
  popo_entry: BlueprintPopoEntry
  prompt: string
  run_prompt: string
  collapsed: boolean
  execution_mode: BlueprintExecutionMode
  cli_kind: string
  model: string
  cwd: string
  skills: string[]
  skill_selection: BlueprintSkillSelection
  rule_paths: string[]
  timeout_sec: number
  prompt_via_file: BlueprintPromptViaFile
  command: string
  adapter_options: Record<string, unknown>
  extra_env: Record<string, string>
  external: boolean
  workspace_id?: string
  workspace_root?: string
  read_scope: string[]
  write_scope: string[]
  artifact_scope: string[]
  access_policy: BlueprintAgentAccessPolicy
}

type LegacyBlueprintAgentNode = Partial<BlueprintAgentNode> & {
  prompt_input_enabled?: unknown
  popoEntry?: Partial<BlueprintPopoEntry>
}

export type BlueprintRouteNode = {
  node_id: string
  route_kind: BlueprintRouteKind
  targets: string[]
  reduce_target?: string
  reduce_prompt?: string
}

export type BlueprintScriptPort = {
  name: string
  type: string
  required?: boolean
}

export type BlueprintScriptNode = {
  node_id: string
  script_id: string
  module_path: string
  function_name: string
  title: string
  description: string
  inputs: BlueprintScriptPort[]
  outputs: BlueprintScriptPort[]
  collapsed: boolean
  feedback_only?: boolean
  require_call_before_dispatch?: boolean
}

export type BlueprintPromptNode = {
  node_id: string
  text: string
  trigger: BlueprintPromptTrigger
  expanded: boolean
}

export type BlueprintCommonNode =
  | {
      node_id: string
      kind: "branch"
    }
  | {
      node_id: string
      kind: "tick"
      every_n_seconds: number
    }

export type BlueprintPortConnectResult = {
  ok: boolean
  reason?: "unknown_node" | "unknown_port" | "type_mismatch"
  sourceType?: BlueprintPortDataType
  targetType?: BlueprintPortDataType
}

export type BlueprintScriptCompileResult = {
  draft: BlueprintDraft
  updated: number
  missing: number
  removedEdges: number
}

export type BlueprintEdge = {
  id: string
  from: string
  to: string
  edge_type: string
  output_port?: string
  input_port?: string
}

export type BlueprintAgentRingEdgePair = {
  from: string
  to: string
}

export type BlueprintAgentRing = {
  ring_id: string
  topology_id: string
  ordered_node_ids: string[]
  edge_node_pairs: BlueprintAgentRingEdgePair[]
  closing_edge: BlueprintAgentRingEdgePair
  max_circulations: number
  context_refresh_period: number
  visual_edge_ids: string[]
}

export type BlueprintNodeLayout = {
  x: number
  y: number
}

export type BlueprintViewport = {
  x: number
  y: number
  zoom: number
}

export type BlueprintSelection =
  | {
      type: "node"
      id: string
    }
  | {
      type: "edge"
      id: string
    }

export type BlueprintInspectable =
  | {
      type: "node"
      id: string
    }
  | {
      type: "edge"
      id: string
    }

export type BlueprintDraft = {
  schema_version: 1
  config: BlueprintConfig
  runtime: {
    start_node_id: string
    popo_entry: BlueprintPopoEntry
  }
  graph: {
    agent_nodes: Record<string, BlueprintAgentNode>
    route_nodes: Record<string, BlueprintRouteNode>
    terminal_nodes: Record<string, BlueprintTerminalKind>
    prompt_nodes: Record<string, BlueprintPromptNode>
    script_nodes: Record<string, BlueprintScriptNode>
    common_nodes: Record<string, BlueprintCommonNode>
    edges: BlueprintEdge[]
    agent_ring_max_circulations: Record<string, number>
    agent_ring_context_refresh_periods: Record<string, number>
  }
  layout: {
    nodes: Record<string, BlueprintNodeLayout>
    viewport: BlueprintViewport
  }
  selection?: BlueprintSelection
  inspector?: BlueprintInspectable
}

export type RuntimeGraphDraft = {
  terminal_nodes: Record<string, BlueprintTerminalKind>
  agent_nodes: Record<string, BlueprintAgentNode>
  route_nodes: Record<string, BlueprintRouteNode>
  common_nodes?: Record<string, BlueprintCommonNode>
  script_nodes?: Record<string, BlueprintScriptNode>
  prompt_nodes?: Record<string, BlueprintPromptNode>
  agent_ring_max_circulations?: Record<string, number>
  agent_ring_context_refresh_periods?: Record<string, number>
  edges: Array<{
    from: string
    to: string
    edge_type: string
    output_port?: string
    input_port?: string
  }>
}

export type BlueprintDocument = {
  schema_version: 1
  id: string
  name: string
  graph: RuntimeGraphDraft
  runtime?: {
    start_node_id?: string
    startNodeId?: string
    popo_entry?: Partial<BlueprintPopoEntry>
    popoEntry?: Partial<BlueprintPopoEntry>
  }
  ui: {
    config: BlueprintConfig
    nodes: Record<string, BlueprintNodeLayout>
    viewport: BlueprintViewport
    selection?: BlueprintSelection
    inspector?: BlueprintInspectable
  }
}

const DEFAULT_VIEWPORT: BlueprintViewport = {
  x: 48,
  y: 96,
  zoom: 1,
}

const DEFAULT_AGENT_SCOPE = ["**"]
const LEGACY_REPORT_ONLY_AGENT_SCOPE = ["shared/reports/**"]
const DEFAULT_MODEL = "gpt-5.4"
const DEFAULT_PROJECT_WORKDIR = "."
export const DEFAULT_PYTHON_PATH = ""
export const DEFAULT_SKILL_DIR = ""
export const DEFAULT_RULE_DIR = ""
export const CLI_KIND_OPTIONS: BlueprintCliKind[] = ["codex"]
export const TEST_AGENT_NODE_FLAG = "gulicode_test_node"
const TEST_AGENT_TIMEOUT_SEC = 1800
const DANGEROUS_CODEX_EXTRA_ARGS = ["--dangerously-bypass-approvals-and-sandbox"]

export const DEFAULT_AGENT_ACCESS_POLICY: BlueprintAgentAccessPolicy = {
  direct_project_io: true,
  outside_project_io: true,
  unrestricted_commands: true,
  disable_sandbox: true,
  framework_message_tools: true,
  blueprint_monitor_tools: false,
}

export const DEFAULT_WORKER_AGENT_ACCESS_POLICY: BlueprintAgentAccessPolicy = {
  direct_project_io: false,
  outside_project_io: false,
  unrestricted_commands: false,
  disable_sandbox: false,
  framework_message_tools: true,
  blueprint_monitor_tools: false,
}

export function defaultCommandForCliKind(cliKind: string) {
  return "codex"
}

export function defaultModelForCliKind(cliKind: string) {
  return DEFAULT_MODEL
}

export function createDefaultBlueprintConfig(projectWorkdir = DEFAULT_PROJECT_WORKDIR): BlueprintConfig {
  return {
    python_path: DEFAULT_PYTHON_PATH,
    project_workdir: projectWorkdir || DEFAULT_PROJECT_WORKDIR,
    skill_dir: DEFAULT_SKILL_DIR,
    skill_dirs: [],
    rule_dir: DEFAULT_RULE_DIR,
    rule_dirs: [],
  }
}

export function createDefaultPopoEntry(): BlueprintPopoEntry {
  return {
    enabled: false,
    robot_app_key: "",
    robot_name: "",
    robot_app_secret: "",
    callback_token: "",
    aes_key: "",
  }
}

export function popoEntryHasValues(entry?: Partial<BlueprintPopoEntry>): boolean {
  const normalized = normalizePopoEntry(entry)
  return (
    normalized.enabled ||
    Boolean(
      normalized.robot_app_key ||
        normalized.robot_name ||
        normalized.robot_app_secret ||
        normalized.callback_token ||
        normalized.aes_key,
    )
  )
}

function agentNode(input: {
  node_id: string
  agent_id: string
  prompt: string
  node_type?: BlueprintAgentNodeType
  write_scope?: string[]
  artifact_scope?: string[]
}): BlueprintAgentNode {
  return createAgentNode({
    node_id: input.node_id,
    agent_id: input.agent_id,
    prompt: input.prompt,
    node_type: input.node_type ?? "worker_agent",
    write_scope: input.write_scope ?? DEFAULT_AGENT_SCOPE,
    artifact_scope: input.artifact_scope ?? [],
  })
}

export function createDefaultBlueprintDraft(projectWorkdir = DEFAULT_PROJECT_WORKDIR): BlueprintDraft {
  return {
    schema_version: 1,
    config: createDefaultBlueprintConfig(projectWorkdir),
    runtime: {
      start_node_id: "planner",
      popo_entry: createDefaultPopoEntry(),
    },
    graph: {
      terminal_nodes: {},
      route_nodes: {},
      prompt_nodes: {},
      script_nodes: {},
      common_nodes: {},
      agent_nodes: {
        planner: agentNode({
          node_id: "planner",
          node_type: "agent",
          agent_id: "agent-planner",
          prompt: "Break down the user goal and dispatch implementation work.",
          write_scope: ["shared/reports/planning/**"],
        }),
        coder: agentNode({
          node_id: "coder",
          agent_id: "agent-coder",
          prompt: "Implement the requested changes.",
          write_scope: ["src/**"],
          artifact_scope: ["shared/artifacts/code/**"],
        }),
        review: agentNode({
          node_id: "review",
          agent_id: "agent-review",
          prompt: "Review implementation output and identify required fixes.",
          write_scope: ["shared/reports/review/**"],
        }),
        summary: agentNode({
          node_id: "summary",
          agent_id: "agent-summary",
          prompt: "Summarize the run and prepare final records.",
          write_scope: ["shared/reports/**"],
        }),
      },
      edges: [
        createEdge("planner", "coder"),
        createEdge("coder", "review"),
        createEdge("review", "summary"),
      ],
      agent_ring_max_circulations: {},
      agent_ring_context_refresh_periods: {},
    },
    layout: {
      nodes: {
        planner: { x: 0, y: 96 },
        coder: { x: 240, y: 96 },
        review: { x: 480, y: 96 },
        summary: { x: 720, y: 96 },
      },
      viewport: { ...DEFAULT_VIEWPORT },
    },
  }
}

export function cloneBlueprintDraft(draft: BlueprintDraft): BlueprintDraft {
  return {
    schema_version: 1,
    config: normalizeBlueprintConfig(draft.config),
    runtime: {
      start_node_id: draft.runtime?.start_node_id?.trim() ?? "",
      popo_entry: createDefaultPopoEntry(),
    },
    graph: {
      terminal_nodes: { ...draft.graph.terminal_nodes },
      route_nodes: Object.fromEntries(
        Object.entries(draft.graph.route_nodes ?? {}).map(([id, node]) => [id, normalizeRouteNode(id, node)]),
      ),
      common_nodes: Object.fromEntries(
        Object.entries(draft.graph.common_nodes ?? {}).map(([id, node]) => [id, normalizeCommonNode(id, node)]),
      ),
      prompt_nodes: Object.fromEntries(
        Object.entries(draft.graph.prompt_nodes ?? {}).map(([id, node]) => [id, normalizePromptNode(id, node)]),
      ),
      script_nodes: Object.fromEntries(
        Object.entries(draft.graph.script_nodes ?? {}).map(([id, node]) => [id, normalizeScriptNode(id, node)]),
      ),
      agent_nodes: Object.fromEntries(
        Object.entries(draft.graph.agent_nodes).map(([id, node]) => [id, normalizeAgentNode(id, node)]),
      ),
      edges: draft.graph.edges.map((edge) => ({ ...edge })),
      agent_ring_max_circulations: normalizeRingNumberRecord(draft.graph.agent_ring_max_circulations, 0),
      agent_ring_context_refresh_periods: normalizeRingNumberRecord(draft.graph.agent_ring_context_refresh_periods, 1),
    },
    layout: {
      nodes: Object.fromEntries(Object.entries(draft.layout.nodes).map(([id, layout]) => [id, { ...layout }])),
      viewport: { ...draft.layout.viewport },
    },
    selection: draft.selection ? { ...draft.selection } : undefined,
    inspector: draft.inspector ? { ...draft.inspector } : undefined,
  }
}

export function toBlueprintDocument(
  draft: BlueprintDraft,
  id = DEFAULT_BLUEPRINT_ID,
  name = DEFAULT_BLUEPRINT_NAME,
): BlueprintDocument {
  return {
    schema_version: 1,
    id,
    name,
    graph: toRuntimeGraphDraft(draft),
    runtime: {
      start_node_id: draft.runtime?.start_node_id?.trim() ?? "",
      popo_entry: createDefaultPopoEntry(),
    },
    ui: {
      config: normalizeBlueprintConfig(draft.config),
      nodes: visibleLayoutNodes(draft),
      viewport: { ...draft.layout.viewport },
      selection: visibleInspectable(draft, draft.selection),
      inspector: visibleInspectable(draft, draft.inspector),
    },
  }
}

export function fromBlueprintDocument(
  document: Partial<BlueprintDocument>,
  projectWorkdir = DEFAULT_PROJECT_WORKDIR,
): BlueprintDraft {
  const fallback = createDefaultBlueprintDraft(projectWorkdir)
  const graph = (document.graph ?? fallback.graph) as RuntimeGraphDraft
  const ui = (document.ui ?? {}) as Partial<BlueprintDocument["ui"]>
  const runtime = (document.runtime ?? {}) as NonNullable<BlueprintDocument["runtime"]>
  const startNodeId = String(runtime.start_node_id ?? runtime.startNodeId ?? fallback.runtime.start_node_id ?? "").trim()
  const legacyRuntimePopoEntry = normalizePopoEntry(runtime.popo_entry ?? runtime.popoEntry ?? fallback.runtime.popo_entry)
  const agentNodes = Object.fromEntries(
    Object.entries(graph.agent_nodes ?? fallback.graph.agent_nodes).map(([id, node]) => [
      id,
      normalizeAgentNode(id, node),
    ]),
  )
  if (
    popoEntryHasValues(legacyRuntimePopoEntry) &&
    !Object.values(agentNodes).some((node) => node.node_type === "agent" && popoEntryHasValues(node.popo_entry))
  ) {
    const startNode = agentNodes[startNodeId]
    if (startNode?.node_type === "agent") {
      agentNodes[startNodeId] = {
        ...startNode,
        popo_entry: legacyRuntimePopoEntry,
      }
    }
  }
  return cloneBlueprintDraft({
    schema_version: 1,
    config: normalizeBlueprintConfig(ui.config ?? fallback.config),
    runtime: {
      start_node_id: startNodeId,
      popo_entry: createDefaultPopoEntry(),
    },
    graph: {
      terminal_nodes: { ...(graph.terminal_nodes ?? fallback.graph.terminal_nodes) },
      route_nodes: Object.fromEntries(
        Object.entries(graph.route_nodes ?? {}).map(([id, node]) => [id, normalizeRouteNode(id, node)]),
      ),
      common_nodes: Object.fromEntries(
        Object.entries(graph.common_nodes ?? {}).map(([id, node]) => [id, normalizeCommonNode(id, node)]),
      ),
      prompt_nodes: Object.fromEntries(
        Object.entries(graph.prompt_nodes ?? {}).map(([id, node]) => [id, normalizePromptNode(id, node)]),
      ),
      script_nodes: Object.fromEntries(
        Object.entries(graph.script_nodes ?? {}).map(([id, node]) => [id, normalizeScriptNode(id, node)]),
      ),
      agent_nodes: agentNodes,
      edges: (graph.edges ?? fallback.graph.edges).map((edge) => ({
        id: edgeId(
          edge.from,
          edge.to,
          edge.edge_type || "exec",
          edge.output_port ?? DEFAULT_OUTPUT_PORT,
          edge.input_port ?? DEFAULT_INPUT_PORT,
        ),
        from: edge.from,
        to: edge.to,
        edge_type: edge.edge_type || "exec",
        output_port: edge.output_port ?? DEFAULT_OUTPUT_PORT,
        input_port: edge.input_port ?? DEFAULT_INPUT_PORT,
      })),
      agent_ring_max_circulations: normalizeRingNumberRecord(graph.agent_ring_max_circulations, 0),
      agent_ring_context_refresh_periods: normalizeRingNumberRecord(graph.agent_ring_context_refresh_periods, 1),
    },
    layout: {
      nodes: Object.fromEntries(
        Object.entries(ui.nodes ?? fallback.layout.nodes).map(([nodeId, layout]) => [nodeId, { ...layout }]),
      ),
      viewport: { ...(ui.viewport ?? fallback.layout.viewport) },
    },
    selection: ui.selection ? { ...ui.selection } : undefined,
    inspector: ui.inspector ? { ...ui.inspector } : undefined,
  })
}

export function createEdge(
  from: string,
  to: string,
  edgeType = "exec",
  outputPort = DEFAULT_OUTPUT_PORT,
  inputPort = DEFAULT_INPUT_PORT,
): BlueprintEdge {
  return {
    id: edgeId(from, to, edgeType, outputPort, inputPort),
    from,
    to,
    edge_type: edgeType,
    output_port: outputPort,
    input_port: inputPort,
  }
}

export function edgeId(
  from: string,
  to: string,
  edgeType = "exec",
  outputPort = DEFAULT_OUTPUT_PORT,
  inputPort = DEFAULT_INPUT_PORT,
) {
  return `${from}:${outputPort}->${to}:${inputPort}:${edgeType}`
}

export function nodeIds(draft: BlueprintDraft) {
  return [
    ...Object.keys(draft.graph.terminal_nodes),
    ...Object.keys(draft.graph.route_nodes ?? {}),
    ...Object.keys(draft.graph.common_nodes ?? {}),
    ...Object.keys(draft.graph.prompt_nodes ?? {}),
    ...Object.keys(draft.graph.script_nodes ?? {}),
    ...Object.keys(draft.graph.agent_nodes),
  ]
}

export function nodeKind(draft: BlueprintDraft, id: string): BlueprintNodeKind | undefined {
  if (isAgentNode(draft, id)) return "agent"
  if (isRouteNode(draft, id)) return "route"
  if (isTerminalNode(draft, id)) return "terminal"
  if (isPromptNode(draft, id)) return "prompt"
  if (isScriptNode(draft, id)) return "script"
  if (isCommonNode(draft, id)) return "common"
}

export function isTerminalNode(draft: BlueprintDraft, id: string) {
  return draft.graph.terminal_nodes[id] !== undefined
}

export function isAgentNode(draft: BlueprintDraft, id: string) {
  return draft.graph.agent_nodes[id] !== undefined
}

export function isRouteNode(draft: BlueprintDraft, id: string) {
  return draft.graph.route_nodes?.[id] !== undefined
}

export function isScriptNode(draft: BlueprintDraft, id: string) {
  return draft.graph.script_nodes?.[id] !== undefined
}

export function isCommonNode(draft: BlueprintDraft, id: string) {
  return draft.graph.common_nodes?.[id] !== undefined
}

export function isPromptNode(draft: BlueprintDraft, id: string) {
  return draft.graph.prompt_nodes?.[id] !== undefined
}

export function addNode(
  draft: BlueprintDraft,
  input: {
    kind: BlueprintAddNodeKind
    node_id?: string
    position?: BlueprintNodeLayout
  },
) {
  if (input.kind === "agent") return addFullAgentNode(draft, input)
  if (input.kind === "worker-agent" || input.kind === "test-agent") return addAgentNode(draft, input)
  if (input.kind === "prompt") return addPromptNode(draft, input)
  if (input.kind === "script") return addScriptNode(draft, input)
  if (input.kind === "branch" || input.kind === "tick") return addCommonNode(draft, input.kind, input)
  if (input.kind === "start" || input.kind === "end") return addTerminalNode(draft, input.kind, input)
  return addRouteNode(draft, routeKindFromAddKind(input.kind), input)
}

export function addFullAgentNode(
  draft: BlueprintDraft,
  input: {
    node_id?: string
    position?: BlueprintNodeLayout
  } = {},
) {
  const next = cloneBlueprintDraft(draft)
  const node_id = uniqueNodeId(next, input.node_id ?? "agent")
  next.graph.agent_nodes[node_id] = createAgentNode({
    node_id,
    node_type: "agent",
    agent_id: `agent-${node_id}`,
    prompt: "Describe this full CLI agent's work.",
  })
  next.layout.nodes[node_id] = snapPosition(input.position ?? nextNodePosition(next))
  next.selection = { type: "node", id: node_id }
  next.inspector = { type: "node", id: node_id }
  return next
}

export function addAgentNode(
  draft: BlueprintDraft,
  input: {
    node_id?: string
    position?: BlueprintNodeLayout
  } = {},
) {
  const next = cloneBlueprintDraft(draft)
  const node_id = uniqueNodeId(next, input.node_id ?? "agent")
  next.graph.agent_nodes[node_id] = createAgentNode({
    node_id,
    node_type: "worker_agent",
    agent_id: `agent-${node_id}`,
    prompt: "Describe this worker's work.",
  })
  next.layout.nodes[node_id] = snapPosition(input.position ?? nextNodePosition(next))
  next.selection = { type: "node", id: node_id }
  next.inspector = { type: "node", id: node_id }
  return next
}

export function addTestAgentNode(
  draft: BlueprintDraft,
  input: {
    node_id?: string
    position?: BlueprintNodeLayout
  } = {},
) {
  return addAgentNode(draft, input)
}

export function addPromptNode(
  draft: BlueprintDraft,
  input: {
    node_id?: string
    position?: BlueprintNodeLayout
  } = {},
) {
  const next = cloneBlueprintDraft(draft)
  const node_id = uniqueNodeId(next, input.node_id ?? "prompt")
  next.graph.prompt_nodes[node_id] = normalizePromptNode(node_id, {
    node_id,
    text: "",
    trigger: "once",
    expanded: false,
  })
  next.layout.nodes[node_id] = snapPosition(input.position ?? nextNodePosition(next))
  next.selection = { type: "node", id: node_id }
  next.inspector = { type: "node", id: node_id }
  return next
}

export function addRouteNode(
  draft: BlueprintDraft,
  route_kind: BlueprintRouteKind,
  input: {
    node_id?: string
    position?: BlueprintNodeLayout
  } = {},
) {
  const next = cloneBlueprintDraft(draft)
  const node_id = uniqueNodeId(next, input.node_id ?? route_kind.replace("_", "-"))
  next.graph.route_nodes[node_id] = {
    node_id,
    route_kind,
    targets: [],
    reduce_target: route_kind === "parallel_reduce" ? "" : undefined,
    reduce_prompt: route_kind === "parallel_reduce" ? "Merge and deduplicate:\n{results}" : undefined,
  }
  next.layout.nodes[node_id] = snapPosition(input.position ?? nextNodePosition(next))
  next.selection = { type: "node", id: node_id }
  next.inspector = { type: "node", id: node_id }
  return next
}

export function addCommonNode(
  draft: BlueprintDraft,
  kind: BlueprintCommonNodeKind,
  input: {
    node_id?: string
    position?: BlueprintNodeLayout
  } = {},
) {
  const next = cloneBlueprintDraft(draft)
  const node_id = uniqueNodeId(next, input.node_id ?? kind)
  next.graph.common_nodes[node_id] = normalizeCommonNode(node_id, {
    node_id,
    kind,
    every_n_seconds: kind === "tick" ? 1 : undefined,
  })
  next.layout.nodes[node_id] = snapPosition(input.position ?? nextNodePosition(next))
  next.selection = { type: "node", id: node_id }
  next.inspector = { type: "node", id: node_id }
  return next
}

export function addScriptNode(
  draft: BlueprintDraft,
  input: {
    node_id?: string
    position?: BlueprintNodeLayout
    script?: Partial<BlueprintScriptNode>
  } = {},
) {
  const next = cloneBlueprintDraft(draft)
  const script = input.script ?? {}
  const preferred = script.function_name || script.title || input.node_id || "function"
  const node_id = uniqueNodeId(next, input.node_id ?? sanitizeNodeId(preferred))
  next.graph.script_nodes[node_id] = normalizeScriptNode(node_id, {
    node_id,
    script_id: script.script_id ?? `${script.module_path ?? ""}:${script.function_name ?? ""}`,
    module_path: script.module_path ?? "",
    function_name: script.function_name ?? "",
    title: script.title ?? script.function_name ?? node_id,
    description: script.description ?? "",
    inputs: script.inputs ?? [],
    outputs: script.outputs ?? [{ name: "result", type: "Any", required: true }],
    collapsed: script.collapsed ?? true,
    feedback_only: script.feedback_only ?? isTableQueueServiceScript(script),
    require_call_before_dispatch: script.require_call_before_dispatch ?? isTableQueueServiceScript(script),
  })
  next.layout.nodes[node_id] = snapPosition(input.position ?? nextNodePosition(next))
  next.selection = { type: "node", id: node_id }
  next.inspector = { type: "node", id: node_id }
  return next
}

export function addTerminalNode(
  draft: BlueprintDraft,
  terminal_kind: BlueprintTerminalKind,
  input: {
    node_id?: string
    position?: BlueprintNodeLayout
  } = {},
) {
  const next = cloneBlueprintDraft(draft)
  const node_id = uniqueNodeId(next, input.node_id ?? terminal_kind)
  next.graph.terminal_nodes[node_id] = terminal_kind
  next.layout.nodes[node_id] = snapPosition(input.position ?? nextNodePosition(next))
  next.selection = { type: "node", id: node_id }
  next.inspector = { type: "node", id: node_id }
  return next
}

export function addEdge(
  draft: BlueprintDraft,
  from: string,
  to: string,
  edgeType = "exec",
  outputPort = DEFAULT_OUTPUT_PORT,
  inputPort = DEFAULT_INPUT_PORT,
) {
  const next = cloneBlueprintDraft(draft)
  if (from === to) return next
  if (!nodeIds(next).includes(from) || !nodeIds(next).includes(to)) return next
  const normalizedEdgeType = edgeTypeForPorts(next, from, outputPort, to, inputPort, edgeType)
  const ports = expandedScriptFanPorts(next, from, outputPort, to, inputPort)
  for (const port of ports) {
    if (!canConnectPorts(next, from, port.outputPort, to, port.inputPort).ok) return next
  }
  for (const port of ports) {
    const portEdgeType = edgeTypeForPorts(next, from, port.outputPort, to, port.inputPort, normalizedEdgeType)
    const id = edgeId(from, to, portEdgeType, port.outputPort, port.inputPort)
    if (
      !next.graph.edges.some(
        (edge) =>
          edge.id === id ||
          (edge.from === from &&
            edge.to === to &&
            edge.edge_type === portEdgeType &&
            (edge.output_port || DEFAULT_OUTPUT_PORT) === port.outputPort &&
            (edge.input_port || DEFAULT_INPUT_PORT) === port.inputPort),
      )
    ) {
      next.graph.edges.push(createEdge(from, to, portEdgeType, port.outputPort, port.inputPort))
    }
  }
  const selectedId = ports.some((port) => port.outputPort === outputPort && port.inputPort === inputPort)
    ? edgeId(from, to, normalizedEdgeType, outputPort, inputPort)
    : edgeId(
        from,
        to,
        edgeTypeForPorts(next, from, ports[0]?.outputPort ?? outputPort, to, ports[0]?.inputPort ?? inputPort, normalizedEdgeType),
        ports[0]?.outputPort ?? outputPort,
        ports[0]?.inputPort ?? inputPort,
      )
  next.selection = { type: "edge", id: selectedId }
  return next
}

type FanPortPair = {
  outputPort: string
  inputPort: string
}

function expandedScriptFanPorts(
  draft: BlueprintDraft,
  from: string,
  outputPort: string,
  to: string,
  inputPort: string,
): FanPortPair[] {
  const targetScript = draft.graph.script_nodes?.[to]
  if (targetScript && isAgentNode(draft, from)) {
    const inputs = scriptInputPortNames(targetScript)
    if (inputs.length > 1) return inputs.map((name) => ({ outputPort, inputPort: name }))
  }

  const sourceScript = draft.graph.script_nodes?.[from]
  if (sourceScript && isAgentNode(draft, to)) {
    const outputs = scriptOutputPortNames(sourceScript)
    if (outputs.length > 1) return outputs.map((name) => ({ outputPort: name, inputPort }))
  }

  return [{ outputPort, inputPort }]
}

function scriptInputPortNames(node: BlueprintScriptNode) {
  const names = node.inputs.map((port) => port.name).filter(Boolean)
  return names.length ? names : [DEFAULT_INPUT_PORT]
}

function scriptOutputPortNames(node: BlueprintScriptNode) {
  const names = node.outputs.map((port) => port.name).filter(Boolean)
  return names.length ? names : [DEFAULT_OUTPUT_PORT]
}

export function fanEdgeGroup(draft: BlueprintDraft, edge: BlueprintEdge): BlueprintEdge[] {
  const sourceScript = draft.graph.script_nodes?.[edge.from]
  const targetScript = draft.graph.script_nodes?.[edge.to]
  if (targetScript && isAgentNode(draft, edge.from) && scriptInputPortNames(targetScript).length > 1) {
    const allowedInputs = new Set(scriptInputPortNames(targetScript))
    const outputPort = edge.output_port || DEFAULT_OUTPUT_PORT
    return draft.graph.edges.filter(
      (item) =>
        item.from === edge.from &&
        item.to === edge.to &&
        item.edge_type === edge.edge_type &&
        (item.output_port || DEFAULT_OUTPUT_PORT) === outputPort &&
        allowedInputs.has(item.input_port || DEFAULT_INPUT_PORT),
    )
  }

  if (sourceScript && isAgentNode(draft, edge.to) && scriptOutputPortNames(sourceScript).length > 1) {
    const allowedOutputs = new Set(scriptOutputPortNames(sourceScript))
    const inputPort = edge.input_port || DEFAULT_INPUT_PORT
    return draft.graph.edges.filter(
      (item) =>
        item.from === edge.from &&
        item.to === edge.to &&
        item.edge_type === edge.edge_type &&
        (item.input_port || DEFAULT_INPUT_PORT) === inputPort &&
        allowedOutputs.has(item.output_port || DEFAULT_OUTPUT_PORT),
    )
  }

  return [edge]
}

type AgentRingConnection = {
  target: string
  edgeIds: string[]
}

export function agentRingConfigKey(ring: Pick<BlueprintAgentRing, "topology_id" | "ring_id">) {
  return ring.topology_id || ring.ring_id
}

export function agentRingsForDraft(draft: BlueprintDraft): BlueprintAgentRing[] {
  const connections = agentConnectionsForRings(draft)
  const cycles: string[][] = []
  const seen = new Set<string>()
  const orderedAgentIds = Object.keys(draft.graph.agent_nodes).sort()

  function visit(start: string, current: string, path: string[]) {
    for (const connection of connections[current] ?? []) {
      const target = connection.target
      if (target === start) {
        if (path.length >= 2) {
          const key = path.join("\u0000")
          if (!seen.has(key)) {
            seen.add(key)
            cycles.push([...path])
          }
        }
        continue
      }
      if (path.includes(target)) continue
      if (target < start) continue
      visit(start, target, [...path, target])
    }
  }

  for (const start of orderedAgentIds) {
    visit(start, start, [start])
  }

  cycles.sort((left, right) => left.length - right.length || left.join("\u0000").localeCompare(right.join("\u0000")))
  return cycles.map((cycle, cycleIndex) => {
    const index = cycleIndex + 1
    const ringId = `ring${index}`
    const topologyId = `ring-${cycle.join("-")}`
    const edgeNodePairs = cycle.map((nodeId, nodeIndex) => ({
      from: nodeId,
      to: cycle[(nodeIndex + 1) % cycle.length]!,
    }))
    const visualEdgeIds = new Set<string>()
    for (const pair of edgeNodePairs) {
      const connection = (connections[pair.from] ?? []).find((item) => item.target === pair.to)
      for (const edgeIdValue of connection?.edgeIds ?? []) {
        visualEdgeIds.add(edgeIdValue)
      }
    }
    return {
      ring_id: ringId,
      topology_id: topologyId,
      ordered_node_ids: [...cycle],
      edge_node_pairs: edgeNodePairs,
      closing_edge: edgeNodePairs[edgeNodePairs.length - 1]!,
      max_circulations: configuredRingNumber(draft.graph.agent_ring_max_circulations, topologyId, ringId, index, 1, 0),
      context_refresh_period: configuredRingNumber(
        draft.graph.agent_ring_context_refresh_periods,
        topologyId,
        ringId,
        index,
        1,
        1,
      ),
      visual_edge_ids: [...visualEdgeIds],
    }
  })
}

function agentConnectionsForRings(draft: BlueprintDraft): Record<string, AgentRingConnection[]> {
  const connections: Record<string, AgentRingConnection[]> = Object.fromEntries(
    Object.keys(draft.graph.agent_nodes).map((nodeId) => [nodeId, []]),
  )
  for (const sourceId of Object.keys(draft.graph.agent_nodes).sort()) {
    for (const connection of agentTargetsThroughScripts(draft, sourceId)) {
      if (!connections[sourceId].some((item) => item.target === connection.target)) {
        connections[sourceId].push(connection)
      }
    }
  }
  return connections
}

function agentTargetsThroughScripts(draft: BlueprintDraft, sourceId: string): AgentRingConnection[] {
  const nodeSet = new Set(nodeIds(draft))
  const execEdges = draft.graph.edges
    .filter((edge) => (edge.edge_type || "exec") === "exec" && nodeSet.has(edge.from) && nodeSet.has(edge.to))
    .sort((left, right) => left.id.localeCompare(right.id))
  const edgesBySource = new Map<string, BlueprintEdge[]>()
  for (const edge of execEdges) {
    const items = edgesBySource.get(edge.from) ?? []
    items.push(edge)
    edgesBySource.set(edge.from, items)
  }
  const targets: AgentRingConnection[] = []
  const queue = (edgesBySource.get(sourceId) ?? []).map((edge) => ({
    nodeId: edge.to,
    edgeIds: [edge.id],
  }))
  const seen = new Set<string>([sourceId])
  while (queue.length > 0) {
    const current = queue.shift()
    if (!current) continue
    if (seen.has(current.nodeId)) continue
    seen.add(current.nodeId)
    if (draft.graph.agent_nodes[current.nodeId]) {
      targets.push({ target: current.nodeId, edgeIds: current.edgeIds })
      continue
    }
    if (!draft.graph.script_nodes?.[current.nodeId]) continue
    for (const edge of edgesBySource.get(current.nodeId) ?? []) {
      queue.push({ nodeId: edge.to, edgeIds: [...current.edgeIds, edge.id] })
    }
  }
  return targets
}

export function deleteNode(draft: BlueprintDraft, id: string) {
  const next = cloneBlueprintDraft(draft)
  if (!nodeIds(next).includes(id)) return next

  delete next.graph.agent_nodes[id]
  delete next.graph.route_nodes[id]
  delete next.graph.common_nodes[id]
  delete next.graph.terminal_nodes[id]
  delete next.graph.prompt_nodes[id]
  delete next.graph.script_nodes[id]
  delete next.layout.nodes[id]
  next.graph.edges = next.graph.edges.filter((edge) => edge.from !== id && edge.to !== id)
  clearDanglingSelectionAndInspector(next)
  return next
}

export function deleteEdge(draft: BlueprintDraft, id: string) {
  const next = cloneBlueprintDraft(draft)
  const target = next.graph.edges.find((edge) => edge.id === id)
  if (!target) return next
  const groupIds = new Set(fanEdgeGroup(next, target).map((edge) => edge.id))
  next.graph.edges = next.graph.edges.filter((edge) => !groupIds.has(edge.id))
  clearDanglingSelectionAndInspector(next)
  return next
}

export function deleteSelection(draft: BlueprintDraft) {
  if (!draft.selection) return cloneBlueprintDraft(draft)
  if (draft.selection.type === "node") return deleteNode(draft, draft.selection.id)
  return deleteEdge(draft, draft.selection.id)
}

export function updateAgentNode(draft: BlueprintDraft, id: string, patch: Partial<BlueprintAgentNode>) {
  const next = cloneBlueprintDraft(draft)
  const current = next.graph.agent_nodes[id]
  if (!current) return next
  const patchedNodeType = normalizeAgentNodeType(patch.node_type ?? current.node_type)
  next.graph.agent_nodes[id] = {
    ...current,
    ...patch,
    node_id: id,
    node_type: patchedNodeType,
    popo_entry:
      patchedNodeType === "agent"
        ? normalizePopoEntry(patch.popo_entry ?? current.popo_entry)
        : createDefaultPopoEntry(),
    skills: patch.skills ? [...patch.skills] : current.skills,
    skill_selection: patch.skill_selection ? cloneSkillSelection(patch.skill_selection) : cloneSkillSelection(current.skill_selection),
    rule_paths: patch.rule_paths ? [...patch.rule_paths] : current.rule_paths,
    adapter_options: patch.adapter_options ? { ...patch.adapter_options } : current.adapter_options,
    extra_env: patch.extra_env ? { ...patch.extra_env } : current.extra_env,
    read_scope: patch.read_scope ? [...patch.read_scope] : current.read_scope,
    write_scope: patch.write_scope ? [...patch.write_scope] : current.write_scope,
    artifact_scope: patch.artifact_scope ? [...patch.artifact_scope] : current.artifact_scope,
    access_policy: normalizeAgentAccessPolicy(patch.access_policy ?? current.access_policy, patchedNodeType),
  }
  return next
}

export function updatePromptNode(draft: BlueprintDraft, id: string, patch: Partial<BlueprintPromptNode>) {
  const next = cloneBlueprintDraft(draft)
  const current = next.graph.prompt_nodes[id]
  if (!current) return next
  next.graph.prompt_nodes[id] = normalizePromptNode(id, {
    ...current,
    ...patch,
  })
  return next
}

export function canConnectPorts(
  draft: BlueprintDraft,
  from: string,
  outputPort = DEFAULT_OUTPUT_PORT,
  to: string,
  inputPort = DEFAULT_INPUT_PORT,
): BlueprintPortConnectResult {
  if (!nodeIds(draft).includes(from) || !nodeIds(draft).includes(to)) return { ok: false, reason: "unknown_node" }
  const sourceType = blueprintPortDataType(draft, from, "output", outputPort)
  const targetType = blueprintPortDataType(draft, to, "input", inputPort)
  if (sourceType.reason || targetType.reason) return { ok: false, reason: "unknown_port", sourceType: sourceType.type, targetType: targetType.type }
  const sourcePrompt = isPromptNode(draft, from)
  const targetPromptInput = isAgentPromptInput(draft, to, inputPort)
  if (sourcePrompt || targetPromptInput) {
    if (sourcePrompt && targetPromptInput) return { ok: true, sourceType: "str", targetType: "str" }
    return { ok: false, reason: "type_mismatch", sourceType: sourceType.type, targetType: targetType.type }
  }
  if (sourceType.type === undefined || targetType.type === undefined) return { ok: true }
  if (sourceType.type !== targetType.type) {
    return {
      ok: false,
      reason: "type_mismatch",
      sourceType: sourceType.type,
      targetType: targetType.type,
    }
  }
  return { ok: true, sourceType: sourceType.type, targetType: targetType.type }
}

function isAgentPromptInput(draft: BlueprintDraft, nodeId: string, portName: string) {
  return !!draft.graph.agent_nodes[nodeId] && portName === AGENT_PROMPT_INPUT_PORT
}

function edgeTypeForPorts(
  draft: BlueprintDraft,
  from: string,
  outputPort: string,
  to: string,
  inputPort: string,
  fallback: string,
) {
  return isPromptNode(draft, from) && isAgentPromptInput(draft, to, inputPort) && outputPort === DEFAULT_OUTPUT_PORT
    ? "data"
    : (fallback || "exec")
}

export function updateRouteNode(draft: BlueprintDraft, id: string, patch: Partial<BlueprintRouteNode>) {
  const next = cloneBlueprintDraft(draft)
  const current = next.graph.route_nodes[id]
  if (!current) return next
  next.graph.route_nodes[id] = {
    ...current,
    ...patch,
    node_id: id,
    targets: patch.targets ? [...patch.targets] : current.targets,
  }
  return next
}

export function updateScriptNode(draft: BlueprintDraft, id: string, patch: Partial<BlueprintScriptNode>) {
  const next = cloneBlueprintDraft(draft)
  const current = next.graph.script_nodes[id]
  if (!current) return next
  next.graph.script_nodes[id] = normalizeScriptNode(id, {
    ...current,
    ...patch,
    inputs: patch.inputs ? [...patch.inputs] : current.inputs,
    outputs: patch.outputs ? [...patch.outputs] : current.outputs,
  })
  return next
}

export function compileScriptNodesFromCatalog(
  draft: BlueprintDraft,
  catalogNodes: BlueprintScriptNode[],
): BlueprintScriptCompileResult {
  const next = cloneBlueprintDraft(draft)
  const byScriptId = new Map<string, BlueprintScriptNode>()
  const byLocation = new Map<string, BlueprintScriptNode>()

  for (const node of catalogNodes) {
    const normalized = normalizeScriptNode(node.node_id || node.script_id || node.function_name, node)
    if (normalized.script_id) byScriptId.set(normalized.script_id, normalized)
    const location = scriptNodeLocationKey(normalized)
    if (location) byLocation.set(location, normalized)
  }

  let updated = 0
  let missing = 0
  const updatedNodeIds = new Set<string>()

  for (const [id, node] of Object.entries(next.graph.script_nodes ?? {})) {
    const current = normalizeScriptNode(id, node)
    const fresh = byScriptId.get(current.script_id) ?? byLocation.get(scriptNodeLocationKey(current))
    if (!fresh) {
      missing += 1
      continue
    }
    next.graph.script_nodes[id] = normalizeScriptNode(id, {
      ...fresh,
      node_id: id,
      collapsed: current.collapsed,
      feedback_only: current.feedback_only,
      require_call_before_dispatch: current.require_call_before_dispatch,
    })
    updated += 1
    updatedNodeIds.add(id)
  }

  const edgeCountBefore = next.graph.edges.length
  if (updatedNodeIds.size > 0) {
    next.graph.edges = next.graph.edges.filter((edge) =>
      scriptEdgePortsStillValid(edge, next.graph.script_nodes, updatedNodeIds),
    )
  }
  const removedEdges = edgeCountBefore - next.graph.edges.length
  clearDanglingSelectionAndInspector(next)

  return {
    draft: next,
    updated,
    missing,
    removedEdges,
  }
}

export function updateEdge(draft: BlueprintDraft, id: string, patch: Partial<BlueprintEdge>) {
  const next = cloneBlueprintDraft(draft)
  const index = next.graph.edges.findIndex((edge) => edge.id === id)
  if (index === -1) return next
  const current = next.graph.edges[index]
  const from = patch.from ?? current.from
  const to = patch.to ?? current.to
  const output_port = patch.output_port ?? current.output_port ?? DEFAULT_OUTPUT_PORT
  const input_port = patch.input_port ?? current.input_port ?? DEFAULT_INPUT_PORT
  const edge_type = edgeTypeForPorts(next, from, output_port, to, input_port, patch.edge_type?.trim() || current.edge_type || "exec")
  if (!canConnectPorts(next, from, output_port, to, input_port).ok) return next
  const updated = {
    ...current,
    ...patch,
    from,
    to,
    edge_type,
    output_port,
    input_port,
    id: edgeId(from, to, edge_type, output_port, input_port),
  }
  next.graph.edges[index] = updated
  if (next.selection?.type === "edge" && next.selection.id === id) {
    next.selection = { type: "edge", id: updated.id }
  }
  if (next.inspector?.type === "edge" && next.inspector.id === id) {
    next.inspector = { type: "edge", id: updated.id }
  }
  return next
}

export function setSelection(draft: BlueprintDraft, selection?: BlueprintSelection) {
  const next = cloneBlueprintDraft(draft)
  next.selection = selection
  return next
}

export function setInspector(draft: BlueprintDraft, inspector?: BlueprintInspectable) {
  const next = cloneBlueprintDraft(draft)
  next.inspector = inspector
  return next
}

export function setNodePosition(draft: BlueprintDraft, id: string, position: BlueprintNodeLayout) {
  const next = cloneBlueprintDraft(draft)
  if (!next.layout.nodes[id]) return next
  next.layout.nodes[id] = snapPosition(position)
  return next
}

export function scopeText(scope: string[]) {
  return scope.join("\n")
}

export function parseScopeText(value: string) {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean)
}

export function jsonText(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2)
}

export function parseJsonObject(value: string) {
  const parsed = JSON.parse(value.trim() || "{}")
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Expected a JSON object")
  }
  return parsed as Record<string, unknown>
}

export function parseStringRecord(value: string) {
  const parsed = parseJsonObject(value)
  return Object.fromEntries(Object.entries(parsed).map(([key, entry]) => [key, String(entry)]))
}

export function isAbsoluteBlueprintPath(value: string) {
  const path = value.trim()
  if (!path) return false
  if (path.startsWith("/")) return true
  if (/^[A-Za-z]:[\\/]/.test(path)) return true
  return /^\\\\[^\\]+\\[^\\]+/.test(path)
}

export function normalizeBlueprintConfigPathList(paths: unknown, legacyPath?: unknown) {
  const rawList = Array.isArray(paths) ? paths : []
  const values = rawList
    .map((item) => String(item ?? "").trim())
    .filter(Boolean)
  const source = values.length > 0 ? values : [String(legacyPath ?? "").trim()].filter(Boolean)
  const seen = new Set<string>()
  const result: string[] = []
  for (const value of source) {
    if (seen.has(value)) continue
    seen.add(value)
    result.push(value)
  }
  return result
}

export function effectiveBlueprintSkillDirs(config?: Partial<BlueprintConfig>) {
  return normalizeBlueprintConfigPathList(config?.skill_dirs, config?.skill_dir)
}

export function effectiveBlueprintRuleDirs(config?: Partial<BlueprintConfig>) {
  return normalizeBlueprintConfigPathList(config?.rule_dirs, config?.rule_dir)
}

export function requiredBlueprintConfigFields(draft: BlueprintDraft): BlueprintConfigField[] {
  const fields: BlueprintConfigField[] = ["python_path", "project_workdir"]
  if (blueprintUsesRuleDirectory(draft)) fields.push("rule_dir")
  return fields
}

export function validateBlueprintConfigForStart(draft: BlueprintDraft): BlueprintConfigValidationIssue[] {
  const config = normalizeBlueprintConfig(draft.config)
  const required = new Set(requiredBlueprintConfigFields(draft))
  const issues: BlueprintConfigValidationIssue[] = []

  const addIssue = (field: BlueprintConfigField, reason: BlueprintConfigValidationIssue["reason"]) => {
    if (!issues.some((issue) => issue.field === field && issue.reason === reason)) issues.push({ field, reason })
  }

  for (const field of ["python_path", "project_workdir"] as BlueprintConfigField[]) {
    const value = String(config[field] ?? "").trim()
    if (!value) {
      if (required.has(field)) addIssue(field, "missing")
      continue
    }
    if (!isAbsoluteBlueprintPath(value)) addIssue(field, "not_absolute")
  }

  const skillDirs = effectiveBlueprintSkillDirs(config)
  if (skillDirs.some((value) => !isAbsoluteBlueprintPath(value))) addIssue("skill_dir", "not_absolute")

  const ruleDirs = effectiveBlueprintRuleDirs(config)
  if (required.has("rule_dir") && ruleDirs.length === 0) addIssue("rule_dir", "missing")
  else if (ruleDirs.some((value) => !isAbsoluteBlueprintPath(value))) addIssue("rule_dir", "not_absolute")

  return issues
}

export function snapToGrid(value: number, gridSize = GRID_SIZE) {
  return Math.round(value / gridSize) * gridSize
}

export function snapPosition(position: BlueprintNodeLayout, gridSize = GRID_SIZE): BlueprintNodeLayout {
  return {
    x: snapToGrid(position.x, gridSize),
    y: snapToGrid(position.y, gridSize),
  }
}

export function toRuntimeGraphDraft(draft: BlueprintDraft): RuntimeGraphDraft {
  const config = normalizeBlueprintConfig(draft.config)
  const runtimeNodeIds = visibleNodeIdSet(draft)
  return {
    terminal_nodes: {},
    route_nodes: Object.fromEntries(
      Object.entries(draft.graph.route_nodes ?? {}).map(([id, node]) => [id, normalizeRouteNode(id, node)]),
    ),
    common_nodes: Object.fromEntries(
      Object.entries(draft.graph.common_nodes ?? {}).map(([id, node]) => [id, normalizeCommonNode(id, node)]),
    ),
    prompt_nodes: Object.fromEntries(
      Object.entries(draft.graph.prompt_nodes ?? {}).map(([id, node]) => [id, normalizePromptNode(id, node)]),
    ),
    script_nodes: Object.fromEntries(
      Object.entries(draft.graph.script_nodes ?? {}).map(([id, node]) => [id, normalizeScriptNode(id, node)]),
    ),
    agent_nodes: Object.fromEntries(
      Object.entries(draft.graph.agent_nodes).map(([id, node]) => [
        id,
        normalizeAgentNodeForRuntime(id, node, config),
      ]),
    ),
    agent_ring_max_circulations: normalizeRingNumberRecord(draft.graph.agent_ring_max_circulations, 0),
    agent_ring_context_refresh_periods: normalizeRingNumberRecord(draft.graph.agent_ring_context_refresh_periods, 1),
    edges: draft.graph.edges
      .filter((edge) => runtimeNodeIds.has(edge.from) && runtimeNodeIds.has(edge.to))
      .map((edge) => {
        const out: RuntimeGraphDraft["edges"][number] = {
          from: edge.from,
          to: edge.to,
          edge_type: edge.edge_type || "exec",
        }
        if (edge.output_port) out.output_port = edge.output_port
        if (edge.input_port) out.input_port = edge.input_port
        return out
      }),
  }
}

function visibleNodeIdSet(draft: BlueprintDraft) {
  return new Set([
    ...Object.keys(draft.graph.route_nodes ?? {}),
    ...Object.keys(draft.graph.common_nodes ?? {}),
    ...Object.keys(draft.graph.prompt_nodes ?? {}),
    ...Object.keys(draft.graph.script_nodes ?? {}),
    ...Object.keys(draft.graph.agent_nodes),
  ])
}

export function hasTickSourceNode(draft: BlueprintDraft) {
  return Object.values(draft.graph.common_nodes ?? {}).some((node) => node.kind === "tick")
}

function visibleLayoutNodes(draft: BlueprintDraft): Record<string, BlueprintNodeLayout> {
  const visible = visibleNodeIdSet(draft)
  return Object.fromEntries(
    Object.entries(draft.layout.nodes)
      .filter(([nodeId]) => visible.has(nodeId))
      .map(([nodeId, layout]) => [nodeId, { ...layout }]),
  )
}

function visibleInspectable<T extends BlueprintSelection | BlueprintInspectable | undefined>(
  draft: BlueprintDraft,
  value: T,
): T | undefined {
  if (!value) return undefined
  if (value.type === "edge") {
    const visible = visibleNodeIdSet(draft)
    const edge = draft.graph.edges.find((item) => item.id === value.id)
    return edge && visible.has(edge.from) && visible.has(edge.to) ? { ...value } : undefined
  }
  return visibleNodeIdSet(draft).has(value.id) ? { ...value } : undefined
}

function createAgentNode(input: {
  node_id: string
  node_type?: BlueprintAgentNodeType
  agent_id: string
  prompt: string
  run_prompt?: string
  write_scope?: string[]
  artifact_scope?: string[]
}): BlueprintAgentNode {
  const nodeType = input.node_type ?? "worker_agent"
  const fullAgent = nodeType === "agent"
  const cliKind = "codex"
  const accessPolicy = fullAgent ? DEFAULT_AGENT_ACCESS_POLICY : DEFAULT_WORKER_AGENT_ACCESS_POLICY
  return {
    node_id: input.node_id,
    node_type: nodeType,
    agent_id: input.agent_id,
    popo_entry: createDefaultPopoEntry(),
    prompt: input.prompt,
    run_prompt: input.run_prompt ?? "",
    collapsed: true,
    execution_mode: "blocking",
    cli_kind: cliKind,
    model: defaultModelForCliKind(cliKind),
    cwd: DEFAULT_PROJECT_WORKDIR,
    skills: [],
    skill_selection: { mode: "none" },
    rule_paths: [],
    timeout_sec: 1800,
    prompt_via_file: "auto",
    command: defaultCommandForCliKind(cliKind),
    adapter_options: fullAgent
      ? {
          sandbox: "danger-full-access",
          dangerous_access: true,
          extra_args: [...DANGEROUS_CODEX_EXTRA_ARGS],
        }
      : {},
    extra_env: {},
    external: false,
    read_scope: [],
    write_scope: input.write_scope ?? DEFAULT_AGENT_SCOPE,
    artifact_scope: input.artifact_scope ?? [],
    access_policy: { ...accessPolicy },
  }
}

function normalizeAgentNodeType(value: unknown): BlueprintAgentNodeType {
  return value === "agent" ? "agent" : "worker_agent"
}

function normalizeAgentAccessPolicy(
  value: unknown,
  nodeType: BlueprintAgentNodeType,
): BlueprintAgentAccessPolicy {
  const defaults = nodeType === "agent" ? DEFAULT_AGENT_ACCESS_POLICY : DEFAULT_WORKER_AGENT_ACCESS_POLICY
  if (!value || typeof value !== "object" || Array.isArray(value)) return { ...defaults }
  const raw = value as Partial<Record<keyof BlueprintAgentAccessPolicy, unknown>>
  return {
    direct_project_io: Boolean(raw.direct_project_io ?? defaults.direct_project_io),
    outside_project_io: Boolean(raw.outside_project_io ?? defaults.outside_project_io),
    unrestricted_commands: Boolean(raw.unrestricted_commands ?? defaults.unrestricted_commands),
    disable_sandbox: Boolean(raw.disable_sandbox ?? defaults.disable_sandbox),
    framework_message_tools: Boolean(raw.framework_message_tools ?? defaults.framework_message_tools),
    blueprint_monitor_tools: Boolean(raw.blueprint_monitor_tools ?? defaults.blueprint_monitor_tools),
  }
}

function normalizePopoEntry(value?: Partial<BlueprintPopoEntry>): BlueprintPopoEntry {
  const raw = value && typeof value === "object" && !Array.isArray(value) ? value : {}
  const legacy = raw as Partial<BlueprintPopoEntry> & Record<string, unknown>
  return {
    enabled: Boolean(raw.enabled),
    robot_app_key: String(raw.robot_app_key ?? legacy.robotAppKey ?? "").trim(),
    robot_name: String(raw.robot_name ?? legacy.robotName ?? "").trim(),
    robot_app_secret: String(raw.robot_app_secret ?? legacy.robotAppSecret ?? "").trim(),
    callback_token: String(raw.callback_token ?? legacy.callbackToken ?? "").trim(),
    aes_key: String(raw.aes_key ?? legacy.aesKey ?? "").trim(),
  }
}

function normalizeBlueprintConfig(config?: Partial<BlueprintConfig>): BlueprintConfig {
  const skillDirs = normalizeBlueprintConfigPathList(config?.skill_dirs, config?.skill_dir)
  const ruleDirs = normalizeBlueprintConfigPathList(config?.rule_dirs, config?.rule_dir)
  return {
    ...createDefaultBlueprintConfig(),
    ...(config ?? {}),
    python_path: config?.python_path?.trim() ?? DEFAULT_PYTHON_PATH,
    project_workdir: config?.project_workdir?.trim() ?? DEFAULT_PROJECT_WORKDIR,
    skill_dir: skillDirs[0] ?? DEFAULT_SKILL_DIR,
    skill_dirs: skillDirs,
    rule_dir: ruleDirs[0] ?? DEFAULT_RULE_DIR,
    rule_dirs: ruleDirs,
  }
}

function normalizeRingNumberRecord(value: unknown, minValue: number): Record<string, number> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {}
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .map(([key, rawValue]) => [String(key), Math.trunc(Number(rawValue))] as const)
      .filter(([key, numberValue]) => key.trim() && Number.isFinite(numberValue))
      .map(([key, numberValue]) => [key, Math.max(minValue, numberValue)]),
  )
}

function configuredRingNumber(
  value: unknown,
  topologyId: string,
  ringId: string,
  index: number,
  fallback: number,
  minValue: number,
) {
  const record = normalizeRingNumberRecord(value, minValue)
  return record[topologyId] ?? record[ringId] ?? record[String(index)] ?? fallback
}

function normalizeAgentNode(id: string, node: LegacyBlueprintAgentNode): BlueprintAgentNode {
  const {
    prompt_input_enabled: _legacyPromptInputEnabled,
    popo_entry: rawPopoEntry,
    popoEntry: legacyPopoEntry,
    ...nodeFields
  } = node
  const nodeType = normalizeAgentNodeType(node.node_type)
  const defaults = createAgentNode({
    node_id: id,
    node_type: nodeType,
    agent_id: node.agent_id ?? `agent-${id}`,
    prompt: node.prompt ?? (nodeType === "agent" ? "Describe this full CLI agent's work." : "Describe this worker's work."),
    run_prompt: node.run_prompt ?? "",
  })
  const skills = [...(node.skills ?? node.skill_selection?.skill_hashes ?? defaults.skills)]
  const skillSelection = normalizeSkillSelection(node.skill_selection ?? defaults.skill_selection, skills)
  const adapterOptions = { ...(node.adapter_options ?? defaults.adapter_options) }
  const cliKind = String(node.cli_kind ?? defaults.cli_kind)
  const testAgent = adapterOptions[TEST_AGENT_NODE_FLAG] === true && cliKind === "codex"
  if (testAgent) {
    adapterOptions.skip_git_repo_check ??= true
  }
  const configuredTimeoutSec = Number(node.timeout_sec)
  const timeoutSec =
    testAgent && (!Number.isFinite(configuredTimeoutSec) || configuredTimeoutSec < TEST_AGENT_TIMEOUT_SEC)
      ? TEST_AGENT_TIMEOUT_SEC
      : (node.timeout_sec ?? defaults.timeout_sec)
  const configuredWriteScope = node.write_scope ?? defaults.write_scope
  const writeScope =
    configuredWriteScope.length === LEGACY_REPORT_ONLY_AGENT_SCOPE.length &&
    configuredWriteScope.every((scope, index) => scope === LEGACY_REPORT_ONLY_AGENT_SCOPE[index])
      ? defaults.write_scope
      : configuredWriteScope
  return {
    ...defaults,
    ...nodeFields,
    node_id: id,
    node_type: nodeType,
    popo_entry:
      nodeType === "agent"
        ? normalizePopoEntry(rawPopoEntry ?? legacyPopoEntry ?? defaults.popo_entry)
        : createDefaultPopoEntry(),
    run_prompt: String(node.run_prompt ?? defaults.run_prompt),
    collapsed: node.collapsed !== false,
    skills,
    skill_selection: skillSelection,
    rule_paths: [...(node.rule_paths ?? defaults.rule_paths)],
    adapter_options: adapterOptions,
    extra_env: Object.fromEntries(
      Object.entries(node.extra_env ?? defaults.extra_env).map(([key, value]) => [key, String(value)]),
    ),
    timeout_sec: timeoutSec,
    read_scope: [...(node.read_scope ?? defaults.read_scope)],
    write_scope: [...writeScope],
    artifact_scope: [...(node.artifact_scope ?? defaults.artifact_scope)],
    access_policy: normalizeAgentAccessPolicy(node.access_policy ?? defaults.access_policy, nodeType),
  }
}

function normalizeAgentNodeForRuntime(
  id: string,
  node: LegacyBlueprintAgentNode,
  config: BlueprintConfig,
): BlueprintAgentNode {
  const normalized = normalizeAgentNode(id, node)
  const adapter_options = { ...normalized.adapter_options }
  if (normalized.node_type === "agent" && normalized.cli_kind === "codex") {
    if (normalized.access_policy.disable_sandbox) {
      adapter_options.sandbox = "danger-full-access"
      adapter_options.dangerous_access = true
      const extraArgs = Array.isArray(adapter_options.extra_args) ? adapter_options.extra_args.map(String) : []
      for (const arg of DANGEROUS_CODEX_EXTRA_ARGS) {
        if (!extraArgs.includes(arg)) extraArgs.push(arg)
      }
      adapter_options.extra_args = extraArgs
    } else {
      adapter_options.dangerous_access = false
      adapter_options.sandbox = normalized.access_policy.direct_project_io ? "workspace-write" : "read-only"
      if (Array.isArray(adapter_options.extra_args)) {
        adapter_options.extra_args = adapter_options.extra_args
          .map(String)
          .filter((arg) => !DANGEROUS_CODEX_EXTRA_ARGS.includes(arg))
      }
    }
  } else if (normalized.node_type === "agent") {
    delete adapter_options.sandbox
    delete adapter_options.dangerous_access
    if (Array.isArray(adapter_options.extra_args)) {
      adapter_options.extra_args = adapter_options.extra_args
        .map(String)
        .filter((arg) => !DANGEROUS_CODEX_EXTRA_ARGS.includes(arg))
    }
  }
  return {
    ...normalized,
    cwd: config.project_workdir || DEFAULT_PROJECT_WORKDIR,
    command: defaultCommandForCliKind(normalized.cli_kind),
    adapter_options,
  }
}

function normalizeRouteNode(id: string, node: Partial<BlueprintRouteNode>): BlueprintRouteNode {
  return {
    node_id: id,
    route_kind: node.route_kind ?? "sequence",
    targets: [...(node.targets ?? [])],
    reduce_target: node.reduce_target,
    reduce_prompt: node.reduce_prompt,
  }
}

function normalizeCommonNode(
  id: string,
  node: Partial<BlueprintCommonNode> & { every_n_ticks?: number; every_n_seconds?: number },
): BlueprintCommonNode {
  const kind = node.kind === "tick" ? "tick" : "branch"
  if (kind === "tick") {
    return {
      node_id: id,
      kind,
      every_n_seconds: Math.max(1, Math.floor(Number(node.every_n_seconds ?? node.every_n_ticks ?? 1) || 1)),
    }
  }
  return {
    node_id: id,
    kind,
  }
}

function normalizePromptNode(
  id: string,
  node: Partial<BlueprintPromptNode> & { prompt?: unknown; mode?: unknown },
): BlueprintPromptNode {
  const trigger = node.trigger === "always" || node.mode === "always" ? "always" : "once"
  return {
    node_id: id,
    text: String(node.text ?? node.prompt ?? ""),
    trigger,
    expanded: node.expanded === true,
  }
}

function blueprintPortDataType(
  draft: BlueprintDraft,
  nodeId: string,
  side: "input" | "output",
  portName: string,
): { type?: BlueprintPortDataType; reason?: "unknown_node" | "unknown_port" } {
  const agent = draft.graph.agent_nodes[nodeId]
  if (agent) {
    if (side === "input" && portName === AGENT_PROMPT_INPUT_PORT) {
      return { type: "str" }
    }
    return {}
  }
  if (isScriptNode(draft, nodeId)) return {}
  if (isPromptNode(draft, nodeId)) {
    if (side === "output" && portName === DEFAULT_OUTPUT_PORT) return { type: "str" }
    return { reason: "unknown_port" }
  }
  const common = draft.graph.common_nodes?.[nodeId]
  if (common) {
    if (common.kind === "branch") {
      if (side === "input" && portName === "condition") return { type: "bool" }
      if (side === "output" && (portName === "true" || portName === "false")) return { type: "message" }
      return { reason: "unknown_port" }
    }
    if (side === "output" && portName === "tick") return { type: "tick" }
    return { reason: "unknown_port" }
  }
  if (isRouteNode(draft, nodeId) || isTerminalNode(draft, nodeId)) return { type: "message" }
  return { reason: "unknown_node" }
}

function normalizeScriptPort(port: Partial<BlueprintScriptPort>, fallbackName: string): BlueprintScriptPort {
  const name = String(port.name || fallbackName).trim() || fallbackName
  const rawType = String(port.type || "Any").trim() || "Any"
  return {
    name,
    type: normalizeScriptPortType(rawType),
    required: port.required !== false,
  }
}

function normalizeScriptPortType(value: string) {
  if (value === "int" || value === "float" || value === "str" || value === "bool" || value === "dict" || value === "list") {
    return value
  }
  return "Any"
}

function normalizeScriptNode(id: string, node: Partial<BlueprintScriptNode>): BlueprintScriptNode {
  const functionName = String(node.function_name || "").trim()
  const modulePath = String(node.module_path || "").replace(/\\/g, "/").trim()
  return {
    node_id: id,
    script_id: String(node.script_id || `${modulePath}:${functionName}`).trim(),
    module_path: modulePath,
    function_name: functionName,
    title: String(node.title || functionName || id).trim(),
    description: String(node.description || ""),
    inputs: (node.inputs ?? []).map((port, index) => normalizeScriptPort(port, `arg${index + 1}`)),
    outputs: (node.outputs?.length ? node.outputs : [{ name: "result", type: "Any", required: true }]).map((port, index) =>
      normalizeScriptPort(port, index === 0 ? "result" : `out${index + 1}`),
    ),
    collapsed: node.collapsed !== false,
    feedback_only: node.feedback_only === true,
    require_call_before_dispatch: node.require_call_before_dispatch === true,
  }
}

function scriptNodeLocationKey(node: Pick<BlueprintScriptNode, "module_path" | "function_name">) {
  const modulePath = String(node.module_path || "").replace(/\\/g, "/").trim()
  const functionName = String(node.function_name || "").trim()
  return modulePath && functionName ? `${modulePath}:${functionName}` : ""
}

function isTableQueueServiceScript(node: Partial<BlueprintScriptNode>) {
  const functionName = String(node.function_name || "").trim()
  const scriptId = String(node.script_id || "").trim()
  const modulePath = String(node.module_path || "").replace(/\\/g, "/").trim()
  return functionName === "table_queue_service" || scriptId.endsWith(":table_queue_service") || modulePath.endsWith("table_queue_service.py")
}

function scriptEdgePortsStillValid(
  edge: BlueprintEdge,
  scriptNodes: Record<string, BlueprintScriptNode>,
  updatedNodeIds: Set<string>,
) {
  const source = scriptNodes[edge.from]
  if (source && updatedNodeIds.has(edge.from) && !scriptPortStillExists(source.outputs, edge.output_port, DEFAULT_OUTPUT_PORT)) {
    return false
  }

  const target = scriptNodes[edge.to]
  if (target && updatedNodeIds.has(edge.to) && !scriptPortStillExists(target.inputs, edge.input_port, DEFAULT_INPUT_PORT)) {
    return false
  }

  return true
}

function scriptPortStillExists(ports: BlueprintScriptPort[], portName: string | undefined, defaultPort: string) {
  const name = portName || defaultPort
  if (name === defaultPort) return true
  return ports.some((port) => port.name === name)
}

function routeKindFromAddKind(kind: BlueprintAddNodeKind): BlueprintRouteKind {
  if (kind === "route-parallel") return "parallel"
  if (kind === "route-parallel-reduce") return "parallel_reduce"
  return "sequence"
}

function cloneSkillSelection(selection: BlueprintSkillSelection = { mode: "none" }): BlueprintSkillSelection {
  return {
    ...selection,
    skill_hashes: selection.skill_hashes ? [...selection.skill_hashes] : undefined,
  }
}

function normalizeSkillSelection(selection: BlueprintSkillSelection, skills: string[]): BlueprintSkillSelection {
  if (skills.length === 0) return { mode: selection.mode === "all" || selection.mode === "upstream" ? selection.mode : "none" }
  if (selection.mode === "selected" && selection.skill_hashes?.length) return cloneSkillSelection(selection)
  return {
    mode: "selected",
    skill_hashes: [...skills],
  }
}

function blueprintUsesRuleDirectory(draft: BlueprintDraft) {
  return Object.entries(draft.graph.agent_nodes).some(([id, node]) => normalizeAgentNode(id, node).rule_paths.length > 0)
}

function uniqueNodeId(draft: BlueprintDraft, preferred: string) {
  const base = sanitizeNodeId(preferred) || "agent"
  const used = new Set(nodeIds(draft))
  if (!used.has(base)) return base

  for (let index = 1; ; index++) {
    const candidate = `${base}-${index}`
    if (!used.has(candidate)) return candidate
  }
}

function sanitizeNodeId(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
}

function nextNodePosition(draft: BlueprintDraft): BlueprintNodeLayout {
  const layouts = Object.values(draft.layout.nodes)
  if (layouts.length === 0) return { x: 192, y: 120 }
  const right = layouts.reduce((max, layout) => Math.max(max, layout.x), 0)
  return {
    x: right + 240,
    y: 120,
  }
}

function clearDanglingSelectionAndInspector(draft: BlueprintDraft) {
  const ids = new Set(nodeIds(draft))
  const edgeIds = new Set(draft.graph.edges.map((edge) => edge.id))
  if (draft.selection?.type === "node" && !ids.has(draft.selection.id)) draft.selection = undefined
  if (draft.selection?.type === "edge" && !edgeIds.has(draft.selection.id)) draft.selection = undefined
  if (draft.inspector?.type === "node" && !ids.has(draft.inspector.id)) draft.inspector = undefined
  if (draft.inspector?.type === "edge" && !edgeIds.has(draft.inspector.id)) draft.inspector = undefined
}
