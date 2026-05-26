import { spawn, spawnSync, type ChildProcessWithoutNullStreams } from "node:child_process"
import { existsSync, statSync } from "node:fs"
import { dirname, delimiter, isAbsolute, join, resolve } from "node:path"
import { randomUUID } from "node:crypto"
import { fileURLToPath } from "node:url"

type ReadyPayload = {
  ok: true
  url: string
  token: string
}

type PythonLauncher = {
  command: string
  args: string[]
  source: string
  executable?: string
}

export type BlueprintDocument = {
  schema_version: 1
  id: string
  name: string
  graph: Record<string, unknown>
  ui: Record<string, unknown>
}

export type BlueprintRunEndAction = "complete" | "cancel" | "fail" | "pause"

export type BlueprintRelocateConflictPolicy = "overwrite" | "load_existing"

export class BlueprintRuntime {
  private child?: ChildProcessWithoutNullStreams
  private ready?: Promise<ReadyPayload>
  private configuredPythonCommand?: string
  private activeLauncher?: PythonLauncher

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

  relocateProjectWorkdir(
    projectDir: string,
    blueprintId: string,
    document: BlueprintDocument,
    projectWorkdir: string,
    conflictPolicy?: BlueprintRelocateConflictPolicy,
  ) {
    return this.request("blueprint.relocateProjectWorkdir", {
      projectDir,
      blueprintId,
      document,
      projectWorkdir,
      conflictPolicy,
    })
  }

  validate(projectDir: string, blueprintId: string, document?: BlueprintDocument) {
    return this.request("blueprint.validate", { projectDir, blueprintId, document })
  }

  listRuns(projectDir?: string, blueprintId?: string) {
    return this.request("blueprint.listRuns", { projectDir, blueprintId }).then((result) => result.runs)
  }

  detectPython(projectDir?: string, pythonCommand?: string) {
    const packageRoot = this.opts.packageRoot ?? findPackageRoot()
    const runtimeEnv = {
      ...process.env,
      ...(this.opts.env ?? {}),
    }
    try {
      const validatedProjectDir =
        projectDir && isAbsolute(projectDir) && existsSync(projectDir) && statSync(projectDir).isDirectory()
          ? validateProjectDir(projectDir)
          : undefined
      const python = resolvePythonLauncher({
        configured: pythonCommand === undefined ? (this.configuredPythonCommand ?? this.opts.pythonCommand) : pythonCommand,
        env: runtimeEnv,
        packageRoot,
        projectDir: validatedProjectDir,
      })
      if (!python.executable || !isAbsolute(python.executable)) {
        throw new Error(`Python interpreter could not be verified from ${python.source}`)
      }
      return {
        ok: true,
        pythonCommand: python.executable,
        source: python.source,
      }
    } catch (error) {
      return {
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      }
    }
  }

  configure(opts: { pythonCommand?: string } = {}) {
    const nextPython = opts.pythonCommand?.trim() || undefined
    const previousPython = this.configuredPythonCommand
    if (previousPython !== nextPython) {
      this.configuredPythonCommand = nextPython
      if (this.shouldRestartForPython(nextPython)) this.close()
    }
    return {
      ok: true,
      pythonCommand: this.configuredPythonCommand ?? null,
    }
  }

  start(projectDir: string, blueprintId: string, plan: Record<string, unknown>, executionMode: "status" | "live" = "status") {
    const planPythonCommand = pythonCommandFromStartPlan(plan)
    if (planPythonCommand) this.configure({ pythonCommand: planPythonCommand })
    return this.request("blueprint.start", { projectDir, blueprintId, plan, executionMode })
  }

  status(runId: string) {
    return this.request("blueprint.status", { runId })
  }

  runDiff(runId: string) {
    return this.request("blueprint.runDiff", { runId })
  }

  changesetDiff(runId: string, changesetId: string) {
    return this.request("blueprint.changesetDiff", { runId, changesetId })
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

  ensurePlanningContext(projectDir: string, blueprintId: string, desktopSessionId: string) {
    return this.request("blueprint.planning.ensureContext", { projectDir, blueprintId, desktopSessionId })
  }

  answerPlanningQuestion(
    sessionId: string,
    questionId: string,
    answers: unknown,
    opts: { rejected?: boolean; reason?: string } = {},
  ) {
    return this.request("blueprint.planning.answerQuestion", {
      sessionId,
      questionId,
      answers,
      rejected: opts.rejected ?? false,
      reason: opts.reason,
    })
  }

  rejectPlanningPlan(sessionId: string, reason?: string) {
    return this.request("blueprint.planning.rejectPlan", { sessionId, reason })
  }

  markPlanningPlanStarted(sessionId: string, runId: string, started?: unknown) {
    return this.request("blueprint.planning.markPlanStarted", { sessionId, runId, started })
  }

  planningStatus(sessionId: string) {
    return this.request("blueprint.planning.status", { sessionId })
  }

  endPlanningSession(sessionId: string, reason?: string) {
    return this.request("blueprint.planning.endSession", { sessionId, reason })
  }

  close() {
    this.child?.kill()
    this.child = undefined
    this.ready = undefined
  }

  async request(command: string, args: Record<string, unknown>) {
    const projectDir = typeof args.projectDir === "string" ? validateProjectDir(args.projectDir) : args.projectDir
    const ready = await this.ensureReady(typeof projectDir === "string" ? projectDir : undefined)
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
      const details = payload.details && typeof payload.details === "object" ? payload.details as Record<string, unknown> : undefined
      const detailError = typeof details?.error === "string" && details.error.trim() ? details.error.trim() : undefined
      const baseMessage = String(payload.error ?? `blueprint runtime request failed: ${command}`)
      const message = detailError ? `${baseMessage}: ${detailError}` : baseMessage
      const error = new Error(code ? `${code}: ${message}` : message)
      ;(error as Error & { code?: string }).code = code
      ;(error as Error & { details?: Record<string, unknown> }).details = details
      throw error
    }
    return payload
  }

  private ensureReady(projectDir?: string) {
    if (this.ready) return this.ready
    this.ready = new Promise<ReadyPayload>((resolveReady, rejectReady) => {
      const packageRoot = this.opts.packageRoot ?? findPackageRoot()
      const runtimeEnv = {
        ...process.env,
        ...(this.opts.env ?? {}),
      }
      let python: PythonLauncher
      try {
        python = resolvePythonLauncher({
          configured: this.configuredPythonCommand ?? this.opts.pythonCommand,
          env: runtimeEnv,
          packageRoot,
          projectDir,
        })
      } catch (error) {
        this.ready = undefined
        rejectReady(error instanceof Error ? error : new Error(String(error)))
        return
      }
      const token = randomUUID()
      const env = {
        ...runtimeEnv,
        PYTHONPATH: mergePythonPath(packageRoot, runtimeEnv.PYTHONPATH),
      }
      const child = spawn(
        python.command,
        [...python.args, "-m", "multi_agent_tcp", "desktop-blueprint-service", "--port", "0", "--token", token],
        {
          env,
          windowsHide: true,
        },
      )
      this.child = child
      this.activeLauncher = python

      let stdout = ""
      let stderr = ""
      let resolved = false

      const fail = (error: Error) => {
        if (resolved) return
        resolved = true
        this.ready = undefined
        if (this.child === child) {
          this.child = undefined
          this.activeLauncher = undefined
        }
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
      child.on("error", (error) => fail(new Error(`failed to start Python blueprint runtime with ${python.source}: ${error.message}`)))
      child.on("exit", (code) => {
        if (this.child === child) {
          this.child = undefined
          this.activeLauncher = undefined
          if (resolved) this.ready = undefined
        }
        if (!resolved) fail(new Error(`desktop blueprint service exited before ready: ${code}; ${stderr.trim()}`))
      })
    })
    return this.ready
  }

  private shouldRestartForPython(nextPython?: string) {
    if (!this.child && !this.ready) return false
    const current = this.activeLauncher
    if (!current?.executable) return true
    const packageRoot = this.opts.packageRoot ?? findPackageRoot()
    const runtimeEnv = {
      ...process.env,
      ...(this.opts.env ?? {}),
    }
    try {
      const next = resolvePythonLauncher({
        configured: nextPython,
        env: runtimeEnv,
        packageRoot,
      })
      return !sameExecutable(current.executable, next.executable)
    } catch {
      return true
    }
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

function pythonCommandFromStartPlan(plan: Record<string, unknown>) {
  const commonConfig = plan.common_config
  if (!isRecord(commonConfig)) return undefined
  const value = commonConfig.python_path
  if (typeof value !== "string") return undefined
  const trimmed = value.trim()
  return trimmed || undefined
}

function resolvePythonLauncher(input: {
  configured?: string
  env: NodeJS.ProcessEnv
  packageRoot: string
  projectDir?: string
}): PythonLauncher {
  const configured = input.configured?.trim()
  if (configured) return launcherWithExecutable(launcherFromCommand(configured, "blueprint common config python_path"))

  const envPython = input.env.GULICODE_PYTHON?.trim()
  if (envPython) return launcherWithExecutable(launcherFromCommand(envPython, "GULICODE_PYTHON"))

  const candidates: PythonLauncher[] = [
    { command: "python", args: [], source: "PATH python" },
    { command: "python3", args: [], source: "PATH python3" },
  ]
  if (process.platform === "win32") candidates.push({ command: "py", args: ["-3"], source: "Windows py -3" })

  candidates.push(...venvPythonCandidates(input.projectDir), ...venvPythonCandidates(input.packageRoot))

  for (const candidate of candidates) {
    const executable = pythonExecutable(candidate)
    if (executable) return { ...candidate, executable }
  }

  throw new Error(
    "Python interpreter is required for blueprint runtime. Set the Blueprint config Python path or GULICODE_PYTHON.",
  )
}

function venvPythonCandidates(root?: string): PythonLauncher[] {
  if (!root) return []
  const candidates =
    process.platform === "win32"
      ? [join(root, ".venv", "Scripts", "python.exe")]
      : [join(root, ".venv", "bin", "python")]
  return candidates.map((command) => ({
    command,
    args: [],
    source: `.venv Python at ${command}`,
  }))
}

function launcherFromCommand(value: string, source: string): PythonLauncher {
  const trimmed = value.trim()
  const parsed = parseCommandValue(trimmed)
  return {
    ...parsed,
    source,
  }
}

function launcherWithExecutable(candidate: PythonLauncher): PythonLauncher {
  const executable = pythonExecutable(candidate)
  return executable ? { ...candidate, executable } : candidate
}

function parseCommandValue(value: string): Pick<PythonLauncher, "command" | "args"> {
  if (value.startsWith('"')) {
    const end = value.indexOf('"', 1)
    if (end > 1) {
      const command = value.slice(1, end)
      const rest = value.slice(end + 1).trim()
      return { command, args: rest ? rest.split(/\s+/) : [] }
    }
  }
  if (existsSync(value) || /[\\/]/.test(value)) return { command: value, args: [] }
  const [command, ...args] = value.split(/\s+/).filter(Boolean)
  return { command: command || value, args }
}

function pythonExecutable(candidate: PythonLauncher) {
  if (/[\\/]/.test(candidate.command) && !existsSync(candidate.command)) return undefined
  const result = spawnSync(candidate.command, [...candidate.args, "-c", "import sys; print(sys.executable)"], {
    encoding: "utf8",
    windowsHide: true,
    timeout: 3000,
  })
  if (result.error || result.status !== 0) return undefined
  const executable = result.stdout.trim().split(/\r?\n/).at(0)?.trim()
  return executable || undefined
}

function sameExecutable(left?: string, right?: string) {
  if (!left || !right) return false
  const normalizeExecutable = (value: string) => {
    const resolved = resolve(value)
    return process.platform === "win32" ? resolved.toLowerCase() : resolved
  }
  return normalizeExecutable(left) === normalizeExecutable(right)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
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
