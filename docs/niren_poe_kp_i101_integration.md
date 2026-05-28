# 泥人 POE-KP-I101 继电器接入方案

## 现场设备

截图与实测确认同款设备如下：

| IP | MAC | 当前掌握参数 | 建议接入 |
| --- | --- | --- | --- |
| 192.168.50.35 | 4E:24:04:17:01:42 | TCP Server, 502, Modbus TCP/RTU, 地址 1 | 协议控制 Modbus RTU-over-TCP |
| 192.168.50.52 | 4E:25:03:05:01:86 | TCP Server, 22222, Modbus TCP/RTU, 地址 1 | 协议控制 Modbus RTU-over-TCP |
| 192.168.50.89 | 4E:24:04:17:01:46 | TCP Server, 44489, AT 指令, 地址 1 | 灯光驱动 AT 或协议控制 AT |
| 192.168.50.107 | 4E:24:04:17:02:58 | TCP Server, 502, Modbus TCP/RTU, 地址 1 | 协议控制 Modbus RTU-over-TCP |
| 192.168.50.108 | 4E:24:04:17:01:31 | TCP Server, 502, Modbus TCP/RTU, 地址 1 | 协议控制 Modbus RTU-over-TCP |

## 协议结论

厂家资料确认设备同时支持 AT 指令集和 Modbus 协议。RJ45 数据口在 `Modbus TCP/RTU` 模式下会自动识别标准 Modbus TCP 与 RTU 帧，但 192.168.50.89 联调结果显示实际响应的是 RTU-over-TCP：

- AT 模式：`AT+PROTOCOL=0`
- Modbus TCP/RTU 模式：`AT+PROTOCOL=4`
- TCP Server：`AT+MODEL=0`
- 设备端口：`AT+PORT=?`
- Modbus 地址码：`AT+MBTCPADDR=?`

注意：切到 `AT+PROTOCOL=4` 后，数据口可能不再接受 AT 恢复命令。50.89 本次测试最终已恢复到 `PROTOCOL=0`，后续不要在无人值守时反复切换设备协议。

## 中控落点

长期建议把此类设备放入“协议控制”栏目，而不是残留在旧 `custom_devices`：

1. AT 设备导入内置包 `niren_poe_kp_i101_at`。
2. Modbus 设备导入内置包 `niren_poe_kp_i101_modbus`。
3. 每台设备建立独立 target group，按现场配置填写 `host`、`port`、`unit_id`。
4. 原旧泛型设备若确认是泥人设备，应从 `custom_devices` 删除，避免同一真实设备出现在两个控制入口。

当前 `config.json` 未发现 192.168.50.35/52/89/107/108 的残留配置；现有 `custom_devices` 里只有一个 `192.168.50.254:1882` 的户外灯泛型设备，不能直接按泥人设备删除。

## 已验证

192.168.50.89 AT 模式：

- `AT` 返回 `OK`
- `AT+DEVICEINFO=?` 返回 `UT:POE-KP-I1O1`、`DO:1`、`DI:1`
- `AT+STACH1=?` 返回 DO1 状态
- `AT+OCCH1=?` 返回 DI1 状态
- `AT+STACH1=1` 后读回 DO1=1
- `AT+STACH1=0` 后读回 DO1=0

192.168.50.89 临时切到 Modbus 模式时：

- RTU-over-TCP 读 DO1 成功：`01 01 00 00 00 01 FD CA`
- RTU-over-TCP 读 DI1 成功：`01 02 00 00 00 01 B9 CA`
- 标准 Modbus TCP MBAP 未收到响应

## 实施边界

本轮没有修改 `config.py`、`templates/index.html` 或配置页模板，因为当前全局锁和模板锁被其它任务占用。配置页后续可在锁释放后继续增强：

- 在协议控制导入界面增加泥人设备快捷模板说明。
- 在配置页添加“生成泥人 target group”辅助入口。
- 根据截图批量生成 5 台设备的 target groups。
