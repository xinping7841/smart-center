# Windows 12700K 全新 Git 接入流程

中心仓库：`ssh://xinping@192.168.50.120/srv/git/smart-center.git`

目标：12700K 不合并旧本地修改，旧目录只做压缩备份；之后从中心仓库全新克隆，所有新修改都走独立分支。

## 1. 前置条件

- 12700K 已安装 Git for Windows。
- 12700K 可以 SSH 到 `192.168.50.120` 或 Tailscale 下的 `node-120`。
- 已把 12700K 的 SSH 公钥加入 `node-120` 的 `xinping` 用户 `authorized_keys`。

## 2. 只备份旧代码，不导入

在 12700K 管理员 PowerShell 中执行，先把 `$OldProjectPath` 改成当前旧代码目录。如果旧目录不需要保留，可跳过这一步。

```powershell
$OldProjectPath = "D:\smart-center"
$BackupRoot = "D:\smart-center-backups"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
Compress-Archive -Path (Join-Path $OldProjectPath "*") -DestinationPath (Join-Path $BackupRoot "smart-center-old-before-fresh-git-$Stamp.zip") -Force
```

## 3. 全新克隆中心仓库

推荐新目录，不覆盖旧目录：

```powershell
$GitWork = "D:\smart-center-git"
git clone ssh://xinping@192.168.50.120/srv/git/smart-center.git $GitWork
cd $GitWork
git status
```

如果在异地，且 12700K 能通过 Tailscale 访问 `node-120`，可用：

```powershell
git clone ssh://xinping@node-120/srv/git/smart-center.git D:\smart-center-git
```

## 4. 新修改从分支开始

```powershell
cd D:\smart-center-git
git fetch origin
git switch -c codex/12700k-feature-name origin/main
# 修改、测试
git add .
git commit -m "说明这次修改"
git push -u origin HEAD
```

## 5. 注意

- 不要把旧目录 `robocopy` 到新 Git 目录。
- 不要直接在 `main` 上边试边改。
- `main` 只保留确认可部署的代码。
- 旧目录压缩包只作为回滚/查资料备份，不参与合并。
