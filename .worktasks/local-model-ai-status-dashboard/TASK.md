# 任务记忆

## 基本信息

- 任务名：local-model-ai-status-dashboard
- 模块锁：frontend_assets
- 分支：codex/mac-local-model-ai-status-dashboard-20260602
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-active-worktrees/local-model-ai-status-dashboard
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-06-02 13:56:26
- 预计结束：

## 目标

```text
重设计 /local-model 页面：降低对话窗口占用，将页面重心调整为 AI 配置状态、模型解析状态、学习沉淀与本地切换准备；保留轻量对话测试但默认收起。
```

## 当前阶段

```text
待提交合并生产
```

## 修改范围

```text
static/js/views/local-model.js
static/css/views/local-model.css
static/js/app-runtime.js
templates/local_model.html
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- /local-model 首页改为配置状态、解析状态、学习沉淀三栏主工作区
- 指标区补齐本地模型、知识库、上下文、模型服务、云端增强、决策模式
- 对话测试改为默认折叠抽屉，避免占用首屏
- 学习沉淀区显示样本存储、知识包、摘要状态、本地切换准备
- cache bust 版本更新为 20260602-local-model-status-dashboard-v2

## 已验证

- node --check static/js/views/local-model.js
- node --check static/js/app-runtime.js
- git diff --check
- mock /local-model 599x846：无横向溢出，聊天抽屉默认收起，高度约 62px，模型解析状态进入首屏底部
- mock 数据填充：qwen3:14b、doubao-seed-2-0-pro-260215、12 条解析记录、飞书控制状态

## 未验证

- 生产部署后需验证 https://zhankongceshi.iepose.cn/local-model 静态资源版本和页面布局

## 风险点

- 页面保存配置按钮会修改模型/飞书控制配置；验收时不点击真实控制按钮
- 生产部署需要使用项目远程脚本，复杂命令不 inline ssh

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
已额外获取 templates_index_html 锁用于 local_model.html 资源版本更新。
```

## 下一步

- 提交分支、合并 main、部署生产、验证后释放 frontend_assets 和 templates_index_html 锁
