import { execFile } from "node:child_process"
import { constants } from "node:fs"
import { access, readdir, readFile } from "node:fs/promises"
import path from "node:path"

export type BlueprintCatalogItem = {
  value: string
  label: string
  description?: string
}

const RULE_EXTENSIONS = new Set([".md", ".txt", ".json", ".yaml", ".yml", ".toml"])
const MODEL_COMMAND_TIMEOUT_MS = 15_000
const WINDOWS_SCRIPT_EXTENSIONS = new Set([".bat", ".cmd"])

export async function listBlueprintDirectories(root: string): Promise<BlueprintCatalogItem[]> {
  const rootDir = root.trim()
  if (!rootDir) return []
  const entries = await readCatalogDirectory(rootDir)
  return entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => ({
      value: path.join(rootDir, entry.name),
      label: entry.name,
    }))
    .sort(compareCatalogItems)
}

export async function listBlueprintSkills(dir: string): Promise<BlueprintCatalogItem[]> {
  const skillDir = dir.trim()
  if (!skillDir) return []
  const [entries, manifest] = await Promise.all([readCatalogDirectory(skillDir), readSkillManifest(skillDir)])
  const skills: Array<BlueprintCatalogItem | undefined> = await Promise.all(
    entries
      .filter((entry) => entry.isDirectory())
      .map(async (entry) => {
        const skillPath = path.join(skillDir, entry.name, "SKILL.md")
        const source = await readFile(skillPath, "utf8").catch(() => undefined)
        if (!source) return undefined
        const metadata = parseSkillMetadata(source)
        return {
          value: entry.name,
          label: metadata.name || entry.name,
          description: manifest[entry.name]?.description || metadata.description,
        } satisfies BlueprintCatalogItem
      }),
  )
  return skills.filter(isCatalogItem).sort(compareCatalogItems)
}

export async function listBlueprintRules(dir: string): Promise<BlueprintCatalogItem[]> {
  const ruleDir = dir.trim()
  if (!ruleDir) return []
  const entries = await readCatalogDirectory(ruleDir)
  return entries
    .filter((entry) => entry.isFile() && RULE_EXTENSIONS.has(path.extname(entry.name).toLowerCase()))
    .map((entry) => ({
      value: entry.name,
      label: entry.name,
    }))
    .sort(compareCatalogItems)
}

export async function listBlueprintModels(cliKind: string): Promise<string[]> {
  try {
    if (cliKind === "codemaker") {
      const output = await execFileText("codemaker", ["models", "netease-codemaker"])
      return parseCodemakerModels(output)
    }
    if (cliKind === "codex") {
      const output = await execFileText("codex", ["debug", "models"])
      return parseCodexModels(output)
    }
  } catch (error) {
    console.warn(`Failed to list blueprint models for ${cliKind}`, error)
    return []
  }
  throw new Error(`Unsupported CLI kind: ${cliKind}`)
}

async function readCatalogDirectory(dir: string) {
  try {
    return await readdir(dir, { withFileTypes: true })
  } catch (error) {
    if (isMissingDirectoryError(error)) return []
    throw error
  }
}

function isMissingDirectoryError(error: unknown) {
  return (
    error instanceof Error &&
    "code" in error &&
    ((error as NodeJS.ErrnoException).code === "ENOENT" || (error as NodeJS.ErrnoException).code === "ENOTDIR")
  )
}

export function parseCodemakerModels(output: string): string[] {
  return uniqueStrings(
    output
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean),
  )
}

export function parseCodexModels(output: string): string[] {
  const data = parseJsonObjectFromOutput(output)
  if (!data || typeof data !== "object" || !Array.isArray((data as { models?: unknown }).models)) return []
  return uniqueStrings(
    (data as { models: unknown[] }).models
      .map((model) => (model && typeof model === "object" ? (model as { slug?: unknown }).slug : undefined))
      .filter((slug): slug is string => typeof slug === "string" && slug.trim().length > 0)
      .map((slug) => slug.trim()),
  )
}

function parseSkillMetadata(source: string) {
  const frontmatter = source.match(/^---\r?\n([\s\S]*?)\r?\n---/)
  const metadata = frontmatter?.[1] ?? ""
  const name = metadata.match(/^name:\s*(.+)$/m)?.[1]?.trim().replace(/^["']|["']$/g, "")
  const rawDescription = metadata.match(/^description:\s*(.+)$/m)?.[1]?.trim().replace(/^["']|["']$/g, "")
  const description = rawDescription && ![">", ">-", "|", "|-"].includes(rawDescription) ? rawDescription : firstHeading(source)
  return {
    name,
    description,
  }
}

function firstHeading(source: string) {
  return source.match(/^#\s+(.+)$/m)?.[1]?.trim()
}

async function readSkillManifest(dir: string): Promise<Record<string, { description?: string }>> {
  const source = await readFile(path.join(dir, "manifest.json"), "utf8").catch(() => undefined)
  if (!source) return {}
  try {
    const parsed = JSON.parse(source)
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, { description?: string }>)
      : {}
  } catch {
    return {}
  }
}

type ExecCommand = {
  command: string
  args: string[]
  windowsVerbatimArguments?: boolean
}

type ResolveCommandOptions = {
  platform?: NodeJS.Platform
  env?: NodeJS.ProcessEnv
  comspec?: string
  exists?: (file: string) => Promise<boolean>
}

export async function resolveCommandForExec(
  command: string,
  args: string[],
  options: ResolveCommandOptions = {},
): Promise<ExecCommand> {
  const platform = options.platform ?? process.platform
  if (platform !== "win32") return { command, args }

  const executable = await resolveWindowsCommand(command, options)
  if (!executable) return { command, args }

  const extension = path.extname(executable).toLowerCase()
  if (!WINDOWS_SCRIPT_EXTENSIONS.has(extension)) return { command: executable, args }

  return {
    command: options.comspec ?? process.env.ComSpec ?? "cmd.exe",
    args: ["/d", "/c", `call ${[executable, ...args].map(quoteWindowsShellArg).join(" ")}`],
    windowsVerbatimArguments: true,
  }
}

async function execFileText(command: string, args: string[]): Promise<string> {
  const resolved = await resolveCommandForExec(command, args)
  return new Promise((resolve, reject) => {
    execFile(
      resolved.command,
      resolved.args,
      {
        timeout: MODEL_COMMAND_TIMEOUT_MS,
        windowsHide: true,
        windowsVerbatimArguments: resolved.windowsVerbatimArguments,
      },
      (error, stdout, stderr) => {
        if (error) {
          reject(error)
          return
        }
        resolve(`${stdout ?? ""}${stderr ? `\n${stderr}` : ""}`)
      },
    )
  })
}

async function resolveWindowsCommand(command: string, options: ResolveCommandOptions) {
  const env = options.env ?? process.env
  const exists = options.exists ?? pathExists
  const hasPathSeparator = command.includes("/") || command.includes("\\")
  const hasExtension = path.extname(command).length > 0
  const pathExt = (env.PATHEXT || ".COM;.EXE;.BAT;.CMD")
    .split(";")
    .map((extension) => extension.trim())
    .filter(Boolean)
  const commandCandidates = hasExtension
    ? [command]
    : [...pathExt.map((extension) => `${command}${extension}`), command]
  const directories = hasPathSeparator ? [""] : (env.PATH || env.Path || "").split(path.delimiter).filter(Boolean)

  for (const directory of directories) {
    for (const candidate of commandCandidates) {
      const file = directory ? path.join(directory, candidate) : candidate
      if (await exists(file)) return file
    }
  }

  return undefined
}

function pathExists(file: string) {
  return access(file, constants.F_OK)
    .then(() => true)
    .catch(() => false)
}

function quoteWindowsShellArg(value: string) {
  return `"${value.replaceAll('"', '""')}"`
}

function parseJsonObjectFromOutput(output: string): unknown {
  const trimmed = output.trim()
  try {
    return JSON.parse(trimmed)
  } catch {
    const start = trimmed.indexOf("{")
    const end = trimmed.lastIndexOf("}")
    if (start === -1 || end === -1 || end <= start) throw new Error("CLI output did not contain JSON")
    return JSON.parse(trimmed.slice(start, end + 1))
  }
}

function uniqueStrings(values: string[]) {
  return Array.from(new Set(values))
}

function compareCatalogItems(a: BlueprintCatalogItem, b: BlueprintCatalogItem) {
  return a.label.localeCompare(b.label, undefined, { sensitivity: "base" })
}

function isCatalogItem(item: BlueprintCatalogItem | undefined): item is BlueprintCatalogItem {
  return item !== undefined
}
