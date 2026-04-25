# GuLiCode

GuLiCode is a rebuildable, runnable baseline copied from the upstream OpenCode workspace and intended for gradual integration into `multi_agent_tcp`.

Upstream:
- Repository: https://github.com/anomalyco/opencode
- License: MIT
- Local source baseline: `multi_agent_tcp/opencode/`

Rebuild policy:
- Keep workspace/package structure required for Bun startup
- Exclude generated dependencies and local build caches such as `node_modules`, `dist`, `.next`, `.turbo`, `.sst`, and `.git`
- Preserve upstream license and core workspace metadata so the baseline remains runnable

Important:
- This directory is meant to stay bootable first, then be trimmed incrementally with repeated startup verification.
- If `GuLiCode` is mentioned publicly, clarify that it is an independent project derived from OpenCode and is not affiliated with the OpenCode team.

## 二开与本 vendor 副本的差异

当前副本**不包含**上游的 `packages/opencode`（终端 TUI CLI）。根目录默认 **`bun run dev`** 已改为启动 **`dev:web`**（`packages/app`）。

| 命令 | 说明 |
|------|------|
| `bun install` | 在 `GuLiCode/` 下安装；`bunfig.toml` 使用 `registry.npmjs.org`，避免子目录继承全局内网 npm 源导致 Bun 在 Windows 上缓存报错。 |
| `bun run dev` / `bun run dev:web` | Web 前端（Vite） |
| `bun run dev:desktop` | Electron 桌面 |
| `bun run dev:console` | Console 应用（跨平台；若遇 macOS 句柄上限可改用 `dev:console:unix`） |
| `bun run dev:cli` | 上游 TUI；**仅当**已自行恢复 `packages/opencode` 时使用 |

`postinstall` 仅在存在 `packages/opencode` 时执行 `fix-node-pty`；否则跳过。`prepare`（husky）仅在 **GuLiCode 为 git 根目录** 时执行，避免作为 `multi_agent_tcp` 子目录时把 hooks 装到父仓库。
