# AI_MODULE: api_package
# AI_PURPOSE: Flask 蓝图路由包。
"""API 蓝图包 — Flask 路由蓝图集中管理。

所有 api/*.py 模块注册为独立蓝图，由 app.py 统一装配。
新增 API 模块应在 app.py 中 import 并 register_blueprint。
"""
