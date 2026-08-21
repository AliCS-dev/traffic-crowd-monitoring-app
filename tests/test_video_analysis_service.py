from pathlib import Path
from uuid import UUID

import numpy as np
import pytest

import app.services.video_analysis_service as service_module
from app.crowd_analysis import load_dense_crowd_analysis_decision
from app.database.video_job_repository import CreatedVideoJob
from app.model_profile import load_runtime_model_profile
from app.services.video_analysis_service import (
    PUBLIC_PROCESSING_FAILURE,
    InvalidVideoAnalysisOptionsError,
    VideoAnalysisService,
)
from app.services.video_detection_service import VideoFrameDetectionResult
from app.services.video_service import VideoMetadata
from app.services.video_upload_service import StoredVideoUpload, VideoUploadPolicy

ASSET_ID = UUID("12345678-1234-5678-1234-567812345678")


class CapturingExecutor:
    def __init__(self):
        self.work = None
        self.shutdown_calls = []

    def submit(self, function, item):
        self.work = (function, item)

    def run(self):
        function, item = self.work
        function(item)

    def shutdown(self, **values):
        self.shutdown_calls.append(values)


class FakeReader:
    def __init__(self, path):
        self.metadata = VideoMetadata(Path(path), 20, 10, 2, 3, 1.5)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read_next_frame(self):
        return None


def create_service(tmp_path, monkeypatch, *, processing_error=None):
    executor = CapturingExecutor()
    calls = {"detector": 0, "progress": [], "failed": [], "completed": []}
    path = tmp_path / "stored.mp4"
    path.write_bytes(b"video")
    stored = StoredVideoUpload(
        asset_id=None,
        original_filename="traffic.mp4",
        path=path,
        metadata=VideoMetadata(path, 20, 10, 2, 3, 1.5),
    )

    def detector_provider():
        calls["detector"] += 1
        return object()

    def process_frames(*_args):
        if processing_error:
            raise processing_error
        yield VideoFrameDetectionResult(
            frame_number=0,
            timestamp_seconds=0,
            image_width=20,
            image_height=10,
            detection_records=[
                {
                    "object_class": "car_or_van",
                    "confidence": 0.9,
                    "bbox_x_min": 1.0,
                    "bbox_y_min": 1.0,
                    "bbox_x_max": 5.0,
                    "bbox_y_max": 5.0,
                }
            ],
            object_counts={"car_or_van": 1},
            annotated_image=np.zeros((10, 20, 3), dtype=np.uint8),
        )

    monkeypatch.setattr(service_module, "process_sampled_video_frames", process_frames)
    service = VideoAnalysisService(
        detector_provider=detector_provider,
        model_profile=load_runtime_model_profile(),
        crowd_analysis_decision=load_dense_crowd_analysis_decision(),
        upload_directory=tmp_path,
        output_directory=tmp_path / "outputs",
        upload_policy=VideoUploadPolicy(max_bytes=100, max_frame_pixels=1000),
        max_grid_dimension=20,
        executor=executor,
        store_upload=lambda *_args, **_kwargs: stored,
        create_job=lambda **_kwargs: CreatedVideoJob(42, 7),
        mark_processing=lambda session_id: calls.setdefault("processing", []).append(
            session_id
        ),
        update_progress=lambda session_id, count: calls["progress"].append(
            (session_id, count)
        ),
        complete_job=lambda session_id, results: calls["completed"].append(
            (session_id, results)
        ),
        fail_job=lambda *values: calls["failed"].append(values),
        read_job=lambda session_id: {"session_id": session_id},
        video_reader_factory=FakeReader,
        asset_id_factory=lambda: ASSET_ID,
    )
    return service, executor, calls


def test_upload_returns_queued_job_before_detector_runs_and_worker_persists_grid(
    tmp_path, monkeypatch
):
    service, executor, calls = create_service(tmp_path, monkeypatch)

    result = service.submit_upload(
        object(),
        filename="traffic.mp4",
        content_type="video/mp4",
        session_name=" morning ",
        sampling_interval_seconds=1,
        grid_rows=2,
        grid_columns=2,
    )

    assert result.session_id == 42
    assert result.status == "queued"
    assert calls["detector"] == 0
    executor.run()
    assert calls["detector"] == 1
    assert calls["progress"] == [(42, 1)]
    persisted = calls["completed"][0][1][0]
    assert persisted.grid_count_result.total_count == 1
    assert persisted.output_asset_id == ASSET_ID
    assert persisted.output_file_path == tmp_path / "outputs" / f"{ASSET_ID}.jpg"
    assert persisted.output_file_path.is_file()
    assert persisted.annotated_image is None
    assert calls["failed"] == []


def test_worker_failure_is_persisted_without_private_details(tmp_path, monkeypatch):
    service, executor, calls = create_service(
        tmp_path, monkeypatch, processing_error=RuntimeError("private GPU detail")
    )
    service.submit_upload(
        object(),
        filename="traffic.mp4",
        content_type="video/mp4",
        session_name=None,
        sampling_interval_seconds=1,
        grid_rows=None,
        grid_columns=None,
    )

    executor.run()

    assert calls["completed"] == []
    assert calls["failed"] == [
        (42, "video_processing_failed", PUBLIC_PROCESSING_FAILURE)
    ]


def test_invalid_grid_is_rejected_before_upload(tmp_path, monkeypatch):
    service, _executor, calls = create_service(tmp_path, monkeypatch)

    with pytest.raises(InvalidVideoAnalysisOptionsError):
        service.submit_upload(
            object(),
            filename="traffic.mp4",
            content_type="video/mp4",
            session_name=None,
            sampling_interval_seconds=1,
            grid_rows=2,
            grid_columns=None,
        )

    assert calls["detector"] == 0
