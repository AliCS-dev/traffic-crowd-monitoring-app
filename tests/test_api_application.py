from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.api.application import create_app
from app.api.dependencies import (
    DATABASE_READINESS_TIMEOUT_SECONDS,
    ApplicationServices,
    create_application_services,
    get_detector,
)
from app.api.errors import ApiError
from app.api.settings import ApiSettings, ApiSettingsError


def create_services(
    *,
    database_ready=True,
    detector_ready=True,
    detector_factory=lambda: object(),
):
    return ApplicationServices(
        database_probe=lambda: database_ready,
        detector_probe=lambda: detector_ready,
        detector_factory=detector_factory,
    )


def create_test_app(services, *, origins=("http://localhost:5173",)):
    return create_app(
        settings=ApiSettings(cors_origins=origins),
        service_factory=lambda: services,
    )


def test_health_reports_process_identity_without_running_readiness_probes():
    probe_calls = []
    services = ApplicationServices(
        database_probe=lambda: probe_calls.append("database") or True,
        detector_probe=lambda: probe_calls.append("detector") or True,
        detector_factory=lambda: object(),
    )

    with TestClient(create_test_app(services)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Traffic and Crowd Monitoring API",
        "version": "0.1.0",
    }
    assert probe_calls == []


def test_readiness_reports_each_available_dependency():
    with TestClient(create_test_app(create_services())) as client:
        response = client.get("/api/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {
            "database": {"status": "ready"},
            "detector": {"status": "ready"},
        },
    }


def test_readiness_returns_503_without_leaking_probe_errors():
    def unavailable_database():
        raise RuntimeError("private database connection details")

    services = ApplicationServices(
        database_probe=unavailable_database,
        detector_probe=lambda: True,
        detector_factory=lambda: object(),
    )

    with TestClient(create_test_app(services)) as client:
        response = client.get("/api/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "database": {"status": "not_ready"},
            "detector": {"status": "ready"},
        },
    }
    assert "private" not in response.text


def test_detector_is_lazy_cached_and_released_at_shutdown():
    created_detectors = []

    def detector_factory():
        detector = object()
        created_detectors.append(detector)
        return detector

    services = create_services(detector_factory=detector_factory)
    application = create_test_app(services)

    @application.get("/api/test-detector")
    def use_detector(detector: Annotated[object, Depends(get_detector)]):
        return {"loaded": detector is not None}

    assert created_detectors == []
    with TestClient(application) as client:
        assert client.get("/api/health").status_code == 200
        assert created_detectors == []
        assert client.get("/api/test-detector").json() == {"loaded": True}
        assert client.get("/api/test-detector").json() == {"loaded": True}
        assert len(created_detectors) == 1

    services.get_detector()
    assert len(created_detectors) == 2


def test_startup_recovers_interrupted_video_jobs():
    recovery_calls = []
    services = ApplicationServices(
        database_probe=lambda: True,
        detector_probe=lambda: True,
        detector_factory=lambda: object(),
        startup_function=lambda: recovery_calls.append("recover") or 0,
    )

    with TestClient(create_test_app(services)) as client:
        assert client.get("/api/health").status_code == 200

    assert recovery_calls == ["recover"]


def test_default_services_use_a_bounded_database_readiness_probe(monkeypatch):
    database_calls = []
    profile = object()
    monkeypatch.setattr(
        "app.api.dependencies.load_runtime_model_profile", lambda: profile
    )
    monkeypatch.setattr(
        "app.api.dependencies.check_database_connection",
        lambda **options: database_calls.append(options) or True,
    )
    monkeypatch.setattr(
        "app.api.dependencies.verify_runtime_checkpoint",
        lambda received_profile, _root: received_profile is profile,
    )

    services = create_application_services()

    assert services.readiness() == {"database": True, "detector": True}
    assert database_calls == [{"connect_timeout": DATABASE_READINESS_TIMEOUT_SECONDS}]


def test_openapi_and_interactive_documentation_are_available():
    with TestClient(create_test_app(create_services())) as client:
        schema = client.get("/openapi.json")
        documentation = client.get("/docs")

    assert schema.status_code == 200
    assert schema.json()["info"] == {
        "title": "Traffic and Crowd Monitoring API",
        "version": "0.1.0",
    }
    assert set(schema.json()["paths"]) == {
        "/api/analyses/images",
        "/api/analyses/videos",
        "/api/analyses/videos/{session_id}",
        "/api/analyses/{session_id}",
        "/api/health",
        "/api/ready",
    }
    assert documentation.status_code == 200


def test_cors_uses_only_the_configured_development_origin():
    application = create_test_app(create_services(), origins=("http://frontend.test",))
    headers = {
        "Origin": "http://frontend.test",
        "Access-Control-Request-Method": "GET",
    }

    with TestClient(application) as client:
        allowed = client.options("/api/health", headers=headers)
        denied = client.options(
            "/api/health",
            headers={**headers, "Origin": "http://unknown.test"},
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://frontend.test"
    assert "access-control-allow-origin" not in denied.headers


def test_http_validation_and_application_errors_share_one_json_shape():
    application = create_test_app(create_services())

    @application.get("/api/test-validation/{item_id}")
    def validated_route(item_id: int):
        return {"item_id": item_id}

    @application.get("/api/test-error")
    def error_route():
        raise ApiError(409, "test_conflict", "The test request conflicts.")

    with TestClient(application) as client:
        missing = client.get("/api/missing")
        invalid = client.get("/api/test-validation/not-an-integer")
        conflict = client.get("/api/test-error")

    assert missing.json() == {
        "error": {"code": "not_found", "message": "Route not found."}
    }
    assert invalid.json() == {
        "error": {
            "code": "validation_error",
            "message": "The request contains invalid data.",
        }
    }
    assert conflict.json() == {
        "error": {
            "code": "test_conflict",
            "message": "The test request conflicts.",
        }
    }
    assert (missing.status_code, invalid.status_code, conflict.status_code) == (
        404,
        422,
        409,
    )


def test_unexpected_errors_use_the_public_internal_error_message():
    application = create_test_app(create_services())

    @application.get("/api/test-unexpected")
    def unexpected_route():
        raise RuntimeError("private implementation details")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/api/test-unexpected")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected server error occurred.",
        }
    }
    assert "private implementation details" not in response.text


def test_api_settings_parse_multiple_explicit_origins(monkeypatch):
    monkeypatch.setenv(
        "API_CORS_ORIGINS",
        "http://localhost:5173, https://frontend.example.test",
    )

    settings = ApiSettings.from_environment()

    assert settings.cors_origins == (
        "http://localhost:5173",
        "https://frontend.example.test",
    )


def test_api_settings_reject_wildcard_cors(monkeypatch):
    monkeypatch.setenv("API_CORS_ORIGINS", "*")

    with pytest.raises(ApiSettingsError, match="explicit HTTP or HTTPS origins"):
        ApiSettings.from_environment()


def test_api_settings_parse_positive_image_limits(monkeypatch):
    monkeypatch.setenv("API_MAX_IMAGE_UPLOAD_MB", "2")
    monkeypatch.setenv("API_MAX_IMAGE_PIXELS", "12345")
    monkeypatch.setenv("API_MAX_GRID_DIMENSION", "8")

    settings = ApiSettings.from_environment()

    assert settings.max_image_upload_bytes == 2 * 1024 * 1024
    assert settings.max_image_pixels == 12345
    assert settings.max_grid_dimension == 8


def test_api_settings_parse_positive_video_limits(monkeypatch):
    monkeypatch.setenv("API_MAX_VIDEO_UPLOAD_MB", "250")
    monkeypatch.setenv("API_VIDEO_WORKERS", "2")

    settings = ApiSettings.from_environment()

    assert settings.max_video_upload_bytes == 250 * 1024 * 1024
    assert settings.video_workers == 2


@pytest.mark.parametrize(
    "variable",
    [
        "API_MAX_IMAGE_UPLOAD_MB",
        "API_MAX_IMAGE_PIXELS",
        "API_MAX_GRID_DIMENSION",
        "API_MAX_VIDEO_UPLOAD_MB",
        "API_VIDEO_WORKERS",
    ],
)
def test_api_settings_reject_non_positive_limits(monkeypatch, variable):
    monkeypatch.setenv(variable, "0")

    with pytest.raises(
        ApiSettingsError, match=f"{variable} must be a positive integer"
    ):
        ApiSettings.from_environment()
