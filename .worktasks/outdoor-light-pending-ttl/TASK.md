# 任务记忆

## 基本信息

- 任务名：outdoor-light-pending-ttl
- 模块锁：light
- 分支：codex/local-codex-outdoor-light-pending-ttl-20260522
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/outdoor-light-pending-ttl
- 执行机器：local-codex
- 任务类型：light
- 开始时间：2026-05-22 18:35:41
- 预计结束：

## 目标

修复协议控制页新户外灯开关后弹出 `name 'PENDING_TTL_SEC' is not defined` 的错误，并给户外灯开关补上保护冷却时间，避免连续拨动反复下发。

## 当前阶段

已完成，待提交推送。

## 修改范围

event_logger.py
api/node_red.py
static/js/views/universal.js

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 修复事件日志 pending 命令清理常量名错误。
- 为 Node-RED 户外灯 `courtyard_light` 增加 8 秒后端开关冷却保护。
- 协议控制页增加执行中/保护冷却状态显示，并在冷却期间禁用开关。

## 已验证

- `python3 -m compileall event_logger.py api/node_red.py`
- `node --check static/js/views/universal.js`

## 未验证

- 未直接点击真实户外灯，避免在修复验证中触发现场设备控制。
- 本机 `python3` 是 3.9.6，直接 import 项目会被既有 `paths.py` 的 `Path | None` 运行时注解阻断；语法编译检查已通过。

## 风险点

- 后端冷却默认全局为 0 秒，仅对明确配置 `control_cooldown_sec` 的 `courtyard_light` 生效，避免误伤其它 Node-RED 设备。

## 依赖和冲突

未修改高风险文件；远端存在 `templates_index` 锁，本任务已避开。

## 下一步

- 提交、推送、释放 `light` 工作锁。
