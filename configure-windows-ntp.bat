@echo off
setlocal
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo Please run this file as Administrator.
  pause
  exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure-windows-ntp.ps1"
pause
