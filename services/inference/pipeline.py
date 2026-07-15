"""
Inference pipeline — wires capture threads → per-camera queues → worker pool.

Architecture
------------
  CaptureThread (one per camera)
      └─► queue.Queue(maxsize=N)   ← per-camera bounded queue
              └─► WorkerThread (pool of M, shared round-robin)
                      └─► detect → publish callback

Worker threads pull from a shared work queue that aggregates all per-camera
queues.  This avoids a worker starving when a slow camera dominates.

Hot-swap
--------
  pipeline.swap_model(new_name) drains the shared queue, replaces the
  detectors across all workers, then resumes.  Called by the /config/model
  API endpoint.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

import structlog

from capture import CaptureThread, CapturedFrame
from config import Settings
from detector import DetectionResult, YoloxDetector

log = structlog.get_logger()

# Type alias for the async publish callback
PublishCallback = Callable[
    [str, str, str, int, int, int, list[DetectionResult]],
    Coroutine[Any, Any, None],
]


class InferencePipeline:
    """
    Manages the full capture → queue → inference → publish lifecycle.
    Call start() once; stop() to shut down cleanly.
    """

    def __init__(self, settings: Settings, event_loop: asyncio.AbstractEventLoop) -> None:
        self._settings    = settings
        self._loop        = event_loop

        # Prometheus metric handles — injected after metrics are registered in main.py
        self.fps_gauge        = None
        self.queue_depth_gauge = None
        self.latency_hist     = None
        self.detections_ctr   = None
        self.dropped_ctr      = None

        # Per-camera queues (depth-monitored separately for Prometheus)
        self._camera_queues: dict[str, "queue.Queue[CapturedFrame]"] = {}

        # Single aggregated queue fed by a fan-in thread
        self._work_queue: "queue.Queue[CapturedFrame]" = queue.Queue(
            maxsize=settings.queue_max_size * max(1, len(settings.camera_list))
        )

        self._capture_threads: list[CaptureThread]   = []
        self._worker_threads:  list[threading.Thread] = []
        self._fanin_thread:    threading.Thread | None = None

        self._stop_event    = threading.Event()
        self._publish_cb:   PublishCallback | None = None
        self._current_model = settings.yolox_model
        self._swap_lock     = threading.Lock()
        self._detectors:    list[YoloxDetector] = []

    # ── Public API ────────────────────────────────────────

    def set_publish_callback(self, cb: PublishCallback) -> None:
        self._publish_cb = cb

    def start(self) -> None:
        log.info("pipeline_starting", model=self._current_model,
                 cameras=self._settings.camera_list, workers=self._settings.inference_workers)

        self._start_capture_threads()
        self._start_fanin_thread()
        self._start_worker_threads()
        self._start_queue_depth_monitor()

        log.info("pipeline_started")

    def stop(self) -> None:
        log.info("pipeline_stopping")
        self._stop_event.set()

        for ct in self._capture_threads:
            ct.stop()
        for ct in self._capture_threads:
            ct.join(timeout=5)

        if self._fanin_thread:
            self._fanin_thread.join(timeout=5)

        for wt in self._worker_threads:
            wt.join(timeout=10)

        log.info("pipeline_stopped")

    def swap_model(self, new_model_name: str) -> None:
        """Hot-swap the YOLOX model across all workers (drain → reload → resume)."""
        with self._swap_lock:
            log.info("model_swap_started", old=self._current_model, new=new_model_name)

            # Drain the work queue
            drained = 0
            while not self._work_queue.empty():
                try:
                    self._work_queue.get_nowait()
                    drained += 1
                except queue.Empty:
                    break

            log.info("model_swap_queue_drained", frames_discarded=drained)

            # Reload each worker's detector
            for detector in self._detectors:
                detector._variant = __import__("model_registry").get_variant(new_model_name)
                detector._model   = None
                detector.load()

            self._current_model = new_model_name
            log.info("model_swap_complete", model=new_model_name)

    @property
    def camera_statuses(self) -> dict[str, str]:
        return {ct.camera_id: ct.status for ct in self._capture_threads}

    @property
    def current_model(self) -> str:
        return self._current_model

    # ── Private ───────────────────────────────────────────

    def _start_capture_threads(self) -> None:
        for uri in self._settings.camera_list:
            camera_id = self._uri_to_id(uri)
            q: "queue.Queue[CapturedFrame]" = queue.Queue(
                maxsize=self._settings.queue_max_size
            )
            self._camera_queues[camera_id] = q

            ct = CaptureThread(
                camera_id    = camera_id,
                source_uri   = uri,
                frame_queue  = q,
                settings     = self._settings,
                fps_gauge    = self.fps_gauge,
                dropped_counter = self.dropped_ctr,
            )
            ct.start()
            self._capture_threads.append(ct)

    def _start_fanin_thread(self) -> None:
        """Fan all per-camera queues into one shared work queue."""
        def fanin():
            while not self._stop_event.is_set():
                for q in self._camera_queues.values():
                    try:
                        frame = q.get_nowait()
                        self._work_queue.put(frame, timeout=0.1)
                    except queue.Empty:
                        pass
                    except queue.Full:
                        pass
                time.sleep(0.001)   # 1 ms polling — tight but not a busy spin

        self._fanin_thread = threading.Thread(
            target=fanin, name="pipeline-fanin", daemon=True
        )
        self._fanin_thread.start()

    def _start_worker_threads(self) -> None:
        s = self._settings
        for i in range(s.inference_workers):
            detector = YoloxDetector(
                model_name     = s.yolox_model,
                weights_dir    = s.model_weights_dir,
                conf_threshold = s.conf_threshold,
                nms_threshold  = s.nms_threshold,
                device         = "cuda" if self._cuda_available() else "cpu",
            )
            detector.load()
            self._detectors.append(detector)

            wt = threading.Thread(
                target=self._worker_loop,
                args=(detector,),
                name=f"worker-{i}",
                daemon=True,
            )
            wt.start()
            self._worker_threads.append(wt)

    def _start_queue_depth_monitor(self) -> None:
        """Periodically update the queue depth Prometheus gauges."""
        def monitor():
            while not self._stop_event.is_set():
                if self.queue_depth_gauge is not None:
                    for cam_id, q in self._camera_queues.items():
                        self.queue_depth_gauge.labels(camera_id=cam_id).set(q.qsize())
                time.sleep(1.0)

        t = threading.Thread(target=monitor, name="queue-monitor", daemon=True)
        t.start()

    def _worker_loop(self, detector: YoloxDetector) -> None:
        log.info("worker_started", model=detector.model_name)

        while not self._stop_event.is_set():
            try:
                frame: CapturedFrame = self._work_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                detections, inference_ms = detector.predict(frame.frame_bgr)
            except Exception as exc:
                log.error("inference_error", camera_id=frame.camera_id, error=str(exc))
                continue

            # Update Prometheus metrics
            if self.latency_hist is not None:
                self.latency_hist.labels(
                    camera_id=frame.camera_id, model=detector.model_name
                ).observe(inference_ms / 1000.0)

            if self.detections_ctr is not None:
                for det in detections:
                    self.detections_ctr.labels(
                        camera_id=frame.camera_id, cls=det.class_name
                    ).inc()

            # Publish via async callback
            if self._publish_cb and detections:
                h, w = frame.frame_bgr.shape[:2]
                coro = self._publish_cb(
                    frame.camera_id,
                    frame.frame_ts.isoformat(),
                    detector.model_name,
                    round(inference_ms),
                    w,
                    h,
                    detections,
                )
                asyncio.run_coroutine_threadsafe(coro, self._loop)

        log.info("worker_stopped")

    @staticmethod
    def _uri_to_id(uri: str) -> str:
        """Generate a stable short camera_id from a URI."""
        if uri.startswith("webcam:"):
            return f"webcam-{uri.split(':')[1]}"
        if uri.startswith("file:"):
            return "file-" + uri.split("/")[-1].replace(".", "-")
        # RTSP: use host + last path segment
        try:
            from urllib.parse import urlparse
            p = urlparse(uri)
            return f"{p.hostname}-{p.path.strip('/').replace('/', '-')}"
        except Exception:
            return uri[:32].replace("/", "-").replace(":", "-")

    @staticmethod
    def _cuda_available() -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
