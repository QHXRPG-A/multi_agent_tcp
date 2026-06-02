# Current Core Architecture

## Position

`multi_agent_tcp` is now best understood as the runtime substrate for the
**gulicode-bp Codex plugin + multi-agent blueprint system**. GuLiCode
desktop/Electron is a secondary explicit compatibility track.

The current main line is:

```text
gulicode-bp plugin / Blueprint web workbench
  -> GuLiCode app dev surfaces: /mobile and /console
  -> DesktopBlueprintService
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
| Plugin workbench and app surfaces | `plugins/gulicode-bp`, `GuLiCode/packages/app` | Default Blueprint workbench, `/mobile`, `/console`, top-agent/session surfaces |
| GuLiCode desktop compatibility | `GuLiCode/packages/desktop-electron`, `GuLiCode/packages/app` | Explicit desktop shell, IPC, packaging, taskbar, and windowing work |
| Runtime control plane | `graph_control.py`, `__main__.py` runtime commands | Stable non-UI interface for organization reads, top-agent context, run start/status/end, message batches, agent dispatch, joins |
| Runtime scheduler | `graph_runtime.py` | Trusted scheduler for AgentNode queues, dispatch state, outgoing batches, join barriers, events, jobs, final status |
| Graph model | `graph_runtime.py`, `ryven_blueprint.py` | AgentNode definitions, graph edges, organization view, runnable graph validation, graph scheduling, exec-edge SCC cycle grouping for agents |
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
- The active private-Agent workspace model is `project_reference`: the project directory is the authoritative code source and final code target; Agent private checkouts materialize only task-relevant files via `checkout --path` / `--scope-path`; the temporary shared workspace stores reports, artifacts, manifests, changeset references, and conflict records rather than project code copies. Legacy `snapshot_copy` remains for old job/worktree compatibility.
- Worker process replies are not treated as framework facts. `GraphRuntime` extracts a framework-private minimal Agent utterance record (`who`, `said`, `received_at`, `task_id` / `message_id`) and discards raw adapter payloads for runtime semantics.
- Top Agent may inspect Agent utterance records through the dedicated `top_agent.utterances` / `runtime top-agent-utterances` control-plane interface when its profile has the `utterances` permission.
- Ordinary Agents do not receive utterance records or the utterance inspection interface through `framework_context`; downstream communication still requires `agent.dispatch`.
- Prompt injection now distinguishes internal runtime context from prompt-facing context. `execution_context` remains the full adapter/runtime record; `prompt_execution_context` is the reduced view merged into CLI prompts. Ordinary Agents should receive direct-read project/shared roots and MCP tool context, but not CLI Workspace API recipes, Codex home, real skill-space paths, bearer/RPC tokens, or unrelated private internals.
- Top-agent organization context is prompt-facing and compact by default: it includes governance-relevant graph, agent, permission, rule, and skill data, not the full launch configuration.
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
- Plugin-first debug startup: [`debug_start.md`](debug_start.md)
- Explicit GuLiCode desktop work: [`gulicode_desktop.md`](gulicode_desktop.md)
- Runtime control commands: [`dispatch_workflows.md`](dispatch_workflows.md)
- Backend compatibility: [`cluster_api.md`](cluster_api.md)
- Registry and skills: [`registry_and_skills.md`](registry_and_skills.md)

## GraphDefinition: agent cycle groups (`agent_cycle_groups`)

`GraphDefinition.agent_cycle_groups()` returns `List[List[str]]`: each inner list is the **sorted** `node_id`s of `AgentNode`s that belong to one **cyclic** strongly connected component (SCC) of the graph when only **`exec` edges** are considered.

- SCC is computed over **all** registered node ids (agents, `RouteNode`, `BlueprintTerminalNode`, etc.), so a cycle that **passes through a route or terminal node** is still detected; the public result **filters to agent ids only** (non-agent nodes in the component are omitted from the inner list, not split into a separate group).
- Acyclic components and singleton SCCs without a self-loop produce **no** inner list.
- Self-loop on an agent via a single `exec` edge is treated as cyclic and yields one one-element inner list.
- Groups are sorted lexicographically by their tuple of agent ids for stable output.
- Example shape: `[["a", "b", "c"], ["d", "e", "f"]]`.
- Tests: `multi_agent_tcp/test_agent_runtime.py` (`test_graph_definition_agent_cycle_groups_detects_agent_cycles`, `test_graph_definition_agent_cycle_groups_ignores_acyclic_graphs`); full `test_agent_runtime.py` was at **64 passed** after this landed.
- **Possible follow-up (not implemented):** a thin wrapper that also returns each SCC’s **full** node id set (including routes) for debugging or UI overlays.

Implementation: `graph_runtime.py` (`GraphDefinition.agent_cycle_groups`).

## Deprecated Center Framing

Avoid presenting the project as primarily:

- "Cursor talks to many CodeMaker CLI workers"
- "CodeMakerCluster is the core architecture"
- "Ryven Start -> AgentNode -> End is the main current loop"

Those are historical or secondary views. The current center is the
`gulicode-bp` plugin workbench backed by framework-owned runtime APIs.
