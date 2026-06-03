# 任务记忆

## 基本信息

- 任务名：code-knowledge-index-ai-markers
- 模块锁：backend_api
- 分支：codex/mac-code-knowledge-index-ai-markers-20260603
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees-active/code-knowledge-index-ai-markers
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-03 22:44:11
- 预计结束：

## 目标

```text
建立 123 本地模型长期代码知识索引基础：补齐第一批核心 AI_* 标注，
强化代码知识导出覆盖率报告，并导出/刷新生产代码知识包。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
docs/AI_CODE_MARKERS.md
docs/AI_NAVIGATION.md
docs/LOCAL_MODEL_LEARNING.md
scripts/export_code_knowledge.py
scripts/export_local_model_training.py
scripts/ssh_exec.sh
scripts/collab/*.sh
templates/index.html
templates/config.html
api/auth_api.py
api/hy_edge.py
apple_audio_core.py
control_center_core.py
power.py
event_logger.py
services/meter_center.py
services/meter_payloads.py
services/miio_hvac.py
services/mqtt_env_bridge.py
services/cabinet_gateway.py
static/js/core/viewport-layout.js
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 额外获取 templates_index_html 锁
- 添加长期记忆：后续修改 Smart Center 代码必须同步维护 AI_* 标注
- 第一批核心文件补齐 AI_* 标注
- 代码知识导出器增加 ai_marker_coverage_*.json

## 已验证

- 待验证

## 未验证

- 本地 compile/export
- 远程生产代码知识导出
- 123 代码知识问答探针

## 风险点

- 本次只改注释/知识导出，不改业务行为；仍需验证 Python 语法和导出 JSON schema

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 
