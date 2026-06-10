# Blueprint Catalog Models Rules Popo Streaming

Date: 2026-06-10

## Summary

This archive records the runtime/backend companion changes for the Blueprint
Workbench catalog and POPO reply work completed on 2026-06-10.

Use this record when:

- Agent Inspector model options are missing `gpt-5.5`
- Workbench Skill or Rule catalogs do not update from configured directories
- `blueprint.listRules` is rejected by the plugin bridge
- rule paths selected from multiple Rule directories fail to resolve at start
- POPO replies should use streaming cards but fall back to text safely
- framework idle termination keeps stale agent terminator metadata

## Main Files

- `desktop_blueprint_service.py`
- `plugins/gulicode-bp/mcp/gulicode_bp_mcp.py`
- `test_desktop_blueprint_service.py`
- `agent_launch_context.py`
- `framework_assets/`
- `pyproject.toml`
- `test_agent_runtime.py`

## Catalog Commands

`blueprint.listModels` is a read-only DesktopBlueprintService command.

- Input: `args.cliKind`, defaulting to `codex`
- For `codex`, runs `codex debug models` with a 15 second timeout
- On Windows, retries with `codex.cmd debug models` when the bare command
  cannot be launched
- Parses JSON `models[].slug`
- Drops empty and duplicate slugs while preserving CLI order
- Returns `{ ok: true, models: [] }` for unsupported CLI kinds, nonzero exit,
  timeout, invalid JSON, or missing command

`blueprint.listSkills` now accepts multiple directories:

```json
{ "dirs": ["F:/skills-a", "F:/skills-b"] }
```

Legacy `{ "dir": "F:/skills" }` still works. With no path arguments the command
continues to scan `$CODEX_HOME/skills`.

Skill scanning preserves configured directory order. If two directories contain
the same skill directory name, the first configured directory wins.

`blueprint.listRules` is a new read-only command. It accepts the same
`dirs`/`dir` shape and returns rule files with absolute `value` paths:

```json
{
  "value": "F:/rules-a/policy.md",
  "label": "policy.md",
  "description": "F:/rules-a"
}
```

Absolute rule values avoid collisions when different Rule directories contain
files with the same name.

`plugins/gulicode-bp/mcp/gulicode_bp_mcp.py` whitelists
`blueprint.listRules`. It remains a read command and is not in write/control
command sets.

## Start-Time Compatibility

Blueprint common config now supports both plural and legacy path fields:

- `skill_dirs` preferred, falling back to `skill_dir`
- `rule_dirs` preferred, falling back to `rule_dir`

Start validation keeps UI-facing field names stable:

- invalid Skill dirs report `skill_dir`
- missing or invalid Rule dirs report `rule_dir`

Existing blueprints that store:

```json
{
  "rule_dir": "F:/project/rules",
  "rule_paths": ["policy.md"]
}
```

still resolve `policy.md` under the legacy `rule_dir`.

New selections may store absolute rule paths. Absolute paths are accepted when
they are under any configured `rule_dirs` entry.

## POPO Reply Transport

POPO user replies now prefer a streaming card transport:

- initialize card message with template `series_5564199`
- update key `resultStream`
- finalize with the reply content
- record the POPO message/card id in transcript metadata

If card initialization or update fails, the service falls back to the previous
plain text message path and records `transport: "text_fallback"` plus a
fallback reason.

The reply transcript stores `transport`, `popoMessageId`, and
`fallbackReason` when available.

## Session Termination Metadata

Session termination metadata is centralized through a helper that clears stale
agent identity fields when the terminator is framework-owned. Auto-idle
termination now records:

```json
{
  "lastTerminatedBy": "framework_auto_idle"
}
```

and removes prior `lastTerminatedByAgentNodeId` /
`lastTerminatedByAgentId` values.

## Verification

Commands run from `F:\src\Package\Script\Python\multi_agent_tcp`:

```powershell
python -m py_compile agent_launch_context.py desktop_blueprint_service.py plugins/gulicode-bp/mcp/gulicode_bp_mcp.py
pytest test_agent_runtime.py::test_graph_runtime_private_context_materializes_codex_skill_and_rules test_agent_runtime.py::test_graph_runtime_full_agent_skips_private_workspace test_desktop_blueprint_service.py::test_blueprint_session_auto_terminates_after_ten_idle_minutes_without_queue test_desktop_blueprint_service.py::test_send_popo_message_prefers_streaming_card_and_reuses_token test_desktop_blueprint_service.py::test_send_popo_message_falls_back_to_text_when_streaming_card_init_fails test_desktop_blueprint_service.py::test_send_popo_message_falls_back_to_text_when_streaming_card_update_fails test_desktop_blueprint_service.py::test_gulicode_bp_mcp_whitelists_python_detection_command test_desktop_blueprint_service.py::test_blueprint_service_lists_default_codex_home_skills test_desktop_blueprint_service.py::test_blueprint_service_lists_skills_from_multiple_dirs_with_first_duplicate_winning test_desktop_blueprint_service.py::test_blueprint_service_lists_rules_from_multiple_dirs_with_absolute_values test_desktop_blueprint_service.py::test_blueprint_service_resolves_rule_dirs_and_absolute_rule_paths test_desktop_blueprint_service.py::test_blueprint_service_lists_codex_models_from_cli test_desktop_blueprint_service.py::test_blueprint_service_model_listing_returns_empty_for_unsupported_cli_kind test_desktop_blueprint_service.py::test_blueprint_service_model_listing_retries_codex_cmd_on_windows_oserror test_desktop_blueprint_service.py::test_blueprint_service_model_listing_returns_empty_on_cli_failures
```

Results:

- Python compile passed.
- Targeted Python tests passed: `15 passed`.

Runtime API smoke after plugin cache sync and singleton restart:

```text
blueprint.listRules -> ok, 2 rules from framework_assets/rules
blueprint.listSkills -> ok, framework runtime skills from framework_assets/skills
```
