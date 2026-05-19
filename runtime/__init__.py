def init_runtime():
    from .bootstrap import init_runtime as _init_runtime
    return _init_runtime()


def start_background_services():
    from .bootstrap import start_background_services as _start_background_services
    return _start_background_services()


def ensure_runtime_started():
    from .bootstrap import ensure_runtime_started as _ensure_runtime_started
    return _ensure_runtime_started()


def iter_background_services():
    from .bootstrap import iter_background_services as _iter_background_services
    return _iter_background_services()


def get_background_service_manifest():
    from .bootstrap import get_background_service_manifest as _get_background_service_manifest
    return _get_background_service_manifest()


def __getattr__(name):
    if name in {
        "BACKGROUND_SERVICES",
        "BackgroundService",
    }:
        from . import bootstrap
        return getattr(bootstrap, name)
    raise AttributeError(f"module 'runtime' has no attribute {name!r}")


__all__ = [
    "BACKGROUND_SERVICES",
    "BackgroundService",
    "ensure_runtime_started",
    "get_background_service_manifest",
    "init_runtime",
    "iter_background_services",
    "start_background_services",
]
