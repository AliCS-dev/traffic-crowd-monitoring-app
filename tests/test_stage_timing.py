import json
import logging
from contextlib import contextmanager

import pytest

import app.stage_timing as timing
from app.logging_config import StructuredFormatter, request_id_context
from app.services.detection_service import ObjectDetector


def timing_records(caplog):
    return [
        json.loads(StructuredFormatter().format(record))
        for record in caplog.records
        if record.getMessage() == "stage_timing"
    ]


def test_detector_timer_excludes_lock_wait_and_prior_cuda_work(monkeypatch, caplog):
    now = [0.0]
    monkeypatch.setattr(timing, "monotonic", lambda: now[0])
    caplog.set_level(logging.INFO, logger="app.stage_timing")

    def sync(_device):
        now[0] += 3

    def model(*_args, **_kwargs):
        now[0] += 2
        return ["result"]

    @contextmanager
    def lock():
        now[0] += 10
        yield

    monkeypatch.setattr("app.services.detection_service.torch.cuda.synchronize", sync)
    detector = ObjectDetector("unused", model_factory=lambda _: model)
    detector._inference_lock = lock()
    token = request_id_context.set("request-1")
    try:
        assert detector.detect(
            None, confidence_threshold=0.25, image_size=1280, device="cuda:0"
        ) == ["result"]
        record = timing_records(caplog)[0]
        assert record["request_id"] == "request-1"
        assert record["duration_seconds"] == 5
        assert record["stage_status"] == "completed"
    finally:
        request_id_context.reset(token)


def test_cpu_detector_does_not_synchronize_cuda(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.stage_timing")
    monkeypatch.setattr(
        "app.services.detection_service.torch.cuda.synchronize",
        lambda _: pytest.fail("CPU must not use CUDA"),
    )
    detector = ObjectDetector("unused", model_factory=lambda _: lambda *a, **k: [])
    assert (
        detector.detect(None, confidence_threshold=0.25, image_size=640, device="cpu")
        == []
    )
    assert timing_records(caplog)[0]["stage_status"] == "completed"


@pytest.mark.parametrize("commit_fails", [False, True])
def test_image_persistence_timer_includes_commit(monkeypatch, caplog, commit_fails):
    from test_detection_repository import (
        CROWD_ANALYSIS_DECISION,
        MODEL_PROFILE,
        FakeConnection,
        FakeCursor,
    )

    import app.database.detection_repository as repository

    caplog.set_level(logging.INFO, logger="app.stage_timing")
    now = [0.0]
    monkeypatch.setattr(timing, "monotonic", lambda: now[0])

    class Connection(FakeConnection):
        def __exit__(self, *_args):
            now[0] += 4
            if commit_fails:
                raise RuntimeError("private credentials")

    connection = Connection(FakeCursor(range(1, 10)))
    monkeypatch.setattr(repository, "open_database_connection", lambda: connection)

    def save():
        return repository.save_image_detection_results(
            "test.jpg",
            20,
            10,
            [],
            model_profile=MODEL_PROFILE,
            crowd_analysis_decision=CROWD_ANALYSIS_DECISION,
        )

    if commit_fails:
        with pytest.raises(RuntimeError):
            save()
    else:
        save()
    record = timing_records(caplog)[0]
    assert record["stage"] == "image_persistence"
    assert record["duration_seconds"] == 4
    assert record["stage_status"] == ("failed" if commit_fails else "completed")
    assert "private" not in json.dumps(record)


def test_video_queue_time_keeps_original_request_context(tmp_path, monkeypatch, caplog):
    from test_video_analysis_service import create_service, submit

    import app.services.video_analysis_service as video

    caplog.set_level(logging.INFO, logger="app.stage_timing")
    now = [10.0]
    monkeypatch.setattr(video, "monotonic", lambda: now[0])
    service, executor, _calls = create_service(tmp_path, monkeypatch)
    token = request_id_context.set("upload-request")
    try:
        submit(service)
    finally:
        request_id_context.reset(token)
    now[0] = 12.0
    executor.run()
    record = timing_records(caplog)[0]
    assert record["stage"] == "video_queue"
    assert record["duration_seconds"] == 2
    assert record["request_id"] == "upload-request"
    assert record["session_id"] == 42
    assert request_id_context.get() is None


@pytest.mark.parametrize("commit_fails", [False, True])
def test_video_persistence_timer_includes_commit(monkeypatch, caplog, commit_fails):
    from test_detection_repository import (
        FakeConnection,
        FakeCursor,
        create_frame_result,
    )

    from app.database.video_job_repository import complete_video_analysis_job

    now = [0.0]
    monkeypatch.setattr(timing, "monotonic", lambda: now[0])
    caplog.set_level(logging.INFO, logger="app.stage_timing")

    class Cursor(FakeCursor):
        def execute(self, query, parameters):
            super().execute(query, parameters)
            if "SELECT input_source_id" in query:
                self._last_row = (7, 1)

    class Connection(FakeConnection):
        def __exit__(self, *_args):
            now[0] += 3
            if commit_fails:
                raise RuntimeError("commit failed")

    connection = Connection(Cursor(range(1, 10)))

    def save():
        complete_video_analysis_job(
            42,
            [create_frame_result(0, 0, [], {})],
            connection_factory=lambda: connection,
        )

    if commit_fails:
        with pytest.raises(RuntimeError):
            save()
    else:
        save()
    record = timing_records(caplog)[0]
    assert record["stage"] == "video_persistence"
    assert record["duration_seconds"] == 3
    assert record["stage_status"] == ("failed" if commit_fails else "completed")
