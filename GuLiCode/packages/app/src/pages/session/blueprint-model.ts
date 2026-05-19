export const GRID_SIZE = 24
export const DEFAULT_OUTPUT_PORT = "out"
export const DEFAULT_INPUT_PORT = "in"
export const DEFAULT_BLUEPRINT_ID = "default"
export const DEFAULT_BLUEPRINT_NAME = "Default Blueprint"

export type BlueprintExecutionMode = "blocking" | "nonblocking"
export type BlueprintTerminalKind = "start" | "end"
export type BlueprintRouteKind = "sequence" | "parallel" | "parallel_reduce"
export type BlueprintPromptViaFile = "auto" | "always" | "never"
export type BlueprintNodeKind = "agent" | "route" | "terminal"
export type BlueprintAddNodeKind =
  | "agent"
  | "test-agent"
  | "route-sequence"
  | "route-parallel"
  | "route-parallel-reduce"
  | "start"
  | "end"
export type BlueprintCliKind = "codemaker" | "codex"

export type BlueprintSkillSelection = {
  mode: "none" | "all" | "selected" | "upstream"
  skill_hashes?: string[]
  assigned_by?: string
}

export type BlueprintConfig = {
  python_path: string
  project_workdir: string
  skill_dir: string
  rule_dir: string
}

export type BlueprintConfigField = keyof BlueprintConfig

export type BlueprintConfigValidationIssue = {
  field: BlueprintConfigField
  reason: "missing" | "not_absolute"
}

export type BlueprintAgentNode = {
  node_id: string
  agent_id?: string
  prompt: string
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
}

export type BlueprintRouteNode = {
  node_id: string
  route_kind: BlueprintRouteKind
  targets: string[]
  reduce_target?: string
  reduce_prompt?: string
}

export type BlueprintEdge = {
  id: string
  from: string
  to: string
  edge_type: string
  output_port?: string
  input_port?: string
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
  graph: {
    agent_nodes: Record<string, BlueprintAgentNode>
    route_nodes: Record<string, BlueprintRouteNode>
    terminal_nodes: Record<string, BlueprintTerminalKind>
    edges: BlueprintEdge[]
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
  ui: {
    config: BlueprintConfig
    nodes: Record<string, BlueprintNodeLayout>
    viewport: BlueprintViewport
    selection?: BlueprintSelection
    inspector?: BlueprintInspectable
  }
}

export type BlueprintStartPlan = {
  common_config: BlueprintConfig
  user_goal: string
  agent_descriptions: Record<string, string>
  start_nodes: string[]
  tasks: Record<
    string,
    {
      goal: string
      context_refs: string[]
      expected_output: string
      acceptance: string
      downstream_collaboration?: string
      metadata?: Record<string, unknown>
    }
  >
  run_policy: {
    allow_parallel: boolean
    source: "blueprint-ui-derived"
  }
}

const DEFAULT_VIEWPORT: BlueprintViewport = {
  x: 48,
  y: 96,
  zoom: 1,
}

const DEFAULT_AGENT_SCOPE = ["shared/reports/**"]
const DEFAULT_MODEL = "netease-codemaker/kimi-k2.5"
const DEFAULT_PROJECT_WORKDIR = "."
export const DEFAULT_PYTHON_PATH = ""
export const DEFAULT_SKILL_DIR = ""
export const DEFAULT_RULE_DIR = ""
export const CLI_KIND_OPTIONS: BlueprintCliKind[] = ["codemaker", "codex"]
export const TEST_AGENT_NODE_FLAG = "gulicode_test_node"

export function defaultCommandForCliKind(cliKind: string) {
  if (cliKind === "codex") return "codex"
  return "codemaker"
}

export function defaultModelForCliKind(cliKind: string) {
  if (cliKind === "codex") return "gpt-5.4"
  return DEFAULT_MODEL
}

export function createDefaultBlueprintConfig(projectWorkdir = DEFAULT_PROJECT_WORKDIR): BlueprintConfig {
  return {
    python_path: DEFAULT_PYTHON_PATH,
    project_workdir: projectWorkdir || DEFAULT_PROJECT_WORKDIR,
    skill_dir: DEFAULT_SKILL_DIR,
    rule_dir: DEFAULT_RULE_DIR,
  }
}

function agentNode(input: {
  node_id: string
  agent_id: string
  prompt: string
  write_scope?: string[]
  artifact_scope?: string[]
}): BlueprintAgentNode {
  return createAgentNode({
    node_id: input.node_id,
    agent_id: input.agent_id,
    prompt: input.prompt,
    write_scope: input.write_scope ?? DEFAULT_AGENT_SCOPE,
    artifact_scope: input.artifact_scope ?? [],
  })
}

export function createDefaultBlueprintDraft(projectWorkdir = DEFAULT_PROJECT_WORKDIR): BlueprintDraft {
  return {
    schema_version: 1,
    config: createDefaultBlueprintConfig(projectWorkdir),
    graph: {
      terminal_nodes: {
        start: "start",
        end: "end",
      },
      route_nodes: {},
      agent_nodes: {
        planner: agentNode({
          node_id: "planner",
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
        createEdge("start", "planner"),
        createEdge("planner", "coder"),
        createEdge("coder", "review"),
        createEdge("review", "summary"),
        createEdge("summary", "end"),
      ],
    },
    layout: {
      nodes: {
        start: { x: 0, y: 120 },
        planner: { x: 192, y: 96 },
        coder: { x: 432, y: 96 },
        review: { x: 672, y: 96 },
        summary: { x: 912, y: 96 },
        end: { x: 1152, y: 120 },
      },
      viewport: { ...DEFAULT_VIEWPORT },
    },
  }
}

export function cloneBlueprintDraft(draft: BlueprintDraft): BlueprintDraft {
  return {
    schema_version: 1,
    config: normalizeBlueprintConfig(draft.config),
    graph: {
      terminal_nodes: { ...draft.graph.terminal_nodes },
      route_nodes: Object.fromEntries(
        Object.entries(draft.graph.route_nodes ?? {}).map(([id, node]) => [id, normalizeRouteNode(id, node)]),
      ),
      agent_nodes: Object.fromEntries(
        Object.entries(draft.graph.agent_nodes).map(([id, node]) => [id, normalizeAgentNode(id, node)]),
      ),
      edges: draft.graph.edges.map((edge) => ({ ...edge })),
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
    ui: {
      config: normalizeBlueprintConfig(draft.config),
      nodes: Object.fromEntries(Object.entries(draft.layout.nodes).map(([nodeId, layout]) => [nodeId, { ...layout }])),
      viewport: { ...draft.layout.viewport },
      selection: draft.selection ? { ...draft.selection } : undefined,
      inspector: draft.inspector ? { ...draft.inspector } : undefined,
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
  return cloneBlueprintDraft({
    schema_version: 1,
    config: normalizeBlueprintConfig(ui.config ?? fallback.config),
    graph: {
      terminal_nodes: { ...(graph.terminal_nodes ?? fallback.graph.terminal_nodes) },
      route_nodes: Object.fromEntries(
        Object.entries(graph.route_nodes ?? {}).map(([id, node]) => [id, normalizeRouteNode(id, node)]),
      ),
      agent_nodes: Object.fromEntries(
        Object.entries(graph.agent_nodes ?? fallback.graph.agent_nodes).map(([id, node]) => [
          id,
          normalizeAgentNode(id, node),
        ]),
      ),
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
    ...Object.keys(draft.graph.agent_nodes),
  ]
}

export function nodeKind(draft: BlueprintDraft, id: string): BlueprintNodeKind | undefined {
  if (isAgentNode(draft, id)) return "agent"
  if (isRouteNode(draft, id)) return "route"
  if (isTerminalNode(draft, id)) return "terminal"
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

export function addNode(
  draft: BlueprintDraft,
  input: {
    kind: BlueprintAddNodeKind
    node_id?: string
    position?: BlueprintNodeLayout
  },
) {
  if (input.kind === "agent") return addAgentNode(draft, input)
  if (input.kind === "test-agent") return addTestAgentNode(draft, input)
  if (input.kind === "start" || input.kind === "end") return addTerminalNode(draft, input.kind, input)
  return addRouteNode(draft, routeKindFromAddKind(input.kind), input)
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
    agent_id: `agent-${node_id}`,
    prompt: "Describe this agent's work.",
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
  const next = cloneBlueprintDraft(draft)
  const node_id = uniqueNodeId(next, input.node_id ?? "test-agent")
  next.graph.agent_nodes[node_id] = {
    ...createAgentNode({
      node_id,
      agent_id: `agent-${node_id}`,
      prompt: "Display sample Agent information panel content for UI testing.",
    }),
    cli_kind: "codex",
    model: defaultModelForCliKind("codex"),
    command: defaultCommandForCliKind("codex"),
    timeout_sec: 300,
    adapter_options: { [TEST_AGENT_NODE_FLAG]: true, skip_git_repo_check: true },
  }
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
  const id = edgeId(from, to, edgeType, outputPort, inputPort)
  if (
    !next.graph.edges.some(
      (edge) =>
        edge.id === id ||
        (edge.from === from &&
          edge.to === to &&
          edge.edge_type === edgeType &&
          (edge.output_port || DEFAULT_OUTPUT_PORT) === outputPort &&
          (edge.input_port || DEFAULT_INPUT_PORT) === inputPort),
    )
  ) {
    next.graph.edges.push(createEdge(from, to, edgeType, outputPort, inputPort))
  }
  next.selection = { type: "edge", id }
  return next
}

export function deleteNode(draft: BlueprintDraft, id: string) {
  const next = cloneBlueprintDraft(draft)
  if (!nodeIds(next).includes(id)) return next

  delete next.graph.agent_nodes[id]
  delete next.graph.route_nodes[id]
  delete next.graph.terminal_nodes[id]
  delete next.layout.nodes[id]
  next.graph.edges = next.graph.edges.filter((edge) => edge.from !== id && edge.to !== id)
  clearDanglingSelectionAndInspector(next)
  return next
}

export function deleteEdge(draft: BlueprintDraft, id: string) {
  const next = cloneBlueprintDraft(draft)
  next.graph.edges = next.graph.edges.filter((edge) => edge.id !== id)
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
  next.graph.agent_nodes[id] = {
    ...current,
    ...patch,
    node_id: id,
    skills: patch.skills ? [...patch.skills] : current.skills,
    skill_selection: patch.skill_selection ? cloneSkillSelection(patch.skill_selection) : cloneSkillSelection(current.skill_selection),
    rule_paths: patch.rule_paths ? [...patch.rule_paths] : current.rule_paths,
    adapter_options: patch.adapter_options ? { ...patch.adapter_options } : current.adapter_options,
    extra_env: patch.extra_env ? { ...patch.extra_env } : current.extra_env,
    read_scope: patch.read_scope ? [...patch.read_scope] : current.read_scope,
    write_scope: patch.write_scope ? [...patch.write_scope] : current.write_scope,
    artifact_scope: patch.artifact_scope ? [...patch.artifact_scope] : current.artifact_scope,
  }
  return next
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

export function updateEdge(draft: BlueprintDraft, id: string, patch: Partial<BlueprintEdge>) {
  const next = cloneBlueprintDraft(draft)
  const index = next.graph.edges.findIndex((edge) => edge.id === id)
  if (index === -1) return next
  const current = next.graph.edges[index]
  const edge_type = patch.edge_type?.trim() || current.edge_type || "exec"
  const from = patch.from ?? current.from
  const to = patch.to ?? current.to
  const output_port = patch.output_port ?? current.output_port ?? DEFAULT_OUTPUT_PORT
  const input_port = patch.input_port ?? current.input_port ?? DEFAULT_INPUT_PORT
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

export function requiredBlueprintConfigFields(draft: BlueprintDraft): BlueprintConfigField[] {
  const fields: BlueprintConfigField[] = ["python_path", "project_workdir"]
  if (blueprintUsesSkillDirectory(draft)) fields.push("skill_dir")
  if (blueprintUsesRuleDirectory(draft)) fields.push("rule_dir")
  return fields
}

export function validateBlueprintConfigForStart(draft: BlueprintDraft): BlueprintConfigValidationIssue[] {
  const config = draft.config ?? createDefaultBlueprintConfig()
  const required = new Set(requiredBlueprintConfigFields(draft))
  const fields: BlueprintConfigField[] = ["python_path", "project_workdir", "skill_dir", "rule_dir"]
  const issues: BlueprintConfigValidationIssue[] = []

  for (const field of fields) {
    const value = String(config[field] ?? "").trim()
    if (!value) {
      if (required.has(field)) issues.push({ field, reason: "missing" })
      continue
    }
    if (!isAbsoluteBlueprintPath(value)) issues.push({ field, reason: "not_absolute" })
  }

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
  return {
    terminal_nodes: { ...draft.graph.terminal_nodes },
    route_nodes: Object.fromEntries(
      Object.entries(draft.graph.route_nodes ?? {}).map(([id, node]) => [id, normalizeRouteNode(id, node)]),
    ),
    agent_nodes: Object.fromEntries(
      Object.entries(draft.graph.agent_nodes).map(([id, node]) => [
        id,
        normalizeAgentNodeForRuntime(id, node, config),
      ]),
    ),
    edges: draft.graph.edges.map((edge) => {
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

export function createBlueprintStartPlan(draft: BlueprintDraft): BlueprintStartPlan {
  const common_config = normalizeBlueprintConfig(draft.config)
  const agentNodes = Object.entries(draft.graph.agent_nodes)
  const startNodes = deriveStartAgentNodes(draft)
  const agent_descriptions = Object.fromEntries(
    agentNodes.map(([id, node]) => [id, node.prompt.trim() || `AgentNode ${id}`]),
  )
  const tasks = Object.fromEntries(
    startNodes.map((nodeId) => {
      const node = draft.graph.agent_nodes[nodeId]
      const goal = node?.prompt.trim() || `Run AgentNode ${nodeId}.`
      return [
        nodeId,
        {
          goal,
          context_refs: [],
          expected_output: `Complete the assigned work for AgentNode ${nodeId} and report the result through the framework runtime.`,
          acceptance: `AgentNode ${nodeId} has a clear result recorded in runtime status, reports, artifacts, or queued downstream work.`,
          metadata: {
            source: "blueprint-ui-derived",
            node_id: nodeId,
          },
        },
      ]
    }),
  )

  return {
    common_config,
    user_goal: "Run the current GuLiCode blueprint.",
    agent_descriptions,
    start_nodes: startNodes,
    tasks,
    run_policy: {
      allow_parallel: true,
      source: "blueprint-ui-derived",
    },
  }
}

function deriveStartAgentNodes(draft: BlueprintDraft): string[] {
  const agentIds = new Set(Object.keys(draft.graph.agent_nodes))
  const routeIds = new Set(Object.keys(draft.graph.route_nodes ?? {}))
  const terminalIds = new Set(Object.keys(draft.graph.terminal_nodes))
  const startTerminalIds = Object.entries(draft.graph.terminal_nodes)
    .filter(([, kind]) => kind === "start")
    .map(([id]) => id)
  const result: string[] = []
  const added = new Set<string>()

  for (const startId of startTerminalIds) {
    const queued = outgoingExecTargets(draft, startId)
    const visited = new Set<string>([startId])
    while (queued.length) {
      const nodeId = queued.shift()
      if (!nodeId || visited.has(nodeId)) continue
      visited.add(nodeId)
      if (agentIds.has(nodeId)) {
        if (!added.has(nodeId)) {
          result.push(nodeId)
          added.add(nodeId)
        }
        continue
      }
      if (routeIds.has(nodeId) || terminalIds.has(nodeId)) {
        queued.push(...outgoingExecTargets(draft, nodeId))
      }
    }
  }

  return result
}

function outgoingExecTargets(draft: BlueprintDraft, nodeId: string): string[] {
  return draft.graph.edges
    .filter((edge) => edge.from === nodeId && (edge.edge_type || "exec") === "exec")
    .map((edge) => edge.to)
}

function createAgentNode(input: {
  node_id: string
  agent_id: string
  prompt: string
  write_scope?: string[]
  artifact_scope?: string[]
}): BlueprintAgentNode {
  return {
    node_id: input.node_id,
    agent_id: input.agent_id,
    prompt: input.prompt,
    execution_mode: "blocking",
    cli_kind: "codemaker",
    model: DEFAULT_MODEL,
    cwd: DEFAULT_PROJECT_WORKDIR,
    skills: [],
    skill_selection: { mode: "none" },
    rule_paths: [],
    timeout_sec: 1800,
    prompt_via_file: "auto",
    command: "codemaker",
    adapter_options: {},
    extra_env: {},
    external: false,
    read_scope: [],
    write_scope: input.write_scope ?? DEFAULT_AGENT_SCOPE,
    artifact_scope: input.artifact_scope ?? [],
  }
}

function normalizeBlueprintConfig(config?: Partial<BlueprintConfig>): BlueprintConfig {
  return {
    ...createDefaultBlueprintConfig(),
    ...(config ?? {}),
    python_path: config?.python_path?.trim() ?? DEFAULT_PYTHON_PATH,
    project_workdir: config?.project_workdir?.trim() ?? DEFAULT_PROJECT_WORKDIR,
    skill_dir: config?.skill_dir?.trim() ?? DEFAULT_SKILL_DIR,
    rule_dir: config?.rule_dir?.trim() ?? DEFAULT_RULE_DIR,
  }
}

function normalizeAgentNode(id: string, node: Partial<BlueprintAgentNode>): BlueprintAgentNode {
  const defaults = createAgentNode({
    node_id: id,
    agent_id: node.agent_id ?? `agent-${id}`,
    prompt: node.prompt ?? "Describe this agent's work.",
  })
  const skills = [...(node.skills ?? node.skill_selection?.skill_hashes ?? defaults.skills)]
  const skillSelection = normalizeSkillSelection(node.skill_selection ?? defaults.skill_selection, skills)
  const adapterOptions = { ...(node.adapter_options ?? defaults.adapter_options) }
  const cliKind = String(node.cli_kind ?? defaults.cli_kind)
  if (adapterOptions[TEST_AGENT_NODE_FLAG] === true && cliKind === "codex") {
    adapterOptions.skip_git_repo_check ??= true
  }
  return {
    ...defaults,
    ...node,
    node_id: id,
    skills,
    skill_selection: skillSelection,
    rule_paths: [...(node.rule_paths ?? defaults.rule_paths)],
    adapter_options: adapterOptions,
    extra_env: Object.fromEntries(
      Object.entries(node.extra_env ?? defaults.extra_env).map(([key, value]) => [key, String(value)]),
    ),
    read_scope: [...(node.read_scope ?? defaults.read_scope)],
    write_scope: [...(node.write_scope ?? defaults.write_scope)],
    artifact_scope: [...(node.artifact_scope ?? defaults.artifact_scope)],
  }
}

function normalizeAgentNodeForRuntime(
  id: string,
  node: Partial<BlueprintAgentNode>,
  config: BlueprintConfig,
): BlueprintAgentNode {
  const normalized = normalizeAgentNode(id, node)
  return {
    ...normalized,
    cwd: config.project_workdir || DEFAULT_PROJECT_WORKDIR,
    command: defaultCommandForCliKind(normalized.cli_kind),
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

function blueprintUsesSkillDirectory(draft: BlueprintDraft) {
  return Object.entries(draft.graph.agent_nodes).some(([id, node]) => {
    const normalized = normalizeAgentNode(id, node)
    return normalized.skill_selection.mode !== "none" || normalized.skills.length > 0
  })
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
