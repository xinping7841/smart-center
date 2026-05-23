import argparse
import json
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "deploy" / "node_red_driver_pack"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _make_id(prefix: str, index: int) -> str:
    return f"{prefix}_{index:04d}_{int(time.time())}"


def build_flow(base_url: str) -> list:
    tab_id = _make_id("tab", 1)
    inject_id = _make_id("inject", 1)
    http_req_id = _make_id("http", 1)
    json_id = _make_id("json", 1)
    function_id = _make_id("fn", 1)
    debug_id = _make_id("debug", 1)
    ui_group_id = _make_id("ui_group", 1)
    ui_tab_id = _make_id("ui_tab", 1)
    ui_text_id = _make_id("ui_text", 1)

    return [
        {
            "id": tab_id,
            "type": "tab",
            "label": "Driver Hub Bridge",
            "disabled": False,
            "info": "Poll Smart Power Monitor driver snapshot and expose for Node-RED UI and logic.",
        },
        {
            "id": inject_id,
            "type": "inject",
            "z": tab_id,
            "name": "poll every 5s",
            "props": [{"p": "payload"}, {"p": "topic", "vt": "str"}],
            "repeat": "5",
            "crontab": "",
            "once": True,
            "onceDelay": "1",
            "topic": "",
            "payload": "",
            "payloadType": "date",
            "x": 190,
            "y": 100,
            "wires": [[http_req_id]],
        },
        {
            "id": http_req_id,
            "type": "http request",
            "z": tab_id,
            "name": "get driver snapshot",
            "method": "GET",
            "ret": "txt",
            "paytoqs": "ignore",
            "url": f"{base_url.rstrip('/')}/api/driver_hub/snapshot",
            "tls": "",
            "persist": False,
            "proxy": "",
            "authType": "",
            "senderr": False,
            "headers": [],
            "x": 450,
            "y": 100,
            "wires": [[json_id]],
        },
        {
            "id": json_id,
            "type": "json",
            "z": tab_id,
            "name": "parse json",
            "property": "payload",
            "action": "",
            "pretty": False,
            "x": 640,
            "y": 100,
            "wires": [[function_id, debug_id, ui_text_id]],
        },
        {
            "id": function_id,
            "type": "function",
            "z": tab_id,
            "name": "summary",
            "func": (
                "const p = msg.payload || {};\n"
                "msg.topic = 'driver_hub_summary';\n"
                "msg.payload = {\n"
                "  total: p.total_drivers || 0,\n"
                "  online: p.online_drivers || 0,\n"
                "  offline: p.offline_drivers || 0,\n"
                "  generated_at: p.generated_at || ''\n"
                "};\n"
                "return msg;"
            ),
            "outputs": 1,
            "timeout": "",
            "noerr": 0,
            "initialize": "",
            "finalize": "",
            "libs": [],
            "x": 830,
            "y": 100,
            "wires": [[debug_id]],
        },
        {
            "id": debug_id,
            "type": "debug",
            "z": tab_id,
            "name": "snapshot out",
            "active": True,
            "tosidebar": True,
            "console": False,
            "tostatus": False,
            "complete": "payload",
            "targetType": "msg",
            "statusVal": "",
            "statusType": "auto",
            "x": 1050,
            "y": 100,
            "wires": [],
        },
        {
            "id": ui_tab_id,
            "type": "ui_tab",
            "name": "Drivers",
            "icon": "dashboard",
            "disabled": False,
            "hidden": False,
        },
        {
            "id": ui_group_id,
            "type": "ui_group",
            "name": "Driver Online",
            "tab": ui_tab_id,
            "order": 1,
            "disp": True,
            "width": "12",
            "collapse": False,
            "className": "",
        },
        {
            "id": ui_text_id,
            "type": "ui_text",
            "z": tab_id,
            "group": ui_group_id,
            "order": 1,
            "width": 0,
            "height": 0,
            "name": "online stats",
            "label": "Driver status",
            "format": "{{msg.payload.online}} / {{msg.payload.total}} online",
            "layout": "row-spread",
            "className": "",
            "style": False,
            "font": "",
            "fontSize": 16,
            "color": "#4ade80",
            "x": 850,
            "y": 180,
            "wires": [],
        },
    ]


def build_readme(base_url: str) -> str:
    return (
        "# Node-RED Driver Pack\n\n"
        "This folder is generated by script. It helps import current driver data into Node-RED.\n\n"
        "## Files\n"
        "- `flows_driver_hub.json`: import this flow in Node-RED\n"
        "- `drivers_manifest.json`: current driver inventory\n"
        "- `snapshot_example.json`: current real-time snapshot sample\n\n"
        "## Import\n"
        "1. Open Node-RED editor.\n"
        "2. Menu -> Import -> choose `flows_driver_hub.json`.\n"
        "3. Deploy.\n"
        "4. If your backend URL is different, edit node `get driver snapshot` to:\n"
        f"   `{base_url.rstrip('/')}/api/driver_hub/snapshot`\n\n"
        "## Notes\n"
        "- Data source is `/api/driver_hub/snapshot` from this project.\n"
        "- UI page for same data: `/driver_hub`.\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Node-RED driver import pack.")
    parser.add_argument("--base-url", default="http://127.0.0.1:6899")
    args = parser.parse_args()

    from runtime.driver_hub import build_manifest, collect_snapshot

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    flow = build_flow(args.base_url)
    (OUTPUT_DIR / "flows_driver_hub.json").write_text(
        json.dumps(flow, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "drivers_manifest.json").write_text(
        json.dumps(build_manifest(include_disabled=True), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "snapshot_example.json").write_text(
        json.dumps(collect_snapshot(include_disabled=False), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "README.md").write_text(build_readme(args.base_url), encoding="utf-8")

    print(str(OUTPUT_DIR))


if __name__ == "__main__":
    main()
