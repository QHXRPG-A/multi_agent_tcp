# Remote Client Debugging Workflow

Use this workflow for POPO/user requests about debugging a game client, Hunter,
remote REPL, sending commands to a client, collecting device logs, runtime
hotfix verification, or similar client-side diagnosis. Examples include
`调试我的客户端`, `帮我看客户端日志`, `给客户端发指令`, `Hunter 调试`,
and `验证这个 hotfix`.

Before running any Hunter command, read:

```text
C:/Users/qiuhaoxuan/.codex/skills/AISkills/hunter-cli-debug/SKILL.md
```

Follow that skill for command syntax, token safety, script selection, stdout
capture, file transfer, and hotfix injection behavior. Do not print real tokens
or copy private config values into replies, documents, examples, or logs.

Use the Full Agent Python command declared in `SKILL.md`: `py -3.13`. For
Hunter scripts, do not probe other Python interpreters first. If dependency
confirmation is needed, run `py -3.13 -c "import hunter2_cli; print('ok')"`.

## Required Target Information

The user must provide enough concrete target information to identify one client
device. Valid information includes an IP address, Hunter device id, device name,
binding name, owner/name fragment, or another searchable identifier such as
`SC-b-zhanghao51`.

`local`, `本地`, `我的本地客户端`, or equivalent wording alone is not sufficient
for Full Agent debugging. If the user only says a local target without a concrete
IP/device/name/owner identifier, stop immediately and ask the user for the
client IP, device id, device name, or owner/binding name.

In short: `local` or `本地` alone is not enough.

## Target Resolution

- If the user provides an explicit IP or Hunter device id, use it as the target
  after reading the Hunter skill.
- If the user provides a device name, binding name, owner, or name fragment, run
  `py -3.13 scripts/list_devices.py --filter <term>` from the Hunter skill
  directory to resolve candidates.
- If the lookup returns exactly one matching device, use that resolved target.
- If the lookup returns zero devices, stop and ask the user for a valid IP,
  device id, device name, or owner/binding name.
- If the lookup returns multiple devices, do not execute any debug command.
  Return the candidate list and ask the user to choose one.

Do not fall back to the Hunter skill's default `local` target unless the user
also provided concrete information that resolves to the current machine's
client/device. In this framework, missing or vague target information is a
`needs_input` condition, not an execution default.

## Command Selection

- Use `py -3.13 scripts/run.py` for ordinary client debugging, remote
  Python/GM/console snippets, and stdout checks.
- Add `--log-wait 1` when the requested verification depends on `print(...)`,
  stdout, or client-side log proof.
- Use `--stdin` or `--file` for larger scripts, complex indentation, Markdown
  code blocks, or hotfix-style code. Do not pack large code into a command-line
  string.
- Use `py -3.13 scripts/inject_hotfix.py` only for runtime verification of
  already generated or confirmed hotfix code. This does not write release
  `hotfix.pyw`, does not commit SVN, and does not perform a formal hotfix
  release.

## Safety

- Do not run commands against an ambiguous or unresolved target.
- Before running a command with side effects on another user's device, state the
  resolved target and a concise summary of the code/action.
- Do not edit release files, write formal hotfix files, or run `svn commit`
  unless the user separately asks for the corresponding release workflow.
- If target resolution or Hunter connectivity fails, report the concrete failure
  and ask for the missing or corrected target information.
