import hashlib
import json
import platform
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO
from urllib.request import Request, urlopen

from evaluation.model_candidates import ModelCandidate, ModelCandidateSelection

DOWNLOAD_CHUNK_SIZE = 1024 * 1024


class ModelPreflightError(RuntimeError):
    """Raised when a candidate checkpoint fails a preflight requirement."""


@dataclass(frozen=True)
class CheckpointIdentity:
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class CandidatePreflightResult:
    candidate_id: str
    repository_id: str
    repository_revision: str
    checkpoint_path: Path
    checkpoint_identity: CheckpointIdentity
    model_task: str
    source_classes: tuple[str, ...]
    validation_asset_id: str
    validation_image_sha256: str
    device: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "repository_id": self.repository_id,
            "repository_revision": self.repository_revision,
            "checkpoint_path": self.checkpoint_path.as_posix(),
            "checkpoint_size_bytes": self.checkpoint_identity.size_bytes,
            "checkpoint_sha256": self.checkpoint_identity.sha256,
            "model_task": self.model_task,
            "source_classes": list(self.source_classes),
            "validation_asset_id": self.validation_asset_id,
            "validation_image_sha256": self.validation_image_sha256,
            "device": self.device,
            "status": "passed",
        }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(DOWNLOAD_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint_identity(path: Path) -> CheckpointIdentity:
    try:
        size_bytes = path.stat().st_size
    except FileNotFoundError as error:
        raise ModelPreflightError(f"Checkpoint not found: {path}") from error
    return CheckpointIdentity(size_bytes=size_bytes, sha256=sha256(path))


def candidate_checkpoint_path(
    models_directory: Path, candidate: ModelCandidate
) -> Path:
    return models_directory / candidate.candidate_id / candidate.weights_filename


def verify_checkpoint(path: Path, candidate: ModelCandidate) -> CheckpointIdentity:
    identity = checkpoint_identity(path)
    if identity.size_bytes != candidate.weights_size_bytes:
        raise ModelPreflightError(
            f"Checkpoint size mismatch for {candidate.candidate_id}: "
            f"expected {candidate.weights_size_bytes}, found {identity.size_bytes}"
        )
    if identity.sha256 != candidate.weights_sha256:
        raise ModelPreflightError(
            f"Checkpoint SHA-256 mismatch for {candidate.candidate_id}: "
            f"expected {candidate.weights_sha256}, found {identity.sha256}"
        )
    return identity


def _open_download(url: str, timeout_seconds: float) -> BinaryIO:
    request = Request(url, headers={"User-Agent": "traffic-monitoring-thesis/1.0"})
    return urlopen(request, timeout=timeout_seconds)


def download_checkpoint(
    candidate: ModelCandidate,
    destination: Path,
    *,
    timeout_seconds: float = 120.0,
    opener: Callable[[str, float], BinaryIO] = _open_download,
) -> CheckpointIdentity:
    if destination.exists():
        return verify_checkpoint(destination, candidate)

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial_path = destination.with_name(f"{destination.name}.part")
    partial_path.unlink(missing_ok=True)
    try:
        with opener(candidate.weights_url, timeout_seconds) as response:
            with partial_path.open("wb") as output:
                while chunk := response.read(DOWNLOAD_CHUNK_SIZE):
                    output.write(chunk)
        identity = verify_checkpoint(partial_path, candidate)
        partial_path.replace(destination)
        return identity
    except Exception:
        partial_path.unlink(missing_ok=True)
        raise


def source_class_names(model: Any) -> tuple[str, ...]:
    names = model.names
    if isinstance(names, dict):
        try:
            class_ids = sorted(names)
            expected_ids = list(range(len(names)))
            if class_ids != expected_ids:
                raise ModelPreflightError(
                    "Model class IDs must be consecutive and start at zero"
                )
            return tuple(str(names[class_id]) for class_id in class_ids)
        except TypeError as error:
            raise ModelPreflightError("Model class IDs must be integers") from error
    if isinstance(names, (list, tuple)):
        return tuple(str(name) for name in names)
    raise ModelPreflightError("Model class names are unavailable or invalid")


def inspect_candidate(
    *,
    candidate: ModelCandidate,
    checkpoint_path: Path,
    validation_asset_id: str,
    validation_image_path: Path,
    device: str,
    image_size: int,
    confidence: float,
    max_detections: int,
    model_factory: Callable[[str], Any] | None = None,
) -> CandidatePreflightResult:
    identity = verify_checkpoint(checkpoint_path, candidate)
    if not validation_image_path.is_file():
        raise ModelPreflightError(
            f"Validation image not found: {validation_image_path}"
        )

    if model_factory is None:
        from ultralytics import YOLO

        model_factory = YOLO

    model = model_factory(str(checkpoint_path))
    model_task = str(getattr(model, "task", ""))
    if model_task != "detect":
        raise ModelPreflightError(
            f"Candidate {candidate.candidate_id} has task {model_task!r}, not 'detect'"
        )

    class_names = source_class_names(model)
    if class_names != candidate.source_classes:
        raise ModelPreflightError(
            f"Candidate {candidate.candidate_id} has unexpected source classes: "
            f"{', '.join(class_names)}"
        )

    results = model.predict(
        source=str(validation_image_path),
        conf=confidence,
        imgsz=image_size,
        device=device,
        max_det=max_detections,
        verbose=False,
    )
    if not isinstance(results, list) or len(results) != 1:
        raise ModelPreflightError(
            f"Candidate {candidate.candidate_id} did not return one image result"
        )
    if getattr(results[0], "boxes", None) is None:
        raise ModelPreflightError(
            f"Candidate {candidate.candidate_id} returned no detection container"
        )

    return CandidatePreflightResult(
        candidate_id=candidate.candidate_id,
        repository_id=candidate.repository_id,
        repository_revision=candidate.repository_revision,
        checkpoint_path=checkpoint_path,
        checkpoint_identity=identity,
        model_task=model_task,
        source_classes=class_names,
        validation_asset_id=validation_asset_id,
        validation_image_sha256=sha256(validation_image_path),
        device=device,
    )


def build_preflight_report(
    *,
    selection: ModelCandidateSelection,
    selection_path: Path,
    results: list[CandidatePreflightResult],
    torch_version: str,
    ultralytics_version: str,
    cuda_available: bool,
    cuda_device_name: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "performed_at": datetime.now(timezone.utc).isoformat(),
        "selection_name": selection.selection_name,
        "selection_path": selection_path.as_posix(),
        "selection_sha256": sha256(selection_path),
        "protocol_version": selection.protocol_version,
        "environment": {
            "python_version": platform.python_version(),
            "torch_version": torch_version,
            "ultralytics_version": ultralytics_version,
            "cuda_available": cuda_available,
            "cuda_device_name": cuda_device_name,
        },
        "candidates": [result.as_dict() for result in results],
        "status": "passed",
    }


def write_preflight_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
