# Multi Agent TCP CLI Productization Archive - 2026-05-17

This archive records the `cli-creator` pass that turned the existing
`multi_agent_tcp` module CLI into a durable command-line tool for future Codex
threads.

## Summary

The project already had a broad `python -m multi_agent_tcp` command surface for
registry reads, dispatch, GraphRuntime control-plane calls, desktop blueprint
service startup, and legacy TCP worker orchestration. This pass packaged that
surface as an installed CLI on PATH and added a small health check plus raw RPC
escape hatch so future threads can use it from any workspace.

## Landed

1. Added Python packaging metadata:
   - `pyproject.toml`
   - package name: `multi-agent-tcp`
   - console scripts: `multi-agent-tcp` and `multi_agent_tcp`
   - root package mapping: repository root is the `multi_agent_tcp` package
2. Added install/test helper targets:
   - `Makefile`
   - `make install-local`
   - `make test-cli`
3. Added `multi-agent-tcp doctor --json`.
   - Reports CLI path, Python executable/version, package root, registry
     existence/loadability, agent count, skill list directory, and worker CLI
     availability.
   - Designed to work even when optional worker CLIs are missing.
4. Added `multi-agent-tcp rpc`.
   - Thin raw GraphRuntime RPC escape hatch.
   - Accepts `--rpc-url`, `--token`, `--command`, and optional JSON args from
     `--args-json` or `--args-file`.
   - Intended for read-only or explicit user-requested control-plane calls
     when high-level commands are insufficient.
5. Documented editable install in `README.md`.
6. Added installed-CLI smoke tests:
   - `test_multi_agent_tcp_cli.py`
   - verifies `--help` and `doctor --json` from outside the source tree.
7. Installed the CLI locally with:

```powershell
python -m pip install -e .
```

8. Created a companion Codex skill:
   - `C:\Users\13429\.codex\skills\multi-agent-tcp-cli\SKILL.md`
   - teaches future Codex threads to start with `doctor --json`, discover via
     `show-registry`, use async dispatch for long jobs, prefer safe reads
     before runtime writes, and reserve `rpc` for missing high-level commands.

## Command Surface After This Pass

Start/diagnose:

```powershell
multi-agent-tcp --help
multi-agent-tcp --version
multi-agent-tcp doctor --json
```

Discovery and dispatch:

```powershell
multi-agent-tcp show-registry -o agents.json
multi-agent-tcp dispatch --async --tasks tasks.json
multi-agent-tcp dispatch-status --job-id <job_id> --wait 25
```

Runtime/control plane:

```powershell
multi-agent-tcp organization --graph graph.json -o organization.json
multi-agent-tcp runtime validate-start --graph graph.json --plan plan.json -o validation.json
multi-agent-tcp runtime status --rpc-url http://127.0.0.1:PORT --token TOKEN -o status.json
multi-agent-tcp runtime explain-status --rpc-url http://127.0.0.1:PORT --token TOKEN
multi-agent-tcp rpc --rpc-url http://127.0.0.1:PORT --token TOKEN --command organization.read --args-json "{}"
```

## Verification

Observed successful verification from outside the source folder:

```powershell
cd C:\Users\13429
Get-Command multi-agent-tcp, multi_agent_tcp
multi-agent-tcp --help
multi-agent-tcp --version
multi-agent-tcp doctor --json
multi-agent-tcp show-registry -o cli-registry-smoke.json
multi-agent-tcp rpc --help
```

Observed successful tests:

```powershell
cd D:\agent\multi_agent_tcp
python -m py_compile __main__.py
python -m pytest test_multi_agent_tcp_cli.py
python -m pytest test_registry_skill_selection.py test_workspace_api.py
```

Results:

```text
test_multi_agent_tcp_cli.py: 2 passed
test_registry_skill_selection.py + test_workspace_api.py: 17 passed
multi-agent-tcp --version: multi-agent-tcp 0.5.0
```

Companion skill validation:

```powershell
cd C:\Users\13429\.codex\skills\.system\skill-creator\scripts
python quick_validate.py C:\Users\13429\.codex\skills\multi-agent-tcp-cli
```

Result:

```text
Skill is valid!
```

Note: `PyYAML` was installed into the local Python environment because the
skill validator imports `yaml`.

## Environment Observed

`doctor --json` reported:

- CLI on PATH:
  `C:\Users\13429\AppData\Local\Programs\Python\Python313\Scripts\multi-agent-tcp.exe`
- Python: `3.13.13`
- package root: `D:\agent\multi_agent_tcp`
- registry: loadable, `agent_count = 3`
- `codex`: available
- `codex`: not available on PATH

`codex` absence is an environment fact, not a packaging failure.

## Files

Repository files changed or added by this pass:

- `pyproject.toml`
- `Makefile`
- `__main__.py`
- `README.md`
- `test_multi_agent_tcp_cli.py`

Personal companion skill files created outside the repo:

- `C:\Users\13429\.codex\skills\multi-agent-tcp-cli\SKILL.md`
- `C:\Users\13429\.codex\skills\multi-agent-tcp-cli\agents\openai.yaml`

## Follow-up

1. Keep `multi-agent-tcp` as the preferred durable command for future Codex
   threads; fall back to `python -m multi_agent_tcp` only if the command is not
   installed.
2. Extend `doctor --json` if new required worker CLIs or runtime service
   dependencies become mandatory.
3. Keep raw `rpc` use narrow. Prefer high-level `runtime ...` commands and use
   raw writes only when the user explicitly asks for the write.
4. Consider adding a package-data policy if future installs need bundled
   examples, docs, or registry defaults beyond editable checkout usage.
