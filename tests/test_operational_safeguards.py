import json
import logging
import os
from contextlib import contextmanager
from dataclasses import replace
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from test_api_application import create_services
from test_image_analysis_service import (
    FakeDetector,
    FakeResult,
    analyse,
    create_service,
)

from app.api.application import create_app
from app.api.settings import ApiSettings, ApiSettingsError
from app.logging_config import StructuredFormatter, request_id_context
from app.services.media_cleanup_service import collect_expired_media
from app.services.workload import (
    AnalysisBusyError,
    AnalysisTimeoutError,
    WorkloadAdmission,
    WorkloadLimits,
)


@pytest.mark.parametrize("apply", [False, True])
def test_cleanup_command_dry_run_and_apply(tmp_path, monkeypatch, capsys, apply):
    import scripts.cleanup_media as module

    orphan = tmp_path / f"{uuid4()}.jpg"
    saved = tmp_path / f"{uuid4()}.jpg"
    for path in (orphan, saved):
        path.write_bytes(b"test media")
        os.utime(path, (0, 0))
    settings = replace(
        ApiSettings(),
        image_upload_directory=tmp_path,
        image_output_directory=tmp_path / "outputs",
        video_upload_directory=tmp_path / "videos",
        video_output_directory=tmp_path / "video-outputs",
    )

    @contextmanager
    def snapshot():
        yield [str(saved)]

    monkeypatch.setattr(module.ApiSettings, "from_environment", lambda: settings)
    monkeypatch.setattr(module, "media_maintenance_snapshot", snapshot)
    monkeypatch.setattr("sys.argv", ["cleanup_media"] + (["--apply"] if apply else []))
    assert module.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == ("applied" if apply else "dry_run")
    assert output["files"] == [str(orphan)]
    assert orphan.exists() is not apply
    assert saved.exists()


def test_cleanup_command_refuses_when_database_is_unavailable(monkeypatch, capsys):
    import scripts.cleanup_media as module

    def unavailable():
        raise RuntimeError("private database credentials")

    monkeypatch.setattr(module, "media_maintenance_snapshot", unavailable)
    monkeypatch.setattr("sys.argv", ["cleanup_media", "--apply"])
    assert module.main() == 1
    output = capsys.readouterr()
    assert "Cleanup refused" in output.err
    assert "private database credentials" not in output.err
    assert output.out == ""


@pytest.mark.parametrize("value", [0, -1, True, float("inf"), float("nan"), 1.5])
def test_invalid_capacity_is_rejected(value):
    with pytest.raises(ValueError):
        WorkloadLimits(max_inflight_analyses=value)


@pytest.mark.parametrize(
    "name,value",
    [
        ("API_MAX_SAMPLED_FRAMES", "0"),
        ("API_MAX_QUEUE_SECONDS", "invalid"),
        ("API_MIN_SAMPLING_INTERVAL_SECONDS", "nan"),
        ("API_VIDEO_WORKERS", "5"),
    ],
)
def test_invalid_environment_limits_fail_startup(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ApiSettingsError):
        ApiSettings.from_environment()


def test_image_busy_is_rejected_before_read_and_slot_survives_failure(tmp_path):
    admission = WorkloadAdmission(1)
    service = create_service(
        tmp_path, FakeDetector([FakeResult()]), lambda **_: {"session_id": 1}
    )
    service._admission = admission
    stream = BytesIO(b"not read")
    admission.acquire()
    with pytest.raises(AnalysisBusyError):
        service.analyze_upload(stream, filename="image.jpg", content_type="image/jpeg")
    assert stream.tell() == 0
    admission.release()
    with pytest.raises(ValueError):
        service.analyze_upload(stream, filename="image.jpg", content_type="image/jpeg")
    assert analyse(service).session_id == 1


def test_image_timeout_cleans_partial_files_and_does_not_persist(tmp_path, monkeypatch):
    import app.services.image_analysis_service as module

    now = [1.0]
    monkeypatch.setattr(module, "monotonic", lambda: now[0])
    detector = FakeDetector([FakeResult()])
    original = detector.detect

    def slow(*args, **kwargs):
        now[0] += 2
        return original(*args, **kwargs)

    detector.detect = slow
    service = create_service(
        tmp_path, detector, lambda **_: pytest.fail("No persistence after deadline")
    )
    service._limits = replace(service._limits, max_processing_seconds=1)
    with pytest.raises(AnalysisTimeoutError):
        analyse(service)
    assert list((tmp_path / "uploads").iterdir()) == []
    assert list((tmp_path / "outputs").iterdir()) == []
    service._admission.acquire()
    service._admission.release()


def test_request_ids_and_busy_errors_are_safe_and_correlated(caplog):
    app = create_app(settings=ApiSettings(), service_factory=create_services)

    @app.get("/busy")
    def busy():
        raise AnalysisBusyError("secret database path")

    @app.get("/broken")
    def broken():
        raise RuntimeError("secret database path")

    with TestClient(app, raise_server_exceptions=False) as client:
        busy_response = client.get("/busy", headers={"X-Request-ID": "untrusted"})
        broken_response = client.get("/broken")
    assert busy_response.status_code == 503
    assert busy_response.headers["Retry-After"] == "5"
    assert broken_response.status_code == 500
    assert "secret" not in busy_response.text + broken_response.text
    for response in (busy_response, broken_response):
        request_id = response.headers["X-Request-ID"]
        UUID(request_id)
        assert any(
            getattr(record, "request_id", None) == request_id
            for record in caplog.records
        )
    assert request_id_context.get() is None


def test_json_logging_does_not_dump_exception_credentials():
    record = logging.LogRecord(
        "app.test", logging.ERROR, "", 1, "video_failed", (), None
    )
    record.session_id = 9
    record.request_id = "correlated"
    try:
        raise RuntimeError("postgresql://secret:password@localhost")
    except RuntimeError:
        import sys

        record.exc_info = sys.exc_info()
    payload = StructuredFormatter().format(record)
    assert "password" not in payload
    assert json.loads(payload)["session_id"] == 9
    assert json.loads(payload)["exception_type"] == "RuntimeError"


def test_cleanup_keeps_referenced_recent_non_uuid_and_symlink_files(tmp_path):
    now = 2_000_000
    names = {name: tmp_path / f"{uuid4()}.jpg" for name in ("old", "kept", "recent")}
    names["part"] = tmp_path / f".{uuid4()}.part"
    names["manual"] = tmp_path / "thesis-figure.jpg"
    for path in names.values():
        path.write_bytes(b"media")
        os.utime(path, (1, 1))
    os.utime(names["recent"], (now, now))
    link = tmp_path / f"{uuid4()}.jpg"
    link.symlink_to(names["old"])
    retained = [f"/app/data/output/analyses/{names['kept'].name}"]
    selected = collect_expired_media([tmp_path], retained, now=now)
    assert set(selected) == {names["old"], names["part"]}
    assert all(path.exists() for path in names.values())


def test_cleanup_refuses_symlink_root_and_invalid_retention(tmp_path):
    root = tmp_path / "real"
    root.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError):
        collect_expired_media([link], [])
    with pytest.raises(ValueError):
        collect_expired_media([root], [], older_than_days=0)


def test_sampler_checks_unsampled_frames_and_stops_before_next_decode():
    from types import SimpleNamespace

    import numpy as np

    from app.services.frame_sampling_service import sample_video_frames

    reads = []
    reader = SimpleNamespace(
        metadata=SimpleNamespace(fps=30),
        read_next_frame=lambda: reads.append(1) or np.zeros((2, 2, 3)),
    )

    def guard(index, _frame):
        if index == 2:
            raise AnalysisTimeoutError("deadline")

    iterator = sample_video_frames(reader, 10, check_frame=guard)
    assert next(iterator).frame_number == 0
    with pytest.raises(AnalysisTimeoutError):
        next(iterator)
    assert len(reads) == 2


def test_shared_admission_covers_both_image_and_queued_video(tmp_path, monkeypatch):
    from test_video_analysis_service import create_service as video_service
    from test_video_analysis_service import submit

    admission = WorkloadAdmission(1)
    video, executor, _calls = video_service(tmp_path, monkeypatch, admission=admission)
    image = create_service(
        tmp_path, FakeDetector([FakeResult()]), lambda **_: {"session_id": 1}
    )
    image._admission = admission
    submit(video)
    with pytest.raises(AnalysisBusyError):
        analyse(image)
    executor.run()
    assert analyse(image).session_id == 1


def test_budget_report_does_not_pass_missing_measurements():
    from scripts.measure_system_budget import assess_budgets

    checks = assess_budgets({"first_image_seconds": 61, "video_seconds": 2})
    assert checks["first_image_seconds"]["status"] == "warning"
    assert checks["video_seconds"]["status"] == "pass"
    assert checks["backend_sampled_memory_mib"]["status"] == "unavailable"
