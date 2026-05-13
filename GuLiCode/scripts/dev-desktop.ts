#!/usr/bin/env bun
/**
 * GuLiCode desktop one-click dev launcher.
 *
 * 目标：
 *   一条命令打开 GuLiCode 桌面窗口，跨 Windows / macOS / Linux 一致使用。
 *
 * 行为：
 *   1. 找 bun（PATH，或常见安装位置）。
 *   2. 检查 packages/desktop-electron/node_modules/electron-vite 是否就绪；
 *      缺失 → 自动 `bun install --ignore-scripts`。
 *   3. 检查 packages/opencode/dist/node/node.js 是否存在；
 *      缺失 → 自动跑 `bun --cwd packages/opencode script/build-node.ts`。
 *   4. 默认清理上一轮残留的 GuLiCode Electron / bun 进程（仅命令行包含 GuLiCode 才杀，
 *      避免误伤同机其他 Electron 实例）。可用 `--no-clean` 关闭。
 *   5. 在 packages/desktop-electron 下直接执行
 *      `bun node_modules/electron-vite/bin/electron-vite.js dev`，
 *      stdio 透传到当前终端，同时同步追加到 GuLiCode/logs/gulicode-desktop-direct.log。
 *   6. Ctrl+C → 收子进程后退出。
 *
 * 使用：
 *   bun run desktop                      # 推荐
 *   bun run desktop -- --no-clean        # 不清理旧进程
 *   bun ./scripts/dev-desktop.ts         # 等价
 */

import { spawn, spawnSync, type ChildProcess } from "node:child_process"
import { existsSync, mkdirSync, openSync, closeSync, writeSync } from "node:fs"
import { homedir, platform } from "node:os"
import { dirname, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(SCRIPT_DIR, "..")
const PKG_DESKTOP = join(ROOT, "packages", "desktop-electron")
const PKG_OPENCODE = join(ROOT, "packages", "opencode")
const ELECTRON_VITE_BIN = join(PKG_DESKTOP, "node_modules", "electron-vite", "bin", "electron-vite.js")
const OPENCODE_NODE_BUNDLE = join(PKG_OPENCODE, "dist", "node", "node.js")
const LOG_DIR = join(ROOT, "logs")
const LOG_FILE = join(LOG_DIR, "gulicode-desktop-direct.log")

const args = process.argv.slice(2)
const NO_CLEAN = args.includes("--no-clean")

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

function findBun(): string {
  // 1. PATH 上的 bun
  const probe = spawnSync(platform() === "win32" ? "where" : "which", ["bun"], {
    encoding: "utf8",
  })
  if (probe.status === 0) {
    const first = probe.stdout.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)[0]
    if (first && existsSync(first)) return first
  }
  // 2. 常见安装路径
  const candidates =
    platform() === "win32"
      ? [
          join(homedir(), ".bun", "bin", "bun.exe"),
          join(process.env.LOCALAPPDATA ?? "", "Programs", "bun", "bun.exe"),
        ]
      : [join(homedir(), ".bun", "bin", "bun")]
  for (const c of candidates) {
    if (c && existsSync(c)) return c
  }
  die(
    "未找到 bun。请先安装 Bun (https://bun.com)。\n" +
      "  Windows: powershell -c \"irm bun.com/install.ps1 | iex\"\n" +
      "  macOS/Linux: curl -fsSL https://bun.com/install | bash",
  )
}

function ensureDeps(bun: string) {
  if (existsSync(ELECTRON_VITE_BIN)) {
    return
  }
  log("electron-vite 入口不存在，自动执行 bun install --ignore-scripts ...")
  const r = spawnSync(bun, ["install", "--ignore-scripts"], {
    cwd: ROOT,
    stdio: "inherit",
  })
  if (r.status !== 0) {
    die(`bun install 失败 (exit=${r.status ?? "?"})`)
  }
  if (!existsSync(ELECTRON_VITE_BIN)) {
    die(`bun install 完成后仍找不到 ${ELECTRON_VITE_BIN}`)
  }
}

/**
 * (历史) 这里曾经做 nested electron-dl symlink 的运行时热修，
 * 用来兼容 Node 24 + electron-dl@4 ESM 与 Electron 41 不兼容的问题。
 * 当 Node 回到 22.x 时该问题自动消失，已撤回；保留此说明便于追溯。
 */

function ensureOpencodeBundle(bun: string) {
  if (existsSync(OPENCODE_NODE_BUNDLE)) {
    return
  }
  const buildScript = join(PKG_OPENCODE, "script", "build-node.ts")
  if (!existsSync(buildScript)) {
    warn(`未找到 ${buildScript}，跳过 opencode node bundle 构建。`)
    warn("如果 Electron main 报 virtual:opencode-server 解析失败，请手动恢复该脚本。")
    return
  }
  log("packages/opencode/dist/node/node.js 不存在，构建 opencode node bundle ...")
  const r = spawnSync(bun, ["script/build-node.ts"], {
    cwd: PKG_OPENCODE,
    stdio: "inherit",
  })
  if (r.status !== 0) {
    die(`opencode build-node.ts 失败 (exit=${r.status ?? "?"})`)
  }
}

interface ProcInfo {
  pid: number
  name: string
  cmd: string
}

function listGuliProcesses(): ProcInfo[] {
  const targetNames = new Set(["electron.exe", "electron", "bun.exe", "bun"])
  if (platform() === "win32") {
    const ps = spawnSync(
      "powershell.exe",
      [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "Get-CimInstance Win32_Process | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Depth 3",
      ],
      { encoding: "utf8" },
    )
    if (ps.status !== 0 || !ps.stdout.trim()) return []
    let parsed: any
    try {
      parsed = JSON.parse(ps.stdout)
    } catch {
      return []
    }
    const arr = Array.isArray(parsed) ? parsed : [parsed]
    return arr
      .filter((x) => x && targetNames.has(String(x.Name).toLowerCase()))
      .map((x) => ({
        pid: Number(x.ProcessId),
        name: String(x.Name),
        cmd: String(x.CommandLine ?? ""),
      }))
      .filter((p) => p.cmd.includes("GuLiCode") || p.cmd.includes("gulicode"))
  }
  // *nix
  const ps = spawnSync("ps", ["-eo", "pid=,comm=,args="], { encoding: "utf8" })
  if (ps.status !== 0) return []
  return ps.stdout
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const m = line.match(/^(\d+)\s+(\S+)\s+(.*)$/)
      if (!m) return null
      return { pid: Number(m[1]), name: m[2], cmd: m[3] }
    })
    .filter((p): p is ProcInfo => !!p && targetNames.has(p.name.toLowerCase()))
    .filter((p) => p.cmd.includes("GuLiCode") || p.cmd.includes("gulicode"))
}

function killOldProcesses() {
  if (NO_CLEAN) {
    log("--no-clean 已开启，跳过清理旧进程。")
    return
  }
  const procs = listGuliProcesses().filter((p) => p.pid !== process.pid)
  if (procs.length === 0) {
    return
  }
  log(`发现 ${procs.length} 个残留 GuLiCode 相关进程，正在终止 ...`)
  for (const p of procs) {
    try {
      process.kill(p.pid, "SIGKILL")
    } catch {
      /* ignore */
    }
  }
}

function ensureLogFile(): number {
  if (!existsSync(LOG_DIR)) {
    mkdirSync(LOG_DIR, { recursive: true })
  }
  // 'w' 模式重置日志
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

function main() {
  log(`root = ${ROOT}`)
  const bun = findBun()
  log(`bun  = ${bun}`)

  ensureDeps(bun)
  ensureOpencodeBundle(bun)
  killOldProcesses()

  const logFd = ensureLogFile()
  log(`log  = ${LOG_FILE}`)
  log("启动 electron-vite dev ...")

  const child = spawn(bun, [ELECTRON_VITE_BIN, "dev"], {
    cwd: PKG_DESKTOP,
    env: { ...process.env, FORCE_COLOR: "1" },
    stdio: ["ignore", "pipe", "pipe"],
  })

  teePipe(child, logFd)

  const shutdown = (signal: NodeJS.Signals) => {
    log(`收到 ${signal}，正在关闭 ...`)
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
      log(`electron-vite 被信号 ${signal} 终止`)
      process.exit(1)
    }
    log(`electron-vite 退出 code=${code ?? 0}`)
    process.exit(code ?? 0)
  })
}

main()
