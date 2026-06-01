# Feishu Integration

This integration runs as a standalone long-connection bot. It does not modify the main Flask startup path.

## Feishu App

Required Feishu app setup:

- Bot capability enabled.
- Event subscription mode set to long connection.
- Event `im.message.receive_v1` subscribed.
- Message receive/send permissions approved and published.

## Local Configuration

Create `.env` in the project root:

```powershell
Copy-Item .env.example .env
notepad .env
```

```env
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=replace_with_rotated_app_secret
FEISHU_DEFAULT_CHAT_ID=
SMART_CENTER_BASE_URL=http://192.168.50.120:6899
FEISHU_PUSH_TIMES=09:00
FEISHU_HTTP_TIMEOUT_SEC=4
FEISHU_NL_MODEL_ENABLED=false
FEISHU_NL_MODEL_URL=http://127.0.0.1:8001/v1
FEISHU_NL_MODEL_NAME=qwen3:14b
FEISHU_NL_MODEL_TIMEOUT_SEC=8
```

`FEISHU_DEFAULT_CHAT_ID` can stay empty for the first run. Start the bot, send a message in the target group, and copy `chat_id=oc_xxx` from the bot log.

## Start

```powershell
cd D:\SmartCenter\smart-center-worktrees\feishu-integration
python run_feishu_bot.py
```

Windows shortcut:

```powershell
.\start_feishu_bot.bat
```

## Test

Before connecting to Feishu, verify local read-only status formatting:

```powershell
python run_feishu_bot.py --print-status
```

Supported chat commands:

```text
状态
日报
查询 电流
哪些设备离线
昨日电量消耗是多少
昨天用了多少电
今日用电
本月用电排行
当前电流
服务器状态
最近自动化日志
最近灯光日志
UPS状态
机房温度
空调状态
代理状态
本地模型状态
```

The bot accepts natural-language read-only questions. It can answer current status,
history, logs, statistics, and diagnostics. Control actions such as switching,
rebooting, issuing commands, changing configuration, or executing scenes are
intentionally refused in Feishu.

## Optional Local Model Intent Parser

If the Smart Center local model service is reachable from the Feishu bot, enable:

```env
FEISHU_NL_MODEL_ENABLED=true
FEISHU_NL_MODEL_URL=http://127.0.0.1:8001/v1
FEISHU_NL_MODEL_NAME=qwen3:14b
```

The model is used to classify the user intent and rewrite fuzzy control text into
a safer standard phrase. It must use an OpenAI-compatible `/v1/chat/completions`
endpoint. Smart Center still routes every proposal through permissions, risk
policy, audit logging, and confirmation before any device command can execute.

If the bot runs on another machine and the local model service only listens on
120 localhost, either run the bot on 120 or expose a protected model proxy URL and set
`FEISHU_NL_MODEL_URL`.

See `docs/QUERY_KNOWLEDGE_BASE.md` for the full query capability map and safety
policy.

Manual one-shot daily push:

```powershell
python run_feishu_bot.py --send-daily-now
```
