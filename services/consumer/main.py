"""
Consumer service entry point — Phase 1 skeleton with SQLModel wiring.

Phase 3 will add:
  - aio_pika RabbitMQ consumer loop
  - Detection persistence via `session.add(detection)`
  - Alert rule evaluation and Telegram/webhook dispatch
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from prometheus_client import Counter, Gauge, make_asgi_app, REGISTRY

import database

log = structlog.get_logger()

# ── Prometheus metrics ────────────────────────────────────

detections_persisted_total = Counter(
    "consumer_detections_persisted_total",
    "Total detection records written to PostgreSQL",
    ["camera_id"],
)
alert_events_sent_total = Counter(
    "consumer_alert_events_sent_total",
    "Total alert notifications dispatched",
    ["channel", "status"],
)
consumer_lag = Gauge(
    "consumer_rabbitmq_lag",
    "Approximate number of unprocessed messages in the consume queue",
    [],
)


# ── Lifespan ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("consumer_startup")
    await database.connect()

    # Phase 3: start RabbitMQ consumer task here
    # amqp_task = asyncio.create_task(consume_detections())

    yield

    # Phase 3: cancel amqp_task here
    await database.disconnect()
    log.info("consumer_shutdown")


# ── App ───────────────────────────────────────────────────

app = FastAPI(
    title="Consumer Service",
    version="0.1.0-skeleton",
    docs_url="/docs",
    lifespan=lifespan,
)

metrics_app = make_asgi_app(registry=REGISTRY)
app.mount("/metrics", metrics_app)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok", "service": "consumer"}


@app.get("/ready", tags=["ops"])
async def ready() -> dict:
    """Phase 3: check live DB + RabbitMQ connections before returning 200."""
    return {"status": "ok", "db_connected": False, "amqp_connected": False}


# ── Entry point ───────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("METRICS_PORT", "8002"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    log.info("consumer_service_starting", port=port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level=log_level, access_log=False)
