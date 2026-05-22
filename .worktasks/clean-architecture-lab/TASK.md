# Task Memory

## Basic Info

- Task: clean-architecture-lab
- Module lock: clean_architecture
- Branch: codex/12700k-clean-architecture-lab-20260522
- Worktree: D:\smart-center-work\smart-center-worktrees\clean-architecture-lab
- Machine: 12700k
- Kind: heavy
- Started: 2026-05-22 21:49:31
- Expected finish:

## Goal

```text
Build a clean-lab architecture branch without touching production: thin app entrypoint,
explicit app assembly modules, shared physical-control dry-run guard, and removal of
confirmed historical/generated source clutter.
```

## Current Phase

```text
validated
```

## Change Scope

```text
app.py
modules/app/*
runtime/control_safety.py
api control endpoints
apple_audio_core.py
docs/*
root historical/generated files
```

## Done

- Created task worktree
- Acquired module worklock
- Split Flask app assembly out of app.py.
- Added shared dry-run/read-only/disabled guard for physical control routes.
- Converted Apple Audio service to lazy initialization so API imports do not scan NAS music on startup.
- Removed confirmed stale root duplicate/generated files from the clean-lab branch.
- Documented module ownership and validation flow.

## Verified

- `python -m compileall app.py api services runtime modules apple_audio_core.py config.py background.py snmp_core.py`
- Flask app factory creates 174 routes with expected `/`, `/config`, `/api/status`, `/api/projector/status`, `/api/machines`, `/api/control_center/execute`, and `/api/light/control` routes.
- `api.apple_audio` import reduced from timeout over 12 seconds to about 0.28 seconds.
- Dry-run HTTP smoke checks returned `blocked=True`, `control_mode=dry_run`, `dry_run=True` for power, projector, screen, sequencer, UPS, HVAC, light, server command, and universal control.

## Not Verified

- No production deploy or merge was performed.
- No real device command was sent during validation.

## Risks

- `config.py` still auto-migrates `config.json` on import; validation can dirty local runtime/config files.
- `api/server.py` still has legacy PowerShell string SyntaxWarnings during compile.
- Normal production mode is unchanged; dry-run protection only activates when the control-mode environment/header/query option is set.

## Dependencies And Conflicts

`	ext
If this task touches templates/index.html, config.py, background.py, app.py, api/server.py, or snmp_core.py, acquire the related high-risk lock too.
`

## Next

- Review branch diff, deploy to a test port with `SMART_CENTER_CONTROL_MODE=dry_run`, then decide whether to merge.
