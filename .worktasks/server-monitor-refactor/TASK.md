# 任务记忆

## 基本信息

- 任务名：server-monitor-refactor
- 模块锁：server_monitor
- 分支：待创建
- Worktree 路径：../smart-center-worktrees/server-monitor-refactor
- 执行机器：待填写
- 任务类型：heavy
- 开始时间：未开始
- 预计结束：待填写

## 目标

```text
拆分服务器监控模块，先保持旧接口兼容，再逐步为独立服务化做准备。
```

## 当前阶段

```text
planned
```

## 修改范围

```text
api/server.py
modules/server_monitor/
agent/
相关服务器监控前端函数
```

## 已完成

- 创建任务记忆。

## 已验证

- 尚未开始验证。

## 未验证

- `/api/machines`
- `/report`
- `/agent/config`
- `/deploy_agent.bat`
- WOL/关机/重启接口仅检查存在，不在无人流程触发。

## 风险点

- 当前 `api/server.py` 很大，包含 Agent、GPU、加密锁、命令队列、WOL、扫描发现等逻辑。
- 该任务可能碰高风险文件 `api/server.py` 和 `templates/index.html`。
- 必须保持旧 Agent 和旧页面兼容。

## 依赖和冲突

```text
如果修改服务器监控前端，必须额外获取 templates_index 锁。
如果修改 app.py 蓝图注册，必须额外获取 app_bootstrap 锁。
```

## 下一步

- 使用 `scripts/collab/start-work.sh --task server-monitor-refactor --module server_monitor --machine <机器名> --kind heavy` 创建 worktree 和工作锁。

