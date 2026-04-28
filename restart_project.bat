@echo off
chcp 65001 >nul
title Restart Smart Power Monitor

echo ========================================
echo   Restart Smart Power Monitor
echo ========================================
echo.
echo [1/2] Stop previous Python processes...
call "%~dp0stop_current_project.bat" nopause

echo [2/2] Start project...
echo.
call "%~dp0start.bat"
