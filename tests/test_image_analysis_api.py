from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.application import create_app
from app.api.dependencies import ApplicationServices
from app.api.settings import ApiSettings
from app.crowd_analysis import load_dense_crowd_analysis_decision
from app.model_profile import load_runtime_model_profile
from app.services.image_analysis_service import (
    ImageAnalysisResult,
    ImageAnalysisService,
    InvalidImageAnalysisOptionsError,
)
from app.services.image_upload_service import (
    ImageUploadPolicy,
    ImageUploadTooLargeError,
    InvalidImageUploadError,
    UnsupportedImageUploadError,
)

ASSET_ID = UUID("12345678-1234-5678-1234-567812345678")
CROWD_ANALYSIS_DECISION = load_dense_crowd_analysis_decision()


class FakeImageAnalysisService:
    def __init__(self, result=None, error=None):
        self.result = result or ImageAnalysisResult(
            session_id=42,
            output_asset_id=ASSET_ID,
            detection_count=3,
            grid_rows=2,
            grid_columns=4,
            dense_crowd_analysis=CROWD_ANALYSIS_DECISION,
        )
        self.error = error
        self.calls = []

    def analyze_upload(self, file, **values):
        self.calls.append({"content": file.read(), **values})
        if self.error is not None:
            raise self.error
        return self.result


def create_test_client(analysis_service, *, session_reader=lambda _session_id: None):
    services = ApplicationServices(
        database_probe=lambda: True,
        detector_probe=lambda: True,
        detector_factory=lambda: object(),
        image_analysis_factory=lambda _detector: analysis_service,
        monitoring_session_reader=session_reader,
    )
    application = create_app(
        settings=ApiSettings(),
        service_factory=lambda: services,
    )
    return TestClient(application, raise_server_exceptions=False)


def post_image(client, *, data=None, filename="scene.jpg", content_type="image/jpeg"):
    return client.post(
        "/api/analyses/images",
        files={"image": (filename, b"controlled image bytes", content_type)},
        data=data or {},
    )


def test_image_upload_returns_stable_completed_analysis_identifier():
    analysis_service = FakeImageAnalysisService()

    with create_test_client(analysis_service) as client:
        response = post_image(
            client,
            data={
                "session_name": "morning traffic",
                "grid_rows": "2",
                "grid_columns": "4",
            },
        )

    assert response.status_code == 201
    assert response.json() == {
        "session_id": 42,
        "status": "completed",
        "result_url": "/api/analyses/42",
        "output_asset_id": str(ASSET_ID),
        "detection_count": 3,
        "grid_rows": 2,
        "grid_columns": 4,
        "dense_crowd_analysis": {
            "status": "unsupported",
            "count": None,
            "method_id": None,
            "model_id": None,
            "evaluated_candidate_id": "p2pnet-shtecha",
            "quality_gate_status": "failed",
            "evaluation_reference": (
                "docs/evaluation/dedicated_crowd_counting_result.md"
            ),
            "reason_code": "no_accepted_dense_crowd_model",
            "message": CROWD_ANALYSIS_DECISION.message,
        },
    }
    assert analysis_service.calls == [
        {
            "content": b"controlled image bytes",
            "filename": "scene.jpg",
            "content_type": "image/jpeg",
            "session_name": "morning traffic",
            "grid_rows": 2,
            "grid_columns": 4,
        }
    ]


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (ImageUploadTooLargeError("too large"), 413, "image_too_large"),
        (UnsupportedImageUploadError("unsupported"), 415, "unsupported_image"),
        (InvalidImageUploadError("malformed"), 422, "invalid_image"),
        (
            InvalidImageAnalysisOptionsError("bad grid"),
            422,
            "invalid_analysis_options",
        ),
    ],
)
def test_upload_validation_errors_use_consistent_api_payload(error, status_code, code):
    with create_test_client(FakeImageAnalysisService(error=error)) as client:
        response = post_image(client)

    assert response.status_code == status_code
    assert response.json() == {"error": {"code": code, "message": str(error)}}


def test_unsafe_uploads_are_rejected_before_detection_or_file_creation(tmp_path):
    class DetectorThatMustNotRun:
        calls = 0

        def detect(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("Detector must not run for an invalid upload.")

    detector = DetectorThatMustNotRun()
    service = ImageAnalysisService(
        detector=detector,
        model_profile=load_runtime_model_profile(),
        crowd_analysis_decision=CROWD_ANALYSIS_DECISION,
        upload_directory=tmp_path / "uploads",
        output_directory=tmp_path / "outputs",
        upload_policy=ImageUploadPolicy(max_bytes=32, max_pixels=10_000),
        max_grid_dimension=20,
        persistence_function=lambda **_values: pytest.fail(
            "Persistence must not run for an invalid upload."
        ),
    )

    with create_test_client(service) as client:
        malformed = client.post(
            "/api/analyses/images",
            files={"image": ("scene.jpg", b"not an image", "image/jpeg")},
        )
        oversized = client.post(
            "/api/analyses/images",
            files={"image": ("scene.jpg", b"x" * 33, "image/jpeg")},
        )

    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "invalid_image"
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "image_too_large"
    assert detector.calls == 0
    assert not (tmp_path / "uploads").exists()
    assert not (tmp_path / "outputs").exists()


def test_processing_failure_uses_generic_error_without_private_details():
    service = FakeImageAnalysisService(error=RuntimeError("private detector failure"))

    with create_test_client(service) as client:
        response = post_image(client)

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected server error occurred.",
        }
    }
    assert "private detector failure" not in response.text


def result_record():
    return {
        "id": 42,
        "session_name": "morning traffic",
        "status": "completed",
        "started_at": "2026-08-18T12:00:00Z",
        "completed_at": "2026-08-18T12:00:01Z",
        "notes": None,
        "model_profile": None,
        "dense_crowd_analysis": {
            "status": "unsupported",
            "count": None,
            "method_id": None,
            "model_id": None,
            "evaluated_candidate_id": "p2pnet-shtecha",
            "quality_gate_status": "failed",
            "evaluation_reference": (
                "docs/evaluation/dedicated_crowd_counting_result.md"
            ),
            "reason_code": "no_accepted_dense_crowd_model",
            "message": CROWD_ANALYSIS_DECISION.message,
        },
        "sources": [
            {
                "id": 10,
                "source_type": "image",
                "original_filename": "scene.jpg",
                "created_at": "2026-08-18T12:00:00Z",
            }
        ],
        "frames": [
            {
                "id": 20,
                "input_source_id": 10,
                "frame_number": 0,
                "frame_timestamp_seconds": 0,
                "image_width": 200,
                "image_height": 100,
                "output_asset_id": str(ASSET_ID),
                "visual_asset": {
                    "asset_id": str(ASSET_ID),
                    "url": f"/api/assets/{ASSET_ID}",
                    "content_type": "image/jpeg",
                    "width": 200,
                    "height": 100,
                    "rendered_overlays": ["detections"],
                },
                "coordinate_space": {
                    "name": "processed_image_pixels",
                    "origin": "top_left",
                    "x_axis_direction": "right",
                    "y_axis_direction": "down",
                    "width": 200,
                    "height": 100,
                },
                "processed_at": "2026-08-18T12:00:01Z",
                "detections": [],
                "frame_summaries": [],
                "grid_cells": [],
                "alerts": [],
            }
        ],
    }


def test_completed_analysis_is_available_through_read_route():
    requested_ids = []

    def session_reader(session_id):
        requested_ids.append(session_id)
        return result_record()

    with create_test_client(
        FakeImageAnalysisService(), session_reader=session_reader
    ) as client:
        response = client.get("/api/analyses/42")

    assert response.status_code == 200
    assert response.json()["id"] == 42
    assert response.json()["frames"][0]["output_asset_id"] == str(ASSET_ID)
    assert response.json()["frames"][0]["visual_asset"]["url"] == (
        f"/api/assets/{ASSET_ID}"
    )
    assert response.json()["dense_crowd_analysis"]["status"] == "unsupported"
    assert response.json()["dense_crowd_analysis"]["count"] is None
    assert "file_path" not in response.text
    assert requested_ids == [42]


def test_missing_or_invalid_analysis_identifier_has_clear_domain_error():
    with create_test_client(FakeImageAnalysisService()) as client:
        missing = client.get("/api/analyses/999")
        invalid = client.get("/api/analyses/0")

    assert missing.status_code == 404
    assert missing.json() == {
        "error": {
            "code": "analysis_not_found",
            "message": "Analysis result not found.",
        }
    }
    assert invalid.status_code == 422
    assert invalid.json() == {
        "error": {
            "code": "invalid_session_id",
            "message": "Session ID must be a positive integer.",
        }
    }
