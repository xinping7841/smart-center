# 远程脚本执行规范

本项目多机维护时，不要把复杂逻辑直接写进 `ssh "..."`。复杂内联命令会被本地 shell、SSH、远端 shell、PowerShell、CMD、awk、JSON、here-doc 多层解析，极容易把引号拆坏。

## 强制规则

- 复杂远程操作必须先写成脚本文件，再上传执行。
- Linux 远端使用 `.sh` 或 `.py`，通过 `scripts/ssh_exec.sh` 或 `scripts/ssh_exec.ps1` 执行。
- Windows 远端使用 `.ps1`，通过 `scripts/ssh_exec_windows.sh` 或 `scripts/ssh_exec_windows.ps1` 执行。
- 只有无嵌套引号、无管道、无 JSON、无 awk、无 here-doc、无 PowerShell script block 的单条命令，才允许直接 `ssh host command`。

## Linux 远端示例

```bash
bash scripts/ssh_exec.sh \
  --host node-120-ts \
  --script scripts/remote/check_status.sh
```

验证 runner 是否正常：

```bash
bash scripts/ssh_exec.sh \
  --host node-120-ts \
  --remote-workdir /srv/git/smart-center-clean.git \
  --script scripts/remote/quote_smoke.sh

bash scripts/ssh_exec.sh \
  --host node-120-ts \
  --remote-workdir /srv/git/smart-center-clean.git \
  --script scripts/remote/quote_smoke.py
```

如果需要指定工作目录：

```bash
bash scripts/ssh_exec.sh \
  --host node-120-ts \
  --remote-workdir /srv/git/smart-center-clean.git \
  --script /tmp/audit_branch.sh
```

## Windows 远端示例

```bash
bash scripts/ssh_exec_windows.sh \
  --host 12700k-ts \
  --script scripts/remote/check_windows_smart_center.ps1
```

PowerShell 调用：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ssh_exec_windows.ps1 `
  -HostName 12700k-ts `
  -ScriptPath scripts/remote/check_windows_smart_center.ps1
```

验证 Windows runner 是否正常：

```bash
bash scripts/ssh_exec_windows.sh \
  --host 12700k-ts \
  --remote-workdir D:\SmartCenter\smart-center-clean \
  --script scripts/remote/quote_smoke_windows.ps1
```

## 不再使用的写法

```bash
ssh node-120-ts 'bash -lc "cat <<EOF ... EOF"'
ssh 12700k-ts 'powershell -Command "Get-CimInstance | Where-Object { ... }"'
```

上面这类命令禁止用于正式维护，因为一旦出现中文、JSON、管道、百分号、括号、花括号或嵌套引号，很容易被错误解析。

## 实现原则

runner 必须按下面的方式工作：

- 本地上传业务脚本为 payload 文件。
- 本地生成一个极小 wrapper 文件并上传。
- 远端只执行 wrapper，不把业务脚本内容拼进 `ssh "..."`。
- 业务脚本退出码必须透传，不能被清理动作覆盖。

## 推荐目录

- 临时 Linux 脚本可以放在 `/tmp/*.sh` 或 `/tmp/*.py`，执行后自动清理。
- 项目长期脚本放在 `scripts/remote/`。
- 重要审计脚本可以提交到 `scripts/remote/` 或写入对应任务 `.worktasks/<task>/TASK.md`。
