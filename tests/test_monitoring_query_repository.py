from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from app.database.monitoring_query_repository import (
    InvalidPaginationError,
    InvalidSessionIdError,
    get_monitoring_session,
    list_monitoring_sessions,
)

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)


class FakeCursor:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.current_rows = []
        self.execute_calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, parameters=None):
        self.execute_calls.append((" ".join(query.split()), parameters))
        self.current_rows = next(self.responses)

    def fetchone(self):
        return self.current_rows[0] if self.current_rows else None

    def fetchall(self):
        return self.current_rows


class FakeConnection:
    def __init__(self, cursor):
        self.query_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def cursor(self, **_options):
        return self.query_cursor


def connection_factory_for(*responses):
    cursor = FakeCursor(responses)
    return cursor, lambda: FakeConnection(cursor)


def session_row(**overrides):
    row = {
        "id": 11,
        "session_name": "junction image",
        "status": "completed",
        "started_at": NOW,
        "completed_at": NOW,
        "notes": None,
        "profile_id": "test-profile",
        "model_id": "test-model",
        "quality_gate_status": "failed",
        "evaluation_reference": "evaluation/result.json",
        "checkpoint_path": "models/test.pt",
        "checkpoint_sha256": "a" * 64,
        "class_mapping": {"car": "car_or_van"},
        "confidence": Decimal("0.25000"),
        "image_size": 1280,
        "scale_factor": 2,
        "max_detections": 300,
        "numeric_precision": "float32",
        "device": "cuda:0",
        "profile_created_at": NOW,
    }
    row.update(overrides)
    return row


def crowd_analysis_row(**overrides):
    row = {
        "status": "unsupported",
        "count": None,
        "method_id": None,
        "model_id": None,
        "evaluated_candidate_id": "p2pnet-shtecha",
        "quality_gate_status": "failed",
        "evaluation_reference": ("docs/evaluation/dedicated_crowd_counting_result.md"),
        "reason_code": "no_accepted_dense_crowd_model",
        "message": "The evaluated candidate did not meet the acceptance threshold.",
    }
    row.update(overrides)
    return row


def test_list_sessions_returns_deterministic_page_metadata():
    rows = [
        {
            "id": 3,
            "session_name": "newer id",
            "status": "completed",
            "started_at": NOW,
            "completed_at": NOW,
        },
        {
            "id": 2,
            "session_name": "older id",
            "status": "completed",
            "started_at": NOW,
            "completed_at": NOW,
        },
    ]
    cursor, connection_factory = connection_factory_for([{"total_items": 5}], rows)

    result = list_monitoring_sessions(
        page=2,
        page_size=2,
        connection_factory=connection_factory,
    )

    assert [session.id for session in result.items] == [3, 2]
    assert result.pagination.model_dump() == {
        "page": 2,
        "page_size": 2,
        "total_items": 5,
        "total_pages": 3,
    }
    assert "ORDER BY started_at DESC, id DESC" in cursor.execute_calls[1][0]
    assert cursor.execute_calls[1][1] == (2, 2)


@pytest.mark.parametrize(
    ("page", "page_size", "message"),
    [
        (0, 20, "page must be a positive integer"),
        (True, 20, "page must be a positive integer"),
        (1, 0, "page_size must be an integer between 1 and 100"),
        (1, 101, "page_size must be an integer between 1 and 100"),
    ],
)
def test_list_sessions_rejects_invalid_pagination(page, page_size, message):
    with pytest.raises(InvalidPaginationError, match=message):
        list_monitoring_sessions(
            page=page,
            page_size=page_size,
            connection_factory=lambda: pytest.fail("Database connection opened."),
        )


def test_missing_session_returns_none_after_one_query():
    cursor, connection_factory = connection_factory_for([])

    result = get_monitoring_session(999, connection_factory=connection_factory)

    assert result is None
    assert len(cursor.execute_calls) == 1


def test_session_without_model_profile_or_frames_remains_readable():
    legacy_session = session_row(
        profile_id=None,
        model_id=None,
        quality_gate_status=None,
        evaluation_reference=None,
        checkpoint_path=None,
        checkpoint_sha256=None,
        class_mapping=None,
        confidence=None,
        image_size=None,
        scale_factor=None,
        max_detections=None,
        numeric_precision=None,
        device=None,
        profile_created_at=None,
    )
    cursor, connection_factory = connection_factory_for([legacy_session], [], [], [])

    result = get_monitoring_session(11, connection_factory=connection_factory)

    assert result is not None
    assert result.model_profile is None
    assert result.dense_crowd_analysis is None
    assert result.sources == []
    assert result.frames == []
    assert len(cursor.execute_calls) == 4


def test_complete_result_is_grouped_by_frame_and_grid_level():
    source = {
        "id": 21,
        "source_type": "image",
        "original_filename": "junction.jpg",
        "created_at": NOW,
    }
    frame = {
        "id": 31,
        "input_source_id": 21,
        "frame_number": 0,
        "frame_timestamp_seconds": Decimal("0.000"),
        "image_width": 200,
        "image_height": 100,
        "output_asset_id": UUID("12345678-1234-5678-1234-567812345678"),
        "processed_at": NOW,
    }
    detection = {
        "id": 41,
        "processed_frame_id": 31,
        "object_class": "car_or_van",
        "confidence": Decimal("0.90000"),
        "bbox_x_min": Decimal("10.00"),
        "bbox_y_min": Decimal("20.00"),
        "bbox_x_max": Decimal("50.00"),
        "bbox_y_max": Decimal("60.00"),
        "created_at": NOW,
    }
    grid_cell = {
        "id": 51,
        "processed_frame_id": 31,
        "row_index": 0,
        "column_index": 0,
        "x_min": Decimal("0.00"),
        "y_min": Decimal("0.00"),
        "x_max": Decimal("100.00"),
        "y_max": Decimal("100.00"),
    }
    summaries = [
        {
            "id": 61,
            "processed_frame_id": 31,
            "grid_cell_id": None,
            "object_class": "car_or_van",
            "object_count": 1,
            "created_at": NOW,
        },
        {
            "id": 62,
            "processed_frame_id": 31,
            "grid_cell_id": 51,
            "object_class": "car_or_van",
            "object_count": 1,
            "created_at": NOW,
        },
    ]
    alert = {
        "id": 71,
        "processed_frame_id": 31,
        "grid_cell_id": 51,
        "alert_type": "test_threshold",
        "analysis_method": "detector_object_count",
        "object_class": "car_or_van",
        "scope": "grid_cell",
        "comparison_operator": "greater_than_or_equal",
        "severity": "warning",
        "message": "Test alert",
        "measured_value": Decimal("1.000"),
        "threshold_value": Decimal("2.000"),
        "created_at": NOW,
        "resolved_at": None,
    }
    cursor, connection_factory = connection_factory_for(
        [session_row()],
        [crowd_analysis_row()],
        [source],
        [frame],
        [detection],
        [grid_cell],
        summaries,
        [alert],
    )

    result = get_monitoring_session(11, connection_factory=connection_factory)

    assert result is not None
    assert result.model_profile.model_id == "test-model"
    assert result.dense_crowd_analysis.status == "unsupported"
    assert result.dense_crowd_analysis.count is None
    assert result.dense_crowd_analysis.method_id is None
    assert result.dense_crowd_analysis.model_id is None
    assert result.dense_crowd_analysis.evaluated_candidate_id == "p2pnet-shtecha"
    assert result.sources[0].original_filename == "junction.jpg"
    assert len(result.frames) == 1
    result_frame = result.frames[0]
    assert result_frame.detections[0].bounds.x_max == 50
    assert str(result_frame.output_asset_id) == "12345678-1234-5678-1234-567812345678"
    assert result_frame.coordinate_space.model_dump() == {
        "name": "processed_image_pixels",
        "origin": "top_left",
        "x_axis_direction": "right",
        "y_axis_direction": "down",
        "width": 200,
        "height": 100,
    }
    assert result_frame.visual_asset.url == (
        "/api/assets/12345678-1234-5678-1234-567812345678"
    )
    assert result_frame.visual_asset.content_type == "image/jpeg"
    assert result_frame.visual_asset.rendered_overlays == ("detections",)
    assert [summary.id for summary in result_frame.frame_summaries] == [61]
    assert [summary.id for summary in result_frame.grid_cells[0].summaries] == [62]
    assert result_frame.alerts[0].grid_cell_id == 51
    assert result_frame.alerts[0].analysis_method == "detector_object_count"
    assert result_frame.alerts[0].object_class == "car_or_van"
    assert result_frame.alerts[0].scope == "grid_cell"
    assert result_frame.alerts[0].comparison_operator == "greater_than_or_equal"
    assert len(cursor.execute_calls) == 8
    for _query, parameters in cursor.execute_calls[4:]:
        assert parameters == ([31],)


def test_detail_query_count_does_not_grow_with_video_frames():
    frame_rows = [
        {
            "id": frame_id,
            "input_source_id": 21,
            "frame_number": frame_number,
            "frame_timestamp_seconds": frame_number / 30,
            "image_width": 1280,
            "image_height": 720,
            "output_asset_id": None,
            "processed_at": NOW,
        }
        for frame_id, frame_number in [(31, 0), (32, 30), (33, 60)]
    ]
    cursor, connection_factory = connection_factory_for(
        [session_row()], [crowd_analysis_row()], [], frame_rows, [], [], [], []
    )

    result = get_monitoring_session(11, connection_factory=connection_factory)

    assert result is not None
    assert [frame.frame_number for frame in result.frames] == [0, 30, 60]
    assert all(frame.visual_asset is None for frame in result.frames)
    assert all(frame.coordinate_space.width == 1280 for frame in result.frames)
    assert len(cursor.execute_calls) == 8
    for _query, parameters in cursor.execute_calls[4:]:
        assert parameters == ([31, 32, 33],)


@pytest.mark.parametrize("session_id", [0, -1, True, "1"])
def test_get_session_rejects_invalid_identifier(session_id):
    with pytest.raises(InvalidSessionIdError, match="positive integer"):
        get_monitoring_session(
            session_id,
            connection_factory=lambda: pytest.fail("Database connection opened."),
        )
