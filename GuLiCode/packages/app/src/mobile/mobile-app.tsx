import { Icon } from "@opencode-ai/ui/icon"
import { Collapsible } from "@opencode-ai/ui/collapsible"
import { Markdown } from "@opencode-ai/ui/markdown"
import { createEffect, createMemo, createSignal, For, Index, onCleanup, onMount, Show, type JSX } from "solid-js"
import {
  applyMobileTickToData,
  createMobileTickGuard,
  answerMobilePlanningQuestion,
  approveMobileDiff,
  approveMobilePlanningPlan,
  cancelMobileRun,
  createMobilePlanningRequest,
  deleteMobileDesktopSession,
  isCollaborationUnauthorized,
  loadMobileCollaborationData,
  loadMobileTick,
  logoutMobileCollaboration,
  rejectMobilePlanningPlan,
  rollbackMobileDiff,
  sendMobileAgentMessage,
  sendMobileDesktopMessage,
  type MobileLoadResult,
} from "./mobile-api"
import { requireCollaborationAuth } from "@/components/collaboration-auth"
import { mobileMockData } from "./mock-data"
import {
  mobileTabs,
  nodeKindLabel,
  nodeStateLabel,
  nodeStateTone,
  type BlueprintAgentPanelEvent,
  type BlueprintEdge,
  type BlueprintDiffFile,
  type BlueprintDiffPreviewLine,
  type BlueprintNode,
  type MobilePlanningRequest,
  type MobileServerState,
  type MobileMockData,
  type MobileTab,
  type MobileDesktopComposerMode,
  type MobileDesktopMessageSegment,
  type TopAgentMessage,
} from "./mobile-state"
import { pwaEvents, type PwaUpdateDetail } from "@/pwa"

type MobileFontSize = "small" | "normal" | "large"

const MOBILE_FONT_SIZE_STORAGE_KEY = "gulicode.mobile.font-size"
const mobileFontSizeOptions: Array<{ id: MobileFontSize; label: string }> = [
  { id: "small", label: "小" },
  { id: "normal", label: "标准" },
  { id: "large", label: "大" },
]

const MOBILE_FONT_SIZE_CSS = `
[data-component="mobile-pwa"][data-mobile-font-size="small"] .text-11-regular,
[data-component="mobile-pwa"][data-mobile-font-size="small"] .text-11-medium,
[data-component="mobile-pwa"][data-mobile-font-size="small"] .text-11-semibold { font-size: 10px; line-height: 1.35; }
[data-component="mobile-pwa"][data-mobile-font-size="small"] .text-13-regular,
[data-component="mobile-pwa"][data-mobile-font-size="small"] .text-13-medium,
[data-component="mobile-pwa"][data-mobile-font-size="small"] .text-13-semibold { font-size: 12px; line-height: 1.45; }
[data-component="mobile-pwa"][data-mobile-font-size="small"] .text-18-semibold { font-size: 16px; line-height: 1.25; }
[data-component="mobile-pwa"][data-mobile-font-size="small"] .text-22-semibold { font-size: 19px; line-height: 1.25; }
[data-component="mobile-pwa"][data-mobile-font-size="large"] .text-11-regular,
[data-component="mobile-pwa"][data-mobile-font-size="large"] .text-11-medium,
[data-component="mobile-pwa"][data-mobile-font-size="large"] .text-11-semibold { font-size: 12px; line-height: 1.45; }
[data-component="mobile-pwa"][data-mobile-font-size="large"] .text-13-regular,
[data-component="mobile-pwa"][data-mobile-font-size="large"] .text-13-medium,
[data-component="mobile-pwa"][data-mobile-font-size="large"] .text-13-semibold { font-size: 14px; line-height: 1.55; }
[data-component="mobile-pwa"][data-mobile-font-size="large"] .text-18-semibold { font-size: 19px; line-height: 1.3; }
[data-component="mobile-pwa"][data-mobile-font-size="large"] .text-22-semibold { font-size: 23px; line-height: 1.25; }
`

function isMobileFontSize(value: unknown): value is MobileFontSize {
  return value === "small" || value === "normal" || value === "large"
}

function readMobileFontSize(): MobileFontSize {
  if (typeof localStorage === "undefined") return "normal"
  try {
    const value = localStorage.getItem(MOBILE_FONT_SIZE_STORAGE_KEY)
    return isMobileFontSize(value) ? value : "normal"
  } catch {
    return "normal"
  }
}

function writeMobileFontSize(value: MobileFontSize) {
  if (typeof localStorage === "undefined") return
  try {
    localStorage.setItem(MOBILE_FONT_SIZE_STORAGE_KEY, value)
  } catch {
    return
  }
}

function mobileFontSizeStyle(value: MobileFontSize): JSX.CSSProperties {
  const styles: Record<string, string> = {
    "--font-size-small": "13px",
    "--font-size-base": "14px",
    "--font-size-large": "16px",
    "--font-size-x-large": "20px",
    "--mobile-page-x": "20px",
    "--mobile-main-y": "20px",
    "--mobile-header-bottom": "16px",
    "--mobile-header-min": "48px",
    "--mobile-nav-top": "16px",
    "--mobile-gap": "8px",
    "--mobile-section-gap": "16px",
    "--mobile-card-p": "8px",
    "--mobile-form-p": "12px",
    "--mobile-session-x": "12px",
    "--mobile-session-y": "8px",
    "--mobile-bubble-x": "16px",
    "--mobile-bubble-y": "12px",
    "--mobile-field-x": "12px",
    "--mobile-field-y": "8px",
    "--mobile-message-field-min": "64px",
    "--mobile-goal-field-min": "80px",
    "--mobile-button-h": "36px",
    "--mobile-segment-x": "8px",
    "--mobile-segment-y": "3px",
    "--mobile-segment-height": "20px",
    "--mobile-segment-gap": "6px",
    "--mobile-segment-font": "12px",
    "--mobile-segment-status-font": "10px",
    "--mobile-segment-expanded-max": "112px",
    "--mobile-segment-expanded-x": "7px",
    "--mobile-segment-expanded-y": "5px",
  }
  if (value === "small") {
    Object.assign(styles, {
      "--font-size-small": "12px",
      "--font-size-base": "13px",
      "--font-size-large": "15px",
      "--font-size-x-large": "18px",
      "--mobile-page-x": "12px",
      "--mobile-main-y": "12px",
      "--mobile-header-bottom": "12px",
      "--mobile-header-min": "42px",
      "--mobile-nav-top": "12px",
      "--mobile-gap": "6px",
      "--mobile-section-gap": "12px",
      "--mobile-card-p": "6px",
      "--mobile-form-p": "10px",
      "--mobile-session-x": "10px",
      "--mobile-session-y": "6px",
      "--mobile-bubble-x": "12px",
      "--mobile-bubble-y": "9px",
      "--mobile-field-x": "10px",
      "--mobile-field-y": "6px",
      "--mobile-message-field-min": "56px",
      "--mobile-goal-field-min": "68px",
      "--mobile-button-h": "32px",
      "--mobile-segment-x": "6px",
      "--mobile-segment-y": "2px",
      "--mobile-segment-height": "18px",
      "--mobile-segment-gap": "4px",
      "--mobile-segment-font": "11px",
      "--mobile-segment-status-font": "9px",
      "--mobile-segment-expanded-max": "96px",
      "--mobile-segment-expanded-x": "6px",
      "--mobile-segment-expanded-y": "4px",
    })
  }
  if (value === "large") {
    Object.assign(styles, {
      "--font-size-small": "14px",
      "--font-size-base": "15px",
      "--font-size-large": "17px",
      "--font-size-x-large": "21px",
      "--mobile-page-x": "22px",
      "--mobile-main-y": "22px",
      "--mobile-header-bottom": "18px",
      "--mobile-header-min": "52px",
      "--mobile-nav-top": "18px",
      "--mobile-gap": "10px",
      "--mobile-section-gap": "18px",
      "--mobile-card-p": "10px",
      "--mobile-form-p": "14px",
      "--mobile-session-x": "14px",
      "--mobile-session-y": "9px",
      "--mobile-bubble-x": "18px",
      "--mobile-bubble-y": "14px",
      "--mobile-field-x": "14px",
      "--mobile-field-y": "9px",
      "--mobile-message-field-min": "72px",
      "--mobile-goal-field-min": "88px",
      "--mobile-button-h": "40px",
      "--mobile-segment-x": "9px",
      "--mobile-segment-y": "4px",
      "--mobile-segment-height": "22px",
      "--mobile-segment-gap": "7px",
      "--mobile-segment-font": "13px",
      "--mobile-segment-status-font": "11px",
      "--mobile-segment-expanded-max": "128px",
      "--mobile-segment-expanded-x": "8px",
      "--mobile-segment-expanded-y": "6px",
    })
  }
  return styles as JSX.CSSProperties
}

export function MobileApp() {
  const [tab, setTab] = createSignal<MobileTab>("chat")
  const [pwaUpdate, setPwaUpdate] = createSignal<PwaUpdateDetail | null>(null)
  const [offlineReady, setOfflineReady] = createSignal(false)
  const [mobileData, setMobileData] = createSignal<MobileMockData>(mobileMockData)
  const [serverState, setServerState] = createSignal<MobileLoadResult>({
    data: mobileMockData,
    source: "mock",
    status: "ready",
  })
  const [actionMessage, setActionMessage] = createSignal<string | null>(null)
  const [settingsOpen, setSettingsOpen] = createSignal(false)
  const [mobileFontSize, setMobileFontSize] = createSignal<MobileFontSize>(readMobileFontSize())
  const [logoutSubmitting, setLogoutSubmitting] = createSignal(false)
  let tickTimer: number | undefined

  const refreshMobileData = async () => {
    const result = await loadMobileCollaborationData()
    setMobileData(result.data)
    setServerState(result)
    if (result.status === "logged-out") requireCollaborationAuth()
    return result
  }

  const stopMobileTick = () => {
    if (!tickTimer) return
    window.clearInterval(tickTimer)
    tickTimer = undefined
  }

  const runMobileTick = createMobileTickGuard(async () => {
    try {
      const tick = await loadMobileTick()
      const nextData = applyMobileTickToData(mobileData(), tick)
      setMobileData(nextData)
      if (!tick.syncReady) {
        setServerState({
          data: nextData,
          source: "api",
          status: "waiting-peer",
          message: "Waiting for desktop login",
        })
        return
      }
      setServerState({
        data: nextData,
        source: "api",
        status: tick.status ? "ready" : "empty",
        message: tick.status ? undefined : "No blueprint run",
      })
    } catch (error) {
      if (isCollaborationUnauthorized(error)) {
        stopMobileTick()
        setServerState({
          data: mobileData(),
          source: "mock",
          status: "logged-out",
          message: "Login required",
        })
        requireCollaborationAuth()
        return
      }
      setServerState({
        data: mobileData(),
        source: "api",
        status: "error",
        message: error instanceof Error ? error.message : String(error),
      })
    }
  })

  const server = () => mobileData().server
  const canWrite = (capability: string) => Boolean(server()?.csrfToken && server()?.capabilities.includes(capability))
  const canSendDesktop = () => Boolean(server()?.csrfToken && server()?.desktopSessions?.online)
  const setMobileFontSizeValue = (value: MobileFontSize) => {
    setMobileFontSize(value)
    writeMobileFontSize(value)
  }

  const logout = async () => {
    if (logoutSubmitting()) return
    setLogoutSubmitting(true)
    try {
      await logoutMobileCollaboration()
    } finally {
      stopMobileTick()
      setSettingsOpen(false)
      setLogoutSubmitting(false)
      setMobileData(mobileMockData)
      setServerState({
        data: mobileMockData,
        source: "mock",
        status: "logged-out",
        message: "Login required",
      })
      requireCollaborationAuth()
    }
  }

  const runWriteAction = async (label: string, action: (server: MobileServerState | undefined) => Promise<unknown>) => {
    setActionMessage(`${label}中...`)
    try {
      await action(server())
      await refreshMobileData()
      setActionMessage(`${label}完成`)
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : String(error))
    }
  }

  onMount(() => {
    const handleUpdate = (event: Event) => {
      setPwaUpdate((event as CustomEvent<PwaUpdateDetail>).detail)
    }
    const handleOfflineReady = () => {
      setOfflineReady(true)
    }
    const handleDocumentClick = (event: MouseEvent) => {
      const target = event.target
      if (!(target instanceof Element) || !target.closest("[data-mobile-settings-menu]")) setSettingsOpen(false)
    }
    const handleKeydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSettingsOpen(false)
    }

    window.addEventListener(pwaEvents.update, handleUpdate)
    window.addEventListener(pwaEvents.offlineReady, handleOfflineReady)
    document.addEventListener("click", handleDocumentClick)
    document.addEventListener("keydown", handleKeydown)
    void refreshMobileData().then(() => runMobileTick())
    tickTimer = window.setInterval(() => {
      void runMobileTick()
    }, 1000)
    onCleanup(() => {
      stopMobileTick()
      window.removeEventListener(pwaEvents.update, handleUpdate)
      window.removeEventListener(pwaEvents.offlineReady, handleOfflineReady)
      document.removeEventListener("click", handleDocumentClick)
      document.removeEventListener("keydown", handleKeydown)
    })
  })

  return (
    <div
      data-component="mobile-pwa"
      data-testid="mobile-app"
      data-mobile-font-size={mobileFontSize()}
      class="h-full min-h-0 w-full max-w-full overflow-hidden bg-[#fbf7f4] text-[#161312]"
      style={mobileFontSizeStyle(mobileFontSize())}
    >
      <style>{MOBILE_FONT_SIZE_CSS}</style>
      <div class="mx-auto flex size-full max-w-[460px] flex-col overflow-hidden border-x border-[#eee4de] bg-[#fbf7f4]">
        <header class="shrink-0 border-b border-[#eee4de] bg-[#fffdfa]/95 px-[var(--mobile-page-x)] pb-[var(--mobile-header-bottom)] shadow-[0_10px_32px_rgba(48,38,32,0.06)] backdrop-blur">
          <div class="flex min-h-[var(--mobile-header-min)] items-center justify-between gap-[var(--mobile-gap)]">
            <div class="min-w-0">
              <div class="text-11-medium uppercase tracking-[0.16em] text-[#9a8f88]">GULICODE</div>
              <h1 class="mt-0.5 truncate text-18-semibold text-[#161312]">移动协作台</h1>
            </div>
            <div class="relative shrink-0" data-mobile-settings-menu>
              <button
                type="button"
                data-mobile-touch
                data-testid="mobile-settings-button"
                aria-haspopup="menu"
                aria-expanded={settingsOpen()}
                class="flex items-center gap-1.5 rounded-full border border-[#eaded7] bg-white px-3 py-1.5 text-12-medium text-[#6f6560] transition-colors hover:border-[#e7c8c1] hover:bg-[#fffaf8] hover:text-[#3c3430] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#b94f45]"
                onClick={(event) => {
                  event.stopPropagation()
                  setSettingsOpen((open) => !open)
                }}
              >
                <Icon name="settings-gear" size="small" />
                设置
              </button>

              <Show when={settingsOpen()}>
                <div
                  data-testid="mobile-settings-menu"
                  role="menu"
                  class="absolute right-0 top-[calc(100%+8px)] z-30 w-56 isolate overflow-hidden rounded-md border border-[#eaded7] bg-[#fffdfa] py-1 opacity-100 shadow-[0_18px_42px_rgba(48,38,32,0.14)] [background-color:#fffdfa]"
                >
                  <div class="border-b border-[#f0e7e1] bg-[#fffdfa] px-[var(--mobile-field-x)] py-[var(--mobile-field-y)] text-12-regular text-[#81756e]">
                    同步：{serverState().source === "api" ? "API" : "Mock"}
                  </div>
                  <div
                    data-testid="mobile-font-size-setting"
                    class="border-b border-[#f0e7e1] bg-[#fffdfa] px-[var(--mobile-field-x)] py-[var(--mobile-field-y)]"
                  >
                    <div class="mb-1.5 flex items-center justify-between gap-2 text-12-regular text-[#81756e]">
                      <span>字体大小</span>
                      <span class="text-11-regular text-[#a69b95]">
                        {mobileFontSizeOptions.find((item) => item.id === mobileFontSize())?.label}
                      </span>
                    </div>
                    <div class="grid grid-cols-3 gap-1" role="group" aria-label="字体大小">
                      <For each={mobileFontSizeOptions}>
                        {(item) => (
                          <button
                            type="button"
                            data-mobile-touch
                            data-testid={`mobile-font-size-${item.id}`}
                            aria-pressed={mobileFontSize() === item.id}
                            class="min-w-0 rounded-sm border px-2 py-1 text-11-medium transition-colors"
                            classList={{
                              "border-[#efc8c1] bg-[#fff7f5] text-[#161312]": mobileFontSize() === item.id,
                              "border-[#eaded7] bg-white text-[#6f6560] hover:border-[#e7c8c1] hover:bg-[#fffaf8]":
                                mobileFontSize() !== item.id,
                            }}
                            onClick={() => setMobileFontSizeValue(item.id)}
                          >
                            {item.label}
                          </button>
                        )}
                      </For>
                    </div>
                  </div>
                  <button
                    type="button"
                    role="menuitem"
                    data-mobile-touch
                    data-testid="mobile-logout-button"
                    disabled={logoutSubmitting()}
                    class="flex w-full items-center gap-2 bg-[#fffdfa] px-[var(--mobile-field-x)] py-[var(--mobile-field-y)] text-left text-13-medium text-[#6f3932] transition-colors hover:bg-[#fff7f5] disabled:opacity-60"
                    onClick={() => void logout()}
                  >
                    <Icon name="enter" size="small" />
                    {logoutSubmitting() ? "退出中" : "退出登录"}
                  </button>
                </div>
              </Show>
            </div>
          </div>

          <nav class="mt-[var(--mobile-nav-top)] grid grid-cols-3 gap-[var(--mobile-gap)]" aria-label="移动端视图">
            <For each={mobileTabs}>
              {(item) => (
                <button
                  type="button"
                  data-mobile-touch
                  aria-current={tab() === item.id ? "page" : undefined}
                  class="min-w-0 rounded-md border px-[var(--mobile-session-x)] py-[var(--mobile-session-y)] text-center text-13-medium transition-[background-color,border-color,color,box-shadow]"
                  classList={{
                    "border-[#efc8c1] bg-[#fff7f5] text-[#161312] shadow-[0_8px_18px_rgba(185,79,69,0.10)]":
                      tab() === item.id,
                    "border-[#eaded7] bg-white text-[#81756e] hover:border-[#e7c8c1] hover:bg-[#fffaf8] hover:text-[#3c3430]":
                      tab() !== item.id,
                  }}
                  onClick={() => setTab(item.id)}
                >
                  <span class="block truncate">{item.label}</span>
                </button>
              )}
            </For>
          </nav>

          <Show when={pwaUpdate()}>
            {(detail) => (
              <div class="mt-3 flex items-center justify-between gap-3 rounded-md border border-[#f0d4cf] bg-[#fff1ef] px-3 py-2">
                <span class="text-12-regular text-[#6f3932]">新的应用壳已可用。</span>
                <button
                  type="button"
                  class="rounded-md bg-[#161312] px-3 py-1.5 text-12-medium text-white"
                  onClick={() => void detail().update()}
                >
                  更新
                </button>
              </div>
            )}
          </Show>
          <Show when={offlineReady()}>
            <div class="mt-3 rounded-md border border-[#eaded7] bg-white px-3 py-2 text-12-regular text-[#81756e]">
              前端壳已缓存；动态运行数据仍保持联网获取。
            </div>
          </Show>
          <Show when={serverState().status !== "ready" && serverState().message}>
            <div class="mt-3 rounded-md border border-[#eaded7] bg-white px-3 py-2 text-12-regular text-[#81756e]">
              {serverState().message}
            </div>
          </Show>
        </header>

        <main class="flex min-h-0 flex-1 flex-col overflow-y-auto px-[var(--mobile-page-x)] py-[var(--mobile-main-y)]">
          <Show when={tab() === "chat"}>
            <TopAgentPanel
              data={mobileData()}
              canSend={canSendDesktop()}
              canClear={canSendDesktop()}
              actionMessage={actionMessage()}
              onSendDesktopMessage={(text, options) =>
                runWriteAction("发送消息", (server) => sendMobileDesktopMessage(server, text, options))
              }
              onClearDesktopSession={(sessionId) =>
                runWriteAction("清空对话", (server) => deleteMobileDesktopSession(server, sessionId))
              }
            />
          </Show>
          <Show when={tab() === "blueprint"}>
            <BlueprintPanel
              data={mobileData()}
              canCreate={canWrite("run:create")}
              canMessage={canWrite("run:message")}
              canEnd={canWrite("run:end")}
              canApprove={canWrite("run:approve")}
              actionMessage={actionMessage()}
              onCreatePlanningRequest={(goal) => runWriteAction("规划请求", (server) => createMobilePlanningRequest(server, goal))}
              onOpenPlanning={() => setTab("blueprint")}
              onCancelRun={() => runWriteAction("取消运行", (server) => cancelMobileRun(server))}
              onSendMessage={(nodeId, text, mode) =>
                runWriteAction("发送消息", (server) => sendMobileAgentMessage(server, nodeId, text, mode))
              }
              onApproveDiff={(changesetId) => runWriteAction("批准 Diff", (server) => approveMobileDiff(server, changesetId))}
              onRollbackDiff={(changesetId) => runWriteAction("回滚 Diff", (server) => rollbackMobileDiff(server, changesetId))}
            />
          </Show>
          <Show when={tab() === "pending"}>
            <WritablePendingPanel
              server={server()}
              canCreate={canWrite("run:create")}
              actionMessage={actionMessage()}
              onAnswer={(requestId, questionId, answers) =>
                runWriteAction("提交回答", (server) => answerMobilePlanningQuestion(server, requestId, questionId, answers))
              }
              onApprove={(requestId) =>
                runWriteAction("批准计划", (server) => approveMobilePlanningPlan(server, requestId))
              }
              onReject={(requestId, reason) =>
                runWriteAction("拒绝计划", (server) => rejectMobilePlanningPlan(server, requestId, reason))
              }
            />
          </Show>
        </main>
      </div>
    </div>
  )
}

type DesktopMessageSubmitOptions = {
  promptMode: "normal" | "blueprintPlanning"
  agentName?: string | null
}

function TopAgentPanel(props: {
  data: MobileMockData
  canSend: boolean
  canClear: boolean
  actionMessage?: string | null
  onSendDesktopMessage: (text: string, options: DesktopMessageSubmitOptions) => Promise<void>
  onClearDesktopSession: (sessionId?: string) => Promise<void>
}) {
  const [message, setMessage] = createSignal("")
  const [mode, setMode] = createSignal("")
  const [sending, setSending] = createSignal(false)
  const [clearing, setClearing] = createSignal(false)
  let topAgentChatScroller: HTMLDivElement | undefined
  let lastTopAgentScrollKey: string | undefined
  let lastActiveComposerModeId: string | undefined
  let topAgentChatPinnedToBottom = true
  const [openSegmentKeys, setOpenSegmentKeys] = createSignal<Record<string, true>>({})
  const [segmentDisclosureWidths, setSegmentDisclosureWidths] = createSignal<Record<string, number>>({})
  const desktopMirror = () => props.data.server?.desktopSessions
  const canSend = () => props.canSend && message().trim().length > 0 && Boolean(selectedComposerMode()) && !sending()
  const activeDesktopSessionId = () => desktopMirror()?.activeSessionId ?? undefined
  const canClear = () => props.canClear && Boolean(activeDesktopSessionId()) && !clearing()
  const composerModes = () => desktopMirror()?.composer?.modes ?? []
  const activeComposerModeId = () => desktopMirror()?.composer?.activeModeId ?? undefined
  const selectedComposerMode = (): MobileDesktopComposerMode | undefined => {
    const modes = composerModes()
    return modes.find((item) => item.id === mode()) ?? modes[0]
  }
  const selectedSubmitOptions = (): DesktopMessageSubmitOptions | undefined => {
    const selected = selectedComposerMode()
    if (!selected) return undefined
    if (selected.kind === "blueprintPlanning") return { promptMode: "blueprintPlanning" }
    return { promptMode: "normal", agentName: selected.id }
  }
  const submitMessage = async (event: SubmitEvent) => {
    event.preventDefault()
    if (!canSend()) return
    const options = selectedSubmitOptions()
    if (!options) return
    setSending(true)
    try {
      await props.onSendDesktopMessage(message().trim(), options)
      setMessage("")
    } finally {
      setSending(false)
    }
  }
  const clearDesktopSession = async () => {
    if (!canClear()) return
    setClearing(true)
    try {
      await props.onClearDesktopSession(activeDesktopSessionId())
    } finally {
      setClearing(false)
    }
  }
  const hasDesktopSessions = () => Boolean(desktopMirror()?.sessions?.length)
  const hasTopAgentMessages = () => props.data.messages.length > 0
  const desktopStatusText = () => {
    const mirror = desktopMirror()
    if (mirror?.online) return "桌面端在线，移动端消息会通过桌面端发送。"
    if (mirror?.loggedIn) return "桌面端已登录，等待桥接注册。"
    return "等待桌面端登录并完成桥接注册。"
  }
  const topAgentScrollKey = () => {
    const lastMessage = props.data.messages.at(-1)
    if (!lastMessage) return ""
    const segments = lastMessage.segments ?? []
    const lastSegment = segments.at(-1)
    return [
      props.data.messages.length,
      lastMessage.id,
      lastMessage.body.length,
      segments.length,
      lastSegment?.id ?? "",
      lastSegment?.body?.length ?? 0,
      lastSegment?.status ?? "",
    ].join(":")
  }
  const isTopAgentChatNearBottom = () => {
    if (!topAgentChatScroller) return true
    const distanceFromBottom =
      topAgentChatScroller.scrollHeight - topAgentChatScroller.scrollTop - topAgentChatScroller.clientHeight
    return distanceFromBottom <= 24
  }
  const updateTopAgentPinnedState = () => {
    topAgentChatPinnedToBottom = isTopAgentChatNearBottom()
  }
  const scrollTopAgentChatToBottom = () => {
    queueMicrotask(() => {
      window.requestAnimationFrame(() => {
        if (!topAgentChatScroller) return
        topAgentChatScroller.scrollTop = topAgentChatScroller.scrollHeight
        topAgentChatPinnedToBottom = true
      })
    })
  }
  const isSegmentDisclosureOpen = (key: string) => openSegmentKeys()[key] === true
  const segmentDisclosureWidth = (key: string) => segmentDisclosureWidths()[key]
  const setSegmentDisclosureWidth = (key: string, width: number) => {
    if (!Number.isFinite(width) || width <= 0) return
    const nextWidth = Math.round(width)
    setSegmentDisclosureWidths((current) => {
      if (current[key] === nextWidth) return current
      return { ...current, [key]: nextWidth }
    })
  }
  const setSegmentDisclosureOpen = (key: string, open: boolean) => {
    topAgentChatPinnedToBottom = false
    setOpenSegmentKeys((current) => {
      if (open) {
        if (current[key]) return current
        return { ...current, [key]: true }
      }
      if (!current[key]) return current
      const next = { ...current }
      delete next[key]
      return next
    })
  }

  createEffect(() => {
    const modes = composerModes()
    const activeModeId = activeComposerModeId()
    if (!modes.length) {
      if (mode()) setMode("")
      lastActiveComposerModeId = undefined
      return
    }
    const currentMode = mode()
    const currentModeIsValid = modes.some((item) => item.id === currentMode)
    const nextMode = activeModeId && modes.some((item) => item.id === activeModeId) ? activeModeId : (modes[0]?.id ?? "")
    const shouldFollowDesktopMode = !currentMode || !currentModeIsValid || currentMode === lastActiveComposerModeId
    if (shouldFollowDesktopMode && currentMode !== nextMode) setMode(nextMode)
    lastActiveComposerModeId = activeModeId
  })

  createEffect(() => {
    const scrollKey = topAgentScrollKey()
    if (!scrollKey) {
      lastTopAgentScrollKey = undefined
      topAgentChatPinnedToBottom = true
      return
    }
    if (scrollKey === lastTopAgentScrollKey) return
    const shouldAutoScroll = lastTopAgentScrollKey === undefined || topAgentChatPinnedToBottom
    lastTopAgentScrollKey = scrollKey
    if (shouldAutoScroll) scrollTopAgentChatToBottom()
  })

  return (
    <section data-testid="top-agent-panel" class="flex min-h-0 w-full min-w-0 flex-1 flex-col gap-[var(--mobile-section-gap)]">
      <div class="shrink-0">
        <p class="text-12-medium uppercase tracking-[0.14em] text-[#b5837d]">顶层代理</p>
        <h2 class="mt-1 text-22-semibold text-[#161312]">聊天</h2>
        <p class="mt-[var(--mobile-gap)] text-13-regular leading-5 text-[#81756e]">
          {desktopStatusText()}
        </p>
      </div>

      <div
        data-testid="mobile-top-agent-chat"
        class="flex min-h-0 w-full min-w-0 flex-1 flex-col rounded-md border border-[#eaded7] bg-[#fffdfa] p-[var(--mobile-card-p)] shadow-[0_12px_30px_rgba(48,38,32,0.05)]"
      >
        <div class="flex min-w-0 shrink-0 items-start justify-between gap-[var(--mobile-gap)] pb-[var(--mobile-card-p)]">
          <div class="flex min-w-0 flex-1 gap-[var(--mobile-gap)] overflow-x-auto">
            <For each={desktopMirror()?.sessions ?? []}>
              {(session) => (
                <div
                  class="shrink-0 rounded-md border px-[var(--mobile-session-x)] py-[var(--mobile-session-y)] text-left"
                  classList={{
                    "border-[#efc8c1] bg-[#fff7f5] text-[#161312]": session.id === desktopMirror()?.activeSessionId,
                    "border-[#eaded7] bg-white text-[#6f6560]": session.id !== desktopMirror()?.activeSessionId,
                  }}
                >
                  <div class="max-w-40 truncate text-12-semibold">{session.title || session.id}</div>
                  <div class="mt-0.5 text-11-regular text-[#9a8f88]">{session.messageCount ?? 0} 条消息</div>
                </div>
              )}
            </For>
          </div>
          <button
            type="button"
            data-mobile-touch
            data-testid="mobile-desktop-session-clear"
            disabled={!canClear()}
            class="inline-flex h-8 shrink-0 items-center gap-1 rounded-md border border-[#f0d4cf] bg-[#fff7f5] px-2 text-11-medium text-[#9f6159] transition-colors hover:border-[#e7b8b0] hover:bg-[#fff1ee] disabled:cursor-not-allowed disabled:opacity-50"
            onClick={() => void clearDesktopSession()}
          >
            <Icon name="trash" size="small" />
            清空
          </button>
        </div>
        <div
          ref={topAgentChatScroller}
          data-testid="mobile-top-agent-chat-scroll"
          class="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1 [scrollbar-color:#d8c7bf_transparent] [scrollbar-width:thin]"
          onScroll={updateTopAgentPinnedState}
          classList={{
            "mt-[var(--mobile-card-p)] border-t border-[#f0e7e1] pt-[var(--mobile-card-p)]": hasDesktopSessions() && hasTopAgentMessages(),
          }}
        >
          <Show
            when={hasTopAgentMessages()}
            fallback={<div class="flex min-h-32 items-center justify-center px-2 py-5 text-center text-12-regular text-[#9a8f88]">暂无桌面消息。</div>}
          >
            <div class="grid gap-[var(--mobile-gap)]">
              <Index each={props.data.messages}>
                {(message) => (
                  <MessageBubble
                    message={message()}
                    isSegmentOpen={isSegmentDisclosureOpen}
                    onSegmentOpenChange={setSegmentDisclosureOpen}
                    segmentWidth={segmentDisclosureWidth}
                    onSegmentWidthChange={setSegmentDisclosureWidth}
                  />
                )}
              </Index>
            </div>
          </Show>
        </div>

        <form
          data-testid="mobile-desktop-message-form"
          class="mt-[var(--mobile-card-p)] grid shrink-0 gap-[var(--mobile-gap)] border-t border-[#f0e7e1] pt-[var(--mobile-card-p)]"
          onSubmit={submitMessage}
        >
          <label class="text-12-medium text-[#6f6560]" for="mobile-desktop-message">
            发送消息
          </label>
          <textarea
            id="mobile-desktop-message"
            data-testid="mobile-desktop-message"
            class="min-h-[var(--mobile-message-field-min)] resize-none rounded-md border border-[#eaded7] bg-[#fbf7f4] px-[var(--mobile-field-x)] py-[var(--mobile-field-y)] text-13-regular text-[#3c3430] outline-none placeholder:text-[#a69b95]"
            placeholder="发送到桌面当前会话"
            disabled={!props.canSend}
            value={message()}
            onInput={(event) => setMessage(event.currentTarget.value)}
          />
          <div class="flex items-center justify-between gap-[var(--mobile-gap)]">
            <div class="flex min-w-0 items-center gap-[var(--mobile-gap)]">
              <label class="sr-only" for="mobile-desktop-message-mode">
                发送模式
              </label>
              <select
                id="mobile-desktop-message-mode"
                data-testid="mobile-desktop-message-mode"
                class="h-[var(--mobile-button-h)] min-w-24 rounded-md border border-[#eaded7] bg-white px-2 text-11-medium text-[#6f6560] outline-none disabled:cursor-not-allowed disabled:opacity-60"
                disabled={!props.canSend || sending() || composerModes().length === 0}
                value={mode()}
                onChange={(event) => setMode(event.currentTarget.value)}
              >
                <Show when={composerModes().length > 0} fallback={<option value="">等待桌面模式</option>}>
                  <For each={composerModes()}>
                    {(item) => <option value={item.id}>{item.label}</option>}
                  </For>
                </Show>
              </select>
              <span class="min-w-0 truncate text-11-regular text-[#9a8f88]">{props.actionMessage ?? "就绪"}</span>
            </div>
            <button
              type="submit"
              data-mobile-touch
              data-testid="mobile-desktop-message-submit"
              disabled={!canSend()}
              class="inline-flex h-[var(--mobile-button-h)] items-center gap-1.5 rounded-md border px-[var(--mobile-session-x)] text-12-medium disabled:cursor-not-allowed"
              style={{
                "background-color": canSend() ? "#161312" : "#fbf7f4",
                "border-color": canSend() ? "#161312" : "#eaded7",
                color: canSend() ? "#ffffff" : "#6f6560",
              }}
            >
              <Icon name="arrow-right" size="small" />
              发送
            </button>
          </div>
        </form>
      </div>
    </section>
  )
}

function MobilePlanningForm(props: {
  canCreate: boolean
  actionMessage?: string | null
  onCreatePlanningRequest: (goal: string) => Promise<void>
}) {
  const [goal, setGoal] = createSignal("")
  const [submitting, setSubmitting] = createSignal(false)
  const canSubmit = () => props.canCreate && goal().trim().length > 0 && !submitting()
  const submitGoal = async (event: SubmitEvent) => {
    event.preventDefault()
    if (!canSubmit()) return
    setSubmitting(true)
    try {
      await props.onCreatePlanningRequest(goal().trim())
      setGoal("")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Show
      when={props.canCreate}
      fallback={
        <div
          data-testid="readonly-notice"
          class="rounded-md border border-dashed border-[#e9ccc7] bg-[#fff9f7] px-[var(--mobile-bubble-x)] py-[var(--mobile-bubble-y)] text-13-medium text-[#9f6159]"
        >
          当前账号暂无创建规划权限
        </div>
      }
    >
      <form
        data-testid="mobile-planning-form"
        class="grid gap-[var(--mobile-gap)] rounded-md border border-[#eaded7] bg-white p-[var(--mobile-form-p)] shadow-[0_12px_30px_rgba(48,38,32,0.05)]"
        onSubmit={submitGoal}
      >
        <label class="text-12-medium text-[#6f6560]" for="mobile-planning-goal">
          蓝图目标
        </label>
        <textarea
          id="mobile-planning-goal"
          data-testid="mobile-planning-goal"
          class="min-h-[var(--mobile-goal-field-min)] resize-none rounded-md border border-[#eaded7] bg-[#fbf7f4] px-[var(--mobile-field-x)] py-[var(--mobile-field-y)] text-13-regular text-[#3c3430] outline-none placeholder:text-[#a69b95]"
          placeholder="描述需要顶层代理规划的蓝图任务"
          value={goal()}
          onInput={(event) => setGoal(event.currentTarget.value)}
        />
        <div class="flex items-center justify-between gap-[var(--mobile-gap)]">
          <span class="min-w-0 truncate text-11-regular text-[#9a8f88]">{props.actionMessage ?? "就绪"}</span>
          <button
            type="submit"
            data-mobile-touch
            data-testid="mobile-planning-submit"
            disabled={!canSubmit()}
            class="inline-flex h-[var(--mobile-button-h)] items-center gap-1.5 rounded-md border px-[var(--mobile-session-x)] text-12-medium disabled:cursor-not-allowed"
            style={{
              "background-color": canSubmit() ? "#161312" : "#fbf7f4",
              "border-color": canSubmit() ? "#161312" : "#eaded7",
              color: canSubmit() ? "#ffffff" : "#6f6560",
            }}
          >
            <Icon name="arrow-right" size="small" />
            开始规划
          </button>
        </div>
      </form>
    </Show>
  )
}

function segmentDisclosureKey(messageId: string, segment: MobileDesktopMessageSegment) {
  return `${messageId}:${segment.type}:${segment.id}`
}

function MessageBubble(props: {
  message: TopAgentMessage
  isSegmentOpen: (key: string) => boolean
  onSegmentOpenChange: (key: string, open: boolean) => void
  segmentWidth: (key: string) => number | undefined
  onSegmentWidthChange: (key: string, width: number) => void
}) {
  const user = () => props.message.speaker === "user"
  const segments = () => (props.message.segments ?? []).filter((segment) => segment.body?.trim() || segment.type !== "text")
  return (
    <article
      class="max-w-[88%] rounded-md border px-[var(--mobile-bubble-x)] py-[var(--mobile-bubble-y)] shadow-[0_10px_26px_rgba(48,38,32,0.05)]"
      classList={{
        "ml-auto border-[#f1d0ca] bg-[#fff1ee]": user(),
        "mr-auto border-[#eaded7] bg-white": !user(),
      }}
    >
      <div class="mb-1 flex items-center justify-between gap-3">
        <span class="text-12-semibold text-[#161312]">{props.message.label}</span>
        <span class="text-11-regular text-[#a69b95]">{props.message.time}</span>
      </div>
      <Show
        when={segments().length > 0}
        fallback={<MessageMarkdown text={props.message.body} cacheKey={props.message.id} />}
      >
        <div class="grid gap-[var(--mobile-segment-gap)]">
          <Index each={segments()}>
            {(segment) => (
              <Show
                when={segment().type !== "text"}
                fallback={<MessageMarkdown text={segment().body ?? ""} cacheKey={`${props.message.id}:${segment().id}`} />}
              >
                <MessageSegmentDisclosure
                  segment={segment()}
                  collapsedWidth={props.segmentWidth(segmentDisclosureKey(props.message.id, segment()))}
                  open={props.isSegmentOpen(segmentDisclosureKey(props.message.id, segment()))}
                  onWidthChange={(width) => props.onSegmentWidthChange(segmentDisclosureKey(props.message.id, segment()), width)}
                  onOpenChange={(open) => props.onSegmentOpenChange(segmentDisclosureKey(props.message.id, segment()), open)}
                />
              </Show>
            )}
          </Index>
        </div>
      </Show>
    </article>
  )
}

function MessageMarkdown(props: { text: string; cacheKey?: string; compact?: boolean }) {
  const markdownClass = () =>
    [
      "select-text break-words text-[#3c3430]",
      props.compact ? "text-12-regular leading-5" : "text-14-regular leading-6",
      "[&_p]:mb-2 [&_p:last-child]:mb-0",
      "[&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5",
      "[&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5",
      "[&_li]:mb-1",
      "[&_blockquote]:my-2 [&_blockquote]:border-l-2 [&_blockquote]:border-[#e3d5cd] [&_blockquote]:pl-3 [&_blockquote]:text-[#6f6560]",
      "[&_code]:rounded-sm [&_code]:bg-[#f4ece7] [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.92em]",
      "[&_pre]:my-2 [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:bg-[#2b2521] [&_pre]:p-2 [&_pre]:text-11-regular [&_pre]:leading-5 [&_pre]:text-[#fffdfa]",
      "[&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_a]:text-[#9f4d45] [&_a]:underline",
      "[&_h1]:mb-2 [&_h1]:text-16-semibold [&_h2]:mb-2 [&_h2]:text-15-semibold [&_h3]:mb-1 [&_h3]:text-14-semibold",
      "[&_table]:my-2 [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-[#eaded7] [&_th]:px-2 [&_th]:py-1 [&_td]:border [&_td]:border-[#eaded7] [&_td]:px-2 [&_td]:py-1",
    ].join(" ")
  return <Markdown text={props.text} cacheKey={props.cacheKey} class={markdownClass()} />
}

function MessageSegmentDisclosure(props: {
  segment: MobileDesktopMessageSegment
  collapsedWidth?: number
  open: boolean
  onWidthChange: (width: number) => void
  onOpenChange: (open: boolean) => void
}) {
  let root: HTMLDivElement | undefined
  const title = () => {
    if (props.segment.type === "reasoning") return props.segment.title || "思考过程"
    if (props.segment.title && !props.segment.toolName) return props.segment.title
    return props.segment.toolName ? `工具调用 · ${props.segment.toolName}` : "工具调用"
  }
  const body = () => props.segment.body?.trim() || "暂无可见详情。"
  const statusLabel = () => segmentStatusLabel(props.segment.status)
  const measureCollapsedWidth = () => {
    if (!root) return
    const width = root.getBoundingClientRect().width
    if (width > 0) props.onWidthChange(width)
  }
  const handleOpenChange = (open: boolean) => {
    if (open) measureCollapsedWidth()
    props.onOpenChange(open)
  }
  createEffect(() => {
    if (props.open) return
    queueMicrotask(() => {
      window.requestAnimationFrame(measureCollapsedWidth)
    })
  })
  return (
    <div
      ref={root}
      class="min-w-0 max-w-full overflow-hidden rounded-sm border px-[var(--mobile-segment-x)] py-[var(--mobile-segment-y)]"
      style={{
        width: props.open && props.collapsedWidth ? `${props.collapsedWidth}px` : undefined,
        "max-width": "100%",
      }}
      classList={{
        "border-[#e7d9f4] bg-[#fbf7ff]": props.segment.type === "reasoning",
        "border-[#d5e9ed] bg-[#f4fbfb]": props.segment.type === "tool",
      }}
    >
      <Collapsible variant="ghost" open={props.open} onOpenChange={handleOpenChange}>
        <Collapsible.Trigger class="flex !h-[var(--mobile-segment-height)] !min-h-0 w-full min-w-0 items-center justify-between gap-[var(--mobile-segment-gap)] rounded-sm text-left !text-[length:var(--mobile-segment-font)] font-medium !leading-tight text-[#3c3430]">
          <span class="min-w-0 truncate">{title()}</span>
          <div class="flex shrink-0 items-center gap-[var(--mobile-segment-gap)] text-[length:var(--mobile-segment-status-font)] leading-tight text-[#81756e]">
            <Show when={statusLabel()}>{(status) => <span class="max-w-24 truncate">{status()}</span>}</Show>
            <Collapsible.Arrow class="!size-4 text-[#9a8f88]" />
          </div>
        </Collapsible.Trigger>
        <Collapsible.Content>
          <div class="mt-1 max-h-[var(--mobile-segment-expanded-max)] min-w-0 max-w-full overflow-x-auto overflow-y-auto overscroll-contain rounded-sm bg-white/70 px-[var(--mobile-segment-expanded-x)] py-[var(--mobile-segment-expanded-y)]">
            <Show
              when={props.segment.type === "tool"}
              fallback={<MessageMarkdown text={body()} cacheKey={props.segment.id} compact />}
            >
              <pre class="whitespace-pre-wrap break-words text-11-regular leading-5 text-[#4d4540]">{body()}</pre>
            </Show>
          </div>
        </Collapsible.Content>
      </Collapsible>
    </div>
  )
}

function segmentStatusLabel(status?: string | null) {
  switch (status?.toLowerCase()) {
    case "completed":
    case "complete":
    case "done":
    case "success":
      return "完成"
    case "running":
    case "in_progress":
      return "运行中"
    case "pending":
    case "queued":
      return "等待"
    case "failed":
    case "failure":
      return "失败"
    case "error":
      return "错误"
    case "canceled":
    case "cancelled":
      return "已取消"
    default:
      return status || null
  }
}

function BlueprintPanel(props: {
  data: MobileMockData
  canCreate: boolean
  canMessage: boolean
  canEnd: boolean
  canApprove: boolean
  actionMessage?: string | null
  onCreatePlanningRequest: (goal: string) => Promise<void>
  onOpenPlanning: () => void
  onCancelRun: () => Promise<void>
  onSendMessage: (nodeId: string, text: string, mode: "default" | "top") => Promise<void>
  onApproveDiff: (changesetId?: string) => Promise<void>
  onRollbackDiff: (changesetId: string) => Promise<void>
}) {
  const blueprint = () => props.data.blueprint
  const currentNodeId = createMemo(
    () => blueprint().nodes.find((node) => node.label === blueprint().run.currentNode)?.id ?? blueprint().nodes[0]?.id ?? "",
  )
  const [structureOpen, setStructureOpen] = createSignal(false)
  const [selectedNodeId, setSelectedNodeId] = createSignal(currentNodeId())
  const [agentSheetNodeId, setAgentSheetNodeId] = createSignal<string | null>(null)
  const [activeDiffMetric, setActiveDiffMetric] = createSignal<DiffMetricKey>("files")
  const [expandedDiffPath, setExpandedDiffPath] = createSignal<string | null>(null)
  const agentSheetNode = createMemo(() => blueprint().nodes.find((node) => node.id === agentSheetNodeId()) ?? null)

  createEffect(() => {
    if (!blueprint().nodes.some((node) => node.id === selectedNodeId())) setSelectedNodeId(currentNodeId())
  })

  const selectNode = (node: BlueprintNode) => {
    setSelectedNodeId(node.id)
  }

  const openAgentInfo = (node: BlueprintNode) => {
    selectNode(node)
    setAgentSheetNodeId(node.id)
  }

  const closeAgentInfo = () => {
    setAgentSheetNodeId(null)
  }

  const toggleDiffFile = (file: BlueprintDiffFile) => {
    setExpandedDiffPath((current) => (current === file.path ? null : file.path))
  }

  return (
    <section data-testid="blueprint-panel" class="grid gap-4">
      <Show when={structureOpen()}>
        <BlueprintStructureOverlay
          nodes={blueprint().nodes}
          edges={blueprint().edges}
          selectedNodeId={selectedNodeId()}
          onSelectNode={openAgentInfo}
          onClose={() => setStructureOpen(false)}
          currentNode={blueprint().run.currentNode}
          progress={blueprint().run.progress}
        />
      </Show>

      <MobilePlanningForm
        canCreate={props.canCreate}
        actionMessage={props.actionMessage}
        onCreatePlanningRequest={props.onCreatePlanningRequest}
      />

      <section
        data-testid="blueprint-structure-preview"
        class="rounded-md border border-[#eaded7] bg-white p-4 text-left shadow-[0_12px_30px_rgba(48,38,32,0.05)]"
      >
        <div class="flex items-center justify-between gap-3">
          <SectionTitle title="蓝图结构" icon="blueprint" />
          <button
            type="button"
            data-mobile-touch
            class="flex size-8 shrink-0 items-center justify-center rounded-md border border-[#eaded7] bg-[#fbf7f4] text-[#6f6560] transition-colors hover:border-[#161312] hover:text-[#161312] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#161312]"
            aria-label="打开蓝图结构全屏查看"
            onClick={() => setStructureOpen(true)}
          >
            <Icon name="expand" size="small" />
          </button>
        </div>
        <BlueprintStructureMap
          nodes={blueprint().nodes}
          edges={blueprint().edges}
          variant="preview"
          selectedNodeId={selectedNodeId()}
          onSelectNode={openAgentInfo}
          onOpenFullscreen={() => setStructureOpen(true)}
        />
      </section>

      <div>
        <p class="text-12-medium uppercase tracking-[0.14em] text-[#b5837d]">蓝图</p>
        <h2 class="mt-1 text-22-semibold text-[#161312]">{blueprint().title}</h2>
        <p class="mt-2 text-13-regular leading-5 text-[#81756e]">{blueprint().description}</p>
      </div>

      <section class="rounded-md border border-[#eaded7] bg-white p-4 shadow-[0_12px_30px_rgba(48,38,32,0.05)]">
        <SectionTitle title="结构总览" icon="blueprint" />
        <div class="mt-4 grid gap-2">
          <For
            each={blueprint().nodes}
            fallback={
              <div class="rounded-md border border-dashed border-[#eaded7] bg-[#fbf7f4] px-3 py-4 text-13-regular text-[#81756e]">
                等待桌面端同步蓝图结构
              </div>
            }
          >
            {(node) => (
              <button
                type="button"
                data-mobile-touch
                data-testid="blueprint-node-row"
                aria-pressed={selectedNodeId() === node.id}
                class="flex w-full items-center gap-2 rounded-md border px-2 py-2 text-left transition-[background-color,border-color,box-shadow]"
                classList={{
                  "border-[#efc8c1] bg-[#fff7f5] shadow-[0_8px_18px_rgba(185,79,69,0.08)]":
                    selectedNodeId() === node.id,
                  "border-[#f0e7e1] bg-[#fbf7f4] hover:border-[#eaded7] hover:bg-[#fffdfa]":
                    selectedNodeId() !== node.id,
                }}
                onClick={() => openAgentInfo(node)}
              >
                <span class={`shrink-0 rounded-full border px-2.5 py-1 text-12-medium ${nodeStateTone(node.state)}`}>
                  {nodeStateLabel(node.state)}
                </span>
                <span class="min-w-0 flex-1 truncate text-13-medium text-[#2c2521]">
                  {node.label}
                </span>
                <span class="shrink-0 rounded-full border border-[#eaded7] bg-white px-2 py-1 text-10-medium text-[#81756e]">
                  {nodeKindLabel(node.kind)}
                </span>
                <span class="shrink-0 rounded-full bg-white px-2 py-1 text-11-medium text-[#9a8f88]">信息</span>
              </button>
            )}
          </For>
        </div>
      </section>

      <section class="rounded-md border border-[#eaded7] bg-white p-4 shadow-[0_12px_30px_rgba(48,38,32,0.05)]">
        <SectionTitle title="运行情况" icon="status" />
        <div class="mt-4 rounded-md border border-[#f0e7e1] bg-[#fbf7f4] p-3">
          <div class="flex items-center justify-between gap-3">
            <div>
              <div class="text-13-semibold text-[#161312]">{blueprint().run.label}</div>
              <div class="mt-1 text-12-regular text-[#81756e]">当前节点：{blueprint().run.currentNode || "无"}</div>
            </div>
            <div class="rounded-full border border-[#f1d0ca] bg-[#fff1ee] px-3 py-1 text-12-medium text-[#b94f45]">
              {blueprint().run.progress}%
            </div>
          </div>
          <div class="mt-3 h-2 overflow-hidden rounded-full bg-[#eee4de]">
            <div class="h-full rounded-full bg-[#ef7b70]" style={{ width: `${blueprint().run.progress}%` }} />
          </div>
          <div class="mt-3 flex flex-wrap gap-2">
            <For
              each={blueprint().run.agents}
              fallback={
                <span class="rounded-full border border-stone-200 bg-white px-2.5 py-1 text-12-medium text-stone-500">
                  暂无 Agent 状态
                </span>
              }
            >
              {(agent) => (
                <span class={`rounded-full border px-2.5 py-1 text-12-medium ${nodeStateTone(agent.state)}`}>
                  {agent.name}
                </span>
              )}
            </For>
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              data-mobile-touch
              data-testid="run-start-planning"
              disabled={!props.data.server?.projectId}
              class="inline-flex h-8 items-center gap-1.5 rounded-md border border-[#eaded7] bg-white px-2.5 text-11-medium text-[#3c3430] disabled:cursor-not-allowed disabled:opacity-60"
              onClick={props.onOpenPlanning}
            >
              <Icon name="arrow-right" size="small" />
              开始规划
            </button>
            <button
              type="button"
              data-mobile-touch
              data-testid="run-cancel"
              disabled={!props.canEnd}
              class="inline-flex h-8 items-center gap-1.5 rounded-md border border-[#f0d4cf] bg-[#fff7f5] px-2.5 text-11-medium text-[#9f6159] disabled:cursor-not-allowed disabled:opacity-60"
              onClick={() => void props.onCancelRun()}
            >
              <Icon name="close" size="small" />
              取消运行
            </button>
          </div>
          <Show when={props.actionMessage}>
            {(message) => <div class="mt-2 text-11-regular text-[#9a8f88]">{message()}</div>}
          </Show>
          <div class="mt-3 text-11-regular text-[#a69b95]">更新于 {blueprint().run.updatedAt}</div>
        </div>
      </section>

      <section class="rounded-md border border-[#eaded7] bg-white p-4 shadow-[0_12px_30px_rgba(48,38,32,0.05)]">
        <SectionTitle title="Diff" icon="code-lines" />
        <div class="mt-4 grid grid-cols-3 gap-2">
          <DiffMetricButton
            metric="files"
            active={activeDiffMetric() === "files"}
            label="文件"
            value={`${blueprint().diff.fileCount}`}
            onClick={setActiveDiffMetric}
          />
          <DiffMetricButton
            metric="additions"
            active={activeDiffMetric() === "additions"}
            label="新增"
            value={`+${blueprint().diff.additions}`}
            tone="plus"
            onClick={setActiveDiffMetric}
          />
          <DiffMetricButton
            metric="deletions"
            active={activeDiffMetric() === "deletions"}
            label="删除"
            value={`-${blueprint().diff.deletions}`}
            tone="minus"
            onClick={setActiveDiffMetric}
          />
        </div>
        <div
          data-testid="diff-metric-detail"
          class="mt-3 rounded-md border border-[#f0e7e1] bg-[#fffdfa] px-3 py-2 text-12-regular leading-5 text-[#6f6560]"
        >
          {diffMetricDetail(activeDiffMetric(), blueprint().diff)}
        </div>
        <div class="mt-3 grid gap-2">
          <For
            each={blueprint().diff.files}
            fallback={
              <div class="rounded-md border border-dashed border-[#eaded7] bg-[#fbf7f4] px-3 py-4 text-13-regular text-[#81756e]">
                暂无 diff 数据
              </div>
            }
          >
            {(file) => (
              <DiffFileAccordion
                file={file}
                open={expandedDiffPath() === file.path}
                onToggle={() => toggleDiffFile(file)}
                canApprove={props.canApprove}
                onApprove={() => props.onApproveDiff(file.changesetId)}
                onRollback={() => (file.changesetId ? props.onRollbackDiff(file.changesetId) : Promise.resolve())}
              />
            )}
          </For>
        </div>
      </section>

      <Show when={agentSheetNode()}>
        {(node) => (
          <AgentInfoSheet
            node={node()}
            canMessage={props.canMessage}
            onSendMessage={(text, mode) => props.onSendMessage(node().id, text, mode)}
            onClose={closeAgentInfo}
          />
        )}
      </Show>
    </section>
  )
}

type DiffMetricKey = "files" | "additions" | "deletions"

function AgentInfoSheet(props: {
  node: BlueprintNode
  canMessage: boolean
  onSendMessage: (text: string, mode: "default" | "top") => Promise<void>
  onClose: () => void
}) {
  const panel = () => props.node.agentPanel
  const isAgentLike = () => props.node.kind === "agent" || props.node.kind === "worker_agent"
  const [statusDetailsOpen, setStatusDetailsOpen] = createSignal(false)
  const [text, setText] = createSignal("")
  const [mode, setMode] = createSignal<"default" | "top">("default")
  const [sending, setSending] = createSignal(false)
  const canSend = () => isAgentLike() && props.canMessage && text().trim().length > 0 && !sending()
  const send = async () => {
    if (!canSend()) return
    setSending(true)
    try {
      await props.onSendMessage(text().trim(), mode())
      setText("")
    } finally {
      setSending(false)
    }
  }

  return (
    <div
      data-testid="agent-info-sheet-backdrop"
      class="fixed inset-0 z-[70] flex items-end justify-center bg-[#f7eee8]/75 px-3 pb-[max(12px,env(safe-area-inset-bottom))] pt-10 backdrop-blur-sm"
      onClick={props.onClose}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-label={`${props.node.label} 节点信息`}
        data-testid="agent-info-sheet"
        data-node-id={props.node.id}
        data-node-kind={props.node.kind}
        class="flex max-h-[82dvh] w-full max-w-[460px] flex-col overflow-hidden rounded-t-lg border border-[#eaded7] bg-[#fffdfa] text-[#161312] shadow-[0_24px_70px_rgba(90,70,62,0.20),0_0_0_1px_rgba(255,255,255,0.70)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div class="flex h-11 shrink-0 items-center justify-between border-b border-[#f0e7e1] bg-white/80 px-3">
          <div class="min-w-0 flex-1">
            <div class="truncate text-12-medium text-[#161312]">{props.node.label}</div>
            <div class="mt-0.5 truncate text-10-regular text-[#9a8f88]">
              {nodeKindLabel(props.node.kind)} · {nodeStateLabel(props.node.state)}
            </div>
          </div>
          <button
            type="button"
            data-mobile-touch
            class="flex size-8 shrink-0 items-center justify-center rounded-md text-[#81756e] transition-colors hover:bg-[#fff7f5] hover:text-[#161312] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#efc8c1]"
            aria-label="关闭 Agent 信息面板"
            onClick={props.onClose}
          >
            <Icon name="close" size="small" />
          </button>
        </div>

        <div
          data-testid="agent-info-sheet-scroll"
          class="min-h-0 flex-1 overflow-y-auto overscroll-contain [scrollbar-color:#d8c6bd_transparent] [scrollbar-width:thin] [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-[#d8c6bd] [&::-webkit-scrollbar-thumb:hover]:bg-[#c8aa99] [&::-webkit-scrollbar-track]:bg-transparent"
        >
          <div data-testid="agent-info-status-summary" class="border-b border-[#f0e7e1] p-3">
            <Show
              when={isAgentLike()}
              fallback={
                <div class="grid grid-cols-3 gap-2">
                  <AgentPanelMetric label="类型" value={nodeKindLabel(props.node.kind)} />
                  <AgentPanelMetric label="状态" value={nodeStateLabel(props.node.state)} />
                  <AgentPanelMetric label="输入" value={`${props.node.inputPorts?.length ?? 0}`} />
                  <AgentPanelMetric label="输出" value={`${props.node.outputPorts?.length ?? 0}`} />
                  <AgentPanelMetric label="节拍" value={props.node.everyNTicks ? `${props.node.everyNTicks}` : "-"} />
                  <AgentPanelMetric label="更新" value={panel().updatedAt} />
                </div>
              }
            >
              <div class="grid grid-cols-3 gap-2">
                <AgentPanelMetric label="状态" value={nodeStateLabel(props.node.state)} />
                <AgentPanelMetric label="任务状态" value={panel().taskStatus} />
                <AgentPanelMetric label="队列" value={`${panel().queueSize}`} />
                <AgentPanelMetric label="消息" value={`${panel().messagesSent}`} />
                <AgentPanelMetric label="忙碌" value={`${panel().busyCount}`} />
                <AgentPanelMetric label="更新" value={panel().updatedAt} />
              </div>
            </Show>
            <NodeTypeDetails node={props.node} />
            <div data-testid="agent-info-status-card" class="mt-3 overflow-hidden rounded-md border border-[#f0d4cf] bg-[#fff7f5]">
              <button
                type="button"
                data-mobile-touch
                data-testid="agent-info-status-toggle"
                aria-expanded={statusDetailsOpen()}
                class="flex w-full items-center justify-between gap-3 px-2.5 py-2 text-left"
                onClick={() => setStatusDetailsOpen((open) => !open)}
              >
                <span class="min-w-0">
                  <span class="block text-10-medium uppercase text-[#b5837d]">运行状态</span>
                  <span class="mt-1 block truncate text-11-regular text-[#6f6560]">职责：{props.node.role}</span>
                </span>
                <Icon
                  name="chevron-down"
                  size="small"
                  class="shrink-0 text-[#b5837d] transition-transform"
                  classList={{ "rotate-180": statusDetailsOpen() }}
                />
              </button>
              <Show when={statusDetailsOpen()}>
                <div data-testid="agent-info-status-details" class="grid gap-1 border-t border-[#f0d4cf] px-2.5 py-2">
                  <AgentPanelStatusRow label="说明" value={props.node.detail} />
                  <For each={panel().statusDetails}>
                    {(item) => <AgentPanelStatusRow label={item.label} value={item.value} mono />}
                  </For>
                </div>
              </Show>
            </div>
          </div>

          <div
            data-testid="agent-info-chat"
            class="min-h-[34dvh] px-3 py-2 [overflow-anchor:none]"
          >
            <Show
              when={panel().events.length}
              fallback={<div class="py-8 text-center text-11-regular text-[#a69b95]">暂无 agent 输出</div>}
            >
              <For each={panel().events}>{(event) => <AgentPanelEventRow event={event} />}</For>
            </Show>
          </div>

          <Show
            when={isAgentLike()}
            fallback={
              <div class="border-t border-[#f0e7e1] bg-white/70 p-3">
                <div class="rounded-md border border-[#f2dfb8] bg-[#fff8e7] px-2 py-1.5 text-11-regular text-[#8a6421]">
                  {nodeKindLabel(props.node.kind)} 是桌面端蓝图结构节点，移动端只展示同步信息，不提供编辑或执行入口。
                </div>
              </div>
            }
          >
            <div class="border-t border-[#f0e7e1] bg-white/70 p-3">
              <div class="mb-2 rounded-md border border-[#f2dfb8] bg-[#fff8e7] px-2 py-1.5 text-11-regular text-[#8a6421]">
                {props.canMessage ? "API 已就绪：消息将通过 Collaboration Server 发送。" : panel().disabledNotice}
              </div>
              <textarea
                data-testid="agent-info-input"
                aria-label={`发送给 ${props.node.label}`}
                class="h-16 w-full resize-none rounded-md border border-[#eaded7] bg-[#fbf7f4] px-2 py-1.5 text-12-regular text-[#3c3430] outline-none placeholder:text-[#a69b95] disabled:cursor-not-allowed disabled:opacity-80"
                disabled={!props.canMessage || sending()}
                placeholder={panel().inputPlaceholder}
                value={text()}
                onInput={(event) => setText(event.currentTarget.value)}
              />
              <div class="mt-2 flex items-center gap-2">
                <select
                  data-testid="agent-info-mode"
                  aria-label="Agent 消息模式"
                  class="h-8 rounded-md border border-[#eaded7] bg-white px-2 text-11-regular text-[#6f6560] disabled:cursor-not-allowed disabled:opacity-75"
                  disabled={!props.canMessage || sending()}
                  value={mode()}
                  onChange={(event) => setMode(event.currentTarget.value === "top" ? "top" : "default")}
                >
                  <option value="default">默认</option>
                  <option value="top">置顶</option>
                </select>
                <button
                  type="button"
                  data-testid="agent-info-send"
                  class="ml-auto h-8 rounded-md border border-[#eaded7] bg-[#fbf7f4] px-3 text-11-medium text-[#81756e] disabled:cursor-not-allowed disabled:opacity-70"
                  disabled={!canSend()}
                  onClick={() => void send()}
                >
                  发送
                </button>
              </div>
            </div>
          </Show>
        </div>
      </section>
    </div>
  )
}

function NodeTypeDetails(props: { node: BlueprintNode }) {
  const inputs = () => props.node.inputPorts ?? []
  const outputs = () => props.node.outputPorts ?? []
  return (
    <div data-testid="node-type-details" class="mt-3 rounded-md border border-[#f0e7e1] bg-[#fffdfa] px-2.5 py-2">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="text-10-medium uppercase text-[#b5837d]">{nodeKindLabel(props.node.kind)}</div>
          <div class="mt-1 text-12-regular leading-5 text-[#6f6560]">{props.node.summary || props.node.detail}</div>
        </div>
        <Show when={props.node.everyNTicks}>
          {(every) => <span class="shrink-0 rounded-full border border-[#eaded7] bg-white px-2 py-1 text-10-medium text-[#81756e]">每 {every()} tick</span>}
        </Show>
      </div>
      <Show when={inputs().length || outputs().length}>
        <div class="mt-2 grid gap-1.5">
          <PortList label="输入" ports={inputs()} />
          <PortList label="输出" ports={outputs()} />
        </div>
      </Show>
    </div>
  )
}

function PortList(props: { label: string; ports: string[] }) {
  return (
    <div class="flex min-w-0 items-start gap-2">
      <span class="shrink-0 text-10-medium text-[#9a8f88]">{props.label}</span>
      <div class="flex min-w-0 flex-1 flex-wrap gap-1">
        <Show when={props.ports.length} fallback={<span class="text-10-regular text-[#a69b95]">无</span>}>
          <For each={props.ports}>
            {(port) => (
              <span class="max-w-full truncate rounded-full border border-[#eaded7] bg-white px-2 py-0.5 text-10-regular text-[#6f6560]">
                {port}
              </span>
            )}
          </For>
        </Show>
      </div>
    </div>
  )
}

function AgentPanelMetric(props: { label: string; value: string }) {
  return (
    <div class="min-w-0 rounded-md border border-[#f0e7e1] bg-[#fbf7f4] px-2 py-2">
      <div class="truncate text-10-regular text-[#9a8f88]">{props.label}</div>
      <div class="mt-1 truncate text-12-semibold text-[#161312]">{props.value}</div>
    </div>
  )
}

function AgentPanelStatusRow(props: { label: string; value: string; mono?: boolean }) {
  return (
    <div class="grid grid-cols-[72px_minmax(0,1fr)] gap-2 text-11-regular leading-4">
      <span class="text-[#9a8f88]">{props.label}</span>
      <span
        class="min-w-0 break-words text-[#3c3430]"
        classList={{ "font-mono text-[10px]": props.mono }}
      >
        {props.value}
      </span>
    </div>
  )
}

function AgentPanelEventRow(props: { event: BlueprintAgentPanelEvent }) {
  return (
    <article
      data-testid="agent-info-event"
      data-tone={props.event.tone}
      class={`mb-2 rounded-md border px-2.5 py-2 ${agentPanelEventToneClass(props.event.tone)}`}
    >
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <div class="truncate text-11-semibold text-[#161312]">{props.event.title}</div>
          <Show when={props.event.detail}>
            {(detail) => <div class="mt-0.5 truncate text-10-regular text-[#9a8f88]">{detail()}</div>}
          </Show>
        </div>
        <div class="shrink-0 text-right text-10-regular text-[#a69b95]">
          <Show when={props.event.status}>
            {(status) => <div class="uppercase">{status()}</div>}
          </Show>
          <Show when={props.event.time}>
            {(time) => <div>{time()}</div>}
          </Show>
        </div>
      </div>
      <p class="mt-2 whitespace-pre-wrap break-words text-11-regular leading-5 text-[#3c3430]">{props.event.text}</p>
    </article>
  )
}

function agentPanelEventToneClass(tone: BlueprintAgentPanelEvent["tone"]) {
  switch (tone) {
    case "user":
      return "border-[#d8d5f0] bg-[#f7f5ff]"
    case "reply":
      return "border-[#d9eadf] bg-[#f5fbf7]"
    case "reasoning":
      return "border-[#eaded7] bg-[#fffdfa]"
    case "tool":
      return "border-[#dce8d4] bg-[#f8fbf3]"
    case "error":
      return "border-[#f3c7c0] bg-[#fff1ee]"
    case "event":
      return "border-[#f0e7e1] bg-[#fbf7f4]"
  }
}

function DiffMetricButton(props: {
  metric: DiffMetricKey
  active: boolean
  label: string
  value: string
  tone?: "plus" | "minus"
  onClick: (metric: DiffMetricKey) => void
}) {
  return (
    <button
      type="button"
      data-mobile-touch
      data-testid={`diff-metric-${props.metric}`}
      aria-pressed={props.active}
      class="min-w-0 rounded-md border px-3 py-2 text-left transition-[background-color,border-color,box-shadow]"
      classList={{
        "border-[#efc8c1] bg-[#fff7f5] shadow-[0_8px_18px_rgba(185,79,69,0.08)]": props.active,
        "border-[#f0e7e1] bg-[#fbf7f4] hover:border-[#eaded7] hover:bg-[#fffdfa]": !props.active,
      }}
      onClick={() => props.onClick(props.metric)}
    >
      <div class="text-11-regular text-[#9a8f88]">{props.label}</div>
      <div
        class="mt-1 truncate text-16-semibold"
        classList={{
          "text-emerald-700": props.tone === "plus",
          "text-rose-700": props.tone === "minus",
          "text-[#161312]": !props.tone,
        }}
      >
        {props.value}
      </div>
    </button>
  )
}

function diffMetricDetail(metric: DiffMetricKey, diff: MobileMockData["blueprint"]["diff"]) {
  if (diff.fileCount === 0 && diff.additions === 0 && diff.deletions === 0) return "当前没有后端同步的 diff 数据。"
  switch (metric) {
    case "files":
      return `本轮同步到 ${diff.fileCount} 个变更文件。`
    case "additions":
      return `新增 ${diff.additions} 行。`
    case "deletions":
      return `删除 ${diff.deletions} 行。`
  }
}

function DiffFileAccordion(props: {
  file: BlueprintDiffFile
  open: boolean
  canApprove: boolean
  onToggle: () => void
  onApprove: () => Promise<void>
  onRollback: () => Promise<void>
}) {
  return (
    <article
      data-testid="blueprint-diff-file"
      data-expanded={props.open || undefined}
      class="overflow-hidden rounded-md border border-[#f0e7e1] bg-[#fbf7f4]"
    >
      <button
        type="button"
        data-mobile-touch
        class="flex w-full items-start justify-between gap-3 px-3 py-2 text-left transition-colors hover:bg-[#fffdfa]"
        aria-expanded={props.open}
        onClick={props.onToggle}
      >
        <span class="min-w-0">
          <span class="block truncate text-12-semibold text-[#161312]">{props.file.path}</span>
          <span class="mt-1 block text-12-regular text-[#81756e]">{props.file.summary}</span>
        </span>
        <span class="flex shrink-0 items-center gap-2 pt-0.5 text-11-medium text-[#9a8f88]">
          <span class="text-emerald-700">+{props.file.additions}</span>
          <span class="text-rose-700">-{props.file.deletions}</span>
          <Icon
            name="chevron-down"
            size="small"
            class="text-[#b8aaa2] transition-transform"
            classList={{ "rotate-180": props.open }}
          />
        </span>
      </button>
      <Show when={props.open}>
        <div data-testid="blueprint-diff-preview" class="border-t border-[#f0e7e1] bg-white">
          <For each={props.file.previewLines}>{(line) => <DiffPreviewLine line={line} />}</For>
          <Show when={props.canApprove}>
            <div class="flex flex-wrap gap-2 border-t border-[#f0e7e1] bg-[#fffdfa] px-3 py-2">
              <button
                type="button"
                data-mobile-touch
                data-testid="diff-approve"
                class="inline-flex h-8 items-center gap-1.5 rounded-md border border-[#d9eadf] bg-[#f5fbf7] px-2.5 text-11-medium text-emerald-700"
                onClick={(event) => {
                  event.stopPropagation()
                  void props.onApprove()
                }}
              >
                <Icon name="check" size="small" />
                Approve diff
              </button>
              <button
                type="button"
                data-mobile-touch
                data-testid="diff-rollback"
                disabled={!props.file.changesetId || !props.file.rollbackable}
                class="inline-flex h-8 items-center gap-1.5 rounded-md border border-[#f0d4cf] bg-[#fff7f5] px-2.5 text-11-medium text-[#9f6159] disabled:cursor-not-allowed disabled:opacity-60"
                onClick={(event) => {
                  event.stopPropagation()
                  void props.onRollback()
                }}
              >
                <Icon name="reset" size="small" />
                Rollback
              </button>
            </div>
          </Show>
        </div>
      </Show>
    </article>
  )
}

function DiffPreviewLine(props: { line: BlueprintDiffPreviewLine }) {
  return (
    <div
      data-line-type={props.line.type}
      class="min-w-0 whitespace-pre-wrap break-words px-3 py-1 font-mono text-[11px] leading-5"
      classList={{
        "bg-[#dafbe1] text-[#1f6f3a]": props.line.type === "add",
        "bg-[#ffebe9] text-[#8c2f28]": props.line.type === "delete",
        "bg-white text-[#4f463f]": props.line.type === "context",
      }}
    >
      {props.line.text}
    </div>
  )
}

type BlueprintStructureVariant = "preview" | "fullscreen"

type BlueprintMapPoint = {
  x: number
  y: number
}

type BlueprintViewport = BlueprintMapPoint & {
  zoom: number
}

const BLUEPRINT_CANVAS_WIDTH = 980
const BLUEPRINT_CANVAS_HEIGHT = 560
const BLUEPRINT_NODE_WIDTH = 156
const BLUEPRINT_NODE_HEIGHT = 72
const BLUEPRINT_ZOOM_MIN = 0.55
const BLUEPRINT_ZOOM_MAX = 2.4
const BLUEPRINT_TAP_THRESHOLD = 6

const blueprintNodeLayout: Record<string, BlueprintMapPoint> = {
  start: { x: 116, y: 122 },
  "top-agent": { x: 390, y: 122 },
  planner: { x: 664, y: 122 },
  "tick-refresh": { x: 116, y: 260 },
  "branch-review": { x: 390, y: 260 },
  "script-format": { x: 664, y: 260 },
  coder: { x: 664, y: 398 },
  review: { x: 390, y: 398 },
  summary: { x: 116, y: 398 },
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function blueprintInitialViewport(variant: BlueprintStructureVariant): BlueprintViewport {
  return variant === "fullscreen" ? { x: 28, y: 36, zoom: 0.72 } : { x: -34, y: 24, zoom: 0.56 }
}

function blueprintMapPoint(node: BlueprintNode, index: number) {
  const layout = blueprintNodeLayout[node.id]
  if (layout) return layout

  const column = index % 3
  const row = Math.floor(index / 3)
  const xSlots = [116, 390, 664]
  const visualColumn = row % 2 === 0 ? column : 2 - column
  return {
    x: xSlots[visualColumn] ?? 390,
    y: 122 + row * 276,
  }
}

function normalizedBlueprintMapPoints(nodes: BlueprintNode[]) {
  const fallbackPoints = nodes.map((node, index) => [node.id, blueprintMapPoint(node, index)] as const)
  const hasDesktopLayout = nodes.some((node) => isBlueprintLayoutPoint(node.layout))
  if (!hasDesktopLayout) return new Map(fallbackPoints)

  const rawPoints = nodes.map((node, index) => {
    const layout = isBlueprintLayoutPoint(node.layout) ? node.layout : blueprintMapPoint(node, index)
    return [node.id, { x: layout.x, y: layout.y }] as const
  })
  const xValues = rawPoints.map(([, point]) => point.x)
  const yValues = rawPoints.map(([, point]) => point.y)
  const minX = Math.min(...xValues)
  const maxX = Math.max(...xValues)
  const minY = Math.min(...yValues)
  const maxY = Math.max(...yValues)
  const marginX = 118
  const marginY = 86
  const availableWidth = BLUEPRINT_CANVAS_WIDTH - marginX * 2
  const availableHeight = BLUEPRINT_CANVAS_HEIGHT - marginY * 2
  const sourceWidth = maxX - minX
  const sourceHeight = maxY - minY
  const scale = Math.min(
    1,
    availableWidth / Math.max(sourceWidth, 1),
    availableHeight / Math.max(sourceHeight, 1),
  )
  const scaledWidth = sourceWidth * scale
  const scaledHeight = sourceHeight * scale
  const offsetX = marginX + (availableWidth - scaledWidth) / 2
  const offsetY = marginY + (availableHeight - scaledHeight) / 2

  return new Map(
    rawPoints.map(([id, point]) => [
      id,
      {
        x: offsetX + (point.x - minX) * scale,
        y: offsetY + (point.y - minY) * scale,
      },
    ]),
  )
}

function isBlueprintLayoutPoint(value: BlueprintNode["layout"] | undefined): value is BlueprintMapPoint {
  return Boolean(value && Number.isFinite(value.x) && Number.isFinite(value.y))
}

function blueprintEdgePath(from: BlueprintMapPoint, to: BlueprintMapPoint) {
  const dx = to.x - from.x
  const dy = to.y - from.y

  if (Math.abs(dx) >= Math.abs(dy)) {
    const direction = dx >= 0 ? 1 : -1
    const startX = from.x + direction * (BLUEPRINT_NODE_WIDTH / 2 - 2)
    const endX = to.x - direction * (BLUEPRINT_NODE_WIDTH / 2 + 10)
    return `M ${startX} ${from.y} L ${endX} ${to.y}`
  }

  const direction = dy >= 0 ? 1 : -1
  const startY = from.y + direction * (BLUEPRINT_NODE_HEIGHT / 2 - 2)
  const endY = to.y - direction * (BLUEPRINT_NODE_HEIGHT / 2 + 10)
  return `M ${from.x} ${startY} L ${to.x} ${endY}`
}

function distanceBetween(a: BlueprintMapPoint, b: BlueprintMapPoint) {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

function midpointBetween(a: BlueprintMapPoint, b: BlueprintMapPoint) {
  return {
    x: (a.x + b.x) / 2,
    y: (a.y + b.y) / 2,
  }
}

function zoomViewportAroundPoint(viewport: BlueprintViewport, zoom: number, point: BlueprintMapPoint): BlueprintViewport {
  const nextZoom = clamp(zoom, BLUEPRINT_ZOOM_MIN, BLUEPRINT_ZOOM_MAX)
  const worldX = (point.x - viewport.x) / viewport.zoom
  const worldY = (point.y - viewport.y) / viewport.zoom

  return {
    x: point.x - worldX * nextZoom,
    y: point.y - worldY * nextZoom,
    zoom: nextZoom,
  }
}

function blueprintNodeTone(state: BlueprintNode["state"]) {
  switch (state) {
    case "done":
      return {
        cardBackground: "#ecfdf5",
        cardBorder: "#6ee7b7",
        cardText: "#064e3b",
        chipBackground: "#d1fae5",
        chipBorder: "#6ee7b7",
        chipText: "#047857",
      }
    case "running":
      return {
        cardBackground: "#fff1f2",
        cardBorder: "#fda4af",
        cardText: "#881337",
        chipBackground: "#ffe4e6",
        chipBorder: "#fda4af",
        chipText: "#be123c",
      }
    case "queued":
      return {
        cardBackground: "#fffbeb",
        cardBorder: "#fcd34d",
        cardText: "#78350f",
        chipBackground: "#fef3c7",
        chipBorder: "#fcd34d",
        chipText: "#92400e",
      }
    case "idle":
      return {
        cardBackground: "#ffffff",
        cardBorder: "#d6d3d1",
        cardText: "#57534e",
        chipBackground: "#fafaf9",
        chipBorder: "#d6d3d1",
        chipText: "#78716c",
      }
    case "failed":
      return {
        cardBackground: "#fef2f2",
        cardBorder: "#fca5a5",
        cardText: "#7f1d1d",
        chipBackground: "#fee2e2",
        chipBorder: "#fca5a5",
        chipText: "#b91c1c",
      }
  }
}

function BlueprintStructureOverlay(props: {
  nodes: BlueprintNode[]
  edges: BlueprintEdge[]
  selectedNodeId?: string | null
  onSelectNode?: (node: BlueprintNode) => void
  onClose: () => void
  currentNode: string
  progress: number
}) {
  return (
    <div
      data-testid="blueprint-structure-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="蓝图结构全屏查看"
      class="fixed inset-0 z-50 flex flex-col bg-[#fbf7f4] text-[#161312]"
    >
      <div class="shrink-0 border-b border-[#eee4de] bg-[#fffdfa]/95 px-5 pb-4 pt-[max(16px,env(safe-area-inset-top))] shadow-[0_10px_32px_rgba(48,38,32,0.06)] backdrop-blur">
        <div class="mx-auto flex w-full max-w-[760px] items-center justify-between gap-3">
          <div class="min-w-0">
            <p class="text-12-medium uppercase tracking-[0.14em] text-[#b5837d]">蓝图</p>
            <h2 class="mt-1 truncate text-20-semibold text-[#161312]">蓝图结构</h2>
          </div>
          <button
            type="button"
            data-mobile-touch
            class="flex size-10 shrink-0 items-center justify-center rounded-md border border-[#eaded7] bg-white text-[#6f6560] transition-colors hover:border-[#161312] hover:text-[#161312] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#161312]"
            aria-label="关闭蓝图结构全屏查看"
            onClick={props.onClose}
          >
            <Icon name="close" size="small" />
          </button>
        </div>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto px-5 py-5">
        <div class="mx-auto grid w-full max-w-[760px] gap-4">
          <BlueprintStructureMap
            nodes={props.nodes}
            edges={props.edges}
            variant="fullscreen"
            selectedNodeId={props.selectedNodeId}
            onSelectNode={props.onSelectNode}
          />
          <div class="grid grid-cols-3 gap-2">
            <Metric label="节点" value={`${props.nodes.length}`} />
            <Metric label="当前" value={props.currentNode} />
            <Metric label="进度" value={`${props.progress}%`} />
          </div>
        </div>
      </div>
    </div>
  )
}

function BlueprintStructureMap(props: {
  nodes: BlueprintNode[]
  edges: BlueprintEdge[]
  variant: BlueprintStructureVariant
  selectedNodeId?: string | null
  onSelectNode?: (node: BlueprintNode) => void
  onOpenFullscreen?: () => void
}) {
  const fullscreen = () => props.variant === "fullscreen"
  const markerId = () => `blueprint-structure-arrow-${props.variant}`
  const [viewport, setViewport] = createSignal<BlueprintViewport>(blueprintInitialViewport(props.variant))
  const pointers = new Map<number, BlueprintMapPoint>()
  let frameRef: HTMLDivElement | undefined
  let dragStart: { pointer: BlueprintMapPoint; viewport: BlueprintViewport } | null = null
  let pinchStart: { distance: number; midpoint: BlueprintMapPoint; viewport: BlueprintViewport } | null = null
  let moved = false
  let pinched = false

  const nodeIndexById = createMemo(() => new Map(props.nodes.map((node, index) => [node.id, index] as const)))
  const mapPoints = createMemo(() => normalizedBlueprintMapPoints(props.nodes))
  const renderedEdges = createMemo(() => {
    const explicitEdges = props.edges.filter((edge) => nodeIndexById().has(edge.source) && nodeIndexById().has(edge.target))
    return explicitEdges
  })
  const edgePoint = (nodeId: string) => {
    return mapPoints().get(nodeId) ?? null
  }

  const relativePoint = (clientX: number, clientY: number): BlueprintMapPoint => {
    const rect = frameRef?.getBoundingClientRect()
    if (!rect) return { x: clientX, y: clientY }

    return {
      x: clientX - rect.left,
      y: clientY - rect.top,
    }
  }

  const activePinch = () => {
    const active = Array.from(pointers.values())
    if (active.length < 2) return null

    return {
      distance: distanceBetween(active[0], active[1]),
      midpoint: midpointBetween(active[0], active[1]),
    }
  }

  const zoomBy = (factor: number) => {
    const rect = frameRef?.getBoundingClientRect()
    const point = rect ? { x: rect.width / 2, y: rect.height / 2 } : { x: 0, y: 0 }
    setViewport((current) => zoomViewportAroundPoint(current, current.zoom * factor, point))
  }

  const handlePointerDown = (event: PointerEvent) => {
    const target = event.currentTarget as HTMLDivElement
    target.setPointerCapture(event.pointerId)
    pointers.set(event.pointerId, relativePoint(event.clientX, event.clientY))

    if (pointers.size === 1) {
      dragStart = { pointer: relativePoint(event.clientX, event.clientY), viewport: viewport() }
      pinchStart = null
      moved = false
      pinched = false
    } else {
      const pinch = activePinch()
      if (pinch) {
        pinchStart = { ...pinch, viewport: viewport() }
        dragStart = null
        pinched = true
      }
    }

    event.preventDefault()
  }

  const handlePointerMove = (event: PointerEvent) => {
    if (!pointers.has(event.pointerId)) return

    const point = relativePoint(event.clientX, event.clientY)
    pointers.set(event.pointerId, point)

    if (pointers.size >= 2 && pinchStart) {
      const pinch = activePinch()
      if (pinch && pinchStart.distance > 0) {
        moved = true
        pinched = true
        const nextZoom = pinchStart.viewport.zoom * (pinch.distance / pinchStart.distance)
        const worldX = (pinchStart.midpoint.x - pinchStart.viewport.x) / pinchStart.viewport.zoom
        const worldY = (pinchStart.midpoint.y - pinchStart.viewport.y) / pinchStart.viewport.zoom
        const clampedZoom = clamp(nextZoom, BLUEPRINT_ZOOM_MIN, BLUEPRINT_ZOOM_MAX)

        setViewport({
          x: pinch.midpoint.x - worldX * clampedZoom,
          y: pinch.midpoint.y - worldY * clampedZoom,
          zoom: clampedZoom,
        })
      }
    } else if (dragStart) {
      const dx = point.x - dragStart.pointer.x
      const dy = point.y - dragStart.pointer.y
      if (Math.hypot(dx, dy) > BLUEPRINT_TAP_THRESHOLD) moved = true

      setViewport({
        x: dragStart.viewport.x + dx,
        y: dragStart.viewport.y + dy,
        zoom: dragStart.viewport.zoom,
      })
    }

    event.preventDefault()
  }

  const handlePointerEnd = (event: PointerEvent) => {
    if (!pointers.has(event.pointerId)) return

    const target = event.currentTarget as HTMLDivElement
    if (target.hasPointerCapture(event.pointerId)) target.releasePointerCapture(event.pointerId)
    pointers.delete(event.pointerId)

    if (pointers.size === 1) {
      const pointer = Array.from(pointers.values())[0]
      dragStart = { pointer, viewport: viewport() }
      pinchStart = null
      return
    }

    if (pointers.size === 0) {
      const shouldOpen = !fullscreen() && !moved && !pinched
      dragStart = null
      pinchStart = null
      moved = false
      pinched = false

      if (shouldOpen) props.onOpenFullscreen?.()
    }
  }

  return (
    <div
      ref={(element) => (frameRef = element)}
      data-testid={fullscreen() ? "blueprint-structure-map-fullscreen" : "blueprint-structure-map"}
      class="relative mt-4 touch-none overflow-hidden rounded-md border border-[#eaded7] bg-[#fffdfa] select-none"
      classList={{
        "h-56 cursor-grab active:cursor-grabbing": !fullscreen(),
        "h-[calc(100dvh-190px)] min-h-[520px] cursor-grab active:cursor-grabbing": fullscreen(),
      }}
      aria-label={fullscreen() ? "蓝图结构全屏地图" : "蓝图结构预览地图"}
      onClick={(event) => event.stopPropagation()}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerEnd}
      onPointerCancel={handlePointerEnd}
    >
      <div
        data-testid="blueprint-structure-canvas"
        class="absolute left-0 top-0 overflow-hidden rounded-md bg-[linear-gradient(rgba(230,218,210,0.72)_1px,transparent_1px),linear-gradient(90deg,rgba(230,218,210,0.72)_1px,transparent_1px)] bg-[size:28px_28px]"
        style={{
          width: `${BLUEPRINT_CANVAS_WIDTH}px`,
          height: `${BLUEPRINT_CANVAS_HEIGHT}px`,
          transform: `translate3d(${viewport().x}px, ${viewport().y}px, 0) scale(${viewport().zoom})`,
          "transform-origin": "0 0",
        }}
      >
        <Show when={props.nodes.length === 0}>
          <div class="absolute inset-0 flex items-center justify-center px-4 text-center text-13-regular text-[#81756e]">
            等待桌面端同步蓝图结构
          </div>
        </Show>
        <svg
          class="absolute inset-0 size-full"
          viewBox={`0 0 ${BLUEPRINT_CANVAS_WIDTH} ${BLUEPRINT_CANVAS_HEIGHT}`}
          aria-hidden="true"
        >
          <defs>
            <marker id={markerId()} markerWidth="3.5" markerHeight="3.5" refX="3.25" refY="1.75" orient="auto">
              <path d="M 0 0 L 3.5 1.75 L 0 3.5 z" fill="#c8aa99" />
            </marker>
          </defs>
          <For each={renderedEdges()}>
            {(edge) => {
              const start = () => edgePoint(edge.source)
              const end = () => edgePoint(edge.target)

              return (
                <Show when={start() && end()}>
                  <path
                    d={blueprintEdgePath(start()!, end()!)}
                    fill="none"
                    stroke="#c8aa99"
                    stroke-width="5"
                    stroke-linecap="round"
                    marker-end={`url(#${markerId()})`}
                  />
                </Show>
              )
            }}
          </For>
        </svg>

        <For each={props.nodes}>
          {(node, index) => {
            const point = () => mapPoints().get(node.id) ?? blueprintMapPoint(node, index())
            const tone = () => blueprintNodeTone(node.state)

            return (
              <button
                type="button"
                data-testid="blueprint-structure-node"
                data-node-id={node.id}
                aria-pressed={props.selectedNodeId === node.id}
                class="absolute w-[156px] rounded-md border px-3 py-2.5 text-left shadow-[0_14px_26px_rgba(48,38,32,0.12)] transition-[box-shadow,border-color]"
                classList={{
                  "cursor-pointer ring-2 ring-[#f0c8c1] ring-offset-2 ring-offset-[#fffdfa]":
                    props.selectedNodeId === node.id,
                  "cursor-pointer hover:shadow-[0_16px_30px_rgba(48,38,32,0.16)]": !!props.onSelectNode,
                }}
                style={{
                  left: `${point().x}px`,
                  top: `${point().y}px`,
                  transform: "translate(-50%, -50%)",
                  "background-color": tone().cardBackground,
                  "border-color": tone().cardBorder,
                  color: tone().cardText,
                }}
                onPointerDown={(event) => {
                  if (props.onSelectNode) event.stopPropagation()
                }}
                onClick={(event) => {
                  if (!props.onSelectNode) return
                  event.stopPropagation()
                  props.onSelectNode(node)
                }}
              >
                <div class="flex justify-end">
                  <span
                    class="max-w-full truncate rounded-full border px-2 py-0.5 text-11-medium"
                    style={{
                      "background-color": tone().chipBackground,
                      "border-color": tone().chipBorder,
                      color: tone().chipText,
                    }}
                  >
                    {nodeStateLabel(node.state)}
                  </span>
                </div>
                <div class="mt-1 truncate text-10-medium uppercase text-[#81756e]">{nodeKindLabel(node.kind)}</div>
                <div class="mt-2 truncate text-14-semibold leading-5">{node.label}</div>
              </button>
            )
          }}
        </For>
      </div>

      <div class="absolute bottom-3 right-3 z-10 grid gap-2">
        <BlueprintZoomButton label="放大蓝图结构" testId="blueprint-structure-zoom-in" icon="plus-small" onClick={() => zoomBy(1.18)} />
        <BlueprintZoomButton label="缩小蓝图结构" testId="blueprint-structure-zoom-out" icon="dash" onClick={() => zoomBy(1 / 1.18)} />
      </div>
    </div>
  )
}

function BlueprintZoomButton(props: {
  label: string
  testId: string
  icon: "plus-small" | "dash"
  onClick: () => void
}) {
  return (
    <button
      type="button"
      data-mobile-touch
      data-testid={props.testId}
      class="flex size-9 items-center justify-center rounded-md border border-[#eaded7] bg-white text-[#4f463f] shadow-[0_10px_22px_rgba(48,38,32,0.14)] transition-colors hover:border-[#161312] hover:text-[#161312] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#161312]"
      aria-label={props.label}
      onPointerDown={(event) => event.stopPropagation()}
      onClick={(event) => {
        event.stopPropagation()
        props.onClick()
      }}
    >
      <span class="relative flex size-5 items-center justify-center">
        <Icon name="magnifying-glass" size="small" />
        <span class="absolute -right-1 -top-1 flex size-3.5 items-center justify-center rounded-full border border-[#eaded7] bg-white text-[#161312]">
          <Icon name={props.icon} size="small" />
        </span>
      </span>
    </button>
  )
}

function SectionTitle(props: { title: string; icon: Parameters<typeof Icon>[0]["name"] }) {
  return (
    <div class="flex items-center gap-2 text-15-semibold text-[#161312]">
      <Icon name={props.icon} size="small" />
      {props.title}
    </div>
  )
}

function Metric(props: { label: string; value: string; tone?: "plus" | "minus" }) {
  return (
    <div class="rounded-md border border-[#f0e7e1] bg-[#fbf7f4] px-3 py-2">
      <div class="text-11-regular text-[#9a8f88]">{props.label}</div>
      <div
        class="mt-1 text-16-semibold"
        classList={{
          "text-emerald-700": props.tone === "plus",
          "text-rose-700": props.tone === "minus",
          "text-[#161312]": !props.tone,
        }}
      >
        {props.value}
      </div>
    </div>
  )
}

function PendingPanel() {
  return (
    <section
      data-testid="pending-empty-panel"
      class="flex min-h-[420px] flex-col items-center justify-center rounded-md border border-dashed border-[#eaded7] bg-white px-8 text-center shadow-[0_12px_30px_rgba(48,38,32,0.05)]"
    >
      <div class="flex size-12 items-center justify-center rounded-full bg-[#fff1ee] text-[#b94f45]">
        <Icon name="status" />
      </div>
      <h2 class="mt-4 text-20-semibold text-[#161312]">待定</h2>
      <p class="mt-2 text-13-regular leading-5 text-[#81756e]">这里先保留为空状态，为后续扩展预留。</p>
    </section>
  )
}

function WritablePendingPanel(props: {
  server?: MobileServerState
  canCreate: boolean
  actionMessage?: string | null
  onAnswer: (requestId: string, questionId: string, answers: Record<string, unknown>) => Promise<void>
  onApprove: (requestId: string) => Promise<void>
  onReject: (requestId: string, reason: string) => Promise<void>
}) {
  const requests = () => props.server?.planningRequests ?? []
  const hasRequests = () => requests().length > 0

  return (
    <section data-testid="pending-panel" class="grid gap-3">
      <div class="rounded-md border border-[#eaded7] bg-white p-4 shadow-[0_12px_30px_rgba(48,38,32,0.05)]">
        <div class="flex items-center justify-between gap-3">
          <SectionTitle title="Pending" icon="status" />
          <span class="rounded-full border border-[#eaded7] bg-[#fbf7f4] px-2 py-1 text-11-medium text-[#81756e]">
            {requests().length}
          </span>
        </div>
        <Show when={props.actionMessage}>
          {(message) => (
            <div class="mt-3 rounded-md border border-[#f0e7e1] bg-[#fffdfa] px-3 py-2 text-12-regular text-[#6f6560]">
              {message()}
            </div>
          )}
        </Show>
      </div>

      <Show when={hasRequests()} fallback={<PendingPanel />}>
        <For each={requests()}>
          {(request) => (
            <PlanningRequestCard
              request={request}
              canCreate={props.canCreate}
              onAnswer={props.onAnswer}
              onApprove={props.onApprove}
              onReject={props.onReject}
            />
          )}
        </For>
      </Show>
    </section>
  )
}

function PlanningRequestCard(props: {
  request: MobilePlanningRequest
  canCreate: boolean
  onAnswer: (requestId: string, questionId: string, answers: Record<string, unknown>) => Promise<void>
  onApprove: (requestId: string) => Promise<void>
  onReject: (requestId: string, reason: string) => Promise<void>
}) {
  const [answer, setAnswer] = createSignal("")
  const [rejectReason, setRejectReason] = createSignal("")
  const questionId = () => String(props.request.pendingQuestion?.questionId ?? props.request.pendingQuestion?.id ?? "question")
  const questionItems = () =>
    Array.isArray(props.request.pendingQuestion?.questions)
      ? (props.request.pendingQuestion?.questions as Record<string, unknown>[])
      : []
  const firstQuestion = () => questionItems()[0]
  const answerKey = () => String(firstQuestion()?.id ?? "q1")
  const questionText = () =>
    String(
      firstQuestion()?.question ??
        props.request.pendingQuestion?.text ??
        props.request.pendingQuestion?.question ??
        props.request.pendingQuestion?.prompt ??
        "",
    )
  const plan = () => props.request.pendingPlan?.plan ?? props.request.pendingPlan

  return (
    <article
      data-testid="planning-request-card"
      class="rounded-md border border-[#eaded7] bg-white p-4 shadow-[0_12px_30px_rgba(48,38,32,0.05)]"
    >
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="text-13-semibold text-[#161312]">{props.request.goal}</div>
          <div class="mt-1 text-11-regular text-[#9a8f88]">{props.request.id}</div>
        </div>
        <span class="shrink-0 rounded-full border border-[#f0d4cf] bg-[#fff7f5] px-2 py-1 text-11-medium text-[#9f6159]">
          {props.request.status}
        </span>
      </div>

      <Show when={props.request.pendingQuestion}>
        <div class="mt-3 rounded-md border border-[#f0e7e1] bg-[#fbf7f4] p-3">
          <div class="text-12-semibold text-[#161312]">{questionText() || questionId()}</div>
          <textarea
            data-testid="planning-answer-input"
            class="mt-2 min-h-16 w-full resize-none rounded-md border border-[#eaded7] bg-white px-2 py-1.5 text-12-regular text-[#3c3430] outline-none"
            disabled={!props.canCreate}
            value={answer()}
            onInput={(event) => setAnswer(event.currentTarget.value)}
          />
          <button
            type="button"
            data-mobile-touch
            data-testid="planning-answer-submit"
            disabled={!props.canCreate || !answer().trim()}
            class="mt-2 h-8 rounded-md border border-[#161312] bg-[#161312] px-3 text-11-medium text-white disabled:cursor-not-allowed disabled:border-[#eaded7] disabled:bg-white disabled:text-[#9a8f88]"
            onClick={() => void props.onAnswer(props.request.id, questionId(), { [answerKey()]: answer().trim() })}
          >
            Answer
          </button>
        </div>
      </Show>

      <Show when={props.request.pendingPlan}>
        <div class="mt-3 rounded-md border border-[#f0e7e1] bg-[#fbf7f4] p-3">
          <div class="text-12-semibold text-[#161312]">Plan ready</div>
          <pre class="mt-2 max-h-36 overflow-auto whitespace-pre-wrap rounded-md bg-white p-2 text-[11px] leading-5 text-[#3c3430]">
            {JSON.stringify(plan(), null, 2)}
          </pre>
          <textarea
            data-testid="planning-reject-reason"
            class="mt-2 min-h-12 w-full resize-none rounded-md border border-[#eaded7] bg-white px-2 py-1.5 text-12-regular text-[#3c3430] outline-none"
            placeholder="Reject reason"
            disabled={!props.canCreate}
            value={rejectReason()}
            onInput={(event) => setRejectReason(event.currentTarget.value)}
          />
          <div class="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              data-mobile-touch
              data-testid="planning-approve"
              disabled={!props.canCreate}
              class="inline-flex h-8 items-center gap-1.5 rounded-md border border-[#d9eadf] bg-[#f5fbf7] px-2.5 text-11-medium text-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
              onClick={() => void props.onApprove(props.request.id)}
            >
              <Icon name="check" size="small" />
              Approve
            </button>
            <button
              type="button"
              data-mobile-touch
              data-testid="planning-reject"
              disabled={!props.canCreate}
              class="inline-flex h-8 items-center gap-1.5 rounded-md border border-[#f0d4cf] bg-[#fff7f5] px-2.5 text-11-medium text-[#9f6159] disabled:cursor-not-allowed disabled:opacity-60"
              onClick={() => void props.onReject(props.request.id, rejectReason().trim() || "rejected from mobile")}
            >
              <Icon name="close" size="small" />
              Reject
            </button>
          </div>
        </div>
      </Show>

      <Show when={props.request.error}>
        {(error) => (
          <div class="mt-3 rounded-md border border-[#f0d4cf] bg-[#fff7f5] px-3 py-2 text-12-regular text-[#9f6159]">
            {error()}
          </div>
        )}
      </Show>
    </article>
  )
}
