"""
YOLOX inference wrapper.

Handles the full predict cycle:
  1. Letterbox-resize the BGR frame to the model's input size.
  2. Convert to a float32 tensor (no ImageNet normalization — YOLOX uses raw [0,255]).
  3. Run the YOLOX model forward pass.
  4. Apply NMS postprocessing.
  5. Scale bounding boxes back to original image coordinates.
  6. Return a list of DetectionResult dataclasses.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import cv2
import numpy as np
import structlog
import torch

from classes import class_group, class_name, ClassGroup
from model_registry import ModelVariant, ensure_weights, get_variant

log = structlog.get_logger()


@dataclass
class DetectionResult:
    class_id:   int
    class_name: str
    group:      str
    confidence: float           # obj_conf × cls_conf
    bbox:       list[float]     # [x1, y1, x2, y2] in original image pixels


def _letterbox(
    img: np.ndarray,
    target_size: int,
) -> tuple[np.ndarray, float]:
    """
    Resize + pad image to (target_size × target_size) with grey border.
    Returns the padded image and the scale ratio (used to unscale boxes).
    """
    h, w = img.shape[:2]
    ratio = min(target_size / h, target_size / w)
    new_h, new_w = int(h * ratio), int(w * ratio)

    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    padded = np.full((target_size, target_size, 3), 114, dtype=np.uint8)
    padded[:new_h, :new_w] = resized

    return padded, ratio


class YoloxDetector:
    """
    Thread-safe inference engine wrapping a single YOLOX model.
    Each worker thread should own its own YoloxDetector instance to avoid
    locking the GIL during torch.no_grad() forward passes.
    """

    def __init__(
        self,
        model_name:     str,
        weights_dir:    str,
        conf_threshold: float = 0.25,
        nms_threshold:  float = 0.45,
        device:         str   = "cpu",
    ) -> None:
        self._variant:        ModelVariant = get_variant(model_name)
        self._weights_dir:    str          = weights_dir
        self._conf_threshold: float        = conf_threshold
        self._nms_threshold:  float        = nms_threshold
        self._device:         torch.device = torch.device(device)
        self._model:          torch.nn.Module | None = None

    # ── Public API ────────────────────────────────────────

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def model_name(self) -> str:
        return self._variant.name

    @property
    def input_size(self) -> int:
        return self._variant.input_size

    def load(self) -> None:
        """Download weights if missing, then load model onto device."""
        weight_file = ensure_weights(self._variant.name, self._weights_dir)

        log.info("model_loading", model=self._variant.name, device=str(self._device))

        from yolox.exp import get_exp  # noqa: PLC0415

        exp = get_exp(exp_file=None, exp_name=self._variant.exp_name)
        model = exp.get_model()
        model.eval()

        ckpt = torch.load(str(weight_file), map_location="cpu")
        model_state = ckpt.get("model", ckpt)
        model.load_state_dict(model_state)
        model = model.to(self._device)

        # Fuse Conv + BN layers for faster CPU inference
        from yolox.utils import fuse_model  # noqa: PLC0415
        model = fuse_model(model)
        model.eval()

        self._model = model
        log.info(
            "model_loaded",
            model=self._variant.name,
            params_m=self._variant.params_m,
            input_size=self._variant.input_size,
            device=str(self._device),
        )

    def predict(
        self,
        frame_bgr: np.ndarray,
    ) -> tuple[list[DetectionResult], float]:
        """
        Run inference on a single BGR frame.
        Returns (detections, inference_ms).
        """
        if self._model is None:
            raise RuntimeError("Call load() before predict()")

        img_h, img_w = frame_bgr.shape[:2]
        padded, ratio = _letterbox(frame_bgr, self._input_size_px)

        # HWC BGR → CHW float32, no normalization (YOLOX uses raw pixel values)
        tensor = torch.from_numpy(
            padded.transpose(2, 0, 1)
        ).float().unsqueeze(0).to(self._device)

        t0 = time.perf_counter()
        with torch.no_grad():
            outputs = self._model(tensor)
        inference_ms = (time.perf_counter() - t0) * 1000.0

        return self._postprocess(outputs, ratio, img_w, img_h), inference_ms

    # ── Private helpers ────────────────────────────────────

    @property
    def _input_size_px(self) -> int:
        return self._variant.input_size

    def _postprocess(
        self,
        raw_outputs: torch.Tensor,
        ratio:       float,
        img_w:       int,
        img_h:       int,
    ) -> list[DetectionResult]:
        from yolox.utils import postprocess  # noqa: PLC0415

        outputs = postprocess(
            raw_outputs,
            num_classes=80,
            conf_thre=self._conf_threshold,
            nms_thre=self._nms_threshold,
            class_agnostic=False,
        )

        if outputs[0] is None:
            return []

        detections_tensor = outputs[0].cpu().numpy()
        results: list[DetectionResult] = []

        for det in detections_tensor:
            x1, y1, x2, y2, obj_conf, cls_conf, cls_id_f = det

            # Scale boxes back to original image space
            x1 = max(0.0, x1 / ratio)
            y1 = max(0.0, y1 / ratio)
            x2 = min(float(img_w), x2 / ratio)
            y2 = min(float(img_h), y2 / ratio)

            cls_id    = int(cls_id_f)
            confidence = float(obj_conf * cls_conf)
            group      = class_group(cls_id)

            results.append(DetectionResult(
                class_id   = cls_id,
                class_name = class_name(cls_id),
                group      = group.value if group else "unknown",
                confidence = round(confidence, 4),
                bbox       = [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
            ))

        return results
