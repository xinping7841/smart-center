$ErrorActionPreference = 'Stop'
$regPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'

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

try {
    Clear-Host
    Show-Step '1/3 Disabling system proxy'
    New-ItemProperty -Path $regPath -Name ProxyEnable -Value 0 -PropertyType DWord -Force | Out-Null

    Show-Step '2/3 Clearing proxy server and bypass list'
    Remove-ItemProperty -Path $regPath -Name ProxyServer -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path $regPath -Name ProxyOverride -ErrorAction SilentlyContinue

    Show-Step '3/3 Refreshing system proxy state'
    Refresh-Proxy

    Write-Host ''
    Write-Host 'Company proxy disabled. Window will close automatically.' -ForegroundColor Green
    Start-Sleep -Seconds 2
    exit 0
} catch {
    Pause-Fail "Disable failed: $($_.Exception.Message)"
}
