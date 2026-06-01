# 任务记忆

## 基本信息

- 任务名：release-maintenance-audit
- 模块锁：collab_tools
- 分支：codex/mac-release-maintenance-audit-20260601
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/release-maintenance-audit
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-01 12:33:44
- 预计结束：

## 目标

```text
修复生产 release metadata 陈旧问题，避免 .codex_deploy_ts.txt 从历史基线被带入新 release；
增强生产 release 检查脚本，并记录/验证当前生产 release 的真实 revision 与时间戳。
```

## 当前阶段

```text
完成，等待最终提交/推送/释放锁
```

## 修改范围

```text
.codex_deploy_ts.txt
deploy/linux/remote_release.sh
scripts/remote/check_active_release.sh
scripts/remote/deploy_runtime_domain_split.sh
scripts/remote/stamp_active_release_metadata.sh
.worktasks/release-maintenance-audit/
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 删除仓库根部历史 .codex_deploy_ts.txt，避免后续 archive release 继续携带 20260404_145744。
- 发布脚本写入 REVISION、.codex_deploy_ts.txt 与 RELEASE_INFO.json。
- 增强 check_active_release.sh，显示 release_name、revision、deploy_ts_status 与 RELEASE_INFO.json。
- 新增 stamp_active_release_metadata.sh，用于只修当前生产 release 的 metadata，不切换 release、不重启服务。
- 已在 node-120 当前 release 执行 metadata 修复。

## 已验证

- bash -n deploy/linux/remote_release.sh scripts/remote/deploy_runtime_domain_split.sh scripts/remote/check_active_release.sh scripts/remote/stamp_active_release_metadata.sh scripts/ssh_exec.sh
- git diff --check
- python3 -m compileall -q app.py api services runtime config.py background.py power.py snmp_core.py（仅保留既有 api/server.py Windows 路径转义 SyntaxWarning）
- curl 验证 https://zhankongceshi.iepose.cn/、https://zhankongceshi.iepose.cn/?view=server、http://192.168.50.120:6899/ 均返回 200。
- 通过 scripts/ssh_exec.sh 上传执行 scripts/remote/stamp_active_release_metadata.sh 到 node-120。
- 通过 scripts/ssh_exec.sh 上传执行 scripts/remote/check_active_release.sh，确认 service_active=active、release_name=smart-center-release-20260601_121405-main-a9bf34e、revision=a9bf34eb9a6b6c890aca56adb334e0068521790d、deploy_ts=20260601_121405、deploy_ts_status=ok。

## 未验证

- 未执行新的完整生产 release 切换；本任务只修复当前 release metadata 并更新后续发布脚本。

## 风险点

- stamp_active_release_metadata.sh 只写当前 release 目录 metadata 文件，不修改 /srv/smart-center-data，不重启 smart-center.service。
- deploy_runtime_domain_split.sh 是生产发布脚本；后续使用时会在 release 内新增 metadata 文件。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交并推送任务分支。
- 快进 main 并推送。
- 释放 collab_tools 工作锁。
