import os
from datetime import datetime, timezone

import pytest

from app.crowd_analysis import load_dense_crowd_analysis_decision
from app.database.connection import open_database_connection
from app.database.detection_repository import (
    create_alert_results,
    save_image_detection_results,
    save_video_detection_results,
)
from app.database.migration_runner import apply_pending_migrations
from app.database.monitoring_query_repository import (
    get_monitoring_session,
    list_monitoring_sessions,
)
from app.model_profile import load_runtime_model_profile
from app.services.alert_service import (
    AlertAnalysisMethod,
    AlertComparison,
    AlertScope,
    AlertSeverity,
    ThresholdAlertRule,
    evaluate_threshold_alerts,
)
from app.services.grid_counting_service import count_detections_by_grid
from app.services.video_detection_service import VideoFrameDetectionResult

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION_TESTS") != "1",
    reason="PostgreSQL integration tests are not enabled.",
)

CAR_DETECTION = {
    "object_class": "car_or_van",
    "confidence": 0.91,
    "bbox_x_min": 10.0,
    "bbox_y_min": 20.0,
    "bbox_x_max": 50.0,
    "bbox_y_max": 80.0,
}


def test_reads_complete_image_and_ordered_video_sessions_from_postgresql():
    apply_pending_migrations()
    model_profile = load_runtime_model_profile()
    crowd_analysis_decision = load_dense_crowd_analysis_decision()
    grid_result = count_detections_by_grid(
        [CAR_DETECTION],
        image_width=200,
        image_height=100,
        rows=1,
        columns=2,
    )
    alert_records = evaluate_threshold_alerts(
        (
            ThresholdAlertRule(
                rule_id="grid-car-information",
                analysis_method=AlertAnalysisMethod.DETECTOR_OBJECT_COUNT,
                object_class="car_or_van",
                scope=AlertScope.GRID_CELL,
                comparison=AlertComparison.GREATER_THAN_OR_EQUAL,
                threshold=1,
                severity=AlertSeverity.INFORMATION,
            ),
        ),
        frame_object_counts={"car_or_van": 1},
        grid_count_result=grid_result,
    )
    image_result = save_image_detection_results(
        "data/input/query-integration.jpg",
        image_width=200,
        image_height=100,
        detection_records=[CAR_DETECTION],
        object_count_summary_records=[
            {"object_class": "car_or_van", "object_count": 1}
        ],
        session_name="query repository image",
        grid_count_result=grid_result,
        alert_records=alert_records,
        model_profile=model_profile,
        crowd_analysis_decision=crowd_analysis_decision,
    )
    video_result = save_video_detection_results(
        "data/input/query-integration.mp4",
        [
            VideoFrameDetectionResult(
                frame_number=120,
                timestamp_seconds=4.0,
                image_width=1280,
                image_height=720,
                detection_records=[],
                object_counts={},
            ),
            VideoFrameDetectionResult(
                frame_number=0,
                timestamp_seconds=0.0,
                image_width=1280,
                image_height=720,
                detection_records=[CAR_DETECTION],
                object_counts={"car_or_van": 1},
            ),
        ],
        session_name="query repository video",
        model_profile=model_profile,
        crowd_analysis_decision=crowd_analysis_decision,
    )
    session_ids = [image_result["session_id"], video_result["session_id"]]

    try:
        with open_database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE monitoring_sessions
                    SET started_at = %s
                    WHERE id = ANY(%s);
                    """,
                    (
                        datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc),
                        session_ids,
                    ),
                )
                cursor.execute(
                    """
                    SELECT id, row_index, column_index
                    FROM grid_cells
                    WHERE processed_frame_id = %s;
                    """,
                    (image_result["processed_frame_id"],),
                )
                grid_cell_ids = {
                    (row_index, column_index): grid_cell_id
                    for grid_cell_id, row_index, column_index in cursor.fetchall()
                }
                create_alert_results(
                    cursor,
                    image_result["processed_frame_id"],
                    alert_records,
                    grid_cell_ids,
                )
                create_alert_results(
                    cursor,
                    image_result["processed_frame_id"],
                    alert_records,
                    grid_cell_ids,
                )
                cursor.execute(
                    "SELECT COUNT(*) FROM alerts WHERE processed_frame_id = %s;",
                    (image_result["processed_frame_id"],),
                )
                assert cursor.fetchone() == (1,)

        image_session = get_monitoring_session(image_result["session_id"])
        video_session = get_monitoring_session(video_result["session_id"])
        history = list_monitoring_sessions(page=1, page_size=100)
    finally:
        with open_database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM monitoring_sessions WHERE id = ANY(%s);",
                    (session_ids,),
                )

    assert image_session is not None
    assert image_session.sources[0].source_type == "image"
    assert image_session.model_profile.model_id == model_profile.model_id
    assert image_session.dense_crowd_analysis.status == "unsupported"
    assert image_session.dense_crowd_analysis.count is None
    assert image_session.dense_crowd_analysis.model_id is None
    assert len(image_session.frames) == 1
    image_frame = image_session.frames[0]
    assert len(image_frame.detections) == 1
    assert [
        (item.object_class, item.object_count) for item in image_frame.frame_summaries
    ] == [("car_or_van", 1)]
    assert len(image_frame.grid_cells) == 2
    assert len(image_frame.grid_cells[0].summaries) == 1
    assert image_frame.grid_cells[1].summaries == []
    assert image_frame.alerts[0].alert_type == "grid-car-information"
    assert image_frame.alerts[0].analysis_method == "detector_object_count"
    assert image_frame.alerts[0].object_class == "car_or_van"
    assert image_frame.alerts[0].scope == "grid_cell"
    assert image_frame.alerts[0].severity == "information"
    assert image_frame.alerts[0].measured_value == 1
    assert image_frame.alerts[0].threshold_value == 1

    assert video_session is not None
    assert video_session.sources[0].source_type == "video"
    assert video_session.dense_crowd_analysis.status == "unsupported"
    assert [frame.frame_number for frame in video_session.frames] == [0, 120]
    assert [len(frame.detections) for frame in video_session.frames] == [1, 0]

    matching_history_ids = [
        session.id for session in history.items if session.id in session_ids
    ]
    assert matching_history_ids == sorted(session_ids, reverse=True)
