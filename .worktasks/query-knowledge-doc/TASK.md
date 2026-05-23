# Task Memory

## Basic Info

- Task: query-knowledge-doc
- Module lock: docs
- Branch: codex/12700k-query-knowledge-doc-20260524
- Worktree: D:\SmartCenter\smart-center-worktrees\query-knowledge-doc
- Machine: 12700k
- Kind: light
- Started: 2026-05-24 05:01:37
- Expected finish:

## Goal

```text
Create a unified read-only query knowledge document for Smart Center and extend Feishu natural-language replies toward status, history, logs, diagnostics, and optional Ollama intent classification.
```

## Current Phase

`	ext
in_progress
`

## Change Scope

```text
docs/QUERY_KNOWLEDGE_BASE.md
FEISHU_INTEGRATION.md
.env.example
services/feishu_bot.py
```

## Done

- Created task worktree
- Acquired module worklock
- Acquired feishu worklock for bot changes
- Added unified query knowledge base and read-only safety policy
- Extended Feishu natural-language read-only query coverage for logs/status/history/diagnostics
- Added optional Ollama qwen3:14b intent classifier with think:false
- Added docs navigation entry for the query knowledge base

## Verified

- python -m py_compile services/feishu_bot.py run_feishu_bot.py
- Local query simulations against http://192.168.50.120:6899:
  - 最近自动化日志
  - 最近灯光日志
  - UPS状态
  - 机房温度
  - 空调状态
  - 代理状态
  - 本地模型状态
  - 开灯 / 重启node-120 refusal

## Not Verified

- Live Feishu group message after restart
- Ollama classifier live call; 192.168.50.120:11434 refused from this machine, likely localhost-only on node-120

## Risks

- Ollama may only listen on node-120 localhost; FEISHU_NL_MODEL_URL must match where the bot runs

## Dependencies And Conflicts

`	ext
If this task touches templates/index.html, config.py, background.py, app.py, api/server.py, or snmp_core.py, acquire the related high-risk lock too.
`

## Next

- Commit, push, and release docs/feishu locks
