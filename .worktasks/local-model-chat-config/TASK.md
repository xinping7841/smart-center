# Task Memory

## Basic Info

- Task: local-model-chat-config
- Module lock: local_model
- Extra lock: templates_index
- Branch: codex/12700k-local-model-chat-config-20260522
- Worktree: D:\smart-center-work\smart-center-worktrees\local-model-chat-config
- Machine: 12700k
- Kind: heavy
- Started: 2026-05-22 18:26:32
- Updated: 2026-05-22 18:55:00

## Goal

把本地模型对话框和后台配置接入中控主界面，默认对接 122 的知识代理/vLLM 服务。

## Current Phase

verified

## Change Scope

- api/local_model.py
- templates/index.html
- templates/local_model.html
- static/js/views/local-model.js
- static/css/views/local-model.css
- static/js/views/README.md
- docs/MODULE_INDEX.yaml

## Done

- Created task worktree.
- Acquired module worklock local_model.
- Acquired high-risk worklock templates_index.
- Added main sidebar view-local_model with chat, status, backend config, and training export panels.
- Updated default model config to 122 knowledge proxy 8001 + vLLM upstream 8000 + gemma-4-e4b-awq-int4 + 32768 context.
- Added dual endpoint health check response fields.
- Made local-model.js safe to initialize in both index.html and standalone /local-model.
- Updated module docs for the new main-page entry.

## Verified

- python -m py_compile api/local_model.py
- node --check static/js/views/local-model.js
- git diff --check (only Windows CRLF warnings)
- Flask template render contains view-local_model, local model CSS/JS, vLLM field, and max context field.
- Browser check on lightweight local server: ?view=local_model active/display block, chat/config/export visible.
- /api/local-model/health returns proxy_online=True, vllm_online=True, docs_count=392, and max_model_len=32768 against 192.168.50.122.
- /api/local-model/chat returns ok=True from model gemma-4-e4b-awq-int4.

## Not Verified

- Full production service restart on 120 yet.

## Risks

- templates/index.html touched; templates_index lock is held until finish.
- /api/local-model/config save still requires system.config permission by design.

## Dependencies And Conflicts

No other active worklocks besides this task's local_model/templates_index locks when edits started.

## Next

- Commit/push task branch.
- Merge/push codex/12700k-dev and deploy to 120 if required.
- Release local_model and templates_index locks.
