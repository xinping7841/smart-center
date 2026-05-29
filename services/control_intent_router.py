"""Conservative natural-language control router for Smart Center.

AI_MODULE: control_intent_router
AI_PURPOSE: Convert short Chinese control phrases into a safe module route before
the Feishu/local-model control chain builds the final executable command.
AI_BOUNDARY: This module never executes devices. It only selects a route, blocks
unsafe ambiguity, or returns a small prebuilt command for well-known gateways.
AI_DATA_FLOW: text + action + alias rows -> route decision -> legacy resolver/API
command builder.
AI_RISK: High. A wrong route can control the wrong real device, so ambiguity must
return an error instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

import requests

from services.device_aliases import find_alias_rows, normalize_alias_text


RouteResolver = Callable[[str, str], dict[str, Any] | None]


OUTDOOR_LIGHT_WORDS = ("庭院灯", "户外灯", "室外灯", "室外照明", "院子灯", "院子里的灯", "外墙灯", "院灯")
DOOR_CONTROL_WORDS = ("大门", "门禁", "开门", "关门", "停止大门", "停门")
POWER_WORDS = ("强电", "电柜", "电箱", "电源柜", "配电柜", "回路")
SEQUENCER_WORDS = ("时序", "时序电源", "sequencer")
HVAC_WORDS = ("空调", "hvac", "制冷", "制热")
PROJECTOR_WORDS = ("投影", "投影机", "pjlink")
LIGHT_WORDS = ("灯", "灯光", "照明", "继电器")
SERVER_WORDS = ("服务器", "主机", "机器", "电脑", "节点")


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(str(word).lower() in lowered for word in words)


def _looks_like_bare_channel(text: str) -> bool:
    raw = str(text or "")
    if not re.search(r"(?:第?\s*\d+\s*(?:路|回路|通道)|第?\s*[一二两三四五六七八九十]\s*(?:路|回路|通道))", raw):
        return False
    return not _contains_any(raw, POWER_WORDS + SEQUENCER_WORDS + HVAC_WORDS + PROJECTOR_WORDS + SERVER_WORDS + ("灯光", "照明"))


def _action_for_on_off(action: str) -> str:
    return "on" if action in {"on", "toggle"} else "off"


@dataclass(frozen=True)
class ControlRouteResult:
    command: dict[str, Any] | None = None
    module: str = ""
    reason: str = ""
    stop: bool = False


class ControlIntentRouter:
    """Choose the safest control module before legacy command construction.

    The old parser is still the source of executable API payloads. This router
    only prevents known bad routes and provides a few unambiguous gateway commands.
    """

    def __init__(self, alias_rows: list[dict[str, Any]] | None = None) -> None:
        self.alias_rows = alias_rows or []

    def route(
        self,
        text: str,
        action: str,
        *,
        door: RouteResolver,
        sequencer: RouteResolver,
        power: RouteResolver,
        hvac: RouteResolver,
        projector: RouteResolver,
        node_red: RouteResolver,
        light: RouteResolver,
        server: Callable[[str, str, bool], dict[str, Any] | None],
        infer: Callable[[str, str, str], dict[str, Any] | None],
    ) -> ControlRouteResult:
        raw = str(text or "").strip()
        normalized = normalize_alias_text(raw)
        if not raw or not action:
            return ControlRouteResult()

        # "门口LED电柜" contains 门口 but is a cabinet phrase, not the gate.
        if _contains_any(raw, POWER_WORDS):
            return ControlRouteResult(power(raw, action), module="power", reason="包含电柜/回路语义")

        if _contains_any(raw, SEQUENCER_WORDS):
            return ControlRouteResult(sequencer(raw, action), module="sequencer", reason="包含时序电源语义")

        if _contains_any(raw, OUTDOOR_LIGHT_WORDS) or (
            _contains_any(raw, ("院子", "室外", "户外", "外墙")) and _contains_any(raw, ("灯", "照明"))
        ):
            return ControlRouteResult(self._courtyard_light_command(action), module="node_red", reason="户外/庭院灯固定走121 Node-RED")

        if _contains_any(raw, DOOR_CONTROL_WORDS):
            return ControlRouteResult(door(raw, action), module="door", reason="包含明确大门/门禁动作")

        if _looks_like_bare_channel(raw):
            return ControlRouteResult(
                {
                    "type": "error",
                    "message": "只识别到回路编号，但没有明确是强电柜、灯光、时序电源还是其他设备。请补充模块，例如：中控室电柜第8路关闭，或一号厅前言墙灯打开。",
                },
                stop=True,
                reason="裸回路编号不允许猜测",
            )

        if _contains_any(raw, HVAC_WORDS):
            return ControlRouteResult(hvac(raw, action), module="hvac", reason="包含空调语义")

        if _contains_any(raw, PROJECTOR_WORDS):
            return ControlRouteResult(projector(raw, action), module="projector", reason="包含投影语义")

        alias_modules = self._infer_modules_from_aliases(raw)
        if "power" in alias_modules:
            return ControlRouteResult(power(raw, action), module="power", reason="别名匹配强电柜")
        if "sequencer" in alias_modules:
            return ControlRouteResult(sequencer(raw, action), module="sequencer", reason="别名匹配时序电源")
        if "hvac" in alias_modules:
            return ControlRouteResult(hvac(raw, action), module="hvac", reason="别名匹配空调")
        if "projector" in alias_modules:
            return ControlRouteResult(projector(raw, action), module="projector", reason="别名匹配投影")
        if "door" in alias_modules:
            return ControlRouteResult(door(raw, action), module="door", reason="别名匹配门禁")
        if "light" in alias_modules:
            node_red_command = node_red(raw, action)
            return ControlRouteResult(node_red_command or light(raw, action), module="light", reason="别名匹配灯光")

        if _contains_any(raw, LIGHT_WORDS):
            node_red_command = node_red(raw, action)
            return ControlRouteResult(node_red_command or light(raw, action), module="light", reason="包含灯光语义")

        if _contains_any(raw, SERVER_WORDS) or re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", raw):
            command = server(raw, action, True)
            return ControlRouteResult(command, module="server", reason="服务器/IP语义")

        inferred = infer(raw, action, normalized)
        if inferred:
            return ControlRouteResult(inferred, module=str(inferred.get("type") or ""), reason="兜底推断")

        return ControlRouteResult()

    def _infer_modules_from_aliases(self, text: str) -> set[str]:
        matches = find_alias_rows(text, self.alias_rows)
        modules: set[str] = set()
        for row in matches[:8]:
            module = str(row.get("module") or "")
            if module and row.get("control_capability"):
                modules.add(module)
        return modules

    def _courtyard_light_command(self, action: str) -> dict[str, Any]:
        normalized_action = _action_for_on_off(action)
        return {
            "type": "node_red",
            "risk": "normal",
            "label": "庭院灯",
            "path": f"/api/node-red/device/{requests.utils.quote('courtyard_light', safe='')}/control",
            "payload": {"action": normalized_action},
            "action": normalized_action,
            "confidence": "high",
            "inference_reason": "",
        }
