# Task Memory

## Basic Info

- Task: current-collector-sidebar-unify
- Module lock: frontend_controls
- Branch: codex/12700k-current-collector-sidebar-unify-20260615
- Worktree: D:\IDE\AI\smart-center-worktrees\current-collector-sidebar-unify
- Machine: 12700k
- Kind: light
- Started: 2026-06-15 22:59:33
- Expected finish:

## Goal

Fix the standalone `/current-collector` sidebar so it matches the main Smart Center shell navigation and title.

## Current Phase

in_progress

## Change Scope

- `templates/current_collector.html`: align logo and fallback navigation entries with the main sidebar.
- `api/current_collector.py`: pass `current_user` to the template for the config-entry permission check.

## Done

- Created task worktree
- Acquired module worklock
- Updated current collector sidebar title and fallback navigation entries
- Added current user context for config-link visibility

## Verified

- `python -m compileall api\current_collector.py`
- `git diff --check`

## Not Verified

- Local Jinja render smoke test skipped because the system Python does not have `jinja2` installed.
- Production browser verification pending

## Risks

- Low: isolated to the standalone current collector page sidebar and its current-user context.

## Dependencies And Conflicts

No high-risk shared template or runtime files touched.

## Next

- Run local checks
- Commit, push, merge, deploy, and verify on production
