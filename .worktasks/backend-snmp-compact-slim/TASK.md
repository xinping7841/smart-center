# 任务记忆

## 基本信息

- 任务名：backend-snmp-compact-slim
- 模块锁：backend_api
- 分支：codex/mac-backend-snmp-compact-slim-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/backend-snmp-compact-slim
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-31 19:44:25
- 预计结束：

## 目标

```text
缩小 /api/snmp/status?compact=1 响应体：首页摘要只保留计数、吞吐、Top 忙碌/异常和少量样本，完整端口/VLAN/桥表明细仍保留在 full SNMP 详情接口。
```

## 当前阶段

```text
本地验证完成，准备提交合并生产
```

## 修改范围

```text
api/snmp.py
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 缩减 compact 模式下的 switch_port_rows、network_top_rows、interface_rows 等列表数量。
- compact 模式移除 configured_port_rows、configured_vlan_rows、vlan_traffic_rows、bridge_port_mac_rows 等详情明细行。
- 清理本地测试导入造成的 config.json 噪声，未纳入提交。

## 已验证

- python3 -m compileall api/snmp.py
- git diff --check
- 使用生产 /tmp/snmp-compact.json 样本模拟新 compact 输出：约 248849 bytes -> 122150 bytes，H3C 设备约 163KB -> 52KB。

## 未验证

- 待合并 main 后部署 node-120 生产，并验证 dashboard/SNMP 页面显示正常。

## 风险点

- 首页 SNMP 卡片仍需能展示关键状态；详情页 full 模式不受影响。
- compact 响应不再包含完整 VLAN/桥表明细，用户点击进入 SNMP 详情页时再读取 full 数据。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交、合并、部署生产，复测 /api/snmp/status?compact=1 包体和耗时。
