# 每台机器 5 并行任务方案

本项目允许每台机器最多同时运行 5 个并行任务，但默认只建议 1-2 个重任务，其余为轻量任务。

## 并行上限

```text
每台机器最多 5 个 worktree
同一时间最多 2 个重任务
同一时间最多 1 个任务修改 templates/index.html
同一时间最多 1 个任务修改 config.py / app.py / background.py
```

## 推荐组合

```text
任务 1：server_monitor 拆分，重任务
任务 2：snmp_monitor 拆分，重任务
任务 3：文档和注释，轻任务
任务 4：配置中心小优化，轻任务
任务 5：验证报告和测试脚本，轻任务
```

## 不推荐组合

```text
任务 1：server_monitor 改 api/server.py
任务 2：首页加载拆 templates/index.html
任务 3：配置中心改 config.py
任务 4：自动化改 background.py
任务 5：SNMP 改 snmp_core.py
```

这种组合会同时碰多个高风险文件，冲突成本很高。

## 标准目录

默认 worktree 放在仓库同级目录：

```text
../smart-center-worktrees/
  server-monitor-refactor/
  snmp-monitor-refactor/
  hvac-small-fix/
  docs-comment-pass/
  validation-report/
```

每个 worktree 里都有自己的任务记忆：

```text
.worktasks/<task>/TASK.md
```

## 开始一个任务

```bash
bash scripts/collab/start-work.sh \
  --task server-monitor-refactor \
  --module server_monitor \
  --machine 12700k \
  --kind heavy
```

## 查看同步状态

```bash
bash scripts/collab/check-sync.sh
```

## 结束一个任务

```bash
bash scripts/collab/finish-work.sh \
  --message "refactor: split server monitor module" \
  --release-lock server_monitor
```

