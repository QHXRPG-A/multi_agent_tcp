import { describe, expect, test } from "bun:test"
import { mobileMockData } from "./mock-data"
import { mobileTabs, nodeKindLabel, nodeStateLabel, nodeStateTone } from "./mobile-state"

describe("mobile display mock state", () => {
  test("defines the three top-level mobile tabs", () => {
    expect(mobileTabs.map((tab) => tab.id)).toEqual(["chat", "blueprint", "pending"])
    expect(mobileTabs.map((tab) => tab.label)).toEqual(["聊天", "蓝图", "待定"])
  })

  test("keeps Top Agent messages read-only display data", () => {
    expect(mobileMockData.messages).toHaveLength(5)
    expect(mobileMockData.messages.some((message) => message.speaker === "user")).toBe(true)
    expect(mobileMockData.messages.some((message) => message.speaker === "top-agent")).toBe(true)
    expect(mobileMockData.messages[0]?.body).toContain("暂时不要从手机端改蓝图")
    const segmented = mobileMockData.messages.find((message) => message.segments?.length)
    expect(segmented?.segments?.map((segment) => segment.type)).toEqual(["text", "reasoning", "tool"])
    expect(mobileMockData.server?.desktopSessions?.sessions.map((session) => session.title)).toContain("移动端镜像同步")
    expect(mobileMockData.server?.desktopSessions?.composer?.activeModeId).toBe("mode-blueprint")
  })

  test("keeps planning requests visible but disabled without mobile write capability", () => {
    expect(mobileMockData.server?.csrfToken).toBeUndefined()
    expect(mobileMockData.server?.capabilities).toEqual([])
    expect(mobileMockData.server?.planningRequests).toHaveLength(2)
    expect(mobileMockData.server?.planningRequests[0]?.pendingQuestion?.questionId).toBe("scope")
    expect(mobileMockData.server?.planningRequests[1]?.pendingPlan).toBeTruthy()
  })

  test("describes a read-only blueprint overview and diff summary", () => {
    expect(mobileMockData.blueprint.nodes.map((node) => node.label)).toEqual([
      "Start",
      "Top Agent",
      "Planner",
      "Coder",
      "Format Result",
      "Branch",
      "Tick",
      "Review",
      "Summary",
    ])
    expect(mobileMockData.blueprint.run.currentNode).toBe("Coder")
    expect(mobileMockData.blueprint.diff.fileCount).toBe(5)
    expect(mobileMockData.blueprint.diff.additions).toBe(128)
    expect(mobileMockData.blueprint.diff.deletions).toBe(34)
    expect(mobileMockData.blueprint.nodes.every((node) => node.role && node.detail && node.note)).toBe(true)
    expect(mobileMockData.blueprint.nodes.map((node) => node.kind)).toEqual([
      "worker_agent",
      "worker_agent",
      "worker_agent",
      "agent",
      "script",
      "branch",
      "tick",
      "worker_agent",
      "worker_agent",
    ])
    expect(mobileMockData.blueprint.nodes.find((node) => node.kind === "script")?.inputPorts).toContain("payload: dict")
    expect(mobileMockData.blueprint.nodes.find((node) => node.kind === "branch")?.outputPorts).toContain("true: message")
    expect(mobileMockData.blueprint.nodes.find((node) => node.kind === "tick")?.everyNTicks).toBe(3)
    expect(
      mobileMockData.blueprint.nodes.every(
        (node) =>
          node.agentPanel.agentId &&
          node.agentPanel.cliKind &&
          node.agentPanel.taskStatus &&
          node.agentPanel.statusDetails.length > 0 &&
          node.agentPanel.events.length > 0,
      ),
    ).toBe(true)
    expect(mobileMockData.blueprint.nodes.find((node) => node.id === "coder")?.detail).toContain("点击反馈")
    expect(mobileMockData.blueprint.nodes.find((node) => node.id === "coder")?.agentPanel.taskStatus).toBe("running")
    expect(mobileMockData.blueprint.nodes.find((node) => node.id === "coder")?.agentPanel.messagesSent).toBeGreaterThan(0)
    expect(mobileMockData.blueprint.nodes.find((node) => node.id === "coder")?.agentPanel.inputPlaceholder).toContain(
      "live runtime",
    )
    expect(mobileMockData.blueprint.diff.files.every((file) => file.previewLines.length > 0)).toBe(true)
    expect(mobileMockData.blueprint.diff.files[0]?.previewLines.some((line) => line.type === "add")).toBe(true)
  })

  test("maps blueprint node states to display labels and tones", () => {
    expect(nodeStateLabel("done")).toBe("已完成")
    expect(nodeStateLabel("running")).toBe("运行中")
    expect(nodeStateLabel("queued")).toBe("排队中")
    expect(nodeStateTone("running")).toContain("rose")
    expect(nodeKindLabel("script")).toBe("Script")
    expect(nodeKindLabel("worker_agent")).toBe("Worker Agent")
  })
})
