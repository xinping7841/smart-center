# 任务记忆

## 基本信息

- 任务名：core-config-cleanup
- 模块锁：config_core
- 分支：待创建
- Worktree 路径：../smart-center-worktrees/core-config-cleanup
- 执行机器：待填写
- 任务类型：light
- 开始时间：未开始
- 预计结束：待填写

## 目标

```text
整理公共配置、模块清单、共享状态和文档标记，让后续模块拆分和本地 AI 理解更容易。
```

## 当前阶段

```text
planned
```

## 修改范围

```text
config.py
AGENTS.md
docs/work-session-log/
core/
模块清单文档
```

## 已完成

- 创建任务记忆。

## 已验证

- 尚未开始验证。

## 未验证

- 配置保存。
- 配置中心页面。
- 默认配置兼容。

## 风险点

- `config.py` 是高风险文件，容易影响所有页面。
- 只能做结构性整理和标注，不能随意改默认配置语义。

## 依赖和冲突

```text
如果修改 app.py，需要额外获取 app_bootstrap 锁。
如果修改 background.py，需要额外获取 background_runtime 锁。
```

## 下一步

- 使用 `scripts/collab/start-work.sh --task core-config-cleanup --module config_core --machine <机器名> --kind light` 创建 worktree 和工作锁。

