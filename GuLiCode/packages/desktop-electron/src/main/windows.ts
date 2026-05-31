import windowState from "electron-window-state"
import { app, BrowserWindow, net, nativeImage, nativeTheme, protocol, screen } from "electron"
import { dirname, isAbsolute, join, relative, resolve } from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import log from "electron-log/main.js"
import type { BlueprintWindowContext, BlueprintWindowRect, TitlebarTheme } from "../preload/types"

const root = dirname(fileURLToPath(import.meta.url))
const rendererRoot = join(root, "../renderer")
const rendererProtocol = "oc"
const rendererHost = "renderer"

protocol.registerSchemesAsPrivileged([
  {
    scheme: rendererProtocol,
    privileges: {
      secure: true,
      standard: true,
      supportFetchAPI: true,
    },
  },
])

let backgroundColor: string | undefined
const blueprintWindowContexts = new Map<number, BlueprintWindowContext>()
const blueprintWindowDocking = new Set<number>()

type ManagedWindowState = ReturnType<typeof windowState>

export function setBackgroundColor(color: string) {
  backgroundColor = color
}

export function getBackgroundColor(): string | undefined {
  return backgroundColor
}

function overlapSize(startA: number, sizeA: number, startB: number, sizeB: number) {
  const endA = startA + sizeA
  const endB = startB + sizeB
  return Math.max(0, Math.min(endA, endB) - Math.max(startA, startB))
}

function clampNumber(value: number, min: number, max: number) {
  if (max < min) return min
  return Math.min(Math.max(value, min), max)
}

function isWindowStateVisible(state: ManagedWindowState) {
  if (typeof state.x !== "number" || typeof state.y !== "number") return true

  return screen.getAllDisplays().some((display) => {
    const visibleWidth = overlapSize(state.x, state.width, display.workArea.x, display.workArea.width)
    const visibleHeight = overlapSize(state.y, state.height, display.workArea.y, display.workArea.height)
    return visibleWidth >= 120 && visibleHeight >= 120
  })
}

function ensureWindowStateVisible(state: ManagedWindowState) {
  if (isWindowStateVisible(state)) {
    return
  }

  const workArea = screen.getPrimaryDisplay().workArea
  state.width = Math.min(state.width, workArea.width)
  state.height = Math.min(state.height, workArea.height)
  state.x = Math.round(workArea.x + (workArea.width - state.width) / 2)
  state.y = Math.round(workArea.y + (workArea.height - state.height) / 2)
}

function iconsDir() {
  return app.isPackaged ? join(process.resourcesPath, "icons") : join(root, "../../resources/icons")
}

function iconPath() {
  const ext = process.platform === "win32" ? "ico" : "png"
  return join(iconsDir(), `icon.${ext}`)
}

function readWindowIcon() {
  const path = iconPath()
  const icon = nativeImage.createFromPath(path)
  if (icon.isEmpty()) {
    log.warn("window icon asset unavailable", {
      path,
      packaged: app.isPackaged,
    })
    return null
  }
  return icon
}

function applyWindowsTaskbarDetails(win: BrowserWindow, appId?: string) {
  if (process.platform !== "win32") return
  const iconPathValue = iconPath()
  const icon = readWindowIcon()

  if (icon) {
    try {
      win.setIcon(icon)
    } catch (error) {
      log.warn("failed to set window icon", {
        path: iconPathValue,
        error: error instanceof Error ? error.message : String(error),
      })
    }
  }

  if (!appId) return

  try {
    win.setAppDetails(
      icon
        ? {
            appId,
            appIconPath: iconPathValue,
            appIconIndex: 0,
          }
        : {
            appId,
          },
    )
  } catch (error) {
    log.warn("failed to set app details", {
      appId,
      path: iconPathValue,
      error: error instanceof Error ? error.message : String(error),
    })
  }
}

function tone() {
  return nativeTheme.shouldUseDarkColors ? "dark" : "light"
}

function overlay(theme: Partial<TitlebarTheme> = {}) {
  const mode = theme.mode ?? tone()
  return {
    color: "#00000000",
    symbolColor: mode === "dark" ? "white" : "black",
    height: 40,
  }
}

export function setTitlebar(win: BrowserWindow, theme: Partial<TitlebarTheme> = {}) {
  if (process.platform !== "win32") return
  if (getBlueprintWindowContext(win)) return
  try {
    win.setTitleBarOverlay(overlay(theme))
  } catch (error) {
    log.warn("failed to set titlebar overlay", {
      windowId: win.id,
      error: error instanceof Error ? error.message : String(error),
    })
  }
}

export function setDockIcon() {
  if (process.platform !== "darwin") return
  const icon = nativeImage.createFromPath(join(iconsDir(), "dock.png"))
  if (!icon.isEmpty()) app.dock?.setIcon(icon)
}

export function createMainWindow(appId?: string) {
  const state = windowState({
    defaultWidth: 1280,
    defaultHeight: 800,
  })
  ensureWindowStateVisible(state)

  const mode = tone()
  const windowIcon = readWindowIcon() ?? undefined
  const win = new BrowserWindow({
    x: state.x,
    y: state.y,
    width: state.width,
    height: state.height,
    show: false,
    title: "GuLiCode",
    icon: windowIcon,
    backgroundColor,
    ...(process.platform === "darwin"
      ? {
          titleBarStyle: "hidden" as const,
          trafficLightPosition: { x: 12, y: 14 },
        }
      : {}),
    ...(process.platform === "win32"
      ? {
          frame: false,
          titleBarStyle: "hidden" as const,
          titleBarOverlay: overlay({ mode }),
        }
      : {}),
    webPreferences: {
      preload: join(root, "../preload/index.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  applyWindowsTaskbarDetails(win, appId)

  wireRendererRequestHeaders(win)
  win.webContents.on("did-fail-load", (_event, code, description, validatedURL, isMainFrame) => {
    log.error("main window webContents: did-fail-load", {
      code,
      description,
      validatedURL,
      isMainFrame,
    })
  })
  win.webContents.on("render-process-gone", (_event, details) => {
    log.error("main window webContents: render-process-gone", details)
  })

  state.manage(win)
  loadWindow(win, "index.html")
  wireZoom(win)

  win.once("ready-to-show", () => {
    win.show()
  })
  globalThis.setTimeout(() => {
    if (win.isDestroyed() || win.isVisible()) return
    log.warn("main window fallback show after timeout")
    win.show()
  }, 3000)

  return win
}

export function openBlueprintWindow(
  context: BlueprintWindowContext,
  opts: { appId?: string; sourceWindow?: BrowserWindow | null } = {},
) {
  const existing = findBlueprintWindow(context)
  if (existing) {
    existing.show()
    existing.focus()
    return existing
  }

  const rect = clampBlueprintWindowRect(toScreenRect(context.rect, opts.sourceWindow))
  const windowIcon = readWindowIcon() ?? undefined
  const win = new BrowserWindow({
    x: rect.x,
    y: rect.y,
    width: rect.width,
    height: rect.height,
    minWidth: 640,
    minHeight: 420,
    show: false,
    title: "GuLiCode Blueprint",
    icon: windowIcon,
    backgroundColor,
    webPreferences: {
      preload: join(root, "../preload/index.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  blueprintWindowContexts.set(win.id, {
    projectDir: context.projectDir,
    sessionId: context.sessionId,
  })
  applyWindowsTaskbarDetails(win, opts.appId)
  wireRendererRequestHeaders(win)
  wireBlueprintWindowDiagnostics(win)
  loadWindow(win, "index.html")
  wireZoom(win)

  win.once("ready-to-show", () => {
    win.show()
    win.focus()
  })
  win.on("closed", () => {
    const closedContext = blueprintWindowContexts.get(win.id)
    blueprintWindowContexts.delete(win.id)
    if (!closedContext || blueprintWindowDocking.delete(win.id)) return
    sendToMainWindow("blueprint-window-closed", closedContext)
  })
  globalThis.setTimeout(() => {
    if (win.isDestroyed() || win.isVisible()) return
    log.warn("blueprint window fallback show after timeout")
    win.show()
  }, 3000)

  return win
}

export function getBlueprintWindowContext(win: BrowserWindow | null | undefined) {
  if (!win) return null
  return blueprintWindowContexts.get(win.id) ?? null
}

export function findBlueprintMainWindow() {
  return BrowserWindow.getAllWindows().find((win) => !win.isDestroyed() && !getBlueprintWindowContext(win)) ?? null
}

export function dockBlueprintWindow(win: BrowserWindow | null | undefined, fallbackContext?: BlueprintWindowContext) {
  const context = getBlueprintWindowContext(win) ?? fallbackContext
  if (!context) return false
  sendToMainWindow("blueprint-window-dock-request", context)
  const target = findBlueprintMainWindow()
  if (target) {
    target.show()
    target.focus()
  }
  if (win && !win.isDestroyed()) {
    blueprintWindowDocking.add(win.id)
    win.close()
  }
  return true
}

export function closeBlueprintWindow(win: BrowserWindow | null | undefined) {
  if (!win || win.isDestroyed()) return false
  if (!getBlueprintWindowContext(win)) return false
  win.close()
  return true
}

export function createLoadingWindow(appId?: string) {
  const mode = tone()
  const windowIcon = readWindowIcon() ?? undefined
  const win = new BrowserWindow({
    width: 640,
    height: 480,
    resizable: false,
    center: true,
    show: true,
    icon: windowIcon,
    backgroundColor,
    ...(process.platform === "darwin" ? { titleBarStyle: "hidden" as const } : {}),
    ...(process.platform === "win32"
      ? {
          frame: false,
          titleBarStyle: "hidden" as const,
          titleBarOverlay: overlay({ mode }),
        }
      : {}),
    webPreferences: {
      preload: join(root, "../preload/index.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  applyWindowsTaskbarDetails(win, appId)

  loadWindow(win, "loading.html")

  return win
}

function findBlueprintWindow(context: BlueprintWindowContext) {
  return BrowserWindow.getAllWindows().find((win) => {
    const current = getBlueprintWindowContext(win)
    return (
      !win.isDestroyed() &&
      current?.projectDir === context.projectDir &&
      (current.sessionId ?? "") === (context.sessionId ?? "")
    )
  })
}

function sendToMainWindow(channel: string, context: BlueprintWindowContext) {
  const target = findBlueprintMainWindow()
  if (!target || target.isDestroyed()) return false
  target.webContents.send(channel, context)
  return true
}

function wireRendererRequestHeaders(win: BrowserWindow) {
  win.webContents.session.webRequest.onBeforeSendHeaders((details, callback) => {
    const { requestHeaders } = details
    upsertKeyValue(requestHeaders, "Access-Control-Allow-Origin", ["*"])
    callback({ requestHeaders })
  })

  win.webContents.session.webRequest.onHeadersReceived((details, callback) => {
    const { responseHeaders = {} } = details
    upsertKeyValue(responseHeaders, "Access-Control-Allow-Origin", ["*"])
    upsertKeyValue(responseHeaders, "Access-Control-Allow-Headers", ["*"])
    callback({ responseHeaders })
  })
}

function wireBlueprintWindowDiagnostics(win: BrowserWindow) {
  win.webContents.on("did-fail-load", (_event, code, description, validatedURL, isMainFrame) => {
    log.error("blueprint window webContents: did-fail-load", {
      code,
      description,
      validatedURL,
      isMainFrame,
    })
  })
  win.webContents.on("render-process-gone", (_event, details) => {
    log.error("blueprint window webContents: render-process-gone", details)
  })
}

function toScreenRect(rect: BlueprintWindowRect | undefined, sourceWindow?: BrowserWindow | null): BlueprintWindowRect | undefined {
  if (!rect) return undefined
  if (!sourceWindow || sourceWindow.isDestroyed()) return rect
  const bounds = sourceWindow.getBounds()
  return {
    ...rect,
    x: bounds.x + rect.x,
    y: bounds.y + rect.y,
  }
}

function clampBlueprintWindowRect(rect?: BlueprintWindowRect): BlueprintWindowRect {
  const width = clampNumber(rect?.width ?? 980, 640, Math.max(640, screen.getPrimaryDisplay().workArea.width))
  const height = clampNumber(rect?.height ?? 680, 420, Math.max(420, screen.getPrimaryDisplay().workArea.height))
  const point = {
    x: rect?.x ?? screen.getPrimaryDisplay().workArea.x + Math.round((screen.getPrimaryDisplay().workArea.width - width) / 2),
    y: rect?.y ?? screen.getPrimaryDisplay().workArea.y + Math.round((screen.getPrimaryDisplay().workArea.height - height) / 2),
  }
  const workArea = screen.getDisplayNearestPoint(point).workArea
  return {
    width: Math.min(width, workArea.width),
    height: Math.min(height, workArea.height),
    x: clampNumber(point.x, workArea.x, workArea.x + workArea.width - width),
    y: clampNumber(point.y, workArea.y, workArea.y + workArea.height - height),
  }
}

export function registerRendererProtocol() {
  if (protocol.isProtocolHandled(rendererProtocol)) return

  protocol.handle(rendererProtocol, (request) => {
    const url = new URL(request.url)
    if (url.host !== rendererHost) {
      return new Response("Not found", { status: 404 })
    }

    const file = resolve(rendererRoot, `.${decodeURIComponent(url.pathname)}`)
    const rel = relative(rendererRoot, file)
    if (rel.startsWith("..") || isAbsolute(rel)) {
      return new Response("Not found", { status: 404 })
    }

    return net.fetch(pathToFileURL(file).toString())
  })
}

function loadWindow(win: BrowserWindow, html: string) {
  const devUrl = normalizedDevRendererUrl(process.env.ELECTRON_RENDERER_URL)
  if (devUrl) {
    const url = new URL(html, devUrl)
    void win.loadURL(url.toString())
    return
  }

  void win.loadURL(`${rendererProtocol}://${rendererHost}/${html}`)
}

function normalizedDevRendererUrl(value: string | undefined) {
  if (!value) return
  const url = new URL(value)
  return url.toString()
}

function wireZoom(win: BrowserWindow) {
  win.webContents.setZoomFactor(1)
  win.webContents.on("zoom-changed", () => {
    win.webContents.setZoomFactor(1)
  })
}

function upsertKeyValue(obj: Record<string, any>, keyToChange: string, value: any) {
  const keyToChangeLower = keyToChange.toLowerCase()
  for (const key of Object.keys(obj)) {
    if (key.toLowerCase() === keyToChangeLower) {
      // Reassign old key
      obj[key] = value
      // Done
      return
    }
  }
  // Insert at end instead
  obj[keyToChange] = value
}
