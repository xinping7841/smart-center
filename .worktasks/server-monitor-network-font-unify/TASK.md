# Task Memory

## Basic Info

- Task: server-monitor-network-font-unify
- Module lock: server_monitor
- Branch: codex/12700k-server-monitor-network-font-unify-20260528
- Worktree: D:\SmartCenter\smart-center-worktrees\server-monitor-network-font-unify
- Machine: 12700k
- Kind: light
- Started: 2026-05-28 13:47:03
- Expected finish:

## Goal

Unify server monitor NIC typography with the surrounding hardware values.

## Current Phase

in_progress

## Change Scope

- static/smart-center-time-ntp.css
- templates/index.html

## Done

- Created task worktree
- Acquired module worklock
- Changed adapter index/name/meta font weights to match hardware rows
- Bumped server monitor asset version to server-network-font-unify
- Deployed production release server-font-unify-1004484

## Verified

- node --check static/js/views/server-monitor.js
- git diff --check
- Browser live verification: hardware value, adapter name, and adapter meta all compute to 12px / 400 / rgb(203,213,225)

## Not Verified

- None

## Risks

- templates/index.html touched for cache bust and scoped hotfix; templates_index and global locks acquired.

## Dependencies And Conflicts

- Preserve current live release contents by overlaying only server monitor assets and template.

## Next

- Release locks.
