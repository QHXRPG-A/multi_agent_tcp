/**
 * Vendor 副本可能不包含 packages/opencode；仅在存在时执行上游的 fix-node-pty。
 */
import { spawnSync } from "node:child_process"
import { existsSync } from "node:fs"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"

const root = resolve(fileURLToPath(new URL("..", import.meta.url)))
const marker = resolve(root, "packages/opencode/package.json")

if (!existsSync(marker)) {
  console.log("[GuLiCode] packages/opencode missing — skip fix-node-pty.")
  process.exit(0)
}

const r = spawnSync("bun", ["run", "--cwd", "packages/opencode", "fix-node-pty"], {
  cwd: root,
  stdio: "inherit",
  shell: process.platform === "win32",
})
process.exit(r.status ?? (r.error ? 1 : 0))
