# Debug Start Workflow

Trigger phrase: when the user says `调试启动`, bring up the local GuLiCode
debug stack without asking for another plan.

Use the current repo root unless the user gives another checkout:

```powershell
F:\src\Package\Script\Python\multi_agent_tcp
```

## Services To Start

Preferred one-click debug startup:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
.\start-gulicode-debug.cmd
```

This starts or reuses the Collaboration Server, GuLiCode desktop, the app dev
server, `/mobile`, and `/console`.

1. Collaboration Server:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
$env:NO_PROXY = '127.0.0.1,localhost,::1'
$env:no_proxy = $env:NO_PROXY
python -m multi_agent_tcp collaboration-server --host 127.0.0.1 --port 8787 --db logs/collaboration_server.sqlite3 --log-dir logs --log-level INFO
```

For the local mobile write-loop smoke, include the repo debug seed:

```powershell
python -m multi_agent_tcp collaboration-server --host 127.0.0.1 --port 8787 --db logs/collaboration_server.sqlite3 --seed-config examples/collaboration_server_debug_seed.json --log-dir logs --log-level INFO
```

2. GuLiCode desktop:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
.\start-gulicode-desktop.cmd
```

Fallback direct entry:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode
bun run desktop
```

3. Mock mobile client:

Start the app dev server on the current safe mobile debug port `3040`.
Port `3000` can be unavailable on Windows machines where it falls inside a
system TCP exclusion range.
Open:

```text
http://127.0.0.1:3040/mobile
```

Start it directly when it is not already running:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun run dev -- --host 127.0.0.1
```

The Vite app dev server proxies `/api/*` to the Collaboration Server at
`http://127.0.0.1:8787` by default. Override the target with
`GULICODE_COLLABORATION_API_URL` if needed.

Then open the same `/mobile` URL and sign in with the debug seed user:

```text
username: 1
password: 1
```

The debug seed creates one project and an active placeholder runtime binding so
mobile planning requests can be created before the desktop runtime bridge is
fully registered. Approving a generated plan still requires a real desktop
runtime binding.

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

The console is read-only in the current debug workflow. It monitors users,
mobile/desktop presence, active sessions, and recent client logs. Console login
does not mark the browser as a mobile or desktop client.

## Verification

- Collaboration Server health: `http://127.0.0.1:8787/api/health`
- Mobile page: `http://127.0.0.1:3040/mobile`
- Server console: `http://127.0.0.1:3040/console`
- Desktop renderer health on this Windows machine:
  `http://[::1]:5173/`
- Desktop success markers commonly include renderer dev server, Electron app
  started, and sidecar server ready.

## Notes

- `/mobile` keeps mock/logged-out fallback if API auth or same-origin routing is
  unavailable. This is expected for mock-mobile debug.
- Do not use `DEBUG=*` by default for Electron; it floods Vite/Babel logs.
- Prefer background helper processes for servers; keep the Electron window
  visible because the user needs to inspect the desktop app.
- If `127.0.0.1:5173` times out but `http://[::1]:5173/` returns `200`, treat
  the desktop renderer as reachable through IPv6 loopback. A stale Windows TCP
  listener can remain on `127.0.0.1:5173` even after its owning process exits.
  The dev Electron window should keep the original `localhost` renderer URL
  instead of forcing it to `127.0.0.1`.
