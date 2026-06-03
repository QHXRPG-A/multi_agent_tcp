// @refresh reload

import {
  ACCEPTED_FILE_EXTENSIONS,
  ACCEPTED_FILE_TYPES,
  AppBaseProviders,
  AppInterface,
  handleNotificationClick,
  loadLocaleDict,
  normalizeLocale,
  type Locale,
  type Platform,
  PlatformProvider,
  ServerConnection,
  useCommand,
} from "@opencode-ai/app"
import type { AsyncStorage } from "@solid-primitives/storage"
import { createMemoryHistory, MemoryRouter, type BaseRouterProps } from "@solidjs/router"
import { createEffect, createResource, onCleanup, onMount, Show } from "solid-js"
import { render } from "solid-js/web"
import pkg from "../../package.json"
import { initI18n, t } from "./i18n"
import { webviewZoom } from "./webview-zoom"
import "./styles.css"
import { useTheme } from "@opencode-ai/ui/theme"

const root = document.getElementById("root")
if (import.meta.env.DEV && !(root instanceof HTMLElement)) {
  throw new Error(t("error.dev.rootNotFound"))
}

void initI18n()

const deepLinkEvent = "opencode:deep-link"
const blueprintWindowDockEvent = "gulicode:blueprint-window-dock"
const blueprintWindowClosedEvent = "gulicode:blueprint-window-closed"
const blueprintWindowPlanningSubmitEvent = "gulicode:blueprint-planning-submit"
const desktopControlBridgeCommandEvent = "gulicode:desktop-control-bridge-command"

function base64Encode(value: string) {
  const bytes = new TextEncoder().encode(value)
  const binary = Array.from(bytes, (byte) => String.fromCharCode(byte)).join("")
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "")
}

const emitDeepLinks = (urls: string[]) => {
  if (urls.length === 0) return
  window.__OPENCODE__ ??= {}
  const pending = window.__OPENCODE__.deepLinks ?? []
  window.__OPENCODE__.deepLinks = [...pending, ...urls]
  window.dispatchEvent(new CustomEvent(deepLinkEvent, { detail: { urls } }))
}

const listenForDeepLinks = () => {
  void window.api.consumeInitialDeepLinks().then((urls) => emitDeepLinks(urls))
  return window.api.onDeepLink((urls) => emitDeepLinks(urls))
}

const createPlatform = (): Platform => {
  const api = window.api as typeof window.api & {
    blueprintRunDiff?: (runId: string) => Promise<Record<string, unknown>>
    blueprintChangesetDiff?: (runId: string, changesetId: string) => Promise<Record<string, unknown>>
    blueprintRollbackChangesets?: (
      runId: string,
      toChangesetId: string,
      reason?: string,
    ) => Promise<Record<string, unknown>>
    blueprintRestoreRollback?: (
      runId: string,
      rollbackId?: string,
      reason?: string,
    ) => Promise<Record<string, unknown>>
    blueprintCreateScriptNode?: (projectDir: string, name: string, description?: string) => Promise<Record<string, unknown>>
    blueprintListEditors?: () => Promise<
      Array<{
        id: string
        label: string
        command?: string
        args?: string[]
        source: string
        systemDefault?: boolean
      }>
    >
    blueprintOpenScriptInEditor?: (
      projectDir: string,
      modulePath: string,
      editorId?: string,
    ) => Promise<Record<string, unknown>>
    blueprintResidentServices?: () => Promise<Record<string, unknown>>
    blueprintCreateResidentService?: (name: string, description?: string) => Promise<Record<string, unknown>>
    blueprintOpenResidentServiceInEditor?: (modulePath: string, editorId?: string) => Promise<Record<string, unknown>>
    blueprintStartResidentService?: (serviceName: string) => Promise<Record<string, unknown>>
    blueprintStopResidentService?: (serviceName: string) => Promise<Record<string, unknown>>
    blueprintResidentServiceLogs?: (serviceName: string, limit?: number) => Promise<Record<string, unknown>>
    blueprintResidentServiceDocs?: (serviceName: string) => Promise<Record<string, unknown>>
  }
  const blueprintCreateScriptNode = api.blueprintCreateScriptNode
  const blueprintListEditors = api.blueprintListEditors
  const blueprintOpenScriptInEditor = api.blueprintOpenScriptInEditor
  const blueprintResidentServices = api.blueprintResidentServices
  const blueprintCreateResidentService = api.blueprintCreateResidentService
  const blueprintOpenResidentServiceInEditor = api.blueprintOpenResidentServiceInEditor
  const blueprintStartResidentService = api.blueprintStartResidentService
  const blueprintStopResidentService = api.blueprintStopResidentService
  const blueprintResidentServiceLogs = api.blueprintResidentServiceLogs
  const blueprintResidentServiceDocs = api.blueprintResidentServiceDocs
  const os = (() => {
    const ua = navigator.userAgent
    if (ua.includes("Mac")) return "macos"
    if (ua.includes("Windows")) return "windows"
    if (ua.includes("Linux")) return "linux"
    return undefined
  })()

  const isWslEnabled = async () => {
    if (os !== "windows") return false
    return window.api
      .getWslConfig()
      .then((config) => config.enabled)
      .catch(() => false)
  }

  const wslHome = async () => {
    if (!(await isWslEnabled())) return undefined
    return window.api.wslPath("~", "windows").catch(() => undefined)
  }

  const handleWslPicker = async <T extends string | string[]>(result: T | null): Promise<T | null> => {
    if (!result || !(await isWslEnabled())) return result
    if (Array.isArray(result)) {
      return Promise.all(result.map((path) => window.api.wslPath(path, "linux").catch(() => path))) as any
    }
    return window.api.wslPath(result, "linux").catch(() => result) as any
  }

  const storage = (() => {
    const cache = new Map<string, AsyncStorage>()

    const createStorage = (name: string) => {
      const api: AsyncStorage = {
        getItem: (key: string) => window.api.storeGet(name, key),
        setItem: (key: string, value: string) => window.api.storeSet(name, key, value),
        removeItem: (key: string) => window.api.storeDelete(name, key),
        clear: () => window.api.storeClear(name),
        key: async (index: number) => (await window.api.storeKeys(name))[index],
        getLength: () => window.api.storeLength(name),
        get length() {
          return api.getLength()
        },
      }
      return api
    }

    return (name = "default.dat") => {
      const cached = cache.get(name)
      if (cached) return cached
      const api = createStorage(name)
      cache.set(name, api)
      return api
    }
  })()

  return {
    platform: "desktop",
    os,
    version: pkg.version,

    async openDirectoryPickerDialog(opts) {
      const defaultPath = opts?.defaultPath ?? (await wslHome())
      const result = await window.api.openDirectoryPicker({
        multiple: opts?.multiple ?? false,
        title: opts?.title ?? t("desktop.dialog.chooseFolder"),
        defaultPath,
      })
      return await handleWslPicker(result)
    },

    async openFilePickerDialog(opts) {
      const result = await window.api.openFilePicker({
        multiple: opts?.multiple ?? false,
        title: opts?.title ?? t("desktop.dialog.chooseFile"),
        defaultPath: opts?.defaultPath,
        accept: opts?.accept ?? ACCEPTED_FILE_TYPES,
        extensions: opts?.extensions ?? ACCEPTED_FILE_EXTENSIONS,
      })
      return handleWslPicker(result)
    },

    async saveFilePickerDialog(opts) {
      const result = await window.api.saveFilePicker({
        title: opts?.title ?? t("desktop.dialog.saveFile"),
        defaultPath: opts?.defaultPath,
      })
      return handleWslPicker(result)
    },

    listBlueprintDirectories: (dir: string) => window.api.blueprintListDirectories(dir),

    listBlueprintSkills: (dir: string) => window.api.blueprintListSkills(dir),

    listBlueprintRules: (dir: string) => window.api.blueprintListRules(dir),

    listBlueprintModels: (cliKind: string) => window.api.blueprintListModels(cliKind),

    detectBlueprintPython: (projectDir?: string, pythonCommand?: string) => window.api.blueprintDetectPython(projectDir, pythonCommand),

    configureBlueprintRuntime: (pythonPath?: string) => window.api.blueprintConfigureRuntime(pythonPath),

    listBlueprints: (projectDir: string) => window.api.blueprintList(projectDir),

    openBlueprint: (projectDir: string, blueprintId: string) => window.api.blueprintOpen(projectDir, blueprintId),

    saveBlueprint: (projectDir: string, document) => window.api.blueprintSave(projectDir, document),

    listBlueprintScriptNodes: (projectDir: string) => window.api.blueprintScriptNodes(projectDir),

    ...(typeof blueprintCreateScriptNode === "function"
      ? {
          createBlueprintScriptNode: (projectDir: string, name: string, description?: string) =>
            blueprintCreateScriptNode(projectDir, name, description),
        }
      : {}),

    ...(typeof blueprintListEditors === "function"
      ? {
          listBlueprintEditors: () => blueprintListEditors(),
        }
      : {}),

    ...(typeof blueprintOpenScriptInEditor === "function"
      ? {
          openBlueprintScriptInEditor: async (projectDir: string, modulePath: string, editorId?: string) => {
            const resolvedProjectDir =
              os === "windows" && (await isWslEnabled())
                ? await window.api.wslPath(projectDir, "windows").catch(() => projectDir)
                : projectDir
            return blueprintOpenScriptInEditor(resolvedProjectDir, modulePath, editorId)
          },
        }
      : {}),

    ...(typeof blueprintResidentServices === "function"
      ? { listBlueprintResidentServices: () => blueprintResidentServices() }
      : {}),

    ...(typeof blueprintCreateResidentService === "function"
      ? { createBlueprintResidentService: (name: string, description?: string) => blueprintCreateResidentService(name, description) }
      : {}),

    ...(typeof blueprintOpenResidentServiceInEditor === "function"
      ? { openBlueprintResidentServiceInEditor: (modulePath: string, editorId?: string) => blueprintOpenResidentServiceInEditor(modulePath, editorId) }
      : {}),

    ...(typeof blueprintStartResidentService === "function"
      ? { startBlueprintResidentService: (serviceName: string) => blueprintStartResidentService(serviceName) }
      : {}),

    ...(typeof blueprintStopResidentService === "function"
      ? { stopBlueprintResidentService: (serviceName: string) => blueprintStopResidentService(serviceName) }
      : {}),

    ...(typeof blueprintResidentServiceLogs === "function"
      ? { blueprintResidentServiceLogs: (serviceName: string, limit?: number) => blueprintResidentServiceLogs(serviceName, limit) }
      : {}),

    ...(typeof blueprintResidentServiceDocs === "function"
      ? { blueprintResidentServiceDocs: (serviceName: string) => blueprintResidentServiceDocs(serviceName) }
      : {}),

    relocateBlueprintProjectWorkdir: (projectDir: string, blueprintId: string, document, targetProjectWorkdir, conflictPolicy) =>
      window.api.blueprintRelocateProjectWorkdir(projectDir, blueprintId, document, targetProjectWorkdir, conflictPolicy),

    validateBlueprint: (projectDir: string, blueprintId: string, document) =>
      window.api.blueprintValidate(projectDir, blueprintId, document),

    listBlueprintRuns: (projectDir?: string, blueprintId?: string) => window.api.blueprintListRuns(projectDir, blueprintId),

    startBlueprintRun: (projectDir: string, blueprintId: string, plan, executionMode) =>
      window.api.blueprintStart(projectDir, blueprintId, plan, executionMode),

    blueprintRunStatus: (runId: string) => window.api.blueprintStatus(runId),

    ...(typeof api.blueprintRunDiff === "function"
      ? { blueprintRunDiff: (runId: string) => api.blueprintRunDiff!(runId) }
      : {}),

    ...(typeof api.blueprintChangesetDiff === "function"
      ? {
          blueprintChangesetDiff: (runId: string, changesetId: string) =>
            api.blueprintChangesetDiff!(runId, changesetId),
        }
      : {}),

    ...(typeof api.blueprintRollbackChangesets === "function"
      ? {
          rollbackBlueprintChangesets: (runId: string, toChangesetId: string, reason?: string) =>
            api.blueprintRollbackChangesets!(runId, toChangesetId, reason),
        }
      : {}),

    ...(typeof api.blueprintRestoreRollback === "function"
      ? {
          restoreBlueprintRollback: (runId: string, rollbackId?: string, reason?: string) =>
            api.blueprintRestoreRollback!(runId, rollbackId, reason),
        }
      : {}),

    endBlueprintRun: (runId, action, reason) => window.api.blueprintEnd(runId, action, reason),

    blueprintRecentEvents: (runId, limit) => window.api.blueprintRecentEvents(runId, limit),

    blueprintAgentInfo: (runId, nodeId) => window.api.blueprintAgentInfo(runId, nodeId),

    queueBlueprintAgentMessage: (runId, nodeId, text, mode) =>
      window.api.blueprintQueueAgentMessage(runId, nodeId, text, mode),

    blueprintAgentStreamToken: (runId, cursor) => window.api.blueprintAgentStreamToken(runId, cursor),

    ensureBlueprintPlanningContext: (projectDir, blueprintId, desktopSessionId) =>
      window.api.blueprintPlanningEnsureContext(projectDir, blueprintId, desktopSessionId),

    answerBlueprintPlanningQuestion: (sessionId, questionId, answers, opts) =>
      window.api.blueprintPlanningAnswerQuestion(sessionId, questionId, answers, opts),

    rejectBlueprintPlanningPlan: (sessionId, reason) => window.api.blueprintPlanningRejectPlan(sessionId, reason),

    markBlueprintPlanningPlanStarted: (sessionId, runId, started) =>
      window.api.blueprintPlanningMarkPlanStarted(sessionId, runId, started),

    blueprintPlanningStatus: (sessionId) => window.api.blueprintPlanningStatus(sessionId),

    endBlueprintPlanningSession: (sessionId, reason) => window.api.blueprintPlanningEndSession(sessionId, reason),

    saveBlueprintAgentPanelTest: (payload) => window.api.blueprintSaveAgentPanelTest(payload),

    openBlueprintWindow: (projectDir, sessionId, rect) => window.api.openBlueprintWindow(projectDir, sessionId, rect),

    dockBlueprintWindow: (projectDir, sessionId) => window.api.dockBlueprintWindow(projectDir, sessionId),

    closeBlueprintWindow: () => window.api.closeBlueprintWindow(),

    submitBlueprintWindowPlanning: (projectDir, sessionId, input) =>
      window.api.submitBlueprintWindowPlanning(projectDir, sessionId, input),

    openLink(url: string) {
      window.api.openLink(url)
    },
    async openPath(path: string, app?: string) {
      if (os === "windows") {
        const resolvedApp = app ? await window.api.resolveAppPath(app).catch(() => null) : null
        const resolvedPath = await (async () => {
          if (await isWslEnabled()) {
            const converted = await window.api.wslPath(path, "windows").catch(() => null)
            if (converted) return converted
          }
          return path
        })()
        return window.api.openPath(resolvedPath, resolvedApp ?? undefined)
      }
      return window.api.openPath(path, app)
    },
    async revealPathInFileManager(path: string) {
      if (os === "windows" && (await isWslEnabled())) {
        const converted = await window.api.wslPath(path, "windows").catch(() => null)
        return window.api.revealPathInFileManager(converted ?? path)
      }
      return window.api.revealPathInFileManager(path)
    },

    back() {
      window.history.back()
    },

    forward() {
      window.history.forward()
    },

    storage,

    checkUpdate: async () => {
      const config = await window.api.getWindowConfig().catch(() => ({ updaterEnabled: false }))
      if (!config.updaterEnabled) return { updateAvailable: false }
      return window.api.checkUpdate()
    },

    update: async () => {
      const config = await window.api.getWindowConfig().catch(() => ({ updaterEnabled: false }))
      if (!config.updaterEnabled) return
      await window.api.installUpdate()
    },

    restart: async () => {
      await window.api.killSidecar().catch(() => undefined)
      window.api.relaunch()
    },

    notify: async (title, description, href) => {
      const focused = await window.api.getWindowFocused().catch(() => document.hasFocus())
      if (focused) return

      const notification = new Notification(title, {
        body: description ?? "",
        icon: "https://opencode.ai/favicon-96x96-v3.png",
      })
      notification.onclick = () => {
        void window.api.showWindow()
        void window.api.setWindowFocus()
        handleNotificationClick(href)
        notification.close()
      }
    },

    fetch: (input, init) => {
      if (input instanceof Request) return fetch(input)
      return fetch(input, init)
    },

    getWslEnabled: () => isWslEnabled(),

    setWslEnabled: async (enabled) => {
      await window.api.setWslConfig({ enabled })
    },

    getDefaultServer: async () => {
      const url = await window.api.getDefaultServerUrl().catch(() => null)
      if (!url) return null
      return ServerConnection.Key.make(url)
    },

    setDefaultServer: async (url: string | null) => {
      await window.api.setDefaultServerUrl(url)
    },

    getDisplayBackend: async () => {
      return window.api.getDisplayBackend().catch(() => null)
    },

    setDisplayBackend: async (backend) => {
      await window.api.setDisplayBackend(backend)
    },

    parseMarkdown: (markdown: string) => window.api.parseMarkdownCommand(markdown),

    webviewZoom,

    checkAppExists: async (appName: string) => {
      return window.api.checkAppExists(appName)
    },

    async readClipboardImage() {
      const image = await window.api.readClipboardImage().catch(() => null)
      if (!image) return null
      const blob = new Blob([image.buffer], { type: "image/png" })
      return new File([blob], `pasted-image-${Date.now()}.png`, {
        type: "image/png",
      })
    },
  }
}

let menuTrigger = null as null | ((id: string) => void)
window.api.onMenuCommand((id) => {
  menuTrigger?.(id)
})
listenForDeepLinks()
window.api.onBlueprintWindowDock((context) => {
  window.dispatchEvent(new CustomEvent(blueprintWindowDockEvent, { detail: context }))
})
window.api.onBlueprintWindowClosed((context) => {
  window.dispatchEvent(new CustomEvent(blueprintWindowClosedEvent, { detail: context }))
})
window.api.onBlueprintWindowPlanningSubmitRequest((request) => {
  let responded = false
  const respond = (accepted: boolean) => {
    if (responded) return
    responded = true
    void window.api.respondBlueprintWindowPlanningSubmit(request.requestId, accepted)
  }
  window.dispatchEvent(new CustomEvent(blueprintWindowPlanningSubmitEvent, { detail: { ...request, respond } }))
  queueMicrotask(() => {
    if (!responded) respond(false)
  })
})
window.api.onDesktopControlBridgeCommand((request) => {
  let responded = false
  const respond = (response: { ok?: boolean; accepted?: boolean; result?: unknown; code?: string; message?: string }) => {
    if (responded) return
    responded = true
    void window.api.respondDesktopControlBridgeCommand(request.requestId, response)
  }
  window.dispatchEvent(new CustomEvent(desktopControlBridgeCommandEvent, { detail: { ...request, respond } }))
  window.setTimeout(() => {
    if (!responded) respond({ ok: true, accepted: false, code: "DESKTOP_COMMAND_UNHANDLED", message: "command was not handled" })
  }, 4500)
})

render(() => {
  const platform = createPlatform()
  const [windowConfig] = createResource(() => window.api.getWindowConfig().catch(() => ({ updaterEnabled: false })))
  const [blueprintWindowContext] = createResource(() => window.api.getBlueprintWindowContext().catch(() => null))
  const loadLocale = async () => {
    const current = await platform.storage?.("opencode.global.dat").getItem("language")
    const legacy = current ? undefined : await platform.storage?.().getItem("language.v1")
    const raw = current ?? legacy
    if (!raw) return
    const locale = raw.match(/"locale"\s*:\s*"([^"]+)"/)?.[1]
    if (!locale) return
    const next = normalizeLocale(locale)
    if (next !== "en") await loadLocaleDict(next)
    return next satisfies Locale
  }

  const [windowCount] = createResource(() => window.api.getWindowCount())

  // Fetch sidecar credentials (available immediately, before health check)
  const [sidecar] = createResource(() => window.api.awaitInitialization(() => undefined))

  const [defaultServer] = createResource(() =>
    platform.getDefaultServer?.().then((url) => {
      if (url) return ServerConnection.key({ type: "http", http: { url } })
    }),
  )
  const [locale] = createResource(loadLocale)

  const servers = () => {
    const data = sidecar()
    if (!data) return []
    const server: ServerConnection.Sidecar = {
      displayName: "Local Server",
      type: "sidecar",
      variant: "base",
      http: {
        url: data.url,
        username: data.username ?? undefined,
        password: data.password ?? undefined,
      },
    }
    return [server] as ServerConnection.Any[]
  }

  function handleClick(e: MouseEvent) {
    const link = (e.target as HTMLElement).closest("a.external-link") as HTMLAnchorElement | null
    if (link?.href) {
      e.preventDefault()
      platform.openLink(link.href)
    }
  }

  function Inner() {
    const cmd = useCommand()
    menuTrigger = (id) => cmd.trigger(id)

    const theme = useTheme()

    createEffect(() => {
      theme.themeId()
      theme.mode()
      const bg = getComputedStyle(document.documentElement).getPropertyValue("--background-base").trim()
      if (bg) {
        void window.api.setBackgroundColor(bg)
      }
    })

    return null
  }

  onMount(() => {
    document.addEventListener("click", handleClick)
    onCleanup(() => {
      document.removeEventListener("click", handleClick)
    })
  })

  return (
    <PlatformProvider value={platform}>
      <AppBaseProviders locale={locale.latest}>
        <Show
          when={
            !defaultServer.loading &&
            !sidecar.loading &&
            !windowConfig.loading &&
            !windowCount.loading &&
            !blueprintWindowContext.loading &&
            !locale.loading
          }
        >
          {(_) => {
            const context = blueprintWindowContext.latest
            const history = createMemoryHistory()
            if (context) {
              const session = context.sessionId ? `/${context.sessionId}` : ""
              history.set({
                value: `/${base64Encode(context.projectDir)}/blueprint-window${session}`,
                replace: true,
                scroll: false,
              })
            }
            const Router = (props: BaseRouterProps) => <MemoryRouter {...props} history={history} />
            return (
              <AppInterface
                defaultServer={defaultServer.latest ?? ServerConnection.Key.make("sidecar")}
                servers={servers()}
                router={Router}
                visualShell={!context}
              >
                <Inner />
              </AppInterface>
            )
          }}
        </Show>
      </AppBaseProviders>
    </PlatformProvider>
  )
}, root!)
