import { execFileSync } from "node:child_process"
import { existsSync, readFileSync, readdirSync } from "node:fs"
import { basename, dirname, extname, join } from "node:path"

export type BlueprintEditorCandidate = {
  id: string
  label: string
  command?: string
  args?: string[]
  source: string
  systemDefault?: boolean
}

export function checkAppExists(appName: string): boolean {
  if (process.platform === "win32") return true
  if (process.platform === "linux") return true
  return checkMacosApp(appName)
}

export function resolveAppPath(appName: string): string | null {
  if (process.platform !== "win32") return appName
  return resolveWindowsAppPath(appName)
}

export function listBlueprintEditors(): BlueprintEditorCandidate[] {
  const candidates: BlueprintEditorCandidate[] = []
  const seen = new Set<string>()
  const add = (candidate: BlueprintEditorCandidate | null) => {
    if (!candidate) return
    const key = candidate.systemDefault
      ? candidate.id
      : `${candidate.command ?? ""}\u0000${(candidate.args ?? []).join("\u0000")}`.toLowerCase()
    if (seen.has(key)) return
    seen.add(key)
    candidates.push(candidate)
  }

  add(editorFromEnv("VISUAL"))
  add(editorFromEnv("EDITOR"))
  add(editorFromKnownCommand("vscode", "VS Code", ["code"], "Visual Studio Code"))
  add(editorFromKnownCommand("cursor", "Cursor", ["cursor"], "Cursor"))
  add(editorFromKnownCommand("windsurf", "Windsurf", ["windsurf"], "Windsurf"))
  add(editorFromKnownCommand("zed", "Zed", ["zed"], "Zed"))
  add(editorFromKnownCommand("pycharm", "PyCharm", ["pycharm64", "pycharm"], "PyCharm"))
  add(systemDefaultEditor())

  return candidates
}

export function resolveBlueprintEditor(editorId?: string): BlueprintEditorCandidate {
  const id = editorId?.trim()
  const candidates = listBlueprintEditors()
  return candidates.find((candidate) => candidate.id === id) ?? systemDefaultEditor()
}

export function wslPath(path: string, mode: "windows" | "linux" | null): string {
  if (process.platform !== "win32") return path

  const flag = mode === "windows" ? "-w" : "-u"
  try {
    if (path.startsWith("~")) {
      const suffix = path.slice(1)
      const cmd = `wslpath ${flag} "$HOME${suffix.replace(/"/g, '\\"')}"`
      const output = execFileSync("wsl", ["-e", "sh", "-lc", cmd])
      return output.toString().trim()
    }

    const output = execFileSync("wsl", ["-e", "wslpath", flag, path])
    return output.toString().trim()
  } catch (error) {
    throw new Error(`Failed to run wslpath: ${String(error)}`, { cause: error })
  }
}

function systemDefaultEditor(): BlueprintEditorCandidate {
  return {
    id: "system",
    label: "System default",
    source: "system",
    systemDefault: true,
  }
}

function editorFromEnv(envName: "VISUAL" | "EDITOR"): BlueprintEditorCandidate | null {
  const raw = process.env[envName]?.trim()
  if (!raw) return null
  const parts = splitEditorCommand(raw)
  const command = parts[0]
  if (!command) return null
  const resolved = resolveProgram(command)
  if (!resolved) return null
  return {
    id: `env:${envName.toLowerCase()}`,
    label: `${envName}: ${basename(command)}`,
    command: resolved,
    args: parts.slice(1),
    source: envName,
  }
}

function editorFromKnownCommand(
  id: string,
  label: string,
  commands: string[],
  macosAppName: string,
): BlueprintEditorCandidate | null {
  if (process.platform === "darwin" && checkMacosApp(macosAppName)) {
    return {
      id,
      label,
      command: "open",
      args: ["-a", macosAppName],
      source: `macOS app ${macosAppName}`,
    }
  }

  for (const command of commands) {
    const resolved = resolveProgram(command)
    if (resolved) {
      return {
        id,
        label,
        command: resolved,
        args: [],
        source: `PATH ${command}`,
      }
    }
  }
  return null
}

function splitEditorCommand(raw: string): string[] {
  const parts: string[] = []
  const pattern = /"([^"]*)"|'([^']*)'|(\S+)/g
  let match: RegExpExecArray | null
  while ((match = pattern.exec(raw))) {
    parts.push(match[1] ?? match[2] ?? match[3] ?? "")
  }
  return parts.filter(Boolean)
}

function resolveProgram(program: string): string | null {
  if (/[\\/]/.test(program)) return existsSync(program) ? program : null
  if (process.platform === "win32") return resolveWindowsAppPath(program)
  try {
    return execFileSync("which", [program]).toString().trim().split(/\r?\n/)[0] || null
  } catch {
    return null
  }
}

function checkMacosApp(appName: string) {
  const locations = [`/Applications/${appName}.app`, `/System/Applications/${appName}.app`]

  const home = process.env.HOME
  if (home) locations.push(`${home}/Applications/${appName}.app`)

  if (locations.some((location) => existsSync(location))) return true

  try {
    execFileSync("which", [appName])
    return true
  } catch {
    return false
  }
}

function resolveWindowsAppPath(appName: string): string | null {
  let output: string
  try {
    output = execFileSync("where", [appName]).toString()
  } catch {
    return null
  }

  const paths = output
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)

  const hasExt = (path: string, ext: string) => extname(path).toLowerCase() === `.${ext}`

  const exe = paths.find((path) => hasExt(path, "exe"))
  if (exe) return exe

  const resolveCmd = (path: string) => {
    const content = readFileSync(path, "utf8")
    for (const token of content.split('"').map((value: string) => value.trim())) {
      const lower = token.toLowerCase()
      if (!lower.includes(".exe")) continue

      const index = lower.indexOf("%~dp0")
      if (index >= 0) {
        const base = dirname(path)
        const suffix = token.slice(index + 5)
        const resolved = suffix
          .replace(/\//g, "\\")
          .split("\\")
          .filter((part: string) => part && part !== ".")
          .reduce((current: string, part: string) => {
            if (part === "..") return dirname(current)
            return join(current, part)
          }, base)

        if (existsSync(resolved)) return resolved
      }

      if (existsSync(token)) return token
    }

    return null
  }

  for (const path of paths) {
    if (hasExt(path, "cmd") || hasExt(path, "bat")) {
      const resolved = resolveCmd(path)
      if (resolved) return resolved
    }

    if (!extname(path)) {
      const cmd = `${path}.cmd`
      if (existsSync(cmd)) {
        const resolved = resolveCmd(cmd)
        if (resolved) return resolved
      }

      const bat = `${path}.bat`
      if (existsSync(bat)) {
        const resolved = resolveCmd(bat)
        if (resolved) return resolved
      }
    }
  }

  const key = appName
    .split("")
    .filter((value: string) => /[a-z0-9]/i.test(value))
    .map((value: string) => value.toLowerCase())
    .join("")

  if (key) {
    for (const path of paths) {
      const dirs = [dirname(path), dirname(dirname(path)), dirname(dirname(dirname(path)))]
      for (const dir of dirs) {
        try {
          for (const entry of readdirSync(dir)) {
            const candidate = join(dir, entry)
            if (!hasExt(candidate, "exe")) continue
            const stem = entry.replace(/\.exe$/i, "")
            const name = stem
              .split("")
              .filter((value: string) => /[a-z0-9]/i.test(value))
              .map((value: string) => value.toLowerCase())
              .join("")
            if (name.includes(key) || key.includes(name)) return candidate
          }
        } catch {
          continue
        }
      }
    }
  }

  return paths[0] ?? null
}
