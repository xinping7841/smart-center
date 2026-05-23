# Node-RED Current Collector Push

This pack moves the 16-channel current collector polling from node-120 to node-121.

Data flow:

```text
192.168.50.109:502 current collector -> node-121 Node-RED -> node-120 /api/current-collector/push
```

Deploy on node-121:

```bash
python3 deploy_current_collector_flow.py
sudo systemctl restart node-red.service
```

Expected Smart Center config:

```json
{
  "current_collector": {
    "source_mode": "push",
    "transport": "tcp-rtu",
    "host": "192.168.50.109",
    "port": 502,
    "count": 16,
    "scale": 100,
    "push_allowed_hosts": ["192.168.50.121", "100.122.235.56"]
  }
}
```
