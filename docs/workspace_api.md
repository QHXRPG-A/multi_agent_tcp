# Workspace API for Blueprint Agents

Agents should publish run-scope reports and artifacts through the framework Workspace API instead of writing directly to shared workspace paths.

The framework prepares the API context before the agent starts. Agents do not need to know the physical workspace directories. In blueprint runs the context normally points at a runtime-owned local RPC endpoint with an opaque token; the CLI below is only the thin client.

Blueprint agents edit code through a VCS-style private checkout. In the current project-reference mode, the project directory remains the authoritative code source and final code target; the private checkout starts as an agent workbench and materializes only the files requested by `checkout --path` or `checkout --scope-path`. Final code changes are submitted back to the framework as a changeset. Run-scope reports and artifacts still use `publish`/`publish-file`; run-scope code never does.

The long-term shared workspace is read-only for agents. The framework archives each run's temporary shared workspace into a named zip under the long-term workspace. Agents can list those archives and extract interesting results into their own private workspace for reading.

## Agent Project Working Directory

Blueprint AgentNodes receive three workspace zones:

- `project_context` / `project_code_root`: the authoritative code source and final code target, accessed through framework checkout/submit operations.
- `checkout_path`: the writable private workbench. The worker process starts with this path as `cwd`.
- temporary shared workspace areas: `reports` and `artifacts`, used for collaboration records, summaries, produced files, file/version references, and changeset ids.

For Codex workers, the blueprint runtime defaults to `codex exec --sandbox workspace-write --cd <checkout_path>` unless the node explicitly overrides the Codex sandbox option.

All AgentNodes are started when the blueprint run starts. A downstream working directory can only be reassigned later through the framework runtime API, and only by a `SuperAgentProfile` with `can_assign_downstream_workdir=True`. The framework rejects reassignment with `AGENT_BUSY` if the target agent is currently executing a task; otherwise it kills and relaunches that worker with the same config plus the new working directory.

## Command

```powershell
python -m multi_agent_tcp.workspace_api <command> [options]
```

## Areas

- `artifacts`: generated images, documents, binary-adjacent text metadata, or other reusable assets.
- `reports`: summaries, manifests, test results, review notes, and structured run outputs.

## VCS-Style Code Flow

Use these commands when the runtime asks agents to work in private code checkouts instead of writing directly to the project directory.

Create or refresh the agent checkout:

```powershell
python -m multi_agent_tcp.workspace_api checkout --path "src/parser.py" --path "tests/test_parser.py"
```

or:

```powershell
python -m multi_agent_tcp.workspace_api checkout --scope-path "src/**" --scope-path "tests/**"
```

The command returns JSON with `checkout_path`, `checkout_id`, `base_ref`, and `writable`. Edit files under `checkout_path`. Prefer explicit `--path` entries for focused tasks; use broad `--scope-path` only when the task truly needs that whole area.

Inspect checkout changes:

```powershell
python -m multi_agent_tcp.workspace_api status
python -m multi_agent_tcp.workspace_api diff
python -m multi_agent_tcp.workspace_api diff --summary
```

Submit the checkout as a changeset:

```powershell
python -m multi_agent_tcp.workspace_api submit --task-id task-123 --summary "Implement parser fix"
```

Accepted submissions are merged into the current code target and archived under `changesets/<changeset_id>/`. In project-reference mode the code target is the project directory; in legacy snapshot mode it is the run integration tree. Conflicts return `ok: false`, `status: "conflict"`, and structured file entries with `reason`, hashes, and a merge preview when available. After a conflict, refresh from the latest code target:

```powershell
python -m multi_agent_tcp.workspace_api sync
```

Then reapply the fix in the private checkout and submit again.

## Publish Text

Write UTF-8 text to a specific outcome area. The framework acquires a file lease, writes atomically, records the write in the shared manifest, then releases the lease.

```powershell
"summary" | python -m multi_agent_tcp.workspace_api publish --area reports --path result.md --stdin
```

```powershell
python -m multi_agent_tcp.workspace_api publish --area reports --path status.json --text "{\"ok\": true}"
```

The command prints JSON with `ok`, `area`, and `path`. It does not print the physical workspace location.

For read-modify-write workflows, use `read --json` to obtain the current `version`, then pass it to publish:

```powershell
python -m multi_agent_tcp.workspace_api publish --area reports --path result.md --file updated.md --expected-version 3
```

If another agent published the same path after your read, the command fails with a version conflict instead of overwriting newer content.

## Publish File

Publish any local file, including images and other binary artifacts. The file is copied through the framework API under a lease.

```powershell
python -m multi_agent_tcp.workspace_api publish-file --area artifacts --path images/result.png --file local_result.png
```

The command prints JSON with `ok`, `area`, `path`, and `bytes`. It does not print the physical workspace location.

`publish-file` also supports `--expected-version <N>` for read-modify-write workflows.

## Long-Term Archives

List run archives stored by the framework in the read-only long-term workspace:

```powershell
python -m multi_agent_tcp.workspace_api list-archives
```

Extract a whole archive, or a single relative path inside it, into your private workspace:

```powershell
python -m multi_agent_tcp.workspace_api extract-archive --archive-id run-123-completed --path reports
```

The extract command returns the private path to read. It does not write into the long-term workspace.

## Read Text

Read a UTF-8 text output that has already been published through the shared workspace.

```powershell
python -m multi_agent_tcp.workspace_api read --area reports --path result.md
```

Use `--json` to include the current path version:

```powershell
python -m multi_agent_tcp.workspace_api read --area reports --path result.md --json
```

## List Files

List files previously published under an area.

```powershell
python -m multi_agent_tcp.workspace_api list --area artifacts
```

The command prints JSON containing relative paths.

## Rules

- Do not write task outcomes directly to filesystem paths.
- Treat the project directory as the authoritative code source and final code target, but make task edits in the private checkout.
- Code collaboration must use `checkout -> edit -> status/diff -> submit`.
- Use the temporary shared workspace for reports, artifacts, summaries, file/version references, and changeset ids instead of copying project source trees into it.
- Use `publish-file --area artifacts` for generated assets such as images or binary files.
- Use `publish --area reports` for summaries, manifests, and test output.
- Keep private scratch files private. Only data published through the API is treated as a run outcome.
- If a publish command reports a lock conflict, stop and report the conflict instead of overwriting the file.

## Read/Write Locking

The Workspace API uses a per-file read/write lock:

- Multiple agents may read the same file at the same time.
- While any agent is reading a file, publishing to that same file is blocked.
- While an agent is publishing a file, other agents cannot read or publish that same file.
- Locks are recorded in the shared manifest and have a lease timeout so abandoned processes do not block the run forever.
- For joint editing, combine the lock with version checking: read with `--json`, edit privately, then publish with `--expected-version`.

If an API command returns JSON with `ok: false` and a lock-related `error`, do not retry by writing directly to the filesystem. Report the conflict or choose a different output path.
