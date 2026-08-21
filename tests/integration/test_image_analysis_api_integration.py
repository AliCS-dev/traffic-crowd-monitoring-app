import os
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.application import create_app
from app.api.dependencies import ApplicationServices
from app.api.settings import ApiSettings
from app.crowd_analysis import load_dense_crowd_analysis_decision
from app.database.connection import open_database_connection
from app.database.migration_runner import apply_pending_migrations
from app.database.monitoring_query_repository import get_monitoring_session
from app.model_profile import load_runtime_model_profile
from app.services.image_analysis_service import ImageAnalysisService
from app.services.image_upload_service import ImageUploadPolicy
from app.services.output_asset_service import OutputAssetService

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION_TESTS") != "1",
    reason="PostgreSQL integration tests are not enabled.",
)


class ControlledResult:
    names = {0: "pedestrian", 1: "car"}
    boxes = [
        SimpleNamespace(
            cls=[1],
            conf=[0.91],
            xyxy=[[20.0, 20.0, 60.0, 60.0]],
        )
    ]

    def plot(self):
        return np.full((100, 200, 3), 200, dtype=np.uint8)


class ControlledDetector:
    def detect(self, _image, **_options):
        return [ControlledResult()]


def test_complete_image_api_workflow_persists_and_reads_result(tmp_path):
    apply_pending_migrations()
    profile = load_runtime_model_profile()
    crowd_analysis_decision = load_dense_crowd_analysis_decision()
    settings = ApiSettings(
        image_upload_directory=tmp_path / "uploads",
        image_output_directory=tmp_path / "outputs",
        max_image_upload_bytes=1024 * 1024,
        max_image_pixels=10_000,
        max_grid_dimension=20,
    )
    services = ApplicationServices(
        database_probe=lambda: True,
        detector_probe=lambda: True,
        detector_factory=ControlledDetector,
        image_analysis_factory=lambda detector: ImageAnalysisService(
            detector=detector,
            model_profile=profile,
            crowd_analysis_decision=crowd_analysis_decision,
            upload_directory=settings.image_upload_directory,
            output_directory=settings.image_output_directory,
            upload_policy=ImageUploadPolicy(
                max_bytes=settings.max_image_upload_bytes,
                max_pixels=settings.max_image_pixels,
            ),
            max_grid_dimension=settings.max_grid_dimension,
        ),
        output_asset_factory=lambda: OutputAssetService(
            allowed_directories=(settings.image_output_directory,)
        ),
        monitoring_session_reader=get_monitoring_session,
    )
    application = create_app(settings=settings, service_factory=lambda: services)
    success, encoded = cv2.imencode(".jpg", np.full((50, 100, 3), 127, dtype=np.uint8))
    assert success
    session_id = None

    try:
        with TestClient(application) as client:
            created = client.post(
                "/api/analyses/images",
                files={
                    "image": (
                        "original-drone-scene.jpg",
                        encoded.tobytes(),
                        "image/jpeg",
                    )
                },
                data={
                    "session_name": "API integration image",
                    "grid_rows": "2",
                    "grid_columns": "2",
                },
            )
            session_id = created.json().get("session_id")
            result = client.get(f"/api/analyses/{session_id}")
            visual_asset_url = result.json()["frames"][0]["visual_asset"]["url"]
            visual_asset = client.get(visual_asset_url)

        assert created.status_code == 201
        assert result.status_code == 200
        values = result.json()
        assert values["id"] == session_id
        assert values["status"] == "completed"
        assert values["sources"][0]["original_filename"] == ("original-drone-scene.jpg")
        assert values["model_profile"]["model_id"] == profile.model_id
        assert values["dense_crowd_analysis"]["status"] == "unsupported"
        assert values["dense_crowd_analysis"]["count"] is None
        assert values["dense_crowd_analysis"]["method_id"] is None
        assert values["dense_crowd_analysis"]["model_id"] is None
        assert (
            values["dense_crowd_analysis"]["evaluated_candidate_id"] == "p2pnet-shtecha"
        )
        assert len(values["frames"]) == 1
        frame = values["frames"][0]
        assert frame["output_asset_id"] == created.json()["output_asset_id"]
        assert frame["coordinate_space"]["width"] == 200
        assert frame["coordinate_space"]["height"] == 100
        assert frame["visual_asset"]["rendered_overlays"] == ["detections"]
        assert visual_asset.status_code == 200
        assert visual_asset.headers["content-type"] == "image/jpeg"
        decoded_asset = cv2.imdecode(
            np.frombuffer(visual_asset.content, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        assert decoded_asset.shape[:2] == (100, 200)
        assert len(frame["detections"]) == 1
        assert frame["detections"][0]["object_class"] == "car_or_van"
        assert frame["frame_summaries"][0]["object_count"] == 1
        assert len(frame["grid_cells"]) == 4
        assert (
            sum(
                summary["object_count"]
                for cell in frame["grid_cells"]
                for summary in cell["summaries"]
            )
            == 1
        )
        assert len(list(settings.image_upload_directory.iterdir())) == 1
        assert len(list(settings.image_output_directory.iterdir())) == 1

        with open_database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT input_sources.file_path, processed_frames.output_file_path
                    FROM processed_frames
                    JOIN input_sources
                        ON input_sources.id = processed_frames.input_source_id
                    WHERE processed_frames.session_id = %s;
                    """,
                    (session_id,),
                )
                input_path, output_path = cursor.fetchone()
        assert str(tmp_path) in input_path
        assert str(tmp_path) in output_path
        assert "original-drone-scene" not in input_path
    finally:
        if session_id is not None:
            with open_database_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM monitoring_sessions WHERE id = %s;",
                        (session_id,),
                    )
