# ── Stage 1: builder ─────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    libglib2.0-0 libsm6 libxrender1 libxext6 \
    libgl1-mesa-glx \
    curl \
  && rm -rf /var/lib/apt/lists/*

# ── PyTorch (CPU-only by default) ─────────────────────────
# To use CUDA, build with: --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu121
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
RUN pip install --upgrade pip \
 && pip install --no-cache-dir --prefix=/install \
    "torch>=2.6,<3.0" "torchvision>=0.21,<2.0" \
    --index-url ${TORCH_INDEX}

# ── YOLOX ─────────────────────────────────────────────────
# --no-deps   : skip onnx==1.8.1 / tensorboard / pycocotools (training only)
# --no-build-isolation : setup.py needs torch visible at build time
RUN pip install --no-cache-dir --prefix=/install \
    --no-deps --no-build-isolation \
    "yolox>=0.3.0"

# ── Remaining deps ────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install \
    -r requirements.txt \
    --ignore-installed torch torchvision yolox

# ── Stage 2: runtime ─────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="real-time-inference/inference" \
      org.opencontainers.image.description="YOLOX inference pipeline: capture → bounded queue → YOLOX workers → RabbitMQ" \
      org.opencontainers.image.licenses="Apache-2.0"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxrender1 libxext6 \
    libgl1-mesa-glx \
    curl \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

WORKDIR /app
COPY . .

# Model weights are stored here; mounted as a named Docker volume so
# downloaded weights survive container restarts.
RUN mkdir -p /model-weights && chmod 777 /model-weights

RUN useradd -r -u 1001 inference && chown -R inference:inference /app
USER inference

EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=60s \
  CMD curl -sf http://localhost:8001/health || exit 1

CMD ["python", "-m", "main"]
