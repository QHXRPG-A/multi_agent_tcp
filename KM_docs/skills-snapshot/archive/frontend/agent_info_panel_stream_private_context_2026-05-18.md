# Agent Info Panel Stream Cleanup And Private Context Gap - 2026-05-18

## Scope

This archive records the follow-up GuLiCode blueprint Agent information panel
debug pass after the Test Agent JSON v2 and interaction work. It also records
the architecture gap discovered while testing Test Agent behavior in packaged
desktop builds.

## Completed In This Pass

- Test Agent debug JSON is now a lightweight v2 message snapshot:
  `agentReplies`, `userMessages`, and `frameworkMessages`.
- The fixed JSON path remains:
  `%APPDATA%\ai.opencode.desktop.dev\logs\agent-info-panel-tests\agent-panel-test.json`.
- The v2 JSON intentionally omits raw `node`, `panel`, `runtime`,
  `streamEvents`, and raw event payloads.
- Framework API names are translated before JSON write; raw interface names
  are not persisted for panel-debug use.
- The Agent information panel no longer shows raw `status` JSON or
  `message.started` entries in the visible transcript.
- Latest status fields are projected into structured UI:
  state, queue, messages, busy count, current message, update time, last error,
  and collapsed technical details.
- The panel can be moved outside the visible canvas after it opens.
- Panel display text is selectable/copyable.
- Panel body wheel scrolling stays inside the panel instead of zooming the
  underlying blueprint canvas.
- The visible transcript filters noisy framework/runtime events:
  `status`, `message.started`, `queue.updated`, `tool.started`,
  `tool.completed`, stderr deltas, reasoning deltas, and Codex internal log
  lines such as `codex_core::exec` / Windows sandbox errors.
- User-facing `part.delta` and `message.completed` text is grouped per
  `message_id` and displayed as the Agent reply card.
- Windows packaging was rerun after the cleanup. The latest package produced:
  `GuLiCode/packages/desktop-electron/dist/opencode-electron-win-x64.exe`.

## Critical Finding

The Test Agent appearing unaware of the multi-agent framework exposed a broader
desktop runtime issue:

- Desktop blueprint `live` mode currently creates `CLIWorkerBackend` workers
  from raw AgentNode configs before `GraphRuntime` can materialize private
  Agent context.
- The desktop service constructs `GraphRuntime(backend)` without
  `enforce_private_agent_context=True`.
- As a result, both ordinary Agents and Test Agents in desktop `live` mode miss
  the normal framework-managed launch context:
  private checkout cwd, private `CODEX_HOME`, `framework-agent-runtime`,
  `AGENTS.md`, Workspace API env and prompt context, and authorized skill/rule
  materialization.
- This is not a Test Agent-only defect. Test Agent panel debugging merely made
  the raw-worker startup path visible.

## Highest Next Task

Fix desktop blueprint `live` startup before adding more Agent panel polish:

1. Start `CLIWorkerBackend` without raw prestarted workers, or otherwise use a
   lazy-start path.
2. Construct `GraphRuntime` with `enforce_private_agent_context=True` and the
   desktop workspace manager/run/RPC server/SkillSpace context.
3. Let `GraphRuntime.ensure_agent()` call `materialize_private_agent_context()`
   before launching each worker.
4. Ensure `GraphRuntimeControlPlane` remains the owner of start validation,
   queues, outgoing batches, joins, status, end, and stream events.
5. Add desktop service tests proving launched worker configs include private
   checkout cwd, private `codex_home`, `prompt_execution_context`,
   `framework-agent-runtime`, `AGENTS.md`, Workspace API env, and authorized
   skill/rule catalog entries.

## Main Files

- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-test-agent-snapshot.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc.ts`
- `desktop_blueprint_service.py`
- `graph_runtime.py`
- `agent_launch_context.py`
- `cluster.py`
- `codex_bridge.py`
- `test_desktop_blueprint_service.py`

## Verification Run

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run typecheck
bun run build

cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun run build
$env:CSC_IDENTITY_AUTO_DISCOVERY='false'
bunx electron-builder --win --config electron-builder.config.ts --config.win.signAndEditExecutable=false
```

Latest package observed:

```text
F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron\dist\opencode-electron-win-x64.exe
LastWriteTime: 2026-05-18 20:19:31
Size: 149.27 MB
```
