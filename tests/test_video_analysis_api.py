from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.application import create_app
from app.api.dependencies import ApplicationServices
from app.api.settings import ApiSettings
from app.schemas.monitoring import VideoAnalysisJobResult
from app.services.video_analysis_service import InvalidVideoAnalysisOptionsError
from app.services.video_upload_service import (
    InvalidVideoUploadError,
    UnsupportedVideoUploadError,
    VideoUploadTooLargeError,
)


class FakeVideoAnalysisService:
    def __init__(self, *, error=None, job=None):
        self.error = error
        self.calls = []
        self.closed = False
        self.job = job

    def submit_upload(self, file, **values):
        self.calls.append({"content": file.read(), **values})
        if self.error:
            raise self.error
        return SimpleNamespace(
            session_id=42,
            status="queued",
            sampled_frames_total=6,
            sampling_interval_seconds=1.5,
            grid_rows=2,
            grid_columns=3,
        )

    def get_job(self, _session_id):
        return self.job

    def close(self):
        self.closed = True


def create_client(service):
    services = ApplicationServices(
        database_probe=lambda: True,
        detector_probe=lambda: True,
        detector_factory=lambda: object(),
        video_analysis_factory=lambda _provider: service,
    )
    return TestClient(
        create_app(settings=ApiSettings(), service_factory=lambda: services),
        raise_server_exceptions=False,
    )


def post_video(client):
    return client.post(
        "/api/analyses/videos",
        files={"video": ("traffic.mp4", b"video bytes", "video/mp4")},
        data={
            "session_name": "traffic run",
            "sampling_interval_seconds": "1.5",
            "grid_rows": "2",
            "grid_columns": "3",
        },
    )


def test_video_upload_returns_accepted_job_and_progress_urls():
    service = FakeVideoAnalysisService()
    with create_client(service) as client:
        response = post_video(client)

    assert response.status_code == 202
    assert response.json() == {
        "session_id": 42,
        "status": "queued",
        "job_url": "/api/analyses/videos/42",
        "result_url": "/api/analyses/42",
        "sampled_frames_total": 6,
        "sampling_interval_seconds": 1.5,
        "grid_rows": 2,
        "grid_columns": 3,
    }
    assert service.calls[0]["content"] == b"video bytes"
    assert service.closed is True


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (VideoUploadTooLargeError("large"), 413, "video_too_large"),
        (UnsupportedVideoUploadError("format"), 415, "unsupported_video"),
        (InvalidVideoUploadError("broken"), 422, "invalid_video"),
        (
            InvalidVideoAnalysisOptionsError("options"),
            422,
            "invalid_analysis_options",
        ),
    ],
)
def test_video_validation_errors_use_public_api_shape(error, status_code, code):
    with create_client(FakeVideoAnalysisService(error=error)) as client:
        response = post_video(client)

    assert response.status_code == status_code
    assert response.json() == {"error": {"code": code, "message": str(error)}}


def test_progress_endpoint_returns_persistent_job_state():
    now = datetime.now(timezone.utc)
    job = VideoAnalysisJobResult(
        session_id=42,
        status="processing",
        sampling_interval_seconds=1.5,
        grid_rows=None,
        grid_columns=None,
        total_source_frames=100,
        sampled_frames_total=10,
        sampled_frames_processed=4,
        progress_percent=40,
        failure_code=None,
        failure_message=None,
        queued_at=now,
        started_at=now,
        finished_at=None,
    )
    with create_client(FakeVideoAnalysisService(job=job)) as client:
        response = client.get("/api/analyses/videos/42")

    assert response.status_code == 200
    assert response.json()["status"] == "processing"
    assert response.json()["progress_percent"] == 40


def test_missing_progress_job_returns_not_found():
    with create_client(FakeVideoAnalysisService()) as client:
        response = client.get("/api/analyses/videos/999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "video_job_not_found"
