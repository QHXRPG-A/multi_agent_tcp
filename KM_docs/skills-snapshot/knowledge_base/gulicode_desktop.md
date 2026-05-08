# GuLiCode 桌面端知识

本文件沉淀 `multi_agent_tcp/GuLiCode` 中桌面端源码的当前有效知识。后续若要把蓝图系统嵌入 GuLiCode 桌面端，优先阅读本文件，再进入具体源码。

## 定位

`GuLiCode` 是从 OpenCode 项目拷贝并二开的本地 vendor baseline。当前仓库中保留了两套桌面端实现：

- `GuLiCode/packages/desktop-electron/`：Electron 桌面端。当前本机已验证可启动，是近期桌面深度开发的优先入口。
- `GuLiCode/packages/desktop/`：Tauri v2 桌面端。保留源码和配置，但本机当前缺 Rust/Cargo，启动会停在 `cargo metadata`。

桌面 UI 的主体并不写在桌面包里，而是复用共享应用包：

```text
packages/desktop-electron
  -> Electron main / preload / renderer shell
  -> 引入 packages/app 的 AppInterface

packages/desktop
  -> Tauri shell
  -> 引入 packages/app 的 AppInterface

packages/app
  -> 真正的 Solid UI、路由、layout、session、project、provider、terminal、file tree 等应用层
```

因此后续要嵌入蓝图系统，优先判断改动属于哪一层：

- 需要本地进程、文件系统、Python runtime、蓝图运行服务、原生窗口能力：改 `desktop-electron/src/main`、`preload`、IPC。
- 需要新增页面、面板、侧栏入口、状态视图、蓝图编辑器 UI：改 `packages/app`。
- 需要共用 UI 元件、主题、图标：改 `packages/ui`。

## 当前推荐启动入口

### Electron dev

根目录：

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode
bun --cwd packages/desktop-electron dev
```

脚本链路：

```text
root package.json dev:desktop
  -> bun --cwd packages/desktop-electron dev
  -> packages/desktop-electron scripts.predev
  -> bun ./scripts/predev.ts
  -> cd ../opencode && bun script/build-node.ts
  -> electron-vite dev
```

当前本机验证结果：

- Electron 窗口标题为 `GuLiCode`。
- Renderer dev server 端口通常是 `http://localhost:5173/`。
- 内嵌 OpenCode server 会由 Electron main 选择随机本地端口，例如 `http://127.0.0.1:2607`。
- server ready 后 renderer 通过 `window.api.awaitInitialization()` 获得 URL、username、password。

注意：本地曾缺失 `packages/opencode/script/build-node.ts`，导致 `predev` 报错：

```text
error: Module not found "script/build-node.ts"
```

Electron dev 需要该脚本生成：

```text
packages/opencode/dist/node/node.js
```

`packages/desktop-electron/electron.vite.config.ts` 中的 `virtual:opencode-server` 会解析到这个文件。

### Tauri dev

根目录：

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode
bun run --cwd packages/desktop tauri dev
```

当前本机限制：

- 需要 Rust / Cargo。
- 未安装时会报：

```text
failed to run 'cargo metadata' command ... program not found
```

Tauri 前端 dev server 默认：

```text
http://localhost:1420
```

单独跑 `packages/desktop` 的 Vite web dev 可能黑屏，因为桌面前端依赖 Tauri / Electron 注入的原生 API 与 sidecar 初始化，不适合作为完整效果判断。

## Electron 桌面端结构

### 入口文件

```text
packages/desktop-electron/
  package.json
  electron.vite.config.ts
  electron-builder.config.ts
  src/main/index.ts
  src/main/server.ts
  src/main/ipc.ts
  src/main/windows.ts
  src/preload/index.ts
  src/preload/types.ts
  src/renderer/index.tsx
  src/renderer/index.html
  src/renderer/loading.html
```

### `electron.vite.config.ts`

职责：

- 配置 Electron main / preload / renderer 三个构建目标。
- `main` 入口是 `src/main/index.ts`。
- `preload` 入口是 `src/preload/index.ts`。
- `renderer` root 是 `src/renderer`，入口包括 `index.html` 与 `loading.html`。
- 通过 `@opencode-ai/app/vite` 复用 app 包的 Vite 插件。
- 把 `virtual:opencode-server` 解析到 `../opencode/dist/node/node.js`。
- 将 `dist/node` 中的 `.wasm` 复制到 `out/main/chunks/`。
- 将 `@lydell/node-pty` 按平台收窄到 `@lydell/node-pty-${process.platform}-${process.arch}`。

### `src/main/index.ts`

职责：

- 设置 app 名称、app id、userData 路径：
  - dev: `GuLiCode Dev` / `ai.opencode.desktop.dev`
  - beta: `GuLiCode Beta` / `ai.opencode.desktop.beta`
  - prod: `GuLiCode` / `ai.opencode.desktop`
- 注册 `opencode://` deep link。
- 注册 renderer 自定义协议 `oc://renderer/`。
- 初始化 updater。
- 初始化本地 server、SQLite migration、loading window、main window。
- 注册 IPC handlers。
- 在退出、信号、relaunch 时停止本地 server。

重要流程：

```text
app.whenReady()
  -> registerRendererProtocol()
  -> setupAutoUpdater()
  -> initialize()
     -> getSidecarPort()
     -> migration if needed
     -> spawnLocalServer(hostname, port, password)
     -> serverReady.resolve({ url, username, password })
     -> createMainWindow()
```

这里的 `sidecar` 名称在 Electron 版本中有点历史包袱：实际不是启动外部 `opencode-cli.exe`，而是 main 进程通过 `virtual:opencode-server` 直接导入并监听本地 HTTP server。

### `src/main/server.ts`

职责：

- 管理默认 server URL 与 WSL 开关在 `electron-store` 中的持久化。
- 准备 server 环境变量。
- 导入 `virtual:opencode-server` 并调用 `Server.listen()`。
- 使用 Basic Auth 暴露本地 HTTP server。
- 做 `/global/health` 健康检查。

关键环境变量：

```text
OPENCODE_EXPERIMENTAL_ICON_DISCOVERY=true
OPENCODE_EXPERIMENTAL_FILEWATCHER=true
OPENCODE_CLIENT=desktop
OPENCODE_SERVER_USERNAME=opencode
OPENCODE_SERVER_PASSWORD=<randomUUID>
XDG_STATE_HOME=<app userData>
```

server 启动配置：

```ts
Server.listen({
  port,
  hostname,
  username: "opencode",
  password,
  cors: ["oc://renderer"],
})
```

### `src/main/windows.ts`

职责：

- 注册 `oc://renderer/` 协议并安全映射到 `out/renderer` 文件。
- 创建 main window 与 loading window。
- Windows 下使用 frameless window + hidden titlebar + `setTitleBarOverlay()`。
- 设置窗口图标、背景色、zoom 锁定。
- dev 模式下通过 `ELECTRON_RENDERER_URL` 加载 Vite renderer；打包模式下通过 `oc://renderer/index.html` 加载。

主窗口安全配置：

```ts
webPreferences: {
  preload: join(root, "../preload/index.js"),
  contextIsolation: true,
  nodeIntegration: false,
  sandbox: true,
}
```

这意味着 renderer 不应直接访问 Node / Electron。新增蓝图本地能力必须经 preload 暴露受控 API。

### `src/main/ipc.ts`

职责：

- 集中注册 Electron IPC handler。
- 桥接窗口、文件选择器、路径打开、剪贴板图片、通知、store、WSL path、markdown parse、updater、titlebar 等能力。

当前常用 IPC：

- `await-initialization`
- `get-window-config`
- `consume-initial-deep-links`
- `get-default-server-url`
- `set-default-server-url`
- `get-wsl-config`
- `set-wsl-config`
- `parse-markdown`
- `open-directory-picker`
- `open-file-picker`
- `save-file-picker`
- `open-path`
- `read-clipboard-image`
- `show-notification`
- `set-titlebar`
- `set-background-color`

未来嵌入蓝图系统时，建议新增 IPC 命名保持领域前缀，例如：

```text
blueprint:list
blueprint:open
blueprint:save
blueprint:run
blueprint:stop
blueprint:status
blueprint:event-stream
blueprint:agent-message
```

不要让 renderer 直接拼 shell 命令运行 Python；由 main 进程或本地 server 承担进程管理、路径校验和生命周期。

### `src/preload/index.ts` 与 `types.ts`

职责：

- 使用 `contextBridge.exposeInMainWorld("api", api)` 暴露 `window.api`。
- `types.ts` 定义 `ElectronAPI` 类型，renderer 依赖这份契约。

新增桌面原生能力时必须三处同步：

1. `src/main/ipc.ts` 注册 handler。
2. `src/preload/index.ts` 暴露函数。
3. `src/preload/types.ts` 扩展类型。

如果未来蓝图功能需要在 `packages/app` 里调用，`packages/app/src/app.tsx` 已声明了 `Window.api` 的局部类型；也需要同步扩展或更好地复用 preload 类型。

### `src/renderer/index.tsx`

职责：

- 初始化 i18n。
- 建立 desktop `Platform` 实现。
- 监听 deep link。
- 通过 `window.api.awaitInitialization()` 获取本地 sidecar server 凭据。
- 构造 `ServerConnection.Sidecar`，再渲染 `AppInterface`。
- 通过 `MemoryRouter` 承载 app 路由。

关键逻辑：

```text
createPlatform()
  -> platform: "desktop"
  -> native directory/file/save picker
  -> openPath/openLink/clipboard/notification
  -> electron-store backed storage
  -> WSL path conversion
  -> default server management
  -> markdown parse
  -> update/restart

sidecar = window.api.awaitInitialization()
servers() = [{ type: "sidecar", variant: "base", http: { url, username, password } }]
AppInterface(defaultServer = "sidecar", servers = servers(), router = MemoryRouter)
```

## `packages/app` 应用层结构

`packages/app` 是桌面端和 web 端共享的 Solid 应用层。

关键入口：

- `packages/app/src/index.ts`：对外导出 `AppBaseProviders`、`AppInterface`、`PlatformProvider`、`ServerConnection` 等。
- `packages/app/src/app.tsx`：全局 providers、路由、server connection gate、`AppInterface`。
- `packages/app/src/pages/layout.tsx`：主 shell、侧栏、项目/工作区/会话导航、titlebar、debug bar。
- `packages/app/src/pages/home.tsx`：首页。
- `packages/app/src/pages/directory-layout.tsx`：项目目录布局。
- `packages/app/src/pages/session.tsx`：会话页。
- `packages/app/src/context/platform.tsx`：平台能力抽象。
- `packages/app/src/context/server.tsx`：server 列表、sidecar/http/ssh/wsl connection model。
- `packages/app/src/context/global-sdk.tsx`：创建 SDK client、监听全局 SSE event stream。
- `packages/app/src/context/global-sync.tsx`：同步 server 数据。
- `packages/app/src/context/layout.tsx`：侧栏、项目、工作区、session tabs、file tree、terminal 等布局状态。

### 路由结构

`AppInterface` 当前路由：

```tsx
<Route path="/" component={HomeRoute} />
<Route path="/:dir" component={DirectoryLayout}>
  <Route path="/" component={SessionIndexRoute} />
  <Route path="/session/:id?" component={SessionRoute} />
</Route>
```

蓝图系统若作为 app 内页面，可能新增：

```text
/:dir/blueprint
/:dir/blueprint/:blueprintId
/:dir/blueprint/:blueprintId/run/:runId
```

同时需要在 `pages/layout.tsx` 的 sidebar / project panel 中加入口。

### Platform 抽象

`packages/app/src/context/platform.tsx` 定义了 Web/Desktop 能力边界。桌面端通过 renderer 的 `createPlatform()` 实现：

- 文件夹选择、文件选择、保存文件
- 打开外链、打开本地路径
- 通知
- async storage
- update/restart
- WSL 开关和路径转换
- markdown parse
- clipboard image
- zoom

蓝图 UI 如果需要本地能力，应优先扩展 `Platform` 或单独建 `BlueprintPlatform` context，而不是在 UI 组件里直接访问 Electron。

### Server 与 SDK

`ServerConnection` 支持：

- `http`
- `sidecar`，包括 base / wsl
- `ssh`

Electron 桌面端默认给 `AppInterface` 注入一个 `sidecar` server。`GlobalSDKProvider` 使用 `createSdkForServer()` 创建 SDK client，并通过 `global.event` SSE 监听事件。

蓝图系统未来有两种接入方式：

1. 扩展 OpenCode server API：让 `virtual:opencode-server` 提供蓝图相关 REST/SSE 能力，app 通过 SDK 访问。
2. 新增 Electron main IPC / 本地 Python runtime：main 进程启动 `multi_agent_tcp` 蓝图服务，renderer 通过 `window.api` 或平台 context 调用。

推荐长期方向是“本地蓝图 runtime server + app SDK/client + SSE 事件流”，这样能复用当前 `GlobalSDKProvider`、event stream、layout 和状态面板思路。

## Tauri 桌面端结构

`packages/desktop` 是 Tauri v2 版本：

- `package.json`：`dev` 是 Vite，`tauri` 是 Tauri CLI。
- `src-tauri/tauri.conf.json`：dev 配置，产品名 `GuLiCode Dev`，devUrl `http://localhost:1420`。
- `src-tauri/tauri.prod.conf.json`：prod 配置，产品名 `GuLiCode`。
- `src-tauri/sidecars/opencode-cli-*`：预期放置 sidecar CLI。

Tauri dev 预处理：

```text
packages/desktop/scripts/predev.ts
  -> getCurrentSidecar(RUST_TARGET)
  -> cd ../opencode && bun run build --single [--baseline]
  -> copyBinaryToSidecarFolder(...)
```

当前坑：

- `RUST_TARGET` 未设置时，单独 `bun --cwd packages/desktop dev` 会被 `predev` 拦下。
- `tauri dev` 需要 Cargo。
- Windows x64 配置当前倾向 `opencode-windows-x64-baseline`，本机曾遇到 Bun baseline executable 下载/解包失败。

近期若目标是快速桌面深度开发，优先走 Electron。Tauri 可作为后续打包/性能/原生集成方向再恢复。

## 打包与品牌残留

虽然 GuLiCode 已做了一轮品牌替换，桌面配置里仍有 OpenCode 残留：

- app id / identifier 仍是 `ai.opencode.desktop*`。
- deep link scheme 仍是 `opencode`。
- Electron artifact name 仍是 `opencode-electron-${os}-${arch}.${ext}`。
- Electron publish repo 仍指向 `anomalyco/opencode` 或 `anomalyco/opencode-beta`。
- Tauri updater endpoint 仍指向 `https://github.com/anomalyco/opencode/...`。
- Tauri / Electron rpm package name 仍是 `opencode*`。
- Tauri sidecar 名称仍是 `opencode-cli`。
- OpenCode server username 仍是 `opencode`。

后续正式发布 GuLiCode 桌面端前，需要统一：

- app id / bundle identifier
- deep link scheme
- artifact name
- package name
- updater endpoint
- publish repo
- icon / metadata / appstream
- sidecar binary name
- storage path / database path 是否从 `opencode` 迁移到 `gulicode`

不要在蓝图开发中顺手做大范围品牌替换，除非任务明确要求；这类改动影响发布、更新、数据库路径和 deep link。

## 蓝图系统嵌入建议

### 推荐架构

```text
Electron main
  -> 启动 GuLiCode/OpenCode sidecar server
  -> 启动或管理 multi_agent_tcp blueprint runtime
  -> 暴露 blueprint IPC 或本地 HTTP/SSE endpoint

preload
  -> window.api.blueprint.*

packages/app
  -> 新增 Blueprint route / panel / context
  -> 显示图编辑器、运行状态、agent 状态、changeset、conflict、artifact、report

multi_agent_tcp
  -> GraphRuntime / Workspace API / AgentNode / Ryven bridge
  -> 长期作为蓝图执行与多 agent 编排后端
```

### UI 嵌入点

优先考虑在 `packages/app` 新增：

- `src/pages/blueprint.tsx`
- `src/context/blueprint.tsx`
- `src/components/blueprint/*`

并在 `AppInterface` 路由里添加：

```text
/:dir/blueprint
/:dir/blueprint/:id
```

侧栏入口在 `pages/layout.tsx` / `pages/layout/sidebar-*` 相关组件中接入。不要把蓝图 UI 写死在 `packages/desktop-electron/src/renderer/index.tsx`，那里只是桌面 shell。

### 运行时接入点

短期可用 IPC：

```text
window.api.blueprint.list()
window.api.blueprint.open(path)
window.api.blueprint.save(data)
window.api.blueprint.run(id, options)
window.api.blueprint.stop(runId)
window.api.blueprint.status(runId)
window.api.blueprint.subscribe(runId)
```

中长期更适合本地 server：

- Electron main 启动 Python `multi_agent_tcp` blueprint service。
- service 提供 REST + SSE/WebSocket。
- renderer 通过 SDK/client 消费状态。
- run events 映射到 UI：`RunStarted`、`AgentStateChanged`、`TaskCompleted`、`ChangesetAccepted`、`ConflictDetected` 等。

### 与 OpenCode session 的关系

GuLiCode 当前主模型是“项目 -> session -> message/tool/file/terminal”。蓝图系统不应该直接替代 session，而应先作为项目级工作台：

- 一个项目可以有多个 blueprint。
- 一个 blueprint run 可以启动多个 AgentNode。
- AgentNode 可以使用 Codex/OpenCode CLI adapter，也可把结果汇入 OpenCode session。
- 蓝图 run 的结果应链接到 reports/artifacts/changesets，而不是只塞进聊天消息。

### 权限与安全

遵守现有桌面安全边界：

- renderer sandbox 开启，不能直接使用 Node。
- 所有本地能力走 preload 暴露的窄 API。
- main 进程负责路径校验、进程生命周期、token 管理。
- 蓝图 runtime 不应把真实 skill 目录、RPC token、agent 私有目录泄露给 renderer 或普通 agent。
- 对项目文件写入仍应走 `checkout -> diff -> submit` 或框架定义的 Workspace API。

## 已验证启动记录

本机验证过的 Electron dev 关键日志：

```text
electron main process built successfully
electron preload scripts built successfully
dev server running for the electron renderer process at http://localhost:5173/
starting electron app...
app starting { version: '1.14.19', packaged: false }
sidecar connection started { url: 'http://127.0.0.1:<port>' }
spawning sidecar
loading task finished
init step { phase: 'done' }
server ready { url: 'http://127.0.0.1:<port>' }
```

进程中可看到：

```text
electron      MainWindowTitle: GuLiCode
electron-vite packages/desktop-electron
node          renderer dev server
bun           --cwd packages/desktop-electron dev
```

## 维护提醒

- 桌面端深度开发优先从 Electron 路线入手，Tauri 暂作为备用路线。
- 修改桌面 native 能力时同时更新 main / preload / preload types / app 类型声明。
- 修改主界面、路由、侧栏、项目页、session 页时优先在 `packages/app` 中做。
- 修改蓝图执行后端时优先在 `multi_agent_tcp` 中沉淀 GraphRuntime / Workspace API / event 模型，再给 GuLiCode 桌面端接 UI。
- 本知识文档记录当前有效结构；大规模迁移历史或品牌替换历史应追加到 `archive/gulicode_runtime_baseline_archive.md`。
