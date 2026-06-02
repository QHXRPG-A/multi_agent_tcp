import { describe, expect, test } from "bun:test"
import { createTestAgentPanelSnapshot } from "./blueprint-test-agent-snapshot"

describe("blueprint inspector source", () => {
  test("does not render framework-managed agent fields as editable inspector controls", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const agentBranch = source.slice(source.indexOf("<Match when={props.selectedAgent"), source.indexOf("<Match when={props.selectedRoute"))

    expect(agentBranch).not.toContain('label={language.t("blueprint.field.command")}')
    expect(agentBranch).not.toContain('label={language.t("blueprint.field.cwd")}')
    expect(agentBranch).not.toContain('label={language.t("blueprint.field.workspaceId")}')
    expect(agentBranch).not.toContain('label={language.t("blueprint.field.workspaceRoot")}')
    expect(agentBranch).not.toContain('label={language.t("blueprint.field.readScope")}')
    expect(agentBranch).not.toContain('label={language.t("blueprint.field.writeScope")}')
    expect(agentBranch).not.toContain('label={language.t("blueprint.field.artifactScope")}')
    expect(agentBranch).not.toContain('label={language.t("blueprint.field.skillSelection")}')

    expect(agentBranch).toContain('label={language.t("blueprint.field.cliKind")}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.model")}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.prompt")}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.runPrompt")}')
    expect(agentBranch).toContain('tip="prompt"')
    expect(agentBranch).toContain('tip="runPrompt"')
    expect(agentBranch).toContain('value={props.selectedAgent?.prompt ?? ""}')
    expect(agentBranch).toContain('value={props.selectedAgent?.run_prompt ?? ""}')
    expect(agentBranch).toContain('onChange={(value) => updateAgentField("run_prompt", value)}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.skills")}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.rulePaths")}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.adapterOptions")}')
    expect(agentBranch).toContain('props.selectedAgent?.node_type === "agent"')
    expect(agentBranch).toContain('label={language.t("blueprint.field.directProjectIo" as never)}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.outsideProjectIo" as never)}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.unrestrictedCommands" as never)}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.disableSandbox" as never)}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.frameworkMessageTools" as never)}')
  })

  test("uses separate copy for agent description and per-run prompt help", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const zh = await Bun.file(new URL("../../i18n/zh.ts", import.meta.url)).text()
    const en = await Bun.file(new URL("../../i18n/en.ts", import.meta.url)).text()

    expect(source).toContain("blueprint.tip.runPrompt.what")
    expect(source).toContain("blueprint.tip.runPrompt.usage")
    expect(zh).toContain('"blueprint.field.prompt": "简介"')
    expect(zh).toContain('"blueprint.field.runPrompt": "提示词"')
    expect(zh).toContain("它不会作为运行提示词注入")
    expect(zh).toContain("每个 Agent 每次运行只注入一次")
    expect(en).toContain('"blueprint.field.prompt": "Description"')
    expect(en).toContain('"blueprint.field.runPrompt": "Prompt"')
    expect(en).toContain("it is not injected as the runtime prompt")
    expect(en).toContain("injected once per run")
  })

  test("renders full Agent access policy controls and Worker Agent copy", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const model = await Bun.file(new URL("./blueprint-model.ts", import.meta.url)).text()
    const en = await Bun.file(new URL("../../i18n/en.ts", import.meta.url)).text()

    expect(model).toContain('export type BlueprintAgentNodeType = "agent" | "worker_agent"')
    expect(model).toContain("DEFAULT_AGENT_ACCESS_POLICY")
    expect(model).toContain("DEFAULT_WORKER_AGENT_ACCESS_POLICY")
    expect(model).toContain('sandbox: "danger-full-access"')
    expect(model).toContain('"--dangerously-bypass-approvals-and-sandbox"')
    expect(source).toContain('kind: "agent" as const')
    expect(source).toContain('kind: "worker-agent" as const')
    expect(source).toContain('language.t("blueprint.node.workerAgent" as never)')
    expect(source).toContain('updateAgentAccessPolicy("framework_message_tools", checked)')
    expect(source).toContain('props.item.node.node_type === "agent"')
    expect(source).toContain("linear-gradient(135deg, #bbf7d0, #86efac)")
    expect(source).toContain('style={{ color: nodeTone().text }}')
    expect(source).toContain('style={{ color: nodeTone().subtitle }}')
    expect(en).toContain('"blueprint.node.workerAgent": "Worker Agent"')
    expect(en).toContain('"blueprint.add.agent.description": "Full CLI node with direct project and system access"')
    expect(en).toContain('"blueprint.add.workerAgent.description": "Framework-managed worker with private workspace isolation"')
    expect(en).toContain('"blueprint.field.disableSandbox": "Disable sandbox"')
    expect(en).toContain("agent_dispatch, agent_context, agent_task_status, and join_contribute")
  })
})

describe("blueprint project persistence source", () => {
  test("lists project blueprints, opens the selected document, and keeps local fallback", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()

    expect(source).toContain("const openBlueprint = platform.openBlueprint")
    expect(source).toContain("platform.listBlueprints")
    expect(source).toContain("initialBlueprintId?: string")
    expect(source).toContain('const routeInitialBlueprintId = () => props.initialBlueprintId?.trim() || ""')
    expect(source).toContain("const requestedBlueprintId = initialBlueprintId()")
    expect(source).toContain("await refreshProjectBlueprints(requestedBlueprintId)")
    expect(source).toContain("await loadProjectBlueprint(targetBlueprintId, targetBlueprintName)")
    expect(source).toContain("await openBlueprint(projectDirectory, blueprintId)")
    expect(source).toContain("toBlueprintDocument(next, currentBlueprintId(), currentBlueprintName())")
    expect(source).toContain("syncWorkbenchBlueprintRoute(documentId)")
    expect(source).toContain("syncWorkbenchBlueprintRoute(blueprintId)")
    expect(source).toContain("data-blueprint-document-select")
    expect(source).toContain("data-blueprint-document-create")
    expect(source).toContain("BlueprintCreateDialog")
    expect(source).toContain("uniqueBlueprintId")
    expect(source).not.toContain("toBlueprintDocument(next, DEFAULT_BLUEPRINT_ID, DEFAULT_BLUEPRINT_NAME)")
    expect(source).toContain('code === "NOT_FOUND"')
    expect(source).toContain("await saveProjectDraft(draft)")
    expect(source).toContain('source: "local"')
    expect(source).toContain("error: readableError(error)")
    expect(source).toContain("function BlueprintHeaderStatus")
    expect(source).toContain("data-blueprint-header-status-trigger")
    expect(source).toContain("data-blueprint-header-status-details")
  })

  test("confirms and relocates the project workdir through the desktop bridge", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()

    expect(source).toContain("BlueprintProjectWorkdirConfirmDialog")
    expect(source).toContain("BlueprintProjectWorkdirConflictDialog")
    expect(source).toContain("platform.relocateBlueprintProjectWorkdir")
    expect(source).toContain('result.conflict === "target_exists"')
    expect(source).toContain('resolve("load_existing")')
    expect(source).toContain('resolve("overwrite")')
    expect(source).toContain("layout?.projects.open(targetProjectDir)")
    expect(source).toContain('const route = props.floating')
    expect(source).toContain('`/${base64Encode(targetProjectDir)}/session`')
    expect(source).toContain('`/${base64Encode(targetProjectDir)}/blueprint-window/${encodeURIComponent(currentBlueprintId())}`')
    expect(source).toContain("navigate(route, { replace: true })")
    expect(source).toContain("data-blueprint-project-workdir-dialog")
    expect(source).toContain("data-blueprint-project-workdir-conflict-dialog")
  })
})

describe("blueprint runtime source", () => {
  test("submits runtime tasks through blueprint planning after saving the project document", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const snapshotSource = source.slice(source.indexOf("function createDesktopBlueprintSnapshot"), source.indexOf("function desktopSnapshotNodeState"))

    expect(source).toContain("BlueprintCollaborationAuthPanel")
    expect(source).toContain('<BlueprintCollaborationAuthPanel defaultUsername="1" />')
    expect(snapshotSource).toContain("const layout = draft.layout.nodes[id]")
    expect(snapshotSource).toContain("x: layout?.x")
    expect(snapshotSource).toContain("y: layout?.y")
    expect(source).toContain("const startDraft = await ensureDetectedPythonPath()")
    expect(source).toContain("validateBlueprintConfigForStart(startDraft)")
    expect(source).toContain("BlueprintConfigRequiredDialog")
    expect(source).toContain("await persistProjectDraft(startDraft)")
    expect(source).toContain("buildBlueprintPlanningMessage(task, startNodeIds)")
    expect(source).toContain("props.onBlueprintPlanningSubmit")
    expect(source).toContain("refreshBlueprintPlanningRequest")
    expect(source).toContain("platform.blueprintWindowPlanningStatus")
    expect(source).toContain("cancelBlueprintPlanningRequest")
    expect(source).toContain("platform.cancelBlueprintWindowPlanning")
    expect(source).toContain("blueprintPlanningRequestCancelAvailable")
    expect(source).toContain('blueprintProgressPhase() === "planning"')
    expect(source).toContain("data-blueprint-progress-close")
    expect(source).toContain("blueprint.progress.cancelPlanning")
    expect(source).toContain("planningRequest")
    expect(source).toContain("data-blueprint-runtime-planning-request")
    expect(source).toContain("blueprintPlanningBridgeAvailable()")
    expect(source).toContain("submitBlueprintPlanningTask()")
    expect(source).toContain("createBlueprintStartPlan(startDraft, { startNodes, taskText })")
    expect(source).toContain('platform.startBlueprintRun(projectDirectory, currentBlueprintId(), plan, "live")')
    expect(source).toContain("data-blueprint-runtime-start-node-select")
    expect(source).toContain("data-blueprint-runtime-task-input")
    expect(source).toContain("data-blueprint-runtime-plan-create")
    expect(source).toContain("data-blueprint-runtime-confirm-run")
    expect(source).toContain("data-blueprint-runtime-toggle")
    expect(source).toContain("data-blueprint-runtime-panel-handle")
    expect(source).toContain("data-blueprint-runtime-panel-ghost")
    expect(source).toContain("data-blueprint-runtime-panel-placeholder")
    expect(source).toContain("reorderRuntimePanels")
    expect(source).toContain("runtimePanelShellProps")
    expect(source).not.toContain("onStart={openRuntimePlanningPanel}")
    expect(source).toContain("platform.blueprintRunStatus(runId)")
    expect(source).toContain("platform.blueprintRecentEvents?.(runId, 50)")
    expect(source).toContain("platform.blueprintAgentStreamToken")
    expect(source).toContain("platform.queueBlueprintAgentMessage")
    expect(source).toContain("platform.saveBlueprintAgentPanelTest")
    expect(source).toContain('Persist.global("blueprint-agent-panel-test-log.v1")')
    expect(source).toContain("data-blueprint-test-log-toggle")
    expect(source).toContain("setAgentPanelTestLogEnabled")
    expect(source).toContain("agentPanelTestLogActive")
    expect(source).toContain("data-agent-info-panel")
    expect(source).not.toContain('kind: "test-agent" as const')
    expect(source).toContain("createTestAgentPanelSnapshot")
    expect(source).toContain("refreshOpenAgentPanelInfos(runId)")
    expect(source).toContain("scheduleTestAgentPanelPersist")
    expect(source).toContain("appendAgentPanelUserMessage")
    const sendAgentPanelMessage = source.slice(source.indexOf("async function sendAgentPanelMessage"), source.indexOf("const agentPanelEntries"))
    expect(sendAgentPanelMessage.indexOf("appendAgentPanelUserMessage")).toBeLessThan(sendAgentPanelMessage.indexOf("if (testLogActive)"))
    expect(sendAgentPanelMessage).toContain("updateAgentPanelUserMessage(nodeId, messageId")
    expect(source).toContain("syncAgentPanelUserMessagesFromRuntimeEvents")
    expect(source).toContain("runtimeMessageId")
    expect(source).toContain("mergeRuntimeRunsWithStatus")
    expect(source).toContain("succeeded")
    expect(source).toContain("userMessages")
    expect(source).toContain("testJsonPath")
    expect(source).toContain("JSON 位置")
    expect(source).not.toContain("startTestAgentInfoPanel")
    expect(source).not.toContain("createTestAgentStreamEvents")
    expect(source).not.toContain("isTestAgentNode")
    expect(source).not.toContain("TEST_AGENT_NODE_FLAG")
    expect(source).not.toContain("rgba(250, 204, 21")
    expect(source).not.toContain("启动测试")
    expect(source).toContain('setAgentPanel("panels", reconcile(panels))')
    expect(source).toContain("onClose={() => closeAgentPanel(panel.nodeId)}")
    expect(source).toContain('isTerminalRuntimeStatus(status)')
    expect(source).toContain('setInterval(() =>')
    expect(source).toContain("platform.endBlueprintRun(runId, action, opts.reason ?? `blueprint UI ${action}`)")
  })

  test("opens blueprint panels in an independent desktop window with a dock action", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const sessionSource = await Bun.file(new URL("../session.tsx", import.meta.url)).text()
    const blueprintWindowSource = await Bun.file(new URL("./blueprint-window.tsx", import.meta.url)).text()
    const sidePanelSource = await Bun.file(new URL("./session-side-panel.tsx", import.meta.url)).text()
    const layoutSource = await Bun.file(new URL("../../context/layout.tsx", import.meta.url)).text()
    const appSource = await Bun.file(new URL("../../app.tsx", import.meta.url)).text()
    const entrySource = await Bun.file(new URL("../../entry.tsx", import.meta.url)).text()
    const platformSource = await Bun.file(new URL("../../context/platform.tsx", import.meta.url)).text()

    expect(source).toContain("data-blueprint-float-handle")
    expect(source).toContain("data-blueprint-dock-button")
    expect(source).toContain("BLUEPRINT_FLOAT_DRAG_THRESHOLD")
    expect(source).toContain("platform.openBlueprintWindow")
    expect(source).toContain("platform.dockBlueprintWindow")
    expect(source).toContain("platform.closeBlueprintWindow")
    expect(source).toContain("const layout = props.floating ? undefined : useLayout()")
    expect(source).toContain("view().blueprintPanel.float(rect)")
    expect(source).toContain("await platform.openBlueprintWindow(projectDirectory, params.id, rect)")
    expect(sessionSource).toContain('"gulicode:blueprint-window-dock"')
    expect(sessionSource).toContain('"gulicode:blueprint-window-closed"')
    expect(sessionSource).toContain('"gulicode:blueprint-planning-submit"')
    expect(sessionSource).not.toContain("data-blueprint-floating-panel")
    expect(sessionSource).not.toContain("desktopBlueprintFloatingOpen")
    expect(blueprintWindowSource).toContain("data-blueprint-popout-window")
    expect(blueprintWindowSource).toContain("const workbenchInitialBlueprintId = () => (window.__GULICODE_BP__ ? params.id : undefined)")
    expect(blueprintWindowSource).toContain("initialBlueprintId={workbenchInitialBlueprintId()}")
    expect(blueprintWindowSource).toContain("submitBlueprintWindowPlanning")
    expect(blueprintWindowSource).toContain("onBlueprintPlanningSubmit={platform.submitBlueprintWindowPlanning ? submitPlanningTask : undefined}")
    expect(appSource).toContain('path="/blueprint-window/:id?"')
    expect(appSource).toContain('path="/:dir/blueprint-window/:id?"')
    expect(appSource).toContain("const StandaloneBlueprintWindowRoute = () => <BlueprintWindow />")
    expect(appSource).toContain("fallback={<StandaloneRouted />}")
    expect(appSource).toContain("visualShell")
    expect(appSource).toContain("disableServerSync")
    expect(appSource).toContain("<Show when={!props.disableServerSync}")
    expect(entrySource).toContain("planningThreadId")
    expect(entrySource).toContain('"blueprint.planning.submit"')
    expect(entrySource).toContain('"blueprint.planning.status"')
    expect(entrySource).toContain('"blueprint.planning.cancel"')
    expect(platformSource).toContain("cancelBlueprintWindowPlanning?")
    expect(entrySource).toContain("disableServerSync={!!blueprintConfig}")
    expect(sidePanelSource).toContain("!view().blueprintPanel.floating()")
    expect(layoutSource).toContain("floatingRect")
    expect(layoutSource).toContain("clampBlueprintFloatingRect")
  })

  test("shows node ports from edge direction with interactive editing fallbacks", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const nodeView = source.slice(source.indexOf("function BlueprintNodeView"), source.indexOf("function PortButton"))

    expect(source).toContain("const incomingNodeIds")
    expect(source).toContain("const outgoingNodeIds")
    expect(source).toContain("hasIncomingEdge={incomingNodeIds().has(item.id)}")
    expect(source).toContain("hasOutgoingEdge={outgoingNodeIds().has(item.id)}")
    expect(source).toContain("isConnectTargetVisible={!!connection() && connection()?.source !== item.id}")
    expect(nodeView).toContain("props.hasIncomingEdge || props.isConnectTargetVisible || interactive()")
    expect(nodeView).toContain("props.hasOutgoingEdge || interactive()")
    expect(nodeView).toContain("onPointerEnter={() => setHovering(true)}")
    expect(nodeView).toContain('const portShape = (side: "input" | "output") =>')
    expect(nodeView).toContain('props.item.node.kind === "branch" && side === "input"')
    expect(nodeView).toContain('shape={portShape("input")}')
    expect(nodeView).toContain('shape={portShape("output")}')
    expect(source).toContain('shape: "circle" | "triangle"')
    expect(source).toContain("data-blueprint-port-shape={props.shape}")
    expect(source).toContain('props.shape === "circle" && props.side === "input"')
    expect(source).toContain('props.shape === "circle" && props.side === "output"')
    expect(source).toContain("h-2.5 w-2.5 rounded-full")
  })

  test("surfaces common Branch and Tick nodes with shared port validation", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const model = await Bun.file(new URL("./blueprint-model.ts", import.meta.url)).text()
    const en = await Bun.file(new URL("../../i18n/en.ts", import.meta.url)).text()

    expect(model).toContain('export type BlueprintCommonNodeKind = "branch" | "tick"')
    expect(model).toContain("export function canConnectPorts")
    expect(model).toContain("function blueprintPortDataType")
    expect(model).toContain('sourceType.type !== targetType.type')
    expect(source).toContain('kind: "branch" as const')
    expect(source).toContain('kind: "tick" as const')
    expect(source).toContain("connectPorts(current.source, current.output_port, id, portName)")
    expect(source).toContain("const updateSelectedEdge = (edge: BlueprintEdge, patch: Partial<BlueprintEdge>)")
    expect(source).toContain("selectedCommon={inspectedCommon()}")
    expect(source).toContain("function commonNodePorts")
    expect(source).toContain('name: "condition", title: "condition: bool"')
    expect(source).toContain('data-blueprint-common-port-label="input"')
    expect(source).toContain('data-blueprint-common-port-label="output"')
    expect(source).toContain("function commonNodeSize")
    expect(source).toContain('name: "tick", title: "tick: tick"')
    expect(source).toContain("blueprint.connection.typeMismatch")
    expect(en).toContain('"blueprint.node.branch": "Branch"')
    expect(en).toContain('"blueprint.connection.typeMismatch": "Output type {{source}} cannot connect to input type {{target}}"')
  })

  test("hides terminal nodes from new blueprint interactions", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const addOptions = source.slice(source.indexOf("const addOptions"), source.indexOf("const nodes"))
    const nodes = source.slice(source.indexOf("const nodes"), source.indexOf("const visibleNodeIds"))

    expect(addOptions).not.toContain('kind: "start" as const')
    expect(addOptions).not.toContain('kind: "end" as const')
    expect(addOptions).toContain('kind: "agent" as const')
    expect(addOptions).toContain('kind: "worker-agent" as const')
    expect(nodes).not.toContain("draft.graph.terminal_nodes")
    expect(source).toContain("projectWorkdirAutoPromptShownThisApp")
  })

  test("uses right click node search and script editor workflow", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const en = await Bun.file(new URL("../../i18n/en.ts", import.meta.url)).text()
    const zh = await Bun.file(new URL("../../i18n/zh.ts", import.meta.url)).text()
    const zht = await Bun.file(new URL("../../i18n/zht.ts", import.meta.url)).text()

    expect(source).toContain("RIGHT_CLICK_PAN_THRESHOLD")
    expect(source).toContain('type: "pan-pending"')
    expect(source).toContain("openNodeSearch(currentDrag.startClientX, currentDrag.startClientY)")
    expect(source).toContain("data-blueprint-node-search")
    expect(source).toContain("data-blueprint-node-search-input")
    expect(source).toContain("data-blueprint-node-search-list")
    expect(source).toContain("data-blueprint-node-search-option")
    expect(source).toContain("filteredAddOptions")
    expect(source).toContain("max-h-[264px] overflow-y-auto")
    expect(source).toContain("BlueprintScriptCreateDialog")
    expect(source).toContain("data-blueprint-script-create")
    expect(source).toContain("data-blueprint-script-description")
    expect(source).toContain("createBlueprintScriptNode")
    expect(source).toContain("createBlueprintScriptNode(projectDirectory, name, description)")
    expect(source).toContain("openBlueprintScriptInEditor")
    expect(source).toContain('data-blueprint-script-editor-select')
    expect(source).toContain('Persist.global("blueprint.scriptEditor.v1")')
    expect(source).toContain("compileBlueprintScripts")
    expect(source).toContain("compileScriptNodesFromCatalog")
    expect(source).toContain("fanEdgeGroup")
    expect(source).toContain("visibleEdgeGroups")
    expect(source).toContain("hoveredEdgeGroupId")
    expect(source).toContain("function edgeGroupGeometry")
    expect(source).toContain("data-blueprint-edge-group")
    expect(source).toContain("data-blueprint-edge-fan-hub")
    expect(source).toContain("data-blueprint-script-compile")
    expect(source).toContain("data-blueprint-script-collapse-toggle")
    expect(source).toContain("data-blueprint-script-port-label")
    expect(source).toContain("data-blueprint-script-background")
    expect(source).toContain("SCRIPT_NODE_BLUE_CLIP_PATH")
    expect(source).toContain("polygon(0 0, 42% 0, 55% 30%, 47% 30%, 60% 58%, 52% 58%, 64% 100%, 0 100%)")
    expect(source).toContain("data-blueprint-script-split-line")
    expect(source).toContain("data-blueprint-script-split-shadow")
    expect(source).toContain("drop-shadow(2px 0 4px rgba(8,47,73,0.42))")
    expect(source).toContain("SCRIPT_NODE_SPLIT_LINE_POINTS")
    expect(source).toContain("scriptNodeDescription")
    expect(source).toContain('props.shape === "triangle" && props.side === "input"')
    expect(source).toContain("border-y-[4px] border-r-[7px]")
    expect(source).toContain("border-r-[#facc15]")
    expect(source).toContain('props.shape === "triangle" && props.side === "output"')
    expect(source).toContain("border-y-[4px] border-l-[7px]")
    expect(source).toContain("border-l-[#7dd3fc]")
    expect(source).toContain("onScriptCollapsedChange")
    expect(source).toContain("scriptCompileDisabled")
    expect(source).toContain("scriptCompileSummary")
    expect(source).toContain("compileBlueprintScripts={compileBlueprintScripts}")
    expect(source).toContain("scriptCompiling={scriptCompiling()}")
    expect(source).toContain('if (item.type === "script")')
    expect(source).toContain("void openScriptNodeInEditor(item.node)")
    expect(source).not.toContain("data-blueprint-add-node")
    for (const locale of [en, zh, zht]) {
      expect(locale).toContain('"blueprint.editor.select"')
      expect(locale).toContain('"blueprint.editor.systemDefaultDescription"')
      expect(locale).toContain('"blueprint.nodeSearch.placeholder"')
      expect(locale).toContain('"blueprint.script.compile"')
      expect(locale).toContain('"blueprint.script.compiling"')
      expect(locale).toContain('"blueprint.script.compileSuccess"')
      expect(locale).toContain('"blueprint.script.compileWarning"')
      expect(locale).toContain('"blueprint.script.compileFailed"')
      expect(locale).toContain('"blueprint.script.compileUnavailable"')
      expect(locale).toContain('"blueprint.script.expand"')
      expect(locale).toContain('"blueprint.script.collapse"')
      expect(locale).toContain('"blueprint.script.description"')
      expect(locale).toContain('"blueprint.script.descriptionPlaceholder"')
      expect(locale).toContain('"blueprint.script.noDescription"')
      expect(locale).toContain('"blueprint.script.create"')
      expect(locale).toContain('"blueprint.script.bridgeUnavailable"')
      expect(locale).toContain('"blueprint.script.openSuccess"')
      expect(locale).toContain('"blueprint.script.openSuccessDescription"')
      expect(locale).toContain('"blueprint.script.openFailed"')
    }
  })

  test("renders common config help buttons with inspector tip behavior", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const entry = await Bun.file(new URL("../../entry.tsx", import.meta.url)).text()
    const configPanel = source.slice(source.indexOf("function BlueprintGlobalConfigPanel"), source.indexOf("function BlueprintConfigRequiredDialog"))
    const configField = source.slice(source.indexOf("function DirectoryConfigField"), source.indexOf("function blueprintConfigFieldLabel"))

    expect(configPanel).toContain('tip="pythonPath"')
    expect(configPanel).toContain('tip="projectWorkdir"')
    expect(configPanel).toContain('tip="skillDir"')
    expect(configPanel).toContain('tip="ruleDir"')
    expect(configPanel).toContain('language.t("blueprint.field.pythonPath")')
    expect(configPanel).toContain('language.t("blueprint.directory.pickPython")')
    expect(configPanel).toContain('language.t("blueprint.python.detect")')
    expect(configPanel).toContain('language.t("blueprint.python.detectShort")')
    expect(configPanel).toContain('language.t("blueprint.python.detecting")')
    expect(configPanel).toContain('language.t("blueprint.python.detectFailed")')
    expect(configPanel).toContain("openFilePickerDialog")
    expect(configPanel).toContain('extensions: platform.os === "windows" ? ["exe"] : undefined')
    expect(configPanel).toContain('invalid("python_path")')
    expect(configPanel).toContain("onProjectWorkdirBrowse")
    expect(configPanel).toContain("readOnly")
    expect(configPanel).toContain("w-[360px]")
    expect(configPanel).toContain("overflow-y-auto")
    expect(configPanel).toContain("absolute left-0 top-8")
    expect(configPanel).toContain("style={BLUEPRINT_INSPECTOR_THEME}")
    expect(configPanel).not.toContain("left-3 top-3")
    expect(configPanel).not.toContain('language.t("blueprint.globalConfig.title")')
    expect(configPanel).not.toContain("props.skillCount} / {props.ruleCount")
    expect(configField).toContain("InspectorFieldHeader")
    expect(configField).toContain("<textarea")
    expect(configField).toContain("readOnly={props.readOnly}")
    expect(configField).toContain("props.onChange?.")
    expect(configField).toContain("Tooltip")
    expect(configField).toContain("<Button")
    expect(configField).toContain('icon="magnifying-glass"')
    expect(configField).toContain('icon="folder"')
    expect(configField).toContain('variant="secondary"')
    expect(configField).toContain("!h-11 !w-10")
    expect(configField).toContain("detectButtonClass")
    expect(configField).toContain("data-blueprint-detect-python")
    expect(configField).toContain("border-[#fb7185] focus:border-[#fb7185]")
    expect(configField).toContain('language.t("blueprint.globalConfig.unset")')
    expect(configField).not.toContain("data-blueprint-config-path-preview")
    expect(source).toContain("const [globalConfigOpen, setGlobalConfigOpen] = createSignal(false)")
    expect(source).toContain("const [configIssues, setConfigIssues]")
    expect(source).toContain("const [pythonDetecting, setPythonDetecting]")
    expect(source).toContain("const [pythonDetectFailed, setPythonDetectFailed]")
    expect(source).toContain("detectBlueprintPython")
    expect(source).toContain("detectAndApplyPythonPath")
    expect(source).toContain("ensureDetectedPythonPath")
    expect(source).toContain("draftSnapshotWithPythonPath")
    expect(source).toContain("configureBlueprintRuntime")
    expect(entry).toContain("detectBlueprintPython: async (projectDir?: string, pythonCommand?: string) =>")
    expect(entry).toContain('blueprintRequest(config, "blueprint.detectPython", { projectDir, pythonCommand })')
    expect(source).toContain("invalidFields={configIssues().map((issue) => issue.field)}")
    expect(source).toContain("data-blueprint-global-config-toggle")
    expect(source).toContain("disabled={blueprintConfigLocked()}")
    expect(source).toContain("blueprint.globalConfig.locked")
    expect(source).toContain('variant="ghost"')
    expect(source).toContain("data-active={globalConfigOpen()}")
    expect(source).toContain("<Show when={globalConfigOpen() && !blueprintConfigLocked()}>")
    expect(source).toContain("setGlobalConfigOpen(false)")
    expect(source).toContain("setScriptEditorMenuOpen(false)")
    expect(source).toContain("if (blueprintConfigLocked() && globalConfigOpen()) setGlobalConfigOpen(false)")
    const toolbar = source.slice(source.indexOf("<DropdownMenu"), source.indexOf('<div class="flex shrink-0 items-center gap-1">'))
    expect(toolbar).toContain("BlueprintGlobalConfigPanel")
    const canvasStart = source.indexOf("ref={canvasRef}")
    const canvasNodeLayer = source.indexOf('class="absolute left-0 top-0"', canvasStart)
    expect(source.slice(canvasStart, canvasNodeLayer)).not.toContain("BlueprintGlobalConfigPanel")
    expect(source).toContain("backfillCommonConfigPaths")
    expect(source).toContain('joinProjectPath(projectRoot, "skill_list")')
    expect(source).toContain("function InspectorTipButton")
    expect(source).toContain("placement={props.placement ?? \"left-start\"}")
  })

  test("builds compact v2 test agent message snapshots", () => {
    const snapshot = createTestAgentPanelSnapshot({
      node: {
        node_id: "test-agent",
        agent_id: "agent-test-agent",
        cli_kind: "codex",
      } as never,
      panel: {
        nodeId: "test-agent",
        userMessages: [
          {
            id: "local-1",
            runtimeMessageId: "msg-user-1",
            nodeId: "test-agent",
            mode: "top",
            text: "hello",
            status: "succeeded",
            created_at: "2026-05-18T00:00:00.000Z",
            completed_at: "2026-05-18T00:00:02.000Z",
          },
        ],
        info: {
          messageJournal: [
            {
              id: "journal-1",
              recordType: "agent.outgoing.staged",
              time: "2026-05-18T00:00:03.000Z",
              from: "test-agent",
              to: "framework",
              status: "staged",
              summary: "handoff",
              batchId: "out-1",
              targetNodeId: "reviewer",
            },
          ],
          frameworkApiCalls: [
            {
              id: "call-1",
              api: "agent.dispatch",
              time: "2026-05-18T00:00:03.000Z",
              from: "test-agent",
              status: "staged",
              summary: "handoff",
              batchId: "out-1",
            },
            {
              id: "call-2",
              api: "workspace",
              command: "checkout",
              time: "2026-05-18T00:00:04.000Z",
              from: "test-agent",
              status: "called",
            },
          ],
        },
      },
      events: [
        {
          event_id: "stream-1",
          kind: "message.completed",
          node_id: "test-agent",
          message_id: "msg-user-1",
          text: "reply to user",
          status: "completed",
          created_at: "2026-05-18T00:00:02.000Z",
        },
      ],
      runId: "run-1",
      jsonPath: "agent-panel-test.json",
      now: () => new Date("2026-05-18T00:00:05.000Z"),
    })

    expect(snapshot.schema_version).toBe(2)
    expect(snapshot.kind).toBe("gulicode.blueprint.test_agent_messages")
    expect(Object.keys(snapshot).sort()).toEqual([
      "agentId",
      "agentReplies",
      "frameworkMessages",
      "jsonPath",
      "kind",
      "nodeId",
      "runId",
      "schema_version",
      "updated_at",
      "userMessages",
    ])
    expect(snapshot.agentReplies).toEqual([
      {
        id: "stream-1",
        time: "2026-05-18T00:00:02.000Z",
        from: "test-agent",
        to: "用户",
        status: "completed",
        text: "reply to user",
        messageId: "msg-user-1",
        replyType: "to_user",
      },
      {
        id: "journal-1",
        time: "2026-05-18T00:00:03.000Z",
        from: "test-agent",
        to: "reviewer",
        status: "staged",
        text: "handoff",
        batchId: "out-1",
        replyType: "to_agent",
      },
    ])
    expect(snapshot.frameworkMessages).toEqual([
      {
        id: "call-1",
        time: "2026-05-18T00:00:03.000Z",
        from: "test-agent",
        to: "框架",
        status: "staged",
        action: "发送给其它 Agent",
        summary: "handoff",
        batchId: "out-1",
      },
      {
        id: "call-2",
        time: "2026-05-18T00:00:04.000Z",
        from: "test-agent",
        to: "框架",
        status: "called",
        action: "检出工作区",
      },
    ])
    const serialized = JSON.stringify(snapshot)
    expect(serialized).not.toContain("agent.dispatch")
    expect(serialized).not.toContain("workspace checkout")
    expect(serialized).not.toContain("recordType")
    expect(serialized).not.toContain("streamEvents")
    expect(serialized).not.toContain('"runtime":')
    expect(serialized).not.toContain('"panel":')
    expect(serialized).not.toContain("node\":")
  })

  test("projects agent panel chat, status, and structured stream events", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const agentPanel = source.slice(source.indexOf("function AgentInfoPanel"), source.indexOf("function BlueprintNodeView"))
    const eventBody = agentPanel.slice(
      agentPanel.indexOf("function AgentPanelDisplayEventBody"),
      agentPanel.indexOf("function AgentPanelDisplayEventRow"),
    )
    const visibleEvents = source.slice(source.indexOf("function visibleAgentPanelEvents"), source.indexOf("function agentStatusFieldText"))
    const statusSummary = agentPanel.slice(agentPanel.indexOf("data-agent-panel-status-summary"), agentPanel.indexOf('class="min-h-0 flex-1'))
    const chatBody = agentPanel.slice(agentPanel.indexOf('class="min-h-0 flex-1'), agentPanel.indexOf('<div class="shrink-0 border-t'))
    const composer = agentPanel.slice(agentPanel.indexOf('<div class="shrink-0 border-t'), agentPanel.indexOf("<textarea"))

    expect(visibleEvents).toContain('kind === "status"')
    expect(visibleEvents).toContain('kind === "message.started"')
    expect(visibleEvents).toContain('kind === "queue.updated"')
    expect(visibleEvents).toContain('"Agent error"')
    expect(visibleEvents).toContain("last_error")
    expect(visibleEvents).toContain('kind === "tool.started"')
    expect(visibleEvents).toContain('kind === "tool.completed"')
    expect(visibleEvents).toContain('kind === "part.delta" || kind === "message.completed"')
    expect(visibleEvents).toContain('"Agent 思考"')
    expect(visibleEvents).toContain("`工具调用")
    expect(visibleEvents).toContain("agentPanelTimelineItems(events, userMessages)")
    expect(visibleEvents).toContain("flushAgentPanelToolGroup()")
    expect(visibleEvents).toContain("agentPanelToolGroupDisplayEvent")
    expect(visibleEvents).toContain("mergeAdjacentAgentPanelToolGroups(")
    expect(visibleEvents).toContain("if (reasoningText) flushAgentPanelToolGroup()")
    expect(visibleEvents).toContain("if (text) flushAgentPanelToolGroup()")
    expect(visibleEvents).toContain("event.toolItems ?? [event]")
    expect(visibleEvents).toContain("工具调用组")
    expect(visibleEvents).toContain("agentPanelToolCategory(event)")
    expect(visibleEvents).toContain("agentPanelToolGroupCategory")
    expect(visibleEvents).toContain("toolIds: new Set<string>()")
    expect(visibleEvents).toContain("isAgentReplyTextEvent")
    expect(visibleEvents).toContain('partType === "text"')
    expect(visibleEvents).toContain('partType === "agent_message"')
    expect(visibleEvents).toContain('partType === "reasoning"')
    expect(visibleEvents).toContain("cleanAgentPanelReplyText")
    expect(visibleEvents).toContain("isCodexInternalLogLine")
    expect(visibleEvents).toContain("shouldReplaceAgentReplyDraft")
    expect(visibleEvents).toContain('"Agent 回复"')
    expect(visibleEvents).toContain("userMessages: AgentPanelUserMessage[] = []")
    expect(visibleEvents).toContain('tone: "user"')
    expect(visibleEvents).toContain('tone: "reasoning"')
    expect(visibleEvents).toContain('tone: "tool"')
    expect(agentPanel).toContain("latestAgentStatusEvent(props.events)")
    expect(source).toContain('import { Markdown } from "@opencode-ai/ui/markdown"')
    expect(agentPanel).toContain("function AgentPanelDisplayEventBody")
    expect(eventBody).toContain('when={props.event.tone === "reply"}')
    expect(eventBody).toContain("<Markdown")
    expect(eventBody).toContain("text={props.event.text}")
    expect(eventBody).toContain("cacheKey={props.event.id}")
    expect(eventBody).toContain('streaming={props.event.status !== "completed"}')
    expect(eventBody).toContain("class={markdownClass}")
    expect(eventBody).toContain("[&_pre]:!bg-[#06101a]")
    expect(eventBody).toContain("[&_.shiki]:!bg-[#06101a]")
    expect(eventBody).toContain("<pre")
    expect(agentPanel).toContain("visibleAgentPanelEvents(props.events, props.panel.userMessages ?? [])")
    expect(agentPanel).toContain('statusField("busy_count")')
    expect(agentPanel).toContain("latestAgentTaskStatusEvent(props.events)")
    expect(agentPanel).toContain('statusField("task_status")')
    expect(agentPanel).toContain('statusField("current_message_id")')
    expect(agentPanel).toContain('statusField("last_error")')
    expect(agentPanel).toContain("stabilizeAgentPanelDisplayEvents(previous")
    expect(source).toContain("const AGENT_PANEL_DEFAULT_WIDTH = 420")
    expect(source).toContain("const AGENT_PANEL_DEFAULT_HEIGHT = 620")
    expect(agentPanel).not.toContain("agent panel size preset")
    expect(agentPanel).not.toContain("props.onSizePreset")
    expect(source).not.toContain("AGENT_PANEL_SIZE_PRESETS")
    expect(statusSummary).toContain('label="状态"')
    expect(statusSummary).toContain('label="任务状态"')
    expect(statusSummary).toContain('label="队列"')
    expect(statusSummary).toContain('label="消息"')
    expect(statusSummary).toContain('label="忙碌"')
    expect(statusSummary).toContain("statusDetailsOpen")
    expect(statusSummary).toContain("toggle agent panel status details")
    expect(statusSummary).toContain("data-agent-panel-status-details")
    expect(statusSummary).toContain("运行状态")
    expect(statusSummary).toContain("任务摘要")
    expect(statusSummary).toContain("JSON 位置")
    expect(source).toContain("function latestAgentTaskStatusEvent")
    expect(agentPanel).toContain("状态详情")
    expect(agentPanel).toContain("when={visibleEvents().length}")
    expect(agentPanel).toContain("Index each={visibleEvents()}")
    expect(agentPanel).toContain("[overflow-anchor:none]")
    expect(agentPanel).toContain("{props.event.text}")
    expect(agentPanel).toContain("AgentPanelDisplayEventRow")
    expect(agentPanel).toContain("nestedToolItems")
    expect(agentPanel).toContain("(event().toolItems?.length ?? 0) > 1")
    expect(agentPanel).toContain("agentPanelToolCategoryBadgeClass")
    expect(agentPanel).toContain("toolCategory() === \"mcp\"")
    expect(agentPanel).toContain("toolCategory() === \"command\"")
    expect(agentPanel).toContain("For each={nestedToolItems()}")
    expect(agentPanel).toContain("onOpenChange={(open) => props.onEventOpenChange(tool.id, open)}")
    expect(agentPanel).toContain("<AgentPanelDisplayEventBody event={event()} />")
    expect(agentPanel).toContain('compact() ? "mb-1 px-2 py-1" : "mb-2 p-2"')
    expect(agentPanel).toContain('compact() ? "!h-7 px-0 py-0" : "px-1 py-0.5"')
    expect(agentPanel).toContain("agentPanelEventOpen")
    expect(agentPanel).toContain("open={isAgentPanelEventOpen(event().id)}")
    expect(agentPanel).toContain("onOpenChange={(open) => setAgentPanelEventOpenState(event().id, open)}")
    expect(source).toContain("function stabilizeAgentPanelDisplayEvents")
    expect(source).toContain("agentPanelDisplayEventEquals")
    expect(chatBody).not.toContain("运行状态")
    expect(chatBody).not.toContain("JSON 位置")
    expect(composer).not.toContain("运行状态")
    expect(composer).not.toContain("JSON 位置")
    expect(agentPanel).not.toContain("agentStreamEventText(event)")
    expect(agentPanel).not.toContain("For each={props.events}")
  })

  test("lets agent info panels move off canvas while keeping selection and wheel scrolling", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const updateFrame = source.slice(source.indexOf("function updateAgentPanelFrame"), source.indexOf("function agentPanelSize"))
    const positionFrame = source.slice(source.indexOf("function agentPanelPosition"), source.indexOf("async function openAgentPanel"))
    const agentPanel = source.slice(source.indexOf("function AgentInfoPanel"), source.indexOf("function BlueprintNodeView"))

    expect(source).toContain("function normalizeAgentPanelFrame")
    expect(source).toContain("function clampAgentPanelInitialFrame")
    expect(updateFrame).toContain("normalizeAgentPanelFrame(frame)")
    expect(updateFrame).not.toContain("clampAgentPanelInitialFrame(frame)")
    expect(positionFrame).toContain("clampAgentPanelInitialFrame")
    expect(agentPanel).toContain("select-text")
    expect(agentPanel).toContain("overflow-y-auto")
    expect(agentPanel).toContain("onWheel={(event) => event.stopPropagation()}")
    expect(source).toContain("const AGENT_PANEL_LONG_PRESS_MS = 500")
    expect(source).toContain("startAgentPanelLongPress(event, item)")
    expect(source).toContain("void openAgentPanel(current.nodeId, false)")
  })

  test("renders thin runtime status projections instead of scheduler logic", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const css = await Bun.file(new URL("../../index.css", import.meta.url)).text()
    const runtimePanel = source.slice(source.indexOf("function BlueprintRuntimePanel"), source.indexOf("function BlueprintNodeView"))
    const nodeView = source.slice(source.indexOf("function BlueprintNodeView"), source.indexOf("function PortButton"))

    expect(runtimePanel).toContain("status()?.outgoing_batches")
    expect(runtimePanel).toContain("status()?.joins")
    expect(runtimePanel).toContain("status()?.jobs")
    expect(runtimePanel).toContain("status()?.workspace")
    expect(runtimePanel).toContain("RuntimeWorkspaceMetric")
    expect(runtimePanel).toContain("props.onWorkspaceAreaOpen")
    expect(source).toContain("function WorkspaceContentPanel")
    expect(source).toContain("data-blueprint-workspace-content-panel")
    expect(source).toContain("data-blueprint-workspace-content-item")
    expect(source).toContain("platform.openPath")
    expect(source).toContain("platform.revealPathInFileManager")
    expect(runtimePanel).toContain("props.state.events")
    expect(runtimePanel).toContain("data-blueprint-runtime-events-height-slider")
    expect(runtimePanel).toContain("runtimeEventsPanelHeight")
    expect(runtimePanel).toContain("RuntimeEventRow")
    expect(runtimePanel).toContain("agent.task_status")
    expect(source).toContain("function runtimeAgentDetail")
    expect(source).toContain("blueprint.runtime.taskStatus")
    expect(runtimePanel).toContain("ready_for_top_agent_summary")
    expect(source).toContain("ready_for_top_agent_summary_generation")
    expect(source).not.toContain("autoTopAgentSummaryAttempts")
    expect(source).not.toContain("buildTopAgentSummaryMessage")
    expect(source).not.toContain("Summarize completed blueprint run")
    expect(source).not.toContain("silentBlocked: true")
    expect(source).toContain("autoCompletedRuntimeKeys")
    expect(source).toContain("blueprintFlowLockStore")
    expect(source).toContain("blueprintRuntimeManualUnlockKeys")
    expect(source).toContain("runtimeManualUnlockVersion()")
    expect(source).toContain("unlockRuntimeForManualControl(runId)")
    expect(source).toContain("BLUEPRINT_FLOW_LOCK_PENDING_GRACE_MS")
    expect(source).toContain("function planningProgressActive()")
    expect(source).toContain("active: true")
    expect(source).toContain("planningSeen: planningProgressActive()")
    expect(source).toContain("runtimeSummaryKey")
    expect(source).toContain("AUTO_RUNTIME_COMPLETE_REASON")
    expect(source).toContain('endBlueprintRuntime("complete"')
    expect(source).toContain("const runtimeRunActive = createMemo")
    expect(source).toContain("const runtimeStarted = createMemo")
    expect(source).toContain("const runtimeSummaryLockActive = createMemo")
    expect(source).toContain("const blueprintFlowLockActive = createMemo")
    expect(source).toContain("runtimeStatus(runtime().status)")
    expect(source).toContain("const blueprintProgressPhase = createMemo")
    expect(source).toContain("if (!blueprintFlowLockActive()) return undefined")
    expect(source).toContain("if (runtimeStarted()) return undefined")
    expect(source).toContain('if (runId && status === "running" && !runtimeSummaryReady())')
    expect(source).toContain("if (!blueprintFlowLockActive()) return")
    expect(source).toContain("BlueprintProgressOverlay")
    expect(source).toContain("data-blueprint-progress-overlay")
    expect(source).toContain("data-blueprint-progress-mask")
    expect(source).toContain("data-blueprint-progress-bar")
    expect(source).toContain("pointer-events-auto")
    expect(source).toContain("bg-white/55")
    expect(source).toContain("blueprintPlanningProgress")
    expect(source).toContain("blueprintPlanningActiveRun")
    expect(source).toContain('!externalBlueprintProgressPhase() && runtime().action !== "plan"')
    expect(source).toContain("function runtimeEdgeFlows")
    expect(source).toContain("function runtimePendingMessageEntries")
    expect(source).toContain("function runtimeMessageIsActive")
    expect(source).toContain("queues?.pending_messages")
    expect(runtimePanel).toContain("const pendingMessages = createMemo(() => runtimePendingMessageEntries(queues()?.pending_messages))")
    expect(runtimePanel).not.toContain("const pendingMessages = createMemo(() => recordEntries(asRecord(queues()?.pending_messages)))")
    expect(source).toContain("data-blueprint-runtime-flow")
    expect(source).toContain("data-blueprint-runtime-frame")
    expect(source).toContain("runtimeNodeVisualState(runtimeNodeVisualStates(), item.id)")
    expect(source).toContain("RUNTIME_WORKING_AGENT_STATES")
    expect(source).toContain("busy_count")
    expect(nodeView).toContain('"border-width": props.selected ? "2px" : "1px"')
    expect(nodeView).toContain('"box-shadow": runtimeNodeBoxShadow(props.runtimeVisualState)')
    expect(nodeView).not.toContain("nodeTone().glow")
    expect(nodeView).not.toContain("glow:")
    expect(css).toContain("@keyframes blueprint-runtime-node-breathe")
    expect(css).toContain("[data-blueprint-runtime-flow] circle")
    expect(css).toContain("@keyframes blueprint-progress-indeterminate")
    expect(css).toContain("[data-blueprint-progress-bar]")
    expect(css).toContain("prefers-reduced-motion")
    expect(runtimePanel).not.toContain("dispatchQueued")
    expect(runtimePanel).not.toContain("tick(")
  })

  test("keeps blueprint diff controls inside the blueprint canvas surface", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const sessionSource = await Bun.file(new URL("../session.tsx", import.meta.url)).text()
    const sessionSidePanelSource = await Bun.file(new URL("./session-side-panel.tsx", import.meta.url)).text()
    const globalConfigIndex = source.indexOf("data-blueprint-global-config-toggle")
    const diffToggleIndex = source.indexOf("data-blueprint-diff-toggle")
    const runtimeToggleIndex = source.indexOf("data-blueprint-runtime-toggle")
    const canvasIndex = source.indexOf("ref={canvasRef}")
    const overlayMountIndex = source.indexOf("<BlueprintDiffOverlay")
    const overlaySelectorIndex = source.indexOf("data-blueprint-diff-overlay")
    const runtimePanelIndex = source.indexOf("<BlueprintRuntimePanel")

    expect(diffToggleIndex).toBeGreaterThan(globalConfigIndex)
    expect(diffToggleIndex).toBeLessThan(runtimeToggleIndex)
    expect(overlayMountIndex).toBeGreaterThan(canvasIndex)
    expect(overlayMountIndex).toBeLessThan(runtimePanelIndex)
    expect(overlaySelectorIndex).toBeGreaterThan(overlayMountIndex)
    expect(source).toContain("platform.blueprintRunDiff")
    expect(source).toContain("platform.blueprintChangesetDiff")
    expect(source).toContain("platform.rollbackBlueprintChangesets")
    expect(source).toContain("platform.restoreBlueprintRollback")
    expect(source).toContain("data-blueprint-diff-changeset")
    expect(source).toContain("data-blueprint-diff-detail")
    expect(source).toContain("onRollbackChangeset")
    expect(source).toContain("onRestoreRollback")
    expect(source).toContain("rollbackable")
    expect(source).toContain("blueprint.diff.status.rolledBack")
    expect(source).toContain("blueprint.diff.restoreRollback")
    expect(source).toContain("blueprintAgentColor")
    expect(source).toContain("workspace.diff.changed")
    expect(source).toContain("acceptedDiffs")
    expect(source).toContain("syncedAcceptedDiffSignature")
    expect(source).toContain("onBlueprintDiffChanged")
    expect(source).toContain("props.onBlueprintDiffChanged?.(payload)")
    expect(source).toContain("const shouldSync")
    expect(source).toContain('await refreshBlueprintRunDiff(runId, { quiet: true })')
    expect(source).toContain('if (detail?.source === "blueprint") return')
    expect(sessionSource).toContain("workspace.diff.changed")
    expect(sessionSource).toContain("handleBlueprintDiffChanged")
    expect(sessionSource).toContain("onBlueprintDiffChanged={handleBlueprintDiffChanged}")
    expect(sessionSource).toContain("refreshWorkspaceDiffViews()")
    expect(sessionSource).toContain('file.tree.refresh("")')
    expect(sessionSource).toContain("mergeBlueprintReviewDiffs")
    expect(sessionSource).toContain("return mergeBlueprintReviewDiffs(turnDiffs())")
    expect(sessionSource).toContain("blueprintPlanningActiveRun={blueprintPlanning.activeRun}")
    expect(sessionSidePanelSource).toContain("onBlueprintDiffChanged={props.onBlueprintDiffChanged}")
    expect(source).not.toContain("view().reviewPanel.open()")
  })

  test("toggles blueprint changeset details and renders rolled back patches without diff coloring", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()

    expect(source).toContain("if (blueprintDiffSelectedChangesetId() === changesetId)")
    expect(source).toContain("setBlueprintDiffSelectedChangesetId(undefined)")
    expect(source).toContain('aria-expanded={props.selectedChangesetId === changeset.changesetId}')
    expect(source).toContain('tone={changeset.status === "rolled_back" ? "neutral" : "diff"}')
    expect(source).toContain('function blueprintPatchLineClass(line: string, tone: "diff" | "neutral" = "diff")')
    expect(source).toContain('if (tone === "neutral") return "text-[#cbd5e1]"')
    expect(source).toContain("blueprint.diff.noTextDiff")
  })
})
