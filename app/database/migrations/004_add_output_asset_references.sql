ALTER TABLE processed_frames
    ADD COLUMN output_asset_id UUID,
    ADD COLUMN output_file_path TEXT,
    ADD CONSTRAINT processed_frames_output_reference_pair
        CHECK (
            (output_asset_id IS NULL AND output_file_path IS NULL)
            OR
            (output_asset_id IS NOT NULL AND output_file_path IS NOT NULL)
        );

CREATE UNIQUE INDEX idx_processed_frames_output_asset_id
    ON processed_frames(output_asset_id)
    WHERE output_asset_id IS NOT NULL;
