# 任务记忆

## 基本信息

- 任务名：local-model-page-redesign
- 模块锁：frontend_assets
- 分支：codex/mac-local-model-page-redesign-20260602
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-active-worktrees/local-model-page-redesign
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-06-02 13:28:09
- 预计结束：

## 目标

```text
重新设计本地模型 /local-model 页面和主界面 local_model 视图，让自然语言控制台、飞书执行开关、云端/本地理解链路和处理记录在默认视图中更明显。
```

## 当前阶段

```text
本地验证完成，准备提交合并生产。
```

## 修改范围

```text
templates/local_model.html
static/js/views/local-model.js
static/css/views/local-model.css
static/js/app-runtime.js
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 将独立 /local-model 模板改为复用 local-model.js 渲染，避免双份页面结构漂移。
- 将默认页面重排为运行概览、飞书执行权限、模型理解链路、对话测试、处理记录、知识库和维护参数。
- 将飞书控制执行开关提前到默认视图，并保留原有配置保存、健康检查、知识库、处理记录和训练导出 ID。
- 更新本地模型资源缓存版本为 20260602-local-model-redesign-v1。

## 已验证

- `node --check static/js/views/local-model.js`
- `node --check static/js/app-runtime.js`
- `git diff --check`
- 使用临时只读 mock 服务验证 `http://127.0.0.1:6919/local-model`，599x846 与 1440x920 视口均无横向溢出。
- 浏览器验证：飞书执行开关、云端开关、输入框、发送按钮均唯一；处理记录渲染正常；控制台无 error。

## 未验证

- 未点击真实设备控制按钮。
- 本轮本地页面验证使用 mock local-model API，生产部署后还需要走生产 URL 确认资源版本和页面加载。

## 风险点

- 本次重排触及独立页和主界面共用视图，需要生产缓存版本同步生效。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交分支并合并 main，部署生产后验证 `https://zhankongceshi.iepose.cn/local-model`。
