CREATE TABLE IF NOT EXISTS monitoring_sessions (
    id BIGSERIAL PRIMARY KEY,
    session_name VARCHAR(150),
    status VARCHAR(30) NOT NULL DEFAULT 'created',
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS input_sources (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES monitoring_sessions(id) ON DELETE CASCADE,
    source_type VARCHAR(20) NOT NULL CHECK (source_type IN ('image', 'video')),
    file_path TEXT NOT NULL,
    original_filename VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS processed_frames (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES monitoring_sessions(id) ON DELETE CASCADE,
    input_source_id BIGINT NOT NULL REFERENCES input_sources(id) ON DELETE CASCADE,
    frame_number INTEGER NOT NULL DEFAULT 0 CHECK (frame_number >= 0),
    frame_timestamp_seconds NUMERIC(12, 3) CHECK (frame_timestamp_seconds >= 0),
    image_width INTEGER CHECK (image_width > 0),
    image_height INTEGER CHECK (image_height > 0),
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (input_source_id, frame_number)
);

CREATE TABLE IF NOT EXISTS grid_cells (
    id BIGSERIAL PRIMARY KEY,
    processed_frame_id BIGINT NOT NULL REFERENCES processed_frames(id) ON DELETE CASCADE,
    row_index INTEGER NOT NULL CHECK (row_index >= 0),
    column_index INTEGER NOT NULL CHECK (column_index >= 0),
    x_min NUMERIC(10, 2) NOT NULL CHECK (x_min >= 0),
    y_min NUMERIC(10, 2) NOT NULL CHECK (y_min >= 0),
    x_max NUMERIC(10, 2) NOT NULL CHECK (x_max >= x_min),
    y_max NUMERIC(10, 2) NOT NULL CHECK (y_max >= y_min),
    UNIQUE (processed_frame_id, row_index, column_index)
);

CREATE TABLE IF NOT EXISTS detection_results (
    id BIGSERIAL PRIMARY KEY,
    processed_frame_id BIGINT NOT NULL REFERENCES processed_frames(id) ON DELETE CASCADE,
    object_class VARCHAR(100) NOT NULL,
    confidence NUMERIC(6, 5) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    bbox_x_min NUMERIC(10, 2) NOT NULL CHECK (bbox_x_min >= 0),
    bbox_y_min NUMERIC(10, 2) NOT NULL CHECK (bbox_y_min >= 0),
    bbox_x_max NUMERIC(10, 2) NOT NULL CHECK (bbox_x_max >= bbox_x_min),
    bbox_y_max NUMERIC(10, 2) NOT NULL CHECK (bbox_y_max >= bbox_y_min),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS object_count_summaries (
    id BIGSERIAL PRIMARY KEY,
    processed_frame_id BIGINT NOT NULL REFERENCES processed_frames(id) ON DELETE CASCADE,
    grid_cell_id BIGINT REFERENCES grid_cells(id) ON DELETE CASCADE,
    object_class VARCHAR(100) NOT NULL,
    object_count INTEGER NOT NULL CHECK (object_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    processed_frame_id BIGINT NOT NULL REFERENCES processed_frames(id) ON DELETE CASCADE,
    grid_cell_id BIGINT REFERENCES grid_cells(id) ON DELETE SET NULL,
    alert_type VARCHAR(100) NOT NULL,
    severity VARCHAR(30) NOT NULL DEFAULT 'warning',
    message TEXT NOT NULL,
    measured_value NUMERIC(12, 3),
    threshold_value NUMERIC(12, 3),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_input_sources_session_id
    ON input_sources(session_id);

CREATE INDEX IF NOT EXISTS idx_processed_frames_session_id
    ON processed_frames(session_id);

CREATE INDEX IF NOT EXISTS idx_detection_results_processed_frame_id
    ON detection_results(processed_frame_id);

CREATE INDEX IF NOT EXISTS idx_object_count_summaries_processed_frame_id
    ON object_count_summaries(processed_frame_id);

CREATE INDEX IF NOT EXISTS idx_grid_cells_processed_frame_id
    ON grid_cells(processed_frame_id);

CREATE INDEX IF NOT EXISTS idx_alerts_processed_frame_id
    ON alerts(processed_frame_id);
