# Task Memory

## Basic Info

- Task: node-red-click-optimistic-card
- Module lock: frontend_controls
- Branch: codex/12700k-node-red-click-optimistic-card-20260615
- Worktree: D:\IDE\AI\smart-center-worktrees\node-red-click-optimistic-card
- Machine: 12700k
- Kind: light
- Started: 2026-06-15 21:50:31
- Expected finish: 2026-06-15

## Goal

Fix the Node-RED courtyard light UI toggle so a page click immediately keeps the target visual state and stale status polling cannot bounce the switch back.

## Current Phase

completed

## Change Scope

- static/js/views/universal.js
- static/js/app-runtime.js
- templates/index.html

## Done

- Created task worktree
- Acquired module worklock
- Added Node-RED device cache and single-card optimistic render
- On click, immediately sets checkbox/card to the target state
- Success path renders returned/pending target device instead of immediately fetching stale status
- Verification poll is delayed and local desired state keeps stale readback from bouncing the switch
- Bumped frontend asset version to force fresh browser assets

## Verified

- node --check static/js/views/universal.js
- node --check static/js/app-runtime.js
- git diff --check
- Mocked frontend test: current off, click on, control returns pending target on, stale off poll still keeps checkbox checked

## Not Verified

- Live browser click against production after deploy; pending deployment.

## Risks

- UI holds the requested target for up to CONTROL_VERIFY_HOLD_MS while readback catches up. This is intentional to prevent visual bounce on slow RF/status confirmation.

## Dependencies And Conflicts

None observed.

## Next

- Commit, merge to main, deploy to node-120, then verify production asset version and API status.
