from dataclasses import replace

import pytest

from app.api.dependencies import create_application_services
from app.api.settings import ApiSettings, ApiSettingsError
from app.model_profile import load_runtime_model_profile


@pytest.mark.parametrize("device", ["cpu", "cuda", "cuda:0", "cuda:2"])
def test_environment_accepts_explicit_device(monkeypatch, device):
    monkeypatch.setenv("API_DEVICE", device)
    assert ApiSettings.from_environment().model_device == device


@pytest.mark.parametrize("device", ["", "auto", "cuda:-1", "cuda:abc", " cpu", "mps"])
def test_environment_rejects_invalid_device(monkeypatch, device):
    monkeypatch.setenv("API_DEVICE", device)
    with pytest.raises(ApiSettingsError, match="API_DEVICE"):
        ApiSettings.from_environment()


@pytest.mark.parametrize(
    ("device", "available", "count", "ready"),
    [
        ("cuda:0", False, 0, False),
        ("cuda:1", True, 1, False),
        ("cuda", True, 1, True),
        ("cpu", False, 0, True),
    ],
)
def test_readiness_checks_selected_device(monkeypatch, device, available, count, ready):
    monkeypatch.setattr(
        "app.api.dependencies.check_database_connection", lambda **_: True
    )
    monkeypatch.setattr(
        "app.api.dependencies.verify_runtime_checkpoint", lambda *_: None
    )
    monkeypatch.setattr(
        "app.api.dependencies.torch.cuda.is_available", lambda: available
    )
    monkeypatch.setattr("app.api.dependencies.torch.cuda.device_count", lambda: count)
    services = create_application_services(ApiSettings(model_device=device))
    assert services.readiness() == {"database": True, "detector": ready}


def test_device_override_preserves_model_identity_and_reaches_stored_profile(
    monkeypatch,
):
    profile = load_runtime_model_profile()
    received = []
    monkeypatch.setattr(
        "app.api.dependencies.load_runtime_model_profile", lambda: profile
    )
    monkeypatch.setattr(
        "app.api.dependencies.ObjectDetector.from_runtime_profile",
        lambda selected: received.append(selected) or object(),
    )
    monkeypatch.setattr(
        "app.api.dependencies.ImageAnalysisService",
        lambda **options: options,
    )
    services = create_application_services(ApiSettings(model_device="cpu"))
    options = services.get_image_analysis_service()
    expected = replace(profile, device="cpu")
    assert received == [expected]
    assert options["model_profile"] == expected
    assert profile.device == "cuda:0"


def test_default_device_is_unchanged(monkeypatch):
    profile = load_runtime_model_profile()
    monkeypatch.setattr(
        "app.api.dependencies.ObjectDetector.from_runtime_profile",
        lambda selected: selected,
    )
    assert create_application_services(ApiSettings()).get_detector() == profile
