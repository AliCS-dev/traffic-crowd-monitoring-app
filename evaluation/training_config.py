import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RUN_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class TrainingConfigError(ValueError):
    """Raised when a fine-tuning configuration is invalid."""


@dataclass(frozen=True)
class TrainingDatasetSettings:
    selection_plan_path: Path
    validation_annotations_path: Path
    output_directory: Path
    collection_id: str
    role: str
    frame_stride: int


@dataclass(frozen=True)
class TrainingSettings:
    epochs: int
    patience: int
    image_size: int
    batch_size: int
    device: str
    workers: int
    freeze_layers: int
    optimizer: str
    learning_rate: float
    amp: bool
    cache: bool


@dataclass(frozen=True)
class FineTuningConfig:
    schema_version: int
    run_name: str
    random_seed: int
    base_checkpoint: Path
    base_checkpoint_sha256: str
    source_classes: tuple[str, ...]
    project_class_mapping: tuple[tuple[str, str], ...]
    dataset: TrainingDatasetSettings
    training: TrainingSettings
    output_directory: Path
    config_sha256: str

    def source_class_ids(self) -> dict[str, int]:
        return {name: class_id for class_id, name in enumerate(self.source_classes)}

    def mapped_class_ids(self) -> dict[str, int]:
        source_ids = self.source_class_ids()
        return {
            project_name: source_ids[source_name]
            for project_name, source_name in self.project_class_mapping
        }


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TrainingConfigError(f"{field} must be a JSON object")
    return value


def _fields(values: dict[str, Any], field: str, expected: set[str]) -> None:
    missing = expected - set(values)
    unknown = set(values) - expected
    if missing:
        raise TrainingConfigError(
            f"{field} is missing fields: {', '.join(sorted(missing))}"
        )
    if unknown:
        raise TrainingConfigError(
            f"{field} contains unknown fields: {', '.join(sorted(unknown))}"
        )


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrainingConfigError(f"{field} must be a non-empty string")
    return value


def _integer(value: Any, field: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise TrainingConfigError(f"{field} must be an integer >= {minimum}")
    return value


def _relative_path(value: Any, field: str) -> Path:
    path = Path(_string(value, field))
    if path.is_absolute() or ".." in path.parts:
        raise TrainingConfigError(f"{field} must be relative to the repository")
    return path


def _derived_output_path(value: Any, field: str) -> Path:
    path = _relative_path(value, field)
    if path.parts[:3] != ("data", "evaluation", "derived") or len(path.parts) < 4:
        raise TrainingConfigError(f"{field} must be a child of data/evaluation/derived")
    return path


def _parse_dataset(value: Any) -> TrainingDatasetSettings:
    values = _object(value, "dataset")
    expected = {
        "selection_plan_path",
        "validation_annotations_path",
        "output_directory",
        "collection_id",
        "role",
        "frame_stride",
    }
    _fields(values, "dataset", expected)
    role = _string(values["role"], "dataset.role")
    if role != "training":
        raise TrainingConfigError("dataset.role must be 'training'")
    return TrainingDatasetSettings(
        selection_plan_path=_relative_path(
            values["selection_plan_path"], "dataset.selection_plan_path"
        ),
        validation_annotations_path=_relative_path(
            values["validation_annotations_path"],
            "dataset.validation_annotations_path",
        ),
        output_directory=_derived_output_path(
            values["output_directory"], "dataset.output_directory"
        ),
        collection_id=_string(values["collection_id"], "dataset.collection_id"),
        role=role,
        frame_stride=_integer(values["frame_stride"], "dataset.frame_stride", 1),
    )


def _parse_training(value: Any) -> TrainingSettings:
    values = _object(value, "training")
    expected = {
        "epochs",
        "patience",
        "image_size",
        "batch_size",
        "device",
        "workers",
        "freeze_layers",
        "optimizer",
        "learning_rate",
        "amp",
        "cache",
    }
    _fields(values, "training", expected)
    learning_rate = values["learning_rate"]
    if (
        isinstance(learning_rate, bool)
        or not isinstance(learning_rate, (int, float))
        or not 0 < float(learning_rate) <= 1
    ):
        raise TrainingConfigError("training.learning_rate must be in (0, 1]")
    amp = values["amp"]
    if not isinstance(amp, bool):
        raise TrainingConfigError("training.amp must be a boolean")
    cache = values["cache"]
    if not isinstance(cache, bool):
        raise TrainingConfigError("training.cache must be a boolean")
    return TrainingSettings(
        epochs=_integer(values["epochs"], "training.epochs", 1),
        patience=_integer(values["patience"], "training.patience", 0),
        image_size=_integer(values["image_size"], "training.image_size", 32),
        batch_size=_integer(values["batch_size"], "training.batch_size", 1),
        device=_string(values["device"], "training.device"),
        workers=_integer(values["workers"], "training.workers", 0),
        freeze_layers=_integer(values["freeze_layers"], "training.freeze_layers", 0),
        optimizer=_string(values["optimizer"], "training.optimizer"),
        learning_rate=float(learning_rate),
        amp=amp,
        cache=cache,
    )


def load_training_config(path: Path) -> FineTuningConfig:
    raw = path.read_bytes()
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as error:
        raise TrainingConfigError(f"Invalid JSON in {path}: {error}") from error
    values = _object(values, "config")
    expected = {
        "schema_version",
        "run_name",
        "random_seed",
        "base_checkpoint",
        "base_checkpoint_sha256",
        "source_classes",
        "project_class_mapping",
        "dataset",
        "training",
        "output_directory",
    }
    _fields(values, "config", expected)

    run_name = _string(values["run_name"], "run_name")
    if not RUN_NAME_PATTERN.fullmatch(run_name):
        raise TrainingConfigError("run_name must use lowercase kebab-case")

    source_classes_value = values["source_classes"]
    if not isinstance(source_classes_value, list) or not source_classes_value:
        raise TrainingConfigError("source_classes must be a non-empty list")
    source_classes = tuple(
        _string(name, "source_classes entry") for name in source_classes_value
    )
    if len(set(source_classes)) != len(source_classes):
        raise TrainingConfigError("source_classes must not contain duplicates")

    mapping_value = _object(values["project_class_mapping"], "project_class_mapping")
    if not mapping_value:
        raise TrainingConfigError("project_class_mapping must not be empty")
    unknown_targets = set(mapping_value.values()) - set(source_classes)
    if unknown_targets:
        raise TrainingConfigError(
            "project_class_mapping contains unknown source classes: "
            + ", ".join(sorted(unknown_targets))
        )

    checkpoint_sha256 = _string(
        values["base_checkpoint_sha256"], "base_checkpoint_sha256"
    ).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", checkpoint_sha256):
        raise TrainingConfigError("base_checkpoint_sha256 must contain 64 hex digits")

    return FineTuningConfig(
        schema_version=_integer(values["schema_version"], "schema_version", 1),
        run_name=run_name,
        random_seed=_integer(values["random_seed"], "random_seed", 0),
        base_checkpoint=_relative_path(values["base_checkpoint"], "base_checkpoint"),
        base_checkpoint_sha256=checkpoint_sha256,
        source_classes=source_classes,
        project_class_mapping=tuple(sorted(mapping_value.items())),
        dataset=_parse_dataset(values["dataset"]),
        training=_parse_training(values["training"]),
        output_directory=_derived_output_path(
            values["output_directory"], "output_directory"
        ),
        config_sha256=hashlib.sha256(raw).hexdigest(),
    )
