# 任务记忆

## 基本信息

- 任务名：frontend-optimization-sweep
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-optimization-sweep-20260601
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-optimization-sweep
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-06-01 13:41:43
- 预计结束：

## 目标

```text
先以 main/生产当前版本为基线完成代码备份，然后推进前端优化 1-5：
1. 继续瘦身 app-runtime.js。
2. 将模板内联 CSS 外置，并做必要的首页 CSS 清理。
3. 将 SNMP/NVR 运行时继续拆分。
4. 清理强电运行时并保留旧全局函数兼容。
5. 拆分自动化页面/运行时。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
templates/index.html
static/css/views/hotfix-overrides.css
static/js/app-runtime.js
static/js/views/power-meter-runtime.js
static/js/views/snmp-runtime.js
static/js/views/nvr-preview-runtime.js
static/js/views/automation-runtime.js
.worktasks/frontend-optimization-sweep/*
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 生产 main 基线确认、代码归档备份、Git backup tag 已完成。
- 将强电控制状态、通道期望态、启停和单通道控制迁移到 power-meter-runtime.js，app-runtime.js 保留桥接函数。
- 将 templates/index.html 末尾 lazy-shell/hvac hotfix 内联 CSS 外置到 static/css/views/hotfix-overrides.css。
- 增加 nvr-preview-runtime.js，将监控预览墙/直播/快照刷新从 snmp-runtime.js 分离。
- 增加 automation-runtime.js，将自动化状态轮询、户外灯自动化首页卡、自动化页面上下文桥接从 app-runtime.js 分离。
- 更新懒加载版本号为 20260601-frontend-opt-sweep-v1。

## 已验证

- node --check static/js/app-runtime.js
- node --check static/js/views/power-meter-runtime.js
- node --check static/js/views/snmp-runtime.js
- node --check static/js/views/nvr-preview-runtime.js
- node --check static/js/views/automation-runtime.js

## 未验证

- 浏览器页面烟测和生产发布前验证待执行。
- finish-work.sh 全链路验证待执行。

## 风险点

- app-runtime.js 仍保留大量旧全局入口，拆分必须继续兼容模板内联 onclick。
- 自动化和环境/门禁/幕布摘要有交叉调用，当前通过 automation-runtime + 全局桥接兼容。
- SNMP 完整详情仍在 snmp.js，NVR 预览已拆到 nvr-preview-runtime.js，camera_preview 视图必须加载该模块。

## 依赖和冲突

```text
已额外获取 templates_index_html 锁用于 templates/index.html。
不处理泥人 AT 切换；灯光模块只做读页面/状态验证，不触发真实控制。
```

## 下一步

- 检查 gzip/静态产物是否需要同步。
- 运行 git diff --check、node --check、必要的本地/生产只读烟测。
- finish-work.sh 提交并释放 frontend_assets，随后释放 templates_index_html。
