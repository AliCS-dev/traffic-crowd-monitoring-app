import pytest

import app.database.detection_repository as detection_repository
from app.services.video_detection_service import VideoFrameDetectionResult

CAR_DETECTION = {
    "object_class": "car",
    "confidence": 0.91,
    "bbox_x_min": 10.0,
    "bbox_y_min": 20.0,
    "bbox_x_max": 50.0,
    "bbox_y_max": 80.0,
}

PERSON_DETECTION = {
    "object_class": "person",
    "confidence": 0.78,
    "bbox_x_min": 100.0,
    "bbox_y_min": 120.0,
    "bbox_x_max": 140.0,
    "bbox_y_max": 180.0,
}


class FakeCursor:
    def __init__(self, generated_ids, fail_on=None):
        self._generated_ids = iter(generated_ids)
        self._last_row = None
        self.fail_on = fail_on
        self.execute_calls = []
        self.executemany_calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, parameters):
        operation = self._operation_name(query)
        self.execute_calls.append((operation, parameters))

        if operation == self.fail_on:
            raise RuntimeError(f"Failed to insert {operation}.")

        if "RETURNING id" in query:
            self._last_row = (next(self._generated_ids),)

    def executemany(self, query, parameters):
        operation = self._operation_name(query)
        records = list(parameters)
        self.executemany_calls.append((operation, records))

        if operation == self.fail_on:
            raise RuntimeError(f"Failed to insert {operation}.")

    def fetchone(self):
        return self._last_row

    @staticmethod
    def _operation_name(query):
        normalized_query = " ".join(query.split())

        if "INSERT INTO monitoring_sessions" in normalized_query:
            return "monitoring_session"
        if "INSERT INTO input_sources" in normalized_query:
            return "input_source"
        if "INSERT INTO processed_frames" in normalized_query:
            return "processed_frame"
        if "INSERT INTO detection_results" in normalized_query:
            return "detection_results"
        if "INSERT INTO object_count_summaries" in normalized_query:
            return "object_count_summaries"
        if "UPDATE monitoring_sessions" in normalized_query:
            return "complete_session"

        return "unknown"


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.exit_exception_type = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_exception_type = exc_type
        return False

    def cursor(self):
        return self._cursor


def use_fake_database(monkeypatch, generated_ids, fail_on=None):
    cursor = FakeCursor(generated_ids=generated_ids, fail_on=fail_on)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(
        detection_repository,
        "open_database_connection",
        lambda: connection,
    )
    return cursor, connection


def create_frame_result(
    frame_number,
    timestamp_seconds,
    detection_records,
    object_counts,
):
    return VideoFrameDetectionResult(
        frame_number=frame_number,
        timestamp_seconds=timestamp_seconds,
        image_width=1280,
        image_height=720,
        detection_records=detection_records,
        object_counts=object_counts,
    )


def test_save_video_results_associates_multiple_frames_and_records(monkeypatch):
    cursor, connection = use_fake_database(
        monkeypatch,
        generated_ids=[10, 20, 30, 31],
    )
    frame_results = [
        create_frame_result(0, 0.0, [CAR_DETECTION], {"car": 1}),
        create_frame_result(120, 4.0, [PERSON_DETECTION], {"person": 1}),
    ]

    stored_result = detection_repository.save_video_detection_results(
        "data/input/traffic.mp4",
        frame_results,
        session_name="sample video",
    )

    assert stored_result == {
        "session_id": 10,
        "input_source_id": 20,
        "processed_frame_ids": [30, 31],
        "frame_count": 2,
        "detection_count": 2,
        "object_count_summary_count": 2,
    }
    assert ("input_source", (10, "video", "data/input/traffic.mp4", "traffic.mp4")) in (
        cursor.execute_calls
    )
    assert ("processed_frame", (10, 20, 0, 0.0, 1280, 720)) in cursor.execute_calls
    assert ("processed_frame", (10, 20, 120, 4.0, 1280, 720)) in cursor.execute_calls
    assert cursor.executemany_calls == [
        (
            "detection_results",
            [{"processed_frame_id": 30, **CAR_DETECTION}],
        ),
        (
            "object_count_summaries",
            [
                {
                    "processed_frame_id": 30,
                    "object_class": "car",
                    "object_count": 1,
                }
            ],
        ),
        (
            "detection_results",
            [{"processed_frame_id": 31, **PERSON_DETECTION}],
        ),
        (
            "object_count_summaries",
            [
                {
                    "processed_frame_id": 31,
                    "object_class": "person",
                    "object_count": 1,
                }
            ],
        ),
    ]
    assert cursor.execute_calls[-1] == ("complete_session", ("completed", 10))
    assert connection.exit_exception_type is None


def test_save_video_result_records_frame_without_detections(monkeypatch):
    cursor, _connection = use_fake_database(
        monkeypatch,
        generated_ids=[10, 20, 30],
    )
    frame_result = create_frame_result(30, 1.0, [], {})

    stored_result = detection_repository.save_video_detection_results(
        "data/input/empty-frame.mp4",
        [frame_result],
    )

    assert stored_result["frame_count"] == 1
    assert stored_result["detection_count"] == 0
    assert stored_result["object_count_summary_count"] == 0
    assert ("processed_frame", (10, 20, 30, 1.0, 1280, 720)) in cursor.execute_calls
    assert cursor.executemany_calls == []


def test_save_video_results_rejects_empty_frame_sequence(monkeypatch):
    def fail_if_connection_opens():
        pytest.fail("Database connection opened for an empty frame sequence.")

    monkeypatch.setattr(
        detection_repository,
        "open_database_connection",
        fail_if_connection_opens,
    )

    with pytest.raises(ValueError, match="At least one processed video frame"):
        detection_repository.save_video_detection_results(
            "data/input/no-frames.mp4",
            [],
        )


def test_save_video_results_rolls_back_complete_transaction_on_failure(monkeypatch):
    cursor, connection = use_fake_database(
        monkeypatch,
        generated_ids=[10, 20, 30],
        fail_on="detection_results",
    )
    frame_result = create_frame_result(
        0,
        0.0,
        [CAR_DETECTION],
        {"car": 1},
    )

    with pytest.raises(RuntimeError, match="Failed to insert detection_results"):
        detection_repository.save_video_detection_results(
            "data/input/traffic.mp4",
            [frame_result],
        )

    assert connection.exit_exception_type is RuntimeError
    assert not any(
        operation == "complete_session"
        for operation, _parameters in cursor.execute_calls
    )


def test_existing_image_storage_uses_image_source_and_zero_frame(monkeypatch):
    cursor, _connection = use_fake_database(
        monkeypatch,
        generated_ids=[10, 20, 30],
    )

    stored_result = detection_repository.save_image_detection_results(
        "data/input/image.jpg",
        image_width=640,
        image_height=480,
        detection_records=[],
    )

    assert stored_result["processed_frame_id"] == 30
    assert ("input_source", (10, "image", "data/input/image.jpg", "image.jpg")) in (
        cursor.execute_calls
    )
    assert ("processed_frame", (10, 20, 0, 0, 640, 480)) in cursor.execute_calls
