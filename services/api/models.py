"""
SQLModel table definitions for the Real-Time Inference Platform.

Convention
----------
- *Base   — shared fields, used for input validation (no table=True)
- *       — table model (inherits Base, adds id + server-set fields)
- *Create — request body for POST endpoints (inherits Base)
- *Update — request body for PATCH endpoints (all fields Optional)
- *Read   — response schema (inherits table model, safe to serialise)

The table=True models map 1-to-1 with infra/postgres/migrations/001_initial_schema.sql.
SQLModel uses SQLAlchemy 2 under the hood, so async sessions work out of the box.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel


# ── Enum types ────────────────────────────────────────────
# Mirror the PostgreSQL ENUM types so Python and DB stay in sync.

class SourceType(str, enum.Enum):
    rtsp   = "rtsp"
    webcam = "webcam"
    file   = "file"


class CameraStatus(str, enum.Enum):
    unknown    = "unknown"
    connecting = "connecting"
    active     = "active"
    degraded   = "degraded"
    stopped    = "stopped"


class AlertChannel(str, enum.Enum):
    telegram = "telegram"
    webhook  = "webhook"


class AlertStatus(str, enum.Enum):
    pending    = "pending"
    sent       = "sent"
    failed     = "failed"
    suppressed = "suppressed"


# ─────────────────────────────────────────────────────────
# Camera
# ─────────────────────────────────────────────────────────

class CameraBase(SQLModel):
    name:            str        = Field(min_length=1, max_length=128)
    source_type:     SourceType
    source_uri:      str        = Field(min_length=1, max_length=512)
    enabled:         bool       = Field(default=True)
    queue_max_size:  int | None = Field(default=None, ge=1, le=10_000)
    sample_every_k:  int | None = Field(default=None, ge=1, le=100)


class Camera(CameraBase, table=True):
    __tablename__ = "cameras"

    id:         uuid.UUID    = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    status:     CameraStatus = Field(default=CameraStatus.unknown)
    created_at: datetime     = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    updated_at: datetime     = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={"server_default": text("NOW()"), "onupdate": text("NOW()")},
    )

    # Relationships (loaded lazily by default in async mode — use selectinload)
    detections:  list["Detection"]  = Relationship(back_populates="camera")
    alert_rules: list["AlertRule"]  = Relationship(back_populates="camera")


class CameraCreate(CameraBase):
    pass


class CameraUpdate(SQLModel):
    name:           str | None        = Field(default=None, min_length=1, max_length=128)
    source_uri:     str | None        = Field(default=None, min_length=1)
    enabled:        bool | None       = None
    status:         CameraStatus | None = None
    queue_max_size: int | None        = Field(default=None, ge=1, le=10_000)
    sample_every_k: int | None        = Field(default=None, ge=1, le=100)


class CameraRead(CameraBase):
    id:         uuid.UUID
    status:     CameraStatus
    created_at: datetime
    updated_at: datetime


# ─────────────────────────────────────────────────────────
# Detection
# ─────────────────────────────────────────────────────────

# A single detected object inside a frame.
class DetectionObject(SQLModel):
    cls:        str   = Field(alias="class")
    confidence: float = Field(ge=0.0, le=1.0)
    # [x1, y1, x2, y2] in pixels
    bbox:       list[float] = Field(min_length=4, max_length=4)

    model_config = {"populate_by_name": True}


class DetectionBase(SQLModel):
    camera_id:    uuid.UUID
    frame_ts:     datetime
    model:        str = Field(min_length=1, max_length=64)
    inference_ms: int = Field(ge=0)
    frame_width:  int | None = None
    frame_height: int | None = None


class Detection(DetectionBase, table=True):
    __tablename__ = "detections"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    # JSONB column — stored as a raw list[dict]; parsed into DetectionObject on read
    objects: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={"server_default": text("NOW()")},
    )

    camera:        "Camera"           = Relationship(back_populates="detections")
    alert_events:  list["AlertEvent"] = Relationship(back_populates="detection")


class DetectionCreate(DetectionBase):
    objects: list[DetectionObject] = Field(default_factory=list)


class DetectionRead(DetectionBase):
    id:           uuid.UUID
    objects:      list[dict[str, Any]]
    object_count: int                  # computed on the way out
    created_at:   datetime

    @property  # type: ignore[override]
    def object_count(self) -> int:  # noqa: F811
        return len(self.objects)


# ─────────────────────────────────────────────────────────
# AlertRule
# ─────────────────────────────────────────────────────────

class AlertRuleBase(SQLModel):
    # NULL camera_id means "all cameras"
    camera_id:        uuid.UUID | None = None
    class_name:       str              = Field(min_length=1, max_length=64)
    min_confidence:   float            = Field(default=0.5, ge=0.0, le=1.0)
    channel:          AlertChannel
    target:           str              = Field(min_length=1, max_length=512,
                                               description="Telegram chat_id or webhook URL")
    enabled:          bool             = Field(default=True)
    debounce_seconds: int              = Field(default=60, ge=0)
    label:            str | None       = Field(default=None, max_length=128)


class AlertRule(AlertRuleBase, table=True):
    __tablename__ = "alert_rules"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={"server_default": text("NOW()"), "onupdate": text("NOW()")},
    )

    camera:       "Camera | None"    = Relationship(back_populates="alert_rules")
    alert_events: list["AlertEvent"] = Relationship(back_populates="rule")


class AlertRuleCreate(AlertRuleBase):
    pass


class AlertRuleUpdate(SQLModel):
    class_name:       str | None          = Field(default=None, min_length=1)
    min_confidence:   float | None        = Field(default=None, ge=0.0, le=1.0)
    channel:          AlertChannel | None = None
    target:           str | None          = Field(default=None, min_length=1)
    enabled:          bool | None         = None
    debounce_seconds: int | None          = Field(default=None, ge=0)
    label:            str | None          = None


class AlertRuleRead(AlertRuleBase):
    id:         uuid.UUID
    created_at: datetime
    updated_at: datetime


# ─────────────────────────────────────────────────────────
# AlertEvent
# ─────────────────────────────────────────────────────────

class AlertEventBase(SQLModel):
    rule_id:      uuid.UUID
    detection_id: uuid.UUID
    status:       AlertStatus = Field(default=AlertStatus.pending)
    provider_ref: str | None  = None
    error_message: str | None = None
    sent_at:      datetime | None = None


class AlertEvent(AlertEventBase, table=True):
    __tablename__ = "alert_events"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={"server_default": text("NOW()")},
    )

    rule:      "AlertRule" = Relationship(back_populates="alert_events")
    detection: "Detection" = Relationship(back_populates="alert_events")


class AlertEventRead(AlertEventBase):
    id:         uuid.UUID
    created_at: datetime


# ─────────────────────────────────────────────────────────
# SystemConfig
# ─────────────────────────────────────────────────────────

class SystemConfig(SQLModel, table=True):
    __tablename__ = "system_config"

    key:         str      = Field(primary_key=True)
    value:       str
    description: str | None = None
    updated_at:  datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={"server_default": text("NOW()"), "onupdate": text("NOW()")},
    )


class SystemConfigRead(SQLModel):
    key:         str
    value:       str
    description: str | None
    updated_at:  datetime


class SystemConfigUpdate(SQLModel):
    value: str
