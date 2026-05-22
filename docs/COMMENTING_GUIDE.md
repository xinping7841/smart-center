# Commenting Guide

Last updated: 2026-05-22

Comments should help future humans and local AI understand module boundaries and operational risk. They should not narrate obvious code.

## Add Comments For

- Module ownership and what belongs elsewhere.
- Physical device control side effects.
- Polling/cache freshness rules.
- Legacy route or payload compatibility.
- Generated code templates, especially Windows Agent and deploy scripts.
- Concurrency locks and hardware timing delays.

## Avoid Comments For

- Simple assignments.
- Repeating the function name in prose.
- Temporary guesses that will become stale.
- Large commented-out code blocks.

## Module Header Template

```python
# Module role: short sentence.
# Boundaries: what this file owns; what should stay in service/core modules.
# Compatibility: routes or payload fields that external clients rely on.
```

## Function Comment Template

```python
# Keep this route thin: it preserves the public payload and delegates expensive work.
```

## AI Marker Template

Use normal comments, not special syntax, so tools can read them everywhere:

```python
# AI map: server_monitor.agent_generation. Bump AGENT_VERSION when editing this template.
```

## AI Module Header Template

Use this when a file is an important route, runtime service, frontend view, or device protocol module:

```python
# AI_MODULE: server_monitor_api
# AI_PURPOSE: 服务器监控 API、Agent 分发、关机/重启/唤醒命令队列。
# AI_BOUNDARY: 不在这里写前端布局；新增硬件解析优先放到 service/helper。
# AI_DATA_FLOW: Windows/Linux Agent -> /report -> monitor.db -> /api/machines -> 前端卡片。
# AI_RISK: 高，涉及远程关机、网络唤醒、Agent 自动更新和加密锁状态。
# AI_COMPAT: /report、/agent/config、/agent/worker.json、/deploy_agent.bat 不能随意改字段。
# AI_SEARCH_KEYWORDS: server, machines, agent, wol, codemeter, shutdown.
```

Full marker rules live in `docs/AI_CODE_MARKERS.md`.
