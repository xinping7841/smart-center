from dataclasses import dataclass, field
from typing import Dict, List

from .permissions import get_role_permissions, normalize_role


@dataclass
class UserIdentity:
    username: str
    role: str = "regular"
    display_name: str = ""
    enabled: bool = True
    permissions: List[str] = field(default_factory=list)
    account_category: str = "regular"
    control_schedule: Dict[str, object] = field(default_factory=dict)
    temporary_access: Dict[str, object] = field(default_factory=dict)
    account_flags: Dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, object]:
        explicit_permissions = self.permissions if self.permissions is not None else get_role_permissions(self.role)
        return {
            "username": self.username,
            "role": self.role,
            "display_name": self.display_name or self.username,
            "enabled": bool(self.enabled),
            "permissions": sorted(set(explicit_permissions)),
            "account_category": self.account_category,
            "control_schedule": self.control_schedule if isinstance(self.control_schedule, dict) else {},
            "temporary_access": self.temporary_access if isinstance(self.temporary_access, dict) else {},
            "account_flags": self.account_flags if isinstance(self.account_flags, dict) else {},
        }


def build_identity(payload: Dict[str, object] | None = None) -> UserIdentity:
    payload = payload or {}
    username = str(payload.get("username") or "guest").strip() or "guest"
    default_role = "guest" if username == "guest" else "regular"
    role = normalize_role(str(payload.get("role") or default_role).strip().lower() or default_role)
    explicit_permissions = payload.get("permissions") if "permissions" in payload else None
    account_category = str(payload.get("account_category") or ("admin" if role == "admin" else "regular")).strip().lower() or "regular"
    return UserIdentity(
        username=username,
        role=role,
        display_name=str(payload.get("display_name") or payload.get("username") or "Guest").strip() or "Guest",
        enabled=bool(payload.get("enabled", True)),
        permissions=sorted(set(explicit_permissions if explicit_permissions is not None else get_role_permissions(role))),
        account_category=account_category,
        control_schedule=payload.get("control_schedule", {}) if isinstance(payload.get("control_schedule", {}), dict) else {},
        temporary_access=payload.get("temporary_access", {}) if isinstance(payload.get("temporary_access", {}), dict) else {},
        account_flags=payload.get("account_flags", {}) if isinstance(payload.get("account_flags", {}), dict) else {},
    )
