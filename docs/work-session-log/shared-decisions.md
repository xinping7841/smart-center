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

### 2026-06-01 Mac worktree 清理审计

在 `main` 已同步到 `836f3b6` 且无 active worklocks 后，Mac 本地清理旧任务 checkout：

- 已移除 `frontend-dashboard-template-slim`、`frontend-snmp-runtime-slim`、`frontend-universal-runtime-split` 三个 worktree；它们的 HEAD 均已包含在 `main`。
- 移除前已把运行态配置漂移保存为 Git stash，stash message 分别以 `cleanup/frontend-dashboard-template-slim`、`cleanup/frontend-snmp-runtime-slim`、`cleanup/frontend-universal-runtime-split` 开头。
- 这些 stash 主要包含 `config.json` 的配置规范化写回和 `music_tag_library.json` 的 `last_scan_at` 刷新，不作为主线业务改动处理。
- `frontend-power-meter-runtime-split` 最初保留，因其 HEAD `6125fbe` 尚未直接包含在当时的 `main`。
- 后续审计确认 `6125fbe` 的前端拆分内容已由主线祖先 `a73404c` 覆盖；旧提交额外包含的 `runtime/auth_users.json` 是运行态账号文件，主线已通过 `.gitignore` 忽略。已移除该 worktree，仅保留本地分支记录。

### 2026-05-22 多机器并行策略

采用 Git worktree + coordination/worklocks + .worktasks/TASK.md 的组合：

- Git worktree 解决同机多任务代码隔离。
- coordination/worklocks 解决跨机器模块占用提醒。
- .worktasks/TASK.md 解决单任务上下文记忆。
- shared-decisions.md 解决跨任务共识同步。
