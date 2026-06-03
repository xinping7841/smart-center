# 任务记忆

## 基本信息

- 任务名：sidebar-carousel-mode-fix
- 模块锁：frontend_assets
- 分支：codex/mac-sidebar-carousel-mode-fix-20260603
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-sidebar-carousel
- 执行机器：mac
- 开始时间：2026-06-03

## 目标

```text
解除 display_mode=carousel 对 dashboard compact/fixed 适配的误触发，保留侧边栏轮播功能，修复轮播切页时侧边栏尺寸跳变。
```

## 修改范围

```text
static/js/app-runtime.js
static/js/core/viewport-layout.js
```

## 已完成

- 从 origin/main 创建修复分支
- 获取 frontend_assets 和 templates_index_html 锁
- 移除 carousel 对 dashboard compact/fixed 模式的触发
- 更新资源版本到 20260603-sidebar-carousel-v2

## 已验证

- python3 -m compileall app.py api services runtime modules core config.py background.py power.py snmp_core.py
- 静态断言：display_mode=carousel 保留轮播启用，不再触发 dashboard fixed/compact

## 风险点

- 仅调整 URL 参数语义，不改变控制按钮逻辑。
