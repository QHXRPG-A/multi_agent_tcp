import { describe, expect, test } from "bun:test"
import { mobileMockData } from "./mock-data"
import { mobileTabs, nodeStateLabel, nodeStateTone } from "./mobile-state"

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
  })

  test("describes a read-only blueprint overview and diff summary", () => {
    expect(mobileMockData.blueprint.nodes.map((node) => node.label)).toEqual([
      "Start",
      "Top Agent",
      "Planner",
      "Coder",
      "Review",
      "Summary",
    ])
    expect(mobileMockData.blueprint.run.currentNode).toBe("Coder")
    expect(mobileMockData.blueprint.diff.fileCount).toBe(5)
    expect(mobileMockData.blueprint.diff.additions).toBe(128)
    expect(mobileMockData.blueprint.diff.deletions).toBe(34)
    expect(mobileMockData.blueprint.nodes.every((node) => node.role && node.detail && node.note)).toBe(true)
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
  })
})
