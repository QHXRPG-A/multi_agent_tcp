# Graph File Workflow

Use this workflow for POPO/user messages that include a `.graph` file, uploaded
graph attachment, graph path, or graph filename.

## Fixed Sources

- Graph skill:
  `F:\src\Package\Script\Python\.codex\skills\messiah-character-graph`
- Graph skill entry:
  `F:\src\Package\Script\Python\.codex\skills\messiah-character-graph\SKILL.md`
- Project graph root:
  `F:\src\Package\Graph`

## Resolve The Graph

1. If the current message includes attachments, inspect the normalized
   `attachments` payload or the `[Current POPO Attachments]` section first.
   Prefer an attachment item whose `path` exists locally and whose name or path
   ends with `.graph`.
2. If the user provided an absolute path, use it only when it exists and ends
   with `.graph`.
3. If the user provided only a filename or relative path, search under
   `F:\src\Package\Graph` for the exact filename first, then for a relative-path
   suffix match.
4. If exactly one graph is found, use that path.
5. If multiple graphs match, ask the user to choose one and call
   `agent_task_status` with `needs_input` before the POPO-visible reply.
6. If no graph is found, ask the user to upload the `.graph` file or provide the
   full path, then call `agent_task_status` with `needs_input`.

Do not guess between multiple project graph files with the same basename.

## Load The Graph Skill

Before analysis, debugging, design, or modification:

1. Read
   `F:\src\Package\Script\Python\.codex\skills\messiah-character-graph\SKILL.md`.
2. Follow that skill's routing:
   - existing graph analysis: `scripts\inspect_graph.py` plus
     `references\graph-parse-workflow.md`;
   - graph creation or modification: `references\graph-build-workflow.md` and
     the relevant generator/compiler scripts;
   - node semantics: `references\knowledge-routing.md` and the matching
     `graph-node-reference*` expert entries.
3. Use the Full Agent Python command from `SKILL.md`: `py -3.13`.

For analysis, run:

```powershell
py -3.13 F:\src\Package\Script\Python\.codex\skills\messiah-character-graph\scripts\inspect_graph.py --graph <graph-path>
```

When the user gives an event, variable, node, or node type, add the matching
focus argument:

```powershell
--focus event:<name>
--focus var:<name>
--focus node:<name>
--focus type:<Type>
```

## Analysis Output

Answer only the current request. Prefer:

- resolved graph path;
- root/state-machine structure;
- relevant transitions, events, variables, cues, and key nodes;
- node meaning backed by the graph skill's knowledge sources;
- gameplay interpretation;
- uncertainty or follow-up search suggestions when static graph facts are not
  enough.

Do not paste the full XML or raw inspection JSON unless the user explicitly asks
for it.

## Modification Flow

For graph modification requests:

1. Resolve the target graph and load the graph skill first.
2. Inspect the original graph and keep the inspection result as the before
   evidence.
3. Make the smallest graph change that satisfies the request. Preserve existing
   manual layout; for existing graphs, only lay out the new or generated local
   subtree when the graph skill requires layout.
4. Re-run `inspect_graph.py` on the edited graph and, when relevant, with the
   same focus argument.
5. Summarize the changed graph path, the behavioral change, and the validation
   result.
6. Show a concise diff summary. Use SVN or text/XML diff evidence when
   available, but do not dump the whole graph file.

Do not run `svn commit`, send the file, or mark the task completed until the
post-modification delivery decision is handled.

## Post-Modification Delivery

After a graph has been modified and validated, ask the user to choose exactly
one delivery path:

- Send the edited graph file back to the current POPO user with
  `blueprint_send_popo_file(path)`.
- Commit the graph through SVN.

If the user chooses file send, call `blueprint_send_popo_file(path)` with only
the local graph path. Do not ask for robot credentials, receiver ids, upload
tokens, or POPO app keys.

If the user chooses SVN commit:

1. Require an explicit ticket/order number before committing.
2. Ask for the ticket/order number if it was not already provided, then call
   `agent_task_status` with `needs_input`.
3. Run `svn commit` only after the user explicitly confirms the commit and the
   ticket/order number is available.
4. Include the committed graph path and SVN revision in the final reply.

Never run `svn commit` without both explicit user confirmation and a real
ticket/order number.
