import { execFile } from "node:child_process"
import { readdir, readFile } from "node:fs/promises"
import path from "node:path"

export type BlueprintCatalogItem = {
  value: string
  label: string
  description?: string
}

const RULE_EXTENSIONS = new Set([".md", ".txt", ".json", ".yaml", ".yml", ".toml"])
const MODEL_COMMAND_TIMEOUT_MS = 15_000

export async function listBlueprintDirectories(root: string): Promise<BlueprintCatalogItem[]> {
  if (!root.trim()) return []
  const entries = await readdir(root, { withFileTypes: true })
  return entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => ({
      value: path.join(root, entry.name),
      label: entry.name,
    }))
    .sort(compareCatalogItems)
}

export async function listBlueprintSkills(dir: string): Promise<BlueprintCatalogItem[]> {
  if (!dir.trim()) return []
  const [entries, manifest] = await Promise.all([readdir(dir, { withFileTypes: true }), readSkillManifest(dir)])
  const skills: Array<BlueprintCatalogItem | undefined> = await Promise.all(
    entries
      .filter((entry) => entry.isDirectory())
      .map(async (entry) => {
        const skillPath = path.join(dir, entry.name, "SKILL.md")
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
  if (!dir.trim()) return []
  const entries = await readdir(dir, { withFileTypes: true })
  return entries
    .filter((entry) => entry.isFile() && RULE_EXTENSIONS.has(path.extname(entry.name).toLowerCase()))
    .map((entry) => ({
      value: path.join(dir, entry.name),
      label: entry.name,
    }))
    .sort(compareCatalogItems)
}

export async function listBlueprintModels(cliKind: string): Promise<string[]> {
  if (cliKind === "codemaker") {
    const output = await execFileText("codemaker", ["models", "netease-codemaker"])
    return parseCodemakerModels(output)
  }
  if (cliKind === "codex") {
    const output = await execFileText("codex", ["debug", "models"])
    return parseCodexModels(output)
  }
  throw new Error(`Unsupported CLI kind: ${cliKind}`)
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

function execFileText(command: string, args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(command, args, { timeout: MODEL_COMMAND_TIMEOUT_MS, windowsHide: true }, (error, stdout, stderr) => {
      if (error) {
        reject(error)
        return
      }
      resolve(`${stdout ?? ""}${stderr ? `\n${stderr}` : ""}`)
    })
  })
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
