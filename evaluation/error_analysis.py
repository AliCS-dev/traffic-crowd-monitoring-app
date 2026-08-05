import hashlib
import json
import platform
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np
from pycocotools import mask as mask_utils

from evaluation.confidence_sweep import (
    SourceEvaluationRun,
    load_source_evaluation_run,
    verify_source_dataset_identity,
)
from evaluation.dataset_validation import validate_dataset
from evaluation.error_visualization import (
    render_contact_sheet,
    render_count_error,
    render_detection_error,
)
from evaluation.evaluation_config import PROJECT_CLASSES
from evaluation.evaluation_data import (
    BoundingBox,
    EvaluationDataset,
    PredictionRecord,
    load_evaluation_dataset,
)
from evaluation.evaluation_metrics import (
    CATEGORY_IDS,
    _build_coco_inputs,
    _run_operating_evaluation,
    calculate_detection_metrics,
)

ERROR_TYPES = (
    "false_positive",
    "false_negative",
    "class_confusion",
    "excluded_label_confusion",
)
OBJECT_SIZE_ORDER = {"small": 0, "medium": 1, "large": 2}


class ErrorAnalysisError(RuntimeError):
    """Raised when qualitative error analysis is invalid or incomplete."""


@dataclass(frozen=True)
class ErrorAnalysisConfig:
    schema_version: int
    analysis_name: str
    protocol_version: str
    operating_confidence: float
    operating_iou: float
    cases_per_error_type: int
    count_error_cases: int
    crop_size: int
    context_multiplier: float
    output_directory: Path


@dataclass(frozen=True)
class DetectionError:
    error_id: str
    error_type: str
    asset_id: str
    collection_id: str
    source_group_id: str
    expected_class: str | None
    predicted_class: str | None
    confidence: float | None
    iou: float | None
    ground_truth_box: BoundingBox | None
    prediction_box: BoundingBox | None
    object_size: str


@dataclass(frozen=True)
class CountError:
    asset_id: str
    collection_id: str
    source_group_id: str
    project_class: str
    ground_truth_count: int
    predicted_count: int
    signed_error: int
    absolute_error: int
    normalized_absolute_error: float | None


@dataclass(frozen=True)
class DetectionErrorAnalysis:
    true_positives: int
    false_positives: int
    false_negatives: int
    errors: tuple[DetectionError, ...]


@dataclass(frozen=True)
class ErrorAnalysisResult:
    source_run_id: str
    source_manifest_sha256: str
    dataset_role: str
    operating_confidence: float
    operating_iou: float
    detection: DetectionErrorAnalysis
    count_errors: tuple[CountError, ...]
    selected_detection_error_ids: tuple[str, ...]
    selected_count_asset_ids: tuple[str, ...]


@dataclass(frozen=True)
class RenderedCase:
    case_type: str
    case_id: str
    asset_id: str
    image_path: Path


@dataclass(frozen=True)
class SavedErrorAnalysis:
    analysis_id: str
    output_directory: Path
    summary_path: Path


@dataclass(frozen=True)
class _UnmatchedPrediction:
    detection_id: int
    asset_id: str
    project_class: str
    confidence: float
    box: BoundingBox


@dataclass(frozen=True)
class _UnmatchedGroundTruth:
    annotation_id: int
    asset_id: str
    project_class: str
    box: BoundingBox


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ErrorAnalysisError(f"Could not read JSON file: {path}") from error
    except json.JSONDecodeError as error:
        raise ErrorAnalysisError(f"File is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ErrorAnalysisError(f"JSON file must contain an object: {path}")
    return value


def _relative_path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ErrorAnalysisError(f"{field} must be a non-empty string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ErrorAnalysisError(f"{field} must be repository-relative")
    return path


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ErrorAnalysisError(f"{field} must be a positive integer")
    return value


def _probability(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ErrorAnalysisError(f"{field} must be numeric")
    number = float(value)
    if not 0 < number <= 1:
        raise ErrorAnalysisError(f"{field} must be greater than 0 and at most 1")
    return number


def _positive_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ErrorAnalysisError(f"{field} must be numeric")
    number = float(value)
    if number <= 0:
        raise ErrorAnalysisError(f"{field} must be positive")
    return number


def parse_error_analysis_config(values: dict[str, Any]) -> ErrorAnalysisConfig:
    required = {
        "schema_version",
        "analysis_name",
        "protocol_version",
        "operating_confidence",
        "operating_iou",
        "cases_per_error_type",
        "count_error_cases",
        "crop_size",
        "context_multiplier",
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
        raise ErrorAnalysisError(
            f"Error-analysis configuration fields are invalid ({'; '.join(details)})"
        )
    if values["schema_version"] != 1:
        raise ErrorAnalysisError("Error-analysis schema_version must be 1")
    name = values["analysis_name"]
    protocol_version = values["protocol_version"]
    if not isinstance(name, str) or not name:
        raise ErrorAnalysisError("analysis_name must be a non-empty string")
    if not isinstance(protocol_version, str) or not protocol_version:
        raise ErrorAnalysisError("protocol_version must be a non-empty string")
    return ErrorAnalysisConfig(
        schema_version=1,
        analysis_name=name,
        protocol_version=protocol_version,
        operating_confidence=_probability(
            values["operating_confidence"], "operating_confidence"
        ),
        operating_iou=_probability(values["operating_iou"], "operating_iou"),
        cases_per_error_type=_positive_integer(
            values["cases_per_error_type"], "cases_per_error_type"
        ),
        count_error_cases=_positive_integer(
            values["count_error_cases"], "count_error_cases"
        ),
        crop_size=_positive_integer(values["crop_size"], "crop_size"),
        context_multiplier=_positive_number(
            values["context_multiplier"], "context_multiplier"
        ),
        output_directory=_relative_path(values["output_directory"], "output_directory"),
    )


def load_error_analysis_config(path: Path) -> ErrorAnalysisConfig:
    return parse_error_analysis_config(_read_json(path))


def _object_size(box: BoundingBox) -> str:
    area = box.width * box.height
    if area < 32**2:
        return "small"
    if area < 96**2:
        return "medium"
    return "large"


def _box_from_annotation(annotation: dict[str, Any]) -> BoundingBox:
    try:
        return BoundingBox(*(float(value) for value in annotation["bbox"]))
    except (KeyError, TypeError, ValueError) as error:
        raise ErrorAnalysisError("COCO evaluation returned an invalid box") from error


def _collect_unmatched(
    dataset: EvaluationDataset,
    predictions: list[PredictionRecord],
    *,
    confidence_floor: float,
    operating_confidence: float,
    operating_iou: float,
    max_detections: int,
) -> tuple[int, list[_UnmatchedPrediction], list[_UnmatchedGroundTruth]]:
    ground_truth, result_rows, image_lookup, support = _build_coco_inputs(
        dataset, predictions, confidence_floor
    )
    supported_classes = [name for name in PROJECT_CLASSES if support[name] > 0]
    category_ids = [CATEGORY_IDS[name] for name in supported_classes]
    evaluator = _run_operating_evaluation(
        ground_truth,
        result_rows,
        list(image_lookup.values()),
        category_ids,
        operating_confidence,
        operating_iou,
        max_detections,
    )
    category_names = {value: key for key, value in CATEGORY_IDS.items()}
    asset_by_image = {value: key for key, value in image_lookup.items()}
    true_positives = 0
    false_positives = []
    false_negatives = []
    for image_result in evaluator.evalImgs:
        if image_result is None:
            continue
        asset_id = asset_by_image[image_result["image_id"]]
        detection_matches = np.asarray(image_result["dtMatches"])[0]
        detection_ignored = np.asarray(image_result["dtIgnore"])[0].astype(bool)
        for index, detection_id in enumerate(image_result["dtIds"]):
            if detection_ignored[index]:
                continue
            if detection_matches[index] > 0:
                true_positives += 1
                continue
            annotation = evaluator.cocoDt.anns[detection_id]
            false_positives.append(
                _UnmatchedPrediction(
                    detection_id=detection_id,
                    asset_id=asset_id,
                    project_class=category_names[annotation["category_id"]],
                    confidence=float(annotation["score"]),
                    box=_box_from_annotation(annotation),
                )
            )
        ground_truth_matches = np.asarray(image_result["gtMatches"])[0]
        ground_truth_ignored = np.asarray(image_result["gtIgnore"]).astype(bool)
        for index, annotation_id in enumerate(image_result["gtIds"]):
            if ground_truth_ignored[index] or ground_truth_matches[index] > 0:
                continue
            annotation = evaluator.cocoGt.anns[annotation_id]
            false_negatives.append(
                _UnmatchedGroundTruth(
                    annotation_id=annotation_id,
                    asset_id=asset_id,
                    project_class=category_names[annotation["category_id"]],
                    box=_box_from_annotation(annotation),
                )
            )
    return true_positives, false_positives, false_negatives


def _confusion_pairs(
    predictions: list[_UnmatchedPrediction],
    ground_truth: list[_UnmatchedGroundTruth],
    iou_threshold: float,
) -> list[tuple[_UnmatchedPrediction, _UnmatchedGroundTruth, float]]:
    predictions_by_asset: dict[str, list[_UnmatchedPrediction]] = defaultdict(list)
    ground_truth_by_asset: dict[str, list[_UnmatchedGroundTruth]] = defaultdict(list)
    for prediction in predictions:
        predictions_by_asset[prediction.asset_id].append(prediction)
    for annotation in ground_truth:
        ground_truth_by_asset[annotation.asset_id].append(annotation)

    pairs = []
    for asset_id in sorted(set(predictions_by_asset) & set(ground_truth_by_asset)):
        asset_predictions = predictions_by_asset[asset_id]
        asset_ground_truth = ground_truth_by_asset[asset_id]
        ious = mask_utils.iou(
            [list(item.box.as_xywh()) for item in asset_predictions],
            [list(item.box.as_xywh()) for item in asset_ground_truth],
            [0] * len(asset_ground_truth),
        )
        candidates = []
        for prediction_index, prediction in enumerate(asset_predictions):
            for ground_truth_index, annotation in enumerate(asset_ground_truth):
                iou = float(ious[prediction_index, ground_truth_index])
                if (
                    prediction.project_class != annotation.project_class
                    and iou >= iou_threshold
                ):
                    candidates.append((iou, prediction, annotation))
        candidates.sort(
            key=lambda value: (
                -value[0],
                -value[1].confidence,
                value[1].detection_id,
                value[2].annotation_id,
            )
        )
        used_predictions = set()
        used_ground_truth = set()
        for iou, prediction, annotation in candidates:
            if (
                prediction.detection_id in used_predictions
                or annotation.annotation_id in used_ground_truth
            ):
                continue
            used_predictions.add(prediction.detection_id)
            used_ground_truth.add(annotation.annotation_id)
            pairs.append((prediction, annotation, iou))
    return pairs


def _excluded_predictions(
    dataset: EvaluationDataset,
    predictions: list[PredictionRecord],
    operating_confidence: float,
) -> list[_UnmatchedPrediction]:
    assets = dataset.asset_by_id()
    values = []
    for index, prediction in enumerate(predictions, start=1):
        asset = assets.get(prediction.asset_id)
        if (
            asset is None
            or asset.annotation_type != "bounding_box"
            or prediction.confidence < operating_confidence
            or asset.includes_class(prediction.project_class)
        ):
            continue
        values.append(
            _UnmatchedPrediction(
                detection_id=index,
                asset_id=prediction.asset_id,
                project_class=prediction.source_class,
                confidence=prediction.confidence,
                box=prediction.box,
            )
        )
    return values


def analyze_detection_errors(
    dataset: EvaluationDataset,
    predictions: list[PredictionRecord],
    *,
    confidence_floor: float,
    operating_confidence: float,
    operating_iou: float,
    max_detections: int,
) -> DetectionErrorAnalysis:
    true_positives, false_positives, false_negatives = _collect_unmatched(
        dataset,
        predictions,
        confidence_floor=confidence_floor,
        operating_confidence=operating_confidence,
        operating_iou=operating_iou,
        max_detections=max_detections,
    )
    confusion_pairs = _confusion_pairs(false_positives, false_negatives, operating_iou)
    confused_detection_ids = {
        prediction.detection_id for prediction, _, _ in confusion_pairs
    }
    confused_annotation_ids = {
        annotation.annotation_id for _, annotation, _ in confusion_pairs
    }
    remaining_false_negatives = [
        annotation
        for annotation in false_negatives
        if annotation.annotation_id not in confused_annotation_ids
    ]
    excluded_label_pairs = _confusion_pairs(
        _excluded_predictions(dataset, predictions, operating_confidence),
        remaining_false_negatives,
        operating_iou,
    )
    excluded_label_annotation_ids = {
        annotation.annotation_id for _, annotation, _ in excluded_label_pairs
    }
    assets = dataset.asset_by_id()
    errors = []
    for prediction in false_positives:
        if prediction.detection_id in confused_detection_ids:
            continue
        asset = assets[prediction.asset_id]
        errors.append(
            DetectionError(
                error_id=f"fp-{prediction.asset_id}-{prediction.detection_id}",
                error_type="false_positive",
                asset_id=prediction.asset_id,
                collection_id=asset.collection_id,
                source_group_id=asset.source_group_id,
                expected_class=None,
                predicted_class=prediction.project_class,
                confidence=prediction.confidence,
                iou=None,
                ground_truth_box=None,
                prediction_box=prediction.box,
                object_size=_object_size(prediction.box),
            )
        )
    for annotation in false_negatives:
        if (
            annotation.annotation_id in confused_annotation_ids
            or annotation.annotation_id in excluded_label_annotation_ids
        ):
            continue
        asset = assets[annotation.asset_id]
        errors.append(
            DetectionError(
                error_id=f"fn-{annotation.asset_id}-{annotation.annotation_id}",
                error_type="false_negative",
                asset_id=annotation.asset_id,
                collection_id=asset.collection_id,
                source_group_id=asset.source_group_id,
                expected_class=annotation.project_class,
                predicted_class=None,
                confidence=None,
                iou=None,
                ground_truth_box=annotation.box,
                prediction_box=None,
                object_size=_object_size(annotation.box),
            )
        )
    for prediction, annotation, iou in confusion_pairs:
        asset = assets[prediction.asset_id]
        errors.append(
            DetectionError(
                error_id=(
                    f"confusion-{prediction.asset_id}-"
                    f"{annotation.annotation_id}-{prediction.detection_id}"
                ),
                error_type="class_confusion",
                asset_id=prediction.asset_id,
                collection_id=asset.collection_id,
                source_group_id=asset.source_group_id,
                expected_class=annotation.project_class,
                predicted_class=prediction.project_class,
                confidence=prediction.confidence,
                iou=iou,
                ground_truth_box=annotation.box,
                prediction_box=prediction.box,
                object_size=_object_size(annotation.box),
            )
        )
    for prediction, annotation, iou in excluded_label_pairs:
        asset = assets[prediction.asset_id]
        errors.append(
            DetectionError(
                error_id=(
                    f"excluded-label-confusion-{prediction.asset_id}-"
                    f"{annotation.annotation_id}-{prediction.detection_id}"
                ),
                error_type="excluded_label_confusion",
                asset_id=prediction.asset_id,
                collection_id=asset.collection_id,
                source_group_id=asset.source_group_id,
                expected_class=annotation.project_class,
                predicted_class=prediction.project_class,
                confidence=prediction.confidence,
                iou=iou,
                ground_truth_box=annotation.box,
                prediction_box=prediction.box,
                object_size=_object_size(annotation.box),
            )
        )
    errors.sort(key=lambda item: (item.error_type, item.asset_id, item.error_id))
    return DetectionErrorAnalysis(
        true_positives=true_positives,
        false_positives=len(false_positives),
        false_negatives=len(false_negatives),
        errors=tuple(errors),
    )


def analyze_count_errors(
    dataset: EvaluationDataset,
    predictions: list[PredictionRecord],
    *,
    operating_confidence: float,
) -> tuple[CountError, ...]:
    assets = dataset.asset_by_id()
    predicted_counts: Counter[tuple[str, str]] = Counter()
    for prediction in predictions:
        if prediction.confidence < operating_confidence:
            continue
        asset = assets.get(prediction.asset_id)
        if asset is not None and asset.includes_class(prediction.project_class):
            predicted_counts[(prediction.asset_id, prediction.project_class)] += 1
    errors = []
    for reference in dataset.count_references:
        asset = assets[reference.asset_id]
        predicted = predicted_counts[(reference.asset_id, reference.project_class)]
        signed_error = predicted - reference.count
        errors.append(
            CountError(
                asset_id=reference.asset_id,
                collection_id=asset.collection_id,
                source_group_id=asset.source_group_id,
                project_class=reference.project_class,
                ground_truth_count=reference.count,
                predicted_count=predicted,
                signed_error=signed_error,
                absolute_error=abs(signed_error),
                normalized_absolute_error=(
                    abs(signed_error) / reference.count if reference.count > 0 else None
                ),
            )
        )
    return tuple(sorted(errors, key=lambda item: item.asset_id))


def _error_priority(error: DetectionError) -> tuple[Any, ...]:
    if error.error_type == "false_positive":
        return (
            -(error.confidence or 0.0),
            OBJECT_SIZE_ORDER[error.object_size],
            error.error_id,
        )
    if error.error_type == "false_negative":
        box = error.ground_truth_box
        area = box.width * box.height if box is not None else 0.0
        return (-area, OBJECT_SIZE_ORDER[error.object_size], error.error_id)
    return (-(error.iou or 0.0), -(error.confidence or 0.0), error.error_id)


def _diversity_key(error: DetectionError) -> tuple[str, ...]:
    if error.error_type == "false_positive":
        class_name = error.predicted_class or "unknown"
    else:
        class_name = error.expected_class or "unknown"
    if error.error_type in {"class_confusion", "excluded_label_confusion"}:
        class_name = f"{class_name}->{error.predicted_class or 'unknown'}"
    return error.source_group_id, class_name, error.object_size


def _select_diverse_errors(
    errors: list[DetectionError], limit: int
) -> tuple[DetectionError, ...]:
    ordered = sorted(errors, key=_error_priority)
    selected = []
    selected_ids = set()
    seen_keys = set()
    for object_size in OBJECT_SIZE_ORDER:
        candidate = next(
            (
                error
                for error in ordered
                if error.object_size == object_size
                and error.error_id not in selected_ids
            ),
            None,
        )
        if candidate is None:
            continue
        selected.append(candidate)
        selected_ids.add(candidate.error_id)
        seen_keys.add(_diversity_key(candidate))
        if len(selected) == limit:
            return tuple(selected)
    for error in ordered:
        if error.error_id in selected_ids:
            continue
        key = _diversity_key(error)
        if key in seen_keys:
            continue
        selected.append(error)
        selected_ids.add(error.error_id)
        seen_keys.add(key)
        if len(selected) == limit:
            return tuple(selected)
    seen_assets = {error.asset_id for error in selected}
    for error in ordered:
        if error.error_id in selected_ids or error.asset_id in seen_assets:
            continue
        selected.append(error)
        selected_ids.add(error.error_id)
        seen_assets.add(error.asset_id)
        if len(selected) == limit:
            return tuple(selected)
    for error in ordered:
        if error.error_id in selected_ids:
            continue
        selected.append(error)
        if len(selected) == limit:
            break
    return tuple(selected)


def select_representative_errors(
    analysis: DetectionErrorAnalysis, cases_per_error_type: int
) -> tuple[DetectionError, ...]:
    selected = []
    for error_type in ERROR_TYPES:
        candidates = [
            error for error in analysis.errors if error.error_type == error_type
        ]
        selected.extend(_select_diverse_errors(candidates, cases_per_error_type))
    return tuple(selected)


def select_count_errors(
    errors: tuple[CountError, ...], limit: int
) -> tuple[CountError, ...]:
    ordered = sorted(
        errors,
        key=lambda item: (
            -item.absolute_error,
            item.source_group_id,
            item.asset_id,
        ),
    )
    selected = []
    seen_groups = set()
    for error in ordered:
        if error.source_group_id in seen_groups:
            continue
        selected.append(error)
        seen_groups.add(error.source_group_id)
        if len(selected) == limit:
            return tuple(selected)
    for error in ordered:
        if error in selected:
            continue
        selected.append(error)
        if len(selected) == limit:
            break
    return tuple(selected)


def create_error_analysis_result(
    dataset: EvaluationDataset,
    source: SourceEvaluationRun,
    config: ErrorAnalysisConfig,
) -> ErrorAnalysisResult:
    if dataset.role != "validation" or source.config.dataset.role != "validation":
        raise ErrorAnalysisError("Qualitative tuning may use validation data only")
    if source.config.protocol_version != config.protocol_version:
        raise ErrorAnalysisError("Analysis and source protocol versions do not match")
    if config.operating_confidence < source.config.inference.confidence_floor:
        raise ErrorAnalysisError(
            "Analysis confidence is below the saved prediction confidence floor"
        )
    expected_asset_ids = tuple(asset.asset_id for asset in dataset.assets)
    if source.predictions.asset_ids != expected_asset_ids:
        raise ErrorAnalysisError(
            "Source run assets do not match the complete validation dataset"
        )
    predictions = list(source.predictions.predictions)
    detection = analyze_detection_errors(
        dataset,
        predictions,
        confidence_floor=source.config.inference.confidence_floor,
        operating_confidence=config.operating_confidence,
        operating_iou=config.operating_iou,
        max_detections=source.config.inference.max_detections,
    )
    metrics = calculate_detection_metrics(
        dataset,
        predictions,
        confidence_floor=source.config.inference.confidence_floor,
        operating_confidence=config.operating_confidence,
        operating_iou=config.operating_iou,
        max_detections=source.config.inference.max_detections,
        low_support_threshold=source.config.metrics.low_support_threshold,
    )
    if (
        detection.true_positives
        != sum(metric.true_positives for metric in metrics.per_class)
        or detection.false_positives
        != sum(metric.false_positives for metric in metrics.per_class)
        or detection.false_negatives
        != sum(metric.false_negatives for metric in metrics.per_class)
    ):
        raise ErrorAnalysisError(
            "Qualitative error totals do not match quantitative metrics"
        )
    count_errors = analyze_count_errors(
        dataset, predictions, operating_confidence=config.operating_confidence
    )
    selected_detection = select_representative_errors(
        detection, config.cases_per_error_type
    )
    selected_counts = select_count_errors(count_errors, config.count_error_cases)
    return ErrorAnalysisResult(
        source_run_id=source.run_id,
        source_manifest_sha256=source.manifest_sha256,
        dataset_role=dataset.role,
        operating_confidence=config.operating_confidence,
        operating_iou=config.operating_iou,
        detection=detection,
        count_errors=count_errors,
        selected_detection_error_ids=tuple(
            error.error_id for error in selected_detection
        ),
        selected_count_asset_ids=tuple(error.asset_id for error in selected_counts),
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
    if isinstance(value, (tuple, list)):
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
        raise ErrorAnalysisError(
            f"Could not write analysis artifact: {path}"
        ) from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ErrorAnalysisError(f"Could not hash analysis artifact: {path}") from error
    return digest.hexdigest()


def _provenance(repository_root: Path) -> dict[str, Any]:
    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    versions = {}
    for package in ("numpy", "opencv-python", "pycocotools"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return {
        "git": {
            "commit": git("rev-parse", "HEAD"),
            "dirty": bool(git("status", "--porcelain")),
        },
        "python_version": platform.python_version(),
        "dependencies": versions,
    }


def _case_detail(error: DetectionError) -> str:
    if error.error_type == "false_positive":
        return f"predicted {error.predicted_class} at {error.confidence:.3f}"
    if error.error_type == "false_negative":
        return f"missed {error.expected_class}"
    return (
        f"expected {error.expected_class}, predicted {error.predicted_class}, "
        f"IoU {error.iou:.3f}"
    )


def build_error_analysis_report(
    result: ErrorAnalysisResult,
    rendered_cases: tuple[RenderedCase, ...],
    contact_sheet_paths: tuple[Path, ...] = (),
) -> str:
    type_counts = Counter(error.error_type for error in result.detection.errors)
    confusion_counts = Counter(
        (error.error_type, error.expected_class, error.predicted_class)
        for error in result.detection.errors
        if error.error_type in {"class_confusion", "excluded_label_confusion"}
    )
    rendered_by_id = {case.case_id: case for case in rendered_cases}
    errors_by_id = {error.error_id: error for error in result.detection.errors}
    count_by_id = {error.asset_id: error for error in result.count_errors}
    lines = [
        "# Qualitative Error Analysis",
        "",
        f"- Source run: `{result.source_run_id}`",
        f"- Dataset role: {result.dataset_role}",
        f"- Operating confidence: {result.operating_confidence:.2f}",
        f"- Operating IoU: {result.operating_iou:.2f}",
        "",
        "## Detection Error Totals",
        "",
        "| Measure | Count |",
        "| --- | ---: |",
        f"| True positives | {result.detection.true_positives} |",
        f"| False positives used by metrics | {result.detection.false_positives} |",
        f"| False negatives used by metrics | {result.detection.false_negatives} |",
        f"| Standalone false-positive cases | {type_counts['false_positive']} |",
        f"| Standalone false-negative cases | {type_counts['false_negative']} |",
        f"| Cross-class confusions | {type_counts['class_confusion']} |",
        f"| Excluded-label confusions | {type_counts['excluded_label_confusion']} |",
        "",
        "A class confusion contributes one false positive for the predicted class "
        "and one false negative for the expected class in the quantitative metrics.",
        "An excluded-label confusion contributes a false negative only because "
        "the raw predicted label is outside the evaluated labels for that asset.",
        "",
        "## Classification Confusions",
        "",
        "| Type | Expected | Predicted | Cases |",
        "| --- | --- | --- | ---: |",
    ]
    if confusion_counts:
        for (error_type, expected, predicted), count in sorted(
            confusion_counts.items()
        ):
            lines.append(f"| {error_type} | {expected} | {predicted} | {count} |")
    else:
        lines.append("| none | none | none | 0 |")
    lines.extend(
        [
            "",
            "## Selected Detection Cases",
            "",
            "| Type | Asset | Object size | Detail | Image |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for error_id in result.selected_detection_error_ids:
        error = errors_by_id[error_id]
        case = rendered_by_id[error_id]
        lines.append(
            f"| {error.error_type} | `{error.asset_id}` | {error.object_size} | "
            f"{_case_detail(error)} | [{case.image_path.name}]"
            f"({case.image_path.as_posix()}) |"
        )
    lines.extend(
        [
            "",
            "Cases are selected deterministically. The first pass covers available "
            "object-size categories, followed by distinct source groups and classes. "
            "Remaining places are filled by confidence, missed-object area, or "
            "confusion IoU.",
            "",
            "## Selected Count-Only Crowd Cases",
            "",
            "| Asset | Ground truth | Predicted | Signed error | NAE | Image |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for asset_id in result.selected_count_asset_ids:
        error = count_by_id[asset_id]
        case = rendered_by_id[asset_id]
        nae = (
            "n/a"
            if error.normalized_absolute_error is None
            else f"{error.normalized_absolute_error:.4f}"
        )
        lines.append(
            f"| `{asset_id}` | {error.ground_truth_count} | "
            f"{error.predicted_count} | {error.signed_error:+d} | {nae} | "
            f"[{case.image_path.name}]({case.image_path.as_posix()}) |"
        )
    lines.extend(
        [
            "",
            "Count-only annotations contain a total person count but no person "
            "locations. They demonstrate undercounting at scene level and cannot "
            "identify spatial false-negative boxes.",
            "No held-out data or new model inference is used in this analysis.",
        ]
    )
    if contact_sheet_paths:
        lines.extend(["", "## Contact Sheets", ""])
        for path in contact_sheet_paths:
            lines.append(f"- [{path.name}]({path.as_posix()})")
    lines.append("")
    return "\n".join(lines)


def _prediction_lookup(
    source: SourceEvaluationRun, confidence: float
) -> dict[str, tuple[PredictionRecord, ...]]:
    grouped: dict[str, list[PredictionRecord]] = defaultdict(list)
    for prediction in source.predictions.predictions:
        if prediction.confidence >= confidence and prediction.project_class == "person":
            grouped[prediction.asset_id].append(prediction)
    return {
        asset_id: tuple(sorted(values, key=lambda item: -item.confidence))
        for asset_id, values in grouped.items()
    }


def save_error_analysis(
    repository_root: Path,
    config: ErrorAnalysisConfig,
    result: ErrorAnalysisResult,
    dataset: EvaluationDataset,
    source: SourceEvaluationRun,
    *,
    created_at: datetime | None = None,
    provenance: dict[str, Any] | None = None,
) -> SavedErrorAnalysis:
    timestamp = created_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ErrorAnalysisError("Analysis timestamp must include a timezone")
    timestamp = timestamp.astimezone(timezone.utc)
    analysis_id = f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{config.analysis_name}"
    output_directory = repository_root / config.output_directory / analysis_id
    try:
        output_directory.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        raise ErrorAnalysisError(
            f"Could not create analysis directory: {output_directory}"
        ) from error
    assets = dataset.asset_by_id()
    errors_by_id = {error.error_id: error for error in result.detection.errors}
    count_by_id = {error.asset_id: error for error in result.count_errors}
    person_predictions = _prediction_lookup(source, result.operating_confidence)
    rendered_cases = []
    for error_id in result.selected_detection_error_ids:
        error = errors_by_id[error_id]
        asset = assets[error.asset_id]
        relative_path = Path("cases/detection") / f"{error.error_id}.jpg"
        render_detection_error(
            asset.image_path,
            output_directory / relative_path,
            asset_id=error.asset_id,
            error_type=error.error_type,
            expected_class=error.expected_class,
            predicted_class=error.predicted_class,
            confidence=error.confidence,
            iou=error.iou,
            ground_truth_box=error.ground_truth_box,
            prediction_box=error.prediction_box,
            crop_size=config.crop_size,
            context_multiplier=config.context_multiplier,
        )
        rendered_cases.append(
            RenderedCase(
                error.error_type, error.error_id, error.asset_id, relative_path
            )
        )
    for asset_id in result.selected_count_asset_ids:
        error = count_by_id[asset_id]
        asset = assets[asset_id]
        relative_path = Path("cases/count") / f"count-{asset_id}.jpg"
        render_count_error(
            asset.image_path,
            output_directory / relative_path,
            asset_id=asset_id,
            ground_truth_count=error.ground_truth_count,
            predicted_count=error.predicted_count,
            predictions=person_predictions.get(asset_id, ()),
        )
        rendered_cases.append(
            RenderedCase("count_error", asset_id, asset_id, relative_path)
        )
    rendered_tuple = tuple(rendered_cases)
    contact_sheet_paths = []
    for case_type, relative_path in (
        ("detection", Path("contact_sheets/detection_errors.jpg")),
        ("count", Path("contact_sheets/count_errors.jpg")),
    ):
        case_paths = tuple(
            output_directory / case.image_path
            for case in rendered_tuple
            if (
                case.case_type == "count_error"
                if case_type == "count"
                else case.case_type != "count_error"
            )
        )
        if not case_paths:
            continue
        render_contact_sheet(
            case_paths,
            output_directory / relative_path,
            columns=2 if case_type == "count" else 3,
        )
        contact_sheet_paths.append(relative_path)
    contact_sheet_tuple = tuple(contact_sheet_paths)
    analysis_path = output_directory / "analysis.json"
    _write_json(
        analysis_path,
        {
            "schema_version": 1,
            "analysis_id": analysis_id,
            "created_at_utc": timestamp.isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            ),
            "configuration": config,
            "provenance": provenance or _provenance(repository_root),
            "analysis": result,
            "rendered_cases": rendered_tuple,
            "contact_sheets": contact_sheet_tuple,
        },
    )
    summary_path = output_directory / "summary.md"
    try:
        summary_path.write_text(
            build_error_analysis_report(result, rendered_tuple, contact_sheet_tuple),
            encoding="utf-8",
        )
    except OSError as error:
        raise ErrorAnalysisError(
            f"Could not write analysis report: {summary_path}"
        ) from error
    artifact_paths = [analysis_path, summary_path]
    artifact_paths.extend(output_directory / case.image_path for case in rendered_tuple)
    artifact_paths.extend(output_directory / path for path in contact_sheet_tuple)
    _write_json(
        output_directory / "analysis_manifest.json",
        {
            "schema_version": 1,
            "analysis_id": analysis_id,
            "artifacts": [
                {
                    "filename": path.relative_to(output_directory).as_posix(),
                    "sha256": _sha256(path),
                }
                for path in sorted(artifact_paths)
            ],
        },
    )
    return SavedErrorAnalysis(analysis_id, output_directory, summary_path)


def run_error_analysis(
    repository_root: Path,
    source_run_directory: Path,
    config_path: Path,
) -> SavedErrorAnalysis:
    source_directory = (
        source_run_directory
        if source_run_directory.is_absolute()
        else repository_root / source_run_directory
    )
    resolved_config = (
        config_path if config_path.is_absolute() else repository_root / config_path
    )
    config = load_error_analysis_config(resolved_config)
    source = load_source_evaluation_run(source_directory)
    validation = validate_dataset(repository_root)
    if not validation.dataset_ready:
        raise ErrorAnalysisError("Evaluation dataset quality checks did not pass")
    verify_source_dataset_identity(repository_root, source)
    dataset = load_evaluation_dataset(repository_root, source.config.dataset)
    result = create_error_analysis_result(dataset, source, config)
    return save_error_analysis(repository_root, config, result, dataset, source)
