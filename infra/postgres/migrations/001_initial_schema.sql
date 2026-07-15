-- ============================================================
-- Migration: 001_initial_schema
-- Real-Time Inference Platform — PostgreSQL schema
--
-- Executed automatically by postgres:16-alpine on first startup
-- via the /docker-entrypoint-initdb.d/ mount.
-- ============================================================

-- ── Extensions ──────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- ── Enum types ───────────────────────────────────────────

CREATE TYPE source_type_enum AS ENUM (
    'rtsp',
    'webcam',
    'file'   -- useful for offline testing with video files
);

CREATE TYPE alert_channel_enum AS ENUM (
    'telegram',
    'webhook'
);

CREATE TYPE alert_status_enum AS ENUM (
    'pending',
    'sent',
    'failed',
    'suppressed'   -- debounced / duplicate
);

-- ── cameras ──────────────────────────────────────────────
-- One row per configured video source.
-- Created/updated via the API; read by the inference service on startup.

CREATE TABLE cameras (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT        NOT NULL,
    source_type  source_type_enum NOT NULL,
    source_uri   TEXT        NOT NULL,              -- rtsp://..., webcam:0, /data/video.mp4
    enabled      BOOLEAN     NOT NULL DEFAULT TRUE,
    -- Current operational state written by the inference service
    status       TEXT        NOT NULL DEFAULT 'unknown'
                             CHECK (status IN ('unknown', 'connecting', 'active', 'degraded', 'stopped')),
    -- Runtime-configurable per-camera overrides (null → use global defaults)
    queue_max_size   INT,
    sample_every_k   INT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT cameras_name_unique UNIQUE (name),
    CONSTRAINT cameras_source_uri_unique UNIQUE (source_uri)
);

-- Auto-update updated_at on every write
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER cameras_updated_at
    BEFORE UPDATE ON cameras
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── detections ───────────────────────────────────────────
-- One row per inference result (a single frame may contain N objects,
-- stored as a JSONB array so queries can filter by class, confidence, bbox).

CREATE TABLE detections (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id       UUID        NOT NULL REFERENCES cameras (id) ON DELETE CASCADE,
    -- Timestamp of the original captured frame (from the inference service)
    frame_ts        TIMESTAMPTZ NOT NULL,
    model           TEXT        NOT NULL,           -- e.g. "yolov8n"
    inference_ms    INT         NOT NULL CHECK (inference_ms >= 0),
    frame_width     INT,
    frame_height    INT,
    -- Array of detection objects:
    -- [{"class": "person", "confidence": 0.91, "bbox": [x1,y1,x2,y2]}, ...]
    objects         JSONB       NOT NULL DEFAULT '[]'::JSONB,
    object_count    INT         NOT NULL GENERATED ALWAYS AS (jsonb_array_length(objects)) STORED,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Deduplicate on redelivery: (camera_id, frame_ts) is the natural key
    -- Use the message UUID from RabbitMQ as the primary key for idempotency
    CONSTRAINT detections_camera_frame_unique UNIQUE (camera_id, frame_ts)
);

-- Time-ordered reads are the dominant access pattern
CREATE INDEX idx_detections_camera_frame_ts  ON detections (camera_id, frame_ts DESC);
CREATE INDEX idx_detections_frame_ts         ON detections (frame_ts DESC);
CREATE INDEX idx_detections_created_at       ON detections (created_at DESC);

-- GIN index for JSON queries: WHERE objects @> '[{"class": "person"}]'
CREATE INDEX idx_detections_objects_gin      ON detections USING GIN (objects);

-- ── alert_rules ──────────────────────────────────────────
-- Operator-defined rules: "notify when class X seen on camera Y
-- with confidence >= Z".  Evaluated by the consumer service.

CREATE TABLE alert_rules (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    -- NULL camera_id means the rule applies to all cameras
    camera_id       UUID        REFERENCES cameras (id) ON DELETE CASCADE,
    class_name      TEXT        NOT NULL,           -- YOLO class name, e.g. "person", "car"
    min_confidence  NUMERIC(4,3) NOT NULL DEFAULT 0.5
                                CHECK (min_confidence BETWEEN 0 AND 1),
    channel         alert_channel_enum NOT NULL,
    -- Telegram chat_id or webhook URL depending on channel
    target          TEXT        NOT NULL,
    enabled         BOOLEAN     NOT NULL DEFAULT TRUE,
    -- Suppress repeat alerts for this rule+camera for N seconds
    debounce_seconds INT         NOT NULL DEFAULT 60,
    -- Optional human-readable label shown in the React GUI
    label           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER alert_rules_updated_at
    BEFORE UPDATE ON alert_rules
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_alert_rules_camera_id ON alert_rules (camera_id) WHERE enabled = TRUE;
CREATE INDEX idx_alert_rules_class     ON alert_rules (class_name) WHERE enabled = TRUE;

-- ── alert_events ─────────────────────────────────────────
-- Audit log of every notification attempt.

CREATE TABLE alert_events (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id         UUID        NOT NULL REFERENCES alert_rules (id) ON DELETE CASCADE,
    detection_id    UUID        NOT NULL REFERENCES detections (id) ON DELETE CASCADE,
    status          alert_status_enum NOT NULL DEFAULT 'pending',
    -- Telegram message_id or HTTP response code stored for debugging
    provider_ref    TEXT,
    error_message   TEXT,
    sent_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alert_events_rule_id       ON alert_events (rule_id, created_at DESC);
CREATE INDEX idx_alert_events_detection_id  ON alert_events (detection_id);
CREATE INDEX idx_alert_events_status        ON alert_events (status) WHERE status = 'pending';

-- ── system_config ────────────────────────────────────────
-- Key-value store for runtime-mutable configuration (model selection,
-- global queue sizes, etc.).  The API reads/writes here; inference
-- service polls or receives a reload signal.

CREATE TABLE system_config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER system_config_updated_at
    BEFORE UPDATE ON system_config
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Seed with sensible defaults
INSERT INTO system_config (key, value, description) VALUES
    ('yolo_model',          'yolov8n.pt',  'Active YOLO model filename'),
    ('queue_max_size',      '30',          'Default per-camera queue capacity'),
    ('drop_policy',         'oldest',      'Frame drop policy: oldest | newest'),
    ('inference_workers',   '2',           'Number of parallel YOLO worker threads'),
    ('sample_every_k',      '1',           'Run inference every Kth frame (1 = every frame)');

-- ── Views ────────────────────────────────────────────────

-- Handy view for the API /metrics/summary endpoint
CREATE VIEW detection_summary AS
SELECT
    c.id                                    AS camera_id,
    c.name                                  AS camera_name,
    COUNT(d.id)                             AS total_detections,
    MAX(d.frame_ts)                         AS last_detection_at,
    ROUND(AVG(d.inference_ms))              AS avg_inference_ms,
    SUM(d.object_count)                     AS total_objects
FROM cameras c
LEFT JOIN detections d ON d.camera_id = c.id
GROUP BY c.id, c.name;

-- Recent alerts (last 24 h) for the dashboard
CREATE VIEW recent_alerts AS
SELECT
    ae.id,
    ae.status,
    ae.sent_at,
    ae.created_at,
    ar.class_name,
    ar.channel,
    ar.target,
    ar.label        AS rule_label,
    c.name          AS camera_name,
    d.frame_ts,
    d.objects
FROM alert_events ae
JOIN alert_rules  ar ON ar.id = ae.rule_id
JOIN detections   d  ON d.id  = ae.detection_id
JOIN cameras      c  ON c.id  = d.camera_id
WHERE ae.created_at > NOW() - INTERVAL '24 hours'
ORDER BY ae.created_at DESC;
