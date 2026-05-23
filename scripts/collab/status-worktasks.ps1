param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $PSCommandPath
$Root = [System.IO.Path]::GetFullPath((Join-Path $ScriptDir "../.."))
Set-Location $Root
& git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) {
    throw "not inside a git repository: $Root"
}

$TaskRoot = Join-Path $Root ".worktasks"
if (-not (Test-Path -LiteralPath $TaskRoot)) {
    Write-Host "no .worktasks directory"
    exit 0
}

$Rows = @()
Get-ChildItem -LiteralPath $TaskRoot -Directory | ForEach-Object {
    $TaskName = $_.Name
    $StatusPath = Join-Path $_.FullName "STATUS.json"
    if (Test-Path -LiteralPath $StatusPath) {
        try {
            $Status = Get-Content -LiteralPath $StatusPath -Raw | ConvertFrom-Json
            $Props = @{}
            foreach ($Prop in $Status.PSObject.Properties) {
                $Props[$Prop.Name] = $Prop.Value
            }
            $Rows += [pscustomobject]@{
                task       = if ($Props.ContainsKey("task")) { $Props["task"] } else { $TaskName }
                module     = if ($Props.ContainsKey("module")) { $Props["module"] } else { "" }
                machine    = if ($Props.ContainsKey("machine")) { $Props["machine"] } else { "" }
                kind       = if ($Props.ContainsKey("kind")) { $Props["kind"] } else { "" }
                status     = if ($Props.ContainsKey("status")) { $Props["status"] } else { "" }
                branch     = if ($Props.ContainsKey("branch")) { $Props["branch"] } else { "" }
                started_at = if ($Props.ContainsKey("started_at")) { $Props["started_at"] } else { "" }
            }
        } catch {
            $Rows += [pscustomobject]@{
                task       = $TaskName
                module     = ""
                machine    = ""
                kind       = ""
                status     = "invalid STATUS.json"
                branch     = ""
                started_at = ""
            }
        }
    }
}

if ($Rows.Count -eq 0) {
    Write-Host "no worktask status files"
} else {
    $Rows | Format-Table -AutoSize
}
