@echo off
chcp 65001 >nul
title Stop Current Smart Power Monitor
setlocal

set "NO_PAUSE=%~1"
set "SERVICE_PORT=6899"

echo ========================================
echo   Stop Current Smart Power Monitor
echo ========================================
echo.
echo Scanning project-related Python processes...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$projectPath = (Resolve-Path '%~dp0').Path.TrimEnd('\');" ^
  "$pidSet = New-Object 'System.Collections.Generic.HashSet[int]';" ^
  "$pythonNames = @('python.exe','pythonw.exe','python3.13.exe','python3.14.exe','py.exe');" ^
  "Get-CimInstance Win32_Process | Where-Object { ($_.Name -in $pythonNames) -and $_.CommandLine -and (([string]$_.CommandLine -like ('*' + $projectPath + '*')) -or ([string]$_.CommandLine -like '*app.py*')) } | ForEach-Object { [void]$pidSet.Add([int]$_.ProcessId) };" ^
  "Get-NetTCPConnection -LocalPort %SERVICE_PORT% -ErrorAction SilentlyContinue | ForEach-Object { $proc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $_.OwningProcess) -ErrorAction SilentlyContinue; $cmd = [string]$proc.CommandLine; if ($proc -and ($proc.Name -in $pythonNames) -and (($cmd -like ('*' + $projectPath + '*')) -or ($cmd -like '*app.py*'))) { [void]$pidSet.Add([int]$_.OwningProcess) } };" ^
  "if ($pidSet.Count -eq 0) { Write-Host 'No running project process was found.'; exit 0 };" ^
  "$pidSet | Sort-Object | ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction Stop; Write-Host ('Stopped PID: ' + $_) } catch { Write-Host ('Failed to stop PID: ' + $_ + ' -> ' + $PSItem.Exception.Message) } }"

echo.
echo Done. You can run start.bat or restart_project.bat when needed.
echo.

if /I not "%NO_PAUSE%"=="nopause" pause
endlocal
