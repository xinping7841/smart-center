# 任务记忆

## 基本信息

- 任务名：ui-device-semantic-knowledge-index
- 模块锁：local_model
- 分支：codex/mac-ui-device-semantic-knowledge-index-20260603
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-task-worktrees/ui-device-semantic-knowledge-index
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-03 23:54:21
- 预计结束：

## 目标

```text
新增全量 UI 文案/设备名/别名/查询控制路由语义索引，写入本地模型知识包并同步 123 学习。
```

## 当前阶段

```text
已完成实现和远程只读导出验证，待合并发布与 123 学习。
```

## 修改范围

```text
api/local_model.py
services/device_aliases.py
scripts/remote/apply_node123_device_code_context_20260603.py
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 新增 ui_device_semantics 知识层：统一页面文案、配置文案、设备名、别名、查询 API、控制 API 和风险边界
- 把 Node-RED 庭院灯纳入通用 device_aliases，不再只在单点代码里硬编码
- 更新 123 compact prompt apply 脚本，纳入 UI 文案与设备语义索引

## 已验证

- python3 -m py_compile api/local_model.py services/device_aliases.py scripts/remote/apply_node123_device_code_context_20260603.py 通过。
- git diff --check 通过。
- 120 临时分支导出验证通过：ui_device_semantics=3436。
- 覆盖模块：current_collector/custom/door/env/hvac/light/meter/node_red/power/projector/proxy/screen/sequencer/server/snmp/ups。
- 来源覆盖：config_ui_text=271、ui_literal=852、device_alias=2151、device_alias_name=107、device_inventory=55。
- 风险边界验证：power/sequencer/server/ups 为 high，hvac/projector/door 等为 medium。

## 未验证

- 本机缺 Flask，未在本机直接运行 export_local_model_training.py；已用 120 生产 venv 在 /tmp 只读导出验证替代。
- 尚未合并发布生产，123 学习需发布后执行生产导出。

## 风险点

- 该索引只生成知识包，不改变设备控制执行链路。
- 控制路由仅作为模型理解提示；真实执行仍由 120 后端权限、审计、锁、确认策略校验。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- finish-work 提交并释放 local_model 锁。
- 合并 main，发布生产，重新导出知识包并刷新 123 compact prompt。
