# Current Short-Term Goals

Last cleaned: 2026-05-13

## Current Main Line

The active project direction is:

```text
Guli productization
  -> blueprint embedded in GuLiCode desktop
  -> GraphRuntimeControlPlane
  -> GraphRuntime
  -> AgentNode queues, outgoing batches, joins, workspace/events
  -> CLIWorkerBackend adapters
```

Primary design source:

- [`../多agents通信设计.md`](../多agents通信设计.md)
- [`guli_desktop_ui_tasks.md`](guli_desktop_ui_tasks.md)
- [`multi_agent_communication_tasks.md`](multi_agent_communication_tasks.md)
- [`../knowledge_base/gulicode_desktop.md`](../knowledge_base/gulicode_desktop.md)
- [`../knowledge_base/guli_desktop_ui.md`](../knowledge_base/guli_desktop_ui.md)
- [`../knowledge_base/core_architecture.md`](../knowledge_base/core_architecture.md)

## Recently Completed Baseline

This round has already established the first usable desktop/UI baseline:

- One-click packaged startup now uses `start-gulicode-desktop.cmd --packaged`.
- Packaged output is stabilized at `GuLiCode/packages/desktop-electron/dist/packaged-launch/current/win-unpacked/GuLiCode Dev.exe`.
- Packaged startup now waits for renderer assets, tolerates `electron-builder` partial Windows sign-tool noise, and patches the final `exe` icon with `rcedit`.
- Packaged main-window bring-up is hardened against off-screen saved window state and icon-load failures inside the Electron main process.
- Desktop icon assets have been replaced for `dev` / `beta` / `prod`.
- The new-session empty state now shows `GULI`.
- The session header now contains a blueprint entry button with placeholder feedback and i18n wiring.

## Active Priorities

1. Finish the blueprint open logic from the new header button into a dedicated desktop route, panel, or workbench entry.
2. Define the first productized blueprint workbench layout inside `GuLiCode/packages/app` instead of building a separate visual-editor product surface.
3. Bind GuLiCode UI to runtime/control-plane status surfaces for runs, agents, outgoing batches, joins, workspace changes, artifacts, and reports without duplicating scheduling semantics in the renderer.
4. Keep desktop startup stable in both dev and packaged flows, with evidence-based smoke checks and fixed launcher behavior.
5. Continue brand unification across desktop window title, taskbar identity, packaged icons, empty states, and any remaining user-visible `OpenCode` wording.
6. Expose top-agent/operator audit surfaces, such as utterance history and runtime explanations, only in top-level UI views and not as ordinary-Agent message context.
7. Keep workspace/archive behavior aligned with framework-owned changeset, conflict, report, artifact, and reference records.
8. Keep Tauri secondary on this machine; Electron remains the default bring-up and verification path.

## 2026-05-13 Testing Focus

1. Desktop packaged smoke:
   - Run `F:\src\Package\Script\Python\multi_agent_tcp\start-gulicode-desktop.cmd --packaged`.
   - Verify the produced app launches from `dist/packaged-launch/current/win-unpacked/GuLiCode Dev.exe`.
   - Verify Electron main log reaches `main window created`.

2. Icon and branding smoke:
   - Verify the packaged `exe` carries the GuLiCode icon.
   - Verify the new-session center surface still says `GULI`.
   - Verify the session header blueprint button renders and shows placeholder feedback.

3. Blueprint embedding smoke:
   - Verify the blueprint entry remains in the desktop chrome.
   - When open logic is wired, verify it routes into a GuLiCode-owned surface rather than a standalone editor shell.

4. Runtime/UI contract smoke:
   - Keep the rule that renderer surfaces consume runtime/control-plane state instead of rebuilding graph scheduling locally.
   - Keep durable Agent outputs flowing through framework APIs: `agent.dispatch`, Workspace API, `join.contribute`, and later structured task APIs.

## Deferred / Secondary Tracks

### CLI backend adapters

Continue maintaining Codex/CodeMaker adapters and `CLIWorkerBackend`, but do not let adapter mechanics drive product architecture.

See [`multi_cli_adapter_tasks.md`](multi_cli_adapter_tasks.md).

### Legacy Ryven/editor line

The old Ryven/editor UI line was removed from the active skill snapshot on 2026-05-13. Recover it from git history or old archives only if the user explicitly asks to restart that track.

## Validation Snapshot

Most recent desktop productization smoke observed during this round:

```text
F:\src\Package\Script\Python\multi_agent_tcp\start-gulicode-desktop.cmd --packaged
-> builds packaged desktop app
-> patches final exe icon
-> launches GuLiCode Dev from dist/packaged-launch/current/win-unpacked

C:\Users\qiuhaoxuan\AppData\Roaming\ai.opencode.desktop.dev\logs\main.log
-> creating main window
-> main window created
```
