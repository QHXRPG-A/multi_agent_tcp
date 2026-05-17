import { describe, expect, test } from "bun:test"

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

    expect(source).toContain('platform.openBlueprint(projectDirectory, DEFAULT_BLUEPRINT_ID)')
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
    expect(source).toContain("await persistProjectDraft(draft)")
    expect(source).toContain("platform.startBlueprintRun(")
    expect(source).toContain("platform.blueprintRunStatus(runId)")
    expect(source).toContain("platform.blueprintRecentEvents?.(runId, 50)")
    expect(source).toContain('isTerminalRuntimeStatus(status)')
    expect(source).toContain('setInterval(() =>')
    expect(source).toContain('platform.endBlueprintRun(runId, action, `blueprint UI ${action}`)')
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
