#!/usr/bin/env python3
"""
Download YOLOX weight files into ./weights/

Usage:
    # Download the default model (nano)
    python scripts/download_weights.py

    # Download a specific model
    python scripts/download_weights.py --model yolox-s

    # Download all models
    python scripts/download_weights.py --all

Weights are saved to ./weights/ which is bind-mounted into the inference
container at /model-weights.  The folder is gitignored — weights are never
committed to the repository.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from the project root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "inference"))

from model_registry import MODEL_NAMES_ORDERED, ensure_weights  # noqa: E402

WEIGHTS_DIR = str(Path(__file__).parent.parent / "weights")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download YOLOX weights")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--model",
        choices=MODEL_NAMES_ORDERED,
        default="yolox-nano",
        help="Model variant to download (default: yolox-nano)",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Download all six model variants",
    )
    args = parser.parse_args()

    models = MODEL_NAMES_ORDERED if args.all else [args.model]

    print(f"Saving to: {WEIGHTS_DIR}\n")
    for name in models:
        path = ensure_weights(name, WEIGHTS_DIR)
        size_mb = round(path.stat().st_size / 1e6, 1)
        print(f"  ✓ {name:12s}  {size_mb:6.1f} MB  →  {path}")


if __name__ == "__main__":
    main()
