# 任务记忆

## 基本信息

- 任务名：frontend-lazy-load-baseline
- 模块锁：template
- 分支：codex/mac-frontend-lazy-load-baseline-20260530
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-lazy-load-baseline
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-30 11:38:46
- 预计结束：

## 目标

```text
降低首页首屏加载压力，先做低风险前端懒加载基线：移除首屏不必要的重模块同步加载，保留现有控制接口和业务行为。
```

## 当前阶段

```text
本地验证完成，准备提交并释放 template 锁
```

## 修改范围

```text
templates/index.html
static/js/core/bootstrap.js
docs/ARCHITECTURE.md
docs/FRONTEND_SPLIT_PLAN.md
docs/PERFORMANCE_REFACTOR_PLAN.md
scripts/perf_baseline.py
.gitignore
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 增加 SmartCenter 懒加载注册表和视图模块映射。
- 首页改用 SNMP 摘要模块，完整 SNMP 详情、协议控制、代理、本地模型、Apple Audio 改为进入页面后加载。
- ECharts 改为图表可渲染时再加载，隐藏页面轮询不再提前拉取图表库。
- 移除不存在的 `static/js/views/nvr-view.js` 同步引用。
- 增加性能基线脚本和结构优化说明文档。

## 已验证

- `scripts/collab/check-sync.sh`：当前分支与 `origin/main` 无 ahead/behind，template 锁由 mac 当前任务持有。
- `.venv` 依赖导入：Flask、FastAPI、requests、OpenCV、pysnmp、lark-oapi 等通过。
- `node --check`：核心和懒加载相关前端模块通过。
- `git diff --check`：通过。
- `python3 -m py_compile scripts/perf_baseline.py`：通过。
- `python3 scripts/perf_baseline.py`：已生成本地忽略的 `.baseline_reports/perf-baseline-*.json`。
- 本地服务 `http://127.0.0.1:6901/?view=dashboard`：首页可渲染，首屏脚本不包含 `echarts.min.js`、完整 `snmp.js`、`universal.js`、`proxy.js`、`apple-audio.js`、`local-model.js`。

## 未验证

- 浏览器多视图自动化验证通道在多标签关闭后间歇断开，已用首页实测、静态检查和服务访问日志补充验证。
- 未切换生产服务，生产发布需另行执行。

## 风险点

- `templates/index.html` 仍然很大，懒加载兼容层保留了旧全局函数名，后续继续拆分时需要逐步删除内联 `onclick`。
- 本地验证启动 Flask 后产生了 `config.json`、`music_tag_library.json`、`runtime/auth_users.json` 运行态变化，本次不提交这些文件。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 合并生产前，在 120 上用生产环境再验证首页、SNMP、协议控制、本地模型、电表、代理、音乐播放器页面。
- 后续继续把 SNMP、服务器监控、强电/电表、自动化画布从 `templates/index.html` 拆到独立 view 模块。
