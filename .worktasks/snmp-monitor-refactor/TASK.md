# 任务记忆

## 基本信息

- 任务名：snmp-monitor-refactor
- 模块锁：snmp_monitor
- 分支：待创建
- Worktree 路径：../smart-center-worktrees/snmp-monitor-refactor
- 执行机器：待填写
- 任务类型：heavy
- 开始时间：未开始
- 预计结束：待填写

## 目标

```text
拆分 SNMP 监控模块，采集、快照、厂商解析、页面接口逐步解耦，降低页面加载阻塞。
```

## 当前阶段

```text
planned
```

## 修改范围

```text
api/snmp.py
snmp_core.py
modules/snmp_monitor/
相关 SNMP 前端函数
```

## 已完成

- 创建任务记忆。

## 已验证

- 尚未开始验证。

## 未验证

- SNMP 设备列表。
- H3C 端口/VLAN 信息。
- 威联通 NAS 容量和硬盘状态。
- 爱快、飞牛等设备显示。

## 风险点

- `snmp_core.py` 体积大，厂商解析和通用 SNMP 采集耦合较重。
- SNMP 采集慢时可能拖慢页面或后台。
- 必须保留现有显示字段，避免容量、端口、告警信息再次丢失。

## 依赖和冲突

```text
如果修改 SNMP 页面渲染，必须额外获取 templates_index 锁。
```

## 下一步

- 使用 `scripts/collab/start-work.sh --task snmp-monitor-refactor --module snmp_monitor --machine <机器名> --kind heavy` 创建 worktree 和工作锁。

