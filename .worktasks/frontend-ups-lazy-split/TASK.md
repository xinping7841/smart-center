# 任务记忆

## 基本信息

- 任务名：frontend-ups-lazy-split
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-ups-lazy-split-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-ups-lazy-split
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-31 18:22:00
- 预计结束：

## 目标

```text
继续前端首屏瘦身：将 UPS 视图脚本从模板首屏强制加载改为 SmartCenter 懒加载模块，保持 /api/ups/status 与控制接口不变。
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
- 获取 templates_index_html 额外锁
- 注册 ups-runtime 懒加载模块
- 移除模板首屏 ups.js 脚本
- UPS 轮询改为进入 UPS 页或首页 UPS 区接近视口时加载

## 已验证

- 

## 未验证

- 

## 风险点

- UPS 控制涉及供电安全，本任务只改前端加载方式，不触发 UPS 控制指令。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 
