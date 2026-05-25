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

## Notes

- Put complex remote operations in `*.sh` files under this folder.
- Put Windows remote operations in `*.ps1` files under this folder.
- Avoid inline `ssh "..."` commands for anything non-trivial.
- `ssh_exec.ps1` is for Linux targets and runs Bash.
- `ssh_exec_windows.ps1` is for Windows targets from a PowerShell caller.
- `ssh_exec_windows.sh` is for Windows targets from macOS, Linux, or Git Bash.
- The runner uploads the script as a file first, then executes it remotely, so
  quotes, braces, pipes, semicolons, JSON strings, and here-strings remain
  inside the script file instead of being parsed by three shells.
