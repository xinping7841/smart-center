$ErrorActionPreference = 'Stop'

$PrimaryNtp = '192.168.50.120'
$FallbackNtp = '192.168.50.121'
$PeerList = "$PrimaryNtp,0x8 $FallbackNtp,0x8"

Write-Host "Configuring Windows Time service..."
Write-Host "Primary NTP:  $PrimaryNtp"
Write-Host "Fallback NTP: $FallbackNtp"

Start-Service w32time -ErrorAction SilentlyContinue
Set-Service w32time -StartupType Automatic

w32tm /config /manualpeerlist:$PeerList /syncfromflags:manual /reliable:no /update | Out-Host
Restart-Service w32time -Force

try {
    w32tm /resync /force | Out-Host
} catch {
    Write-Warning "Initial resync failed, service will retry automatically: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "Current time source:"
w32tm /query /source | Out-Host
Write-Host ""
Write-Host "Time status:"
w32tm /query /status | Out-Host
