# 飞牛 NAS 电表服务上线检查清单

## 一、部署前

- 已确认飞牛 NAS 与各电表网络可互通
- 已确认 NAS 能访问电表所在 VLAN 或已配置静态路由
- 已准备好部署目录 `meter_service_bundle`
- 已准备好主中控当前配置作为同步源

## 二、NAS 部署

1. 将 `meter_service_bundle` 整体复制到飞牛 NAS
2. 进入 `meter_service_bundle/meter_service`
3. 执行：

```bash
docker compose up -d --build
```

4. 检查容器状态：

```bash
docker ps
```

## 三、接口验证

浏览器或命令行访问：

- `http://NAS_IP:6901/api/health`
- `http://NAS_IP:6901/api/meters?target=total&period=day&days=7`
- `http://NAS_IP:6901/api/export/meter_summary`

期望结果：

- `api/health` 返回 `ok: 1`
- `meter_count`、`cabinet_meter_count` 数量正常
- `api/meters` 能返回电表列表与统计数据

## 四、报表验证

检查映射目录中的文件是否生成：

- `latest_summary.csv`
- `latest_daily.csv`
- `latest_weekly.csv`
- `latest_monthly.csv`
- `latest_raw.csv`

同时确认有归档目录：

- `summary`
- `daily`
- `weekly`
- `monthly`
- `raw`

## 五、主中控切换

在主中控配置页：

1. 远程服务地址填写 `http://NAS_IP:6901`
2. 点击“测试远程电表服务”
3. 测试成功后再开启“远程电表服务”
4. 如需后续配置联动，再开启“保存后同步配置”

## 六、上线后观察

- 首页电表中心“数据来源”显示为 `NAS 远程`
- 电表数量、在线数量、实时功率与本地模式基本一致
- 报表持续更新
- 手动物理开关动作后，数据能在轮询周期内变化

## 七、异常排查

- 若 `api/health` 不通：先看容器是否启动、6901 端口是否映射
- 若部分电表离线：检查 NAS 到目标 IP/端口/VLAN 路由
- 若主中控显示 `本地回退`：说明远程服务测试失败，查看主中控配置中的远程地址与超时设置
- 若报表为空：先确认 `api/meters` 是否已返回正常数据
