#!/usr/bin/env python3
"""Apply compact runtime and code knowledge to node-123 local-model prompt.

AI_MODULE: remote_apply_node123_device_code_context
AI_PURPOSE: Combine latest device knowledge, code index, module cards, and AI marker policy into local_model.system_prompt.
AI_BOUNDARY: Edits config.json only; never calls Smart Center control APIs or device drivers.
AI_RUNTIME: Run via scripts/ssh_exec.sh on node-120 with sudo -n for /srv/smart-center-data/config.json.
AI_RISK: Medium. Prompt must stay compact enough for the 8K context model while keeping safety boundaries explicit.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


CONFIG_PATH = Path(os.environ.get("SMART_CENTER_CONFIG_FILE", "/srv/smart-center-data/config.json"))
DATA_DIR = Path(os.environ.get("SMART_CENTER_DATA_DIR", "/srv/smart-center-data"))
TRAINING_DIR = DATA_DIR / "training" / "local_model"
MAX_PROMPT_CHARS = int(os.environ.get("SMART_CENTER_COMPACT_KNOWLEDGE_PROMPT_CHARS", "10500") or 10500)


def reexec_with_sudo_if_needed() -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return
    os.execvp("sudo", ["sudo", "-n", sys.executable, *sys.argv])


def latest(prefix: str, suffix: str) -> Path | None:
    rows = sorted(TRAINING_DIR.glob(f"{prefix}_*{suffix}"), key=lambda p: p.stat().st_mtime, reverse=True)
    return rows[0] if rows else None


def read_json(path: Path | None) -> dict:
    if not path or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def read_jsonl(path: Path | None, limit: int = 10000) -> list[dict]:
    if not path or not path.is_file():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if len(rows) >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def compact(value: object, limit: int = 100) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text[:limit]


def selected_devices(rows: list[dict]) -> list[str]:
    preferred = {"server_machines", "hvac_devices", "env_sensors", "cabinets", "sequencers", "projectors", "snmp_devices", "ups_devices"}
    sections: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        section = str(row.get("source_section") or "").strip() or "unknown"
        if section not in preferred:
            continue
        name = compact(row.get("name") or row.get("device_id"), 34)
        device_id = compact(row.get("device_id"), 36)
        host = compact(row.get("host"), 18)
        aliases = row.get("aliases") if isinstance(row.get("aliases"), list) else []
        alias_text = f" 别名:{'/'.join(compact(x, 12) for x in aliases[:3])}" if aliases else ""
        item = f"{name}({device_id})"
        if host:
            item += f" @{host}"
        item += alias_text
        sections[section].append(item)
    lines: list[str] = []
    for section in ["server_machines", "hvac_devices", "env_sensors", "cabinets", "sequencers", "projectors", "snmp_devices", "ups_devices"]:
        items = sections.get(section) or []
        shown = items[:8]
        more = f"；另{len(items)-len(shown)}项" if len(items) > len(shown) else ""
        if shown:
            lines.append(f"- {section}({len(items)}): " + "；".join(shown) + more)
    return lines


def selected_code_modules(module_cards: list[dict]) -> list[str]:
    wanted_tokens = [
        "hvac",
        "home_assistant",
        "miio",
        "env",
        "background",
        "dashboard",
        "local_model",
        "feishu",
        "server",
        "power",
        "snmp",
        "config",
        "viewport",
    ]
    rows: list[str] = []
    seen = set()
    for card in module_cards:
        haystack = " ".join(
            [
                str(card.get("module") or ""),
                str(card.get("purpose") or ""),
                " ".join(str(x) for x in (card.get("files") or [])),
                " ".join(str(x) for x in (card.get("search_keywords") or [])),
            ]
        ).lower()
        if not any(token in haystack for token in wanted_tokens):
            continue
        module = compact(card.get("module"), 42)
        files = [compact(x, 48) for x in (card.get("files") or [])[:5]]
        routes = [compact(x, 38) for x in (card.get("routes") or [])[:4]]
        purpose = compact(card.get("purpose"), 130)
        key = module or ",".join(files)
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(f"- {module}: {purpose} 文件:{', '.join(files)} 路由:{', '.join(routes)}")
        if len(rows) >= 26:
            break
    return rows


def build_prompt() -> tuple[str, dict]:
    files = {
        "system_map": latest("system_map", ".json"),
        "device_inventory": latest("device_inventory", ".jsonl"),
        "control_capabilities": latest("control_capabilities", ".jsonl"),
        "insights": latest("insights", ".jsonl"),
        "nl_intent_examples": latest("nl_intent_examples", ".jsonl"),
        "system_summary": latest("system_summary", ".json"),
        "code_system_map": latest("code_system_map", ".json"),
        "module_cards": latest("module_cards", ".jsonl"),
        "code_knowledge": latest("code_knowledge", ".jsonl"),
        "full_code_context": latest("full_code_context", ".jsonl"),
        "ai_marker_coverage": latest("ai_marker_coverage", ".json"),
    }
    system_map = read_json(files["system_map"])
    code_system_map = read_json(files["code_system_map"])
    summary = read_json(files["system_summary"])
    marker_coverage = read_json(files["ai_marker_coverage"])
    devices = read_jsonl(files["device_inventory"])
    capabilities = read_jsonl(files["control_capabilities"])
    module_cards = read_jsonl(files["module_cards"])

    control_counts = defaultdict(int)
    for row in capabilities:
        module = compact(row.get("module") or "unknown", 24)
        control_counts[module] += 1
    control_line = "；".join(f"{key}:{value}" for key, value in sorted(control_counts.items())[:18])

    code_counts = code_system_map.get("counts") if isinstance(code_system_map.get("counts"), dict) else {}
    runtime_counts = system_map.get("counts") if isinstance(system_map.get("counts"), dict) else {}
    marker_counts = marker_coverage.get("counts") if isinstance(marker_coverage.get("counts"), dict) else {}
    summary_text = compact(summary.get("summary"), 800)
    device_lines = selected_devices(devices)
    module_lines = selected_code_modules(module_cards)
    generated_at = datetime.now().isoformat(timespec="seconds")

    ha_chain = [
        "- HA/空调滞后优先查: api/hvac.py, hvac_core.py, services/home_assistant_bridge.py, services/miio_hvac.py, services/mqtt_env_bridge.py, static/js/views/hvac-view.js, static/js/views/hvac-summary.js, static/js/views/env.js, background.py, runtime/state.py, event_logger.py, config.py。",
        "- 判断顺序: 先看 HA/米家桥接连通和实体映射，再看后台轮询/缓存时间戳，再看 /api/hvac/status 和 /api/env/status 返回字段，最后看前端是否使用 stale/last_updated 展示。",
        "- 明天 121 从 16G 升到 32G 后，再验证 HA/桥接/轮询是否受资源瓶颈影响；123 当前 64G 负责本地模型。",
    ]

    prompt = f"""你是 Smart Center 演播中控的本地模型助手，运行在 123 服务器 Qwen/Qwen2.5-32B-Instruct-AWQ。
你已学习 120 中控的设备知识和代码知识索引。回答时优先给出具体模块、文件路径、接口和安全边界；信息不足时说明应查询只读 API 或最新知识文件。
绝对安全边界：模型只能做理解、查询、摘要、排障建议和受控控制意图解析；真实设备控制必须回到 Smart Center 后端权限、操作锁、审计、确认和状态回读链路。不要输出绕过后端的控制 HTTP 调用或脚本。强电、时序电源、UPS、服务器关机/重启、不确定目标必须二次确认。

[现场总览]
生成时间: {generated_at}
运行知识计数: {json.dumps(runtime_counts, ensure_ascii=False)}
代码知识计数: {json.dumps(code_counts, ensure_ascii=False)}
AI 标注覆盖: {json.dumps(marker_counts, ensure_ascii=False)}
控制能力计数: {control_line}
系统摘要: {summary_text}

[关键设备索引]
{chr(10).join(device_lines)}

[关键代码索引]
{chr(10).join(module_lines)}

[HA/空调信息滞后排查索引]
{chr(10).join(ha_chain)}

[代码学习长期规则]
- 以后 Smart Center 任意代码修改，都要同步维护触碰文件的 AI_* 标注。
- 核心文件至少保持 AI_MODULE、AI_PURPOSE、AI_BOUNDARY、AI_RISK；职责/数据流/运行方式/兼容字段变化时同步更新 AI_DATA_FLOW、AI_RUNTIME、AI_COMPAT、AI_SEARCH_KEYWORDS。
- 最新代码知识文件包括 code_system_map、module_cards、code_knowledge、full_code_context、ai_marker_coverage。需要具体源码时先按 module_cards/code_knowledge 检索，再读取 full_code_context 片段。
"""
    if len(prompt) > MAX_PROMPT_CHARS:
        prompt = prompt[:MAX_PROMPT_CHARS].rstrip() + "\n[提示] 代码/设备知识已截断，只保留高优先级索引。"
    meta = {key: str(value or "") for key, value in files.items()}
    meta.update(
        {
            "device_count": len(devices),
            "capability_count": len(capabilities),
            "module_card_count": len(module_cards),
            "prompt_chars": len(prompt),
            "marker_required_missing": marker_counts.get("required_target_missing_required"),
        }
    )
    return prompt, meta


def main() -> int:
    reexec_with_sudo_if_needed()
    prompt, meta = build_prompt()
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    local_model = payload.setdefault("local_model", {})
    if not isinstance(local_model, dict):
        raise SystemExit("local_model is not an object")
    old_prompt = str(local_model.get("system_prompt") or "")
    local_model["system_prompt"] = prompt
    local_model["knowledge_context"] = {
        "enabled": True,
        "kind": "device_and_code_context",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        **meta,
    }
    changed = old_prompt != prompt
    backup = ""
    if changed:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = CONFIG_PATH.with_name(f"{CONFIG_PATH.name}.pre-node123-device-code-context-{stamp}")
        shutil.copy2(CONFIG_PATH, backup_path)
        tmp_path = CONFIG_PATH.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(CONFIG_PATH)
        backup = str(backup_path)
    print(json.dumps({"ok": True, "changed": changed, "backup": backup, "meta": meta}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
