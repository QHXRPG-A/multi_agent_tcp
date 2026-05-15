# Environment Setup for Agents

This note is the fast path for bringing up the current `multi_agent_tcp` repo.
The project center is GuLiCode desktop plus the blueprint runtime; treat the
Python runtime and the Bun/Electron app as two cooperating parts.

## Repository Root

Current common root on this machine:

```powershell
F:\src\Package\Script\Python\multi_agent_tcp
```

Run Python commands either from this directory or from its parent with
`multi_agent_tcp` importable. The runtime tests currently work from the repo
root.

## Required Tools

Minimum practical tools:

- Python 3.10+.
- Git.
- Bun 1.3.x. `GuLiCode/package.json` pins `packageManager` to `bun@1.3.11`;
  this machine currently has Bun 1.3.13.
- At least one worker CLI on `PATH` for real AgentNode execution:
  `codemaker` and/or `codex`.

Current known-good local versions on 2026-05-15:

```powershell
python --version      # Python 3.13.5
bun --version         # 1.3.13
git --version         # 2.54.0.windows.1
codex --version       # codex-cli 0.125.0
codemaker --version   # 1.2.16-prod-0.0.30
```

## Python Runtime

There is no committed `requirements.txt` or `pyproject.toml` at repo root.
The code is mostly standard-library Python, with vendored Dulwich under
`vendor/dulwich`.

Recommended Python packages:

```powershell
python -m pip install pytest merge3
```

Notes:

- `pytest` is needed for the test suite.
- `merge3` is recommended by `README.md` for Dulwich-backed three-way text
  merges in the workspace changeset flow.
- Do not commit generated caches such as `.pytest_cache/`, `.pytest_tmp/`,
  `__pycache__/`, `logs/`, or local runtime output.

Useful Python checks from repo root:

```powershell
python -m py_compile agent_launch_context.py workspace_manager.py cluster.py codex_bridge.py workspace_rpc.py graph_runtime.py test_agent_runtime.py test_workspace_api.py test_workspace_manager.py
python -m pytest -q
```

Real Codex integration tests use external CLI/model service behavior. If a
combined run fails with `stream disconnected before response.completed`, rerun
the single target before treating it as a framework regression.

## GuLiCode Bun Workspace

Install JavaScript dependencies from the `GuLiCode` workspace root:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode
bun install
```

Important:

- Do not run tests from the `GuLiCode` root; `GuLiCode/bunfig.toml` points test
  root at `./do-not-run-tests-from-root`.
- Run package-specific tests/builds from package directories.
- `GuLiCode/bunfig.toml` forces `registry = "https://registry.npmjs.org/"`
  and `exact = true` to avoid inherited global npm registry issues.

## Desktop Bring-Up

Preferred Windows launcher:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
.\start-gulicode-desktop.cmd
```

Packaged smoke path:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
.\start-gulicode-desktop.cmd --packaged
```

Direct Bun entry, if needed:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode
bun run desktop
```

For local web UI work, run backend and app separately:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\opencode
bun run --conditions=browser ./src/index.ts serve --port 4096

cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun dev -- --port 4444
```

Open `http://localhost:4444`; it targets the backend at `http://localhost:4096`.

Do not restart an already running app/server unless the user explicitly asks.

## Focused UI Checks

Blueprint app checks:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run build
```

Desktop Electron checks:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-catalog.test.ts
bun run build
```

Known limitation: `bun run typecheck` in `packages/app` can still be blocked by
existing `src/custom-elements.d.ts` / `../../ui/src/custom-elements.d.ts`
content. Do not treat that as caused by unrelated blueprint or docs work unless
the touched code directly affects it.

## Packaging Notes on Windows

Normal command:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun run build
bun run package:win
```

Known Windows issue: `bun run package:win` can fail while extracting
`winCodeSign-2.6.0.7z` because symlink creation is denied. The documented local
workaround is to use a temporary `electron-builder.local.config.ts` that sets
`win.signAndEditExecutable = false`, then patch the final executable icon with
cached `rcedit`.

PowerShell helper to locate cached `rcedit`:

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

If packaging fails while clearing `dist/win-unpacked` with an access-denied
error on `d3dcompiler_47.dll`, close old `GuLiCode Dev.exe` processes that are
running from `dist/win-unpacked`, then rerun the same packaging command.

## Worker CLI Notes

The blueprint inspector exposes `cli_kind` values for `codemaker` and `codex`.
Model discovery uses:

```powershell
codemaker models netease-codemaker
codex debug models
```

Real Codex framework tests require a working `codex exec` setup and usable
`CODEX_HOME` runtime state (`config.toml`, `auth.json`, `models_cache.json`).
The framework creates private agent `CODEX_HOME` directories and copies only
runtime state plus authorized skills/rules.

## Skill Snapshot

The Codex skill source for this project is:

```powershell
C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp
```

The repository snapshot lives at:

```powershell
F:\src\Package\Script\Python\multi_agent_tcp\KM_docs\skills-snapshot
```

When updating the skill, mirror the source skill tree into
`KM_docs/skills-snapshot` so removed legacy files also disappear from the
snapshot.
