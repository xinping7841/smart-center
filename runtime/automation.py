# AI_MODULE: automation_runtime
# AI_PURPOSE: 自动化规则的条件求值、触发去抖、执行状态缓存和运行日志生成。
# AI_BOUNDARY: 不处理配置表单保存；API 层负责保存 CONFIG，本模块只消费已归一化规则。
# AI_DATA_FLOW: CONFIG.automation_rules + runtime caches -> trigger decision -> scene/control action -> operation/event logs。
# AI_RUNTIME: background.py 周期调用，前端自动化页读取 snapshot 展示节点状态。
# AI_RISK: 高，可能间接触发灯光、空调、强电、时序电源、投影等真实动作。
# AI_COMPAT: 规则 state、last_* 字段和 snapshot 结构会被 static/js/views/automation-view.js 使用。
# AI_SEARCH_KEYWORDS: automation runtime, condition evaluate, compound trigger, scene link, debounce.

import threading
import time
from datetime import datetime

import modbus_core as mc
from config import CONFIG, SERVER_COMMANDS
from data_logger import add_log
from .env_history import build_env_lux_trend

from .state import LIGHT_DRIVERS, get_state_value

_AUTO_STATE = {}
_SCENE_RUNNING = {}


def _new_rule_state():
    return {
        "latched": False,
        "trigger_states": {},
        "preconditions": [],
        "preconditions_met": True,
        "condition_true": False,
        "hits": 0,
        "active_since": None,
        "crossing_active": False,
        "crossing_started_at": None,
        "last_schedule_key": "",
        "last_schedule_day": "",
        "last_schedule_planned_at": None,
        "last_schedule_missed": False,
        "last_schedule_delay_sec": 0.0,
        "last_evaluated_at": None,
        "last_current_value": None,
        "last_condition_raw": False,
        "last_condition_stable": False,
        "last_day_match": None,
        "last_in_window": None,
        "last_trigger_matched": False,
        "last_triggered_at": None,
        "last_trigger_value": None,
        "last_error": "",
        "last_action_ok": None,
        "last_action_at": None,
        "last_action_message": "",
        "last_skip_reason": "",
        "last_window_key": "",
        "window_entered_at": None,
        "window_bootstrap_fired": False,
    }


def _new_trigger_state():
    state = _new_rule_state()
    state.pop("trigger_states", None)
    state.pop("preconditions", None)
    state.pop("preconditions_met", None)
    return state


def _parse_number(value):
    try:
        return float(value)
    except Exception:
        return None


def _compare_value(current, op, target):
    if op in ["is_true", "true"]:
        return bool(current) is True
    if op in ["is_false", "false"]:
        return bool(current) is False

    current_num = _parse_number(current)
    target_num = _parse_number(target)
    if current_num is not None and target_num is not None:
        if op == ">":
            return current_num > target_num
        if op == ">=":
            return current_num >= target_num
        if op == "<":
            return current_num < target_num
        if op == "<=":
            return current_num <= target_num
        if op == "==":
            return current_num == target_num
        if op == "!=":
            return current_num != target_num

    current_text = "" if current is None else str(current)
    target_text = "" if target is None else str(target)
    if op == "==":
        return current_text == target_text
    if op == "!=":
        return current_text != target_text
    if op == "contains":
        return target_text in current_text
    return False


def _condition_label(condition):
    if not isinstance(condition, dict):
        return ""
    return str(condition.get("label") or condition.get("name") or condition.get("title") or "").strip()


def _compare_with_hysteresis(current, op, target, hysteresis, was_true):
    current_num = _parse_number(current)
    target_num = _parse_number(target)
    hysteresis_num = _parse_number(hysteresis) or 0
    if hysteresis_num <= 0 or current_num is None or target_num is None:
        return _compare_value(current, op, target)

    if op == ">":
        return current_num > (target_num - hysteresis_num if was_true else target_num)
    if op == ">=":
        return current_num >= (target_num - hysteresis_num if was_true else target_num)
    if op == "<":
        return current_num < (target_num + hysteresis_num if was_true else target_num)
    if op == "<=":
        return current_num <= (target_num + hysteresis_num if was_true else target_num)
    return _compare_value(current, op, target)


def _wait_for_condition(condition, timeout_ms=60000, poll_ms=500):
    started_at = time.time()
    timeout_sec = max(float(timeout_ms or 0) / 1000.0, 0)
    poll_sec = max(float(poll_ms or 0) / 1000.0, 0.2)
    source_type = condition.get("source_type", "env")
    device_id = condition.get("device_id")
    prop = condition.get("prop", "online")
    op = condition.get("op", "==")
    value = condition.get("value")
    hysteresis = condition.get("hysteresis", 0)
    channel = condition.get("channel")

    while True:
        ok, current_value, _ = get_state_value(source_type, device_id, prop, channel=channel)
        if ok and _compare_with_hysteresis(current_value, op, value, hysteresis, False):
            return True, current_value
        if timeout_sec > 0 and (time.time() - started_at) >= timeout_sec:
            return False, current_value
        time.sleep(poll_sec)


def _find_screen_action_command(screen_cfg, action_name):
    for cmd in screen_cfg.get("commands", []) or []:
        if str(cmd.get("action")) == str(action_name):
            return cmd
    return None


def _execute_screen_action(screen_cfg, action):
    from screen_core import ScreenDriver

    driver = ScreenDriver(screen_cfg)
    action_type = action.get("action_type", action.get("action", "stop"))
    if action_type == "set_position":
        target_position = float(action.get("target_position", 0))
        plan = driver.set_position(target_position)
        move_cmd = _find_screen_action_command(screen_cfg, plan["direction"])
        stop_cmd = _find_screen_action_command(screen_cfg, "stop")
        if not move_cmd or not stop_cmd:
            return False, "missing screen movement commands"
        success, res = driver.execute(move_cmd)
        if not success:
            return success, res
        time.sleep(max(float(plan.get("move_time", 0)), 0))
        return driver.execute(stop_cmd)

    command = {
        "action": action_type,
        "payload": action.get("payload", ""),
        "format": action.get("format", "hex"),
        "name": action.get("name", action_type),
    }
    return driver.execute(command)


def _do_binary_action(sys_type, action, state):
    channel = action.get("channel")
    if sys_type == "light":
        drv = LIGHT_DRIVERS.get(action.get("device_id"))
        if drv:
            drv.control_channel(channel, state)
            return True, f"[自动化] 灯光设备 {action.get('device_id')} 通道{channel} {'闭合' if state else '断开'}"
        return False, f"[自动化] 灯光设备 {action.get('device_id')} 不在线，通道{channel} 控制失败"
    elif sys_type == "power":
        mc.set_channel(int(action.get("device_id", 0)), channel, state)
        return True, f"[自动化] 强电柜 {action.get('device_id')} 通道{channel} {'闭合' if state else '断开'}"
    return False, f"[自动化] 未知二值控制类型: {sys_type}"


def _find_hvac_device(device_id):
    return next(
        (item for item in CONFIG.get("hvac_devices", []) if str(item.get("id")) == str(device_id)),
        None,
    )


def _hvac_protocol(device):
    return str(device.get("protocol") or device.get("source_type") or "mock").strip().lower()


def _control_hvac_device(device, action_type, payload):
    protocol = _hvac_protocol(device)
    if protocol == "miio":
        from services.miio_hvac import miio_hvac_service

        return miio_hvac_service.control(
            device,
            action_type,
            temperature=payload.get("temperature"),
            mode=payload.get("mode"),
            fan_mode=payload.get("fan_mode") or payload.get("fan_speed"),
        )
    if protocol in {"home_assistant", "homeassistant", "ha"}:
        from services.home_assistant_bridge import control_hvac as ha_control_hvac

        return ha_control_hvac(
            device,
            action_type,
            CONFIG,
            temperature=payload.get("temperature"),
            mode=payload.get("mode"),
            fan_mode=payload.get("fan_mode") or payload.get("fan_speed"),
        )
    return True, "mock_success", "mock"


def _execute_hvac_action(action):
    device = _find_hvac_device(action.get("device_id"))
    if not device:
        return False, f"[自动化] 空调未配置: {action.get('device_id')}"

    action_type = str(action.get("action_type") or "").strip().lower()
    if not action_type:
        action_type = "power_on" if action.get("is_open", True) else "power_off"

    ok, result, driver_class = _control_hvac_device(device, action_type, action)
    device_name = str(device.get("name") or action.get("device_id") or "未命名空调")
    if not ok:
        return False, f"[自动化] 空调 {device_name} 动作失败: {action_type} -> {result}"
    return True, f"[自动化] 空调 {device_name} 已执行 {action_type} ({driver_class})"


def _should_skip_node_red_action(device_id, normalized_action):
    if device_id != "courtyard_light" or normalized_action != "on":
        return False, ""

    try:
        from api.node_red import get_node_red_device_status

        status = get_node_red_device_status(device_id)
    except Exception as exc:
        return False, f"status_check_failed:{exc}"

    current_status = str((status or {}).get("status") or "").strip().lower()
    display_name = str((status or {}).get("device_name") or device_id)
    if current_status == "on":
        return True, f"[自动化] Node-RED {display_name} 当前已开，跳过重复 on"
    return False, ""


def _execute_node_red_action(action):
    device_id = str(action.get("device_id") or "").strip()
    if not device_id:
        return False, "[自动化] Node-RED 设备未配置"

    action_type = str(action.get("action_type") or "").strip().lower()
    if not action_type:
        action_type = "on" if action.get("is_open", True) else "off"
    action_aliases = {
        "power_on": "on",
        "turn_on": "on",
        "open": "on",
        "power_off": "off",
        "turn_off": "off",
        "close": "off",
    }
    normalized_action = action_aliases.get(action_type, action_type)
    if normalized_action not in {"on", "off", "toggle", "status"}:
        return False, f"[自动化] Node-RED 不支持动作: {device_id}/{action_type}"

    try:
        skipped, skip_message = _should_skip_node_red_action(device_id, normalized_action)
        if skipped:
            return True, skip_message

        from api.node_red import control_node_red_device

        ok, result, driver_class = control_node_red_device(device_id, normalized_action, source="automation_scene")
    except Exception as exc:
        return False, f"[自动化] Node-RED {device_id} 动作失败: {normalized_action} -> {exc}"

    device_name = str((result or {}).get("device_name") or device_id)
    detail = str((result or {}).get("display_text") or (result or {}).get("status") or "").strip()
    if not ok:
        return False, f"[自动化] Node-RED {device_name} 动作失败: {normalized_action} -> {detail or result}"
    return True, f"[自动化] Node-RED {device_name} 已执行 {normalized_action} ({driver_class})"


def _execute_scene_action(action):
    sys_type = action.get("sub_system", "light")
    act_type = action.get("action_type", "on" if action.get("is_open", True) else "off")
    jog_ms = int(action.get("jog_time_ms", 1000) or 1000)

    if sys_type == "hvac":
        return _execute_hvac_action(action)

    if str(sys_type).strip().lower() in {"node_red", "node-red", "nodered"}:
        return _execute_node_red_action(action)

    if sys_type == "server":
        mac = str(action.get("device_id"))
        if act_type == "wake":
            try:
                from wakeonlan import send_magic_packet

                send_magic_packet(mac)
                add_log(-1, f"[server] wake-on-lan sent: {mac}")
            except Exception as exc:
                add_log(-1, f"[server] wake-on-lan failed: {exc}")
                return False, f"[自动化] 服务器唤醒失败: {mac} -> {exc}"
        elif act_type in ["shutdown", "restart", "refresh"]:
            SERVER_COMMANDS[mac] = act_type
            return True, f"[自动化] 服务器 {mac} 已下发 {act_type}"
        return True, f"[自动化] 服务器 {mac} 已下发唤醒"

    if sys_type == "projector":
        proj_cfg = next((p for p in CONFIG.get("projectors", []) if str(p.get("id")) == str(action.get("device_id"))), None)
        if proj_cfg:
            from projector_core import ProjectorDriver

            cmd_payload = {"payload": action.get("payload", ""), "format": action.get("format", "hex")}
            if action.get("command"):
                cmd_payload = action.get("command")
            success, res = ProjectorDriver(proj_cfg).execute(cmd_payload)
            if not success:
                add_log(-1, f"[projector] scene action failed: {res}")
                return False, f"[自动化] 投影机动作失败: {proj_cfg.get('name', action.get('device_id'))} -> {res}"
            return True, f"[自动化] 投影机 {proj_cfg.get('name', action.get('device_id'))} 已执行动作"
        return False, f"[自动化] 投影机未配置: {action.get('device_id')}"

    if sys_type == "screen":
        screen_cfg = next((s for s in CONFIG.get("screens", []) if str(s.get("id")) == str(action.get("device_id"))), None)
        if screen_cfg:
            success, res = _execute_screen_action(screen_cfg, action)
            if not success:
                add_log(-1, f"[screen] scene action failed: {res}")
                return False, f"[自动化] 幕布动作失败: {screen_cfg.get('name', action.get('device_id'))} -> {res}"
            return True, f"[自动化] 幕布 {screen_cfg.get('name', action.get('device_id'))} 已执行动作"
        return False, f"[自动化] 幕布未配置: {action.get('device_id')}"

    if sys_type == "universal":
        dev_cfg = next((d for d in CONFIG.get("custom_devices", []) if str(d.get("id")) == str(action.get("device_id"))), None)
        if dev_cfg:
            from universal_core import UniversalDriver

            command = {
                "payload": action.get("payload", ""),
                "format": action.get("format", "str"),
                "wait_ms": action.get("wait_ms", 0),
            }
            success, result = UniversalDriver(dev_cfg).execute_command(command)
            device_name = dev_cfg.get("name", action.get("device_id"))
            target = f"{dev_cfg.get('interface', 'tcp')}://{dev_cfg.get('ip') or dev_cfg.get('com_port')}:{dev_cfg.get('port', '')}"
            if not success:
                return (
                    False,
                    f"[自动化] 协议控制 {device_name} 指令失败: {target} payload={command.get('payload')} -> {result}",
                )
            return True, f"[自动化] 协议控制 {device_name} 已发送指令: {target} payload={command.get('payload')}"
        return False, f"[自动化] 泛型设备未配置: {action.get('device_id')}"

    if sys_type == "light" and act_type not in {"on", "off", "jog"}:
        drv = LIGHT_DRIVERS.get(action.get("device_id"))
        if drv and hasattr(drv, "execute_action"):
            drv.execute_action(act_type)
            return True, f"[自动化] 灯光设备 {action.get('device_id')} 已执行动作 {act_type}"
        return False, f"[自动化] 灯光设备 {action.get('device_id')} 不支持动作 {act_type}"

    if sys_type == "wait":
        wait_type = action.get("wait_type", "duration")
        if wait_type == "duration":
            time.sleep(max(float(action.get("duration_ms", action.get("delay_ms", 0)) or 0) / 1000.0, 0))
            return True, f"[自动化] 等待 {int(float(action.get('duration_ms', action.get('delay_ms', 0)) or 0))}ms 完成"
        condition = {
            "source_type": action.get("source_type", "screen"),
            "device_id": action.get("device_id"),
            "prop": action.get("prop", "position"),
            "op": action.get("op", ">="),
            "value": action.get("value", action.get("target_position", 0)),
            "hysteresis": action.get("hysteresis", 0),
            "channel": action.get("channel"),
        }
        ok, current_value = _wait_for_condition(
            condition,
            timeout_ms=action.get("timeout_ms", 60000),
            poll_ms=action.get("poll_ms", 500),
        )
        if not ok:
            add_log(-1, f"[scene] wait timeout: {condition}, current={current_value}")
            return False, f"[自动化] 条件等待超时: current={current_value}"
        return True, "[自动化] 条件等待完成"

    if act_type == "on":
        return _do_binary_action(sys_type, action, True)
    elif act_type == "off":
        return _do_binary_action(sys_type, action, False)
    elif act_type == "jog":
        ok_on, msg_on = _do_binary_action(sys_type, action, True)
        time.sleep(jog_ms / 1000.0)
        ok_off, msg_off = _do_binary_action(sys_type, action, False)
        return (ok_on and ok_off), f"{msg_on}; {msg_off}"
    return False, f"[自动化] 未支持的动作: {sys_type}/{act_type}"


def execute_scene(scene_id, async_mode=True, return_detail=False):
    def _run():
        scene = next((s for s in CONFIG.get("scenes", []) if str(s["id"]) == str(scene_id)), None)
        if not scene:
            add_log(-1, f"[scene] missing: {scene_id}")
            return False, f"场景不存在: {scene_id}"
        scene_key = str(scene.get("id"))
        if _SCENE_RUNNING.get(scene_key):
            add_log(-1, f"[scene] skip duplicate trigger: {scene['name']}")
            return False, f"场景正在执行中: {scene['name']}"

        _SCENE_RUNNING[scene_key] = True
        try:
            add_log(-1, f"[scene] start: {scene['name']}")
            for action in scene.get("actions", []):
                delay = int(action.get("delay_ms", 0) or 0)
                if delay > 0:
                    time.sleep(delay / 1000.0)
                ok, action_msg = _execute_scene_action(action)
                if action_msg:
                    add_log(-1, action_msg)
                if not ok:
                    add_log(-1, f"[自动化] 场景动作执行失败: {scene['name']} -> {action_msg}")
                    return False, action_msg
            add_log(-1, f"[scene] completed: {scene['name']}")
            return True, f"场景执行完成: {scene['name']}"
        finally:
            _SCENE_RUNNING[scene_key] = False

    if async_mode:
        threading.Thread(target=_run, daemon=True).start()
        if return_detail:
            return True, "场景已开始异步执行"
        return True
    ok, message = _run()
    if return_detail:
        return bool(ok), message
    return bool(ok)


def _execute_rule_scene(rule, state):
    scene_id = rule.get("action_scene_id")
    scene_exists = any(str(scene.get("id")) == str(scene_id) for scene in CONFIG.get("scenes", []))
    state["last_action_at"] = datetime.now().isoformat()
    if not scene_exists:
        message = f"[automation] target scene missing: [{rule['name']}] -> {scene_id}"
        state["last_action_ok"] = False
        state["last_action_message"] = message
        state["last_error"] = "target_scene_missing"
        add_log(-1, message)
        return False
    ok, message = execute_scene(scene_id, async_mode=False, return_detail=True)
    state["last_action_ok"] = bool(ok)
    state["last_action_message"] = message or ("scene_completed" if ok else "scene_failed")
    if not ok:
        state["last_error"] = "scene_action_failed"
        add_log(-1, f"[automation] action failed: [{rule['name']}] -> {scene_id}")
    else:
        state["last_error"] = ""
    return bool(ok)


def _get_rule_state(rule_id):
    if rule_id not in _AUTO_STATE:
        _AUTO_STATE[rule_id] = _new_rule_state()
    return _AUTO_STATE[rule_id]


def _day_match(schedule, now):
    day_type = schedule.get("day_type", "everyday")
    wd = now.weekday()
    if day_type == "everyday":
        return True
    if day_type == "workday":
        return wd < 5
    if day_type == "weekend":
        return wd >= 5
    if day_type == "custom":
        return str(wd) in [str(item) for item in schedule.get("days", [])]
    return True


def _evaluate_condition(cond, state, now):
    source_type = cond.get("source_type", "env")
    device_id = cond.get("device_id")
    prop = cond.get("prop", "lux")
    op = cond.get("op", "<")
    value = cond.get("value", 0)
    hysteresis = cond.get("hysteresis", 0)
    debounce_sec = max(float(cond.get("debounce_sec", 0) or 0), 0)
    consecutive_hits = max(int(cond.get("consecutive_hits", 1) or 1), 1)
    crossing_mode = str(cond.get("crossing_mode") or "none").strip().lower()
    rearm_value = cond.get("rearm_value", "")
    channel = cond.get("channel")

    ok, current_value, _ = get_state_value(source_type, device_id, prop, channel=channel)
    state["last_evaluated_at"] = now.isoformat()
    state["last_current_value"] = current_value
    if not ok:
        state["condition_true"] = False
        state["hits"] = 0
        state["active_since"] = None
        state["last_condition_raw"] = False
        state["last_condition_stable"] = False
        state["last_error"] = "state_unavailable"
        return False, current_value

    previous_value = state.get("previous_value")
    base_match = _compare_with_hysteresis(current_value, op, value, hysteresis, state["condition_true"])
    raw_match = base_match
    crossing_ready = bool(state.get("crossing_ready", True))
    crossing_active = bool(state.get("crossing_active", False))
    current_num = _parse_number(current_value)
    threshold_num = _parse_number(value)
    previous_num = _parse_number(previous_value)
    rearm_num = _parse_number(rearm_value)
    if rearm_num is None:
        if threshold_num is not None:
            rearm_num = threshold_num + max(_parse_number(hysteresis) or 0.0, 0.0)
        else:
            rearm_num = None

    if crossing_mode == "cross_down":
        crossed_down = (
            current_num is not None
            and threshold_num is not None
            and previous_num is not None
            and previous_num > threshold_num
            and current_num <= threshold_num
        )
        if current_num is not None and rearm_num is not None and current_num >= rearm_num:
            crossing_ready = True
            crossing_active = False
            state["crossing_started_at"] = None
        recovered_after_restart = bool(
            previous_num is None
            and base_match
            and crossing_ready
        )
        if crossing_ready and (crossed_down or recovered_after_restart):
            crossing_ready = False
            crossing_active = True
            if state.get("crossing_started_at") in (None, "", 0):
                state["crossing_started_at"] = now.timestamp()
        elif not base_match:
            crossing_active = False
            state["crossing_started_at"] = None
        raw_match = bool(base_match and crossing_active)
    elif crossing_mode == "cross_up":
        crossed_up = (
            current_num is not None
            and threshold_num is not None
            and previous_num is not None
            and previous_num < threshold_num
            and current_num >= threshold_num
        )
        if current_num is not None and rearm_num is not None and current_num <= rearm_num:
            crossing_ready = True
            crossing_active = False
            state["crossing_started_at"] = None
        recovered_after_restart = bool(
            previous_num is None
            and base_match
            and crossing_ready
        )
        if crossing_ready and (crossed_up or recovered_after_restart):
            crossing_ready = False
            crossing_active = True
            if state.get("crossing_started_at") in (None, "", 0):
                state["crossing_started_at"] = now.timestamp()
        elif not base_match:
            crossing_active = False
            state["crossing_started_at"] = None
        raw_match = bool(base_match and crossing_active)

    if raw_match:
        state["hits"] += 1
        if state["active_since"] is None:
            state["active_since"] = now.timestamp()
    else:
        state["hits"] = 0
        state["active_since"] = None

    stable = raw_match
    if stable and state["hits"] < consecutive_hits:
        stable = False
    if stable and debounce_sec > 0:
        stable = (now.timestamp() - (state["active_since"] or now.timestamp())) >= debounce_sec

    state["condition_true"] = raw_match
    state["last_condition_raw"] = raw_match
    state["last_condition_stable"] = stable
    state["last_error"] = ""
    state["previous_value"] = current_value
    state["crossing_mode"] = crossing_mode
    state["crossing_ready"] = crossing_ready
    state["crossing_active"] = crossing_active
    state["rearm_value"] = rearm_num
    state["last_base_match"] = bool(base_match)
    return stable, current_value


def _evaluate_extra_condition(rule, now):
    extras = rule.get("extra_conditions")
    if isinstance(extras, list):
        conditions = [item for item in extras if isinstance(item, dict)]
    else:
        extra = rule.get("extra_condition")
        conditions = [extra] if isinstance(extra, dict) else []
    if not conditions:
        return True, None

    last_value = None
    for extra in conditions:
        temp_state = {
            "condition_true": False,
            "hits": 0,
            "active_since": None,
            "crossing_active": False,
            "crossing_started_at": None,
            "last_evaluated_at": None,
            "last_current_value": None,
            "last_condition_raw": False,
            "last_condition_stable": False,
            "last_error": "",
            "last_skip_reason": "",
            "crossing_mode": "none",
            "crossing_ready": True,
            "rearm_value": None,
            "previous_value": None,
            "last_base_match": False,
        }
        matched, current_value = _evaluate_condition(extra, temp_state, now)
        last_value = current_value
        if not bool(matched):
            return False, current_value
    return True, last_value


def _evaluate_preconditions(rule, now):
    conditions = rule.get("preconditions")
    if not isinstance(conditions, list):
        conditions = []
    conditions = [item for item in conditions if isinstance(item, dict)]
    if not conditions:
        return True, []

    mode = str(rule.get("precondition_mode") or "all").strip().lower()
    if mode not in {"all", "any"}:
        mode = "all"

    results = []
    for idx, condition in enumerate(conditions):
        temp_state = _new_trigger_state()
        matched, current_value = _evaluate_condition(condition, temp_state, now)
        results.append(
            {
                "id": str(condition.get("id") or f"pre_{idx + 1}"),
                "label": _condition_label(condition),
                "condition": condition,
                "matched": bool(matched),
                "current_value": current_value,
                "last_error": temp_state.get("last_error", ""),
                "last_base_match": bool(temp_state.get("last_base_match", matched)),
            }
        )

    if mode == "any":
        return any(item["matched"] for item in results), results
    return all(item["matched"] for item in results), results


def _ts_to_iso(ts_value):
    try:
        if ts_value in (None, "", 0):
            return None
        return datetime.fromtimestamp(float(ts_value)).isoformat()
    except Exception:
        return None


def _parse_schedule_time_value(time_text):
    text = str(time_text or "").strip()
    if not text:
        return None
    try:
        hour_text, minute_text = text.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except Exception:
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour, minute


def _is_time_in_window(now, schedule):
    start_text = str(schedule.get("time_start", "00:00") or "00:00").strip() or "00:00"
    end_text = str(schedule.get("time_end", "23:59") or "23:59").strip() or "23:59"
    start_parts = _parse_schedule_time_value(start_text)
    end_parts = _parse_schedule_time_value(end_text)
    if start_parts is None or end_parts is None:
        return True, "", start_text, end_text

    current_minutes = now.hour * 60 + now.minute
    start_minutes = start_parts[0] * 60 + start_parts[1]
    end_minutes = end_parts[0] * 60 + end_parts[1]
    if start_minutes <= end_minutes:
        in_window = start_minutes <= current_minutes <= end_minutes
    else:
        in_window = current_minutes >= start_minutes or current_minutes <= end_minutes
    return in_window, f"{start_text}-{end_text}", start_text, end_text


def _update_window_state(state, now, in_window, window_key):
    previous_key = str(state.get("last_window_key") or "")
    if in_window:
        if previous_key != window_key:
            state["window_entered_at"] = now.timestamp()
            state["window_bootstrap_fired"] = False
        state["last_window_key"] = window_key
    else:
        state["last_window_key"] = ""
        state["window_entered_at"] = None
        state["window_bootstrap_fired"] = False


def _maybe_match_window_bootstrap(rule, state, now, cond_match, in_window, current_value):
    condition = rule.get("condition", {}) if isinstance(rule.get("condition", {}), dict) else {}
    schedule = rule.get("schedule", {}) if isinstance(rule.get("schedule", {}), dict) else {}
    crossing_mode = str(condition.get("crossing_mode") or "none").strip().lower()
    bootstrap_sec = max(float(condition.get("window_bootstrap_sec", 0) or 0), 0.0)
    if bootstrap_sec <= 0:
        return False
    if crossing_mode not in {"cross_down", "cross_up"}:
        return False
    base_match = bool(state.get("last_base_match", False))
    if not in_window:
        return False
    if not cond_match and not base_match:
        return False
    entered_at = state.get("window_entered_at")
    if entered_at in (None, "", 0):
        return False
    if bool(state.get("window_bootstrap_fired", False)):
        return False
    try:
        held_for_sec = max(0.0, now.timestamp() - float(entered_at))
    except Exception:
        held_for_sec = 0.0
    if held_for_sec < bootstrap_sec:
        return False
    state["window_bootstrap_fired"] = True
    state["last_skip_reason"] = f"window_bootstrap_after_{round(held_for_sec, 1)}s"
    add_log(
        -1,
        f"[automation] window bootstrap trigger: [{rule.get('name')}] "
        f"value={current_value} held={round(held_for_sec, 1)}s",
    )
    return True


def _build_schedule_trigger(now, schedule, state):
    schedule_parts = _parse_schedule_time_value(schedule.get("time"))
    state["last_schedule_planned_at"] = None
    state["last_schedule_missed"] = False
    state["last_schedule_delay_sec"] = 0.0
    state["last_skip_reason"] = ""
    if schedule_parts is None:
        state["last_error"] = "invalid_schedule_time"
        return False

    hour, minute = schedule_parts
    planned_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    state["last_schedule_planned_at"] = planned_at.timestamp()
    state["last_error"] = ""

    if now < planned_at:
        return False

    today_key = planned_at.strftime("%Y-%m-%d")
    if state.get("last_schedule_day") == today_key:
        return False

    delay_sec = max((now - planned_at).total_seconds(), 0.0)
    try:
        recovery_grace_sec = max(float(schedule.get("recovery_grace_sec", 300) or 300), 0.0)
    except Exception:
        recovery_grace_sec = 300.0
    state["last_schedule_delay_sec"] = delay_sec
    state["last_schedule_missed"] = delay_sec >= 60

    if recovery_grace_sec > 0 and delay_sec > recovery_grace_sec:
        state["last_schedule_day"] = today_key
        state["last_schedule_key"] = planned_at.strftime("%Y-%m-%d %H:%M")
        state["last_error"] = "schedule_missed_window"
        state["last_skip_reason"] = f"stale_by_{round(delay_sec, 1)}s"
        return False

    state["last_schedule_day"] = today_key
    state["last_schedule_key"] = planned_at.strftime("%Y-%m-%d %H:%M")
    return True


def _describe_schedule_trigger(state):
    planned_at = _ts_to_iso(state.get("last_schedule_planned_at")) or "unknown"
    delay_sec = float(state.get("last_schedule_delay_sec", 0.0) or 0.0)
    if state.get("last_schedule_missed"):
        return f"schedule recovered after {round(delay_sec, 1)}s delay (planned {planned_at})"
    return f"schedule on time (planned {planned_at})"


def _build_condition_trend(condition, state):
    if not isinstance(condition, dict):
        return {}
    source_type = str(condition.get("source_type") or "env").strip().lower()
    prop = str(condition.get("prop") or "").strip().lower()
    if source_type != "env" or prop != "lux":
        return {}
    device_id = condition.get("device_id")
    if not device_id:
        return {}
    trend = build_env_lux_trend(
        device_id,
        current_lux=state.get("last_current_value"),
        threshold=condition.get("value"),
        op=condition.get("op", "<"),
    )
    return trend if isinstance(trend, dict) else {}


def _trigger_key(trigger, index):
    return str(trigger.get("id") or trigger.get("key") or f"trigger_{index + 1}")


def _trigger_label(trigger, index):
    return str(
        trigger.get("label")
        or trigger.get("name")
        or trigger.get("title")
        or f"触发条件{index + 1}"
    )


def _trigger_type(trigger):
    trigger_type = str(trigger.get("type") or trigger.get("trigger_type") or "condition").strip().lower()
    if trigger_type not in {"condition", "schedule", "mixed"}:
        trigger_type = "condition"
    return trigger_type


def _trigger_condition(trigger):
    condition = trigger.get("condition")
    if isinstance(condition, dict):
        return condition
    keys = {
        "source_type",
        "device_id",
        "prop",
        "op",
        "value",
        "debounce_sec",
        "hysteresis",
        "consecutive_hits",
        "crossing_mode",
        "rearm_value",
        "window_bootstrap_sec",
        "channel",
    }
    if any(key in trigger for key in keys):
        return {key: trigger.get(key) for key in keys if key in trigger}
    return {}


def _trigger_schedule(trigger):
    schedule = trigger.get("schedule")
    if isinstance(schedule, dict):
        return schedule
    keys = {"day_type", "time", "time_start", "time_end", "days", "recovery_grace_sec"}
    if any(key in trigger for key in keys):
        return {key: trigger.get(key) for key in keys if key in trigger}
    return {}


def _trigger_state_snapshot(trigger, trigger_type, state, now_ts, key="", label=""):
    condition = _trigger_condition(trigger)
    schedule = _trigger_schedule(trigger)
    active_since = state.get("active_since")
    debounce_sec = max(float(condition.get("debounce_sec", 0) or 0), 0.0)
    hits_required = max(int(condition.get("consecutive_hits", 1) or 1), 1)
    stable_for_sec = 0.0
    if active_since not in (None, "", 0):
        try:
            stable_for_sec = max(0.0, now_ts - float(active_since))
        except Exception:
            stable_for_sec = 0.0
    return {
        "key": str(key or ""),
        "id": str(trigger.get("id") or trigger.get("key") or ""),
        "label": str(label or trigger.get("label") or trigger.get("name") or ""),
        "type": trigger_type,
        "condition": condition,
        "schedule": schedule,
        "matched": bool(state.get("last_trigger_matched", False)),
        "latched": bool(state.get("latched", False)),
        "current_value": state.get("last_current_value"),
        "last_evaluated_at": state.get("last_evaluated_at"),
        "last_condition_raw": bool(state.get("last_condition_raw", False)),
        "last_condition_stable": bool(state.get("last_condition_stable", False)),
        "last_base_match": bool(state.get("last_base_match", False)),
        "last_day_match": state.get("last_day_match"),
        "last_in_window": state.get("last_in_window"),
        "last_schedule_key": state.get("last_schedule_key", ""),
        "last_schedule_day": state.get("last_schedule_day", ""),
        "last_schedule_planned_at": _ts_to_iso(state.get("last_schedule_planned_at")),
        "last_schedule_missed": bool(state.get("last_schedule_missed", False)),
        "last_schedule_delay_sec": round(float(state.get("last_schedule_delay_sec", 0.0) or 0.0), 1),
        "last_error": state.get("last_error", ""),
        "last_skip_reason": state.get("last_skip_reason", ""),
        "hits": int(state.get("hits", 0) or 0),
        "hits_required": hits_required,
        "active_since": _ts_to_iso(active_since),
        "stable_for_sec": round(stable_for_sec, 1),
        "debounce_sec": debounce_sec,
        "debounce_progress": round(min(stable_for_sec / debounce_sec, 1.0), 3)
        if debounce_sec > 0
        else (1.0 if bool(state.get("last_condition_stable")) else 0.0),
        "previous_value": state.get("previous_value"),
        "crossing_mode": state.get("crossing_mode", "none"),
        "crossing_ready": bool(state.get("crossing_ready", True)),
        "crossing_active": bool(state.get("crossing_active", False)),
        "crossing_started_at": _ts_to_iso(state.get("crossing_started_at")),
        "rearm_value": state.get("rearm_value"),
    }


def _evaluate_single_trigger(rule, trigger, trigger_state, now, index=0, key=""):
    trigger_type = _trigger_type(trigger)
    key = str(key or _trigger_key(trigger, index))
    label = _trigger_label(trigger, index)
    condition = _trigger_condition(trigger)
    schedule = _trigger_schedule(trigger)
    trigger_state["last_evaluated_at"] = now.isoformat()
    trigger_state["last_day_match"] = None
    trigger_state["last_in_window"] = None
    trigger_state["last_trigger_matched"] = False
    trigger_state["last_skip_reason"] = ""
    current_value = trigger_state.get("last_current_value")
    matched = False

    if trigger_type == "schedule":
        day_match = _day_match(schedule, now)
        trigger_state["last_day_match"] = day_match
        matched = bool(day_match and _build_schedule_trigger(now, schedule, trigger_state))
        current_value = trigger_state.get("last_schedule_key") or schedule.get("time")
    else:
        cond_match, current_value = _evaluate_condition(condition, trigger_state, now)
        if trigger_type == "condition":
            matched = bool(cond_match)
        else:
            day_match = _day_match(schedule, now)
            in_window, window_key, _, _ = _is_time_in_window(now, schedule)
            in_window = bool(day_match and in_window)
            trigger_state["last_day_match"] = day_match
            trigger_state["last_in_window"] = in_window
            _update_window_state(trigger_state, now, in_window, f"{now.strftime('%Y-%m-%d')}|{window_key}")
            matched = bool(cond_match and in_window)
            if not matched:
                pseudo_rule = {"name": f"{rule.get('name')} / {label}", "condition": condition, "schedule": schedule}
                matched = _maybe_match_window_bootstrap(
                    pseudo_rule,
                    trigger_state,
                    now,
                    cond_match,
                    in_window,
                    current_value,
                )

        if matched:
            extra_ok, extra_value = _evaluate_extra_condition(trigger, now)
            if not extra_ok:
                matched = False
                trigger_state["last_skip_reason"] = f"extra_condition_not_met:{extra_value}"

    trigger_state["last_trigger_matched"] = bool(matched)
    return {
        "key": key,
        "label": label,
        "type": trigger_type,
        "matched": bool(matched),
        "current_value": current_value,
    }


def _evaluate_compound_rule(rule, state, now):
    raw_triggers = rule.get("triggers")
    if not isinstance(raw_triggers, list):
        raw_triggers = []
    triggers = [item for item in raw_triggers if isinstance(item, dict)]
    trigger_states = state.setdefault("trigger_states", {})
    mode = str(rule.get("trigger_mode") or "any").strip().lower()
    if mode not in {"any", "all"}:
        mode = "any"

    preconditions_met, precondition_results = _evaluate_preconditions(rule, now)
    state["preconditions_met"] = bool(preconditions_met)
    state["preconditions"] = precondition_results

    results = []
    matched_results = []
    fire_results = []
    for idx, trigger in enumerate(triggers):
        key = _trigger_key(trigger, idx)
        trigger_state = trigger_states.setdefault(key, _new_trigger_state())
        result = _evaluate_single_trigger(rule, trigger, trigger_state, now, idx, key=key)
        result["key"] = key
        result["latched"] = bool(trigger_state.get("latched", False))
        results.append(result)
        if result["matched"]:
            matched_results.append(result)

    if mode == "all":
        triggers_matched = bool(triggers) and len(matched_results) == len(triggers)
        if triggers_matched and preconditions_met and not bool(state.get("latched", False)):
            fire_results = matched_results
            state["latched"] = True
        elif not triggers_matched or not preconditions_met:
            state["latched"] = False
    else:
        triggers_matched = bool(matched_results)
        if preconditions_met:
            for result in matched_results:
                trigger_state = trigger_states.get(result["key"], {})
                if not bool(trigger_state.get("latched", False)):
                    fire_results.append(result)
                    trigger_state["latched"] = True
        for result in results:
            if not result["matched"]:
                trigger_state = trigger_states.get(result["key"], {})
                trigger_state["latched"] = False
        state["latched"] = bool(matched_results)

    if matched_results and not preconditions_met:
        state["last_skip_reason"] = "preconditions_not_met"
    elif not matched_results:
        state["last_skip_reason"] = ""

    state["trigger_results"] = results
    state["last_trigger_matched"] = bool(triggers_matched and preconditions_met)
    state["condition_true"] = bool(matched_results)
    state["last_condition_raw"] = bool(matched_results)
    state["last_condition_stable"] = bool(matched_results)
    state["last_current_value"] = matched_results[0]["current_value"] if matched_results else None
    state["last_error"] = next((str(trigger_states.get(item["key"], {}).get("last_error") or "") for item in results if str(trigger_states.get(item["key"], {}).get("last_error") or "")), "")
    return bool(fire_results), fire_results, bool(triggers_matched), state.get("last_current_value")


def get_automation_runtime_snapshot():
    now_ts = time.time()
    scenes = {str(scene.get("id")): scene for scene in CONFIG.get("scenes", [])}
    snapshots = []

    for rule in CONFIG.get("automations", []):
        rule_id = rule.get("id")
        state = _get_rule_state(rule_id)
        condition = rule.get("condition", {}) if isinstance(rule.get("condition", {}), dict) else {}
        schedule = rule.get("schedule", {}) if isinstance(rule.get("schedule", {}), dict) else {}
        debounce_sec = max(float(condition.get("debounce_sec", 0) or 0), 0.0)
        hits_required = max(int(condition.get("consecutive_hits", 1) or 1), 1)
        active_since = state.get("active_since")
        stable_for_sec = 0.0
        if active_since not in (None, "", 0):
            try:
                stable_for_sec = max(0.0, now_ts - float(active_since))
            except Exception:
                stable_for_sec = 0.0
        scene_id = rule.get("action_scene_id")
        scene = scenes.get(str(scene_id))
        condition_trend = _build_condition_trend(condition, state)
        trigger_snapshots = []
        if str(rule.get("trigger_type") or "").strip().lower() == "compound":
            trigger_states = state.get("trigger_states") if isinstance(state.get("trigger_states"), dict) else {}
            for idx, trigger in enumerate([item for item in rule.get("triggers", []) if isinstance(item, dict)]):
                key = _trigger_key(trigger, idx)
                label = _trigger_label(trigger, idx)
                trigger_state = trigger_states.get(key) or _new_trigger_state()
                trigger_snapshots.append(
                    _trigger_state_snapshot(trigger, _trigger_type(trigger), trigger_state, now_ts, key=key, label=label)
                )

        snapshots.append(
            {
                "id": str(rule_id),
                "name": str(rule.get("name") or rule_id or ""),
                "group": str(rule.get("group") or rule.get("automation_group") or rule.get("group_id") or ""),
                "group_name": str(rule.get("group_name") or rule.get("group_title") or rule.get("display_group") or ""),
                "enabled": bool(rule.get("enabled", False)),
                "trigger_type": rule.get("trigger_type", "condition"),
                "trigger_mode": rule.get("trigger_mode", "any"),
                "scene_id": scene_id,
                "scene_name": scene.get("name") if scene else "",
                "condition": condition,
                "schedule": schedule,
                "triggers": trigger_snapshots,
                "precondition_mode": rule.get("precondition_mode", "all"),
                "preconditions": state.get("preconditions", []),
                "state": {
                    "latched": bool(state.get("latched", False)),
                    "preconditions_met": bool(state.get("preconditions_met", True)),
                    "condition_true": bool(state.get("condition_true", False)),
                    "hits": int(state.get("hits", 0) or 0),
                    "hits_required": hits_required,
                    "active_since": _ts_to_iso(active_since),
                    "stable_for_sec": round(stable_for_sec, 1),
                    "debounce_sec": debounce_sec,
                    "debounce_progress": round(min(stable_for_sec / debounce_sec, 1.0), 3)
                    if debounce_sec > 0
                    else (1.0 if bool(state.get("last_condition_stable")) else 0.0),
                    "current_value": state.get("last_current_value"),
                    "last_evaluated_at": state.get("last_evaluated_at"),
                    "last_condition_raw": bool(state.get("last_condition_raw", False)),
                    "last_condition_stable": bool(state.get("last_condition_stable", False)),
                    "last_day_match": state.get("last_day_match"),
                    "last_in_window": state.get("last_in_window"),
                    "last_trigger_matched": bool(state.get("last_trigger_matched", False)),
                    "last_triggered_at": state.get("last_triggered_at"),
                    "last_trigger_value": state.get("last_trigger_value"),
                    "last_schedule_key": state.get("last_schedule_key", ""),
                    "last_schedule_day": state.get("last_schedule_day", ""),
                    "last_schedule_planned_at": _ts_to_iso(state.get("last_schedule_planned_at")),
                    "last_schedule_missed": bool(state.get("last_schedule_missed", False)),
                    "last_schedule_delay_sec": round(float(state.get("last_schedule_delay_sec", 0.0) or 0.0), 1),
                    "last_error": state.get("last_error", ""),
                    "last_action_ok": state.get("last_action_ok"),
                    "last_action_at": state.get("last_action_at"),
                    "last_action_message": state.get("last_action_message", ""),
                    "last_skip_reason": state.get("last_skip_reason", ""),
                    "previous_value": state.get("previous_value"),
                    "crossing_mode": state.get("crossing_mode", "none"),
                    "crossing_ready": bool(state.get("crossing_ready", True)),
                    "crossing_active": bool(state.get("crossing_active", False)),
                    "crossing_started_at": _ts_to_iso(state.get("crossing_started_at")),
                    "rearm_value": state.get("rearm_value"),
                    "last_base_match": bool(state.get("last_base_match", False)),
                    "scene_running": bool(_SCENE_RUNNING.get(str(scene_id), False)),
                    "condition_trend": condition_trend,
                },
            }
        )

    return {"server_time": datetime.now().isoformat(), "rules": snapshots}


def automation_engine_loop():
    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_key = now.strftime("%Y-%m-%d %H:%M")

        for rule in CONFIG.get("automations", []):
            rid = rule["id"]
            state = _get_rule_state(rid)

            if not rule.get("enabled", False):
                _AUTO_STATE[rid] = _new_rule_state()
                continue

            trigger_type = str(rule.get("trigger_type", "condition") or "condition").strip().lower()
            schedule = rule.get("schedule", {})
            condition = rule.get("condition", {})
            day_match = _day_match(schedule, now)
            trigger_matched = False
            current_value = state.get("last_current_value")
            state["last_day_match"] = day_match
            state["last_in_window"] = None

            if trigger_type == "compound":
                should_fire, fire_results, trigger_matched, current_value = _evaluate_compound_rule(rule, state, now)
                if should_fire:
                    state["last_triggered_at"] = now.isoformat()
                    state["last_trigger_value"] = current_value
                    trigger_names = "、".join(item.get("label") or item.get("key") or "触发条件" for item in fire_results)
                    add_log(-1, f"[automation] triggered: [{rule['name']}] ({trigger_names})")
                    _execute_rule_scene(rule, state)
                continue

            if trigger_type == "schedule":
                trigger_matched = day_match and _build_schedule_trigger(now, schedule, state)
                state["last_evaluated_at"] = now.isoformat()
                if state.get("last_error") == "invalid_schedule_time":
                    last_error_log_key = f"{now.strftime('%Y-%m-%d %H:%M')}|invalid_schedule"
                    if state.get("last_schedule_key") != last_error_log_key:
                        add_log(-1, f"[automation] invalid schedule time: [{rule['name']}] -> {schedule.get('time')}")
                        state["last_schedule_key"] = last_error_log_key
                elif state.get("last_error") == "schedule_missed_window":
                    stale_log_key = f"{state.get('last_schedule_key')}|stale_skip"
                    if state.get("_last_logged_skip_key") != stale_log_key:
                        add_log(
                            -1,
                            f"[automation] skipped stale schedule: [{rule['name']}] "
                            f"delay={round(float(state.get('last_schedule_delay_sec', 0.0) or 0.0), 1)}s",
                        )
                        state["_last_logged_skip_key"] = stale_log_key
            else:
                cond_match, current_value = _evaluate_condition(condition, state, now)
                if trigger_type == "condition":
                    trigger_matched = cond_match
                elif trigger_type == "mixed":
                    in_window, window_key, _, _ = _is_time_in_window(now, schedule)
                    in_window = bool(day_match and in_window)
                    state["last_in_window"] = in_window
                    _update_window_state(state, now, in_window, f"{now.strftime('%Y-%m-%d')}|{window_key}")
                    trigger_matched = cond_match and in_window
                    if not trigger_matched:
                        trigger_matched = _maybe_match_window_bootstrap(rule, state, now, cond_match, in_window, current_value)
                if not trigger_matched and condition.get("log_current_value", False):
                    add_log(-1, f"[automation] rule [{rule['name']}] current value: {current_value}")

                if trigger_matched:
                    extra_ok, extra_value = _evaluate_extra_condition(rule, now)
                    if not extra_ok:
                        trigger_matched = False
                        state["last_skip_reason"] = f"extra_condition_not_met:{extra_value}"

            state["last_trigger_matched"] = trigger_matched
            if trigger_matched and not state["latched"]:
                state["latched"] = True
                state["last_triggered_at"] = now.isoformat()
                state["last_trigger_value"] = current_value
                detail = ""
                if trigger_type == "schedule":
                    detail = f" ({_describe_schedule_trigger(state)})"
                add_log(-1, f"[automation] triggered: [{rule['name']}]{detail}")
                _execute_rule_scene(rule, state)
            elif not trigger_matched:
                state["latched"] = False

        time.sleep(1)
