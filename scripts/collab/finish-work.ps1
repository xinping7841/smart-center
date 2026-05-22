param(
    [string]$Message = "",
    [string]$ReleaseLock = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Git {
    & git @args
    if ($LASTEXITCODE -ne 0) {
        throw "git command failed: git $($args -join ' ')"
    }
}

function Get-PythonCommand {
    foreach ($Name in @("python", "python3", "py")) {
        $Cmd = Get-Command $Name -ErrorAction SilentlyContinue
        if ($Cmd) {
            return $Name
        }
    }
    return ""
}

$Root = (& git rev-parse --show-toplevel 2>$null).Trim()
if (-not $Root) {
    throw "not inside a git repository"
}
Set-Location $Root

$LockBranch = "coordination/worklocks"
$RemoteLockRef = "origin/$LockBranch"

Write-Host "== status =="
& git status -sb
Write-Host ""

Write-Host "== diff stat =="
& git diff --stat
Write-Host ""

Write-Host "== compile check =="
$Python = Get-PythonCommand
if ($Python) {
    $Targets = @()
    foreach ($Target in @("app.py", "api", "services", "runtime", "modules", "core", "config.py", "background.py", "power.py", "snmp_core.py")) {
        if (Test-Path -LiteralPath $Target) {
            $Targets += $Target
        }
    }
    if ($Targets.Count -eq 0) {
        Write-Host "no python compile targets found"
    } else {
        & $Python -m compileall @Targets
        if ($LASTEXITCODE -ne 0) {
            throw "python compile check failed"
        }
    }
} else {
    Write-Host "python missing, skip compile"
}
Write-Host ""

if ($Message) {
    $Dirty = (& git status --porcelain)
    if (-not $Dirty) {
        Write-Host "no changes to commit"
    } else {
        Invoke-Git add -A
        Invoke-Git commit -m $Message
    }
    $CurrentBranch = (& git branch --show-current).Trim()
    Invoke-Git push -u origin $CurrentBranch
} else {
    Write-Host "no -Message provided; skip commit and push"
}

if ($ReleaseLock) {
    & git ls-remote --exit-code --heads origin $LockBranch *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "worklock branch missing, skip release"
        exit 0
    }
    $RefSpec = "${LockBranch}:refs/remotes/origin/${LockBranch}"
    & git fetch origin $RefSpec *> $null
    $TmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("smart-center-locks-" + [guid]::NewGuid().ToString("N"))
    try {
        Invoke-Git worktree add --detach $TmpDir $RemoteLockRef
        Push-Location $TmpDir
        try {
            Invoke-Git switch -C $LockBranch $RemoteLockRef
            $LockFile = "locks/$ReleaseLock.json"
            if (Test-Path -LiteralPath $LockFile) {
                Remove-Item -LiteralPath $LockFile -Force
                Invoke-Git add -u -- $LockFile
                Invoke-Git commit -m "unlock: $ReleaseLock"
                Invoke-Git push origin $LockBranch
                Write-Host "released lock: $ReleaseLock"
            } else {
                Write-Host "lock not found: $ReleaseLock"
            }
        } finally {
            Pop-Location
        }
    } finally {
        & git worktree remove --force $TmpDir *> $null
        if (Test-Path -LiteralPath $TmpDir) {
            Remove-Item -LiteralPath $TmpDir -Force -Recurse
        }
    }
}

Write-Host "finish done"
