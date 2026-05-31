# 任务记忆

## 基本信息

- 任务名：backend-frontend-runtime-config-slim
- 模块锁：backend_api
- 分支：codex/mac-backend-frontend-runtime-config-slim-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/backend-frontend-runtime-config-slim
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-31 20:14:57
- 预计结束：

## 目标

```text
减少首页 HTML 中 configData 的一次性注入体积：
后端渲染模板仍使用完整 CONFIG，但前端 app-runtime 只接收需要的 frontend_runtime_config。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
api/power.py
templates/index.html
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 补充获取 templates_index_html 高风险锁
- 新增 build_frontend_runtime_config，只复制首页/各视图运行时直接消费的配置字段
- index 路由新增 frontend_runtime_config 模板变量
- templates/index.html 的 configData 注入改为 frontend_runtime_config

## 已验证

- python3 -m compileall api/power.py
- node --check static/js/app-runtime.js
- git diff --check
- 纯 JSON 估算：configData 注入从约 123570 bytes 降到约 89222 bytes，减少约 34348 bytes

## 未验证

- 模板渲染/生产首页体积对比
- 主要页面浏览器 smoke

## 风险点

- 

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 本地编译和渲染体积检查，通过后提交、部署、验证。
