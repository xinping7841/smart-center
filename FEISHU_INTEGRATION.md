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
```

Manual one-shot daily push:

```powershell
python run_feishu_bot.py --send-daily-now
```
