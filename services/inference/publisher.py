"""
RabbitMQ publisher — async (aio-pika).

Publishes detection results to the `detections` topic exchange with
routing key `camera.{camera_id}`.

Message format (JSON):
{
  "detection_id":   "uuid4",
  "camera_id":      "cam-01",
  "frame_timestamp": "2026-07-01T10:00:00.123Z",
  "model":          "yolox-s",
  "inference_ms":   42,
  "frame_width":    1920,
  "frame_height":   1080,
  "objects": [
    {
      "class":      "person",
      "group":      "people",
      "confidence": 0.91,
      "bbox":       [100.0, 200.0, 150.0, 300.0]
    }
  ]
}
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict

import aio_pika
import structlog

from config import Settings
from detector import DetectionResult

log = structlog.get_logger()


class DetectionPublisher:
    """
    Async publisher that holds one persistent AMQP connection and channel.
    Must be used from the asyncio event loop thread only.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings   = settings
        self._connection: aio_pika.RobustConnection | None = None
        self._channel:    aio_pika.Channel | None          = None
        self._exchange:   aio_pika.Exchange | None         = None

    async def connect(self) -> None:
        """Open a robust (auto-reconnecting) AMQP connection."""
        log.info("publisher_connecting", url=self._settings.rabbitmq_url)

        self._connection = await aio_pika.connect_robust(
            self._settings.rabbitmq_url,
            reconnect_interval=5,
            # fail_fast=False: don't crash on first connect — retry in the background.
            # The service stays up and publishes once the connection is established.
            fail_fast=False,
        )
        self._channel  = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(
            self._settings.detections_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        log.info(
            "publisher_connected",
            exchange=self._settings.detections_exchange,
        )

    async def disconnect(self) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
        log.info("publisher_disconnected")

    async def publish(
        self,
        camera_id:    str,
        frame_ts:     str,
        model:        str,
        inference_ms: int,
        frame_width:  int,
        frame_height: int,
        detections:   list[DetectionResult],
    ) -> None:
        """
        Serialize detection results to JSON and publish to RabbitMQ.
        Raises if the connection is not established — the pipeline will log
        the error and continue rather than crashing.
        """
        if self._exchange is None:
            raise RuntimeError("Publisher not connected — call connect() first")

        payload = {
            "detection_id":    str(uuid.uuid4()),
            "camera_id":       camera_id,
            "frame_timestamp": frame_ts,
            "model":           model,
            "inference_ms":    inference_ms,
            "frame_width":     frame_width,
            "frame_height":    frame_height,
            "objects": [
                {
                    "class":      d.class_name,
                    "group":      d.group,
                    "confidence": d.confidence,
                    "bbox":       d.bbox,
                }
                for d in detections
            ],
        }

        routing_key = f"camera.{camera_id}"
        body = json.dumps(payload, separators=(",", ":")).encode()

        message = aio_pika.Message(
            body        = body,
            content_type = "application/json",
            delivery_mode = aio_pika.DeliveryMode.PERSISTENT,
            message_id  = payload["detection_id"],
        )

        await self._exchange.publish(message, routing_key=routing_key)

        log.debug(
            "detection_published",
            camera_id=camera_id,
            routing_key=routing_key,
            object_count=len(detections),
            inference_ms=inference_ms,
        )

        # Also publish to alert.high if any object has confidence > 0.85
        high_confidence = [d for d in detections if d.confidence >= 0.85]
        if high_confidence:
            alert_payload = {**payload, "objects": [
                {"class": d.class_name, "group": d.group,
                 "confidence": d.confidence, "bbox": d.bbox}
                for d in high_confidence
            ]}
            alert_body = json.dumps(alert_payload, separators=(",", ":")).encode()
            await self._exchange.publish(
                aio_pika.Message(
                    body=alert_body,
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    message_id=str(uuid.uuid4()),
                    priority=9,
                ),
                routing_key="alert.high",
            )
