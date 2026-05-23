$ErrorActionPreference = 'Continue'
$proxyHost = '192.168.50.254'
$proxyPort = 7895
$regPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'

function Show-Section([string]$Title) {
    Write-Host ''
    Write-Host "==== $Title ====" -ForegroundColor Cyan
}

function Show-Value([string]$Name, [string]$Value, [ConsoleColor]$Color = [ConsoleColor]::Gray) {
    Write-Host ($Name.PadRight(18) + $Value) -ForegroundColor $Color
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

Clear-Host
Write-Host 'Company proxy diagnostics starting...' -ForegroundColor Green

Show-Section 'Target Proxy'
Show-Value 'Proxy Host' $proxyHost
Show-Value 'Proxy Port' ([string]$proxyPort)

Show-Section 'System Proxy State'
try {
    $props = Get-ItemProperty -Path $regPath -ErrorAction Stop
    Show-Value 'ProxyEnable' ([string]$props.ProxyEnable)
    Show-Value 'ProxyServer' ([string]$props.ProxyServer)
    Show-Value 'ProxyOverride' ([string]$props.ProxyOverride)
} catch {
    Show-Value 'System Proxy' 'Registry values not found' Yellow
}

Show-Section 'Reachability'
try {
    $pingOk = Test-Connection -ComputerName $proxyHost -Count 1 -Quiet -ErrorAction Stop
    Show-Value 'Ping NAS' ($(if($pingOk){'Success'}else{'Failed'})) $(if($pingOk){'Green'}else{'Red'})
} catch {
    Show-Value 'Ping NAS' 'Failed' Red
}

$tcpOk = Test-TcpPort -HostName $proxyHost -Port $proxyPort
Show-Value 'TCP 7895' ($(if($tcpOk){'Success'}else{'Failed'})) $(if($tcpOk){'Green'}else{'Red'})

Show-Section 'Notes'
Write-Host '1. If Ping fails, check routing or VLAN reachability to NAS.'
Write-Host '2. If TCP 7895 fails, check ACL, firewall, or NAS listener.'
Write-Host '3. If manual proxy works but scripts fail, send this screen back for review.'
Write-Host ''
Read-Host 'Press Enter to close'
