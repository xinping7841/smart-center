$ErrorActionPreference = 'Stop'

function Show-Step([string]$Message) {
    Write-Host "[Deploy] $Message" -ForegroundColor Cyan
}

function Pause-Fail([string]$Message) {
    Write-Host ''
    Write-Host $Message -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}

try {
    Clear-Host
    $source = $PSScriptRoot
    $installDir = Join-Path $env:LOCALAPPDATA 'CompanyProxyTool'
    $desktop = [Environment]::GetFolderPath('Desktop')
    $files = @(
        'company-proxy-enable.cmd',
        'company-proxy-disable.cmd',
        'company-proxy-diagnose.cmd',
        'company-proxy-enable.ps1',
        'company-proxy-disable.ps1',
        'company-proxy-diagnose.ps1',
        'README.txt',
        'company-proxy-cleanup.cmd',
        'company-proxy-cleanup.ps1'
    )

    Show-Step '1/3 Creating local install directory'
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null

    Show-Step '2/3 Copying tool files'
    foreach ($file in $files) {
        Copy-Item -LiteralPath (Join-Path $source $file) -Destination (Join-Path $installDir $file) -Force
    }

    Show-Step '3/3 Creating desktop shortcuts'
    $ws = New-Object -ComObject WScript.Shell

    $lnk1 = $ws.CreateShortcut((Join-Path $desktop '公司代理-开启.lnk'))
    $lnk1.TargetPath = Join-Path $installDir 'company-proxy-enable.cmd'
    $lnk1.WorkingDirectory = $installDir
    $lnk1.IconLocation = "$env:SystemRoot\System32\shell32.dll,174"
    $lnk1.Save()

    $lnk2 = $ws.CreateShortcut((Join-Path $desktop '公司代理-关闭.lnk'))
    $lnk2.TargetPath = Join-Path $installDir 'company-proxy-disable.cmd'
    $lnk2.WorkingDirectory = $installDir
    $lnk2.IconLocation = "$env:SystemRoot\System32\shell32.dll,131"
    $lnk2.Save()

    $lnk3 = $ws.CreateShortcut((Join-Path $desktop '公司代理-诊断.lnk'))
    $lnk3.TargetPath = Join-Path $installDir 'company-proxy-diagnose.cmd'
    $lnk3.WorkingDirectory = $installDir
    $lnk3.IconLocation = "$env:SystemRoot\System32\shell32.dll,23"
    $lnk3.Save()

    Write-Host ''
    Write-Host 'Deployment complete. Desktop shortcuts were created.' -ForegroundColor Green
    Start-Sleep -Seconds 2
    exit 0
} catch {
    Pause-Fail "Deployment failed: $($_.Exception.Message)"
}

