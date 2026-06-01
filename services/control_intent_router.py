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
POWER_DEVICE_WORDS = ("强电", "电柜", "电箱", "电源柜", "配电柜")
SEQUENCER_WORDS = ("时序", "时序电源", "sequencer")
HVAC_WORDS = ("空调", "hvac", "制冷", "制热")
PROJECTOR_WORDS = ("投影", "投影机", "pjlink")
LIGHT_WORDS = ("灯", "灯光", "照明", "继电器")
SERVER_WORDS = ("服务器", "主机", "机器", "电脑", "节点")
SCREEN_WORDS = ("幕布", "幕", "升降幕", "投影幕")
CUSTOM_PROTOCOL_WORDS = ("泥人", "协议控制")
WHOLE_LIGHT_WORDS = ("所有灯", "全部灯", "全灯", "所有灯光", "全部灯光", "灯全")


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(str(word).lower() in lowered for word in words)


def _looks_like_bare_channel(text: str) -> bool:
    raw = str(text or "")
    if not re.search(r"(?:第?\s*\d+\s*(?:路|回路|通道)|第?\s*[一二两三四五六七八九十]\s*(?:路|回路|通道))", raw):
        return False
    return not _contains_any(raw, POWER_DEVICE_WORDS + SEQUENCER_WORDS + HVAC_WORDS + PROJECTOR_WORDS + SERVER_WORDS + ("灯", "灯光", "照明"))


def _explicit_power_context(text: str) -> bool:
    if _contains_any(text, SEQUENCER_WORDS):
        return False
    return _contains_any(text, POWER_DEVICE_WORDS + ("供电", "电源", "插座", "断电", "上电", "合闸", "空气开关", "空开"))


def _looks_like_protocol_ip(text: str) -> bool:
    raw = str(text or "")
    return bool(re.search(r"(?:\b\d{1,3}(?:\.\d{1,3}){1,3}\b|(?:^|[^\d])50\.\d{1,3}(?:[^\d]|$))", raw))


def _action_for_on_off(action: str) -> str:
    return "on" if action in {"on", "toggle"} else "off"


def _specific_alias_modules(text: str, rows: list[dict[str, Any]]) -> set[str]:
    normalized = normalize_alias_text(text)
    modules: set[str] = set()
    if not normalized:
        return modules
    for row in find_alias_rows(text, rows)[:10]:
        for alias in row.get("aliases") or []:
            alias_norm = normalize_alias_text(alias)
            if len(alias_norm) >= 4 and alias_norm in normalized:
                module = str(row.get("module") or "")
                if module and row.get("control_capability"):
                    modules.add(module)
                    break
    return modules


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
        screen: RouteResolver,
        custom: RouteResolver,
        infer: Callable[[str, str, str], dict[str, Any] | None],
    ) -> ControlRouteResult:
        raw = str(text or "").strip()
        normalized = normalize_alias_text(raw)
        if not raw or not action:
            return ControlRouteResult()

        # Whole-room lighting phrases such as "1号厅所有灯" must prefer the
        # lighting controller over the similarly named hall projector.
        if _contains_any(raw, WHOLE_LIGHT_WORDS) or (_contains_any(raw, ("全开", "全关", "全关灯")) and _contains_any(raw, LIGHT_WORDS)):
            return ControlRouteResult(light(raw, action), module="light", reason="整区灯光控制")

        if _contains_any(raw, CUSTOM_PROTOCOL_WORDS) or (_contains_any(raw, ("继电器", "设备")) and _looks_like_protocol_ip(raw)):
            return ControlRouteResult(custom(raw, action), module="control_center", reason="协议控制/泥人设备语义")

        if _contains_any(raw, SCREEN_WORDS):
            return ControlRouteResult(screen(raw, action), module="screen", reason="包含幕布语义")

        if _contains_any(raw, SEQUENCER_WORDS):
            return ControlRouteResult(sequencer(raw, action), module="sequencer", reason="包含时序电源语义")

        # "一号厅空调" can also be a cabinet channel name. Prefer the HVAC
        # device unless the user explicitly says cabinet/power/circuit.
        if _contains_any(raw, HVAC_WORDS) and not _explicit_power_context(raw):
            return ControlRouteResult(hvac(raw, action), module="hvac", reason="包含空调语义")

        # A server label may overlap a cabinet-channel label, such as
        # "门口LED服务器". Never reinterpret server wording as a power cut.
        if _contains_any(raw, SERVER_WORDS):
            command = server(raw, action, True)
            if command is None:
                command = {
                    "type": "error",
                    "message": "识别到服务器控制语义，但动作不够明确。请说：唤醒、关机、重启或刷新指定服务器。",
                }
            return ControlRouteResult(command, module="server", reason="包含服务器语义", stop=True)

        # "门口LED电柜" contains 门口 but is a cabinet phrase, not the gate.
        if _explicit_power_context(raw):
            return ControlRouteResult(power(raw, action), module="power", reason="包含电柜/回路语义")

        if _looks_like_bare_channel(raw):
            return ControlRouteResult(
                {
                    "type": "error",
                    "message": "只识别到回路编号，但没有明确是强电柜、灯光、时序电源还是其他设备。请补充模块，例如：中控室电柜第8路关闭，或一号厅前言墙灯打开。",
                },
                stop=True,
                reason="裸回路编号不允许猜测",
            )

        specific_alias_modules = _specific_alias_modules(raw, self.alias_rows)
        if "power" in specific_alias_modules:
            return ControlRouteResult(power(raw, action), module="power", reason="明确别名匹配强电柜")
        if "light" in specific_alias_modules:
            node_red_command = node_red(raw, action)
            return ControlRouteResult(node_red_command or light(raw, action), module="light", reason="明确别名匹配灯光")

        if _contains_any(raw, OUTDOOR_LIGHT_WORDS) or (
            _contains_any(raw, ("院子", "室外", "户外", "外墙")) and _contains_any(raw, ("灯", "照明"))
        ):
            return ControlRouteResult(self._courtyard_light_command(action), module="node_red", reason="户外/庭院灯固定走121 Node-RED")

        if _contains_any(raw, DOOR_CONTROL_WORDS):
            return ControlRouteResult(door(raw, action), module="door", reason="包含明确大门/门禁动作")

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
        if "screen" in alias_modules:
            return ControlRouteResult(screen(raw, action), module="screen", reason="别名匹配幕布")
        if "custom" in alias_modules:
            return ControlRouteResult(custom(raw, action), module="control_center", reason="别名匹配协议控制设备")
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
