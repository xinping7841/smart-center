# Remote Script Runner

Use script upload runners to avoid PowerShell quoting/escaping issues when
running complex remote commands. Do not put complex logic directly inside
`ssh "..."`.

## Linux target

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\ssh_exec.ps1 `
  -HostName zhongkong `
  -ScriptPath .\scripts\remote\check_status.sh
```

## Windows target

From Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\ssh_exec_windows.ps1 `
  -HostName lk402 `
  -ScriptPath .\scripts\remote\check_windows_smart_center.ps1
```

From macOS/Linux/Git Bash:

```bash
bash scripts/ssh_exec_windows.sh \
  --host lk402 \
  --script scripts/remote/check_windows_smart_center.ps1
```

For a Windows Smart Center checkout in the standard location, the checker
reports OS, Git/Python/Node versions, repo status, worktrees, and collaboration
locks.

## Smoke tests

Run these after changing the runners. They intentionally include Chinese text,
JSON, pipes, awk, braces, and mixed quotes.

```bash
bash scripts/ssh_exec.sh \
  --host node-120-ts \
  --remote-workdir /srv/git/smart-center-clean.git \
  --script scripts/remote/quote_smoke.sh

bash scripts/ssh_exec.sh \
  --host node-120-ts \
  --remote-workdir /srv/git/smart-center-clean.git \
  --script scripts/remote/quote_smoke.py

bash scripts/ssh_exec_windows.sh \
  --host 12700k-ts \
  --remote-workdir D:\SmartCenter\smart-center-clean \
  --script scripts/remote/quote_smoke_windows.ps1
```

## Notes

- Put complex remote operations in `*.sh` files under this folder.
- Put Windows remote operations in `*.ps1` files under this folder.
- Avoid inline `ssh "..."` commands for anything non-trivial. If the command
  contains pipes, awk, JSON, here-docs, PowerShell script blocks, braces,
  nested quotes, or multiple statements, upload a script and run it through a
  runner instead.
- Use `scripts/ssh_exec.sh` for Linux/macOS targets from macOS, Linux, or Git
  Bash.
- `ssh_exec.ps1` is for Linux targets and runs Bash.
- `ssh_exec_windows.ps1` is for Windows targets from a PowerShell caller.
- `ssh_exec_windows.sh` is for Windows targets from macOS, Linux, or Git Bash.
- The runner uploads the script as a file first, then executes it remotely, so
  quotes, braces, pipes, semicolons, JSON strings, and here-strings remain
  inside the script file instead of being parsed by three shells.
- Do not build ad-hoc quote-heavy smoke commands inline. Add a script under
  `scripts/remote/` and execute it through a runner instead.
