import { randomBytes, randomUUID } from "node:crypto"
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http"
import type { AddressInfo } from "node:net"
import type { BrowserWindow } from "electron"
import log from "electron-log/main.js"

const MAX_BODY_BYTES = 1024 * 1024
const COMMAND_TIMEOUT_MS = 5000
const ALLOWED_COMMANDS = new Set(["desktop.mobilePlanning.submit", "desktop.session.submit", "desktop.session.delete"])

export type DesktopControlBridgeInfo = {
  bridgeUrl: string
  bridgeToken: string
}

export type DesktopControlBridgeCommandRequest = {
  requestId: string
  command: string
  args: Record<string, unknown>
}

export type DesktopControlBridgeCommandResponse = {
  ok?: boolean
  accepted?: boolean
  result?: unknown
  code?: string
  message?: string
}

export class DesktopControlBridge {
  private server: Server | undefined
  private token = randomBytes(32).toString("hex")
  private url: string | undefined
  private pending = new Map<string, (response: DesktopControlBridgeCommandResponse) => void>()

  constructor(private readonly getMainWindow: () => BrowserWindow | null) {}

  async start() {
    if (this.server && this.url) return this.info()
    this.server = createServer((request, response) => {
      void this.handle(request, response)
    })
    await new Promise<void>((resolve, reject) => {
      this.server?.once("error", reject)
      this.server?.listen(0, "127.0.0.1", () => resolve())
    })
    const address = this.server.address()
    if (!address || typeof address !== "object") {
      throw new Error("desktop control bridge failed to bind")
    }
    this.url = `http://127.0.0.1:${(address as AddressInfo).port}/desktop-control`
    log.info("desktop control bridge listening", { url: this.url })
    return this.info()
  }

  info(): DesktopControlBridgeInfo {
    if (!this.url) throw new Error("desktop control bridge is not started")
    return {
      bridgeUrl: this.url,
      bridgeToken: this.token,
    }
  }

  stop() {
    for (const resolve of this.pending.values()) {
      resolve({ ok: false, accepted: false, code: "DESKTOP_BRIDGE_STOPPED", message: "desktop bridge stopped" })
    }
    this.pending.clear()
    this.server?.close()
    this.server = undefined
    this.url = undefined
  }

  respond(requestId: string, response: DesktopControlBridgeCommandResponse) {
    const resolve = this.pending.get(requestId)
    if (!resolve) return
    this.pending.delete(requestId)
    resolve(response)
  }

  private async handle(request: IncomingMessage, response: ServerResponse) {
    if (request.method !== "POST" || request.url !== "/desktop-control") {
      writeJson(response, 404, { ok: false, code: "NOT_FOUND", message: "not found" })
      return
    }
    const payload = await readJsonBody(request).catch((error) => {
      writeJson(response, 400, { ok: false, code: "BAD_REQUEST", message: error instanceof Error ? error.message : "bad request" })
      return undefined
    })
    if (!payload) return
    if (payload.token !== this.token) {
      writeJson(response, 403, { ok: false, code: "BAD_TOKEN", message: "desktop bridge token is invalid" })
      return
    }
    const command = typeof payload.command === "string" ? payload.command : ""
    if (!ALLOWED_COMMANDS.has(command)) {
      writeJson(response, 400, { ok: false, code: "BAD_COMMAND", message: "desktop bridge command is not allowed" })
      return
    }
    const args = isRecord(payload.args) ? payload.args : {}
    const result = await this.dispatch(command, args)
    writeJson(response, result.ok === false ? 502 : 200, result)
  }

  private async dispatch(command: string, args: Record<string, unknown>) {
    const target = this.getMainWindow()
    if (!target || target.isDestroyed()) {
      return { ok: true, accepted: false, code: "DESKTOP_RENDERER_UNAVAILABLE", message: "desktop renderer is unavailable" }
    }
    const requestId = randomUUID()
    const result = await new Promise<DesktopControlBridgeCommandResponse>((resolve) => {
      const timer = globalThis.setTimeout(() => {
        this.pending.delete(requestId)
        resolve({ ok: false, accepted: false, code: "DESKTOP_RENDERER_TIMEOUT", message: "desktop renderer did not respond" })
      }, COMMAND_TIMEOUT_MS)
      this.pending.set(requestId, (response) => {
        globalThis.clearTimeout(timer)
        resolve(response)
      })
      target.webContents.send("desktop-control-bridge-command", { requestId, command, args })
    })
    return result
  }
}

function writeJson(response: ServerResponse, status: number, body: Record<string, unknown>) {
  response.statusCode = status
  response.setHeader("content-type", "application/json; charset=utf-8")
  response.end(JSON.stringify(body))
}

function readJsonBody(request: IncomingMessage) {
  return new Promise<Record<string, unknown>>((resolve, reject) => {
    const chunks: Buffer[] = []
    let total = 0
    request.on("data", (chunk: Buffer) => {
      total += chunk.byteLength
      if (total > MAX_BODY_BYTES) {
        reject(new Error("request body is too large"))
        request.destroy()
        return
      }
      chunks.push(chunk)
    })
    request.on("end", () => {
      try {
        const raw = Buffer.concat(chunks).toString("utf8")
        const parsed = JSON.parse(raw)
        if (!isRecord(parsed)) throw new Error("request body must be an object")
        resolve(parsed)
      } catch (error) {
        reject(error)
      }
    })
    request.on("error", reject)
  })
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}
