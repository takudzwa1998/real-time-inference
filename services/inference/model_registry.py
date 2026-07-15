"""
YOLOX model registry — metadata for all six model variants and weight download.

All weights are from the official Megvii YOLOX 0.1.1rc0 release (Apache 2.0).
Download URL: https://github.com/Megvii-BaseDetection/YOLOX/releases/tag/0.1.1rc0
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import requests
import structlog
from tqdm import tqdm

log = structlog.get_logger()


@dataclass(frozen=True)
class ModelVariant:
    # Name used in YOLOX's get_exp() and as the user-facing model identifier
    name:        str
    # YOLOX experiment name (passed to get_exp(exp_name=...))
    exp_name:    str
    # Square input resolution the model was trained at
    input_size:  int
    # Weight filename saved to disk
    weight_file: str
    # Direct download URL (GitHub release asset, Apache-2.0 weights)
    weight_url:  str
    # Approximate parameter count (millions) — shown in /config/model endpoint
    params_m:    float
    # COCO val mAP 0.5:0.95 from official benchmark
    map_val:     float
    # V100 latency in milliseconds (single image, from official benchmark)
    latency_ms:  float | None


# ── Registry ──────────────────────────────────────────────

MODELS: dict[str, ModelVariant] = {
    "yolox-nano": ModelVariant(
        name        = "yolox-nano",
        exp_name    = "yolox-nano",
        input_size  = 416,
        weight_file = "yolox_nano.pth",
        weight_url  = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.pth",
        params_m    = 0.91,
        map_val     = 25.8,
        latency_ms  = None,   # not benchmarked on V100 (edge model)
    ),
    "yolox-tiny": ModelVariant(
        name        = "yolox-tiny",
        exp_name    = "yolox-tiny",
        input_size  = 416,
        weight_file = "yolox_tiny.pth",
        weight_url  = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_tiny.pth",
        params_m    = 5.06,
        map_val     = 32.8,
        latency_ms  = None,
    ),
    "yolox-s": ModelVariant(
        name        = "yolox-s",
        exp_name    = "yolox-s",
        input_size  = 640,
        weight_file = "yolox_s.pth",
        weight_url  = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.pth",
        params_m    = 9.0,
        map_val     = 40.5,
        latency_ms  = 9.8,
    ),
    "yolox-m": ModelVariant(
        name        = "yolox-m",
        exp_name    = "yolox-m",
        input_size  = 640,
        weight_file = "yolox_m.pth",
        weight_url  = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_m.pth",
        params_m    = 25.3,
        map_val     = 46.9,
        latency_ms  = 12.3,
    ),
    "yolox-l": ModelVariant(
        name        = "yolox-l",
        exp_name    = "yolox-l",
        input_size  = 640,
        weight_file = "yolox_l.pth",
        weight_url  = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_l.pth",
        params_m    = 54.2,
        map_val     = 49.7,
        latency_ms  = 14.5,
    ),
    "yolox-x": ModelVariant(
        name        = "yolox-x",
        exp_name    = "yolox-x",
        input_size  = 640,
        weight_file = "yolox_x.pth",
        weight_url  = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_x.pth",
        params_m    = 99.1,
        map_val     = 51.1,
        latency_ms  = 17.3,
    ),
}

# Ordered from lightest to heaviest (used in API responses / docs)
MODEL_NAMES_ORDERED: list[str] = [
    "yolox-nano", "yolox-tiny", "yolox-s", "yolox-m", "yolox-l", "yolox-x"
]


def get_variant(model_name: str) -> ModelVariant:
    name = model_name.lower().strip()
    if name not in MODELS:
        valid = ", ".join(MODEL_NAMES_ORDERED)
        raise ValueError(f"Unknown model '{model_name}'. Valid options: {valid}")
    return MODELS[name]


def weight_path(model_name: str, weights_dir: str) -> Path:
    variant = get_variant(model_name)
    return Path(weights_dir) / variant.weight_file


def ensure_weights(model_name: str, weights_dir: str) -> Path:
    """
    Return the path to the weight file, downloading it first if absent.
    Uses a streaming download with a progress bar so large files (yolox-x ~200 MB)
    don't time out silently.
    """
    variant = get_variant(model_name)
    dest = Path(weights_dir) / variant.weight_file
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        log.info("model_weights_found", model=model_name, path=str(dest))
        return dest

    log.info(
        "model_weights_downloading",
        model=model_name,
        url=variant.weight_url,
        dest=str(dest),
        params_m=variant.params_m,
    )

    try:
        response = requests.get(variant.weight_url, stream=True, timeout=60)
        response.raise_for_status()

        total = int(response.headers.get("content-length", 0))
        tmp = dest.with_suffix(".tmp")

        with open(tmp, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True,
            desc=f"Downloading {variant.weight_file}",
        ) as bar:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                bar.update(len(chunk))

        tmp.rename(dest)
        log.info("model_weights_downloaded", model=model_name, size_mb=round(dest.stat().st_size / 1e6, 1))

    except Exception as exc:
        if tmp.exists():
            tmp.unlink()
        raise RuntimeError(f"Failed to download {model_name} weights: {exc}") from exc

    return dest
