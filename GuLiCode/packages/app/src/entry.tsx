// @refresh reload

import { render } from "solid-js/web"
import { AppBaseProviders, AppInterface } from "@/app"
import { CollaborationAuthGate } from "@/components/collaboration-auth"
import { type Platform, PlatformProvider } from "@/context/platform"
import { dict as en } from "@/i18n/en"
import { dict as zh } from "@/i18n/zh"
import { MobileApp } from "@/mobile/mobile-app"
import { registerPwa } from "@/pwa"
import { ServerConsoleApp } from "@/server-console/server-console-app"
import { base64Encode } from "@opencode-ai/shared/util/encode"
import { handleNotificationClick } from "@/utils/notification-click"
import pkg from "../package.json"
import { ServerConnection } from "./context/server"

const DEFAULT_SERVER_URL_KEY = "opencode.settings.dat:defaultServerUrl"

type BlueprintWorkbenchConfig = {
  token?: string
  projectDir?: string
  blueprintId?: string
  apiBase?: string
  planningThreadId?: string
}

declare global {
  interface Window {
    __GULICODE_BP__?: BlueprintWorkbenchConfig
  }
}

const getLocale = () => {
  if (typeof navigator !== "object") return "en" as const
  const languages = navigator.languages?.length ? navigator.languages : [navigator.language]
  for (const language of languages) {
    if (!language) continue
    if (language.toLowerCase().startsWith("zh")) return "zh" as const
  }
  return "en" as const
}

const getRootNotFoundError = () => {
  const key = "error.dev.rootNotFound" as const
  const locale = getLocale()
  return locale === "zh" ? (zh[key] ?? en[key]) : en[key]
}

const getStorage = (key: string) => {
  if (typeof localStorage === "undefined") return null
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

const setStorage = (key: string, value: string | null) => {
  if (typeof localStorage === "undefined") return
  try {
    if (value !== null) {
      localStorage.setItem(key, value)
      return
    }
    localStorage.removeItem(key)
  } catch {
    return
  }
}

const readDefaultServerUrl = () => getStorage(DEFAULT_SERVER_URL_KEY)
const writeDefaultServerUrl = (url: string | null) => setStorage(DEFAULT_SERVER_URL_KEY, url)

const blueprintWorkbenchConfig = () => {
  const config = window.__GULICODE_BP__
  if (!config?.token) return
  return config
}

const isBlueprintWorkbenchLikeRoute = () =>
  location.pathname.includes("/blueprint-window/") ||
  location.pathname === "/mobile" ||
  location.pathname.startsWith("/mobile/") ||
  location.pathname === "/console" ||
  location.pathname.startsWith("/console/")

const loadBlueprintWorkbenchConfigScript = async () => {
  if (blueprintWorkbenchConfig() || !isBlueprintWorkbenchLikeRoute()) return
  await new Promise<void>((resolve) => {
    const script = document.createElement("script")
    script.src = `/config.js?t=${Date.now()}`
    script.async = false
    script.onload = () => resolve()
    script.onerror = () => resolve()
    document.head.appendChild(script)
  })
}

const unregisterBlueprintWorkbenchPwa = () => {
  if (!isBlueprintWorkbenchLikeRoute()) return
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return
  void navigator.serviceWorker.getRegistrations().then((registrations) => {
    for (const registration of registrations) {
      void registration.unregister()
    }
  })
}

const blueprintApiBase = (config: BlueprintWorkbenchConfig) => (config.apiBase || location.origin).replace(/\/+$/, "")

const blueprintRequest = async (config: BlueprintWorkbenchConfig, command: string, args: Record<string, unknown> = {}) => {
  const response = await fetch(`${blueprintApiBase(config)}/api/blueprint`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      token: config.token,
      command,
      args,
    }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || payload?.ok === false) {
    throw new Error(payload?.error || payload?.code || `Blueprint request failed: ${command}`)
  }
  return payload
}

const blueprintRecord = (value: unknown) =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined

const blueprintString = (value: unknown) => (typeof value === "string" && value.trim() ? value.trim() : undefined)

type BlueprintPickerPaths = Awaited<ReturnType<NonNullable<Platform["openDirectoryPickerDialog"]>>>

const withBlueprintWorkbenchPlatform = (base: Platform, config: BlueprintWorkbenchConfig): Platform => ({
  ...base,
  platform: "desktop",
  os: "windows",
  listBlueprints: async (projectDir: string) =>
    (await blueprintRequest(config, "blueprint.list", { projectDir })).blueprints ?? [],
  openBlueprint: async (projectDir: string, blueprintId: string) =>
    (await blueprintRequest(config, "blueprint.open", { projectDir, blueprintId })).document,
  createBlueprint: async (projectDir: string, blueprintId?: string, name?: string) =>
    (await blueprintRequest(config, "blueprint.create", { projectDir, blueprintId, name })).document,
  deleteBlueprint: async (projectDir: string, blueprintId: string) =>
    blueprintRequest(config, "blueprint.delete", { projectDir, blueprintId }),
  saveBlueprint: async (projectDir: string, document) =>
    (await blueprintRequest(config, "blueprint.save", { projectDir, document })).document,
  detectBlueprintPython: async (projectDir?: string, pythonCommand?: string) =>
    blueprintRequest(config, "blueprint.detectPython", { projectDir, pythonCommand }),
  listBlueprintScriptNodes: async (projectDir: string) =>
    blueprintRequest(config, "blueprint.scriptNodes", { projectDir }),
  createBlueprintScriptNode: async (projectDir: string, name: string, description?: string) =>
    blueprintRequest(config, "blueprint.createScriptNode", { projectDir, name, description }),
  listBlueprintEditors: async () => (await blueprintRequest(config, "blueprint.listEditors")).editors ?? [],
  openBlueprintScriptInEditor: async (projectDir: string, modulePath: string, editorId?: string) =>
    blueprintRequest(config, "blueprint.openScriptInEditor", { projectDir, modulePath, editorId }),
  openDirectoryPickerDialog: async (opts) => {
    const payload = await blueprintRequest(config, "blueprint.pickDirectory", {
      title: opts?.title,
      multiple: opts?.multiple,
      defaultPath: opts?.defaultPath,
    })
    return (payload.path ?? null) as BlueprintPickerPaths
  },
  openFilePickerDialog: async (opts) => {
    const payload = await blueprintRequest(config, "blueprint.pickFile", {
      title: opts?.title,
      multiple: opts?.multiple,
      defaultPath: opts?.defaultPath,
      accept: opts?.accept,
      extensions: opts?.extensions,
    })
    return (payload.path ?? null) as BlueprintPickerPaths
  },
  relocateBlueprintProjectWorkdir: async (projectDir, blueprintId, document, projectWorkdir, conflictPolicy) =>
    blueprintRequest(config, "blueprint.relocateProjectWorkdir", {
      projectDir,
      blueprintId,
      document,
      projectWorkdir,
      conflictPolicy,
    }),
  validateBlueprint: async (projectDir: string, blueprintId: string, document) =>
    blueprintRequest(config, "blueprint.validate", { projectDir, blueprintId, document }),
  createBlueprintStartPlan: async (projectDir: string, blueprintId: string, input) =>
    blueprintRequest(config, "blueprint.plan.create", {
      projectDir,
      blueprintId,
      task: input.task,
      startNodeIds: input.startNodeIds,
      planOverrides: input.planOverrides,
    }),
  validateBlueprintStartPlan: async (projectDir: string, blueprintId: string, plan) =>
    blueprintRequest(config, "blueprint.plan.validate", { projectDir, blueprintId, plan }),
  listBlueprintRuns: async (projectDir?: string, blueprintId?: string) =>
    (await blueprintRequest(config, "blueprint.listRuns", { projectDir, blueprintId })).runs ?? [],
  startBlueprintRun: async (projectDir: string, blueprintId: string, plan, executionMode) =>
    blueprintRequest(config, "blueprint.start", { projectDir, blueprintId, plan, executionMode }),
  blueprintRunStatus: async (runId: string) => blueprintRequest(config, "blueprint.status", { runId }),
  blueprintRunDiff: async (runId: string) => blueprintRequest(config, "blueprint.runDiff", { runId }),
  blueprintChangesetDiff: async (runId: string, changesetId: string) =>
    blueprintRequest(config, "blueprint.changesetDiff", { runId, changesetId }),
  rollbackBlueprintChangesets: async (runId: string, toChangesetId: string, reason?: string) =>
    blueprintRequest(config, "blueprint.rollbackChangesets", { runId, toChangesetId, reason }),
  restoreBlueprintRollback: async (runId: string, rollbackId?: string, reason?: string) =>
    blueprintRequest(config, "blueprint.restoreRollback", { runId, rollbackId, reason }),
  endBlueprintRun: async (runId, action, reason) => blueprintRequest(config, "blueprint.end", { runId, action, reason }),
  blueprintRecentEvents: async (runId, limit) => blueprintRequest(config, "blueprint.recentEvents", { runId, limit }),
  blueprintAgentInfo: async (runId, nodeId) => blueprintRequest(config, "blueprint.agentInfo", { runId, nodeId }),
  queueBlueprintAgentMessage: async (runId, nodeId, text, mode) =>
    blueprintRequest(config, "blueprint.queueAgentMessage", { runId, nodeId, text, mode }),
  blueprintAgentStreamToken: async (runId, cursor) =>
    blueprintRequest(config, "blueprint.agentStreamToken", {
      runId,
      cursor,
      baseUrl: blueprintApiBase(config),
    }),
  openBlueprintWindow: async () => undefined,
  dockBlueprintWindow: async () => undefined,
  closeBlueprintWindow: async () => undefined,
  ...(config.planningThreadId
    ? ({
        submitBlueprintWindowPlanning: async (projectDir, sessionId, input) => {
          const payload = await blueprintRequest(config, "blueprint.planning.submit", {
            projectDir,
            sessionId,
            threadId: config.planningThreadId,
            task: input.task,
            blueprintId: input.blueprintId,
            blueprintName: input.blueprintName,
            startNodeIds: input.startNodeIds,
            message: input.message,
            silentBlocked: input.silentBlocked,
          })
          const request = blueprintRecord(payload.request) ?? payload
          return {
            accepted: payload.accepted !== false,
            requestId: blueprintString(request.requestId) ?? blueprintString(payload.requestId),
            status: blueprintString(request.status) ?? blueprintString(payload.status),
            message: blueprintString(request.message) ?? blueprintString(payload.message),
          }
        },
        blueprintWindowPlanningStatus: async (requestId: string) =>
          blueprintRequest(config, "blueprint.planning.status", { requestId }),
        cancelBlueprintWindowPlanning: async (requestId: string, reason?: string) =>
          blueprintRequest(config, "blueprint.planning.cancel", { requestId, reason }),
      } satisfies Pick<
        Platform,
        "submitBlueprintWindowPlanning" | "blueprintWindowPlanningStatus" | "cancelBlueprintWindowPlanning"
      >)
    : {}),
})

const ensureBlueprintWorkbenchRoute = (config: BlueprintWorkbenchConfig) => {
  const projectDir = config.projectDir?.trim() || "global"
  const session = config.blueprintId?.trim() || "codex"
  const route = `/${base64Encode(projectDir)}/blueprint-window/${session}`
  if (location.pathname === "/" || location.pathname === "/index.html") {
    history.replaceState(null, "", `${route}${location.search}${location.hash}`)
  }
}

const notify: Platform["notify"] = async (title, description, href) => {
  if (!("Notification" in window)) return

  const permission =
    Notification.permission === "default"
      ? await Notification.requestPermission().catch(() => "denied")
      : Notification.permission

  if (permission !== "granted") return

  const inView = document.visibilityState === "visible" && document.hasFocus()
  if (inView) return

  const notification = new Notification(title, {
    body: description ?? "",
    icon: "https://opencode.ai/favicon-96x96-v3.png",
  })

  notification.onclick = () => {
    handleNotificationClick(href)
    notification.close()
  }
}

const openLink: Platform["openLink"] = (url) => {
  window.open(url, "_blank")
}

const back: Platform["back"] = () => {
  window.history.back()
}

const forward: Platform["forward"] = () => {
  window.history.forward()
}

const restart: Platform["restart"] = async () => {
  window.location.reload()
}

const root = document.getElementById("root")
if (!(root instanceof HTMLElement) && import.meta.env.DEV) {
  throw new Error(getRootNotFoundError())
}

const getCurrentUrl = () => {
  if (location.hostname.includes("opencode.ai")) return "http://localhost:4096"
  if (import.meta.env.DEV)
    return `http://${import.meta.env.VITE_OPENCODE_SERVER_HOST ?? "localhost"}:${import.meta.env.VITE_OPENCODE_SERVER_PORT ?? "4096"}`
  return location.origin
}

const getDefaultUrl = () => {
  const lsDefault = readDefaultServerUrl()
  if (lsDefault) return lsDefault
  return getCurrentUrl()
}

const platform: Platform = {
  platform: "web",
  version: pkg.version,
  openLink,
  back,
  forward,
  restart,
  notify,
  getDefaultServer: async () => {
    const stored = readDefaultServerUrl()
    return stored ? ServerConnection.Key.make(stored) : null
  },
  setDefaultServer: writeDefaultServerUrl,
}

const bootstrap = async (rootElement: HTMLElement) => {
  await loadBlueprintWorkbenchConfigScript()
  const blueprintConfig = blueprintWorkbenchConfig()
  if (blueprintConfig || isBlueprintWorkbenchLikeRoute()) {
    unregisterBlueprintWorkbenchPwa()
  } else {
    registerPwa()
  }
  if (blueprintConfig) ensureBlueprintWorkbenchRoute(blueprintConfig)
  const activePlatform = blueprintConfig ? withBlueprintWorkbenchPlatform(platform, blueprintConfig) : platform

  if (location.pathname === "/console" || location.pathname.startsWith("/console/")) {
    render(
      () => (
        <PlatformProvider value={activePlatform}>
          <AppBaseProviders>
            <ServerConsoleApp />
          </AppBaseProviders>
        </PlatformProvider>
      ),
      rootElement,
    )
  } else if (location.pathname === "/mobile" || location.pathname.startsWith("/mobile/")) {
    render(
      () => (
        <PlatformProvider value={activePlatform}>
          <AppBaseProviders>
            <CollaborationAuthGate clientKind="mobile" defaultUsername="1">
              <MobileApp />
            </CollaborationAuthGate>
          </AppBaseProviders>
        </PlatformProvider>
      ),
      rootElement,
    )
  } else {
    const server: ServerConnection.Http = { type: "http", http: { url: getCurrentUrl() } }
    render(
      () => (
        <PlatformProvider value={activePlatform}>
          <AppBaseProviders>
            <AppInterface
              defaultServer={ServerConnection.Key.make(getDefaultUrl())}
              servers={[server]}
              disableHealthCheck
              disableServerSync={!!blueprintConfig}
              visualShell={!blueprintConfig}
            />
          </AppBaseProviders>
        </PlatformProvider>
      ),
      rootElement,
    )
  }
}

if (root instanceof HTMLElement) {
  void bootstrap(root)
}
