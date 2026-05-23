# 给另一台机器的完整对接信息

把这份内容发给另一台机器，按步骤配置即可加入协作。

## 当前协作规则

- 每台机器最多 5 个并行任务。
- 每个任务使用独立 Git worktree。
- 每个任务使用独立分支。
- 每个任务创建 `.worktasks/<task>/TASK.md`。
- 修改前必须检查远端提交和工作锁。
- 高风险文件必须上锁。
- 完成后提交、推送、释放锁。

## 首次目录建设

如果是 Windows Git Bash，推荐：

```bash
mkdir -p /d/SmartCenter
cd /d/SmartCenter
git clone node-120-ts:/srv/git/smart-center.git smart-center-git
cd smart-center-git
bash scripts/collab/bootstrap-other-machine.sh --machine 12700k --worktree-base /d/SmartCenter/smart-center-worktrees
```

如果是 macOS/Linux，推荐：

```bash
mkdir -p ~/SmartCenter
cd ~/SmartCenter
git clone node-120-ts:/srv/git/smart-center.git smart-center-git
cd smart-center-git
bash scripts/collab/bootstrap-other-machine.sh --machine laptop --worktree-base ~/SmartCenter/smart-center-worktrees
```

## 已有代码时先执行

```bash
cd /path/to/smart-center
bash scripts/collab/setup-git-collab.sh
bash scripts/collab/check-sync.sh
```

## 创建任务

示例：12700K 开始服务器监控拆分：

```bash
bash scripts/collab/start-work.sh \
  --task server-monitor-refactor \
  --module server_monitor \
  --machine 12700k \
  --kind heavy
```

一台机器最多同时创建 5 个任务 worktree。默认只建议同时运行 1-2 个重任务，其余为轻量任务。

示例：另一台机器做轻量文档任务：

```bash
bash scripts/collab/start-work.sh \
  --task docs-comment-pass \
  --module docs \
  --machine laptop \
  --kind light
```

## 结束任务

在任务 worktree 目录里执行：

```bash
bash scripts/collab/finish-work.sh \
  --message "docs: update collaboration notes" \
  --release-lock docs
```

## 模块锁选择

常用锁：

```text
server_monitor
snmp_monitor
power
meter
hvac
automation
ups
nvr
projector
light
sequencer
templates_index
config_core
app_bootstrap
background_runtime
docs
```

如果要改 `templates/index.html`，必须额外锁 `templates_index`。

如果要改 `config.py`，必须额外锁 `config_core`。

如果要改 `background.py`，必须额外锁 `background_runtime`。

## 判断是否可以开始

可以开始：

```text
本地没有未提交改动
远端没有必须先合并的新提交
目标模块没有工作锁
任务数量少于 5
```

不能开始：

```text
本地有未提交改动
目标模块已有锁
要改的高风险文件没有锁
当前机器已有 5 个活动任务
```
