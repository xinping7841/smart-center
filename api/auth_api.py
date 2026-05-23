from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from audit import load_audit_logs, log_audit_event
from auth import clear_manual_logout_flag, get_current_user, login_user, logout_user, require_permission
from auth.store import delete_user, find_user, list_users, upsert_user, verify_password
from config import CONFIG

bp = Blueprint("auth_api", __name__)


def _safe_user_view(user: dict) -> dict:
    return {
        "username": user.get("username"),
        "display_name": user.get("display_name"),
        "role": user.get("role"),
        "account_category": user.get("account_category", "regular"),
        "enabled": bool(user.get("enabled", True)),
        "permissions": user.get("permissions", []),
        "control_schedule": user.get("control_schedule", {}),
        "temporary_access": user.get("temporary_access", {}),
        "account_flags": user.get("account_flags", {}),
    }


def _require_admin_user():
    current = get_current_user()
    if str(current.role or "").lower() != "admin" or not current.enabled:
        return None, (jsonify({"ok": False, "msg": "仅管理员可执行此操作"}), 403)
    user = find_user(current.username)
    if not user:
        return None, (jsonify({"ok": False, "msg": "当前管理员账号不存在"}), 403)
    return user, None


def _confirm_admin_password_from_payload(data):
    admin_user, error = _require_admin_user()
    if error:
        return None, error
    password = str((data or {}).get("admin_password") or "")
    if not password:
        return None, (jsonify({"ok": False, "msg": "请输入管理员二次密码"}), 400)
    if not verify_password(password, admin_user.get("password")):
        log_audit_event(
            "auth.confirm_admin_password",
            target=admin_user.get("username"),
            detail={"username": admin_user.get("username"), "error": "invalid_password"},
            status="error",
        )
        return None, (jsonify({"ok": False, "msg": "管理员二次密码错误"}), 401)
    return admin_user, None


@bp.route("/login")
def login_page():
    current = get_current_user()
    next_url = request.args.get("next") or "/"
    if current.username not in ("", "guest") and current.enabled:
        return redirect(next_url if str(next_url).startswith("/") else url_for("power.index"))
    return render_template("login.html", login_page_text=CONFIG.get("login_page_text", {}))


@bp.route("/api/auth/me")
def api_auth_me():
    user = get_current_user()
    return jsonify({"ok": True, "user": user.as_dict()})


@bp.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    data = request.json or {}
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    remember = bool(data.get("remember"))
    user = find_user(username)

    if not user or not verify_password(password, user.get("password")):
        log_audit_event(
            "auth.login",
            target=username,
            detail={"username": username, "error": "invalid_credentials"},
            status="error",
        )
        return jsonify({"ok": False, "msg": "用户名或密码错误"}), 401
    if not bool(user.get("enabled", True)):
        log_audit_event(
            "auth.login",
            target=username,
            detail={"username": username, "error": "account_disabled"},
            status="error",
        )
        return jsonify({"ok": False, "msg": "账号已停用"}), 403

    clear_manual_logout_flag()
    identity = login_user(user)
    session.permanent = remember
    response = jsonify({"ok": True, "user": identity.as_dict()})
    log_audit_event("auth.login", target=username, detail={"username": username, "role": user.get("role")})
    return response


@bp.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    user = get_current_user()
    logout_user()
    response = jsonify({"ok": True})
    log_audit_event("auth.logout", target=user.username, detail={"username": user.username})
    return response


@bp.route("/api/auth/confirm-admin-password", methods=["POST"])
@require_permission("auth.manage")
def api_confirm_admin_password():
    _, error = _confirm_admin_password_from_payload(request.json or {})
    if error:
        return error
    return jsonify({"ok": True})


@bp.route("/api/auth/users")
@require_permission("auth.manage")
def api_auth_users():
    return jsonify({"ok": True, "items": [_safe_user_view(user) for user in list_users()]})


@bp.route("/api/auth/users", methods=["POST"])
@require_permission("auth.manage")
def api_auth_users_upsert():
    data = request.json or {}
    username = str(data.get("username") or "").strip()
    if not username:
        return jsonify({"ok": False, "msg": "用户名不能为空"}), 400

    admin_user, error = _confirm_admin_password_from_payload(data)
    if error:
        return error

    saved = upsert_user(data)
    log_audit_event(
        "auth.user.save",
        target=username,
        detail={
            "username": username,
            "role": saved.get("role"),
            "account_category": saved.get("account_category"),
            "enabled": saved.get("enabled"),
            "permissions": saved.get("permissions", []),
            "operator": admin_user.get("username"),
        },
    )
    return jsonify({"ok": True, "item": _safe_user_view(saved)})


@bp.route("/api/auth/users/<username>", methods=["DELETE"])
@require_permission("auth.manage")
def api_auth_users_delete(username):
    data = request.json or {}
    admin_user, error = _confirm_admin_password_from_payload(data)
    if error:
        return error

    ok = delete_user(username)
    if not ok:
        log_audit_event(
            "auth.user.delete",
            target=username,
            detail={"username": username, "error": "delete_failed", "operator": admin_user.get("username")},
            status="error",
        )
        return jsonify({"ok": False, "msg": "删除失败，或该账号不允许删除"}), 400

    log_audit_event(
        "auth.user.delete",
        target=username,
        detail={"username": username, "operator": admin_user.get("username")},
    )
    return jsonify({"ok": True})


@bp.route("/api/auth/audit")
@require_permission("auth.manage")
def api_auth_audit():
    return jsonify({"ok": True, "items": load_audit_logs()})
