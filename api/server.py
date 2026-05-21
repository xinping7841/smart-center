import sqlite3, json, socket, time, subprocess, ipaddress, threading, base64
from datetime import datetime, timedelta
from pathlib import Path
import os
import platform
import shutil
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Blueprint, jsonify, request, Response
from audit import log_audit_event
from auth.decorators import require_permission
from config import CONFIG, SERVER_COMMANDS
from data_logger import add_log
from paths import DB_FILE as DB_FILE_PATH, ensure_parent_dir

bp = Blueprint('server', __name__)
DB_FILE = str(DB_FILE_PATH)
AGENT_VERSION = "2026.05.21.03"
REPORT_MAX_BYTES = 8 * 1024 * 1024
REPORT_MIN_INTERVAL_SEC = 2.0
REPORT_CACHE = {}
REPORT_CACHE_LOCK = threading.Lock()
MACHINES_CACHE = {"expires_at": 0.0, "payload": None}
MACHINES_CACHE_TTL_SEC = 2.5
MACHINE_STATE_LOG_CACHE = {}
PING_CACHE = {}
PING_CACHE_LOCK = threading.Lock()
PING_REFRESH_LOCK = threading.Lock()
PING_REFRESHING_TARGETS = set()
PING_CACHE_TTL_SEC = 8.0
PING_CACHE_STALE_SEC = 20.0
PING_REFRESH_MAX_WORKERS = 24
LOCAL_MONITOR_INTERVAL_SEC = 5.0
LOCAL_MACHINE_STATE_LOCK = threading.Lock()
LOCAL_MACHINE_CPU_SAMPLE = {"total": None, "idle": None}
LOCAL_MACHINE_NET_SAMPLE = {"sent": None, "recv": None, "ts": None}
LOCAL_MACHINE_HW_CACHE = {"expires_at": 0.0, "payload": {}}
LOCAL_MACHINE_GPU_CACHE = {"expires_at": 0.0, "payload": []}
LOCAL_MACHINE_CODEMETER_CACHE = {"expires_at": 0.0, "payload": {}}
LOCAL_MACHINE_MAC = None
DISCOVERY_LOCK = threading.Lock()
DISCOVERY_STATE = {
    "status": "idle",
    "progress": 0,
    "scanned_hosts": 0,
    "total_hosts": 0,
    "alive_count": 0,
    "items": [],
    "count": 0,
    "error": "",
    "started_at": "",
    "finished_at": "",
    "scan_networks": [],
    "warnings": [],
    "workers": 8,
    "stopped": False
}
MAX_HOSTS_PER_NETWORK = 254
MAX_TOTAL_SCAN_HOSTS = 1024

def init_db():
    ensure_parent_dir(DB_FILE_PATH)
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS machines (mac TEXT PRIMARY KEY, hostname TEXT, ip TEXT, last_online TEXT, data TEXT, is_manual INTEGER DEFAULT 0, custom_name TEXT)''')
    for col, defval in [("sort_order","INTEGER DEFAULT 999"), ("remark","TEXT DEFAULT ''"), ("card_size","TEXT DEFAULT 'normal'"), ("asset_group","TEXT DEFAULT ''")]:
        try: c.execute(f"ALTER TABLE machines ADD COLUMN {col} {defval}")
        except: pass
    c.execute('''CREATE TABLE IF NOT EXISTS metrics_history (id INTEGER PRIMARY KEY AUTOINCREMENT, mac TEXT, timestamp TEXT, data TEXT)''')
    conn.commit(); conn.close()

def clean_old_history():
    while True:
        try:
            conn = sqlite3.connect(DB_FILE); c = conn.cursor()
            c.execute("DELETE FROM metrics_history WHERE timestamp < ?", ((datetime.now() - timedelta(hours=1)).isoformat(),))
            conn.commit(); conn.close()
        except: pass
        time.sleep(600)

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close(); return ip
    except: return "127.0.0.1"


def _read_text_file(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return ""


def _read_linux_machine_id():
    for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        value = _read_text_file(candidate)
        if value:
            return value
    return ""


def get_local_machine_mac():
    global LOCAL_MACHINE_MAC
    if LOCAL_MACHINE_MAC:
        return LOCAL_MACHINE_MAC
    machine_id = _read_linux_machine_id()
    if not machine_id:
        machine_id = hashlib.sha1(socket.gethostname().encode("utf-8", errors="ignore")).hexdigest()
    normalized = "".join(ch for ch in str(machine_id).upper() if ch.isalnum())[-12:] or "LOCALHOST"
    LOCAL_MACHINE_MAC = f"LOCAL-{normalized}"
    return LOCAL_MACHINE_MAC


def normalize_machine_mac(raw_mac):
    text = str(raw_mac or "").strip().upper()
    if not text:
        return ""
    for prefix in ("LOCAL-", "TEMP-"):
        if text.startswith(prefix):
            suffix = re.sub(r"[^0-9A-Z]", "", text[len(prefix):]) or "UNKNOWN"
            return f"{prefix}{suffix}"
    compact = re.sub(r"[^0-9A-F]", "", text)
    if len(compact) == 12:
        return "-".join(compact[index:index + 2] for index in range(0, 12, 2))
    return text


def _read_linux_iface_mac(iface):
    name = str(iface or "").strip()
    if not name:
        return ""
    mac = normalize_machine_mac(_read_text_file(f"/sys/class/net/{name}/address"))
    if not mac or mac == "00-00-00-00-00-00":
        return ""
    return mac


def _linux_iface_for_ip(ip_addr):
    target = str(ip_addr or "").strip()
    if not target:
        return ""
    try:
        result = subprocess.run(["ip", "-o", "-4", "addr", "show"], capture_output=True, text=True, timeout=2)
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    for line in result.stdout.splitlines():
        parts = [item for item in line.split() if item]
        if len(parts) < 4:
            continue
        iface = parts[1]
        try:
            inet_index = parts.index("inet")
        except ValueError:
            continue
        cidr = parts[inet_index + 1] if inet_index + 1 < len(parts) else ""
        if cidr.split("/", 1)[0] == target:
            return iface
    return ""


def _linux_network_primary(iface_name, ip_addr):
    iface = str(iface_name or "").strip()
    ip_value = str(ip_addr or "").strip()
    if ip_value:
        ip_iface = _linux_iface_for_ip(ip_value)
        if ip_iface:
            iface = ip_iface
    return {
        "adapter_name": iface,
        "adapter_ip": ip_value,
        "adapter_mac": _read_linux_iface_mac(iface),
        "sample_scope": "default_route_interface",
    }


def _get_machine_ip_for_wol(normalized_mac):
    mac = normalize_machine_mac(normalized_mac)
    if not mac or mac.startswith(("LOCAL-", "TEMP-")):
        return ""
    compact_mac = mac.replace("-", "")
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            "SELECT ip FROM machines WHERE mac=? OR REPLACE(mac, '-', '')=? LIMIT 1",
            (mac, compact_mac),
        )
        row = c.fetchone()
        return str(row[0] or "").strip() if row else ""
    except Exception as exc:
        add_log(-1, f"[服务器] 查询WOL目标IP失败: {mac} {exc}")
        return ""
    finally:
        if conn is not None:
            conn.close()


def _get_machine_mac_by_ip(ip):
    ip_text = str(ip or "").strip()
    if not ip_text:
        return ""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            "SELECT mac FROM machines WHERE ip=? AND mac NOT LIKE 'TEMP-%' ORDER BY last_online DESC LIMIT 1",
            (ip_text,),
        )
        row = c.fetchone()
        return normalize_machine_mac(row[0]) if row else ""
    except Exception as exc:
        add_log(-1, f"[服务器] 按IP反查机器MAC失败: {ip_text} {exc}")
        return ""
    finally:
        if conn is not None:
            conn.close()


def _get_recent_machine_mac_by_remote_addr(remote_addr):
    ip_text = str(remote_addr or "").strip()
    if not ip_text:
        return ""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            """
            SELECT mac FROM machines
            WHERE ip=? AND mac NOT LIKE 'TEMP-%'
            ORDER BY last_online DESC
            LIMIT 1
            """,
            (ip_text,),
        )
        row = c.fetchone()
        return normalize_machine_mac(row[0]) if row else ""
    except Exception as exc:
        add_log(-1, f"[服务器] 按远端IP兜底反查机器MAC失败: {ip_text} {exc}")
        return ""
    finally:
        if conn is not None:
            conn.close()


def _get_machine_mac_by_hostname_or_name(hostname):
    host_text = str(hostname or "").strip()
    if not host_text:
        return ""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            """
            SELECT mac FROM machines
            WHERE (hostname=? OR custom_name=?) AND mac NOT LIKE 'TEMP-%'
            ORDER BY last_online DESC
            LIMIT 1
            """,
            (host_text, host_text),
        )
        row = c.fetchone()
        return normalize_machine_mac(row[0]) if row else ""
    except Exception as exc:
        add_log(-1, f"[服务器] 按主机名兜底反查机器MAC失败: {host_text} {exc}")
        return ""
    finally:
        if conn is not None:
            conn.close()


def _get_machine_mac_by_legacy_report(report_ip="", remote_addr="", hostname="", raw_mac=""):
    """Recover old agents whose MAC formatter produced an invalid value."""
    candidates = []
    for value in (report_ip, remote_addr):
        value = str(value or "").strip()
        if value and value not in candidates:
            candidates.append(("ip", value))
    host_text = str(hostname or "").strip()
    if host_text:
        candidates.append(("hostname", host_text))
    raw_text = str(raw_mac or "").strip().upper()
    raw_hex = re.sub(r"[^0-9A-F]", "", raw_text)
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        for field, value in candidates:
            if field == "ip":
                c.execute(
                    """
                    SELECT mac FROM machines
                    WHERE ip=? AND mac NOT LIKE 'TEMP-%'
                    ORDER BY last_online DESC
                    LIMIT 1
                    """,
                    (value,),
                )
            else:
                c.execute(
                    """
                    SELECT mac FROM machines
                    WHERE (hostname=? OR custom_name=?) AND mac NOT LIKE 'TEMP-%'
                    ORDER BY last_online DESC
                    LIMIT 1
                    """,
                    (value, value),
                )
            row = c.fetchone()
            if row:
                return normalize_machine_mac(row[0])
        if raw_hex and len(raw_hex) >= 8:
            c.execute("SELECT mac FROM machines WHERE mac NOT LIKE 'TEMP-%'")
            scored = []
            for (stored_mac,) in c.fetchall():
                stored_compact = re.sub(r"[^0-9A-F]", "", str(stored_mac or "").upper())
                if not stored_compact:
                    continue
                common = sum(1 for item in (raw_hex[:4], raw_hex[-4:]) if item and item in stored_compact)
                if common >= 1:
                    scored.append((common, stored_mac))
            if len(scored) == 1 or (scored and scored[0][0] > scored[1][0]):
                scored.sort(reverse=True)
                return normalize_machine_mac(scored[0][1])
    except Exception as exc:
        add_log(-1, f"[服务器] 旧Agent畸形MAC兜底匹配失败: remote={remote_addr} ip={report_ip} host={hostname} mac={raw_mac} {exc}")
    finally:
        if conn is not None:
            conn.close()
    return ""


def _list_local_ipv4_broadcasts():
    targets = []
    try:
        output = subprocess.check_output(
            ["ip", "-o", "-4", "addr", "show"],
            text=True,
            timeout=2,
            stderr=subprocess.DEVNULL,
        )
        for line in output.splitlines():
            parts = line.split()
            if "inet" not in parts:
                continue
            cidr = parts[parts.index("inet") + 1]
            address = ipaddress.ip_interface(cidr)
            if address.ip.is_loopback:
                continue
            targets.append(str(address.network.broadcast_address))
    except Exception:
        pass
    return targets


def _ipv4_network24(ip_text):
    try:
        address = ipaddress.ip_address(str(ip_text or "").strip())
        if address.version != 4 or address.is_loopback:
            return None
        return ipaddress.ip_network(f"{address}/24", strict=False)
    except Exception:
        return None


def _parse_machine_data_json(raw_value):
    try:
        parsed = json.loads(raw_value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _online_window_for_machine_data(status_data):
    offline_window_sec = 180
    agent_status = status_data.get("agent", {}) if isinstance(status_data, dict) else {}
    try:
        report_interval = int(agent_status.get("report_interval_sec") or 0)
        if report_interval > 0:
            offline_window_sec = max(180, int(report_interval * 2 + 30))
    except Exception:
        pass
    return offline_window_sec


def _is_machine_recently_online(last_online, status_data):
    reference_at = status_data.get("server_received_at") if isinstance(status_data, dict) else ""
    parsed = _parse_machine_timestamp(reference_at or last_online)
    if not parsed:
        return False
    return (datetime.now() - parsed).total_seconds() < _online_window_for_machine_data(status_data)


def _find_wol_relay_candidates(target_mac, target_ip):
    target_network = _ipv4_network24(target_ip)
    if target_network is None:
        return []
    excluded_mac = normalize_machine_mac(target_mac)
    candidates = []
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT mac, hostname, custom_name, ip, last_online, data FROM machines")
        for row in c.fetchall():
            relay_mac = normalize_machine_mac(row[0])
            relay_ip = str(row[3] or "").strip()
            if not relay_mac or relay_mac == excluded_mac or relay_mac.startswith(("LOCAL-", "TEMP-")):
                continue
            relay_network = _ipv4_network24(relay_ip)
            if relay_network != target_network:
                continue
            status_data = _parse_machine_data_json(row[5])
            if not _is_machine_recently_online(row[4], status_data):
                continue
            agent = status_data.get("agent", {}) if isinstance(status_data, dict) else {}
            candidates.append({
                "mac": relay_mac,
                "ip": relay_ip,
                "name": row[2] or row[1] or relay_mac,
                "agent_version": str(agent.get("version") or ""),
                "last_online": row[4] or "",
            })
    except Exception as exc:
        add_log(-1, f"[服务器] 查询WOL中继候选失败: {exc}")
    finally:
        if conn is not None:
            conn.close()
    candidates.sort(key=lambda item: item.get("last_online") or "", reverse=True)
    return candidates


def _wol_broadcast_targets(target_ip):
    targets = ["255.255.255.255"]
    ip_text = str(target_ip or "").strip()
    try:
        address = ipaddress.ip_address(ip_text)
        if address.version == 4 and not address.is_loopback:
            # Most managed VLANs here are /24. Directed broadcast gives WOL a
            # chance to cross VLANs when the gateway allows it.
            targets.append(str(ipaddress.ip_network(f"{address}/24", strict=False).broadcast_address))
    except Exception:
        pass
    targets.extend(_list_local_ipv4_broadcasts())
    for fallback in ("192.168.50.255", "192.168.40.255", "192.168.19.255"):
        targets.append(fallback)
    unique_targets = []
    for target in targets:
        if target and target not in unique_targets:
            unique_targets.append(target)
    return unique_targets


def _parse_machine_timestamp(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _format_machine_timestamp(value):
    parsed = _parse_machine_timestamp(value)
    if parsed:
        return parsed.isoformat()
    return str(value or "").strip()


def _annotate_report_timing(status_payload, client_reported_at, server_received_at):
    payload = dict(status_payload or {})
    server_iso = _format_machine_timestamp(server_received_at) or datetime.now().isoformat()
    client_iso = _format_machine_timestamp(
        payload.get("report_generated_at")
        or payload.get("client_reported_at")
        or client_reported_at
    )
    payload["server_received_at"] = server_iso
    if client_iso:
        payload["client_reported_at"] = client_iso
    client_dt = _parse_machine_timestamp(client_iso)
    server_dt = _parse_machine_timestamp(server_iso)
    if client_dt and server_dt:
        payload["clock_offset_sec"] = round((client_dt - server_dt).total_seconds(), 1)
    return payload


def _payload_is_agent_heartbeat(payload):
    payload = payload if isinstance(payload, dict) else {}
    agent = payload.get("agent") if isinstance(payload.get("agent"), dict) else {}
    return bool(agent.get("heartbeat"))


def _payload_is_bootstrap(payload):
    payload = payload if isinstance(payload, dict) else {}
    agent = payload.get("agent") if isinstance(payload.get("agent"), dict) else {}
    return bool(agent.get("bootstrap")) and not _payload_has_runtime_metrics(payload)


def _parse_machine_payload(payload_text):
    try:
        return json.loads(payload_text) if payload_text else {}
    except Exception:
        return {}


def _decode_json_report_body(raw_bytes):
    if not raw_bytes:
        return None, "empty"
    last_error = ""
    last_context = ""
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "gb18030"):
        try:
            text = raw_bytes.decode(encoding)
        except Exception as exc:
            last_error = f"{encoding}:decode:{exc}"
            continue
        text = text.strip("\ufeff\x00\r\n\t ")
        if not text:
            continue
        candidates = [text]
        starts = [pos for pos in (text.find("{"), text.find("[")) if pos >= 0]
        ends = [pos for pos in (text.rfind("}"), text.rfind("]")) if pos >= 0]
        if starts and ends and min(starts) <= max(ends):
            candidates.append(text[min(starts):max(ends) + 1])
        for candidate in candidates:
            try:
                return json.loads(candidate), ""
            except Exception as exc:
                last_error = f"{encoding}:json:{exc}"
                pos = getattr(exc, "pos", None)
                if isinstance(pos, int):
                    start = max(0, pos - 180)
                    end = min(len(candidate), pos + 180)
                    context = candidate[start:end]
                    context = context.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
                    last_context = context[:420]
    if last_context:
        return None, f"{last_error or 'unknown_parse_error'} context={last_context}"
    return None, last_error or "unknown_parse_error"


def _load_report_json_payload():
    parsed = request.get_json(silent=True)
    if parsed not in (None, ""):
        return parsed, ""
    raw = request.get_data(cache=True) or b""
    parsed, error = _decode_json_report_body(raw)
    return (parsed if parsed is not None else {}), error


def _is_virtual_gpu_name(name):
    text = str(name or "").lower()
    return any(
        marker in text
        for marker in (
            "gameviewer",
            "oray",
            "virtual display",
            "idddriver",
            "remote display",
        )
    )


def _compact_gpu_name(name):
    text = str(name or "GPU").strip()
    text = re.sub(r"^VGA compatible controller:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^3D controller:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^Display controller:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"Advanced Micro Devices,\s*Inc\.\s*", "AMD ", text, flags=re.IGNORECASE)
    text = re.sub(r"\[AMD/ATI\]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^NVIDIA\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^Intel\(R\)\s+", "Intel ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+\(rev\s+[0-9a-f]+\)$", "", text, flags=re.IGNORECASE)
    return text.strip()


def _normalize_gpu_identity(name):
    return re.sub(r"[^a-z0-9]+", "", _compact_gpu_name(name).lower())


def _gpu_row_score(row):
    row = row if isinstance(row, dict) else {}
    score = 0
    try:
        if float(row.get("temp") or 0) > 0:
            score += 100
    except Exception:
        pass
    if "nvidia" in str(row.get("source") or "").lower():
        score += 10
    try:
        if float(row.get("util_percent") or 0) > 0:
            score += 1
    except Exception:
        pass
    return score


def _gpu_row_has_metrics(row):
    row = row if isinstance(row, dict) else {}
    for key in ("temp", "util_percent", "fan_rpm", "power"):
        try:
            if float(row.get(key) or 0) > 0:
                return True
        except Exception:
            continue
    return False


def _gpu_vendor_group(row):
    row = row if isinstance(row, dict) else {}
    text = f"{row.get('name') or ''} {row.get('source') or ''}".lower()
    if any(marker in text for marker in ("nvidia", "geforce", "quadro", "rtx", "gtx")):
        return "nvidia"
    if any(marker in text for marker in ("amd", "radeon")):
        return "amd"
    if "intel" in text:
        return "intel"
    if _gpu_row_has_metrics(row):
        return f"metric-{row.get('source') or row.get('index') or 'gpu'}"
    return ""


def _sanitize_gpu_list(gpu_list):
    if isinstance(gpu_list, dict):
        gpu_list = [gpu_list]
    if not isinstance(gpu_list, list):
        return []
    best_by_key = {}
    order = []
    for idx, item in enumerate(gpu_list):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if _is_virtual_gpu_name(name):
            continue
        identity = _normalize_gpu_identity(name) or _gpu_vendor_group(item) or f"gpu-{idx}"
        score = _gpu_row_score(item)
        previous = best_by_key.get(identity)
        if not previous:
            best_by_key[identity] = {"item": item, "score": score, "order": idx}
            order.append(identity)
            continue
        if score > previous["score"]:
            best_by_key[identity] = {"item": item, "score": score, "order": previous["order"]}
    rows = [best_by_key[key]["item"] for key in order if key in best_by_key]
    if not any(_gpu_row_has_metrics(row) for row in rows):
        metric_rows = [
            item for item in gpu_list
            if isinstance(item, dict)
            and not _is_virtual_gpu_name(item.get("name"))
            and _gpu_row_has_metrics(item)
        ]
        for item in metric_rows:
            if item not in rows:
                rows.append(item)
    return rows


def _sanitize_machine_payload(payload):
    payload = payload if isinstance(payload, dict) else {}
    if "gpu_list" not in payload:
        return payload
    cleaned = dict(payload)
    cleaned["gpu_list"] = _sanitize_gpu_list(payload.get("gpu_list"))
    return cleaned


def _valid_ping_target(ip):
    text = str(ip or "").strip()
    if not text:
        return ""
    try:
        addr = ipaddress.ip_address(text)
        if addr.is_loopback or addr.is_unspecified or addr.is_multicast:
            return ""
        return text
    except Exception:
        return ""


def _ping_command(ip):
    if platform.system().lower().startswith("win"):
        return ["ping", "-n", "1", "-w", "800", ip]
    return ["ping", "-c", "1", "-W", "1", ip]


def _cached_ping_host(ip):
    target = _valid_ping_target(ip)
    if not target:
        return None
    now_ts = time.time()
    with PING_CACHE_LOCK:
        cached = PING_CACHE.get(target)
        if cached and now_ts - float(cached.get("ts") or 0.0) < PING_CACHE_TTL_SEC:
            return bool(cached.get("online"))
    online = ping_host(target)
    with PING_CACHE_LOCK:
        PING_CACHE[target] = {"ts": now_ts, "online": bool(online)}
    return bool(online)


def _get_ping_cache_entry(target, now_ts=None):
    now_ts = time.time() if now_ts is None else now_ts
    with PING_CACHE_LOCK:
        cached = PING_CACHE.get(target)
        if not cached:
            return None
        age = max(0.0, now_ts - float(cached.get("ts") or 0.0))
        return {
            "online": bool(cached.get("online")),
            "ts": float(cached.get("ts") or 0.0),
            "age_sec": age,
            "fresh": age < PING_CACHE_TTL_SEC,
            "stale": age >= PING_CACHE_TTL_SEC,
        }


def _refresh_ping_targets_async(targets):
    unique_targets = []
    seen = set()
    for ip in targets:
        target = _valid_ping_target(ip)
        if target and target not in seen:
            unique_targets.append(target)
            seen.add(target)
    if not unique_targets:
        return
    with PING_REFRESH_LOCK:
        pending = [target for target in unique_targets if target not in PING_REFRESHING_TARGETS]
        if not pending:
            return
        PING_REFRESHING_TARGETS.update(pending)

    def _worker(target_list):
        try:
            max_workers = min(PING_REFRESH_MAX_WORKERS, max(1, len(target_list)))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {executor.submit(ping_host, target): target for target in target_list}
                for future in as_completed(future_map):
                    target = future_map[future]
                    try:
                        online = bool(future.result())
                    except Exception:
                        online = False
                    with PING_CACHE_LOCK:
                        PING_CACHE[target] = {"ts": time.time(), "online": online}
        finally:
            with PING_REFRESH_LOCK:
                for target in target_list:
                    PING_REFRESHING_TARGETS.discard(target)

    threading.Thread(target=_worker, args=(pending,), name="server-ping-refresh", daemon=True).start()


def _resolve_ping_states(targets):
    unique_targets = []
    seen = set()
    for ip in targets:
        target = _valid_ping_target(ip)
        if target and target not in seen:
            unique_targets.append(target)
            seen.add(target)
    if not unique_targets:
        return {}
    results = {}
    now_ts = time.time()
    pending = []
    with PING_CACHE_LOCK:
        for target in unique_targets:
            cached = PING_CACHE.get(target)
            if cached and now_ts - float(cached.get("ts") or 0.0) < PING_CACHE_TTL_SEC:
                results[target] = bool(cached.get("online"))
            else:
                pending.append(target)
    if pending:
        max_workers = min(12, len(pending))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(ping_host, target): target for target in pending}
            for future in as_completed(future_map):
                target = future_map[future]
                try:
                    online = bool(future.result())
                except Exception:
                    online = False
                results[target] = online
                with PING_CACHE_LOCK:
                    PING_CACHE[target] = {"ts": time.time(), "online": online}
    return results


def _resolve_ping_states_cached(targets):
    unique_targets = []
    seen = set()
    for ip in targets:
        target = _valid_ping_target(ip)
        if target and target not in seen:
            unique_targets.append(target)
            seen.add(target)
    if not unique_targets:
        return {}, {}

    now_ts = time.time()
    results = {}
    meta = {}
    refresh_targets = []
    for target in unique_targets:
        cached = _get_ping_cache_entry(target, now_ts)
        if cached is None:
            meta[target] = {"state": "pending", "age_sec": None, "refreshing": True}
            refresh_targets.append(target)
            continue
        if cached["age_sec"] < PING_CACHE_STALE_SEC:
            results[target] = cached["online"]
            meta[target] = {
                "state": "fresh" if cached["fresh"] else "stale",
                "age_sec": round(cached["age_sec"], 1),
                "refreshing": cached["stale"],
            }
            if cached["stale"]:
                refresh_targets.append(target)
        else:
            meta[target] = {"state": "pending", "age_sec": round(cached["age_sec"], 1), "refreshing": True}
            refresh_targets.append(target)
    _refresh_ping_targets_async(refresh_targets)
    return results, meta


def _machine_command_keys(mac):
    keys = []
    raw_key = str(mac or "").strip().upper()
    normalized_key = normalize_machine_mac(raw_key)
    for item in (normalized_key, raw_key):
        if item and item not in keys:
            keys.append(item)
    return keys


def _compare_version_text(left, right):
    def parts(value):
        return [int(item) for item in re.split(r"[^0-9]+", str(value or "")) if item != ""]

    left_parts = parts(left)
    right_parts = parts(right)
    max_len = max(len(left_parts), len(right_parts))
    for index in range(max_len):
        left_value = left_parts[index] if index < len(left_parts) else 0
        right_value = right_parts[index] if index < len(right_parts) else 0
        if left_value > right_value:
            return 1
        if left_value < right_value:
            return -1
    return 0


def _is_agent_version_outdated(agent_version, latest_version=AGENT_VERSION):
    current = str(agent_version or "").strip()
    latest = str(latest_version or "").strip()
    if not current or not latest:
        return False
    return _compare_version_text(current, latest) < 0


def _command_min_agent_version(command):
    if isinstance(command, dict):
        return str(command.get("min_agent_version") or "").strip()
    return ""


def _pop_machine_command(mac, agent_version=""):
    for key in _machine_command_keys(mac):
        if key in SERVER_COMMANDS:
            command = SERVER_COMMANDS.get(key)
            min_version = _command_min_agent_version(command)
            if min_version and _compare_version_text(agent_version, min_version) < 0:
                return None
            return SERVER_COMMANDS.pop(key, None)
    return None


def _set_machine_command(mac, command):
    key = normalize_machine_mac(mac) or str(mac or "").strip().upper()
    if key:
        SERVER_COMMANDS[key] = command

def get_agent_server_host():
    server_cfg = CONFIG.get("server_monitor", {}) if isinstance(CONFIG, dict) else {}
    configured_host = str(server_cfg.get("agent_host", "") or "").strip()
    return configured_host or get_local_ip()

def get_agent_server_port():
    server_cfg = CONFIG.get("server_monitor", {}) if isinstance(CONFIG, dict) else {}
    try:
        return int(server_cfg.get("agent_port", 6899) or 6899)
    except Exception:
        return 6899

def get_agent_candidate_hosts(request_host=None):
    hosts = []
    configured_host = str(CONFIG.get("server_monitor", {}).get("agent_host", "") or "").strip()
    if configured_host:
        hosts.append(configured_host)
    if request_host:
        hosts.append(str(request_host).strip())
    local_ip = get_local_ip()
    if local_ip and local_ip != "127.0.0.1":
        hosts.append(local_ip)
    for host_name in [socket.gethostname(), socket.getfqdn()]:
        host_name = str(host_name or "").strip()
        if host_name and host_name not in ["localhost", "127.0.0.1"]:
            hosts.append(host_name)
    unique_hosts = []
    seen = set()
    for host in hosts:
        if host and host not in seen:
            unique_hosts.append(host)
            seen.add(host)
    return unique_hosts

def build_agent_runtime_config(server_host=None):
    chosen_host = str(server_host or get_agent_server_host() or "").strip()
    port = get_agent_server_port()
    return {
        "service": "smart_center_agent",
        "version": AGENT_VERSION,
        "server_host": chosen_host,
        "server_port": port,
        "report_path": "/report",
        "config_path": "/agent/config",
        "worker_path": "/agent/worker.json",
        "launcher_path": "/agent/launcher.json",
        "linux_worker_path": "/agent/linux.py",
        "linux_service_name": "smart-center-agent.service",
        "report_interval_sec": 60,
        "sync_interval_sec": 60,
        "discovery_retry_sec": 120,
        "ntp_enabled": True,
        "ntp_primary": "192.168.50.120",
        "ntp_fallback": "192.168.50.121",
        "ntp_check_interval_sec": 3600,
        "candidate_hosts": get_agent_candidate_hosts(chosen_host),
        "scan_networks": get_scan_networks(),
        "updated_at": datetime.now().isoformat()
    }


def _read_linux_cpu_percent():
    lines = _read_text_file("/proc/stat").splitlines()
    if not lines:
        return 0.0
    parts = [item for item in lines[0].split() if item]
    if len(parts) < 5 or parts[0] != "cpu":
        return 0.0
    values = []
    for raw in parts[1:]:
        try:
            values.append(int(raw))
        except Exception:
            values.append(0)
    total = sum(values)
    idle = (values[3] if len(values) > 3 else 0) + (values[4] if len(values) > 4 else 0)
    with LOCAL_MACHINE_STATE_LOCK:
        prev_total = LOCAL_MACHINE_CPU_SAMPLE["total"]
        prev_idle = LOCAL_MACHINE_CPU_SAMPLE["idle"]
        LOCAL_MACHINE_CPU_SAMPLE["total"] = total
        LOCAL_MACHINE_CPU_SAMPLE["idle"] = idle
    if prev_total is None or prev_idle is None:
        return 0.0
    delta_total = total - prev_total
    delta_idle = idle - prev_idle
    if delta_total <= 0:
        return 0.0
    busy = max(0.0, float(delta_total - delta_idle))
    return round(max(0.0, min(100.0, (busy / float(delta_total)) * 100.0)), 1)


def _read_linux_meminfo():
    data = {}
    for line in _read_text_file("/proc/meminfo").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        number = str(value).strip().split()[0] if str(value).strip() else "0"
        try:
            data[key.strip()] = int(number) * 1024
        except Exception:
            data[key.strip()] = 0
    total = int(data.get("MemTotal", 0) or 0)
    available = int(data.get("MemAvailable", 0) or 0)
    if not available:
        available = int(data.get("MemFree", 0) or 0) + int(data.get("Buffers", 0) or 0) + int(data.get("Cached", 0) or 0)
    used = max(0, total - available)
    percent = (used / total * 100.0) if total else 0.0
    return {"total": total, "used": used, "percent": round(percent, 1)}


def _read_linux_net_rates():
    default_iface = ""
    for line in _read_text_file("/proc/net/route").splitlines()[1:]:
        parts = [item for item in line.split() if item]
        if len(parts) >= 2 and parts[1] == "00000000":
            default_iface = parts[0]
            break
    rows = []
    for line in _read_text_file("/proc/net/dev").splitlines()[2:]:
        if ":" not in line:
            continue
        name, values = line.split(":", 1)
        iface = name.strip()
        if iface == "lo" or re.match(r"^(docker|veth|br-|virbr|tun|tap|wg|tailscale)", iface):
            continue
        parts = [item for item in values.strip().split() if item]
        if len(parts) < 16:
            continue
        try:
            rows.append({"iface": iface, "recv": int(parts[0]), "sent": int(parts[8])})
        except Exception:
            continue
    selected = None
    if default_iface:
        selected = next((row for row in rows if row["iface"] == default_iface), None)
    if selected is None and rows:
        selected = rows[0]
    recv_total = int(selected["recv"]) if selected else 0
    sent_total = int(selected["sent"]) if selected else 0
    iface_name = selected["iface"] if selected else (default_iface or "")
    network_primary = _linux_network_primary(iface_name, get_local_ip())
    now_ts = time.time()
    with LOCAL_MACHINE_STATE_LOCK:
        prev_sent = LOCAL_MACHINE_NET_SAMPLE["sent"]
        prev_recv = LOCAL_MACHINE_NET_SAMPLE["recv"]
        prev_ts = LOCAL_MACHINE_NET_SAMPLE["ts"]
        prev_iface = LOCAL_MACHINE_NET_SAMPLE.get("iface")
        LOCAL_MACHINE_NET_SAMPLE.update({"sent": sent_total, "recv": recv_total, "ts": now_ts, "iface": iface_name})
    if prev_sent is None or prev_recv is None or prev_ts is None:
        return {"sent_kb_s": 0.0, "recv_kb_s": 0.0, "network_primary": network_primary}
    delta_ts = max(0.001, now_ts - float(prev_ts))
    if prev_iface and prev_iface != iface_name:
        sent_kb_s = 0.0
        recv_kb_s = 0.0
    else:
        sent_kb_s = max(0.0, (sent_total - int(prev_sent)) / 1024.0 / delta_ts)
        recv_kb_s = max(0.0, (recv_total - int(prev_recv)) / 1024.0 / delta_ts)
    return {"sent_kb_s": round(sent_kb_s, 1), "recv_kb_s": round(recv_kb_s, 1), "network_primary": network_primary}


def _read_linux_gpu_snapshot():
    now_ts = time.time()
    with LOCAL_MACHINE_STATE_LOCK:
        cached = LOCAL_MACHINE_GPU_CACHE["payload"]
        expires_at = float(LOCAL_MACHINE_GPU_CACHE["expires_at"] or 0.0)
    if cached and now_ts < expires_at:
        return cached
    gpu_list = []
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            encoding="utf-8",
            errors="ignore",
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = [item.strip() for item in line.split(",")]
                if len(parts) < 4:
                    continue
                try:
                    gpu_list.append({
                        "index": int(parts[0]),
                        "name": parts[1],
                        "util_percent": int(float(parts[2] or 0)),
                        "temp": int(float(parts[3] or 0)),
                    })
                except Exception:
                    continue
    except Exception:
        gpu_list = []
    if not gpu_list:
        try:
            for card_path in sorted(Path("/sys/class/drm").glob("card[0-9]")):
                device_path = card_path / "device"
                if not device_path.is_dir():
                    continue
                vendor_id = _read_text_file(device_path / "vendor").lower()
                if vendor_id not in ("0x1002", "0x8086"):
                    continue
                name = "AMD GPU" if vendor_id == "0x1002" else "Intel GPU"
                util = 0
                busy_text = _read_text_file(device_path / "gpu_busy_percent")
                try:
                    util = max(0, min(100, int(float(busy_text))))
                except Exception:
                    util = 0
                temp = 0
                for temp_path in sorted(device_path.glob("hwmon/hwmon*/temp*_input")):
                    try:
                        candidate = int(float(_read_text_file(temp_path))) // 1000
                    except Exception:
                        continue
                    if 0 < candidate < 150:
                        temp = candidate
                        break
                source = "amdgpu-hwmon" if vendor_id == "0x1002" else "drm-sysfs"
                gpu_list.append({
                    "index": len(gpu_list),
                    "name": name,
                    "util_percent": util,
                    "temp": temp,
                    "source": source,
                })
        except Exception:
            pass
    with LOCAL_MACHINE_STATE_LOCK:
        LOCAL_MACHINE_GPU_CACHE["payload"] = gpu_list
        LOCAL_MACHINE_GPU_CACHE["expires_at"] = now_ts + 30.0
    return gpu_list


def _parse_linux_memory_speed(raw_text):
    text = str(raw_text or "").strip()
    if not text:
        return None
    match = re.search(r"(\d+)\s*(?:MT/s|MHz)?", text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        value = int(match.group(1))
    except Exception:
        return None
    if value <= 0:
        return None
    return value


def _read_linux_memory_speed():
    # 1) Fast path: sysfs if any platform exposes it
    sysfs_candidates = (
        "/sys/devices/system/edac/mc/mc0/dimm0/dimm_speed",
        "/sys/devices/system/memory/memory0/speed",
    )
    for candidate in sysfs_candidates:
        value = _parse_linux_memory_speed(_read_text_file(candidate))
        if value:
            return value

    # 2) dmidecode (available on Ubuntu host)
    try:
        result = subprocess.run(
            ["dmidecode", "-t", "memory"],
            capture_output=True,
            text=True,
            timeout=3,
            encoding="utf-8",
            errors="ignore",
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line_text = line.strip()
                if not line_text:
                    continue
                if not (
                    line_text.lower().startswith("configured memory speed:")
                    or line_text.lower().startswith("speed:")
                ):
                    continue
                if "unknown" in line_text.lower():
                    continue
                value = _parse_linux_memory_speed(line_text)
                if value:
                    return value
    except Exception:
        pass

    # 3) lshw fallback
    try:
        result = subprocess.run(
            ["lshw", "-class", "memory"],
            capture_output=True,
            text=True,
            timeout=3,
            encoding="utf-8",
            errors="ignore",
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line_text = line.strip()
                if not line_text or not line_text.lower().startswith("clock:"):
                    continue
                value = _parse_linux_memory_speed(line_text)
                if value:
                    return value
    except Exception:
        pass

    return None


def _linux_command_output(command, timeout=3):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="ignore",
        )
        if result.returncode == 0:
            return result.stdout or ""
    except Exception:
        pass
    return ""


def _read_linux_os_info():
    values = {}
    for line in _read_text_file("/etc/os-release").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"')
    return {
        "name": values.get("PRETTY_NAME") or platform.platform(),
        "id": values.get("ID") or "",
        "version": values.get("VERSION_ID") or "",
        "codename": values.get("VERSION_CODENAME") or values.get("UBUNTU_CODENAME") or "",
        "kernel": platform.release(),
        "arch": platform.machine(),
    }


def _parse_linux_size_bytes(text):
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMGTPE]?B)", str(text or ""), flags=re.IGNORECASE)
    if not match:
        return 0
    unit = match.group(2).upper()
    scale = {"KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4, "PB": 1024 ** 5}.get(unit, 1)
    try:
        return int(float(match.group(1)) * scale)
    except Exception:
        return 0


def _read_linux_memory_topology():
    text = _linux_command_output(["dmidecode", "-t", "memory"], timeout=4)
    modules = []
    current = None
    for line in text.splitlines():
        if line and not line.startswith("\t") and line.strip() == "Memory Device":
            if current:
                modules.append(current)
            current = {}
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.strip().split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "size":
            current["size"] = value
            current["size_bytes"] = _parse_linux_size_bytes(value)
        elif key in ("locator", "bank locator", "manufacturer", "part number", "speed", "configured memory speed"):
            current[key.replace(" ", "_")] = value
    if current:
        modules.append(current)
    installed = [
        item for item in modules
        if item.get("size_bytes", 0) > 0 and "no module" not in str(item.get("size", "")).lower()
    ]
    channels = []
    for item in installed:
        label = " ".join([str(item.get("locator") or ""), str(item.get("bank_locator") or "")])
        match = re.search(r"channel\s*([a-z0-9]+)", label, flags=re.IGNORECASE) or re.search(r"channel([a-z])", label, flags=re.IGNORECASE)
        if match:
            channel = match.group(1).upper()
            if channel and channel not in channels:
                channels.append(channel)
    channel_count = len(channels)
    if channel_count >= 2:
        mode = "dual"
    elif channel_count == 1 and installed:
        mode = "single"
    else:
        mode = "unknown"
    total_bytes = sum(int(item.get("size_bytes") or 0) for item in installed)
    summary_bits = [f"{len(installed)} DIMM"]
    if total_bytes:
        summary_bits.append(f"{round(total_bytes / (1024 ** 3), 1):g} GB")
    summary_bits.append(f"{mode} channel inferred" if mode != "unknown" else "channel unknown")
    return {
        "summary": " / ".join(summary_bits),
        "channel_mode": mode,
        "channel_count": channel_count,
        "channel_inferred": channel_count > 0,
        "channels": channels,
        "installed_count": len(installed),
        "slot_count": len(modules),
        "total_bytes": total_bytes,
        "modules": installed[:16],
    }


def _linux_mounts_from_lsblk_node(node):
    mounts = node.get("mountpoints")
    if isinstance(mounts, list):
        return [str(item) for item in mounts if item]
    mount = node.get("mountpoint")
    return [str(mount)] if mount else []


def _read_linux_filesystem_usage():
    usage = {}
    text = _linux_command_output(["df", "-T", "-B1", "-P"], timeout=4)
    for line in text.splitlines()[1:]:
        parts = line.split(None, 6)
        if len(parts) < 7:
            continue
        source, fstype, total, used, avail, percent, mountpoint = parts
        if fstype in {"devtmpfs", "tmpfs", "squashfs", "overlay", "proc", "sysfs", "efivarfs", "cgroup2", "debugfs", "tracefs"}:
            continue
        try:
            total_bytes = int(total)
            used_bytes = int(used)
            free_bytes = int(avail)
        except Exception:
            continue
        try:
            percent_value = float(str(percent).rstrip("%"))
        except Exception:
            percent_value = 0.0
        usage[mountpoint] = {
            "source": source,
            "fstype": fstype,
            "size_bytes": total_bytes,
            "used_bytes": used_bytes,
            "free_bytes": free_bytes,
            "percent": round(percent_value, 1),
            "mountpoints": [mountpoint],
            "is_network": fstype.lower() in {"nfs", "nfs4", "cifs", "smb3", "sshfs"} or ":" in source or source.startswith("//"),
            "is_removable": mountpoint.startswith("/media/") or mountpoint.startswith("/run/media/"),
            "is_system": mountpoint == "/",
        }
    return usage


def _read_linux_storage_devices():
    output = _linux_command_output(["lsblk", "-b", "-J", "-o", "NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS,MOUNTPOINT,MODEL,SERIAL,TRAN,ROTA,RM,PKNAME"], timeout=4)
    try:
        parsed = json.loads(output) if output else {}
    except Exception:
        parsed = {}
    devices = []
    filesystems = []
    fs_usage = _read_linux_filesystem_usage()
    for node in parsed.get("blockdevices", []) if isinstance(parsed, dict) else []:
        if not isinstance(node, dict) or node.get("type") in ("loop", "rom"):
            continue
        children = []
        for child in node.get("children") or []:
            if not isinstance(child, dict):
                continue
            mounts = _linux_mounts_from_lsblk_node(child)
            part = {
                "name": child.get("name") or "",
                "type": child.get("type") or "",
                "size_bytes": int(child.get("size") or 0),
                "fstype": child.get("fstype") or "",
                "mountpoints": mounts,
                "is_system": "/" in mounts,
            }
            for mount in mounts:
                if mount in fs_usage:
                    part.update(fs_usage[mount])
                    break
            children.append(part)
            if mounts:
                filesystems.append({**part, "disk": node.get("name") or "", "model": node.get("model") or ""})
        mounts = _linux_mounts_from_lsblk_node(node)
        devices.append({
            "name": node.get("name") or "",
            "type": node.get("type") or "",
            "size_bytes": int(node.get("size") or 0),
            "model": str(node.get("model") or "").strip(),
            "serial": str(node.get("serial") or "").strip(),
            "tran": node.get("tran") or "",
            "rotational": str(node.get("rota") or "0") == "1",
            "removable": str(node.get("rm") or "0") == "1",
            "mountpoints": mounts,
            "partitions": children,
            "is_system": "/" in mounts or any(item.get("is_system") for item in children),
        })
    known_mounts = {mount for item in filesystems for mount in item.get("mountpoints", [])}
    for mount, item in fs_usage.items():
        if mount in known_mounts:
            continue
        filesystems.append({
            **item,
            "name": mount,
            "type": "network" if item.get("is_network") else "mount",
            "disk": item.get("source") or "",
            "model": "NAS / 网络存储" if item.get("is_network") else "",
        })
    return {
        "devices": devices[:16],
        "filesystems": filesystems[:32],
        "disk_count": len([item for item in devices if item.get("type") == "disk"]),
        "mounted_count": len(filesystems),
    }


def _read_linux_network_adapters():
    output = _linux_command_output(["ip", "-j", "addr"], timeout=3)
    try:
        rows = json.loads(output) if output else []
    except Exception:
        rows = []
    adapters = []
    wireless_items = []
    virtual_pattern = re.compile(r"^(lo|docker|veth|br-|virbr|tun|tap|wg|tailscale|p2p-)", re.IGNORECASE)
    for row in rows if isinstance(rows, list) else []:
        ifname = str(row.get("ifname") or "")
        if not ifname or ifname == "lo":
            continue
        is_virtual = bool(virtual_pattern.search(ifname))
        try:
            speed_mbps = int(_read_text_file(f"/sys/class/net/{ifname}/speed"))
        except Exception:
            speed_mbps = 0
        ipv4 = []
        ipv6 = []
        for addr in row.get("addr_info") or []:
            if addr.get("family") == "inet":
                ipv4.append(addr.get("local") or "")
            elif addr.get("family") == "inet6":
                ipv6.append(addr.get("local") or "")
        is_wireless = Path(f"/sys/class/net/{ifname}/wireless").exists()
        item = {
            "name": ifname,
            "mac": _read_text_file(f"/sys/class/net/{ifname}/address"),
            "state": str(row.get("operstate") or "").lower(),
            "speed_mbps": speed_mbps,
            "ipv4": [value for value in ipv4 if value],
            "ipv6": [value for value in ipv6 if value],
            "is_wireless": is_wireless,
            "is_virtual": is_virtual,
        }
        adapters.append(item)
        if is_wireless:
            wireless_items.append(dict(item))
    nmcli = _linux_command_output(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev", "status"], timeout=3)
    ssid_by_iface = {}
    for line in nmcli.splitlines():
        parts = line.split(":", 3)
        if len(parts) >= 4 and parts[1] in ("wifi", "wifi-p2p"):
            ssid_by_iface[parts[0]] = parts[3] if "connected" in parts[2] else ""
    for item in wireless_items:
        item["ssid"] = ssid_by_iface.get(item.get("name") or "", "")
        item["connected"] = bool(item.get("ssid"))
    connected = next((item for item in wireless_items if item.get("connected")), None)
    return {
        "adapters": adapters[:32],
        "physical_count": len([item for item in adapters if not item.get("is_virtual")]),
        "active_count": len([item for item in adapters if item.get("state") == "up" and not item.get("is_virtual")]),
        "wireless": {
            "present": bool(wireless_items),
            "connected": bool(connected),
            "ssid": connected.get("ssid") if connected else "",
            "interfaces": wireless_items[:8],
        },
    }


def _read_linux_bluetooth_info():
    controllers = []
    for line in _linux_command_output(["bluetoothctl", "list"], timeout=3).splitlines():
        match = re.match(r"Controller\s+([0-9A-Fa-f:]+)\s+(.+)", line.strip())
        if match:
            controllers.append({"mac": match.group(1).upper(), "name": match.group(2).strip()})
    rfkill_text = _linux_command_output(["rfkill", "list"], timeout=3)
    lsusb_text = _linux_command_output(["lsusb"], timeout=3)
    return {
        "present": bool(controllers or re.search(r"Bluetooth", rfkill_text, flags=re.IGNORECASE) or re.search(r"bluetooth", lsusb_text, flags=re.IGNORECASE)),
        "blocked": bool(re.search(r"Hard blocked:\s*yes|Soft blocked:\s*yes", rfkill_text, flags=re.IGNORECASE)),
        "controllers": controllers[:8],
    }


def _read_linux_hardware_profile():
    now_ts = time.time()
    with LOCAL_MACHINE_STATE_LOCK:
        cached = LOCAL_MACHINE_HW_CACHE["payload"]
        expires_at = float(LOCAL_MACHINE_HW_CACHE["expires_at"] or 0.0)
    if cached and now_ts < expires_at:
        return cached
    cpu_name = ""
    for line in _read_text_file("/proc/cpuinfo").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip().lower() == "model name":
            cpu_name = value.strip()
            break
    board_vendor = _read_text_file("/sys/class/dmi/id/board_vendor")
    board_name = _read_text_file("/sys/class/dmi/id/board_name")
    motherboard = " / ".join([item for item in [board_vendor, board_name] if item]) or platform.platform()
    storage = _read_linux_storage_devices()
    network = _read_linux_network_adapters()
    payload = {
        "cpu_name": cpu_name or platform.processor() or platform.machine() or "Linux Host",
        "motherboard": motherboard,
        "mem_speed": _read_linux_memory_speed(),
        "os_info": _read_linux_os_info(),
        "memory_topology": _read_linux_memory_topology(),
        "storage_devices": storage.get("devices") or [],
        "storage_filesystems": storage.get("filesystems") or [],
        "storage_summary": {"disk_count": storage.get("disk_count") or 0, "mounted_count": storage.get("mounted_count") or 0},
        "network_adapters": network.get("adapters") or [],
        "network_summary": {"physical_count": network.get("physical_count") or 0, "active_count": network.get("active_count") or 0},
        "wireless": network.get("wireless") or {},
        "bluetooth": _read_linux_bluetooth_info(),
        "gpu_list": _read_linux_gpu_snapshot(),
    }
    with LOCAL_MACHINE_STATE_LOCK:
        LOCAL_MACHINE_HW_CACHE["payload"] = payload
        LOCAL_MACHINE_HW_CACHE["expires_at"] = now_ts + 300.0
    return payload


def _find_codemeter_tool():
    for name in ("cmu", "cmu32"):
        path = shutil.which(name)
        if path:
            return path
    for candidate in (
        "/usr/bin/cmu",
        "/usr/sbin/cmu",
        "/usr/local/bin/cmu",
        "/opt/CodeMeter/Runtime/bin/cmu",
        "/opt/codemeter/bin/cmu",
    ):
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return ""


def _read_codemeter_service_state():
    for service in ("codemeter", "CodeMeter"):
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True,
                text=True,
                timeout=1.5,
                encoding="utf-8",
                errors="ignore",
            )
            state = (result.stdout or result.stderr or "").strip()
            if state:
                return state
        except Exception:
            continue
    try:
        result = subprocess.run(
            ["pgrep", "-af", "CodeMeter|codemeter|CmWebAdmin"],
            capture_output=True,
            text=True,
            timeout=1.5,
            encoding="utf-8",
            errors="ignore",
        )
        if result.returncode == 0 and result.stdout.strip():
            return "active"
    except Exception:
        pass
    return "unknown"


def _run_codemeter_command(tool, args):
    try:
        result = subprocess.run(
            [tool] + list(args),
            capture_output=True,
            text=True,
            timeout=5,
            encoding="utf-8",
            errors="ignore",
        )
        return result.returncode, ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    except Exception as exc:
        return 999, str(exc)


def _parse_codemeter_output(text):
    raw = str(text or "")
    runtime_version = ""
    runtime_major = None
    runtime_match = re.search(r"\bVersion\s+([0-9]+(?:\.[0-9]+)?[A-Za-z]?)\b", raw, flags=re.IGNORECASE)
    if runtime_match:
        runtime_version = runtime_match.group(1).strip()
        try:
            runtime_major = int(re.match(r"([0-9]+)", runtime_version).group(1))
        except Exception:
            runtime_major = None
    runtime_outdated = runtime_major is not None and runtime_major < 8
    serials = []
    for match in re.finditer(
        r"(?:CmContainer\s+with\s+Serial\s+Number|Serial\s+(?:Number|No\.?)|Serial)\s*[:#]?\s*([0-9]+-[0-9]+)",
        raw,
        flags=re.IGNORECASE,
    ):
        serial = match.group(1).strip()
        if serial and serial not in serials:
            serials.append(serial)
    for match in re.finditer(r"\b[1-9][0-9]?-[0-9]{5,}\b", raw):
        serial = match.group(0).strip()
        if serial and serial not in serials:
            serials.append(serial)
    physical_serials = [serial for serial in serials if not str(serial).startswith("130-")]
    display_serials = physical_serials or serials

    firmcodes = []
    for match in re.finditer(r"\bFC\s*=\s*([0-9]{3,})\b", raw, flags=re.IGNORECASE):
        code = match.group(1).strip()
        if code and code not in firmcodes:
            firmcodes.append(code)
    has_company_license = "102541" in firmcodes or re.search(r"Lan\s+Jing\s+Ke\s+Ji", raw, flags=re.IGNORECASE) is not None

    company_raw = raw
    company_match = re.search(r"\b102541\b(?P<section>.*?)(?:\n\s*\*\s*FC=|\n\s*[0-9]{6}\s+|\Z)", raw, flags=re.IGNORECASE | re.S)
    if company_match:
        company_raw = company_match.group(0)

    permanent = bool(re.search(r"(no\s+expiration|never\s+expires|unlimited|permanent|lifetime|长期|永久|无限)", company_raw, flags=re.IGNORECASE))
    def _is_license_expiry_context(source, start_index):
        context = source[max(0, start_index - 96): start_index]
        lower = context.lower()
        if any(token in lower for token in ("system time", "box time", "certified time", "version", "build", "copyright")):
            return False
        if re.search(r"\b(?:pc|product\s*code)\s*=\s*\d+", context, flags=re.IGNORECASE):
            return True
        if re.search(r"^\s*\d{1,5}\s+[-\\w]", context, flags=re.MULTILINE):
            return True
        return not company_match

    expirations = []
    patterns = [
        r"(?:Expiration\s+(?:Time|Date)|Expires|Valid\s+Until|Valid\s+to)\s*[:=]?\s*([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2}(?:[T\s][0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?)?)",
        r"(?:到期|有效期至|有效至)\s*[:：]?\s*([0-9]{4}[-/年][0-9]{1,2}[-/月][0-9]{1,2})",
    ]
    if company_match:
        patterns.append(r"\b([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2}(?:[T\s][0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?)?)\b")
    for pattern in patterns:
        for match in re.finditer(pattern, company_raw, flags=re.IGNORECASE):
            if not _is_license_expiry_context(company_raw, match.start()):
                continue
            value = match.group(1).strip().replace("年", "-").replace("月", "-").replace("日", "")
            if value and value not in expirations:
                expirations.append(value)

    licenses = [{"validity": "expires", "expires_at": value} for value in expirations[:8]]
    if permanent and not licenses:
        licenses.append({"validity": "permanent", "expires_at": ""})
    return display_serials, licenses, raw[:2000], {
        "firmcodes": firmcodes,
        "company_code": "102541" if has_company_license else "",
        "company_name": "Lan Jing Ke Ji" if has_company_license else "",
        "has_company_license": has_company_license,
        "scoped_to_company": bool(company_match),
        "physical_serials": physical_serials,
        "virtual_serials": [serial for serial in serials if str(serial).startswith("130-")],
        "runtime_version": runtime_version,
        "runtime_major": runtime_major,
        "runtime_outdated": runtime_outdated,
    }


def _read_codemeter_info():
    now_ts = time.time()
    with LOCAL_MACHINE_STATE_LOCK:
        cached = LOCAL_MACHINE_CODEMETER_CACHE["payload"]
        expires_at = float(LOCAL_MACHINE_CODEMETER_CACHE["expires_at"] or 0.0)
    if cached and now_ts < expires_at:
        return cached

    checked_at = datetime.now().isoformat()
    service_state = _read_codemeter_service_state()
    tool = _find_codemeter_tool()
    installed = bool(tool) or service_state not in ("unknown", "inactive", "failed")
    running = service_state == "active"
    outputs = []
    errors = []
    if tool:
        for args in (("-l", "--show-expiration"), ("--list", "--show-expiration"), ("-x",), ("-l",)):
            code, output = _run_codemeter_command(tool, args)
            if output:
                outputs.append(output)
            if code == 0 and output:
                break
            if output:
                errors.append(output[:240])

    serials, licenses, raw_excerpt, license_identity = _parse_codemeter_output("\n".join(outputs))
    validity = "unknown"
    if licenses:
        if any(item.get("validity") == "expires" for item in licenses):
            validity = "expires"
        elif any(item.get("validity") == "permanent" for item in licenses):
            validity = "permanent"
    if not installed:
        level, summary = "muted", "未安装"
    elif not running:
        level, summary = "warning", "服务未运行"
    elif not serials:
        level, summary = "warning", "未发现加密锁"
    elif validity == "expires":
        level, summary = "ok", "有期限授权"
    elif validity == "permanent":
        level, summary = "ok", "长期有效"
    else:
        level, summary = "ok", "已检测到加密锁"

    payload = {
        "installed": installed,
        "running": running,
        "service_state": service_state,
        "tool": tool,
        "serials": serials,
        "containers": [{"serial": serial} for serial in serials],
        "license_identity": license_identity,
        "license_code": license_identity.get("company_code") or "",
        "license_name": license_identity.get("company_name") or "",
        "runtime_version": license_identity.get("runtime_version") or "",
        "runtime_major": license_identity.get("runtime_major"),
        "runtime_outdated": bool(license_identity.get("runtime_outdated")),
        "licenses": licenses,
        "validity": validity,
        "summary": summary,
        "level": level,
        "checked_at": checked_at,
        "raw_excerpt": raw_excerpt,
        "error": "; ".join(errors[:2]),
    }
    with LOCAL_MACHINE_STATE_LOCK:
        LOCAL_MACHINE_CODEMETER_CACHE["payload"] = payload
        LOCAL_MACHINE_CODEMETER_CACHE["expires_at"] = now_ts + 120.0
    return payload


def _invalidate_local_hardware_cache():
    with LOCAL_MACHINE_STATE_LOCK:
        LOCAL_MACHINE_HW_CACHE["expires_at"] = 0.0
        LOCAL_MACHINE_GPU_CACHE["expires_at"] = 0.0
        LOCAL_MACHINE_CODEMETER_CACHE["expires_at"] = 0.0


def _read_local_ntp_state():
    payload = {
        "ntp_enabled": True,
        "ntp_primary": "192.168.50.120",
        "ntp_fallback": "192.168.50.121",
        "last_ntp_check_at": datetime.now().isoformat(),
        "ntp_service": "chrony",
        "ntp_last_result": "",
    }
    try:
        result = subprocess.run(["chronyc", "tracking"], capture_output=True, text=True, timeout=4)
        text = (result.stdout or "") + (result.stderr or "")
        if result.returncode == 0:
            match = re.search(r"Reference ID\s*:\s*(.+)", text)
            source = match.group(1).strip() if match else ""
            payload["ntp_last_result"] = "ok local_ntp_server" + (f" source={source}" if source else "")
        else:
            payload["ntp_last_result"] = "error " + re.sub(r"\s+", " ", text.strip())[:240]
    except Exception as exc:
        payload["ntp_last_result"] = "error " + str(exc)
    return payload


def _build_local_machine_status():
    hardware = _read_linux_hardware_profile()
    meminfo = _read_linux_meminfo()
    disk_usage = shutil.disk_usage("/")
    net_rates = _read_linux_net_rates()
    now_iso = datetime.now().isoformat()
    configured_ip = str(CONFIG.get("server_monitor", {}).get("agent_host", "") or "").strip()
    network_primary = _linux_network_primary(
        (net_rates.get("network_primary") or {}).get("adapter_name"),
        configured_ip or get_local_ip(),
    )
    physical_mac = normalize_machine_mac(network_primary.get("adapter_mac"))
    ntp_state = _read_local_ntp_state()
    return {
        "cpu_name": hardware.get("cpu_name"),
        "motherboard": hardware.get("motherboard"),
        "mem_speed": hardware.get("mem_speed"),
        "os_info": hardware.get("os_info") or {},
        "memory_topology": hardware.get("memory_topology") or {},
        "storage_devices": hardware.get("storage_devices") or [],
        "storage_filesystems": hardware.get("storage_filesystems") or [],
        "storage_summary": hardware.get("storage_summary") or {},
        "network_adapters": hardware.get("network_adapters") or [],
        "network_summary": hardware.get("network_summary") or {},
        "wireless": hardware.get("wireless") or {},
        "bluetooth": hardware.get("bluetooth") or {},
        "gpu_list": hardware.get("gpu_list") or [],
        "codemeter": _read_codemeter_info(),
        "cpu_percent": _read_linux_cpu_percent(),
        "mem_total": round(meminfo["total"] / (1024 ** 3), 1) if meminfo["total"] else 0,
        "mem_used": round(meminfo["used"] / (1024 ** 3), 1) if meminfo["used"] else 0,
        "mem_percent": meminfo["percent"],
        "disk_total": round(disk_usage.total / (1024 ** 3), 1) if disk_usage.total else 0,
        "disk_used": round(disk_usage.used / (1024 ** 3), 1) if disk_usage.used else 0,
        "disk_percent": round((disk_usage.used / float(disk_usage.total)) * 100.0, 1) if disk_usage.total else 0,
        "net_sent_kb_s": net_rates["sent_kb_s"],
        "net_recv_kb_s": net_rates["recv_kb_s"],
        "network_primary": network_primary,
        "physical_mac": physical_mac,
        "display_mac": physical_mac,
        "hardware_refreshed_at": now_iso,
        "host_type": "linux_builtin",
        "agent": {
            "version": AGENT_VERSION,
            "physical_mac": physical_mac,
            "task_exists": True,
            "task_state": "systemd 内置采集",
            "task_user": os.environ.get("USER") or "root",
            "current_server_url": f"http://{get_agent_server_host()}:{get_agent_server_port()}",
            "service": "smart-center.service",
            "report_interval_sec": LOCAL_MONITOR_INTERVAL_SEC,
            "updated_at": now_iso,
            "ntp_enabled": ntp_state.get("ntp_enabled"),
            "ntp_primary": ntp_state.get("ntp_primary"),
            "ntp_fallback": ntp_state.get("ntp_fallback"),
            "last_ntp_check_at": ntp_state.get("last_ntp_check_at"),
            "ntp_configured_at": ntp_state.get("ntp_configured_at"),
            "ntp_last_result": ntp_state.get("ntp_last_result"),
            "ntp_service": ntp_state.get("ntp_service"),
        },
    }


def _payload_has_runtime_metrics(payload):
    if not isinstance(payload, dict):
        return False
    metric_keys = (
        "cpu_name",
        "cpu_percent",
        "motherboard",
        "mem_speed",
        "mem_total",
        "mem_used",
        "mem_percent",
        "disk_percent",
        "disk_total",
        "disk_used",
        "net_sent_kb_s",
        "net_recv_kb_s",
        "gpu_list",
        "hardware_refreshed_at",
        "os_caption",
        "os_version",
        "codemeter",
    )
    return any(key in payload for key in metric_keys)


def _mark_payload_as_full_report(payload, server_received_at="", prefer_server=True):
    payload = payload if isinstance(payload, dict) else {}
    agent = payload.get("agent") if isinstance(payload.get("agent"), dict) else {}
    if agent:
        # Heartbeat/bootstrap are transient states. If runtime metrics are
        # present, keeping these flags makes a healthy full report look stale.
        for key in ("heartbeat", "bootstrap", "initial_worker_exit_code", "initial_worker_log_tail"):
            agent.pop(key, None)
        payload["agent"] = agent
    full_at = ""
    if prefer_server and server_received_at:
        full_at = server_received_at
    if not full_at:
        full_at = (
            payload.get("last_full_report_at")
            or payload.get("client_reported_at")
            or payload.get("hardware_refreshed_at")
            or payload.get("server_received_at")
            or server_received_at
            or ""
        )
    payload["last_report_kind"] = "full"
    if full_at:
        payload["last_full_report_at"] = _format_machine_timestamp(full_at) or str(full_at)
    return payload


def _classify_machine_report(payload, data=None):
    payload = payload if isinstance(payload, dict) else {}
    data = data if isinstance(data, dict) else {}
    if isinstance(data.get("wake_proxy_result"), dict):
        return "wake_proxy_result"
    if _payload_has_runtime_metrics(payload):
        return "full"
    agent = payload.get("agent") if isinstance(payload.get("agent"), dict) else {}
    if bool(agent.get("bootstrap")):
        return "bootstrap"
    if agent:
        return "agent_heartbeat"
    return "partial"


def _payload_runtime_freshness(payload, reference_at=None):
    payload = payload if isinstance(payload, dict) else {}
    if not _payload_has_runtime_metrics(payload):
        return {
            "fresh": False,
            "age_sec": None,
            "reference_at": reference_at or "",
            "runtime_at": "",
            "source": "",
        }
    reference_at = reference_at or datetime.now().isoformat()
    reference_dt = _parse_machine_timestamp(reference_at)
    runtime_at = payload.get("last_full_report_at") or ""
    source = "last_full_report_at" if payload.get("last_full_report_at") else ""
    runtime_dt = _parse_machine_timestamp(runtime_at)
    age_sec = None
    if reference_dt and runtime_dt:
        age_sec = max(0.0, (reference_dt - runtime_dt).total_seconds())
    fresh = age_sec is not None and age_sec <= max(300, _online_window_for_machine_data(payload) * 2)
    return {
        "fresh": fresh,
        "age_sec": round(age_sec, 1) if age_sec is not None else None,
        "reference_at": _format_machine_timestamp(reference_at),
        "runtime_at": _format_machine_timestamp(runtime_at),
        "source": source,
    }


def _payload_is_linux_builtin(payload):
    payload = payload if isinstance(payload, dict) else {}
    agent = payload.get("agent") if isinstance(payload.get("agent"), dict) else {}
    return payload.get("host_type") == "linux_builtin" or str(agent.get("service") or "") == "smart-center.service"


def _format_age_text(age_sec):
    if not isinstance(age_sec, (int, float)):
        return "未知时长"
    if age_sec < 90:
        return f"{int(age_sec)} 秒"
    if age_sec < 7200:
        return f"{int(age_sec // 60)} 分钟"
    return f"{round(age_sec / 3600, 1)} 小时"


def _trim_diagnostic_text(value, limit=240):
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("\r", " ").replace("\n", " ").replace("||", " | ")
    text = " ".join(part for part in text.split() if part)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _detect_bootstrap_root_cause(log_tail):
    text = _trim_diagnostic_text(log_tail, 420)
    lower = text.lower()
    if not text:
        return {
            "root_cause": "",
            "suggestion": "",
        }
    if (
        "cannot overwrite variable host" in lower
        or "host because it is read-only" in lower
        or "foreach ($host in @($cfg['candidate_hosts']))" in lower
        or "$host" in lower
    ):
        return {
            "root_cause": "旧版 Windows agent worker 命中了 PowerShell 保留变量 $Host，启动即崩溃。",
            "suggestion": "在目标 Windows 机器重新运行最新版 deploy_agent.bat，覆盖旧版 agent 后即可恢复。",
        }
    if "missing worker script" in lower:
        return {
            "root_cause": "计划任务已存在，但 agent_worker.ps1 文件缺失或未成功写入。",
            "suggestion": "重新运行 deploy_agent.bat，确认 C:\\ProgramData\\SmartCenterAgent 下脚本已写入。",
        }
    if "executionpolicy" in lower or "running scripts is disabled" in lower:
        return {
            "root_cause": "目标 Windows 机器脚本执行策略阻止了 agent 启动。",
            "suggestion": "以管理员身份重新运行部署脚本，并确认 PowerShell 执行策略允许本次启动。",
        }
    if "timed out" in lower or "timeout" in lower:
        return {
            "root_cause": "agent 已启动，但与中控服务端握手或上报时超时。",
            "suggestion": "先检查网络连通性、agent 接入地址与端口，再执行重部署或刷新。",
        }
    if "not recognized" in lower:
        return {
            "root_cause": "目标 Windows 环境缺少当前 agent 启动所需命令或组件。",
            "suggestion": "确认 PowerShell 版本与系统组件完整后重新部署，并检查 deploy.log / agent.log。",
        }
    return {
        "root_cause": _trim_diagnostic_text(text, 180),
        "suggestion": "优先查看 deploy.log / agent.log，并重新运行最新版 deploy_agent.bat 覆盖部署。",
    }


def _build_machine_diagnostic(machine):
    machine = machine if isinstance(machine, dict) else {}
    status_payload = machine.get("status") if isinstance(machine.get("status"), dict) else {}
    agent = machine.get("agent_status") if isinstance(machine.get("agent_status"), dict) else {}
    is_online = bool(machine.get("is_online"))
    report_online = bool(machine.get("report_online", is_online))
    agent_heartbeat_online = bool(machine.get("agent_heartbeat_online"))
    ping_online = machine.get("ping_online")
    network_reachable = machine.get("network_reachable")
    has_runtime_metrics = _payload_has_runtime_metrics(status_payload)
    runtime_freshness = _payload_runtime_freshness(status_payload, machine.get("server_received_at") or machine.get("last_online"))
    runtime_fresh = bool(runtime_freshness.get("fresh"))
    bootstrap = bool(agent.get("bootstrap"))
    agent_version = str(agent.get("version") or "").strip()
    agent_outdated = _is_agent_version_outdated(agent_version)
    task_exists = bool(agent.get("task_exists"))
    exit_code_raw = agent.get("initial_worker_exit_code")
    exit_code = None
    try:
        if exit_code_raw not in (None, "", "None"):
            exit_code = int(exit_code_raw)
    except Exception:
        exit_code = None
    log_tail = _trim_diagnostic_text(agent.get("initial_worker_log_tail"), 420)

    diagnostic = {
        "level": "info",
        "code": "unknown",
        "summary": "等待节点上报",
        "detail": "当前尚未拿到完整节点运行信息。",
        "root_cause": "",
        "suggestion": "确认节点已部署并能访问中控服务后，等待下一轮自动上报。",
        "needs_attention": True,
        "needs_redeploy": False,
        "has_runtime_metrics": has_runtime_metrics,
        "runtime_fresh": runtime_fresh,
        "runtime_age_sec": runtime_freshness.get("age_sec"),
        "runtime_at": runtime_freshness.get("runtime_at"),
        "report_online": report_online,
        "agent_heartbeat_online": agent_heartbeat_online,
        "latest_agent_version": AGENT_VERSION,
        "agent_outdated": agent_outdated,
        "bootstrap_only": bootstrap and not has_runtime_metrics,
        "log_excerpt": log_tail,
    }

    if report_online and has_runtime_metrics and not runtime_fresh:
        age_text = _format_age_text(runtime_freshness.get("age_sec"))
        self_update = agent.get("self_update") if isinstance(agent.get("self_update"), dict) else {}
        self_update_action = str(self_update.get("action") or "").strip()
        self_update_error = str(self_update.get("error") or "").strip()
        detail_bits = ["120 仍能收到节点心跳，但 CPU / 内存 / GPU 等完整采集指标没有同步刷新。"]
        if agent_outdated:
            detail_bits.append(f"节点当前 Agent {agent_version or '未知'}，中控发布 {AGENT_VERSION}。")
        if self_update_error:
            detail_bits.append(f"自更新错误: {self_update_error}")
        diagnostic.update(
            {
                "level": "warn",
                "code": "agent_heartbeat_runtime_stale" if agent_heartbeat_online else "runtime_stale",
                "summary": f"心跳在线，采集停滞 {age_text}",
                "detail": " ".join(detail_bits),
                "root_cause": self_update_error,
                "suggestion": "不要继续盲目重复覆盖安装；优先查看目标机器 SmartCenterAgent 的 agent.log / deploy.log，确认工作脚本是否卡死、被 400 拒绝或自更新失败。",
                "needs_attention": True,
                "needs_redeploy": agent_outdated and self_update_action in ("failed", ""),
            }
        )
        return diagnostic

    if report_online and agent_outdated:
        self_update = agent.get("self_update") if isinstance(agent.get("self_update"), dict) else {}
        self_update_action = str(self_update.get("action") or "").strip()
        self_update_error = str(self_update.get("error") or "").strip()
        summary = f"Agent 版本落后: {agent_version} -> {AGENT_VERSION}"
        if self_update_action == "updated":
            summary = f"已拉取新版 Agent，等待下一轮切换到 {AGENT_VERSION}"
        elif self_update_action == "failed":
            summary = "Agent 自更新失败"
        diagnostic.update(
            {
                "level": "warn" if self_update_action != "failed" else "error",
                "code": "agent_outdated" if self_update_action != "failed" else "agent_update_failed",
                "summary": summary,
                "detail": (
                    f"节点当前上报版本 {agent_version}，中控发布版本 {AGENT_VERSION}。"
                    + (f" 自更新错误: {self_update_error}" if self_update_error else "")
                ),
                "root_cause": self_update_error,
                "suggestion": "等待下一轮自动更新；如果仍未变化，先查看 agent.log / deploy.log 里的自更新错误，再决定是否覆盖安装。",
                "needs_attention": True,
                "needs_redeploy": self_update_action in ("failed", "") or not self_update,
            }
        )
        return diagnostic

    if is_online and has_runtime_metrics:
        diagnostic.update(
            {
                "level": "success",
                "code": "healthy",
                "summary": "节点运行正常",
                "detail": "代理在线，硬件与运行指标已完整上报。",
                "root_cause": "",
                "suggestion": "如需校验最新硬件信息，可执行“刷新信息”。",
                "needs_attention": False,
            }
        )
        return diagnostic

    if not report_online:
        if ping_online is False:
            diagnostic.update(
                {
                    "level": "error",
                    "code": "offline_unreachable",
                    "summary": "节点离线",
                    "detail": "节点超过上报窗口，且当前 IP ping 不通，判断为关机、断网或网络不可达。",
                    "root_cause": _detect_bootstrap_root_cause(log_tail).get("root_cause", "") if log_tail else "",
                    "suggestion": "先确认机器电源与网络；如需要远程恢复，可尝试网络唤醒，开机后再观察 Agent 是否恢复上报。",
                    "needs_attention": True,
                    "needs_redeploy": False,
                }
            )
            return diagnostic
        if ping_online is True:
            diagnostic.update(
                {
                    "level": "warn",
                    "code": "agent_offline_host_reachable",
                    "summary": "主机可达，Agent 未上报",
                    "detail": "节点超过上报窗口，但当前 IP ping 可达，说明机器大概率开机，采集服务可能未运行或上报链路异常。",
                    "root_cause": _detect_bootstrap_root_cause(log_tail).get("root_cause", "") if log_tail else "",
                    "suggestion": "优先检查目标机器的 Smart Center Agent 计划任务/服务；必要时运行最新版覆盖安装命令。",
                    "needs_attention": True,
                    "needs_redeploy": True,
                }
            )
            return diagnostic
        diagnostic.update(
            {
                "level": "warn",
                "code": "offline",
                "summary": "节点当前离线",
                "detail": "节点最近没有按预期继续上报，当前未获得可用 ping 判定，可能是机器关机、网络中断或 agent 未正常拉起。",
                "root_cause": _detect_bootstrap_root_cause(log_tail).get("root_cause", "") if log_tail else "",
                "suggestion": "先检查机器是否开机、网络是否可达；如仍不恢复，可重新运行 deploy_agent.bat 或执行网络唤醒后再观察。",
                "needs_attention": True,
                "needs_redeploy": bool(log_tail or network_reachable is not False),
            }
        )
        return diagnostic

    if bootstrap and not has_runtime_metrics:
        root_info = _detect_bootstrap_root_cause(log_tail)
        failed = exit_code not in (None, 0)
        diagnostic.update(
            {
                "level": "error" if failed else "warn",
                "code": "bootstrap_failed" if failed else "bootstrap_only",
                "summary": "代理已安装，但工作脚本未完成稳定上报",
                "detail": (
                    f"bootstrap 已回传，工作脚本退出码 {exit_code}。"
                    if failed
                    else "节点只回传了 bootstrap 信息，尚未进入稳定上报。"
                ),
                "root_cause": root_info.get("root_cause", ""),
                "suggestion": root_info.get("suggestion", "") or "重新运行 deploy_agent.bat 覆盖部署后，再观察是否转为在线运行。",
                "needs_attention": True,
                "needs_redeploy": True,
            }
        )
        return diagnostic

    if agent and not task_exists:
        diagnostic.update(
            {
                "level": "warn",
                "code": "task_missing",
                "summary": "节点已接入，但未检测到计划任务",
                "detail": "agent 元信息存在，但计划任务未创建或已被移除。",
                "suggestion": "在目标 Windows 机器重新运行 deploy_agent.bat，恢复计划任务与开机自启。",
                "needs_attention": True,
                "needs_redeploy": True,
            }
        )
        return diagnostic

    if not agent and not status_payload:
        diagnostic.update(
            {
                "level": "warn",
                "code": "manual_only",
                "summary": "仅有手工登记信息，尚未收到任何上报",
                "detail": "该节点目前只有配置记录，没有 agent 或运行数据。",
                "suggestion": "确认 IP / MAC 正确后，在目标机器执行 deploy_agent.bat 完成接入。",
                "needs_attention": True,
                "needs_redeploy": True,
            }
        )
        return diagnostic

    if report_online and not has_runtime_metrics:
        diagnostic.update(
            {
                "level": "warn",
                "code": "partial_metrics",
                "summary": "节点在线，但硬件指标未完整上报",
                "detail": "当前只收到部分节点状态，CPU / 内存 / 硬件等指标还不完整。",
                "suggestion": "稍等一轮自动上报，或执行“刷新信息”强制刷新节点硬件缓存。",
                "needs_attention": True,
            }
        )
        return diagnostic

    return diagnostic


def _merge_machine_payload(existing_payload, incoming_payload):
    existing_payload = existing_payload if isinstance(existing_payload, dict) else {}
    incoming_payload = incoming_payload if isinstance(incoming_payload, dict) else {}
    incoming_payload = _sanitize_machine_payload(incoming_payload)
    incoming_has_runtime = _payload_has_runtime_metrics(incoming_payload)
    incoming_agent = incoming_payload.get("agent")
    if isinstance(incoming_agent, dict):
        if incoming_has_runtime:
            _mark_payload_as_full_report(incoming_payload, incoming_payload.get("server_received_at"), prefer_server=True)
        if incoming_agent.get("heartbeat"):
            incoming_agent.pop("bootstrap", None)
    if not existing_payload:
        if incoming_has_runtime:
            _mark_payload_as_full_report(incoming_payload, incoming_payload.get("server_received_at"), prefer_server=True)
        return incoming_payload
    existing_payload = _sanitize_machine_payload(existing_payload)
    existing_has_runtime = _payload_has_runtime_metrics(existing_payload)
    if incoming_has_runtime:
        _mark_payload_as_full_report(incoming_payload, incoming_payload.get("server_received_at"), prefer_server=True)
        return incoming_payload
    merged = dict(existing_payload)
    incoming_agent = incoming_payload.get("agent")
    if isinstance(incoming_agent, dict):
        merged_agent = dict(existing_payload.get("agent") or {}) if isinstance(existing_payload.get("agent"), dict) else {}
        merged_agent.update(incoming_agent)
        if existing_has_runtime:
            for key in ("heartbeat", "bootstrap", "initial_worker_exit_code", "initial_worker_log_tail"):
                merged_agent.pop(key, None)
        merged["agent"] = merged_agent
    existing_runtime_at = existing_payload.get("client_reported_at") or existing_payload.get("hardware_refreshed_at") or ""
    merged.setdefault("last_runtime_report_at", existing_runtime_at)
    incoming_server_at = incoming_payload.get("server_received_at")
    report_kind = _classify_machine_report(incoming_payload)
    downgrade_only_kinds = {"agent_heartbeat", "partial", "bootstrap"}
    if report_kind in downgrade_only_kinds and existing_has_runtime:
        _mark_payload_as_full_report(merged, prefer_server=False)
    else:
        merged["last_report_kind"] = report_kind
    if incoming_server_at:
        merged["last_agent_heartbeat_at"] = incoming_server_at
        if report_kind == "bootstrap":
            merged["last_bootstrap_report_at"] = incoming_server_at
        elif report_kind == "wake_proxy_result":
            merged["last_wake_proxy_report_at"] = incoming_server_at
    runtime_keys = {
        "cpu_name",
        "cpu_percent",
        "motherboard",
        "mem_speed",
        "mem_total",
        "mem_used",
        "mem_percent",
        "disk_percent",
        "disk_total",
        "disk_used",
        "net_sent_kb_s",
        "net_recv_kb_s",
        "gpu_list",
        "gpu_diagnostics",
        "codemeter",
        "os_caption",
        "os_version",
        "hardware_refreshed_at",
        "report_generated_at",
        "client_reported_at",
        "clock_offset_sec",
        "last_report_kind",
        "last_full_report_at",
        "last_runtime_report_at",
        "last_agent_heartbeat_at",
        "last_bootstrap_report_at",
        "last_wake_proxy_report_at",
    }
    for key, value in incoming_payload.items():
        if key == "agent":
            continue
        if key in runtime_keys:
            continue
        if value not in (None, "", [], {}):
            merged[key] = value
    if report_kind in downgrade_only_kinds and existing_has_runtime:
        _mark_payload_as_full_report(merged, prefer_server=False)
    return merged


def _find_machine_alias_row(cursor, mac, hostname, ip):
    alias_candidates = []
    normalized_mac = normalize_machine_mac(mac)
    raw_mac = str(mac or "").strip().upper()
    compact_mac = re.sub(r"[^0-9A-F]", "", normalized_mac)
    if normalized_mac:
        alias_candidates.append(normalized_mac)
    if raw_mac and raw_mac not in alias_candidates:
        alias_candidates.append(raw_mac)
    if compact_mac and compact_mac not in alias_candidates:
        alias_candidates.append(compact_mac)

    seen_rows = set()
    for candidate in alias_candidates:
        if not candidate or candidate == normalized_mac:
            continue
        cursor.execute(
            """
            SELECT mac, hostname, ip, last_online, data, is_manual, custom_name, sort_order, remark, card_size, asset_group
            FROM machines
            WHERE mac=?
            LIMIT 1
            """,
            (candidate,),
        )
        alias_row = cursor.fetchone()
        if alias_row and alias_row[0] not in seen_rows:
            return alias_row
        if candidate == compact_mac:
            cursor.execute(
                """
                SELECT mac, hostname, ip, last_online, data, is_manual, custom_name, sort_order, remark, card_size, asset_group
                FROM machines
                WHERE REPLACE(mac, '-', '')=?
                ORDER BY mac ASC
                LIMIT 1
                """,
                (compact_mac,),
            )
            alias_row = cursor.fetchone()
            if alias_row and alias_row[0] not in seen_rows:
                return alias_row
    alias_conditions = []
    alias_params = []
    normalized_ip = str(ip or "").strip()
    normalized_hostname = str(hostname or "").strip()
    if normalized_ip:
        alias_conditions.append("ip=?")
        alias_params.append(normalized_ip)
    # Avoid merging real machines just because Windows left the default
    # hostname as SERVER/DESKTOP. Hostname fallback is only for manual
    # placeholders; real nodes are identified by MAC, or by a matching
    # placeholder IP when the agent reports for the first time.
    generic_hostnames = {"SERVER", "DESKTOP", "PC", "UNKNOWN", "未知主机", "未命名节点"}
    if normalized_hostname and normalized_hostname.upper() not in generic_hostnames:
        alias_conditions.append("hostname=?")
        alias_params.append(normalized_hostname)
        alias_conditions.append("custom_name=?")
        alias_params.append(normalized_hostname)
    if alias_conditions:
        cursor.execute(
            f"""
            SELECT mac, hostname, ip, last_online, data, is_manual, custom_name, sort_order, remark, card_size, asset_group
            FROM machines
            WHERE ({' OR '.join(alias_conditions)})
              AND (mac LIKE 'TEMP-%' OR is_manual=1)
            ORDER BY
                CASE WHEN mac LIKE 'TEMP-%' THEN 0 ELSE 1 END ASC,
                sort_order ASC,
                mac ASC
            LIMIT 1
            """,
            tuple(alias_params),
        )
        alias_row = cursor.fetchone()
        if alias_row and alias_row[0] != normalized_mac:
            return alias_row
    return None


def _choose_machine_primary_row(primary_mac, primary_row, alias_row):
    if not alias_row:
        return primary_mac, primary_row, None
    if not primary_row:
        return primary_mac, alias_row, alias_row[0]

    primary_ts = _parse_machine_timestamp(primary_row[3])
    alias_ts = _parse_machine_timestamp(alias_row[3])
    if alias_ts and (not primary_ts or alias_ts > primary_ts):
        return primary_mac, alias_row, alias_row[0]
    return primary_mac, primary_row, alias_row[0]


def _merge_machine_rows(cursor, target_mac, target_row, source_mac):
    if not source_mac or source_mac == target_mac:
        return
    cursor.execute("UPDATE metrics_history SET mac=? WHERE mac=?", (target_mac, source_mac))
    cursor.execute("DELETE FROM machines WHERE mac=?", (source_mac,))
    for key in _machine_command_keys(source_mac):
        if key in SERVER_COMMANDS and target_mac not in SERVER_COMMANDS:
            SERVER_COMMANDS[target_mac] = SERVER_COMMANDS[key]
        SERVER_COMMANDS.pop(key, None)


def _is_test_machine_report(mac, hostname="", ip="", status_payload=None):
    normalized_mac = normalize_machine_mac(mac)
    normalized_ip = str(ip or "").strip()
    normalized_hostname = str(hostname or "").strip().lower()
    payload = status_payload if isinstance(status_payload, dict) else {}
    agent_payload = payload.get("agent") if isinstance(payload.get("agent"), dict) else {}
    agent_version = str(agent_payload.get("version") or "").strip().lower()
    cpu_name = str(payload.get("cpu_name") or "").strip().lower()
    if normalized_mac.startswith("AA-BB-CC-DD-EE-"):
        return True
    if normalized_mac.startswith("TEMP-TIMECHECK"):
        return True
    if normalized_hostname in {"test", "test2", "time-check-test", "codex-test-full-report"}:
        return True
    if normalized_ip in {"1.1.1.1", "1.1.1.2", "127.0.0.1"} and agent_version in {"test", "time-test"}:
        return True
    if "codex test" in cpu_name or agent_version in {"test", "time-test"}:
        return True
    return False


def _store_machine_status(mac, hostname, ip, timestamp, status_payload):
    mac = normalize_machine_mac(mac)
    status_payload = status_payload if isinstance(status_payload, dict) else {}
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    normalized_hostname = str(hostname or "").strip()
    normalized_ip = str(ip or "").strip()
    c.execute(
        """
        SELECT mac, hostname, ip, last_online, data, is_manual, custom_name, sort_order, remark, card_size, asset_group
        FROM machines
        WHERE mac=?
        LIMIT 1
        """,
        (mac,),
    )
    primary_row = c.fetchone()
    alias_row = _find_machine_alias_row(c, mac, normalized_hostname, normalized_ip)
    target_mac, selected_row, merged_source_mac = _choose_machine_primary_row(mac, primary_row, alias_row)
    if merged_source_mac:
        _merge_machine_rows(c, target_mac, selected_row, merged_source_mac)
    row = selected_row[5:] if selected_row else None
    existing_payload = {}
    if selected_row and len(selected_row) > 4:
        existing_payload = _parse_machine_payload(selected_row[4])
    status_payload = _merge_machine_payload(existing_payload, status_payload)
    data_json = json.dumps(status_payload, ensure_ascii=False, separators=(",", ":"))
    skip_history = _should_skip_report(target_mac, data_json, time.time())
    c.execute(
        '''INSERT OR REPLACE INTO machines (mac, hostname, ip, last_online, data, is_manual, custom_name, sort_order, remark, card_size, asset_group) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
        (
            target_mac,
            hostname,
            ip,
            timestamp,
            data_json,
            row[0] if row else 0,
            row[1] if row else None,
            row[2] if row else 999,
            row[3] if row else '',
            row[4] if row else 'normal',
            row[5] if row else '',
        ),
    )
    if not skip_history:
        c.execute('''INSERT INTO metrics_history (mac, timestamp, data) VALUES (?,?,?)''', (target_mac, timestamp, data_json))
    conn.commit()
    conn.close()
    invalidate_machines_cache()


def _run_linux_host_command(command):
    candidates = []
    if command == "restart":
        candidates = [["systemctl", "reboot"], ["shutdown", "-r", "now"]]
    elif command == "shutdown":
        candidates = [["systemctl", "poweroff"], ["shutdown", "-h", "now"]]
    for cmd in candidates:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True
        except Exception:
            continue
    return False


def _handle_local_machine_command(local_mac):
    command = SERVER_COMMANDS.pop(local_mac, None)
    if not command:
        return
    if command == "refresh":
        _invalidate_local_hardware_cache()
        add_log(-1, "[服务器] 已刷新本机 Ubuntu 监控信息缓存")
        return
    if command in {"restart", "shutdown"}:
        action_name = "重启" if command == "restart" else "关机"
        if _run_linux_host_command(command):
            add_log(-1, f"[服务器] 已执行本机 Ubuntu [{action_name}] 指令")
        else:
            add_log(-1, f"[服务器] 本机 Ubuntu [{action_name}] 指令执行失败")


def _record_machine_wake_proxy_result(relay_mac, result):
    relay_mac = normalize_machine_mac(relay_mac)
    if not relay_mac:
        return
    result_payload = result if isinstance(result, dict) else {}
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT data FROM machines WHERE mac=? LIMIT 1", (relay_mac,))
        row = c.fetchone()
        payload = _parse_machine_payload(row[0]) if row else {}
        payload["wake_proxy_result"] = result_payload
        c.execute("UPDATE machines SET data=? WHERE mac=?", (json.dumps(payload, ensure_ascii=False, separators=(",", ":")), relay_mac))
        conn.commit()
        invalidate_machines_cache()
    except Exception as exc:
        add_log(-1, f"[服务器] 记录WOL中继结果失败: {relay_mac} {exc}")
    finally:
        if conn is not None:
            conn.close()


def local_server_monitor_loop():
    if platform.system().lower() != "linux":
        return
    local_mac = get_local_machine_mac()
    while True:
        try:
            configured_ip = str(CONFIG.get("server_monitor", {}).get("agent_host", "") or "").strip()
            report_ip = configured_ip or get_local_ip()
            _handle_local_machine_command(local_mac)
            now_iso = datetime.now().isoformat()
            _store_machine_status(
                local_mac,
                socket.gethostname() or "zhongkong",
                report_ip,
                now_iso,
                _annotate_report_timing(_build_local_machine_status(), now_iso, now_iso),
            )
        except Exception:
            pass
        time.sleep(LOCAL_MONITOR_INTERVAL_SEC)

def get_server_host_from_request():
    configured_host = str(CONFIG.get("server_monitor", {}).get("agent_host", "") or "").strip()
    if configured_host:
        return configured_host
    host = request.headers.get("host", "").split(":")[0]
    if not host or host in ["127.0.0.1", "localhost"]:
        host = get_local_ip()
    return host

def build_agent_worker_script(server_host):
    initial_config_json = json.dumps(build_agent_runtime_config(server_host), ensure_ascii=False, indent=2)
    return f"""$ErrorActionPreference = 'Continue'
$AgentVersion = '{AGENT_VERSION}'
$TaskName = 'SmartCenterAgent'
$AgentDir = Join-Path $env:ProgramData 'SmartCenterAgent'
$ConfigPath = Join-Path $AgentDir 'agent_config.json'
$LogPath = Join-Path $AgentDir 'agent.log'
$NetSamplePath = Join-Path $AgentDir 'net_sample.json'
$WorkerPath = if ($PSCommandPath) {{ $PSCommandPath }} else {{ Join-Path $AgentDir 'agent_worker.ps1' }}
$LauncherPath = Join-Path $AgentDir 'agent_launcher.ps1'
$lastNetBytesSent = $null
$lastNetBytesRecv = $null
$lastNetSampleTime = $null
$script:HardwareCache = $null
$script:LastTaskInfoAt = $null
	$script:TaskInfoCache = $null
	$script:ConsecutiveFailures = 0
	$script:LastSuccessfulReportAt = $null
	$script:GpuProbeDiagnostic = @{{}}
	$script:WakeProxyResult = $null
	$script:SelfUpdateStatus = @{{}}
	$script:AgentRunMutex = $null
	$script:AgentRunMutexAcquired = $false
	$Utf8Encoding = New-Object System.Text.UTF8Encoding($true)

function Write-TextFile([string]$path, [string]$content) {{
    $parent = [System.IO.Path]::GetDirectoryName($path)
    if ($parent) {{
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }}
    if (Test-Path $path -PathType Container) {{
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
    }}
    $lastError = $null
    for ($attempt = 1; $attempt -le 8; $attempt++) {{
        try {{
            [System.IO.File]::WriteAllText($path, [string]$content, $Utf8Encoding)
            return
        }} catch {{
            $lastError = $_
            Start-Sleep -Milliseconds (150 * $attempt)
        }}
    }}
    if ($lastError) {{
        throw $lastError
    }}
}}

function Append-TextFile([string]$path, [string]$content) {{
    $parent = [System.IO.Path]::GetDirectoryName($path)
    if ($parent) {{
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }}
    [System.IO.File]::AppendAllText($path, ([string]$content + [Environment]::NewLine), $Utf8Encoding)
}}

function Write-AgentLog([string]$msg) {{
    Append-TextFile $LogPath ("[" + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + "] " + $msg)
}}

function Write-StageLog([string]$stage, [string]$status = 'start') {{
    Write-AgentLog ('stage ' + $stage + ' ' + $status)
}}

function Enter-AgentRunLock {{
    try {{
        $createdNew = $false
        $script:AgentRunMutex = New-Object System.Threading.Mutex($false, 'Global\\SmartCenterAgentWorker', [ref]$createdNew)
        $script:AgentRunMutexAcquired = $script:AgentRunMutex.WaitOne(0)
        if (-not $script:AgentRunMutexAcquired) {{
            Write-AgentLog 'another worker instance is already running; skip this tick'
            exit 0
        }}
    }} catch {{
        Write-AgentLog ('worker lock failed, continue without lock: ' + $_.Exception.Message)
    }}
}}

function Exit-AgentRunLock {{
    try {{
        if ($script:AgentRunMutexAcquired -and $script:AgentRunMutex) {{
            $script:AgentRunMutex.ReleaseMutex() | Out-Null
        }}
    }} catch {{}}
    try {{
        if ($script:AgentRunMutex) {{
            $script:AgentRunMutex.Dispose()
        }}
    }} catch {{}}
}}

function Get-CommandOrNull([string]$name) {{
    try {{
        return Get-Command $name -ErrorAction Stop
    }} catch {{
        return $null
    }}
}}

function Get-ErrorDetails([object]$err) {{
    if ($null -eq $err) {{
        return 'unknown_error'
    }}
    $parts = @()
    try {{
        if ($err.Exception -and $err.Exception.Message) {{
            $parts += [string]$err.Exception.Message
        }}
    }} catch {{}}
    try {{
        if ($err.ErrorDetails -and $err.ErrorDetails.Message) {{
            $parts += ([string]$err.ErrorDetails.Message).Trim()
        }}
    }} catch {{}}
    try {{
        if ($err.Exception -and $err.Exception.Response) {{
            $statusCode = [int]$err.Exception.Response.StatusCode
            $statusDesc = [string]$err.Exception.Response.StatusDescription
            $parts += ('HTTP ' + $statusCode + ' ' + $statusDesc)
            $stream = $err.Exception.Response.GetResponseStream()
            if ($stream) {{
                $reader = New-Object System.IO.StreamReader($stream)
                try {{
                    $bodyText = $reader.ReadToEnd()
                    if ($bodyText) {{ $parts += ('response=' + $bodyText) }}
                }} finally {{
                    $reader.Close()
                }}
            }}
        }}
    }} catch {{}}
    try {{
        if ($err.InvocationInfo -and $err.InvocationInfo.PositionMessage) {{
            $parts += ([string]$err.InvocationInfo.PositionMessage).Trim()
        }}
    }} catch {{}}
    try {{
        if ($err.ScriptStackTrace) {{
            $parts += ([string]$err.ScriptStackTrace).Trim()
        }}
    }} catch {{}}
    $text = (($parts | Where-Object {{ $_ -and $_.Trim() }}) -join ' | ').Trim()
    if (-not $text) {{
        try {{
            $text = ([string]$err).Trim()
        }} catch {{
            $text = 'unknown_error'
        }}
    }}
    if (-not $text) {{
        $text = 'unknown_error'
    }}
    return $text
}}

function Convert-ToJsonSafeObject([object]$obj, [int]$depth = 0) {{
    if ($null -eq $obj) {{ return $null }}
    if ($obj -is [string] -or $obj -is [char]) {{
        $text = [string]$obj
        $text = $text -replace '[\x00-\x08\x0B\x0C\x0E-\x1F]', ' '
        $text = $text.Replace('"', "'")
        if ($text.Length -gt 1200) {{
            $text = $text.Substring(0, 1200) + '...'
        }}
        return $text
    }}
    if ($obj -is [bool] -or $obj -is [byte] -or $obj -is [int16] -or $obj -is [int] -or $obj -is [int64] -or $obj -is [single] -or $obj -is [double] -or $obj -is [decimal]) {{
        return $obj
    }}
    if ($depth -ge 8) {{
        return ([string]$obj)
    }}
    if ($obj -is [System.Collections.IDictionary]) {{
        $hash = @{{}}
        foreach ($key in @($obj.Keys)) {{
            $safeKey = [string](Convert-ToJsonSafeObject $key ($depth + 1))
            if (-not $safeKey) {{ continue }}
            $hash[$safeKey] = Convert-ToJsonSafeObject $obj[$key] ($depth + 1)
        }}
        return $hash
    }}
    if (($obj -is [System.Collections.IEnumerable]) -and -not ($obj -is [string])) {{
        $items = @()
        foreach ($item in $obj) {{
            $items += ,(Convert-ToJsonSafeObject $item ($depth + 1))
        }}
        return ,$items
    }}
    if ($obj.PSObject -and $obj.PSObject.Properties.Count -gt 0) {{
        $hash = @{{}}
        foreach ($prop in $obj.PSObject.Properties) {{
            $hash[[string]$prop.Name] = Convert-ToJsonSafeObject $prop.Value ($depth + 1)
        }}
        return $hash
    }}
    return ([string]$obj)
}}

function ConvertTo-AgentJson([object]$obj, [int]$depth = 8) {{
    $json = Convert-ToJsonSafeObject $obj 0 | ConvertTo-Json -Depth $depth -Compress
    $probe = $json | ConvertFrom-Json -ErrorAction Stop
    return $json
}}

function Remove-AgentDiagnosticNoise([hashtable]$diag) {{
    if (-not $diag) {{ return @{{}} }}
    foreach ($key in @('amd_adl_error','dxgk_error')) {{
        if ($diag.ContainsKey($key)) {{
            $diag.Remove($key)
        }}
    }}
    return $diag
}}

function Get-LogTail([string]$path, [int]$lineCount = 20) {{
    try {{
        if (-not (Test-Path $path)) {{
            return ''
        }}
        $lines = Get-Content $path -Tail $lineCount -ErrorAction Stop
        return (($lines | ForEach-Object {{ Convert-ToJsonSafeObject ([string]$_) 0 }}) -join ' || ')
    }} catch {{
        return ''
    }}
}}

function Invoke-AgentJsonRequest([string]$uri, [string]$method = 'GET', [string]$contentType = 'application/json', [string]$body = '', [int]$timeoutSec = 8) {{
    $irm = Get-CommandOrNull 'Invoke-RestMethod'
    if ($irm) {{
        if ($method.ToUpperInvariant() -eq 'POST') {{
            return Invoke-RestMethod -Uri $uri -Method Post -ContentType $contentType -Body $body -TimeoutSec $timeoutSec -ErrorAction Stop
        }}
        return Invoke-RestMethod -Uri $uri -Method Get -TimeoutSec $timeoutSec -ErrorAction Stop
    }}

    $request = [System.Net.HttpWebRequest]::Create($uri)
    $request.Method = $method.ToUpperInvariant()
    $request.Timeout = $timeoutSec * 1000
    $request.ReadWriteTimeout = $timeoutSec * 1000
    if ($request.Method -eq 'POST') {{
        $bodyText = [string]$body
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($bodyText)
        $request.ContentType = $contentType
        $request.ContentLength = $bytes.Length
        $stream = $request.GetRequestStream()
        try {{
            $stream.Write($bytes, 0, $bytes.Length)
        }} finally {{
            $stream.Close()
        }}
    }}
    $response = $request.GetResponse()
    try {{
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
        try {{
            $text = $reader.ReadToEnd()
        }} finally {{
            $reader.Close()
        }}
    }} finally {{
        $response.Close()
    }}
    if (-not $text) {{
        return $null
    }}
    try {{
        return ($text | ConvertFrom-Json)
    }} catch {{
        return $null
    }}
}}

function Send-AgentHeartbeat([hashtable]$cfg) {{
    try {{
        if (-not $cfg -or -not $cfg['current_server_url']) {{ return }}
        $heartbeatMac = ''
        $heartbeatIp = ''
        try {{ $heartbeatMac = Get-MacAddress }} catch {{}}
        try {{ $heartbeatIp = Get-PrimaryIPv4 }} catch {{}}
        if ($heartbeatMac) {{ $cfg['machine_mac'] = $heartbeatMac }}
        if ($heartbeatIp) {{ $cfg['machine_ip'] = $heartbeatIp }}
        $taskInfo = Get-AgentTaskInfo
        $heartbeatPayload = @{{
            mac = $heartbeatMac
            hostname = $env:COMPUTERNAME
            ip = $heartbeatIp
            timestamp = (Get-Date).ToString('o')
            status = @{{
                agent = @{{
                    version = $AgentVersion
                    machine_mac = $heartbeatMac
                    machine_ip = $heartbeatIp
                    hostname = $env:COMPUTERNAME
                    current_server_url = $cfg['current_server_url']
                    candidate_hosts = @($cfg['candidate_hosts'])
                    report_interval_sec = [int]$cfg['report_interval_sec']
                    config_updated_at = $cfg['config_updated_at']
                    last_config_sync_at = $cfg['last_config_sync_at']
                    last_discovery_at = $cfg['last_discovery_at']
                    ntp_enabled = [bool]$cfg['ntp_enabled']
                    ntp_primary = $cfg['ntp_primary']
                    ntp_fallback = $cfg['ntp_fallback']
                    last_ntp_check_at = $cfg['last_ntp_check_at']
                    ntp_configured_at = $cfg['ntp_configured_at']
                    ntp_last_result = $cfg['ntp_last_result']
                    task_name = $TaskName
                    task_exists = $taskInfo.exists
                    task_state = $taskInfo.state
                    task_user = $taskInfo.user
                    task_last_run_time = $taskInfo.last_run_time
                    task_next_run_time = $taskInfo.next_run_time
                    worker_path = $WorkerPath
                    launcher_path = $LauncherPath
                    heartbeat = $true
                    self_update = $script:SelfUpdateStatus
                    log_tail = Get-LogTail $LogPath 12
                }}
            }}
        }}
        $heartbeatPayload = ConvertTo-AgentJson $heartbeatPayload 8
        $heartbeatUrl = $cfg['current_server_url'].TrimEnd('/') + $cfg['report_path']
        Invoke-AgentJsonRequest -Uri $heartbeatUrl -Method Post -ContentType 'application/json' -Body $heartbeatPayload -TimeoutSec 5 | Out-Null
        Write-AgentLog ('heartbeat ok -> ' + $heartbeatUrl)
    }} catch {{
        Write-AgentLog ('heartbeat failed: ' + (Get-ErrorDetails $_))
    }}
}}

function Invoke-ExternalCommandCapture([string]$filePath, [string[]]$arguments, [int]$timeoutSec = 6) {{
    $result = @{{
        exit_code = 999
        timed_out = $false
        output = ''
        error = ''
    }}
    try {{
        if (-not $filePath -or -not (Test-Path $filePath)) {{
            $result.error = 'tool_not_found'
            return $result
        }}
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $filePath
        $safeArguments = @()
        foreach ($arg in @($arguments)) {{
            if ($null -eq $arg) {{ continue }}
            $argText = [System.Convert]::ToString($arg, [System.Globalization.CultureInfo]::InvariantCulture)
            if ([string]::IsNullOrWhiteSpace($argText)) {{ continue }}
            $safeArguments += $argText
        }}
        if ($safeArguments.Count -gt 0) {{
            $quotedArguments = @()
            foreach ($argText in $safeArguments) {{
                $quotedArguments += ('"' + ($argText -replace '"', '\\"') + '"')
            }}
            $psi.Arguments = ($quotedArguments -join ' ')
        }}
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $proc = New-Object System.Diagnostics.Process
        $proc.StartInfo = $psi
        [void]$proc.Start()
        if (-not $proc.WaitForExit([Math]::Max(1, $timeoutSec) * 1000)) {{
            $result.timed_out = $true
            try {{ $proc.Kill() }} catch {{}}
        }}
        try {{ $result.output = [string]$proc.StandardOutput.ReadToEnd() }} catch {{}}
        try {{ $result.error = [string]$proc.StandardError.ReadToEnd() }} catch {{}}
        try {{ $result.exit_code = [int]$proc.ExitCode }} catch {{}}
    }} catch {{
        $result.error = Get-ErrorDetails $_
    }}
    return $result
}}

function Get-AgentInstances([string]$className, [string]$filter = '') {{
    $items = $null
    $cim = Get-CommandOrNull 'Get-CimInstance'
    if ($cim) {{
        try {{
            if ($filter) {{
                $items = Get-CimInstance -ClassName $className -Filter $filter -ErrorAction Stop
            }} else {{
                $items = Get-CimInstance -ClassName $className -ErrorAction Stop
            }}
        }} catch {{}}
        if ($items) {{
            return $items
        }}
    }}
    $wmi = Get-CommandOrNull 'Get-WmiObject'
    if ($wmi) {{
        try {{
            if ($filter) {{
                $items = Get-WmiObject -Class $className -Filter $filter -ErrorAction Stop
            }} else {{
                $items = Get-WmiObject -Class $className -ErrorAction Stop
            }}
        }} catch {{}}
    }}
    return $items
}}

function Format-MacAddress([string]$raw) {{
    $text = [string]$raw
    if (-not $text) {{
        return ''
    }}
    $compact = ($text -replace '[^0-9A-Fa-f]', '').ToUpper()
    if ($compact.Length -ne 12) {{
        return ''
    }}
    return ($compact.Substring(0, 2) + '-' + $compact.Substring(2, 2) + '-' + $compact.Substring(4, 2) + '-' + $compact.Substring(6, 2) + '-' + $compact.Substring(8, 2) + '-' + $compact.Substring(10, 2))
}}

function Convert-ToHashtable([object]$obj) {{
    if ($null -eq $obj) {{ return $null }}
    if ($obj -is [string] -or $obj -is [char]) {{ return [string]$obj }}
    if ($obj -is [System.ValueType]) {{ return $obj }}
    if ($obj -is [System.Collections.IDictionary]) {{
        $hash = @{{}}
        foreach ($key in $obj.Keys) {{
            $hash[$key] = Convert-ToHashtable $obj[$key]
        }}
        return $hash
    }}
    if (($obj -is [System.Collections.IEnumerable]) -and -not ($obj -is [string])) {{
        $items = @()
        foreach ($item in $obj) {{
            $items += ,(Convert-ToHashtable $item)
        }}
        return $items
    }}
    if ($obj.PSObject -and $obj.PSObject.Properties.Count -gt 0) {{
        $hash = @{{}}
        foreach ($prop in $obj.PSObject.Properties) {{
            $hash[$prop.Name] = Convert-ToHashtable $prop.Value
        }}
        return $hash
    }}
    return $obj
}}

function Add-UniqueValue([System.Collections.ArrayList]$list, [hashtable]$seen, [object]$value) {{
    if ($null -eq $value) {{ return }}
    if (($value -is [System.Collections.IEnumerable]) -and -not ($value -is [string])) {{
        foreach ($item in $value) {{
            Add-UniqueValue $list $seen $item
        }}
        return
    }}
    $text = [string]$value
    if (-not $text) {{ return }}
    $text = $text.Trim()
    if (-not $text) {{ return }}
    if (-not $seen.ContainsKey($text)) {{
        $seen[$text] = $true
        [void]$list.Add($text)
    }}
}}

function Merge-UniqueList([object]$values) {{
    $list = New-Object System.Collections.ArrayList
    $seen = @{{}}
    Add-UniqueValue $list $seen $values
    return @($list)
}}

function Get-InitialAgentConfig() {{
    $json = @"
{initial_config_json}
"@
    return (Convert-ToHashtable ($json | ConvertFrom-Json))
}}

function Get-ConfigTextValue([object]$value, [string]$fallback = '') {{
    if ($null -eq $value) {{ return $fallback }}
    if ($value -is [string] -or $value -is [char]) {{
        $text = [string]$value
        if ($text.Trim()) {{
            return $text
        }}
        return $fallback
    }}
    if ($value -is [System.ValueType]) {{
        return [string]$value
    }}
    return $fallback
}}

function Get-ConfigStringListValue([object]$value) {{
    $items = @()
    if ($null -eq $value) {{
        return $items
    }}
    if (($value -is [System.Collections.IEnumerable]) -and -not ($value -is [string])) {{
        foreach ($item in $value) {{
            $text = Get-ConfigTextValue $item ''
            if ($text) {{
                $items += $text
            }}
        }}
        return @($items)
    }}
    $single = Get-ConfigTextValue $value ''
    if ($single) {{
        $items += $single
    }}
    return @($items)
}}

function Get-ConfigIntValue([object]$value, [int]$fallback) {{
    if ($null -eq $value) {{ return $fallback }}
    try {{
        return [int]$value
    }} catch {{
        return $fallback
    }}
}}

function New-AgentConfigObject([hashtable]$raw) {{
    $cfg = @{{}}
    if ($raw) {{
        foreach ($key in $raw.Keys) {{
            $cfg[$key] = $raw[$key]
        }}
    }}
    if (-not $cfg.ContainsKey('service') -or -not $cfg['service']) {{ $cfg['service'] = 'smart_center_agent' }}
    if (-not $cfg.ContainsKey('version') -or -not $cfg['version']) {{ $cfg['version'] = $AgentVersion }}
    if (-not $cfg.ContainsKey('server_port') -or -not $cfg['server_port']) {{ $cfg['server_port'] = 6899 }}
    if (-not $cfg.ContainsKey('report_path') -or -not $cfg['report_path']) {{ $cfg['report_path'] = '/report' }}
    if (-not $cfg.ContainsKey('config_path') -or -not $cfg['config_path']) {{ $cfg['config_path'] = '/agent/config' }}
    if (-not $cfg.ContainsKey('worker_path') -or -not $cfg['worker_path']) {{ $cfg['worker_path'] = '/agent/worker.json' }}
    if (-not $cfg.ContainsKey('launcher_path') -or -not $cfg['launcher_path']) {{ $cfg['launcher_path'] = '/agent/launcher.json' }}
    if (-not $cfg.ContainsKey('report_interval_sec') -or -not $cfg['report_interval_sec']) {{ $cfg['report_interval_sec'] = 60 }}
    if (-not $cfg.ContainsKey('sync_interval_sec') -or -not $cfg['sync_interval_sec']) {{ $cfg['sync_interval_sec'] = 60 }}
    if (-not $cfg.ContainsKey('discovery_retry_sec') -or -not $cfg['discovery_retry_sec']) {{ $cfg['discovery_retry_sec'] = 120 }}
    if (-not $cfg.ContainsKey('ntp_enabled')) {{ $cfg['ntp_enabled'] = $true }}
    if (-not $cfg.ContainsKey('ntp_primary') -or -not $cfg['ntp_primary']) {{ $cfg['ntp_primary'] = '192.168.50.120' }}
    if (-not $cfg.ContainsKey('ntp_fallback') -or -not $cfg['ntp_fallback']) {{ $cfg['ntp_fallback'] = '192.168.50.121' }}
    if (-not $cfg.ContainsKey('ntp_check_interval_sec') -or -not $cfg['ntp_check_interval_sec']) {{ $cfg['ntp_check_interval_sec'] = 3600 }}
    if (-not $cfg.ContainsKey('last_ntp_check_at')) {{ $cfg['last_ntp_check_at'] = '' }}
    if (-not $cfg.ContainsKey('ntp_configured_at')) {{ $cfg['ntp_configured_at'] = '' }}
    if (-not $cfg.ContainsKey('ntp_last_result')) {{ $cfg['ntp_last_result'] = '' }}
    $cfg['candidate_hosts'] = @(Merge-UniqueList @($cfg['server_host'], $cfg['candidate_hosts']))
    $cfg['scan_networks'] = @(Merge-UniqueList @($cfg['scan_networks']))
    if ((-not $cfg.ContainsKey('server_host') -or -not $cfg['server_host']) -and $cfg['candidate_hosts'].Count -gt 0) {{
        $cfg['server_host'] = $cfg['candidate_hosts'][0]
    }}
    if (-not $cfg.ContainsKey('current_server_url') -or -not $cfg['current_server_url']) {{
        if ($cfg['server_host']) {{
            $cfg['current_server_url'] = 'http://' + $cfg['server_host'] + ':' + $cfg['server_port']
        }} else {{
            $cfg['current_server_url'] = ''
        }}
    }}
    return $cfg
}}

function Save-AgentConfig([hashtable]$cfg) {{
    Write-TextFile $ConfigPath (ConvertTo-AgentJson $cfg 8)
}}

function Load-AgentConfig() {{
    $initial = New-AgentConfigObject (Get-InitialAgentConfig)
    if (Test-Path $ConfigPath) {{
        try {{
            $storedJson = (Get-Content $ConfigPath -Raw -Encoding UTF8) | ConvertFrom-Json
            $stored = @{{
                service = Get-ConfigTextValue $storedJson.service ''
                version = Get-ConfigTextValue $storedJson.version ''
                server_host = Get-ConfigTextValue $storedJson.server_host ''
                server_port = Get-ConfigIntValue $storedJson.server_port 0
                report_path = Get-ConfigTextValue $storedJson.report_path ''
                config_path = Get-ConfigTextValue $storedJson.config_path ''
                worker_path = Get-ConfigTextValue $storedJson.worker_path ''
                launcher_path = Get-ConfigTextValue $storedJson.launcher_path ''
                report_interval_sec = Get-ConfigIntValue $storedJson.report_interval_sec 0
                sync_interval_sec = Get-ConfigIntValue $storedJson.sync_interval_sec 0
                discovery_retry_sec = Get-ConfigIntValue $storedJson.discovery_retry_sec 0
                current_server_url = Get-ConfigTextValue $storedJson.current_server_url ''
                config_updated_at = Get-ConfigTextValue $storedJson.config_updated_at ''
                last_config_sync_at = Get-ConfigTextValue $storedJson.last_config_sync_at ''
                last_discovery_at = Get-ConfigTextValue $storedJson.last_discovery_at ''
                last_ntp_check_at = Get-ConfigTextValue $storedJson.last_ntp_check_at ''
                ntp_configured_at = Get-ConfigTextValue $storedJson.ntp_configured_at ''
                ntp_last_result = Get-ConfigTextValue $storedJson.ntp_last_result ''
                ntp_enabled = if ($null -ne $storedJson.ntp_enabled) {{ [bool]$storedJson.ntp_enabled }} else {{ $true }}
                ntp_primary = Get-ConfigTextValue $storedJson.ntp_primary ''
                ntp_fallback = Get-ConfigTextValue $storedJson.ntp_fallback ''
                ntp_check_interval_sec = Get-ConfigIntValue $storedJson.ntp_check_interval_sec 0
                updated_at = Get-ConfigTextValue $storedJson.updated_at ''
                candidate_hosts = @(Get-ConfigStringListValue $storedJson.candidate_hosts)
                scan_networks = @(Get-ConfigStringListValue $storedJson.scan_networks)
            }}
            return New-AgentConfigObject $stored
        }} catch {{
            Write-AgentLog ('load local config failed, fallback to defaults: ' + $_.Exception.Message)
        }}
    }}
    Save-AgentConfig $initial
    return $initial
}}

function Compare-VersionText([string]$left, [string]$right) {{
    try {{
        $leftParts = @(([string]$left -split '[^0-9]+') | Where-Object {{ $_ -ne '' }} | ForEach-Object {{ [int]$_ }})
        $rightParts = @(([string]$right -split '[^0-9]+') | Where-Object {{ $_ -ne '' }} | ForEach-Object {{ [int]$_ }})
        $max = [Math]::Max($leftParts.Count, $rightParts.Count)
        for ($idx = 0; $idx -lt $max; $idx++) {{
            $l = if ($idx -lt $leftParts.Count) {{ $leftParts[$idx] }} else {{ 0 }}
            $r = if ($idx -lt $rightParts.Count) {{ $rightParts[$idx] }} else {{ 0 }}
            if ($l -gt $r) {{ return 1 }}
            if ($l -lt $r) {{ return -1 }}
        }}
    }} catch {{}}
    return 0
}}

	function Invoke-AgentSelfUpdate([hashtable]$cfg, [hashtable]$incoming) {{
	    $checkedAt = (Get-Date).ToString('o')
	    if (-not $incoming -or -not $incoming.ContainsKey('version')) {{
	        $script:SelfUpdateStatus = @{{
	            checked_at = $checkedAt
	            local_version = $AgentVersion
	            remote_version = ''
	            action = 'skip_no_remote_version'
	            ok = $true
	        }}
	        return $false
	    }}
	    $remoteVersion = [string]$incoming['version']
	    if (-not $remoteVersion -or (Compare-VersionText $remoteVersion $AgentVersion) -le 0) {{
	        $script:SelfUpdateStatus = @{{
	            checked_at = $checkedAt
	            local_version = $AgentVersion
	            remote_version = $remoteVersion
	            action = 'skip_current'
	            ok = $true
	        }}
	        return $false
	    }}
	    $workerPathValue = if ($incoming.ContainsKey('worker_path') -and $incoming['worker_path']) {{ [string]$incoming['worker_path'] }} else {{ '/agent/worker.json' }}
	    $launcherPathValue = if ($incoming.ContainsKey('launcher_path') -and $incoming['launcher_path']) {{ [string]$incoming['launcher_path'] }} else {{ '/agent/launcher.json' }}
	    $baseUrl = if ($cfg['current_server_url']) {{ [string]$cfg['current_server_url'] }} else {{ 'http://' + $cfg['server_host'] + ':' + $cfg['server_port'] }}
	    if (-not $baseUrl) {{
	        $script:SelfUpdateStatus = @{{
	            checked_at = $checkedAt
	            local_version = $AgentVersion
	            remote_version = $remoteVersion
	            action = 'skip_no_server_url'
	            ok = $false
	        }}
	        return $false
	    }}
	    $workerUrl = $baseUrl.TrimEnd('/') + $workerPathValue + '?v=' + [uri]::EscapeDataString($remoteVersion) + '&ts=' + [uri]::EscapeDataString((Get-Date).Ticks)
	    $launcherUrl = $baseUrl.TrimEnd('/') + $launcherPathValue + '?v=' + [uri]::EscapeDataString($remoteVersion) + '&ts=' + [uri]::EscapeDataString((Get-Date).Ticks)
	    try {{
	        $response = Invoke-AgentJsonRequest -Uri $workerUrl -Method Get -TimeoutSec 15
	        $workerText = ''
        if ($response -and $response.worker_b64) {{
            $workerText = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String([string]$response.worker_b64))
        }}
        if (-not $workerText) {{
            $client = New-Object System.Net.WebClient
            $client.Headers.Add('Cache-Control', 'no-cache')
            $workerText = $client.DownloadString($workerUrl)
        }}
        if (-not $workerText -or $workerText -notmatch [regex]::Escape($remoteVersion)) {{
            throw 'downloaded worker version mismatch'
        }}
        $launcherText = ''
        try {{
            $launcherResponse = Invoke-AgentJsonRequest -Uri $launcherUrl -Method Get -TimeoutSec 12
            if ($launcherResponse -and $launcherResponse.launcher_b64) {{
                $launcherText = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String([string]$launcherResponse.launcher_b64))
            }}
        }} catch {{
            Write-AgentLog ('launcher self-update download failed, worker update will continue: ' + (Get-ErrorDetails $_))
        }}
        if ($launcherText -and $launcherText -notmatch [regex]::Escape($remoteVersion)) {{
            Write-AgentLog 'launcher self-update skipped: downloaded launcher version mismatch'
            $launcherText = ''
        }}
        $backupPath = $WorkerPath + '.bak_' + (Get-Date).ToString('yyyyMMddHHmmss')
	        if (Test-Path $WorkerPath) {{
	            Copy-Item -LiteralPath $WorkerPath -Destination $backupPath -Force -ErrorAction SilentlyContinue
	        }}
	        Write-TextFile $WorkerPath $workerText
	        $launcherBackupPath = ''
	        if ($launcherText) {{
	            $launcherBackupPath = $LauncherPath + '.bak_' + (Get-Date).ToString('yyyyMMddHHmmss')
	            if (Test-Path $LauncherPath) {{
	                Copy-Item -LiteralPath $LauncherPath -Destination $launcherBackupPath -Force -ErrorAction SilentlyContinue
	            }}
	            Write-TextFile $LauncherPath $launcherText
	        }}
	        $script:SelfUpdateStatus = @{{
	            checked_at = $checkedAt
	            local_version = $AgentVersion
	            remote_version = $remoteVersion
	            action = 'updated'
	            ok = $true
	            worker_url = $workerUrl
	            backup_path = $backupPath
	            launcher_url = $launcherUrl
	            launcher_updated = [bool]$launcherText
	            launcher_backup_path = $launcherBackupPath
	        }}
	        Write-AgentLog ('self-updated worker/launcher ' + $AgentVersion + ' -> ' + $remoteVersion + '; restart on next scheduled run')
	        return $true
	    }} catch {{
	        $errorText = Get-ErrorDetails $_
	        $script:SelfUpdateStatus = @{{
	            checked_at = $checkedAt
	            local_version = $AgentVersion
	            remote_version = $remoteVersion
	            action = 'failed'
	            ok = $false
	            worker_url = $workerUrl
	            error = $errorText
	        }}
	        Write-AgentLog ('self-update failed: ' + $errorText)
	        return $false
	    }}
	}}

function Merge-AgentConfig([hashtable]$cfg, [hashtable]$incoming) {{
    if (-not $incoming) {{ return $cfg }}
    foreach ($key in @('service','version','server_host','server_port','report_path','config_path','worker_path','launcher_path','report_interval_sec','sync_interval_sec','discovery_retry_sec','ntp_enabled','ntp_primary','ntp_fallback','ntp_check_interval_sec')) {{
        if ($incoming.ContainsKey($key) -and $null -ne $incoming[$key] -and [string]$incoming[$key] -ne '') {{
            $cfg[$key] = $incoming[$key]
        }}
    }}
    if ($incoming.ContainsKey('candidate_hosts')) {{
        $cfg['candidate_hosts'] = @(Merge-UniqueList @($incoming['candidate_hosts'], $cfg['candidate_hosts'], $incoming['server_host'], $cfg['server_host']))
    }} else {{
        $cfg['candidate_hosts'] = @(Merge-UniqueList @($cfg['candidate_hosts'], $cfg['server_host']))
    }}
    if ($incoming.ContainsKey('scan_networks')) {{
        $cfg['scan_networks'] = @(Merge-UniqueList @($incoming['scan_networks'], $cfg['scan_networks']))
    }} else {{
        $cfg['scan_networks'] = @(Merge-UniqueList @($cfg['scan_networks']))
    }}
    if ((-not $cfg['server_host']) -and $cfg['candidate_hosts'].Count -gt 0) {{
        $cfg['server_host'] = $cfg['candidate_hosts'][0]
    }}
    if ($cfg['server_host']) {{
        $cfg['current_server_url'] = 'http://' + $cfg['server_host'] + ':' + $cfg['server_port']
    }}
    $cfg['config_updated_at'] = (Get-Date).ToString('o')
    return $cfg
}}

function Get-NtpPeerList([hashtable]$cfg) {{
    $peers = @()
    foreach ($peer in @($cfg['ntp_primary'], $cfg['ntp_fallback'])) {{
        $text = [string]$peer
        if ($text -and $text.Trim()) {{
            $peers += ($text.Trim() + ',0x8')
        }}
    }}
    return (($peers | Select-Object -Unique) -join ' ')
}}

function Get-WindowsTimePeerList {{
    try {{
        $raw = (& w32tm /query /configuration 2>&1 | Out-String)
        $match = [regex]::Match($raw, 'NtpServer:\\s*(.+?)(?:\\s+\\(|\\r?\\n)')
        if ($match.Success) {{
            return $match.Groups[1].Value.Trim()
        }}
    }} catch {{}}
    return ''
}}

function Test-NtpPeerConfigured([string]$currentPeerList, [string]$desiredPeerList) {{
    $current = [string]$currentPeerList
    $desired = [string]$desiredPeerList
    if (-not $desired) {{ return $true }}
    foreach ($part in @($desired -split '\\s+')) {{
        $peerHost = ([string]$part).Split(',')[0]
        if ($peerHost -and $current -notmatch [regex]::Escape($peerHost)) {{
            return $false
        }}
    }}
    return $true
}}

function Invoke-NtpAutoConfigure([hashtable]$cfg) {{
    if (-not [bool]$cfg['ntp_enabled']) {{ return $cfg }}
    $desiredPeerList = Get-NtpPeerList $cfg
    if (-not $desiredPeerList) {{ return $cfg }}
    $intervalSec = Get-ConfigIntValue $cfg['ntp_check_interval_sec'] 3600
    if ($intervalSec -lt 300) {{ $intervalSec = 300 }}
    $shouldCheck = $true
    if ($cfg['last_ntp_check_at']) {{
        try {{
            $shouldCheck = (((Get-Date) - [datetime]::Parse([string]$cfg['last_ntp_check_at'])).TotalSeconds -ge $intervalSec)
        }} catch {{
            $shouldCheck = $true
        }}
    }}
    if (-not $cfg['ntp_configured_at']) {{
        $shouldCheck = $true
    }}
    if ([string]$cfg['ntp_last_result'] -like 'error*') {{
        $shouldCheck = $true
    }}
    if (-not $shouldCheck) {{ return $cfg }}
    $cfg['last_ntp_check_at'] = (Get-Date).ToString('o')
    try {{
        if (-not (Get-CommandOrNull 'w32tm')) {{
            throw 'w32tm not found'
        }}
        $currentPeerList = Get-WindowsTimePeerList
        $needsConfigure = -not (Test-NtpPeerConfigured $currentPeerList $desiredPeerList)
        try {{ Set-Service w32time -StartupType Automatic -ErrorAction SilentlyContinue }} catch {{}}
        try {{ Start-Service w32time -ErrorAction SilentlyContinue }} catch {{}}
        if ($needsConfigure) {{
            & w32tm /config /manualpeerlist:$desiredPeerList /syncfromflags:manual /reliable:no /update | Out-Null
            try {{ Restart-Service w32time -Force -ErrorAction SilentlyContinue }} catch {{}}
            $cfg['ntp_configured_at'] = (Get-Date).ToString('o')
            Write-AgentLog ('ntp configured peers=' + $desiredPeerList)
        }}
        try {{ & w32tm /resync /force | Out-Null }} catch {{}}
        $source = ''
        try {{ $source = ((& w32tm /query /source 2>&1 | Out-String).Trim()) }} catch {{}}
        $cfg['ntp_last_result'] = ('ok peers=' + $desiredPeerList + ' source=' + $source)
    }} catch {{
        $cfg['ntp_last_result'] = 'error ' + (Get-ErrorDetails $_)
        Write-AgentLog ('ntp auto-config failed: ' + (Get-ErrorDetails $_))
    }}
    return $cfg
}}

function Convert-IPv4ToUInt([string]$ip) {{
    $bytes = [System.Net.IPAddress]::Parse($ip).GetAddressBytes()
    [array]::Reverse($bytes)
    return [BitConverter]::ToUInt32($bytes, 0)
}}

function Convert-UIntToIPv4([uint32]$value) {{
    $bytes = [BitConverter]::GetBytes([uint32]$value)
    [array]::Reverse($bytes)
    return ([System.Net.IPAddress]::new($bytes)).ToString()
}}

function Get-LocalDiscoveryNetworks() {{
    $networks = @()
    try {{
        $ipv4 = Get-PrimaryIPv4
        if ($ipv4) {{
            $parts = $ipv4.Split('.')
            if ($parts.Count -eq 4) {{
                $networks += ($parts[0] + '.' + $parts[1] + '.' + $parts[2] + '.0/24')
            }}
        }}
    }} catch {{}}
    return @(Merge-UniqueList $networks)
}}

function Get-NetworkHosts([string]$networkText) {{
    $networkText = [string]$networkText
    if (-not $networkText) {{ return @() }}
    $parts = $networkText.Split('/')
    if ($parts.Count -ne 2) {{ return @() }}
    try {{
        $prefix = [int]$parts[1]
        if ($prefix -lt 16 -or $prefix -gt 30) {{ return @() }}
        $base = Convert-IPv4ToUInt $parts[0]
        $hostBits = 32 - $prefix
        $mask = [uint32]0xFFFFFFFF
        if ($hostBits -gt 0) {{
            $mask = [uint32]($mask -shl $hostBits)
        }}
        $networkBase = [uint32]($base -band $mask)
        $maxHosts = [Math]::Min([Math]::Pow(2, $hostBits) - 2, 254)
        $hosts = @()
        for ($i = 1; $i -le $maxHosts; $i++) {{
            $hosts += (Convert-UIntToIPv4 ([uint32]($networkBase + $i)))
        }}
        return $hosts
    }} catch {{
        return @()
    }}
}}

function Get-AgentTaskInfo() {{
    if ($script:TaskInfoCache -and $script:LastTaskInfoAt -and ((Get-Date) - $script:LastTaskInfoAt).TotalSeconds -lt 30) {{
        return $script:TaskInfoCache
    }}
    $info = @{{
        exists = $false
        state = 'unknown'
        user = ''
        last_run_time = ''
        next_run_time = ''
    }}
    try {{
        $schedule = New-Object -ComObject 'Schedule.Service'
        $schedule.Connect()
        $rootFolder = $schedule.GetFolder('\\')
        $task = $null
        try {{
            $task = $rootFolder.GetTask('\\' + $TaskName)
        }} catch {{
            try {{
                $task = $rootFolder.GetTask($TaskName)
            }} catch {{}}
        }}
        if ($task) {{
            $stateMap = @{{
                0 = 'unknown'
                1 = 'disabled'
                2 = 'queued'
                3 = 'ready'
                4 = 'running'
            }}
            $stateValue = 0
            try {{
                $stateValue = [int]$task.State
            }} catch {{}}
            $info.exists = $true
            $info.state = if ($stateMap.ContainsKey($stateValue)) {{ $stateMap[$stateValue] }} else {{ [string]$task.State }}
            try {{
                if ($task.Definition -and $task.Definition.Principal) {{
                    $info.user = [string]$task.Definition.Principal.UserId
                }}
            }} catch {{}}
            try {{
                $lastRun = [datetime]$task.LastRunTime
                if ($lastRun.Year -ge 2000) {{
                    $info.last_run_time = $lastRun.ToString('o')
                }}
            }} catch {{}}
            try {{
                $nextRun = [datetime]$task.NextRunTime
                if ($nextRun.Year -ge 2000) {{
                    $info.next_run_time = $nextRun.ToString('o')
                }}
            }} catch {{}}
        }}
        if (-not $info.exists) {{
        if (Get-CommandOrNull 'Get-ScheduledTask') {{
            $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            if ($task) {{
                $taskInfo = $null
                if (Get-CommandOrNull 'Get-ScheduledTaskInfo') {{
                    $taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
                }}
                $info.exists = $true
                $info.state = [string]$task.State
                $info.user = if ($task.Principal) {{ [string]$task.Principal.UserId }} else {{ '' }}
                $info.last_run_time = if ($taskInfo -and $taskInfo.LastRunTime) {{ $taskInfo.LastRunTime.ToString('o') }} else {{ '' }}
                $info.next_run_time = if ($taskInfo -and $taskInfo.NextRunTime) {{ $taskInfo.NextRunTime.ToString('o') }} else {{ '' }}
            }}
        }}
        }}
    }} catch {{}}
    $script:LastTaskInfoAt = Get-Date
    $script:TaskInfoCache = $info
    return $info
}}

function Invoke-AgentConfigProbe([string]$serverUrl, [hashtable]$cfg) {{
    if (-not $serverUrl) {{ return $null }}
    try {{
        $uri = $serverUrl.TrimEnd('/') + $cfg['config_path'] + '?probe=1'
        $response = Invoke-AgentJsonRequest -Uri $uri -Method Get -TimeoutSec 2
        $incoming = $null
        if ($response -and $response.agent_config) {{
            $incoming = Convert-ToHashtable $response.agent_config
        }} elseif ($response -and $response.service -eq 'smart_center_agent') {{
            $incoming = Convert-ToHashtable $response
        }}
        if ($incoming) {{
            if (-not $incoming.ContainsKey('server_host') -or -not $incoming['server_host']) {{
                try {{
                    $incoming['server_host'] = ([uri]$serverUrl).Host
                }} catch {{}}
            }}
            return $incoming
        }}
    }} catch {{}}
    return $null
}}

function Find-AvailableServer([hashtable]$cfg, [switch]$ForceDiscovery) {{
    $urls = @()
    if ($cfg['current_server_url']) {{
        $urls += $cfg['current_server_url']
    }}
    foreach ($candidateHost in @($cfg['candidate_hosts'])) {{
        if ($candidateHost) {{
            $urls += ('http://' + $candidateHost + ':' + $cfg['server_port'])
        }}
    }}
    $urls = @(Merge-UniqueList $urls)
    foreach ($url in $urls) {{
        $incoming = Invoke-AgentConfigProbe $url $cfg
        if ($incoming) {{
            $cfg['current_server_url'] = $url.TrimEnd('/')
            if (Invoke-AgentSelfUpdate $cfg $incoming) {{
                exit 0
            }}
            Merge-AgentConfig $cfg $incoming | Out-Null
            $cfg['last_config_sync_at'] = (Get-Date).ToString('o')
            Save-AgentConfig $cfg
            return $cfg
        }}
    }}

    $shouldDiscover = $ForceDiscovery
    if (-not $shouldDiscover) {{
        if (-not $cfg['last_discovery_at']) {{
            $shouldDiscover = $true
        }} else {{
            try {{
                $shouldDiscover = ((Get-Date) - [datetime]::Parse($cfg['last_discovery_at'])).TotalSeconds -ge [int]$cfg['discovery_retry_sec']
            }} catch {{
                $shouldDiscover = $true
            }}
        }}
    }}
    if (-not $shouldDiscover) {{
        return $cfg
    }}

    $cfg['last_discovery_at'] = (Get-Date).ToString('o')
    $networks = @(Merge-UniqueList @($cfg['scan_networks'], (Get-LocalDiscoveryNetworks)))
    foreach ($network in $networks) {{
        foreach ($candidateIp in Get-NetworkHosts $network) {{
            if ($candidateIp -eq (Get-PrimaryIPv4)) {{ continue }}
            $url = 'http://' + $candidateIp + ':' + $cfg['server_port']
            $incoming = Invoke-AgentConfigProbe $url $cfg
            if ($incoming) {{
                $cfg['current_server_url'] = $url.TrimEnd('/')
                if (Invoke-AgentSelfUpdate $cfg $incoming) {{
                    exit 0
                }}
                Merge-AgentConfig $cfg $incoming | Out-Null
                $cfg['last_config_sync_at'] = (Get-Date).ToString('o')
                Save-AgentConfig $cfg
                Write-AgentLog ('discovered control server: ' + $cfg['current_server_url'])
                return $cfg
            }}
        }}
    }}
    Save-AgentConfig $cfg
    return $cfg
}}

function Get-MacAddress {{
    try {{
        $adapters = @(Get-AgentInstances 'Win32_NetworkAdapterConfiguration') | Where-Object {{
            $_.IPEnabled -eq $true -and $_.MACAddress -and $_.IPAddress
        }}
        $adapter = $adapters | Sort-Object -Property IPConnectionMetric, InterfaceIndex | Select-Object -First 1
        if ($adapter) {{
            return (Format-MacAddress ([string]$adapter.MACAddress))
        }}
    }} catch {{}}
    try {{
        $adapters = @(Get-AgentInstances 'Win32_NetworkAdapterConfiguration') | Where-Object {{
            $_.MACAddress
        }}
        $adapter = $adapters | Sort-Object -Property IPEnabled, IPConnectionMetric, InterfaceIndex -Descending | Select-Object -First 1
        if ($adapter) {{
            return (Format-MacAddress ([string]$adapter.MACAddress))
        }}
    }} catch {{}}
    try {{
        $interfaces = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() | Where-Object {{
            $_.OperationalStatus -eq [System.Net.NetworkInformation.OperationalStatus]::Up -and
            $_.GetPhysicalAddress() -and
            $_.GetPhysicalAddress().ToString()
        }}
        foreach ($iface in $interfaces) {{
            $formatted = Format-MacAddress ($iface.GetPhysicalAddress().ToString())
            if ($formatted) {{
                return $formatted
            }}
        }}
    }} catch {{}}
    try {{
        if (Test-Path $ConfigPath) {{
            $storedJson = (Get-Content $ConfigPath -Raw -Encoding UTF8) | ConvertFrom-Json
            $storedMac = Format-MacAddress ([string]$storedJson.machine_mac)
            if ($storedMac) {{ return $storedMac }}
        }}
    }} catch {{}}
    return ''
}}

function Get-PrimaryIPv4 {{
    try {{
        $adapters = @(Get-AgentInstances 'Win32_NetworkAdapterConfiguration') | Where-Object {{
            $_.IPEnabled -eq $true -and $_.IPAddress
        }}
        foreach ($adapter in @($adapters | Sort-Object -Property IPConnectionMetric, InterfaceIndex)) {{
            $ipv4 = $adapter.IPAddress | Where-Object {{ $_ -match '^\\d+\\.\\d+\\.\\d+\\.\\d+$' -and $_ -notlike '169.254.*' -and $_ -ne '127.0.0.1' }} | Select-Object -First 1
            if ($ipv4) {{ return $ipv4 }}
        }}
    }} catch {{}}
    try {{
        $interfaces = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() | Where-Object {{
            $_.OperationalStatus -eq [System.Net.NetworkInformation.OperationalStatus]::Up
        }}
        foreach ($iface in $interfaces) {{
            foreach ($uni in $iface.GetIPProperties().UnicastAddresses) {{
                $addr = [string]$uni.Address
                if ($uni.Address.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and $addr -notlike '169.254.*') {{
                    return $addr
                }}
            }}
        }}
    }} catch {{}}
    try {{
        $dnsName = [System.Net.Dns]::GetHostName()
        $addresses = [System.Net.Dns]::GetHostAddresses($dnsName) | Where-Object {{
            $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and
            ([string]$_) -notlike '169.254.*' -and
            ([string]$_) -ne '127.0.0.1'
        }}
        $addr = $addresses | Select-Object -First 1
        if ($addr) {{ return [string]$addr }}
    }} catch {{}}
    return ''
}}

function Get-NetSpeed {{
    $primaryIp = Get-PrimaryIPv4
    $selected = $null
    $candidates = @()
    $totalSent = 0.0
    $totalRecv = 0.0
    $adapterId = 'unknown'
    $adapterName = ''
    $adapterDescription = ''
    $adapterIp = ''
    $linkSpeedMbps = 0.0
    $sampleScope = 'primary_interface'
    $virtualNamePattern = 'Loopback|Teredo|ISATAP|Tunnel|Pseudo|虚拟|隧道|Hyper-V|vEthernet|VMware|VirtualBox|Npcap|Bluetooth|ZeroTier|Tailscale|Wintun|WireGuard'
    try {{
        $interfaces = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() | Where-Object {{
            $_.OperationalStatus -eq [System.Net.NetworkInformation.OperationalStatus]::Up -and
            $_.NetworkInterfaceType -ne [System.Net.NetworkInformation.NetworkInterfaceType]::Loopback -and
            $_.NetworkInterfaceType -ne [System.Net.NetworkInformation.NetworkInterfaceType]::Tunnel
        }}
        foreach ($iface in @($interfaces)) {{
            try {{
                $name = [string]$iface.Name
                $desc = [string]$iface.Description
                if (($name + ' ' + $desc) -match $virtualNamePattern) {{ continue }}
                $props = $iface.GetIPProperties()
                $ipv4 = ''
                foreach ($uni in @($props.UnicastAddresses)) {{
                    $addr = [string]$uni.Address
                    if ($uni.Address.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and $addr -notlike '169.254.*' -and $addr -ne '127.0.0.1') {{
                        $ipv4 = $addr
                        break
                    }}
                }}
                if (-not $ipv4) {{ continue }}
                $speed = [double]$iface.Speed
                $score = 0
                if ($primaryIp -and $ipv4 -eq $primaryIp) {{ $score += 1000 }}
                if ($iface.NetworkInterfaceType -eq [System.Net.NetworkInformation.NetworkInterfaceType]::Ethernet) {{ $score += 100 }}
                elseif ($iface.NetworkInterfaceType -eq [System.Net.NetworkInformation.NetworkInterfaceType]::Wireless80211) {{ $score += 80 }}
                if ($speed -gt 0) {{ $score += [math]::Min(50, [math]::Floor($speed / 1000000000)) }}
                $candidates += [pscustomobject]@{{
                    Interface = $iface
                    Id = [string]$iface.Id
                    Name = $name
                    Description = $desc
                    IPv4 = $ipv4
                    Speed = $speed
                    Score = $score
                }}
            }} catch {{}}
        }}
        if ($candidates.Count -gt 0) {{
            $selected = $candidates | Sort-Object -Property @{{Expression='Score';Descending=$true}}, @{{Expression='Speed';Descending=$true}} | Select-Object -First 1
            if ($primaryIp) {{
                $primaryCandidate = $candidates | Where-Object {{ $_.IPv4 -eq $primaryIp }} | Sort-Object -Property @{{Expression='Speed';Descending=$true}} | Select-Object -First 1
                if ($primaryCandidate) {{ $selected = $primaryCandidate }}
            }}
        }}
        if ($selected) {{
            $stats = $selected.Interface.GetIPv4Statistics()
            $totalSent = [double]$stats.BytesSent
            $totalRecv = [double]$stats.BytesReceived
            $adapterId = [string]$selected.Id
            $adapterName = [string]$selected.Name
            $adapterDescription = [string]$selected.Description
            $adapterIp = [string]$selected.IPv4
            if ([double]$selected.Speed -gt 0) {{ $linkSpeedMbps = [math]::Round(([double]$selected.Speed) / 1000000, 0) }}
        }}
    }} catch {{}}
    if ((-not $selected) -or (($totalSent -le 0) -and ($totalRecv -le 0))) {{
        $sampleScope = 'non_virtual_total'
        $adapterId = 'fallback-total'
        $adapterName = '物理网卡合计'
        $adapterDescription = ''
        $adapterIp = $primaryIp
        $totalSent = 0.0
        $totalRecv = 0.0
        foreach ($counter in @(Get-AgentInstances 'Win32_PerfRawData_Tcpip_NetworkInterface')) {{
            $name = [string]$counter.Name
            if ($name -match $virtualNamePattern) {{ continue }}
            $totalSent += [double]$counter.BytesSentPersec
            $totalRecv += [double]$counter.BytesReceivedPersec
        }}
    }}

    $now = Get-Date
    $nowIso = $now.ToString('o')
    $sendKb = 0.0
    $recvKb = 0.0
    $previous = $null
    try {{
        if (Test-Path $NetSamplePath) {{
            $previous = Get-Content $NetSamplePath -Raw -Encoding UTF8 | ConvertFrom-Json
        }}
    }} catch {{
        $previous = $null
    }}
    if ($previous -and $previous.sampled_at) {{
        try {{
            $prevTime = [datetime]::Parse([string]$previous.sampled_at)
            $seconds = ($now - $prevTime).TotalSeconds
            $sentDelta = $totalSent - [double]$previous.bytes_sent
            $recvDelta = $totalRecv - [double]$previous.bytes_recv
            $sameAdapter = (([string]$previous.adapter_id) -eq $adapterId)
            if ($seconds -gt 0 -and $seconds -lt 7200 -and $sentDelta -ge 0 -and $recvDelta -ge 0 -and $sameAdapter) {{
                $sendKb = [math]::Round(($sentDelta / $seconds) / 1KB, 1)
                $recvKb = [math]::Round(($recvDelta / $seconds) / 1KB, 1)
            }}
        }} catch {{}}
    }}
    $sample = @{{
        sampled_at = $nowIso
        bytes_sent = [math]::Round($totalSent, 0)
        bytes_recv = [math]::Round($totalRecv, 0)
        adapter_id = $adapterId
        adapter_name = $adapterName
        adapter_description = $adapterDescription
        adapter_ip = $adapterIp
        link_speed_mbps = $linkSpeedMbps
        sample_scope = $sampleScope
    }}
    try {{
        Write-TextFile $NetSamplePath (ConvertTo-AgentJson $sample 4)
    }} catch {{
        Write-AgentLog ('network sample save failed: ' + (Get-ErrorDetails $_))
    }}
    $script:lastNetBytesSent = $totalSent
    $script:lastNetBytesRecv = $totalRecv
    $script:lastNetSampleTime = $now
    $effectiveErrors = @($errors)
    if ($serials.Count -gt 0) {{
        $effectiveErrors = @($effectiveErrors | Where-Object {{ [string]$_ -notmatch '(?i)CodeMeter command timed out' }})
    }}
    return @{{
        sent_kb_s = $sendKb
        recv_kb_s = $recvKb
        adapter_id = $adapterId
        adapter_name = $adapterName
        adapter_description = $adapterDescription
        adapter_ip = $adapterIp
        link_speed_mbps = $linkSpeedMbps
        sample_scope = $sampleScope
    }}
}}

function Get-NvidiaSmiPath {{
    try {{
        $cmd = Get-Command 'nvidia-smi.exe' -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) {{
            return [string]$cmd.Source
        }}
    }} catch {{}}
    foreach ($candidate in @(
        (Join-Path $env:ProgramFiles 'NVIDIA Corporation\\NVSMI\\nvidia-smi.exe'),
        (Join-Path ${{env:ProgramFiles(x86)}} 'NVIDIA Corporation\\NVSMI\\nvidia-smi.exe'),
        'C:\\Windows\\System32\\nvidia-smi.exe'
    )) {{
        try {{
            if ($candidate -and (Test-Path $candidate)) {{
                return [string]$candidate
            }}
        }} catch {{}}
    }}
    return ''
}}

function Get-NvidiaGpuInfo {{
    $gpuList = @()
    $smiPath = Get-NvidiaSmiPath
    if (-not $smiPath) {{
        return @()
    }}
    try {{
        $capture = Invoke-ExternalCommandCapture -FilePath $smiPath -Arguments ([string[]]@('--query-gpu=index,name,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits')) -TimeoutSec 6
        if ($capture.timed_out) {{
            Write-AgentLog 'nvidia-smi gpu query timed out'
            return @()
        }}
        if ($capture.exit_code -ne 0 -and $capture.error) {{
            Write-AgentLog ('nvidia-smi gpu query failed: ' + [string]$capture.error)
        }}
        $lines = @(([string]$capture.output) -split "`r?`n" | Where-Object {{ $_ -and $_.Trim() }})
        foreach ($line in $lines) {{
            $parts = @([string]$line -split ',')
            if ($parts.Count -lt 4) {{
                continue
            }}
            $idx = 0
            $util = 0
            $temp = 0
            [int]::TryParse($parts[0].Trim(), [ref]$idx) | Out-Null
            [double]$utilDouble = 0
            [double]$tempDouble = 0
            [double]::TryParse($parts[2].Trim(), [ref]$utilDouble) | Out-Null
            [double]::TryParse($parts[3].Trim(), [ref]$tempDouble) | Out-Null
            $util = [int][math]::Round($utilDouble)
            $temp = [int][math]::Round($tempDouble)
            $gpuList += @{{
                index = $idx
                name = $parts[1].Trim()
                util_percent = $util
                temp = $temp
                source = 'nvidia-smi'
            }}
        }}
    }} catch {{
        Write-AgentLog ('nvidia-smi gpu query failed: ' + $_.Exception.Message)
    }}
    return @($gpuList)
}}

function Get-DxgkGpuPerfData {{
    $items = @()
    $script:GpuProbeDiagnostic['dxgk_checked_at'] = (Get-Date).ToString('o')
    if (-not (Get-CommandOrNull 'Add-Type')) {{
        $script:GpuProbeDiagnostic['dxgk_error'] = 'Add-Type unavailable'
        return @()
    }}
    try {{
        if (-not ('SmartCenterGpuPerfReader' -as [type])) {{
            $source = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public class SmartCenterGpuPerfReader {{
    [StructLayout(LayoutKind.Sequential)]
    public struct LUID {{
        public uint LowPart;
        public int HighPart;
    }}

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct DISPLAY_DEVICE {{
        public int cb;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string DeviceName;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string DeviceString;
        public int StateFlags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string DeviceID;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string DeviceKey;
    }}

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct D3DKMT_OPENADAPTERFROMGDIDISPLAYNAME {{
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string DeviceName;
        public uint hAdapter;
        public LUID AdapterLuid;
        public uint VidPnSourceId;
    }}

    [StructLayout(LayoutKind.Sequential)]
    public struct D3DKMT_CLOSEADAPTER {{
        public uint hAdapter;
    }}

    [StructLayout(LayoutKind.Sequential)]
    public struct D3DKMT_QUERYADAPTERINFO {{
        public uint hAdapter;
        public int Type;
        public IntPtr pPrivateDriverData;
        public uint PrivateDriverDataSize;
    }}

    [StructLayout(LayoutKind.Sequential)]
    public struct D3DKMT_ADAPTER_PERFDATA {{
        public uint PhysicalAdapterIndex;
        public ulong MemoryFrequency;
        public ulong MaxMemoryFrequency;
        public ulong MaxMemoryFrequencyOC;
        public ulong MemoryBandwidth;
        public ulong PCIEBandwidth;
        public uint FanRPM;
        public uint Power;
        public uint Temperature;
        public byte PowerStateOverride;
    }}

    [StructLayout(LayoutKind.Sequential)]
    public struct D3DKMT_ADAPTERINFO {{
        public uint hAdapter;
        public LUID AdapterLuid;
        public uint NumOfSources;
        [MarshalAs(UnmanagedType.Bool)]
        public bool bPrecisePresentRegionsPreferred;
    }}

    [StructLayout(LayoutKind.Sequential)]
    public struct D3DKMT_ENUMADAPTERS2 {{
        public uint NumAdapters;
        public IntPtr pAdapters;
    }}

    [StructLayout(LayoutKind.Sequential)]
    public struct D3DKMT_ADAPTERADDRESS {{
        public uint BusNumber;
        public uint DeviceNumber;
        public uint FunctionNumber;
    }}

    public class GpuPerfResult {{
        public string DeviceName;
        public string Name;
        public string Luid;
        public int QueryType;
        public int QueryStatus;
        public int RawTemperature;
        public int BusNumber;
        public int DeviceNumber;
        public int FunctionNumber;
        public int Utilization;
        public int Temperature;
        public int FanRPM;
        public int Power;
    }}

    public class GpuPerfDiagnostic {{
        public string DeviceName;
        public string Name;
        public string Luid;
        public int OpenStatus;
        public int QueryType;
        public int QueryStatus;
        public int RawTemperature;
        public int AddressStatus;
        public int BusNumber;
        public int DeviceNumber;
        public int FunctionNumber;
        public int Utilization;
        public int Temperature;
        public int FanRPM;
        public int Power;
    }}

    public static List<GpuPerfDiagnostic> Diagnostics = new List<GpuPerfDiagnostic>();
    public static int GdiDisplayCount = 0;
    public static int EnumAdapters2Status = 0;
    public static int EnumAdapters2Count = 0;
	    public static int EnumAdapters2Returned = 0;
	    public static int EngineCounterInstanceCount = 0;
	    public static int EngineCounterLuidCount = 0;
	    public static int EngineMaxUtilization = 0;
	    public static int EngineTotalUtilization = 0;
	    public static string EngineLuidSummary = "";

    private static string NormalizeLuid(LUID luid) {{
        return "luid_0x" + ((ulong)luid.HighPart & 0xffffffffUL).ToString("x8") + "_0x" + luid.LowPart.ToString("x8");
    }}

	    private static Dictionary<string, int> ReadGpuEngineUtilizationByLuid() {{
	        EngineCounterInstanceCount = 0;
	        EngineCounterLuidCount = 0;
	        Dictionary<string, double> engineTotals = new Dictionary<string, double>(StringComparer.OrdinalIgnoreCase);
	        int observedCounterCount = 0;
	        try {{
	            var category = new System.Diagnostics.PerformanceCounterCategory("GPU Engine");
	            List<System.Diagnostics.PerformanceCounter> counters = new List<System.Diagnostics.PerformanceCounter>();
	            List<string> counterLuids = new List<string>();
            foreach (string instance in category.GetInstanceNames()) {{
                if (String.IsNullOrWhiteSpace(instance)) continue;
	                string lower = instance.ToLowerInvariant();
	                var luidMatch = System.Text.RegularExpressions.Regex.Match(lower, @"luid_0x[0-9a-f]+_0x[0-9a-f]+");
	                if (!luidMatch.Success) continue;
	                string luidPart = luidMatch.Value;
                try {{
                    var counter = new System.Diagnostics.PerformanceCounter("GPU Engine", "Utilization Percentage", instance, true);
                    counter.NextValue();
	                    counters.Add(counter);
	                    counterLuids.Add(luidPart);
	                }} catch {{
	                    continue;
	                }}
	            }}
	            observedCounterCount = counters.Count;
	            if (counters.Count > 0) {{
	                System.Threading.Thread.Sleep(200);
	            }}
            for (int idx = 0; idx < counters.Count; idx++) {{
                double value = 0.0;
                try {{
                    value = counters[idx].NextValue();
                }} catch {{
                    value = 0.0;
                }}
                try {{ counters[idx].Dispose(); }} catch {{}}
                if (value <= 0.0) continue;
                string luidPart = counterLuids[idx];
                if (!engineTotals.ContainsKey(luidPart)) engineTotals[luidPart] = 0.0;
                engineTotals[luidPart] += value;
            }}
        }} catch {{
        }}
	        Dictionary<string, int> result = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
	        int maxUtil = 0;
	        int totalUtil = 0;
	        List<string> summaries = new List<string>();
	        foreach (var item in engineTotals) {{
	            int rounded = (int)Math.Round(item.Value);
	            if (rounded < 0) rounded = 0;
	            if (rounded > 100) rounded = 100;
	            result[item.Key] = rounded;
	            if (rounded > maxUtil) maxUtil = rounded;
	            totalUtil += rounded;
	            if (summaries.Count < 8) summaries.Add(item.Key + "=" + rounded.ToString());
	        }}
	        EngineCounterInstanceCount = observedCounterCount;
	        EngineCounterLuidCount = result.Count;
	        EngineMaxUtilization = maxUtil;
	        EngineTotalUtilization = totalUtil > 100 ? 100 : totalUtil;
	        EngineLuidSummary = String.Join(",", summaries.ToArray());
	        return result;
	    }}

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern bool EnumDisplayDevices(string lpDevice, uint iDevNum, ref DISPLAY_DEVICE lpDisplayDevice, uint dwFlags);

    [DllImport("gdi32.dll", EntryPoint = "D3DKMTOpenAdapterFromGdiDisplayName")]
    public static extern int D3DKMTOpenAdapterFromGdiDisplayName(ref D3DKMT_OPENADAPTERFROMGDIDISPLAYNAME data);

    [DllImport("gdi32.dll", EntryPoint = "D3DKMTQueryAdapterInfo")]
    public static extern int D3DKMTQueryAdapterInfo(ref D3DKMT_QUERYADAPTERINFO data);

    [DllImport("gdi32.dll", EntryPoint = "D3DKMTCloseAdapter")]
    public static extern int D3DKMTCloseAdapter(ref D3DKMT_CLOSEADAPTER data);

    [DllImport("gdi32.dll", EntryPoint = "D3DKMTEnumAdapters2")]
    public static extern int D3DKMTEnumAdapters2(ref D3DKMT_ENUMADAPTERS2 data);

    private static int QueryAdapterAddress(uint hAdapter, out D3DKMT_ADAPTERADDRESS address) {{
        address = new D3DKMT_ADAPTERADDRESS();
        int size = Marshal.SizeOf(typeof(D3DKMT_ADAPTERADDRESS));
        IntPtr ptr = Marshal.AllocHGlobal(size);
        try {{
            Marshal.StructureToPtr(address, ptr, false);
            D3DKMT_QUERYADAPTERINFO query = new D3DKMT_QUERYADAPTERINFO();
            query.hAdapter = hAdapter;
            query.Type = 6;
            query.pPrivateDriverData = ptr;
            query.PrivateDriverDataSize = (uint)size;
            int status = D3DKMTQueryAdapterInfo(ref query);
            if (status == 0) {{
                address = (D3DKMT_ADAPTERADDRESS)Marshal.PtrToStructure(ptr, typeof(D3DKMT_ADAPTERADDRESS));
            }}
            return status;
        }} finally {{
            Marshal.FreeHGlobal(ptr);
        }}
    }}

    private static void QueryAndAppendPerf(List<GpuPerfResult> results, HashSet<string> seen, Dictionary<string, int> utilByLuid, uint hAdapter, LUID adapterLuid, string deviceName, string name, int openStatus) {{
        D3DKMT_ADAPTERADDRESS address;
        int addressStatus = QueryAdapterAddress(hAdapter, out address);
        D3DKMT_ADAPTER_PERFDATA perf = new D3DKMT_ADAPTER_PERFDATA();
        int size = Marshal.SizeOf(typeof(D3DKMT_ADAPTER_PERFDATA));
        IntPtr ptr = Marshal.AllocHGlobal(size);
        try {{
            Marshal.StructureToPtr(perf, ptr, false);
            D3DKMT_QUERYADAPTERINFO query = new D3DKMT_QUERYADAPTERINFO();
            query.hAdapter = hAdapter;
            // KMTQAITYPE_ADAPTERPERFDATA in d3dkmthk.h.
            query.Type = 62;
            query.pPrivateDriverData = ptr;
            query.PrivateDriverDataSize = (uint)size;
            int status = D3DKMTQueryAdapterInfo(ref query);
            string luid = adapterLuid.HighPart.ToString("X8") + ":" + adapterLuid.LowPart.ToString("X8");
            string perfLuid = NormalizeLuid(adapterLuid);
            int utilization = 0;
            if (utilByLuid != null && utilByLuid.ContainsKey(perfLuid)) {{
                utilization = utilByLuid[perfLuid];
            }}
            if (status == 0) {{
                perf = (D3DKMT_ADAPTER_PERFDATA)Marshal.PtrToStructure(ptr, typeof(D3DKMT_ADAPTER_PERFDATA));
                double tempC = perf.Temperature / 10.0;
                int temp = (tempC > 0 && tempC < 150) ? (int)Math.Round(tempC) : 0;
                Diagnostics.Add(new GpuPerfDiagnostic {{
                    DeviceName = deviceName,
                    Name = name,
                    Luid = luid,
                    OpenStatus = openStatus,
                    QueryType = query.Type,
                    QueryStatus = status,
                    RawTemperature = (int)perf.Temperature,
                    AddressStatus = addressStatus,
                    BusNumber = (int)address.BusNumber,
                    DeviceNumber = (int)address.DeviceNumber,
                    FunctionNumber = (int)address.FunctionNumber,
                    Utilization = utilization,
                    Temperature = temp,
                    FanRPM = (int)perf.FanRPM,
                    Power = (int)perf.Power
                }});
                if (!seen.Contains(luid)) {{
                    seen.Add(luid);
                    results.Add(new GpuPerfResult {{
                        DeviceName = deviceName,
                        Name = name,
                        Luid = luid,
                        QueryType = query.Type,
                        QueryStatus = status,
                        RawTemperature = (int)perf.Temperature,
                        BusNumber = (int)address.BusNumber,
                        DeviceNumber = (int)address.DeviceNumber,
                        FunctionNumber = (int)address.FunctionNumber,
                        Utilization = utilization,
                        Temperature = temp,
                        FanRPM = (int)perf.FanRPM,
                        Power = (int)perf.Power
                    }});
                }}
            }} else {{
                Diagnostics.Add(new GpuPerfDiagnostic {{
                    DeviceName = deviceName,
                    Name = name,
                    Luid = luid,
                    OpenStatus = openStatus,
                    QueryType = query.Type,
                    QueryStatus = status,
                    AddressStatus = addressStatus,
                    BusNumber = (int)address.BusNumber,
                    DeviceNumber = (int)address.DeviceNumber,
                    FunctionNumber = (int)address.FunctionNumber,
                    Utilization = utilization
                }});
            }}
        }} finally {{
            Marshal.FreeHGlobal(ptr);
        }}
    }}

    private static void ReadFromEnumAdapters2(List<GpuPerfResult> results, HashSet<string> seen, Dictionary<string, int> utilByLuid) {{
        D3DKMT_ENUMADAPTERS2 enumData = new D3DKMT_ENUMADAPTERS2();
        enumData.NumAdapters = 0;
        enumData.pAdapters = IntPtr.Zero;
        int firstStatus = D3DKMTEnumAdapters2(ref enumData);
        EnumAdapters2Status = firstStatus;
        EnumAdapters2Count = (int)enumData.NumAdapters;
        if (enumData.NumAdapters == 0) {{
            Diagnostics.Add(new GpuPerfDiagnostic {{
                DeviceName = "enum2:init",
                Name = "D3DKMTEnumAdapters2",
                OpenStatus = firstStatus,
                QueryType = 62,
                QueryStatus = -1
            }});
            return;
        }}
        uint count = Math.Min(enumData.NumAdapters, 32);
        int itemSize = Marshal.SizeOf(typeof(D3DKMT_ADAPTERINFO));
        IntPtr adaptersPtr = Marshal.AllocHGlobal(itemSize * (int)count);
        try {{
            D3DKMT_ENUMADAPTERS2 enumData2 = new D3DKMT_ENUMADAPTERS2();
            enumData2.NumAdapters = count;
            enumData2.pAdapters = adaptersPtr;
            int enumStatus = D3DKMTEnumAdapters2(ref enumData2);
            EnumAdapters2Status = enumStatus;
            EnumAdapters2Returned = (int)enumData2.NumAdapters;
            if (enumStatus != 0) {{
                Diagnostics.Add(new GpuPerfDiagnostic {{
                    DeviceName = "enum2:query",
                    Name = "D3DKMTEnumAdapters2",
                    OpenStatus = enumStatus,
                    QueryType = 62,
                    QueryStatus = -1
                }});
                return;
            }}
            for (int idx = 0; idx < enumData2.NumAdapters; idx++) {{
                IntPtr itemPtr = IntPtr.Add(adaptersPtr, idx * itemSize);
                D3DKMT_ADAPTERINFO info = (D3DKMT_ADAPTERINFO)Marshal.PtrToStructure(itemPtr, typeof(D3DKMT_ADAPTERINFO));
                QueryAndAppendPerf(results, seen, utilByLuid, info.hAdapter, info.AdapterLuid, "enum2:" + idx.ToString(), "DXGK Adapter " + idx.ToString(), enumStatus);
                D3DKMT_CLOSEADAPTER close = new D3DKMT_CLOSEADAPTER();
                close.hAdapter = info.hAdapter;
                D3DKMTCloseAdapter(ref close);
            }}
        }} finally {{
            Marshal.FreeHGlobal(adaptersPtr);
        }}
    }}

    public static GpuPerfResult[] Read() {{
        List<GpuPerfResult> results = new List<GpuPerfResult>();
        HashSet<string> seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
	        Diagnostics.Clear();
	        GdiDisplayCount = 0;
	        EnumAdapters2Status = 0;
	        EnumAdapters2Count = 0;
	        EnumAdapters2Returned = 0;
	        EngineCounterInstanceCount = 0;
	        EngineCounterLuidCount = 0;
	        EngineMaxUtilization = 0;
	        EngineTotalUtilization = 0;
	        EngineLuidSummary = "";
	        Dictionary<string, int> utilByLuid = ReadGpuEngineUtilizationByLuid();
        for (uint i = 0; i < 32; i++) {{
            DISPLAY_DEVICE dd = new DISPLAY_DEVICE();
            dd.cb = Marshal.SizeOf(typeof(DISPLAY_DEVICE));
            if (!EnumDisplayDevices(null, i, ref dd, 0)) {{
                break;
            }}
            GdiDisplayCount++;
            if (String.IsNullOrWhiteSpace(dd.DeviceName)) {{
                continue;
            }}
            D3DKMT_OPENADAPTERFROMGDIDISPLAYNAME open = new D3DKMT_OPENADAPTERFROMGDIDISPLAYNAME();
            open.DeviceName = dd.DeviceName;
            int openStatus = D3DKMTOpenAdapterFromGdiDisplayName(ref open);
            if (openStatus != 0 || open.hAdapter == 0) {{
                Diagnostics.Add(new GpuPerfDiagnostic {{
                    DeviceName = dd.DeviceName,
                    Name = dd.DeviceString,
                    OpenStatus = openStatus,
                    QueryType = 62,
                    QueryStatus = -1
                }});
                continue;
            }}
            try {{
                QueryAndAppendPerf(results, seen, utilByLuid, open.hAdapter, open.AdapterLuid, dd.DeviceName, dd.DeviceString, openStatus);
            }} finally {{
                D3DKMT_CLOSEADAPTER close = new D3DKMT_CLOSEADAPTER();
                close.hAdapter = open.hAdapter;
                D3DKMTCloseAdapter(ref close);
            }}
        }}
        ReadFromEnumAdapters2(results, seen, utilByLuid);
        return results.ToArray();
    }}
}}
'@
            Add-Type -TypeDefinition $source -Language CSharp -ErrorAction Stop | Out-Null
        }}
        $items = @([SmartCenterGpuPerfReader]::Read())
        $script:GpuProbeDiagnostic['dxgk_count'] = [int]$items.Count
        $script:GpuProbeDiagnostic['dxgk_gdi_display_count'] = [int][SmartCenterGpuPerfReader]::GdiDisplayCount
        $script:GpuProbeDiagnostic['dxgk_enum2_status'] = [int][SmartCenterGpuPerfReader]::EnumAdapters2Status
        $script:GpuProbeDiagnostic['dxgk_enum2_count'] = [int][SmartCenterGpuPerfReader]::EnumAdapters2Count
        $script:GpuProbeDiagnostic['dxgk_enum2_returned'] = [int][SmartCenterGpuPerfReader]::EnumAdapters2Returned
	        $script:GpuProbeDiagnostic['gpu_engine_counter_instances'] = [int][SmartCenterGpuPerfReader]::EngineCounterInstanceCount
	        $script:GpuProbeDiagnostic['gpu_engine_luid_count'] = [int][SmartCenterGpuPerfReader]::EngineCounterLuidCount
	        $script:GpuProbeDiagnostic['gpu_engine_max_util'] = [int][SmartCenterGpuPerfReader]::EngineMaxUtilization
	        $script:GpuProbeDiagnostic['gpu_engine_total_util'] = [int][SmartCenterGpuPerfReader]::EngineTotalUtilization
	        $script:GpuProbeDiagnostic['gpu_engine_luid_summary'] = [string][SmartCenterGpuPerfReader]::EngineLuidSummary
	        $script:GpuProbeDiagnostic['dxgk_probe'] = @(
            @([SmartCenterGpuPerfReader]::Diagnostics) | Select-Object -First 8 | ForEach-Object {{
                @{{
                    device = [string]$_.DeviceName
                    name = [string]$_.Name
                    luid = [string]$_.Luid
                    open_status = [int]$_.OpenStatus
                    query_type = [int]$_.QueryType
                    query_status = [int]$_.QueryStatus
                    raw_temp = [int]$_.RawTemperature
                    temp = [int]$_.Temperature
                    util = [int]$_.Utilization
                    address_status = [int]$_.AddressStatus
                    bus = [int]$_.BusNumber
                    device_number = [int]$_.DeviceNumber
                    function_number = [int]$_.FunctionNumber
                    fan_rpm = [int]$_.FanRPM
                    power = [int]$_.Power
                }}
            }}
        )
    }} catch {{
        $script:GpuProbeDiagnostic['dxgk_error'] = Get-ErrorDetails $_
        Write-AgentLog ('dxgk gpu perf query failed: ' + $_.Exception.Message)
        return @()
    }}
    return @($items)
}}

function Merge-DxgkGpuPerfData([array]$gpuList) {{
    $perfItems = @(Get-DxgkGpuPerfData)
    if ($perfItems.Count -eq 0) {{
        return @($gpuList)
    }}
    $nonzeroMetricItems = @($perfItems | Where-Object {{
        $candidateTemp = 0
        $candidateUtil = 0
        try {{ $candidateTemp = [int]$_.Temperature }} catch {{ $candidateTemp = 0 }}
        try {{ $candidateUtil = [int]$_.Utilization }} catch {{ $candidateUtil = 0 }}
        $candidateTemp -gt 0 -or $candidateUtil -gt 0
    }})
    $amdRowIndexes = @()
    $nvidiaRowIndexes = @()
    $genericFallbackIndexes = @()
    $hasNvidiaRow = $false
    for ($idx = 0; $idx -lt $gpuList.Count; $idx++) {{
        $row = $gpuList[$idx]
        if ([string]$row.name -match '(?i)nvidia|geforce|quadro|rtx|gtx' -or [string]$row.source -match '(?i)nvidia') {{
            $hasNvidiaRow = $true
            $nvidiaRowIndexes += $idx
            continue
        }}
        if ([string]$row.name -match '(?i)amd|radeon') {{
            $amdRowIndexes += $idx
        }}
        $genericFallbackIndexes += $idx
    }}
	    foreach ($perf in $perfItems) {{
        $temp = 0
        $util = 0
        try {{ $temp = [int]$perf.Temperature }} catch {{ $temp = 0 }}
        try {{ $util = [int]$perf.Utilization }} catch {{ $util = 0 }}
        if ($temp -le 0 -and $util -le 0) {{
            continue
        }}
        $perfIdentity = Normalize-GpuIdentity ([string]$perf.Name)
        $updated = $false
        for ($i = 0; $i -lt $gpuList.Count; $i++) {{
            $row = $gpuList[$i]
            $rowTemp = 0
            $rowUtil = 0
            try {{ $rowTemp = [int]$row.temp }} catch {{ $rowTemp = 0 }}
            try {{ $rowUtil = [int]$row.util_percent }} catch {{ $rowUtil = 0 }}
            $rowIdentity = Normalize-GpuIdentity ([string]$row.name)
            $nameMatches = $perfIdentity -and $rowIdentity -and ($perfIdentity -eq $rowIdentity -or $perfIdentity.Contains($rowIdentity) -or $rowIdentity.Contains($perfIdentity))
            $amdFallback = ([string]$row.name -match '(?i)amd|radeon') -and ([string]$perf.Name -match '(?i)amd|radeon')
            if ($nameMatches -or $amdFallback) {{
                if ($temp -gt 0 -and $rowTemp -le 0) {{ $row.temp = $temp }}
                if ($util -gt 0 -and $rowUtil -le 0) {{ $row.util_percent = $util }}
                $row.source = 'dxgk'
                if ($perf.FanRPM -gt 0) {{ $row.fan_rpm = [int]$perf.FanRPM }}
                $gpuList[$i] = $row
                $updated = $true
                break
            }}
	        }}
        if (-not $updated -and $nonzeroMetricItems.Count -eq 1 -and $nvidiaRowIndexes.Count -eq 1) {{
            $targetIndex = [int]$nvidiaRowIndexes[0]
            $row = $gpuList[$targetIndex]
            if ($temp -gt 0) {{ $row.temp = $temp }}
            if ($util -gt 0) {{ $row.util_percent = $util }}
            if (-not $row.source -or [string]$row.source -eq 'wmi') {{
                $row.source = 'dxgk'
            }} elseif ([string]$row.source -notmatch '(?i)dxgk') {{
                $row.source = ([string]$row.source + '+dxgk')
            }}
            if ($perf.FanRPM -gt 0) {{ $row.fan_rpm = [int]$perf.FanRPM }}
            if ($perf.Power -gt 0) {{ $row.power = [int]$perf.Power }}
            $gpuList[$targetIndex] = $row
            $script:GpuProbeDiagnostic['dxgk_fallback_target'] = [string]$row.name
            $updated = $true
        }}
        if (-not $updated -and $nonzeroMetricItems.Count -eq 1 -and $amdRowIndexes.Count -eq 1) {{
            $targetIndex = [int]$amdRowIndexes[0]
            $row = $gpuList[$targetIndex]
            if ($temp -gt 0) {{ $row.temp = $temp }}
            if ($util -gt 0) {{ $row.util_percent = $util }}
            $row.source = 'dxgk'
            if ($perf.FanRPM -gt 0) {{ $row.fan_rpm = [int]$perf.FanRPM }}
            $gpuList[$targetIndex] = $row
            $updated = $true
        }}
        if (-not $updated -and -not $hasNvidiaRow -and $nonzeroMetricItems.Count -eq 1 -and $genericFallbackIndexes.Count -eq 1) {{
            $targetIndex = [int]$genericFallbackIndexes[0]
            $row = $gpuList[$targetIndex]
            if ($temp -gt 0) {{ $row.temp = $temp }}
            if ($util -gt 0) {{ $row.util_percent = $util }}
            $row.source = 'dxgk'
            if ($perf.FanRPM -gt 0) {{ $row.fan_rpm = [int]$perf.FanRPM }}
            $gpuList[$targetIndex] = $row
            $updated = $true
        }}
	        if (-not $updated -and -not $hasNvidiaRow -and $gpuList.Count -eq 0 -and $perf.Name) {{
	            $gpuList += @{{
                index = $gpuList.Count
                name = [string]$perf.Name
                util_percent = $util
                temp = $temp
                source = 'dxgk'
                fan_rpm = if ($perf.FanRPM -gt 0) {{ [int]$perf.FanRPM }} else {{ 0 }}
            }}
	        }}
	    }}
	    $hasAnyUtil = $false
	    foreach ($row in @($gpuList)) {{
	        try {{
	            if ([int]$row.util_percent -gt 0) {{ $hasAnyUtil = $true; break }}
	        }} catch {{}}
	    }}
	    $engineMaxUtil = 0
	    try {{ $engineMaxUtil = [int]$script:GpuProbeDiagnostic['gpu_engine_max_util'] }} catch {{ $engineMaxUtil = 0 }}
	    $engineLuidCount = 0
	    try {{ $engineLuidCount = [int]$script:GpuProbeDiagnostic['gpu_engine_luid_count'] }} catch {{ $engineLuidCount = 0 }}
		    if ((-not $hasAnyUtil) -and $engineMaxUtil -gt 0 -and $engineLuidCount -eq 1) {{
		        $targetIndexes = @()
		        $amdWithDxgkMetrics = @()
		        $nvidiaIndexes = @()
		        for ($idx = 0; $idx -lt $gpuList.Count; $idx++) {{
		            $row = $gpuList[$idx]
		            if ([string]$row.name -match '(?i)nvidia|geforce|quadro|rtx|gtx' -or [string]$row.source -match '(?i)nvidia') {{
		                $nvidiaIndexes += $idx
		                continue
		            }}
	            $targetIndexes += $idx
	            $rowTemp = 0
	            try {{ $rowTemp = [int]$row.temp }} catch {{ $rowTemp = 0 }}
	            if ([string]$row.name -match '(?i)amd|radeon' -and [string]$row.source -match '(?i)dxgk' -and $rowTemp -gt 0) {{
	                $amdWithDxgkMetrics += $idx
	            }}
	        }}
	        $targetIndex = $null
		        if ($nvidiaIndexes.Count -eq 1) {{
		            $targetIndex = [int]$nvidiaIndexes[0]
		        }} elseif ($amdWithDxgkMetrics.Count -eq 1) {{
		            $targetIndex = [int]$amdWithDxgkMetrics[0]
	        }} elseif ($targetIndexes.Count -eq 1) {{
	            $targetIndex = [int]$targetIndexes[0]
	        }}
	        if ($null -ne $targetIndex) {{
	            $row = $gpuList[$targetIndex]
	            $row.util_percent = $engineMaxUtil
	            if (-not $row.source -or [string]$row.source -eq 'wmi') {{
	                $row.source = 'gpu-engine'
	            }} elseif ([string]$row.source -notmatch '(?i)gpu-engine') {{
	                $row.source = ([string]$row.source + '+gpu-engine')
	            }}
	            $gpuList[$targetIndex] = $row
	            $script:GpuProbeDiagnostic['gpu_engine_fallback_target'] = [string]$row.name
	            $script:GpuProbeDiagnostic['gpu_engine_fallback_util'] = $engineMaxUtil
	        }}
	    }}
	    return @($gpuList)
	}}

function Get-AmdAdlGpuTemps {{
    $items = @()
    $script:GpuProbeDiagnostic['amd_adl_checked_at'] = (Get-Date).ToString('o')
    $adlSearchDirs = @(
        (Join-Path $env:WINDIR 'System32'),
        (Join-Path $env:WINDIR 'SysWOW64'),
        (Join-Path $env:ProgramFiles 'AMD\CNext\CNext'),
        (Join-Path ${{env:ProgramFiles(x86)}} 'AMD\CNext\CNext')
    )
    foreach ($dll in @('atiadlxx.dll','atiadlxy.dll')) {{
        $found = $false
        foreach ($dir in $adlSearchDirs) {{
            try {{
                if ($dir -and (Test-Path (Join-Path $dir $dll))) {{
                    $found = $true
                    break
                }}
            }} catch {{}}
        }}
        $script:GpuProbeDiagnostic[('has_' + $dll)] = [bool]$found
    }}
    if (-not (Get-CommandOrNull 'Add-Type')) {{
        $script:GpuProbeDiagnostic['amd_adl_error'] = 'Add-Type unavailable'
        return @()
    }}
    try {{
        if (-not ('SmartCenterAmdAdlReader' -as [type])) {{
            $source = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public class SmartCenterAmdAdlReader {{
    public delegate IntPtr ADL_MAIN_MALLOC_CALLBACK(int size);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct ADLAdapterInfo {{
        public int Size;
        public int AdapterIndex;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)]
        public string UDID;
        public int BusNumber;
        public int DeviceNumber;
        public int FunctionNumber;
        public int VendorID;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)]
        public string AdapterName;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)]
        public string DisplayName;
        public int Present;
        public int Exist;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)]
        public string DriverPath;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)]
        public string DriverPathExt;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)]
        public string PNPString;
        public int OSDisplayIndex;
    }}

    [StructLayout(LayoutKind.Sequential)]
    public struct ADLTemperature {{
        public int Size;
        public int Temperature;
    }}

    public class AmdTempResult {{
        public int AdapterIndex;
        public string Name;
        public int Temperature;
    }}

    [DllImport("atiadlxx.dll", CallingConvention = CallingConvention.Cdecl, EntryPoint = "ADL_Main_Control_Create")]
    public static extern int ADL_Main_Control_Create_64(ADL_MAIN_MALLOC_CALLBACK callback, int enumConnectedAdapters);
    [DllImport("atiadlxy.dll", CallingConvention = CallingConvention.Cdecl, EntryPoint = "ADL_Main_Control_Create")]
    public static extern int ADL_Main_Control_Create_32(ADL_MAIN_MALLOC_CALLBACK callback, int enumConnectedAdapters);
    [DllImport("atiadlxx.dll", CallingConvention = CallingConvention.Cdecl, EntryPoint = "ADL_Main_Control_Destroy")]
    public static extern int ADL_Main_Control_Destroy_64();
    [DllImport("atiadlxy.dll", CallingConvention = CallingConvention.Cdecl, EntryPoint = "ADL_Main_Control_Destroy")]
    public static extern int ADL_Main_Control_Destroy_32();
    [DllImport("atiadlxx.dll", CallingConvention = CallingConvention.Cdecl, EntryPoint = "ADL_Adapter_NumberOfAdapters_Get")]
    public static extern int ADL_Adapter_NumberOfAdapters_Get_64(ref int numAdapters);
    [DllImport("atiadlxy.dll", CallingConvention = CallingConvention.Cdecl, EntryPoint = "ADL_Adapter_NumberOfAdapters_Get")]
    public static extern int ADL_Adapter_NumberOfAdapters_Get_32(ref int numAdapters);
    [DllImport("atiadlxx.dll", CallingConvention = CallingConvention.Cdecl, EntryPoint = "ADL_Adapter_AdapterInfo_Get")]
    public static extern int ADL_Adapter_AdapterInfo_Get_64(IntPtr info, int inputSize);
    [DllImport("atiadlxy.dll", CallingConvention = CallingConvention.Cdecl, EntryPoint = "ADL_Adapter_AdapterInfo_Get")]
    public static extern int ADL_Adapter_AdapterInfo_Get_32(IntPtr info, int inputSize);
    [DllImport("atiadlxx.dll", CallingConvention = CallingConvention.Cdecl, EntryPoint = "ADL_Overdrive5_Temperature_Get")]
    public static extern int ADL_Overdrive5_Temperature_Get_64(int adapterIndex, int thermalControllerIndex, ref ADLTemperature temperature);
    [DllImport("atiadlxy.dll", CallingConvention = CallingConvention.Cdecl, EntryPoint = "ADL_Overdrive5_Temperature_Get")]
    public static extern int ADL_Overdrive5_Temperature_Get_32(int adapterIndex, int thermalControllerIndex, ref ADLTemperature temperature);

    public static IntPtr Alloc(int size) {{
        return Marshal.AllocHGlobal(size);
    }}

    private static int MainCreate(ADL_MAIN_MALLOC_CALLBACK cb, int enumConnected) {{
        try {{ return ADL_Main_Control_Create_64(cb, enumConnected); }} catch {{ return ADL_Main_Control_Create_32(cb, enumConnected); }}
    }}
    private static int MainDestroy() {{
        try {{ return ADL_Main_Control_Destroy_64(); }} catch {{ return ADL_Main_Control_Destroy_32(); }}
    }}
    private static int GetAdapterCount(ref int count) {{
        try {{ return ADL_Adapter_NumberOfAdapters_Get_64(ref count); }} catch {{ return ADL_Adapter_NumberOfAdapters_Get_32(ref count); }}
    }}
    private static int GetAdapterInfo(IntPtr ptr, int size) {{
        try {{ return ADL_Adapter_AdapterInfo_Get_64(ptr, size); }} catch {{ return ADL_Adapter_AdapterInfo_Get_32(ptr, size); }}
    }}
    private static int GetTemperature(int adapterIndex, ref ADLTemperature temp) {{
        try {{ return ADL_Overdrive5_Temperature_Get_64(adapterIndex, 0, ref temp); }} catch {{ return ADL_Overdrive5_Temperature_Get_32(adapterIndex, 0, ref temp); }}
    }}

    public static AmdTempResult[] Read() {{
        List<AmdTempResult> results = new List<AmdTempResult>();
        ADL_MAIN_MALLOC_CALLBACK cb = new ADL_MAIN_MALLOC_CALLBACK(Alloc);
        int created = MainCreate(cb, 1);
        if (created < 0) return results.ToArray();
        try {{
            int count = 0;
            if (GetAdapterCount(ref count) < 0 || count <= 0 || count > 32) return results.ToArray();
            int size = Marshal.SizeOf(typeof(ADLAdapterInfo));
            IntPtr ptr = Marshal.AllocHGlobal(size * count);
            try {{
                for (int i = 0; i < size * count; i++) Marshal.WriteByte(ptr, i, 0);
                if (GetAdapterInfo(ptr, size * count) < 0) return results.ToArray();
                for (int i = 0; i < count; i++) {{
                    IntPtr itemPtr = new IntPtr(ptr.ToInt64() + size * i);
                    ADLAdapterInfo info = (ADLAdapterInfo)Marshal.PtrToStructure(itemPtr, typeof(ADLAdapterInfo));
                    ADLTemperature temp = new ADLTemperature();
                    temp.Size = Marshal.SizeOf(typeof(ADLTemperature));
                    int status = GetTemperature(info.AdapterIndex, ref temp);
                    if (status >= 0) {{
                        int tempC = (int)Math.Round(temp.Temperature / 1000.0);
                        if (tempC > 0 && tempC < 150) {{
                            results.Add(new AmdTempResult {{
                                AdapterIndex = info.AdapterIndex,
                                Name = String.IsNullOrWhiteSpace(info.AdapterName) ? info.DisplayName : info.AdapterName,
                                Temperature = tempC
                            }});
                        }}
                    }}
                }}
            }} finally {{
                Marshal.FreeHGlobal(ptr);
            }}
        }} finally {{
            MainDestroy();
        }}
        return results.ToArray();
    }}
}}
'@
            Add-Type -TypeDefinition $source -Language CSharp -ErrorAction Stop | Out-Null
        }}
        $items = @([SmartCenterAmdAdlReader]::Read())
        $script:GpuProbeDiagnostic['amd_adl_count'] = [int]$items.Count
    }} catch {{
        $script:GpuProbeDiagnostic['amd_adl_error'] = Get-ErrorDetails $_
        Write-AgentLog ('amd adl gpu temp query failed: ' + $_.Exception.Message)
        return @()
    }}
    return @($items)
}}

function Merge-AmdAdlGpuTemps([array]$gpuList) {{
    $amdTemps = @(Get-AmdAdlGpuTemps)
    if ($amdTemps.Count -eq 0) {{
        return @($gpuList)
    }}
    foreach ($amd in $amdTemps) {{
        $temp = 0
        try {{ $temp = [int]$amd.Temperature }} catch {{ $temp = 0 }}
        if ($temp -le 0) {{ continue }}
        $amdIdentity = Normalize-GpuIdentity ([string]$amd.Name)
        $updated = $false
        for ($i = 0; $i -lt $gpuList.Count; $i++) {{
            $row = $gpuList[$i]
            $rowTemp = 0
            try {{ $rowTemp = [int]$row.temp }} catch {{ $rowTemp = 0 }}
            $rowIdentity = Normalize-GpuIdentity ([string]$row.name)
            $nameMatches = $amdIdentity -and $rowIdentity -and ($amdIdentity -eq $rowIdentity -or $amdIdentity.Contains($rowIdentity) -or $rowIdentity.Contains($amdIdentity))
            $amdFallback = ([string]$row.name -match '(?i)amd|radeon') -and (($amd.Name -eq $null) -or ([string]$amd.Name -match '(?i)amd|radeon|pro|graphics'))
            if (($nameMatches -or $amdFallback) -and $rowTemp -le 0) {{
                $row.temp = $temp
                $row.source = 'amd-adl'
                $gpuList[$i] = $row
                $updated = $true
                break
            }}
        }}
        if (-not $updated) {{
            $gpuList += @{{
                index = $gpuList.Count
                name = if ($amd.Name) {{ [string]$amd.Name }} else {{ 'AMD GPU' }}
                util_percent = 0
                temp = $temp
                source = 'amd-adl'
            }}
        }}
    }}
    return @($gpuList)
}}

function Normalize-GpuIdentity([string]$name) {{
    $text = ([string]$name).Trim().ToLowerInvariant()
    if (-not $text) {{
        return ''
    }}
    $text = $text -replace '^vga compatible controller:\s*', ''
    $text = $text -replace '^3d controller:\s*', ''
    $text = $text -replace '^display controller:\s*', ''
    $text = $text -replace '^nvidia\s+', ''
    $text = $text -replace '^intel\(r\)\s+', 'intel '
    $text = $text -replace '[^a-z0-9]+', ''
    return $text
}}

function Test-GpuNameMatch([string]$left, [string]$right) {{
    $leftId = Normalize-GpuIdentity $left
    $rightId = Normalize-GpuIdentity $right
    if (-not $leftId -or -not $rightId) {{ return $false }}
    if ($leftId -eq $rightId -or $leftId.Contains($rightId) -or $rightId.Contains($leftId)) {{
        return $true
    }}
    $leftVendor = if ($left -match '(?i)nvidia|geforce|quadro|rtx|gtx') {{ 'nvidia' }} elseif ($left -match '(?i)amd|radeon') {{ 'amd' }} elseif ($left -match '(?i)intel') {{ 'intel' }} else {{ '' }}
    $rightVendor = if ($right -match '(?i)nvidia|geforce|quadro|rtx|gtx') {{ 'nvidia' }} elseif ($right -match '(?i)amd|radeon') {{ 'amd' }} elseif ($right -match '(?i)intel') {{ 'intel' }} else {{ '' }}
    return $leftVendor -and $rightVendor -and $leftVendor -eq $rightVendor
}}

function Add-MissingDisplayGpu([array]$gpuList, [string]$name, [ref]$indexRef) {{
    $text = ([string]$name).Trim()
    if (-not $text) {{
        return @($gpuList)
    }}
    foreach ($item in @($gpuList)) {{
        if ($item.name -and (Test-GpuNameMatch ([string]$item.name) $text)) {{
            return @($gpuList)
        }}
    }}
    $gpuList += @{{
        index = [int]$indexRef.Value
        name = $text
        util_percent = 0
        temp = 0
        source = 'wmi'
    }}
    $indexRef.Value = [int]$indexRef.Value + 1
    return @($gpuList)
}}

function Get-GpuInfo {{
    $gpuList = @(Get-NvidiaGpuInfo)
    $hasIntelDisplay = $false
    $hasAmdDisplay = $false
    $nextIndex = 0
    if ($gpuList.Count -gt 0) {{
        try {{
            $maxIndex = ($gpuList | Measure-Object -Property index -Maximum).Maximum
            if ($null -ne $maxIndex) {{
                $nextIndex = [int]$maxIndex + 1
            }}
        }} catch {{
            $nextIndex = $gpuList.Count
        }}
    }}
    try {{
        $gpus = @(Get-AgentInstances 'Win32_VideoController')
        foreach ($gpu in $gpus) {{
            if ([string]$gpu.Name -match '(?i)intel') {{
                $hasIntelDisplay = $true
            }}
            if ([string]$gpu.Name -match '(?i)amd|radeon') {{
                $hasAmdDisplay = $true
            }}
            $gpuList = @(Add-MissingDisplayGpu $gpuList ([string]$gpu.Name) ([ref]$nextIndex))
        }}
    }} catch {{}}
    $hasNvidia = @($gpuList | Where-Object {{ [string]$_.name -match '(?i)nvidia|geforce|quadro|rtx|gtx' -or [string]$_.source -match '(?i)nvidia' }}).Count -gt 0
    if ($hasNvidia -and $hasIntelDisplay) {{
        $script:GpuProbeDiagnostic['amd_adl_skipped'] = 'nvidia_intel_hybrid'
        Write-AgentLog 'amd adl gpu probe skipped for NVIDIA+Intel hybrid graphics'
    }}
    try {{
        $gpuList = @(Merge-DxgkGpuPerfData $gpuList)
    }} catch {{
        Write-AgentLog ('dxgk gpu merge failed: ' + $_.Exception.Message)
    }}
    if ($hasAmdDisplay) {{
        try {{
            $gpuList = @(Merge-AmdAdlGpuTemps $gpuList)
        }} catch {{
            Write-AgentLog ('amd adl gpu merge failed: ' + $_.Exception.Message)
        }}
    }} else {{
        $script:GpuProbeDiagnostic['amd_adl_skipped'] = 'no_amd_display'
    }}
    if ($gpuList.Count -eq 0) {{
        try {{
            $pnpDevices = Get-PnpDevice -Class Display -ErrorAction Stop | Where-Object {{
                $_.FriendlyName -and $_.Status -eq 'OK'
            }}
            foreach ($gpu in $pnpDevices) {{
                $gpuList = @(Add-MissingDisplayGpu $gpuList ([string]$gpu.FriendlyName) ([ref]$nextIndex))
            }}
        }} catch {{}}
    }}
    return @($gpuList)
}}

function Get-CodeMeterToolPath {{
    try {{
        $cmd = Get-Command 'cmu32.exe' -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) {{ return [string]$cmd.Source }}
    }} catch {{}}
    try {{
        $cmd = Get-Command 'cmu.exe' -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) {{ return [string]$cmd.Source }}
    }} catch {{}}
    foreach ($candidate in @(
        (Join-Path $env:ProgramFiles 'CodeMeter\\Runtime\\bin\\cmu32.exe'),
        (Join-Path ${{env:ProgramFiles(x86)}} 'CodeMeter\\Runtime\\bin\\cmu32.exe'),
        (Join-Path $env:ProgramFiles 'CodeMeter\\Runtime\\bin\\cmu.exe'),
        (Join-Path ${{env:ProgramFiles(x86)}} 'CodeMeter\\Runtime\\bin\\cmu.exe')
    )) {{
        try {{
            if ($candidate -and (Test-Path $candidate)) {{ return [string]$candidate }}
        }} catch {{}}
    }}
    return ''
}}

function Get-CodeMeterServiceState {{
    foreach ($name in @('CodeMeter.exe', 'CodeMeter')) {{
        try {{
            $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
            if ($svc) {{ return [string]$svc.Status }}
        }} catch {{}}
    }}
    try {{
        $proc = Get-Process -Name 'CodeMeter' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($proc) {{ return 'Running' }}
    }} catch {{}}
    return 'Unknown'
}}

function Parse-CodeMeterOutput([string]$text) {{
    $serials = @()
    $licenses = @()
    $raw = [string]$text
    $runtimeVersion = ''
    $runtimeMajor = $null
    $runtimeOutdated = $false
    $runtimeMatch = [regex]::Match($raw, '(?i)\\bVersion\\s+([0-9]+(?:\\.[0-9]+)?[A-Za-z]?)\\b')
    if ($runtimeMatch.Success) {{
        $runtimeVersion = [string]$runtimeMatch.Groups[1].Value
        $majorMatch = [regex]::Match($runtimeVersion, '^([0-9]+)')
        if ($majorMatch.Success) {{
            try {{ $runtimeMajor = [int]$majorMatch.Groups[1].Value }} catch {{ $runtimeMajor = $null }}
        }}
        $runtimeOutdated = $runtimeMajor -ne $null -and $runtimeMajor -lt 8
    }}
    foreach ($match in [regex]::Matches($raw, '(?i)(?:CmContainer\s+with\s+Serial\s+Number|Serial\s+(?:Number|No\.?)|Serial)\s*[:#]?\s*([0-9]+-[0-9]+)')) {{
        $serial = [string]$match.Groups[1].Value
        if ($serial -and $serials -notcontains $serial) {{ $serials += $serial }}
    }}
    foreach ($match in [regex]::Matches($raw, '\\b[1-9][0-9]?-[0-9]{{5,}}\\b')) {{
        $serial = [string]$match.Value
        if ($serial -and $serials -notcontains $serial) {{ $serials += $serial }}
    }}
    $physicalSerials = @($serials | Where-Object {{ -not ([string]$_).StartsWith('130-') }})
    $virtualSerials = @($serials | Where-Object {{ ([string]$_).StartsWith('130-') }})
    $displaySerials = @($physicalSerials)
    if ($displaySerials.Count -eq 0) {{ $displaySerials = @($serials) }}
    $firmcodes = @()
    foreach ($match in [regex]::Matches($raw, '(?i)\\bFC\\s*=\\s*([0-9]{{3,}})\\b')) {{
        $code = [string]$match.Groups[1].Value
        if ($code -and $firmcodes -notcontains $code) {{ $firmcodes += $code }}
    }}
    $hasCompanyLicense = ($firmcodes -contains '102541') -or ($raw -match '(?i)Lan\\s+Jing\\s+Ke\\s+Ji')
    $companyRaw = $raw
    $companySectionMatch = [regex]::Match($raw, '(?is)\\b102541\\b.*?(?:\\r?\\n\\s*\\*\\s*FC=|\\r?\\n\\s*[0-9]{{6}}\\s+|\\z)')
    if ($companySectionMatch.Success) {{ $companyRaw = [string]$companySectionMatch.Value }}
    $permanent = $companyRaw -match '(?i)(no\s+expiration|never\s+expires|unlimited|permanent|lifetime)'
    foreach ($match in [regex]::Matches($companyRaw, '(?i)(?:Expiration\s+(?:Time|Date)|Expires|Valid\s+Until|Valid\s+to)\s*[:=]?\s*([0-9]{{4}}[-/][0-9]{{1,2}}[-/][0-9]{{1,2}}(?:[T\s][0-9]{{1,2}}:[0-9]{{2}}(?::[0-9]{{2}})?)?)')) {{
        $contextStart = [Math]::Max(0, $match.Index - 96)
        $context = $companyRaw.Substring($contextStart, $match.Index - $contextStart)
        $badContext = $context -match '(?i)(system\s+time|box\s+time|certified\s+time|version|build|copyright)'
        if ($companySectionMatch.Success -and $badContext) {{ continue }}
        $expires = [string]$match.Groups[1].Value
        if ($expires) {{ $licenses += @{{ validity='expires'; expires_at=$expires }} }}
    }}
    if ($companySectionMatch.Success) {{
        foreach ($match in [regex]::Matches($companyRaw, '\\b([0-9]{{4}}[-/][0-9]{{1,2}}[-/][0-9]{{1,2}}(?:[T\\s][0-9]{{1,2}}:[0-9]{{2}}(?::[0-9]{{2}})?)?)\\b')) {{
            $contextStart = [Math]::Max(0, $match.Index - 96)
            $context = $companyRaw.Substring($contextStart, $match.Index - $contextStart)
            $badContext = $context -match '(?i)(system\s+time|box\s+time|certified\s+time|version|build|copyright)'
            $licenseContext = ($context -match '(?i)\b(?:pc|product\s*code)\s*=\s*\d+') -or ($context -match '(?m)^\s*\d{{1,5}}\s+[-\w]')
            if ($badContext -or -not $licenseContext) {{ continue }}
            $expires = [string]$match.Groups[1].Value
            if ($expires -and -not ($licenses | Where-Object {{ $_.expires_at -eq $expires }} | Select-Object -First 1)) {{
                $licenses += @{{ validity='expires'; expires_at=$expires }}
            }}
        }}
    }}
    if ($permanent -and $licenses.Count -eq 0) {{
        $licenses += @{{ validity='permanent'; expires_at='' }}
    }}
    return @{{
        serials = @($displaySerials)
        licenses = @($licenses)
        license_identity = @{{
            firmcodes = @($firmcodes)
            company_code = if ($hasCompanyLicense) {{ '102541' }} else {{ '' }}
            company_name = if ($hasCompanyLicense) {{ 'Lan Jing Ke Ji' }} else {{ '' }}
            has_company_license = [bool]$hasCompanyLicense
            scoped_to_company = [bool]$companySectionMatch.Success
            physical_serials = @($physicalSerials)
            virtual_serials = @($virtualSerials)
            runtime_version = $runtimeVersion
            runtime_major = $runtimeMajor
            runtime_outdated = [bool]$runtimeOutdated
        }}
        raw_excerpt = if ($raw.Length -gt 2000) {{ $raw.Substring(0, 2000) }} else {{ $raw }}
    }}
}}

function Get-CodeMeterInfo {{
    $checkedAt = (Get-Date).ToString('o')
    $serviceState = Get-CodeMeterServiceState
    $tool = Get-CodeMeterToolPath
    $installed = [bool]$tool -or ($serviceState -notin @('Unknown', 'Stopped'))
    $running = $serviceState -eq 'Running'
    $outputs = @()
    $errors = @()
    if ($tool) {{
        foreach ($args in @(
            @('-x'),
            @('-l')
        )) {{
            try {{
                $capture = Invoke-ExternalCommandCapture -FilePath $tool -Arguments @($args | Where-Object {{ $null -ne $_ -and [string]$_ -ne '' }}) -TimeoutSec 6
                $joined = ([string]$capture.output + [Environment]::NewLine + [string]$capture.error).Trim()
                if ($joined) {{ $outputs += $joined }}
                if ($capture.timed_out) {{
                    $errors += ('CodeMeter command timed out: ' + ($args -join ' '))
                    continue
                }}
                if ($capture.exit_code -eq 0 -and $joined) {{ break }}
                if ($joined) {{ $errors += $joined.Substring(0, [Math]::Min(240, $joined.Length)) }}
            }} catch {{
                $errors += $_.Exception.Message
            }}
        }}
    }}
    $parsed = Parse-CodeMeterOutput (($outputs | ForEach-Object {{ [string]$_ }}) -join [Environment]::NewLine)
    $serials = @($parsed.serials)
    $licenses = @($parsed.licenses)
    $validity = 'unknown'
    if (($licenses | Where-Object {{ $_.validity -eq 'expires' }} | Select-Object -First 1)) {{
        $validity = 'expires'
    }} elseif (($licenses | Where-Object {{ $_.validity -eq 'permanent' }} | Select-Object -First 1)) {{
        $validity = 'permanent'
    }}
    if (-not $installed) {{
        $level = 'muted'; $summary = 'not_installed'
    }} elseif (-not $running) {{
        $level = 'warning'; $summary = 'service_not_running'
    }} elseif ($serials.Count -eq 0) {{
        $level = 'warning'; $summary = 'dongle_not_found'
    }} elseif ($validity -eq 'expires') {{
        $level = 'ok'; $summary = 'expires'
    }} elseif ($validity -eq 'permanent') {{
        $level = 'ok'; $summary = 'permanent'
    }} else {{
        $level = 'ok'; $summary = 'detected'
    }}
    return @{{
        installed = $installed
        running = $running
        service_state = $serviceState
        tool = $tool
        serials = @($serials)
        containers = @($serials | ForEach-Object {{ @{{ serial = [string]$_ }} }})
        license_identity = $parsed.license_identity
        license_code = if ($parsed.license_identity) {{ [string]$parsed.license_identity.company_code }} else {{ '' }}
        license_name = if ($parsed.license_identity) {{ [string]$parsed.license_identity.company_name }} else {{ '' }}
        runtime_version = if ($parsed.license_identity) {{ [string]$parsed.license_identity.runtime_version }} else {{ '' }}
        runtime_major = if ($parsed.license_identity) {{ $parsed.license_identity.runtime_major }} else {{ $null }}
        runtime_outdated = if ($parsed.license_identity) {{ [bool]$parsed.license_identity.runtime_outdated }} else {{ $false }}
        licenses = @($licenses)
        validity = $validity
        summary = $summary
        level = $level
        checked_at = $checkedAt
        raw_excerpt = $parsed.raw_excerpt
        error = (($effectiveErrors | Select-Object -First 2) -join '; ')
    }}
}}

function Get-MemorySpeed {{
    try {{
        $modules = @(Get-AgentInstances 'Win32_PhysicalMemory') | Where-Object {{ $_.Speed -gt 0 }}
        if ($modules) {{
            return [int](($modules | Measure-Object -Property Speed -Maximum).Maximum)
        }}
    }} catch {{}}
    try {{
        $modules = @(Get-AgentInstances 'Win32_PhysicalMemory') | Where-Object {{ $_.ConfiguredClockSpeed -gt 0 }}
        if ($modules) {{
            return [int](($modules | Measure-Object -Property ConfiguredClockSpeed -Maximum).Maximum)
        }}
    }} catch {{}}
    try {{
        $modules = @(Get-AgentInstances 'Win32_PhysicalMemory') | Where-Object {{ $_.ConfiguredVoltage -gt 0 -and $_.SMBIOSMemoryType }}
        if ($modules) {{
            $speed = ($modules | Select-Object -ExpandProperty Speed | Where-Object {{ $_ -gt 0 }} | Select-Object -First 1)
            if ($speed) {{
                return [int]$speed
            }}
        }}
    }} catch {{}}
    return 0
}}

function Get-BoardText([object]$board) {{
    $parts = @()
    foreach ($value in @($board.Manufacturer, $board.Product)) {{
        $text = [string]$value
        if (
            $text -and
            $text.Trim() -and
            $text.Trim() -notin @('Default string', 'System manufacturer', 'System Product Name', 'To be filled by O.E.M.')
        ) {{
            $parts += $text.Trim()
        }}
    }}
    if ($parts.Count -gt 0) {{
        return ($parts -join ' ')
    }}
    if ($board.SerialNumber -and ([string]$board.SerialNumber).Trim()) {{
        return ([string]$board.SerialNumber).Trim()
    }}
    return 'unknown'
}}

function Get-MemoryTopology {{
    $modules = @()
    try {{
        foreach ($m in @(Get-AgentInstances 'Win32_PhysicalMemory')) {{
            $sizeBytes = 0
            try {{ $sizeBytes = [int64]$m.Capacity }} catch {{}}
            if ($sizeBytes -le 0) {{ continue }}
            $modules += @{{
                bank_locator = [string]$m.BankLabel
                locator = [string]$m.DeviceLocator
                manufacturer = [string]$m.Manufacturer
                part_number = ([string]$m.PartNumber).Trim()
                size = ([math]::Round($sizeBytes / 1GB, 1).ToString() + ' GB')
                size_bytes = $sizeBytes
                speed = if ($m.Speed) {{ ([string]$m.Speed + ' MHz') }} else {{ '' }}
                configured_memory_speed = if ($m.ConfiguredClockSpeed) {{ ([string]$m.ConfiguredClockSpeed + ' MHz') }} else {{ '' }}
            }}
        }}
    }} catch {{}}
    $slotCount = $modules.Count
    try {{
        $array = @(Get-AgentInstances 'Win32_PhysicalMemoryArray') | Select-Object -First 1
        if ($array -and $array.MemoryDevices) {{ $slotCount = [int]$array.MemoryDevices }}
    }} catch {{}}
    $channels = New-Object System.Collections.ArrayList
    $seen = @{{}}
    $controllers = New-Object System.Collections.ArrayList
    $seenControllers = @{{}}
    foreach ($m in $modules) {{
        $label = (([string]$m.locator) + ' ' + ([string]$m.bank_locator))
        $match = [regex]::Match($label, 'Channel\s*([A-Za-z0-9]+)', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if (-not $match.Success) {{ $match = [regex]::Match($label, 'Channel([A-Za-z0-9]+)', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase) }}
        if ($match.Success) {{
            $value = $match.Groups[1].Value.ToUpper()
            if ($value -and -not $seen.ContainsKey($value)) {{ $seen[$value] = $true; [void]$channels.Add($value) }}
        }}
        $controllerMatch = [regex]::Match($label, 'Controller\s*([0-9]+)', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if ($controllerMatch.Success) {{
            $value = ('C' + $controllerMatch.Groups[1].Value)
            if (-not $seenControllers.ContainsKey($value)) {{ $seenControllers[$value] = $true; [void]$controllers.Add($value) }}
        }}
    }}
    $channelCount = [Math]::Max($channels.Count, $controllers.Count)
    $mode = 'unknown'
    if ($channelCount -ge 2) {{ $mode = 'dual' }} elseif ($channelCount -eq 1 -and $modules.Count -gt 0) {{ $mode = 'single' }}
    $totalBytes = [int64]0
    foreach ($m in $modules) {{ try {{ $totalBytes += [int64]$m.size_bytes }} catch {{}} }}
    $summary = ([string]$modules.Count + ' DIMM')
    if ($totalBytes -gt 0) {{ $summary += (' / ' + ([math]::Round($totalBytes / 1GB, 1).ToString()) + ' GB') }}
    if ($mode -ne 'unknown') {{ $summary += (' / ' + $mode + ' channel inferred') }} else {{ $summary += ' / channel unknown' }}
    return @{{
        summary = $summary
        channel_mode = $mode
        channel_count = $channelCount
        channel_inferred = ($channelCount -gt 0)
        channels = @($channels)
        installed_count = $modules.Count
        slot_count = $slotCount
        total_bytes = $totalBytes
        modules = @($modules)
    }}
}}

function Get-StorageInventory {{
    $logicalByPartition = @{{}}
    try {{
        foreach ($link in @(Get-AgentInstances 'Win32_LogicalDiskToPartition')) {{
            $partText = [string]$link.Antecedent
            $driveText = [string]$link.Dependent
            $partMatch = [regex]::Match($partText, 'Disk\s*#(\d+),\s*Partition\s*#(\d+)', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
            if (-not $partMatch.Success) {{
                $partMatch = [regex]::Match($partText, 'DiskIndex\s*=\s*"?(\d+)"?.*Index\s*=\s*"?(\d+)"?', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
            }}
            $driveMatch = [regex]::Match($driveText, 'DeviceID\s*=\s*"([^"]+)"', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
            if ($partMatch.Success -and $driveMatch.Success) {{
                $logicalByPartition[($partMatch.Groups[1].Value + ':' + $partMatch.Groups[2].Value)] = $driveMatch.Groups[1].Value
            }}
        }}
    }} catch {{}}
    $logicalByDrive = @{{}}
    try {{
        foreach ($ld in @(Get-AgentInstances 'Win32_LogicalDisk')) {{
            $logicalByDrive[[string]$ld.DeviceID] = $ld
        }}
    }} catch {{}}
    $partitionsByDisk = @{{}}
    try {{
        foreach ($p in @(Get-AgentInstances 'Win32_DiskPartition')) {{
            $key = [string]$p.DiskIndex
            if (-not $partitionsByDisk.ContainsKey($key)) {{ $partitionsByDisk[$key] = @() }}
            $drive = $logicalByPartition[([string]$p.DiskIndex + ':' + [string]$p.Index)]
            $ld = if ($drive -and $logicalByDrive.ContainsKey($drive)) {{ $logicalByDrive[$drive] }} else {{ $null }}
            $mounts = @()
            if ($drive) {{ $mounts += $drive }}
            $partitionsByDisk[$key] += @{{
                name = [string]$p.Name
                type = [string]$p.Type
                size_bytes = [int64]$p.Size
                fstype = if ($ld) {{ [string]$ld.FileSystem }} else {{ '' }}
                mountpoints = @($mounts)
                is_system = ($drive -eq $env:SystemDrive)
                used_bytes = if ($ld -and $ld.Size -gt 0) {{ [int64]($ld.Size - $ld.FreeSpace) }} else {{ 0 }}
                free_bytes = if ($ld) {{ [int64]$ld.FreeSpace }} else {{ 0 }}
                percent = if ($ld -and $ld.Size -gt 0) {{ [math]::Round((($ld.Size - $ld.FreeSpace) / $ld.Size) * 100, 1) }} else {{ 0 }}
                volume_name = if ($ld) {{ [string]$ld.VolumeName }} else {{ '' }}
                drive_type = if ($ld) {{ [int]$ld.DriveType }} else {{ 0 }}
                is_network = if ($ld) {{ [int]$ld.DriveType -eq 4 }} else {{ $false }}
                is_removable = if ($ld) {{ [int]$ld.DriveType -in @(2, 5) }} else {{ $false }}
            }}
        }}
    }} catch {{}}
    $devices = @()
    try {{
        foreach ($d in @(Get-AgentInstances 'Win32_DiskDrive')) {{
            $key = [string]$d.Index
            $parts = if ($partitionsByDisk.ContainsKey($key)) {{ @($partitionsByDisk[$key]) }} else {{ @() }}
            $devices += @{{
                name = ('Disk ' + [string]$d.Index)
                type = 'disk'
                size_bytes = [int64]$d.Size
                model = [string]$d.Model
                serial = ([string]$d.SerialNumber).Trim()
                tran = [string]$d.InterfaceType
                rotational = ([string]$d.MediaType -match 'hard disk')
                removable = ([string]$d.MediaType -match 'removable')
                mountpoints = @()
                partitions = @($parts)
                is_system = [bool](@($parts | Where-Object {{ $_.is_system }} | Select-Object -First 1))
            }}
        }}
    }} catch {{}}
    $filesystems = @()
    foreach ($device in $devices) {{
        foreach ($part in @($device.partitions)) {{
            if ($part.mountpoints -and $part.mountpoints.Count -gt 0) {{
                $fs = @{{}}
                foreach ($k in $part.Keys) {{ $fs[$k] = $part[$k] }}
                $fs['disk'] = $device.name
                $fs['model'] = $device.model
                $filesystems += $fs
            }}
        }}
    }}
    foreach ($drive in $logicalByDrive.Keys) {{
        $exists = @($filesystems | Where-Object {{ $_.mountpoints -contains $drive }} | Select-Object -First 1)
        if ($exists.Count -gt 0) {{ continue }}
        $ld = $logicalByDrive[$drive]
        $sizeBytes = 0
        $freeBytes = 0
        try {{ $sizeBytes = [int64]$ld.Size }} catch {{}}
        try {{ $freeBytes = [int64]$ld.FreeSpace }} catch {{}}
        $usedBytes = [Math]::Max(0, $sizeBytes - $freeBytes)
        $filesystems += @{{
            name = [string]$drive
            type = 'logical'
            disk = if ([int]$ld.DriveType -eq 4) {{ 'network' }} else {{ '' }}
            model = if ([int]$ld.DriveType -eq 4) {{ 'NAS / 网络存储' }} else {{ '' }}
            fstype = [string]$ld.FileSystem
            mountpoints = @([string]$drive)
            size_bytes = $sizeBytes
            used_bytes = $usedBytes
            free_bytes = $freeBytes
            percent = if ($sizeBytes -gt 0) {{ [math]::Round(($usedBytes / $sizeBytes) * 100, 1) }} else {{ 0 }}
            is_system = ([string]$drive -eq $env:SystemDrive)
            is_network = ([int]$ld.DriveType -eq 4)
            is_removable = ([int]$ld.DriveType -in @(2, 5))
            drive_type = [int]$ld.DriveType
            volume_name = [string]$ld.VolumeName
        }}
    }}
    return @{{
        devices = @($devices)
        filesystems = @($filesystems)
        disk_count = $devices.Count
        mounted_count = $filesystems.Count
    }}
}}

function Get-NetworkInventory {{
    $profiles = @{{}}
    try {{
        if (Get-CommandOrNull 'Get-NetConnectionProfile') {{
            foreach ($p in @(Get-NetConnectionProfile -ErrorAction SilentlyContinue)) {{
                $profiles[[string]$p.InterfaceAlias] = [string]$p.Name
            }}
        }}
    }} catch {{}}
    $ipByMac = @{{}}
    try {{
        foreach ($cfg in @(Get-AgentInstances 'Win32_NetworkAdapterConfiguration') | Where-Object {{ $_.MACAddress }}) {{
            $mac = ([string]$cfg.MACAddress).ToUpper()
            $ipv4 = @()
            $ipv6 = @()
            foreach ($ip in @($cfg.IPAddress)) {{
                $text = [string]$ip
                if ($text -match '^\d+\.\d+\.\d+\.\d+$') {{ $ipv4 += $text }}
                elseif ($text -and $text -match ':') {{ $ipv6 += $text }}
            }}
            $ipByMac[$mac] = @{{ ipv4 = @($ipv4); ipv6 = @($ipv6) }}
        }}
    }} catch {{}}
    $adapters = @()
    try {{
        foreach ($a in @(Get-AgentInstances 'Win32_NetworkAdapter') | Where-Object {{ $_.PhysicalAdapter -eq $true }}) {{
            $name = if ($a.NetConnectionID) {{ [string]$a.NetConnectionID }} else {{ [string]$a.Name }}
            $desc = [string]$a.Name
            $isWireless = ($desc -match 'Wi-?Fi|Wireless|WLAN|802\.11')
            $isBluetooth = ($desc -match 'Bluetooth')
            $mac = [string]$a.MACAddress
            $ipInfo = if ($mac -and $ipByMac.ContainsKey($mac.ToUpper())) {{ $ipByMac[$mac.ToUpper()] }} else {{ @{{ ipv4 = @(); ipv6 = @() }} }}
            $adapters += @{{
                name = $name
                description = $desc
                mac = $mac
                state = if ($a.NetEnabled) {{ 'up' }} else {{ 'down' }}
                speed_mbps = if ($a.Speed) {{ [math]::Round(([double]$a.Speed) / 1000000, 0) }} else {{ 0 }}
                ipv4 = @($ipInfo.ipv4)
                ipv6 = @($ipInfo.ipv6)
                is_wireless = $isWireless
                is_bluetooth = $isBluetooth
                is_virtual = ($desc -match 'Virtual|Tunnel|Tailscale|Wintun|Hyper-V|Loopback')
                ssid = if ($isWireless -and $profiles.ContainsKey($name)) {{ $profiles[$name] }} else {{ '' }}
            }}
        }}
    }} catch {{}}
    $wireless = @($adapters | Where-Object {{ $_.is_wireless }})
    $connectedWifi = @($wireless | Where-Object {{ $_.ssid }} | Select-Object -First 1)
    return @{{
        adapters = @($adapters)
        physical_count = @($adapters | Where-Object {{ -not $_.is_virtual }}).Count
        active_count = @($adapters | Where-Object {{ $_.state -eq 'up' -and -not $_.is_virtual }}).Count
        wireless = @{{
            present = ($wireless.Count -gt 0)
            connected = ($connectedWifi.Count -gt 0)
            ssid = if ($connectedWifi.Count -gt 0) {{ [string]$connectedWifi[0].ssid }} else {{ '' }}
            interfaces = @($wireless)
        }}
    }}
}}

function Get-BluetoothInventory {{
    $controllers = @()
    try {{
        foreach ($b in @(Get-AgentInstances 'Win32_PnPEntity') | Where-Object {{ ([string]$_.Name) -match 'Bluetooth' }}) {{
            $controllers += @{{
                name = [string]$b.Name
                status = [string]$b.Status
                device_id = [string]$b.DeviceID
            }}
        }}
    }} catch {{}}
    return @{{
        present = ($controllers.Count -gt 0)
        blocked = $false
        controllers = @($controllers | Select-Object -First 12)
    }}
}}

function Get-HardwareSnapshot {{
    if (-not $script:HardwareCache) {{
        $cpu = @(Get-AgentInstances 'Win32_Processor') | Select-Object -First 1
        $board = @(Get-AgentInstances 'Win32_BaseBoard') | Select-Object -First 1
        $storage = Get-StorageInventory
        $network = Get-NetworkInventory
        $script:HardwareCache = @{{
            cpu_name = if ($cpu -and $cpu.Name) {{ $cpu.Name }} else {{ 'Unknown CPU' }}
            motherboard = if ($board) {{ Get-BoardText $board }} else {{ 'Unknown motherboard' }}
            mem_speed = Get-MemorySpeed
            memory_topology = Get-MemoryTopology
            storage_devices = @($storage.devices)
            storage_filesystems = @($storage.filesystems)
            storage_summary = @{{ disk_count = $storage.disk_count; mounted_count = $storage.mounted_count }}
            network_adapters = @($network.adapters)
            network_summary = @{{ physical_count = $network.physical_count; active_count = $network.active_count }}
            wireless = $network.wireless
            bluetooth = Get-BluetoothInventory
            hardware_refreshed_at = (Get-Date).ToString('o')
        }}
    }}
    return $script:HardwareCache
}}

function Get-StatusPayload([hashtable]$cfg) {{
    Write-StageLog 'payload' 'start'
    $reportGeneratedAt = (Get-Date).ToString('o')
    $machineMac = Get-MacAddress
    $machineIp = Get-PrimaryIPv4
    if ($machineMac) {{ $cfg['machine_mac'] = $machineMac }}
    if ($machineIp) {{ $cfg['machine_ip'] = $machineIp }}
    $hardware = $null
    Write-StageLog 'hardware' 'start'
    try {{
        $hardware = Get-HardwareSnapshot
        Write-StageLog 'hardware' 'ok'
    }} catch {{
        Write-StageLog 'hardware' ('failed: ' + (Get-ErrorDetails $_))
        $hardware = @{{
            cpu_name = 'Unknown CPU'
            motherboard = 'Unknown motherboard'
            mem_speed = 0
            hardware_refreshed_at = ''
        }}
    }}
    $os = $null
    Write-StageLog 'os' 'start'
    try {{
        $os = @(Get-AgentInstances 'Win32_OperatingSystem') | Select-Object -First 1
        Write-StageLog 'os' 'ok'
    }} catch {{
        Write-StageLog 'os' ('failed: ' + (Get-ErrorDetails $_))
    }}
    $logicalDisk = $null
    Write-StageLog 'disk' 'start'
    try {{
        $logicalDisk = @(Get-AgentInstances 'Win32_LogicalDisk' "DeviceID='C:'") | Select-Object -First 1
        Write-StageLog 'disk' 'ok'
    }} catch {{
        Write-StageLog 'disk' ('failed: ' + (Get-ErrorDetails $_))
    }}
    $memUsed = 0
    $memTotal = 0
    $memPercent = 0
    if ($os) {{
        try {{
            $memUsed = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / 1MB, 2)
            $memTotal = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
            $memPercent = if ($memTotal -gt 0) {{ [math]::Round(($memUsed / $memTotal) * 100, 1) }} else {{ 0 }}
        }} catch {{}}
    }}
    $diskPercent = 0
    if ($logicalDisk -and $logicalDisk.Size -gt 0) {{
        try {{
            $diskPercent = [math]::Round((($logicalDisk.Size - $logicalDisk.FreeSpace) / $logicalDisk.Size) * 100, 1)
        }} catch {{}}
    }}
    $cpuPercent = 0
    Write-StageLog 'cpu_counter' 'start'
    try {{
        if (Get-CommandOrNull 'Get-Counter') {{
            $cpuPercent = [math]::Round((Get-Counter '\\Processor(_Total)\\% Processor Time').CounterSamples[0].CookedValue, 1)
        }}
        Write-StageLog 'cpu_counter' 'ok'
    }} catch {{
        Write-StageLog 'cpu_counter' ('failed: ' + (Get-ErrorDetails $_))
    }}
    $netSpeed = @(0, 0)
    Write-StageLog 'network' 'start'
    try {{
        $netSpeed = Get-NetSpeed
        Write-StageLog 'network' 'ok'
    }} catch {{
        Write-StageLog 'network' ('failed: ' + (Get-ErrorDetails $_))
    }}
    Write-StageLog 'task_info' 'start'
    $taskInfo = Get-AgentTaskInfo
    Write-StageLog 'task_info' 'ok'
    Write-StageLog 'gpu' 'start'
    $gpuInfo = @()
    try {{
        $gpuInfo = @(Get-GpuInfo)
        Write-StageLog 'gpu' ('ok count=' + [string]$gpuInfo.Count)
    }} catch {{
        Write-StageLog 'gpu' ('failed: ' + (Get-ErrorDetails $_))
    }}
    Write-StageLog 'codemeter' 'start'
    $codemeterInfo = $null
    try {{
        $codemeterInfo = Get-CodeMeterInfo
        Write-StageLog 'codemeter' 'ok'
    }} catch {{
        Write-StageLog 'codemeter' ('failed: ' + (Get-ErrorDetails $_))
        $codemeterInfo = @{{
            installed = $false
            running = $false
            summary = 'probe_failed'
            level = 'warning'
            checked_at = (Get-Date).ToString('o')
            error = Get-ErrorDetails $_
        }}
    }}

    $payload = @{{
        mac = $machineMac
        hostname = $env:COMPUTERNAME
        ip = $machineIp
        timestamp = $reportGeneratedAt
        wake_proxy_result = $script:WakeProxyResult
        status = @{{
            cpu_name = $hardware.cpu_name
            motherboard = $hardware.motherboard
            mem_speed = $hardware.mem_speed
            memory_topology = $hardware.memory_topology
            storage_devices = @($hardware.storage_devices)
            storage_filesystems = @($hardware.storage_filesystems)
            storage_summary = $hardware.storage_summary
            network_adapters = @($hardware.network_adapters)
            network_summary = $hardware.network_summary
            wireless = $hardware.wireless
            bluetooth = $hardware.bluetooth
            cpu_percent = $cpuPercent
            mem_used = $memUsed
            mem_total = $memTotal
            mem_percent = $memPercent
            disk_percent = $diskPercent
            net_sent_kb_s = [double]$netSpeed.sent_kb_s
            net_recv_kb_s = [double]$netSpeed.recv_kb_s
            network_primary = @{{
                adapter_name = [string]$netSpeed.adapter_name
                adapter_description = [string]$netSpeed.adapter_description
                adapter_ip = [string]$netSpeed.adapter_ip
                link_speed_mbps = [double]$netSpeed.link_speed_mbps
                sample_scope = [string]$netSpeed.sample_scope
            }}
            gpu_list = @($gpuInfo)
            gpu_diagnostics = Remove-AgentDiagnosticNoise $script:GpuProbeDiagnostic
            codemeter = $codemeterInfo
            os_info = @{{
                name = if ($os) {{ [string]$os.Caption }} else {{ '' }}
                version = if ($os) {{ [string]$os.Version }} else {{ '' }}
                build = if ($os) {{ [string]$os.BuildNumber }} else {{ '' }}
                arch = if ($os) {{ [string]$os.OSArchitecture }} else {{ '' }}
                kernel = if ($os) {{ [string]$os.Version }} else {{ '' }}
            }}
            os_caption = if ($os) {{ $os.Caption }} else {{ '' }}
            os_version = if ($os) {{ $os.Version }} else {{ '' }}
            hardware_refreshed_at = $hardware.hardware_refreshed_at
            report_generated_at = $reportGeneratedAt
                agent = @{{
                    version = $AgentVersion
                    machine_mac = $machineMac
                    machine_ip = $machineIp
                    hostname = $env:COMPUTERNAME
                    current_server_url = $cfg['current_server_url']
                candidate_hosts = @($cfg['candidate_hosts'])
                report_interval_sec = [int]$cfg['report_interval_sec']
                config_updated_at = $cfg['config_updated_at']
                last_config_sync_at = $cfg['last_config_sync_at']
                last_discovery_at = $cfg['last_discovery_at']
                ntp_enabled = [bool]$cfg['ntp_enabled']
                ntp_primary = $cfg['ntp_primary']
                ntp_fallback = $cfg['ntp_fallback']
                last_ntp_check_at = $cfg['last_ntp_check_at']
                ntp_configured_at = $cfg['ntp_configured_at']
                ntp_last_result = $cfg['ntp_last_result']
                task_name = $TaskName
                task_exists = $taskInfo.exists
                task_state = $taskInfo.state
                task_user = $taskInfo.user
	                task_last_run_time = $taskInfo.last_run_time
	                task_next_run_time = $taskInfo.next_run_time
	                worker_path = $WorkerPath
	                self_update = $script:SelfUpdateStatus
            }}
        }}
    }}
    Write-StageLog 'payload' 'ok'
    return $payload
}}

try {{
    New-Item -ItemType Directory -Force -Path $AgentDir | Out-Null
    Enter-AgentRunLock
    Write-AgentLog ('worker run starting version=' + $AgentVersion)
    $config = Load-AgentConfig
    Write-AgentLog ('config loaded current=' + [string]$config['current_server_url'])
    $config = Find-AvailableServer $config
    $config = Invoke-NtpAutoConfigure $config
    Save-AgentConfig $config
    Send-AgentHeartbeat $config
    $identityMac = Get-MacAddress
    $identityIp = Get-PrimaryIPv4
    if ($identityMac) {{ $config['machine_mac'] = $identityMac }}
    if ($identityIp) {{ $config['machine_ip'] = $identityIp }}
    Save-AgentConfig $config
    Write-AgentLog ('identity mac=' + [string]$identityMac + ' ip=' + [string]$identityIp)
    Write-AgentLog ('active server=' + [string]$config['current_server_url'])
}} catch {{
    try {{
        Write-AgentLog ('worker startup failed: ' + (Get-ErrorDetails $_))
    }} catch {{}}
    Exit-AgentRunLock
    exit 1
}}

try {{
    if ($config['last_config_sync_at']) {{
        try {{
            $secondsSinceSync = ((Get-Date) - [datetime]::Parse($config['last_config_sync_at'])).TotalSeconds
        }} catch {{
            $secondsSinceSync = [int]$config['sync_interval_sec']
        }}
    }} else {{
        $secondsSinceSync = [int]$config['sync_interval_sec']
    }}
    if ($secondsSinceSync -ge [int]$config['sync_interval_sec']) {{
        $config = Find-AvailableServer $config
    }}

    $payload = ConvertTo-AgentJson (Get-StatusPayload $config) 8
    $payloadBytes = [System.Text.Encoding]::UTF8.GetByteCount($payload)
    Write-AgentLog ('payload bytes=' + [string]$payloadBytes)
    try {{
        $payloadProbe = $payload | ConvertFrom-Json
        Write-AgentLog ('payload timestamp=' + [string]$payloadProbe.timestamp + ' status_generated=' + [string]$payloadProbe.status.report_generated_at)
    }} catch {{}}
    $reportUrl = $config['current_server_url'].TrimEnd('/') + $config['report_path']
    $response = Invoke-AgentJsonRequest -Uri $reportUrl -Method Post -ContentType 'application/json' -Body $payload -TimeoutSec 8
    if ($response -and $response.status -eq 'ignored') {{
        Write-AgentLog ('report ignored by server: ' + [string]$response.reason + ' -> ' + $reportUrl)
    }} else {{
        Write-AgentLog ('report ok -> ' + $reportUrl)
    }}
    if ($response -and $response.agent_config) {{
        $incomingConfig = Convert-ToHashtable $response.agent_config
        if (Invoke-AgentSelfUpdate $config $incomingConfig) {{
            Exit-AgentRunLock
            exit 0
        }}
        Merge-AgentConfig $config $incomingConfig | Out-Null
        $config['last_config_sync_at'] = (Get-Date).ToString('o')
        Save-AgentConfig $config
    }}
    if ($response.command -eq 'refresh') {{
        $script:HardwareCache = $null
        Write-AgentLog 'refresh command received'
    }} elseif ($response.command -eq 'shutdown') {{
        Write-AgentLog 'shutdown command received'
        Stop-Computer -Force
    }} elseif ($response.command -eq 'restart') {{
        Write-AgentLog 'restart command received'
        Restart-Computer -Force
    }} elseif ($response.command -and $response.command.action -eq 'wake_proxy') {{
        $targetMac = [string]$response.command.mac
        $targetIp = [string]$response.command.ip
        if ($targetMac) {{
            try {{
                $cleanMac = ($targetMac -replace '[^0-9A-Fa-f]', '').ToUpperInvariant()
                if ($cleanMac.Length -ne 12) {{ throw 'invalid wake mac' }}
                $ports = @(9, 7)
                $targets = New-Object System.Collections.Generic.List[string]
                $targets.Add('255.255.255.255') | Out-Null
                if ($targetIp) {{
                    try {{
                        $networkBytes = [System.Net.IPAddress]::Parse($targetIp).GetAddressBytes()
                        $networkBytes[3] = 255
                        $targets.Add(([System.Net.IPAddress]::new($networkBytes)).ToString()) | Out-Null
                    }} catch {{}}
                }}
                $uniqueTargets = @($targets | Where-Object {{ $_ }} | Select-Object -Unique)
                foreach ($attempt in 1..3) {{
                    foreach ($broadcastTarget in $uniqueTargets) {{
                        foreach ($port in $ports) {{
                            $udp = New-Object System.Net.Sockets.UdpClient
                            try {{
                                $udp.EnableBroadcast = $true
                                $packet = New-Object byte[] 102
                                for ($i = 0; $i -lt 6; $i++) {{ $packet[$i] = 0xFF }}
                                $macBytes = New-Object byte[] 6
                                for ($i = 0; $i -lt 6; $i++) {{
                                    $macBytes[$i] = [Convert]::ToByte($cleanMac.Substring($i * 2, 2), 16)
                                }}
                                for ($block = 0; $block -lt 16; $block++) {{
                                    [Array]::Copy($macBytes, 0, $packet, 6 + ($block * 6), 6)
                                }}
                                [void]$udp.Send($packet, $packet.Length, $broadcastTarget, $port)
                            }} finally {{
                                $udp.Close()
                            }}
                        }}
                    }}
                    Start-Sleep -Milliseconds 120
                }}
                $script:WakeProxyResult = @{{
                    ok = $true
                    mac = $targetMac
                    ip = $targetIp
                    targets = @($uniqueTargets)
                    ports = @($ports)
                    attempts = 3
                    sent_at = (Get-Date).ToString('o')
                }}
                Write-AgentLog ('wake proxy sent mac=' + $targetMac + ' ip=' + $targetIp + ' targets=' + ($uniqueTargets -join ',') + ' ports=' + ($ports -join ','))
            }} catch {{
                $script:WakeProxyResult = @{{
                    ok = $false
                    mac = $targetMac
                    ip = $targetIp
                    error = (Get-ErrorDetails $_)
                    sent_at = (Get-Date).ToString('o')
                }}
                Write-AgentLog ('wake proxy failed mac=' + $targetMac + ': ' + (Get-ErrorDetails $_))
            }}
            if ($script:WakeProxyResult) {{
                try {{
                    $proxyPayload = @{{
                        mac = Get-MacAddress
                        hostname = $env:COMPUTERNAME
                        ip = Get-PrimaryIPv4
                        timestamp = (Get-Date).ToString('o')
                        wake_proxy_result = $script:WakeProxyResult
                        status = @{{
                            agent = @{{
                                version = $AgentVersion
                                current_server_url = $config['current_server_url']
                            }}
                        }}
                    }}
                    $proxyPayload = ConvertTo-AgentJson $proxyPayload 8
                    Invoke-AgentJsonRequest -Uri $reportUrl -Method Post -ContentType 'application/json' -Body $proxyPayload -TimeoutSec 8 | Out-Null
                    Write-AgentLog 'wake proxy result reported'
                }} catch {{
                    Write-AgentLog ('wake proxy result report failed: ' + (Get-ErrorDetails $_))
                }}
            }}
        }}
    }}
}} catch {{
    Write-AgentLog ('worker run failed: ' + (Get-ErrorDetails $_))
    Exit-AgentRunLock
    exit 1
}}
Exit-AgentRunLock
exit 0
"""

def build_agent_launcher_script():
    return """$ErrorActionPreference = 'Continue'
$LauncherVersion = '__AGENT_VERSION__'
$AgentDir = Join-Path $env:ProgramData 'SmartCenterAgent'
$WorkerPath = Join-Path $AgentDir 'agent_worker.ps1'
$LauncherPath = if ($PSCommandPath) { $PSCommandPath } else { Join-Path $AgentDir 'agent_launcher.ps1' }
$ConfigPath = Join-Path $AgentDir 'agent_config.json'
$RunnerLogPath = Join-Path $AgentDir 'agent_runner.log'
$Utf8Encoding = New-Object System.Text.UTF8Encoding($true)

function Append-TextFile([string]$path, [string]$content) {
    $parent = [System.IO.Path]::GetDirectoryName($path)
    if ($parent) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    [System.IO.File]::AppendAllText($path, ([string]$content + [Environment]::NewLine), $Utf8Encoding)
}

function Write-RunnerLog([string]$msg) {
    Append-TextFile $RunnerLogPath ("[" + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + "] " + $msg)
}

function Read-AgentConfig {
    try {
        if (Test-Path $ConfigPath) {
            return Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        }
    } catch {}
    return $null
}

function Write-TextFile([string]$path, [string]$content) {
    $parent = [System.IO.Path]::GetDirectoryName($path)
    if ($parent) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    [System.IO.File]::WriteAllText($path, [string]$content, $Utf8Encoding)
}

function Try-LauncherSelfUpdate {
    try {
        $cfg = Read-AgentConfig
        if (-not $cfg -or -not $cfg.current_server_url) { return $false }
        $baseUrl = ([string]$cfg.current_server_url).TrimEnd('/')
        $configPath = if ($cfg.config_path) { [string]$cfg.config_path } else { '/agent/config' }
        $workerPath = if ($cfg.worker_path) { [string]$cfg.worker_path } else { '/agent/worker.json' }
        $launcherPath = if ($cfg.launcher_path) { [string]$cfg.launcher_path } else { '/agent/launcher.json' }
        $remote = Invoke-RestMethod -Uri ($baseUrl + $configPath + '?probe=1&launcher=1&ts=' + [uri]::EscapeDataString((Get-Date).Ticks)) -Method Get -TimeoutSec 5 -ErrorAction Stop
        $remoteVersion = ''
        if ($remote.version) { $remoteVersion = [string]$remote.version }
        elseif ($remote.agent_config -and $remote.agent_config.version) { $remoteVersion = [string]$remote.agent_config.version }
        if (-not $remoteVersion -or $remoteVersion -eq $LauncherVersion) { return $false }
        $workerJson = Invoke-RestMethod -Uri ($baseUrl + $workerPath + '?launcher=1&v=' + [uri]::EscapeDataString($remoteVersion) + '&ts=' + [uri]::EscapeDataString((Get-Date).Ticks)) -Method Get -TimeoutSec 12 -ErrorAction Stop
        $workerText = ''
        if ($workerJson -and $workerJson.worker_b64) {
            $workerText = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String([string]$workerJson.worker_b64))
        }
        if (-not $workerText -or $workerText -notmatch [regex]::Escape($remoteVersion)) {
            throw 'launcher downloaded worker version mismatch'
        }
        $launcherText = ''
        try {
            $launcherJson = Invoke-RestMethod -Uri ($baseUrl + $launcherPath + '?launcher=1&v=' + [uri]::EscapeDataString($remoteVersion) + '&ts=' + [uri]::EscapeDataString((Get-Date).Ticks)) -Method Get -TimeoutSec 12 -ErrorAction Stop
            if ($launcherJson -and $launcherJson.launcher_b64) {
                $launcherText = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String([string]$launcherJson.launcher_b64))
            }
            if ($launcherText -and $launcherText -notmatch [regex]::Escape($remoteVersion)) {
                Write-RunnerLog 'launcher self-update skipped: downloaded launcher version mismatch'
                $launcherText = ''
            }
        } catch {
            Write-RunnerLog ('launcher self-update download failed, worker update will continue: ' + $_.Exception.Message)
        }
        if (Test-Path $WorkerPath) {
            Copy-Item -LiteralPath $WorkerPath -Destination ($WorkerPath + '.launcher_bak_' + (Get-Date).ToString('yyyyMMddHHmmss')) -Force -ErrorAction SilentlyContinue
        }
        Write-TextFile $WorkerPath $workerText
        if ($launcherText) {
            if (Test-Path $LauncherPath) {
                Copy-Item -LiteralPath $LauncherPath -Destination ($LauncherPath + '.launcher_bak_' + (Get-Date).ToString('yyyyMMddHHmmss')) -Force -ErrorAction SilentlyContinue
            }
            Write-TextFile $LauncherPath $launcherText
        }
        Write-RunnerLog ('launcher self-updated worker/launcher ' + $LauncherVersion + ' -> ' + $remoteVersion)
        return $true
    } catch {
        Write-RunnerLog ('launcher self-update failed: ' + $_.Exception.Message)
        return $false
    }
}

Write-RunnerLog ('launcher started version=' + $LauncherVersion)
try {
    Try-LauncherSelfUpdate | Out-Null
    if (-not (Test-Path $WorkerPath)) {
        throw ('missing worker script: ' + $WorkerPath)
    }
    $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$WorkerPath) -WindowStyle Hidden -PassThru -RedirectStandardOutput ($AgentDir + '\\worker_stdout.log') -RedirectStandardError ($AgentDir + '\\worker_stderr.log')
    if (-not $proc.WaitForExit(45 * 1000)) {
        Write-RunnerLog ('worker timed out after 45s, killing pid=' + $proc.Id)
        try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
        exit 124
    }
    $workerExitCode = $proc.ExitCode
    if ($workerExitCode -ne 0) {
        Write-RunnerLog ('worker exited with code ' + $workerExitCode)
        exit $workerExitCode
    }
    Write-RunnerLog 'worker exited successfully'
} catch {
    Write-RunnerLog ('launcher failed: ' + $_.Exception.Message)
    throw
}
""".replace("__AGENT_VERSION__", AGENT_VERSION)

def build_agent_bootstrap_script(server_host):
    initial_config_json = json.dumps(build_agent_runtime_config(server_host), ensure_ascii=False, indent=2)
    worker_b64 = __import__("base64").b64encode(build_agent_worker_script(server_host).encode("utf-8")).decode("ascii")
    launcher_b64 = __import__("base64").b64encode(build_agent_launcher_script().encode("utf-8")).decode("ascii")
    config_b64 = __import__("base64").b64encode(initial_config_json.encode("utf-8")).decode("ascii")
    return f"""$ErrorActionPreference = 'Stop'
$ServerHost = '{server_host}'
$AgentVersion = '{AGENT_VERSION}'
$AgentDir = Join-Path $env:ProgramData 'SmartCenterAgent'
$WorkerPath = Join-Path $AgentDir 'agent_worker.ps1'
$LauncherPath = Join-Path $AgentDir 'agent_launcher.ps1'
$ConfigPath = Join-Path $AgentDir 'agent_config.json'
$DeployLogPath = Join-Path $AgentDir 'deploy.log'
$AgentLogPath = Join-Path $AgentDir 'agent.log'
$TaskName = 'SmartCenterAgent'
$LegacyTaskNames = @('SmartCenterAgentUser', 'SmartCenterAgentStartup', 'SmartCenterAgentBootstrap', 'SmartCenter Windows Agent', 'Smart Center Agent')
$LegacyAgentDirs = @()
try {{
    if ($env:LOCALAPPDATA) {{
        $LegacyAgentDirs += (Join-Path $env:LOCALAPPDATA 'SmartCenterAgent')
    }}
}} catch {{}}
$Utf8Encoding = New-Object System.Text.UTF8Encoding($true)

function Write-DeployLog([string]$msg) {{
    $parent = [System.IO.Path]::GetDirectoryName($DeployLogPath)
    if ($parent) {{
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }}
    [System.IO.File]::AppendAllText($DeployLogPath, ("[" + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + "] " + $msg + [Environment]::NewLine), $Utf8Encoding)
    Write-Host $msg
}}

function Get-LogTail([string]$path, [int]$lineCount = 20) {{
    try {{
        if (-not (Test-Path $path)) {{
            return ''
        }}
        $lines = Get-Content $path -Tail $lineCount -ErrorAction Stop
        return (($lines | ForEach-Object {{ [string]$_ }}) -join ' || ')
    }} catch {{
        return ''
    }}
}}

function Write-TextFile([string]$path, [string]$content) {{
    $parent = [System.IO.Path]::GetDirectoryName($path)
    if ($parent) {{
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }}
    if (Test-Path $path -PathType Container) {{
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
    }}
    [System.IO.File]::WriteAllText($path, [string]$content, $Utf8Encoding)
}}

function Format-MacAddress([string]$raw) {{
    $text = [string]$raw
    if (-not $text) {{
        return ''
    }}
    $compact = ($text -replace '[^0-9A-Fa-f]', '').ToUpper()
    if ($compact.Length -ne 12) {{
        return ''
    }}
    return ($compact.Substring(0, 2) + '-' + $compact.Substring(2, 2) + '-' + $compact.Substring(4, 2) + '-' + $compact.Substring(6, 2) + '-' + $compact.Substring(8, 2) + '-' + $compact.Substring(10, 2))
}}

function Get-MacAddress {{
    try {{
        $adapters = Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object {{
            $_.IPEnabled -eq $true -and $_.MACAddress -and $_.IPAddress
        }}
        $adapter = $adapters | Sort-Object -Property IPConnectionMetric, InterfaceIndex | Select-Object -First 1
        if ($adapter) {{
            return (Format-MacAddress ([string]$adapter.MACAddress))
        }}
    }} catch {{}}
    try {{
        $adapters = Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object {{
            $_.MACAddress
        }}
        $adapter = $adapters | Sort-Object -Property IPEnabled, IPConnectionMetric, InterfaceIndex -Descending | Select-Object -First 1
        if ($adapter) {{
            return (Format-MacAddress ([string]$adapter.MACAddress))
        }}
    }} catch {{}}
    try {{
        $interfaces = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() | Where-Object {{
            $_.OperationalStatus -eq [System.Net.NetworkInformation.OperationalStatus]::Up -and
            $_.GetPhysicalAddress() -and
            $_.GetPhysicalAddress().ToString()
        }}
        foreach ($iface in $interfaces) {{
            $formatted = Format-MacAddress ($iface.GetPhysicalAddress().ToString())
            if ($formatted) {{
                return $formatted
            }}
        }}
    }} catch {{}}
    try {{
        if (Test-Path $ConfigPath) {{
            $storedJson = (Get-Content $ConfigPath -Raw -Encoding UTF8) | ConvertFrom-Json
            $storedMac = Format-MacAddress ([string]$storedJson.machine_mac)
            if ($storedMac) {{ return $storedMac }}
        }}
    }} catch {{}}
    return ''
}}

function Get-PrimaryIPv4 {{
    try {{
        $adapters = Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object {{
            $_.IPEnabled -eq $true -and $_.IPAddress
        }}
        foreach ($adapter in @($adapters | Sort-Object -Property IPConnectionMetric, InterfaceIndex)) {{
            $ipv4 = $adapter.IPAddress | Where-Object {{ $_ -match '^\\d+\\.\\d+\\.\\d+\\.\\d+$' -and $_ -notlike '169.254.*' -and $_ -ne '127.0.0.1' }} | Select-Object -First 1
            if ($ipv4) {{
                return $ipv4
            }}
        }}
    }} catch {{}}
    try {{
        $hostEntry = [System.Net.Dns]::GetHostEntry([System.Net.Dns]::GetHostName())
        foreach ($address in $hostEntry.AddressList) {{
            $text = [string]$address
            if ($text -match '^\\d+\\.\\d+\\.\\d+\\.\\d+$' -and $text -notlike '169.254.*' -and $text -ne '127.0.0.1') {{
                return $text
            }}
        }}
    }} catch {{}}
    return ''
}}

function Stop-AgentProcesses {{
    try {{
        $targets = Get-CimInstance Win32_Process | Where-Object {{
            $_.CommandLine -and (
                $_.CommandLine -like '*SmartCenterAgent*agent_worker.ps1*' -or
                $_.CommandLine -like '*SmartCenterAgent*agent_launcher.ps1*' -or
                $_.CommandLine -like '*ProgramData*SmartCenterAgent*'
            )
        }}
        foreach ($proc in $targets) {{
            if ($proc.ProcessId -eq $PID) {{ continue }}
            try {{
                Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
                Write-DeployLog ('stopped old process pid=' + $proc.ProcessId)
            }} catch {{}}
        }}
    }} catch {{}}
}}

function Remove-SmartCenterScheduledTasks {{
    try {{
        $taskOutput = @(& schtasks.exe /Query /FO CSV /NH 2>$null)
        foreach ($line in $taskOutput) {{
            $text = [string]$line
            if (-not $text) {{ continue }}
            $columns = @($text -split '","' | ForEach-Object {{ ([string]$_).Trim('"') }})
            $taskPath = if ($columns.Count -gt 0) {{ [string]$columns[0] }} else {{ '' }}
            if (-not $taskPath) {{ continue }}
            $taskNameOnly = Split-Path $taskPath -Leaf
            if ($taskPath -like '*SmartCenter*' -or $taskPath -like '*Smart Center*' -or $taskNameOnly -eq $TaskName -or $taskNameOnly -eq ($TaskName + '_OnStart')) {{
                try {{
                    $result = Invoke-Schtasks -Arguments @('/Delete', '/TN', $taskPath, '/F') -AllowFailure
                    if ($result.exit_code -eq 0) {{
                        Write-DeployLog ('removed scheduled task: ' + $taskPath)
                    }} else {{
                        Write-DeployLog ('scheduled task remove returned exit=' + $result.exit_code + ': ' + $taskPath)
                    }}
                }} catch {{
                    Write-DeployLog ('scheduled task remove failed: ' + $taskPath + ' ' + $_.Exception.Message)
                }}
            }}
        }}
    }} catch {{
        Write-DeployLog ('scheduled task scan failed: ' + $_.Exception.Message)
    }}
    try {{
        if (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue) {{
            $tasks = Get-ScheduledTask | Where-Object {{
                $_.TaskName -like '*SmartCenter*' -or $_.TaskName -like '*Smart Center*' -or $_.TaskName -eq $TaskName -or $_.TaskName -eq ($TaskName + '_OnStart')
            }}
            foreach ($task in $tasks) {{
                try {{
                    Unregister-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
                    Write-DeployLog ('unregistered scheduled task: ' + $task.TaskPath + $task.TaskName)
                }} catch {{}}
            }}
        }}
    }} catch {{
        Write-DeployLog ('powershell scheduled task scan failed: ' + $_.Exception.Message)
    }}
}}

function Remove-LegacyAgent {{
    foreach ($legacyTask in $LegacyTaskNames) {{
        if (-not $legacyTask) {{ continue }}
        try {{
            $result = Invoke-Schtasks -Arguments @('/Delete', '/TN', $legacyTask, '/F') -AllowFailure
            if ($result.exit_code -eq 0) {{
                Write-DeployLog ('legacy scheduled task removed: ' + $legacyTask)
            }}
        }} catch {{
            Write-DeployLog ('legacy scheduled task cleanup failed: ' + $legacyTask + ' ' + $_.Exception.Message)
        }}
        try {{
            Unregister-ScheduledTask -TaskName $legacyTask -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
        }} catch {{}}
    }}
    foreach ($legacyDir in $LegacyAgentDirs) {{
        try {{
            if ($legacyDir -and (Test-Path $legacyDir) -and ($legacyDir -ne $AgentDir)) {{
                $backup = $legacyDir + '.legacy_' + (Get-Date).ToString('yyyyMMddHHmmss')
                Move-Item -LiteralPath $legacyDir -Destination $backup -Force -ErrorAction Stop
                Write-DeployLog ('legacy agent dir moved: ' + $legacyDir + ' -> ' + $backup)
            }}
        }} catch {{
            Write-DeployLog ('legacy agent dir cleanup failed: ' + $legacyDir + ' ' + $_.Exception.Message)
        }}
    }}
}}

function Invoke-Schtasks {{
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$AllowFailure
    )
    $output = @(& schtasks.exe @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    $joinedOutput = (($output | ForEach-Object {{ [string]$_ }}) -join ' | ').Trim()
    if ($joinedOutput) {{
        Write-DeployLog ('schtasks ' + (($Arguments | ForEach-Object {{
            if ([string]$_ -match '\\s') {{ '"' + [string]$_ + '"' }} else {{ [string]$_ }}
        }}) -join ' ') + ' => ' + $joinedOutput)
    }}
    if ($exitCode -ne 0 -and -not $AllowFailure) {{
        if (-not $joinedOutput) {{ $joinedOutput = 'no output' }}
        throw ('schtasks failed (' + $exitCode + '): ' + $joinedOutput)
    }}
    return @{{
        exit_code = $exitCode
        output = @($output)
    }}
}}

function Remove-AgentTask {{
    $removed = $false
    try {{
        $result = Invoke-Schtasks -Arguments @('/Delete', '/TN', $TaskName, '/F') -AllowFailure
        if ($result.exit_code -eq 0) {{
            $removed = $true
            Write-DeployLog 'old scheduled task removed via schtasks'
        }}
    }} catch {{}}
    if (-not $removed) {{
        try {{
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
            Write-DeployLog 'old scheduled task removed via powershell'
        }} catch {{}}
    }}
    try {{
        $startupResult = Invoke-Schtasks -Arguments @('/Delete', '/TN', ($TaskName + '_OnStart'), '/F') -AllowFailure
        if ($startupResult.exit_code -eq 0) {{
            Write-DeployLog 'old startup scheduled task removed via schtasks'
        }}
    }} catch {{}}
    try {{
        Unregister-ScheduledTask -TaskName ($TaskName + '_OnStart') -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
    }} catch {{}}
}}

function Register-AgentTask {{
    $taskCommand = 'powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $LauncherPath + '"'
    $startTime = (Get-Date).AddMinutes(1).ToString('HH:mm')
    $baseArgs = @('/Create', '/SC', 'MINUTE', '/MO', '1', '/TN', $TaskName, '/TR', $taskCommand, '/ST', $startTime, '/RU', 'SYSTEM', '/F')
    try {{
        Invoke-Schtasks -Arguments ($baseArgs + @('/RL', 'HIGHEST')) | Out-Null
    }} catch {{
        Write-DeployLog ('create task with highest run level failed, retrying: ' + $_.Exception.Message)
        Invoke-Schtasks -Arguments $baseArgs | Out-Null
    }}
    Write-DeployLog 'scheduled task registered'
    try {{
        $startResult = Invoke-Schtasks -Arguments @('/Create', '/SC', 'ONSTART', '/TN', ($TaskName + '_OnStart'), '/TR', $taskCommand, '/RU', 'SYSTEM', '/F', '/RL', 'HIGHEST') -AllowFailure
        if ($startResult.exit_code -eq 0) {{
            Write-DeployLog 'startup scheduled task registered'
        }} else {{
            Write-DeployLog ('startup scheduled task registration returned exit=' + $startResult.exit_code)
        }}
    }} catch {{
        Write-DeployLog ('startup scheduled task registration failed: ' + $_.Exception.Message)
        try {{
            Invoke-Schtasks -Arguments @('/Create', '/SC', 'ONSTART', '/TN', ($TaskName + '_OnStart'), '/TR', $taskCommand, '/RU', 'SYSTEM', '/F') -AllowFailure | Out-Null
        }} catch {{}}
    }}
}}

function Start-AgentTask {{
    $result = Invoke-Schtasks -Arguments @('/Run', '/TN', $TaskName) -AllowFailure
    if ($result.exit_code -eq 0) {{
        Write-DeployLog 'scheduled task start requested'
    }} else {{
        Write-DeployLog ('scheduled task start failed with exit=' + $result.exit_code)
    }}
}}

New-Item -ItemType Directory -Force -Path $AgentDir | Out-Null
Write-DeployLog ('deployment started version=' + $AgentVersion)
Remove-AgentTask
Remove-SmartCenterScheduledTasks
Stop-AgentProcesses
Remove-LegacyAgent
Stop-AgentProcesses
Start-Sleep -Milliseconds 600

$worker = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{worker_b64}'))
Write-TextFile $WorkerPath $worker
$launcher = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{launcher_b64}'))
Write-TextFile $LauncherPath $launcher
$agentConfig = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{config_b64}'))
Write-TextFile $ConfigPath $agentConfig
Write-DeployLog 'agent files written'
try {{
    $writtenWorker = Get-Content $WorkerPath -Raw -Encoding UTF8
    if ($writtenWorker -notmatch [regex]::Escape($AgentVersion)) {{
        throw 'worker version verify failed'
    }}
    Write-DeployLog ('worker version verified: ' + $AgentVersion)
}} catch {{
    Write-DeployLog ('worker version verify failed: ' + $_.Exception.Message)
    throw
}}

Register-AgentTask
Write-DeployLog 'scheduled task will take over on next minute tick'

$initialWorkerExitCode = 202
$initialWorkerLogTail = 'initial worker run skipped during install; scheduled task will take over'

try {{
    $bootstrapPayload = @{{
        mac = Get-MacAddress
        hostname = $env:COMPUTERNAME
        ip = Get-PrimaryIPv4
        timestamp = (Get-Date).ToString('o')
        status = @{{
            agent = @{{
                version = $AgentVersion
                current_server_url = 'http://' + $ServerHost + ':{get_agent_server_port()}'
                task_name = $TaskName
                task_exists = $true
                bootstrap = $true
                initial_worker_exit_code = $initialWorkerExitCode
                initial_worker_log_tail = $initialWorkerLogTail
                worker_path = $WorkerPath
                launcher_path = $LauncherPath
                deploy_log_path = $DeployLogPath
            }}
        }}
    }} | ConvertTo-Json -Depth 6
    Invoke-RestMethod -Uri ('http://' + $ServerHost + ':{get_agent_server_port()}/report') -Method Post -ContentType 'application/json' -Body $bootstrapPayload -TimeoutSec 5 -ErrorAction Stop | Out-Null
    Write-DeployLog 'bootstrap heartbeat posted'
}} catch {{
    Write-DeployLog ('bootstrap heartbeat failed: ' + $_.Exception.Message)
}}

try {{
    Start-AgentTask
}} catch {{
    Write-DeployLog ('scheduled task async start request failed: ' + $_.Exception.Message)
}}

Write-Host 'SmartCenterAgent deployed and started'
Write-Host ('Server: http://' + $ServerHost + ':{get_agent_server_port()}')
Write-Host ('Deploy log: ' + $DeployLogPath)
"""

def build_deploy_bat(server_host):
    port = get_agent_server_port()
    ps_url = f"http://{server_host}:{port}/agent.ps1"
    return f"""@echo off
setlocal
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo Requesting administrator privileges...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
echo.
echo Deploying SmartCenter Windows agent...
echo Server: http://{server_host}:{port}
echo Agent version: {AGENT_VERSION}
echo.
set "AGENT_URL={ps_url}?ts=%RANDOM%%RANDOM%"
set "AGENT_TMP=%TEMP%\\smart_center_agent_%RANDOM%%RANDOM%.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{{'Cache-Control'='no-cache';'Pragma'='no-cache'}} -Uri $env:AGENT_URL -OutFile $env:AGENT_TMP"
if not "%errorlevel%"=="0" (
  echo.
  echo Download agent script failed.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%AGENT_TMP%"
set "DEPLOY_EXIT=%errorlevel%"
del /f /q "%AGENT_TMP%" >nul 2>&1
if "%DEPLOY_EXIT%"=="0" (
  exit /b 0
)
echo.
echo Deploy failed. Check network access and execution policy.
pause
exit /b 1
"""

def load_machine_rows():
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT mac,hostname,ip,last_online,data,is_manual,custom_name,sort_order,remark,card_size,asset_group FROM machines ORDER BY sort_order ASC, mac ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def serialize_machine_rows(rows):
    machines = []
    prepared_rows = []
    ping_targets = []
    for row in rows:
        report_online = False
        is_online = False
        offline_window_sec = 180
        agent_status = {}
        status_data = {}
        try:
            status_data = json.loads(row[4]) if row[4] else {}
        except:
            status_data = {}
        status_data = _sanitize_machine_payload(status_data)
        agent_status = status_data.get("agent", {}) if isinstance(status_data, dict) else {}
        try:
            report_interval = int(agent_status.get("report_interval_sec") or 0)
        except Exception:
            report_interval = 0
        if report_interval > 0:
            offline_window_sec = max(180, int(report_interval * 2 + 30))
        server_received_at = status_data.get("server_received_at") if isinstance(status_data, dict) else ""
        online_reference_at = server_received_at or row[3]
        if online_reference_at:
            try: report_online = (datetime.now() - datetime.fromisoformat(str(online_reference_at).replace('Z','+00:00')).replace(tzinfo=None)).total_seconds() < offline_window_sec
            except: pass
        runtime_freshness = _payload_runtime_freshness(status_data, server_received_at or row[3])
        has_runtime_metrics = _payload_has_runtime_metrics(status_data)
        runtime_fresh = bool(runtime_freshness.get("fresh"))
        is_linux_builtin = _payload_is_linux_builtin(status_data)
        is_online = bool(report_online and (runtime_fresh or (is_linux_builtin and has_runtime_metrics)))
        ping_target = _valid_ping_target(row[2])
        if (not report_online or not is_online) and ping_target:
            ping_targets.append(ping_target)
        prepared_rows.append((row, is_online, report_online, runtime_freshness, has_runtime_metrics, status_data, agent_status, server_received_at, ping_target))
    ping_states, ping_meta = _resolve_ping_states_cached(ping_targets)
    for row, is_online, report_online, runtime_freshness, has_runtime_metrics, status_data, agent_status, server_received_at, ping_target in prepared_rows:
        ping_online = None
        ping_state = "not_required"
        ping_age_sec = None
        ping_refreshing = False
        if not report_online or not is_online:
            ping_online = ping_states.get(ping_target) if ping_target else None
            ping_info = ping_meta.get(ping_target, {}) if ping_target else {}
            ping_state = ping_info.get("state") or ("fresh" if ping_online is not None else "pending")
            ping_age_sec = ping_info.get("age_sec")
            ping_refreshing = bool(ping_info.get("refreshing"))
        network_reachable = True if report_online else ping_online
        offline_reason = ""
        if not report_online and ping_online is False:
            offline_reason = "no_report_ping_failed"
        elif not report_online and ping_online is True:
            offline_reason = "no_report_ping_ok"
        elif not report_online and ping_online is None:
            offline_reason = "no_report_ping_pending"
        elif report_online and has_runtime_metrics and not runtime_freshness.get("fresh"):
            offline_reason = "runtime_stale"
        machine = {
            "mac": row[0],
            "hostname": row[1] or "未知主机",
            "ip": row[2],
            "is_online": is_online,
            "report_online": report_online,
            "agent_heartbeat_online": bool(report_online and has_runtime_metrics and not runtime_freshness.get("fresh")),
            "runtime_fresh": bool(runtime_freshness.get("fresh")),
            "runtime_age_sec": runtime_freshness.get("age_sec"),
            "last_report_kind": status_data.get("last_report_kind") if isinstance(status_data, dict) else "",
            "last_full_report_at": status_data.get("last_full_report_at") if isinstance(status_data, dict) else "",
            "last_bootstrap_report_at": status_data.get("last_bootstrap_report_at") if isinstance(status_data, dict) else "",
            "ping_online": ping_online,
            "ping_state": ping_state,
            "ping_age_sec": ping_age_sec,
            "ping_refreshing": ping_refreshing,
            "network_reachable": network_reachable,
            "offline_reason": offline_reason,
            "last_online": row[3],
            "server_received_at": server_received_at or row[3],
            "client_reported_at": status_data.get("client_reported_at") if isinstance(status_data, dict) else "",
            "clock_offset_sec": status_data.get("clock_offset_sec") if isinstance(status_data, dict) else None,
            "status": status_data,
            "agent_status": agent_status,
            "is_manual": bool(row[5]),
            "custom_name": row[6],
            "sort_order": row[7],
            "remark": row[8],
            "card_size": row[9] or 'normal',
            "asset_group": row[10] or ''
        }
        machine["diagnostic"] = _build_machine_diagnostic(machine)
        machines.append(machine)
        try:
            cache_key = str(machine.get("mac") or row[0] or "").strip()
            if cache_key:
                current_online = bool(machine.get("is_online"))
                previous_online = MACHINE_STATE_LOG_CACHE.get(cache_key)
                if previous_online is not None and bool(previous_online) != current_online:
                    name_text = str(machine.get("custom_name") or machine.get("hostname") or machine.get("ip") or cache_key)
                    add_log(-1, f"[状态变化][服务器] {name_text} {'在线' if current_online else '离线'}（状态识别）")
                MACHINE_STATE_LOG_CACHE[cache_key] = current_online
        except Exception:
            pass
    return machines


def invalidate_machines_cache():
    MACHINES_CACHE["expires_at"] = 0.0
    MACHINES_CACHE["payload"] = None


def get_cached_machine_payload(force=False):
    now_ts = time.time()
    if (not force) and MACHINES_CACHE["payload"] is not None and now_ts < float(MACHINES_CACHE["expires_at"] or 0.0):
        return MACHINES_CACHE["payload"]
    payload = serialize_machine_rows(load_machine_rows())
    MACHINES_CACHE["payload"] = payload
    MACHINES_CACHE["expires_at"] = now_ts + MACHINES_CACHE_TTL_SEC
    return payload

def parse_arp_table():
    items = []
    try:
        output = subprocess.check_output(["arp", "-a"], text=True, encoding="gbk", errors="ignore")
        for line in output.splitlines():
            parts = [item for item in line.split() if item]
            if len(parts) >= 3 and "." in parts[0] and "-" in parts[1]:
                normalized_mac = normalize_machine_mac(parts[1])
                if normalized_mac:
                    items.append({"ip": parts[0], "mac": normalized_mac, "type": parts[2]})
    except Exception:
        pass
    return items

def get_scan_networks():
    server_cfg = CONFIG.get("server_monitor", {}) if isinstance(CONFIG, dict) else {}
    raw_networks = server_cfg.get("scan_networks", [])
    networks = []
    if isinstance(raw_networks, str):
        raw_networks = [item.strip() for item in raw_networks.replace(";", ",").split(",") if item.strip()]
    for item in raw_networks if isinstance(raw_networks, list) else []:
        item = str(item).strip()
        if item:
            networks.append(item)
    local_ip = get_local_ip()
    if local_ip and local_ip != "127.0.0.1":
        octets = local_ip.split(".")
        if len(octets) == 4:
            local_network = f"{octets[0]}.{octets[1]}.{octets[2]}.0/24"
            if local_network not in networks:
                networks.insert(0, local_network)
    return networks

def ping_host(ip):
    try:
        result = subprocess.run(
            _ping_command(ip),
            capture_output=True,
            text=True,
            encoding="gbk" if platform.system().lower().startswith("win") else "utf-8",
            errors="ignore"
        )
        return result.returncode == 0
    except Exception:
        return False

def normalize_discovered_item(item, known_machines):
    item_mac = normalize_machine_mac(item.get("mac"))
    known = item_mac in known_machines
    known_info = known_machines.get(item_mac, {})
    return {
        "ip": item["ip"],
        "mac": item_mac,
        "known": known,
        "online": known_info.get("is_online", False),
        "hostname": known_info.get("hostname", ""),
        "asset_group": known_info.get("asset_group", ""),
        "custom_name": known_info.get("custom_name", ""),
        "note": "已接入监控代理" if known else "仅发现网络邻居，尚未部署代理"
    }

def build_discovery_payload(items=None, status=None, error=None):
    payload = dict(DISCOVERY_STATE)
    if items is not None:
        payload["items"] = items
        payload["count"] = len(items)
    if status is not None:
        payload["status"] = status
    if error is not None:
        payload["error"] = error
    payload["server_ip"] = get_local_ip()
    payload["agent_host"] = get_agent_server_host()
    payload["agent_port"] = get_agent_server_port()
    payload["deploy_bat_url"] = f"http://{get_server_host_from_request()}:{get_agent_server_port()}/deploy_agent.bat"
    return payload


def _prune_report_cache(now_ts):
    expired = [
        key
        for key, item in REPORT_CACHE.items()
        if now_ts - float(item.get("ts", 0.0) or 0.0) > 120.0
    ]
    for key in expired:
        REPORT_CACHE.pop(key, None)


def _should_skip_report(mac, payload_text, now_ts):
    digest = hash(payload_text)
    with REPORT_CACHE_LOCK:
        _prune_report_cache(now_ts)
        previous = REPORT_CACHE.get(mac)
        if previous and previous.get("digest") == digest and (now_ts - float(previous.get("ts", 0.0) or 0.0)) < REPORT_MIN_INTERVAL_SEC:
            previous["ts"] = now_ts
            return True
        REPORT_CACHE[mac] = {"digest": digest, "ts": now_ts}
        return False

def prepare_scan_targets():
    targets = []
    warnings = []
    for network_text in get_scan_networks():
        try:
            network = ipaddress.ip_network(network_text, strict=False)
        except ValueError:
            warnings.append(f"扫描网段无效: {network_text}")
            continue
        host_list = []
        for host in network.hosts():
            host_list.append(str(host))
            if len(host_list) >= MAX_HOSTS_PER_NETWORK:
                warnings.append(f"{network_text} 地址数量过多，已限制前 {MAX_HOSTS_PER_NETWORK} 个地址")
                break
        targets.extend(host_list)
        if len(targets) >= MAX_TOTAL_SCAN_HOSTS:
            targets = targets[:MAX_TOTAL_SCAN_HOSTS]
            warnings.append(f"总扫描地址数量已限制为 {MAX_TOTAL_SCAN_HOSTS} 个")
            break
    return targets, warnings

def scan_host_worker(ip):
    alive = ping_host(ip)
    with DISCOVERY_LOCK:
        if alive:
            DISCOVERY_STATE["alive_count"] += 1
        DISCOVERY_STATE["scanned_hosts"] += 1
        total_hosts = DISCOVERY_STATE["total_hosts"] or 0
        DISCOVERY_STATE["progress"] = int((DISCOVERY_STATE["scanned_hosts"] / total_hosts) * 100) if total_hosts else 100

def scan_targets_in_parallel(targets, workers):
    worker_count = max(1, min(int(workers or 1), 32))
    threads = []
    for ip in targets:
        with DISCOVERY_LOCK:
            if DISCOVERY_STATE.get("stopped"):
                break
        thread = threading.Thread(target=scan_host_worker, args=(ip,), daemon=True)
        threads.append(thread)
        thread.start()
        while True:
            active_threads = [t for t in threads if t.is_alive()]
            threads = active_threads
            if len(active_threads) < worker_count:
                break
            time.sleep(0.03)
    for thread in threads:
        thread.join()

def run_discovery_scan():
    try:
        with DISCOVERY_LOCK:
            DISCOVERY_STATE.update({
                "status": "running",
                "progress": 0,
                "scanned_hosts": 0,
                "total_hosts": 0,
                "alive_count": 0,
                "items": [],
                "count": 0,
                "error": "",
                "started_at": datetime.now().isoformat(),
                "finished_at": "",
                "scan_networks": get_scan_networks(),
                "warnings": DISCOVERY_STATE.get("warnings", []),
                "stopped": False
            })

        targets, warnings = prepare_scan_targets()
        with DISCOVERY_LOCK:
            DISCOVERY_STATE["total_hosts"] = len(targets)
            DISCOVERY_STATE["warnings"] = warnings
            worker_count = DISCOVERY_STATE.get("workers", 8)

        scan_targets_in_parallel(targets, worker_count)

        known_machines = {item["mac"]: item for item in serialize_machine_rows(load_machine_rows())}
        discovered = []
        for item in parse_arp_table():
            discovered.append(normalize_discovered_item(item, known_machines))

        with DISCOVERY_LOCK:
            DISCOVERY_STATE["status"] = "stopped" if DISCOVERY_STATE.get("stopped") else "completed"
            DISCOVERY_STATE["progress"] = 100
            DISCOVERY_STATE["items"] = discovered
            DISCOVERY_STATE["count"] = len(discovered)
            DISCOVERY_STATE["finished_at"] = datetime.now().isoformat()
    except Exception as exc:
        with DISCOVERY_LOCK:
            DISCOVERY_STATE["status"] = "error"
            DISCOVERY_STATE["error"] = str(exc)
            DISCOVERY_STATE["finished_at"] = datetime.now().isoformat()

@bp.route('/agent.ps1')
def get_agent_script():
    response = Response(build_agent_bootstrap_script(get_server_host_from_request()), mimetype="text/plain; charset=utf-8")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

@bp.route('/agent/worker.ps1')
def get_agent_worker_script():
    response = Response(build_agent_worker_script(get_server_host_from_request()), mimetype="text/plain; charset=utf-8")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Smart-Center-Agent-Version"] = AGENT_VERSION
    return response

@bp.route('/agent/worker.json')
def get_agent_worker_json():
    worker_text = build_agent_worker_script(get_server_host_from_request())
    response = jsonify({
        "service": "smart_center_agent",
        "version": AGENT_VERSION,
        "worker_b64": base64.b64encode(worker_text.encode("utf-8")).decode("ascii"),
        "updated_at": datetime.now().isoformat(),
    })
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Smart-Center-Agent-Version"] = AGENT_VERSION
    return response

@bp.route('/agent/linux.py')
def get_linux_agent_script():
    template_path = Path(__file__).resolve().parent.parent / "agent" / "linux_agent.py"
    try:
        script_text = template_path.read_text(encoding="utf-8")
    except Exception as exc:
        return Response(f"# linux agent template unavailable: {exc}\n", status=503, mimetype="text/plain; charset=utf-8")
    script_text = (
        script_text
        .replace("__AGENT_VERSION__", AGENT_VERSION)
        .replace("__SERVER_HOST__", get_server_host_from_request())
        .replace("__SERVER_PORT__", str(get_agent_server_port()))
    )
    response = Response(script_text, mimetype="text/plain; charset=utf-8")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Smart-Center-Agent-Version"] = AGENT_VERSION
    return response

@bp.route('/agent/launcher.json')
def get_agent_launcher_json():
    launcher_text = build_agent_launcher_script()
    response = jsonify({
        "service": "smart_center_agent",
        "version": AGENT_VERSION,
        "launcher_b64": base64.b64encode(launcher_text.encode("utf-8")).decode("ascii"),
        "updated_at": datetime.now().isoformat(),
    })
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Smart-Center-Agent-Version"] = AGENT_VERSION
    return response

@bp.route('/deploy_agent.bat')
def get_agent_bat():
    response = Response(build_deploy_bat(get_server_host_from_request()), mimetype="application/octet-stream")
    response.headers["Content-Disposition"] = 'attachment; filename="deploy_agent.bat"'
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

@bp.route('/agent/config')
def get_agent_config():
    request_host = request.headers.get("host", "").split(":")[0]
    config_payload = build_agent_runtime_config(get_server_host_from_request())
    if request.args.get("probe") == "1":
        return jsonify(config_payload)
    return jsonify({"status": "ok", "agent_config": config_payload, "request_host": request_host})

@bp.route('/report', methods=['POST'])
def report_data():
    content_length = int(request.content_length or 0)
    if content_length and content_length > REPORT_MAX_BYTES:
        add_log(-1, f"[服务器] 忽略过大Agent上报 remote={request.remote_addr} bytes={content_length} limit={REPORT_MAX_BYTES}")
        return jsonify({
            "status": "ignored",
            "reason": "payload_too_large",
            "command": None,
            "agent_config": build_agent_runtime_config(get_server_host_from_request())
        }), 202

    data, parse_error = _load_report_json_payload()
    if isinstance(data, list):
        data = next((item for item in data if isinstance(item, dict) and (isinstance(item.get("status"), dict) or _payload_has_runtime_metrics(item))), {})
    if not isinstance(data, dict):
        data = {}
    status_payload = data.get("status") if isinstance(data.get("status"), dict) else {}
    if not status_payload and _payload_has_runtime_metrics(data):
        status_payload = dict(data)
        for envelope_key in ("mac", "hostname", "ip", "timestamp", "wake_proxy_result"):
            status_payload.pop(envelope_key, None)
    agent_payload = status_payload.get("agent") if isinstance(status_payload.get("agent"), dict) else {}
    mac = normalize_machine_mac(
        data.get("mac")
        or status_payload.get("mac")
        or agent_payload.get("machine_mac")
        or agent_payload.get("mac")
    )
    report_ip = str(
        data.get("ip")
        or status_payload.get("ip")
        or agent_payload.get("machine_ip")
        or agent_payload.get("ip")
        or ""
    ).strip()
    hostname = str(
        data.get("hostname")
        or status_payload.get("hostname")
        or agent_payload.get("hostname")
        or "未知主机"
    )
    if not mac:
        mac = _get_machine_mac_by_ip(report_ip)
    if not mac:
        mac = _get_recent_machine_mac_by_remote_addr(request.remote_addr)
    if not mac:
        mac = _get_machine_mac_by_hostname_or_name(hostname)
    if not mac:
        mac = _get_machine_mac_by_legacy_report(report_ip, request.remote_addr, hostname, data.get("mac") or status_payload.get("mac") or "")
    if not mac:
        add_log(
            -1,
            f"[服务器] Agent上报解析失败 remote={request.remote_addr} bytes={content_length} parse_error={parse_error or '-'}"
        )
        return jsonify({
            "status": "ignored",
            "reason": "unparseable_report",
            "command": None,
            "agent_config": build_agent_runtime_config(get_server_host_from_request())
        }), 202
    if parse_error and not data:
        add_log(
            -1,
            f"[服务器] Agent空上报已忽略 remote={request.remote_addr} mac={mac or '-'} bytes={content_length} parse_error={parse_error}"
        )
        return jsonify({
            "status": "ignored",
            "reason": "empty_report",
            "command": None,
            "agent_config": build_agent_runtime_config(get_server_host_from_request())
        }), 202
    if not mac:
        add_log(-1, f"[服务器] 拒绝无MAC上报 remote={request.remote_addr} ip={report_ip or '-'} host={hostname or '-'} keys={','.join(sorted(data.keys()))} status_keys={','.join(sorted(status_payload.keys()))}")
        return jsonify({
            "status": "error",
            "error": "missing mac",
            "message": "report missing mac and no known row matched by ip/remote_addr",
            "remote_addr": request.remote_addr,
            "report_ip": report_ip,
            "agent_config": build_agent_runtime_config(get_server_host_from_request())
        }), 400

    if isinstance(data.get("wake_proxy_result"), dict):
        _record_machine_wake_proxy_result(mac, data.get("wake_proxy_result"))

    if _is_test_machine_report(mac, hostname, report_ip or request.remote_addr, status_payload):
        add_log(
            -1,
            f"[服务器] 忽略测试Agent上报 remote={request.remote_addr} ip={report_ip or '-'} mac={mac or '-'} host={hostname or '-'}"
        )
        return jsonify({
            "status": "ignored",
            "reason": "test_machine_report",
            "command": None,
            "agent_config": build_agent_runtime_config(get_server_host_from_request())
        }), 202

    client_reported_at = str(data.get("timestamp") or status_payload.get("report_generated_at") or "")
    server_received_at = datetime.now().isoformat()
    status_payload = _annotate_report_timing(status_payload, client_reported_at, server_received_at)
    if _payload_has_runtime_metrics(status_payload):
        _mark_payload_as_full_report(status_payload, server_received_at, prefer_server=True)
    else:
        status_payload["last_report_kind"] = _classify_machine_report(status_payload, data)
    timestamp = server_received_at
    ip = str(report_ip or request.remote_addr or "")
    _store_machine_status(mac, hostname, ip, timestamp, status_payload)
    agent_version = ""
    try:
        agent_version = str((status_payload.get("agent") or {}).get("version") or "")
    except Exception:
        agent_version = ""
    return jsonify({
        "status": "ok",
        "command": _pop_machine_command(mac, agent_version),
        "agent_config": build_agent_runtime_config(get_server_host_from_request())
    })

@bp.route('/api/machines/sort', methods=['POST'])
@require_permission("server.control")
def sort_machines():
    mac_list = request.json.get("macs", [])
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    for idx, mac in enumerate(mac_list): c.execute("UPDATE machines SET sort_order=? WHERE mac=?", (idx, mac))
    conn.commit(); conn.close()
    invalidate_machines_cache()
    log_audit_event("server.sort", target="machines", detail={"count": len(mac_list), "macs": mac_list})
    return jsonify({"status": "ok"})

@bp.route('/api/machines/batch_save', methods=['POST'])
@require_permission("system.config")
def batch_save_machines():
    machines = request.json
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    existing_macs = [normalize_machine_mac(m.get('mac')) for m in machines if normalize_machine_mac(m.get('mac'))]
    if existing_macs: c.execute(f"DELETE FROM machines WHERE mac NOT IN ({','.join('?'*len(existing_macs))})", existing_macs)
    else: c.execute("DELETE FROM machines")
    for m in machines:
        normalized_mac = normalize_machine_mac(m.get('mac'))
        if not normalized_mac:
            continue
        c.execute('''INSERT INTO machines (mac,hostname,ip,is_manual,custom_name,sort_order,remark,card_size,asset_group) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(mac) DO UPDATE SET
            hostname=CASE WHEN machines.hostname IS NULL OR machines.hostname='' THEN excluded.hostname ELSE machines.hostname END,
            ip=excluded.ip,
            custom_name=CASE WHEN excluded.custom_name IS NULL OR excluded.custom_name='' THEN machines.custom_name ELSE excluded.custom_name END,
            sort_order=excluded.sort_order,
            remark=CASE WHEN excluded.remark IS NULL OR excluded.remark='' THEN machines.remark ELSE excluded.remark END,
            card_size=excluded.card_size,asset_group=excluded.asset_group''',
            (normalized_mac,m.get('hostname',''),m.get('ip',''),m.get('is_manual',1),m.get('custom_name',''),m.get('sort_order',999),m.get('remark',''),m.get('card_size','normal'),m.get('asset_group','')))
    conn.commit(); conn.close()
    invalidate_machines_cache()
    add_log(-1, "[服务器] 节点配置已更新")
    log_audit_event("server.config.save", target="machines", detail={"count": len(machines) if isinstance(machines, list) else 0})
    return jsonify(ok=1)

@bp.route('/api/machines')
@require_permission("server.view")
def get_machines():
    return jsonify(get_cached_machine_payload())

@bp.route('/api/machines/discover/start', methods=['POST'])
@require_permission("server.control")
def start_discover_machines():
    req = request.json or {}
    workers = req.get("workers", 8)
    with DISCOVERY_LOCK:
        if DISCOVERY_STATE["status"] == "running":
            return jsonify(build_discovery_payload(status="running"))
        DISCOVERY_STATE.update({
            "status": "queued",
            "progress": 0,
            "scanned_hosts": 0,
            "total_hosts": 0,
            "alive_count": 0,
            "items": [],
            "count": 0,
            "error": "",
            "started_at": datetime.now().isoformat(),
            "finished_at": "",
            "scan_networks": get_scan_networks(),
            "warnings": [],
            "workers": max(1, min(int(workers or 8), 32)),
            "stopped": False
        })
    threading.Thread(target=run_discovery_scan, daemon=True).start()
    log_audit_event("server.discovery.start", target="lan_scan", detail={"workers": DISCOVERY_STATE.get("workers", 8)})
    return jsonify(build_discovery_payload(status="queued"))

@bp.route('/api/machines/discover/stop', methods=['POST'])
@require_permission("server.control")
def stop_discover_machines():
    with DISCOVERY_LOCK:
        DISCOVERY_STATE["stopped"] = True
        if DISCOVERY_STATE["status"] == "running":
            DISCOVERY_STATE["status"] = "stopping"
    log_audit_event("server.discovery.stop", target="lan_scan")
    return jsonify(build_discovery_payload())

@bp.route('/api/machines/discover/import', methods=['POST'])
@require_permission("system.config")
def import_discovered_machines():
    data = request.json or {}
    items = data.get("items", [])
    asset_group = str(data.get("asset_group", "") or "").strip()
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    imported = 0
    for item in items:
        mac = normalize_machine_mac(item.get("mac"))
        ip = str(item.get("ip", "") or "").strip()
        if not mac or not ip:
            continue
        hostname = str(item.get("hostname", "") or "").strip()
        custom_name = str(item.get("custom_name", "") or "").strip()
        c.execute("SELECT last_online,data,sort_order,remark,card_size,asset_group FROM machines WHERE mac=?", (mac,))
        row = c.fetchone()
        c.execute('''INSERT INTO machines (mac,hostname,ip,last_online,data,is_manual,custom_name,sort_order,remark,card_size,asset_group)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(mac) DO UPDATE SET hostname=excluded.hostname,ip=excluded.ip,is_manual=excluded.is_manual,
            custom_name=CASE WHEN machines.custom_name IS NULL OR machines.custom_name='' THEN excluded.custom_name ELSE machines.custom_name END,
            asset_group=CASE WHEN excluded.asset_group<>'' THEN excluded.asset_group ELSE machines.asset_group END''',
            (
                mac,
                hostname,
                ip,
                row[0] if row else None,
                row[1] if row else None,
                1,
                custom_name or hostname,
                row[2] if row else 999,
                row[3] if row else '',
                row[4] if row else 'normal',
                asset_group or (row[5] if row else '')
            ))
        imported += 1
    conn.commit(); conn.close()
    invalidate_machines_cache()
    add_log(-1, f"[服务器] 已从扫描结果导入 {imported} 台机器，目标分组: [{asset_group or '未分组'}]")
    log_audit_event("server.discovery.import", target=asset_group or "ungrouped", detail={"imported": imported, "asset_group": asset_group or ""})
    return jsonify({"status": "ok", "imported": imported})

@bp.route('/api/machines/discover')
@require_permission("server.view")
def discover_machines():
    with DISCOVERY_LOCK:
        return jsonify(build_discovery_payload())

@bp.route('/api/wake/<mac>', methods=['POST'])
@require_permission("server.control")
def wake_machine(mac):
    try:
        normalized_mac = normalize_machine_mac(mac)
        wake_mac = normalized_mac.replace("-", "") if "-" in normalized_mac else normalized_mac
        if not wake_mac or normalized_mac.startswith(("LOCAL-", "TEMP-")):
            return jsonify({"error": "invalid mac"}), 400
        target_ip = _get_machine_ip_for_wol(normalized_mac)
        targets = _wol_broadcast_targets(target_ip)
        from wakeonlan import send_magic_packet
        sent_targets = []
        errors = []
        for target in targets:
            for port in (9, 7):
                try:
                    for _ in range(3):
                        send_magic_packet(wake_mac, ip_address=target, port=port)
                        time.sleep(0.08)
                    sent_targets.append({"target": target, "port": port, "attempts": 3})
                except Exception as exc:
                    errors.append({"target": target, "port": port, "error": str(exc)})
        relays = []
        for relay in _find_wol_relay_candidates(normalized_mac, target_ip):
            _set_machine_command(relay["mac"], {
                "action": "wake_proxy",
                "mac": normalized_mac,
                "ip": target_ip,
                "requested_at": datetime.now().isoformat(),
                "min_agent_version": "2026.05.03.03",
            })
            relays.append(relay)
        detail = {"mac": normalized_mac, "ip": target_ip, "targets": sent_targets, "errors": errors, "relays": relays}
        if not sent_targets:
            raise RuntimeError("; ".join(item["error"] for item in errors) or "no wol target sent")
        relay_text = ",".join(f"{relay.get('name')}({relay.get('ip')})" for relay in relays) or "无"
        target_text = ",".join(f"{item.get('target')}:{item.get('port')}x{item.get('attempts')}" for item in sent_targets)
        add_log(-1, f"[服务器] WOL唤醒包已发出: {normalized_mac} IP={target_ip or '未知'} 广播={target_text} 中继={relay_text}")
        log_audit_event("server.wake", target=normalized_mac, detail=detail, status="ok" if not errors else "partial")
        return jsonify({"status": "ok", "mac": normalized_mac, "ip": target_ip, "targets": sent_targets, "errors": errors, "relays": relays})
    except Exception as e:
        normalized_mac = normalize_machine_mac(mac)
        log_audit_event("server.wake", target=normalized_mac or mac, detail={"mac": normalized_mac or mac, "error": str(e)}, status="error")
        return jsonify({"error": str(e)}), 500

@bp.route('/api/machines/<mac>/command', methods=['POST'])
@require_permission("server.control")
def send_machine_cmd(mac):
    normalized_mac = normalize_machine_mac(mac)
    cmd = request.json.get("command"); _set_machine_command(normalized_mac, cmd)
    action_name = {"shutdown": "关机", "restart": "重启", "refresh": "刷新信息"}.get(cmd, cmd)
    add_log(-1, f"[服务器] 已向节点 {normalized_mac or mac} 下发指令: [{action_name}]")
    log_audit_event("server.command.execute", target=normalized_mac or mac, detail={"mac": normalized_mac or mac, "command": cmd, "action_name": action_name})
    return jsonify({"status": "ok"})
