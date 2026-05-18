import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process"
import { existsSync, statSync } from "node:fs"
import { dirname, delimiter, isAbsolute, join, resolve } from "node:path"
import { randomUUID } from "node:crypto"
import { fileURLToPath } from "node:url"

type ReadyPayload = {
  ok: true
  url: string
  token: string
}

export type BlueprintDocument = {
  schema_version: 1
  id: string
  name: string
  graph: Record<string, unknown>
  ui: Record<string, unknown>
}

export type BlueprintRunEndAction = "complete" | "cancel" | "fail" | "pause"

export class BlueprintRuntime {
  private child?: ChildProcessWithoutNullStreams
  private ready?: Promise<ReadyPayload>

  constructor(
    private readonly opts: {
      pythonCommand?: string
      packageRoot?: string
      env?: NodeJS.ProcessEnv
    } = {},
  ) {}

  list(projectDir: string) {
    return this.request("blueprint.list", { projectDir }).then((result) => result.blueprints)
  }

  open(projectDir: string, blueprintId: string) {
    return this.request("blueprint.open", { projectDir, blueprintId }).then((result) => result.document)
  }

  save(projectDir: string, document: BlueprintDocument) {
    return this.request("blueprint.save", { projectDir, document }).then((result) => result.document)
  }

  validate(projectDir: string, blueprintId: string, document?: BlueprintDocument) {
    return this.request("blueprint.validate", { projectDir, blueprintId, document })
  }

  listRuns(projectDir?: string, blueprintId?: string) {
    return this.request("blueprint.listRuns", { projectDir, blueprintId }).then((result) => result.runs)
  }

  start(projectDir: string, blueprintId: string, plan: Record<string, unknown>, executionMode: "status" | "live" = "status") {
    return this.request("blueprint.start", { projectDir, blueprintId, plan, executionMode })
  }

  status(runId: string) {
    return this.request("blueprint.status", { runId })
  }

  end(runId: string, action: BlueprintRunEndAction, reason?: string) {
    return this.request("blueprint.end", { runId, action, reason })
  }

  recentEvents(runId: string, limit?: number) {
    return this.request("blueprint.recentEvents", { runId, limit })
  }

  agentInfo(runId: string | undefined, nodeId: string) {
    return this.request("blueprint.agentInfo", { runId, nodeId })
  }

  queueAgentMessage(runId: string, nodeId: string, text: string, mode: "default" | "top") {
    return this.request("blueprint.queueAgentMessage", { runId, nodeId, text, mode })
  }

  agentStreamToken(runId: string, cursor?: number) {
    return this.ensureReady().then((ready) =>
      this.request("blueprint.agentStreamToken", { runId, cursor, baseUrl: ready.url }),
    )
  }

  close() {
    this.child?.kill()
    this.child = undefined
    this.ready = undefined
  }

  async request(command: string, args: Record<string, unknown>) {
    const projectDir = typeof args.projectDir === "string" ? validateProjectDir(args.projectDir) : args.projectDir
    const ready = await this.ensureReady()
    const response = await fetch(ready.url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        token: ready.token,
        command,
        args: {
          ...args,
          ...(projectDir ? { projectDir } : {}),
        },
      }),
    })
    const payload = (await response.json()) as Record<string, unknown>
    if (!response.ok || payload.ok === false) {
      const code = typeof payload.code === "string" ? payload.code : undefined
      const message = String(payload.error ?? `blueprint runtime request failed: ${command}`)
      const error = new Error(code ? `${code}: ${message}` : message)
      ;(error as Error & { code?: string }).code = code
      throw error
    }
    return payload
  }

  private ensureReady() {
    if (this.ready) return this.ready
    this.ready = new Promise<ReadyPayload>((resolveReady, rejectReady) => {
      const python = this.opts.pythonCommand ?? process.env.GULICODE_PYTHON ?? "python"
      const packageRoot = this.opts.packageRoot ?? findPackageRoot()
      const token = randomUUID()
      const env = {
        ...process.env,
        ...(this.opts.env ?? {}),
        PYTHONPATH: mergePythonPath(packageRoot, process.env.PYTHONPATH),
      }
      const child = spawn(python, ["-m", "multi_agent_tcp", "desktop-blueprint-service", "--port", "0", "--token", token], {
        env,
        windowsHide: true,
      })
      this.child = child

      let stdout = ""
      let stderr = ""
      let resolved = false

      const fail = (error: Error) => {
        if (resolved) return
        resolved = true
        this.ready = undefined
        child.kill()
        rejectReady(error)
      }

      const tryResolve = () => {
        const line = stdout.split(/\r?\n/).find((entry) => entry.trim().startsWith("{"))
        if (!line) return
        try {
          const payload = JSON.parse(line) as ReadyPayload
          if (!payload.ok || !payload.url || !payload.token) throw new Error("invalid ready payload")
          resolved = true
          resolveReady(payload)
        } catch (error) {
          fail(error instanceof Error ? error : new Error(String(error)))
        }
      }

      child.stdout.on("data", (chunk) => {
        stdout += String(chunk)
        tryResolve()
      })
      child.stderr.on("data", (chunk) => {
        stderr += String(chunk)
      })
      child.on("error", (error) => fail(error))
      child.on("exit", (code) => {
        if (!resolved) fail(new Error(`desktop blueprint service exited before ready: ${code}; ${stderr.trim()}`))
      })
    })
    return this.ready
  }
}

export function validateProjectDir(projectDir: string) {
  if (!isAbsolute(projectDir)) throw new Error("projectDir must be an absolute path")
  const resolved = resolve(projectDir)
  if (!existsSync(resolved) || !statSync(resolved).isDirectory()) {
    throw new Error(`projectDir is not a directory: ${projectDir}`)
  }
  return resolved
}

function findPackageRoot() {
  const starts = [process.cwd(), dirname(fileURLToPath(import.meta.url))]
  for (const start of starts) {
    let current = resolve(start)
    for (;;) {
      if (existsSync(join(current, "multi_agent_tcp", "__main__.py"))) return current
      if (existsSync(join(current, "__main__.py")) && existsSync(join(current, "graph_runtime.py"))) {
        return dirname(current)
      }
      const parent = dirname(current)
      if (parent === current) break
      current = parent
    }
  }
  return process.cwd()
}

function mergePythonPath(packageRoot: string, current?: string) {
  const items = [packageRoot, ...(current ? current.split(delimiter).filter(Boolean) : [])]
  return Array.from(new Set(items)).join(delimiter)
}
