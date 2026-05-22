# 任务记忆

## 基本信息

- 任务名：validation-docs-report
- 模块锁：docs
- 分支：待创建
- Worktree 路径：../smart-center-worktrees/validation-docs-report
- 执行机器：待填写
- 任务类型：light
- 开始时间：未开始
- 预计结束：待填写

## 目标

```text
维护验证脚本、阶段报告、协作文档和本地 AI 学习说明，为其他任务提供交接和验收支持。
```

## 当前阶段

```text
planned
```

## 修改范围

```text
docs/
scripts/collab/
reports/
.worktasks/
```

## 已完成

- 创建任务记忆。

## 已验证

- 尚未开始验证。

## 未验证

- 协作脚本在另一台机器上的首次运行。
- 夜间无人拆分交接流程。

## 风险点

- 文档任务通常风险低，但不能误改业务代码。
- 如果脚本涉及 Git 操作，必须避免破坏性命令。

## 依赖和冲突

```text
该任务可以和大多数业务模块并行，但如果修改 scripts/collab/，需要提醒其他任务同步脚本变化。
```

## 下一步

- 使用 `scripts/collab/start-work.sh --task validation-docs-report --module docs --machine <机器名> --kind light` 创建 worktree 和工作锁。

