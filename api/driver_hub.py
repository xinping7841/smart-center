# AI_MODULE: driver_hub_api
# AI_PURPOSE: 驱动中心清单和运行快照接口，用于查看协议驱动健康状态。
# AI_BOUNDARY: 不执行具体设备控制；只汇总 runtime.driver_hub 的 manifest/snapshot。
# AI_DATA_FLOW: runtime.driver_hub -> /api/driver_hub/* -> driver-hub 页面。
# AI_RUNTIME: 独立驱动中心页面按需查看。
# AI_RISK: 低，主要是观察性接口。
# AI_COMPAT: manifest/snapshot 字段被 static/js/views/driver-hub.js 使用。
# AI_SEARCH_KEYWORDS: driver hub, manifest, snapshot, node-red, driver health.

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
