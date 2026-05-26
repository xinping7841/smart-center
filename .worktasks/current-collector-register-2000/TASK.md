# Task Memory

## Basic Info

- Task: current-collector-register-2000
- Module lock: current_collector
- Branch: codex/12700k-current-collector-register-2000-20260526
- Worktree: D:\SmartCenter\smart-center-worktrees\current-collector-register-2000
- Machine: 12700k
- Kind: light
- Started: 2026-05-26 15:29:18
- Expected finish:

## Goal

```text
Fix current collector channel 1-4 zero readings by using the verified 0x2000
16-channel register block and documenting Node-RED as the single live RTU reader.
```

## Current Phase

```text
done
```

## Change Scope

```text
config.py
api/current_collector.py
templates/config.html
deploy/node_red_current_collector/deploy_current_collector_flow.py
deploy/node_red_current_collector/README.md
```

## Done

- Created task worktree
- Acquired module worklock
- Changed current collector defaults from 0x0000 to 0x2000/8192.
- Updated Node-RED deployment flow to publish host/port/channel metadata and cache latest raw frame in flow/global context.
- Documented that Node-RED should be the single live reader for 192.168.50.109:502.
- Applied runtime fix on node-121 Node-RED and synchronized node-120 current_collector.register to 8192.

## Verified

- `python -m py_compile deploy\node_red_current_collector\deploy_current_collector_flow.py config.py api\current_collector.py`
- Runtime: node-121 `/current/raw.json` returned 10/10 samples with nonzero channels 1-4 from register 0x2000.
- Runtime: node-120 `/api/current-collector/status` shows register 8192 and channel 1-4 current values.

## Not Verified

- Full frontend browser regression not run; change is config/default/deploy-flow scoped.

## Risks

- Existing stored configs with an explicit register value are preserved by normalization; production config was manually updated to 8192.

## Dependencies And Conflicts

`	ext
If this task touches templates/index.html, config.py, background.py, app.py, api/server.py, or snmp_core.py, acquire the related high-risk lock too.
`

## Next

- Merge this branch after review so future Node-RED redeploys keep 0x2000.
