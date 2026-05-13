#!/usr/bin/env bun

import { spawn, spawnSync, type ChildProcess } from "node:child_process"
import { closeSync, existsSync, mkdirSync, openSync, readdirSync, readFileSync, writeSync } from "node:fs"
import { homedir, platform } from "node:os"
import { dirname, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(SCRIPT_DIR, "..")
const PKG_DESKTOP = join(ROOT, "packages", "desktop-electron")
const PKG_OPENCODE = join(ROOT, "packages", "opencode")
const DESKTOP_ICON_ICO = join(PKG_DESKTOP, "resources", "icons", "icon.ico")
const ELECTRON_VITE_BIN = join(PKG_DESKTOP, "node_modules", "electron-vite", "bin", "electron-vite.js")
const ELECTRON_BUILDER_BIN = join(PKG_DESKTOP, "node_modules", "electron-builder", "cli.js")
const OPENCODE_NODE_BUNDLE = join(PKG_OPENCODE, "dist", "node", "node.js")
const LOG_DIR = join(ROOT, "logs")
const LOG_FILE = join(LOG_DIR, "gulicode-desktop-direct.log")

const args = process.argv.slice(2)
const NO_CLEAN = args.includes("--no-clean")
const PACKAGED = args.includes("--packaged")
const PACKAGED_OUTPUT_REL = join("dist", "packaged-launch", "current")

function log(msg: string) {
  process.stdout.write(`[dev-desktop] ${msg}\n`)
}

function warn(msg: string) {
  process.stderr.write(`[dev-desktop] ${msg}\n`)
}

function die(msg: string, code = 1): never {
  warn(msg)
  process.exit(code)
}

function getChannel() {
  const raw = process.env.OPENCODE_CHANNEL
  if (raw === "beta" || raw === "prod") return raw
  return "dev"
}

function getProductName() {
  const channel = getChannel()
  if (channel === "beta") return "GuLiCode Beta"
  if (channel === "prod") return "GuLiCode"
  return "GuLiCode Dev"
}

function getSharedEnv(extraEnv: NodeJS.ProcessEnv = {}) {
  return {
    ...process.env,
    ...extraEnv,
    FORCE_COLOR: "1",
    OPENCODE_CHANNEL: process.env.OPENCODE_CHANNEL ?? getChannel(),
  }
}

function getPackagedExePath() {
  if (platform() !== "win32") {
    die("--packaged currently supports Windows only.")
  }
  return join(PKG_DESKTOP, PACKAGED_OUTPUT_REL, "win-unpacked", `${getProductName()}.exe`)
}

function findRceditPath() {
  if (platform() !== "win32") return null

  const cacheRoot = join(homedir(), "AppData", "Local", "electron-builder", "Cache", "winCodeSign")
  if (!existsSync(cacheRoot)) return null

  const subdirs = readdirSync(cacheRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => join(cacheRoot, entry.name, "rcedit-x64.exe"))

  for (const candidate of subdirs.sort()) {
    if (existsSync(candidate)) return candidate
  }

  return null
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function findMissingRendererAssets() {
  const assetsDir = join(PKG_DESKTOP, "out", "renderer", "assets")
  if (!existsSync(assetsDir)) {
    return [assetsDir]
  }

  const cssFiles = readdirSync(assetsDir)
    .filter((name) => name.endsWith(".css"))
    .map((name) => join(assetsDir, name))

  const missing = new Set<string>()
  const urlPattern = /url\((['"]?)([^'")]+)\1\)/g

  for (const cssFile of cssFiles) {
    const css = readFileSync(cssFile, "utf8")
    for (const match of css.matchAll(urlPattern)) {
      const rawUrl = match[2]
      if (!rawUrl || rawUrl.startsWith("data:") || /^[a-z]+:/i.test(rawUrl)) {
        continue
      }
      const assetPath = resolve(dirname(cssFile), rawUrl)
      if (!existsSync(assetPath)) {
        missing.add(assetPath)
      }
    }
  }

  return [...missing]
}

async function waitForRendererAssets() {
  const maxAttempts = 12
  const delayMs = 500

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const missing = findMissingRendererAssets()
    if (missing.length === 0) {
      return
    }
    if (attempt === 1) {
      log("waiting for renderer asset files to finish landing on disk ...")
    }
    await sleep(delayMs)
  }

  const missing = findMissingRendererAssets()
  if (missing.length > 0) {
    warn(`renderer assets still missing after wait: ${missing.slice(0, 3).join(", ")}`)
  }
}

function runChecked(command: string, argv: string[], cwd: string, label: string) {
  const result = spawnSync(command, argv, {
    cwd,
    stdio: "inherit",
    env: getSharedEnv(),
  })
  if (result.status !== 0) {
    die(`${label} failed (exit=${result.status ?? "?"})`)
  }
}

function findBun(): string {
  const probe = spawnSync(platform() === "win32" ? "where" : "which", ["bun"], {
    encoding: "utf8",
  })
  if (probe.status === 0) {
    const first = probe.stdout.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)[0]
    if (first && existsSync(first)) return first
  }

  const candidates =
    platform() === "win32"
      ? [
          join(homedir(), ".bun", "bin", "bun.exe"),
          join(process.env.LOCALAPPDATA ?? "", "Programs", "bun", "bun.exe"),
        ]
      : [join(homedir(), ".bun", "bin", "bun")]

  for (const candidate of candidates) {
    if (candidate && existsSync(candidate)) return candidate
  }

  die(
    "bun was not found.\n" +
      "  Windows: powershell -c \"irm bun.com/install.ps1 | iex\"\n" +
      "  macOS/Linux: curl -fsSL https://bun.com/install | bash",
  )
}

function ensureDeps(bun: string) {
  if (existsSync(ELECTRON_VITE_BIN) && existsSync(ELECTRON_BUILDER_BIN)) {
    return
  }

  log("desktop dependencies are missing, running bun install --ignore-scripts ...")
  runChecked(bun, ["install", "--ignore-scripts"], ROOT, "bun install")

  if (!existsSync(ELECTRON_VITE_BIN)) {
    die(`electron-vite entry not found after install: ${ELECTRON_VITE_BIN}`)
  }
  if (!existsSync(ELECTRON_BUILDER_BIN)) {
    die(`electron-builder entry not found after install: ${ELECTRON_BUILDER_BIN}`)
  }
}

function ensureOpencodeBundle(bun: string) {
  if (existsSync(OPENCODE_NODE_BUNDLE)) {
    return
  }

  const buildScript = join(PKG_OPENCODE, "script", "build-node.ts")
  if (!existsSync(buildScript)) {
    warn(`opencode node bundle build script not found: ${buildScript}`)
    warn("If the Electron main process later fails to resolve virtual:opencode-server, restore that script first.")
    return
  }

  log("building packages/opencode/dist/node/node.js ...")
  runChecked(bun, ["script/build-node.ts"], PKG_OPENCODE, "opencode build-node.ts")
}

interface ProcInfo {
  pid: number
  name: string
  cmd: string
}

function formatProc(proc: ProcInfo) {
  return `${proc.name}#${proc.pid} (${proc.cmd || "no-path"})`
}

function forceKillWindowsProductProcesses() {
  if (platform() !== "win32") return
  spawnSync("taskkill", ["/IM", `${getProductName()}.exe`, "/T", "/F"], {
    stdio: "ignore",
  })
}

function listGuliProcesses(): ProcInfo[] {
  const productName = getProductName()
  const targetNames = new Set(
    ["electron.exe", "electron", "bun.exe", "bun", `${productName}.exe`, productName].map((name) =>
      name.toLowerCase(),
    ),
  )

  if (platform() === "win32") {
    const pathNeedles = [ROOT, join(PKG_DESKTOP, "dist", "win-unpacked")]
    const ps = spawnSync(
      "powershell.exe",
      [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        [
          "$ErrorActionPreference = 'SilentlyContinue'",
          "Get-Process",
          "| ForEach-Object { '{0}|{1}|{2}' -f $_.Id, $_.ProcessName, $_.Path }",
        ].join(" "),
      ],
      { encoding: "utf8" },
    )
    if (ps.status !== 0 || !ps.stdout.trim()) return []

    return ps.stdout
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [pid, name, ...rest] = line.split("|")
        return {
          pid: Number(pid),
          name: String(name ?? ""),
          cmd: rest.join("|"),
        }
      })
      .filter((proc) => targetNames.has(proc.name.toLowerCase()))
      .filter((proc) => pathNeedles.some((needle) => proc.cmd.includes(needle)) || proc.name.includes("GuLiCode"))
  }

  const ps = spawnSync("ps", ["-eo", "pid=,comm=,args="], { encoding: "utf8" })
  if (ps.status !== 0) return []

  return ps.stdout
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const match = line.match(/^(\d+)\s+(\S+)\s+(.*)$/)
      if (!match) return null
      return { pid: Number(match[1]), name: match[2], cmd: match[3] }
    })
    .filter((proc): proc is ProcInfo => !!proc && targetNames.has(proc.name.toLowerCase()))
    .filter((proc) => proc.cmd.includes("GuLiCode") || proc.cmd.includes("gulicode"))
}

async function killOldProcesses() {
  if (NO_CLEAN) {
    log("skipping old-process cleanup because --no-clean is set.")
    return
  }

  const protectedPids = new Set([process.pid, process.ppid].filter((pid) => pid > 0))

  if (platform() === "win32") {
    forceKillWindowsProductProcesses()
    await sleep(500)
  }

  for (let attempt = 1; attempt <= 3; attempt++) {
    const procs = listGuliProcesses().filter((proc) => !protectedPids.has(proc.pid))
    if (procs.length === 0) {
      return
    }

    log(`terminating ${procs.length} stale GuLiCode-related process(es) ...`)
    if (attempt === 1) {
      for (const proc of procs) {
        log(`old  = ${formatProc(proc)}`)
      }
    }

    for (const proc of procs) {
      try {
        if (platform() === "win32") {
          spawnSync("taskkill", ["/PID", String(proc.pid), "/T", "/F"], {
            stdio: "ignore",
          })
        } else {
          process.kill(proc.pid, "SIGKILL")
        }
      } catch {
        /* ignore */
      }
    }

    await sleep(1000)
  }

  const survivors = listGuliProcesses().filter((proc) => !protectedPids.has(proc.pid))
  if (survivors.length > 0) {
    warn(`some stale GuLiCode processes survived cleanup: ${survivors.map(formatProc).join(", ")}`)
  }
}

function isProcessAlive(pid: number) {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

function ensureLogFile(): number {
  if (!existsSync(LOG_DIR)) {
    mkdirSync(LOG_DIR, { recursive: true })
  }
  return openSync(LOG_FILE, "w")
}

function teePipe(child: ChildProcess, logFd: number) {
  const pipe = (stream: NodeJS.ReadableStream | null, dest: NodeJS.WriteStream) => {
    if (!stream) return
    stream.on("data", (chunk: Buffer | string) => {
      const buf = typeof chunk === "string" ? Buffer.from(chunk) : chunk
      dest.write(buf)
      try {
        writeSync(logFd, buf)
      } catch {
        /* ignore */
      }
    })
  }

  pipe(child.stdout, process.stdout)
  pipe(child.stderr, process.stderr)
}

async function runPackagedBuild(bun: string) {
  log("building packaged Windows desktop app for correct taskbar icon ...")
  runChecked(bun, ["./scripts/prebuild.ts", getChannel()], PKG_DESKTOP, "desktop prebuild")
  runChecked(bun, [ELECTRON_VITE_BIN, "build"], PKG_DESKTOP, "electron-vite build")
  await waitForRendererAssets()
  const result = spawnSync(
    bun,
    [ELECTRON_BUILDER_BIN, "--win", "--dir", "--config", "electron-builder.config.ts"],
    {
      cwd: PKG_DESKTOP,
      stdio: "inherit",
      env: getSharedEnv({
        GULICODE_ELECTRON_OUTPUT_DIR: PACKAGED_OUTPUT_REL,
      }),
    },
  )

  if (result.status !== 0) {
    if (existsSync(getPackagedExePath())) {
      warn("electron-builder reported an error after producing the unpacked exe; continuing with the generated app.")
    } else {
      die(`electron-builder --dir failed (exit=${result.status ?? "?"})`)
    }
  }

  patchPackagedExeIcon()
}

function patchPackagedExeIcon() {
  if (platform() !== "win32") return

  const exePath = getPackagedExePath()
  if (!existsSync(exePath)) {
    warn(`cannot patch packaged exe icon because executable is missing: ${exePath}`)
    return
  }
  if (!existsSync(DESKTOP_ICON_ICO)) {
    warn(`cannot patch packaged exe icon because icon is missing: ${DESKTOP_ICON_ICO}`)
    return
  }

  const rcedit = findRceditPath()
  if (!rcedit) {
    warn("rcedit-x64.exe was not found in electron-builder cache; packaged exe icon may stay stale.")
    return
  }

  const result = spawnSync(rcedit, [exePath, "--set-icon", DESKTOP_ICON_ICO], {
    stdio: "inherit",
  })
  if (result.status !== 0) {
    warn(`rcedit failed to patch packaged exe icon (exit=${result.status ?? "?"}).`)
    return
  }

  log(`patched packaged exe icon with rcedit (${rcedit})`)
}

async function launchPackagedApp() {
  const exePath = getPackagedExePath()
  if (!existsSync(exePath)) {
    die(`packaged executable not found: ${exePath}`)
  }

  await killOldProcesses()
  log(`exe  = ${exePath}`)
  const child = spawn(exePath, [], {
    cwd: dirname(exePath),
    detached: true,
    stdio: "ignore",
  })
  child.unref()

  await sleep(6000)
  if (isProcessAlive(child.pid ?? -1)) {
    log("packaged GuLiCode launched.")
    return
  }

  const fallback = listGuliProcesses().find((proc) => proc.cmd.includes(exePath))
  if (fallback) {
    log(`packaged GuLiCode launched via handoff to pid ${fallback.pid}.`)
    return
  }

  warn("packaged executable exited shortly after launch.")
}

function runDevMode(bun: string) {
  const logFd = ensureLogFile()
  log(`log  = ${LOG_FILE}`)
  log("starting electron-vite dev ...")

  const child = spawn(bun, [ELECTRON_VITE_BIN, "dev"], {
    cwd: PKG_DESKTOP,
    env: getSharedEnv(),
    stdio: ["ignore", "pipe", "pipe"],
  })

  teePipe(child, logFd)

  const shutdown = (signal: NodeJS.Signals) => {
    log(`received ${signal}, shutting down ...`)
    if (!child.killed) {
      try {
        child.kill(signal)
      } catch {
        /* ignore */
      }
    }
  }

  process.on("SIGINT", shutdown)
  process.on("SIGTERM", shutdown)

  child.on("exit", (code, signal) => {
    try {
      closeSync(logFd)
    } catch {
      /* ignore */
    }

    if (signal) {
      log(`electron-vite terminated by signal ${signal}`)
      process.exit(1)
    }

    log(`electron-vite exited with code ${code ?? 0}`)
    process.exit(code ?? 0)
  })
}

async function main() {
  log(`root = ${ROOT}`)
  const bun = findBun()
  log(`bun  = ${bun}`)

  ensureDeps(bun)
  ensureOpencodeBundle(bun)
  await killOldProcesses()

  if (PACKAGED) {
    await runPackagedBuild(bun)
    await launchPackagedApp()
    return
  }

  runDevMode(bun)
}

void main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error)
  die(message)
})
