import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def _resolve_env_path(*env_names: str, default: Path) -> Path:
    raw_value = ""
    for env_name in env_names:
        raw_value = str(os.environ.get(env_name, "") or "").strip()
        if raw_value:
            break
    candidate = Path(raw_value).expanduser() if raw_value else Path(default)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_parent_dir(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


DATA_DIR = _resolve_env_path(
    "SMART_CENTER_DATA_DIR",
    "SMART_POWER_DATA_DIR",
    default=PROJECT_ROOT,
)
RUNTIME_DIR = _resolve_env_path(
    "SMART_CENTER_RUNTIME_DIR",
    default=DATA_DIR / "runtime",
)
REPORTS_DIR = _resolve_env_path(
    "SMART_CENTER_REPORTS_DIR",
    default=DATA_DIR / "reports",
)

CONFIG_FILE = _resolve_env_path(
    "SMART_CENTER_CONFIG_FILE",
    default=DATA_DIR / "config.json",
)
DB_FILE = _resolve_env_path(
    "SMART_CENTER_DB_FILE",
    default=DATA_DIR / "monitor.db",
)
ENERGY_LOG_FILE = _resolve_env_path(
    "SMART_CENTER_ENERGY_LOG_FILE",
    default=DATA_DIR / "energy_log.json",
)
OPERATION_LOG_FILE = _resolve_env_path(
    "SMART_CENTER_OPERATION_LOG_FILE",
    default=DATA_DIR / "operation_logs.json",
)
AUDIT_LOG_FILE = _resolve_env_path(
    "SMART_CENTER_AUDIT_LOG_FILE",
    default=DATA_DIR / "audit_logs.json",
)
AUTH_USERS_FILE = _resolve_env_path(
    "SMART_CENTER_AUTH_USERS_FILE",
    default=RUNTIME_DIR / "auth_users.json",
)
PROJECTOR_BRANDS_FILE = _resolve_env_path(
    "SMART_CENTER_PROJECTOR_BRANDS_FILE",
    default=PROJECT_ROOT / "projector_brands.json",
)


def resolve_configured_path(raw_value, default_relative: str = "", base_dir: Path | None = None) -> Path:
    text = str(raw_value or "").strip().replace("\\", "/")
    if not text:
        text = default_relative
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = (base_dir or DATA_DIR) / candidate
    return candidate.resolve()


def resolve_report_dir(raw_value=None) -> Path:
    return resolve_configured_path(raw_value, "reports/energy", DATA_DIR)


def ensure_runtime_layout() -> None:
    ensure_directory(DATA_DIR)
    ensure_directory(RUNTIME_DIR)
    ensure_directory(REPORTS_DIR)
    ensure_parent_dir(CONFIG_FILE)
    ensure_parent_dir(DB_FILE)
    ensure_parent_dir(ENERGY_LOG_FILE)
    ensure_parent_dir(OPERATION_LOG_FILE)
    ensure_parent_dir(AUDIT_LOG_FILE)
    ensure_parent_dir(AUTH_USERS_FILE)


ensure_runtime_layout()
