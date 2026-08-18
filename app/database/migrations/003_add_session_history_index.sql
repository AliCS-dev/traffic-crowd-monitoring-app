CREATE INDEX idx_monitoring_sessions_history
    ON monitoring_sessions(started_at DESC, id DESC);
