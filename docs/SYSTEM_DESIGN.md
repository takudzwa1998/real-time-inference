# Multi-Camera Real-Time Inference Platform — System Design

> **Status:** Phase 0 — System Design  
> **Project:** Portfolio Anchor #1  
> **Goal:** End-to-end video ingestion, YOLO inference, event streaming, persistence, alerting, observability, and a React dashboard — all runnable with `docker compose up`.

---

## 1. Problem Statement

CCTV and IoT video platforms need to:

1. Ingest **multiple live streams** (RTSP cameras + local webcams) concurrently.
2. Run **object detection** without blocking ingestion or crashing under load.
3. **Decouple** inference from downstream consumers (storage, alerts, future AI agents).
4. Provide **operational visibility** (queue depth, latency, FPS per camera).
5. Offer an **operator GUI** to monitor cameras, detections, and alert configuration.

This project demonstrates production-minded patterns used by CCTV SaaS companies in NL/IE/DE: bounded queues, async messaging, metrics-first observability, and containerized deployment.

---

## 2. Requirements

### Functional

| ID | Requirement |
|----|-------------|
| F1 | Accept N concurrent RTSP streams and M webcam streams |
| F2 | Buffer frames in **bounded queues**; drop or skip stale frames under pressure |
| F3 | Run YOLOv8 or YOLOv11 on **background worker threads**; model selectable at runtime |
| F4 | Publish detections to **RabbitMQ** (exchange + routing keys per camera) |
| F5 | Consumer writes detections to **PostgreSQL** |
| F6 | Consumer triggers alerts via **Telegram** and/or **webhooks** |
| F7 | Expose **Prometheus** metrics: queue depth, inference latency, FPS per camera |
| F8 | Ship a pre-built **Grafana** dashboard |
| F9 | **React GUI**: live camera status, recent detections, alert rules, system health |
| F10 | Single-command deploy via **Docker Compose** |

### Non-Functional

| ID | Requirement | Target |
|----|-------------|--------|
| NF1 | Inference decoupled from ingestion | Queue + worker pool |
| NF2 | Backpressure | Bounded queues, frame drop policy |
| NF3 | Configurable at runtime | Model swap, camera add/remove via API |
| NF4 | Observability | RED/USE metrics, Grafana dashboards |
| NF5 | Portability | All services containerized |

### Out of Scope (v1)

- Multi-tenant auth / RBAC (stub API key only)
- Video recording / NVR storage
- Edge deployment (Jetson) — future phase
- LangGraph agentic alert reasoning — **Phase 2** (see §10)

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              OPERATOR LAYER                                  │
│  ┌──────────────────────┐         ┌──────────────────────────────────────┐  │
│  │   React Dashboard    │◄─REST──►│  FastAPI Gateway (api/)              │  │
│  │   (frontend/)        │◄─WS────►│  cameras · detections · alerts · cfg │  │
│  └──────────────────────┘         └──────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
         ┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
         │  PostgreSQL      │      │  Prometheus      │      │  Grafana         │
         │  (detections,    │      │  (scrape targets)│      │  (dashboards)    │
         │   cameras,       │      └────────▲─────────┘      └──────────────────┘
         │   alert rules)   │               │
         └────────▲─────────┘               │ /metrics
                  │                         │
         ┌────────┴─────────┐      ┌────────┴─────────┐
         │  Alert Consumer  │      │  Inference       │
         │  (consumer/)     │      │  Service         │
         │  · persist       │      │  (inference/)    │
         │  · telegram      │      │  · capture       │
         │  · webhooks      │      │  · queue         │
         └────────▲─────────┘      │  · YOLO workers  │
                  │                 └────────▲─────────┘
                  │                          │
                  │                 ┌──────────┴─────────┐
                  │                 │     RabbitMQ       │
                  └─────────────────┤  detections.*      │
                                    └────────────────────┘
                                              ▲
                    RTSP / Webcam streams ──────┘
```

### Data Flow (happy path)

1. **Capture thread** per camera reads frames from OpenCV (`cv2.VideoCapture`).
2. Frame pushed to a **bounded queue** (max size configurable, e.g. 30).
3. **Inference worker** pulls frame, runs YOLO, builds detection payload.
4. Payload published to RabbitMQ exchange `detections` with routing key `camera.{id}`.
5. **Alert consumer** subscribes, batch-inserts to PostgreSQL, evaluates alert rules.
6. If rule matches → Telegram message or webhook POST.
7. **FastAPI** serves REST + WebSocket for the React GUI; reads from PostgreSQL.
8. **Prometheus** scrapes `/metrics` from inference service and consumer.

---

## 4. Technology Choices & Rationale

### Python + FastAPI

| Why | Detail |
|-----|--------|
| Ecosystem | OpenCV, Ultralytics YOLO, async I/O, mature ML stack |
| FastAPI | Async REST + WebSocket, OpenAPI docs, Pydantic validation — ideal for config APIs and GUI backend |
| Threading | GIL-friendly for I/O-bound capture; inference workers use threads or subprocess pool |

**Alternative considered:** Go for ingestion — faster, but weaker ML ecosystem. Python wins for YOLO integration and portfolio clarity.

### YOLOv8 / YOLOv11 (Ultralytics)

| Why | Detail |
|-----|--------|
| Industry standard | Most recognized object-detection brand in CV portfolios |
| Runtime swap | Same API: `YOLO("yolov8n.pt")` vs `YOLO("yolo11n.pt")` |
| Performance tiers | nano → xlarge; configurable via env/API |

Model loaded once per worker; hot-swap via admin API (drain queue → reload → resume).

### RabbitMQ

| Why | Detail |
|-----|--------|
| Decoupling | Inference never waits on DB or Telegram |
| Backpressure signal | Queue depth visible in RabbitMQ management + our Prometheus metrics |
| Routing | Topic exchange: `detections.camera.{id}`, `detections.alert.high` |
| Durability | Messages persisted; consumer acks; survives restarts |

**Alternative considered:** Redis Streams — simpler, but RabbitMQ is the explicit spec and matches enterprise CCTV pipelines.

### PostgreSQL

| Why | Detail |
|-----|--------|
| Structured queries | Detections with JSONB bounding boxes, time-series aggregations |
| Relational config | Cameras, alert rules, webhook endpoints |
| GUI queries | Pagination, filters, joins — natural fit |

**Schema sketch:**

```sql
cameras (id, name, source_type, source_uri, enabled, created_at)
detections (id, camera_id, frame_ts, model, inference_ms, detections_jsonb, created_at)
alert_rules (id, camera_id, class_name, min_confidence, channel, target, enabled)
alert_events (id, rule_id, detection_id, status, sent_at)
```

### Prometheus + Grafana

| Why | Detail |
|-----|--------|
| Market signal | NL/IE/DE CCTV SaaS job posts heavily mention observability |
| Metrics we expose | `camera_fps`, `queue_depth`, `inference_latency_seconds`, `detections_total`, `frames_dropped_total` |
| Grafana | Pre-provisioned dashboard JSON in `infra/grafana/dashboards/` |

### Docker Compose

| Why | Detail |
|-----|--------|
| One command | `docker compose up` for demo/recruiters |
| Service isolation | inference, consumer, api, postgres, rabbitmq, prometheus, grafana, frontend |
| Reproducibility | Identical env on any machine with Docker |

### React Dashboard

| Why | Detail |
|-----|--------|
| User choice | Polished operator UI vs Streamlit |
| Real-time | WebSocket for live detection feed and camera health |
| Portfolio | Shows full-stack capability alongside backend pipeline |

**Pages (v1):**

- **Overview** — system health, aggregate FPS, active cameras
- **Cameras** — add/edit/remove streams, live status badges
- **Detections** — searchable table + optional bbox overlay thumbnail
- **Alerts** — rule editor, recent alert events
- **Settings** — model selection (YOLOv8/v11, size), queue sizes

---

## 5. Service Decomposition

```
real-time-inference/
├── services/
│   ├── inference/          # Capture + queue + YOLO workers + RabbitMQ publish
│   ├── consumer/           # RabbitMQ subscribe + PostgreSQL + alerts
│   └── api/                # FastAPI REST + WebSocket for GUI
├── frontend/               # React + Vite + TypeScript
├── infra/
│   ├── docker-compose.yml
│   ├── prometheus/
│   └── grafana/
├── docs/
│   ├── SYSTEM_DESIGN.md    # this file
│   └── adr/                # Architecture Decision Records
└── README.md
```

### 5.1 Inference Service

**Responsibilities:** Stream capture, frame queuing, model inference, metrics, message publish.

**Key design decisions:**

- **One capture thread per camera** — blocking I/O isolated from inference.
- **Bounded `queue.Queue(maxsize=N)`** — on full, drop oldest or skip (configurable `DROP_POLICY=oldest|newest`).
- **Worker pool** — `N` threads share model instance or one model per worker (trade-off: memory vs contention). Default: 2 workers, 1 model each.
- **Frame sampling** — optional `SAMPLE_EVERY_K=3` to reduce load on weak hardware.

**Detection message schema (JSON):**

```json
{
  "camera_id": "cam-01",
  "frame_timestamp": "2026-07-01T10:00:00.123Z",
  "model": "yolov8n",
  "inference_ms": 42,
  "frame_width": 1920,
  "frame_height": 1080,
  "objects": [
    {"class": "person", "confidence": 0.91, "bbox": [100, 200, 150, 300]}
  ]
}
```

### 5.2 Alert Consumer Service

**Responsibilities:** Consume RabbitMQ, persist detections, evaluate rules, send notifications.

**Key design decisions:**

- **Idempotent inserts** — `detection_id` UUID in message prevents duplicates on redelivery.
- **Alert debouncing** — same rule + camera suppressed for `DEBOUNCE_SECONDS=60`.
- **Telegram** — Bot API via `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`.
- **Webhooks** — POST JSON payload to configured URL with retry (3x exponential backoff).

### 5.3 API Gateway (FastAPI)

**Responsibilities:** CRUD for cameras/alerts, detection queries, WebSocket fan-out, proxy config to inference service.

**Endpoints (v1):**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness |
| GET/POST/PATCH/DELETE | `/cameras` | Camera CRUD |
| GET | `/detections` | Paginated history |
| GET/POST/PATCH/DELETE | `/alert-rules` | Rule CRUD |
| GET | `/metrics/summary` | Aggregated stats for dashboard |
| WS | `/ws/detections` | Live detection stream |
| POST | `/config/model` | Hot-swap YOLO model |

### 5.4 React Frontend

- **Stack:** React 18, Vite, TypeScript, TanStack Query, lightweight chart lib (Recharts)
- **Auth (v1):** None — local demo; API key header stub for future
- **Build:** Multi-stage Docker image → nginx serving static assets; proxies `/api` to FastAPI

---

## 6. Concurrency & Backpressure Model

```
Camera Thread          Bounded Queue           Worker Thread(s)
     │                      │                         │
     │  put(frame)          │                         │
     ├─────────────────────►│                         │
     │  (block or drop)     │  get(frame)             │
     │                      ├────────────────────────►│
     │                      │                         │ YOLO.predict()
     │                      │                         │ publish → RabbitMQ
```

**Why bounded queues matter:** Unbounded queues mask overload until OOM. Explicit drops + `frames_dropped_total` metric prove the system degrades gracefully — a key interview talking point.

---

## 7. Observability Design

### Prometheus Metrics

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `camera_fps` | Gauge | `camera_id` | Ingest rate |
| `inference_queue_depth` | Gauge | `camera_id` | Backpressure |
| `inference_latency_seconds` | Histogram | `camera_id`, `model` | SLA tracking |
| `detections_total` | Counter | `camera_id`, `class` | Business metric |
| `frames_dropped_total` | Counter | `camera_id`, `reason` | Health signal |
| `rabbitmq_publish_errors_total` | Counter | — | Pipeline failures |

### Grafana Dashboard Panels

1. FPS per camera (time series)
2. Queue depth heatmap
3. Inference latency p50/p95
4. Detections by class (bar chart)
5. Frames dropped rate
6. Service up/down status

### Logging

- Structured JSON logs (Python `structlog`)
- Correlation: `camera_id`, `detection_id` in every log line
- Log level via env `LOG_LEVEL`

---

## 8. Deployment Topology (Docker Compose)

| Service | Image | Ports | Depends On |
|---------|-------|-------|------------|
| `postgres` | postgres:16-alpine | 5432 | — |
| `rabbitmq` | rabbitmq:3-management | 5672, 15672 | — |
| `inference` | build: services/inference | 8001 | rabbitmq |
| `consumer` | build: services/consumer | 8002 | rabbitmq, postgres |
| `api` | build: services/api | 8000 | postgres, inference |
| `frontend` | build: frontend | 3000 | api |
| `prometheus` | prom/prometheus | 9090 | inference, consumer, api |
| `grafana` | grafana/grafana | 3001 | prometheus |

**Networks:** Single bridge `inference-net`. No public exposure of postgres/rabbitmq in production (compose override for dev exposes management UI).

---

## 9. Configuration

All services configured via environment variables (12-factor). Example:

```env
# Inference
CAMERAS=rtsp://user:pass@192.168.1.10/stream,webcam:0
YOLO_MODEL=yolov8n.pt
QUEUE_MAX_SIZE=30
DROP_POLICY=oldest
INFERENCE_WORKERS=2

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
DETECTIONS_EXCHANGE=detections

# Alerts
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
WEBHOOK_URL=

# Database
DATABASE_URL=postgresql://inference:inference@postgres:5432/inference
```

Runtime camera changes go through API → inference service reload signal (HTTP or RabbitMQ control queue).

---

## 10. Future: Agentic Alert Reasoning (Phase 2)

Per portfolio roadmap, this platform integrates with:

- **LangGraph** — multi-step alert reasoning (context retrieval, false-positive filtering, escalation)
- **MCP server** — exposes camera metadata and recent detections to Cursor/agents

The RabbitMQ + PostgreSQL boundary keeps Phase 2 additive: agents subscribe to the same detection stream or query the API without changing the core pipeline.

---

## 11. Implementation Phases

| Phase | Deliverable | Est. |
|-------|-------------|------|
| **0** | System design (this doc) + ADRs | ✓ now |
| **1** | Docker Compose skeleton + Postgres/RabbitMQ schemas | Week 1 |
| **2** | Inference service (capture, queue, YOLO, publish) | Week 1–2 |
| **3** | Consumer (persist + Telegram/webhook) | Week 2 |
| **4** | FastAPI + metrics endpoints | Week 2 |
| **5** | Prometheus + Grafana dashboard | Week 2 |
| **6** | React GUI | Week 3 |
| **7** | README, architecture diagram, demo GIF | Week 3 |
| **8** | 90s Loom demo video | Week 3 |

---

## 12. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| RTSP instability | Reconnect with exponential backoff; mark camera `degraded` in metrics |
| GPU not available | Default to CPU + nano model; document CUDA compose profile |
| RabbitMQ backlog | Consumer scaling (multiple consumer instances); alert on queue depth |
| Model load time | Pre-warm on startup; health check waits for model ready |
| Webcam unavailable in Docker | Document `--device` flag; RTSP as primary demo path |

---

## 13. Success Criteria

- [ ] `docker compose up` starts full stack without manual steps
- [ ] 2+ RTSP/webcam streams infer concurrently with visible FPS metrics
- [ ] Detections appear in PostgreSQL and React GUI within 2s
- [ ] Telegram/webhook fires on configured rule
- [ ] Grafana dashboard shows queue depth, latency, FPS
- [ ] Model switchable YOLOv8 ↔ YOLOv11 via API
- [ ] README includes architecture diagram + demo GIF

---

## 14. Next Step

**Phase 1:** Scaffold repository structure, `docker-compose.yml`, database migrations, and RabbitMQ topology — then implement the inference service.

Proceed when ready.
