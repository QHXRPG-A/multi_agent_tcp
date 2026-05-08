# GuLiCode desktop startup debug notes - 2026-05-09

本文记录本次在 Windows / PowerShell 环境中启动 `GuLiCode` 桌面 app 时遇到的问题、定位过程和当前可用修复。工作目录：

```powershell
D:\agents\multi_agent_tcp\GuLiCode
```

## 当前可用启动方式

根目录脚本 `bun run dev:desktop` 会进入 `packages/desktop-electron` 的 Electron dev 启动链路，但当前环境里 Bun 生成的 `.bin` shim 有损坏风险。因此本次采用直接执行 `electron-vite` JS 入口的方式：

```powershell
Set-Location -LiteralPath 'D:\agents\multi_agent_tcp\GuLiCode\packages\desktop-electron'
bun node_modules/electron-vite/bin/electron-vite.js dev
```

后台启动并写日志时使用：

```powershell
$root = 'D:\agents\multi_agent_tcp\GuLiCode'
$log = Join-Path $root 'logs\gulicode-desktop-direct.log'
$cmd = "Set-Location -LiteralPath '$root\packages\desktop-electron'; bun node_modules/electron-vite/bin/electron-vite.js dev *> '$log'"
Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-Command',$cmd) -WindowStyle Hidden
```

成功启动时应看到：

- `electron.exe` 主窗口标题为 `GuLiCode`
- renderer dev server 监听 `http://localhost:5173`
- 日志中出现 `electron main process built successfully`
- 日志中出现 `electron preload scripts built successfully`
- 日志中出现 `init step { step: { phase: 'done' } }`
- 日志中出现 `server ready { url: 'http://127.0.0.1:<port>' }`

## 问题 1：Bun 依赖安装和 bin shim 异常

### 现象

直接执行：

```powershell
bun run dev:desktop
```

曾出现：

```text
Bun failed to remap this bin to its proper location within node_modules.
This is an indication of a corrupted node_modules directory.
```

以及：

```text
error: script "dev" exited with code 255
```

运行 `bun install` 时还出现过 native/postinstall 相关错误：

```text
error: install script from "tree-sitter-powershell" exited with 255
error: postinstall script from "esbuild" exited with 1
error: postinstall script from "protobufjs" exited with 1
```

### 临时处理

先用不执行 install scripts 的方式恢复依赖树：

```powershell
bun install --ignore-scripts
```

再绕过 `.bin` shim，直接执行实际 JS 入口：

```powershell
bun node_modules/electron-vite/bin/electron-vite.js dev
```

这个处理让 `packages/desktop-electron` 的 Electron/Vite 启动链路继续向前推进。

### 注意

`bun install --ignore-scripts` 可以恢复大量 JS 依赖链接，但不会补跑 native 包的 postinstall。若后续遇到 native binary 缺失，应单独处理对应包，而不是盲目反复 `bun install --force`。

## 问题 2：`ghostty-web` 无法被 Vite 解析

### 现象

Electron 主进程和 sidecar 已经启动，但 renderer 页面显示错误。日志中出现：

```text
Pre-transform error: Failed to resolve import "ghostty-web" from "../app/src/components/terminal.tsx".
Plugin: vite:import-analysis
File: D:/agents/multi_agent_tcp/GuLiCode/packages/app/src/components/terminal.tsx:34:18
```

浏览器侧可表现为：

```text
TypeError: Failed to fetch dynamically imported module:
http://localhost:5173/@fs/D:/agents/multi_agent_tcp/GuLiCode/packages/app/src/pages/session.tsx
```

### 根因

`packages/app/src/pages/session.tsx` 是动态加载的 session 页面。它静态依赖：

```text
pages/session.tsx
  -> pages/session/terminal-panel
  -> components/terminal.tsx
  -> import("ghostty-web")
```

当前安装出的 `ghostty-web` GitHub 依赖目录有实际构建产物：

```text
packages/app/node_modules/ghostty-web/dist/ghostty-web.js
packages/app/node_modules/ghostty-web/dist/index.d.ts
packages/app/node_modules/ghostty-web/dist/ghostty-vt.wasm
```

但包根目录没有 `package.json`。Vite 按包名解析 `ghostty-web` 时找不到入口，因此 `terminal.tsx` 预转换失败，进一步导致 `session.tsx` 动态 chunk 请求失败。

### 已采用修复

在 `GuLiCode/packages/desktop-electron/electron.vite.config.ts` 的 renderer 配置中加入显式 alias：

```ts
import { fileURLToPath } from "node:url"

// ...

renderer: {
  plugins: [appPlugin],
  publicDir: "../../../app/public",
  root: "src/renderer",
  resolve: {
    alias: {
      "ghostty-web": fileURLToPath(new URL("../app/node_modules/ghostty-web/dist/ghostty-web.js", import.meta.url)),
    },
  },
  // ...
}
```

这样 Vite 不再依赖 `ghostty-web/package.json`，而是直接解析到实际存在的 ESM 入口。

### 验证方式

重启 Electron dev server 后检查日志：

```powershell
Select-String -LiteralPath 'D:\agents\multi_agent_tcp\GuLiCode\logs\gulicode-desktop-direct.log' `
  -Pattern 'ghostty-web|Failed to fetch dynamically imported module|Pre-transform error|Internal server error|Could not resolve|Failed to resolve|session.tsx' `
  -Context 2,6
```

修复后不应再出现上述错误。

还可以直接请求 Vite 编译后的 session 页面：

```powershell
Invoke-WebRequest -UseBasicParsing `
  -Uri 'http://localhost:5173/@fs/D:/agents/multi_agent_tcp/GuLiCode/packages/app/src/pages/session.tsx' `
  -TimeoutSec 20
```

本次验证结果：

```text
status=200
```

## 问题 3：日志中的 `NativeCommandError` 容易误判

### 现象

PowerShell 日志中有类似：

```text
bun : ../opencode/dist/node/node.js (...): Use of eval ... is strongly discouraged
CategoryInfo          : NotSpecified
FullyQualifiedErrorId : NativeCommandError
```

### 判断

这是 PowerShell 把 Bun 写到 stderr 的 warning 包装成 `NativeCommandError` 展示，并不等于启动失败。是否失败应继续看后续是否出现：

- `electron main process built successfully`
- `electron preload scripts built successfully`
- `starting electron app`
- `init step { step: { phase: 'done' } }`
- renderer 是否有 `Pre-transform error` / `Internal server error`

本次真正阻塞 renderer 的错误是 `ghostty-web` 解析失败，不是 eval warning。

## 清理旧进程和端口

重复启动前建议先停掉上一次 GuLiCode 相关的 Electron/Bun 进程，避免端口和单实例锁干扰：

```powershell
$root = 'D:\agents\multi_agent_tcp\GuLiCode'
Get-CimInstance Win32_Process |
  Where-Object {
    ($_.Name -in @('electron.exe','bun.exe')) -and
    ($_.ExecutablePath -like "$root*" -or $_.CommandLine -like "*$root*")
  } |
  ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }
```

检查端口：

```powershell
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -in 5173,1420,4096 } |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

## 后续建议

1. 优先确认 `ghostty-web` 上游包是否应补 `package.json`。如果可以修上游，alias 可以变成临时兼容层。
2. 若继续维护 Electron 桌面入口，可把 direct 启动命令固化为 Windows dev helper，避免依赖 Bun `.bin` shim。
3. 若需要彻底修复 Bun 安装状态，应单独排查 native postinstall 的 `Operation not permitted`，不要在已有可运行状态下反复重建整个 `node_modules`。
4. 本文记录的是 `packages/desktop-electron` 入口；`packages/desktop` 的 Tauri 入口是另一条链路，需要 Rust/Tauri 前置条件，排障结论不能直接混用。
