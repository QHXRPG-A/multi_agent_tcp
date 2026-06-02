# GuLiCode desktop knowledge

This document records the current effective knowledge for the local
`multi_agent_tcp/GuLiCode` desktop app. Desktop work is now secondary to the
`gulicode-bp` Codex plugin path; use this file when the user explicitly asks
for Electron, desktop shell, IPC, packaging, taskbar, or windowing behavior.

## Position

- `GuLiCode` is the local vendor baseline derived from OpenCode.
- The default Blueprint debug entrypoint is the `gulicode-bp` plugin workbench,
  not the Electron desktop shell.
- The preferred desktop entry on this machine is
  `GuLiCode/packages/desktop-electron/` only for explicit desktop work.
- `GuLiCode/packages/desktop/` (Tauri) still exists, but it is currently a
  secondary path and requires Rust/Cargo.
- For productization, branding, blueprint entry embedding, and icon/taskbar
  rules, pair this file with [`guli_desktop_ui.md`](guli_desktop_ui.md).

## Current local roots

- Repository root: `F:\src\Package\Script\Python\multi_agent_tcp`
- GuLiCode root: `F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode`

Historical paths such as `D:\agents\multi_agent_tcp` may still appear in
archives or old notes. Treat them as historical unless the current machine
actually uses them.

## Explicit Desktop Startup

Use these entrypoints only when desktop-shell behavior is part of the task:

- Windows double-click:
  `F:\src\Package\Script\Python\multi_agent_tcp\start-gulicode-desktop.cmd`
- Windows packaged smoke:
  `F:\src\Package\Script\Python\multi_agent_tcp\start-gulicode-desktop.cmd --packaged`
- Cross-platform terminal:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode
bun run desktop
```

- Skip old-process cleanup only when needed:

```powershell
bun run desktop -- --no-clean
```

### What the launcher does

The launcher is implemented by
`GuLiCode/scripts/dev-desktop.ts` and is wired to both `desktop` and
`dev:desktop` in `GuLiCode/package.json`.

It:

- resolves `bun` from `PATH`, `%USERPROFILE%\.bun\bin\bun.exe`, or
  `%LOCALAPPDATA%\Programs\bun\bun.exe`
- runs `bun install --ignore-scripts` if
  `packages/desktop-electron/node_modules/electron-vite/bin/electron-vite.js`
  is missing
- runs `bun --cwd packages/opencode script/build-node.ts` if
  `packages/opencode/dist/node/node.js` is missing
- kills stale `GuLiCode`-scoped `electron` / `bun` processes unless
  `--no-clean` is passed
- launches `bun node_modules/electron-vite/bin/electron-vite.js dev` inside
  `packages/desktop-electron` in dev mode
- or, in packaged mode, runs `electron-builder --win --dir`, writes output to
  `packages/desktop-electron/dist/packaged-launch/current`, and patches the
  final `GuLiCode Dev.exe` icon with `rcedit`
- tees stdout and stderr to
  `GuLiCode\logs\gulicode-desktop-direct.log`

### Verified success markers

Successful startup should produce all or most of these markers:

- `electron main process built successfully`
- `electron preload scripts built successfully`
- renderer dev server at `http://localhost:5173/`
- `starting electron app...`
- `init step { phase: 'done' }`
- `server ready { url: 'http://127.0.0.1:<port>' }`

Packaged startup should additionally converge to:

- `GuLiCode/packages/desktop-electron/dist/packaged-launch/current/win-unpacked/GuLiCode Dev.exe`
- Electron main log line `main window created`

### Direct fallback

Use this only when the launcher itself is unavailable or under repair:

```powershell
Set-Location -LiteralPath 'F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron'
bun node_modules/electron-vite/bin/electron-vite.js dev
```

Prefer the one-click launcher over older notes that say
`bun --cwd packages/desktop-electron dev` directly.

## Desktop source layering

```text
packages/desktop-electron
  -> Electron main / preload / renderer shell
  -> imports packages/app AppInterface

packages/desktop
  -> Tauri shell
  -> imports packages/app AppInterface

packages/app
  -> Solid app UI, routes, layout, session, project, provider,
     terminal, file tree, and other shared application surfaces
```

Desktop/UI productization files worth checking in the same round:

```text
packages/app/src/components/session/session-header.tsx
packages/app/src/components/session/session-new-view.tsx
packages/ui/src/components/icon.tsx
scripts/dev-desktop.ts
```

When deciding where to edit:

- native process, filesystem, Python runtime, local services, and secure OS
  capabilities belong in `packages/desktop-electron/src/main`,
  `src/preload`, and IPC
- app pages, sidebar entrypoints, panels, and blueprint UI belong in
  `packages/app`
- shared UI components and theme work belong in `packages/ui`

## Electron build and runtime notes

Important files:

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

Current important behaviors:

- `electron.vite.config.ts` resolves `virtual:opencode-server` to
  `../opencode/dist/node/node.js`
- renderer currently needs the `ghostty-web` alias and copied `.wasm` assets
  to keep the terminal/session UI healthy
- the Electron "sidecar" is not an external `opencode-cli.exe`; the main
  process imports the local bundled server through `virtual:opencode-server`
- renderer runs sandboxed; native capabilities must go through preload and IPC
- packaged app identity on Windows depends on both runtime icon loading and the
  final packaged `exe` resource icon

### Windows packaging and icon flow

Use this when the user asks for a Windows package or installer, not just the
unpacked smoke launched by `start-gulicode-desktop.cmd --packaged`.

Baseline build:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun run build
bun run package:win
```

Known local packaging pitfall:

- A normal `bun run package:win` can fail while electron-builder extracts
  `winCodeSign-2.6.0.7z`.
- The failure is Windows symlink privilege during extraction of bundled
  `darwin/10.12/lib/libcrypto.dylib` and `libssl.dylib`, not a GuLiCode app
  build failure.
- If that happens, do not change renderer/app code. Use the local workaround
  below or rerun from a Windows session with Developer Mode/elevated symlink
  privileges.

Local workaround used successfully on 2026-05-14:

1. Create a temporary `electron-builder.local.config.ts` in
   `GuLiCode/packages/desktop-electron`.
2. Import the base `electron-builder.config`.
3. Override `win.signAndEditExecutable` to `false`.
4. Add an `afterPack` hook that runs cached `rcedit-x64.exe` with
   `--set-icon resources/icons/icon.ico` against the final exe.
5. Run electron-builder with the temporary config, then delete the temporary
   config so it is not committed as product configuration.

Temporary config shape:

```ts
import { execFile } from "node:child_process"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { promisify } from "node:util"
import base from "./electron-builder.config"

const execFileAsync = promisify(execFile)
const packageDir = path.dirname(fileURLToPath(import.meta.url))

export default {
  ...base,
  win: { ...(base.win ?? {}), signAndEditExecutable: false },
  async afterPack(context: any) {
    if (context.electronPlatformName !== "win32") return
    const rceditDir = process.env.ELECTRON_BUILDER_RCEDIT_PATH
    if (!rceditDir) throw new Error("ELECTRON_BUILDER_RCEDIT_PATH is required")
    const executable = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.exe`)
    const icon = path.join(packageDir, "resources", "icons", "icon.ico")
    await execFileAsync(path.join(rceditDir, "rcedit-x64.exe"), [executable, "--set-icon", icon])
  },
}
```

PowerShell runner:

```powershell
$rceditDir = (Get-ChildItem $env:LOCALAPPDATA\electron-builder\Cache\winCodeSign -Directory |
  Where-Object {
    (Test-Path (Join-Path $_.FullName 'rcedit-x64.exe')) -and
    (Test-Path (Join-Path $_.FullName 'rcedit-ia32.exe'))
  } | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName

$env:CSC_IDENTITY_AUTO_DISCOVERY = 'false'
$env:ELECTRON_BUILDER_RCEDIT_PATH = $rceditDir
bunx electron-builder --win --config electron-builder.local.config.ts
```

Successful 2026-05-14 outputs:

```text
GuLiCode/packages/desktop-electron/dist/opencode-electron-win-x64.exe
GuLiCode/packages/desktop-electron/dist/opencode-electron-win-x64.exe.blockmap
GuLiCode/packages/desktop-electron/dist/win-unpacked/GuLiCode Dev.exe
```

Observed successful artifact times on 2026-05-14:

```text
dist/opencode-electron-win-x64.exe             18:13:35, 149.29 MB
dist/opencode-electron-win-x64.exe.blockmap    18:13:37, 0.16 MB
dist/win-unpacked/GuLiCode Dev.exe             18:13:03, 212.66 MB
```

If electron-builder fails before packaging with access denied while removing
`dist/win-unpacked/d3dcompiler_47.dll`, the old unpacked app is probably still
running from the output directory. Close or kill only those
`GuLiCode Dev.exe` processes whose executable path is under
`GuLiCode/packages/desktop-electron/dist/win-unpacked`, then rerun the same
workaround command. This is separate from the `winCodeSign` symlink issue.

If `dist/win-unpacked/GuLiCode Dev.exe` shows the wrong icon, patch the exe
directly with the same cached `rcedit-x64.exe --set-icon resources/icons/icon.ico`
and regenerate the installer with the `afterPack` hook.

## Tauri status

Tauri remains secondary on this machine:

- entry path:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode
bun run --cwd packages/desktop tauri dev
```

- it requires Rust/Cargo
- current local troubleshooting and validation should default to Electron
- a standalone `packages/desktop` Vite page is not enough to prove desktop
  correctness because the real app expects Tauri/Electron-injected APIs

## Blueprint integration guidance

Desktop blueprint integration remains a compatibility track. The default
plugin-first path serves the Blueprint workbench through `gulicode-bp` and
reuses `DesktopBlueprintService` / `GraphRuntimeControlPlane` directly.

When working on explicit desktop integration, follow this shape:

```text
Electron main
  -> starts GuLiCode/OpenCode local server
  -> starts or manages multi_agent_tcp blueprint runtime
  -> exposes blueprint IPC or local HTTP/SSE endpoints

preload
  -> window.api.blueprint.*

packages/app
  -> blueprint routes, panels, context, run status, agent status,
     changesets, conflicts, artifacts, and reports
```

Do not revive a separate legacy visual-editor product line.

Do not place real blueprint product logic in
`packages/desktop-electron/src/renderer/index.tsx`; that file is only the
desktop shell bootstrap.

## Test bring-up rule

When the user asks to start or verify GuLiCode on this machine:

- default to the plugin-first workflow in `debug_start.md` when the request is
  ordinary `调试启动` or Blueprint workbench debugging
- use `start-gulicode-desktop.cmd` or `bun run desktop` only when the request is
  explicitly about Electron desktop behavior
- use `start-gulicode-desktop.cmd --packaged` for packaged-smoke and taskbar/icon verification
- do not default to Tauri
- verify success from the launcher log markers above
- prefer current local code and launcher behavior over older removed startup
  notes
- do not hardcode secrets into the skill; if provider configuration is needed,
  use user-provided values or the current local environment
