param(
    [Parameter(Mandatory = $true)][string]$Task,
    [Parameter(Mandatory = $true)][string]$Module,
    [Parameter(Mandatory = $true)][string]$Machine,
    [ValidateSet("light", "heavy")][string]$Kind = "light",
    [string]$Base = "origin/main",
    [string]$WorktreeBase = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Invoke-Git {
    $OldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & git @args
        $ExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $OldErrorActionPreference
    }
    if ($ExitCode -ne 0) {
        throw "git command failed ($ExitCode): git $($args -join ' ')"
    }
}

$ScriptDir = Split-Path -Parent $PSCommandPath
$Root = [System.IO.Path]::GetFullPath((Join-Path $ScriptDir "../.."))
Set-Location $Root
Invoke-Git rev-parse --is-inside-work-tree *> $null

if (-not $WorktreeBase) {
    $WorktreeBase = Join-Path (Split-Path -Parent $Root) "smart-center-worktrees"
}

$LockBranch = "coordination/worklocks"
$LockRef = $LockBranch
$WorktreePath = Join-Path $WorktreeBase $Task
$DateTag = Get-Date -Format "yyyyMMdd"
$Branch = "codex/$Machine-$Task-$DateTag"
$LockFile = "locks/$Module.json"

Invoke-Git fetch --all --prune
New-Item -ItemType Directory -Force -Path $WorktreeBase | Out-Null

$ActiveCount = 0
foreach ($Line in (& git worktree list --porcelain)) {
    if ($Line -like "worktree *") {
        $Path = $Line.Substring(9)
        if ($Path.StartsWith($WorktreeBase, [System.StringComparison]::OrdinalIgnoreCase)) {
            $ActiveCount += 1
        }
    }
}
if ($ActiveCount -ge 5 -and -not (Test-Path -LiteralPath $WorktreePath)) {
    throw "this machine already has $ActiveCount worktrees under base; limit is 5"
}

$OldErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& git ls-remote --exit-code --heads origin $LockBranch *> $null
$ErrorActionPreference = $OldErrorActionPreference
if ($LASTEXITCODE -ne 0) {
    throw "worklock branch missing; run scripts/collab/setup-git-collab.ps1"
}

$RefSpec = "+refs/heads/${LockBranch}:refs/heads/${LockBranch}"
Invoke-Git fetch origin $RefSpec *> $null

$OldErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& git cat-file -e "${LockRef}:$LockFile" 2>$null
$ErrorActionPreference = $OldErrorActionPreference
if ($LASTEXITCODE -eq 0) {
    Write-Host "module is already locked: $Module"
    & git show "${LockRef}:$LockFile"
    exit 1
}

if (Test-Path -LiteralPath $WorktreePath) {
    throw "worktree already exists: $WorktreePath"
}

Invoke-Git worktree add -b $Branch $WorktreePath $Base

$TaskDir = Join-Path $WorktreePath ".worktasks/$Task"
New-Item -ItemType Directory -Force -Path $TaskDir | Out-Null

$StartedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$TaskMd = @"
# Task Memory

## Basic Info

- Task: $Task
- Module lock: $Module
- Branch: $Branch
- Worktree: $WorktreePath
- Machine: $Machine
- Kind: $Kind
- Started: $StartedAt
- Expected finish:

## Goal

```text
Fill in the goal before making code changes.
```

## Current Phase

```text
in_progress
```

## Change Scope

```text
Fill in planned or actual changed files.
```

## Done

- Created task worktree
- Acquired module worklock

## Verified

-

## Not Verified

-

## Risks

-

## Dependencies And Conflicts

```text
If this task touches templates/index.html, config.py, background.py, app.py, api/server.py, or snmp_core.py, acquire the related high-risk lock too.
```

## Next

-
"@
Set-Content -LiteralPath (Join-Path $TaskDir "TASK.md") -Value $TaskMd -Encoding UTF8

$Status = [ordered]@{
    task       = $Task
    module     = $Module
    machine    = $Machine
    kind       = $Kind
    branch     = $Branch
    worktree   = $WorktreePath
    started_at = $StartedAt
    status     = "in_progress"
}
($Status | ConvertTo-Json -Depth 4) | Set-Content -LiteralPath (Join-Path $TaskDir "STATUS.json") -Encoding UTF8

$TmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("smart-center-locks-" + [guid]::NewGuid().ToString("N"))
try {
    Invoke-Git worktree add --detach $TmpDir $LockRef
    Push-Location $TmpDir
    try {
        New-Item -ItemType Directory -Force -Path "locks" | Out-Null
        $Lock = [ordered]@{
            module         = $Module
            owner_machine  = $Machine
            owner_branch   = $Branch
            task           = $Task
            kind           = $Kind
            worktree       = $WorktreePath
            started_at     = $StartedAt
            expected_until = ""
            note           = "created by scripts/collab/start-work.ps1"
        }
        ($Lock | ConvertTo-Json -Depth 4) | Set-Content -LiteralPath $LockFile -Encoding UTF8
        Invoke-Git add $LockFile
        Invoke-Git commit -m "lock: $Module by $Machine"
        Invoke-Git push origin "HEAD:$LockBranch"
    } finally {
        Pop-Location
    }
} finally {
    & git worktree remove --force $TmpDir *> $null
    if (Test-Path -LiteralPath $TmpDir) {
        Remove-Item -LiteralPath $TmpDir -Force -Recurse
    }
}

Write-Host "task created:"
Write-Host "  worktree: $WorktreePath"
Write-Host "  branch:   $Branch"
Write-Host "  lock:     $Module"
Write-Host ""
Write-Host "enter task directory:"
Write-Host "  cd `"$WorktreePath`""
