# Task Memory

## Basic Info

- Task: node-red-csrf-control-post
- Module lock: frontend_controls
- Branch: codex/12700k-node-red-csrf-control-post-20260615
- Worktree: D:\IDE\AI\smart-center-worktrees\node-red-csrf-control-post
- Machine: 12700k
- Kind: light
- Started: 2026-06-15 22:10:58
- Expected finish: same session

## Goal

Fix the production page click bounce for Node-RED courtyard light by making the frontend control POST include the CSRF token, then deploy and verify with a real browser click.

## Current Phase

local_verified

## Change Scope

- static/js/views/universal.js
- static/js/app-runtime.js
- templates/index.html

## Done

- Created task worktree
- Acquired module worklock
- Identified remaining bounce as CSRF 403 from `/api/node-red/device/courtyard_light/control`
- Patched local HTTP-error-tolerant POST helper to attach `X-CSRF-Token`
- Bumped frontend asset version

## Verified

- `node --check static/js/views/universal.js`
- `node --check static/js/app-runtime.js`
- `git diff --check`

## Not Verified

- production deploy
- production browser click test

## Risks

- Real page click toggles the physical outdoor light; restore original state after validation.

## Dependencies And Conflicts

- Holds `frontend_controls` lock.

## Next

- Commit/push, merge/deploy, test the page click against production.
