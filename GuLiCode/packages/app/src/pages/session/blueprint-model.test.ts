import { describe, expect, test } from "bun:test"
import {
  addAgentNode,
  addEdge,
  addNode,
  addRouteNode,
  addTestAgentNode,
  CLI_KIND_OPTIONS,
  createBlueprintStartPlan,
  createDefaultBlueprintDraft,
  fromBlueprintDocument,
  DEFAULT_SKILL_DIR,
  TEST_AGENT_NODE_FLAG,
  deleteNode,
  parseScopeText,
  setInspector,
  snapPosition,
  toBlueprintDocument,
  toRuntimeGraphDraft,
  updateAgentNode,
  validateBlueprintConfigForStart,
} from "./blueprint-model"

describe("blueprint draft model", () => {
  test("creates the default local draft graph with backend-compatible fields", () => {
    const draft = createDefaultBlueprintDraft()

    expect(draft.config).toEqual({
      project_workdir: ".",
      skill_dir: DEFAULT_SKILL_DIR,
      rule_dir: "",
    })
    expect(draft.graph.terminal_nodes).toEqual({ start: "start", end: "end" })
    expect(draft.graph.route_nodes).toEqual({})
    expect(Object.keys(draft.graph.agent_nodes)).toEqual(["planner", "coder", "review", "summary"])
    expect(draft.graph.agent_nodes.planner).toMatchObject({
      node_id: "planner",
      cli_kind: "codemaker",
      model: "netease-codemaker/kimi-k2.5",
      cwd: ".",
      timeout_sec: 1800,
      prompt_via_file: "auto",
      command: "codemaker",
      external: false,
      skill_selection: { mode: "none" },
    })
    expect(draft.graph.edges.map((edge) => [edge.from, edge.output_port, edge.to, edge.input_port, edge.edge_type])).toEqual([
      ["start", "out", "planner", "in", "exec"],
      ["planner", "out", "coder", "in", "exec"],
      ["coder", "out", "review", "in", "exec"],
      ["review", "out", "summary", "in", "exec"],
      ["summary", "out", "end", "in", "exec"],
    ])
    expect(draft.inspector).toBeUndefined()
  })

  test("uses the opened project directory as blueprint common project workdir", () => {
    const draft = createDefaultBlueprintDraft("F:\\repo\\game")

    expect(draft.config.project_workdir).toBe("F:\\repo\\game")
    expect(draft.graph.agent_nodes.planner.cwd).toBe(".")
    expect(toRuntimeGraphDraft(draft).agent_nodes.planner.cwd).toBe("F:\\repo\\game")
  })

  test("adds agent nodes with a unique id, snapped position, selection, and inspector", () => {
    const draft = addAgentNode(createDefaultBlueprintDraft(), {
      node_id: "coder",
      position: { x: 10, y: 20 },
    })

    expect(draft.graph.agent_nodes["coder-1"]?.agent_id).toBe("agent-coder-1")
    expect(draft.layout.nodes["coder-1"]).toEqual({ x: 0, y: 24 })
    expect(draft.selection).toEqual({ type: "node", id: "coder-1" })
    expect(draft.inspector).toEqual({ type: "node", id: "coder-1" })
  })

  test("adds test agent nodes as a Codex panel-inspection preset", () => {
    const draft = addTestAgentNode(createDefaultBlueprintDraft(), {
      position: { x: 10, y: 20 },
    })

    expect(draft.graph.agent_nodes["test-agent"]).toMatchObject({
      node_id: "test-agent",
      agent_id: "agent-test-agent",
      cli_kind: "codex",
      model: "gpt-5.4",
      command: "codex",
      timeout_sec: 60,
      adapter_options: { [TEST_AGENT_NODE_FLAG]: true, skip_git_repo_check: true },
    })
    expect(draft.layout.nodes["test-agent"]).toEqual({ x: 0, y: 24 })
    expect(draft.selection).toEqual({ type: "node", id: "test-agent" })
    expect(draft.inspector).toEqual({ type: "node", id: "test-agent" })

    const viaGenericAdd = addNode(draft, { kind: "test-agent" })
    expect(viaGenericAdd.graph.agent_nodes["test-agent-1"]?.adapter_options[TEST_AGENT_NODE_FLAG]).toBe(true)

    const legacyTestAgent = addTestAgentNode(createDefaultBlueprintDraft())
    const legacyNode = legacyTestAgent.graph.agent_nodes["test-agent"]
    if (legacyNode) delete legacyNode.adapter_options.skip_git_repo_check
    const runtime = toRuntimeGraphDraft(legacyTestAgent)
    expect(runtime.agent_nodes["test-agent"]?.adapter_options.skip_git_repo_check).toBe(true)
  })

  test("adds route and terminal nodes", () => {
    const withRoute = addRouteNode(createDefaultBlueprintDraft(), "parallel_reduce", {
      position: { x: 333, y: 123 },
    })
    const withTerminal = addNode(withRoute, {
      kind: "start",
      position: { x: 401, y: 119 },
    })

    expect(withRoute.graph.route_nodes["parallel-reduce"]?.route_kind).toBe("parallel_reduce")
    expect(withRoute.graph.route_nodes["parallel-reduce"]?.reduce_prompt).toContain("{results}")
    expect(withRoute.layout.nodes["parallel-reduce"]).toEqual({ x: 336, y: 120 })
    expect(withTerminal.graph.terminal_nodes["start-1"]).toBe("start")
    expect(withTerminal.layout.nodes["start-1"]).toEqual({ x: 408, y: 120 })
  })

  test("adds port-aware edges once and selects the edge", () => {
    const initial = createDefaultBlueprintDraft()
    const draft = addEdge(addEdge(initial, "planner", "summary"), "planner", "summary")

    expect(draft.graph.edges.filter((edge) => edge.from === "planner" && edge.to === "summary")).toHaveLength(1)
    expect(draft.selection).toEqual({ type: "edge", id: "planner:out->summary:in:exec" })
    expect(draft.graph.edges.at(-1)).toMatchObject({
      from: "planner",
      output_port: "out",
      to: "summary",
      input_port: "in",
      edge_type: "exec",
    })
  })

  test("deletes every node kind and cascades connected edges", () => {
    const draft = deleteNode(
      addRouteNode(addEdge(createDefaultBlueprintDraft(), "planner", "end"), "sequence", { node_id: "route" }),
      "planner",
    )

    expect(draft.graph.agent_nodes.planner).toBeUndefined()
    expect(draft.layout.nodes.planner).toBeUndefined()
    expect(draft.graph.edges.some((edge) => edge.from === "planner" || edge.to === "planner")).toBe(false)

    const withoutRoute = deleteNode(draft, "route")
    expect(withoutRoute.graph.route_nodes.route).toBeUndefined()

    const withoutStart = deleteNode(withoutRoute, "start")
    expect(withoutStart.graph.terminal_nodes.start).toBeUndefined()
    expect(withoutStart.layout.nodes.start).toBeUndefined()
  })

  test("clears inspector when its target disappears", () => {
    const draft = deleteNode(setInspector(createDefaultBlueprintDraft(), { type: "node", id: "coder" }), "coder")

    expect(draft.inspector).toBeUndefined()
  })

  test("snaps arbitrary positions to the blueprint grid", () => {
    expect(snapPosition({ x: 13, y: 37 })).toEqual({ x: 24, y: 48 })
    expect(snapPosition({ x: 11, y: -13 })).toEqual({ x: 0, y: -24 })
  })

  test("converts local draft to runtime graph shape", () => {
    const draft = updateAgentNode(addRouteNode(createDefaultBlueprintDraft(), "parallel", { node_id: "fanout" }), "planner", {
      cli_kind: "codex",
      model: "gpt-5.4",
      command: "manually-hidden-command",
      skills: ["multi-agent-tcp", "python-lint-check"],
      skill_selection: { mode: "none" },
      rule_paths: ["F:\\rules\\agent.md", "F:\\rules\\review.yaml"],
      read_scope: parseScopeText("docs/**, README.md\nnotes/**"),
      adapter_options: { sandbox: "workspace-write" },
      extra_env: { GULI: "1" },
    })
    draft.config.project_workdir = "F:\\repo\\game"
    const graph = toRuntimeGraphDraft(draft)

    expect(graph.agent_nodes.planner.node_id).toBe("planner")
    expect(graph.agent_nodes.planner.cwd).toBe("F:\\repo\\game")
    expect(graph.agent_nodes.planner.command).toBe("codex")
    expect(graph.agent_nodes.planner.skills).toEqual(["multi-agent-tcp", "python-lint-check"])
    expect(graph.agent_nodes.planner.skill_selection).toEqual({
      mode: "selected",
      skill_hashes: ["multi-agent-tcp", "python-lint-check"],
    })
    expect(graph.agent_nodes.planner.rule_paths).toEqual(["F:\\rules\\agent.md", "F:\\rules\\review.yaml"])
    expect(graph.agent_nodes.planner.read_scope).toEqual(["docs/**", "README.md", "notes/**"])
    expect(graph.agent_nodes.planner.adapter_options).toEqual({ sandbox: "workspace-write" })
    expect(graph.agent_nodes.planner.extra_env).toEqual({ GULI: "1" })
    expect(graph.route_nodes.fanout).toEqual({
      node_id: "fanout",
      route_kind: "parallel",
      targets: [],
      reduce_target: undefined,
      reduce_prompt: undefined,
    })
    expect(graph.edges[0]).toEqual({
      from: "start",
      to: "planner",
      edge_type: "exec",
      output_port: "out",
      input_port: "in",
    })
    expect("id" in graph.edges[0]).toBe(false)
  })

  test("validates required absolute blueprint common config before start", () => {
    let draft = createDefaultBlueprintDraft()

    expect(validateBlueprintConfigForStart(draft)).toEqual([{ field: "project_workdir", reason: "not_absolute" }])

    draft.config.project_workdir = ""
    expect(validateBlueprintConfigForStart(draft)).toEqual([{ field: "project_workdir", reason: "missing" }])

    draft.config.project_workdir = "/repo/game"
    expect(validateBlueprintConfigForStart(draft)).toEqual([])

    draft = updateAgentNode(draft, "planner", {
      skills: ["multi-agent-tcp"],
      skill_selection: { mode: "none" },
    })
    expect(validateBlueprintConfigForStart(draft)).toEqual([{ field: "skill_dir", reason: "missing" }])

    draft.config.skill_dir = "skill_list"
    expect(validateBlueprintConfigForStart(draft)).toEqual([{ field: "skill_dir", reason: "not_absolute" }])

    draft.config.skill_dir = "/repo/skill_list"
    draft = updateAgentNode(draft, "planner", {
      rule_paths: ["/repo/rules/agent.md"],
    })
    expect(validateBlueprintConfigForStart(draft)).toEqual([{ field: "rule_dir", reason: "missing" }])

    draft.config.rule_dir = "/repo/rules"
    expect(validateBlueprintConfigForStart(draft)).toEqual([])
  })

  test("round-trips project blueprint documents with runtime graph and UI state", () => {
    const draft = addAgentNode(createDefaultBlueprintDraft("F:\\repo\\game"), {
      node_id: "extra",
      position: { x: 250, y: 121 },
    })
    const document = toBlueprintDocument(draft)
    const restored = fromBlueprintDocument(document, "F:\\repo\\game")

    expect(document).toMatchObject({
      schema_version: 1,
      id: "default",
      name: "Default Blueprint",
      graph: {
        terminal_nodes: { start: "start", end: "end" },
      },
      ui: {
        config: {
          project_workdir: "F:\\repo\\game",
          skill_dir: DEFAULT_SKILL_DIR,
          rule_dir: "",
        },
      },
    })
    expect(document.graph.edges[0]).not.toHaveProperty("id")
    expect(restored.graph.agent_nodes.extra.node_id).toBe("extra")
    expect(restored.layout.nodes.extra).toEqual({ x: 240, y: 120 })
    expect(toRuntimeGraphDraft(restored).agent_nodes.planner.cwd).toBe("F:\\repo\\game")
  })

  test("keeps supported CLI kinds explicit for inspector dropdowns", () => {
    expect(CLI_KIND_OPTIONS).toEqual(["codemaker", "codex"])
  })

  test("derives a complete start plan from the default blueprint", () => {
    const plan = createBlueprintStartPlan(createDefaultBlueprintDraft())

    expect(plan.agent_descriptions).toMatchObject({
      planner: "Break down the user goal and dispatch implementation work.",
      coder: "Implement the requested changes.",
      review: "Review implementation output and identify required fixes.",
      summary: "Summarize the run and prepare final records.",
    })
    expect(plan.start_nodes).toEqual(["planner"])
    expect(Object.keys(plan.tasks)).toEqual(["planner"])
    expect(plan.tasks.planner.goal).toContain("Break down")
    expect(plan.tasks.planner.expected_output).toContain("AgentNode planner")
    expect(plan.tasks.planner.acceptance).toContain("AgentNode planner")
    expect(plan.run_policy).toEqual({ allow_parallel: true, source: "blueprint-ui-derived" })
  })

  test("derives start nodes through route nodes and multiple start terminals", () => {
    let draft = createDefaultBlueprintDraft()
    draft = addRouteNode(draft, "parallel", { node_id: "fanout" })
    draft = addAgentNode(draft, { node_id: "research" })
    draft = addNode(draft, { kind: "start", node_id: "start-extra" })
    draft.graph.edges = []
    draft = addEdge(draft, "start", "fanout")
    draft = addEdge(draft, "fanout", "planner")
    draft = addEdge(draft, "fanout", "coder")
    draft = addEdge(draft, "start-extra", "research")

    expect(createBlueprintStartPlan(draft).start_nodes).toEqual(["planner", "coder", "research"])
  })

  test("start plan has no tasks when no start terminal reaches an agent", () => {
    const draft = createDefaultBlueprintDraft()
    draft.graph.edges = []

    const plan = createBlueprintStartPlan(draft)
    expect(plan.start_nodes).toEqual([])
    expect(plan.tasks).toEqual({})
  })
})
