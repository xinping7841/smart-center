# 任务记忆

## 基本信息

- 任务名：local-model-system-map
- 模块锁：backend_api
- 分支：codex/mac-local-model-system-map-20260601
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-clean
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-06-01

## 目标

```text
把本地模型知识库从“导出运行/代码知识”扩展为系统地图和高上下文周期摘要机制，服务飞书自然语言查询与受控控制。
```

## 当前阶段

```text
已完成，待提交
```

## 修改范围

```text
scripts/export_code_knowledge.py
scripts/export_local_model_training.py
api/local_model.py
static/js/views/local-model.js
templates/local_model.html
docs
```

## 已完成

- 运行 scripts/collab/check-sync.sh
- 当前 checkout 创建任务分支
- 获取 backend_api、frontend_assets、templates_index_html worklock
- 增加 runtime system_map、device_inventory、control_capabilities 知识包
- 增加 code_system_map、module_cards、full_code_context 脱敏高上下文代码包
- 增加 3090 周期模型摘要脚本和 systemd ExecStartPost
- 增加本地模型页面知识库状态卡和摘要刷新入口

## 已验证

- `./.venv/bin/python -m py_compile api/local_model.py scripts/export_local_model_training.py scripts/export_code_knowledge.py scripts/refresh_local_model_system_summary.py`
- `node --check static/js/views/local-model.js`
- `git diff --check`
- 临时运行目录执行 `scripts/export_local_model_training.py --skip-full-code-context`
- 临时运行目录执行 `scripts/export_code_knowledge.py`，生成 903 个 full_code_context 分块
- 本地 6909 页面浏览器验证：知识库状态、安全开关、摘要按钮正常渲染，无前端错误
- `/api/local-model/knowledge-status` 返回 10 个知识项，带 full_code_context 和 recommended_context_len=131072

## 未验证

- 未调用真实设备控制
- 未调用真实本地模型上游生成 system_summary；本地 6909 的模型上游未运行

## 风险点

- 知识导出不能泄露敏感凭据
- 模型高上下文读取只能产出摘要/索引，不能绕过执行安全链路
- 生产部署后应先运行知识导出，再检查 full_code_context 和 system_summary 文件数量

## 依赖和冲突

```text
start-work.sh 因本机已有 5 个并行 worktree 无法创建新 worktree，本任务在当前干净 checkout 分支执行。
```

## 下一步

- 提交推送任务分支
- 释放 worklocks
