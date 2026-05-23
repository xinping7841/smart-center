# PJLink 投影机模拟器

这个子项目是一个可运行在 Docker 中的 Python PJLink 投影机模拟器，目标是给联调和自动化测试使用。

它支持：

- 模拟 PJLink TCP 服务端，默认端口 `4352`
- 模拟 3 套可切换设备模板
- 管理接口动态改状态、切换品牌、重置设备
- 覆盖 PJLink Class 1 / Class 2 常用命令
- 兼容无认证、MD5 认证，以及测试兼容用的 `auto` 模式

## 已内置的三套模板

- `epson_1_0`
- `smile_2_0`
- `appotronics_2_0`

三者之间的主要差异已经体现在：

- PJLink Class 等级
- 冻结支持
- 音量支持
- 输入名称支持
- 滤网相关支持
- 序列号/软件版本支持

## 快速启动

### 本机运行

```powershell
cd D:\IDE\smart_power_monitor_324 _VS_1\platform_services\pjlink_simulator
pip install -r requirements.txt
python app.py
```

### Docker 运行

```powershell
cd D:\IDE\smart_power_monitor_324 _VS_1\platform_services\pjlink_simulator
docker compose up -d --build
```

启动后：

- PJLink TCP: `127.0.0.1:4352`
- HTTP 管理接口: `http://127.0.0.1:8080`

## 管理接口

查看当前状态：

```bash
curl http://127.0.0.1:8080/api/v1/state
```

查看模板列表：

```bash
curl http://127.0.0.1:8080/api/v1/profiles
```

切换模板：

```bash
curl -X POST http://127.0.0.1:8080/api/v1/profile/select \
  -H "Content-Type: application/json" \
  -d "{\"profile_id\":\"smile_2_0\"}"
```

修改状态：

```bash
curl -X PUT http://127.0.0.1:8080/api/v1/state \
  -H "Content-Type: application/json" \
  -d "{\"power_state\":\"1\",\"input_code\":\"31\",\"freeze\":true,\"speaker_volume\":60}"
```

直接执行 PJLink 命令：

```bash
curl -X POST http://127.0.0.1:8080/api/v1/command \
  -H "Content-Type: application/json" \
  -d "{\"command\":\"%1POWR ?\"}"
```

查看当前模板命令目录：

```bash
curl http://127.0.0.1:8080/api/v1/commands
```

## 认证模式

`auth_mode` 支持：

- `none`
- `md5`
- `auto`

其中 `auto` 会同时接受 MD5 和 SHA-256 前缀，主要用于兼容测试。

## 持久化

状态保存在：

- `./data/state.json`

## 适合的测试场景

- PJLink 对接联调
- 品牌能力差异回归测试
- 开关机中间态测试
- 无真机环境下接口开发和自动化验证
