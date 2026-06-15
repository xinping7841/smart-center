# Task Memory

## Basic Info

- Task: node-red-outdoor-toggle-bounce
- Module lock: frontend_controls
- Branch: codex/12700k-node-red-outdoor-toggle-bounce-20260615
- Worktree: D:\IDE\AI\smart-center-worktrees\node-red-outdoor-toggle-bounce
- Machine: 12700k
- Kind: light
- Started: 2026-06-15 21:10:43
- Expected finish: 2026-06-15

## Goal

Fix the remaining Node-RED/RF outdoor light toggle bounce where the UI immediately returns to the old state after a successful command.

## Current Phase

deploy_verify

## Change Scope

- api/node_red.py: keep in-flight target visible until readback confirms the target state or the in-flight TTL expires.
- static/js/views/universal.js: render Node-RED cards from server target_status before stale readback status.
- static/js/app-runtime.js and templates/index.html: bump cache version for the updated universal view.

## Done

- Created task worktree.
- Acquired module worklock.
- Added backend target_status / target_text exposure while Node-RED control is pending.
- Kept inflight records after successful command when immediate readback still reports the previous state.
- Made the Node-RED outdoor card prioritize target status for checked state, pill text, and class.
- Bumped frontend asset version.

## Verified

- node --check static/js/app-runtime.js
- node --check static/js/views/universal.js
- python -m compileall api/node_red.py
- git diff --check

## Not Verified

- Production deploy and real RF control test still pending at this checkpoint.

## Risks

- Real RF hardware may acknowledge command before status readback changes; UI now holds target state during that window.
- Scope intentionally limited to Node-RED/RF card behavior.

## Dependencies And Conflicts

- Uses frontend_controls lock.
- No changes to electric cabinet, venue light, or Niren Electronics control paths.

## Next

- Commit branch, merge to main, deploy to node-120, and verify with real courtyard_light on/off control.
