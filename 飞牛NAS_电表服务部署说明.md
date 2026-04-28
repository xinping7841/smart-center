# 飞牛 NAS 电表服务部署说明

## 目标

把电表统计与展示从主中控中拆分出来，单独运行在飞牛 NAS 的 Docker 中，保证 7x24 持续采集。

主中控继续负责：

- 页面展示
- 场景联动
- 读取电表服务数据
- 可选把配置同步给电表服务

电表服务负责：

- 持续轮询电表
- 保存实时状态
- 保存每日历史
- 自动导出 CSV 报表
- 提供统一 API

## 当前目录

独立服务目录：

`meter_service`

关键文件：

- `meter_service/app.py`
- `meter_service/service.py`
- `meter_service/reporting.py`
- `meter_service/storage.py`
- `meter_service/docker-compose.yml`
- `meter_service/Dockerfile`

## 默认端口

电表服务默认端口：

`6901`

## 本地验证地址

- `http://127.0.0.1:6901/api/health`
- `http://127.0.0.1:6901/api/meters?target=total&period=day&days=7`
- `http://127.0.0.1:6901/api/export/meter_summary`
- `http://127.0.0.1:6901/api/export/meter_statistics?period=day`
- `http://127.0.0.1:6901/api/export/meter_raw`

## 飞牛 Docker 部署

### 方式一：直接导入项目目录

把整个项目目录复制到飞牛 NAS，例如：

`/vol1/docker/smart_power_monitor`

进入：

`/vol1/docker/smart_power_monitor/meter_service`

执行：

```bash
docker compose up -d --build
```

### 方式二：在飞牛图形界面创建容器

构建目录：

`meter_service`

Dockerfile：

`meter_service/Dockerfile`

端口映射：

- 容器 `6901`
- 宿主 `6901`

卷映射建议：

- `./meter_service/data` -> `/app/meter_service/data`
- `./meter_service/reports` -> `/data/reports`

## 主中控如何接入

打开主中控的“系统配置 -> 电表中心配置 -> 电表统计总配置”：

- 远程电表服务：启用
- 远程服务地址：`http://NAS_IP:6901`
- 远程超时秒数：`5`
- 保存后同步配置：建议联调通过后再开启

## 自动导出说明

电表服务会按配置自动输出以下文件，方便直接给 WPS 或共享目录读取：

- `latest_summary.csv`
- `latest_daily.csv`
- `latest_weekly.csv`
- `latest_monthly.csv`
- `latest_raw.csv`

同时还会保留按日期归档的历史文件：

- `summary/YYYY-MM-DD.csv`
- `daily/YYYY-MM-DD.csv`
- `weekly/YYYY-Www.csv`
- `monthly/YYYY-MM.csv`
- `raw/YYYY-MM-DD.csv`

## 当前版本说明

### 已支持

- 网络电表 `TCP`
- 网络电表 `RTU_OVER_TCP`
- 主中控远程读取独立电表服务
- 主中控保存配置后同步到电表服务
- 自动导出日报、周报、月报和原始电表 CSV

### 暂未优先处理

- Docker 内本地 `COM` 串口采集
- 单独的电表服务 Web 配置页面
- 微信小程序接入鉴权

## 推荐上线顺序

1. 先在飞牛 NAS 启动电表服务
2. 浏览器验证 `6901/api/health`
3. 在主中控里填写远程服务地址
4. 先只开启“远程电表服务”
5. 确认页面数据正常后，再开启“保存后同步配置”

## 备注

第一版重点是先把电表从主中控主进程里稳定拆出来，后续可以继续补：

- 电表服务独立配置页
- WPS 同步目录对接
- 异常告警和断线重连
- 计算电表和区域电表的进一步独立化
