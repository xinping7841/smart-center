#!/usr/bin/env python3
"""Ask the local model to refresh a Smart Center system summary.

AI_MODULE: local_model_system_summary_refresh
AI_PURPOSE: Use exported system/code knowledge to produce a high-context model summary without executing any Smart Center control API.
AI_BOUNDARY: Read training/local_model JSON/JSONL files and call the OpenAI-compatible chat endpoint only; never calls device-control endpoints.
AI_RISK: Medium, model output influences future operator understanding, so source files are structured and the result is saved as reviewable JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.local_model import normalize_local_model_config  # noqa: E402
from config import CONFIG  # noqa: E402
from paths import DATA_DIR, ensure_directory  # noqa: E402


DEFAULT_MAX_INPUT_CHARS = 20_000


def _training_dir() -> Path:
    return ensure_directory(DATA_DIR / "training" / "local_model")


def _latest_file(prefix: str, suffix: str = "") -> Path | None:
    files = sorted(
        [path for path in _training_dir().glob(f"{prefix}_*{suffix}") if path.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def _read_text(path: Path | None, limit: int = 60_000) -> str:
    if not path or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:limit]


def _jsonl_sample(path: Path | None, *, rows: int = 24, max_chars: int = 70_000) -> str:
    if not path or not path.is_file():
        return ""
    output: list[str] = []
    used = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for index, line in enumerate(handle):
            if index >= rows:
                break
            line = line.strip()
            if not line:
                continue
            if used + len(line) > max_chars:
                break
            output.append(line)
            used += len(line)
    return "\n".join(output)


def _build_prompt(max_input_chars: int) -> tuple[str, dict[str, str]]:
    sources = {
        "system_map": str(_latest_file("system_map", ".json") or ""),
        "code_system_map": str(_latest_file("code_system_map", ".json") or ""),
        "device_inventory": str(_latest_file("device_inventory", ".jsonl") or ""),
        "control_capabilities": str(_latest_file("control_capabilities", ".jsonl") or ""),
        "nl_intent_examples": str(_latest_file("nl_intent_examples", ".jsonl") or ""),
        "module_cards": str(_latest_file("module_cards", ".jsonl") or ""),
        "code_knowledge": str(_latest_file("code_knowledge", ".jsonl") or ""),
        "full_code_context": str(_latest_file("full_code_context", ".jsonl") or ""),
    }
    parts = [
        "你正在为 Smart Center 演播中控生成可审阅的系统理解摘要。",
        "只允许总结、归纳、指出风险和改进建议；不要输出任何可直接执行真实设备控制的 HTTP 调用或 payload。",
        "重点覆盖：模块边界、设备情况、查询能力、控制能力、安全链路、飞书自然语言处理、后续修改索引。",
        "\n[system_map]\n" + _read_text(Path(sources["system_map"]) if sources["system_map"] else None, 80_000),
        "\n[code_system_map]\n" + _read_text(Path(sources["code_system_map"]) if sources["code_system_map"] else None, 80_000),
        "\n[device_inventory_sample]\n" + _jsonl_sample(Path(sources["device_inventory"]) if sources["device_inventory"] else None, rows=60),
        "\n[control_capabilities_sample]\n" + _jsonl_sample(Path(sources["control_capabilities"]) if sources["control_capabilities"] else None, rows=80),
        "\n[nl_intent_examples_sample]\n" + _jsonl_sample(Path(sources["nl_intent_examples"]) if sources["nl_intent_examples"] else None, rows=80),
        "\n[module_cards_sample]\n" + _jsonl_sample(Path(sources["module_cards"]) if sources["module_cards"] else None, rows=80),
        "\n[code_knowledge_sample]\n" + _jsonl_sample(Path(sources["code_knowledge"]) if sources["code_knowledge"] else None, rows=40),
        "\n[full_code_context_sample]\n" + _jsonl_sample(Path(sources["full_code_context"]) if sources["full_code_context"] else None, rows=24),
        (
            "\n请输出 JSON，字段包括：overview、module_map、device_map、query_capabilities、"
            "control_capabilities、feishu_nl_flow、safety_boundaries、maintenance_index、open_questions。"
        ),
    ]
    prompt = "\n".join(part for part in parts if part.strip())
    return prompt[:max_input_chars], sources


def _request_chat(cfg: dict[str, Any], prompt: str) -> dict[str, Any]:
    payload = {
        "model": cfg["model"],
        "messages": [
            {
                "role": "system",
                "content": "你是 Smart Center 本地知识整理助手。你只能总结和生成维护知识，不允许执行或建议绕过控制安全链路。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": min(float(cfg.get("temperature", 0.2)), 0.3),
        "max_tokens": min(int(cfg.get("max_tokens", 2048) or 2048), 4096),
        "stream": False,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if cfg.get("api_key"):
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    started = time.time()
    req = urllib.request.Request(f"{cfg['base_url'].rstrip('/')}/chat/completions", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=float(cfg.get("timeout_sec", 120))) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    answer = ""
    choices = data.get("choices") if isinstance(data, dict) else []
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") if isinstance(choices[0].get("message"), dict) else {}
        answer = str(message.get("content") or choices[0].get("text") or "")
    return {"elapsed_ms": int((time.time() - started) * 1000), "answer": answer, "raw": data}


def build_system_summary(max_input_chars: int = DEFAULT_MAX_INPUT_CHARS) -> dict[str, Any]:
    cfg = normalize_local_model_config(CONFIG.get("local_model"))
    prompt, sources = _build_prompt(max_input_chars)
    result = _request_chat(cfg, prompt)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "schema": "smart_center.local_model_system_summary.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model": cfg.get("model"),
        "base_url": cfg.get("base_url"),
        "max_model_len": cfg.get("max_model_len"),
        "prompt_chars": len(prompt),
        "elapsed_ms": result.get("elapsed_ms"),
        "sources": sources,
        "summary": result.get("answer") or "",
        "safety_boundary": "该摘要只用于维护和 RAG；真实设备控制仍必须走 Smart Center 权限、审计和确认链路。",
    }
    out_path = _training_dir() / f"system_summary_{stamp}.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    output["file"] = str(out_path)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh Smart Center system summary with the local high-context model.")
    parser.add_argument("--max-input-chars", type=int, default=DEFAULT_MAX_INPUT_CHARS)
    args = parser.parse_args()
    result = build_system_summary(max_input_chars=max(8_000, min(args.max_input_chars, 240_000)))
    print(json.dumps({"ok": True, "summary": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
