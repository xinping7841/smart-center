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

DEFAULT_LOCAL_MODEL_BASE_URL = "http://127.0.0.1:8001/v1"


@dataclass(frozen=True)
class ControlTranslation:
    rewritten_text: str
    module: str
    confidence: float
    reason: str


def normalize_openai_base_url(base_url: str) -> str:
    value = str(base_url or DEFAULT_LOCAL_MODEL_BASE_URL).strip().rstrip("/")
    for suffix in ("/chat/completions", "/models"):
        if value.endswith(suffix):
            value = value[: -len(suffix)].rstrip("/")
    if not value:
        value = DEFAULT_LOCAL_MODEL_BASE_URL
    if not value.endswith(("/v1", "/api/v3")):
        value = f"{value}/v1"
    return value


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(raw[index:])
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def request_local_model_json(
    base_url: str,
    model: str,
    prompt: str,
    timeout_sec: float,
    *,
    max_tokens: int = 512,
    api_key: str = "",
) -> dict[str, Any] | None:
    endpoint = f"{normalize_openai_base_url(base_url)}/chat/completions"
    payload = {
        "model": model or "qwen3:14b",
        "messages": [
            {"role": "system", "content": "你只输出一个 JSON 对象，不输出解释、Markdown 或额外文本。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": max(64, min(int(max_tokens or 512), 2048)),
        "stream": False,
    }
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = requests.post(
        endpoint,
        json=payload,
        timeout=max(1.0, min(float(timeout_sec or 8.0), 60.0)),
        headers=headers,
    )
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices") if isinstance(data, dict) else []
    content = ""
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            content = str(message.get("content") or "")
        if not content:
            content = str(choices[0].get("text") or "")
    return _extract_json_object(content)


class LocalModelControlTranslator:
    def __init__(self, base_url: str, model: str, timeout_sec: float = 8.0, *, api_key: str = "", label: str = "") -> None:
        self.base_url = normalize_openai_base_url(base_url)
        self.model = model or "qwen3:14b"
        self.timeout_sec = max(1.0, min(float(timeout_sec or 8.0), 60.0))
        self.api_key = str(api_key or "").strip()
        self.label = str(label or self.model or "model").strip()

    def translate(self, text: str, alias_rows: list[dict[str, Any]]) -> ControlTranslation | None:
        raw = str(text or "").strip()
        if not raw:
            return None
        prompt = self._build_prompt(raw, alias_rows)
        try:
            parsed = request_local_model_json(self.base_url, self.model, prompt, self.timeout_sec, api_key=self.api_key)
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
        if self.label:
            reason = f"{self.label}: {reason}" if reason else self.label
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


class ChainedModelControlTranslator:
    def __init__(self, translators: list[LocalModelControlTranslator]) -> None:
        self.translators = [item for item in translators if item]
        self.labels = [item.label for item in self.translators if item.label]

    def translate(self, text: str, alias_rows: list[dict[str, Any]]) -> ControlTranslation | None:
        for translator in self.translators:
            result = translator.translate(text, alias_rows)
            if result:
                return result
        return None
