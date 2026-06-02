# Environment Setup for Agents

Last refreshed: 2026-05-29 on
`F:\src\Package\Script\Python\multi_agent_tcp`.

This is the fast path for bringing up the current `multi_agent_tcp` repo from
the archived GuLiCode / blueprint runtime handoff notes. The active product
center is the `gulicode-bp` Codex plugin plus the framework-owned blueprint
runtime. GuLiCode desktop/Electron is a secondary explicit track.

## Repository Root

Current root on this machine:

```powershell
F:\src\Package\Script\Python\multi_agent_tcp
```

Run package imports either from this repo root or from its parent:

```powershell
cd F:\src\Package\Script\Python
python -m multi_agent_tcp doctor --json
```

The installed `multi-agent-tcp.exe` console wrapper exists on PATH, but this
machine's Windows Application Control policy can block that generated exe.
Prefer the module entry point in automation:

```powershell
python -m multi_agent_tcp <command>
```

## Required Tools

Current observed local tools:

```powershell
python --version      # Python 3.13.5
git --version         # git version 2.54.0.windows.1
node --version        # v24.15.0
bun --version         # 1.3.13
codex.cmd --version   # codex-cli 0.125.0
```

Notes:

- `GuLiCode/package.json` declares `packageManager` as `bun@1.3.11`; Bun
  `1.3.13` has been used here successfully for focused tests.
- PowerShell script execution is disabled on this machine, so `codex` resolves
  first to `codex.ps1` and fails. Use `codex.cmd` or the WindowsApps
  `codex.exe` path for direct checks.
- `codex` is not currently on PATH. `python -m multi_agent_tcp doctor
  --json` reports `codex: true` and `codex: false`.

## Cross-Machine Setup Checklist

When bringing this repo up on another Windows computer, treat paths, console
wrappers, PowerShell policy, and proxy state as machine-local. Before running
MCP tests or GuLiCode desktop smoke:

1. Install Python 3.10+; the current local machine uses Python 3.13.5.
2. Install Git for Windows.
3. Install Bun. `GuLiCode/package.json` pins `bun@1.3.11`; Bun 1.3.13 is
   confirmed working here.
4. Install Node.js 22+ for ecosystem tooling; Node v24.15.0 is confirmed here.
5. Install Codex CLI when running live Codex workers; use `codex.cmd` on
   PowerShell-restricted Windows systems.
6. Install this checkout in editable mode with `python -m pip install -e .`.
7. Install focused test helpers with `python -m pip install pytest merge3`.
8. Install GuLiCode JS dependencies with `cd GuLiCode; bun install
   --frozen-lockfile`.
9. Install Playwright browsers when running browser/e2e smoke tests:
   `cd GuLiCode\packages\app; bunx playwright install chromium`.
10. Prefer `python -m multi_agent_tcp <command>` over the generated
   `multi-agent-tcp.exe` wrapper in automation.
11. Use `codex.cmd` or the WindowsApps `codex.exe` path when PowerShell blocks
   `codex.ps1`.
12. Run `python -m multi_agent_tcp doctor --json` and confirm the expected
   worker CLI reports `true`.
13. Set localhost proxy bypass variables before MCP HTTP tests:

```powershell
$env:NO_PROXY = '127.0.0.1,localhost,::1'
$env:no_proxy = $env:NO_PROXY
```

If another machine reports MCP `502 Bad Gateway`, `503 Service Unavailable`,
empty HTTP bodies, or connection failures against `127.0.0.1:<random-port>`,
check the proxy bypass first. Windows system proxy settings can be inherited by
`httpx` even when `HTTP_PROXY` is not set in the shell.

## Python Runtime

The repo has a real `pyproject.toml`. Install this checkout in editable mode:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
python -m pip install -e .
python -m pip install pytest merge3
```

Current installed Python packages relevant to the archive:

```text
multi-agent-tcp 0.5.0, editable at F:\src\Package\Script\Python\multi_agent_tcp
pytest 9.0.3
merge3 0.0.16
fastapi 0.136.3
mcp 1.27.1
uvicorn 0.47.0
starlette 0.52.1
httpx 0.28.1
```

`pyproject.toml` currently declares the Collaboration Server and MCP/live
blueprint dependencies: `fastapi`, `mcp`, `uvicorn`, `starlette`, and `httpx`.
`merge3` is still recommended for Dulwich-backed three-way text merges in the
workspace changeset flow.

Useful Python checks:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
python -m py_compile __init__.py blueprint_mcp_runtime.py agent_launch_context.py graph_runtime.py graph_control.py workspace_rpc.py desktop_blueprint_service.py test_desktop_blueprint_service.py test_agent_runtime.py test_workspace_api.py test_workspace_manager.py codex_bridge.py
python -m multi_agent_tcp doctor --json
```

Known current proxy requirement:

- Windows system proxy is configured through the system proxy registry as
  `http://127.0.0.1:7897`. `httpx` reads that configuration when
  `trust_env=True`, even if no `HTTP_PROXY` environment variable is present.
  Without a localhost bypass, MCP tests that call `127.0.0.1:<random-port>` are
  sent through that proxy and can fail with empty-body `502 Bad Gateway`,
  `503 Service Unavailable`, or other proxy-originated connection errors.
- Set localhost bypass variables before MCP HTTP tests or desktop MCP smoke:

```powershell
$env:NO_PROXY = '127.0.0.1,localhost,::1'
$env:no_proxy = $env:NO_PROXY
```

With that bypass, these focused MCP HTTP tests pass:

```powershell
python -m pytest -q test_desktop_blueprint_service.py::test_run_mcp_streamable_http_tools_are_split_by_token test_desktop_blueprint_service.py::test_run_mcp_runtime_end_closes_tokens_and_records_control_audit -vv
```

## Skill List

The repo-local `skill_list` has been initialized:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
python -m multi_agent_tcp.init_skill_list
```

Current result:

```text
F:\src\Package\Script\Python\multi_agent_tcp\skill_list\manifest.json
```

The generated manifest is currently `{}` because no additional business skill
entries were discovered by the initializer in this checkout.

## GuLiCode Bun Workspace

Install or verify JavaScript dependencies from the GuLiCode workspace root:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode
bun install --frozen-lockfile
```

Current result: dependencies are already installed; the frozen install reported
no lockfile changes.

Important:

- Do not run tests from the `GuLiCode` root; the root `test` script exits by
  design.
- Run package-specific tests/builds from package directories.
- `GuLiCode/bunfig.toml` forces `registry = "https://registry.npmjs.org/"`
  and `exact = true`.

Focused UI/runtime checks from the current archive:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts

cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-catalog.test.ts ./src/main/blueprint-runtime.test.ts ./src/main/ipc-blueprint-runtime.test.ts
```

Current focused result: app blueprint tests passed, and desktop-electron
blueprint/runtime IPC tests passed.

## Plugin-First Debug Bring-Up

Preferred local debug launcher:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
.\start-gulicode-debug.cmd
```

Equivalent explicit plugin alias:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
.\start-gulicode-bp-plugin.cmd
```

This starts or verifies the Collaboration Server on `127.0.0.1:8787`, the
`gulicode-bp` workbench, the app dev server on `127.0.0.1:3040`, `/mobile`,
and `/console`. It skips the GuLiCode Electron desktop shell.

Use `-SkipWebBuild` for a faster loop when `GuLiCode/packages/app/dist` is
already current. Use `-NoOpen` to keep the browser closed.

## Explicit Desktop Bring-Up

Use this only for desktop-shell, IPC, packaging, taskbar, or windowing work:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
.\start-gulicode-desktop.cmd
```

Packaged smoke path:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
.\start-gulicode-desktop.cmd --packaged
```

Direct Bun entry:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode
bun run desktop
```

Explicit desktop debug startup after Electron main/preload IPC changes:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
$env:ELECTRON_ENABLE_LOGGING = '1'
$env:ELECTRON_ENABLE_STACK_DUMPING = '1'
Remove-Item Env:\DEBUG -ErrorAction SilentlyContinue
bun run dev
```

Do not use `DEBUG=*` by default; archived notes call out that it floods logs
with Vite/Babel traversal output. If IPC/preload handlers changed, restart the
whole Electron main process rather than only reloading the renderer.

## Blueprint Common Config

Current blueprint startup requires these common config fields:

- `python_path`: absolute Python interpreter path.
- `project_workdir`: absolute project directory.
- `skill_dir`: required only when selected Agents use skills.
- `rule_dir`: required only when selected Agents use rule files.

Python detection order from the archive:

```text
configured python_path -> GULICODE_PYTHON -> python -> python3 -> py -3 -> project/package .venv
```

The current interpreter path reported by `doctor` is:

```text
C:\Users\qiuhaoxuan\AppData\Local\Programs\Python\Python313\python.exe
```

## Packaging Notes on Windows

Normal packaging command:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun run build
bun run package:win
```

Known Windows issue from the archive: `bun run package:win` can fail while
extracting `winCodeSign-2.6.0.7z` because symlink creation is denied. The local
workaround is still the temporary `electron-builder.local.config.ts` +
`rcedit` path documented in
`KM_docs/skills-snapshot/knowledge_base/gulicode_desktop.md`.

If packaging fails while clearing `dist/win-unpacked` with an access-denied
error on `d3dcompiler_47.dll`, close old `GuLiCode Dev.exe` processes launched
from that output directory, then rerun the same packaging command.

## Skill Snapshot

The active Codex skill directory for this user is:

```powershell
C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp
```

It has been overwritten with the repository snapshot from:

```powershell
F:\src\Package\Script\Python\multi_agent_tcp\KM_docs\skills-snapshot
```

When updating the skill again, mirror the full snapshot tree, not only
`SKILL.md`, so removed legacy files also disappear.
