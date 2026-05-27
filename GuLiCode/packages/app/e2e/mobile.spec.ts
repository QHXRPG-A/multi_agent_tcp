import { expect, test } from "@playwright/test"

test.use({
  viewport: { width: 390, height: 844 },
  isMobile: true,
})

test("mobile mock workflow renders and creates a run", async ({ page }) => {
  await page.goto("/mobile")

  await expect(page.getByTestId("mobile-app")).toBeVisible()
  await expect(page.getByText("Mobile control")).toBeVisible()
  await expect(page.getByTestId("run-detail")).toContainText("Blueprint runtime smoke")

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  expect(overflow).toBe(false)

  await page.getByRole("button", { name: /New/i }).click()
  await page.getByLabel("Title").fill("Phone dispatch")
  await page.getByLabel("Top-agent instruction").fill("Check the mobile mock run flow and report status.")
  await page.getByRole("button", { name: /Create mock run/i }).click()

  await expect(page.getByTestId("run-detail")).toContainText("Phone dispatch")
  await page.getByTestId("run-confirm").click()
  await expect(page.getByTestId("run-detail")).toContainText("Completed")

  await page.getByRole("button", { name: /Reports/i }).click()
  await expect(page.getByTestId("reports-panel")).toContainText("Mock final report")
})
