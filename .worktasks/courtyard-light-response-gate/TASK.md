# Task Memory

## Basic Info

- Task: courtyard-light-response-gate
- Module lock: node_red
- Branch: codex/12700k-courtyard-light-response-gate-20260526
- Worktree: D:\SmartCenter\smart-center-worktrees\courtyard-light-response-gate
- Machine: 12700k
- Kind: light
- Started: 2026-05-26 13:57:11
- Expected finish:

## Goal

Set courtyard light cooldown to 0 and block repeated controls while the Node-RED command/status readback is still in progress.

## Current Phase

ready_for_review

## Change Scope

- api/node_red.py
- static/js/views/universal.js

## Done

- Created task worktree
- Acquired module worklock
- Changed courtyard_light control_cooldown_sec from 8 to 0
- Added backend in-flight control gate until command response and status readback finish
- Added frontend pending/readback display and disabled switch state

## Verified

- python -m compileall api/node_red.py
- node --check static/js/views/universal.js
- git diff --check

## Not Verified

-

## Risks

- If Node-RED accepts the command but status readback fails, the in-flight gate remains until TTL expiry to avoid immediate repeated controls.

## Dependencies And Conflicts

`	ext
If this task touches templates/index.html, config.py, background.py, app.py, api/server.py, or snmp_core.py, acquire the related high-risk lock too.
`

## Next

- Push branch for review/deployment decision.
