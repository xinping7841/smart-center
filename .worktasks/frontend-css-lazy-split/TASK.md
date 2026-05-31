# 任务记忆

## 基本信息

- 任务名：frontend-css-lazy-split
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-css-lazy-split-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-css-lazy-split
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-31 08:39:19
- 预计结束：

## 目标

```text
继续优化首页加载性能：把 707KB 完整主题 CSS 从首屏阻塞链路移出，新增小型 critical CSS，同步保持各页面完整样式可恢复。
```

## 当前阶段

```text
本地验证完成，准备提交、合并和生产验证。
```

## 修改范围

```text
templates/index.html
static/js/app-runtime.js
static/css/core/critical.css
static/css/core/critical.css.gz
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 新增 critical CSS，覆盖首屏骨架、顶部、侧栏、通用卡片和总览统计基础布局
- 将完整 smart-center-time-ntp.css 改为 media=print/onload 的非阻塞样式加载
- 在懒加载模块注册中加入完整主题 CSS，确保进入重型视图时补齐样式
- 清理本地运行导致的 config.json 迁移噪声，未纳入提交

## 已验证

- git diff --check
- node --check static/js/app-runtime.js
- python3 -m compileall app.py api services runtime config.py background.py power.py snmp_core.py
- 本地 6909 HTTP: dashboard/auto/critical.css/full theme css/app-runtime.js 均返回 200
- 本地浏览器: dashboard/auto/server/snmp/hvac/projector/local_model 均可渲染，完整主题 CSS 已切到 media=all

## 未验证

- 尚未生产部署；提交合并后继续验证 120 和外网节点小宝链接

## 风险点

- critical CSS 只覆盖首屏骨架，完整细节样式依赖异步 CSS 完成加载；若极慢网络下短暂看到简化样式，属于预期折中。

## 依赖和冲突

```text
已获取 frontend_assets 锁，并补充 templates_index_html 高风险锁。
```

## 下一步

- finish-work 提交并释放 frontend_assets 锁
- 手动释放 templates_index_html 锁
- 合并 main，部署 120，外网验证
