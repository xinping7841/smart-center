# Task Memory

## Basic Info

- Task: fix-log-sidebar-mojibake
- Module lock: logs
- Branch: codex/12700k-fix-log-sidebar-mojibake-20260526
- Worktree: D:\SmartCenter\smart-center-worktrees\fix-log-sidebar-mojibake
- Machine: 12700k
- Kind: light
- Started: 2026-05-26 13:05:52
- Expected finish:

## Goal

修复侧边栏日志入口显示为 `?? ????` 的乱码问题，并让旧配置中的坏侧边栏文案在启动时自动恢复。

## Current Phase

`	ext
in_progress
`

## Change Scope

- `templates/index.html`: 修正日志中心兜底入口的显示文本和图标。
- `config.py`: 将日志中心纳入默认侧边栏，并按模块 id 修复问号/乱码的 `icon` 与 `name`。

## Done

- Created task worktree
- Acquired module worklock
- Acquired high-risk worklocks `templates_index` and `config_core`
- Replaced hard-coded `?? ????` logs navigation with `日志中心`
- Added sidebar self-healing for broken configured labels/icons

## Verified

- `python -m compileall config.py api runtime services app.py background.py`
- `PYTHONIOENCODING=utf-8 python -c ...` confirmed loaded sidebar contains `{"id": "logs", "icon": "🧾", "name": "日志中心"}`

## Not Verified

- Browser screenshot not run yet; change is server-rendered template/config only.

## Risks

- `config.py` migration touches startup config normalization; scoped to sidebar items and preserves existing visible/sort values unless text is broken or item is missing.

## Dependencies And Conflicts

- Locks held: `logs`, `templates_index`, `config_core`.

## Next

- Commit, push, and release locks.
