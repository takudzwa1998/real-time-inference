"""
API Gateway — Phase 1 skeleton with SQLModel wiring.

All data-mutating routes return 501 until Phase 4 fills them in.
The DB session dependency and response schemas are already typed so
Phase 4 can drop implementations straight into the stubs.
"""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Any

import structlog
import uvicorn
from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app, REGISTRY
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from fastapi.responses import JSONResponse

import database
from models import (
    Camera,
    CameraCreate,
    CameraRead,
    CameraUpdate,
    Detection,
    DetectionRead,
    AlertRule,
    AlertRuleCreate,
    AlertRuleRead,
    AlertRuleUpdate,
    SystemConfigRead,
    SystemConfigUpdate,
)

log = structlog.get_logger()

# ── Dependency alias ──────────────────────────────────────
SessionDep = Annotated[AsyncSession, Depends(database.get_session)]


# ── Lifespan ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("api_startup")
    await database.connect()
    yield
    await database.disconnect()
    log.info("api_shutdown")


# ── App ───────────────────────────────────────────────────

app = FastAPI(
    title="Real-Time Inference API",
    version="0.1.0-skeleton",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

metrics_app = make_asgi_app(registry=REGISTRY)
app.mount("/metrics", metrics_app)


# ── Health ────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok", "service": "api"}


# ── Cameras ───────────────────────────────────────────────

@app.get("/cameras", response_model=list[CameraRead], tags=["cameras"])
async def list_cameras(session: SessionDep) -> Any:
    result = await session.exec(select(Camera).order_by(Camera.created_at))
    return result.all()


@app.post("/cameras", response_model=CameraRead, status_code=201, tags=["cameras"])
async def create_camera(body: CameraCreate, session: SessionDep) -> Any:
    # Phase 4: persist + signal inference service to start capture
    return JSONResponse(status_code=501, content={"detail": "Not implemented — Phase 4"})


@app.get("/cameras/{camera_id}", response_model=CameraRead, tags=["cameras"])
async def get_camera(camera_id: uuid.UUID, session: SessionDep) -> Any:
    camera = await session.get(Camera, camera_id)
    if camera is None:
        return JSONResponse(status_code=404, content={"detail": "Camera not found"})
    return camera


@app.patch("/cameras/{camera_id}", response_model=CameraRead, tags=["cameras"])
async def update_camera(camera_id: uuid.UUID, body: CameraUpdate, session: SessionDep) -> Any:
    return JSONResponse(status_code=501, content={"detail": "Not implemented — Phase 4"})


@app.delete("/cameras/{camera_id}", status_code=204, tags=["cameras"])
async def delete_camera(camera_id: uuid.UUID, session: SessionDep) -> None:
    # Phase 4: stop capture + delete
    return JSONResponse(status_code=501, content={"detail": "Not implemented — Phase 4"})


# ── Detections ────────────────────────────────────────────

@app.get("/detections", response_model=list[DetectionRead], tags=["detections"])
async def list_detections(
    session: SessionDep,
    camera_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    stmt = select(Detection).order_by(Detection.frame_ts.desc()).limit(limit).offset(offset)
    if camera_id:
        stmt = stmt.where(Detection.camera_id == camera_id)
    result = await session.exec(stmt)
    return result.all()


# ── Alert rules ───────────────────────────────────────────

@app.get("/alert-rules", response_model=list[AlertRuleRead], tags=["alerts"])
async def list_alert_rules(session: SessionDep) -> Any:
    result = await session.exec(select(AlertRule).order_by(AlertRule.created_at))
    return result.all()


@app.post("/alert-rules", response_model=AlertRuleRead, status_code=201, tags=["alerts"])
async def create_alert_rule(body: AlertRuleCreate, session: SessionDep) -> Any:
    return JSONResponse(status_code=501, content={"detail": "Not implemented — Phase 4"})


@app.patch("/alert-rules/{rule_id}", response_model=AlertRuleRead, tags=["alerts"])
async def update_alert_rule(rule_id: uuid.UUID, body: AlertRuleUpdate, session: SessionDep) -> Any:
    return JSONResponse(status_code=501, content={"detail": "Not implemented — Phase 4"})


@app.delete("/alert-rules/{rule_id}", status_code=204, tags=["alerts"])
async def delete_alert_rule(rule_id: uuid.UUID, session: SessionDep) -> None:
    return JSONResponse(status_code=501, content={"detail": "Not implemented — Phase 4"})


# ── System config ─────────────────────────────────────────

@app.get("/config", response_model=list[SystemConfigRead], tags=["config"])
async def list_config(session: SessionDep) -> Any:
    from models import SystemConfig
    result = await session.exec(select(SystemConfig))
    return result.all()


@app.patch("/config/{key}", response_model=SystemConfigRead, tags=["config"])
async def update_config(key: str, body: SystemConfigUpdate, session: SessionDep) -> Any:
    return JSONResponse(status_code=501, content={"detail": "Not implemented — Phase 4"})


@app.post("/config/model", tags=["config"])
async def swap_model(model: str, session: SessionDep) -> Any:
    """Hot-swap the active YOLO model. Proxies to the inference service in Phase 4."""
    return JSONResponse(status_code=501, content={"detail": "Not implemented — Phase 4"})


# ── Metrics summary ───────────────────────────────────────

@app.get("/metrics/summary", tags=["metrics"])
async def metrics_summary(session: SessionDep) -> Any:
    """Aggregated stats from the detection_summary view. Implemented in Phase 4."""
    return JSONResponse(status_code=501, content={"detail": "Not implemented — Phase 4"})


# ── WebSocket ─────────────────────────────────────────────

@app.websocket("/ws/detections")
async def ws_detections(websocket: WebSocket) -> None:
    await websocket.accept()
    log.info("ws_client_connected", client=str(websocket.client))
    try:
        while True:
            # Phase 4: subscribe to RabbitMQ and fan-out detection events here
            await websocket.receive_text()
    except WebSocketDisconnect:
        log.info("ws_client_disconnected", client=str(websocket.client))


# ── Entry point ───────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("METRICS_PORT", "8000"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    log.info("api_service_starting", port=port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level=log_level)
