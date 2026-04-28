from functools import wraps

from flask import jsonify, redirect, request, url_for

from .permissions import has_permission
from .policy import resolve_permission_grant
from .session import get_current_user


def _permission_error_message(error_code: str, permission_state=None) -> str:
    permission_state = permission_state if isinstance(permission_state, dict) else {}
    reason = str(permission_state.get("reason") or "").strip()
    if error_code == "login_required":
        return "当前会话未登录，请先登录后再操作"
    if error_code == "account_disabled":
        return "当前账号已停用"
    if error_code == "permission_denied":
        return "当前账号没有此功能权限"
    if error_code == "permission_time_restricted":
        reason_map = {
            "account_frozen": "当前账号已冻结",
            "account_temporarily_disabled": "当前账号已被临时停用",
            "account_temporarily_disabled_until": "当前账号处于临时停用时段",
            "temporary_control_blocked": "当前账号的控制权限已被临时关闭",
            "outside_control_schedule": "当前不在允许控制的时间段内",
            "permission_not_granted": "当前账号没有此功能权限",
        }
        return reason_map.get(reason, "当前时段不允许执行此操作")
    return "操作被拒绝"


def _should_redirect_to_login() -> bool:
    if request.method != "GET":
        return False
    if request.path.startswith("/api/"):
        return False
    accept = (request.headers.get("Accept") or "").lower()
    if "application/json" in accept and "text/html" not in accept:
        return False
    return not accept or "text/html" in accept or "*/*" in accept


def require_permission(permission: str):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if user.username == "guest":
                if _should_redirect_to_login():
                    return redirect(url_for("auth_api.login_page", next=request.path))
                return jsonify(
                    {
                        "ok": False,
                        "error": "login_required",
                        "permission": permission,
                        "msg": _permission_error_message("login_required"),
                    }
                ), 401
            if not user.enabled:
                return jsonify(
                    {
                        "ok": False,
                        "error": "account_disabled",
                        "msg": _permission_error_message("account_disabled"),
                    }
                ), 403
            if not has_permission(user.role, permission, user.permissions):
                return jsonify(
                    {
                        "ok": False,
                        "error": "permission_denied",
                        "permission": permission,
                        "role": user.role,
                        "msg": _permission_error_message("permission_denied"),
                    }
                ), 403
            permission_state = resolve_permission_grant(user, permission)
            if not permission_state.get("allowed", False):
                return jsonify(
                    {
                        "ok": False,
                        "error": "permission_time_restricted",
                        "permission": permission,
                        "role": user.role,
                        "reason": permission_state.get("reason"),
                        "msg": _permission_error_message("permission_time_restricted", permission_state),
                    }
                ), 403
            return func(*args, **kwargs)

        return wrapper

    return decorator
