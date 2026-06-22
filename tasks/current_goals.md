# Current Goals

Date: 2026-06-11

## Active Focus

The current product focus is the `gulicode-bp` Codex plugin and POPO-triggered
Blueprint execution path after the run-slot model removal.

Temporarily deprioritize GuLiCode desktop shell, mobile `/mobile`, console
`/console`, and hosted/server product work unless the user explicitly asks for
one of those surfaces. Treat them as compatibility or historical context, not as
the default implementation direction.

## Priority Work

1. Keep the installed `gulicode-bp` plugin reliable as the primary Blueprint
   workbench and runtime entrypoint.
2. Keep the POPO robot callback path routed through
   `blueprint.sessions.message`.
3. Harden Blueprint session instance routing:
   - stable session keys
   - one saved start AgentNode per blueprint
   - one Blueprint session maps to one live run instance
   - the same session reuses its active run
   - a new POPO/UI session creates a new run instance without a framework slot
     capacity limit
   - clear ambiguous-Blueprint, timeout, and terminal replies
4. Keep Codex desktop control split into two explicit actions:
   - set the saved start AgentNode
   - execute a caller-provided plan against that saved start AgentNode
5. Preserve MCP boundaries:
   - public Codex tools may inspect, monitor, set start Agent, and execute an
     explicit plan
   - session message and POPO config remain internal service/workbench/POPO
     paths
6. Validate packaged-plugin behavior after source changes:
   - rebuild the GuLiCode app bundle when frontend source changes
   - refresh the personal plugin mirror and Codex cache
   - restart the singleton service when stale runtime code is still active

## Near-Term Test Focus

- Backend tests for session persistence, session-instance routing, POPO routing,
  idle termination, and MCP public/internal command boundaries.
- Workbench browser smoke for plugin-served Blueprint session UI and session
  message entrypoint.
- POPO bot smoke for p2p/group identity mapping and failure messages.
- Installed-plugin smoke after singleton restart.

## Not In Scope For Now

- GuLiCode Electron desktop shell, taskbar, packaging, or IPC work.
- Mobile PWA or `/mobile` collaboration workflows.
- `/console` server-console workflows.
- Hosted/server-side product expansion beyond the local plugin singleton
  service required by `gulicode-bp`.
