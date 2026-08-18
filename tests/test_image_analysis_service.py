from io import BytesIO
from types import SimpleNamespace
from uuid import UUID

import cv2
import numpy as np
import pytest

from app.model_profile import load_runtime_model_profile
from app.services.image_analysis_service import (
    ImageAnalysisService,
    InvalidImageAnalysisOptionsError,
)
from app.services.image_upload_service import ImageUploadPolicy

ASSET_ID = UUID("12345678-1234-5678-1234-567812345678")
MODEL_PROFILE = load_runtime_model_profile()


def encoded_jpeg():
    success, encoded = cv2.imencode(".jpg", np.full((50, 100, 3), 127, dtype=np.uint8))
    assert success
    return encoded.tobytes()


class FakeResult:
    names = {0: "pedestrian", 1: "car"}

    def __init__(self, *, boxes=None):
        self.boxes = (
            boxes
            if boxes is not None
            else [
                SimpleNamespace(
                    cls=[1],
                    conf=[0.9],
                    xyxy=[[20.0, 20.0, 60.0, 60.0]],
                )
            ]
        )

    def plot(self):
        return np.full((100, 200, 3), 200, dtype=np.uint8)


class FakeDetector:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def detect(self, image, **options):
        self.calls.append((image.shape, options))
        return self.results


def create_service(tmp_path, detector, persistence_function):
    return ImageAnalysisService(
        detector=detector,
        model_profile=MODEL_PROFILE,
        upload_directory=tmp_path / "uploads",
        output_directory=tmp_path / "outputs",
        upload_policy=ImageUploadPolicy(max_bytes=1024 * 1024, max_pixels=10_000),
        max_grid_dimension=20,
        persistence_function=persistence_function,
        asset_id_factory=lambda: ASSET_ID,
    )


def analyse(service, **options):
    return service.analyze_upload(
        BytesIO(encoded_jpeg()),
        filename="../../original scene.jpg",
        content_type="image/jpeg",
        **options,
    )


def test_complete_analysis_uses_profile_grid_and_server_controlled_paths(tmp_path):
    persisted = []
    detector = FakeDetector([FakeResult()])
    service = create_service(
        tmp_path,
        detector,
        lambda **values: persisted.append(values) or {"session_id": 42},
    )

    result = analyse(
        service,
        session_name="  morning junction  ",
        grid_rows=2,
        grid_columns=4,
    )

    assert result.session_id == 42
    assert result.output_asset_id == ASSET_ID
    assert result.detection_count == 1
    assert detector.calls[0][0] == (100, 200, 3)
    assert detector.calls[0][1]["confidence_threshold"] == MODEL_PROFILE.confidence
    assert persisted[0]["session_name"] == "morning junction"
    assert persisted[0]["original_filename"] == "original scene.jpg"
    assert persisted[0]["model_profile"] is MODEL_PROFILE
    assert persisted[0]["grid_count_result"].grid_size.rows == 2
    assert persisted[0]["grid_count_result"].grid_size.columns == 4
    assert persisted[0]["output_asset_id"] == ASSET_ID
    assert persisted[0]["image_path"].name == f"{ASSET_ID}.jpg"
    assert persisted[0]["output_file_path"].name == f"{ASSET_ID}.jpg"
    assert "original scene" not in str(persisted[0]["image_path"])
    assert persisted[0]["image_path"].is_file()
    assert persisted[0]["output_file_path"].is_file()


def test_empty_detection_result_is_still_persisted(tmp_path):
    persisted = []
    service = create_service(
        tmp_path,
        FakeDetector([FakeResult(boxes=[])]),
        lambda **values: persisted.append(values) or {"session_id": 43},
    )

    result = analyse(service, grid_rows=1, grid_columns=1)

    assert result.detection_count == 0
    assert persisted[0]["detection_records"] == []
    assert persisted[0]["object_count_summary_records"] == []
    assert persisted[0]["grid_count_result"].cells[0].total_count == 0


@pytest.mark.parametrize("failure_stage", ["detection", "persistence"])
def test_failed_analysis_removes_partial_input_and_output_files(
    tmp_path, failure_stage
):
    if failure_stage == "detection":
        detector = FakeDetector([])

        def persistence_function(**_values):
            pytest.fail("Persistence should not run.")

    else:
        detector = FakeDetector([FakeResult()])

        def persistence_function(**_values):
            raise RuntimeError("database failed")

    service = create_service(tmp_path, detector, persistence_function)

    with pytest.raises(RuntimeError):
        analyse(service)

    assert list((tmp_path / "uploads").iterdir()) == []
    assert list((tmp_path / "outputs").iterdir()) == []


def test_output_write_failure_removes_partial_files(tmp_path, monkeypatch):
    service = create_service(
        tmp_path,
        FakeDetector([FakeResult()]),
        lambda **_values: pytest.fail("Persistence should not run."),
    )

    def fail_after_partial_write(_result, output_path):
        output_path.write_bytes(b"partial output")
        raise OSError("output failed")

    monkeypatch.setattr(
        "app.services.image_analysis_service.save_detection_output",
        fail_after_partial_write,
    )

    with pytest.raises(OSError, match="output failed"):
        analyse(service)

    assert list((tmp_path / "uploads").iterdir()) == []
    assert list((tmp_path / "outputs").iterdir()) == []


@pytest.mark.parametrize(
    ("grid_rows", "grid_columns"),
    [(1, None), (None, 1), (0, 1), (1, 21)],
)
def test_invalid_grid_options_are_rejected_before_upload_read(
    tmp_path, grid_rows, grid_columns
):
    service = create_service(
        tmp_path,
        FakeDetector([FakeResult()]),
        lambda **_values: pytest.fail("Persistence should not run."),
    )

    with pytest.raises(InvalidImageAnalysisOptionsError):
        service.analyze_upload(
            BytesIO(b"not read"),
            filename="scene.jpg",
            content_type="image/jpeg",
            grid_rows=grid_rows,
            grid_columns=grid_columns,
        )
