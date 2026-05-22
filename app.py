"""Smart Center service entrypoint."""

# AI_MODULE: app_entry
# AI_PURPOSE: Start the Flask app and runtime pollers for the Smart Center service.
# AI_BOUNDARY: Keep this file thin. App assembly lives in modules/app, routes in api/*, and protocols in services/drivers/core modules.
# AI_DATA_FLOW: systemd or python app.py -> create_app() -> registered blueprints -> background runtime services.
# AI_RUNTIME: node-120 production executes /srv/smart-center/current/app.py and listens on SMART_POWER_HTTP_PORT=6899 by default.
# AI_RISK: High. Startup, auth hooks, static delivery, and background services affect the whole site.
# AI_COMPAT: Importing app exposes the Flask `app` object for WSGI/embedded launch modes.
# AI_SEARCH_KEYWORDS: startup, Flask app, app factory, smart-center.service, 6899.

import os

from modules.app import create_app, serve_http
from runtime import ensure_runtime_started, init_runtime, start_background_services

# Keep FFmpeg transport selection dynamic in the door camera module.
# Some cameras only become stable over TCP, while others still need UDP fallback.
os.environ.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)

app = create_app()

# Ensure background pollers are available under both `python app.py` and WSGI/embedded launch modes.
ensure_runtime_started()


if __name__ == "__main__":
    print(">>> [startup] 1/3 initialize runtime")
    init_runtime()
    print(">>> [startup] 2/3 start background services")
    start_background_services()
    print(">>> [startup] 3/3 web server listening on :6899")
    serve_http(app)
