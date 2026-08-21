import os
from pathlib import Path
from uuid import uuid4

import pytest

from app.crowd_analysis import load_dense_crowd_analysis_decision
from app.database.connection import open_database_connection
from app.database.migration_runner import apply_pending_migrations
from app.database.monitoring_query_repository import get_monitoring_session
from app.database.video_job_repository import (
    complete_video_analysis_job,
    create_video_analysis_job,
    get_video_analysis_job,
    mark_video_job_processing,
    recover_interrupted_video_jobs,
    update_video_job_progress,
)
from app.model_profile import load_runtime_model_profile
from app.services.alert_service import (
    AlertAnalysisMethod,
    AlertComparison,
    AlertScope,
    AlertSeverity,
    ThresholdAlert,
)
from app.services.grid_counting_service import count_detections_by_grid
from app.services.output_asset_service import OutputAssetService
from app.services.video_detection_service import VideoFrameDetectionResult

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION_TESTS") != "1",
    reason="PostgreSQL integration tests are not enabled.",
)

DETECTION = {
    "object_class": "car_or_van",
    "confidence": 0.9,
    "bbox_x_min": 10.0,
    "bbox_y_min": 10.0,
    "bbox_x_max": 30.0,
    "bbox_y_max": 30.0,
}


def test_video_job_tracks_progress_and_commits_ordered_results_atomically(tmp_path):
    apply_pending_migrations()
    profile = load_runtime_model_profile()
    decision = load_dense_crowd_analysis_decision()
    grid = count_detections_by_grid([DETECTION], 100, 50, rows=1, columns=2)
    output_directory = tmp_path / "video-frames"
    output_directory.mkdir()
    frame_zero_asset_id = uuid4()
    frame_thirty_asset_id = uuid4()
    frame_zero_path = output_directory / f"{frame_zero_asset_id}.jpg"
    frame_thirty_path = output_directory / f"{frame_thirty_asset_id}.jpg"
    frame_zero_path.write_bytes(b"frame zero")
    frame_thirty_path.write_bytes(b"frame thirty")
    created = create_video_analysis_job(
        video_path=Path("data/input/async-integration.mp4"),
        original_filename="drone-traffic.mp4",
        session_name="async video integration",
        sampling_interval_seconds=1,
        grid_rows=1,
        grid_columns=2,
        total_source_frames=31,
        sampled_frames_total=2,
        model_profile=profile,
        crowd_analysis_decision=decision,
    )

    try:
        assert get_video_analysis_job(created.session_id).status == "queued"
        mark_video_job_processing(created.session_id)
        update_video_job_progress(created.session_id, 1)
        processing = get_video_analysis_job(created.session_id)
        assert processing.status == "processing"
        assert processing.progress_percent == 50

        complete_video_analysis_job(
            created.session_id,
            [
                VideoFrameDetectionResult(
                    frame_number=30,
                    timestamp_seconds=1,
                    image_width=100,
                    image_height=50,
                    detection_records=[],
                    object_counts={},
                    grid_count_result=count_detections_by_grid(
                        [], 100, 50, rows=1, columns=2
                    ),
                    output_asset_id=frame_thirty_asset_id,
                    output_file_path=frame_thirty_path,
                ),
                VideoFrameDetectionResult(
                    frame_number=0,
                    timestamp_seconds=0,
                    image_width=100,
                    image_height=50,
                    detection_records=[DETECTION],
                    object_counts={"car_or_van": 1},
                    grid_count_result=grid,
                    output_asset_id=frame_zero_asset_id,
                    output_file_path=frame_zero_path,
                    alert_records=(
                        ThresholdAlert(
                            rule_id="frame-car-warning",
                            analysis_method=(AlertAnalysisMethod.DETECTOR_OBJECT_COUNT),
                            object_class="car_or_van",
                            scope=AlertScope.FRAME,
                            comparison=AlertComparison.GREATER_THAN_OR_EQUAL,
                            severity=AlertSeverity.WARNING,
                            message="Experimental frame count met threshold.",
                            measured_value=1,
                            threshold_value=1,
                        ),
                    ),
                ),
            ],
        )

        completed = get_video_analysis_job(created.session_id)
        result = get_monitoring_session(created.session_id)
        assert completed.status == "completed"
        assert completed.progress_percent == 100
        assert [frame.frame_number for frame in result.frames] == [0, 30]
        assert len(result.frames[0].grid_cells) == 2
        assert len(result.frames[0].alerts) == 1
        assert result.frames[0].alerts[0].alert_type == "frame-car-warning"
        assert result.frames[0].visual_asset.url == (
            f"/api/assets/{frame_zero_asset_id}"
        )
        assert result.frames[1].visual_asset.url == (
            f"/api/assets/{frame_thirty_asset_id}"
        )
        asset_service = OutputAssetService(allowed_directories=(output_directory,))
        assert asset_service.resolve(frame_zero_asset_id).file_path == frame_zero_path
        assert (
            asset_service.resolve(frame_thirty_asset_id).file_path == frame_thirty_path
        )
        assert result.sources[0].original_filename == "drone-traffic.mp4"
    finally:
        _delete_sessions([created.session_id])


def test_startup_recovery_marks_abandoned_job_failed():
    apply_pending_migrations()
    created = create_video_analysis_job(
        video_path=Path("data/input/interrupted.mp4"),
        original_filename="interrupted.mp4",
        session_name="interrupted integration",
        sampling_interval_seconds=1,
        grid_rows=None,
        grid_columns=None,
        total_source_frames=10,
        sampled_frames_total=1,
        model_profile=load_runtime_model_profile(),
        crowd_analysis_decision=load_dense_crowd_analysis_decision(),
    )

    try:
        assert recover_interrupted_video_jobs() >= 1
        failed = get_video_analysis_job(created.session_id)
        assert failed.status == "failed"
        assert failed.failure_code == "worker_interrupted"
        assert get_monitoring_session(created.session_id).status == "failed"
    finally:
        _delete_sessions([created.session_id])


def _delete_sessions(session_ids):
    with open_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM monitoring_sessions WHERE id = ANY(%s);", (session_ids,)
            )
