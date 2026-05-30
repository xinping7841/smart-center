# 任务记忆

## 基本信息

- 任务名：restore-server-monitor-12700k
- 模块锁：server_monitor
- 分支：codex/mac-restore-server-monitor-12700k-20260530
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/restore-server-monitor-12700k
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-05-30 17:50:32
- 预计结束：

## 目标

```text
核对并恢复 12700K 昨天提交后未进入当前生产主线的服务器监控改动，
重点修复 Agent 轻量心跳 404、服务器列表大渲染卡顿、离线卡片提示回退、
以及服务器设备信息导出/工具栏入口丢失。
```

## 当前阶段

```text
本地验证完成，准备提交
```

## 修改范围

```text
api/server.py
agent/linux_agent.py
static/js/views/server-monitor.js
templates/index.html
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 补获取 `template` 锁，因为实际触碰 `templates/index.html`
- 将 Agent 发布版本提升到 `2026.05.30.01`
- 恢复 `/agent/heartbeat` 路由，避免 121/122 等节点心跳继续 404
- 恢复 Windows Agent `heartbeat_path` 配置、发送时间字段和独立心跳上报
- 恢复 Linux Agent `client_sent_at` 和 `/agent/heartbeat` 轻量心跳
- 恢复服务器监控页延迟渲染和并发请求合并，减少进入服务器页时大列表同步阻塞
- 移除离线服务器卡片多余的命令不可用说明，只保留唤醒入口
- 恢复服务器页工具栏和设备信息 CSV 导出入口

## 已验证

- `python3 -m py_compile api/server.py agent/linux_agent.py app.py`
- `node --check static/js/views/server-monitor.js`
- `git diff --check`
- 使用主仓库 `.venv` 启动本地临时服务 `http://127.0.0.1:6910`
- `GET /?view=server` 返回 200，页面包含 `server-toolbar`、`exportServerDeviceInfoCsv`、`renderServerGridDeferred`
- `GET /agent/config?probe=1` 返回 `version=2026.05.30.01` 和 `heartbeat_path=/agent/heartbeat`
- `POST /agent/heartbeat` 不再 404；测试机 payload 正常进入 `202 ignored/test_machine_report` 安全分支
- `GET /static/js/views/server-monitor.js?v=20260530-restore-server-monitor` 返回 200

## 未验证

- 尚未发布生产后的现场节点自动更新效果；需生产部署后观察 121/122 心跳 404 是否停止

## 风险点

- `api/server.py` 内嵌 Windows Agent 脚本变化，必须提升 `AGENT_VERSION` 才能触发节点自动更新
- `templates/index.html` 属于高风险文件，本任务已补拿 `template` 锁
- 本地验证使用 `/tmp` 数据目录，没有碰生产 `/srv/smart-center-data`

## 依赖和冲突

```text
已同时持有 server_monitor 和 template 锁。只补服务器监控相关代码，不合并旧分支中的其它业务配置/自然语言/协议控制差异。
```

## 下一步

- 提交并释放 `server_monitor`、`template` 两个锁
- 合并到 `main` 后创建新生产 release 并重启 `smart-center.service`
