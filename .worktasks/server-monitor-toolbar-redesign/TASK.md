# Task Memory

## Basic Info

- Task: server-monitor-toolbar-redesign
- Module lock: server_monitor
- Branch: codex/12700k-server-monitor-toolbar-redesign-20260528
- Worktree: D:\SmartCenter\smart-center-worktrees\server-monitor-toolbar-redesign
- Machine: 12700k
- Kind: light
- Started: 2026-05-28 15:29:26
- Expected finish:

## Goal

Redesign the server monitor card header toolbar and include CodeMeter license data in the device information CSV export.

## Current Phase

ready_to_merge

## Change Scope

- `templates/index.html`
- `static/smart-center-time-ntp.css`
- `static/js/views/server-monitor.js`

## Done

- Created task worktree
- Acquired module worklock
- Acquired high-risk `templates_index` and `global` locks
- Redesigned server monitor toolbar into a compact grouped control
- Added CodeMeter installed/running/status/serial/product/expiry/days/license status columns to CSV export
- Export rows now expand across adapters and CodeMeter license rows

## Verified

- `node --check static\js\views\server-monitor.js`
- `git diff --check` (CRLF warnings only)

## Not Verified

- Live browser verification pending after merge/deploy.

## Risks

- Toolbar visual density must be verified in the live layout because the user flagged this area as visually poor.

## Dependencies And Conflicts

- Requires production branch merge and deployment.

## Next

- Commit, merge production, deploy, browser verify, release locks.
