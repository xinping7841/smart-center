"""Local-model translator for natural-language control text.

AI_MODULE: control_model_translator
AI_PURPOSE: Ask a local LLM to rewrite fuzzy user control text into a structured,
standard Smart Center control phrase that deterministic routing can validate.
AI_BOUNDARY: The model may propose intent and rewritten text only. It must never
emit executable HTTP paths, secrets, or bypass confirmation policy.
AI_DATA_FLOW: user text + compact device catalog -> LLM JSON -> deterministic
control resolver.
AI_RISK: Medium. Model output is treated as untrusted and must be validated by
the normal control router.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class ControlTranslation:
    rewritten_text: str
    module: str
    confidence: float
    reason: str


class LocalModelControlTranslator:
    def __init__(self, base_url: str, model: str, timeout_sec: float = 8.0) -> None:
        self.base_url = (base_url or "http://127.0.0.1:11434").rstrip("/")
        self.model = model or "qwen3:14b"
        self.timeout_sec = max(1.0, min(float(timeout_sec or 8.0), 60.0))

    def translate(self, text: str, alias_rows: list[dict[str, Any]]) -> ControlTranslation | None:
        raw = str(text or "").strip()
        if not raw:
            return None
        prompt = self._build_prompt(raw, alias_rows)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "think": False,
            "options": {"temperature": 0},
        }
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout_sec,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
            parsed = json.loads(str(data.get("response") or "").strip())
        except Exception:
            return None
        if not isinstance(parsed, dict):
            return None
        rewritten = str(parsed.get("rewritten_text") or "").strip()
        module = str(parsed.get("module") or "").strip().lower()
        reason = str(parsed.get("reason") or "").strip()
        try:
            confidence = float(parsed.get("confidence"))
        except Exception:
            confidence = 0.0
        allowed_modules = {"power", "sequencer", "light", "node_red", "door", "hvac", "projector", "server", "unknown"}
        if module not in allowed_modules:
            module = "unknown"
        if not rewritten or confidence < 0.55:
            return None
        if any(token in rewritten.lower() for token in ("http://", "https://", "/api/", "curl ", "requests.")):
            return None
        return ControlTranslation(
            rewritten_text=rewritten[:120],
            module=module,
            confidence=max(0.0, min(confidence, 1.0)),
            reason=reason[:160],
        )

    def _build_prompt(self, text: str, alias_rows: list[dict[str, Any]]) -> str:
        catalog = self._catalog_text(alias_rows)
        return (
            "你是深澜中控的自然语言控制转译器。只输出 JSON，不要解释。\n"
            "你的任务是把用户口语改写成中控能安全解析的标准说法，不允许输出 HTTP API、代码、密钥或执行参数。\n"
            "强电柜、时序电源、服务器关机/重启、目标不确定时仍然只输出改写建议，真实执行由后端二次确认。\n"
            "如果无法确定目标，module=unknown，rewritten_text 为空。\n"
            "输出格式：{\"module\":\"power|sequencer|light|node_red|door|hvac|projector|server|unknown\",\"rewritten_text\":\"标准中文控制句\",\"confidence\":0.0到1.0,\"reason\":\"简短理由\"}\n"
            "可控设备摘要：\n"
            f"{catalog}\n"
            f"用户原话：{text}"
        )

    def _catalog_text(self, alias_rows: list[dict[str, Any]]) -> str:
        rows: list[str] = []
        for row in alias_rows:
            if not row.get("control_capability"):
                continue
            module = str(row.get("module") or "")
            device_type = str(row.get("device_type") or "")
            if module not in {"power", "sequencer", "light", "hvac", "projector", "door"}:
                continue
            aliases = [str(x) for x in (row.get("aliases") or [])[:8] if x]
            rows.append(f"- module={module}; type={device_type}; name={row.get('name')}; aliases={','.join(aliases)}")
            if len(rows) >= 90:
                break
        rows.append("- module=node_red; type=gateway_light; name=庭院灯; aliases=庭院灯,户外灯,室外灯,院子灯,院子里的灯")
        rows.append("- module=server; type=server; name=服务器; aliases=服务器,主机,机器,电脑,IP地址,门口LED服务器")
        return "\n".join(rows)
