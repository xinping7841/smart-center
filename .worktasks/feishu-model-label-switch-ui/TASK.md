# 任务记忆

## 基本信息

- 任务名：feishu-model-label-switch-ui
- 模块锁：frontend_assets
- 分支：codex/mac-feishu-model-label-switch-ui-20260601
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/feishu-model-label-switch-ui
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-01 23:09:34
- 预计结束：

## 目标

```text
去除飞书/本地模型链路中的旧 Ollama 表述，统一到本地模型 / OpenAI 兼容 / vLLM；让 AI 模块里的飞书控制安全开关更明显。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
services/control_model_translator.py
services/feishu_bot.py
api/local_model.py
static/js/views/local-model.js
static/css/views/local-model.css
templates/local_model.html
static/js/app-runtime.js
templates/index.html
docs / .env.example / FEISHU_INTEGRATION.md
scripts/remote/migrate_local_model_openai_config_20260601.py
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 追加获取 backend_api 和 templates_index_html 锁
- 移除旧模型端点 /api/generate 调用，改为 OpenAI-compatible /v1/chat/completions
- 重命名飞书意图分类器为 LocalModelIntentClassifier
- AI 模块顶部新增醒目的飞书控制安全开关状态卡
- 更新缓存版本，避免浏览器继续读旧 local-model.js/css
- 新增生产配置迁移脚本，清理历史名称里的旧供应商标签

## 已验证

- python3 -m compileall api services scripts/remote/migrate_local_model_openai_config_20260601.py
- git diff --check
- rg 确认源码/文档不再出现旧供应商名称、旧 /api/generate 或 11434 文档默认值
- 本地 helpers 检查：OpenAI base_url 归一化、JSON 提取、迁移脚本名称清理

## 未验证

- 本地 Flask 页面未启动验证：当前系统 python 缺少 Flask；上线后用生产服务和浏览器验证

## 风险点

- 飞书启用本地模型分类时将走 OpenAI-compatible 服务；如生产环境仍只配置旧非 /v1 端点，需用迁移脚本或 .env 更新到 /v1。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交、合并 main、部署生产、执行配置迁移、验证 /local-model 页面和 /api/local-model/config 不再显示旧名称。
