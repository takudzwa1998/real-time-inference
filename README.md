# Multi-Camera Real-Time Inference Platform

End-to-end video analytics pipeline: multi-stream ingestion, YOLO inference, RabbitMQ event bus, PostgreSQL persistence, Telegram/webhook alerts, Prometheus/Grafana observability, and a React operator dashboard.

> **Current phase:** System Design — see [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md)

## What This Demonstrates

- Concurrent RTSP + webcam ingestion with **bounded queues** and backpressure
- Configurable **YOLOv8 / YOLOv11** inference on background workers
- **RabbitMQ**-decoupled detection pipeline
- **PostgreSQL** persistence + alert rules
- **Prometheus + Grafana** operational metrics
- **React GUI** for cameras, detections, and alerts
- **Docker Compose** one-command deployment

## Architecture

See the full diagram and data-flow breakdown in [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md).

## Tech Stack

| Layer | Technology |
|-------|------------|
| Inference | Python, OpenCV, Ultralytics YOLO |
| API | FastAPI |
| Messaging | RabbitMQ |
| Database | PostgreSQL |
| Observability | Prometheus, Grafana |
| Frontend | React, Vite, TypeScript |
| Deploy | Docker Compose |

## Documentation

- [System Design](docs/SYSTEM_DESIGN.md) — requirements, architecture, phases
- [ADRs](docs/adr/) — key architectural decisions

## Roadmap

- [x] Phase 0 — System design
- [ ] Phase 1 — Infrastructure scaffold (Compose, DB, RabbitMQ)
- [ ] Phase 2 — Inference service
- [ ] Phase 3 — Alert consumer
- [ ] Phase 4 — FastAPI + metrics
- [ ] Phase 5 — Grafana dashboard
- [ ] Phase 6 — React GUI
- [ ] Phase 7 — Demo GIF + Loom video

## License

MIT
