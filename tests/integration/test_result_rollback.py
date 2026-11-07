import os
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg.errors import CheckViolation

from app.crowd_analysis import load_dense_crowd_analysis_decision
from app.database.connection import open_database_connection
from app.database.detection_repository import save_image_detection_results
from app.database.migration_runner import apply_pending_migrations
from app.database.monitoring_query_repository import get_monitoring_session
from app.database.video_job_repository import (
    complete_video_analysis_job,
    create_video_analysis_job,
    fail_video_analysis_job,
    get_video_analysis_job,
    mark_video_job_processing,
)
from app.model_profile import load_runtime_model_profile
from app.services.video_detection_service import VideoFrameDetectionResult

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION_TESTS") != "1",
    reason="PostgreSQL integration tests are not enabled.",
)


@pytest.mark.parametrize("kind", ["image", "video"])
def test_result_constraint_failure_rolls_back_partial_writes(kind):
    apply_pending_migrations()
    name = f"rollback-{uuid4()}"
    profile = load_runtime_model_profile()
    decision = load_dense_crowd_analysis_decision()
    valid = {
        "object_class": "car_or_van",
        "confidence": 0.9,
        "bbox_x_min": 1,
        "bbox_y_min": 1,
        "bbox_x_max": 10,
        "bbox_y_max": 10,
    }
    invalid = {**valid, "confidence": 1.5}
    try:
        if kind == "image":
            with pytest.raises(CheckViolation):
                save_image_detection_results(
                    "rollback.png",
                    100,
                    100,
                    [valid, invalid],
                    session_name=name,
                    model_profile=profile,
                    crowd_analysis_decision=decision,
                )
            with (
                open_database_connection() as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute(
                    "SELECT id FROM monitoring_sessions WHERE session_name = %s;",
                    (name,),
                )
                assert cursor.fetchall() == []
        else:
            created = create_video_analysis_job(
                video_path=Path("rollback.avi"),
                original_filename="rollback.avi",
                session_name=name,
                sampling_interval_seconds=1,
                grid_rows=None,
                grid_columns=None,
                total_source_frames=2,
                sampled_frames_total=2,
                model_profile=profile,
                crowd_analysis_decision=decision,
            )
            mark_video_job_processing(created.session_id)
            frames = [
                VideoFrameDetectionResult(
                    frame_number=index,
                    timestamp_seconds=index,
                    image_width=100,
                    image_height=100,
                    detection_records=[record],
                    object_counts={"car_or_van": 1},
                )
                for index, record in enumerate([valid, invalid])
            ]
            with pytest.raises(CheckViolation):
                complete_video_analysis_job(created.session_id, frames)
            result = get_monitoring_session(created.session_id)
            assert result.status == "processing"
            assert result.frames == []
            assert get_video_analysis_job(created.session_id).status == "processing"
            fail_video_analysis_job(
                created.session_id, "test_failure", "Controlled failure"
            )
            assert (
                get_video_analysis_job(created.session_id).failure_code
                == "test_failure"
            )
    finally:
        with open_database_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM monitoring_sessions WHERE session_name = %s;", (name,)
            )
