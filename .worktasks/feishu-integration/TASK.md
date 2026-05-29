# Task Memory

## Basic Info

- Task: feishu-integration
- Module lock: feishu
- Branch: codex/12700k-feishu-integration-20260524
- Worktree: D:\SmartCenter\smart-center-worktrees\feishu-integration
- Machine: 12700k
- Kind: light
- Started: 2026-05-24 04:14:46
- Expected finish:

## Goal

```text
Add a production Feishu long-connection bot that can answer read-only status commands and push scheduled reports without touching the main Flask startup path.
```

## Current Phase

`	ext
in_progress
`

## Change Scope

```text
services/feishu_bot.py
run_feishu_bot.py
start_feishu_bot.bat
FEISHU_INTEGRATION.md
.env.example
requirements*.txt
.gitignore
```

## Done

- Created task worktree
- Acquired module worklock
- Added standalone Feishu bot service and startup entry points
- Added read-only status/daily/query command handling
- Added deterministic natural-language read-only replies for offline devices, energy, current collector, and server status
- Added optional daily scheduled push via FEISHU_PUSH_TIMES
- Added .env.example for local credential setup
- Set documented production SMART_CENTER_BASE_URL to http://192.168.50.120:6899
- Documented local setup and tests

## Verified

- python -m py_compile services/feishu_bot.py run_feishu_bot.py
- python run_feishu_bot.py --print-status
- $env:SMART_CENTER_BASE_URL='http://192.168.50.120:6899'; python run_feishu_bot.py --print-status
- Local natural-language query simulation against http://192.168.50.120:6899

## Not Verified

- Live Feishu group natural-language replies after the bot process is restarted

## Risks

- lark-oapi must be installed in the runtime environment
- The bot reads local Flask HTTP APIs, so SMART_CENTER_BASE_URL must point at the running smart-center service
- The Feishu app secret previously appeared in a screenshot; rotate it before production use

## Dependencies And Conflicts

`	ext
If this task touches templates/index.html, config.py, background.py, app.py, api/server.py, or snmp_core.py, acquire the related high-risk lock too.
`

## Next

- Restart python run_feishu_bot.py, then send “哪些设备离线” or “昨日电量” in the Feishu group
