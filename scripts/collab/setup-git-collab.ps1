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

Write-Host "[setup] repo: $Root"
Write-Host "[setup] worktree base: $WorktreeBase"

Invoke-Git config pull.rebase true
Invoke-Git config fetch.prune true
Invoke-Git config rerere.enabled true
Invoke-Git config merge.conflictstyle zdiff3
Invoke-Git config branch.autosetuprebase always

New-Item -ItemType Directory -Force -Path $WorktreeBase | Out-Null

$Origin = (& git remote get-url origin 2>$null)
if ($LASTEXITCODE -eq 0) {
    Write-Host "[setup] origin: $Origin"
} else {
    Write-Host "[setup] warning: origin remote is missing"
}

$OldErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& git ls-remote --exit-code --heads origin $LockBranch *> $null
$ErrorActionPreference = $OldErrorActionPreference
$HasLockBranch = ($LASTEXITCODE -eq 0)

if ($HasLockBranch) {
    Write-Host "[setup] worklock branch exists: origin/$LockBranch"
    $RefSpec = "${LockBranch}:refs/remotes/origin/${LockBranch}"
    Invoke-Git fetch origin $RefSpec *> $null
} else {
    Write-Host "[setup] creating worklock branch: $LockBranch"
    $TmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("smart-center-locks-" + [guid]::NewGuid().ToString("N"))
    try {
        Invoke-Git worktree add --detach $TmpDir HEAD
        Push-Location $TmpDir
        try {
            Invoke-Git switch --orphan $LockBranch
            Invoke-Git rm -rf . *> $null
            New-Item -ItemType Directory -Force -Path "locks" | Out-Null
            Set-Content -Path "README.md" -Value "# Smart Center worklocks`n`nThis branch stores module work locks only.`n" -Encoding UTF8
            Set-Content -Path "locks/.gitkeep" -Value "" -Encoding UTF8
            Invoke-Git add README.md locks/.gitkeep
            Invoke-Git commit -m "chore: initialize worklocks"
            Invoke-Git push -u origin $LockBranch
        } finally {
            Pop-Location
        }
    } finally {
        & git worktree remove --force $TmpDir *> $null
        if (Test-Path -LiteralPath $TmpDir) {
            Remove-Item -LiteralPath $TmpDir -Force -Recurse
        }
    }
    Write-Host "[setup] worklock branch created and pushed"
}

Write-Host "[setup] done"
