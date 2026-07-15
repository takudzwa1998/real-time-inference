"""
Per-camera capture thread.

Each camera runs its own CaptureThread that:
  - Opens the video source via OpenCV (RTSP, webcam, or file).
  - Reads frames in a tight loop.
  - Pushes frames into the camera's bounded queue.
  - Drops frames according to drop_policy when the queue is full.
  - Updates Prometheus metrics (FPS, frames dropped).
  - Reconnects with exponential backoff on stream failure.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import cv2
import numpy as np
import structlog

from config import DropPolicy, Settings

log = structlog.get_logger()


@dataclass
class CapturedFrame:
    camera_id:  str
    frame_ts:   datetime          # UTC timestamp of the read() call
    frame_bgr:  np.ndarray
    frame_index: int              # monotonic counter per camera (for SAMPLE_EVERY_K)


class CaptureThread(threading.Thread):
    """
    Background thread: continuously reads frames from one video source
    and places them onto a bounded queue for the worker pool.
    """

    def __init__(
        self,
        camera_id:      str,
        source_uri:     str,
        frame_queue:    "queue.Queue[CapturedFrame]",
        settings:       Settings,
        # Prometheus gauge references (created by the pipeline, injected here)
        fps_gauge=None,
        dropped_counter=None,
    ) -> None:
        super().__init__(name=f"capture-{camera_id}", daemon=True)
        self._camera_id    = camera_id
        self._source_uri   = source_uri
        self._queue        = frame_queue
        self._settings     = settings
        self._fps_gauge    = fps_gauge
        self._dropped_ctr  = dropped_counter

        self._stop_event   = threading.Event()
        self._status       = "stopped"     # stopped | connecting | active | degraded
        self._frame_index  = 0

    @property
    def camera_id(self) -> str:
        return self._camera_id

    @property
    def status(self) -> str:
        return self._status

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        log.info("capture_thread_started", camera_id=self._camera_id, source=self._source_uri)
        backoff = self._settings.capture_reconnect_delay

        while not self._stop_event.is_set():
            self._status = "connecting"
            cap = self._open_capture()

            if cap is None or not cap.isOpened():
                self._status = "degraded"
                log.warning(
                    "capture_open_failed",
                    camera_id=self._camera_id,
                    source=self._source_uri,
                    retry_in=backoff,
                )
                self._stop_event.wait(backoff)
                backoff = min(backoff * 2, self._settings.capture_reconnect_max_delay)
                continue

            backoff = self._settings.capture_reconnect_delay
            self._status = "active"
            log.info("capture_stream_opened", camera_id=self._camera_id, source=self._source_uri)

            self._read_loop(cap)

            cap.release()
            if not self._stop_event.is_set():
                self._status = "degraded"
                log.warning(
                    "capture_stream_lost",
                    camera_id=self._camera_id,
                    retry_in=backoff,
                )
                self._stop_event.wait(backoff)
                backoff = min(backoff * 2, self._settings.capture_reconnect_max_delay)

        self._status = "stopped"
        log.info("capture_thread_stopped", camera_id=self._camera_id)

    # ── Private ───────────────────────────────────────────

    def _open_capture(self) -> cv2.VideoCapture | None:
        uri = self._resolve_uri()
        try:
            cap = cv2.VideoCapture(uri)
            # Increase RTSP buffer to reduce initial stall
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
            return cap
        except Exception as exc:
            log.error("capture_open_exception", camera_id=self._camera_id, error=str(exc))
            return None

    def _resolve_uri(self) -> str | int:
        """Convert 'webcam:0' → int(0), 'file:/path' → '/path', RTSP → unchanged."""
        uri = self._source_uri
        if uri.startswith("webcam:"):
            return int(uri.split(":")[1])
        if uri.startswith("file:"):
            return uri[5:]
        return uri

    def _read_loop(self, cap: cv2.VideoCapture) -> None:
        fps_window_start  = time.monotonic()
        fps_frame_count   = 0
        sample_k          = self._settings.sample_every_k

        while not self._stop_event.is_set():
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            self._frame_index += 1
            fps_frame_count   += 1
            now = datetime.now(timezone.utc)

            # FPS metric — update every second
            elapsed = time.monotonic() - fps_window_start
            if elapsed >= 1.0:
                fps = fps_frame_count / elapsed
                if self._fps_gauge is not None:
                    self._fps_gauge.labels(camera_id=self._camera_id).set(fps)
                fps_frame_count  = 0
                fps_window_start = time.monotonic()

            # Frame sampling
            if self._frame_index % sample_k != 0:
                continue

            captured = CapturedFrame(
                camera_id   = self._camera_id,
                frame_ts    = now,
                frame_bgr   = frame,
                frame_index = self._frame_index,
            )

            self._enqueue(captured)

    def _enqueue(self, frame: CapturedFrame) -> None:
        policy = self._settings.drop_policy

        if policy == DropPolicy.newest:
            # Drop the incoming frame if the queue is full
            try:
                self._queue.put_nowait(frame)
            except queue.Full:
                if self._dropped_ctr is not None:
                    self._dropped_ctr.labels(
                        camera_id=self._camera_id, reason="queue_full_newest"
                    ).inc()
                log.debug("frame_dropped_newest", camera_id=self._camera_id)
        else:
            # Drop the oldest frame to make room for the incoming one
            while True:
                try:
                    self._queue.put_nowait(frame)
                    break
                except queue.Full:
                    try:
                        self._queue.get_nowait()
                        if self._dropped_ctr is not None:
                            self._dropped_ctr.labels(
                                camera_id=self._camera_id, reason="queue_full_oldest"
                            ).inc()
                        log.debug("frame_dropped_oldest", camera_id=self._camera_id)
                    except queue.Empty:
                        pass
