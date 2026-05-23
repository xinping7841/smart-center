飞牛 NAS 电表服务打包说明

目录说明
- `meter_service/`：电表采集与统计服务
- `modbus_core.py`：Modbus 通讯核心模块
- `飞牛NAS_电表服务上线检查清单.md`：上线检查清单
- `飞牛NAS_电表服务部署说明.md`：部署说明文档

使用步骤
1. 将整个 `meter_service_bundle` 目录复制到 NAS。
2. 进入 `meter_service` 目录。
3. 执行 `docker compose up -d --build`。
4. 访问 `http://NAS_IP:6901/api/health` 检查服务状态。
