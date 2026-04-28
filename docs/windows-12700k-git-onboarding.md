# Windows 12700K Git 接入流程

中心仓库：`ssh://xinping@192.168.50.120/srv/git/smart-center.git`

> 目标：先备份 12700K 本地代码，再把本地改动提交到独立分支，避免覆盖 node-120 线上基线。

## 1. 前置条件

- 12700K 已安装 Git for Windows。
- 12700K 可以 SSH 到 `192.168.50.120`。
- 已把 12700K 的 SSH 公钥加入 `node-120` 的 `xinping` 用户 `authorized_keys`。

## 2. 首次备份本地代码

在 12700K 管理员 PowerShell 中执行，先把 `$ProjectPath` 改成 12700K 当前代码目录：

```powershell
$ProjectPath = "D:\smart-center"
$BackupRoot = "D:\smart-center-backups"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
Compress-Archive -Path (Join-Path $ProjectPath "*") -DestinationPath (Join-Path $BackupRoot "smart-center-before-git-$Stamp.zip") -Force
```

## 3. 克隆中心仓库

```powershell
$GitWork = "D:\smart-center-git"
git clone ssh://xinping@192.168.50.120/srv/git/smart-center.git $GitWork
cd $GitWork
git switch -c codex/12700k-local-$Stamp
```

## 4. 导入 12700K 本地改动

确认 `$ProjectPath` 是旧代码目录，`$GitWork` 是刚克隆的新 Git 目录：

```powershell
robocopy $ProjectPath $GitWork /E /XD .git __pycache__ backups runtime\logs /XF *.pyc *.pyo *.log *.db *.sqlite *.sqlite3
cd $GitWork
git status
git add .
git commit -m "Import 12700K local changes"
git push -u origin HEAD
```

## 5. 日常协作

```powershell
git fetch origin
git switch -c codex/12700k-feature-name origin/main
# 修改、测试
git add .
git commit -m "说明这次修改"
git push -u origin HEAD
```

不要直接在 `main` 上修改；`main` 只保留确认可部署的代码。
