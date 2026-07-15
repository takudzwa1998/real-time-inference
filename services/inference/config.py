"""
Inference service configuration — all values read from environment variables.
Defaults are safe for a single-camera CPU demo.
"""

from __future__ import annotations

from enum import Enum
from pydantic_settings import BaseSettings, SettingsConfigDict


class DropPolicy(str, Enum):
    oldest = "oldest"   # discard the oldest frame in the queue (keeps latency low)
    newest = "newest"   # discard the incoming frame (keeps historical continuity)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Camera sources ───────────────────────────────────
    # Comma-separated list of stream URIs.
    # Formats:
    #   rtsp://user:pass@192.168.1.10/stream1
    #   webcam:0                    (device index)
    #   file:/data/test_clip.mp4    (offline testing)
    cameras: str = "webcam:0"

    # ── YOLOX model selection ────────────────────────────
    # Valid values: yolox-nano | yolox-tiny | yolox-s | yolox-m | yolox-l | yolox-x
    yolox_model: str = "yolox-nano"

    # Inside the container this is bind-mounted from ./weights/ on the host.
    # Running locally outside Docker, set MODEL_WEIGHTS_DIR=./weights
    model_weights_dir: str = "/model-weights"

    # ── Inference thresholds ─────────────────────────────
    conf_threshold: float = 0.25   # minimum objectness × class confidence to keep
    nms_threshold:  float = 0.45   # IoU threshold for NMS suppression

    # ── Queue / backpressure ─────────────────────────────
    queue_max_size:   int        = 30       # max frames per camera queue before drop
    drop_policy:      DropPolicy = DropPolicy.oldest
    sample_every_k:   int        = 1        # run inference on every Kth frame

    # ── Worker pool ──────────────────────────────────────
    inference_workers: int = 2

    # ── Capture reconnect ────────────────────────────────
    capture_reconnect_delay:     float = 2.0   # initial backoff seconds
    capture_reconnect_max_delay: float = 30.0  # cap for exponential backoff

    # ── RabbitMQ ────────────────────────────────────────
    rabbitmq_url:         str = "amqp://guest:guest@rabbitmq:5672/"
    detections_exchange:  str = "detections"

    # ── FastAPI / metrics ────────────────────────────────
    metrics_port: int = 8001

    # ── Logging ──────────────────────────────────────────
    log_level: str = "INFO"

    # ── Derived helpers ──────────────────────────────────
    @property
    def camera_list(self) -> list[str]:
        return [c.strip() for c in self.cameras.split(",") if c.strip()]


settings = Settings()
