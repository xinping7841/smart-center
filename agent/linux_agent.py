#!/usr/bin/env python3
# AI_MODULE: smart_center_linux_agent
# AI_PURPOSE: Linux 服务器监控 Agent，采集 CPU/内存/硬件/网络/GPU/CodeMeter 并上报中控。
# AI_BOUNDARY: 只采集和执行中控下发的服务器命令；不包含前端展示布局。
# AI_DATA_FLOW: Linux host sensors/dmidecode/procfs -> /report payload -> server_monitor_api -> 服务器看板。
# AI_RISK: 高，包含自更新、命令轮询和关机/重启/WOL 状态反馈，采集字段要保持兼容。
# AI_SEARCH_KEYWORDS: linux agent, memory topology, cpu topology, dimm channel, server monitor.
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


AGENT_VERSION = "__AGENT_VERSION__"
DEFAULT_REPORT_URL = "http://__SERVER_HOST__:__SERVER_PORT__/report"
REPORT_URL = os.environ.get("SMART_CENTER_REPORT_URL", DEFAULT_REPORT_URL)
HEARTBEAT_URL = os.environ.get("SMART_CENTER_HEARTBEAT_URL", REPORT_URL.rsplit("/", 1)[0] + "/agent/heartbeat")
REPORT_INTERVAL_SEC = float(os.environ.get("SMART_CENTER_REPORT_INTERVAL", "5"))
SERVICE_NAME = os.environ.get("SMART_CENTER_SERVICE_NAME", "smart-center-agent.service")
AGENT_PATH = Path(os.environ.get("SMART_CENTER_AGENT_PATH", __file__)).resolve()
AGENT_DIR = AGENT_PATH.parent
BACKUP_DIR = AGENT_DIR / "backups"
SELF_UPDATE_STATE_PATH = AGENT_DIR / "self_update.json"

CPU_SAMPLE = {"total": None, "idle": None}
NET_SAMPLE = {"sent": None, "recv": None, "ts": None}
HW_CACHE = {"expires_at": 0.0, "payload": {}}
GPU_CACHE = {"expires_at": 0.0, "payload": []}
GPU_DIAGNOSTIC_CACHE = {"expires_at": 0.0, "payload": {}}
CODEMETER_CACHE = {"expires_at": 0.0, "payload": {}}
NTP_STATE_PATH = AGENT_DIR / "ntp_state.json"


def now_iso():
    return datetime.now().isoformat()


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return ""


def write_json(path, payload):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    except Exception:
        pass


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}


def read_int(path):
    try:
        return int(read_text(path))
    except Exception:
        return None


def log(message):
    print(f"[{now_iso()}] {message}", flush=True)


def machine_id():
    for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        value = read_text(candidate)
        if value:
            return value
    return hashlib.sha1(socket.gethostname().encode("utf-8", errors="ignore")).hexdigest()


def machine_mac():
    normalized = "".join(ch for ch in machine_id().upper() if ch.isalnum())[-12:] or "LOCALHOST"
    return f"LOCAL-{normalized}"


def format_mac(raw):
    compact = "".join(ch for ch in str(raw or "") if ch in "0123456789abcdefABCDEF").upper()
    if len(compact) != 12 or compact == "000000000000":
        return ""
    return "-".join(compact[index:index + 2] for index in range(0, 12, 2))


def iface_mac(iface):
    name = str(iface or "").strip()
    if not name:
        return ""
    return format_mac(read_text(f"/sys/class/net/{name}/address"))


def iface_for_ip(ip_addr):
    target = str(ip_addr or "").strip()
    if not target:
        return ""
    try:
        result = subprocess.run(["ip", "-o", "-4", "addr", "show"], capture_output=True, text=True, timeout=2, encoding="utf-8", errors="ignore")
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


def build_network_primary(iface_name, ip_addr):
    iface = str(iface_name or "").strip()
    ip_value = str(ip_addr or "").strip()
    if ip_value:
        ip_iface = iface_for_ip(ip_value)
        if ip_iface:
            iface = ip_iface
    return {
        "adapter_name": iface,
        "adapter_ip": ip_value,
        "adapter_mac": iface_mac(iface),
        "sample_scope": "default_route_interface",
    }


def primary_ip():
    try:
        host, port = urllib.parse.urlparse(REPORT_URL).hostname, urllib.parse.urlparse(REPORT_URL).port or 80
    except Exception:
        host, port = "192.168.50.120", 6899
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect((host or "192.168.50.120", int(port)))
        value = sock.getsockname()[0]
        sock.close()
        return value
    except Exception:
        return "127.0.0.1"


def local_ipv4_addresses():
    addresses = set()
    primary = primary_ip()
    if primary and primary != "127.0.0.1":
        addresses.add(primary)
    try:
        result = subprocess.run(["ip", "-o", "-4", "addr", "show"], capture_output=True, text=True, timeout=2, encoding="utf-8", errors="ignore")
        if result.returncode == 0:
            for match in re.finditer(r"\binet\s+([0-9.]+)/", result.stdout or ""):
                value = match.group(1)
                if value and not value.startswith("127."):
                    addresses.add(value)
    except Exception:
        pass
    return addresses


def report_base_url():
    return REPORT_URL.rsplit("/", 1)[0]


def http_json(url, timeout=8):
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(1024 * 1024)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8", errors="ignore"))


def http_text(url, timeout=12):
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(4 * 1024 * 1024).decode("utf-8", errors="ignore")


def command_exists(name):
    return bool(shutil.which(str(name or "")))


def run_command(command, timeout=8):
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="ignore")


def service_is_active(name):
    if not command_exists("systemctl"):
        return False
    try:
        result = run_command(["systemctl", "is-active", name], timeout=3)
        return (result.stdout or "").strip() == "active"
    except Exception:
        return False


def service_exists(name):
    if not command_exists("systemctl"):
        return False
    try:
        result = run_command(["systemctl", "status", name], timeout=3)
        text = (result.stdout or "") + (result.stderr or "")
        return "Loaded: not-found" not in text and "could not be found" not in text
    except Exception:
        return False


def managed_block(lines):
    return [
        "# BEGIN Smart Center managed NTP",
        *lines,
        "# END Smart Center managed NTP",
        "",
    ]


def replace_managed_block(text, lines):
    block = "\n".join(managed_block(lines))
    pattern = r"(?ms)^# BEGIN Smart Center managed NTP\n.*?^# END Smart Center managed NTP\n?"
    if re.search(pattern, text or ""):
        return re.sub(pattern, block, text or "").rstrip() + "\n"
    return (text or "").rstrip() + "\n\n" + block


def strip_managed_block(text):
    pattern = r"(?ms)^# BEGIN Smart Center managed NTP\n.*?^# END Smart Center managed NTP\n?"
    return re.sub(pattern, "", text or "").rstrip() + "\n"


def chrony_config_has_servers(text, servers):
    for server in servers:
        if not re.search(r"(?m)^\s*(server|pool)\s+" + re.escape(server) + r"(\s|$)", text or ""):
            return False
    return True


def command_summary(result):
    if result is None:
        return ""
    text = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:360]


def read_ntp_source():
    if command_exists("chronyc"):
        try:
            result = run_command(["chronyc", "tracking"], timeout=4)
            if result.returncode == 0:
                match = re.search(r"Reference ID\s*:\s*(.+)", result.stdout or "")
                if match:
                    return match.group(1).strip()
        except Exception:
            pass
    if command_exists("timedatectl"):
        try:
            result = run_command(["timedatectl", "show", "-p", "NTPSynchronized", "-p", "NTP"], timeout=4)
            if result.returncode == 0:
                return re.sub(r"\s+", " ", result.stdout.strip())
        except Exception:
            pass
    return ""


def write_ntp_state(payload):
    state = read_json(NTP_STATE_PATH)
    if not isinstance(state, dict):
        state = {}
    state.update(payload)
    state["updated_at"] = now_iso()
    write_json(NTP_STATE_PATH, state)
    return state


def desired_ntp_servers(agent_config):
    servers = []
    for key in ("ntp_primary", "ntp_fallback"):
        value = str((agent_config or {}).get(key) or "").strip()
        if value and value not in servers:
            servers.append(value)
    local_ips = local_ipv4_addresses()
    return [server for server in servers if server not in local_ips]


def configure_chrony_ntp(servers):
    conf_path = Path("/etc/chrony/chrony.conf")
    if not conf_path.exists():
        conf_path = Path("/etc/chrony.conf")
    if not conf_path.exists():
        raise RuntimeError("chrony config not found")
    lines = []
    for index, server in enumerate(servers):
        suffix = " prefer" if index == 0 else ""
        lines.append(f"server {server} iburst{suffix}")
    before = conf_path.read_text(encoding="utf-8", errors="ignore")
    without_managed = strip_managed_block(before)
    if chrony_config_has_servers(without_managed, servers):
        after = without_managed
    else:
        after = replace_managed_block(without_managed, lines)
    changed = before != after
    if changed:
        backup = conf_path.with_name(conf_path.name + f".smart-center-backup-{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(conf_path, backup)
        conf_path.write_text(after, encoding="utf-8")
    if command_exists("systemctl"):
        service = "chrony" if service_exists("chrony") else "chronyd"
        result = run_command(["systemctl", "restart", service], timeout=12)
        if result.returncode != 0:
            raise RuntimeError(f"restart {service} failed: {command_summary(result)}")
    return {"service": "chrony", "changed": changed}


def configure_timesyncd_ntp(servers):
    conf_dir = Path("/etc/systemd/timesyncd.conf.d")
    conf_dir.mkdir(parents=True, exist_ok=True)
    conf_path = conf_dir / "smart-center-ntp.conf"
    primary = servers[0] if servers else ""
    fallback = " ".join(servers[1:])
    text = "[Time]\nNTP=" + primary + "\n"
    if fallback:
        text += "FallbackNTP=" + fallback + "\n"
    before = read_text(conf_path)
    changed = before.strip() != text.strip()
    if changed:
        conf_path.write_text(text, encoding="utf-8")
    if command_exists("timedatectl"):
        run_command(["timedatectl", "set-ntp", "true"], timeout=8)
    if command_exists("systemctl"):
        result = run_command(["systemctl", "restart", "systemd-timesyncd"], timeout=12)
        if result.returncode != 0:
            raise RuntimeError(f"restart systemd-timesyncd failed: {command_summary(result)}")
    return {"service": "systemd-timesyncd", "changed": changed}


def configure_linux_ntp(agent_config):
    cfg = agent_config if isinstance(agent_config, dict) else {}
    if not bool(cfg.get("ntp_enabled", True)):
        return write_ntp_state({"ntp_enabled": False, "ntp_last_result": "disabled"})
    primary = str(cfg.get("ntp_primary") or "").strip()
    fallback = str(cfg.get("ntp_fallback") or "").strip()
    interval = int(float(cfg.get("ntp_check_interval_sec") or 3600))
    interval = max(300, interval)
    state = read_json(NTP_STATE_PATH)
    last_check = str(state.get("last_ntp_check_at") or "")
    if last_check:
        try:
            last_dt = datetime.fromisoformat(last_check)
            if (datetime.now() - last_dt).total_seconds() < interval and str(state.get("ntp_last_result") or "").startswith("ok"):
                return state
        except Exception:
            pass
    servers = desired_ntp_servers(cfg)
    base_state = {
        "ntp_enabled": True,
        "ntp_primary": primary,
        "ntp_fallback": fallback,
        "last_ntp_check_at": now_iso(),
    }
    if not servers:
        return write_ntp_state({**base_state, "ntp_last_result": "ok local_ntp_server"})
    try:
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            raise RuntimeError("linux agent is not running as root")
        if command_exists("chronyc") or service_exists("chrony") or service_exists("chronyd"):
            applied = configure_chrony_ntp(servers)
        elif service_exists("systemd-timesyncd"):
            applied = configure_timesyncd_ntp(servers)
        else:
            raise RuntimeError("no supported NTP service found")
        source = read_ntp_source()
        return write_ntp_state({
            **base_state,
            "ntp_configured_at": now_iso(),
            "ntp_service": applied.get("service"),
            "ntp_servers": servers,
            "ntp_last_result": "ok servers=" + " ".join(servers) + (" source=" + source if source else ""),
        })
    except Exception as exc:
        return write_ntp_state({**base_state, "ntp_servers": servers, "ntp_last_result": "error " + str(exc)})


def version_key(value):
    parts = re.findall(r"\d+|[A-Za-z]+", str(value or ""))
    key = []
    for part in parts:
        key.append((0, int(part)) if part.isdigit() else (1, part.lower()))
    return key


def compare_versions(left, right):
    a, b = version_key(left), version_key(right)
    max_len = max(len(a), len(b))
    a.extend([(0, 0)] * (max_len - len(a)))
    b.extend([(0, 0)] * (max_len - len(b)))
    return (a > b) - (a < b)


def update_self_state(payload):
    data = {
        "checked_at": now_iso(),
        "current_version": AGENT_VERSION,
    }
    if isinstance(payload, dict):
        data.update(payload)
    write_json(SELF_UPDATE_STATE_PATH, data)
    return data


def restart_self():
    # systemd has Restart=always; exiting cleanly is enough and avoids nested restart races.
    sys.exit(0)


def try_self_update(agent_config):
    if not isinstance(agent_config, dict):
        return False
    remote_version = str(agent_config.get("version") or "").strip()
    if not remote_version or compare_versions(remote_version, AGENT_VERSION) <= 0:
        return False
    linux_path = str(agent_config.get("linux_worker_path") or "/agent/linux.py").strip() or "/agent/linux.py"
    url = report_base_url().rstrip("/") + linux_path + f"?v={remote_version}&ts={int(time.time() * 1000)}"
    try:
        script_text = http_text(url, timeout=12)
        if f'AGENT_VERSION = "{remote_version}"' not in script_text:
            raise RuntimeError("downloaded linux agent version mismatch")
        if "smart-center-agent.service" not in script_text or "try_self_update" not in script_text:
            raise RuntimeError("downloaded linux agent marker missing")
        tmp_path = AGENT_PATH.with_suffix(".py.new")
        tmp_path.write_text(script_text, encoding="utf-8")
        tmp_path.chmod(0o755)
        subprocess.run([sys.executable, "-m", "py_compile", str(tmp_path)], check=True, timeout=10)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup_path = BACKUP_DIR / f"linux_agent.py.before_{AGENT_VERSION}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if AGENT_PATH.exists():
            shutil.copy2(AGENT_PATH, backup_path)
        os.replace(tmp_path, AGENT_PATH)
        update_self_state({"action": "updated", "ok": True, "target_version": remote_version, "source": url})
        log(f"self-update installed {AGENT_VERSION} -> {remote_version}; restarting")
        restart_self()
    except SystemExit:
        raise
    except Exception as exc:
        update_self_state({"action": "failed", "ok": False, "target_version": remote_version, "source": url, "error": str(exc)})
        log(f"self-update failed target={remote_version}: {exc}")
    return False


def clean_mac_text(value):
    return "".join(ch for ch in str(value or "") if ch in "0123456789abcdefABCDEF").upper()


def send_magic_packet(target_mac, target_ip=""):
    clean_mac = clean_mac_text(target_mac)
    if len(clean_mac) != 12:
        raise ValueError("invalid wake mac")
    mac_bytes = bytes(int(clean_mac[index:index + 2], 16) for index in range(0, 12, 2))
    packet = b"\xff" * 6 + mac_bytes * 16
    targets = ["255.255.255.255"]
    if target_ip:
        try:
            parts = list(socket.inet_aton(str(target_ip)))
            parts[3] = 255
            targets.append(socket.inet_ntoa(bytes(parts)))
        except Exception:
            pass
    targets = list(dict.fromkeys(item for item in targets if item))
    ports = [9, 7]
    for _ in range(3):
        for broadcast_target in targets:
            for port in ports:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    sock.sendto(packet, (broadcast_target, port))
                finally:
                    sock.close()
        time.sleep(0.12)
    return {"targets": targets, "ports": ports, "attempts": 3}


def run_host_command(command):
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


def read_cpu_percent():
    lines = read_text("/proc/stat").splitlines()
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
    prev_total = CPU_SAMPLE["total"]
    prev_idle = CPU_SAMPLE["idle"]
    CPU_SAMPLE.update({"total": total, "idle": idle})
    if prev_total is None or prev_idle is None:
        return 0.0
    delta_total = total - prev_total
    delta_idle = idle - prev_idle
    if delta_total <= 0:
        return 0.0
    return round(max(0.0, min(100.0, ((delta_total - delta_idle) / float(delta_total)) * 100.0)), 1)


def read_meminfo():
    data = {}
    for line in read_text("/proc/meminfo").splitlines():
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


def read_net_rates():
    default_iface = ""
    for line in read_text("/proc/net/route").splitlines()[1:]:
        parts = [item for item in line.split() if item]
        if len(parts) >= 2 and parts[1] == "00000000":
            default_iface = parts[0]
            break
    rows = []
    for line in read_text("/proc/net/dev").splitlines()[2:]:
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
    network_primary = build_network_primary(iface_name, primary_ip())
    now_ts = time.time()
    prev_sent = NET_SAMPLE["sent"]
    prev_recv = NET_SAMPLE["recv"]
    prev_ts = NET_SAMPLE["ts"]
    prev_iface = NET_SAMPLE.get("iface")
    NET_SAMPLE.update({"sent": sent_total, "recv": recv_total, "ts": now_ts, "iface": iface_name})
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


def parse_memory_speed(raw_text):
    match = re.search(r"(\d+)\s*(?:MT/s|MHz)?", str(raw_text or ""), flags=re.IGNORECASE)
    if not match:
        return None
    try:
        value = int(match.group(1))
    except Exception:
        return None
    return value if value > 0 else None


def read_memory_speed():
    for candidate in ("/sys/devices/system/edac/mc/mc0/dimm0/dimm_speed", "/sys/devices/system/memory/memory0/speed"):
        value = parse_memory_speed(read_text(candidate))
        if value:
            return value
    try:
        result = subprocess.run(["dmidecode", "-t", "memory"], capture_output=True, text=True, timeout=3, encoding="utf-8", errors="ignore")
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line_text = line.strip()
                lower = line_text.lower()
                if (lower.startswith("configured memory speed:") or lower.startswith("speed:")) and "unknown" not in lower:
                    value = parse_memory_speed(line_text)
                    if value:
                        return value
    except Exception:
        pass
    return None


def infer_memory_channel_from_label(label):
    text = str(label or "").strip()
    patterns = (
        r"channel\s*([a-z0-9]+)",
        r"channel([a-z])",
        r"\bDIMM[_\s-]*([A-Z])\d+\b",
        r"\b([A-Z])\d+[_\s-]*DIMM\b",
        r"\bP\d+[_\s-]*DIMM[_\s-]*([A-Z])\d+\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = str(match.group(1) or "").upper()
            if value:
                return value
    return ""


def memory_channel_mode(channel_count, installed_count):
    if channel_count >= 4:
        return "quad"
    if channel_count == 3:
        return "triple"
    if channel_count == 2:
        return "dual"
    if channel_count == 1 and installed_count:
        return "single"
    return "unknown"


def read_cpu_topology():
    physical_core_ids = set()
    physical_ids = set()
    logical_count = 0
    for block in read_text("/proc/cpuinfo").split("\n\n"):
        current = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            current[key.strip().lower()] = value.strip()
        if not current:
            continue
        logical_count += 1
        physical_id = current.get("physical id") or "0"
        core_id = current.get("core id")
        if core_id is not None:
            physical_core_ids.add((physical_id, core_id))
            physical_ids.add(physical_id)
    fallback_logical = os.cpu_count() or logical_count or 0
    core_count = len(physical_core_ids) if physical_core_ids else fallback_logical
    return {
        "core_count": int(core_count or 0),
        "thread_count": int(logical_count or fallback_logical or 0),
        "socket_count": max(1, len(physical_ids)) if physical_core_ids else 1,
    }


def read_lspci_gpus():
    gpu_list = []
    try:
        result = subprocess.run(["lspci"], capture_output=True, text=True, timeout=2, encoding="utf-8", errors="ignore")
    except Exception:
        return gpu_list
    if result.returncode != 0:
        return gpu_list
    index = 0
    for line in result.stdout.splitlines():
        if not re.search(r"(VGA|3D|Display)", line, flags=re.IGNORECASE):
            continue
        name = re.sub(r"^[0-9a-fA-F:.]+\s+", "", line).strip()
        name = re.sub(r"\s*\[[0-9a-fA-F]{4}:[0-9a-fA-F]{4}\].*$", "", name).strip()
        gpu_list.append({"index": index, "name": name or "Display Controller", "util_percent": 0, "temp": 0})
        index += 1
    return gpu_list


def read_amdgpu_metrics():
    metrics = []
    diagnostics = {"linux_gpu_checked_at": now_iso(), "linux_drm_devices": [], "linux_amdgpu_count": 0}
    for device_dir in sorted(Path("/sys/class/drm").glob("card*/device")):
        device_info = {"path": str(device_dir), "realpath": str(device_dir.resolve()) if device_dir.exists() else "", "driver": "", "gpu_busy_percent_raw": "", "temps": [], "source": ""}
        try:
            driver_path = device_dir / "driver"
            if driver_path.exists():
                device_info["driver"] = Path(os.readlink(driver_path)).name
        except Exception:
            pass
        amdgpu_hwmon = None
        for hwmon_dir in sorted(device_dir.glob("hwmon/hwmon*")):
            if read_text(hwmon_dir / "name").lower() == "amdgpu":
                amdgpu_hwmon = hwmon_dir
                break
        if not amdgpu_hwmon:
            diagnostics["linux_drm_devices"].append(device_info)
            continue
        temp_c = 0
        temp_candidates = []
        for temp_input in sorted(amdgpu_hwmon.glob("temp*_input")):
            label = read_text(str(temp_input).replace("_input", "_label")).lower()
            raw_text = read_text(temp_input)
            device_info["temps"].append({"file": temp_input.name, "label": label, "raw": raw_text})
            temp_candidates.append((0 if label == "edge" else 1, temp_input))
        for _, temp_input in sorted(temp_candidates):
            raw = read_int(temp_input)
            if raw is None:
                continue
            temp_c = int(round(raw / 1000.0 if raw > 1000 else raw))
            break
        busy_path = device_dir / "gpu_busy_percent"
        util_raw = read_text(busy_path)
        device_info["gpu_busy_percent_raw"] = util_raw
        util = read_int(busy_path)
        diagnostics["linux_amdgpu_count"] += 1
        device_info["source"] = "amdgpu-hwmon"
        diagnostics["linux_drm_devices"].append(device_info)
        metrics.append({"temp": max(0, temp_c), "util_percent": max(0, min(100, int(util or 0))), "source": "amdgpu-hwmon"})
    GPU_DIAGNOSTIC_CACHE.update({"payload": diagnostics, "expires_at": time.time() + 30.0})
    return metrics


def merge_amdgpu_metrics(gpu_list):
    metrics = read_amdgpu_metrics()
    if not metrics:
        return gpu_list
    merged = list(gpu_list)
    amd_indexes = [idx for idx, item in enumerate(merged) if re.search(r"(amd|radeon|cezanne|vega)", str(item.get("name") or ""), flags=re.IGNORECASE)]
    for metric_idx, metric in enumerate(metrics):
        if metric_idx < len(amd_indexes):
            target = dict(merged[amd_indexes[metric_idx]])
            target.update(metric)
            merged[amd_indexes[metric_idx]] = target
        else:
            target = {"index": len(merged), "name": "AMD Radeon Graphics"}
            target.update(metric)
            merged.append(target)
    return merged


def read_gpu_snapshot():
    now_ts = time.time()
    cached = GPU_CACHE["payload"]
    if cached and now_ts < float(GPU_CACHE["expires_at"] or 0.0):
        return cached
    gpu_list = []
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=2, encoding="utf-8", errors="ignore",
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = [item.strip() for item in line.split(",")]
                if len(parts) < 8:
                    continue
                try:
                    memory_used = int(float(parts[4] or 0))
                    memory_total = int(float(parts[5] or 0))
                    gpu_list.append({
                        "index": int(parts[0]),
                        "name": parts[1],
                        "util_percent": int(float(parts[2] or 0)),
                        "memory_util_percent": int(float(parts[3] or 0)),
                        "memory_used_mb": memory_used,
                        "memory_total_mb": memory_total,
                        "temp": int(float(parts[6] or 0)),
                        "power_w": round(float(parts[7] or 0), 1),
                        "source": "nvidia-smi",
                    })
                except Exception:
                    continue
    except Exception:
        pass
    if not gpu_list:
        gpu_list = merge_amdgpu_metrics(read_lspci_gpus())
    GPU_CACHE.update({"payload": gpu_list, "expires_at": now_ts + 30.0})
    return gpu_list


def read_gpu_diagnostics():
    cached = GPU_DIAGNOSTIC_CACHE["payload"]
    if cached and time.time() < float(GPU_DIAGNOSTIC_CACHE["expires_at"] or 0.0):
        return cached
    GPU_CACHE.update({"expires_at": 0.0, "payload": []})
    read_gpu_snapshot()
    return GPU_DIAGNOSTIC_CACHE["payload"] if isinstance(GPU_DIAGNOSTIC_CACHE["payload"], dict) else {}


def find_codemeter_tool():
    for name in ("cmu", "cmu32"):
        path = shutil.which(name)
        if path:
            return path
    for candidate in ("/usr/bin/cmu", "/usr/sbin/cmu", "/usr/local/bin/cmu", "/opt/CodeMeter/Runtime/bin/cmu", "/opt/codemeter/bin/cmu"):
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return ""


def read_codemeter_info():
    now_ts = time.time()
    cached = CODEMETER_CACHE["payload"]
    if cached and now_ts < float(CODEMETER_CACHE["expires_at"] or 0.0):
        return cached
    checked_at = now_iso()
    tool = find_codemeter_tool()
    service_state = "unknown"
    try:
        result = subprocess.run(["systemctl", "is-active", "codemeter"], capture_output=True, text=True, timeout=1.5, encoding="utf-8", errors="ignore")
        service_state = (result.stdout or result.stderr or "").strip() or "unknown"
    except Exception:
        pass
    installed = bool(tool) or service_state not in ("unknown", "inactive", "failed")
    payload = {"installed": installed, "running": service_state == "active", "service_state": service_state, "tool": tool, "serials": [], "containers": [], "licenses": [], "validity": "unknown", "summary": "未安装" if not installed else "待检测", "level": "muted" if not installed else "warning", "checked_at": checked_at, "raw_excerpt": "", "error": ""}
    CODEMETER_CACHE.update({"payload": payload, "expires_at": now_ts + 120.0})
    return payload


def command_output(command, timeout=3):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="ignore")
        if result.returncode == 0:
            return result.stdout or ""
    except Exception:
        pass
    return ""


def parse_os_release():
    values = {}
    for line in read_text("/etc/os-release").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def read_os_info():
    release = parse_os_release()
    return {
        "name": release.get("PRETTY_NAME") or platform.platform(),
        "id": release.get("ID") or "",
        "version": release.get("VERSION_ID") or "",
        "codename": release.get("VERSION_CODENAME") or release.get("UBUNTU_CODENAME") or "",
        "kernel": platform.release(),
        "arch": platform.machine(),
    }


def parse_size_bytes(text):
    raw = str(text or "").strip()
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMGTPE]?B)", raw, flags=re.IGNORECASE)
    if not match:
        return 0
    value = float(match.group(1))
    unit = match.group(2).upper()
    scale = {"KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4, "PB": 1024 ** 5}.get(unit, 1)
    return int(value * scale)


def read_memory_topology():
    text = command_output(["dmidecode", "-t", "memory"], timeout=4)
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
            current["size_bytes"] = parse_size_bytes(value)
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
        channel = infer_memory_channel_from_label(label)
        if channel and channel not in channels:
            channels.append(channel)
    channel_count = len(channels)
    mode = memory_channel_mode(channel_count, len(installed))
    total_bytes = sum(int(item.get("size_bytes") or 0) for item in installed)
    summary_bits = [f"{len(installed)} DIMM"]
    if total_bytes:
        summary_bits.append(f"{round(total_bytes / (1024 ** 3), 1):g} GB")
    if mode != "unknown":
        summary_bits.append(f"{mode} channel inferred")
    else:
        summary_bits.append("channel unknown")
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


def _mounts_from_lsblk_node(node):
    mounts = node.get("mountpoints")
    if isinstance(mounts, list):
        return [str(item) for item in mounts if item]
    mount = node.get("mountpoint")
    return [str(mount)] if mount else []


def read_filesystem_usage():
    usage = {}
    text = command_output(["df", "-T", "-B1", "-P"], timeout=4)
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
        percent_value = 0.0
        try:
            percent_value = float(str(percent).rstrip("%"))
        except Exception:
            pass
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


def read_storage_devices():
    output = command_output(["lsblk", "-b", "-J", "-o", "NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS,MOUNTPOINT,MODEL,SERIAL,TRAN,ROTA,RM,PKNAME"], timeout=4)
    try:
        parsed = json.loads(output) if output else {}
    except Exception:
        parsed = {}
    devices = []
    filesystems = []
    fs_usage = read_filesystem_usage()
    for node in parsed.get("blockdevices", []) if isinstance(parsed, dict) else []:
        if not isinstance(node, dict) or node.get("type") in ("loop", "rom"):
            continue
        children = []
        for child in node.get("children") or []:
            if not isinstance(child, dict):
                continue
            mounts = _mounts_from_lsblk_node(child)
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
        mounts = _mounts_from_lsblk_node(node)
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


def read_network_adapters():
    output = command_output(["ip", "-j", "addr"], timeout=3)
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
        speed = read_text(f"/sys/class/net/{ifname}/speed")
        try:
            speed_mbps = int(speed)
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
            "mac": read_text(f"/sys/class/net/{ifname}/address"),
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
    nmcli = command_output(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev", "status"], timeout=3)
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


def read_bluetooth_info():
    controllers = []
    for line in command_output(["bluetoothctl", "list"], timeout=3).splitlines():
        match = re.match(r"Controller\s+([0-9A-Fa-f:]+)\s+(.+)", line.strip())
        if match:
            controllers.append({"mac": match.group(1).upper(), "name": match.group(2).strip()})
    rfkill_text = command_output(["rfkill", "list"], timeout=3)
    has_rfkill_bt = bool(re.search(r"Bluetooth", rfkill_text, flags=re.IGNORECASE))
    lsusb_text = command_output(["lsusb"], timeout=3)
    has_usb_bt = bool(re.search(r"bluetooth", lsusb_text, flags=re.IGNORECASE))
    blocked = bool(re.search(r"Hard blocked:\s*yes|Soft blocked:\s*yes", rfkill_text, flags=re.IGNORECASE))
    return {
        "present": bool(controllers or has_rfkill_bt or has_usb_bt),
        "blocked": blocked,
        "controllers": controllers[:8],
    }


def read_hardware_profile():
    now_ts = time.time()
    cached = HW_CACHE["payload"]
    if cached and now_ts < float(HW_CACHE["expires_at"] or 0.0):
        return cached
    cpu_name = ""
    for line in read_text("/proc/cpuinfo").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            if key.strip().lower() == "model name":
                cpu_name = value.strip()
                break
    board_vendor = read_text("/sys/class/dmi/id/board_vendor")
    board_name = read_text("/sys/class/dmi/id/board_name")
    motherboard = " / ".join([item for item in [board_vendor, board_name] if item]) or platform.platform()
    storage = read_storage_devices()
    network = read_network_adapters()
    memory_topology = read_memory_topology()
    mem_speed = read_memory_speed()
    if not mem_speed:
        for module in memory_topology.get("modules") or []:
            for key in ("configured_memory_speed", "speed"):
                value = parse_memory_speed(module.get(key))
                if value:
                    mem_speed = value
                    break
            if mem_speed:
                break
    payload = {
        "cpu_name": cpu_name or platform.processor() or platform.machine() or "Linux Host",
        "cpu_topology": read_cpu_topology(),
        "motherboard": motherboard,
        "mem_speed": mem_speed,
        "os_info": read_os_info(),
        "memory_topology": memory_topology,
        "storage_devices": storage.get("devices") or [],
        "storage_filesystems": storage.get("filesystems") or [],
        "storage_summary": {"disk_count": storage.get("disk_count") or 0, "mounted_count": storage.get("mounted_count") or 0},
        "network_adapters": network.get("adapters") or [],
        "network_summary": {"physical_count": network.get("physical_count") or 0, "active_count": network.get("active_count") or 0},
        "wireless": network.get("wireless") or {},
        "bluetooth": read_bluetooth_info(),
        "gpu_list": read_gpu_snapshot(),
    }
    HW_CACHE.update({"payload": payload, "expires_at": now_ts + 300.0})
    return payload


def build_status():
    hardware = read_hardware_profile()
    meminfo = read_meminfo()
    disk_usage = shutil.disk_usage("/")
    net_rates = read_net_rates()
    collected_at = now_iso()
    self_update = read_json(SELF_UPDATE_STATE_PATH)
    ntp_state = read_json(NTP_STATE_PATH)
    if not isinstance(ntp_state, dict):
        ntp_state = {}
    network_primary = net_rates.get("network_primary") or {}
    physical_mac = format_mac(network_primary.get("adapter_mac"))
    return {
        "cpu_name": hardware.get("cpu_name"),
        "cpu_topology": hardware.get("cpu_topology") or {},
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
        "gpu_list": read_gpu_snapshot(),
        "gpu_diagnostics": read_gpu_diagnostics(),
        "codemeter": read_codemeter_info(),
        "cpu_percent": read_cpu_percent(),
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
        "hardware_refreshed_at": collected_at,
        "host_type": "linux_agent",
        "agent": {
            "version": AGENT_VERSION,
            "physical_mac": physical_mac,
            "task_exists": True,
            "task_state": "systemd 采集",
            "task_user": os.environ.get("USER") or "root",
            "current_server_url": report_base_url(),
            "service": SERVICE_NAME,
            "report_interval_sec": REPORT_INTERVAL_SEC,
            "updated_at": collected_at,
            "self_update": self_update,
            "ntp_enabled": ntp_state.get("ntp_enabled"),
            "ntp_primary": ntp_state.get("ntp_primary"),
            "ntp_fallback": ntp_state.get("ntp_fallback"),
            "last_ntp_check_at": ntp_state.get("last_ntp_check_at"),
            "ntp_configured_at": ntp_state.get("ntp_configured_at"),
            "ntp_last_result": ntp_state.get("ntp_last_result"),
            "ntp_service": ntp_state.get("ntp_service"),
        },
    }


def build_report_payload(status=None, extra=None):
    payload = {"mac": machine_mac(), "hostname": socket.gethostname() or "linux-node", "ip": primary_ip(), "timestamp": now_iso(), "status": status if isinstance(status, dict) else build_status()}
    if isinstance(extra, dict):
        payload.update(extra)
    return payload


def post_report_payload(payload):
    sent_at = now_iso()
    if isinstance(payload, dict):
        payload["client_sent_at"] = sent_at
        status = payload.get("status")
        if isinstance(status, dict):
            status["client_sent_at"] = sent_at
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(REPORT_URL, data=body, headers={"Content-Type": "application/json", "User-Agent": f"smart-center-linux-agent/{AGENT_VERSION}"}, method="POST")
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read(1024 * 1024)
        parsed = json.loads(raw.decode("utf-8", errors="ignore")) if raw else {}
        return resp.status, parsed if isinstance(parsed, dict) else {}


def post_heartbeat_payload():
    sent_at = now_iso()
    payload = {
        "mac": machine_mac(),
        "hostname": socket.gethostname() or "linux-node",
        "ip": primary_ip(),
        "timestamp": sent_at,
        "client_sent_at": sent_at,
        "status": {
            "client_sent_at": sent_at,
            "agent": {
                "version": AGENT_VERSION,
                "current_server_url": report_base_url(),
                "service": SERVICE_NAME,
                "report_interval_sec": REPORT_INTERVAL_SEC,
                "updated_at": sent_at,
                "heartbeat": True,
            },
        },
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(HEARTBEAT_URL, data=body, headers={"Content-Type": "application/json", "User-Agent": f"smart-center-linux-agent/{AGENT_VERSION}"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        raw = resp.read(1024 * 1024)
        parsed = json.loads(raw.decode("utf-8", errors="ignore")) if raw else {}
        return resp.status, parsed if isinstance(parsed, dict) else {}


def report_wake_proxy_result(result):
    status = {"host_type": "linux_agent", "agent": {"version": AGENT_VERSION, "current_server_url": report_base_url(), "service": SERVICE_NAME, "updated_at": now_iso()}}
    post_report_payload(build_report_payload(status=status, extra={"wake_proxy_result": result}))


def handle_command(command):
    if not command:
        return
    if command == "refresh":
        HW_CACHE.update({"expires_at": 0.0, "payload": {}})
        GPU_CACHE.update({"expires_at": 0.0, "payload": []})
        GPU_DIAGNOSTIC_CACHE.update({"expires_at": 0.0, "payload": {}})
        CODEMETER_CACHE.update({"expires_at": 0.0, "payload": {}})
        log("refresh command received")
        return
    if command in ("shutdown", "restart"):
        log(f"{command} command received")
        run_host_command(command)
        return
    if isinstance(command, dict) and command.get("action") == "wake_proxy":
        target_mac = str(command.get("mac") or "")
        target_ip = str(command.get("ip") or "")
        result = {"ok": False, "mac": target_mac, "ip": target_ip, "sent_at": now_iso()}
        try:
            result.update(send_magic_packet(target_mac, target_ip))
            result["ok"] = True
            log(f"wake proxy sent mac={target_mac} ip={target_ip}")
        except Exception as exc:
            result["error"] = str(exc)
            log(f"wake proxy failed mac={target_mac}: {exc}")
        try:
            report_wake_proxy_result(result)
        except Exception as exc:
            log(f"wake proxy result report failed: {exc}")


def report_once():
    _, response = post_report_payload(build_report_payload())
    try:
        post_heartbeat_payload()
    except Exception as exc:
        log(f"heartbeat failed: {exc}")
    if isinstance(response, dict):
        handle_command(response.get("command"))
        agent_config = response.get("agent_config")
        if isinstance(agent_config, dict):
            configure_linux_ntp(agent_config)
        try_self_update(agent_config)


def main():
    update_self_state({"action": "running", "ok": True})
    while True:
        try:
            report_once()
        except SystemExit:
            raise
        except Exception as exc:
            log(f"report failed: {exc}")
        time.sleep(max(2.0, REPORT_INTERVAL_SEC))


if __name__ == "__main__":
    main()
