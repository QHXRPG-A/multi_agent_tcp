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
    expect(agentBranch).toContain('label={language.t("blueprint.field.skills")}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.rulePaths")}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.adapterOptions")}')
  })
})

describe("blueprint project persistence source", () => {
  test("opens default project blueprint, imports missing documents, and keeps local fallback", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()

    expect(source).toContain("const openBlueprint = platform.openBlueprint")
    expect(source).toContain("await openBlueprint(projectDirectory, DEFAULT_BLUEPRINT_ID)")
    expect(source).toContain('platform.saveBlueprint(projectDirectory, toBlueprintDocument(next, DEFAULT_BLUEPRINT_ID, DEFAULT_BLUEPRINT_NAME))')
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
    expect(source).toContain("layout.projects.open(targetProjectDir)")
    expect(source).toContain('navigate(`/${base64Encode(targetProjectDir)}/session`, { replace: true })')
    expect(source).toContain("data-blueprint-project-workdir-dialog")
    expect(source).toContain("data-blueprint-project-workdir-conflict-dialog")
  })
})

describe("blueprint runtime source", () => {
  test("submits runtime tasks through blueprint planning after saving the project document", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()

    expect(source).toContain("const startDraft = await ensureDetectedPythonPath()")
    expect(source).toContain("validateBlueprintConfigForStart(startDraft)")
    expect(source).toContain("BlueprintConfigRequiredDialog")
    expect(source).toContain("await persistProjectDraft(startDraft)")
    expect(source).toContain("buildBlueprintPlanningMessage(task, startNodeIds)")
    expect(source).toContain("props.onBlueprintPlanningSubmit")
    expect(source).toContain("data-blueprint-runtime-start-node-select")
    expect(source).toContain("data-blueprint-runtime-task-input")
    expect(source).toContain("data-blueprint-runtime-task-submit")
    expect(source).toContain("data-blueprint-runtime-toggle")
    expect(source).toContain("data-blueprint-runtime-panel-handle")
    expect(source).toContain("data-blueprint-runtime-panel-ghost")
    expect(source).toContain("data-blueprint-runtime-panel-placeholder")
    expect(source).toContain("reorderRuntimePanels")
    expect(source).toContain("runtimePanelShellProps")
    expect(source).not.toContain("createBlueprintStartPlan(startDraft)")
    expect(source).not.toContain("platform.startBlueprintRun(")
    expect(source).not.toContain("onStart={openRuntimePlanningPanel}")
    expect(source).toContain("platform.blueprintRunStatus(runId)")
    expect(source).toContain("platform.blueprintRecentEvents?.(runId, 50)")
    expect(source).toContain("platform.blueprintAgentStreamToken")
    expect(source).toContain("platform.queueBlueprintAgentMessage")
    expect(source).toContain("platform.saveBlueprintAgentPanelTest")
    expect(source).toContain("data-agent-info-panel")
    expect(source).toContain('"test-agent"')
    expect(source).toContain("createTestAgentPanelSnapshot")
    expect(source).toContain("refreshOpenAgentPanelInfos(runId)")
    expect(source).toContain("scheduleTestAgentPanelPersist")
    expect(source).toContain("appendAgentPanelUserMessage")
    const sendAgentPanelMessage = source.slice(source.indexOf("async function sendAgentPanelMessage"), source.indexOf("const agentPanelEntries"))
    expect(sendAgentPanelMessage.indexOf("appendAgentPanelUserMessage")).toBeLessThan(sendAgentPanelMessage.indexOf("if (testAgent)"))
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
    expect(source).not.toContain("启动测试")
    expect(source).toContain('setAgentPanel("panels", reconcile(panels))')
    expect(source).toContain("onClose={() => closeAgentPanel(panel.nodeId)}")
    expect(source).toContain('isTerminalRuntimeStatus(status)')
    expect(source).toContain('setInterval(() =>')
    expect(source).toContain('platform.endBlueprintRun(runId, action, `blueprint UI ${action}`)')
  })

  test("opens blueprint panels in an independent desktop window with a dock action", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const sessionSource = await Bun.file(new URL("../session.tsx", import.meta.url)).text()
    const blueprintWindowSource = await Bun.file(new URL("./blueprint-window.tsx", import.meta.url)).text()
    const sidePanelSource = await Bun.file(new URL("./session-side-panel.tsx", import.meta.url)).text()
    const layoutSource = await Bun.file(new URL("../../context/layout.tsx", import.meta.url)).text()
    const appSource = await Bun.file(new URL("../../app.tsx", import.meta.url)).text()

    expect(source).toContain("data-blueprint-float-handle")
    expect(source).toContain("data-blueprint-dock-button")
    expect(source).toContain("BLUEPRINT_FLOAT_DRAG_THRESHOLD")
    expect(source).toContain("platform.openBlueprintWindow")
    expect(source).toContain("platform.dockBlueprintWindow")
    expect(source).toContain("platform.closeBlueprintWindow")
    expect(source).toContain("view().blueprintPanel.float(rect)")
    expect(source).toContain("await platform.openBlueprintWindow(projectDirectory, params.id, rect)")
    expect(sessionSource).toContain('"gulicode:blueprint-window-dock"')
    expect(sessionSource).toContain('"gulicode:blueprint-window-closed"')
    expect(sessionSource).toContain('"gulicode:blueprint-planning-submit"')
    expect(sessionSource).not.toContain("data-blueprint-floating-panel")
    expect(sessionSource).not.toContain("desktopBlueprintFloatingOpen")
    expect(blueprintWindowSource).toContain("data-blueprint-popout-window")
    expect(blueprintWindowSource).toContain("submitBlueprintWindowPlanning")
    expect(appSource).toContain('path="/blueprint-window/:id?"')
    expect(appSource).toContain("visualShell")
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
  })

  test("hides terminal nodes from new blueprint interactions", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const addOptions = source.slice(source.indexOf("const addOptions"), source.indexOf("const nodes"))
    const nodes = source.slice(source.indexOf("const nodes"), source.indexOf("const visibleNodeIds"))

    expect(addOptions).not.toContain('kind: "start" as const')
    expect(addOptions).not.toContain('kind: "end" as const')
    expect(nodes).not.toContain("draft.graph.terminal_nodes")
    expect(source).toContain("projectWorkdirAutoPromptShownThisApp")
  })

  test("renders common config help buttons with inspector tip behavior", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
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
    expect(source).toContain("invalidFields={configIssues().map((issue) => issue.field)}")
    expect(source).toContain("data-blueprint-global-config-toggle")
    expect(source).toContain("disabled={blueprintConfigLocked()}")
    expect(source).toContain("blueprint.globalConfig.locked")
    expect(source).toContain('variant="ghost"')
    expect(source).toContain("data-active={globalConfigOpen()}")
    expect(source).toContain("<Show when={globalConfigOpen() && !blueprintConfigLocked()}>")
    expect(source).toContain("if (open) setGlobalConfigOpen(false)")
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
    expect(agentPanel).toContain('statusField("current_message_id")')
    expect(agentPanel).toContain('statusField("last_error")')
    expect(agentPanel).toContain("stabilizeAgentPanelDisplayEvents(previous")
    expect(source).toContain("const AGENT_PANEL_DEFAULT_WIDTH = 420")
    expect(source).toContain("const AGENT_PANEL_DEFAULT_HEIGHT = 620")
    expect(agentPanel).not.toContain("agent panel size preset")
    expect(agentPanel).not.toContain("props.onSizePreset")
    expect(source).not.toContain("AGENT_PANEL_SIZE_PRESETS")
    expect(statusSummary).toContain('label="状态"')
    expect(statusSummary).toContain('label="队列"')
    expect(statusSummary).toContain('label="消息"')
    expect(statusSummary).toContain('label="忙碌"')
    expect(statusSummary).toContain("statusDetailsOpen")
    expect(statusSummary).toContain("toggle agent panel status details")
    expect(statusSummary).toContain("data-agent-panel-status-details")
    expect(statusSummary).toContain("运行状态")
    expect(statusSummary).toContain("JSON 位置")
    expect(agentPanel).toContain("状态详情")
    expect(agentPanel).toContain("when={visibleEvents().length}")
    expect(agentPanel).toContain("Index each={visibleEvents()}")
    expect(agentPanel).toContain("[overflow-anchor:none]")
    expect(agentPanel).toContain("{props.event.text}")
    expect(agentPanel).toContain("AgentPanelDisplayEventRow")
    expect(agentPanel).toContain("nestedToolItems")
    expect(agentPanel).toContain("(event().toolItems?.length ?? 0) > 1")
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
    const runtimePanel = source.slice(source.indexOf("function BlueprintRuntimePanel"), source.indexOf("function BlueprintNodeView"))

    expect(runtimePanel).toContain("status()?.outgoing_batches")
    expect(runtimePanel).toContain("status()?.joins")
    expect(runtimePanel).toContain("status()?.jobs")
    expect(runtimePanel).toContain("status()?.workspace")
    expect(runtimePanel).toContain("props.state.events")
    expect(runtimePanel).not.toContain("dispatchQueued")
    expect(runtimePanel).not.toContain("tick(")
  })
})
