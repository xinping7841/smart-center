# 任务记忆

## 基本信息

- 任务名：frontend-wide-ui-1080-polish
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-wide-ui-1080-polish-20260602
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-wide-ui-1080-polish
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-06-02 14:41:30
- 预计结束：

## 目标

```text
备份生产代码后，彻底优化 Smart Center 首页与宽屏显示体验。
优先适配 16:9 的 1920x1080 与 3840x2160 监控屏，主页改为只读监控大屏数据展示，
正常模式不触发旧的固定画布/轮播专用逻辑，不影响真实设备控制链路。
```

## 当前阶段

```text
本地验证完成，准备提交并释放锁
```

## 修改范围

```text
api/dashboard.py
templates/index.html
static/js/app-runtime.js
static/js/core/viewport-layout.js
static/js/views/dashboard-shell.js
static/js/views/dashboard-summary.js
static/css/views/ui-wide-1080.css
scripts/remote/backup_current_production_code_20260602_ui_polish.sh
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 获取 companion lock：templates_index_html
- 生产 current 代码已备份到 /srv/smart-center/backups/pre-ui-wide-1080-polish-20260602_144238-b4e814c
- 首页改成监控大屏骨架：综合态势、KPI、状态矩阵、关键设备态势、AI/飞书、告警、SNMP、机器、日志流
- /api/dashboard/summary 增加只读快照：投影、幕布、自动化、本地/云端模型、门禁、日志
- 首页仅使用 /api/dashboard/summary 渲染，不加载旧主页控制模块，不显示真实设备控制按钮
- 普通 dashboard 不再默认进入固定画布/轮播布局；display_mode/fit_dashboard 专用参数才启用专用显示适配
- 清理主页轮询：强电、灯光、投影、幕布、空调、时序、UPS、门禁、SNMP 等详情轮询只在对应详情页运行
- 资源版本更新为 20260602-monitor-wall-v1
- 5 个旧 worktree 检查后已释放；当前只保留 main 与本任务 worktree

## 已验证

- scripts/collab/check-sync.sh：本分支与 origin/main 同步，active locks 为本任务 frontend_assets/templates_index_html
- node --check static/js/views/dashboard-shell.js
- node --check static/js/views/dashboard-summary.js
- node --check static/js/app-runtime.js
- node --check static/js/core/viewport-layout.js
- /Users/wanghongyu/Documents/New project/smart-center-clean/.venv/bin/python -m py_compile api/dashboard.py
- GET http://127.0.0.1:6910/api/dashboard/summary 返回 ok/counts/modules，包含 automation、door、env、light、local_model、logs、power、projector、proxy、screen、sequencer、server、snmp、ups
- Playwright 1920x1080：issueCount=0、rootX=0、bodyX=0、首页按钮=0
- Playwright 3840x2160：issueCount=0、rootX=0、bodyX=0、首页按钮=0
- 首页仅加载 dashboard-summary.js、dashboard-shell.js、page-shells.js 三个 view 脚本

## 未验证

- 尚未部署本次 UI 改造到生产 release
- 轮播专用模式仅预留 display_mode/fit_dashboard 入口，本轮未实现自动切换各功能页面

## 风险点

- config.json 与 music_tag_library.json 有运行时/无关改动，明确不纳入本次提交
- 首页显示飞书控制状态文字，但不提供执行按钮；真实控制仍需进入原功能页并按权限/确认链路执行

## 依赖和冲突

```text
已获取 frontend_assets 与 templates_index_html 锁；templates/index.html 属高风险文件，完成后需释放两个锁。
```

## 下一步

- 精确暂存本次文件，排除 config.json 与 music_tag_library.json
- 提交并 push
- 释放 frontend_assets 与 templates_index_html 锁
- 如需上线，再按 release 流程部署生产并验证 https://zhankongceshi.iepose.cn/?view=dashboard
