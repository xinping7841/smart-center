# PowerShell Collaboration Quickstart

Use this when a Windows machine does not have Git Bash. Run commands from the root of `smart-center-clean`.

## Fresh Clone

```powershell
New-Item -ItemType Directory -Force D:\SmartCenter
Set-Location D:\SmartCenter
git clone node-120-ts:/srv/git/smart-center-clean.git smart-center-clean
Set-Location D:\SmartCenter\smart-center-clean
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/bootstrap-other-machine.ps1 -Machine 12700k -WorktreeBase D:\SmartCenter\smart-center-worktrees
```

## Check Before Work

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/check-sync.ps1 -WorktreeBase D:\SmartCenter\smart-center-worktrees
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/status-worktasks.ps1
```

## Start A Task

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/start-work.ps1 `
  -Task server-monitor-refactor `
  -Module server_monitor `
  -Machine 12700k `
  -Kind heavy `
  -WorktreeBase D:\SmartCenter\smart-center-worktrees
```

The script creates an isolated worktree, writes `.worktasks/<task>/TASK.md` and `STATUS.json`, then publishes `locks/<module>.json` to `coordination/worklocks`.

## Finish A Task

Run this inside the task worktree:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/finish-work.ps1 `
  -Message "refactor: split server monitor module" `
  -ReleaseLock server_monitor
```

## Notes

- Keep no more than 5 active worktrees per machine.
- Acquire a module lock before editing high-risk shared files.
- Never use `git reset --hard`, `git checkout -- <file>`, or `git clean -fd` to handle another person's changes.
