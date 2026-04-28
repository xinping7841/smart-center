PERMISSIONS = {
    "dashboard.view",
    "config.view",
    "door.view",
    "door.control",
    "hvac.view",
    "hvac.control",
    "light.view",
    "light.control",
    "power.view",
    "power.control",
    "meter.view",
    "meter.config",
    "control_center.view",
    "control_center.control",
    "control_center.config",
    "projector.view",
    "projector.control",
    "screen.view",
    "screen.control",
    "ups.view",
    "ups.control",
    "snmp.view",
    "sequencer.view",
    "sequencer.control",
    "server.view",
    "server.control",
    "automation.view",
    "automation.edit",
    "system.config",
    "auth.manage",
}


PERMISSION_CATALOG = {
    "dashboard.view": {"label": "主页总览", "kind": "view"},
    "config.view": {"label": "配置中心", "kind": "view"},
    "door.view": {"label": "门禁模块", "kind": "view"},
    "door.control": {"label": "门禁控制", "kind": "control"},
    "hvac.view": {"label": "空调模块", "kind": "view"},
    "hvac.control": {"label": "空调控制", "kind": "control"},
    "light.view": {"label": "灯光模块", "kind": "view"},
    "light.control": {"label": "灯光控制", "kind": "control"},
    "power.view": {"label": "强电模块", "kind": "view"},
    "power.control": {"label": "强电控制", "kind": "control"},
    "meter.view": {"label": "电表中心", "kind": "view"},
    "meter.config": {"label": "电表与主配置保存", "kind": "control"},
    "control_center.view": {"label": "协议控制中心", "kind": "view"},
    "control_center.control": {"label": "协议控制操作", "kind": "control"},
    "control_center.config": {"label": "协议控制配置", "kind": "control"},
    "projector.view": {"label": "投影机模块", "kind": "view"},
    "projector.control": {"label": "投影机控制", "kind": "control"},
    "screen.view": {"label": "幕布模块", "kind": "view"},
    "screen.control": {"label": "幕布控制", "kind": "control"},
    "ups.view": {"label": "UPS 模块", "kind": "view"},
    "ups.control": {"label": "UPS 控制", "kind": "control"},
    "snmp.view": {"label": "SNMP 模块", "kind": "view"},
    "sequencer.view": {"label": "时序电源", "kind": "view"},
    "sequencer.control": {"label": "时序电源控制", "kind": "control"},
    "server.view": {"label": "服务器看板", "kind": "view"},
    "server.control": {"label": "服务器控制", "kind": "control"},
    "automation.view": {"label": "自动化模块", "kind": "view"},
    "automation.edit": {"label": "自动化编辑", "kind": "control"},
    "system.config": {"label": "系统级配置与扫描", "kind": "control"},
    "auth.manage": {"label": "用户与权限管理", "kind": "control"},
}


PERMISSION_COMPATIBILITY = {
    "control_center.view": {"light.view"},
    "control_center.control": {"light.control"},
    "control_center.config": {"meter.config"},
    "meter.config": {"control_center.config"},
}


ROLE_PERMISSIONS = {
    "guest": set(),
    "admin": set(PERMISSIONS),
    "regular": {
        "dashboard.view",
        "config.view",
        "door.view",
        "door.control",
        "hvac.view",
        "hvac.control",
        "light.view",
        "light.control",
        "power.view",
        "power.control",
        "meter.view",
        "control_center.view",
        "control_center.control",
        "projector.view",
        "projector.control",
        "screen.view",
        "screen.control",
        "ups.view",
        "ups.control",
        "snmp.view",
        "sequencer.view",
        "sequencer.control",
        "server.view",
        "server.control",
        "automation.view",
        "automation.edit",
    },
    "operator": {
        "dashboard.view",
        "config.view",
        "door.view",
        "door.control",
        "hvac.view",
        "hvac.control",
        "light.view",
        "light.control",
        "power.view",
        "power.control",
        "meter.view",
        "control_center.view",
        "control_center.control",
        "projector.view",
        "projector.control",
        "screen.view",
        "screen.control",
        "ups.view",
        "ups.control",
        "snmp.view",
        "sequencer.view",
        "sequencer.control",
        "server.view",
        "server.control",
        "automation.view",
        "automation.edit",
    },
    "viewer": {
        "dashboard.view",
        "config.view",
        "door.view",
        "hvac.view",
        "light.view",
        "power.view",
        "meter.view",
        "control_center.view",
        "projector.view",
        "screen.view",
        "ups.view",
        "snmp.view",
        "sequencer.view",
        "server.view",
        "automation.view",
    },
}


def get_role_permissions(role: str) -> set[str]:
    role_key = str(role or "guest").strip().lower()
    if role_key in {"viewer", "operator"}:
        role_key = "regular"
    return set(ROLE_PERMISSIONS.get(role_key, set()))


def normalize_role(role: str) -> str:
    role_key = str(role or "guest").strip().lower()
    if role_key in {"viewer", "operator"}:
        return "regular"
    return role_key or "guest"


def get_permission_kind(permission: str) -> str:
    return str(PERMISSION_CATALOG.get(str(permission or "").strip(), {}).get("kind") or "view")


def is_control_permission(permission: str) -> bool:
    return get_permission_kind(permission) == "control"


def has_permission(role: str, permission: str, explicit_permissions=None) -> bool:
    permission_key = str(permission or "").strip()
    granted = set(explicit_permissions) if explicit_permissions is not None else get_role_permissions(role)
    if permission_key in granted:
        return True
    for alias in PERMISSION_COMPATIBILITY.get(permission_key, set()):
        if alias in granted:
            return True
    return False
