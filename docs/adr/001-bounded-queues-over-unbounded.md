# ADR 001: Bounded Queues Over Unbounded Buffers

**Status:** Accepted  
**Date:** 2026-07-01

## Context

Video capture produces frames at a fixed rate (e.g. 30 FPS). Inference throughput varies with model size, hardware, and concurrent cameras. If inference falls behind capture, frames accumulate in memory.

## Decision

Use **bounded queues** (`queue.Queue(maxsize=N)`) between capture threads and inference workers. When full, apply a configurable drop policy (`oldest` or `newest`).

## Rationale

- Unbounded queues hide overload until the process OOMs — unacceptable in production.
- Bounded queues provide explicit **backpressure** and measurable degradation (`frames_dropped_total`).
- Dropping stale frames is correct for real-time CV: a 2-second-old frame has no detection value.

## Consequences

- Operators must monitor queue depth and dropped frames in Grafana.
- Tune `QUEUE_MAX_SIZE` and `INFERENCE_WORKERS` per deployment hardware.
- Interview/demo talking point: graceful degradation vs silent failure.
