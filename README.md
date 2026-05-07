# multi_agent_tcp

A **peer-to-peer agent CLI communication bus** with multi-agent lifecycle, session and capability management. Any agent CLI (CodeMaker / Claude Code / Codex / custom) connects to a shared broker and can act as both **receiver** (handle inbound tasks) and **initiator** (dispatch sub-tasks to other peer agents). The framework provides addressing, mailboxes, heartbeat, batch_gather, serial chains, structured results — but **does not** replace any agent's own LLM reasoning, tool calling, or planning.

> **Project pivot**: As of 2026-04-30 the project moved away from the earlier "Cursor / CodeMaker as upstream orchestrator + N CodeMaker workers" framing and toward "agent CLIs collaborating as peers". CodeMaker remains the only fully-implemented CLI adapter today; Claude Code / Codex adapters are tracked in `ROADMAP.md` (P0). See `KM_docs/multi-cli-node-workflow-brainstorm.md` for the design discussion.

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
