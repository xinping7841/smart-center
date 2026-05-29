# Node-RED Current Collector Push

This pack moves the 16-channel current collector polling from node-120 to node-121.

Data flow:

```text
192.168.50.109:502 current collector -> node-121 Node-RED -> node-120 /api/current-collector/push
```

Node-RED must be the only live reader for the RTU-over-TCP collector. Other
flows should read `global.current_collector_latest_raw` instead of opening a
second socket to `192.168.50.109:502`, otherwise responses can interleave.

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
    "register": 8192,
    "count": 16,
    "scale": 100,
    "push_allowed_hosts": ["192.168.50.121", "100.122.235.56"]
  }
}
```

`register: 8192` is `0x2000`, the stable full 16-channel current register
block verified on the installed collector. `0x0000` may return sparse frames
where low-current channels are zero.
