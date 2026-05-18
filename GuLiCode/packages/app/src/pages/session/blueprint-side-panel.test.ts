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
  })
})

describe("blueprint runtime source", () => {
  test("starts by saving the project document and then calling runtime APIs", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()

    expect(source).toContain("createBlueprintStartPlan(draft)")
    expect(source).toContain("validateBlueprintConfigForStart(draft)")
    expect(source).toContain("BlueprintConfigRequiredDialog")
    expect(source).toContain("await persistProjectDraft(draft)")
    expect(source).toContain("platform.startBlueprintRun(")
    expect(source).toContain('"live"')
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

  test("renders common config help buttons with inspector tip behavior", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const configPanel = source.slice(source.indexOf("function BlueprintGlobalConfigPanel"), source.indexOf("function BlueprintConfigRequiredDialog"))
    const configField = source.slice(source.indexOf("function DirectoryConfigField"), source.indexOf("function blueprintConfigFieldLabel"))

    expect(configPanel).toContain('tip="projectWorkdir"')
    expect(configPanel).toContain('tip="skillDir"')
    expect(configPanel).toContain('tip="ruleDir"')
    expect(configField).toContain("InspectorFieldHeader")
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

  test("projects agent panel status and hides non-content stream events", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const agentPanel = source.slice(source.indexOf("function AgentInfoPanel"), source.indexOf("function BlueprintNodeView"))
    const visibleEvents = source.slice(source.indexOf("function visibleAgentPanelEvents"), source.indexOf("function agentStatusFieldText"))

    expect(visibleEvents).toContain('kind === "status"')
    expect(visibleEvents).toContain('kind === "message.started"')
    expect(visibleEvents).toContain('kind === "queue.updated"')
    expect(visibleEvents).toContain('kind === "tool.started"')
    expect(visibleEvents).toContain('kind === "tool.completed"')
    expect(visibleEvents).toContain('kind === "part.delta" || kind === "message.completed"')
    expect(visibleEvents).toContain("isAgentReplyTextEvent")
    expect(visibleEvents).toContain('partType === "text"')
    expect(visibleEvents).toContain('partType === "agent_message"')
    expect(visibleEvents).toContain("cleanAgentPanelReplyText")
    expect(visibleEvents).toContain("isCodexInternalLogLine")
    expect(visibleEvents).toContain("shouldReplaceAgentReplyDraft")
    expect(visibleEvents).toContain('"Agent 回复"')
    expect(agentPanel).toContain("latestAgentStatusEvent(props.events)")
    expect(agentPanel).toContain('statusField("busy_count")')
    expect(agentPanel).toContain('statusField("current_message_id")')
    expect(agentPanel).toContain('statusField("last_error")')
    expect(agentPanel).toContain("状态详情")
    expect(agentPanel).toContain("when={visibleEvents().length}")
    expect(agentPanel).toContain("For each={visibleEvents()}")
    expect(agentPanel).toContain("{event.text}")
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
