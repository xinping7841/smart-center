# 任务记忆

## 基本信息

- 任务名：door-state-feishu-followup
- 模块锁：door
- 分支：codex/mac-door-state-feishu-followup-20260530
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/door-state-feishu-followup
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-30 01:52:27
- 预计结束：

## 目标

```text
修复飞书/接口查询大门状态时只显示 unknown 或门磁信息的问题，让系统能明确说明视觉状态不可判定的原因，并沉淀只读诊断脚本。
```

## 当前阶段

```text
代码完成，等待提交合并与生产发布
```

## 修改范围

```text
api/door.py
services/feishu_bot.py
scripts/diagnose_door_status.py
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 在 /api/door/vision_status 与 /get_door_status 增加 diagnosis 结构化诊断字段
- 飞书“大门状态”查询优先读取视觉状态，并保留门磁信息作为补充
- 增加只读诊断脚本 scripts/diagnose_door_status.py

## 已验证

- python3 -m py_compile api/door.py services/feishu_bot.py scripts/diagnose_door_status.py
- 本地抽取诊断函数验证 reference_mismatch 识别逻辑
- 120 上用临时脚本验证 reference_mismatch 识别逻辑
- 120 现网 /api/door/vision_status 显示参考图存在、视觉服务正常，但当前画面与开/关参考图差异均远高于阈值

## 未验证

- 尚未重新采集大门参考图；真实状态恢复为 open/closed 需要现场确认姿态后重采参考图或调整检测区域。

## 风险点

- 本次不触发真实开门/关门控制，只改查询解释和诊断。
- 生产页面如果依赖旧 msg 文案，会看到更准确的 reference_mismatch 提示。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交分支，合并到 main，发布到 120 后用 127.0.0.1 验证接口字段和飞书服务。
