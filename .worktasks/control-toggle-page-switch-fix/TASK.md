# Task Memory

## Basic Info

- Task: control-toggle-page-switch-fix
- Module lock: frontend_controls
- Branch: codex/12700k-control-toggle-page-switch-fix-20260615
- Worktree: D:\IDE\AI\smart-center-worktrees\control-toggle-page-switch-fix
- Machine: 12700k
- Kind: light
- Started: 2026-06-15 20:37:13
- Expected finish:

## Goal

Fix two production UI bugs before urllib migration:

- Prevent normal operator pages from auto-switching unless carousel is explicitly requested.
- Prevent control toggles from visually bouncing back while device state readback is still catching up.

## Current Phase

```text
ready_to_finish
```

## Change Scope

```text
static/js/app-runtime.js
static/js/views/light-runtime.js
static/js/views/universal.js
templates/index.html
```

## Done

- Created task worktree
- Acquired module worklock
- Limited sidebar carousel startup to explicit URL carousel mode or manual home carousel toggle
- Added light channel desired-state hold and 30s verification window
- Added protocol output desired-state hold and 30s verification window
- Added Node-RED device desired-state hold and 30s verification window
- Bumped app-runtime and lazy module asset versions

## Verified

- node --check static/js/app-runtime.js
- node --check static/js/views/light-runtime.js
- node --check static/js/views/universal.js
- python -m compileall app.py api services runtime config.py background.py power.py snmp_core.py
- git diff --check

## Not Verified

- Browser/manual production device interaction not run from this task to avoid triggering real controls without operator confirmation.

## Risks

- Frontend now keeps target state for up to 30s if readback lags. Actual failures still roll back on API failure or after timeout.

## Dependencies And Conflicts

```text
No high-risk backend files touched.
```

## Next

- Deploy to node-120 and manually verify one low-risk switch interaction with an operator present.
