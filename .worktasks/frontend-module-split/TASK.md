# 任务记忆

## 基本信息

- 任务名：frontend-module-split
- 模块锁：templates_index
- 分支：待创建
- Worktree 路径：../smart-center-worktrees/frontend-module-split
- 执行机器：待填写
- 任务类型：heavy
- 开始时间：未开始
- 预计结束：待填写

## 目标

```text
把大首页前端 JS/CSS 按侧边栏模块逐步拆分，最终支持按需加载，降低首页刷新慢和多人冲突。
```

## 当前阶段

```text
planned
```

## 修改范围

```text
templates/index.html
static/
modules/*/frontend 或后续前端资源目录
```

## 已完成

- 创建任务记忆。

## 已验证

- 尚未开始验证。

## 未验证

- 首页。
- 服务器监控页。
- SNMP 页。
- 自动化页。
- 16:9 预览。
- 移动端/桌面版布局策略。

## 风险点

- `templates/index.html` 是最高冲突文件。
- 前端拆分容易导致页面刷新空白或函数加载顺序问题。
- 必须先小步拆，不做大规模 UI 重设计。

## 依赖和冲突

```text
同一时间不允许其他任务修改 templates/index.html。
如果涉及服务器监控页面，需要同时协调 server_monitor 任务。
如果涉及 SNMP 页面，需要同时协调 snmp_monitor 任务。
```

## 下一步

- 使用 `scripts/collab/start-work.sh --task frontend-module-split --module templates_index --machine <机器名> --kind heavy` 创建 worktree 和工作锁。

