# 任务记忆

## 基本信息

- 任务名：venue-light-physical-switch
- 模块锁：frontend_assets
- 分支：codex/mac-venue-light-physical-switch-20260601
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/venue-light-physical-switch
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-01 17:27:49
- 预计结束：

## 目标

```text
优化场馆灯光通道开关 UI，让开关呈现接近实体跷板开关的视觉：开启绿色上压，关闭红色下压，同时压缩文字信息占用。
```

## 当前阶段

```text
本地实现和静态验证完成，准备提交/部署。
```

## 修改范围

```text
static/css/generated/core-theme.css
static/css/generated/core-theme.css.gz
static/css/generated/manifest.json
templates/index.html
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 获取 templates_index_html 伴随锁
- 将灯光通道按钮改为紧凑实体跷板开关视觉
- 隐藏 remark 文本，名称一行省略，状态压到底部胶囊
- 开启状态为绿色上压，关闭状态为红色下压
- 刷新 core-theme.css.gz、manifest core.bytes 和模板 CSS 版本号

## 已验证

- git diff --check
- python3 -m json.tool static/css/generated/manifest.json
- node --check static/js/views/light-scene-view.js
- node --check static/js/app-runtime.js
- 本地 HTTP 静态预览截图确认视觉
- Playwright 视口验证 390/760/1280/1920/3840 无横向溢出，大屏卡片仍限制 520px

## 未验证

- 未点击真实灯光控制按钮，避免触发现场设备

## 风险点

- 视觉样式仅作用于 #view-light #light-page-grid 下的 .ch-btn，避免影响强电等其他页面通道按钮

## 依赖和冲突

```text
已额外获取 templates_index_html 锁用于 templates/index.html 缓存版本号修改。
```

## 下一步

- 提交、合并 main、部署生产并核对公开域名 CSS 生效
