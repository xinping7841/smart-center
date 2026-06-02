# 任务记忆

## 基本信息

- 任务名：frontend-monitor-wall-4k-polish
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-monitor-wall-4k-polish-20260602
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-monitor-wall-4k-polish
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-02 17:04:53
- 预计结束：

## 目标

```text
根据 3840x2160 实拍反馈优化首页监控大屏 UI，重点修正左侧侧边栏比例、4K 小字可读性、主页面信息层级和 16:9 单页显示稳定性。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
static/css/views/ui-wide-1080.css
static/js/app-runtime.js
static/js/views/dashboard-shell.js
static/js/views/dashboard-summary.js
templates/index.html
.worktasks/frontend-monitor-wall-4k-polish/TASK.md
.worktasks/frontend-monitor-wall-4k-polish/STATUS.json
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 优化 1920x1080 dashboard-wide 模式的侧边栏、标题和核心指标基础比例
- 优化 3840x2160 dashboard-wide 模式的侧边栏宽度、导航行高、图标尺寸、顶部状态条和主屏卡片层级
- 为 4K 首页设定大屏文字下限：正文/备注/日志/状态说明不低于约 15px，普通标题/状态行不低于约 18px
- 收敛 4K Live Feed 和顶部 chip 的行数与间距，避免字号放大后挤出单页
- 状态矩阵 4K 改为 7x2，并新增只读“日志流”状态块，填满第 14 格
- 轻微增强在线率、标题、告警和状态块视觉权重，让首页更接近监控大屏
- 将大屏侧边栏尺寸从首页专属样式提升为全局桌面框架样式，修复页面切换时侧栏忽大忽小
- 统一 1920x1080 / 3840x2160 下侧栏宽度、导航字号、图标尺寸、logo 和系统信息字号
- 抬高 1920 首页统计/备注小字下限，CSS 中不再保留 8px 字号
- 限制 4K 首页告警面板显示行数，避免字号放大后面板内部溢出
- 获取 `templates_index_html` 高风险锁并更新资源版本到 `20260602-monitor-wall-4k-sidebar-v2`

## 已验证

- `node --check static/js/views/dashboard-shell.js`
- `node --check static/js/views/dashboard-summary.js`
- `node --check static/js/app-runtime.js`
- `node --check static/js/core/viewport-layout.js`
- `git diff --check`
- Playwright 本地 `http://127.0.0.1:6911/?view=dashboard`：1920x1080 无横向溢出、首页按钮数 0
- Playwright 本地 `http://127.0.0.1:6911/?view=dashboard`：3840x2160 小字计数 0、内部溢出 0、横向溢出 0、首页按钮数 0、状态矩阵 14 格完整显示
- Playwright 本地页面切换 `dashboard -> power -> light -> server -> logs -> dashboard`：
  - 1920x1080 侧栏稳定为 224px，导航行高 36px，导航字号 13px，无横向溢出
  - 3840x2160 侧栏稳定为 286px，导航行高 58px，导航字号 18px，无横向溢出
- 资源版本检查：`templates/index.html` 与 `static/js/app-runtime.js` 均使用 `20260602-monitor-wall-4k-sidebar-v2`

## 未验证

- 尚未完成生产部署验收；当前准备提交并合并 main

## 风险点

- 本次只改展示 CSS，不改控制逻辑；首页仍不包含控制按钮
- 启动本地预览服务时运行时写脏了 config.json 和 music_tag_library.json；这两个文件不属于本次 UI 修改范围，后续提交时需要排除或按用户要求处理
- 当前持有 `frontend_assets` 与 `templates_index_html` 锁，生产发布验收后释放

## 依赖和冲突

```text
已获取 templates_index_html 锁；如需修改 config.py、background.py、app.py、api/server.py 或 snmp_core.py，需要额外获取对应锁。
```

## 下一步

- 提交、合并 main、备份生产、部署并释放 frontend_assets / templates_index_html 锁
