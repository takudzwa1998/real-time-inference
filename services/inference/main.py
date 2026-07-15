"""
Inference service — Phase 2.

Startup sequence:
  1. FastAPI lifespan begins.
  2. Publisher connects to RabbitMQ.
  3. Pipeline loads YOLOX weights, starts capture + worker threads.
  4. /health returns 200; /ready returns 200 once model is loaded.
  5. Detections flow: capture → queue → YOLOX → RabbitMQ.

Shutdown sequence (Ctrl-C or SIGTERM):
  1. Pipeline.stop() drains workers and capture threads.
  2. Publisher disconnects from RabbitMQ.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app, REGISTRY

from classes import CLASS_NAMES, group_summary
from config import settings
from detector import DetectionResult
from model_registry import MODEL_NAMES_ORDERED, get_variant
from pipeline import InferencePipeline
from publisher import DetectionPublisher

log = structlog.get_logger()

# ── Prometheus metrics ────────────────────────────────────

camera_fps = Gauge(
    "camera_fps",
    "Frames per second ingested per camera",
    ["camera_id"],
)
inference_queue_depth = Gauge(
    "inference_queue_depth",
    "Frames waiting in the per-camera bounded queue",
    ["camera_id"],
)
inference_latency = Histogram(
    "inference_latency_seconds",
    "YOLOX end-to-end inference time per frame",
    ["camera_id", "model"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0],
)
detections_total = Counter(
    "detections_total",
    "Total objects detected",
    ["camera_id", "cls"],
)
frames_dropped_total = Counter(
    "frames_dropped_total",
    "Frames dropped due to queue pressure",
    ["camera_id", "reason"],
)
rabbitmq_publish_errors_total = Counter(
    "rabbitmq_publish_errors_total",
    "RabbitMQ publish failures",
    [],
)

# ── Globals (initialised in lifespan) ────────────────────

_publisher: DetectionPublisher | None = None
_pipeline:  InferencePipeline  | None = None


# ── Publish callback (sync thread → async event loop) ────

async def _publish_callback(
    camera_id:    str,
    frame_ts:     str,
    model:        str,
    inference_ms: int,
    frame_width:  int,
    frame_height: int,
    detections:   list[DetectionResult],
) -> None:
    if _publisher is None:
        return
    try:
        await _publisher.publish(
            camera_id, frame_ts, model, inference_ms,
            frame_width, frame_height, detections,
        )
    except Exception as exc:
        rabbitmq_publish_errors_total.inc()
        log.error("publish_error", error=str(exc))


# ── Lifespan ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _publisher, _pipeline

    log.info("inference_service_starting", model=settings.yolox_model)

    _publisher = DetectionPublisher(settings)
    await _publisher.connect()

    loop = asyncio.get_running_loop()
    _pipeline = InferencePipeline(settings, loop)

    # Inject metric handles so the pipeline can update them from worker threads
    _pipeline.fps_gauge         = camera_fps
    _pipeline.queue_depth_gauge = inference_queue_depth
    _pipeline.latency_hist      = inference_latency
    _pipeline.detections_ctr    = detections_total
    _pipeline.dropped_ctr       = frames_dropped_total

    _pipeline.set_publish_callback(_publish_callback)

    # Run blocking start() in a thread so it doesn't block the event loop
    # (model loading can take several seconds on first run)
    await asyncio.to_thread(_pipeline.start)

    log.info("inference_service_ready", model=settings.yolox_model)

    yield

    log.info("inference_service_stopping")
    await asyncio.to_thread(_pipeline.stop)
    await _publisher.disconnect()
    log.info("inference_service_stopped")


# ── App ───────────────────────────────────────────────────

app = FastAPI(
    title="Inference Service",
    version="2.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)

metrics_app = make_asgi_app(registry=REGISTRY)
app.mount("/metrics", metrics_app)


# ── Ops endpoints ─────────────────────────────────────────

@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok", "service": "inference"}


@app.get("/ready", tags=["ops"])
async def ready() -> dict:
    loaded = _pipeline is not None and all(d.is_loaded for d in (_pipeline._detectors or []))
    if not loaded:
        return JSONResponse(
            status_code=503,
            content={"status": "loading", "model": settings.yolox_model},
        )
    return {"status": "ok", "model": settings.yolox_model}


# ── Status endpoints ──────────────────────────────────────

@app.get("/cameras", tags=["cameras"])
async def camera_statuses() -> dict:
    if _pipeline is None:
        return {"cameras": {}}
    return {"cameras": _pipeline.camera_statuses}


@app.get("/model", tags=["model"])
async def current_model() -> dict:
    variant = get_variant(settings.yolox_model)
    return {
        "active":       variant.name,
        "input_size":   variant.input_size,
        "params_m":     variant.params_m,
        "map_val":      variant.map_val,
        "latency_ms":   variant.latency_ms,
        "available":    MODEL_NAMES_ORDERED,
    }


@app.post("/config/model", tags=["model"])
async def swap_model(model: str) -> dict:
    """Hot-swap the active YOLOX model. Drains the queue then reloads."""
    if model not in MODEL_NAMES_ORDERED:
        return JSONResponse(
            status_code=422,
            content={"detail": f"Invalid model '{model}'. Valid: {MODEL_NAMES_ORDERED}"},
        )
    if _pipeline is None:
        return JSONResponse(status_code=503, content={"detail": "Pipeline not started"})

    await asyncio.to_thread(_pipeline.swap_model, model)
    return {"status": "ok", "model": model}


@app.get("/classes", tags=["model"])
async def list_classes() -> dict:
    """Return all 80 COCO classes organised by semantic group."""
    return {
        "total":  len(CLASS_NAMES),
        "groups": group_summary(),
    }


# ── Entry point ───────────────────────────────────────────

if __name__ == "__main__":
    port      = settings.metrics_port
    log_level = settings.log_level.lower()

    log.info("uvicorn_starting", port=port)
    # Pass the app object directly (not the "main:app" string) to avoid
    # uvicorn re-importing this module and double-registering Prometheus metrics.
    uvicorn.run(app, host="0.0.0.0", port=port, log_level=log_level)
