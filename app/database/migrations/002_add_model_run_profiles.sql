CREATE TABLE model_run_profiles (
    session_id BIGINT PRIMARY KEY
        REFERENCES monitoring_sessions(id) ON DELETE CASCADE,
    profile_id VARCHAR(150) NOT NULL,
    model_id VARCHAR(150) NOT NULL,
    quality_gate_status VARCHAR(30) NOT NULL
        CHECK (
            quality_gate_status IN (
                'not_evaluated', 'conditional', 'passed', 'failed'
            )
        ),
    evaluation_reference TEXT NOT NULL,
    checkpoint_path TEXT NOT NULL,
    checkpoint_sha256 CHAR(64) NOT NULL
        CHECK (checkpoint_sha256 ~ '^[0-9a-f]{64}$'),
    class_mapping JSONB NOT NULL
        CHECK (jsonb_typeof(class_mapping) = 'object'),
    confidence NUMERIC(6, 5) NOT NULL
        CHECK (confidence > 0 AND confidence <= 1),
    image_size INTEGER NOT NULL CHECK (image_size > 0),
    scale_factor INTEGER NOT NULL CHECK (scale_factor > 0),
    max_detections INTEGER NOT NULL CHECK (max_detections > 0),
    numeric_precision VARCHAR(20) NOT NULL
        CHECK (numeric_precision IN ('float16', 'float32')),
    device VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
