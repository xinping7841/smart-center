import threading
import time


_LOCK = threading.Lock()
_ACTIVE_OPERATIONS: dict[str, dict] = {}


def acquire_operation_lock(resource_key: str, owner: str, action: str, timeout_sec: float = 2.5):
    now = time.time()
    with _LOCK:
        current = _ACTIVE_OPERATIONS.get(resource_key)
        if current:
            expires_at = float(current.get("expires_at", 0) or 0)
            if expires_at > now and str(current.get("owner") or "") != str(owner or ""):
                return False, {
                    "resource": resource_key,
                    "owner": current.get("owner"),
                    "action": current.get("action"),
                    "expires_at": expires_at,
                }
        _ACTIVE_OPERATIONS[resource_key] = {
            "owner": owner,
            "action": action,
            "expires_at": now + max(0.5, float(timeout_sec or 2.5)),
        }
        return True, _ACTIVE_OPERATIONS[resource_key]


def release_operation_lock(resource_key: str, owner: str | None = None):
    with _LOCK:
        current = _ACTIVE_OPERATIONS.get(resource_key)
        if not current:
            return
        if owner and str(current.get("owner") or "") != str(owner):
            return
        _ACTIVE_OPERATIONS.pop(resource_key, None)
