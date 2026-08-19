CREATE TABLE dense_crowd_analysis_results (
    session_id BIGINT PRIMARY KEY
        REFERENCES monitoring_sessions(id) ON DELETE CASCADE,
    status VARCHAR(30) NOT NULL
        CHECK (status IN ('completed', 'unsupported')),
    crowd_count INTEGER CHECK (crowd_count >= 0),
    method_id VARCHAR(150),
    model_id VARCHAR(150),
    evaluated_candidate_id VARCHAR(150) NOT NULL,
    quality_gate_status VARCHAR(30) NOT NULL
        CHECK (quality_gate_status IN ('conditional', 'passed', 'failed')),
    evaluation_reference TEXT NOT NULL,
    reason_code VARCHAR(100),
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT dense_crowd_analysis_status_values
        CHECK (
            (
                status = 'unsupported'
                AND crowd_count IS NULL
                AND method_id IS NULL
                AND model_id IS NULL
                AND quality_gate_status = 'failed'
                AND reason_code IS NOT NULL
            )
            OR
            (
                status = 'completed'
                AND crowd_count IS NOT NULL
                AND method_id IS NOT NULL
                AND model_id IS NOT NULL
                AND quality_gate_status IN ('conditional', 'passed')
                AND reason_code IS NULL
            )
        )
);
