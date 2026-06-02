import { mkdtemp, mkdir, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { describe, expect, test } from "bun:test"

import {
  listBlueprintDirectories,
  listBlueprintRules,
  listBlueprintSkills,
  parseCodexModels,
  resolveCommandForExec,
} from "./blueprint-catalog"

describe("blueprint catalog", () => {
  test("parses Codex model slugs from debug JSON", () => {
    expect(
      parseCodexModels(
        JSON.stringify({
          models: [{ slug: "gpt-5.4" }, { slug: "gpt-5.4-mini" }, { id: "ignored" }, { slug: "gpt-5.4" }],
        }),
      ),
    ).toEqual(["gpt-5.4", "gpt-5.4-mini"])
  })

  test("resolves Windows command shims before extensionless files", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "blueprint-commands-"))
    await writeFile(path.join(root, "codex"), "")
    await writeFile(path.join(root, "codex.cmd"), "")

    const resolved = await resolveCommandForExec("codex", ["debug", "models"], {
      platform: "win32",
      env: { PATH: root, PATHEXT: ".EXE;.CMD" },
      comspec: "cmd.exe",
    })

    expect(resolved.command).toBe("cmd.exe")
    expect(resolved.args.slice(0, 2)).toEqual(["/d", "/c"])
    expect(resolved.args[2]?.toLowerCase()).toBe(
      `call "${path.join(root, "codex.cmd").toLowerCase()}" "debug" "models"`,
    )
  })

  test("runs Windows exe commands directly", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "blueprint-commands-"))
    const command = path.join(root, "codex.exe")
    await writeFile(command, "")

    const resolved = await resolveCommandForExec("codex", ["debug", "models"], {
      platform: "win32",
      env: { PATH: root, PATHEXT: ".EXE;.CMD" },
      comspec: "cmd.exe",
    })

    expect(resolved.command.toLowerCase()).toBe(command.toLowerCase())
    expect(resolved.args).toEqual(["debug", "models"])
  })

  test("scans skills by subdirectory SKILL.md and uses manifest descriptions as enrichment", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "blueprint-skills-"))
    await mkdir(path.join(root, "alpha"))
    await mkdir(path.join(root, "ignored"))
    await writeFile(path.join(root, "alpha", "SKILL.md"), "---\nname: alpha-skill\ndescription: fallback\n---\n# Alpha\n")
    await writeFile(
      path.join(root, "manifest.json"),
      JSON.stringify({
        alpha: { description: "manifest description" },
      }),
    )

    expect(await listBlueprintSkills(root)).toEqual([
      {
        value: "alpha",
        label: "alpha-skill",
        description: "manifest description",
      },
    ])
  })

  test("treats missing catalog directories as empty lists", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "blueprint-missing-catalog-"))
    const missing = path.join(root, "missing")

    expect(await listBlueprintDirectories(missing)).toEqual([])
    expect(await listBlueprintSkills(missing)).toEqual([])
    expect(await listBlueprintRules(missing)).toEqual([])
  })

  test("scans direct rule files with common text extensions", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "blueprint-rules-"))
    await writeFile(path.join(root, "agent.md"), "# Agent")
    await writeFile(path.join(root, "policy.yaml"), "name: policy")
    await writeFile(path.join(root, "binary.png"), "")

    expect(await listBlueprintRules(root)).toEqual([
      { value: "agent.md", label: "agent.md" },
      { value: "policy.yaml", label: "policy.yaml" },
    ])
  })
})
