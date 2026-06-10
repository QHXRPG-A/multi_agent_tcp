# Blueprint Framework Skill Rule Assets

Date: 2026-06-10

## Summary

This archive records the framework skill/rule source-of-truth extraction for
Blueprint Agent runtime launch contexts.

The framework skill/rule text previously lived as long Python string builders
inside `agent_launch_context.py`. It now lives as real package data under
`framework_assets`, and runtime launch code only reads/copies those files into
each Agent's private context.

Use this record when:

- framework rules or skills are missing from a worker/full Agent runtime
- `AGENTS.md` no longer contains the old full framework rule text
- checking why framework rules appear before business rules in `rule_catalog`
- debugging runtime wheel/plugin packaging for framework assets
- deciding where to edit framework Agent instructions next

## Main Files

- `framework_assets/skills/framework-agent-runtime/SKILL.md`
- `framework_assets/skills/framework-top-agent-runtime/SKILL.md`
- `framework_assets/rules/framework-agent-runtime.md`
- `framework_assets/rules/framework-top-agent-runtime.md`
- `agent_launch_context.py`
- `pyproject.toml`

## Runtime Behavior

`agent_launch_context.py` keeps compatibility functions such as
`framework_agent_skill()` and `framework_agent_rules()`, but these functions now
read the corresponding files from `framework_assets` instead of holding copied
instruction text.

Worker Agents:

- copy `framework-agent-runtime/SKILL.md` into private
  `codex_home/skills/framework-agent-runtime/SKILL.md`
- copy `framework-agent-runtime.md` into private
  `rules/framework-agent-runtime.md`
- put the framework skill/rule first in `private_context.skill_catalog` and
  `private_context.rule_catalog` with `source: "framework"`
- then append user/business skills and rules as before

Full Agents:

- create the same framework skill/rule copies under
  `runtime_agent_context/<agent>/codex_home` and
  `runtime_agent_context/<agent>/rules`
- expose them through `execution_context.private_context`
- add a short prompt preamble pointing to the materialized framework rule file

`AGENTS.md` now lists framework rule file paths under `# Framework Rules`
instead of embedding the framework rule body. Business rule files continue to be
listed under `# Business Rules`.

Top-agent runtime assets still exist separately as
`framework-top-agent-runtime`; they are selected only for framework top-agent
nodes.

## Packaging

`pyproject.toml` package-data now includes:

```toml
"framework_assets/**/*"
```

This ensures `framework_assets` is present in the `multi-agent-tcp` runtime
wheel and therefore in packaged `gulicode-bp` installs.

## Verification

Commands run from `F:\src\Package\Script\Python\multi_agent_tcp`:

```powershell
python -m py_compile agent_launch_context.py
pytest test_agent_runtime.py::test_graph_runtime_private_context_materializes_codex_skill_and_rules test_agent_runtime.py::test_graph_runtime_full_agent_skips_private_workspace -q
git diff --check
```

Results:

- Python compile passed.
- Targeted runtime tests passed: `2 passed`.
- `git diff --check` passed with only CRLF normalization warnings.

Wheel/package-data checks:

```powershell
python -m pip wheel --no-deps --wheel-dir $env:TEMP\multi_agent_tcp_wheel_check .
python plugins\gulicode-bp\scripts\install_personal_plugin.py --force --skip-web-build --release-dir $env:TEMP\gulicode-bp-framework-assets-check --only-release
```

Both produced a runtime wheel containing exactly these framework asset files:

```text
multi_agent_tcp/framework_assets/rules/framework-agent-runtime.md
multi_agent_tcp/framework_assets/rules/framework-top-agent-runtime.md
multi_agent_tcp/framework_assets/skills/framework-agent-runtime/SKILL.md
multi_agent_tcp/framework_assets/skills/framework-top-agent-runtime/SKILL.md
```

## Known Test Notes

Two broader tests were observed failing for existing expectations outside this
change:

- `test_desktop_blueprint_service.py -k "rule_catalog or codex_home or private_context"`
  fails one case before reaching the new framework assertions with
  `START_PLAN_INVALID`.
- `test_full_agent_receives_standard_context_and_dispatches_via_message_mcp`
  fails because actual allowed MCP tools include resident-service tools while
  the test expects the older shorter list.
