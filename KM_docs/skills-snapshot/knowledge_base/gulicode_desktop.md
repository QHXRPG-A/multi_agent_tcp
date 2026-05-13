# GuLiCode desktop knowledge

This document records the current effective knowledge for the local
`multi_agent_tcp/GuLiCode` desktop app.

## Position

- `GuLiCode` is the local vendor baseline derived from OpenCode.
- The preferred desktop entry on this machine is
  `GuLiCode/packages/desktop-electron/`.
- `GuLiCode/packages/desktop/` (Tauri) still exists, but it is currently a
  secondary path and requires Rust/Cargo.

## Current local roots

- Repository root: `F:\src\Package\Script\Python\multi_agent_tcp`
- GuLiCode root: `F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode`

Historical paths such as `D:\agents\multi_agent_tcp` may still appear in
archives or old notes. Treat them as historical unless the current machine
actually uses them.

## One-click startup (preferred)

Preferred entrypoints on this machine:

- Windows double-click:
  `F:\src\Package\Script\Python\multi_agent_tcp\start-gulicode-desktop.cmd`
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
  `packages/desktop-electron`
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

Longer-term blueprint integration should follow this shape:

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

Do not place real blueprint product logic in
`packages/desktop-electron/src/renderer/index.tsx`; that file is only the
desktop shell bootstrap.

## Test bring-up rule

When the user asks to start or verify GuLiCode on this machine:

- default to `start-gulicode-desktop.cmd` or `bun run desktop`
- do not default to Tauri
- verify success from the launcher log markers above
- prefer current local code and launcher behavior over older removed startup
  notes
- do not hardcode secrets into the skill; if provider configuration is needed,
  use user-provided values or the current local environment
