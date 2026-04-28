$ErrorActionPreference = 'Stop'

function Show-Step([string]$Message) {
    Write-Host "[Cleanup] $Message" -ForegroundColor Cyan
}

function Pause-Fail([string]$Message) {
    Write-Host ''
    Write-Host $Message -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}

try {
    Clear-Host
    $installDir = Join-Path $env:LOCALAPPDATA 'CompanyProxyTool'
    $desktop = [Environment]::GetFolderPath('Desktop')
    $links = @('公司代理-开启.lnk','公司代理-关闭.lnk','公司代理-诊断.lnk')

    Show-Step '1/2 Removing desktop shortcuts'
    foreach ($link in $links) {
        $path = Join-Path $desktop $link
        if (Test-Path $path) {
            Remove-Item -LiteralPath $path -Force
        }
    }

    Show-Step '2/2 Removing local install directory'
    if (Test-Path $installDir) {
        Remove-Item -LiteralPath $installDir -Recurse -Force
    }

    Write-Host ''
    Write-Host 'Cleanup complete. Desktop shortcuts and local files were removed.' -ForegroundColor Green
    Start-Sleep -Seconds 2
    exit 0
} catch {
    Pause-Fail "Cleanup failed: $($_.Exception.Message)"
}
