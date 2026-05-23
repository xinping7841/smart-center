# 跨任务共享决策记录

多个并行任务之间需要共享的结论写在这里。不要只写在聊天里。

## 固定约定

- 每台机器最多 5 个并行任务。
- 每个任务一个 worktree、一个分支、一个 TASK.md。
- 高风险文件必须先获取工作锁。
- 服务器监控和 SNMP 可以优先模块化并逐步独立服务化。
- 120 主中控负责 UI、权限、配置、日志和聚合。
- 采集重任务后续优先迁到独立服务或 121。

## 决策记录

### 2026-05-22 多机器并行策略

采用 Git worktree + coordination/worklocks + .worktasks/TASK.md 的组合：

- Git worktree 解决同机多任务代码隔离。
- coordination/worklocks 解决跨机器模块占用提醒。
- .worktasks/TASK.md 解决单任务上下文记忆。
- shared-decisions.md 解决跨任务共识同步。

