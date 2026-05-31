import { expect, test, type Page } from "@playwright/test"

async function useMobileMockApi(page: Page) {
  await page.route("**/api/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        csrfToken: "csrf-e2e",
        user: { id: "e2e-user", username: "e2e" },
        clients: { mobile: true, desktop: true },
        syncReady: true,
      }),
    })
  })
  await page.route("**/api/projects", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ ok: false, code: "E2E_MOCK_ONLY", message: "Use mobile mock data" }),
    })
  })
  await page.route("**/api/mobile/tick", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ ok: false, code: "E2E_MOCK_ONLY", message: "No live tick in mock e2e" }),
    })
  })
  await page.route("**/api/client-logs", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true }),
    })
  })
}

test.use({
  viewport: { width: 390, height: 844 },
  isMobile: true,
})

test("mobile mock renders three top tabs and read-only panels", async ({ page }) => {
  await useMobileMockApi(page)
  await page.goto("/mobile")

  await expect(page.getByTestId("mobile-app")).toBeVisible()
  await expect(page.getByText("移动协作台")).toBeVisible()
  await expect(page.getByRole("button", { name: "聊天", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "蓝图", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "待定", exact: true })).toBeVisible()
  const topAgentTabBackground = await page
    .getByRole("button", { name: "聊天", exact: true })
    .evaluate((element) => getComputedStyle(element).backgroundColor)
  expect(topAgentTabBackground).not.toBe("rgb(22, 19, 18)")
  expect(topAgentTabBackground).not.toBe("rgb(0, 0, 0)")

  await expect(page.getByTestId("top-agent-panel")).toContainText("顶层代理")
  await expect(page.getByTestId("top-agent-panel")).toContainText("移动端镜像同步")
  await expect(page.getByTestId("top-agent-panel")).toContainText("思考过程")
  await expect(page.getByTestId("top-agent-panel")).toContainText("blueprint.snapshot")
  await expect(page.getByTestId("mobile-desktop-message-mode")).toHaveValue("mode-blueprint")
  await expect(page.getByTestId("mobile-desktop-message")).toBeDisabled()
  await expect(page.getByTestId("mobile-desktop-message-submit")).toBeDisabled()

  await page.getByRole("button", { name: "蓝图", exact: true }).click()
  const blueprintTabBackground = await page
    .getByRole("button", { name: "蓝图", exact: true })
    .evaluate((element) => getComputedStyle(element).backgroundColor)
  expect(blueprintTabBackground).not.toBe("rgb(22, 19, 18)")
  const structurePreview = page.getByTestId("blueprint-structure-preview")
  await expect(structurePreview).toBeVisible()
  await expect(structurePreview).toContainText("蓝图结构")
  const previewMap = page.getByTestId("blueprint-structure-map")
  await expect(previewMap).toBeVisible()
  await expect(previewMap.getByTestId("blueprint-structure-node").filter({ hasText: "Start" })).toBeVisible()
  await expect(previewMap.getByTestId("blueprint-structure-node").filter({ hasText: "Top Agent" })).toBeVisible()
  await expect(previewMap.getByTestId("blueprint-structure-node").filter({ hasText: "Format Result" })).toBeVisible()
  await expect(previewMap.getByTestId("blueprint-structure-node").filter({ hasText: "Branch" })).toBeVisible()
  await expect(previewMap.getByTestId("blueprint-structure-node").filter({ hasText: "Tick" })).toBeVisible()
  await expect(structurePreview).toContainText("Top Agent")
  await expect(page.getByTestId("blueprint-node-detail")).toHaveCount(0)
  await previewMap.getByTestId("blueprint-structure-node").filter({ hasText: "Top Agent" }).click()
  await expect(page.getByTestId("agent-info-sheet")).toBeVisible()
  const agentSheetBackground = await page
    .getByTestId("agent-info-sheet")
    .evaluate((element) => getComputedStyle(element).backgroundColor)
  expect(agentSheetBackground).toBe("rgb(255, 253, 250)")
  await expect(page.getByTestId("agent-info-sheet")).toContainText("Top Agent")
  await expect(page.getByTestId("agent-info-sheet")).toHaveAttribute("data-node-kind", "worker_agent")
  await expect(page.getByTestId("agent-info-sheet")).toContainText("任务状态")
  await expect(page.getByTestId("agent-info-status-toggle")).toHaveAttribute("aria-expanded", "false")
  await expect(page.getByTestId("agent-info-status-details")).toHaveCount(0)
  const agentSheetHeight = await page.getByTestId("agent-info-sheet").evaluate((element) => element.getBoundingClientRect().height)
  const agentChatHeight = await page.getByTestId("agent-info-chat").evaluate((element) => element.getBoundingClientRect().height)
  const agentSheetScroll = page.getByTestId("agent-info-sheet-scroll")
  const agentScrollMetrics = await agentSheetScroll.evaluate((element) => ({
    clientHeight: element.clientHeight,
    overflowY: getComputedStyle(element).overflowY,
    scrollHeight: element.scrollHeight,
  }))
  expect(agentScrollMetrics.overflowY).toBe("auto")
  expect(agentScrollMetrics.scrollHeight).toBeGreaterThan(agentScrollMetrics.clientHeight)
  const agentSheetScrollTop = await agentSheetScroll.evaluate((element) => {
    element.scrollTop = element.scrollHeight
    return element.scrollTop
  })
  expect(agentSheetScrollTop).toBeGreaterThan(0)
  expect(agentChatHeight).toBeGreaterThan(agentSheetHeight * 0.38)
  await expect(page.getByTestId("agent-info-sheet")).toContainText("Agent 回复")
  await page.getByTestId("agent-info-status-toggle").click()
  await expect(page.getByTestId("agent-info-status-toggle")).toHaveAttribute("aria-expanded", "true")
  await expect(page.getByTestId("agent-info-status-details")).toContainText("agentId")
  await expect(page.getByTestId("agent-info-input")).toBeDisabled()
  await expect(page.getByTestId("agent-info-send")).toBeDisabled()
  await page.getByRole("button", { name: "关闭 Agent 信息面板" }).click()
  await expect(page.getByTestId("agent-info-sheet")).toHaveCount(0)
  await previewMap.getByTestId("blueprint-structure-node").filter({ hasText: "Format Result" }).click()
  await expect(page.getByTestId("agent-info-sheet")).toHaveAttribute("data-node-kind", "script")
  await expect(page.getByTestId("node-type-details")).toContainText("payload: dict")
  await expect(page.getByTestId("node-type-details")).toContainText("summary: str")
  await expect(page.getByTestId("agent-info-input")).toHaveCount(0)
  await page.getByRole("button", { name: "关闭 Agent 信息面板" }).click()
  await previewMap.getByTestId("blueprint-structure-node").filter({ hasText: "Branch" }).click()
  await expect(page.getByTestId("agent-info-sheet")).toHaveAttribute("data-node-kind", "branch")
  await expect(page.getByTestId("node-type-details")).toContainText("condition: bool")
  await expect(page.getByTestId("node-type-details")).toContainText("true: message")
  await page.getByRole("button", { name: "关闭 Agent 信息面板" }).click()
  const firstNodeText = await previewMap.getByTestId("blueprint-structure-node").first().innerText()
  expect(firstNodeText.trim().startsWith("1")).toBe(false)
  const firstNodeBackground = await previewMap
    .getByTestId("blueprint-structure-node")
    .first()
    .evaluate((element) => getComputedStyle(element).backgroundColor)
  expect(firstNodeBackground).not.toBe("rgba(0, 0, 0, 0)")

  const canvas = previewMap.getByTestId("blueprint-structure-canvas")
  const zoomStartTransform = await canvas.evaluate((element) => getComputedStyle(element).transform)
  await previewMap.getByTestId("blueprint-structure-zoom-in").click()
  await expect(previewMap.getByTestId("blueprint-structure-zoom-out")).toBeVisible()
  const zoomedTransform = await canvas.evaluate((element) => getComputedStyle(element).transform)
  expect(zoomedTransform).not.toBe(zoomStartTransform)

  const box = await previewMap.boundingBox()
  expect(box).not.toBeNull()
  const dragStartTransform = await canvas.evaluate((element) => getComputedStyle(element).transform)
  await page.mouse.move(box!.x + 180, box!.y + 128)
  await page.mouse.down()
  await page.mouse.move(box!.x + 120, box!.y + 98)
  await page.mouse.up()
  const draggedTransform = await canvas.evaluate((element) => getComputedStyle(element).transform)
  expect(draggedTransform).not.toBe(dragStartTransform)

  await page.getByRole("button", { name: "打开蓝图结构全屏查看" }).click()
  const overlay = page.getByTestId("blueprint-structure-overlay")
  await expect(overlay).toBeVisible()
  await expect(overlay.getByTestId("blueprint-structure-map-fullscreen")).toBeVisible()
  await expect(overlay.getByTestId("blueprint-structure-node").filter({ hasText: "Summary" })).toBeVisible()
  await expect(overlay.getByTestId("blueprint-structure-node").filter({ hasText: "Tick" })).toBeVisible()
  await expect(overlay.getByTestId("blueprint-structure-zoom-in")).toBeVisible()
  await expect(overlay).toContainText("Summary")
  await overlay.getByTestId("blueprint-structure-node").filter({ hasText: "Summary" }).click()
  await expect(page.getByTestId("agent-info-sheet")).toBeVisible()
  await expect(page.getByTestId("agent-info-sheet")).toContainText("Summary")
  const overlayZIndex = await overlay.evaluate((element) => Number(getComputedStyle(element).zIndex))
  const sheetZIndex = await page
    .getByTestId("agent-info-sheet-backdrop")
    .evaluate((element) => Number(getComputedStyle(element).zIndex))
  expect(sheetZIndex).toBeGreaterThan(overlayZIndex)
  await page.getByRole("button", { name: "关闭 Agent 信息面板" }).click()
  await page.getByRole("button", { name: "关闭蓝图结构全屏查看" }).click()
  await expect(page.getByTestId("blueprint-structure-overlay")).toHaveCount(0)
  await expect(page.getByTestId("blueprint-panel")).toContainText("结构总览")
  await expect(page.getByTestId("blueprint-panel").getByText("→", { exact: true })).toHaveCount(0)
  await expect(page.getByTestId("blueprint-node-detail")).toHaveCount(0)
  await page.getByTestId("blueprint-node-row").filter({ hasText: "Start" }).click()
  await expect(page.getByTestId("agent-info-sheet")).toContainText("Start")
  await expect(page.getByTestId("agent-info-sheet")).toContainText("入口")
  await expect(page.getByTestId("agent-info-sheet")).toContainText("纯前端 mock")
  await page.getByRole("button", { name: "关闭 Agent 信息面板" }).click()
  await expect(page.getByTestId("agent-info-sheet")).toHaveCount(0)
  await page.getByTestId("blueprint-node-row").filter({ hasText: "Planner" }).click()
  await expect(page.getByTestId("agent-info-sheet")).toContainText("Planner")
  await expect(page.getByTestId("agent-info-sheet")).toContainText("规划")
  await page.getByTestId("agent-info-sheet-backdrop").click({ position: { x: 8, y: 8 } })
  await expect(page.getByTestId("agent-info-sheet")).toHaveCount(0)
  await page.getByTestId("blueprint-node-row").filter({ hasText: "Tick" }).click()
  await expect(page.getByTestId("agent-info-sheet")).toHaveAttribute("data-node-kind", "tick")
  await expect(page.getByTestId("node-type-details")).toContainText("每 3 tick")
  await page.getByRole("button", { name: "关闭 Agent 信息面板" }).click()
  await expect(page.getByTestId("blueprint-node-detail")).toHaveCount(0)
  await expect(page.getByTestId("blueprint-panel")).toContainText("运行情况")
  await expect(page.getByTestId("blueprint-panel")).toContainText("Diff")
  await expect(page.getByTestId("blueprint-panel")).toContainText("5")
  await expect(page.getByTestId("blueprint-panel")).toContainText("+128")
  await expect(page.getByTestId("blueprint-panel")).toContainText("-34")
  await page.getByTestId("diff-metric-additions").click()
  await expect(page.getByTestId("diff-metric-detail")).toContainText("新增 128 行")
  const mobileAppDiff = page.getByTestId("blueprint-diff-file").filter({ hasText: "mobile-app.tsx" })
  await mobileAppDiff.click()
  await expect(mobileAppDiff.getByRole("button")).toHaveAttribute("aria-expanded", "true")
  await expect(mobileAppDiff.getByTestId("blueprint-diff-preview")).toContainText("active tab")

  await page.getByRole("button", { name: "待定", exact: true }).click()
  await expect(page.getByTestId("pending-panel")).toContainText("Pending")
  await expect(page.getByTestId("planning-request-card")).toHaveCount(2)
  await expect(page.getByTestId("pending-panel")).toContainText("补全移动端桌面镜像同步")
  await expect(page.getByTestId("pending-panel")).toContainText("同步桌面 Blueprint 全图节点")
  await expect(page.getByTestId("planning-answer-input")).toBeDisabled()
  await expect(page.getByTestId("planning-approve")).toBeDisabled()
  await expect(page.getByTestId("planning-reject")).toBeDisabled()

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  expect(overflow).toBe(false)
})
