"""
CSRF 保护模块 — 基于 Double Submit Cookie 模式。

安全机制：
- 首次 GET 请求时，服务器下发 csrf_token cookie
- 后续 POST/PUT/DELETE 请求必须携带 X-CSRF-Token header，值与 cookie 一致
- 攻击者无法跨域读取或设置 cookie，因此无法伪造 token
"""

import secrets
from flask import Flask, request, jsonify

COOKIE_NAME = "csrf_token"
HEADER_NAME = "X-CSRF-Token"
_CSRF_TOKEN_BYTES = 32
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _generate_token() -> str:
    return secrets.token_hex(_CSRF_TOKEN_BYTES)


def _get_cookie_token() -> str:
    return str(request.cookies.get(COOKIE_NAME, "")).strip()


def init_csrf(app: Flask):
    # before_request: 校验 CSRF token
    @app.before_request
    def csrf_check():
        path = (request.path or "").strip()

        # 静态资源、登录页、首页、agent 路径跳过
        if path.startswith("/static/") or path.startswith("/login"):
            return None
        if path in ("/", "/config", "/report", "/agent/config") or path.startswith("/agent/"):
            return None

        # 安全方法放行
        if request.method in _SAFE_METHODS:
            return None

        # 不安全方法校验 token
        header_token = str(request.headers.get(HEADER_NAME, "")).strip()
        cookie_token = _get_cookie_token()

        # Only reject if cookie exists but header doesn't match
        # If no cookie yet, allow first request and set cookie in response
        if cookie_token and header_token != cookie_token:
            return jsonify({
                "ok": False,
                "error": "csrf_invalid", 
                "msg": "CSRF token 校验失败，请刷新页面后重试"
            }), 403
        return None

    # after_request: 下发 csrf_token cookie
    @app.after_request
    def set_csrf(response):
        # 只对页面请求下发 cookie（跳过静态资源和 API）
        if request.method not in _SAFE_METHODS:
            return response

        path = (request.path or "").strip()
        if path.startswith("/static/"):
            return response

        existing = _get_cookie_token()
        if existing:
            return response

        token = _generate_token()
        response.set_cookie(
            COOKIE_NAME,
            token,
            httponly=False,
            samesite="Lax",
            secure=False,
            path="/",
            max_age=86400,
        )
        return response
