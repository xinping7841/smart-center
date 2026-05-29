@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set "PYTHON_CMD="
if exist ".venv64\Scripts\python.exe" set "PYTHON_CMD=.venv64\Scripts\python.exe"
if not defined PYTHON_CMD if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"
if not defined PYTHON_CMD (
    where py >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3.13"
)
if not defined PYTHON_CMD (
    echo [ERROR] No compatible Python runtime was found. Install Python 3.13 x64 or create .venv64.
    pause
    exit /b 1
)
%PYTHON_CMD% run_feishu_bot.py 1>>feishu_bot_stdout.log 2>>feishu_bot_stderr.log
