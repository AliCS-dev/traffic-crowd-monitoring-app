CREATE TABLE video_analysis_jobs (
    session_id BIGINT PRIMARY KEY
        REFERENCES monitoring_sessions(id) ON DELETE CASCADE,
    input_source_id BIGINT NOT NULL UNIQUE
        REFERENCES input_sources(id) ON DELETE CASCADE,
    status VARCHAR(30) NOT NULL
        CHECK (status IN ('queued', 'processing', 'completed', 'failed')),
    sampling_interval_seconds NUMERIC(10, 3) NOT NULL
        CHECK (sampling_interval_seconds > 0),
    grid_rows INTEGER CHECK (grid_rows > 0),
    grid_columns INTEGER CHECK (grid_columns > 0),
    total_source_frames INTEGER NOT NULL CHECK (total_source_frames > 0),
    sampled_frames_total INTEGER NOT NULL CHECK (sampled_frames_total > 0),
    sampled_frames_processed INTEGER NOT NULL DEFAULT 0
        CHECK (
            sampled_frames_processed >= 0
            AND sampled_frames_processed <= sampled_frames_total
        ),
    failure_code VARCHAR(100),
    failure_message TEXT,
    queued_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    CONSTRAINT video_analysis_grid_pair
        CHECK (
            (grid_rows IS NULL AND grid_columns IS NULL)
            OR
            (grid_rows IS NOT NULL AND grid_columns IS NOT NULL)
        ),
    CONSTRAINT video_analysis_status_values
        CHECK (
            (
                status = 'queued'
                AND started_at IS NULL
                AND finished_at IS NULL
                AND failure_code IS NULL
                AND failure_message IS NULL
            )
            OR
            (
                status = 'processing'
                AND started_at IS NOT NULL
                AND finished_at IS NULL
                AND failure_code IS NULL
                AND failure_message IS NULL
            )
            OR
            (
                status = 'completed'
                AND started_at IS NOT NULL
                AND finished_at IS NOT NULL
                AND sampled_frames_processed = sampled_frames_total
                AND failure_code IS NULL
                AND failure_message IS NULL
            )
            OR
            (
                status = 'failed'
                AND finished_at IS NOT NULL
                AND failure_code IS NOT NULL
                AND failure_message IS NOT NULL
            )
        )
);

CREATE INDEX idx_video_analysis_jobs_status_queued
    ON video_analysis_jobs(status, queued_at, session_id);
