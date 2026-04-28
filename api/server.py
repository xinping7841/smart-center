import sqlite3, json, socket, time, subprocess, ipaddress, threading
from datetime import datetime, timedelta
from pathlib import Path
import os
import platform
import shutil
import hashlib
import re
from flask import Blueprint, jsonify, request, Response
from audit import log_audit_event
from auth.decorators import require_permission
from config import CONFIG, SERVER_COMMANDS
from data_logger import add_log
from paths import DB_FILE as DB_FILE_PATH, ensure_parent_dir

bp = Blueprint('server', __name__)
DB_FILE = str(DB_FILE_PATH)
AGENT_VERSION = "2026.04.28.12"
REPORT_MAX_BYTES = 512 * 1024
REPORT_MIN_INTERVAL_SEC = 2.0
REPORT_CACHE = {}
REPORT_CACHE_LOCK = threading.Lock()
MACHINES_CACHE = {"expires_at": 0.0, "payload": None}
MACHINES_CACHE_TTL_SEC = 2.5
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


def _parse_machine_timestamp(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _parse_machine_payload(payload_text):
    try:
        return json.loads(payload_text) if payload_text else {}
    except Exception:
        return {}


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


def _sanitize_gpu_list(gpu_list):
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
        identity = _normalize_gpu_identity(name) or f"gpu-{idx}"
        score = _gpu_row_score(item)
        previous = best_by_key.get(identity)
        if not previous:
            best_by_key[identity] = {"item": item, "score": score, "order": idx}
            order.append(identity)
            continue
        if score > previous["score"]:
            best_by_key[identity] = {"item": item, "score": score, "order": previous["order"]}
    return [best_by_key[key]["item"] for key in order if key in best_by_key]


def _sanitize_machine_payload(payload):
    payload = payload if isinstance(payload, dict) else {}
    if "gpu_list" not in payload:
        return payload
    cleaned = dict(payload)
    cleaned["gpu_list"] = _sanitize_gpu_list(payload.get("gpu_list"))
    return cleaned


def _machine_command_keys(mac):
    keys = []
    raw_key = str(mac or "").strip().upper()
    normalized_key = normalize_machine_mac(raw_key)
    for item in (normalized_key, raw_key):
        if item and item not in keys:
            keys.append(item)
    return keys


def _pop_machine_command(mac):
    for key in _machine_command_keys(mac):
        if key in SERVER_COMMANDS:
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
        "worker_path": "/agent/worker.ps1",
        "report_interval_sec": 60,
        "sync_interval_sec": 60,
        "discovery_retry_sec": 120,
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
    recv_total = 0
    sent_total = 0
    for line in _read_text_file("/proc/net/dev").splitlines()[2:]:
        if ":" not in line:
            continue
        name, values = line.split(":", 1)
        iface = name.strip()
        if iface == "lo":
            continue
        parts = [item for item in values.strip().split() if item]
        if len(parts) < 16:
            continue
        try:
            recv_total += int(parts[0])
            sent_total += int(parts[8])
        except Exception:
            continue
    now_ts = time.time()
    with LOCAL_MACHINE_STATE_LOCK:
        prev_sent = LOCAL_MACHINE_NET_SAMPLE["sent"]
        prev_recv = LOCAL_MACHINE_NET_SAMPLE["recv"]
        prev_ts = LOCAL_MACHINE_NET_SAMPLE["ts"]
        LOCAL_MACHINE_NET_SAMPLE.update({"sent": sent_total, "recv": recv_total, "ts": now_ts})
    if prev_sent is None or prev_recv is None or prev_ts is None:
        return {"sent_kb_s": 0.0, "recv_kb_s": 0.0}
    delta_ts = max(0.001, now_ts - float(prev_ts))
    sent_kb_s = max(0.0, (sent_total - int(prev_sent)) / 1024.0 / delta_ts)
    recv_kb_s = max(0.0, (recv_total - int(prev_recv)) / 1024.0 / delta_ts)
    return {"sent_kb_s": round(sent_kb_s, 1), "recv_kb_s": round(recv_kb_s, 1)}


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
    payload = {
        "cpu_name": cpu_name or platform.processor() or platform.machine() or "Linux Host",
        "motherboard": motherboard,
        "mem_speed": _read_linux_memory_speed(),
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


def _build_local_machine_status():
    hardware = _read_linux_hardware_profile()
    meminfo = _read_linux_meminfo()
    disk_usage = shutil.disk_usage("/")
    net_rates = _read_linux_net_rates()
    now_iso = datetime.now().isoformat()
    return {
        "cpu_name": hardware.get("cpu_name"),
        "motherboard": hardware.get("motherboard"),
        "mem_speed": hardware.get("mem_speed"),
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
        "hardware_refreshed_at": now_iso,
        "host_type": "linux_builtin",
        "agent": {
            "version": AGENT_VERSION,
            "task_exists": True,
            "task_state": "systemd 内置采集",
            "task_user": os.environ.get("USER") or "root",
            "current_server_url": f"http://{get_agent_server_host()}:{get_agent_server_port()}",
            "service": "smart-center.service",
            "report_interval_sec": LOCAL_MONITOR_INTERVAL_SEC,
            "updated_at": now_iso,
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
    has_runtime_metrics = _payload_has_runtime_metrics(status_payload)
    bootstrap = bool(agent.get("bootstrap"))
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
        "bootstrap_only": bootstrap and not has_runtime_metrics,
        "log_excerpt": log_tail,
    }

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

    if not is_online:
        diagnostic.update(
            {
                "level": "warn",
                "code": "offline",
                "summary": "节点当前离线",
                "detail": "节点最近没有按预期继续上报，可能是机器关机、网络中断或 agent 未正常拉起。",
                "root_cause": _detect_bootstrap_root_cause(log_tail).get("root_cause", "") if log_tail else "",
                "suggestion": "先检查机器是否开机、网络是否可达；如仍不恢复，可重新运行 deploy_agent.bat 或执行网络唤醒后再观察。",
                "needs_attention": True,
                "needs_redeploy": bool(log_tail),
            }
        )
        return diagnostic

    if is_online and not has_runtime_metrics:
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
    if not existing_payload:
        return incoming_payload
    existing_payload = _sanitize_machine_payload(existing_payload)
    if _payload_has_runtime_metrics(incoming_payload):
        return incoming_payload
    if not _payload_has_runtime_metrics(existing_payload):
        return incoming_payload
    merged = dict(existing_payload)
    incoming_agent = incoming_payload.get("agent")
    if isinstance(incoming_agent, dict):
        merged_agent = dict(existing_payload.get("agent") or {}) if isinstance(existing_payload.get("agent"), dict) else {}
        merged_agent.update(incoming_agent)
        merged["agent"] = merged_agent
    for key, value in incoming_payload.items():
        if key == "agent":
            continue
        if value not in (None, "", [], {}):
            merged[key] = value
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


def local_server_monitor_loop():
    if platform.system().lower() != "linux":
        return
    local_mac = get_local_machine_mac()
    while True:
        try:
            configured_ip = str(CONFIG.get("server_monitor", {}).get("agent_host", "") or "").strip()
            _handle_local_machine_command(local_mac)
            _store_machine_status(
                local_mac,
                socket.gethostname() or "zhongkong",
                configured_ip or get_local_ip(),
                datetime.now().isoformat(),
                _build_local_machine_status(),
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
$WorkerPath = if ($PSCommandPath) {{ $PSCommandPath }} else {{ Join-Path $AgentDir 'agent_worker.ps1' }}
$lastNetBytesSent = $null
$lastNetBytesRecv = $null
$lastNetSampleTime = $null
$script:HardwareCache = $null
$script:LastTaskInfoAt = $null
$script:TaskInfoCache = $null
$script:ConsecutiveFailures = 0
$script:LastSuccessfulReportAt = $null
$script:GpuProbeDiagnostic = @{{}}
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
    if ($compact.Length -lt 12) {{
        return $text.ToUpper()
    }}
    return ([regex]::Replace($compact.Substring(0, 12), '([0-9A-F]{2})(?=.)', '$1-'))
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
    if (-not $cfg.ContainsKey('report_interval_sec') -or -not $cfg['report_interval_sec']) {{ $cfg['report_interval_sec'] = 60 }}
    if (-not $cfg.ContainsKey('sync_interval_sec') -or -not $cfg['sync_interval_sec']) {{ $cfg['sync_interval_sec'] = 60 }}
    if (-not $cfg.ContainsKey('discovery_retry_sec') -or -not $cfg['discovery_retry_sec']) {{ $cfg['discovery_retry_sec'] = 120 }}
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
    Write-TextFile $ConfigPath ($cfg | ConvertTo-Json -Depth 8)
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
                report_interval_sec = Get-ConfigIntValue $storedJson.report_interval_sec 0
                sync_interval_sec = Get-ConfigIntValue $storedJson.sync_interval_sec 0
                discovery_retry_sec = Get-ConfigIntValue $storedJson.discovery_retry_sec 0
                current_server_url = Get-ConfigTextValue $storedJson.current_server_url ''
                config_updated_at = Get-ConfigTextValue $storedJson.config_updated_at ''
                last_config_sync_at = Get-ConfigTextValue $storedJson.last_config_sync_at ''
                last_discovery_at = Get-ConfigTextValue $storedJson.last_discovery_at ''
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
    if (-not $incoming -or -not $incoming.ContainsKey('version')) {{ return $false }}
    $remoteVersion = [string]$incoming['version']
    if (-not $remoteVersion -or (Compare-VersionText $remoteVersion $AgentVersion) -le 0) {{ return $false }}
    $workerPathValue = if ($incoming.ContainsKey('worker_path') -and $incoming['worker_path']) {{ [string]$incoming['worker_path'] }} else {{ '/agent/worker.ps1' }}
    $baseUrl = if ($cfg['current_server_url']) {{ [string]$cfg['current_server_url'] }} else {{ 'http://' + $cfg['server_host'] + ':' + $cfg['server_port'] }}
    if (-not $baseUrl) {{ return $false }}
    $workerUrl = $baseUrl.TrimEnd('/') + $workerPathValue + '?v=' + [uri]::EscapeDataString($remoteVersion) + '&ts=' + [uri]::EscapeDataString((Get-Date).Ticks)
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
        $backupPath = $WorkerPath + '.bak_' + (Get-Date).ToString('yyyyMMddHHmmss')
        if (Test-Path $WorkerPath) {{
            Copy-Item -LiteralPath $WorkerPath -Destination $backupPath -Force -ErrorAction SilentlyContinue
        }}
        Write-TextFile $WorkerPath $workerText
        Write-AgentLog ('self-updated worker ' + $AgentVersion + ' -> ' + $remoteVersion + '; restart on next scheduled run')
        return $true
    }} catch {{
        Write-AgentLog ('self-update failed: ' + (Get-ErrorDetails $_))
        return $false
    }}
}}

function Merge-AgentConfig([hashtable]$cfg, [hashtable]$incoming) {{
    if (-not $incoming) {{ return $cfg }}
    foreach ($key in @('service','version','server_host','server_port','report_path','config_path','worker_path','report_interval_sec','sync_interval_sec','discovery_retry_sec')) {{
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
            $_.IPEnabled -eq $true -and $_.MACAddress
        }}
        $adapter = $adapters | Select-Object -First 1
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
    return 'TEMP-' + [guid]::NewGuid().ToString().Substring(0, 12).ToUpper()
}}

function Get-PrimaryIPv4 {{
    try {{
        $adapters = @(Get-AgentInstances 'Win32_NetworkAdapterConfiguration') | Where-Object {{
            $_.IPEnabled -eq $true -and $_.IPAddress
        }}
        foreach ($adapter in $adapters) {{
            $ipv4 = $adapter.IPAddress | Where-Object {{ $_ -match '^\\d+\\.\\d+\\.\\d+\\.\\d+$' -and $_ -notlike '169.254.*' }} | Select-Object -First 1
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
    return ''
}}

function Get-NetSpeed {{
    $counters = @(Get-AgentInstances 'Win32_PerfRawData_Tcpip_NetworkInterface')
    $totalSent = 0
    $totalRecv = 0
    foreach ($counter in $counters) {{
        $totalSent += [double]$counter.BytesSentPersec
        $totalRecv += [double]$counter.BytesReceivedPersec
    }}
    $now = Get-Date
    $sendKb = 0
    $recvKb = 0
    if ($lastNetSampleTime) {{
        $seconds = ($now - $lastNetSampleTime).TotalSeconds
        if ($seconds -gt 0) {{
            $sendKb = [math]::Round((($totalSent - $lastNetBytesSent) / $seconds) / 1KB, 1)
            $recvKb = [math]::Round((($totalRecv - $lastNetBytesRecv) / $seconds) / 1KB, 1)
        }}
    }}
    $script:lastNetBytesSent = $totalSent
    $script:lastNetBytesRecv = $totalRecv
    $script:lastNetSampleTime = $now
    return @($sendKb, $recvKb)
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
        $lines = @(& $smiPath --query-gpu=index,name,utilization.gpu,temperature.gpu --format=csv,noheader,nounits 2>$null)
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
    if (-not (Get-CommandOrNull 'Add-Type')) {{
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

    public class GpuPerfResult {{
        public string DeviceName;
        public string Name;
        public string Luid;
        public int Temperature;
        public int FanRPM;
        public int Power;
    }}

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern bool EnumDisplayDevices(string lpDevice, uint iDevNum, ref DISPLAY_DEVICE lpDisplayDevice, uint dwFlags);

    [DllImport("gdi32.dll", EntryPoint = "D3DKMTOpenAdapterFromGdiDisplayName")]
    public static extern int D3DKMTOpenAdapterFromGdiDisplayName(ref D3DKMT_OPENADAPTERFROMGDIDISPLAYNAME data);

    [DllImport("gdi32.dll", EntryPoint = "D3DKMTQueryAdapterInfo")]
    public static extern int D3DKMTQueryAdapterInfo(ref D3DKMT_QUERYADAPTERINFO data);

    [DllImport("gdi32.dll", EntryPoint = "D3DKMTCloseAdapter")]
    public static extern int D3DKMTCloseAdapter(ref D3DKMT_CLOSEADAPTER data);

    public static GpuPerfResult[] Read() {{
        List<GpuPerfResult> results = new List<GpuPerfResult>();
        HashSet<string> seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        for (uint i = 0; i < 32; i++) {{
            DISPLAY_DEVICE dd = new DISPLAY_DEVICE();
            dd.cb = Marshal.SizeOf(typeof(DISPLAY_DEVICE));
            if (!EnumDisplayDevices(null, i, ref dd, 0)) {{
                break;
            }}
            if (String.IsNullOrWhiteSpace(dd.DeviceName)) {{
                continue;
            }}
            D3DKMT_OPENADAPTERFROMGDIDISPLAYNAME open = new D3DKMT_OPENADAPTERFROMGDIDISPLAYNAME();
            open.DeviceName = dd.DeviceName;
            int openStatus = D3DKMTOpenAdapterFromGdiDisplayName(ref open);
            if (openStatus != 0 || open.hAdapter == 0) {{
                continue;
            }}
            try {{
                D3DKMT_ADAPTER_PERFDATA perf = new D3DKMT_ADAPTER_PERFDATA();
                int size = Marshal.SizeOf(typeof(D3DKMT_ADAPTER_PERFDATA));
                IntPtr ptr = Marshal.AllocHGlobal(size);
                try {{
                    Marshal.StructureToPtr(perf, ptr, false);
                    D3DKMT_QUERYADAPTERINFO query = new D3DKMT_QUERYADAPTERINFO();
                    query.hAdapter = open.hAdapter;
                    query.Type = 49;
                    query.pPrivateDriverData = ptr;
                    query.PrivateDriverDataSize = (uint)size;
                    int status = D3DKMTQueryAdapterInfo(ref query);
                    if (status == 0) {{
                        perf = (D3DKMT_ADAPTER_PERFDATA)Marshal.PtrToStructure(ptr, typeof(D3DKMT_ADAPTER_PERFDATA));
                        string luid = open.AdapterLuid.HighPart.ToString("X8") + ":" + open.AdapterLuid.LowPart.ToString("X8");
                        if (!seen.Contains(luid)) {{
                            seen.Add(luid);
                            double tempC = perf.Temperature / 10.0;
                            int temp = (tempC > 0 && tempC < 150) ? (int)Math.Round(tempC) : 0;
                            results.Add(new GpuPerfResult {{
                                DeviceName = dd.DeviceName,
                                Name = dd.DeviceString,
                                Luid = luid,
                                Temperature = temp,
                                FanRPM = (int)perf.FanRPM,
                                Power = (int)perf.Power
                            }});
                        }}
                    }}
                }} finally {{
                    Marshal.FreeHGlobal(ptr);
                }}
            }} finally {{
                D3DKMT_CLOSEADAPTER close = new D3DKMT_CLOSEADAPTER();
                close.hAdapter = open.hAdapter;
                D3DKMTCloseAdapter(ref close);
            }}
        }}
        return results.ToArray();
    }}
}}
'@
            Add-Type -TypeDefinition $source -Language CSharp -ErrorAction Stop | Out-Null
        }}
        $items = @([SmartCenterGpuPerfReader]::Read())
    }} catch {{
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
    foreach ($perf in $perfItems) {{
        $temp = 0
        try {{ $temp = [int]$perf.Temperature }} catch {{ $temp = 0 }}
        if ($temp -le 0) {{
            continue
        }}
        $perfIdentity = Normalize-GpuIdentity ([string]$perf.Name)
        $updated = $false
        for ($i = 0; $i -lt $gpuList.Count; $i++) {{
            $row = $gpuList[$i]
            $rowTemp = 0
            try {{ $rowTemp = [int]$row.temp }} catch {{ $rowTemp = 0 }}
            $rowIdentity = Normalize-GpuIdentity ([string]$row.name)
            $nameMatches = $perfIdentity -and $rowIdentity -and ($perfIdentity -eq $rowIdentity -or $perfIdentity.Contains($rowIdentity) -or $rowIdentity.Contains($perfIdentity))
            $amdFallback = ([string]$row.name -match '(?i)amd|radeon') -and ([string]$perf.Name -match '(?i)amd|radeon')
            if (($nameMatches -or $amdFallback) -and $rowTemp -le 0) {{
                $row.temp = $temp
                $row.source = 'dxgk'
                if ($perf.FanRPM -gt 0) {{ $row.fan_rpm = [int]$perf.FanRPM }}
                $gpuList[$i] = $row
                $updated = $true
                break
            }}
        }}
        if (-not $updated -and $perf.Name) {{
            $gpuList += @{{
                index = $gpuList.Count
                name = [string]$perf.Name
                util_percent = 0
                temp = $temp
                source = 'dxgk'
                fan_rpm = if ($perf.FanRPM -gt 0) {{ [int]$perf.FanRPM }} else {{ 0 }}
            }}
        }}
    }}
    return @($gpuList)
}}

function Get-AmdAdlGpuTemps {{
    $items = @()
    if (-not (Get-CommandOrNull 'Add-Type')) {{
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
    }} catch {{
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

function Add-MissingDisplayGpu([array]$gpuList, [string]$name, [ref]$indexRef) {{
    $text = ([string]$name).Trim()
    if (-not $text) {{
        return @($gpuList)
    }}
    $identity = Normalize-GpuIdentity $text
    foreach ($item in @($gpuList)) {{
        if ($item.name -and (Normalize-GpuIdentity ([string]$item.name)) -eq $identity) {{
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
            $gpuList = @(Add-MissingDisplayGpu $gpuList ([string]$gpu.Name) ([ref]$nextIndex))
        }}
    }} catch {{}}
    try {{
        $gpuList = @(Merge-DxgkGpuPerfData $gpuList)
    }} catch {{
        Write-AgentLog ('dxgk gpu merge failed: ' + $_.Exception.Message)
    }}
    try {{
        $gpuList = @(Merge-AmdAdlGpuTemps $gpuList)
    }} catch {{
        Write-AgentLog ('amd adl gpu merge failed: ' + $_.Exception.Message)
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
                $output = @(& $tool @args 2>&1)
                $joined = (($output | ForEach-Object {{ [string]$_ }}) -join [Environment]::NewLine)
                if ($joined) {{ $outputs += $joined }}
                if ($LASTEXITCODE -eq 0 -and $joined) {{ break }}
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
        error = (($errors | Select-Object -First 2) -join '; ')
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

function Get-HardwareSnapshot {{
    if (-not $script:HardwareCache) {{
        $cpu = @(Get-AgentInstances 'Win32_Processor') | Select-Object -First 1
        $board = @(Get-AgentInstances 'Win32_BaseBoard') | Select-Object -First 1
        $script:HardwareCache = @{{
            cpu_name = if ($cpu -and $cpu.Name) {{ $cpu.Name }} else {{ 'Unknown CPU' }}
            motherboard = if ($board) {{ Get-BoardText $board }} else {{ 'Unknown motherboard' }}
            mem_speed = Get-MemorySpeed
            hardware_refreshed_at = (Get-Date).ToString('o')
        }}
    }}
    return $script:HardwareCache
}}

function Get-StatusPayload([hashtable]$cfg) {{
    $hardware = $null
    try {{
        $hardware = Get-HardwareSnapshot
    }} catch {{
        $hardware = @{{
            cpu_name = 'Unknown CPU'
            motherboard = 'Unknown motherboard'
            mem_speed = 0
            hardware_refreshed_at = ''
        }}
    }}
    $os = $null
    try {{
        $os = @(Get-AgentInstances 'Win32_OperatingSystem') | Select-Object -First 1
    }} catch {{}}
    $logicalDisk = $null
    try {{
        $logicalDisk = @(Get-AgentInstances 'Win32_LogicalDisk' "DeviceID='C:'") | Select-Object -First 1
    }} catch {{}}
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
    try {{
        if (Get-CommandOrNull 'Get-Counter') {{
            $cpuPercent = [math]::Round((Get-Counter '\\Processor(_Total)\\% Processor Time').CounterSamples[0].CookedValue, 1)
        }}
    }} catch {{}}
    $netSpeed = @(0, 0)
    try {{
        $netSpeed = Get-NetSpeed
    }} catch {{}}
    $taskInfo = Get-AgentTaskInfo

    return @{{
        mac = Get-MacAddress
        hostname = $env:COMPUTERNAME
        ip = Get-PrimaryIPv4
        timestamp = (Get-Date).ToString('o')
        status = @{{
            cpu_name = $hardware.cpu_name
            motherboard = $hardware.motherboard
            mem_speed = $hardware.mem_speed
            cpu_percent = $cpuPercent
            mem_used = $memUsed
            mem_total = $memTotal
            mem_percent = $memPercent
            disk_percent = $diskPercent
            net_sent_kb_s = $netSpeed[0]
            net_recv_kb_s = $netSpeed[1]
            gpu_list = @(Get-GpuInfo)
            codemeter = Get-CodeMeterInfo
            os_caption = if ($os) {{ $os.Caption }} else {{ '' }}
            os_version = if ($os) {{ $os.Version }} else {{ '' }}
            hardware_refreshed_at = $hardware.hardware_refreshed_at
            agent = @{{
                version = $AgentVersion
                current_server_url = $cfg['current_server_url']
                candidate_hosts = @($cfg['candidate_hosts'])
                report_interval_sec = [int]$cfg['report_interval_sec']
                config_updated_at = $cfg['config_updated_at']
                last_config_sync_at = $cfg['last_config_sync_at']
                last_discovery_at = $cfg['last_discovery_at']
                task_name = $TaskName
                task_exists = $taskInfo.exists
                task_state = $taskInfo.state
                task_user = $taskInfo.user
                task_last_run_time = $taskInfo.last_run_time
                task_next_run_time = $taskInfo.next_run_time
                worker_path = $WorkerPath
            }}
        }}
    }}
}}

try {{
    New-Item -ItemType Directory -Force -Path $AgentDir | Out-Null
    Write-AgentLog ('worker run starting version=' + $AgentVersion)
    $config = Load-AgentConfig
    Write-AgentLog ('config loaded current=' + [string]$config['current_server_url'])
    $config = Find-AvailableServer $config
    Write-AgentLog ('active server=' + [string]$config['current_server_url'])
}} catch {{
    try {{
        Write-AgentLog ('worker startup failed: ' + (Get-ErrorDetails $_))
    }} catch {{}}
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

    $payload = Get-StatusPayload $config | ConvertTo-Json -Depth 8
    $reportUrl = $config['current_server_url'].TrimEnd('/') + $config['report_path']
    $response = Invoke-AgentJsonRequest -Uri $reportUrl -Method Post -ContentType 'application/json' -Body $payload -TimeoutSec 8
    Write-AgentLog ('report ok -> ' + $reportUrl)
    if ($response -and $response.agent_config) {{
        Merge-AgentConfig $config (Convert-ToHashtable $response.agent_config) | Out-Null
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
    }}
}} catch {{
    Write-AgentLog ('worker run failed: ' + (Get-ErrorDetails $_))
    exit 1
}}
exit 0
"""

def build_agent_launcher_script():
    return """$ErrorActionPreference = 'Continue'
$AgentDir = Join-Path $env:ProgramData 'SmartCenterAgent'
$WorkerPath = Join-Path $AgentDir 'agent_worker.ps1'
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

Write-RunnerLog 'launcher started'
try {
    if (-not (Test-Path $WorkerPath)) {
        throw ('missing worker script: ' + $WorkerPath)
    }
    & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $WorkerPath *>> $RunnerLogPath
    $workerExitCode = $LASTEXITCODE
    if ($workerExitCode -ne 0) {
        Write-RunnerLog ('worker exited with code ' + $workerExitCode)
        exit $workerExitCode
    }
    Write-RunnerLog 'worker exited successfully'
} catch {
    Write-RunnerLog ('launcher failed: ' + $_.Exception.Message)
    throw
}
"""

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
$Utf8Encoding = New-Object System.Text.UTF8Encoding($true)

function Write-DeployLog([string]$msg) {{
    $parent = [System.IO.Path]::GetDirectoryName($DeployLogPath)
    if ($parent) {{
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }}
    [System.IO.File]::AppendAllText($DeployLogPath, ("[" + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + "] " + $msg + [Environment]::NewLine), $Utf8Encoding)
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
    if ($compact.Length -lt 12) {{
        return ''
    }}
    $compact = $compact.Substring(0, 12)
    return ($compact.Substring(0, 2) + '-' + $compact.Substring(2, 2) + '-' + $compact.Substring(4, 2) + '-' + $compact.Substring(6, 2) + '-' + $compact.Substring(8, 2) + '-' + $compact.Substring(10, 2))
}}

function Get-MacAddress {{
    try {{
        $adapters = Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object {{
            $_.IPEnabled -eq $true -and $_.MACAddress
        }}
        $adapter = $adapters | Select-Object -First 1
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
    return ('TEMP-' + [guid]::NewGuid().ToString().Substring(0, 12).ToUpper())
}}

function Get-PrimaryIPv4 {{
    try {{
        $adapters = Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object {{
            $_.IPEnabled -eq $true -and $_.IPAddress
        }}
        foreach ($adapter in $adapters) {{
            $ipv4 = $adapter.IPAddress | Where-Object {{ $_ -match '^\\d+\\.\\d+\\.\\d+\\.\\d+$' }} | Select-Object -First 1
            if ($ipv4) {{
                return $ipv4
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
                $_.CommandLine -like '*SmartCenterAgent*agent_launcher.ps1*'
            )
        }}
        foreach ($proc in $targets) {{
            try {{
                Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
                Write-DeployLog ('stopped old process pid=' + $proc.ProcessId)
            }} catch {{}}
        }}
    }} catch {{}}
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
Write-DeployLog 'deployment started'
Remove-AgentTask
Stop-AgentProcesses
Start-Sleep -Milliseconds 600

$worker = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{worker_b64}'))
Write-TextFile $WorkerPath $worker
$launcher = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{launcher_b64}'))
Write-TextFile $LauncherPath $launcher
$agentConfig = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{config_b64}'))
Write-TextFile $ConfigPath $agentConfig
Write-DeployLog 'agent files written'

Register-AgentTask
Start-AgentTask

$initialWorkerExitCode = 999
$initialWorkerLogTail = ''
try {{
    & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $WorkerPath *>> $DeployLogPath
    $initialWorkerExitCode = $LASTEXITCODE
    if ($initialWorkerExitCode -eq 0) {{
        Write-DeployLog 'initial worker run completed'
    }} else {{
        Write-DeployLog ('initial worker run failed with exit=' + $initialWorkerExitCode)
    }}
}} catch {{
    Write-DeployLog ('initial worker run failed: ' + $_.Exception.Message)
}}
$initialWorkerLogTail = Get-LogTail $AgentLogPath 20

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
    for row in rows:
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
        if row[3]:
            try: is_online = (datetime.now() - datetime.fromisoformat(row[3].replace('Z','+00:00')).replace(tzinfo=None)).total_seconds() < offline_window_sec
            except: pass
        machine = {
            "mac": row[0],
            "hostname": row[1] or "未知主机",
            "ip": row[2],
            "is_online": is_online,
            "last_online": row[3],
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
            ["ping", "-n", "1", "-w", "120", ip],
            capture_output=True,
            text=True,
            encoding="gbk",
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
        return jsonify({
            "status": "ignored",
            "reason": "payload_too_large",
            "command": None,
            "agent_config": build_agent_runtime_config(get_server_host_from_request())
        }), 202

    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}
    if not data:
        try:
            payload_text = request.get_data(cache=True, as_text=True) or ""
            data = json.loads(payload_text) if payload_text else {}
        except Exception:
            data = {}
    mac = normalize_machine_mac(data.get("mac"))
    if not mac:
        return jsonify({"status": "error", "error": "missing mac"}), 400

    status_payload = data.get("status") if isinstance(data.get("status"), dict) else {}
    timestamp = str(data.get("timestamp") or datetime.now().isoformat())
    hostname = str(data.get("hostname") or "未知主机")
    ip = str(data.get("ip") or request.remote_addr or "")
    _store_machine_status(mac, hostname, ip, timestamp, status_payload)
    return jsonify({
        "status": "ok",
        "command": _pop_machine_command(mac),
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
        from wakeonlan import send_magic_packet; send_magic_packet(wake_mac)
        log_audit_event("server.wake", target=normalized_mac, detail={"mac": normalized_mac})
        return jsonify({"status": "ok"})
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
