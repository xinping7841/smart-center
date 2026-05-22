"""Thread-pooled HTTP server wrapper for Smart Center."""

# AI_MODULE: app_http_server
# AI_PURPOSE: Serve the Flask app with bounded request concurrency for local production.
# AI_BOUNDARY: This file owns WSGI serving only; it does not start device pollers.
# AI_DATA_FLOW: app.py -> serve_http(app) -> ThreadPoolWSGIServer -> Flask app.
# AI_RISK: Medium. Worker and pending-slot limits affect whole-system responsiveness.
# AI_COMPAT: SMART_POWER_HTTP_HOST/PORT/MAX_WORKERS/MAX_PENDING environment variables stay supported.
# AI_SEARCH_KEYWORDS: WSGI, serve_http, thread pool, HTTP worker.

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor

from werkzeug.serving import BaseWSGIServer, WSGIRequestHandler

_HTTP_ACCESS_LOG = str(os.environ.get("SMART_CENTER_HTTP_ACCESS_LOG", "")).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


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
        total_slots = self.max_workers + self.max_pending
        self._request_slots = threading.BoundedSemaphore(total_slots)
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
