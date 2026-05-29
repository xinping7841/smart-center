#!/usr/bin/env python3
"""Install the Node-RED flow that reads the current collector and pushes to node-120."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


NODE_RED_DIR = Path.home() / ".node-red"
FLOW_FILE = NODE_RED_DIR / "flows.json"

FLOW_IDS = {
    "tab_current_collector_push",
    "cc_inject_poll",
    "cc_read_and_push",
    "cc_http_push",
    "cc_debug_error",
    "cc_comment",
    "cc_raw_page_http",
    "cc_raw_page_renderer",
    "cc_raw_page_response",
    "cc_raw_json_http",
    "cc_raw_json_renderer",
    "cc_raw_json_response",
}


FUNCTION_CODE = r"""
const net = global.get('net');

const collectorHost = env.get('CURRENT_COLLECTOR_HOST') || '192.168.50.109';
const collectorPort = Number(env.get('CURRENT_COLLECTOR_PORT') || 502);
const smartCenterUrl = env.get('SMART_CENTER_CURRENT_PUSH_URL') || 'http://192.168.50.120:6899/api/current-collector/push';
const token = env.get('SMART_CENTER_CURRENT_PUSH_TOKEN') || '';
const slave = Number(env.get('CURRENT_COLLECTOR_SLAVE') || 1);
const startRegister = Number(env.get('CURRENT_COLLECTOR_REGISTER') || 0x2000);
const count = Number(env.get('CURRENT_COLLECTOR_COUNT') || 16);
const scale = Number(env.get('CURRENT_COLLECTOR_SCALE') || 100);
const multiplier = Number(env.get('CURRENT_COLLECTOR_MULTIPLIER') || 1);
const timeoutMs = Number(env.get('CURRENT_COLLECTOR_TIMEOUT_MS') || 3000);
const minValidChannels = Number(env.get('CURRENT_COLLECTOR_MIN_VALID_CHANNELS') || 0);

function crc16Modbus(buffer) {
    let crc = 0xFFFF;
    for (const byte of buffer) {
        crc ^= byte;
        for (let i = 0; i < 8; i += 1) {
            if (crc & 1) crc = (crc >> 1) ^ 0xA001;
            else crc >>= 1;
        }
    }
    return crc & 0xFFFF;
}

function toHex(buffer) {
    return Array.from(buffer || []).map((b) => b.toString(16).padStart(2, '0').toUpperCase()).join(' ');
}

function buildRequest() {
    const frame = Buffer.alloc(6);
    frame[0] = slave;
    frame[1] = 0x03;
    frame.writeUInt16BE(startRegister, 2);
    frame.writeUInt16BE(count, 4);
    const crc = crc16Modbus(frame);
    return Buffer.concat([frame, Buffer.from([crc & 0xFF, (crc >> 8) & 0xFF])]);
}

function parseCandidateFrame(frame) {
    const expectedLength = 5 + count * 2;
    const expectedCrc = crc16Modbus(frame.subarray(0, -2));
    const actualCrc = frame[frame.length - 2] | (frame[frame.length - 1] << 8);
    if (expectedCrc !== actualCrc) return null;
    if (frame[0] !== slave || frame[1] !== 0x03 || frame[2] !== count * 2) throw new Error(`unexpected frame: ${toHex(frame)}`);
    const raw = [];
    for (let offset = 3; offset < 3 + count * 2; offset += 2) raw.push(frame.readUInt16BE(offset));
    const currents = raw.map((value) => Number(((value / scale) * multiplier).toFixed(3)));
    return { frame, raw, currents };
}

function parseResponse(buffer) {
    const expectedLength = 5 + count * 2;
    if (!Buffer.isBuffer(buffer) || buffer.length < expectedLength) {
        throw new Error(`short response ${buffer ? buffer.length : 0}/${expectedLength}: ${toHex(buffer)}`);
    }

    // Transparent serial servers can return stale bytes or concatenate frames.
    // Scan for a valid RTU response instead of assuming it starts at byte 0.
    const candidates = [];
    for (let offset = 0; offset <= buffer.length - expectedLength; offset += 1) {
        if (buffer[offset] !== slave || buffer[offset + 1] !== 0x03 || buffer[offset + 2] !== count * 2) continue;
        const frame = buffer.subarray(offset, offset + expectedLength);
        const parsed = parseCandidateFrame(frame);
        if (parsed) return parsed;
        candidates.push(toHex(frame));
    }
    throw new Error(`no valid response frame in ${buffer.length} bytes: ${toHex(buffer)} candidates=${candidates.slice(0, 3).join(' | ')}`);
}

function readCollector() {
    return new Promise((resolve, reject) => {
        const request = buildRequest();
        const socket = net.createConnection({ host: collectorHost, port: collectorPort });
        const chunks = [];
        let settled = false;
        const timer = setTimeout(() => {
            if (settled) return;
            settled = true;
            socket.destroy();
            reject(new Error(`collector timeout ${collectorHost}:${collectorPort}`));
        }, timeoutMs);
        socket.on('connect', () => socket.write(request));
        socket.on('data', (chunk) => {
            chunks.push(chunk);
            const merged = Buffer.concat(chunks);
            if (merged.length >= 5 + count * 2 && !settled) {
                try {
                    const parsed = parseResponse(merged);
                    settled = true;
                    clearTimeout(timer);
                    socket.end();
                    resolve({ request, ...parsed });
                } catch (err) {
                    // Keep reading briefly; a later TCP chunk may complete a valid frame.
                    if (merged.length >= (5 + count * 2) * 3) {
                        settled = true;
                        clearTimeout(timer);
                        socket.destroy();
                        reject(err);
                    }
                }
            }
        });
        socket.on('error', (err) => {
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            reject(err);
        });
        socket.on('close', () => {
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            reject(new Error('collector connection closed before full response'));
        });
    });
}

function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

async function readCollectorWithRetry(maxAttempts) {
    let lastError = null;
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
        try {
            const result = await readCollector();
            if (attempt > 1) {
                node.status({ fill: 'green', shape: 'dot', text: `retry ok ${attempt}/${maxAttempts}` });
            }
            return result;
        } catch (err) {
            lastError = err;
            if (attempt < maxAttempts) await delay(180);
        }
    }
    throw lastError;
}

function countActiveChannels(currents) {
    return (currents || []).filter((value) => value !== null && value !== undefined && Number(value) !== 0).length;
}

(async () => {
    if (context.get('busy')) {
        node.status({ fill: 'yellow', shape: 'ring', text: 'skip: previous read still running' });
        return;
    }
    context.set('busy', true);
    const read = await readCollectorWithRetry(2);
    const activeCount = countActiveChannels(read.currents);
    if (minValidChannels > 0 && activeCount < minValidChannels) {
        node.status({ fill: 'yellow', shape: 'ring', text: `skip sparse ${activeCount}/${minValidChannels}` });
        return;
    }
    const payload = {
        source: 'node-red',
        gateway: 'node-121',
        collector_host: collectorHost,
        collector_port: collectorPort,
        slave,
        register_base: `0x${startRegister.toString(16).padStart(4, '0').toUpperCase()}`,
        scale,
        multiplier,
        channel_count: count,
        raw_registers: read.raw,
        currents: read.currents,
        request_hex: toHex(read.request),
        response_hex: toHex(read.frame),
        collected_at: new Date().toISOString(),
    };
    flow.set('current_collector_latest_raw', payload);
    global.set('current_collector_latest_raw', payload);
    msg.method = 'POST';
    msg.url = smartCenterUrl;
    msg.headers = { 'Content-Type': 'application/json' };
    if (token) msg.headers['X-Current-Collector-Token'] = token;
    msg.payload = payload;
    node.status({ fill: 'blue', shape: 'dot', text: `read ${read.currents.length}ch ${new Date().toLocaleTimeString()}` });
    node.send([msg, null]);
})().catch((err) => {
    node.status({ fill: 'red', shape: 'ring', text: String(err.message || err) });
    msg.error = String(err.stack || err.message || err);
    msg.payload = { ok: false, error: msg.error };
    node.error(msg.error, msg);
    node.send([null, msg]);
}).finally(() => {
    context.set('busy', false);
});
return;
"""


RAW_JSON_CODE = r"""
const latest = flow.get('current_collector_latest_raw') || null;
msg.headers = { 'Content-Type': 'application/json; charset=utf-8' };
msg.payload = JSON.stringify({
    ok: !!latest,
    source: 'node-red',
    gateway: 'node-121',
    latest,
    served_at: new Date().toISOString(),
}, null, 2);
return msg;
"""


RAW_PAGE_CODE = r"""
const latest = flow.get('current_collector_latest_raw') || null;

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
    }[ch]));
}

function formatA(value) {
    const num = Number(value);
    return Number.isFinite(num) ? `${num.toFixed(3)} A` : '--';
}

function channelCards(data) {
    const count = Number(data?.channel_count || data?.currents?.length || 16);
    const currents = Array.isArray(data?.currents) ? data.currents : [];
    const registers = Array.isArray(data?.raw_registers) ? data.raw_registers : [];
    return Array.from({ length: count }, (_, idx) => {
        const current = currents[idx];
        const raw = registers[idx];
        const live = Number.isFinite(Number(current)) && Math.abs(Number(current)) > 0.001;
        return `<section class="card ${live ? 'live' : ''}">
            <div class="card-head"><strong>第${idx + 1}路</strong><span>raw ${escapeHtml(raw ?? '--')}</span></div>
            <div class="value">${escapeHtml(formatA(current))}</div>
        </section>`;
    }).join('');
}

const body = latest ? channelCards(latest) : '<div class="empty">等待 Node-RED 第一次采集数据...</div>';
const meta = latest
    ? `${escapeHtml(latest.collected_at || '--')} / ${escapeHtml(latest.collector_host || '--')}:${escapeHtml(latest.collector_port || '--')} / 地址 ${escapeHtml(latest.slave || '--')} / 寄存器 ${escapeHtml(latest.register_base || '--')}`
    : '暂无数据';
const tx = latest?.request_hex || '--';
const rx = latest?.response_hex || '--';

msg.headers = { 'Content-Type': 'text/html; charset=utf-8' };
msg.payload = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="refresh" content="2">
  <title>121 Node-RED 电流原始采集</title>
  <style>
    :root { color-scheme: dark; font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif; background:#07111f; color:#e5edf8; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; padding:18px; background:linear-gradient(180deg,#07111f,#0b1627); }
    header { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:14px; }
    h1 { margin:0; font-size:22px; }
    .meta { color:#93a4bd; font-size:13px; line-height:1.7; }
    .badge { border:1px solid rgba(34,197,94,.28); background:rgba(34,197,94,.13); color:#86efac; border-radius:999px; padding:6px 11px; font-weight:900; font-size:12px; }
    .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(132px,1fr)); gap:8px; }
    .card { border:1px solid rgba(148,163,184,.18); border-radius:8px; padding:9px; background:rgba(15,23,42,.86); }
    .card.live { border-color:rgba(34,197,94,.62); }
    .card-head { display:flex; justify-content:space-between; gap:8px; color:#94a3b8; font-size:11px; font-family:Consolas,monospace; }
    .card-head strong { color:#f8fafc; font-family:"Segoe UI","Microsoft YaHei",Arial,sans-serif; font-size:13px; }
    .value { margin-top:8px; font-family:Consolas,monospace; font-size:20px; font-weight:900; color:#e5edf8; }
    .live .value { color:#86efac; }
    .log { margin-top:12px; color:#9fb0c8; font-family:Consolas,monospace; font-size:11px; line-height:1.5; word-break:break-all; }
    .empty { border:1px dashed rgba(148,163,184,.25); border-radius:12px; padding:20px; color:#94a3b8; }
    a { color:#93c5fd; }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Node-RED 电流原始采集</h1>
      <div class="meta">${meta}<br>只显示采集器原始 16 路数据，不带中控备注、排序和组合。</div>
    </div>
    <div class="badge">${latest ? 'ONLINE' : 'WAITING'}</div>
  </header>
  <main>
    <div class="grid">${body}</div>
    <div class="log">
      <div>TX: ${escapeHtml(tx)}</div>
      <div>RX: ${escapeHtml(rx)}</div>
      <div>JSON: <a href="/current/raw.json">/current/raw.json</a></div>
    </div>
  </main>
</body>
</html>`;
return msg;
"""


def build_flow() -> list[dict]:
    return [
        {
            "id": "tab_current_collector_push",
            "type": "tab",
            "label": "Current Collector Push",
            "disabled": False,
            "info": "Read 16-channel current collector from node-121 and push data to Smart Center node-120.",
        },
        {
            "id": "cc_comment",
            "type": "comment",
            "z": "tab_current_collector_push",
            "name": "16路电流采集：121读取，主动上报120",
            "info": "Default: 192.168.50.109:502 -> http://192.168.50.120:6899/api/current-collector/push",
            "x": 260,
            "y": 40,
            "wires": [],
        },
        {
            "id": "cc_inject_poll",
            "type": "inject",
            "z": "tab_current_collector_push",
            "name": "每5秒采集并上报",
            "props": [{"p": "payload"}],
            "repeat": "5",
            "crontab": "",
            "once": True,
            "onceDelay": "1",
            "topic": "",
            "payload": "",
            "payloadType": "date",
            "x": 180,
            "y": 100,
            "wires": [["cc_read_and_push"]],
        },
        {
            "id": "cc_read_and_push",
            "type": "function",
            "z": "tab_current_collector_push",
            "name": "读取采集器并推送120",
            "func": FUNCTION_CODE.strip(),
            "outputs": 2,
            "timeout": 0,
            "noerr": 0,
            "initialize": "",
            "finalize": "",
            "libs": [],
            "x": 430,
            "y": 100,
            "wires": [["cc_http_push"], ["cc_debug_error"]],
        },
        {
            "id": "cc_http_push",
            "type": "http request",
            "z": "tab_current_collector_push",
            "name": "POST 到 120 中控",
            "method": "use",
            "ret": "obj",
            "paytoqs": "ignore",
            "url": "",
            "tls": "",
            "persist": False,
            "proxy": "",
            "insecureHTTPParser": False,
            "authType": "",
            "senderr": False,
            "headers": [],
            "x": 660,
            "y": 100,
            "wires": [["cc_debug_error"]],
        },
        {
            "id": "cc_debug_error",
            "type": "debug",
            "z": "tab_current_collector_push",
            "name": "current push result",
            "active": False,
            "tosidebar": True,
            "console": False,
            "tostatus": False,
            "complete": "payload",
            "targetType": "msg",
            "statusVal": "",
            "statusType": "auto",
            "x": 900,
            "y": 100,
            "wires": [],
        },
        {
            "id": "cc_raw_page_http",
            "type": "http in",
            "z": "tab_current_collector_push",
            "name": "实时原始数据页面",
            "url": "/current/raw",
            "method": "get",
            "upload": False,
            "swaggerDoc": "",
            "x": 180,
            "y": 180,
            "wires": [["cc_raw_page_renderer"]],
        },
        {
            "id": "cc_raw_page_renderer",
            "type": "function",
            "z": "tab_current_collector_push",
            "name": "渲染原始16路页面",
            "func": RAW_PAGE_CODE.strip(),
            "outputs": 1,
            "timeout": 0,
            "noerr": 0,
            "initialize": "",
            "finalize": "",
            "libs": [],
            "x": 430,
            "y": 180,
            "wires": [["cc_raw_page_response"]],
        },
        {
            "id": "cc_raw_page_response",
            "type": "http response",
            "z": "tab_current_collector_push",
            "name": "返回实时页面",
            "statusCode": "",
            "headers": {},
            "x": 670,
            "y": 180,
            "wires": [],
        },
        {
            "id": "cc_raw_json_http",
            "type": "http in",
            "z": "tab_current_collector_push",
            "name": "实时原始数据 JSON",
            "url": "/current/raw.json",
            "method": "get",
            "upload": False,
            "swaggerDoc": "",
            "x": 180,
            "y": 240,
            "wires": [["cc_raw_json_renderer"]],
        },
        {
            "id": "cc_raw_json_renderer",
            "type": "function",
            "z": "tab_current_collector_push",
            "name": "返回原始16路 JSON",
            "func": RAW_JSON_CODE.strip(),
            "outputs": 1,
            "timeout": 0,
            "noerr": 0,
            "initialize": "",
            "finalize": "",
            "libs": [],
            "x": 430,
            "y": 240,
            "wires": [["cc_raw_json_response"]],
        },
        {
            "id": "cc_raw_json_response",
            "type": "http response",
            "z": "tab_current_collector_push",
            "name": "返回 JSON",
            "statusCode": "",
            "headers": {},
            "x": 660,
            "y": 240,
            "wires": [],
        },
    ]


def main() -> None:
    if not FLOW_FILE.exists():
        raise SystemExit(f"missing Node-RED flow file: {FLOW_FILE}")
    nodes = json.loads(FLOW_FILE.read_text(encoding="utf-8"))
    if not isinstance(nodes, list):
        raise SystemExit("flows.json is not a list")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = FLOW_FILE.with_name(f"flows.json.backup-current-collector-{stamp}")
    backup.write_text(json.dumps(nodes, ensure_ascii=False, indent=2), encoding="utf-8")
    cleaned = [node for node in nodes if str(node.get("id") or "") not in FLOW_IDS]
    cleaned.extend(build_flow())
    FLOW_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"backup={backup}")
    print(f"installed_nodes={len(FLOW_IDS)}")
    print("restart with: sudo systemctl restart node-red.service")


if __name__ == "__main__":
    main()
