ALTER TABLE alerts
    ADD COLUMN analysis_method VARCHAR(50),
    ADD COLUMN object_class VARCHAR(100),
    ADD COLUMN scope VARCHAR(20),
    ADD COLUMN comparison_operator VARCHAR(30);

ALTER TABLE alerts
    ADD CONSTRAINT alerts_analysis_method_values
        CHECK (
            analysis_method IS NULL
            OR analysis_method = 'detector_object_count'
        ),
    ADD CONSTRAINT alerts_scope_values
        CHECK (scope IS NULL OR scope IN ('frame', 'grid_cell')),
    ADD CONSTRAINT alerts_comparison_values
        CHECK (
            comparison_operator IS NULL
            OR comparison_operator IN ('greater_than', 'greater_than_or_equal')
        ),
    ADD CONSTRAINT alerts_severity_values
        CHECK (severity IN ('information', 'warning', 'critical')),
    ADD CONSTRAINT alerts_object_class_value
        CHECK (object_class IS NULL OR LENGTH(TRIM(object_class)) > 0),
    ADD CONSTRAINT alerts_scope_lineage
        CHECK (
            scope IS NULL
            OR (scope = 'frame' AND grid_cell_id IS NULL)
            OR (scope = 'grid_cell' AND grid_cell_id IS NOT NULL)
        ),
    ADD CONSTRAINT alerts_rule_metadata_pair
        CHECK (
            (
                analysis_method IS NULL
                AND object_class IS NULL
                AND scope IS NULL
                AND comparison_operator IS NULL
            )
            OR
            (
                analysis_method IS NOT NULL
                AND object_class IS NOT NULL
                AND scope IS NOT NULL
                AND comparison_operator IS NOT NULL
                AND measured_value IS NOT NULL
                AND measured_value >= 0
                AND threshold_value IS NOT NULL
                AND threshold_value > 0
            )
        );

CREATE UNIQUE INDEX idx_alerts_rule_lineage_unique
    ON alerts(processed_frame_id, grid_cell_id, alert_type) NULLS NOT DISTINCT;
