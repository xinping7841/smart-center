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
import os
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Any

import requests

DEFAULT_LOCAL_MODEL_BASE_URL = "http://127.0.0.1:8001/v1"


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        return max(minimum, min(float(os.environ.get(name, "") or default), maximum))
    except Exception:
        return default


def _priority_sources(priority: str) -> tuple[str, str]:
    return ("cloud", "local") if str(priority or "") == "cloud_first" else ("local", "cloud")


@dataclass(frozen=True)
class ControlTranslation:
    rewritten_text: str
    module: str
    confidence: float
    reason: str
    source: str = ""
    model: str = ""
    elapsed_ms: int = 0
    comparison: dict[str, Any] | None = None


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
        timeout=max(1.0, min(float(timeout_sec or 8.0), 600.0)),
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
    def __init__(self, base_url: str, model: str, timeout_sec: float = 8.0, *, api_key: str = "", label: str = "", source: str = "local") -> None:
        self.base_url = normalize_openai_base_url(base_url)
        self.model = model or "qwen3:14b"
        self.timeout_sec = max(1.0, min(float(timeout_sec or 8.0), 600.0))
        self.api_key = str(api_key or "").strip()
        self.label = str(label or self.model or "model").strip()
        self.source = str(source or "local").strip() or "local"

    def translate(self, text: str, alias_rows: list[dict[str, Any]]) -> ControlTranslation | None:
        translation, _ = self.translate_with_report(text, alias_rows)
        return translation

    def translate_with_report(self, text: str, alias_rows: list[dict[str, Any]]) -> tuple[ControlTranslation | None, dict[str, Any]]:
        started = time.time()
        report: dict[str, Any] = {
            "source": self.source,
            "label": self.label,
            "model": self.model,
            "ok": False,
            "selected": False,
            "elapsed_ms": 0,
        }
        raw = str(text or "").strip()
        if not raw:
            report["error"] = "empty_text"
            return None, report
        prompt = self._build_prompt(raw, alias_rows)
        try:
            parsed = request_local_model_json(self.base_url, self.model, prompt, self.timeout_sec, api_key=self.api_key)
        except Exception as exc:
            report["elapsed_ms"] = int((time.time() - started) * 1000)
            report["error"] = str(exc)
            return None, report
        report["elapsed_ms"] = int((time.time() - started) * 1000)
        if not isinstance(parsed, dict):
            report["error"] = "no_json"
            return None, report
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
        report.update({
            "module": module,
            "rewritten_text": rewritten[:120],
            "confidence": max(0.0, min(confidence, 1.0)),
            "reason": reason[:160],
        })
        if not rewritten or confidence < 0.55:
            report["error"] = "low_confidence_or_empty"
            return None, report
        if any(token in rewritten.lower() for token in ("http://", "https://", "/api/", "curl ", "requests.")):
            report["error"] = "unsafe_text"
            return None, report
        if self.label:
            reason = f"{self.label}: {reason}" if reason else self.label
        report["ok"] = True
        return ControlTranslation(
            rewritten_text=rewritten[:120],
            module=module,
            confidence=max(0.0, min(confidence, 1.0)),
            reason=reason[:160],
            source=self.source,
            model=self.model,
            elapsed_ms=int(report.get("elapsed_ms") or 0),
        ), report

    def _provider_summary(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "label": self.label,
            "model": self.model,
            "timeout_sec": self.timeout_sec,
        }

    @staticmethod
    def build_comparison(
        *,
        reports: list[dict[str, Any]],
        selected: ControlTranslation | None,
        priority: str,
    ) -> dict[str, Any]:
        selected_source = str(selected.source or "") if selected else ""
        selected_rewrite = str(selected.rewritten_text or "") if selected else ""
        for report in reports:
            report["selected"] = bool(
                selected
                and str(report.get("source") or "") == selected_source
                and str(report.get("rewritten_text") or "") == selected_rewrite
            )
        valid = [row for row in reports if row.get("ok")]
        rewrites = {str(row.get("rewritten_text") or "") for row in valid if row.get("rewritten_text")}
        modules = {str(row.get("module") or "") for row in valid if row.get("module")}
        return {
            "schema": "smart_center.model_comparison.v1",
            "kind": "control_translate",
            "mode": "parallel" if len(reports) > 1 else "single",
            "priority": priority,
            "selected_source": selected_source,
            "selected_label": next((str(row.get("label") or "") for row in reports if row.get("selected")), ""),
            "selected_rewritten_text": selected_rewrite,
            "results": reports,
            "difference": {
                "rewrite_match": len(rewrites) <= 1,
                "module_match": len(modules) <= 1,
            },
        }

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
    def __init__(self, translators: list[LocalModelControlTranslator], *, priority: str = "cloud_first") -> None:
        self.translators = [item for item in translators if item]
        self.labels = [item.label for item in self.translators if item.label]
        self.priority = str(priority or "cloud_first").strip() or "cloud_first"
        self.primary_wait_sec = _env_float("SMART_CENTER_NLU_PRIMARY_WAIT_SEC", 18.0, 1.0, 120.0)
        self.compare_wait_sec = _env_float("SMART_CENTER_NLU_COMPARE_WAIT_SEC", 2.0, 0.0, 30.0)

    def translate(self, text: str, alias_rows: list[dict[str, Any]]) -> ControlTranslation | None:
        translation, _ = self.translate_with_report(text, alias_rows)
        return translation

    def translate_with_report(self, text: str, alias_rows: list[dict[str, Any]]) -> tuple[ControlTranslation | None, dict[str, Any]]:
        if not self.translators:
            return None, LocalModelControlTranslator.build_comparison(reports=[], selected=None, priority=self.priority)
        if len(self.translators) == 1:
            translation, report = self.translators[0].translate_with_report(text, alias_rows)
            comparison = LocalModelControlTranslator.build_comparison(reports=[report], selected=translation, priority=self.priority)
            if translation:
                translation = ControlTranslation(
                    rewritten_text=translation.rewritten_text,
                    module=translation.module,
                    confidence=translation.confidence,
                    reason=translation.reason,
                    source=translation.source,
                    model=translation.model,
                    elapsed_ms=translation.elapsed_ms,
                    comparison=comparison,
                )
            return translation, comparison

        started = time.time()
        translations: list[ControlTranslation] = []
        reports_by_source: dict[str, dict[str, Any]] = {}
        executor = ThreadPoolExecutor(max_workers=len(self.translators))
        futures: dict[Future, LocalModelControlTranslator] = {
            executor.submit(item.translate_with_report, text, alias_rows): item for item in self.translators
        }

        def collect(done_futures: set[Future]) -> None:
            for future in done_futures:
                translator = futures[future]
                try:
                    translation, report = future.result()
                except Exception as exc:
                    report = {
                        **translator._provider_summary(),
                        "ok": False,
                        "selected": False,
                        "elapsed_ms": int((time.time() - started) * 1000),
                        "error": str(exc),
                    }
                    translation = None
                reports_by_source[translator.source] = report
                if translation:
                    translations.append(translation)

        pending: set[Future] = set(futures)
        preferred = _priority_sources(self.priority)[0]
        preferred_exists = any(item.source == preferred for item in self.translators)
        deadline = time.time() + self.primary_wait_sec
        while pending and time.time() < deadline:
            done_now, pending = wait(
                pending,
                timeout=max(0.05, deadline - time.time()),
                return_when=FIRST_COMPLETED,
            )
            if not done_now:
                break
            collect(set(done_now))
            selected_now = self._select_translation(translations)
            if selected_now and (selected_now.source == preferred or not preferred_exists):
                break
            preferred_report = reports_by_source.get(preferred)
            if selected_now and preferred_report and not preferred_report.get("ok"):
                break

        if pending and self.compare_wait_sec > 0:
            done_now, pending = wait(pending, timeout=self.compare_wait_sec)
            collect(set(done_now))

        for future in list(pending):
            translator = futures[future]
            reports_by_source[translator.source] = {
                **translator._provider_summary(),
                "ok": False,
                "selected": False,
                "elapsed_ms": int((time.time() - started) * 1000),
                "error": "pending_after_fast_selection",
            }
        executor.shutdown(wait=False, cancel_futures=True)

        reports: list[dict[str, Any]] = []
        for translator in self.translators:
            report = reports_by_source.get(translator.source)
            if report:
                reports.append(report)
        selected = self._select_translation(translations)
        comparison = LocalModelControlTranslator.build_comparison(reports=reports, selected=selected, priority=self.priority)
        if selected:
            selected = ControlTranslation(
                rewritten_text=selected.rewritten_text,
                module=selected.module,
                confidence=selected.confidence,
                reason=selected.reason,
                source=selected.source,
                model=selected.model,
                elapsed_ms=selected.elapsed_ms,
                comparison=comparison,
            )
        return selected, comparison

    def _select_translation(self, translations: list[ControlTranslation]) -> ControlTranslation | None:
        if not translations:
            return None
        priority_sources = ("cloud", "local") if self.priority == "cloud_first" else ("local", "cloud")
        by_source = {item.source: item for item in translations}
        for source in priority_sources:
            if source in by_source:
                return by_source[source]
        return max(translations, key=lambda item: item.confidence)
