"""Runtime service bootstrap exports.

The Flask entrypoint imports these names from ``runtime`` directly. Keeping
this small package initializer in Git prevents clean release clones from
falling back to an empty namespace package.
"""

from .bootstrap import (
    ensure_runtime_started,
    get_background_service_manifest,
    init_runtime,
    iter_background_services,
    iter_background_targets,
    start_background_services,
)

__all__ = [
    "ensure_runtime_started",
    "get_background_service_manifest",
    "init_runtime",
    "iter_background_services",
    "iter_background_targets",
    "start_background_services",
]
