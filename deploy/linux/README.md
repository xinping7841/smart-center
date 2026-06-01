# Ubuntu 部署说明

目录规划：
- 代码目录：`/srv/smart-center/current`
- 数据目录：`/srv/smart-center-data`
- 环境文件：`/etc/smart-center.env`
- systemd 服务：`smart-center.service`

部署流程：
1. 把代码同步到 `/srv/smart-center/releases/<timestamp>`
2. 更新软链 `/srv/smart-center/current`
3. 首次部署执行：

```bash
bash /srv/smart-center/current/deploy/linux/install.sh
```

4. 检查服务：

```bash
systemctl status smart-center
journalctl -u smart-center -n 200 --no-pager
python3 - <<'PY'
import urllib.request
print(urllib.request.urlopen('http://127.0.0.1:6899/api/auth/me').read().decode())
print(urllib.request.urlopen('http://127.0.0.1:6899/config').status)
PY
```

Release 元数据：
- 每个 release 应包含 `REVISION`、`.codex_deploy_ts.txt` 和 `RELEASE_INFO.json`。
- `.codex_deploy_ts.txt` 只记录当前 release 目录名里的时间戳，不要把它作为仓库根文件提交。
- 如果现有 release 的时间戳标记缺失或陈旧，使用 `scripts/remote/stamp_active_release_metadata.sh` 通过脚本上传 runner 修复。

句柄上限与资源检查（建议在更新后执行）：

```bash
systemctl daemon-reload
systemctl restart smart-center vision-door
systemctl show -p LimitNOFILE smart-center vision-door
pid=$(pgrep -f '/srv/smart-center/current/app.py' | head -n1)
cat /proc/$pid/limits | grep "Max open files"
```

数据文件默认位置：
- `/srv/smart-center-data/config.json`
- `/srv/smart-center-data/monitor.db`
- `/srv/smart-center-data/energy_log.json`
- `/srv/smart-center-data/operation_logs.json`
- `/srv/smart-center-data/audit_logs.json`
- `/srv/smart-center-data/runtime/auth_users.json`
- `/srv/smart-center-data/reports/`

备份通知：
- 在 `/etc/smart-center.env` 中增加：

```bash
SMART_CENTER_BACKUP_WEBHOOK=企业微信机器人 webhook
SMART_CENTER_BACKUP_NOTIFY_TITLE=Smart Center 备份通知
SMART_CENTER_BACKUP_KEEP_COUNT=14
SMART_CENTER_BACKUP_NAS_HOST=192.168.50.254
SMART_CENTER_BACKUP_NAS_BASE=/vol2/1000/数据备份/Ubuntu
```

- 不配置 `SMART_CENTER_BACKUP_WEBHOOK` 时，通知功能保持关闭。

恢复保护：
- 执行恢复脚本前，会先自动把当前线上状态快照到：

```bash
/srv/smart-center/backups/pre_restore/<时间戳>/
```

- 其中包含当前代码、数据目录、`smart-center.env` 和 `smart-center.service`。
