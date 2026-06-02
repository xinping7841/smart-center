# 任务记忆

## 基本信息

- 任务名：frontend-sidebar-carousel
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-sidebar-carousel-20260603
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-sidebar-carousel
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-03 01:39:56
- 预计结束：

## 目标

```text
增加网页轮播模式，用于 4K 电视展示时按侧边栏页面自动切换。
默认间隔 10 秒，支持 URL 参数和配置项调整间隔。
本任务只做轮播功能，不改 4K 页面布局，不执行真实设备控制。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
static/js/app-runtime.js
templates/index.html
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 获取 templates_index_html 附加锁用于资源版本刷新
- 增加 sidebar carousel runtime
- 增加 URL/config 间隔配置读取

## 已验证

- node --check static/js/app-runtime.js
- git diff --check
- python3 -m compileall app.py api services runtime config.py background.py power.py snmp_core.py
- 静态检查确认轮播只调用 switchTab，不调用 click，不触发真实设备控制按钮

## 未验证

- 本机缺少 Flask，未启动本地 app 预览；发布后用生产 URL 验证轮播切页

## 风险点

- URL 参数启用轮播后会自动切换页面；正常 URL 默认不轮播
- 轮播只包含侧边栏里使用 switchTab 的页面，不包含 /config、/m32r、/current-collector 等跳转型入口

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交、合并 main、发布生产并验证 ?carousel=1&carousel_interval=2 自动切页
