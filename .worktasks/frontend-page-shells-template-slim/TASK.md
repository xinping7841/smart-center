# 任务记忆

## 基本信息

- 任务名：frontend-page-shells-template-slim
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-page-shells-template-slim-20260601
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-page-shells-template-slim
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-01 00:47:55
- 预计结束：

## 目标

```text
将非首页页面静态外壳从 templates/index.html 拆到 static/js/views/page-shells.js，
让模板只保留 view 根节点，保留原有容器 id 和业务 runtime。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
templates/index.html
static/js/app-runtime.js
static/js/views/page-shells.js
static/js/views/README.md
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 获取 templates_index_html 伴随锁
- 新增 page-shells.js，统一生成 power/light/ups/snmp/camera/sequencer/scene/server/projector/env/hvac 等页面外壳
- templates/index.html 中非首页页面缩减为 view 根节点
- app-runtime 增加页面壳启动和切换前兜底
- README 补充 page-shells 模块说明

## 已验证

- 待执行

## 未验证

- 本地浏览器验证待执行
- 生产部署验证待执行

## 风险点

- 页面切换前必须先生成对应容器，否则 runtime 找不到原有 id；已在模板直接加载 page-shells.js，并在 app-runtime 增加 ensurePageShellRendered 兜底。
- 本任务只移动静态外壳，不改变设备控制接口。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 执行静态检查、本地验证、合并、部署生产验证。
