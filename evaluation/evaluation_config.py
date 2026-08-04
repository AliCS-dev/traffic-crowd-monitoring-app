import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROJECT_CLASSES = (
    "person",
    "bicycle",
    "motorcycle",
    "car_or_van",
    "bus",
    "truck",
)
DATASET_ROLES = ("training", "validation", "held_out_test")
NUMERIC_PRECISIONS = ("float16", "float32")
RUN_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class EvaluationConfigError(ValueError):
    """Raised when an evaluation configuration is incomplete or inconsistent."""


@dataclass(frozen=True)
class ClassMapping:
    entries: tuple[tuple[str, str], ...]

    @classmethod
    def from_dict(cls, values: dict[str, str]) -> "ClassMapping":
        if not values:
            raise EvaluationConfigError("model.class_mapping must not be empty")

        entries = []
        for source_class, project_class in values.items():
            if not isinstance(source_class, str) or not source_class.strip():
                raise EvaluationConfigError(
                    "model.class_mapping source labels must be non-empty strings"
                )
            if project_class not in PROJECT_CLASSES:
                raise EvaluationConfigError(
                    "model.class_mapping contains an unknown project class: "
                    f"{project_class!r}"
                )
            entries.append((source_class, project_class))

        return cls(tuple(sorted(entries)))

    def map(self, source_class: str) -> str | None:
        return dict(self.entries).get(source_class)

    def as_dict(self) -> dict[str, str]:
        return dict(self.entries)


@dataclass(frozen=True)
class DatasetSettings:
    version: str
    role: str
    manifest_path: Path


@dataclass(frozen=True)
class ModelSettings:
    name: str
    task: str
    weights_path: Path
    source_url: str
    license_id: str
    license_url: str
    class_mapping: ClassMapping


@dataclass(frozen=True)
class InferenceSettings:
    confidence_floor: float
    operating_confidence: float
    image_size: int
    scale_factor: int
    device: str
    max_detections: int
    batch_size: int
    numeric_precision: str


@dataclass(frozen=True)
class MetricSettings:
    operating_iou: float
    low_support_threshold: int


@dataclass(frozen=True)
class TimingSettings:
    warmup_frames: int
    measured_frames: int
    repetitions: int


@dataclass(frozen=True)
class EvaluationConfig:
    schema_version: int
    run_name: str
    protocol_version: str
    random_seed: int
    dataset: DatasetSettings
    model: ModelSettings
    inference: InferenceSettings
    metrics: MetricSettings
    timing: TimingSettings
    output_directory: Path

    def resolve_path(self, repository_root: Path, path: Path) -> Path:
        if path.is_absolute():
            return path
        return repository_root / path


def _require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvaluationConfigError(f"{field} must be a JSON object")
    return value


def _require_fields(values: dict[str, Any], field: str, required: set[str]) -> None:
    missing = required - set(values)
    unknown = set(values) - required
    if missing:
        raise EvaluationConfigError(
            f"{field} is missing required fields: {', '.join(sorted(missing))}"
        )
    if unknown:
        raise EvaluationConfigError(
            f"{field} contains unknown fields: {', '.join(sorted(unknown))}"
        )


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationConfigError(f"{field} must be a non-empty string")
    return value


def _require_integer(value: Any, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise EvaluationConfigError(f"{field} must be an integer >= {minimum}")
    return value


def _require_probability(value: Any, field: str, *, allow_zero: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationConfigError(f"{field} must be a number between 0 and 1")
    number = float(value)
    lower_bound = 0 if allow_zero else 0.0
    if number < lower_bound or number > 1 or (not allow_zero and number == 0):
        raise EvaluationConfigError(f"{field} must be a number between 0 and 1")
    return number


def _require_relative_path(value: Any, field: str) -> Path:
    path = Path(_require_string(value, field))
    if path.is_absolute() or ".." in path.parts:
        raise EvaluationConfigError(f"{field} must be relative to the repository")
    return path


def _require_url(value: Any, field: str) -> str:
    url = _require_string(value, field)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise EvaluationConfigError(f"{field} must be a valid HTTPS URL")
    return url


def _parse_dataset(values: dict[str, Any]) -> DatasetSettings:
    required = {"version", "role", "manifest_path"}
    _require_fields(values, "dataset", required)
    role = _require_string(values["role"], "dataset.role")
    if role not in DATASET_ROLES:
        raise EvaluationConfigError(
            f"dataset.role must be one of: {', '.join(DATASET_ROLES)}"
        )
    return DatasetSettings(
        version=_require_string(values["version"], "dataset.version"),
        role=role,
        manifest_path=_require_relative_path(
            values["manifest_path"], "dataset.manifest_path"
        ),
    )


def _parse_model(values: dict[str, Any]) -> ModelSettings:
    required = {
        "name",
        "task",
        "weights_path",
        "source_url",
        "license_id",
        "license_url",
        "class_mapping",
    }
    _require_fields(values, "model", required)
    task = _require_string(values["task"], "model.task")
    if task != "detection":
        raise EvaluationConfigError("model.task must be 'detection'")
    mapping = _require_object(values["class_mapping"], "model.class_mapping")
    return ModelSettings(
        name=_require_string(values["name"], "model.name"),
        task=task,
        weights_path=_require_relative_path(
            values["weights_path"], "model.weights_path"
        ),
        source_url=_require_url(values["source_url"], "model.source_url"),
        license_id=_require_string(values["license_id"], "model.license_id"),
        license_url=_require_url(values["license_url"], "model.license_url"),
        class_mapping=ClassMapping.from_dict(mapping),
    )


def _parse_inference(values: dict[str, Any]) -> InferenceSettings:
    required = {
        "confidence_floor",
        "operating_confidence",
        "image_size",
        "scale_factor",
        "device",
        "max_detections",
        "batch_size",
        "numeric_precision",
    }
    _require_fields(values, "inference", required)
    confidence_floor = _require_probability(
        values["confidence_floor"], "inference.confidence_floor", allow_zero=False
    )
    operating_confidence = _require_probability(
        values["operating_confidence"], "inference.operating_confidence"
    )
    if confidence_floor > operating_confidence:
        raise EvaluationConfigError(
            "inference.confidence_floor must not exceed operating_confidence"
        )
    batch_size = _require_integer(values["batch_size"], "inference.batch_size", 1)
    if batch_size != 1:
        raise EvaluationConfigError("inference.batch_size must be 1 for this protocol")
    numeric_precision = _require_string(
        values["numeric_precision"], "inference.numeric_precision"
    )
    if numeric_precision not in NUMERIC_PRECISIONS:
        raise EvaluationConfigError(
            "inference.numeric_precision must be one of: "
            f"{', '.join(NUMERIC_PRECISIONS)}"
        )
    return InferenceSettings(
        confidence_floor=confidence_floor,
        operating_confidence=operating_confidence,
        image_size=_require_integer(values["image_size"], "inference.image_size", 1),
        scale_factor=_require_integer(
            values["scale_factor"], "inference.scale_factor", 1
        ),
        device=_require_string(values["device"], "inference.device"),
        max_detections=_require_integer(
            values["max_detections"], "inference.max_detections", 1
        ),
        batch_size=batch_size,
        numeric_precision=numeric_precision,
    )


def _parse_metrics(values: dict[str, Any]) -> MetricSettings:
    required = {"operating_iou", "low_support_threshold"}
    _require_fields(values, "metrics", required)
    return MetricSettings(
        operating_iou=_require_probability(
            values["operating_iou"], "metrics.operating_iou", allow_zero=False
        ),
        low_support_threshold=_require_integer(
            values["low_support_threshold"], "metrics.low_support_threshold", 1
        ),
    )


def _parse_timing(values: dict[str, Any]) -> TimingSettings:
    required = {"warmup_frames", "measured_frames", "repetitions"}
    _require_fields(values, "timing", required)
    return TimingSettings(
        warmup_frames=_require_integer(values["warmup_frames"], "timing.warmup_frames"),
        measured_frames=_require_integer(
            values["measured_frames"], "timing.measured_frames", 1
        ),
        repetitions=_require_integer(values["repetitions"], "timing.repetitions", 1),
    )


def parse_evaluation_config(values: dict[str, Any]) -> EvaluationConfig:
    required = {
        "schema_version",
        "run_name",
        "protocol_version",
        "random_seed",
        "dataset",
        "model",
        "inference",
        "metrics",
        "timing",
        "output_directory",
    }
    _require_fields(values, "configuration", required)
    schema_version = _require_integer(values["schema_version"], "schema_version", 1)
    if schema_version != 1:
        raise EvaluationConfigError("schema_version must be 1")
    run_name = _require_string(values["run_name"], "run_name")
    if not RUN_NAME_PATTERN.fullmatch(run_name):
        raise EvaluationConfigError(
            "run_name must contain lowercase words separated by hyphens"
        )

    return EvaluationConfig(
        schema_version=schema_version,
        run_name=run_name,
        protocol_version=_require_string(
            values["protocol_version"], "protocol_version"
        ),
        random_seed=_require_integer(values["random_seed"], "random_seed"),
        dataset=_parse_dataset(_require_object(values["dataset"], "dataset")),
        model=_parse_model(_require_object(values["model"], "model")),
        inference=_parse_inference(_require_object(values["inference"], "inference")),
        metrics=_parse_metrics(_require_object(values["metrics"], "metrics")),
        timing=_parse_timing(_require_object(values["timing"], "timing")),
        output_directory=_require_relative_path(
            values["output_directory"], "output_directory"
        ),
    )


def load_evaluation_config(path: Path) -> EvaluationConfig:
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise EvaluationConfigError(f"Configuration file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise EvaluationConfigError(
            f"Configuration file is not valid JSON: {path}: {error.msg}"
        ) from error

    return parse_evaluation_config(_require_object(values, "configuration"))
