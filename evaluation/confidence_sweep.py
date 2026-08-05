import hashlib
import json
import platform
import subprocess
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from evaluation.dataset_validation import validate_dataset
from evaluation.evaluation_config import (
    EvaluationConfig,
    parse_evaluation_config,
)
from evaluation.evaluation_data import (
    BoundingBox,
    EvaluationDataset,
    PredictionRecord,
    load_evaluation_dataset,
)
from evaluation.evaluation_metrics import (
    CountMetricResult,
    DetectionMetricResult,
    calculate_count_metrics,
    calculate_detection_metrics,
)
from evaluation.evaluation_runner import PredictionBatch

PREDECLARED_CONFIDENCES = (0.10, 0.15, 0.25, 0.40, 0.50)


class ConfidenceSweepError(RuntimeError):
    """Raised when a confidence comparison is invalid or incomplete."""


@dataclass(frozen=True)
class ConfidenceSweepConfig:
    schema_version: int
    comparison_name: str
    protocol_version: str
    operating_confidences: tuple[float, ...]
    output_directory: Path


@dataclass(frozen=True)
class SourceEvaluationRun:
    run_id: str
    manifest_sha256: str
    config: EvaluationConfig
    predictions: PredictionBatch
    dataset_manifest_sha256: str
    annotation_files: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ConfidenceResult:
    operating_confidence: float
    detection: DetectionMetricResult
    counts: tuple[CountMetricResult, ...]


@dataclass(frozen=True)
class ConfidenceSweepResult:
    source_run_id: str
    source_manifest_sha256: str
    fixed_image_size: int
    fixed_scale_factor: int
    results: tuple[ConfidenceResult, ...]


@dataclass(frozen=True)
class SavedConfidenceSweep:
    comparison_id: str
    output_directory: Path
    summary_path: Path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfidenceSweepError(f"Could not read JSON file: {path}") from error
    except json.JSONDecodeError as error:
        raise ConfidenceSweepError(f"File is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ConfidenceSweepError(f"JSON file must contain an object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ConfidenceSweepError(f"Could not hash file: {path}") from error
    return digest.hexdigest()


def _relative_path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ConfidenceSweepError(f"{field} must be a non-empty string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ConfidenceSweepError(f"{field} must be repository-relative")
    return path


def parse_confidence_sweep_config(values: dict[str, Any]) -> ConfidenceSweepConfig:
    required = {
        "schema_version",
        "comparison_name",
        "protocol_version",
        "operating_confidences",
        "output_directory",
    }
    if set(values) != required:
        missing = required - set(values)
        unknown = set(values) - required
        details = []
        if missing:
            details.append(f"missing: {', '.join(sorted(missing))}")
        if unknown:
            details.append(f"unknown: {', '.join(sorted(unknown))}")
        raise ConfidenceSweepError(
            f"Confidence sweep configuration fields are invalid ({'; '.join(details)})"
        )
    if values["schema_version"] != 1:
        raise ConfidenceSweepError("Confidence sweep schema_version must be 1")
    name = values["comparison_name"]
    protocol_version = values["protocol_version"]
    if not isinstance(name, str) or not name:
        raise ConfidenceSweepError("comparison_name must be a non-empty string")
    if not isinstance(protocol_version, str) or not protocol_version:
        raise ConfidenceSweepError("protocol_version must be a non-empty string")
    raw_confidences = values["operating_confidences"]
    if not isinstance(raw_confidences, list) or any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in raw_confidences
    ):
        raise ConfidenceSweepError("operating_confidences must be a list of numbers")
    confidences = tuple(float(value) for value in raw_confidences)
    if confidences != PREDECLARED_CONFIDENCES:
        raise ConfidenceSweepError(
            "operating_confidences must match the predeclared Issue #40 values"
        )
    return ConfidenceSweepConfig(
        schema_version=1,
        comparison_name=name,
        protocol_version=protocol_version,
        operating_confidences=confidences,
        output_directory=_relative_path(values["output_directory"], "output_directory"),
    )


def load_confidence_sweep_config(path: Path) -> ConfidenceSweepConfig:
    return parse_confidence_sweep_config(_read_json(path))


def _verify_source_manifest(run_directory: Path) -> tuple[str, str]:
    manifest_path = run_directory / "run_manifest.json"
    manifest = _read_json(manifest_path)
    try:
        run_id = manifest["run_id"]
        artifacts = manifest["artifacts"]
    except KeyError as error:
        raise ConfidenceSweepError("Source run manifest is incomplete") from error
    if not isinstance(run_id, str) or not isinstance(artifacts, list):
        raise ConfidenceSweepError("Source run manifest has invalid fields")
    filenames = []
    for artifact in artifacts:
        try:
            filename = artifact["filename"]
            expected_hash = artifact["sha256"]
        except (KeyError, TypeError) as error:
            raise ConfidenceSweepError("Source artifact record is invalid") from error
        path = Path(filename)
        if path.name != filename:
            raise ConfidenceSweepError("Source artifact filename must be local")
        if _sha256(run_directory / path) != expected_hash:
            raise ConfidenceSweepError(f"Source artifact checksum failed: {filename}")
        filenames.append(filename)
    if len(filenames) != len(set(filenames)):
        raise ConfidenceSweepError("Source run manifest contains duplicate artifacts")
    required = {"configuration.json", "predictions.json", "provenance.json"}
    if not required <= set(filenames):
        raise ConfidenceSweepError("Source run manifest omits required artifacts")
    return run_id, _sha256(manifest_path)


def _prediction_record(value: dict[str, Any]) -> PredictionRecord:
    required = {"asset_id", "source_class", "project_class", "confidence", "box"}
    if (
        not isinstance(value, dict)
        or set(value) != required
        or not isinstance(value["box"], dict)
    ):
        raise ConfidenceSweepError("Saved prediction record has invalid fields")
    try:
        box = BoundingBox(**value["box"])
        return PredictionRecord(
            asset_id=value["asset_id"],
            source_class=value["source_class"],
            project_class=value["project_class"],
            confidence=value["confidence"],
            box=box,
        )
    except (TypeError, ValueError) as error:
        raise ConfidenceSweepError("Saved prediction record is invalid") from error


def load_source_evaluation_run(run_directory: Path) -> SourceEvaluationRun:
    run_id, manifest_hash = _verify_source_manifest(run_directory)
    configuration = _read_json(run_directory / "configuration.json")
    prediction_artifact = _read_json(run_directory / "predictions.json")
    provenance = _read_json(run_directory / "provenance.json")
    if configuration.get("run_id") != run_id:
        raise ConfidenceSweepError("Source configuration run ID does not match")
    if prediction_artifact.get("run_id") != run_id:
        raise ConfidenceSweepError("Source prediction run ID does not match")
    if provenance.get("run_id") != run_id:
        raise ConfidenceSweepError("Source provenance run ID does not match")
    try:
        config = parse_evaluation_config(configuration["configuration"])
        raw_asset_ids = prediction_artifact["processed_asset_ids"]
        prediction_values = prediction_artifact["predictions"]
        dataset_identity = provenance["dataset"]
        dataset_manifest_hash = dataset_identity["manifest_sha256"]
        annotation_values = dataset_identity["annotation_files"]
    except (KeyError, TypeError, ValueError) as error:
        raise ConfidenceSweepError(
            "Source evaluation artifacts are incomplete"
        ) from error
    if not isinstance(raw_asset_ids, list) or not all(
        isinstance(asset_id, str) for asset_id in raw_asset_ids
    ):
        raise ConfidenceSweepError("Source processed asset IDs must be a list")
    asset_ids = tuple(raw_asset_ids)
    if len(asset_ids) != len(set(asset_ids)):
        raise ConfidenceSweepError("Source run contains duplicate processed asset IDs")
    if not isinstance(prediction_values, list):
        raise ConfidenceSweepError("Source predictions must be a list")
    if not isinstance(dataset_manifest_hash, str) or not isinstance(
        annotation_values, list
    ):
        raise ConfidenceSweepError("Source dataset provenance is invalid")
    try:
        annotation_files = tuple(
            (value["path"], value["sha256"]) for value in annotation_values
        )
    except (KeyError, TypeError) as error:
        raise ConfidenceSweepError("Source annotation provenance is invalid") from error
    if not all(
        isinstance(path, str) and isinstance(digest, str)
        for path, digest in annotation_files
    ):
        raise ConfidenceSweepError("Source annotation provenance is invalid")
    if not annotation_files:
        raise ConfidenceSweepError("Source annotation provenance is empty")
    predictions = tuple(_prediction_record(value) for value in prediction_values)
    return SourceEvaluationRun(
        run_id=run_id,
        manifest_sha256=manifest_hash,
        config=config,
        predictions=PredictionBatch(asset_ids, predictions),
        dataset_manifest_sha256=dataset_manifest_hash,
        annotation_files=annotation_files,
    )


def verify_source_dataset_identity(
    repository_root: Path, source: SourceEvaluationRun
) -> None:
    manifest_path = source.config.resolve_path(
        repository_root, source.config.dataset.manifest_path
    )
    if _sha256(manifest_path) != source.dataset_manifest_sha256:
        raise ConfidenceSweepError("Dataset manifest changed after the source run")
    for value, expected_hash in source.annotation_files:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ConfidenceSweepError(
                "Source annotation path must be repository-relative"
            )
        if _sha256(repository_root / path) != expected_hash:
            raise ConfidenceSweepError(
                f"Annotation file changed after the source run: {value}"
            )


def calculate_confidence_sweep(
    dataset: EvaluationDataset,
    source: SourceEvaluationRun,
    sweep_config: ConfidenceSweepConfig,
) -> ConfidenceSweepResult:
    if source.config.dataset.role != "validation" or dataset.role != "validation":
        raise ConfidenceSweepError("Confidence tuning may use validation data only")
    if source.config.protocol_version != sweep_config.protocol_version:
        raise ConfidenceSweepError("Sweep and source protocol versions do not match")
    if dataset.version != source.config.dataset.version:
        raise ConfidenceSweepError("Loaded dataset version does not match source run")
    expected_asset_ids = tuple(asset.asset_id for asset in dataset.assets)
    if source.predictions.asset_ids != expected_asset_ids:
        raise ConfidenceSweepError(
            "Source run assets do not match the complete validation dataset"
        )

    predictions = list(source.predictions.predictions)
    results = []
    for confidence in sweep_config.operating_confidences:
        detection = calculate_detection_metrics(
            dataset,
            predictions,
            confidence_floor=source.config.inference.confidence_floor,
            operating_confidence=confidence,
            operating_iou=source.config.metrics.operating_iou,
            max_detections=source.config.inference.max_detections,
            low_support_threshold=source.config.metrics.low_support_threshold,
        )
        counts = calculate_count_metrics(
            dataset,
            predictions,
            operating_confidence=confidence,
            low_support_threshold=source.config.metrics.low_support_threshold,
        )
        results.append(ConfidenceResult(confidence, detection, counts))
    return ConfidenceSweepResult(
        source_run_id=source.run_id,
        source_manifest_sha256=source.manifest_sha256,
        fixed_image_size=source.config.inference.image_size,
        fixed_scale_factor=source.config.inference.scale_factor,
        results=tuple(results),
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _write_json(path: Path, value: Any) -> None:
    try:
        path.write_text(
            json.dumps(_json_value(value), indent=2, sort_keys=True, allow_nan=False)
            + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as error:
        raise ConfidenceSweepError(
            f"Could not write comparison file: {path}"
        ) from error


def _number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _metric_by_name(result: ConfidenceResult, name: str) -> CountMetricResult:
    return next(metric for metric in result.counts if metric.class_name == name)


def build_confidence_sweep_report(result: ConfidenceSweepResult) -> str:
    lines = [
        "# Confidence Threshold Comparison",
        "",
        f"- Source run: `{result.source_run_id}`",
        f"- Fixed image size: {result.fixed_image_size}",
        f"- Fixed scale factor: {result.fixed_scale_factor}",
        "- Dataset role: validation",
        "",
        "## Aggregate Results",
        "",
        "| Confidence | Precision | Recall | mAP50 | mAP50-95 | Person NAE | "
        "Vehicle NAE |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for confidence_result in result.results:
        person = _metric_by_name(confidence_result, "person")
        vehicles = _metric_by_name(confidence_result, "road_vehicle_total")
        detection = confidence_result.detection
        lines.append(
            f"| {confidence_result.operating_confidence:.2f} | "
            f"{detection.macro_precision:.4f} | {detection.macro_recall:.4f} | "
            f"{detection.map50:.4f} | {detection.map50_95:.4f} | "
            f"{_number(person.normalized_absolute_error)} | "
            f"{_number(vehicles.normalized_absolute_error)} |"
        )

    lines.extend(
        [
            "",
            "## Per-Class Detection At Each Operating Threshold",
            "",
            "| Confidence | Class | Support | Precision | Recall | TP | FP | FN | "
            "Low support |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for confidence_result in result.results:
        for metric in confidence_result.detection.per_class:
            lines.append(
                f"| {confidence_result.operating_confidence:.2f} | "
                f"{metric.class_name} | {metric.ground_truth_instances} | "
                f"{metric.precision:.4f} | {metric.recall:.4f} | "
                f"{metric.true_positives} | {metric.false_positives} | "
                f"{metric.false_negatives} | "
                f"{'yes' if metric.low_support else 'no'} |"
            )

    lines.extend(
        [
            "",
            "Average precision is calculated from the same confidence-floor "
            "predictions and therefore remains constant across operating thresholds.",
            "Low-support classes can noticeably affect macro precision and must be "
            "interpreted alongside their support and per-class results.",
            "No held-out test data or new model inference is used in this comparison.",
            "",
        ]
    )
    return "\n".join(lines)


def _comparison_provenance(repository_root: Path) -> dict[str, Any]:
    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    versions = {}
    for package in ("numpy", "pycocotools"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return {
        "git": {"commit": git_commit, "dirty": dirty},
        "python_version": platform.python_version(),
        "dependencies": versions,
    }


def save_confidence_sweep(
    repository_root: Path,
    sweep_config: ConfidenceSweepConfig,
    result: ConfidenceSweepResult,
    *,
    created_at: datetime | None = None,
    provenance: dict[str, Any] | None = None,
) -> SavedConfidenceSweep:
    timestamp = created_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ConfidenceSweepError("Comparison timestamp must include a timezone")
    timestamp = timestamp.astimezone(timezone.utc)
    comparison_id = (
        f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{sweep_config.comparison_name}"
    )
    output_directory = repository_root / sweep_config.output_directory / comparison_id
    try:
        output_directory.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        raise ConfidenceSweepError(
            f"Could not create comparison directory: {output_directory}"
        ) from error

    comparison_path = output_directory / "comparison.json"
    _write_json(
        comparison_path,
        {
            "schema_version": 1,
            "comparison_id": comparison_id,
            "created_at_utc": timestamp.isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            ),
            "configuration": sweep_config,
            "provenance": provenance or _comparison_provenance(repository_root),
            "comparison": result,
        },
    )
    summary_path = output_directory / "summary.md"
    summary_path.write_text(build_confidence_sweep_report(result), encoding="utf-8")
    _write_json(
        output_directory / "comparison_manifest.json",
        {
            "schema_version": 1,
            "comparison_id": comparison_id,
            "artifacts": [
                {"filename": path.name, "sha256": _sha256(path)}
                for path in (comparison_path, summary_path)
            ],
        },
    )
    return SavedConfidenceSweep(comparison_id, output_directory, summary_path)


def run_confidence_sweep(
    repository_root: Path,
    source_run_directory: Path,
    config_path: Path,
) -> SavedConfidenceSweep:
    source_directory = (
        source_run_directory
        if source_run_directory.is_absolute()
        else repository_root / source_run_directory
    )
    resolved_config = (
        config_path if config_path.is_absolute() else repository_root / config_path
    )
    sweep_config = load_confidence_sweep_config(resolved_config)
    source = load_source_evaluation_run(source_directory)
    validation = validate_dataset(repository_root)
    if not validation.dataset_ready:
        raise ConfidenceSweepError("Evaluation dataset quality checks did not pass")
    verify_source_dataset_identity(repository_root, source)
    dataset = load_evaluation_dataset(repository_root, source.config.dataset)
    result = calculate_confidence_sweep(dataset, source, sweep_config)
    return save_confidence_sweep(repository_root, sweep_config, result)
