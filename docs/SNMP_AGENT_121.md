# 121 独立 SNMP 采集服务

## 目标

将 SNMP 慢轮询从 120 中控主进程迁移到 121 的 `smart-snmp-agent`。121 负责采集、差值计算和内存缓存；120 只定时拉取 121 的 `/status`，继续通过原 `/api/snmp/status` 给前端提供数据。

## 121 服务

- 服务名：`smart-snmp.service`
- 默认监听：`0.0.0.0:6916`
- 健康检查：`http://192.168.50.121:6916/health`
- 状态接口：`http://192.168.50.121:6916/status`
- 配置来源：默认读取 `/srv/smart-center-data/config.json` 里的 `snmp_devices`
- `source_ip`：如果原配置写死了 120 的地址，121 agent 会自动忽略不属于本机的 `source_ip`。如确实需要绑定 121 某个网卡地址，可在 `/etc/smart-snmp-agent.env` 设置 `SMART_SNMP_AGENT_SOURCE_IP=192.168.50.121`。

安装：

```bash
cd /srv/smart-center/current
bash deploy/snmp_agent/install-smart-snmp-agent.sh
```

## 120 启用远程拉取

先确认 121 接口正常：

```bash
curl -fsS http://192.168.50.121:6916/health
curl -fsS http://192.168.50.121:6916/status | python3 -m json.tool | head -80
```

再在 120 的 `/etc/smart-center.env` 增加：

```bash
SMART_CENTER_SNMP_REMOTE_ENABLED=1
SMART_CENTER_SNMP_REMOTE_URL=http://192.168.50.121:6916
SMART_CENTER_SNMP_REMOTE_POLL_SEC=3
SMART_CENTER_SNMP_REMOTE_TIMEOUT_SEC=2.5
SMART_CENTER_SNMP_REMOTE_FAILURE_OFFLINE_AFTER=5
```

重启 120 中控：

```bash
sudo systemctl restart smart-center.service
```

## 前端对接

前端仍调用 120 的原接口：

- `/api/snmp/status?compact=1`
- `/api/snmp/status`

接口结构保持兼容。`templates/index.html` 和 `static/js/views/snmp-summary.js` 不需要改 URL，只需要继续按现有方式渲染。区别是 120 的 `SNMP_STATUS` 数据来自 121 agent 缓存，不再来自 120 本地慢轮询。

## 回滚

关闭远程拉取：

```bash
sudo sed -i 's/^SMART_CENTER_SNMP_REMOTE_ENABLED=.*/SMART_CENTER_SNMP_REMOTE_ENABLED=0/' /etc/smart-center.env
sudo systemctl restart smart-center.service
```

停止 121 agent：

```bash
sudo systemctl disable --now smart-snmp.service
```
