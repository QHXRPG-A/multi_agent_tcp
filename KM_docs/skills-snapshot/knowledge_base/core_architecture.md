# Current Core Architecture

## Position

`multi_agent_tcp` is now best understood as the runtime substrate for the **GuLiCode desktop app + multi-agent blueprint system**.

The current main line is:

```text
GuLiCode desktop / UI / top Agent
  -> GraphRuntimeControlPlane
  -> GraphRuntime
  -> AgentNode queues
  -> outgoing message batches
  -> fan-in join barriers
  -> workspace state, changesets, reports, artifacts, events
  -> CLIWorkerBackend
  -> AgentTCPClient / Broker / CLIAdapter / worker process
```

The old low-level TCP worker path remains valid as an execution backend. It is not the current product center.

## Layer Ownership

| Layer | Main Files | Responsibility |
|---|---|---|
| GuLiCode desktop | `GuLiCode/packages/desktop-electron`, `GuLiCode/packages/app` | User-facing desktop shell, top-agent UI, session/project surface, future blueprint workbench |
| Runtime control plane | `graph_control.py`, `__main__.py` runtime commands | Stable non-UI interface for organization reads, top-agent context, run start/status/end, message batches, agent dispatch, joins |
| Runtime scheduler | `graph_runtime.py` | Trusted scheduler for AgentNode queues, dispatch state, outgoing batches, join barriers, events, jobs, final status |
| Graph model | `graph_runtime.py`, `ryven_blueprint.py` | AgentNode definitions, graph edges, organization view, runnable graph validation, graph scheduling |
| Workspace / archive | `workspace_manager.py`, `workspace_api.py`, `workspace_rpc.py` | Private checkout, scoped changesets, conflict detection, accepted changes, reports, artifacts, archive indexing |
| Backend adapter | `cluster.py`, `client.py`, `broker.py`, `adapters.py`, `codex_bridge.py`, `codemaker_bridge.py` | Run concrete CLI workers when a scheduled AgentNode needs model work |
| Registry / skills | `registry.py`, `skill_space.py`, `agents_registry.json` | Agent profiles, skill selection, skill catalog, per-agent skill views |

## Current Runtime Semantics

- GuLiCode/top Agent reads organization context and submits structured start plans.
- The framework validates start plans. The top Agent does not directly mutate runtime internals.
- Ordinary Agents do not directly message each other. They stage intent through framework APIs.
- `GraphRuntime` owns queueing, dispatch, idle reminders, join aggregation, cancellation, final status, and event emission.
- Complete outgoing batches enter downstream Agent queues instead of directly invoking worker processes.
- Fan-in joins aggregate contributions, changesets, conflicts, artifacts, reports, tests, and source statuses before queueing a `join_aggregate` envelope.
- Workspace writes should flow through controlled workspace APIs and changeset submission, not uncontrolled shared-path writes.
- Worker process replies are not treated as framework facts. `GraphRuntime` extracts a framework-private minimal Agent utterance record (`who`, `said`, `received_at`, `task_id` / `message_id`) and discards raw adapter payloads for runtime semantics.
- Top Agent may inspect Agent utterance records through the dedicated `top_agent.utterances` / `runtime top-agent-utterances` control-plane interface when its profile has the `utterances` permission.
- Ordinary Agents do not receive utterance records or the utterance inspection interface through `framework_context`; downstream communication still requires `agent.dispatch`.
- UI should consume runtime/control-plane state rather than rebuilding scheduling semantics in the renderer.

## Backend Adapter Boundary

`CLIWorkerBackend` is the preferred semantic name for the old cluster execution concept.

`CodeMakerCluster` still exists for compatibility and for old APIs such as `run_parallel`, `run_chain`, and `run_parallel_reduce`. Use it only when explaining legacy flows or the concrete TCP backend path.

Current backend path:

```text
GraphRuntime
  -> CLIWorkerBackend
  -> AgentTCPClient
  -> Broker
  -> worker Agent process
  -> CLIAdapter
```

## Important Current Documents

- Top-agent and communication design: [`../多agents通信设计.md`](../多agents通信设计.md)
- GuLiCode desktop: [`gulicode_desktop.md`](gulicode_desktop.md)
- Runtime control commands: [`dispatch_workflows.md`](dispatch_workflows.md)
- Backend compatibility: [`cluster_api.md`](cluster_api.md)
- Registry and skills: [`registry_and_skills.md`](registry_and_skills.md)

## Deprecated Center Framing

Avoid presenting the project as primarily:

- "Cursor talks to many CodeMaker CLI workers"
- "CodeMakerCluster is the core architecture"
- "Ryven Start -> AgentNode -> End is the main current loop"

Those are historical or secondary views. The current center is GuLiCode-led blueprint orchestration through framework-owned runtime APIs.
