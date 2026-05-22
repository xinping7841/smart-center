"""Flask application factory for Smart Center."""

# AI_MODULE: app_factory
# AI_PURPOSE: Build and configure the Flask app without embedding route logic.
# AI_BOUNDARY: HTTP hooks and blueprint registration belong here; device protocols do not.
# AI_DATA_FLOW: systemd/python app.py -> create_app() -> hooks + blueprints -> runtime services.
# AI_RISK: High. Template/static paths, auth context, and cache headers affect every page.
# AI_COMPAT: Keep /static, /, /config, /login, /agent/*, /report and all /api/* URLs stable.
# AI_SEARCH_KEYWORDS: Flask app factory, static path, template path, auth context.

from __future__ import annotations

import os

from flask import Flask

from paths import PROJECT_ROOT

from .blueprints import register_blueprints
from .request_hooks import install_request_hooks


def create_app() -> Flask:
    app = Flask(
        "smart_center",
        root_path=str(PROJECT_ROOT),
        static_folder=str(PROJECT_ROOT / "static"),
        static_url_path="/static",
        template_folder=str(PROJECT_ROOT / "templates"),
    )
    configure_app(app)
    install_request_hooks(app)
    register_blueprints(app)
    return app


def configure_app(app: Flask) -> None:
    app.config["SECRET_KEY"] = os.environ.get("SMART_POWER_SECRET_KEY", "smart-power-monitor-dev-secret")
    app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("SMART_POWER_MAX_CONTENT_LENGTH", 524288))
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = int(os.environ.get("SMART_CENTER_STATIC_MAX_AGE", "31536000"))
