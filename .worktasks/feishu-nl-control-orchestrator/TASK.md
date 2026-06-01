# 任务记忆

## 基本信息

- 任务名：feishu-nl-control-orchestrator
- 模块锁：backend_api
- 分支：codex/mac-feishu-nl-control-orchestrator-20260601
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/feishu-nl-control-orchestrator
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-06-01 22:11:40
- 预计结束：

## 目标

- 梳理并优化飞书自然语言到中控控制的架构：模型只负责理解/结构化，真实执行仍走既有权限、路由、风险和确认链路。
- 在中控 AI / 本地模型模块展示自然语言处理过程：原始输入、模型/规则理解、路由结果、策略、确认、执行结果。
- 增加“允许飞书执行中控命令”开关；关闭时飞书查询不受影响，控制请求只解析和提示，不执行。
- 保留已完成的生产代码备份和代码/运行知识库导出能力。
- 按用户授权，仅对中控室电柜第 8 路、一号厅前言墙灯、泥人 50.89 继电器、中控室空调做全流程控制验证。

## 当前阶段

进行中

## 修改范围

- `api/local_model.py`
- `services/feishu_bot.py`
- `services/natural_language_orchestrator.py`
- `static/js/views/local-model.js`
- `static/css/views/local-model.css`
- `templates/local_model.html`
- `scripts/test_feishu_control_dryrun.py`
- `.worktasks/feishu-nl-control-orchestrator/`

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 新增自然语言处理策略/过程日志服务。
- 本地模型 chat、control dry-run、confirm 写入过程日志。
- 飞书 bot 读取自然语言策略，控制开关关闭时拦截执行但保留查询。
- 飞书控制默认统一进入确认；模型/规则只输出结构化意图，不直接执行。
- AI 模块前端新增飞书控制开关和自然语言处理记录面板。
- 干跑脚本接入飞书确认策略，默认 `would_execute_without_confirmation=0`。
- 上一阶段已完成生产 current 代码备份和代码/运行知识库导出能力：
  `/srv/smart-center/backups/pre-feishu-nl-knowledge-20260601_213944-fbb70b6/current-code.tar.gz`。
- 用户授权真实控制验证完成：
  - 中控室电柜第 8 路：原始 on，测试 off 被接口返回 `控制失败，且状态回读未确认` 拒绝；读回仍 on，未发生状态变化，未继续重试。
  - 一号厅前言墙灯：off -> on -> off，读回确认恢复。
  - 泥人 50.89 继电器 DO1：off -> on -> off，读回确认恢复。
  - 中控室/机房空调 `hvac_ha_shenlan_ac_01`：cool/on/19/高 -> off -> cool/on/19/高，读回确认恢复。

## 已验证

- `scripts/collab/check-sync.sh`
- `python3 -m py_compile api/local_model.py services/feishu_bot.py services/natural_language_orchestrator.py services/control_intent_router.py scripts/test_feishu_control_dryrun.py`
- `python3 scripts/test_feishu_control_dryrun.py --fail-on-unsafe`
- `python3 scripts/test_feishu_control_dryrun.py --base-url http://192.168.50.120:6899 --fail-on-unsafe`
- `/tmp/smart-center-authorized-tests/live_authorized_control_test.py`（不提交）对用户授权目标做真实控制验证并恢复。
- 本地 UI 验证：`SMART_POWER_HTTP_PORT=6909 SMART_CENTER_RUNTIME_DIR=/tmp/smart-center-nl-ui-runtime2 ... app.py`，浏览 `/local-model`。
  - 飞书控制开关默认关闭。
  - 自然语言处理记录面板可展示 `local_model`、待确认状态、目标动作、类型/风险/置信度、API 路径、payload、理解/路由/权限步骤。
  - 只调用 `/api/local-model/control/dry-run` 生成记录，未通过页面确认执行。
- 最终干跑摘要：`count=39`、`recognized=36`、`needs_confirmation=26`、`would_execute_without_confirmation=0`、`feishu_control_enabled=false`、`feishu_control_require_confirmation=true`。

## 未验证

- 生产发布和上线后飞书真实群聊回归。

## 风险点

- 真实设备控制只限用户明确授权范围。
- 飞书控制默认关闭，部署后如需飞书执行必须由中控 AI 模块开启。
- 过程日志在 runtime JSONL 中保存，需继续避免记录密钥等敏感字段。

## 依赖和冲突

- 已获取 `backend_api` 与 `frontend_assets` 锁。
- 不修改 `config.json` 的运行时规范化噪音；该文件若被接口写出，需要在提交前排除。

## 下一步

- 跑编译、干跑、diff 检查。
- 执行授权设备全流程验证。
- 启动本地服务做 AI 模块 UI 检查。
- 提交、推送并释放 `backend_api`、`frontend_assets` 锁。
