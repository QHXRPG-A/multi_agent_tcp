import { mkdtemp, mkdir, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { describe, expect, test } from "bun:test"

import { listBlueprintRules, listBlueprintSkills, parseCodemakerModels, parseCodexModels } from "./blueprint-catalog"

describe("blueprint catalog", () => {
  test("parses CodeMaker models from line output", () => {
    expect(parseCodemakerModels("netease-codemaker/kimi-k2.5\n\nother/model\nother/model\n")).toEqual([
      "netease-codemaker/kimi-k2.5",
      "other/model",
    ])
  })

  test("parses Codex model slugs from debug JSON", () => {
    expect(
      parseCodexModels(
        JSON.stringify({
          models: [{ slug: "gpt-5.4" }, { slug: "gpt-5.4-mini" }, { id: "ignored" }, { slug: "gpt-5.4" }],
        }),
      ),
    ).toEqual(["gpt-5.4", "gpt-5.4-mini"])
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

  test("scans direct rule files with common text extensions", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "blueprint-rules-"))
    await writeFile(path.join(root, "agent.md"), "# Agent")
    await writeFile(path.join(root, "policy.yaml"), "name: policy")
    await writeFile(path.join(root, "binary.png"), "")

    expect((await listBlueprintRules(root)).map((item) => item.label)).toEqual(["agent.md", "policy.yaml"])
  })
})
