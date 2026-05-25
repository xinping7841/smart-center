# 任务记忆

## 基本信息

- 任务名：outdoor-light-rules-20260526
- 模块锁：automation
- 分支：codex/mac-outdoor-light-rules-20260526-20260526
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/outdoor-light-rules-20260526
- 执行机器：mac
- 任务类型：fix
- 开始时间：2026-05-26 02:22:23
- 预计结束：

## 目标

```text
优化庭院灯自动化：低照度开灯阈值调整为 200 lux，晚间自动关灯改为 21:00，并避免庭院灯已开时重复下发 on。
```

## 当前阶段

```text
完成，已发布生产并验证。
```

## 修改范围

```text
config.py
runtime/automation.py
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 新增庭院灯已开跳过重复 on 的 Node-RED 自动化保护
- 将户外灯低照度开灯阈值改为 200 lux，重置阈值改为 260 lux
- 将户外灯晚间自动关灯时间从 20:00 改为 21:00，执行窗口 21:00-21:30
- 已发布到 node-120 生产 release：/srv/smart-center/releases/smart-center-release-20260526_023025-outdoor-rules-20260526
- 发布前备份：/srv/smart-center/backups/pre-outdoor-rules-20260526_023025

## 已验证

- python3 -m py_compile config.py runtime/automation.py
- node-120 smart-center.service active
- 生产 config.json 中 auto_outdoor_light_low_lux_on value=200 rearm_value=260
- 生产 config.json 中 auto_outdoor_light_20_off schedule time=21:00 time_start=21:00 time_end=21:30
- /api/node-red/device/courtyard_light/status 返回 online=true，当前暗/off

## 未验证

- 未在真实夜间触发窗口等待 21:00 自动关灯，需今晚现场观察一次。

## 风险点

- 本次发布采用复制当前生产 release 后替换目标文件方式，避免覆盖 query-knowledge-server 生产改动。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 可在今晚 21:00 后查看 event_logs/operation_logs 是否记录晚九点关灯。
