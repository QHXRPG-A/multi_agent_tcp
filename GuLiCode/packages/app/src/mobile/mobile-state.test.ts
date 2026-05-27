import { describe, expect, test } from "bun:test"
import { mockProjects, mockRuns } from "./mock-data"
import {
  applyRunAction,
  createMobileState,
  createRun,
  getSelectedRun,
  selectProject,
  selectRun,
} from "./mobile-state"

const now = new Date("2026-05-27T12:00:00.000+08:00")

describe("mobile mock state", () => {
  test("creates a run and selects it", () => {
    const initial = createMobileState(mockProjects, mockRuns)
    const next = createRun(
      initial,
      {
        projectId: "proj-gulicode",
        title: "Mobile smoke",
        instruction: "Run a mobile-only smoke flow",
        blueprint: "runtime-control-plane",
      },
      now,
    )

    const selected = getSelectedRun(next)
    expect(selected?.title).toBe("Mobile smoke")
    expect(selected?.status).toBe("running")
    expect(selected?.events[0]?.title).toBe("Run created")
    expect(next.runs).toHaveLength(initial.runs.length + 1)
  })

  test("switches project and run selection together", () => {
    const initial = createMobileState(mockProjects, mockRuns)
    const next = selectProject(initial, "proj-sdk")

    expect(next.selectedProjectId).toBe("proj-sdk")
    expect(getSelectedRun(next)?.projectId).toBe("proj-sdk")

    const selected = selectRun(next, "run-docs-release")
    expect(selected.selectedProjectId).toBe("proj-docs")
    expect(selected.selectedRunId).toBe("run-docs-release")
  })

  test("confirms a run and exposes a summary report", () => {
    const initial = createMobileState(mockProjects, mockRuns)
    const withRun = createRun(
      initial,
      {
        projectId: "proj-gulicode",
        title: "Approval flow",
        instruction: "Create a run that needs approval",
        blueprint: "panel-review",
      },
      now,
    )
    const run = getSelectedRun(withRun)!

    const confirmed = applyRunAction(withRun, run.id, "confirm", now)
    const selected = getSelectedRun(confirmed)!

    expect(selected.status).toBe("completed")
    expect(selected.progress).toBe(100)
    expect(selected.reports.some((report) => report.kind === "summary" && report.ready)).toBe(true)
    expect(selected.events[0]?.title).toBe("Approved")
  })

  test("supports pause cancel and archive state transitions", () => {
    const initial = createMobileState(mockProjects, mockRuns)
    const paused = applyRunAction(initial, "run-runtime-smoke", "pause", now)
    expect(paused.runs.find((run) => run.id === "run-runtime-smoke")?.status).toBe("paused")

    const canceled = applyRunAction(paused, "run-runtime-smoke", "cancel", now)
    expect(canceled.runs.find((run) => run.id === "run-runtime-smoke")?.status).toBe("canceled")

    const archived = applyRunAction(canceled, "run-runtime-smoke", "archive", now)
    expect(archived.runs.find((run) => run.id === "run-runtime-smoke")?.status).toBe("archived")
  })
})
