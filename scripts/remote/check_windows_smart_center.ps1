$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Output "== identity =="
hostname
whoami

Write-Output "== os =="
Get-CimInstance Win32_OperatingSystem |
  Select-Object Caption, Version, OSArchitecture |
  Format-List

Write-Output "== tools =="
foreach ($name in @("git", "python", "py", "node", "npm", "ssh")) {
  $cmd = Get-Command $name -ErrorAction SilentlyContinue
  if ($cmd) {
    Write-Output ("{0}={1}" -f $name, $cmd.Source)
    try {
      if ($name -eq "ssh") {
        cmd /c "`"$($cmd.Source)`" -V 2>&1" | Select-Object -First 1
      } else {
        & $name --version 2>$null | Select-Object -First 1
      }
    } catch {
      Write-Output ("{0}=version_check_failed:{1}" -f $name, $_.Exception.Message)
    }
  } else {
    Write-Output ("{0}=MISSING" -f $name)
  }
}

Write-Output "== smart-center dirs =="
foreach ($path in @(
  "D:\SmartCenter",
  "D:\SmartCenter\smart-center-clean",
  "D:\SmartCenter\smart-center-worktrees"
)) {
  if (Test-Path -LiteralPath $path) {
    Write-Output ("{0} EXISTS" -f $path)
  } else {
    Write-Output ("{0} MISSING" -f $path)
  }
}

if (Test-Path -LiteralPath "D:\SmartCenter\smart-center-clean\.git") {
  Write-Output "== repo =="
  Set-Location -LiteralPath "D:\SmartCenter\smart-center-clean"
  git status --short --branch
  git remote -v
  git branch -vv

  Write-Output "== worktrees =="
  git worktree list

  Write-Output "== collab check =="
  powershell -NoProfile -ExecutionPolicy Bypass `
    -File scripts\collab\check-sync.ps1 `
    -WorktreeBase D:\SmartCenter\smart-center-worktrees
}
