# GuLiCode 运行基线变更归档

本文件只记录 `multi_agent_tcp` 在 GuLiCode / OpenCode 运行基线方向上的历史变更，便于后续回顾。

## 变更记录

### 2026-04-25 — 归档结构重组：新增专题文档并同步 GuLiCode 启动基线

#### 摘要
1. 在 skill 目录下新增 `archive/` 子目录，用于按主题拆分长期归档。
2. 新增 GuLiCode 专题归档，记录从精简快照策略切换为“完整可启动 workspace 基线”的方法。
3. 确认 OpenCode 根许可证为 MIT，可作为项目内源码基线引入并大改，但需保留许可证与来源说明。
4. 验证 `multi_agent_tcp/GuLiCode/` 的最小 CLI 入口可以运行，说明当前基线已具备继续裁剪与迁移的前提。

#### 涉及
- `archive/gulicode_runtime_baseline_archive.md`
- `multi_agent_tcp/GuLiCode`

---

## 当前结论

### 背景

本方向的目标是在 `multi_agent_tcp` 中引入 OpenCode 的合适部分，并建立一个可逐步迁移、可持续裁剪的启动基线，而不是只保存零散源码快照。

### 结论

- OpenCode 根许可证为 MIT，可作为项目内源码基线引入并大改，但需保留许可证与来源说明。
- 仅抽取少量 package 的“精简版 GuLiCode”无法可靠启动，workspace 依赖、`catalog:` 引用与内部包导出会断裂。
- 因此策略调整为：先重建为完整可启动 workspace 基线，再逐步裁剪。

### 最终结构

已在项目内建立：

```text
multi_agent_tcp/GuLiCode/
```

并按“完整 workspace，排除缓存/产物”的原则重建，保留：

- `package.json`
- `bun.lock`
- `bunfig.toml`
- `tsconfig.json`
- `turbo.json`
- `sst.config.ts`
- `sst-env.d.ts`
- `packages/`
- `sdks/`
- `github/`
- `patches/`
- `.opencode/`
- `LICENSE`
- `README.vendor.md`

同时删除：

- `node_modules`
- `dist`
- `.next`
- `.turbo`
- `.sst`
- `.git`

### 启动验证结论

本轮已验证：

```bash
bun run --cwd packages/opencode --conditions=browser src/index.ts --help
```

可成功运行，并输出 OpenCode CLI 帮助信息，期间还完成了一次数据库迁移。

这意味着当前 `GuLiCode` 已具备：

- 完整 workspace 结构
- Bun 依赖解析能力
- 可运行的最小启动基线

### 方法论结论

对这种重度 workspace/monorepo 项目，正确迁移顺序应为：

1. 先建立完整可启动基线
2. 每裁一次就复测启动
3. 在持续可运行的前提下逐步收缩到最小核心

而不是先做静态精简快照再试图补齐缺失依赖。

### 后续建议

1. 对 `GuLiCode` 做“可验证裁剪”，每删一组 package 就做一次启动测试。
2. 优先识别并保留最核心的：
   - `packages/opencode`
   - `packages/shared`
   - 视情况保留 `packages/plugin`、`packages/script`、`packages/sdk/js`
3. 后续再逐步做去 OpenCode 化：
   - 改项目名
   - 改入口
   - 改包边界
   - 去掉不需要的 provider / UI / 平台面

---

### 2026-05-07 - GuLiCode 品牌替换、项目级 CLI 入口与启动验证

#### 摘要

1. 在 `multi_agent_tcp/GuLiCode/` 内完成一轮 GuLiCode 品牌化重构：将用户可见的 `OpenCode` 描述替换为 `GuLiCode`。
2. CLI 展示名从 `opencode` 调整为 `gulicode`，帮助信息、server 描述、TUI 项目位置描述、mDNS 默认说明等已同步。
3. 新增项目级命令入口，使终端可以直接输入 `GuLiCode` 或 `gulicode` 拉起当前 GuLiCode。
4. 修正 TUI 首页中心像素 logo：原先仍显示 `opencode`，已替换为 `GULI CODE` 字模。
5. 完成最小 CLI、version、headless server、全局命令入口 smoke 验证。

#### 涉及文件

- `multi_agent_tcp/GuLiCode/package.json`
- `multi_agent_tcp/GuLiCode/bin/gulicode`
- `multi_agent_tcp/GuLiCode/packages/opencode/src/index.ts`
- `multi_agent_tcp/GuLiCode/packages/opencode/src/cli/cmd/serve.ts`
- `multi_agent_tcp/GuLiCode/packages/opencode/src/cli/cmd/web.ts`
- `multi_agent_tcp/GuLiCode/packages/opencode/src/cli/cmd/run.ts`
- `multi_agent_tcp/GuLiCode/packages/opencode/src/cli/cmd/pr.ts`
- `multi_agent_tcp/GuLiCode/packages/opencode/src/cli/cmd/uninstall.ts`
- `multi_agent_tcp/GuLiCode/packages/opencode/src/cli/cmd/upgrade.ts`
- `multi_agent_tcp/GuLiCode/packages/opencode/src/cli/cmd/tui/attach.ts`
- `multi_agent_tcp/GuLiCode/packages/opencode/src/cli/cmd/tui/thread.ts`
- `multi_agent_tcp/GuLiCode/packages/opencode/src/cli/network.ts`
- `multi_agent_tcp/GuLiCode/packages/opencode/src/cli/logo.ts`
- `multi_agent_tcp/GuLiCode/packages/opencode/src/cli/ui.ts`
- 以及 README、i18n、desktop/web/console、SDK/OpenAPI 等用户可见文案文件。

#### 当前启动方式

项目内部仍以 `packages/opencode/src/index.ts` 为运行入口，当前推荐命令为：

```powershell
GuLiCode --help
GuLiCode
GuLiCode serve --hostname 127.0.0.1 --port 4096
GuLiCode run "hello"
```

项目级入口实现：

```text
GuLiCode/bin/gulicode
```

该入口会转发到：

```powershell
bun run --cwd packages/opencode --conditions=browser src/index.ts
```

本机已在 `GuLiCode/` 下执行：

```powershell
bun link
```

因此当前 Windows 环境里：

```powershell
where.exe gulicode
```

可解析到：

```text
C:\Users\qiuhaoxuan\.bun\bin\gulicode.exe
```

#### 验证结果

已验证：

```powershell
GuLiCode --help
GuLiCode --version
bun run --cwd packages/opencode --conditions=browser src/index.ts --help
bun run --cwd packages/opencode --conditions=browser src/index.ts --version
GuLiCode serve --hostname 127.0.0.1 --port 43993 --print-logs
```

结论：

- `GuLiCode --help` 成功，顶部 wordmark 显示 `GULI CODE`，命令前缀显示 `gulicode`。
- `GuLiCode --version` 成功，输出 `local`。
- `GuLiCode serve` 成功拉起 headless server，HTTP 探测返回 `200`。
- server stdout 显示 `GuLiCode server listening on http://127.0.0.1:<port>`。

#### 仍保留的运行期 OpenCode 标识

以下内容暂时保留，因为仍是当前启动链、依赖解析或配置兼容的一部分：

- `packages/opencode/` 目录名
- `.opencode/` 配置目录
- `@opencode-ai/*` workspace/package 依赖名
- `OPENCODE_*` 环境变量
- `~/.config/opencode` 与 `~/.local/share/opencode` 等用户配置/数据路径
- `opencode` 主题名、插件生态引用、旧插件名兼容信息

这些属于下一阶段深度迁移，不应在未做完整兼容层和数据迁移前机械替换。

#### 当前已知非阻塞提示

- 未设置 `OPENCODE_SERVER_PASSWORD` 时，server 会提示无密码保护；这不影响本地 smoke 启动。
- `.opencode/opencode.jsonc` 中仍可能加载 `oh-my-opencode@latest`，启动时会提示应改为 `oh-my-openagent@latest`；当前不影响 GuLiCode 拉起。
