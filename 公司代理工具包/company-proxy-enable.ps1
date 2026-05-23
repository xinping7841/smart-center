$ErrorActionPreference = 'Stop'
$regPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
$proxyHost = '192.168.50.254'
$proxyPort = 7895
$proxyAddress = "${proxyHost}:$proxyPort"

function Show-Step([string]$Message) {
    Write-Host "[Company Proxy] $Message" -ForegroundColor Cyan
}

function Pause-Fail([string]$Message) {
    Write-Host ''
    Write-Host $Message -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}

function Ensure-WinInet {
    if (-not ('WinInet.NativeMethods' -as [type])) {
        $code = @"
using System;
using System.Runtime.InteropServices;
namespace WinInet {
    public static class NativeMethods {
        [DllImport("wininet.dll", SetLastError = true)]
        public static extern bool InternetSetOption(IntPtr hInternet, int dwOption, IntPtr lpBuffer, int dwBufferLength);
    }
}
"@
        Add-Type -TypeDefinition $code -ErrorAction Stop
    }
}

function Refresh-Proxy {
    Ensure-WinInet
    [WinInet.NativeMethods]::InternetSetOption([IntPtr]::Zero, 39, [IntPtr]::Zero, 0) | Out-Null
    [WinInet.NativeMethods]::InternetSetOption([IntPtr]::Zero, 37, [IntPtr]::Zero, 0) | Out-Null
}

function Get-Snapshot {
    $props = Get-ItemProperty -Path $regPath -ErrorAction SilentlyContinue
    [pscustomobject]@{
        HasProxyEnable = ($null -ne $props -and $null -ne $props.ProxyEnable)
        ProxyEnable = if ($null -ne $props.ProxyEnable) { [int]$props.ProxyEnable } else { 0 }
        HasProxyServer = ($null -ne $props -and $null -ne $props.ProxyServer)
        ProxyServer = if ($null -ne $props.ProxyServer) { [string]$props.ProxyServer } else { $null }
        HasProxyOverride = ($null -ne $props -and $null -ne $props.ProxyOverride)
        ProxyOverride = if ($null -ne $props.ProxyOverride) { [string]$props.ProxyOverride } else { $null }
    }
}

function Restore-Snapshot($Snapshot) {
    if ($Snapshot.HasProxyServer) {
        New-ItemProperty -Path $regPath -Name ProxyServer -Value $Snapshot.ProxyServer -PropertyType String -Force | Out-Null
    } else {
        Remove-ItemProperty -Path $regPath -Name ProxyServer -ErrorAction SilentlyContinue
    }
    if ($Snapshot.HasProxyOverride) {
        New-ItemProperty -Path $regPath -Name ProxyOverride -Value $Snapshot.ProxyOverride -PropertyType String -Force | Out-Null
    } else {
        Remove-ItemProperty -Path $regPath -Name ProxyOverride -ErrorAction SilentlyContinue
    }
    if ($Snapshot.HasProxyEnable) {
        New-ItemProperty -Path $regPath -Name ProxyEnable -Value $Snapshot.ProxyEnable -PropertyType DWord -Force | Out-Null
    } else {
        Remove-ItemProperty -Path $regPath -Name ProxyEnable -ErrorAction SilentlyContinue
    }
    Refresh-Proxy
}

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutMs = 5000) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) { return $false }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

$backup = Get-Snapshot

try {
    Clear-Host
    Show-Step '1/4 Writing system proxy settings'
    New-ItemProperty -Path $regPath -Name ProxyServer -Value $proxyAddress -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $regPath -Name ProxyOverride -Value '<local>' -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $regPath -Name ProxyEnable -Value 1 -PropertyType DWord -Force | Out-Null

    Show-Step '2/4 Refreshing system proxy state'
    Refresh-Proxy

    Show-Step '3/4 Verifying proxy settings'
    $props = Get-ItemProperty -Path $regPath -ErrorAction Stop
    if ($props.ProxyEnable -ne 1 -or $props.ProxyServer -ne $proxyAddress) {
        throw 'Proxy verification failed after writing settings'
    }

    Show-Step "4/4 Checking NAS proxy port $proxyAddress"
    if (-not (Test-TcpPort -HostName $proxyHost -Port $proxyPort)) {
        throw "Cannot connect to proxy port $proxyAddress"
    }

    Write-Host ''
    Write-Host 'Company proxy enabled. Window will close automatically.' -ForegroundColor Green
    Start-Sleep -Seconds 2
    exit 0
} catch {
    Write-Host ''
    Write-Host "Enable failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Restoring previous proxy settings...' -ForegroundColor Yellow
    Restore-Snapshot -Snapshot $backup
    Pause-Fail 'Previous settings restored. Please run diagnose if needed.'
}
