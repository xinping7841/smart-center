# 任务记忆

## 基本信息

- 任务名：frontend-monitor-wall-prod-fit
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-monitor-wall-prod-fit-20260602
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-monitor-wall-prod-fit
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-02 16:37:09
- 预计结束：

## 目标

```text
修复生产真实数据下 3840x2160 首页监控大屏的机器状态列表溢出。
保持主页只读监控展示，不影响设备控制链路。
```

## 当前阶段

```text
验证完成，准备提交并发布
```

## 修改范围

```text
static/css/views/ui-wide-1080.css
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 发现生产 3840x2160 下 server_compact 真实机器数据超过面板高度
- 调整 4K media 规则：告警/SNMP 可恢复更多条目，机器状态仍保持最多 3 条可见，防止溢出

## 已验证

- node --check static/js/views/dashboard-summary.js
- node --check static/js/views/dashboard-shell.js
- node --check static/js/app-runtime.js
- node --check static/js/core/viewport-layout.js
- /Users/wanghongyu/Documents/New project/smart-center-clean/.venv/bin/python -m py_compile api/dashboard.py
- Playwright 注入 hotfix 检查生产真实数据 1920x1080：issueCount=0、rootX=0、bodyX=0、buttons=0
- Playwright 注入 hotfix 检查生产真实数据 3840x2160：issueCount=0、rootX=0、bodyX=0、buttons=0

## 未验证

- 尚未发布 hotfix 到生产 release

## 风险点

- CSS-only 修复；不改接口、不改控制链路

## 依赖和冲突

```text
仅需 frontend_assets 锁；不修改 templates/index.html。
```

## 下一步

- 验证后提交、推送、合并 main、发布生产并释放 frontend_assets 锁
