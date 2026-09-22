ALTER TABLE model_run_profiles
    ADD COLUMN runtime_provenance JSONB
        CHECK (runtime_provenance IS NULL OR jsonb_typeof(runtime_provenance) = 'object');
