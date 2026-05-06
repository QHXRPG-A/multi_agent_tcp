# Workspace API for Blueprint Agents

Agents should publish run outputs through the framework Workspace API instead of writing directly to shared workspace paths.

The framework prepares the API context before the agent starts. Agents do not need to know the physical workspace directories.

## Command

```powershell
python -m multi_agent_tcp.workspace_api <command> [options]
```

## Areas

- `code`: source files or code changes produced by the task.
- `artifacts`: generated images, documents, binary-adjacent text metadata, or other reusable assets.
- `reports`: summaries, manifests, test results, review notes, and structured run outputs.

## Publish Text

Write UTF-8 text to a specific outcome area. The framework acquires a file lease, writes atomically, records the write in the shared manifest, then releases the lease.

```powershell
"summary" | python -m multi_agent_tcp.workspace_api publish --area reports --path result.md --stdin
```

```powershell
python -m multi_agent_tcp.workspace_api publish --area code --path src/example.py --file local_result.py
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

```powershell
python -m multi_agent_tcp.workspace_api publish-file --area code --path src/generated.py --file generated.py
```

The command prints JSON with `ok`, `area`, `path`, and `bytes`. It does not print the physical workspace location.

`publish-file` also supports `--expected-version <N>` for read-modify-write workflows.

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
- Use `publish --area code` for code output.
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
