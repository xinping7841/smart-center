@echo off
chcp 65001 >nul
title Stop Python Services

echo ========================================
echo   Stop Python Services
echo ========================================
echo.
echo 正在停止当前机器上的所有 Python 进程...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Process python,pythonw -ErrorAction SilentlyContinue | Stop-Process -Force"

if errorlevel 1 (
    echo 未发现可停止的 Python 进程，或停止时出现异常。
) else (
    echo 已尝试停止全部 Python / pythonw 进程。
)

echo.
echo 如需重新启动项目，请运行 start.bat
echo.
pause
