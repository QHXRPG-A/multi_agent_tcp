import { Button } from "@opencode-ai/ui/button"
import { Icon } from "@opencode-ai/ui/icon"
import { createMemo, createSignal, For, onCleanup, onMount, Show } from "solid-js"
import { mockProjects, mockRuns } from "./mock-data"
import {
  applyRunAction,
  createMobileState,
  createRun,
  getProjectRuns,
  getSelectedProject,
  getSelectedRun,
  selectProject,
  selectRun,
  statusLabel,
  statusTone,
  type MobileRun,
  type MobileRunAction,
  type MobileRunEvent,
  type MobileToolCard,
} from "./mobile-state"
import { pwaEvents, type PwaUpdateDetail } from "@/pwa"

type View = "runs" | "create" | "reports"

const blueprintOptions = ["runtime-control-plane", "panel-review", "api-contract", "release-note"]

export function MobileApp() {
  const [state, setState] = createSignal(createMobileState(mockProjects, mockRuns))
  const [view, setView] = createSignal<View>("runs")
  const [title, setTitle] = createSignal("")
  const [instruction, setInstruction] = createSignal("")
  const [blueprint, setBlueprint] = createSignal(blueprintOptions[0])
  const [reportNotice, setReportNotice] = createSignal("")
  const [pwaUpdate, setPwaUpdate] = createSignal<PwaUpdateDetail | null>(null)
  const [offlineReady, setOfflineReady] = createSignal(false)

  const selectedProject = createMemo(() => getSelectedProject(state()))
  const selectedRun = createMemo(() => getSelectedRun(state()))
  const projectRuns = createMemo(() => getProjectRuns(state()))
  const readyReports = createMemo(() => selectedRun()?.reports.filter((report) => report.ready) ?? [])

  onMount(() => {
    const handleUpdate = (event: Event) => {
      setPwaUpdate((event as CustomEvent<PwaUpdateDetail>).detail)
    }
    const handleOfflineReady = () => {
      setOfflineReady(true)
    }

    window.addEventListener(pwaEvents.update, handleUpdate)
    window.addEventListener(pwaEvents.offlineReady, handleOfflineReady)
    onCleanup(() => {
      window.removeEventListener(pwaEvents.update, handleUpdate)
      window.removeEventListener(pwaEvents.offlineReady, handleOfflineReady)
    })
  })

  const chooseProject = (projectId: string) => {
    setState((current) => selectProject(current, projectId))
    setView("runs")
  }

  const chooseRun = (runId: string) => {
    setState((current) => selectRun(current, runId))
    setView("runs")
  }

  const runAction = (action: MobileRunAction) => {
    const run = selectedRun()
    if (!run) return
    setState((current) => applyRunAction(current, run.id, action))
  }

  const submitRun = (event: Event) => {
    event.preventDefault()
    const body = instruction().trim()
    if (!body) return
    const projectId = state().selectedProjectId
    setState((current) =>
      createRun(current, {
        projectId,
        title: title().trim() || body.slice(0, 56),
        instruction: body,
        blueprint: blueprint(),
      }),
    )
    setTitle("")
    setInstruction("")
    setBlueprint(blueprintOptions[0])
    setView("runs")
  }

  return (
    <div data-component="mobile-pwa" data-testid="mobile-app" class="w-full max-w-full overflow-hidden bg-background-base text-text-base">
      <div class="mx-auto flex size-full max-w-[460px] flex-col overflow-hidden border-x border-border-weak-base bg-background-base shadow-sm">
        <header class="shrink-0 border-b border-border-weak-base bg-surface-base/80 px-4 pb-3 backdrop-blur">
          <div class="flex min-h-11 items-center justify-between gap-3">
            <div class="min-w-0">
              <div class="text-12-medium uppercase text-text-muted">GuLiCode</div>
              <h1 class="truncate text-18-semibold text-text-strong">Mobile control</h1>
            </div>
            <div class="flex items-center gap-2 rounded-full border border-border-weak-base bg-background-base px-2.5 py-1 text-11-medium text-text-weak">
              <Icon name="server" size="small" />
              Mock
            </div>
          </div>
          <Show when={pwaUpdate()}>
            {(detail) => (
              <div class="mt-2 flex items-center justify-between gap-3 rounded-md border border-border-base bg-surface-info-weak px-3 py-2">
                <span class="text-12-regular text-text-base">A new app shell is ready.</span>
                <Button size="small" variant="primary" class="shrink-0 px-2" onClick={() => void detail().update()}>
                  Update
                </Button>
              </div>
            )}
          </Show>
          <Show when={offlineReady()}>
            <div class="mt-2 rounded-md border border-border-base bg-surface-base px-3 py-2 text-12-regular text-text-weak">
              App shell cached. Dynamic run data remains network-only.
            </div>
          </Show>
        </header>

        <main class="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          <ProjectPicker selected={state().selectedProjectId} onSelect={chooseProject} projects={state().projects} />
          <Show when={selectedProject()}>
            {(project) => (
              <section class="mt-3 rounded-md border border-border-weak-base bg-surface-base p-3">
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <h2 class="truncate text-15-semibold text-text-strong">{project().name}</h2>
                    <p class="mt-1 text-12-regular text-text-weak">{project().description}</p>
                  </div>
                  <div class="shrink-0 rounded-full bg-background-base px-2 py-1 text-11-medium text-text-muted">
                    {projectRuns().length} runs
                  </div>
                </div>
              </section>
            )}
          </Show>

          <Show when={view() === "runs"}>
            <Show when={selectedRun()} fallback={<EmptyRunState onCreate={() => setView("create")} />}>
              {(run) => (
                <>
                  <RunDetail run={run()} onAction={runAction} />
                  <RunList runs={projectRuns()} selectedRunId={run().id} onSelect={chooseRun} />
                </>
              )}
            </Show>
          </Show>

          <Show when={view() === "create"}>
            <CreateRunForm
              title={title()}
              instruction={instruction()}
              blueprint={blueprint()}
              onTitle={setTitle}
              onInstruction={setInstruction}
              onBlueprint={setBlueprint}
              onSubmit={submitRun}
            />
          </Show>

          <Show when={view() === "reports"}>
            <ReportsPanel
              run={selectedRun()}
              notice={reportNotice()}
              onOpen={(title) => setReportNotice(`Mock report opened: ${title}`)}
            />
          </Show>
        </main>

        <nav
          data-component="mobile-bottom-nav"
          class="grid shrink-0 grid-cols-3 gap-2 border-t border-border-weak-base bg-surface-base/95 px-4 py-3 backdrop-blur"
        >
          <NavButton active={view() === "runs"} icon="status" label="Runs" onClick={() => setView("runs")} />
          <NavButton active={view() === "create"} icon="plus" label="New" onClick={() => setView("create")} />
          <NavButton active={view() === "reports"} icon="archive" label={`Reports ${readyReports().length}`} onClick={() => setView("reports")} />
        </nav>
      </div>
    </div>
  )
}

function ProjectPicker(props: {
  projects: ReturnType<typeof createMobileState>["projects"]
  selected: string
  onSelect: (projectId: string) => void
}) {
  return (
    <div class="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1" aria-label="Projects">
      <For each={props.projects}>
        {(project) => (
          <button
            type="button"
            data-mobile-touch
            class="shrink-0 rounded-md border px-3 py-2 text-left transition-colors"
            classList={{
              "border-border-strong bg-surface-raised-base text-text-strong": props.selected === project.id,
              "border-border-weak-base bg-surface-base text-text-weak": props.selected !== project.id,
            }}
            onClick={() => props.onSelect(project.id)}
          >
            <div class="text-13-medium">{project.name}</div>
            <div class="mt-0.5 text-11-regular">{project.activeRunCount} active</div>
          </button>
        )}
      </For>
    </div>
  )
}

function RunDetail(props: { run: MobileRun; onAction: (action: MobileRunAction) => void }) {
  return (
    <section class="mt-3 overflow-hidden rounded-md border border-border-weak-base bg-surface-base" data-testid="run-detail">
      <div class="border-b border-border-weak-base p-3">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <span class={`rounded-full border px-2 py-1 text-11-medium ${statusTone(props.run.status)}`}>
                {statusLabel(props.run.status)}
              </span>
              <Show when={props.run.priority === "high"}>
                <span class="rounded-full border border-border-warning-base bg-surface-warning-weak px-2 py-1 text-11-medium text-icon-warning-base">
                  High
                </span>
              </Show>
            </div>
            <h2 class="mt-2 text-18-semibold text-text-strong">{props.run.title}</h2>
            <p class="mt-1 text-13-regular text-text-weak">{props.run.instruction}</p>
          </div>
        </div>
        <div class="mt-3 min-h-[104px] rounded-md border border-border-weak-base bg-background-base p-3">
          <div class="flex items-center justify-between text-12-medium text-text-weak">
            <span>Cursor {props.run.cursor}</span>
            <span>{props.run.progress}%</span>
          </div>
          <div class="mt-2 h-2 overflow-hidden rounded-full bg-surface-raised-base">
            <div class="h-full rounded-full bg-text-interactive-base" style={{ width: `${props.run.progress}%` }} />
          </div>
          <div class="mt-3 flex flex-wrap gap-1.5">
            <For each={props.run.agents}>
              {(agent) => <span class="rounded-full bg-surface-raised-base px-2 py-1 text-11-medium text-text-base">{agent}</span>}
            </For>
          </div>
        </div>
      </div>

      <div class="grid gap-3 p-3">
        <ToolCards tools={props.run.tools} />
        <EventStream events={props.run.events} />
      </div>

      <RunActions run={props.run} onAction={props.onAction} />
    </section>
  )
}

function ToolCards(props: { tools: MobileToolCard[] }) {
  return (
    <section>
      <div class="mb-2 flex items-center gap-2 text-12-medium text-text-muted">
        <Icon name="checklist" size="small" />
        Tool cards
      </div>
      <div class="grid gap-2">
        <For each={props.tools}>
          {(tool) => (
            <div class="rounded-md border border-border-weak-base bg-background-base p-3">
              <div class="flex items-center justify-between gap-2">
                <div class="truncate text-13-medium text-text-strong">{tool.title}</div>
                <span class="shrink-0 rounded-full bg-surface-raised-base px-2 py-1 text-11-medium text-text-weak">
                  {tool.state}
                </span>
              </div>
              <p class="mt-1 text-12-regular text-text-weak">{tool.description}</p>
            </div>
          )}
        </For>
      </div>
    </section>
  )
}

function EventStream(props: { events: MobileRunEvent[] }) {
  return (
    <section>
      <div class="mb-2 flex items-center gap-2 text-12-medium text-text-muted">
        <Icon name="prompt" size="small" />
        Event stream
      </div>
      <div class="grid gap-2">
        <For each={props.events}>
          {(event) => (
            <article class="rounded-md border border-border-weak-base bg-background-base p-3">
              <div class="flex items-center justify-between gap-2">
                <div class="min-w-0 truncate text-13-medium text-text-strong">{event.title}</div>
                <div class="shrink-0 text-11-regular text-text-muted">{event.time}</div>
              </div>
              <p class="mt-1 text-12-regular text-text-weak">{event.body}</p>
            </article>
          )}
        </For>
      </div>
    </section>
  )
}

function RunActions(props: { run: MobileRun; onAction: (action: MobileRunAction) => void }) {
  const terminal = () => props.run.status === "completed" || props.run.status === "canceled" || props.run.status === "archived"
  return (
    <div data-component="mobile-bottom-actions" class="grid grid-cols-2 gap-2 border-t border-border-weak-base bg-surface-base p-3">
      <Show when={!terminal()}>
        <Button data-testid="run-confirm" icon="check" class="min-h-11 justify-center" onClick={() => props.onAction("confirm")}>
          Confirm
        </Button>
        <Button icon="close" variant="ghost" class="min-h-11 justify-center" onClick={() => props.onAction("reject")}>
          Reject
        </Button>
        <Button icon="status" variant="ghost" class="min-h-11 justify-center" onClick={() => props.onAction("pause")}>
          Pause
        </Button>
        <Button icon="stop" variant="ghost" class="min-h-11 justify-center" onClick={() => props.onAction("cancel")}>
          Cancel
        </Button>
      </Show>
      <Show when={terminal() && props.run.status !== "archived"}>
        <Button icon="archive" class="col-span-2 min-h-11 justify-center" onClick={() => props.onAction("archive")}>
          Archive
        </Button>
      </Show>
      <Show when={props.run.status === "archived"}>
        <div class="col-span-2 rounded-md border border-border-weak-base bg-background-base px-3 py-2 text-center text-12-regular text-text-muted">
          Archived runs are read-only in the mobile mock.
        </div>
      </Show>
    </div>
  )
}

function RunList(props: { runs: MobileRun[]; selectedRunId: string; onSelect: (runId: string) => void }) {
  return (
    <section class="mt-4">
      <div class="mb-2 flex items-center justify-between">
        <h2 class="text-13-semibold text-text-strong">Recent runs</h2>
        <span class="text-11-regular text-text-muted">Latest first</span>
      </div>
      <div class="grid gap-2">
        <For each={props.runs}>
          {(run) => (
            <button
              type="button"
              data-mobile-touch
              class="rounded-md border p-3 text-left transition-colors"
              classList={{
                "border-border-strong bg-surface-raised-base": props.selectedRunId === run.id,
                "border-border-weak-base bg-surface-base": props.selectedRunId !== run.id,
              }}
              onClick={() => props.onSelect(run.id)}
            >
              <div class="flex items-center justify-between gap-2">
                <span class="truncate text-13-medium text-text-strong">{run.title}</span>
                <span class={`shrink-0 rounded-full border px-2 py-0.5 text-11-medium ${statusTone(run.status)}`}>
                  {statusLabel(run.status)}
                </span>
              </div>
              <div class="mt-1 text-12-regular text-text-weak">{run.blueprint}</div>
            </button>
          )}
        </For>
      </div>
    </section>
  )
}

function CreateRunForm(props: {
  title: string
  instruction: string
  blueprint: string
  onTitle: (value: string) => void
  onInstruction: (value: string) => void
  onBlueprint: (value: string) => void
  onSubmit: (event: Event) => void
}) {
  return (
    <form class="mt-3 grid gap-3 rounded-md border border-border-weak-base bg-surface-base p-3" onSubmit={props.onSubmit}>
      <div>
        <label class="mb-1 block text-12-medium text-text-weak" for="mobile-run-title">
          Title
        </label>
        <input
          id="mobile-run-title"
          data-mobile-touch
          value={props.title}
          onInput={(event) => props.onTitle(event.currentTarget.value)}
          class="w-full rounded-md border border-border-weak-base bg-background-base px-3 py-2 text-16-regular text-text-base outline-none focus:border-border-strong"
          placeholder="Optional short title"
        />
      </div>
      <div>
        <label class="mb-1 block text-12-medium text-text-weak" for="mobile-run-blueprint">
          Blueprint
        </label>
        <select
          id="mobile-run-blueprint"
          data-mobile-touch
          value={props.blueprint}
          onInput={(event) => props.onBlueprint(event.currentTarget.value)}
          class="w-full rounded-md border border-border-weak-base bg-background-base px-3 py-2 text-16-regular text-text-base outline-none focus:border-border-strong"
        >
          <For each={blueprintOptions}>{(option) => <option value={option}>{option}</option>}</For>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-12-medium text-text-weak" for="mobile-run-instruction">
          Top-agent instruction
        </label>
        <textarea
          id="mobile-run-instruction"
          data-component="mobile-textarea"
          value={props.instruction}
          onInput={(event) => props.onInstruction(event.currentTarget.value)}
          rows={6}
          class="w-full resize-none rounded-md border border-border-weak-base bg-background-base px-3 py-2 text-text-base outline-none focus:border-border-strong"
          placeholder="Tell the Top Agent what to dispatch, verify, or report."
        />
      </div>
      <Button type="submit" icon="plus" class="min-h-11 justify-center" disabled={!props.instruction.trim()}>
        Create mock run
      </Button>
    </form>
  )
}

function ReportsPanel(props: { run?: MobileRun; notice: string; onOpen: (title: string) => void }) {
  return (
    <section class="mt-3 rounded-md border border-border-weak-base bg-surface-base p-3" data-testid="reports-panel">
      <div class="flex items-center justify-between gap-2">
        <div>
          <h2 class="text-15-semibold text-text-strong">Reports</h2>
          <p class="mt-1 text-12-regular text-text-weak">{props.run?.title ?? "No run selected"}</p>
        </div>
        <Icon name="archive" />
      </div>
      <Show when={props.notice}>
        <div class="mt-3 rounded-md border border-border-base bg-background-base px-3 py-2 text-12-regular text-text-base">
          {props.notice}
        </div>
      </Show>
      <div class="mt-3 grid gap-2">
        <For
          each={props.run?.reports ?? []}
          fallback={<div class="rounded-md border border-border-weak-base bg-background-base p-3 text-12-regular text-text-muted">No report is ready yet.</div>}
        >
          {(report) => (
            <button
              type="button"
              data-testid="report-entry"
              data-mobile-touch
              class="rounded-md border border-border-weak-base bg-background-base p-3 text-left"
              disabled={!report.ready}
              onClick={() => props.onOpen(report.title)}
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-13-medium text-text-strong">{report.title}</span>
                <span class="rounded-full bg-surface-raised-base px-2 py-1 text-11-medium text-text-weak">{report.kind}</span>
              </div>
            </button>
          )}
        </For>
      </div>
    </section>
  )
}

function EmptyRunState(props: { onCreate: () => void }) {
  return (
    <section class="mt-3 rounded-md border border-border-weak-base bg-surface-base p-6 text-center">
      <Icon name="blueprint" class="mx-auto text-text-muted" />
      <h2 class="mt-3 text-15-semibold text-text-strong">No run for this project</h2>
      <p class="mt-1 text-12-regular text-text-weak">Create a mock mobile run to preview the workflow.</p>
      <Button icon="plus" class="mt-4 min-h-11 justify-center px-4" onClick={props.onCreate}>
        New run
      </Button>
    </section>
  )
}

function NavButton(props: { active: boolean; icon: Parameters<typeof Icon>[0]["name"]; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      data-mobile-touch
      class="flex min-w-0 flex-col items-center justify-center gap-1 rounded-md border px-2 py-2 text-11-medium transition-colors"
      classList={{
        "border-border-strong bg-background-base text-text-strong": props.active,
        "border-transparent text-text-weak": !props.active,
      }}
      onClick={props.onClick}
    >
      <Icon name={props.icon} size="small" />
      <span class="w-full truncate text-center">{props.label}</span>
    </button>
  )
}
