# Remote Script Runner

Use `ssh_exec.ps1` to avoid PowerShell quoting/escaping issues when running complex remote commands.

## Usage

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\ssh_exec.ps1 `
  -HostName zhongkong `
  -ScriptPath .\scripts\remote\check_status.sh
```

## Notes

- Put complex remote operations in `*.sh` files under this folder.
- Keep script bodies in Bash syntax only.
- Avoid inline `ssh "..."` commands for anything non-trivial.
- This runner is designed to avoid PowerShell + SSH quote escaping issues.
