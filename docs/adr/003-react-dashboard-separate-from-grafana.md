# ADR 003: React Dashboard Separate from Grafana

**Status:** Accepted  
**Date:** 2026-07-01

## Context

The platform needs operator-facing UI for camera management, detection history, and alert configuration. Grafana is included for infrastructure metrics.

## Decision

Build a **React + FastAPI** operator dashboard (`frontend/` + `services/api/`) distinct from Grafana.

## Rationale

| Tool | Purpose |
|------|---------|
| **Grafana** | SRE metrics: FPS, latency, queue depth, service health |
| **React GUI** | Product UX: CRUD cameras, browse detections, configure alert rules |

Grafana is poor at CRUD workflows and custom business logic. A React app demonstrates full-stack portfolio depth and matches CCTV SaaS product UIs.

## Consequences

- Two UIs to maintain — acceptable; they serve different audiences (ops vs operator).
- FastAPI becomes the BFF (backend-for-frontend) layer over PostgreSQL.
- WebSocket endpoint needed for live detection feed in the GUI.
