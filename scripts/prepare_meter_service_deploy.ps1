$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$sourceMeterService = Join-Path $root 'meter_service'
$sourceModbusCore = Join-Path $root 'modbus_core.py'
$sourceGuide = Join-Path $root '飞牛NAS_电表服务部署说明.md'
$sourceChecklist = Join-Path $root '飞牛NAS_电表服务上线检查清单.md'
$deployRoot = Join-Path $root 'deploy'
$targetRoot = Join-Path $deployRoot 'meter_service_bundle'
$targetMeterService = Join-Path $targetRoot 'meter_service'

if (Test-Path $targetRoot) {
    Remove-Item -Recurse -Force $targetRoot
}

New-Item -ItemType Directory -Path $targetRoot | Out-Null
Copy-Item -Recurse -Force $sourceMeterService $targetMeterService
Copy-Item -Force $sourceModbusCore (Join-Path $targetRoot 'modbus_core.py')
Copy-Item -Force $sourceModbusCore (Join-Path $targetMeterService 'modbus_core.py')

Get-ChildItem -Path $targetRoot -Recurse -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq '__pycache__' } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

if (Test-Path $sourceGuide) {
    Copy-Item -Force $sourceGuide (Join-Path $targetRoot '飞牛NAS_电表服务部署说明.md')
}

if (Test-Path $sourceChecklist) {
    Copy-Item -Force $sourceChecklist (Join-Path $targetRoot '飞牛NAS_电表服务上线检查清单.md')
}

$readme = @"
电表服务 NAS 部署包

目录说明
- meter_service: 独立电表服务目录
- modbus_core.py: 备用 Modbus 核心文件
- 飞牛NAS_电表服务部署说明.md: 部署说明
- 飞牛NAS_电表服务上线检查清单.md: 上线核对清单

建议操作
1. 把整个 meter_service_bundle 复制到飞牛 NAS
2. 进入 meter_service 目录
3. 执行 docker compose up -d --build
4. 浏览器访问 http://NAS_IP:6901/api/health 验证
"@

Set-Content -Path (Join-Path $targetRoot 'README.txt') -Value $readme -Encoding UTF8

Write-Host "部署包已生成: $targetRoot"
