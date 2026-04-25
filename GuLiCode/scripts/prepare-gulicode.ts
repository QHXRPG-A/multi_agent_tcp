/**
 * 仅在 GuLiCode 为 git 根目录时启用 husky，避免作为子目录时把 hooks 装到 multi_agent_tcp 父仓。
 */
import { execSync, spawnSync } from "node:child_process"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"

const root = resolve(fileURLToPath(new URL("..", import.meta.url)))

try {
  const top = execSync("git rev-parse --show-toplevel", {
    encoding: "utf8",
    cwd: root,
  }).trim()
  if (resolve(top) !== resolve(root)) {
    console.log("[GuLiCode] skip husky: this folder is not the git root.")
    process.exit(0)
  }
} catch {
  console.log("[GuLiCode] skip husky: not a git repository or git unavailable.")
  process.exit(0)
}

const r = spawnSync("husky", [], { cwd: root, stdio: "inherit", shell: process.platform === "win32" })
process.exit(r.status ?? (r.error ? 1 : 0))
