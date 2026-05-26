# Task Memory

## Basic Info

- Task: current-collector-zero-deadband
- Module lock: current_collector
- Branch: codex/12700k-current-collector-zero-deadband-20260526
- Worktree: D:\SmartCenter\smart-center-worktrees\current-collector-zero-deadband
- Machine: 12700k
- Kind: light
- Started: 2026-05-26 15:43:00
- Expected finish:

## Goal

```text
Treat disconnected current-collector channels as zero when they only show small ADC/noise drift, while keeping raw measured values visible for diagnostics.
```

## Current Phase

```text
ready_to_commit
```

## Change Scope

```text
api/current_collector.py
config.py
templates/config.html
templates/current_collector.html
static/js/views/current-collector.js
```

## Done

- Created task worktree
- Acquired module worklock
- Added configurable current collector zero deadband, default 0.15A.
- Preserved measured_current/raw_register while using deadbanded current for status, live highlighting, and group totals.
- Added config UI field for zero deadband.
- Bumped current collector page JS cache version.

## Verified

- python -m py_compile config.py api/current_collector.py current_collector.py
- node --check static/js/views/current-collector.js
- Simulated raw 4/4/4/10 on channels 13-16: current=0.0, measured_current=0.04/0.04/0.04/0.10, group total=0.0.

## Not Verified

- Browser visual check after production deploy.

## Risks

- config.py is a high-risk shared file; change is limited to current_collector default normalization.

## Dependencies And Conflicts

```text
Touches config.py only for current_collector default/normalization.
```

## Next

- Commit, push, release current_collector lock, then deploy to 120 and verify live API output.
