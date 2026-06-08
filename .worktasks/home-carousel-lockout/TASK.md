# Task Memory

## Basic Info

- Task: home-carousel-lockout
- Module locks: frontend_assets, templates_index
- Branch: codex/12700k-home-carousel-lockout-20260608
- Worktree: D:/SmartCenter/smart-center-worktrees/ui-review-tone-down
- Machine: 12700k
- Kind: light
- Started: 2026-06-08
- Expected finish:

## Goal

```text
Add a homepage rolling playback / carousel switch, reuse safe read-only dashboard navigation behavior, and block device controls plus system configuration while rolling playback is enabled.
```

## Current Phase

```text
ready_for_merge_deploy
```

## Change Scope

```text
templates/index.html
static/js/app-runtime.js
static/css/views/ui-dark-ops-palette.css
docs/QUERY_KNOWLEDGE_BASE.md
docs/LOCAL_MODEL_CONTROL_INTENTS.jsonl
```

## Done

- Reused existing worktree because this machine already has five task worktrees.
- Created task branch from origin/main.
- Ran collaboration sync check before edits.
- Added homepage top-header 巡屏 switch with persistent localStorage state.
- Reused existing sidebar carousel runtime for homepage rolling playback.
- Added display-only lockout while 巡屏 is enabled:
  - blocks system config links/buttons.
  - blocks inline control clicks and permission-gated control/config/edit/manage actions.
  - blocks known control/config request URLs through guarded fetchJson/fetchJsonLoose/postJsonLoose bridges.
  - excludes automation page from carousel rotation while display lockout is active.
- Updated AI_* markers on template/runtime/CSS.
- Updated query knowledge and control intent seed for 本地 AI 模型 learning.

## Verified

- `bash scripts/collab/check-sync.sh`
- `node --check static\\js\\app-runtime.js`
- `git diff --check` passed with CRLF warnings only.
- `python -m compileall app.py api services runtime config.py background.py power.py snmp_core.py`
- Static Node assertions confirmed guarded helpers and known control URL patterns are present.
- Browser/static harness on `127.0.0.1:8798` confirmed:
  - initial switch state is `关闭` and config entry is not disabled.
  - enabling the switch changes state to `播放中`, adds `home-carousel-active`, and disables config entry.
  - clicking fake config/control targets shows `滚动播放中，请先关闭巡屏再进行控制或系统配置` and does not call the fake control handler.

## Not Verified

- Full Flask local runtime was not started because this Windows environment does not have the project Flask dependency installed outside a venv.
- Production deploy/restart verification pending.
- No real device control was triggered.

## Risks

- High-risk template anchors and global onclick bridges are touched.
- Request guard intentionally blocks only known control/config side-effect URLs so status polling can continue during 巡屏.
- Real device control must not be triggered during production verification.

## Dependencies And Conflicts

```text
Requires frontend_assets and templates_index locks before code edits.
```

## Next

- Commit and push branch.
- Merge to main after final sync check.
- Deploy/restart on node-120 and verify service active plus homepage asset version.
- Release frontend_assets and templates_index locks.
