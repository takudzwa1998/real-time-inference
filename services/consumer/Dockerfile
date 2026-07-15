# ── Stage 1: builder ─────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime ─────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="real-time-inference/consumer" \
      org.opencontainers.image.description="RabbitMQ consumer: persist detections, evaluate alert rules, send notifications"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
WORKDIR /app
COPY . .

RUN useradd -r -u 1001 consumer && chown -R consumer:consumer /app
USER consumer

EXPOSE 8002

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=30s \
  CMD curl -sf http://localhost:8002/health || exit 1

CMD ["python", "-m", "main"]
