import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.config import BASE_DIR, RUNTIME_MODEL_PROFILE_PATH
from app.model_profile import (
    CheckpointVerificationError,
    ModelProfileError,
    load_runtime_model_profile,
    verify_runtime_checkpoint,
)


def tracked_profile_values():
    return json.loads(RUNTIME_MODEL_PROFILE_PATH.read_text(encoding="utf-8"))


def write_profile(tmp_path, values):
    path = tmp_path / "runtime_profile.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    return path


def test_tracked_runtime_profile_matches_frozen_evaluation_selection():
    profile = load_runtime_model_profile()
    selection = json.loads(
        (BASE_DIR / profile.evaluation_reference).read_text(encoding="utf-8")
    )

    assert profile.model_id == selection["selected_candidate_id"]
    assert profile.checkpoint_path.as_posix() == selection["checkpoint"]["path"]
    assert profile.checkpoint_sha256 == selection["checkpoint"]["sha256"]
    assert profile.checkpoint_size_bytes == selection["checkpoint"]["size_bytes"]
    assert profile.class_mapping_dict() == selection["class_mapping"]
    assert profile.confidence == selection["inference"]["operating_confidence"]
    assert profile.image_size == selection["inference"]["image_size"]
    assert profile.scale_factor == selection["inference"]["scale_factor"]
    assert profile.device == selection["inference"]["device"]
    assert profile.max_detections == selection["inference"]["max_detections"]
    assert profile.numeric_precision == selection["inference"]["numeric_precision"]
    assert profile.quality_gate_status == "failed"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda values: values.update({"unexpected": True}), "unknown fields"),
        (lambda values: values.pop("model_id"), "missing required fields"),
        (
            lambda values: values["checkpoint"].update({"sha256": "invalid"}),
            "lowercase SHA-256",
        ),
        (
            lambda values: values["inference"].update({"device": "automatic"}),
            "must be cpu, cuda",
        ),
        (
            lambda values: values["class_mapping"].pop("motor"),
            "does not cover project classes",
        ),
    ],
)
def test_invalid_runtime_profile_is_rejected(tmp_path, change, message):
    values = tracked_profile_values()
    change(values)

    with pytest.raises(ModelProfileError, match=message):
        load_runtime_model_profile(write_profile(tmp_path, values))


def test_missing_runtime_checkpoint_is_rejected(tmp_path):
    profile = replace(
        load_runtime_model_profile(),
        checkpoint_path=Path("missing.pt"),
    )

    with pytest.raises(CheckpointVerificationError, match="not found"):
        verify_runtime_checkpoint(profile, tmp_path)


def test_runtime_checkpoint_size_mismatch_is_rejected(tmp_path):
    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"different size")
    profile = replace(
        load_runtime_model_profile(),
        checkpoint_path=checkpoint.relative_to(tmp_path),
    )

    with pytest.raises(CheckpointVerificationError, match="size mismatch"):
        verify_runtime_checkpoint(profile, tmp_path)


def test_runtime_checkpoint_hash_mismatch_is_rejected(tmp_path):
    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"same-size-wrong")
    profile = replace(
        load_runtime_model_profile(),
        checkpoint_path=checkpoint.relative_to(tmp_path),
        checkpoint_size_bytes=checkpoint.stat().st_size,
    )

    with pytest.raises(CheckpointVerificationError, match="SHA-256 mismatch"):
        verify_runtime_checkpoint(profile, tmp_path)


def test_valid_runtime_checkpoint_returns_resolved_path(tmp_path):
    checkpoint = tmp_path / "model.pt"
    content = b"verified runtime checkpoint"
    checkpoint.write_bytes(content)
    profile = replace(
        load_runtime_model_profile(),
        checkpoint_path=checkpoint.relative_to(tmp_path),
        checkpoint_size_bytes=len(content),
        checkpoint_sha256=hashlib.sha256(content).hexdigest(),
    )

    assert verify_runtime_checkpoint(profile, tmp_path) == checkpoint
