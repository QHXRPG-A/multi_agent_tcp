#!/usr/bin/env bun

import { mkdir, rm, writeFile } from "node:fs/promises"
import { join } from "node:path"

const opencodeDir = join(import.meta.dirname, "..", "..", "opencode")
const dist = join(opencodeDir, "dist", "node")

process.chdir(opencodeDir)

await rm(dist, { recursive: true, force: true })
await mkdir(dist, { recursive: true })

const result = await Bun.build({
  entrypoints: ["./src/node.ts"],
  target: "node",
  format: "esm",
  outdir: "./dist/node",
  entryNaming: "node.js",
  external: ["node-gyp", "jsonc-parser"],
})

if (!result.success) {
  for (const log of result.logs) {
    console.error(log)
  }
  process.exit(1)
}

await writeFile(join(dist, "models-snapshot.js"), "export const snapshot = {}\n")

const webUiStubDir = join(dist, "node_modules", "opencode-web-ui.gen.ts")
await mkdir(webUiStubDir, { recursive: true })
await writeFile(
  join(webUiStubDir, "package.json"),
  JSON.stringify({ name: "opencode-web-ui.gen.ts", type: "module", main: "./index.js" }, null, 2),
)
await writeFile(join(webUiStubDir, "index.js"), "export default {}\n")
