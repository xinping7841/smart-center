# AI_MODULE: snmp_agent_fastapi_app
# AI_PURPOSE: 121 独立 SNMP 采集服务 HTTP API，供 120 中控拉取缓存状态。
# AI_BOUNDARY: 不承载中控 UI、不直接修改 120 缓存；120 通过后台拉取对接。
# AI_DATA_FLOW: SnmpAgentPoller.status_snapshot -> /status JSON -> 120 snmp_remote_agent_loop。
# AI_RUNTIME: uvicorn services.snmp_agent.app:app；systemd 使用 deploy/snmp_agent/smart-snmp.service。
# AI_RISK: 中，接口字段需稳定，否则 120 侧缓存更新失败。
# AI_SEARCH_KEYWORDS: fastapi, smart-snmp-agent, status, health, reload.

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .config import load_agent_config
from .poller import SnmpAgentPoller


poller = SnmpAgentPoller(load_agent_config())


@asynccontextmanager
async def lifespan(app: FastAPI):
    poller.start()
    try:
        yield
    finally:
        poller.stop()


app = FastAPI(
    title="Smart SNMP Agent",
    version="2026.05.28",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, Any]:
    snapshot = poller.status_snapshot()
    agent = snapshot.get("agent", {})
    summary = snapshot.get("summary", {})
    return {
        "ok": bool(agent.get("loop_alive")),
        "agent": agent,
        "summary": summary,
    }


@app.get("/status")
def status() -> JSONResponse:
    snapshot = poller.status_snapshot()
    return JSONResponse(snapshot)


@app.post("/reload")
def reload_config() -> dict[str, Any]:
    try:
        config = poller.reload_config()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "ok": True,
        "source_config_path": config.source_config_path,
        "device_count": len(config.devices),
        "max_workers": config.max_workers,
    }

