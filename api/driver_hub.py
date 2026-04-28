from flask import Blueprint, jsonify, render_template, request

from auth.decorators import require_permission
from runtime.driver_hub import build_manifest, collect_snapshot


bp = Blueprint("driver_hub", __name__)


@bp.route("/driver_hub")
@require_permission("dashboard.view")
def driver_hub_page():
    return render_template("driver_hub.html")


@bp.route("/api/driver_hub/manifest")
@require_permission("dashboard.view")
def api_driver_hub_manifest():
    include_disabled = str(request.args.get("include_disabled", "1")).strip().lower() not in {"0", "false", "no"}
    return jsonify(build_manifest(include_disabled=include_disabled))


@bp.route("/api/driver_hub/snapshot")
@require_permission("dashboard.view")
def api_driver_hub_snapshot():
    groups = request.args.get("groups", "")
    driver_id = request.args.get("driver_id", "")
    include_disabled = str(request.args.get("include_disabled", "0")).strip().lower() in {"1", "true", "yes"}
    return jsonify(
        collect_snapshot(
            groups=groups,
            driver_id=driver_id,
            include_disabled=include_disabled,
        )
    )
