"""Request hooks for authentication context, static caching, and gzip responses."""

# AI_MODULE: app_request_hooks
# AI_PURPOSE: Own request-scoped user loading, static cache headers, and response compression.
# AI_BOUNDARY: Keep business API behavior in api/*; this module only handles cross-cutting HTTP behavior.
# AI_DATA_FLOW: Flask request -> auth context/static shortcut -> route -> cache and gzip headers.
# AI_RISK: High. Hook mistakes can break auth, agent reporting, or dashboard asset loading.
# AI_COMPAT: Agent endpoints stay guest-accessible; pages keep no-store cache headers.
# AI_SEARCH_KEYWORDS: before_request, after_request, gzip, static cache, auth context.

from __future__ import annotations

import gzip
import mimetypes
import os
from urllib.parse import urlparse

from flask import Flask, g, request, send_from_directory

from auth import get_current_user, set_default_user, set_guest_user

_COMPRESSIBLE_MIMETYPES = {
    "application/javascript",
    "application/json",
    "application/xml",
    "text/css",
    "text/html",
    "text/javascript",
    "text/plain",
    "text/xml",
}
_GZIP_MIN_BYTES = int(os.environ.get("SMART_POWER_GZIP_MIN_BYTES", "1024"))
_GZIP_LEVEL = max(1, min(9, int(os.environ.get("SMART_POWER_GZIP_LEVEL", "5"))))
_STATIC_MAX_AGE = int(os.environ.get("SMART_CENTER_STATIC_MAX_AGE", "31536000"))


def install_request_hooks(app: Flask) -> None:
    @app.before_request
    def load_request_user():
        endpoint = str(request.endpoint or "")
        path = urlparse(request.path or "").path
        if endpoint == "static" or path.startswith("/static/"):
            g.current_user = set_guest_user()
            return _maybe_send_precompressed_static(app, path)
        if endpoint == "server.report_data" or path in {"/report", "/agent/config"} or path.startswith("/agent/"):
            g.current_user = set_guest_user()
            return None
        g.current_user = set_default_user()
        return None

    @app.context_processor
    def inject_auth_context():
        return {"current_user": get_current_user()}

    @app.after_request
    def apply_cache_and_compression_headers(response):
        path = urlparse(request.path or "").path
        if path.startswith("/static/"):
            response.headers["Cache-Control"] = f"public, max-age={_STATIC_MAX_AGE}, immutable"
            response.headers.pop("Pragma", None)
            response.headers.pop("Expires", None)
            response.headers.pop("Set-Cookie", None)
            if response.headers.get("Content-Encoding", "").lower() == "gzip":
                _add_vary_accept_encoding(response)
            else:
                response.headers.pop("Vary", None)
        elif path == "/" or path.startswith("/config") or path.startswith("/login"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return _maybe_gzip_response(response)


def _add_vary_accept_encoding(response) -> None:
    vary = response.headers.get("Vary", "")
    parts = [item.strip() for item in vary.split(",") if item.strip()]
    if not any(item.lower() == "accept-encoding" for item in parts):
        parts.append("Accept-Encoding")
    response.headers["Vary"] = ", ".join(parts)


def _maybe_gzip_response(response):
    if request.method == "HEAD":
        return response
    if "gzip" not in request.headers.get("Accept-Encoding", "").lower():
        return response
    if response.status_code < 200 or response.status_code >= 300:
        return response
    if response.direct_passthrough or response.is_streamed:
        return response
    if response.headers.get("Content-Encoding"):
        return response
    if response.mimetype not in _COMPRESSIBLE_MIMETYPES:
        return response
    payload = response.get_data()
    if len(payload) < _GZIP_MIN_BYTES:
        return response
    compressed = gzip.compress(payload, compresslevel=_GZIP_LEVEL)
    if len(compressed) >= len(payload):
        return response
    response.set_data(compressed)
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = str(len(compressed))
    response.headers.pop("ETag", None)
    _add_vary_accept_encoding(response)
    return response


def _maybe_send_precompressed_static(app: Flask, path: str):
    if request.method not in {"GET", "HEAD"}:
        return None
    if "gzip" not in request.headers.get("Accept-Encoding", "").lower():
        return None
    if not path.startswith("/static/"):
        return None
    filename = path.removeprefix("/static/").lstrip("/")
    if not filename or "\x00" in filename:
        return None
    static_dir = app.static_folder
    source_path = os.path.join(static_dir, filename)
    gzip_path = f"{source_path}.gz"
    if not os.path.isfile(source_path) or not os.path.isfile(gzip_path):
        return None
    mimetype, _ = mimetypes.guess_type(source_path)
    response = send_from_directory(
        static_dir,
        f"{filename}.gz",
        mimetype=mimetype or "application/octet-stream",
        conditional=True,
        max_age=_STATIC_MAX_AGE,
    )
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Disposition"] = f"inline; filename={os.path.basename(filename)}"
    _add_vary_accept_encoding(response)
    return response
