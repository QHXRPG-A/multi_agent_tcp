import { describe, expect, test } from "bun:test"
import { createTestAgentPanelSnapshot } from "./blueprint-test-agent-snapshot"

type AgentPanelProjection = (
  events: Array<Record<string, unknown>>,
  userMessages?: Array<Record<string, unknown>>,
  sessionTimelineEvents?: Array<Record<string, unknown>>,
  messageJournal?: Array<Record<string, unknown>>,
) => Array<Record<string, unknown>>

async function loadAgentPanelProjection(): Promise<AgentPanelProjection> {
  const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
  const projectionStart = source.indexOf("function visibleAgentPanelEvents")
  const projectionEnd = source.indexOf("function agentStatusFieldText")
  const textHelperStart = projectionEnd
  const textHelperEnd = source.indexOf("function formatRuntimeTime")
  const projectionSource = source.slice(projectionStart, projectionEnd)
  const textHelperSource = source.slice(textHelperStart, textHelperEnd)
  const script = `
function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined
}
${projectionSource}
${textHelperSource}
export { visibleAgentPanelEvents }
`
  const javascript = new Bun.Transpiler({ loader: "ts" }).transformSync(script)
  const module = await import(`data:text/javascript;base64,${Buffer.from(javascript).toString("base64")}`)
  return module.visibleAgentPanelEvents as AgentPanelProjection
}

async function loadBlueprintSessionVisibleKey(): Promise<(session: Record<string, unknown>) => string> {
  const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
  const helperStart = source.indexOf("function blueprintSessionVisibleKeySlug")
  const helperEnd = source.indexOf("function normalizeBlueprintSessionSummary")
  const helperSource = source.slice(helperStart, helperEnd)
  const script = `
${helperSource}
export { blueprintSessionVisibleKey }
`
  const javascript = new Bun.Transpiler({ loader: "ts" }).transformSync(script)
  const module = await import(`data:text/javascript;base64,${Buffer.from(javascript).toString("base64")}`)
  return module.blueprintSessionVisibleKey as (session: Record<string, unknown>) => string
}

async function loadExcelHistoryRecordDisplay(): Promise<(record: Record<string, unknown>) => Record<string, string>> {
  const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
  const helperStart = source.indexOf("type ExcelHistoryRecordDisplay")
  const helperEnd = source.indexOf("function normalizeScriptCatalogNodeFromJson")
  const helperSource = source.slice(helperStart, helperEnd)
  const script = `
function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : undefined
}
function arrayOfRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(asRecord).filter(Boolean) as Record<string, unknown>[] : []
}
function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined
}
function numberValue(value: unknown): number {
  const number = Number(value)
  return Number.isFinite(number) ? number : 0
}
function formatBlueprintSessionTimestamp(value: number) {
  const date = new Date(value)
  const pad = (part: number) => String(part).padStart(2, "0")
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
  ].join("-") + \` \${pad(date.getHours())}:\${pad(date.getMinutes())}:\${pad(date.getSeconds())}\`
}
${helperSource}
export { excelHistoryRecordDisplay }
`
  const javascript = new Bun.Transpiler({ loader: "ts" }).transformSync(script)
  const module = await import(`data:text/javascript;base64,${Buffer.from(javascript).toString("base64")}`)
  return module.excelHistoryRecordDisplay as (record: Record<string, unknown>) => Record<string, string>
}

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
    expect(agentBranch).not.toContain('label={language.t("blueprint.field.runPrompt")}')
    expect(agentBranch).toContain('tip="prompt"')
    expect(agentBranch).not.toContain('tip="runPrompt"')
    expect(agentBranch).toContain('value={props.selectedAgent?.prompt ?? ""}')
    expect(agentBranch).not.toContain('value={props.selectedAgent?.run_prompt ?? ""}')
    expect(agentBranch).not.toContain('onChange={(value) => updateAgentField("run_prompt", value)}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.skills")}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.rulePaths")}')
    expect(agentBranch).toContain("lockedValues={[frameworkSkillOption().value]}")
    expect(agentBranch).toContain("lockedOptions={[frameworkSkillOption()]}")
    expect(agentBranch).toContain("lockedValues={[frameworkRuleOption().value]}")
    expect(agentBranch).toContain("lockedOptions={[frameworkRuleOption()]}")
    expect(agentBranch).toContain('label={language.t("blueprint.field.adapterOptions")}')
    expect(agentBranch).toContain('props.selectedAgent?.node_type === "agent"')
    expect(agentBranch).toContain('label={language.t("blueprint.field.directProjectIo" as never)}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.outsideProjectIo" as never)}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.unrestrictedCommands" as never)}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.disableSandbox" as never)}')
    expect(agentBranch).toContain('label={language.t("blueprint.field.frameworkMessageTools" as never)}')
  })

  test("keeps framework skill and rule selections locked out of user edits", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const multiSelect = source.slice(source.indexOf("function MultiSelectField"), source.indexOf("function CheckboxField"))

    expect(source).toContain("FRAMEWORK_FULL_AGENT_SKILL_OPTION")
    expect(source).toContain("framework_assets/skills/framework-agent-runtime/SKILL.md")
    expect(source).toContain("FRAMEWORK_WORKER_AGENT_SKILL_OPTION")
    expect(source).toContain("framework_assets/skills/framework-worker-runtime/SKILL.md")
    expect(source).toContain("FRAMEWORK_FULL_AGENT_RULE_OPTION")
    expect(source).toContain("framework_assets/rules/framework-agent-runtime.md")
    expect(source).toContain("FRAMEWORK_WORKER_AGENT_RULE_OPTION")
    expect(source).toContain("framework_assets/rules/framework-worker-runtime.md")
    expect(source).toContain('props.selectedAgent?.node_type === "agent"')
    expect(source).toContain("FRAMEWORK_WORKER_AGENT_RULE_OPTION")
    expect(multiSelect).toContain("lockedValues?: string[]")
    expect(multiSelect).toContain("lockedOptions?: BlueprintCatalogItem[]")
    expect(multiSelect).toContain("const locked = () => new Set(props.lockedValues ?? [])")
    expect(multiSelect).toContain("const editableValues = () => props.values.filter((value) => !locked().has(value))")
    expect(multiSelect).toContain("if (locked().has(value)) return")
    expect(multiSelect).toContain("const next = new Set(editableValues())")
    expect(multiSelect).toContain("disabled={locked().has(option.value)}")
  })

  test("uses separate copy for agent description and Prompt node help", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const zh = await Bun.file(new URL("../../i18n/zh.ts", import.meta.url)).text()
    const en = await Bun.file(new URL("../../i18n/en.ts", import.meta.url)).text()

    expect(source).toContain("blueprint.tip.promptText.what")
    expect(source).toContain("blueprint.tip.promptTrigger.usage")
    expect(zh).toContain('"blueprint.field.prompt": "简介"')
    expect(zh).toContain('"blueprint.field.promptText": "提示词文本"')
    expect(zh).toContain("它不会作为运行提示词注入")
    expect(zh).toContain("多次触发会在每次派发时注入")
    expect(en).toContain('"blueprint.field.prompt": "Description"')
    expect(en).toContain('"blueprint.field.promptText": "Prompt text"')
    expect(en).toContain("it is not injected as the runtime prompt")
    expect(en).toContain("every message injects on each dispatch")
  })

  test("renders full Agent access policy controls and Worker copy", async () => {
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
    expect(en).toContain('"blueprint.node.workerAgent": "Worker"')
    expect(en).toContain('"blueprint.add.agent.description": "Full CLI node with direct project and system access"')
    expect(en).toContain('"blueprint.add.workerAgent.description": "Framework-managed worker with private workspace isolation"')
    expect(en).toContain('"blueprint.field.disableSandbox": "Disable sandbox"')
    expect(en).toContain("agent_dispatch, agent_context, agent_task_status, and join_contribute")
  })

  test("edits POPO forwarding on the saved start full Agent and marks POPO blueprints", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const en = await Bun.file(new URL("../../i18n/en.ts", import.meta.url)).text()
    const zh = await Bun.file(new URL("../../i18n/zh.ts", import.meta.url)).text()
    const zht = await Bun.file(new URL("../../i18n/zht.ts", import.meta.url)).text()
    const inspectorPanel = source.slice(source.indexOf("export function BlueprintInspector"), source.indexOf("function BlueprintGlobalConfigPanel"))
    const nodeView = source.slice(source.indexOf("function BlueprintNodeView"), source.indexOf("function PortButton"))

    expect(source).toContain('setDraft("graph", "agent_nodes", previousNodeId, "popo_entry", "enabled", false)')
    expect(inspectorPanel).toContain('updateAgentField("popo_entry"')
    expect(inspectorPanel).not.toContain('props.setStore("runtime", "popo_entry"')
    expect(inspectorPanel).toContain("otherEnabledPopoAgentId")
    expect(inspectorPanel).toContain("blueprint.popoEntry.lockedByAgent")
    expect(inspectorPanel).toContain("blueprint.popoEntry.startNodeOnly")
    expect(inspectorPanel).toContain('disabled={popoEntryDisabled()}')
    expect(inspectorPanel).toContain('checked={selectedPopoEntry().enabled === true}')
    expect(source).toContain("popoBlueprintAgent={")
    expect(nodeView).toContain("data-blueprint-popo-agent-badge")
    expect(nodeView).toContain("blueprint.popoEntry.activeBadge")
    expect(en).toContain('"blueprint.popoEntry.lockedByAgent"')
    expect(zh).toContain('"blueprint.popoEntry.lockedByAgent"')
    expect(zht).toContain('"blueprint.popoEntry.lockedByAgent"')
  })

  test("renders resident services panel and service controls", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const platform = await Bun.file(new URL("../../context/platform.tsx", import.meta.url)).text()
    const entry = await Bun.file(new URL("../../entry.tsx", import.meta.url)).text()

    expect(platform).toContain("listBlueprintResidentServices")
    expect(platform).toContain("startBlueprintResidentService")
    expect(entry).toContain('"blueprint.residentServices"')
    expect(entry).toContain('"blueprint.startResidentService"')
    expect(source).toContain("data-blueprint-resident-services-panel")
    expect(source).toContain("data-blueprint-resident-service")
    expect(source).toContain("data-blueprint-resident-console")
    expect(source).toContain("BlueprintResidentServiceCreateDialog")
    expect(source).toContain("platform.createBlueprintResidentService")
    expect(source).toContain("residentServiceErrorMessage")
    expect(source).toContain('"blueprint.resident.connectionFailed"')
    expect(source).toContain("refreshResidentServices({ silent: true })")
    expect(source).toContain("RESIDENT_SERVICE_PAGE_SIZE = 5")
    expect(source).toContain("residentServiceSearchQuery")
    expect(source).toContain("residentServicePage")
    expect(source).toContain("residentServiceCollapsed")
    expect(source).toContain("residentServicePanelPosition")
    expect(source).toContain("clampResidentServicePanelPosition")
    expect(source).toContain("data-blueprint-resident-drag-handle")
    expect(source).toContain("setPointerCapture")
    expect(source).toContain("releasePointerCapture")
    expect(source).toContain("data-blueprint-resident-search")
    expect(source).toContain("data-blueprint-resident-pagination")
    expect(source).toContain("data-blueprint-resident-page-first")
    expect(source).toContain("data-blueprint-resident-page-prev")
    expect(source).toContain("data-blueprint-resident-page-next")
    expect(source).toContain("data-blueprint-resident-page-last")
    expect(source).toContain("data-blueprint-resident-toggle")
    expect(source).toContain('aria-expanded={!residentServiceCollapsed()}')
    expect(source).toContain('"blueprint.resident.noMatches"')
    expect(source).not.toContain("normalizedResidentServiceSearch() && services().length > 0")
  })

  test("renders global POPO callback service control drawer", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const platform = await Bun.file(new URL("../../context/platform.tsx", import.meta.url)).text()
    const entry = await Bun.file(new URL("../../entry.tsx", import.meta.url)).text()
    const en = await Bun.file(new URL("../../i18n/en.ts", import.meta.url)).text()
    const zh = await Bun.file(new URL("../../i18n/zh.ts", import.meta.url)).text()

    expect(platform).toContain("BlueprintPopoRobot")
    expect(platform).toContain("blueprintPopoServiceStatus")
    expect(platform).toContain("listBlueprintPopoRobots")
    expect(platform).toContain("saveBlueprintPopoRobot")
    expect(platform).toContain("deleteBlueprintPopoRobot")
    expect(platform).toContain("setBlueprintPopoRobotEnabled")
    expect(entry).toContain('"service.popoStatus"')
    expect(entry).toContain('"blueprint.popo.robots"')
    expect(entry).toContain('"blueprint.popo.robot.save"')
    expect(entry).toContain('"blueprint.popo.robot.delete"')
    expect(entry).toContain('"blueprint.popo.robot.enabled"')
    expect(source).toContain("data-blueprint-control-toggle")
    expect(source).toContain("data-blueprint-control-handle")
    expect(source).toContain("data-blueprint-control-drawer")
    expect(source).toContain("function BlueprintControlDrawer")
    expect(source).toContain("function BlueprintPopoServicePanel")
    expect(source).toContain("function BlueprintPopoRobotEditor")
    expect(source).toContain("data-blueprint-popo-service-panel")
    expect(source).toContain("data-blueprint-popo-robot")
    expect(source).toContain("data-blueprint-popo-robot-enabled")
    expect(source).toContain("data-blueprint-popo-robot-app-key")
    expect(source).toContain("data-blueprint-popo-robot-secret")
    expect(source).toContain("data-blueprint-popo-robot-token")
    expect(source).toContain("data-blueprint-popo-robot-aes")
    expect(source).toContain("callbackUrlTemplate")
    expect(source).toContain("legacyCallbackUrl")
    expect(source).toContain("onSaveRobot={savePopoRobot}")
    expect(source).toContain("onDeleteRobot={deletePopoRobot}")
    expect(source).toContain("onToggleRobot={setPopoRobotEnabled}")
    expect(source).not.toContain("BlueprintCollaborationAuthPanel")
    expect(en).toContain('"blueprint.popoService.title": "POPO Callback Service"')
    expect(en).toContain('"blueprint.popoService.appKeyPlaceholder": "Robot AppKey"')
    expect(zh).toContain('"blueprint.popoService.title": "POPO 回调服务"')
  })
  test("renders planning form history in the Blueprint Control drawer", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const platform = await Bun.file(new URL("../../context/platform.tsx", import.meta.url)).text()
    const entry = await Bun.file(new URL("../../entry.tsx", import.meta.url)).text()
    const en = await Bun.file(new URL("../../i18n/en.ts", import.meta.url)).text()
    const zh = await Bun.file(new URL("../../i18n/zh.ts", import.meta.url)).text()
    const zht = await Bun.file(new URL("../../i18n/zht.ts", import.meta.url)).text()
    const controlDrawer = source.slice(source.indexOf("function BlueprintControlDrawer"), source.indexOf("function BlueprintPopoServicePanel"))
    const detailDialog = source.slice(source.indexOf("function BlueprintExcelHistoryDetailDialog"), source.indexOf("function BlueprintExcelHistoryRecordView"))
    const recordView = source.slice(source.indexOf("function BlueprintExcelHistoryRecordView"), source.indexOf("function BlueprintPopoServicePanel"))

    expect(platform).toContain("BlueprintSessionExcelHistorySummary")
    expect(platform).toContain("BlueprintSessionExcelHistoryRecord")
    expect(platform).toContain("BlueprintSessionExcelHistory")
    expect(platform).toContain("listBlueprintSessionExcelHistory?")
    expect(platform).toContain("blueprintSessionExcelHistory?")
    expect(entry).toContain("listBlueprintSessionExcelHistory: async")
    expect(entry).toContain("blueprintSessionExcelHistory: async")
    expect(entry).toContain('"blueprint.sessions.excelHistoryList"')
    expect(entry).toContain('"blueprint.sessions.excelHistory"')
    expect(source).toContain("function BlueprintExcelHistoryPanel")
    expect(source).toContain("function BlueprintExcelHistoryDetailDialog")
    expect(source).toContain("function BlueprintExcelHistoryRecordView")
    expect(detailDialog).toContain('size="x-large"')
    expect(source).toContain("data-blueprint-excel-history-panel")
    expect(source).toContain("data-blueprint-excel-history-session")
    expect(source).toContain("data-blueprint-excel-history-dialog")
    expect(source).toContain("data-blueprint-excel-history-table")
    expect(source).toContain("data-blueprint-excel-history-header")
    expect(source).toContain("data-blueprint-excel-history-record")
    expect(source).toContain("refreshBlueprintExcelHistory({ silent: true })")
    expect(source).toContain("onOpenExcelHistory={openBlueprintExcelHistoryDialog}")
    expect(recordView).toContain("excelHistoryRecordDisplay")
    expect(source).toContain("blueprint.excelHistory.time")
    expect(source).toContain("blueprint.excelHistory.status")
    expect(source).toContain("blueprint.excelHistory.command")
    expect(source).toContain("blueprint.excelHistory.workbook")
    expect(source).toContain("blueprint.excelHistory.location")
    expect(recordView).not.toContain("userSummary")
    expect(recordView).not.toContain("<pre")
    expect(controlDrawer).toContain("BlueprintPopoServicePanel")
    expect(controlDrawer).toContain("BlueprintExcelHistoryPanel")
    expect(controlDrawer.indexOf("BlueprintPopoServicePanel")).toBeLessThan(controlDrawer.indexOf("BlueprintExcelHistoryPanel"))
    expect(en).toContain('"blueprint.excelHistory.title": "Planning form records"')
    expect(en).toContain('"blueprint.excelHistory.location": "Row / column"')
    expect(zh).toContain('"blueprint.excelHistory.time"')
    expect(zh).toContain('"blueprint.excelHistory.location"')
    expect(zht).toContain('"blueprint.excelHistory.time"')
    expect(zht).toContain('"blueprint.excelHistory.location"')
    expect(zh).toContain('"blueprint.excelHistory.title": "策划填表记录"')
    expect(zht).toContain('"blueprint.excelHistory.title": "策劃填表記錄"')
  })
})

describe("blueprint session display helpers", () => {
  test("shows POPO session keys with blueprint names instead of hash suffixes", async () => {
    const visibleKey = await loadBlueprintSessionVisibleKey()
    const originalKey = "bps_popo_qiuhaoxuan-corp.netease.com_25d80afe394bf1a3ef20066e"

    expect(visibleKey({
      sessionKey: originalKey,
      source: "popo",
      blueprintName: "fill planning form",
    })).toBe("bps_popo_qiuhaoxuan-corp.netease.com_fill-planning-form")
    expect(visibleKey({
      sessionKey: originalKey,
      source: "popo",
      blueprintName: "",
      blueprintId: "fallback blueprint",
    })).toBe("bps_popo_qiuhaoxuan-corp.netease.com_fallback-blueprint")
    expect(visibleKey({
      sessionKey: originalKey,
      source: "popo",
      blueprintName: "填表 结构",
    })).toBe("bps_popo_qiuhaoxuan-corp.netease.com_填表-结构")
    expect(visibleKey({
      sessionKey: originalKey,
      source: "ui",
      blueprintName: "fill planning form",
    })).toBe(originalKey)
    expect(visibleKey({
      sessionKey: "main+fill-planning-form",
      source: "ui",
      blueprintName: "fill planning form",
    })).toBe("main+fill-planning-form")
    expect(visibleKey({
      sessionKey: "bps_popo_qiuhaoxuan-corp.netease.com+fill-planning-form",
      source: "popo",
      blueprintName: "fill planning form",
    })).toBe("bps_popo_qiuhaoxuan-corp.netease.com+fill-planning-form")
  })

  test("formats Excel history records into compact display rows", async () => {
    const display = await loadExcelHistoryRecordDisplay()

    expect(display({
      time: "2026-06-12 15:31:41.667",
      status: "succeeded",
      serviceName: "xltool",
      methodName: "run",
      arguments: {
        command: "read-row",
        arguments: {
          file: "F:\\src\\Package\\Script\\Python\\trunk\\策划表格\\15-0-图标表-18000+.xlsx",
          sheet: "图标表",
          row: 6752,
        },
      },
    })).toMatchObject({
      time: "2026-06-12 15:31:41",
      status: "succeeded",
      command: "read-row",
      workbookLabel: "15-0-图标表-18000+.xlsx",
      location: "图标表 row 6752",
    })

    expect(display({
      status: "failed",
      command: "set-cells",
      beforeAfter: [
        {
          workbook: "C:\\tables\\15-0.xlsx",
          sheet: "图标表",
          cell: "F6751",
          row: 6751,
          column: "F",
          field: "is_download",
        },
        {
          workbook: "C:\\tables\\15-0.xlsx",
          sheet: "图标表",
          cell: "G6751",
          row: 6751,
          column: "G",
          field: "default_icon_path",
        },
      ],
    })).toMatchObject({
      command: "set-cells",
      workbookLabel: "15-0.xlsx",
      location: "图标表 row 6751: is_download, default_icon_path",
    })

    expect(display({
      category: "table_queue",
      serviceName: "table_queue",
      methodName: "release",
      arguments: { tableNames: ["15-0-图标表-18000+.xlsx"] },
    })).toMatchObject({
      command: "table_queue.release",
      workbookLabel: "15-0-图标表-18000+.xlsx",
      location: "-",
    })
  })
})

describe("blueprint project persistence source", () => {
  test("lists project blueprints, opens the selected document, and keeps local fallback", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const entry = await Bun.file(new URL("../../entry.tsx", import.meta.url)).text()
    const en = await Bun.file(new URL("../../i18n/en.ts", import.meta.url)).text()
    const zh = await Bun.file(new URL("../../i18n/zh.ts", import.meta.url)).text()
    const zht = await Bun.file(new URL("../../i18n/zht.ts", import.meta.url)).text()

    expect(source).toContain("const openBlueprint = platform.openBlueprint")
    expect(source).toContain("platform.listBlueprints")
    expect(source).toContain("platform.deleteBlueprint")
    expect(source).toContain("initialBlueprintId?: string")
    expect(source).toContain('const routeInitialBlueprintId = () => props.initialBlueprintId?.trim() || ""')
    expect(source).toContain("const requestedBlueprintId = initialBlueprintId()")
    expect(source).toContain("blueprintWorkbenchProjectDirectory() || decode64(params.dir) || \"global\"")
    expect(source).toContain("await refreshProjectBlueprints(requestedBlueprintId)")
    expect(source).toContain("await loadProjectBlueprint(targetBlueprintId, targetBlueprintName)")
    expect(source).toContain("await openBlueprint(projectDirectory, blueprintId)")
    expect(source).toContain("toBlueprintDocument(next, currentBlueprintId(), currentBlueprintName())")
    expect(source).toContain("saveDraftNow={(next) => void saveProjectDraft(next)}")
    expect(source).toContain('if (field === "model") props.saveDraftNow?.(next)')
    expect(source).toContain("syncWorkbenchBlueprintRoute(documentId)")
    expect(source).toContain("syncWorkbenchBlueprintRoute(blueprintId)")
    expect(source).toContain("data-blueprint-document-select")
    expect(source).toContain("data-blueprint-document-create")
    expect(source).toContain("data-blueprint-document-delete")
    expect(source).toContain("handleBlueprintDocumentItemSelect(event, item.id)")
    expect(source).toContain("pendingBlueprintDocumentDeleteId === blueprintId")
    expect(source).toContain("requestBlueprintDocumentDelete(item.id)")
    expect(source).toContain("BlueprintCreateDialog")
    expect(source).toContain("BlueprintDeleteDialog")
    expect(source).toContain("openDeleteBlueprintDialog")
    expect(source).toContain("createDefaultProjectBlueprintAfterDelete")
    expect(source).toContain("uniqueBlueprintId")
    expect(source).not.toContain("toBlueprintDocument(next, DEFAULT_BLUEPRINT_ID, DEFAULT_BLUEPRINT_NAME)")
    expect(source).toContain('code === "NOT_FOUND"')
    expect(source).toContain("await saveProjectDraft(draft)")
    expect(source).toContain('source: "local"')
    expect(source).toContain("error: readableError(error)")
    expect(source).toContain("function BlueprintHeaderStatus")
    expect(source).toContain("data-blueprint-header-status-trigger")
    expect(source).toContain("data-blueprint-header-status-details")
    expect(entry).toContain('location.pathname.match(/^\\/([^/]+)\\/blueprint-window')
    expect(entry).toContain("location.pathname !== targetRoute")
    expect(en).toContain('"blueprint.document.delete": "Delete blueprint"')
    expect(en).toContain('"blueprint.document.deleteConfirm":')
    expect(zh).toContain('"blueprint.document.delete": "删除蓝图"')
    expect(zht).toContain('"blueprint.document.delete": "刪除藍圖"')
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
  test("sends runtime input through the BlueprintSession message entrypoint", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const snapshotSource = source.slice(source.indexOf("function createDesktopBlueprintSnapshot"), source.indexOf("function desktopSnapshotNodeState"))

    expect(source).not.toContain("BlueprintCollaborationAuthPanel")
    expect(source).toContain("postDesktopBlueprintSnapshot")
    expect(snapshotSource).toContain("const layout = draft.layout.nodes[id]")
    expect(snapshotSource).toContain("x: layout?.x")
    expect(snapshotSource).toContain("y: layout?.y")
    expect(source).toContain("BlueprintConfigRequiredDialog")
    expect(source).toContain('if (external) return external')
    expect(source).not.toContain("buildBlueprintPlanningMessage")
    expect(source).not.toContain("props.onBlueprintPlanningSubmit")
    expect(source).not.toContain("refreshBlueprintPlanningRequest")
    expect(source).not.toContain("platform.blueprintWindowPlanningStatus")
    expect(source).not.toContain("cancelBlueprintPlanningRequest")
    expect(source).not.toContain("platform.cancelBlueprintWindowPlanning")
    expect(source).not.toContain("blueprintPlanningRequestCancelAvailable")
    expect(source).not.toContain("data-blueprint-progress-close")
    expect(source).not.toContain("blueprint.progress.cancelPlanning")
    expect(source).not.toContain("planningRequest")
    expect(source).not.toContain("data-blueprint-runtime-planning-request")
    expect(source).not.toContain("blueprintPlanningBridgeAvailable")
    expect(source).not.toContain("submitBlueprintPlanningTask")
    expect(source).toContain("runtimeStartNodeId")
    expect(source).toContain('.filter(([, node]) => node.node_type === "agent")')
    expect(source).not.toContain("platform.startBlueprintSlot")
    expect(source).not.toContain("platform.sendBlueprintSlotMessage")
    expect(source).toContain("async function submitBlueprintSessionMessage(message: string)")
    expect(source).toContain("platform.sendBlueprintSessionMessage")
    expect(source).toContain("sessionKey: currentBlueprintSessionKey()")
    expect(source).toContain('source: "ui"')
    expect(source).not.toContain("createBlueprintStartPlan(")
    expect(source).not.toContain("platform.startBlueprintRun")
    expect(source).toContain("data-blueprint-runtime-start-node-select")
    expect(source).toContain("selectedStartNodeId")
    expect(source).toContain("onStartNodeSelect")
    expect(source).not.toContain("data-blueprint-runtime-task-input")
    expect(source).not.toContain("data-blueprint-runtime-plan-create")
    expect(source).not.toContain("data-blueprint-runtime-confirm-run")
    expect(source).not.toContain("data-blueprint-runtime-slot-message")
    expect(source).toContain("data-blueprint-runtime-session-message")
    expect(source).toContain("data-blueprint-runtime-toggle")
    expect(source).toContain("data-blueprint-runtime-panel-handle")
    expect(source).toContain("data-blueprint-runtime-panel-ghost")
    expect(source).toContain("data-blueprint-runtime-panel-placeholder")
    expect(source).toContain("reorderRuntimePanels")
    expect(source).toContain("runtimePanelShellProps")
    expect(source).not.toContain("onStart={openRuntimePlanningPanel}")
    expect(source).toContain("platform.blueprintRunStatus(runId)")
    expect(source).toContain("platform.blueprintRecentEvents?.(runId, 50)")
    expect(source).toContain("selectPreferredRuntimeRun(runs, untrack(() => runtime().runId))")
    expect(source).toContain("platform.listBlueprintSessions")
    expect(source).toContain("platform.restartBlueprintSessions")
    expect(source).toContain("async function restartCurrentBlueprintSessions()")
    expect(source).toContain("data-blueprint-session-select")
    expect(source).toContain("data-blueprint-session-card")
    expect(source).toContain("data-blueprint-session-restart")
    expect(source).toContain("data-blueprint-session-delete")
    expect(source).toContain("const visibleKey = () => blueprintSessionVisibleKey(session)")
    expect(source).toContain("title={visibleKey()}>{visibleKey()}")
    expect(source).toContain("props.onSelect(session.sessionKey)")
    expect(source).toContain("props.onRestart()")
    expect(source).toContain("props.onDelete(session.sessionKey)")
    expect(source).toContain("formatBlueprintSessionTimestamp(value())")
    expect(source).toContain("function formatBlueprintSessionTimestamp")
    expect(source).toContain("runtimeRunIsActive(preferredRun)")
    expect(source).toContain("isTerminalRuntimeStatus(currentStatus)")
    expect(source).toContain("const interval = setInterval(syncRuns, 2000)")
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

  test("clears the current session through a dedicated history-clear command", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const platform = await Bun.file(new URL("../../context/platform.tsx", import.meta.url)).text()
    const entry = await Bun.file(new URL("../../entry.tsx", import.meta.url)).text()
    const en = await Bun.file(new URL("../../i18n/en.ts", import.meta.url)).text()
    const zh = await Bun.file(new URL("../../i18n/zh.ts", import.meta.url)).text()
    const clearFunction = source.slice(
      source.indexOf("async function clearCurrentBlueprintSession"),
      source.indexOf("function openClearCurrentBlueprintSessionDialog"),
    )
    const runtimePanel = source.slice(source.indexOf("function BlueprintRuntimePanel"), source.indexOf("function RuntimeActionButton"))

    expect(platform).toContain("clearBlueprintSession?")
    expect(entry).toContain("clearBlueprintSession: async")
    expect(entry).toContain('"blueprint.sessions.clear"')
    expect(clearFunction).toContain("platform.clearBlueprintSession(sessionKey")
    expect(clearFunction).toContain('action: "clear-session"')
    expect(clearFunction).toContain("setBlueprintSessionTimeline({ sessionKey, events: [], loading: false })")
    expect(clearFunction).not.toContain("terminateBlueprintSession")
    expect(source).toContain("function openClearCurrentBlueprintSessionDialog")
    expect(source).toContain("BlueprintSessionClearDialog")
    expect(source).toContain("data-blueprint-session-clear-dialog")
    expect(source).toContain("onClearSession={openClearCurrentBlueprintSessionDialog}")
    expect(runtimePanel).toContain('"blueprint.runtime.clearSession"')
    expect(runtimePanel).toContain('"blueprint.runtime.clearSessionDescription"')
    expect(runtimePanel).toContain("disabled={!props.currentSession || props.state.loading || props.clearSessionDisabled}")
    expect(en).toContain('"blueprint.runtime.clearSession": "Clear current session"')
    expect(zh).toContain('"blueprint.runtime.clearSession": "清理当前会话"')
  })

  test("opens blueprint panels in an independent desktop window without redundant popout chrome", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const sessionSource = await Bun.file(new URL("../session.tsx", import.meta.url)).text()
    const blueprintWindowSource = await Bun.file(new URL("./blueprint-window.tsx", import.meta.url)).text()
    const sidePanelSource = await Bun.file(new URL("./session-side-panel.tsx", import.meta.url)).text()
    const layoutSource = await Bun.file(new URL("../../context/layout.tsx", import.meta.url)).text()
    const appSource = await Bun.file(new URL("../../app.tsx", import.meta.url)).text()
    const entrySource = await Bun.file(new URL("../../entry.tsx", import.meta.url)).text()
    const platformSource = await Bun.file(new URL("../../context/platform.tsx", import.meta.url)).text()

    expect(source).toContain("data-blueprint-float-handle")
    expect(source).toContain("<Show when={!props.floating}>")
    expect(source).not.toContain("data-blueprint-dock-button")
    expect(source).toContain("BLUEPRINT_FLOAT_DRAG_THRESHOLD")
    expect(source).toContain("platform.openBlueprintWindow")
    expect(source).toContain("platform.closeBlueprintWindow")
    expect(source).toContain("const layout = props.floating ? undefined : useLayout()")
    expect(source).toContain("view().blueprintPanel.float(rect)")
    expect(source).toContain("await platform.openBlueprintWindow(projectDirectory, params.id, rect)")
    expect(sessionSource).toContain('"gulicode:blueprint-window-dock"')
    expect(sessionSource).toContain('"gulicode:blueprint-window-closed"')
    expect(sessionSource).not.toContain('"gulicode:blueprint-planning-submit"')
    expect(sessionSource).not.toContain("data-blueprint-floating-panel")
    expect(sessionSource).not.toContain("desktopBlueprintFloatingOpen")
    expect(blueprintWindowSource).toContain("data-blueprint-popout-window")
    expect(blueprintWindowSource).toContain("const workbenchInitialBlueprintId = () => (window.__GULICODE_BP__ ? params.id : undefined)")
    expect(blueprintWindowSource).toContain("initialBlueprintId={workbenchInitialBlueprintId()}")
    expect(blueprintWindowSource).not.toContain("submitBlueprintWindowPlanning")
    expect(blueprintWindowSource).not.toContain("onBlueprintPlanningSubmit")
    expect(appSource).toContain('path="/blueprint-window/:id?"')
    expect(appSource).toContain('path="/:dir/blueprint-window/:id?"')
    expect(appSource).toContain("const StandaloneBlueprintWindowRoute = () => <BlueprintWindow />")
    expect(appSource).toContain("fallback={<StandaloneRouted />}")
    expect(appSource).toContain("visualShell")
    expect(appSource).toContain("disableServerSync")
    expect(appSource).toContain("<Show when={!props.disableServerSync}")
    expect(entrySource).not.toContain("planningThreadId")
    expect(entrySource).not.toContain('"blueprint.planning.submit"')
    expect(entrySource).not.toContain('"blueprint.planning.status"')
    expect(entrySource).not.toContain('"blueprint.planning.cancel"')
    expect(platformSource).not.toContain("cancelBlueprintWindowPlanning?")
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
    expect(nodeView).toContain("props.onPointerEnter?.()")
    expect(nodeView).toContain('const portShape = (side: "input" | "output", portName: string) =>')
    expect(source).toContain("function nodePortShape")
    expect(source).toContain('item.node.kind === "branch" && side === "input"')
    expect(nodeView).toContain('shape={portShape("input", port.name)}')
    expect(nodeView).toContain('shape={portShape("output", port.name)}')
    expect(source).toContain('type BlueprintCanvasPortShape = "circle" | "triangle"')
    expect(source).toContain("data-blueprint-port-shape={props.shape}")
    expect(source).toContain('props.shape === "circle" && props.side === "input"')
    expect(source).toContain('props.shape === "circle" && props.side === "output"')
    expect(source).toContain("h-2.5 w-2.5 rounded-full")
  })

  test("renders agent ring panel, settings, shortcut, and hover highlights", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const model = await Bun.file(new URL("./blueprint-model.ts", import.meta.url)).text()
    const en = await Bun.file(new URL("../../i18n/en.ts", import.meta.url)).text()
    const zh = await Bun.file(new URL("../../i18n/zh.ts", import.meta.url)).text()
    const zht = await Bun.file(new URL("../../i18n/zht.ts", import.meta.url)).text()

    expect(model).toContain("export function agentRingsForDraft")
    expect(model).toContain("agent_ring_max_circulations")
    expect(model).toContain("agent_ring_context_refresh_periods")
    expect(model).toContain("context_refresh_period")
    expect(source).toContain("agentRingsForDraft(draft)")
    expect(source).toContain("runtimeRingStatus")
    expect(source).toContain("hoveredAgentRingNodeId")
    expect(source).toContain("highlightedRingKeys")
    expect(source).toContain("highlightedRingEdgeIds")
    expect(source).toContain("highlightedRingNodeIds")
    expect(source).toContain("ringHighlighted={highlightedRingNodeIds().has(item.id)}")
    expect(source).toContain("props.ringHighlighted")
    expect(source).toContain("event.key.toLowerCase() === \"r\"")
    expect(source).toContain("isEditableEventTarget(event.target)")
    expect(source).toContain("openRingPanel()")
    expect(source).toContain("data-blueprint-ring-panel")
    expect(source).toContain("data-blueprint-ring-panel-header")
    expect(source).toContain("data-blueprint-ring-card")
    expect(source).toContain("data-blueprint-ring-settings")
    expect(source).toContain("data-blueprint-ring-panel-resize")
    expect(source).toContain("data-blueprint-ring-max-circulations")
    expect(source).toContain("data-blueprint-ring-context-refresh-period")
    expect(source).toContain('type: "ring-panel-move"')
    expect(source).toContain('type: "ring-panel-resize"')
    expect(source).toContain("handleRingPanelMovePointerDown")
    expect(source).toContain("handleRingPanelResizePointerDown")
    expect(source).toContain("onDblClick={() => props.onOpenDetail(ring)}")
    expect(source).toContain("runtimeActive={runtimeRunActive()}")
    expect(source).toContain("blueprint.ring.runningReadOnly")
    expect(source).toContain('setDraft("graph", "agent_ring_max_circulations"')
    expect(source).toContain('setDraft("graph", "agent_ring_context_refresh_periods"')
    for (const locale of [en, zh, zht]) {
      expect(locale).toContain('"blueprint.ring.title"')
      expect(locale).toContain('"blueprint.ring.settings"')
      expect(locale).toContain('"blueprint.ring.maxCirculations"')
      expect(locale).toContain('"blueprint.ring.contextRefreshPeriod"')
      expect(locale).toContain('"blueprint.ring.runningReadOnly"')
    }
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
    expect(addOptions).not.toContain('kind: "route-sequence" as const')
    expect(addOptions).not.toContain('kind: "route-parallel" as const')
    expect(addOptions).not.toContain('kind: "route-parallel-reduce" as const')
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
    expect(source).toContain("onScriptSettings")
    expect(source).toContain('"blueprint.context.scriptSettings"')
    expect(source).toContain('updateScriptField("feedback_only", checked)')
    expect(source).toContain('updateScriptField("require_call_before_dispatch", checked)')
    expect(source).toContain('"blueprint.field.scriptFeedbackOnly"')
    expect(source).toContain('"blueprint.field.scriptRequireCallBeforeDispatch"')
    expect(source).toContain('kind: "prompt" as const')
    expect(source).toContain('type: "prompt" as const')
    expect(source).toContain("data-blueprint-prompt-node")
    expect(source).toContain("data-blueprint-prompt-editor")
    expect(source).toContain("data-blueprint-prompt-dialog")
    expect(source).toContain("data-blueprint-prompt-dialog-header")
    expect(source).toContain("data-blueprint-prompt-dialog-resize")
    expect(source).toContain("data-blueprint-prompt-dialog-editor")
    expect(source).toContain("data-blueprint-prompt-trigger")
    expect(source).toContain("updatePromptNode(draft, item.id")
    expect(source).toContain("openPromptEditor(item.id)")
    expect(source).toContain("handlePromptDoubleClick")
    expect(source).toContain("onDblClick={handlePromptDoubleClick}")
    expect(source).toContain("handlePromptEditorMovePointerDown")
    expect(source).toContain('type: "prompt-editor-move"')
    expect(source).toContain("handlePromptEditorResizePointerDown")
    expect(source).toContain('type: "prompt-editor-resize"')
    expect(source).toContain("syncPromptEditorSize")
    expect(source).toContain("ResizeObserver")
    expect(source).toContain("cursor-move")
    expect(source).toContain("cursor-nwse-resize")
    expect(source).not.toContain('resize: "both"')
    expect(source).toContain("PROMPT_NODE_HEIGHT")
    expect(source).not.toContain("PROMPT_NODE_COLLAPSED_HEIGHT")
    expect(source).not.toContain("PROMPT_NODE_EXPANDED_HEIGHT")
    const promptInspectorBranch = source.slice(source.indexOf("<Match when={props.selectedPrompt"), source.indexOf("<Match when={props.selectedScript"))
    expect(promptInspectorBranch).not.toContain('updatePromptField("expanded"')
    expect(promptInspectorBranch).not.toContain("blueprint.field.expanded")
    expect(source).toContain("data-blueprint-agent-collapse-toggle")
    expect(source).toContain("data-blueprint-agent-port-label")
    expect(source).toContain("AGENT_INPUT_PORT_DEFINITIONS")
    expect(source).toContain("AGENT_OUTPUT_PORT_DEFINITIONS")
    expect(source).toContain("function agentNodePorts")
    expect(source).toContain("function agentPortY")
    expect(source).toContain('title: "prompt: str"')
    expect(source).not.toContain("data-blueprint-agent-prompt-port-menu")
    expect(source).not.toContain("data-blueprint-agent-prompt-port-toggle")
    expect(source).not.toContain("setAgentPromptInputEnabled")
    expect(source).toContain("AGENT_PROMPT_INPUT_PORT")
    expect(source).toContain('shape: "triangle"')
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
      expect(locale).toContain('"blueprint.context.scriptSettings"')
      expect(locale).toContain('"blueprint.field.scriptFeedbackOnly"')
      expect(locale).toContain('"blueprint.field.scriptRequireCallBeforeDispatch"')
      expect(locale).toContain('"blueprint.node.prompt"')
      expect(locale).toContain('"blueprint.add.prompt.description"')
      expect(locale).toContain('"blueprint.prompt.trigger.once"')
      expect(locale).toContain('"blueprint.prompt.trigger.always"')
      expect(locale).toContain('"blueprint.agent.expand"')
      expect(locale).toContain('"blueprint.agent.collapse"')
      expect(locale).not.toContain('"blueprint.agentPromptPort.add"')
      expect(locale).not.toContain('"blueprint.agentPromptPort.remove"')
    }
  })

  test("renders common config help buttons with inspector tip behavior", async () => {
    const source = await Bun.file(new URL("./blueprint-side-panel.tsx", import.meta.url)).text()
    const entry = await Bun.file(new URL("../../entry.tsx", import.meta.url)).text()
    const configPanel = source.slice(source.indexOf("function BlueprintGlobalConfigPanel"), source.indexOf("function BlueprintConfigRequiredDialog"))
    const pathListField = source.slice(source.indexOf("function PathListConfigField"), source.indexOf("function DirectoryConfigField"))
    const configField = source.slice(source.indexOf("function DirectoryConfigField"), source.indexOf("function blueprintConfigFieldLabel"))

    expect(configPanel).toContain('tip="pythonPath"')
    expect(configPanel).toContain('tip="projectWorkdir"')
    expect(configPanel).toContain('tip="skillDir"')
    expect(configPanel).toContain('tip="ruleDir"')
    expect(configPanel).toContain("PathListConfigField")
    expect(configPanel).toContain("updateSkillDirs")
    expect(configPanel).toContain("updateRuleDirs")
    expect(configPanel).toContain("effectiveBlueprintSkillDirs(props.config)")
    expect(configPanel).toContain("effectiveBlueprintRuleDirs(props.config)")
    expect(configPanel).toContain('language.t("blueprint.field.pythonPath")')
    expect(configPanel).toContain('language.t("blueprint.field.skillDir")')
    expect(configPanel).toContain('language.t("blueprint.field.ruleDir")')
    expect(configPanel).toContain('language.t("blueprint.directory.pickPython")')
    expect(configPanel).toContain('language.t("blueprint.directory.pickSkill")')
    expect(configPanel).toContain('language.t("blueprint.directory.pickRule")')
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
    expect(pathListField).toContain("data-blueprint-path-list-field")
    expect(pathListField).toContain("data-blueprint-path-list-item")
    expect(pathListField).toContain("data-blueprint-path-list-empty")
    expect(pathListField).toContain('icon="folder"')
    expect(pathListField).toContain('icon="close-small"')
    expect(pathListField).toContain('language.t("blueprint.globalConfig.unset")')
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
    expect(source).toContain('codex: ["gpt-5.5", "gpt-5.4"]')
    expect(entry).toContain('blueprintRequest(config, "blueprint.listSkills", blueprintCatalogDirsPayload(dirs))')
    expect(entry).toContain('blueprintRequest(config, "blueprint.listRules", blueprintCatalogDirsPayload(dirs))')
    expect(entry).toContain("blueprintCatalogDirsPayload")
    expect(entry).toContain("listBlueprintModels: async (cliKind: string) =>")
    expect(entry).toContain('blueprintRequest(config, "blueprint.listModels", { cliKind })')
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
    expect(source).not.toContain('joinProjectPath(projectRoot, "skill_list")')
    expect(source).toContain("platform.listBlueprintSkills?.(skillDirs)")
    expect(source).toContain("platform.listBlueprintRules?.(ruleDirs)")
    expect(source).toContain('skillDirs,')
    expect(source).toContain('ruleDirs,')
    expect(source).toContain('skillDir: skillDirs[0] ?? "$CODEX_HOME/skills"')
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
    expect(visibleEvents).toContain("agentPanelTimelineItems(events, userMessages, sessionTimelineEvents, messageJournal)")
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
    expect(visibleEvents).toContain("agentPanelTextEventContentText(event)")
    expect(visibleEvents).toContain("agentPanelStreamingEntryKey(input.event")
    expect(visibleEvents).toContain("const partId = stringValue(event.part_id)")
    expect(visibleEvents).toContain('"Agent 回复"')
    expect(visibleEvents).toContain("userMessages: AgentPanelUserMessage[] = []")
    expect(visibleEvents).toContain("sessionTimelineEvents: BlueprintSessionTimelineEvent[] = []")
    expect(visibleEvents).toContain("messageJournal: Record<string, unknown>[] = []")
    expect(visibleEvents).toContain("agentPanelDisplayEventFromMessageJournalUser")
    expect(visibleEvents).toContain("agentPanelMessageJournalUserRecords(messageJournal)")
    expect(visibleEvents).toContain("[Current POPO Message]")
    expect(visibleEvents).toContain("agentPanelDisplayEventFromSessionTimeline")
    expect(visibleEvents).toContain("sessionTimelineHasChat(sessionTimelineEvents)")
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
    expect(agentPanel).toContain("visibleAgentPanelEvents(")
    expect(agentPanel).toContain("props.sessionTimelineEvents ?? []")
    expect(agentPanel).toContain('statusField("busy_count")')
    expect(agentPanel).toContain("latestAgentTaskStatusEvent(props.events)")
    expect(agentPanel).toContain('statusField("task_status")')
    expect(agentPanel).toContain('statusField("current_message_id")')
    expect(agentPanel).toContain('statusField("last_error")')
    expect(agentPanel).toContain('props.runId ? "idle" : "未运行"')
    expect(agentPanel).not.toContain('props.runtimeStatus ?? "running"')
    expect(agentPanel).toContain("stabilizeAgentPanelDisplayEvents(")
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

  test("keeps agent replies interleaved with tool calls for the same runtime message", async () => {
    const visibleAgentPanelEvents = await loadAgentPanelProjection()
    const projected = visibleAgentPanelEvents([
      {
        kind: "part.delta",
        seq: 1,
        created_at: 1,
        message_id: "msg-1",
        part_id: "reply-a",
        part_type: "text",
        delta: "before tool",
        status: "completed",
      },
      {
        kind: "tool.completed",
        seq: 2,
        created_at: 2,
        message_id: "msg-1",
        part_id: "tool-1",
        part_type: "tool",
        tool_name: "blueprint_current_status",
        tool_kind: "command_execution",
        tool_input: { command: "status" },
        status: "completed",
      },
      {
        kind: "part.delta",
        seq: 3,
        created_at: 3,
        message_id: "msg-1",
        part_id: "reply-b",
        part_type: "text",
        delta: "after tool",
        status: "completed",
      },
      {
        kind: "message.completed",
        seq: 4,
        created_at: 4,
        message_id: "msg-1",
        status: "completed",
      },
    ])

    expect(projected.map((event) => event.tone)).toEqual(["reply", "tool", "reply"])
    expect(projected[0]?.text).toBe("before tool")
    expect(String(projected[1]?.text)).toContain('"command": "status"')
    expect(projected[2]?.text).toBe("after tool")
    expect(projected[0]?.id).toBe("reply-a")
    expect(projected[2]?.id).toBe("reply-b")
    const toolItems = projected[1]?.toolItems as Array<Record<string, unknown>>
    expect(toolItems).toHaveLength(1)
    expect(toolItems[0]?.id).toBe("tool-1")
  })

  test("uses blueprint session transcript as the agent panel chat timeline", async () => {
    const visibleAgentPanelEvents = await loadAgentPanelProjection()
    const projected = visibleAgentPanelEvents(
      [
        {
          kind: "message.completed",
          seq: 3,
          created_at: "2026-06-09T13:29:26.000Z",
          message_id: "msg-1",
          text: "agent reply",
          status: "completed",
        },
        {
          kind: "tool.completed",
          seq: 4,
          created_at: "2026-06-09T13:29:27.000Z",
          message_id: "msg-1",
          part_id: "tool-1",
          tool_name: "blueprint_reply_popo_user",
          tool_kind: "mcp_tool_call",
          status: "completed",
        },
      ],
      [
        {
          id: "local-user",
          nodeId: "planner",
          mode: "top",
          text: "user message",
          status: "sent",
          created_at: "2026-06-09T13:29:00.000Z",
        },
      ],
      [
        {
          id: "session-1",
          seq: 1,
          type: "user_message",
          timestamp: "2026-06-09T13:29:01.000Z",
          source: "ui",
          message: "user message",
        },
        {
          id: "session-2",
          seq: 2,
          type: "agent_reply",
          timestamp: "2026-06-09T13:29:26.000Z",
          content: "agent reply",
        },
      ],
    )

    expect(projected.map((event) => event.tone)).toEqual(["user", "reply", "tool"])
    expect(projected[0]?.kind).toBe("\u672c\u673a\u7528\u6237")
    expect(projected[0]?.text).toBe("user message")
    expect(projected[1]?.text).toBe("agent reply")
    expect(projected.filter((event) => event.tone === "reply")).toHaveLength(1)
  })

  test("shows all current session users in the agent panel timeline", async () => {
    const visibleAgentPanelEvents = await loadAgentPanelProjection()
    const projected = visibleAgentPanelEvents(
      [],
      [
        {
          id: "pending-local",
          nodeId: "planner",
          mode: "default",
          text: "local panel message",
          status: "sent",
          created_at: "2026-06-09T13:29:04.000Z",
        },
      ],
      [
        {
          id: "popo-user",
          seq: 1,
          type: "user_message",
          timestamp: "2026-06-09T13:29:01.000Z",
          source: "popo",
          message: "POPO message",
        },
        {
          id: "ui-user",
          seq: 2,
          type: "user_message",
          timestamp: "2026-06-09T13:29:02.000Z",
          source: "ui",
          message: "local session message",
        },
        {
          id: "session-agent",
          seq: 3,
          type: "agent_reply",
          timestamp: "2026-06-09T13:29:03.000Z",
          content: "agent answer",
        },
      ],
    )

    expect(projected.map((event) => event.kind)).toEqual([
      "POPO \u7528\u6237",
      "\u672c\u673a\u7528\u6237",
      "Agent 回复",
      "\u672c\u673a\u7528\u6237",
    ])
    expect(projected.map((event) => event.text)).toEqual([
      "POPO message",
      "local session message",
      "agent answer",
      "local panel message",
    ])
  })

  test("falls back to queued session messages when old transcripts lack user_message rows", async () => {
    const visibleAgentPanelEvents = await loadAgentPanelProjection()
    const projected = visibleAgentPanelEvents(
      [],
      [],
      [
        {
          id: "queued-popo",
          seq: 1,
          type: "queued_message",
          timestamp: "2026-06-09T13:29:01.000Z",
          source: "popo",
          message: "old POPO message",
        },
        {
          id: "session-agent",
          seq: 2,
          type: "agent_reply",
          timestamp: "2026-06-09T13:29:02.000Z",
          content: "agent answer",
        },
      ],
    )

    expect(projected.map((event) => event.kind)).toEqual(["POPO \u7528\u6237", "Agent 回复"])
    expect(projected[0]?.text).toBe("old POPO message")
  })

  test("falls back to framework message journal user prompts when session timeline is unavailable", async () => {
    const visibleAgentPanelEvents = await loadAgentPanelProjection()
    const projected = visibleAgentPanelEvents(
      [
        {
          kind: "message.completed",
          seq: 3,
          created_at: "2026-06-09T13:29:26.000Z",
          message_id: "msg-1",
          text: "agent reply",
          status: "completed",
        },
      ],
      [],
      [],
      [
        {
          id: "journal-queued-1",
          recordType: "framework.message.queued",
          time: "2026-06-09T13:29:01.000Z",
          status: "queued",
          messageId: "msg-1",
          summary:
            "[Recent BlueprintSession Messages]\nUser: older message\n\n[Current POPO Message]\n[popo_user] current POPO message",
        },
        {
          id: "journal-sent-1",
          recordType: "framework.message.sent",
          time: "2026-06-09T13:29:02.000Z",
          status: "dispatching",
          messageId: "msg-1",
          summary:
            "# Blueprint Prompt: prompt\n\nruntime prompt\n\n---\n\n[Recent BlueprintSession Messages]\nUser: older message\n\n[Current POPO Message]\n[popo_user] current POPO message",
        },
      ],
    )

    expect(projected.map((event) => event.tone)).toEqual(["user", "reply"])
    expect(projected[0]?.kind).toBe("POPO \u7528\u6237")
    expect(projected[0]?.text).toBe("current POPO message")
    expect(String(projected[0]?.text)).not.toContain("Recent BlueprintSession")
    expect(projected[1]?.text).toBe("agent reply")
  })

  test("ignores textless stream events before maintenance filtering", async () => {
    const visibleAgentPanelEvents = await loadAgentPanelProjection()

    expect(() =>
      visibleAgentPanelEvents([
        {
          kind: "status",
          seq: 1,
          created_at: "2026-06-10T01:00:00.000Z",
          message_id: "msg-1",
        },
      ]),
    ).not.toThrow()

    expect(
      visibleAgentPanelEvents([
        {
          kind: "status",
          seq: 1,
          created_at: "2026-06-10T01:00:00.000Z",
          message_id: "msg-1",
        },
      ]),
    ).toEqual([])
  })

  test("hides framework summary and task status maintenance events", async () => {
    const visibleAgentPanelEvents = await loadAgentPanelProjection()
    const projected = visibleAgentPanelEvents([
      {
        kind: "message.completed",
        seq: 1,
        created_at: "2026-06-10T02:06:56.000Z",
        message_id: "summary-msg-planner-1",
        text: "Recording the current agent outcome for the framework and marking this task complete.",
        status: "completed",
      },
      {
        kind: "tool.completed",
        seq: 2,
        created_at: "2026-06-10T02:06:57.000Z",
        message_id: "summary-msg-planner-1",
        part_id: "tool-status-1",
        tool_name: "agent_task_status",
        tool_kind: "mcp_tool_call",
        status: "completed",
      },
      {
        kind: "agent.task_status",
        seq: 3,
        created_at: "2026-06-10T02:06:58.000Z",
        message_id: "summary-msg-planner-1",
        status: "completed",
      },
    ])

    expect(projected).toEqual([])
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
    expect(source).not.toContain("ready_for_top_agent_summary_generation")
    expect(source).not.toContain("autoTopAgentSummaryAttempts")
    expect(source).not.toContain("buildTopAgentSummaryMessage")
    expect(source).not.toContain("Summarize completed blueprint run")
    expect(source).not.toContain("silentBlocked: true")
    expect(source).toContain("blueprintFlowLockStore")
    expect(source).not.toContain("autoCompletedRuntimeKeys")
    expect(source).not.toContain("blueprintRuntimeManualUnlockKeys")
    expect(source).not.toContain("runtimeManualUnlockVersion()")
    expect(source).not.toContain("unlockRuntimeForManualControl(runId)")
    expect(source).toContain("BLUEPRINT_FLOW_LOCK_PENDING_GRACE_MS")
    expect(source).toContain("function planningProgressActive()")
    expect(source).toContain("active: true")
    expect(source).toContain("planningSeen: true")
    expect(source).not.toContain("runtimeSummaryKey")
    expect(source).not.toContain("AUTO_RUNTIME_COMPLETE_REASON")
    expect(source).not.toContain('reason: AUTO_RUNTIME_COMPLETE_REASON')
    expect(source).toContain("const runtimeRunActive = createMemo")
    expect(source).toContain("const runtimeStarted = createMemo")
    expect(source).not.toContain("blueprintSlotRunCount")
    expect(source).not.toContain("blueprintSlotCapacityFull")
    expect(source).toContain("const runId = currentBlueprintSession()?.activeRunId || \"\"")
    expect(source).not.toContain("const runId = currentBlueprintSession()?.activeRunId || runtime().runId")
    expect(source).not.toContain("const runtimeSummaryLockActive = createMemo")
    expect(source).toContain("const blueprintFlowLockActive = createMemo")
    expect(source).toContain("runtimeStatus(runtime().status)")
    expect(source).toContain("const blueprintProgressPhase = createMemo")
    expect(source).toContain("if (!blueprintFlowLockActive()) return undefined")
    expect(source).toContain("if (runtimeStarted()) return undefined")
    expect(source).toContain('if (runId && status === "running")')
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
    expect(nodeView).toContain("const base = runtimeNodeBoxShadow(props.runtimeVisualState)")
    expect(nodeView).toContain('"box-shadow": boxShadow()')
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
