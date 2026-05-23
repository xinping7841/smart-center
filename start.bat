@echo off
chcp 65001 >nul
echo ========================================
echo   Smart Power Monitor - Starting...
echo ========================================
echo.

cd /d "%~dp0"
set "SERVICE_PORT=6899"
set "PORT_STATE="
set "SCRIPT_PATH=%~dp0app.py"

for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$projectPath = (Resolve-Path '%~dp0').Path.TrimEnd('\');" ^
  "$listener = Get-NetTCPConnection -State Listen -LocalPort %SERVICE_PORT% -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
  "if (-not $listener) { Write-Output 'FREE'; exit 0 }" ^
  "$proc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $listener.OwningProcess) -ErrorAction SilentlyContinue;" ^
  "$cmd = [string]($proc.CommandLine);" ^
  "$isProjectProc = ($cmd -like ('*' + $projectPath + '*')) -or (($cmd -like '*.venv*\Scripts\python.exe*') -and ($cmd -like '*app.py*'));" ^
  "if ($isProjectProc) { Write-Output 'RUNNING'; exit 0 }" ^
  "Write-Output ('BUSY:' + $listener.OwningProcess)"`) do set "PORT_STATE=%%I"

if /I "%PORT_STATE%"=="RUNNING" (
    echo [INFO] Detected an existing Smart Power Monitor service.
    echo [INFO] Open: http://localhost:%SERVICE_PORT%/login
    echo [INFO] Use restart_project.bat if you want to restart it.
    echo.
    pause
    exit /b 0
)

if not "%PORT_STATE%"=="" if /I not "%PORT_STATE%"=="FREE" (
    echo [ERROR] Port %SERVICE_PORT% is already occupied: %PORT_STATE%
    echo [ERROR] Run stop_current_project.bat first, then start again.
    echo.
    pause
    exit /b 1
)

set "PYTHON_EXE="
if exist ".venv64\Scripts\python.exe" set "PYTHON_EXE=.venv64\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"
if not defined PYTHON_EXE (
    where py >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=py -3.13"
)
if not defined PYTHON_EXE (
    where py >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=py -3.14"
)
if not defined PYTHON_EXE (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
    echo [ERROR] No usable Python interpreter was found.
    pause
    exit /b 1
)

set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1

echo [1/2] Using interpreter: %PYTHON_EXE%
echo [2/2] Starting service...
echo.
echo Service URL: http://localhost:%SERVICE_PORT%/login
echo Press Ctrl+C to stop the service.
echo.
%PYTHON_EXE% "%SCRIPT_PATH%"

pause
