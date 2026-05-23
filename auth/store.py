import json
import hashlib
import hmac
import secrets
from pathlib import Path
from typing import Any

from .models import build_identity
from .permissions import get_role_permissions, normalize_role
from paths import AUTH_USERS_FILE as AUTH_USERS_FILE_PATH


AUTH_USERS_FILE = Path(AUTH_USERS_FILE_PATH)


DEFAULT_USERS = [
    {
        "username": "local-admin",
        "display_name": "Local Admin",
        "role": "admin",
        "account_category": "admin",
        "enabled": True,
        "password": "admin123",
    }
]

PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 120000


def _ensure_parent_dir() -> None:
    AUTH_USERS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _normalize_user(item: dict[str, Any]) -> dict[str, Any]:
    identity = build_identity(item)
    explicit_permissions = item.get("permissions") if "permissions" in item else None
    permissions = set(explicit_permissions if explicit_permissions is not None else get_role_permissions(identity.role))
    if identity.role == "admin" or str(item.get("account_category") or "").strip().lower() == "admin":
        permissions.update(get_role_permissions("admin"))
    if permissions.intersection({"meter.config", "system.config", "auth.manage"}) or identity.role in {"admin", "regular"}:
        permissions.add("config.view")
    control_schedule = item.get("control_schedule", {}) if isinstance(item.get("control_schedule", {}), dict) else {}
    temporary_access = item.get("temporary_access", {}) if isinstance(item.get("temporary_access", {}), dict) else {}
    account_flags = item.get("account_flags", {}) if isinstance(item.get("account_flags", {}), dict) else {}
    account_category = str(item.get("account_category") or ("admin" if identity.role == "admin" else "regular")).strip().lower() or "regular"
    return {
        "username": identity.username,
        "display_name": identity.display_name,
        "role": normalize_role(identity.role),
        "account_category": account_category,
        "enabled": bool(identity.enabled),
        "password": prepare_password_for_storage(item.get("password")),
        "permissions": sorted(permissions),
        "control_schedule": control_schedule,
        "temporary_access": temporary_access,
        "account_flags": account_flags,
    }


def is_password_hashed(password: Any) -> bool:
    raw = str(password or "")
    return raw.startswith(f"{PASSWORD_SCHEME}$")


def hash_password(password: str) -> str:
    raw = str(password or "")
    if not raw:
        return ""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        raw.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    ).hex()
    return f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored_password: Any) -> bool:
    raw = str(password or "")
    stored = str(stored_password or "")
    if not stored:
        return False
    if not is_password_hashed(stored):
        return hmac.compare_digest(stored, raw)
    try:
        _, iterations_raw, salt, expected_digest = stored.split("$", 3)
        iterations = int(iterations_raw)
    except ValueError:
        return False
    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        raw.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(actual_digest, expected_digest)


def prepare_password_for_storage(password: Any) -> str:
    raw = str(password or "")
    if not raw:
        return ""
    if is_password_hashed(raw):
        return raw
    return hash_password(raw)


def load_users() -> list[dict[str, Any]]:
    _ensure_parent_dir()
    if not AUTH_USERS_FILE.exists():
        save_users(DEFAULT_USERS)
        return [_normalize_user(item) for item in DEFAULT_USERS]
    try:
        data = json.loads(AUTH_USERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        save_users(DEFAULT_USERS)
        return [_normalize_user(item) for item in DEFAULT_USERS]

    if not isinstance(data, list) or not data:
        save_users(DEFAULT_USERS)
        return [_normalize_user(item) for item in DEFAULT_USERS]
    normalized = [_normalize_user(item) for item in data if isinstance(item, dict)]
    if normalized != data:
        save_users(normalized)
    return normalized


def save_users(users: list[dict[str, Any]]) -> list[dict[str, Any]]:
    _ensure_parent_dir()
    normalized = [_normalize_user(item) for item in users if isinstance(item, dict)]
    AUTH_USERS_FILE.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def list_users() -> list[dict[str, Any]]:
    return load_users()


def find_user(username: str) -> dict[str, Any] | None:
    key = str(username or "").strip().lower()
    if not key:
        return None
    for user in load_users():
        if str(user.get("username") or "").strip().lower() == key:
            return user
    return None


def upsert_user(user_payload: dict[str, Any]) -> dict[str, Any]:
    users = load_users()
    normalized = _normalize_user(user_payload)
    replaced = False
    for idx, user in enumerate(users):
        if str(user.get("username") or "").strip().lower() == normalized["username"].lower():
            if not normalized.get("password"):
                normalized["password"] = str(user.get("password") or "")
            users[idx] = normalized
            replaced = True
            break
    if not replaced:
        users.append(normalized)
    save_users(users)
    return normalized


def delete_user(username: str) -> bool:
    key = str(username or "").strip().lower()
    if not key or key == "local-admin":
        return False
    users = load_users()
    kept = [user for user in users if str(user.get("username") or "").strip().lower() != key]
    if len(kept) == len(users):
        return False
    save_users(kept)
    return True
