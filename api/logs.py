# AI_MODULE: event_logs_api
# AI_PURPOSE: 总事件日志查询接口，供首页日志窗口、灯光过滤和自动化记录等页面使用。
# AI_BOUNDARY: 不直接写日志；写入由 event_logger/data_logger/各业务 API 完成。
# AI_DATA_FLOW: event_logs.db -> /api/events 或日志接口 -> 前端日志列表。
# AI_RUNTIME: 多页面按筛选条件查询。
# AI_RISK: 低到中，日志顺序和过滤错误会影响排障判断。
# AI_COMPAT: query 参数、分页和返回字段需兼容现有前端。
# AI_SEARCH_KEYWORDS: logs, event, operation, audit, filter.

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
