import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import BASE_DIR, RUNTIME_MODEL_PROFILE_PATH

PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
DEVICE_PATTERN = re.compile(r"^(?:cpu|cuda(?::\d+)?)$")
PROJECT_CLASSES = {
    "person",
    "bicycle",
    "motorcycle",
    "car_or_van",
    "bus",
    "truck",
}
NUMERIC_PRECISIONS = {"float16", "float32"}
QUALITY_GATE_STATUSES = {"not_evaluated", "conditional", "passed", "failed"}
HASH_CHUNK_SIZE = 1024 * 1024


class ModelProfileError(ValueError):
    """Raised when a runtime model profile is incomplete or invalid."""


class CheckpointVerificationError(RuntimeError):
    """Raised when configured model weights are missing or have changed."""


@dataclass(frozen=True)
class RuntimeModelProfile:
    profile_id: str
    model_id: str
    quality_gate_status: str
    evaluation_reference: Path
    checkpoint_path: Path
    checkpoint_sha256: str
    checkpoint_size_bytes: int
    class_mapping: tuple[tuple[str, str], ...]
    confidence: float
    image_size: int
    scale_factor: int
    device: str
    max_detections: int
    numeric_precision: str

    def resolve_checkpoint_path(self, repository_root: Path = BASE_DIR) -> Path:
        return repository_root / self.checkpoint_path

    def class_mapping_dict(self) -> dict[str, str]:
        return dict(self.class_mapping)

    @property
    def half_precision(self) -> bool:
        return self.numeric_precision == "float16"


def load_runtime_model_profile(
    path: Path = RUNTIME_MODEL_PROFILE_PATH,
) -> RuntimeModelProfile:
    path = Path(path)
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ModelProfileError(f"Runtime model profile not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ModelProfileError(
            f"Runtime model profile is not valid JSON: {path}"
        ) from error

    root = _object(values, "profile")
    _fields(
        root,
        "profile",
        {
            "schema_version",
            "profile_id",
            "model_id",
            "quality_gate_status",
            "evaluation_reference",
            "checkpoint",
            "class_mapping",
            "inference",
        },
    )
    if _integer(root["schema_version"], "schema_version", minimum=1) != 1:
        raise ModelProfileError("schema_version must be 1")

    checkpoint = _object(root["checkpoint"], "checkpoint")
    _fields(checkpoint, "checkpoint", {"path", "sha256", "size_bytes"})
    inference = _object(root["inference"], "inference")
    _fields(
        inference,
        "inference",
        {
            "confidence",
            "image_size",
            "scale_factor",
            "device",
            "max_detections",
            "numeric_precision",
        },
    )

    profile_id = _identifier(root["profile_id"], "profile_id")
    model_id = _identifier(root["model_id"], "model_id")
    quality_gate_status = _string(root["quality_gate_status"], "quality_gate_status")
    if quality_gate_status not in QUALITY_GATE_STATUSES:
        raise ModelProfileError(
            "quality_gate_status must be not_evaluated, conditional, passed, or failed"
        )

    checkpoint_sha256 = _string(checkpoint["sha256"], "checkpoint.sha256")
    if not SHA256_PATTERN.fullmatch(checkpoint_sha256):
        raise ModelProfileError("checkpoint.sha256 must be a lowercase SHA-256 digest")

    mapping = _class_mapping(root["class_mapping"])
    confidence = _number(inference["confidence"], "inference.confidence")
    if confidence <= 0 or confidence > 1:
        raise ModelProfileError(
            "inference.confidence must be greater than 0 and at most 1"
        )

    numeric_precision = _string(
        inference["numeric_precision"], "inference.numeric_precision"
    )
    if numeric_precision not in NUMERIC_PRECISIONS:
        raise ModelProfileError(
            "inference.numeric_precision must be float16 or float32"
        )

    device = _string(inference["device"], "inference.device")
    if not DEVICE_PATTERN.fullmatch(device):
        raise ModelProfileError("inference.device must be cpu, cuda, or cuda:<index>")

    return RuntimeModelProfile(
        profile_id=profile_id,
        model_id=model_id,
        quality_gate_status=quality_gate_status,
        evaluation_reference=_relative_path(
            root["evaluation_reference"], "evaluation_reference"
        ),
        checkpoint_path=_relative_path(checkpoint["path"], "checkpoint.path"),
        checkpoint_sha256=checkpoint_sha256,
        checkpoint_size_bytes=_integer(
            checkpoint["size_bytes"], "checkpoint.size_bytes", minimum=1
        ),
        class_mapping=mapping,
        confidence=confidence,
        image_size=_integer(inference["image_size"], "inference.image_size", minimum=1),
        scale_factor=_integer(
            inference["scale_factor"], "inference.scale_factor", minimum=1
        ),
        device=device,
        max_detections=_integer(
            inference["max_detections"], "inference.max_detections", minimum=1
        ),
        numeric_precision=numeric_precision,
    )


def verify_runtime_checkpoint(
    profile: RuntimeModelProfile,
    repository_root: Path = BASE_DIR,
) -> Path:
    checkpoint_path = profile.resolve_checkpoint_path(repository_root)
    try:
        size_bytes = checkpoint_path.stat().st_size
    except FileNotFoundError as error:
        raise CheckpointVerificationError(
            f"Runtime checkpoint not found: {checkpoint_path}"
        ) from error

    if size_bytes != profile.checkpoint_size_bytes:
        raise CheckpointVerificationError(
            f"Runtime checkpoint size mismatch for {profile.model_id}: "
            f"expected {profile.checkpoint_size_bytes}, found {size_bytes}"
        )

    digest = hashlib.sha256()
    with checkpoint_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != profile.checkpoint_sha256:
        raise CheckpointVerificationError(
            f"Runtime checkpoint SHA-256 mismatch for {profile.model_id}: "
            f"expected {profile.checkpoint_sha256}, found {actual_sha256}"
        )
    return checkpoint_path


def _fields(values: dict[str, Any], field: str, required: set[str]) -> None:
    missing = required - set(values)
    unknown = set(values) - required
    if missing:
        raise ModelProfileError(
            f"{field} is missing required fields: {', '.join(sorted(missing))}"
        )
    if unknown:
        raise ModelProfileError(
            f"{field} contains unknown fields: {', '.join(sorted(unknown))}"
        )


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelProfileError(f"{field} must be a JSON object")
    return value


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelProfileError(f"{field} must be a non-empty string")
    return value


def _identifier(value: Any, field: str) -> str:
    identifier = _string(value, field)
    if not PROFILE_ID_PATTERN.fullmatch(identifier):
        raise ModelProfileError(
            f"{field} must contain lowercase words separated by hyphens"
        )
    return identifier


def _integer(value: Any, field: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ModelProfileError(f"{field} must be an integer >= {minimum}")
    return value


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelProfileError(f"{field} must be a number")
    return float(value)


def _relative_path(value: Any, field: str) -> Path:
    path = Path(_string(value, field))
    if path.is_absolute() or ".." in path.parts:
        raise ModelProfileError(f"{field} must be relative to the repository")
    return path


def _class_mapping(value: Any) -> tuple[tuple[str, str], ...]:
    mapping = _object(value, "class_mapping")
    if not mapping:
        raise ModelProfileError("class_mapping must not be empty")

    entries = []
    for source_class, project_class in mapping.items():
        source_class = _string(source_class, "class_mapping source class")
        project_class = _string(project_class, f"class_mapping.{source_class}")
        if project_class not in PROJECT_CLASSES:
            raise ModelProfileError(
                f"class_mapping.{source_class} has unknown project class "
                f"{project_class!r}"
            )
        entries.append((source_class, project_class))

    mapped_classes = {project_class for _, project_class in entries}
    if mapped_classes != PROJECT_CLASSES:
        missing = ", ".join(sorted(PROJECT_CLASSES - mapped_classes))
        raise ModelProfileError(
            f"class_mapping does not cover project classes: {missing}"
        )
    return tuple(sorted(entries))
