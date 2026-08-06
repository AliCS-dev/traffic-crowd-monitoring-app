import hashlib
import io
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from evaluation.model_candidates import load_model_candidate_selection
from evaluation.model_preflight import (
    ModelPreflightError,
    candidate_checkpoint_path,
    download_checkpoint,
    inspect_candidate,
    source_class_names,
    verify_checkpoint,
)

CONFIG_PATH = Path("configs/evaluation/aerial_model_candidates.json")


class DownloadResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def candidate_with_identity(content: bytes):
    candidate = load_model_candidate_selection(CONFIG_PATH).candidates[0]
    return replace(
        candidate,
        weights_size_bytes=len(content),
        weights_sha256=hashlib.sha256(content).hexdigest(),
    )


def test_candidate_checkpoints_use_separate_directories():
    candidates = load_model_candidate_selection(CONFIG_PATH).candidates

    paths = [candidate_checkpoint_path(Path("models"), item) for item in candidates]

    assert paths == [
        Path("models/yolo26m-visdrone/best.pt"),
        Path("models/yolo11x-visdrone/best.pt"),
    ]


def test_checkpoint_identity_is_verified(tmp_path):
    content = b"verified checkpoint"
    candidate = candidate_with_identity(content)
    path = tmp_path / "best.pt"
    path.write_bytes(content)

    identity = verify_checkpoint(path, candidate)

    assert identity.size_bytes == len(content)
    assert identity.sha256 == hashlib.sha256(content).hexdigest()


def test_checkpoint_hash_mismatch_is_rejected(tmp_path):
    candidate = candidate_with_identity(b"expected checkpoint")
    path = tmp_path / "best.pt"
    path.write_bytes(b"modified checkpoint")

    with pytest.raises(ModelPreflightError, match="size mismatch|SHA-256 mismatch"):
        verify_checkpoint(path, candidate)


def test_download_uses_pinned_url_and_moves_verified_file(tmp_path):
    content = b"downloaded checkpoint"
    candidate = candidate_with_identity(content)
    calls = []

    def opener(url, timeout):
        calls.append((url, timeout))
        return DownloadResponse(content)

    destination = tmp_path / "candidate" / "best.pt"
    identity = download_checkpoint(candidate, destination, opener=opener)

    assert calls == [(candidate.weights_url, 120.0)]
    assert destination.read_bytes() == content
    assert not destination.with_name("best.pt.part").exists()
    assert identity.sha256 == candidate.weights_sha256


def test_failed_download_removes_partial_file(tmp_path):
    candidate = candidate_with_identity(b"expected checkpoint")
    destination = tmp_path / "candidate" / "best.pt"

    def opener(_url, _timeout):
        return DownloadResponse(b"wrong")

    with pytest.raises(ModelPreflightError, match="size mismatch"):
        download_checkpoint(candidate, destination, opener=opener)

    assert not destination.exists()
    assert not destination.with_name("best.pt.part").exists()


def test_source_names_require_consecutive_ids():
    model = SimpleNamespace(names={0: "pedestrian", 2: "bicycle"})

    with pytest.raises(ModelPreflightError, match="consecutive"):
        source_class_names(model)


def test_candidate_load_and_inference_preflight(tmp_path):
    content = b"verified checkpoint"
    candidate = candidate_with_identity(content)
    checkpoint = tmp_path / "best.pt"
    image = tmp_path / "validation.jpg"
    checkpoint.write_bytes(content)
    image.write_bytes(b"validation image")

    class FakeModel:
        task = "detect"
        names = dict(enumerate(candidate.source_classes))

        def predict(self, **options):
            assert options["source"] == str(image)
            assert options["device"] == "cuda:0"
            return [SimpleNamespace(boxes=[])]

    result = inspect_candidate(
        candidate=candidate,
        checkpoint_path=checkpoint,
        validation_asset_id="validation-asset",
        validation_image_path=image,
        device="cuda:0",
        image_size=1280,
        confidence=0.25,
        max_detections=300,
        model_factory=lambda _path: FakeModel(),
    )

    assert result.model_task == "detect"
    assert result.source_classes == candidate.source_classes
    assert result.validation_asset_id == "validation-asset"
