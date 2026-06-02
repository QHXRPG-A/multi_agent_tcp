# CLIWorkerBackend and Legacy CLIWorkerBackend API

## Status

This document is a compatibility note.

New architecture and documentation should prefer:

```text
CLIWorkerBackend
```

The older name remains available in code and historical docs:

```text
CLIWorkerBackend
```

Use `CLIWorkerBackend` only when working with legacy high-level APIs or the low-level TCP backend path.

## Current Interpretation

The backend path is now one execution backend under `GraphRuntime`:

```text
GraphRuntime
  -> CLIWorkerBackend
  -> AgentTCPClient
  -> Broker
  -> worker process
  -> CLIAdapter
```

It should not own product-level orchestration decisions. Those belong to `GraphRuntimeControlPlane` / `GraphRuntime`.

## Legacy Facade Example

```python
from multi_agent_tcp import CLIWorkerBackend, WorkerConfig, AgentsRegistry

reg = AgentsRegistry.load()

cluster = await CLIWorkerBackend.create_from_registry(
    reg,
    agent_ids=["agent-1", "agent-2"],
    skill_mode="catalog",
    port=9140,
)
```

Legacy task helpers still exist:

```python
par = await cluster.run_parallel([
    ("agent-1", {"prompt": "Task A"}),
    ("agent-2", {"prompt": "Task B"}),
])

results = await cluster.run_chain([
    ("agent-1", {"prompt": "Step 1"}),
    ("agent-2", {"prompt": "Step 2"}),
])

rr = await cluster.run_parallel_reduce(
    tasks=[("agent-1", {"prompt": "A"}), ("agent-2", {"prompt": "B"})],
    reduce_worker="agent-1",
    reduce_prompt="Merge:\n{results}",
)
```

## Preferred New Usage

For new runtime work:

- Model organization through `GraphDefinition.agent_organization_view()`.
- Start runs through `GraphRuntimeControlPlane`.
- Dispatch ordinary Agent messages through runtime-owned message batch / `agent.dispatch` APIs.
- Let `GraphRuntime` decide when an AgentNode can receive work.
- Let backend adapters execute concrete CLI calls only after the runtime schedules them.

## Related Documents

- Current architecture: [`core_architecture.md`](core_architecture.md)
- Runtime/control-plane workflows: [`dispatch_workflows.md`](dispatch_workflows.md)
- CLI adapter history: [`multi_cli_workflow.md`](multi_cli_workflow.md)
