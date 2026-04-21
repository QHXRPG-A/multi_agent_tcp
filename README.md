# multi_agent_tcp

Orchestrate multiple **CodeMaker CLI** workers over a single TCP broker: parallel `batch_gather`, chain runs, registry-driven agents, optional skill injection, and async `dispatch` jobs.

## Requirements

- Python 3.10+
- `codemaker` on `PATH` (non-interactive `codemaker run` with `--format json`)
- Run with the **parent** of this folder on `PYTHONPATH`, or from a project that already imports `multi_agent_tcp` as a package.

Example from `Package/Script/Python` (one level above this directory):

```bash
python -m multi_agent_tcp show-registry
python -m multi_agent_tcp dispatch --tasks path/to/tasks.json
```

See `examples/HOWTO.txt` and `GUIDE_FOR_CODEMAKER.md`.

## Configuration

- Edit `agents_registry.json` for agent ids, `cwd`, models, and skills.
- Run `python -m multi_agent_tcp.init_skill_list` to populate `skill_list/` (gitignored by default).
