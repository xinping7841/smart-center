# 任务记忆

## 基本信息

- 任务名：dashboard-apple-audio-status
- 模块锁：apple_audio
- 分支：codex/mac-dashboard-apple-audio-status-20260604
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/apple-audio-bluetooth-local-player
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-04

## 目标

首页主界面增加音乐播放器只读状态展示，不触发播放/停止/控制动作。

## 修改范围

api/dashboard.py
apple_audio_core.py
static/js/views/dashboard-shell.js
static/js/views/dashboard-summary.js
static/css/views/ui-wide-1080.css
static/js/app-runtime.js
templates/index.html
tests/test_apple_audio_local_player.py
docs/LOCAL_MODEL_QUERY_INTENTS.jsonl
docs/QUERY_KNOWLEDGE_BASE.md

## 已完成

- 首页主界面新增音乐播放器只读状态卡。
- `/api/dashboard/summary` 新增 `modules.apple_audio` compact 状态，不携带完整曲库数组。
- 状态矩阵增加“音乐播放器”。
- 123 本地模型知识索引补充音乐播放器状态查询路由。
- 本地 `.venv` 验证环境已补齐。

## 已验证

- `.venv/bin/python -m unittest tests.test_apple_audio_local_player -v`
- `.venv/bin/python -m compileall apple_audio_core.py api/dashboard.py api/apple_audio.py`
- `node --check static/js/views/dashboard-summary.js`
- `node --check static/js/views/dashboard-shell.js`
- `node --check static/js/app-runtime.js`
- `docs/LOCAL_MODEL_QUERY_INTENTS.jsonl` 逐行 JSON 解析通过。
- 本地 6901 首页浏览器验证：音乐卡存在、状态矩阵 tile 存在、无控制按钮、无 section 重叠。

## 风险点

- 首页新增一个卡片会改变 4K 固定布局右侧区域密度；已避免与 SNMP/日志卡重叠。
