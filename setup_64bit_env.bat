@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

set "PIP_INDEX_URL=%SMART_POWER_PIP_INDEX_URL%"
if not defined PIP_INDEX_URL set "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple"

where py >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python Launcher `py.exe` was not found.
    pause
    exit /b 1
)

echo ========================================
echo   Smart Power Monitor - 64-bit Env Setup
echo ========================================
echo.
echo [1/5] Creating 64-bit virtual environment...
py -3.13 -m venv .venv64
if errorlevel 1 (
    echo [ERROR] Failed to create .venv64 with Python 3.13 x64.
    pause
    exit /b 1
)

echo [2/5] Upgrading pip...
".venv64\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip.
    pause
    exit /b 1
)

echo [3/5] Installing Windows 64-bit runtime dependencies...
".venv64\Scripts\python.exe" -m pip install -i "%PIP_INDEX_URL%" --prefer-binary --progress-bar off -r requirements-windows64.txt
if errorlevel 1 (
    echo [ERROR] Failed to install requirements-windows64.txt.
    pause
    exit /b 1
)

echo [4/5] Installing python-miio without netifaces...
".venv64\Scripts\python.exe" -m pip install -i "%PIP_INDEX_URL%" --no-deps --progress-bar off python-miio==0.5.12
if errorlevel 1 (
    echo [ERROR] Failed to install python-miio.
    pause
    exit /b 1
)

echo [5/5] Verifying runtime bitness...
".venv64\Scripts\python.exe" -c "import struct,sys; print('Python:', sys.version); print('Bits:', struct.calcsize('P') * 8); print('Executable:', sys.executable)"
if errorlevel 1 (
    echo [ERROR] 64-bit runtime verification failed.
    pause
    exit /b 1
)

echo.
echo [OK] .venv64 is ready. start.bat and run_web.bat will now prefer it automatically.
echo.
pause
endlocal
