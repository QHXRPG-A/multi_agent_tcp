# multi-agent-tcp Codex skill

This directory mirrors the active local Codex skill installed at
`C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp\`.

## Purpose

- Keep the project memory centered on `gulicode-bp` Codex plugin development,
  the local Blueprint web workbench, `/mobile`, `/console`,
  `GraphRuntimeControlPlane`, `GraphRuntime`, AgentNode queues,
  workspace/events, and `CLIWorkerBackend`.
- Make the plugin-first debug stack the default when the user says
  `调试启动`.
- Keep GuLiCode desktop/Electron as a secondary compatibility track for
  explicit desktop-shell, IPC, packaging, taskbar, or windowing work.
- Provide a stable place for skill knowledge, tasks, and archives that can be
  synced back to the installed skill tree.

## Current Main Line

```text
gulicode-bp Codex plugin
  -> local Blueprint web workbench
  -> GuLiCode app dev surfaces: /mobile and /console
  -> DesktopBlueprintService / GraphRuntimeControlPlane
  -> GraphRuntime
  -> AgentNode queues, workspace state, events
  -> CLIWorkerBackend adapters
```

The default debug startup does not start the GuLiCode Electron desktop shell.
Use explicit desktop docs and launchers only for desktop-specific work.

## Consistency Status

- Source snapshot: `F:\src\Package\Script\Python\multi_agent_tcp\KM_docs\skills-snapshot`
- Installed skill: `C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp`
- Update the snapshot and installed skill together when changing startup or
  product-center guidance.

## Included Content

- `SKILL.md`
- `environment_setup.md`
- `knowledge_base/`
- `tasks/`
- `archive/`
