# 任务记忆

## 基本信息

- 任务名：outdoor-light-node-red
- 模块锁：automation
- 分支：codex/mac-outdoor-light-node-red-20260524
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/outdoor-light-node-red
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-24 04:30:26
- 预计结束：

## 目标

```text
将户外/庭院灯自动化从旧 TCP 泛型设备切换到 121 Node-RED 庭院灯 RF 网关。
```

## 当前阶段

```text
已验证，准备提交
```

## 修改范围

```text
config.py
runtime/automation.py
.worktasks/outdoor-light-node-red/
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 自动化运行时新增 node_red / node-red / nodered 子系统动作执行支持
- 庭院灯自动生成场景固定指向 Node-RED 设备 courtyard_light
- 生产环境确认 121 Node-RED 监听 1882，旧 254:1882 拒绝连接
- 远端临时导入验证 scene_outdoor_light_on/off 会迁移到 node_red/courtyard_light

## 已验证

- python3 -m py_compile runtime/automation.py config.py api/automation.py api/node_red.py
- git diff --check
- 120 Python 3.12 临时环境导入生产配置，确认庭院灯场景动作切换为 node_red/courtyard_light
- 120 临时环境执行 Node-RED status 动作成功

## 未验证

- 生产 release 部署后的 /api/automation/test 开灯/关灯实测

## 风险点

- /api/automation/test 会真实执行庭院灯开关，生产验证时需要明确选择 on/off。
- Node-RED 庭院灯设备有 8 秒冷却保护，连续测试需要等待。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
本任务不修改 12700K 飞书相关文件。
```

## 下一步

- 提交推送、合并 main、部署生产并调用自动化测试接口验证。
