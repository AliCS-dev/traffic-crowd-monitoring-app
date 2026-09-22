import json
from dataclasses import replace

import pytest

import app.runtime_provenance as provenance
from app.database.detection_repository import create_model_run_profile
from app.model_profile import load_runtime_model_profile
from app.schemas.monitoring import RuntimeProvenanceResult


@pytest.fixture(autouse=True)
def clear_runtime_cache():
    provenance.capture_runtime_provenance.cache_clear()
    yield
    provenance.capture_runtime_provenance.cache_clear()


def test_digest_tracks_backend_files_but_not_secrets(tmp_path):
    (tmp_path / "app").mkdir()
    source = tmp_path / "app/main.py"
    source.write_text("print('one')")
    first = provenance.source_digest(tmp_path)
    (tmp_path / ".env").write_text("SECRET=private")
    assert provenance.source_digest(tmp_path) == first
    source.write_text("print('two')")
    assert provenance.source_digest(tmp_path) != first


def test_missing_git_keeps_revision_and_dirty_state_unknown(tmp_path, monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(provenance.subprocess, "check_output", unavailable)
    result = provenance.source_identity(tmp_path)
    assert result["application_commit"] is None
    assert result["source_dirty"] is None
    assert len(result["source_sha256"]) == 64


def test_baked_revision_survives_without_git_and_detects_modified_source(tmp_path):
    digest = provenance.source_digest(tmp_path)
    (tmp_path / "build-info.json").write_text(
        json.dumps(
            {
                "application_commit": "a" * 40,
                "source_dirty": False,
                "source_sha256": digest,
            }
        )
    )
    assert provenance.source_identity(tmp_path)["source_dirty"] is False
    (tmp_path / "requirements-container.txt").write_text("changed")
    result = provenance.source_identity(tmp_path)
    assert result["application_commit"] == "a" * 40
    assert result["source_dirty"] is True
    assert result["source_sha256"] != digest


def test_capture_is_cached_validated_and_does_not_export_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://private-password")
    monkeypatch.setenv("SECRET_TOKEN", "secret-value")
    record = provenance.capture_runtime_provenance("cpu")
    assert provenance.capture_runtime_provenance("cpu") is record
    validated = RuntimeProvenanceResult.model_validate(record)
    assert validated.dependencies["pydantic"]
    assert validated.device == "cpu"
    assert validated.gpu_name is None
    assert "private-password" not in json.dumps(record)
    assert "secret-value" not in json.dumps(record)


def test_new_model_record_contains_a_snapshot():
    class Cursor:
        def execute(self, query, parameters):
            self.query, self.parameters = query, parameters

    cursor = Cursor()
    profile = replace(load_runtime_model_profile(), device="cpu")
    create_model_run_profile(cursor, 42, profile)
    assert "runtime_provenance" in cursor.query
    stored = RuntimeProvenanceResult.model_validate_json(cursor.parameters[-1])
    assert stored.device == "cpu"
    assert stored.source_sha256


def test_installed_versions_prefer_first_distribution(monkeypatch):
    class Distribution:
        def __init__(self, version):
            self.metadata = {"Name": "some_package"}
            self.version = version

    monkeypatch.setattr(
        provenance, "distributions", lambda: [Distribution("2"), Distribution("1")]
    )
    assert provenance.dependency_versions() == {"some-package": "2"}
