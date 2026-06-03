# 任务记忆

## 基本信息

- 任务名：feishu-courtyard-light-status-query
- 模块锁：backend_api
- 分支：codex/mac-feishu-courtyard-light-status-query-20260603
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-task-worktrees/feishu-courtyard-light-status-query
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-03 23:36:06
- 预计结束：

## 目标

```text
修复飞书查询“庭院灯状态”被误判为通用灯光控制器总览的问题，只读查询 Node-RED courtyard_light 单设备状态。
```

## 当前阶段

```text
已完成本地修复和只读生产诊断，待提交/发布。
```

## 修改范围

```text
services/feishu_bot.py
docs/LOCAL_MODEL_QUERY_INTENTS.jsonl
docs/QUERY_KNOWLEDGE_BASE.md
tests/test_feishu_bot_light_queries.py
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 定位根因：查询路径先命中“灯状态”通用规则，未先识别庭院灯 Node-RED 单设备
- 新增庭院灯/户外灯只读状态查询分支
- 补充本地模型查询种子和知识库 allowlist
- 新增 Feishu 灯光查询单元测试

## 已验证

- 生产日志：2026-06-03 23:25:56 收到“庭院灯状态”，23:25:57 本地模型分类为 lighting_status。
- 生产只读接口：/api/light/status 返回控制器 1/2 汇总，解释了错误回复来源。
- 生产只读接口：/api/node-red/device/courtyard_light/status 返回 庭院灯RF网关 online/off/暗。
- python3 直接执行 tests/test_feishu_bot_light_queries.py 两个测试函数通过。
- python3 -m py_compile services/feishu_bot.py tests/test_feishu_bot_light_queries.py 通过。
- bash -n scripts/remote/check_feishu_courtyard_light_query_20260603.sh 通过。
- git diff --check 通过。

## 未验证

- 本机全局 Python 未安装 pytest，未运行 python3 -m pytest；已用直接调用测试函数替代。
- 尚未发布生产，Feishu 实际回复需发布后再验证。

## 风险点

- 仅调用 GET /api/node-red/device/courtyard_light/status，不触发真实设备控制。
- 如生产 Node-RED 状态接口不可达，会返回明确不可用信息。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交分支并释放 backend_api worklock。
- 合并发布后，在飞书重问“庭院灯状态”验证返回单设备状态。
