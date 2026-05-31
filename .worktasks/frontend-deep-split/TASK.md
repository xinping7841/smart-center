# 任务记忆

## 基本信息

- 任务名：frontend-deep-split
- 模块锁：frontend-performance
- 分支：codex/mac-frontend-deep-split-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-deep-split
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-05-31 08:05:29
- 预计结束：

## 目标

```text
继续首页首屏深度拆分：在不改变设备控制和现有页面行为的前提下，
把 templates/index.html 与首屏 CSS 中可安全外置/按需加载的部分继续拆出去，
并完成生产备份、合并、部署、复测闭环。
```

## 当前阶段

```text
本地验证通过，待提交合并生产发布。
```

## 修改范围

```text
templates/index.html
static/css/views/*
static/js/views/*
必要时新增轻量首屏资源
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 备份 120 生产代码到 /srv/smart-center/backups/pre-frontend-deep-split-20260531_080646
- 将 335KB 内联运行时迁移到 static/js/app-runtime.js
- 将 4 个模板内联 hotfix 样式迁移到 static/css/views/hotfix-overrides.css
- templates/index.html 从约 488KB 降到约 133KB，内联 style 清零
- 本地 6909 验证 dashboard/server/snmp/auto/hvac/projector HTTP 200
- 浏览器真实点击验证 server/hvac/projector/snmp/auto 导航正常

## 已验证

- git diff --check
- node --check static/js/app-runtime.js
- python3 -m compileall app.py api services runtime config.py background.py power.py snmp_core.py
- /usr/bin/curl 本地 6909 页面与新增静态资源均 200

## 未验证

- 生产发布后还需再次验证 HTTPS 和 120 本机响应。

## 风险点

- templates/index.html 仍是高风险文件，必须保持内联 onclick 兼容。
- 不能改变真实控制 payload 和权限链路。
- 拆 CSS 时需要避免破坏当前 1080P 布局。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交分支，释放锁，合并 main，部署 120，生产复测。
