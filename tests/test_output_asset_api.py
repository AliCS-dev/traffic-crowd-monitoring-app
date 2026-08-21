from uuid import UUID

from fastapi.testclient import TestClient

from app.api.application import create_app
from app.api.dependencies import ApplicationServices
from app.api.settings import ApiSettings
from app.services.output_asset_service import (
    OutputAssetNotFoundError,
    OutputAssetUnavailableError,
    ResolvedOutputAsset,
)

ASSET_ID = UUID("12345678-1234-5678-1234-567812345678")


class FakeAssetService:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def resolve(self, asset_id):
        self.calls.append(asset_id)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def create_asset_app(asset_service):
    services = ApplicationServices(
        database_probe=lambda: True,
        detector_probe=lambda: True,
        detector_factory=lambda: object(),
        output_asset_factory=lambda: asset_service,
    )
    return create_app(
        settings=ApiSettings(),
        service_factory=lambda: services,
    )


def test_asset_endpoint_returns_controlled_image_response(tmp_path):
    output_path = tmp_path / "result.jpg"
    output_path.write_bytes(b"generated image")
    asset_service = FakeAssetService(
        ResolvedOutputAsset(
            asset_id=ASSET_ID,
            file_path=output_path,
            content_type="image/jpeg",
        )
    )

    with TestClient(create_asset_app(asset_service)) as client:
        response = client.get(f"/api/assets/{ASSET_ID}")

    assert response.status_code == 200
    assert response.content == b"generated image"
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "private, max-age=3600"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert asset_service.calls == [ASSET_ID]


def test_asset_endpoint_rejects_invalid_identifier_before_service_call():
    asset_service = FakeAssetService(None)

    with TestClient(create_asset_app(asset_service)) as client:
        response = client.get("/api/assets/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert asset_service.calls == []


def test_asset_endpoint_reports_unknown_and_unavailable_assets():
    cases = (
        (OutputAssetNotFoundError("Output asset not found."), "asset_not_found"),
        (
            OutputAssetUnavailableError("Output asset is unavailable."),
            "asset_unavailable",
        ),
    )

    for error, expected_code in cases:
        with TestClient(create_asset_app(FakeAssetService(error))) as client:
            response = client.get(f"/api/assets/{ASSET_ID}")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == expected_code
