# Debug Start Workflow

Trigger phrase: when the user says `调试启动`, bring up the local
plugin-first GuLiCode Blueprint debug stack without asking for another plan.

Use the current repo root unless the user gives another checkout:

```powershell
F:\src\Package\Script\Python\multi_agent_tcp
```

## Preferred Startup

Default one-click debug startup:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
.\start-gulicode-debug.cmd
```

Equivalent explicit plugin entry:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
.\start-gulicode-bp-plugin.cmd
```

This starts or reuses:

- Collaboration Server on `127.0.0.1:8787`
- `gulicode-bp` local Blueprint workbench at
  `http://127.0.0.1:<port>/<project>/blueprint-window/<blueprint>`
- GuLiCode app dev server on `127.0.0.1:3040`
- mock mobile client at `http://127.0.0.1:3040/mobile`
- server console at `http://127.0.0.1:3040/console`

It does not start the GuLiCode Electron desktop shell. Use
`start-gulicode-desktop.cmd` only for explicit desktop-shell, IPC, packaging,
taskbar, or windowing work.

Useful flags:

```powershell
.\start-gulicode-debug.cmd -NoOpen
.\start-gulicode-debug.cmd -SkipWebBuild
.\start-gulicode-debug.cmd -SkipPluginInstall
.\start-gulicode-debug.cmd -BlueprintId default
```

## Services

1. Collaboration Server:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
$env:NO_PROXY = '127.0.0.1,localhost,::1'
$env:no_proxy = $env:NO_PROXY
python -m multi_agent_tcp collaboration-server --host 127.0.0.1 --port 8787 --db logs/collaboration_server.sqlite3 --seed-config examples/collaboration_server_debug_seed.json --log-dir logs --log-level INFO
```

2. Plugin Blueprint workbench:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
python plugins\gulicode-bp\scripts\install_personal_plugin.py --force
python plugins\gulicode-bp\scripts\start_workbench.py --project-dir . --blueprint-id default
```

The workbench serves the built GuLiCode app through the plugin HTTP bridge and
injects only the local workbench token. It reuses
`DesktopBlueprintService` / `GraphRuntimeControlPlane` as the runtime source of
truth.

3. Mock mobile client:

Start the app dev server on the current safe mobile debug port `3040`.
Port `3000` can be unavailable on Windows machines where it falls inside a
system TCP exclusion range.

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun run dev -- --host 127.0.0.1
```

Open:

```text
http://127.0.0.1:3040/mobile
```

Sign in with the debug seed user:

```text
username: 1
password: 1
```

4. Server console:

Open:

```text
http://127.0.0.1:3040/console
```

Sign in with the debug seed admin user:

```text
username: 1
password: 1
```

The console monitors users, mobile/desktop presence, active sessions, and
recent client logs. Console login does not mark the browser as a mobile or
desktop client.

## Verification

- Collaboration Server health: `http://127.0.0.1:8787/api/health`
- Plugin workbench: check the URL printed by `start-gulicode-debug.cmd`
- Mobile page: `http://127.0.0.1:3040/mobile`
- Server console: `http://127.0.0.1:3040/console`
- Electron desktop: skipped by default

The script writes the workbench ready payload to:

```text
logs/gulicode-bp-workbench-ready.json
```

and workbench process logs to:

```text
logs/gulicode-bp-workbench.out.log
logs/gulicode-bp-workbench.err.log
```

## Explicit Desktop Debug

For desktop-specific work only:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
.\start-gulicode-desktop.cmd
```

Fallback direct entry:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode
bun run desktop
```

Do not use `DEBUG=*` by default for Electron; it floods Vite/Babel logs.
