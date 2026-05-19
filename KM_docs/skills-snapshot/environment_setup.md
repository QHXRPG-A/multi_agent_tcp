# Environment Setup for Agents

Last refreshed: 2026-05-20 on `D:\agent\multi_agent_tcp`.

This is the fast path for bringing up the current `multi_agent_tcp` repo from
the archived GuLiCode / blueprint runtime handoff notes. The active product
center is the GuLiCode desktop app plus the framework-owned blueprint runtime.

## Repository Root

Current root on this machine:

```powershell
D:\agent\multi_agent_tcp
```

Run package imports either from this repo root or from its parent:

```powershell
cd D:\agent
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
python --version      # Python 3.13.13
git --version         # git version 2.54.0.windows.1
bun --version         # 1.3.14
codex.cmd --version   # codex-cli 0.130.0
```

Notes:

- `GuLiCode/package.json` declares `packageManager` as `bun@1.3.11`; Bun
  `1.3.14` has been used here successfully for focused tests.
- PowerShell script execution is disabled on this machine, so `codex` resolves
  first to `codex.ps1` and fails. Use `codex.cmd` or the WindowsApps
  `codex.exe` path for direct checks.
- `codemaker` is not currently on PATH. `python -m multi_agent_tcp doctor
  --json` reports `codex: true` and `codemaker: false`.

## Python Runtime

The repo has a real `pyproject.toml`. Install this checkout in editable mode:

```powershell
cd D:\agent\multi_agent_tcp
python -m pip install -e .
python -m pip install pytest merge3
```

Current installed Python packages relevant to the archive:

```text
multi-agent-tcp 0.5.0, editable at D:\agent\multi_agent_tcp
pytest 9.0.3
merge3 0.0.16
mcp 1.27.1
uvicorn 0.47.0
starlette 0.52.1
httpx 0.28.1
```

`pyproject.toml` currently declares the MCP/live blueprint dependencies:
`mcp`, `uvicorn`, `starlette`, and `httpx`. `merge3` is still recommended for
Dulwich-backed three-way text merges in the workspace changeset flow.

Useful Python checks:

```powershell
cd D:\agent\multi_agent_tcp
python -m py_compile __init__.py blueprint_mcp_runtime.py agent_launch_context.py graph_runtime.py graph_control.py workspace_rpc.py desktop_blueprint_service.py test_desktop_blueprint_service.py test_agent_runtime.py test_workspace_api.py test_workspace_manager.py codex_bridge.py
python -m multi_agent_tcp doctor --json
```

Known current proxy requirement:

- Windows system proxy is configured through the system proxy registry as
  `http://127.0.0.1:7897`. `httpx` reads that configuration when
  `trust_env=True`, even if no `HTTP_PROXY` environment variable is present.
  Without a localhost bypass, MCP tests that call `127.0.0.1:<random-port>` are
  sent through that proxy and fail with empty-body `502 Bad Gateway`.
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
cd D:\agent\multi_agent_tcp
python -m multi_agent_tcp.init_skill_list
```

Current result:

```text
D:\agent\multi_agent_tcp\skill_list\manifest.json
```

The generated manifest is currently `{}` because no additional business skill
entries were discovered by the initializer in this checkout.

## GuLiCode Bun Workspace

Install or verify JavaScript dependencies from the GuLiCode workspace root:

```powershell
cd D:\agent\multi_agent_tcp\GuLiCode
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
cd D:\agent\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts

cd D:\agent\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-catalog.test.ts ./src/main/blueprint-runtime.test.ts ./src/main/ipc-blueprint-runtime.test.ts
```

Current focused result: app blueprint tests passed, and desktop-electron
blueprint/runtime IPC tests passed.

## Desktop Bring-Up

Preferred Windows launcher:

```powershell
cd D:\agent\multi_agent_tcp
.\start-gulicode-desktop.cmd
```

Packaged smoke path:

```powershell
cd D:\agent\multi_agent_tcp
.\start-gulicode-desktop.cmd --packaged
```

Direct Bun entry:

```powershell
cd D:\agent\multi_agent_tcp\GuLiCode
bun run desktop
```

Clean debug startup after Electron main/preload IPC changes:

```powershell
cd D:\agent\multi_agent_tcp\GuLiCode\packages\desktop-electron
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
C:\Users\13429\AppData\Local\Programs\Python\Python313\python.exe
```

## Packaging Notes on Windows

Normal packaging command:

```powershell
cd D:\agent\multi_agent_tcp\GuLiCode\packages\desktop-electron
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
C:\Users\13429\.codex\skills\multi-agent-tcp
```

It has been overwritten with the repository snapshot from:

```powershell
D:\agent\multi_agent_tcp\KM_docs\skills-snapshot
```

When updating the skill again, mirror the full snapshot tree, not only
`SKILL.md`, so removed legacy files also disappear.
