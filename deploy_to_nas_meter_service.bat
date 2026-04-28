@echo off
setlocal

set SRC=D:\IDE\smart_power_monitor_324 _VS_1\deploy\meter_service_bundle
set BASE=Z:\smart_power_services
set DST=Z:\smart_power_services\meter_service

if not exist "%BASE%" mkdir "%BASE%"
if exist "%DST%" rmdir /s /q "%DST%"

xcopy "%SRC%\*" "%DST%\" /E /I /Y >nul

echo.
echo NAS deploy folder synced:
echo %DST%
echo.
dir "%BASE%"

endlocal
