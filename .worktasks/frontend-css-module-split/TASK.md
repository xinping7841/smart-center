# 任务记忆

## 基本信息

- 任务名：frontend-css-module-split
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-css-module-split-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-css-module-split
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-31 09:47:54
- 预计结束：

## 目标

```text
继续前端性能优化：把全站大主题 CSS 拆成公共主题 + 视图级 CSS 模块。
首屏只加载 critical.css、core-theme.css、dashboard-inline.css、hotfix-overrides.css；
dashboard/auto/server/snmp/hvac 等视图切换时再按需加载对应 generated/*.css。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
templates/index.html
static/js/app-runtime.js
static/css/generated/*.css
static/css/generated/*.css.gz
static/css/generated/manifest.json
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 额外获取 templates_index_html 高风险锁
- 生成视图级 CSS 模块与 gzip 预压缩文件
- 将 app-runtime 的懒加载样式入口从整包 smart-center-time-ntp.css 改为 viewStyleGroups
- 首页模板默认不再加载 smart-center-time-ntp.css
- 将 server/hvac/projector 的脚本模块与详情页样式模块分离，首页摘要预热不再提前加载详情页 CSS
- app-runtime.js 模板版本号已同步到 20260531-css-module-split，避免生产浏览器缓存旧运行时

## 已验证

- git diff --check 通过
- node --check static/js/app-runtime.js 通过
- static/css/generated/manifest.json JSON 格式通过
- CSS gzip 体积抽样：core-theme.css.gz 14283B、dashboard.css.gz 30943B、auto.css.gz 4704B
- python3 -m compileall app.py api services runtime config.py background.py power.py snmp_core.py 通过
- 本地 HTTP 验证：HTML 包含 critical.css/core-theme.css/app-runtime 新版本，不包含 smart-center-time-ntp.css，不默认包含 generated/dashboard.css
- 本地浏览器验证 13 个视图通过：dashboard/auto/server/snmp/hvac/projector/meter/ups/sequencer/universal/local_model/logs/env
- 本地浏览器验证：dashboard 只加载 core-theme.css + dashboard.css；auto/server/hvac/projector 等直达页各自加载对应 generated/*.css；当前域名 JS error 为 0

## 未验证

- 生产部署后外部域名验证

## 风险点

- CSS 选择器自动拆分可能遗漏跨页面共享样式，需要通过 dashboard/auto/server/snmp/hvac 等视图实测确认。
- templates/index.html 是高风险入口，必须保持可回滚生产备份。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
本任务已经持有 frontend_assets 与 templates_index_html 锁。
```

## 下一步

- 用临时配置启动本地服务，验证首屏和各视图的 CSS 加载情况。
- 验证通过后提交、推送、合并 main，并部署到 120 生产。
