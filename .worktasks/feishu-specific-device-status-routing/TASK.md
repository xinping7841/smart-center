# 任务记忆

## 基本信息

- 任务名：feishu-specific-device-status-routing
- 模块锁：feishu_bot
- 分支：codex/mac-feishu-specific-device-status-routing-20260604
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-task-worktrees/feishu-specific-device-status-routing
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-04 01:57:10
- 预计结束：

## 目标

```text
解决飞书机器人里“庭院灯状态”回复字段混乱的问题，并把具体设备状态查询优化从灯光扩展到空调、UPS、SNMP、投影机、幕布、时序电源、强电柜、自动化规则、代理、环境等设备类别。
同时补齐设备语义索引，让后续导出的知识包能给 123 本地模型学习设备名、别名、查询路由和控制边界。
```

## 当前阶段

```text
待合并发布
```

## 修改范围

```text
services/feishu_bot.py
services/device_aliases.py
tests/test_feishu_bot_light_queries.py
.worktasks/feishu-specific-device-status-routing/
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 庭院灯/户外灯状态回复改为中文分行字段：在线、开关、更新、网关健康。
- UTC `Z` 更新时间统一转换为本地时间文本，避免飞书回复里出现难读 ISO 字符串。
- 具体设备状态查询扩展到 HVAC、UPS、SNMP、投影机、幕布、时序电源、强电柜、自动化规则、代理、环境传感器。
- 查询路由优先级调整：自动化规则优先于户外灯；投影/幕布/时序电源优先于强电柜；强电柜查询必须包含明确电源/通道语义。
- 设备别名索引补充 automation/automation_rules 配置入口，便于长期知识包学习静态自动化规则。
- 新增测试覆盖庭院灯可读回复、非灯具具体设备过滤、投影/幕布/时序/强电柜路由、环境状态本地时间、自动化规则别名索引。

## 已验证

- `python3 -m py_compile services/feishu_bot.py services/device_aliases.py tests/test_feishu_bot_light_queries.py`
- `git diff --check`
- 使用 main repo `.venv` 和临时 config 直跑 `tests/test_feishu_bot_light_queries.py` 内全部测试，已通过。
- 本地配置别名索引统计：95 条，覆盖 node_red/light/power/hvac/projector/screen/sequencer/ups/snmp/env/current_collector/door/meter/proxy/custom 等模块。

## 未验证

- 尚未合并 main。
- 尚未发布生产。
- 尚未在生产只读调用飞书查询路径验证真实回复。
- 尚未刷新 123 本地模型知识包。

## 风险点

- 飞书机器人可触发真实控制；本任务只改状态查询与别名索引，生产验证必须只走只读状态查询，不调用控制 API。
- 强电柜和时序电源属于高风险设备，查询路由必须保持保守，不因“1号厅投影状态”等误入强电柜。
- 当前本地 config.json 没有静态自动化规则；生产知识包需结合运行时 `/api/automation/status` 导出，让 123 学到当前规则。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交并释放 feishu_bot 锁。
- 合并 main、发布生产。
- 生产只读验证典型查询。
- 导出/刷新 local_model 训练知识、代码知识和 system_summary，并应用到 node-123 context。
