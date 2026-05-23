param(
    [string]$Machine = "",
    [string]$WorktreeBase = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $PSCommandPath
$Root = [System.IO.Path]::GetFullPath((Join-Path $ScriptDir "../.."))
Set-Location $Root
& git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) {
    throw "not inside a git repository: $Root"
}

if (-not $Machine) {
    $Machine = ($env:COMPUTERNAME | ForEach-Object { $_.ToLowerInvariant() }) -replace "[^a-z0-9-]", "-"
    if (-not $Machine) {
        $Machine = "machine"
    }
}

if (-not $WorktreeBase) {
    $WorktreeBase = Join-Path (Split-Path -Parent $Root) "smart-center-worktrees"
}

Write-Host "== Smart Center collaboration bootstrap =="
Write-Host "repo: $Root"
Write-Host "machine: $Machine"
Write-Host "worktree_base: $WorktreeBase"
Write-Host ""

& git config user.name "codex-$Machine"
& git config user.email "codex-$Machine@smart-center.local"
& git config pull.rebase true
& git config fetch.prune true
& git config rerere.enabled true
& git config merge.conflictstyle zdiff3
& git config branch.autosetuprebase always

New-Item -ItemType Directory -Force -Path $WorktreeBase | Out-Null

& powershell -NoProfile -ExecutionPolicy Bypass -File "scripts/collab/setup-git-collab.ps1" -WorktreeBase $WorktreeBase

Write-Host ""
Write-Host "== sync check =="
& powershell -NoProfile -ExecutionPolicy Bypass -File "scripts/collab/check-sync.ps1" -WorktreeBase $WorktreeBase

Write-Host ""
Write-Host "== recommended task commands =="
Write-Host "powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/start-work.ps1 -Task server-monitor-refactor -Module server_monitor -Machine $Machine -Kind heavy -WorktreeBase `"$WorktreeBase`""
Write-Host "powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/start-work.ps1 -Task snmp-monitor-refactor -Module snmp_monitor -Machine $Machine -Kind heavy -WorktreeBase `"$WorktreeBase`""
Write-Host "powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/start-work.ps1 -Task frontend-module-split -Module templates_index -Machine $Machine -Kind heavy -WorktreeBase `"$WorktreeBase`""
Write-Host "powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/start-work.ps1 -Task core-config-cleanup -Module config_core -Machine $Machine -Kind light -WorktreeBase `"$WorktreeBase`""
Write-Host "powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/start-work.ps1 -Task validation-docs-report -Module docs -Machine $Machine -Kind light -WorktreeBase `"$WorktreeBase`""
Write-Host ""
Write-Host "bootstrap done"
