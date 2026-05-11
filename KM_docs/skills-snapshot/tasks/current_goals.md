# Current Short-Term Goals

Last cleaned: 2026-05-11

## Current Main Line

The active project direction is:

```text
GuLiCode desktop / top Agent
  -> GraphRuntimeControlPlane
  -> GraphRuntime
  -> AgentNode queues, outgoing batches, joins, workspace/events
  -> CLIWorkerBackend adapters
```

Primary design source:

- [`../多agents通信设计.md`](../多agents通信设计.md)
- [`multi_agent_communication_tasks.md`](multi_agent_communication_tasks.md)
- [`../knowledge_base/gulicode_desktop.md`](../knowledge_base/gulicode_desktop.md)
- [`../knowledge_base/core_architecture.md`](../knowledge_base/core_architecture.md)

## Recently Completed Runtime Capabilities

- Framework-owned one-to-many outgoing message staging.
- Complete-batch dispatch into downstream Agent queues.
- `remaining_targets` reminders when source Agents return to `idle`.
- Graph-derived `agent_connections`.
- Organization view with top/full and scoped ordinary-agent variants.
- GuLiCode top-agent profile, rule/skill skeleton, start-plan validation, and top-agent context rendering.
- Runtime start/status/end basics through `GraphRuntimeControlPlane`, RPC, and CLI thin clients.
- `agent.dispatch` wrapper for ordinary-Agent downstream messages.
- Join barriers for fan-in: `wait-all`, `wait-any`, `quorum`, and `timeout`.
- Join aggregate envelope queueing into target Agent queues.
- Cancel/fail cleanup for pending runtime work.
- Sequential DAG runner with automatic multi-input fan-in.
- Final report generation and archive indexing on completion.
- RingSession / 环状结构 single-pass runtime, with dynamic reachable targets, entry-message merging, auditor gating, and idempotent final output.
- Worker replies are reduced to framework-private utterance receipts instead of raw runtime facts.
- Top Agent can inspect Agent utterance records through a dedicated `top_agent.utterances` / `runtime top-agent-utterances` interface.
- Ordinary Agent baseline rule/skill now states that final CLI replies are not an Agent-to-Agent communication channel; durable information must go through framework APIs.
- Private-Agent workspaces now use the `project_reference` three-zone model by default: project directory as code authority/final target, private checkout as on-demand workbench, temporary shared workspace as reports/artifacts/changeset-reference space.
- Prompt-facing context has been slimmed: adapters prefer `prompt_execution_context`, ordinary Agents no longer receive raw launch paths such as `project_context`, `checkout_path`, or `codex_home` in the prompt, and top-Agent organization context uses a compact runtime view.

## Active Priorities

Testing is now the immediate focus before further feature expansion. Use the 2026-05-11 testing notes below as the current execution bias.

1. Wire the non-UI control plane into a real long-lived GuLiCode/top-Agent session.
2. Keep ordinary-Agent communication and durable output restricted to framework interfaces: `agent.dispatch`, Workspace API, and join/task contribution APIs.
3. Keep AgentNode startup context minimal and audit future additions so ordinary Agents keep seeing only the baseline rule/skill/tool contract and no top-agent-only inspection APIs.
4. Continue hardening status explanation and event summaries for GuLiCode/top Agent and UI.
5. Connect GuLiCode desktop UI to runtime/control-plane state without duplicating scheduling semantics.
6. Keep workspace/archive behavior aligned with the `project_reference` three-zone model and framework-owned changeset, conflict, report, artifact, and reference records.
7. Surface utterance records in future UI only as a top-agent/operator audit view, not as Agent-to-Agent message context.

## 2026-05-11 Testing Focus

Conversation-derived testing tasks:

1. Maintain a complex blueprint test sample that covers serial dispatch, one-to-many fan-out, many-to-one fan-in joins, conditional routing, retry loops, side-channel event monitoring, workspace aggregation, and final archive.
   - Current visual asset in the repo: `docs/blueprints/complex_test_blueprint.svg`.
   - The SVG has Chinese visible labels and Chinese maintenance comments.
   - Next: convert this structure into a machine-readable blueprint fixture JSON.

2. Turn the complex blueprint sample into runtime coverage.
   - Validate graph compilation and organization view.
   - Validate top-agent start-plan generation and `GraphRuntimeControlPlane` start/status/end behavior.
   - Validate fan-out outgoing batches and fan-in join aggregation.
   - Validate condition branches for low/medium/high risk paths.
   - Validate review failure and integration failure retry loops.
   - Validate event/workspace side-channel records without making them scheduling dependencies.

3. Use the fixed GuLiCode test-environment launch rule when testing top-level GuLiCode startup.
   - Source of truth: `knowledge_base/gulicode_desktop.md`, section `测试环境顶层 GuLiCode 启动规则`.
   - Provider/model: `aiapi_world/gpt-5.5`.
   - Reasoning variant: `high`.
   - Launch path: Electron dev via `GuLiCode/packages/desktop-electron`.
   - First smoke check: `bun --cwd .\GuLiCode\packages\opencode src\index.ts models aiapi_world`.
   - Then verify Electron logs reach `sidecar connection started` and `init step { phase: 'done' }`.

4. Add an automated smoke script or test helper for GuLiCode launch verification.
   - It should set test environment variables only for the child process.
   - It should not write credentials into repo files or test logs.
   - It should clean up `bun` / `electron` / `node` child processes after a launch-only verification.

5. Keep validation output short and evidence-based.
   - Report the exact command run.
   - Report whether the provider appeared as `aiapi_world/gpt-5.5`.
   - Report whether Electron main/preload/renderer and sidecar readiness were observed.
   - Link logs when useful, but do not echo credentials.

6. Keep the ring-session / 环状结构 path in the runtime regression suite.
   - Preserve coverage for entry merging, queue gating, auditor final-output idempotency, and single-pass dynamic reachability.
   - Keep `knowledge_base/ring_structure_solution.md` as the canonical current spec instead of restating the whole protocol elsewhere.

## Deferred / Secondary Tracks

### CLI backend adapters

Continue maintaining Codex/CodeMaker adapters and `CLIWorkerBackend`, but do not let adapter mechanics drive product architecture.

See [`multi_cli_adapter_tasks.md`](multi_cli_adapter_tasks.md).

### Ryven / visual editor

Ryven remains useful as a visual editor and historical prototype, but the current control model is GuLiCode/top-Agent start plans validated by the framework. Do not treat `Start -> AgentNode -> End` as the main product priority unless the user explicitly asks for Ryven/editor work.

See [`vendor_ryven_tasks.md`](vendor_ryven_tasks.md).

### Old CodeMakerCluster/TCP docs

The TCP worker path remains as backend compatibility. New docs should say `CLIWorkerBackend`; use `CodeMakerCluster` only for legacy API compatibility.

## Validation Snapshot

Most recent project validation observed during cleanup/update:

```text
python -m pytest test_graph_control.py test_workspace_api.py test_workspace_manager.py test_agent_runtime.py -q
98 passed
```

Re-run tests after code changes, especially changes touching `graph_runtime.py`, `graph_control.py`, workspace APIs, or backend adapters.

Most recent GuLiCode launch smoke observed on 2026-05-11:

```text
bun --cwd .\GuLiCode\packages\opencode src\index.ts models aiapi_world
-> aiapi_world/gpt-5.5

bun --cwd packages/desktop-electron dev
-> electron main/preload built
-> renderer dev server started
-> sidecar connection started
-> init step { phase: 'done' }
```
