# 任务记忆

## 基本信息

- 任务名：frontend-universal-template-slim
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-universal-template-slim-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-universal-template-slim
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-31 20:48:53
- 预计结束：

## 目标

```text
继续优化生产首页加载性能，将协议控制页的服务端 Jinja 循环预展开改为轻量占位 + universal.js 按需渲染。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
templates/index.html
static/js/app-runtime.js
static/js/views/universal.js
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 获取额外锁 templates_index_html
- 将 view-universal 中协议控件卡片、历史协议按钮从 Jinja 预展开迁移为 universal.js 动态渲染
- 更新 app-runtime 缓存版本号，避免生产浏览器继续使用旧 universal.js

## 已验证

- node --check static/js/views/universal.js static/js/app-runtime.js
- git diff --check
- python3 -m compileall -q app.py api runtime services static
- Jinja 轻量渲染：view-universal 区域约 2142 chars，循环为 0
- Node VM 模拟配置 show_on_home=true：可生成协议卡片、信息按钮、点动按钮和输出开关

## 未验证

- 发布后需通过 https://zhankongceshi.iepose.cn/?view=universal 浏览器实测

## 风险点

- 协议控制是真实设备控制入口；本任务只迁移 DOM 生成，不改变控制 API payload

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交分支、合并 main、发布生产并浏览器验证协议控制页
