# 独立电表服务

这是从现有中控工程中拆分出的电表采集与统计服务，适合部署到飞牛 NAS 的 Docker 中长期运行。

## 当前能力

- 独立轮询网络电表
- 提供 `/api/meters` 给主中控读取展示
- 提供 `/diagnostics` 逐表诊断页面，直接核对每块表的电压 / 电流 / 实时功率 / 电能
- 支持主中控通过 `/api/config/sync` 同步电表配置
- 保存最新状态、每日统计和历史快照到本地 SQLite
- 自动导出日报、周报、月报和原始电表 CSV
- 适合优先接入 `TCP / RTU_OVER_TCP` 电表

## 当前限制

- 第一版暂未启用本地 `COM` 串口采集
- 重点先覆盖电表中心，不包含主中控的其他模块
- 显示清零口径目前沿用现有配置逻辑

## 本地运行

```bash
cd meter_service
python -m pip install -r requirements.txt
cd ..
python -m meter_service.app
```

默认端口：

```text
6901
```

## 主要接口

- `GET /api/health`
- `GET /api/meters?target=total&period=day&days=7`
- `GET /api/diagnostics/meters`
- `GET /diagnostics`
- `POST /api/config/sync`
- `GET /api/export/meter_summary`
- `GET /api/export/meter_statistics?period=day`
- `GET /api/export/meter_raw`

## 自动导出目录

默认导出目录可通过 `meter_statistics.report_dir` 配置。

典型输出文件：

- `latest_summary.csv`
- `latest_daily.csv`
- `latest_weekly.csv`
- `latest_monthly.csv`
- `latest_raw.csv`
- `summary/YYYY-MM-DD.csv`
- `daily/YYYY-MM-DD.csv`
- `weekly/YYYY-Www.csv`
- `monthly/YYYY-MM.csv`
- `raw/YYYY-MM-DD.csv`

## Docker

在 `meter_service` 目录执行：

```bash
docker compose up -d --build
```

## 主中控接入

在主系统配置页的“电表统计总配置”中：

- 开启“远程电表服务”
- 地址填写 `http://NAS_IP:6901`
- 如需保存后自动同步配置，再开启“保存后同步配置”
