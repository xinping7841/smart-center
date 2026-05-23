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
}


FUNCTION_CODE = r"""
const net = global.get('net');

const collectorHost = env.get('CURRENT_COLLECTOR_HOST') || '192.168.50.109';
const collectorPort = Number(env.get('CURRENT_COLLECTOR_PORT') || 502);
const smartCenterUrl = env.get('SMART_CENTER_CURRENT_PUSH_URL') || 'http://192.168.50.120:6899/api/current-collector/push';
const token = env.get('SMART_CENTER_CURRENT_PUSH_TOKEN') || '';
const slave = Number(env.get('CURRENT_COLLECTOR_SLAVE') || 1);
const startRegister = Number(env.get('CURRENT_COLLECTOR_REGISTER') || 0);
const count = Number(env.get('CURRENT_COLLECTOR_COUNT') || 16);
const scale = Number(env.get('CURRENT_COLLECTOR_SCALE') || 100);
const multiplier = Number(env.get('CURRENT_COLLECTOR_MULTIPLIER') || 1);
const timeoutMs = Number(env.get('CURRENT_COLLECTOR_TIMEOUT_MS') || 1800);

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

function parseResponse(buffer) {
    const expectedLength = 5 + count * 2;
    if (!Buffer.isBuffer(buffer) || buffer.length < expectedLength) {
        throw new Error(`short response ${buffer ? buffer.length : 0}/${expectedLength}: ${toHex(buffer)}`);
    }
    const frame = buffer.subarray(0, expectedLength);
    const expectedCrc = crc16Modbus(frame.subarray(0, -2));
    const actualCrc = frame[frame.length - 2] | (frame[frame.length - 1] << 8);
    if (expectedCrc !== actualCrc) throw new Error(`bad crc expected=${expectedCrc.toString(16)} actual=${actualCrc.toString(16)} frame=${toHex(frame)}`);
    if (frame[0] !== slave || frame[1] !== 0x03 || frame[2] !== count * 2) throw new Error(`unexpected frame: ${toHex(frame)}`);
    const raw = [];
    for (let offset = 3; offset < 3 + count * 2; offset += 2) raw.push(frame.readUInt16BE(offset));
    const currents = raw.map((value) => Number(((value / scale) * multiplier).toFixed(3)));
    return { frame, raw, currents };
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
                settled = true;
                clearTimeout(timer);
                socket.end();
                try {
                    const parsed = parseResponse(merged);
                    resolve({ request, ...parsed });
                } catch (err) {
                    reject(err);
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

(async () => {
    const read = await readCollector();
    const payload = {
        source: 'node-red',
        gateway: 'node-121',
        slave,
        register_base: `0x${startRegister.toString(16).padStart(4, '0').toUpperCase()}`,
        scale,
        multiplier,
        raw_registers: read.raw,
        currents: read.currents,
        request_hex: toHex(read.request),
        response_hex: toHex(read.frame),
        collected_at: new Date().toISOString(),
    };
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
});
return;
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
            "name": "每2秒采集并上报",
            "props": [{"p": "payload"}],
            "repeat": "2",
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
