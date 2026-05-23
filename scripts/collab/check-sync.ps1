param(
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

$Root = (& git rev-parse --show-toplevel 2>$null).Trim()
if (-not $Root) {
    throw "not inside a git repository"
}
Set-Location $Root

if (-not $WorktreeBase) {
    $WorktreeBase = Join-Path (Split-Path -Parent $Root) "smart-center-worktrees"
}

$LockBranch = "coordination/worklocks"
$RemoteLockRef = "origin/$LockBranch"

Write-Host "== repo =="
Write-Host $Root
Write-Host ""

Write-Host "== fetch =="
Invoke-Git fetch --all --prune
Write-Host ""

Write-Host "== branch/status =="
& git status -sb
Write-Host ""

Write-Host "== upstream ahead/behind =="
$Upstream = (& git rev-parse --abbrev-ref --symbolic-full-name "@{upstream}" 2>$null).Trim()
if ($LASTEXITCODE -eq 0 -and $Upstream) {
    $Counts = (& git rev-list --left-right --count "HEAD...$Upstream").Trim()
    Write-Host "upstream: $Upstream"
    Write-Host "ahead/behind: $Counts"
} else {
    Write-Host "no upstream configured"
}
Write-Host ""

Write-Host "== recent graph =="
& git log --oneline --decorate --graph --all -20
Write-Host ""

Write-Host "== local dirty high-risk files =="
& git status --porcelain -- templates/index.html api/server.py snmp_core.py config.py background.py app.py
Write-Host ""

Write-Host "== active worktrees under base =="
Write-Host "base: $WorktreeBase"
if (Test-Path -LiteralPath $WorktreeBase) {
    $NormalizedBase = [System.IO.Path]::GetFullPath($WorktreeBase).TrimEnd('\', '/').Replace('\', '/')
    $CurrentPath = $null
    foreach ($Line in (& git worktree list --porcelain)) {
        if ($Line -like "worktree *") {
            $CurrentPath = $Line.Substring(9)
            $NormalizedPath = [System.IO.Path]::GetFullPath($CurrentPath).TrimEnd('\', '/').Replace('\', '/')
            if ($NormalizedPath.StartsWith($NormalizedBase, [System.StringComparison]::OrdinalIgnoreCase)) {
                Write-Host $CurrentPath
            }
        }
    }
} else {
    Write-Host "none"
}
Write-Host ""

Write-Host "== worklocks =="
$OldErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& git ls-remote --exit-code --heads origin $LockBranch *> $null
$ErrorActionPreference = $OldErrorActionPreference
if ($LASTEXITCODE -eq 0) {
    $RefSpec = "${LockBranch}:refs/remotes/origin/${LockBranch}"
    Invoke-Git fetch origin $RefSpec *> $null
    $Locks = @(& git ls-tree -r --name-only $RemoteLockRef locks 2>$null | Where-Object { $_ -like "*.json" })
    if (-not $Locks -or $Locks.Count -eq 0) {
        Write-Host "no active locks"
    } else {
        foreach ($LockFile in $Locks) {
            Write-Host "--- $LockFile"
            & git show "${RemoteLockRef}:$LockFile"
            Write-Host ""
        }
    }
} else {
    Write-Host "worklock branch missing; run scripts/collab/setup-git-collab.ps1"
}
