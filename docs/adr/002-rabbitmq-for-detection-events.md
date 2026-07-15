# ADR 002: RabbitMQ for Detection Event Bus

**Status:** Accepted  
**Date:** 2026-07-01

## Context

Detections must reach multiple downstream systems: PostgreSQL persistence, Telegram/webhook alerts, and (Phase 2) LangGraph agents. The inference service must not block on slow consumers.

## Decision

Publish detection payloads to a **RabbitMQ topic exchange** (`detections`) with routing keys `camera.{id}`. A dedicated consumer service handles persistence and alerting.

## Rationale

- **Decoupling:** Inference publishes and moves on; consumer speed does not affect capture FPS.
- **Durability:** Persistent messages survive consumer restarts.
- **Routing:** Topic keys allow per-camera subscriptions and future fan-out without code changes.
- **Spec alignment:** Explicit project requirement; common in enterprise video analytics pipelines.

## Alternatives Considered

| Option | Rejected Because |
|--------|------------------|
| Direct DB write from inference | Blocks workers on DB latency; tight coupling |
| Redis Streams | Simpler but less routing flexibility; not in spec |
| Kafka | Overkill for v1 scale; heavier ops burden |

## Consequences

- RabbitMQ becomes a critical dependency — health checks and queue-depth alerts required.
- Message schema must be versioned and backward-compatible.
- Consumer must be idempotent (UUID per detection).
