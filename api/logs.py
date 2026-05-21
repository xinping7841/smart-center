from flask import Blueprint, jsonify, request

from auth.decorators import require_permission
from event_logger import query_events

bp = Blueprint("logs", __name__)


@bp.route("/api/logs/events")
@require_permission("dashboard.view")
def api_event_logs():
    payload = query_events(
        category=str(request.args.get("category") or "").strip(),
        event_type=str(request.args.get("event_type") or "").strip(),
        source=str(request.args.get("source") or "").strip(),
        result=str(request.args.get("result") or "").strip(),
        device_id=str(request.args.get("device_id") or "").strip(),
        q=str(request.args.get("q") or "").strip(),
        limit=request.args.get("limit", default=100, type=int),
        offset=request.args.get("offset", default=0, type=int),
        hours=request.args.get("hours", default=None, type=float),
    )
    return jsonify(payload)
