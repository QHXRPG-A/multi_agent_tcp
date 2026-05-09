# multi_agent_tcp

A multi-agent runtime substrate for the current **GuLiCode desktop app + blueprint system** direction. The main line is: GuLiCode / UI submits a structured plan, `GraphRuntimeControlPlane` validates it, `GraphRuntime` schedules `AgentNode` queues, outgoing batches, fan-in joins, workspace state and events, and a pluggable execution backend runs the actual CLI worker when an AgentNode needs model work.

The low-level TCP worker path still exists, but it is now best understood as a backend adapter:

```text
GraphRuntime
  -> CLIWorkerBackend
  -> AgentTCPClient
  -> Broker
  -> Worker Agent process
  -> CLIAdapter
```

`CLIWorkerBackend` is the new semantic name for the old `CodeMakerCluster` concept. `CodeMakerCluster` remains as a backward-compatible alias, but new code and documentation should prefer `CLIWorkerBackend`.

## Architecture Diagrams

The current communication model is summarized in the main overview diagram:

![Multi-agent communication overview](docs/diagrams/multi_agents_communication/01_overview.svg)

### Agents 协同与工作区流转

![Agents collaboration and workspace flow](docs/diagrams/agents_collaboration_workspace_flow.svg)

中文注释：这张图把协作拆成三层：上层是用户、总控 Agent 和框架调度；中层是普通 Agent 的任务执行与汇总；下层是私有工作区、临时共享工作区和长期归档。普通 Agent 只在自己的私有工作区修改内容，通过框架提交消息意图、代码变更、报告和产物；框架负责校验、合并、排队、汇总和归档。

More focused diagrams live in [`docs/diagrams/multi_agents_communication/`](docs/diagrams/multi_agents_communication/):

- [One-to-many outgoing batch dispatch](docs/diagrams/multi_agents_communication/02_fanout_dispatch.svg)
- [Fan-in join aggregation](docs/diagrams/multi_agents_communication/03_fanin_join.svg)
- [Appendix: CLIWorkerBackend TCP delivery path](docs/diagrams/multi_agents_communication/04_tcp_delivery.svg)

## Current Architecture Notes

- `GraphRuntimeControlPlane` is the non-UI control surface for organization reads, top-agent context, run start/status/end, outgoing message batches, ordinary `agent.dispatch`, and join contribution commands.
- `GraphRuntime` is the trusted scheduler. Agents do not directly message each other; they stage intent through framework APIs, and the runtime owns queueing, dispatch, reminders, join aggregation and event emission.
- `CLIWorkerBackend` is not the center of the blueprint architecture. It is one execution backend used when a scheduled AgentNode needs to call a CLI worker through TCP.
- In one-to-many dispatch, `stage_outgoing_message()` immediately returns `remaining_targets` to the caller after each `agent.dispatch`. Separately, `tick()` emits `AgentOutgoingTargetsReminder` only when the source Agent is idle/can accept messages and a staging batch still has missing targets. So the diagram concern about "should this wait for idle?" is a diagram wording issue, not a runtime bug: immediate return and idle reminder are two different feedback channels.

## Requirements

- Python 3.10+
- `merge3` Python package is recommended for Dulwich-powered three-way text merges in the workspace changeset flow (`python -m pip install merge3`).
- At least one supported agent CLI on `PATH`. Currently:
  - `codemaker` (non-interactive `codemaker run` with `--format json`) — fully supported via `codemaker_bridge.py`.
  - Other CLIs: planned, see `ROADMAP.md`.
- Run with the **parent** of this folder on `PYTHONPATH`, or from a project that already imports `multi_agent_tcp` as a package.

Example from `Package/Script/Python` (one level above this directory):

```bash
python -m multi_agent_tcp show-registry
python -m multi_agent_tcp dispatch --tasks path/to/tasks.json
```

See [`examples/HOWTO.txt`](examples/HOWTO.txt) for low-level setup and [`GUIDE_FOR_AGENTS.md`](GUIDE_FOR_AGENTS.md) for the standard two-step workflow that any agent CLI or script can use to dispatch tasks to peer agents. Optional local reference [`codemaker_cli.md`](codemaker_cli.md) is **not** in the public repo (gitignored); keep your own copy beside this package if you use it.

## Configuration

- Edit [`agents_registry.json`](agents_registry.json) for agent ids, **`cwd` (use an absolute path to your repo root in practice)**, models, and skills. The committed file uses `"."` as a placeholder.
- Run `python -m multi_agent_tcp.init_skill_list` to populate `skill_list/` (gitignored by default).

## Documentation map

| File | Purpose |
|------|---------|
| [`GUIDE_FOR_AGENTS.md`](GUIDE_FOR_AGENTS.md) | Standard two-step workflow for any agent CLI / script that wants to dispatch sub-tasks to peer agents. **Replaces** the legacy `GUIDE_FOR_CODEMAKER.md`. |
| [`ROADMAP.md`](ROADMAP.md) | Design philosophy, current capabilities, planned milestones (CLI Adapter, multi-modal, DAG, etc.). |
| [`examples/HOWTO.txt`](examples/HOWTO.txt) | Low-level: `broker` / `agent` / `spawn` / orchestrate recipes / library API. |
| [`KM_docs/`](KM_docs/) | Design notes (multi-CLI brainstorm, vendored Ryven editor analysis, etc.). |
| [`codemaker_cli.md`](codemaker_cli.md) | (Local-only, gitignored) CodeMaker CLI reference notes. |

