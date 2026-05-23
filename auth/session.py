import os

from flask import g, session

from config import CONFIG

from .models import UserIdentity, build_identity
from .store import find_user, list_users


SESSION_USER_KEY = "auth_user"
SESSION_MANUAL_LOGOUT_KEY = "auth_manual_logout"


def _guest_payload() -> dict:
    return {
        "username": "guest",
        "display_name": "Guest",
        "role": "guest",
        "account_category": "guest",
        "enabled": True,
        "permissions": [],
    }


def get_current_user() -> UserIdentity:
    cached = getattr(g, "_auth_user", None)
    if cached is not None:
        return cached
    user = build_identity(session.get(SESSION_USER_KEY))
    g._auth_user = user
    return user


def login_user(user_payload: dict) -> UserIdentity:
    user = build_identity(user_payload)
    session[SESSION_USER_KEY] = user.as_dict()
    session.pop(SESSION_MANUAL_LOGOUT_KEY, None)
    g._auth_user = user
    return user


def _clear_session_user(manual_logout: bool = False) -> None:
    session.pop(SESSION_USER_KEY, None)
    if manual_logout:
        session[SESSION_MANUAL_LOGOUT_KEY] = True
    else:
        session.pop(SESSION_MANUAL_LOGOUT_KEY, None)
    if hasattr(g, "_auth_user"):
        delattr(g, "_auth_user")


def logout_user() -> None:
    _clear_session_user(manual_logout=True)


def clear_manual_logout_flag() -> None:
    session.pop(SESSION_MANUAL_LOGOUT_KEY, None)


def set_guest_user() -> UserIdentity:
    guest_user = build_identity(_guest_payload())
    g._auth_user = guest_user
    return guest_user


def _resolve_auth_settings() -> dict:
    auth_settings = CONFIG.get("auth_settings", {})
    if isinstance(auth_settings, dict):
        return auth_settings
    return {}


def _auto_login_enabled() -> bool:
    env_value = str(os.environ.get("SMART_POWER_AUTO_LOGIN_ADMIN", "")).strip().lower()
    if env_value:
        return env_value not in {"0", "false", "off", "no"}
    return bool(_resolve_auth_settings().get("auto_login_default_admin", True))


def _is_admin_user(user: dict | None) -> bool:
    if not isinstance(user, dict):
        return False
    return bool(user.get("enabled", True)) and (
        str(user.get("role") or "").strip().lower() == "admin"
        or str(user.get("account_category") or "").strip().lower() == "admin"
    )


def _find_default_admin_user() -> dict | None:
    auth_settings = _resolve_auth_settings()
    preferred_username = str(auth_settings.get("default_admin_username") or "local-admin").strip()
    if preferred_username:
        preferred_user = find_user(preferred_username)
        if _is_admin_user(preferred_user):
            return preferred_user
    for user in list_users():
        if _is_admin_user(user):
            return user
    return None


def set_default_user() -> UserIdentity:
    if SESSION_USER_KEY in session:
        session_user = session.get(SESSION_USER_KEY) or {}
        stored_user = find_user(session_user.get("username"))
        if stored_user:
            return login_user(stored_user)
        _clear_session_user(manual_logout=False)
    if not session.get(SESSION_MANUAL_LOGOUT_KEY) and _auto_login_enabled():
        default_admin = _find_default_admin_user()
        if default_admin:
            return login_user(default_admin)
    return set_guest_user()
