@echo off
chcp 65001 >nul
title 部署 Windows 监控代理
set SERVER_HOST=192.168.30.12
set SERVER_PORT=6899
echo.
echo 正在从中控服务器部署 Windows 监控代理...
echo 当前地址: http://%SERVER_HOST%:%SERVER_PORT%
echo 如果后续中控主机 IP 或端口变更，请优先在系统配置页的“服务器节点”中修改 Agent 接入地址。
echo 这个本地批处理也可以手动改 SERVER_HOST / SERVER_PORT。
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex (iwr -UseBasicParsing 'http://%SERVER_HOST%:%SERVER_PORT%/agent.ps1').Content"
echo.
echo 部署命令执行完成。
pause
