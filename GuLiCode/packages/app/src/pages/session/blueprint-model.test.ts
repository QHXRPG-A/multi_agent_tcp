import { describe, expect, test } from "bun:test"
import {
  addAgentNode,
  addFullAgentNode,
  addEdge,
  addNode,
  addPromptNode,
  addRouteNode,
  addScriptNode,
  addTestAgentNode,
  agentRingConfigKey,
  agentRingsForDraft,
  canConnectPorts,
  CLI_KIND_OPTIONS,
  compileScriptNodesFromCatalog,
  createEdge,
  createDefaultBlueprintDraft,
  fromBlueprintDocument,
  DEFAULT_PYTHON_PATH,
  DEFAULT_SKILL_DIR,
  TEST_AGENT_NODE_FLAG,
  deleteEdge,
  deleteNode,
  parseScopeText,
  setInspector,
  snapPosition,
  toBlueprintDocument,
  toRuntimeGraphDraft,
  updateAgentNode,
  updateEdge,
  updatePromptNode,
  hasTickSourceNode,
  validateBlueprintConfigForStart,
  createDefaultPopoEntry,
} from "./blueprint-model"

describe("blueprint draft model", () => {
  test("creates the default local draft graph with backend-compatible fields", () => {
    const draft = createDefaultBlueprintDraft()

    expect(draft.config).toEqual({
      python_path: DEFAULT_PYTHON_PATH,
      project_workdir: ".",
      skill_dir: DEFAULT_SKILL_DIR,
      skill_dirs: [],
      rule_dir: "",
      rule_dirs: [],
    })
    expect(draft.runtime).toEqual({ start_node_id: "planner", popo_entry: createDefaultPopoEntry() })
    expect(draft.graph.terminal_nodes).toEqual({})
    expect(draft.graph.route_nodes).toEqual({})
    expect(draft.graph.common_nodes).toEqual({})
    expect(draft.graph.prompt_nodes).toEqual({})
    expect(draft.graph.agent_ring_max_circulations).toEqual({})
    expect(draft.graph.agent_ring_context_refresh_periods).toEqual({})
    expect(Object.keys(draft.graph.agent_nodes)).toEqual(["planner", "coder", "review", "summary"])
    expect(draft.graph.agent_nodes.planner).toMatchObject({
      node_id: "planner",
      node_type: "agent",
      cli_kind: "codex",
      model: "gpt-5.4",
      cwd: ".",
      popo_entry: createDefaultPopoEntry(),
      timeout_sec: 1800,
      prompt_via_file: "auto",
      run_prompt: "",
      collapsed: true,
      command: "codex",
      external: false,
      skill_selection: { mode: "none" },
      access_policy: {
        direct_project_io: true,
        outside_project_io: true,
        unrestricted_commands: true,
        disable_sandbox: true,
        framework_message_tools: true,
      },
    })
    expect(draft.graph.edges.map((edge) => [edge.from, edge.output_port, edge.to, edge.input_port, edge.edge_type])).toEqual([
      ["planner", "out", "coder", "in", "exec"],
      ["coder", "out", "review", "in", "exec"],
      ["review", "out", "summary", "in", "exec"],
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
    expect(draft.graph.agent_nodes["coder-1"]?.node_type).toBe("worker_agent")
    expect(draft.graph.agent_nodes["coder-1"]?.write_scope).toEqual(["**"])
    expect(draft.layout.nodes["coder-1"]).toEqual({ x: 0, y: 24 })
    expect(draft.selection).toEqual({ type: "node", id: "coder-1" })
    expect(draft.inspector).toEqual({ type: "node", id: "coder-1" })
  })

  test("adds full CLI agent nodes with unrestricted defaults", () => {
    const draft = addFullAgentNode(createDefaultBlueprintDraft(), {
      node_id: "shell",
      position: { x: 10, y: 20 },
    })

    expect(draft.graph.agent_nodes.shell).toMatchObject({
      node_id: "shell",
      node_type: "agent",
      agent_id: "agent-shell",
      cli_kind: "codex",
      model: "gpt-5.4",
      command: "codex",
      adapter_options: {
        sandbox: "danger-full-access",
        dangerous_access: true,
        extra_args: ["--dangerously-bypass-approvals-and-sandbox"],
      },
      access_policy: {
        direct_project_io: true,
        outside_project_io: true,
        unrestricted_commands: true,
        disable_sandbox: true,
        framework_message_tools: true,
      },
    })
    expect(draft.layout.nodes.shell).toEqual({ x: 0, y: 24 })
    expect(draft.selection).toEqual({ type: "node", id: "shell" })
    expect(draft.inspector).toEqual({ type: "node", id: "shell" })
  })

  test("adds test-agent compatibility nodes as ordinary agent nodes", () => {
    const draft = addTestAgentNode(createDefaultBlueprintDraft(), {
      position: { x: 10, y: 20 },
    })

    expect(draft.graph.agent_nodes.agent).toMatchObject({
      node_id: "agent",
      node_type: "worker_agent",
      agent_id: "agent-agent",
      cli_kind: "codex",
      model: "gpt-5.4",
      command: "codex",
      timeout_sec: 1800,
      adapter_options: {},
      write_scope: ["**"],
    })
    expect(draft.graph.agent_nodes.agent?.adapter_options[TEST_AGENT_NODE_FLAG]).toBeUndefined()
    expect(draft.layout.nodes.agent).toEqual({ x: 0, y: 24 })
    expect(draft.selection).toEqual({ type: "node", id: "agent" })
    expect(draft.inspector).toEqual({ type: "node", id: "agent" })

    const viaGenericAdd = addNode(draft, { kind: "test-agent" })
    expect(viaGenericAdd.graph.agent_nodes["agent-1"]).toMatchObject({
      node_id: "agent-1",
      node_type: "worker_agent",
      agent_id: "agent-agent-1",
      cli_kind: "codex",
      adapter_options: {},
    })
    expect(viaGenericAdd.graph.agent_nodes["agent-1"]?.adapter_options[TEST_AGENT_NODE_FLAG]).toBeUndefined()
  })

  test("generic add node creates full Agent and Worker explicitly", () => {
    const withFullAgent = addNode(createDefaultBlueprintDraft(), { kind: "agent", node_id: "agent" })
    const withWorkerAgent = addNode(withFullAgent, { kind: "worker-agent", node_id: "agent" })

    expect(withFullAgent.graph.agent_nodes.agent?.node_type).toBe("agent")
    expect(withFullAgent.graph.agent_nodes.agent?.cli_kind).toBe("codex")
    expect(withWorkerAgent.graph.agent_nodes["agent-1"]?.node_type).toBe("worker_agent")
    expect(withWorkerAgent.graph.agent_nodes["agent-1"]?.cli_kind).toBe("codex")
  })

  test("migrates legacy report-only write scope to project-wide default", () => {
    const draft = createDefaultBlueprintDraft()
    draft.graph.agent_nodes.planner.write_scope = ["shared/reports/**"]

    const runtime = toRuntimeGraphDraft(draft)

    expect(runtime.agent_nodes.planner.write_scope).toEqual(["**"])
  })

  test("adds route nodes and keeps the legacy terminal helper available", () => {
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
    expect(withTerminal.graph.terminal_nodes.start).toBe("start")
    expect(withTerminal.layout.nodes.start).toEqual({ x: 408, y: 120 })
  })

  test("adds built-in common Branch and Tick nodes and preserves them in documents", () => {
    let draft = addNode(createDefaultBlueprintDraft(), {
      kind: "branch",
      node_id: "gate",
      position: { x: 190, y: 55 },
    })
    draft = addNode(draft, {
      kind: "tick",
      node_id: "clock",
      position: { x: 290, y: 87 },
    })

    expect(draft.graph.common_nodes.gate).toEqual({ node_id: "gate", kind: "branch" })
    expect(draft.graph.common_nodes.clock).toEqual({ node_id: "clock", kind: "tick", every_n_seconds: 1 })
    expect(draft.layout.nodes.gate).toEqual({ x: 192, y: 48 })
    expect(draft.layout.nodes.clock).toEqual({ x: 288, y: 96 })
    expect(hasTickSourceNode(draft)).toBe(true)

    const document = toBlueprintDocument(draft)
    const restored = fromBlueprintDocument(document)
    expect(document.graph.common_nodes?.clock).toEqual({ node_id: "clock", kind: "tick", every_n_seconds: 1 })
    expect(restored.graph.common_nodes.gate).toEqual({ node_id: "gate", kind: "branch" })
    expect(toRuntimeGraphDraft(restored).common_nodes?.clock).toEqual({ node_id: "clock", kind: "tick", every_n_seconds: 1 })
  })

  test("preserves the configured BlueprintSession start node in documents", () => {
    const draft = createDefaultBlueprintDraft()
    draft.runtime.start_node_id = "coder"

    const document = toBlueprintDocument(draft)
    const restored = fromBlueprintDocument(document)

    expect(document.runtime?.start_node_id).toBe("coder")
    expect(restored.runtime.start_node_id).toBe("coder")
  })

  test("stores POPO entry on the saved start full Agent instead of runtime metadata", () => {
    const draft = createDefaultBlueprintDraft()
    const entry = {
      enabled: true,
      robot_app_key: "app-key",
      robot_name: "bot",
      robot_app_secret: "secret",
      callback_token: "token",
      aes_key: "aes",
    }
    draft.graph.agent_nodes.planner.popo_entry = entry

    const document = toBlueprintDocument(draft)
    const restored = fromBlueprintDocument(document)

    expect(document.runtime?.popo_entry).toEqual(createDefaultPopoEntry())
    expect(document.graph.agent_nodes.planner.popo_entry).toEqual(entry)
    expect(restored.runtime.popo_entry).toEqual(createDefaultPopoEntry())
    expect(restored.graph.agent_nodes.planner.popo_entry).toEqual(entry)
  })

  test("migrates legacy runtime POPO entry to the saved start full Agent", () => {
    const legacyEntry = {
      enabled: true,
      robot_app_key: "legacy-key",
      robot_name: "legacy-bot",
      robot_app_secret: "legacy-secret",
      callback_token: "legacy-token",
      aes_key: "legacy-aes",
    }
    const document = toBlueprintDocument(createDefaultBlueprintDraft())
    document.runtime = {
      start_node_id: "planner",
      popo_entry: legacyEntry,
    }
    document.graph.agent_nodes.planner.popo_entry = createDefaultPopoEntry()

    const restored = fromBlueprintDocument(document)
    const resaved = toBlueprintDocument(restored)

    expect(restored.runtime.popo_entry).toEqual(createDefaultPopoEntry())
    expect(restored.graph.agent_nodes.planner.popo_entry).toEqual(legacyEntry)
    expect(resaved.runtime?.popo_entry).toEqual(createDefaultPopoEntry())
    expect(resaved.graph.agent_nodes.planner.popo_entry).toEqual(legacyEntry)
  })

  test("detects script-transparent agent rings and preserves ring settings", () => {
    const draft = createDefaultBlueprintDraft()
    draft.graph.agent_nodes = {
      a: { ...draft.graph.agent_nodes.planner, node_id: "a", agent_id: "agent-a", node_type: "agent" },
      b: { ...draft.graph.agent_nodes.coder, node_id: "b", agent_id: "agent-b", node_type: "worker_agent" },
      c: { ...draft.graph.agent_nodes.review, node_id: "c", agent_id: "agent-c", node_type: "worker_agent" },
    }
    draft.graph.script_nodes = {
      transform: {
        node_id: "transform",
        script_id: "ring:transform",
        module_path: "ring.py",
        function_name: "transform",
        title: "Transform",
        description: "",
        inputs: [{ name: "in", type: "Any" }],
        outputs: [{ name: "out", type: "Any" }],
        collapsed: true,
      },
    }
    draft.graph.route_nodes = {}
    draft.graph.common_nodes = {}
    draft.graph.prompt_nodes = {}
    draft.graph.edges = [
      createEdge("a", "b"),
      createEdge("b", "a"),
      createEdge("b", "transform"),
      createEdge("transform", "c"),
      createEdge("c", "a"),
      createEdge("a", "c", "data"),
    ]
    draft.graph.agent_ring_max_circulations = { "1": 0, "ring-a-b-c": 4 }
    draft.graph.agent_ring_context_refresh_periods = { ring1: 3, "ring-a-b-c": 2 }

    const rings = agentRingsForDraft(draft)

    expect(rings.map((ring) => [ring.ring_id, ring.topology_id, ring.ordered_node_ids])).toEqual([
      ["ring1", "ring-a-b", ["a", "b"]],
      ["ring2", "ring-a-b-c", ["a", "b", "c"]],
    ])
    expect(rings[0]?.max_circulations).toBe(0)
    expect(rings[0]?.context_refresh_period).toBe(3)
    expect(rings[1]?.max_circulations).toBe(4)
    expect(rings[1]?.context_refresh_period).toBe(2)
    expect(agentRingConfigKey(rings[1]!)).toBe("ring-a-b-c")
    expect(rings[1]?.visual_edge_ids).toEqual([
      "a:out->b:in:exec",
      "b:out->transform:in:exec",
      "transform:out->c:in:exec",
      "c:out->a:in:exec",
    ])

    const document = toBlueprintDocument(draft)
    const restored = fromBlueprintDocument(document)
    const runtime = toRuntimeGraphDraft(restored)
    expect(document.graph.agent_ring_max_circulations).toEqual({ "1": 0, "ring-a-b-c": 4 })
    expect(document.graph.agent_ring_context_refresh_periods).toEqual({ ring1: 3, "ring-a-b-c": 2 })
    expect(runtime.agent_ring_max_circulations).toEqual({ "1": 0, "ring-a-b-c": 4 })
    expect(runtime.agent_ring_context_refresh_periods).toEqual({ ring1: 3, "ring-a-b-c": 2 })
  })

  test("adds Prompt nodes and enforces fixed Agent prompt data input", () => {
    let draft = addPromptNode(createDefaultBlueprintDraft(), {
      node_id: "style_prompt",
      position: { x: 131, y: 77 },
    })
    draft = updatePromptNode(draft, "style_prompt", {
      text: "Use concise implementation notes.",
      trigger: "always",
      expanded: true,
    })

    expect(draft.graph.prompt_nodes.style_prompt).toEqual({
      node_id: "style_prompt",
      text: "Use concise implementation notes.",
      trigger: "always",
      expanded: true,
    })
    expect(draft.layout.nodes.style_prompt).toEqual({ x: 120, y: 72 })
    const connected = addEdge(draft, "style_prompt", "coder", "exec", "out", "prompt")
    expect(connected.graph.edges.at(-1)).toMatchObject({
      from: "style_prompt",
      to: "coder",
      edge_type: "data",
      output_port: "out",
      input_port: "prompt",
    })
    expect(connected.selection).toEqual({ type: "edge", id: "style_prompt:out->coder:prompt:data" })

    const rejectedDefaultInput = addEdge(connected, "style_prompt", "review", "exec", "out", "in")
    expect(rejectedDefaultInput.graph.edges).toEqual(connected.graph.edges)

    const script = addScriptNode(connected, {
      node_id: "script_str",
      script: {
        script_id: "script_str.py:script_str",
        module_path: "script_str.py",
        function_name: "script_str",
        outputs: [{ name: "result", type: "str", required: true }],
      },
    })
    const rejectedScriptSource = addEdge(script, "script_str", "coder", "exec", "result", "prompt")
    expect(rejectedScriptSource.graph.edges).toEqual(script.graph.edges)

    const document = toBlueprintDocument(connected)
    const restored = fromBlueprintDocument(document)
    expect(document.graph.prompt_nodes?.style_prompt).toEqual(connected.graph.prompt_nodes.style_prompt)
    expect(document.graph.agent_nodes.coder.collapsed).toBe(true)
    expect(toRuntimeGraphDraft(restored).prompt_nodes?.style_prompt).toEqual(connected.graph.prompt_nodes.style_prompt)

    const legacyRestored = fromBlueprintDocument({
      ...document,
      graph: {
        ...document.graph,
        agent_nodes: {
          ...document.graph.agent_nodes,
          coder: {
            ...document.graph.agent_nodes.coder,
            prompt_input_enabled: false,
          } as never,
        },
      },
    })
    expect(canConnectPorts(legacyRestored, "style_prompt", "out", "coder", "prompt")).toMatchObject({ ok: true })
  })

  test("enforces port types for non-Agent and non-Script connections only", () => {
    let draft = addNode(createDefaultBlueprintDraft(), { kind: "branch", node_id: "gate" })
    draft = addNode(draft, { kind: "tick", node_id: "clock" })
    draft = addRouteNode(draft, "sequence", { node_id: "route" })
    draft = addScriptNode(draft, {
      node_id: "script",
      script: {
        script_id: "demo.py:demo",
        module_path: "demo.py",
        function_name: "demo",
      },
    })

    const branchInput = addEdge(draft, "planner", "gate", "exec", "out", "condition")
    expect(branchInput.graph.edges.some((edge) => edge.to === "gate" && edge.input_port === "condition")).toBe(true)

    const branchOutput = addEdge(branchInput, "gate", "summary", "exec", "true", "in")
    expect(branchOutput.graph.edges.some((edge) => edge.from === "gate" && edge.output_port === "true")).toBe(true)

    const rejected = addEdge(branchOutput, "clock", "gate", "exec", "tick", "condition")
    expect(rejected.graph.edges).toEqual(branchOutput.graph.edges)
    expect(canConnectPorts(branchOutput, "clock", "tick", "gate", "condition")).toMatchObject({
      ok: false,
      reason: "type_mismatch",
      sourceType: "tick",
      targetType: "bool",
    })

    const routeRejected = addEdge(branchOutput, "clock", "route", "exec", "tick", "in")
    expect(routeRejected.graph.edges).toEqual(branchOutput.graph.edges)
    const withScriptTarget = addEdge(branchOutput, "clock", "script", "exec", "tick", "payload")
    expect(withScriptTarget.graph.edges.at(-1)).toMatchObject({ from: "clock", to: "script", output_port: "tick", input_port: "payload" })
    const withScriptSource = addEdge(withScriptTarget, "script", "gate", "exec", "result", "condition")
    expect(withScriptSource.graph.edges.at(-1)).toMatchObject({ from: "script", to: "gate", output_port: "result", input_port: "condition" })

    const unchanged = updateEdge(branchOutput, branchOutput.graph.edges.at(-1)?.id ?? "", {
      from: "clock",
      to: "gate",
      output_port: "tick",
      input_port: "condition",
    })
    expect(unchanged.graph.edges).toEqual(branchOutput.graph.edges)
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

  test("fans agent to every script input and deletes the input fan group", () => {
    const initial = addScriptNode(createDefaultBlueprintDraft(), {
      node_id: "test_1",
      script: {
        script_id: "test_1.py:test_1",
        module_path: "test_1.py",
        function_name: "test_1",
        title: "test_1",
        inputs: [
          { name: "title", type: "str", required: true },
          { name: "priority", type: "int", required: true },
          { name: "context", type: "dict", required: true },
        ],
        outputs: [{ name: "summary", type: "str", required: true }],
      },
    })

    const draft = addEdge(initial, "planner", "test_1", "exec", "out", "priority")
    const fanEdges = draft.graph.edges.filter((edge) => edge.from === "planner" && edge.to === "test_1")
    expect(fanEdges.map((edge) => edge.input_port).sort()).toEqual(["context", "priority", "title"])
    expect(draft.selection).toEqual({ type: "edge", id: "planner:out->test_1:priority:exec" })

    const deleted = deleteEdge(draft, "planner:out->test_1:priority:exec")
    expect(deleted.graph.edges.some((edge) => edge.from === "planner" && edge.to === "test_1")).toBe(false)
  })

  test("fans every script output into an agent and keeps single-port scripts one-to-one", () => {
    let draft = addScriptNode(createDefaultBlueprintDraft(), {
      node_id: "test_1",
      script: {
        script_id: "test_1.py:test_1",
        module_path: "test_1.py",
        function_name: "test_1",
        title: "test_1",
        inputs: [{ name: "payload", type: "dict", required: true }],
        outputs: [
          { name: "summary", type: "str", required: true },
          { name: "details", type: "dict", required: true },
        ],
      },
    })
    draft = addScriptNode(draft, {
      node_id: "single",
      script: {
        script_id: "single.py:single",
        module_path: "single.py",
        function_name: "single",
        title: "single",
        inputs: [{ name: "payload", type: "dict", required: true }],
        outputs: [{ name: "result", type: "dict", required: true }],
      },
    })

    draft = addEdge(draft, "test_1", "review", "exec", "details", "in")
    const fanInEdges = draft.graph.edges.filter((edge) => edge.from === "test_1" && edge.to === "review")
    expect(fanInEdges.map((edge) => edge.output_port).sort()).toEqual(["details", "summary"])

    draft = addEdge(draft, "single", "summary", "exec", "result", "in")
    expect(draft.graph.edges.filter((edge) => edge.from === "single" && edge.to === "summary")).toHaveLength(1)

    const deleted = deleteEdge(draft, "test_1:details->review:in:exec")
    expect(deleted.graph.edges.some((edge) => edge.from === "test_1" && edge.to === "review")).toBe(false)
  })

  test("compiles placed script nodes from catalog and cleans stale port edges", () => {
    let draft = addScriptNode(createDefaultBlueprintDraft(), {
      node_id: "test_1",
      position: { x: 49, y: 74 },
      script: {
        script_id: "test_1.py:test_1",
        module_path: "test_1.py",
        function_name: "test_1",
        title: "test_1",
        description: "Old script",
        inputs: [
          { name: "title", type: "str", required: true },
          { name: "payload", type: "dict", required: true },
        ],
        outputs: [
          { name: "summary", type: "str", required: true },
          { name: "result", type: "dict", required: true },
        ],
        collapsed: false,
        feedback_only: true,
        require_call_before_dispatch: true,
      },
    })
    draft = addEdge(draft, "planner", "test_1", "exec", "out", "title")
    draft = addEdge(draft, "coder", "test_1", "exec", "out", "payload")
    draft = addEdge(draft, "test_1", "review", "exec", "summary", "in")
    draft = addEdge(draft, "test_1", "summary", "exec", "result", "in")
    draft.inspector = { type: "edge", id: "test_1:result->summary:in:exec" }

    const result = compileScriptNodesFromCatalog(draft, [
      {
        node_id: "test_1",
        script_id: "test_1.py:test_1",
        module_path: "test_1.py",
        function_name: "test_1",
        title: "Format score",
        description: "New script",
        inputs: [
          { name: "title", type: "str", required: true },
          { name: "priority", type: "int", required: true },
          { name: "context", type: "dict", required: true },
        ],
        outputs: [
          { name: "summary", type: "str", required: true },
          { name: "details", type: "dict", required: true },
        ],
        collapsed: true,
      },
    ])

    expect(result.updated).toBe(1)
    expect(result.missing).toBe(0)
    expect(result.removedEdges).toBe(4)
    expect(result.draft.graph.script_nodes.test_1).toMatchObject({
      node_id: "test_1",
      title: "Format score",
      description: "New script",
      collapsed: false,
      feedback_only: true,
      require_call_before_dispatch: true,
      inputs: [
        { name: "title", type: "str", required: true },
        { name: "priority", type: "int", required: true },
        { name: "context", type: "dict", required: true },
      ],
      outputs: [
        { name: "summary", type: "str", required: true },
        { name: "details", type: "dict", required: true },
      ],
    })
    expect(result.draft.layout.nodes.test_1).toEqual({ x: 48, y: 72 })
    expect(result.draft.graph.edges.map((edge) => edge.id)).toEqual([
      "planner:out->coder:in:exec",
      "coder:out->review:in:exec",
      "review:out->summary:in:exec",
      "planner:out->test_1:title:exec",
      "coder:out->test_1:title:exec",
      "test_1:summary->review:in:exec",
      "test_1:summary->summary:in:exec",
    ])
    expect(result.draft.inspector).toBeUndefined()
  })

  test("defaults table queue service script nodes to feedback and required call", () => {
    const draft = addScriptNode(createDefaultBlueprintDraft(), {
      node_id: "table_queue_service",
      script: {
        script_id: "table_queue_service.py:table_queue_service",
        module_path: "table_queue_service.py",
        function_name: "table_queue_service",
      },
    })

    expect(draft.graph.script_nodes.table_queue_service).toMatchObject({
      feedback_only: true,
      require_call_before_dispatch: true,
    })

    const ordinary = addScriptNode(createDefaultBlueprintDraft(), {
      node_id: "ordinary_script",
      script: {
        script_id: "ordinary.py:ordinary",
        module_path: "ordinary.py",
        function_name: "ordinary",
      },
    })
    expect(ordinary.graph.script_nodes.ordinary_script.feedback_only).toBe(false)
    expect(ordinary.graph.script_nodes.ordinary_script.require_call_before_dispatch).toBe(false)
  })

  test("reports missing script catalog entries without changing placed nodes", () => {
    const draft = addScriptNode(createDefaultBlueprintDraft(), {
      node_id: "missing_script",
      script: {
        script_id: "missing.py:missing_script",
        module_path: "missing.py",
        function_name: "missing_script",
        title: "Missing script",
      },
    })

    const result = compileScriptNodesFromCatalog(draft, [])

    expect(result.updated).toBe(0)
    expect(result.missing).toBe(1)
    expect(result.removedEdges).toBe(0)
    expect(result.draft.graph.script_nodes.missing_script).toEqual(draft.graph.script_nodes.missing_script)
  })

  test("deletes every node kind and cascades connected edges", () => {
    const withTerminal = addNode(createDefaultBlueprintDraft(), { kind: "start", node_id: "start" })
    const draft = deleteNode(addRouteNode(addEdge(withTerminal, "planner", "start"), "sequence", { node_id: "route" }), "planner")

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
      run_prompt: "Always inspect the current checkout before editing.",
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
    expect(graph.agent_nodes.planner.run_prompt).toBe("Always inspect the current checkout before editing.")
    expect(graph.agent_nodes.planner.read_scope).toEqual(["docs/**", "README.md", "notes/**"])
    expect(graph.agent_nodes.planner.adapter_options).toEqual({
      dangerous_access: true,
      extra_args: ["--dangerously-bypass-approvals-and-sandbox"],
      sandbox: "danger-full-access",
    })
    expect(graph.agent_nodes.planner.extra_env).toEqual({ GULI: "1" })
    expect(graph.route_nodes.fanout).toEqual({
      node_id: "fanout",
      route_kind: "parallel",
      targets: [],
      reduce_target: undefined,
      reduce_prompt: undefined,
    })
    expect(graph.edges[0]).toEqual({
      from: "planner",
      to: "coder",
      edge_type: "exec",
      output_port: "out",
      input_port: "in",
    })
    expect("id" in graph.edges[0]).toBe(false)
  })

  test("normalizes legacy agent nodes as workers", () => {
    const draft = fromBlueprintDocument({
      schema_version: 1,
      id: "legacy",
      name: "Legacy",
      graph: {
        terminal_nodes: {},
        route_nodes: {},
        agent_nodes: {
          legacy: {
            node_id: "legacy",
            agent_id: "agent-legacy",
            prompt: "Legacy node.",
          } as never,
        },
        edges: [],
      },
      ui: {
        config: {
          python_path: "",
          project_workdir: ".",
          skill_dir: "",
          rule_dir: "",
        } as never,
        nodes: {},
        viewport: { x: 0, y: 0, zoom: 1 },
      },
    })

    expect(draft.graph.agent_nodes.legacy.node_type).toBe("worker_agent")
    expect(draft.config.skill_dirs).toEqual([])
    expect(draft.config.rule_dirs).toEqual([])
    expect(draft.graph.agent_nodes.legacy.access_policy).toEqual({
      direct_project_io: false,
      outside_project_io: false,
      unrestricted_commands: false,
      disable_sandbox: false,
      framework_message_tools: true,
      blueprint_monitor_tools: false,
    })
  })

  test("validates required absolute blueprint common config before start", () => {
    let draft = createDefaultBlueprintDraft()

    expect(validateBlueprintConfigForStart(draft)).toEqual([
      { field: "python_path", reason: "missing" },
      { field: "project_workdir", reason: "not_absolute" },
    ])

    draft.config.python_path = "/usr/bin/python3"
    draft.config.project_workdir = ""
    expect(validateBlueprintConfigForStart(draft)).toEqual([{ field: "project_workdir", reason: "missing" }])

    draft.config.project_workdir = "/repo/game"
    expect(validateBlueprintConfigForStart(draft)).toEqual([])

    draft = updateAgentNode(draft, "planner", {
      skills: ["multi-agent-tcp"],
      skill_selection: { mode: "none" },
    })
    expect(validateBlueprintConfigForStart(draft)).toEqual([])

    draft.config.skill_dir = "skill_list"
    expect(validateBlueprintConfigForStart(draft)).toEqual([{ field: "skill_dir", reason: "not_absolute" }])

    draft.config.skill_dir = "/repo/skill_list"
    draft = updateAgentNode(draft, "planner", {
      rule_paths: ["/repo/rules/agent.md"],
    })
    expect(validateBlueprintConfigForStart(draft)).toEqual([{ field: "rule_dir", reason: "missing" }])

    draft.config.rule_dir = "/repo/rules"
    expect(validateBlueprintConfigForStart(draft)).toEqual([])

    draft.config.rule_dirs = ["rules"]
    expect(validateBlueprintConfigForStart(draft)).toEqual([{ field: "rule_dir", reason: "not_absolute" }])

    draft.config.rule_dirs = ["/repo/rules", "/repo/more-rules"]
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
        terminal_nodes: {},
      },
      ui: {
        config: {
          python_path: DEFAULT_PYTHON_PATH,
          project_workdir: "F:\\repo\\game",
          skill_dir: DEFAULT_SKILL_DIR,
          skill_dirs: [],
          rule_dir: "",
          rule_dirs: [],
        },
      },
    })
    expect(document.graph.edges[0]).not.toHaveProperty("id")
    expect(restored.graph.agent_nodes.extra.node_id).toBe("extra")
    expect(restored.layout.nodes.extra).toEqual({ x: 240, y: 120 })
    expect(toRuntimeGraphDraft(restored).agent_nodes.planner.cwd).toBe("F:\\repo\\game")
  })

  test("migrates legacy single skill and rule config paths to path lists", () => {
    const restored = fromBlueprintDocument({
      schema_version: 1,
      id: "legacy-config",
      name: "Legacy Config",
      graph: createDefaultBlueprintDraft("F:\\repo\\game").graph,
      ui: {
        config: {
          python_path: "C:\\Python313\\python.exe",
          project_workdir: "F:\\repo\\game",
          skill_dir: "F:\\repo\\game\\skills",
          rule_dir: "F:\\repo\\game\\rules",
        } as never,
        nodes: {},
        viewport: { x: 0, y: 0, zoom: 1 },
      },
    })

    expect(restored.config).toMatchObject({
      skill_dir: "F:\\repo\\game\\skills",
      skill_dirs: ["F:\\repo\\game\\skills"],
      rule_dir: "F:\\repo\\game\\rules",
      rule_dirs: ["F:\\repo\\game\\rules"],
    })
  })

  test("round-trips persisted common config, agent settings, tick settings, and UI state", () => {
    let draft = createDefaultBlueprintDraft("F:\\repo\\persist")
    draft.config = {
      python_path: "C:\\Python313\\python.exe",
      project_workdir: "F:\\repo\\persist",
      skill_dir: "F:\\repo\\persist\\skills",
      skill_dirs: ["F:\\repo\\persist\\skills", "F:\\repo\\persist\\more-skills"],
      rule_dir: "F:\\repo\\persist\\rules",
      rule_dirs: ["F:\\repo\\persist\\rules", "F:\\repo\\persist\\more-rules"],
    }
    draft = updateAgentNode(draft, "planner", {
      prompt: "Plan with saved settings.",
      run_prompt: "Use the saved per-run prompt once.",
      execution_mode: "nonblocking",
      model: "gpt-5.5",
      skills: ["business-skill"],
      skill_selection: { mode: "selected", skill_hashes: ["business-skill"] },
      rule_paths: ["policy.md"],
      timeout_sec: 321,
      prompt_via_file: "always",
      adapter_options: { temperature: 0.2, retry: true },
      extra_env: { GULI_SETTING: "1" },
      external: true,
      read_scope: ["docs/**"],
      write_scope: ["src/**"],
      artifact_scope: ["shared/artifacts/**"],
      access_policy: {
        direct_project_io: true,
        outside_project_io: false,
        unrestricted_commands: false,
        disable_sandbox: false,
        framework_message_tools: true,
        blueprint_monitor_tools: false,
      },
    })
    draft = addNode(draft, {
      kind: "tick",
      node_id: "clock",
      position: { x: 301, y: 119 },
    })
    const clock = draft.graph.common_nodes.clock
    if (clock?.kind === "tick") clock.every_n_seconds = 9
    draft.layout.viewport = { x: 33, y: -12, zoom: 1.25 }
    draft.selection = { type: "node", id: "clock" }
    draft.inspector = { type: "node", id: "planner" }

    const document = toBlueprintDocument(draft, "settings", "Settings")
    const restored = fromBlueprintDocument(document, "F:\\repo\\persist")

    expect(document.ui.config).toEqual(draft.config)
    expect(document.graph.common_nodes?.clock).toEqual({ node_id: "clock", kind: "tick", every_n_seconds: 9 })
    expect(document.graph.agent_nodes.planner).toMatchObject({
      prompt: "Plan with saved settings.",
      run_prompt: "Use the saved per-run prompt once.",
      execution_mode: "nonblocking",
      model: "gpt-5.5",
      skills: ["business-skill"],
      skill_selection: { mode: "selected", skill_hashes: ["business-skill"] },
      rule_paths: ["policy.md"],
      timeout_sec: 321,
      prompt_via_file: "always",
      adapter_options: { temperature: 0.2, retry: true },
      extra_env: { GULI_SETTING: "1" },
      external: true,
      read_scope: ["docs/**"],
      write_scope: ["src/**"],
      artifact_scope: ["shared/artifacts/**"],
      access_policy: {
        direct_project_io: true,
        outside_project_io: false,
        unrestricted_commands: false,
        disable_sandbox: false,
        framework_message_tools: true,
      },
    })
    expect(document.ui.nodes.clock).toEqual({ x: 312, y: 120 })
    expect(document.ui.viewport).toEqual({ x: 33, y: -12, zoom: 1.25 })
    expect(document.ui.selection).toEqual({ type: "node", id: "clock" })
    expect(document.ui.inspector).toEqual({ type: "node", id: "planner" })
    expect(restored.config).toEqual(draft.config)
    expect(restored.graph.common_nodes.clock).toEqual({ node_id: "clock", kind: "tick", every_n_seconds: 9 })
    expect(restored.graph.agent_nodes.planner.run_prompt).toBe("Use the saved per-run prompt once.")
    expect(restored.graph.agent_nodes.planner.model).toBe("gpt-5.5")
    expect(restored.graph.agent_nodes.planner.adapter_options).toEqual({
      dangerous_access: false,
      retry: true,
      sandbox: "workspace-write",
      temperature: 0.2,
    })
    expect(restored.layout.viewport).toEqual({ x: 33, y: -12, zoom: 1.25 })
    expect(restored.selection).toEqual({ type: "node", id: "clock" })
    expect(restored.inspector).toEqual({ type: "node", id: "planner" })
  })

  test("reads legacy terminal documents but filters terminals from export and runtime graphs", () => {
    const restored = fromBlueprintDocument({
      schema_version: 1,
      id: "legacy",
      name: "Legacy",
      graph: {
        terminal_nodes: { start: "start", end: "end" },
        route_nodes: {},
        agent_nodes: createDefaultBlueprintDraft().graph.agent_nodes,
        edges: [
          { from: "start", to: "planner", edge_type: "exec" },
          { from: "planner", to: "coder", edge_type: "exec" },
          { from: "summary", to: "end", edge_type: "exec" },
        ],
      },
      ui: {
        config: createDefaultBlueprintDraft().config,
        nodes: {
          start: { x: -120, y: 96 },
          planner: { x: 0, y: 96 },
          coder: { x: 240, y: 96 },
          summary: { x: 720, y: 96 },
          end: { x: 920, y: 96 },
        },
        viewport: { x: 0, y: 0, zoom: 1 },
        selection: { type: "node", id: "start" },
        inspector: { type: "edge", id: "summary:out->end:in:exec" },
      },
    })

    expect(restored.graph.terminal_nodes).toEqual({ start: "start", end: "end" })
    expect(toRuntimeGraphDraft(restored).terminal_nodes).toEqual({})
    expect(toRuntimeGraphDraft(restored).edges.map((edge) => [edge.from, edge.to])).toEqual([["planner", "coder"]])
    const document = toBlueprintDocument(restored)
    expect(document.graph.terminal_nodes).toEqual({})
    expect(document.ui.nodes.start).toBeUndefined()
    expect(document.ui.nodes.end).toBeUndefined()
    expect(document.ui.selection).toBeUndefined()
    expect(document.ui.inspector).toBeUndefined()
  })

  test("keeps supported CLI kinds explicit for inspector dropdowns", () => {
    expect(CLI_KIND_OPTIONS).toEqual(["codex"])
  })

})
