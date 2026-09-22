import copy
import json
import subprocess

import pytest

from app.runtime_provenance import capture_runtime_provenance, source_digest
from evaluation.runtime_regression import compare_records
from scripts.check_runtime_regression_evidence import (
    DATA,
    check_base,
    sha256,
    validate_evidence,
)
from scripts.export_runtime_manifest import export_manifest

TOLERANCES = {"box_pixels": 0.5, "confidence": 0.0001}


@pytest.fixture
def record():
    return {
        "manifest_sha256": "a" * 64,
        "model": {"checkpoint_sha256": "b" * 64, "device": "cuda:0"},
        "frames": {
            "image.png:0": {
                "dimensions": [100, 100],
                "timestamp": 0,
                "output_sha256": "c" * 64,
                "detections": [
                    {"class": "car", "confidence": 0.8, "box": [1, 2, 10, 20]},
                    {"class": "car", "confidence": 0.9, "box": [2, 3, 11, 21]},
                ],
            }
        },
    }


def test_comparison_ignores_detection_order_and_accepts_declared_tolerance(record):
    candidate = copy.deepcopy(record)
    detections = candidate["frames"]["image.png:0"]["detections"]
    detections.reverse()
    detections[0]["box"][0] += 0.5
    detections[0]["confidence"] += 0.00009
    assert compare_records(record, candidate, TOLERANCES) == []


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("dimensions", [200, 100], "frame_metadata_changed"),
        ("timestamp", 1, "frame_metadata_changed"),
        ("detections", [], "class_counts_changed"),
        ("output_sha256", "d" * 64, "rendered_output_changed"),
    ],
)
def test_changed_frame_requires_review(record, field, value, reason):
    candidate = copy.deepcopy(record)
    candidate["frames"]["image.png:0"][field] = value
    assert f"image.png:0:{reason}" in compare_records(record, candidate, TOLERANCES)


@pytest.mark.parametrize("field", ["box", "confidence"])
def test_prediction_outside_tolerance_requires_review(record, field):
    candidate = copy.deepcopy(record)
    detection = candidate["frames"]["image.png:0"]["detections"][0]
    if field == "box":
        detection[field][0] += 0.501
    else:
        detection[field] += 0.00011
    assert "image.png:0:car:predictions_changed" in compare_records(
        record, candidate, TOLERANCES
    )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("manifest_sha256", "changed", "fixture_manifest_changed"),
        ("model", {}, "model_or_inference_settings_changed"),
        ("frames", {}, "frame_set_changed"),
    ],
)
def test_changed_run_requires_review(record, field, value, reason):
    candidate = {**record, field: value}
    assert compare_records(record, candidate, TOLERANCES) == [reason]


@pytest.fixture
def evidence(tmp_path, record):
    directory = tmp_path / DATA
    (directory / "fixtures").mkdir(parents=True)
    image = directory / "fixtures/image.png"
    image.write_bytes(b"test fixture")
    manifest = directory / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "fixtures": [
                    {"name": image.name, "kind": "image", "sha256": sha256(image)}
                ],
                "tolerances": TOLERANCES,
            }
        )
    )
    (tmp_path / "requirements-container.txt").write_text("pydantic>=2\n")
    runtime = {
        **capture_runtime_provenance("cpu"),
        "source_sha256": source_digest(tmp_path),
        "source_dirty": False,
        "application_commit": "a" * 40,
    }
    record.update(manifest_sha256=sha256(manifest), runtime=runtime)
    baseline = directory / "baseline.json"
    baseline.write_text(json.dumps(record))
    candidate = directory / "latest.json"
    record.update(baseline_sha256=sha256(baseline), status="pass", differences=[])
    candidate.write_text(json.dumps(record))
    return tmp_path, candidate


def test_current_evidence_passes(evidence):
    root, _ = evidence
    validate_evidence(root)


@pytest.mark.parametrize(
    "change", ["source", "dirty", "baseline", "predictions", "dependency", "fixture"]
)
def test_stale_or_modified_evidence_fails(evidence, change):
    root, path = evidence
    candidate = json.loads(path.read_text())
    if change == "source":
        candidate["runtime"]["source_sha256"] = "d" * 64
    elif change == "dirty":
        candidate["runtime"]["source_dirty"] = True
    elif change == "baseline":
        candidate["baseline_sha256"] = "d" * 64
    elif change == "predictions":
        candidate["frames"]["image.png:0"]["detections"] = []
    elif change == "dependency":
        candidate["runtime"]["dependencies"]["pydantic"] = "1.0"
    else:
        (root / DATA / "fixtures/image.png").write_bytes(b"modified")
    path.write_text(json.dumps(candidate))
    with pytest.raises(ValueError):
        validate_evidence(root)


def test_dependency_pr_cannot_replace_baseline(evidence, monkeypatch):
    root, _ = evidence
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "Dockerfile\n")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, b"previous baseline"),
    )
    with pytest.raises(ValueError, match="separate baseline PR"):
        check_base(root, "main")


def test_non_runtime_pr_does_not_require_new_inference(evidence, monkeypatch):
    root, _ = evidence
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "README.md\n")
    assert check_base(root, "main") is False


def test_manifest_exports_only_public_identity(monkeypatch):
    responses = iter(
        [
            [
                {
                    "State": {"Running": True},
                    "Id": "abc",
                    "Image": "sha256:def",
                    "Config": {"Env": ["SECRET=password"]},
                }
            ],
            {"schema_version": 1},
            [{"Id": "sha256:def", "RepoDigests": []}],
        ]
    )
    monkeypatch.setattr(
        "scripts.export_runtime_manifest.docker_json", lambda *args: next(responses)
    )
    manifest = export_manifest("backend")
    assert manifest["image_id"] == "sha256:def"
    assert "SECRET" not in json.dumps(manifest)
