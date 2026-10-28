ALTER TABLE processed_frames
    ADD COLUMN source_file_path TEXT,
    ADD CONSTRAINT processed_frames_source_requires_output
        CHECK (source_file_path IS NULL OR output_asset_id IS NOT NULL);
