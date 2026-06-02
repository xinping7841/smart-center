# 任务记忆

## 基本信息

- 任务名：ark-cloud-model-config
- 模块锁：local_model、backend_api、frontend_assets、templates_index_html
- 分支：main
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-clean
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-06-02

## 目标

```text
把火山 Ark 云端增强模型接入 Smart Center 本地模型/飞书自然语言链路，用于复杂理解、系统摘要和低置信度控制转译兜底；密钥只进入生产运行配置，不进入仓库。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
api/local_model.py
services/control_model_translator.py
services/feishu_bot.py
scripts/refresh_local_model_system_summary.py
static/js/views/local-model.js
static/css/views/local-model.css
templates/local_model.html
static/js/app-runtime.js
docs
scripts/remote
```

## 已完成

- 运行 scripts/collab/check-sync.sh
- 在当前干净 main 上获取 local_model、backend_api、frontend_assets、templates_index_html worklock
- 使用临时环境变量探测 Ark /models，确认 API key 可访问模型列表

## 已验证

-

## 未验证

- 未部署生产
- 未执行真实设备控制

## 风险点

- Ark API key 不能提交到仓库或输出到文档
- 云端模型只能产生理解/转译/摘要，不能直接执行中控控制
- 飞书控制开关关闭时必须继续允许查询，但拦截控制执行

## 下一步

- 实现 cloud_model 配置、页面显示、生产迁移和验证
