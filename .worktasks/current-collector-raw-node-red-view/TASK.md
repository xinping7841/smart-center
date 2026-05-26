# Task Memory

## Basic Info

- Task: current-collector-raw-node-red-view
- Module lock: current_collector
- Branch: codex/12700k-current-collector-raw-node-red-view-20260526
- Worktree: D:\SmartCenter\smart-center-worktrees\current-collector-raw-node-red-view
- Machine: 12700k
- Kind: light
- Started: 2026-05-26 14:15:47
- Expected finish:

## Goal

Make the current collector raw area show pure physical channel data and add a Node-RED live raw data page on node-121 for on-site verification.

## Current Phase

ready_for_review

## Change Scope

- static/js/views/current-collector.js
- templates/current_collector.html
- deploy/node_red_current_collector/deploy_current_collector_flow.py
- node-121 /home/xinping/.node-red/flows.json

## Done

- Created task worktree
- Acquired module worklock
- Changed the Smart Center raw section to render channel 1..N directly from snapshot.currents/raw_registers.
- Removed channel name/visibility/sort influence from the raw channel display.
- Added Node-RED live raw HTML endpoint /current/raw and JSON endpoint /current/raw.json.
- Deployed the Node-RED flow update on node-121 with backup /home/xinping/.node-red/flows.json.backup-current-collector-20260526_142231.

## Verified

- node --check static/js/views/current-collector.js
- python -m py_compile deploy/node_red_current_collector/deploy_current_collector_flow.py
- node-121 Node-RED active after restart
- curl http://127.0.0.1:1880/current/raw.json returned ok=true with 16 channels
- node-120 /api/current-collector/status still receives Node-RED push data

## Not Verified

- Node-RED page uses latest flow context data and does not perform extra reads, so it depends on the 5-second polling flow being active.

## Risks

- Commit and push branch, then deploy Smart Center page update to node-120 if needed.

## Dependencies And Conflicts

`	ext
If this task touches templates/index.html, config.py, background.py, app.py, api/server.py, or snmp_core.py, acquire the related high-risk lock too.
`

## Next

-
