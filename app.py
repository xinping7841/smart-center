import gzip
import mimetypes
import os
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, g, request, send_from_directory
from werkzeug.serving import BaseWSGIServer, WSGIRequestHandler

from api.auth_api import bp as auth_api_bp
from api.apple_audio import bp as apple_audio_bp
from api.automation import bp as automation_bp
from api.dashboard import bp as dashboard_bp
from api.door import bp as door_bp
from api.control_center import bp as control_center_bp
from api.driver_hub import bp as driver_hub_bp
from api.env import bp as env_bp
from api.hvac import bp as hvac_bp
from api.hy_edge import bp as hy_edge_bp
from api.light import bp as light_bp
from api.m32r import bp as m32r_bp
from api.power import bp as power_bp
from api.proxy import bp as proxy_bp
from api.projector import bp as projector_bp
from api.screen import bp as screen_bp
from api.sequencer import bp as sequencer_bp
from api.snmp import bp as snmp_bp
from api.nvr import bp as nvr_bp
from api.server import bp as server_bp
from api.ups import bp as ups_bp
from api.universal import bp as universal_bp
from auth import get_current_user, set_default_user, set_guest_user
from runtime import ensure_runtime_started, init_runtime, start_background_services

# Keep FFmpeg transport selection dynamic in the door camera module.
# Some cameras only become stable over TCP, while others still need UDP fallback.
os.environ.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SMART_POWER_SECRET_KEY", "smart-power-monitor-dev-secret")
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("SMART_POWER_MAX_CONTENT_LENGTH", 524288))
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = int(os.environ.get("SMART_CENTER_STATIC_MAX_AGE", "31536000"))

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
_HTTP_ACCESS_LOG = str(os.environ.get("SMART_CENTER_HTTP_ACCESS_LOG", "")).strip().lower() in {"1", "true", "yes", "on"}
_STATIC_MAX_AGE = int(os.environ.get("SMART_CENTER_STATIC_MAX_AGE", "31536000"))


def _add_vary_accept_encoding(response):
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


def _maybe_send_precompressed_static(path):
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


@app.before_request
def load_request_user():
    endpoint = str(request.endpoint or "")
    path = urlparse(request.path or "").path
    if endpoint == "static" or path.startswith("/static/"):
        g.current_user = set_guest_user()
        return _maybe_send_precompressed_static(path)
    if endpoint == "server.report_data" or path in {"/report", "/agent/config"} or path.startswith("/agent/"):
        g.current_user = set_guest_user()
        return
    g.current_user = set_default_user()


@app.context_processor
def inject_auth_context():
    return {"current_user": get_current_user()}


@app.after_request
def disable_page_cache(response):
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


app.register_blueprint(power_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(auth_api_bp)
app.register_blueprint(apple_audio_bp)
app.register_blueprint(light_bp)
app.register_blueprint(door_bp)
app.register_blueprint(control_center_bp)
app.register_blueprint(driver_hub_bp)
app.register_blueprint(server_bp)
app.register_blueprint(proxy_bp)
app.register_blueprint(projector_bp)
app.register_blueprint(screen_bp)
app.register_blueprint(universal_bp)
app.register_blueprint(env_bp)
app.register_blueprint(hy_edge_bp)
app.register_blueprint(snmp_bp)
app.register_blueprint(nvr_bp)
app.register_blueprint(automation_bp)
app.register_blueprint(hvac_bp)
app.register_blueprint(sequencer_bp)
app.register_blueprint(ups_bp)
app.register_blueprint(m32r_bp)


class QuietWSGIRequestHandler(WSGIRequestHandler):
    def log_request(self, code="-", size="-"):
        if _HTTP_ACCESS_LOG:
            super().log_request(code, size)
            return
        try:
            status_code = int(str(code).split()[0])
        except Exception:
            status_code = 0
        if status_code >= 400:
            super().log_request(code, size)


class ThreadPoolWSGIServer(BaseWSGIServer):
    multithread = True
    daemon_threads = True

    def __init__(
        self,
        host,
        port,
        wsgi_app,
        *,
        max_workers=16,
        max_pending=32,
        request_handler=None,
        passthrough_errors=False,
    ):
        self.max_workers = max(2, int(max_workers))
        self.max_pending = max(0, int(max_pending))
        self._request_slots = None
        total_slots = self.max_workers + self.max_pending
        self._request_slots = __import__("threading").BoundedSemaphore(total_slots)
        self.request_queue_size = max(16, total_slots)
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="spm-http",
        )
        super().__init__(
            host,
            port,
            wsgi_app,
            handler=request_handler or QuietWSGIRequestHandler,
            passthrough_errors=passthrough_errors,
        )

    def process_request(self, request, client_address):
        if not self._request_slots.acquire(blocking=False):
            self._reject_busy_request(request, client_address)
            return
        try:
            self._executor.submit(self._process_request_in_pool, request, client_address)
        except Exception:
            self._request_slots.release()
            self.handle_error(request, client_address)
            self.shutdown_request(request)

    def _process_request_in_pool(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            try:
                self.shutdown_request(request)
            finally:
                self._request_slots.release()

    def _reject_busy_request(self, request, client_address):
        body = b"Service temporarily busy"
        try:
            request.sendall(
                b"HTTP/1.1 503 Service Unavailable\r\n"
                b"Connection: close\r\n"
                b"Content-Type: text/plain; charset=utf-8\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
                + body
            )
        except OSError:
            pass
        finally:
            self.shutdown_request(request)
        try:
            host, port = client_address
        except Exception:
            host, port = "<unknown>", 0
        self.log("warning", "HTTP worker pool saturated, rejected request from %s:%s", host, port)

    def server_close(self):
        try:
            super().server_close()
        finally:
            self._executor.shutdown(wait=False, cancel_futures=True)


def serve_http(flask_app):
    host = os.environ.get("SMART_POWER_HTTP_HOST", "0.0.0.0")
    port = int(os.environ.get("SMART_POWER_HTTP_PORT", "6899"))
    cpu_count = os.cpu_count() or 4
    default_workers = min(96, max(24, cpu_count * 4))
    default_pending = default_workers * 2
    max_workers = int(os.environ.get("SMART_POWER_HTTP_MAX_WORKERS", str(default_workers)))
    max_pending = int(os.environ.get("SMART_POWER_HTTP_MAX_PENDING", str(default_pending)))
    server = ThreadPoolWSGIServer(
        host,
        port,
        flask_app,
        max_workers=max_workers,
        max_pending=max_pending,
    )
    server.log_startup()
    server.log(
        "info",
        " * HTTP worker pool: %s workers, %s pending slots",
        max_workers,
        max_pending,
    )
    server.serve_forever()


# Ensure background pollers are available under both `python app.py`
# and WSGI/embedded launch modes.
ensure_runtime_started()


if __name__ == "__main__":
    print(">>> [startup] 1/3 initialize runtime")
    init_runtime()
    print(">>> [startup] 2/3 start background services")
    start_background_services()
    print(">>> [startup] 3/3 web server listening on :6899")
    serve_http(app)
