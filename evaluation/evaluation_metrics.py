import io
from collections import Counter
from contextlib import redirect_stdout
from dataclasses import dataclass

import numpy as np
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval

from evaluation.evaluation_config import PROJECT_CLASSES
from evaluation.evaluation_data import EvaluationDataset, PredictionRecord

ROAD_VEHICLE_CLASSES = frozenset(
    {"bicycle", "motorcycle", "car_or_van", "bus", "truck"}
)
ROAD_VEHICLE_TOTAL = "road_vehicle_total"
CATEGORY_IDS = {name: index for index, name in enumerate(PROJECT_CLASSES, start=1)}


@dataclass(frozen=True)
class CountMetricResult:
    class_name: str
    examples: int
    ground_truth_total: int
    predicted_total: int
    mean_absolute_error: float
    normalized_absolute_error: float | None
    bias: float
    low_support: bool


@dataclass(frozen=True)
class DetectionClassMetric:
    class_name: str
    ground_truth_instances: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    ap50: float | None
    ap50_95: float | None
    low_support: bool


@dataclass(frozen=True)
class DetectionMetricResult:
    evaluated_images: int
    ground_truth_instances: int
    macro_precision: float
    macro_recall: float
    map50: float
    map50_95: float
    ap_small: float | None
    ap_medium: float | None
    ap_large: float | None
    per_class: tuple[DetectionClassMetric, ...]


def _ground_truth_counts(dataset: EvaluationDataset) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for box in dataset.ground_truth_boxes:
        counts[(box.asset_id, box.project_class)] += 1
    for reference in dataset.count_references:
        key = (reference.asset_id, reference.project_class)
        if key in counts:
            raise ValueError(
                f"Asset {reference.asset_id} has box and count-only ground truth"
            )
        counts[key] = reference.count
    return counts


def _prediction_counts(
    dataset: EvaluationDataset,
    predictions: list[PredictionRecord],
    operating_confidence: float,
) -> Counter[tuple[str, str]]:
    if not 0 <= operating_confidence <= 1:
        raise ValueError("Operating confidence must be between 0 and 1")
    assets = dataset.asset_by_id()
    counts: Counter[tuple[str, str]] = Counter()
    for prediction in predictions:
        asset = assets.get(prediction.asset_id)
        if asset is None:
            raise ValueError(
                f"Prediction references unknown asset: {prediction.asset_id}"
            )
        if prediction.confidence < operating_confidence:
            continue
        if asset.includes_class(prediction.project_class):
            counts[(prediction.asset_id, prediction.project_class)] += 1
    return counts


def _calculate_result(
    *,
    class_name: str,
    asset_ids: list[str],
    project_classes: frozenset[str],
    ground_truth: Counter[tuple[str, str]],
    predictions: Counter[tuple[str, str]],
    low_support_threshold: int,
) -> CountMetricResult:
    differences = []
    absolute_error_total = 0
    ground_truth_total = 0
    predicted_total = 0
    for asset_id in asset_ids:
        actual = sum(ground_truth[(asset_id, name)] for name in project_classes)
        predicted = sum(predictions[(asset_id, name)] for name in project_classes)
        difference = predicted - actual
        differences.append(difference)
        absolute_error_total += abs(difference)
        ground_truth_total += actual
        predicted_total += predicted

    example_count = len(asset_ids)
    return CountMetricResult(
        class_name=class_name,
        examples=example_count,
        ground_truth_total=ground_truth_total,
        predicted_total=predicted_total,
        mean_absolute_error=absolute_error_total / example_count,
        normalized_absolute_error=(
            absolute_error_total / ground_truth_total
            if ground_truth_total > 0
            else None
        ),
        bias=sum(differences) / example_count,
        low_support=ground_truth_total < low_support_threshold,
    )


def calculate_count_metrics(
    dataset: EvaluationDataset,
    predictions: list[PredictionRecord],
    *,
    operating_confidence: float,
    low_support_threshold: int,
) -> tuple[CountMetricResult, ...]:
    if low_support_threshold < 1:
        raise ValueError("Low-support threshold must be positive")

    ground_truth = _ground_truth_counts(dataset)
    predicted = _prediction_counts(dataset, predictions, operating_confidence)
    results = []
    for project_class in PROJECT_CLASSES:
        asset_ids = [
            asset.asset_id
            for asset in dataset.assets
            if asset.includes_class(project_class)
        ]
        if asset_ids:
            results.append(
                _calculate_result(
                    class_name=project_class,
                    asset_ids=asset_ids,
                    project_classes=frozenset({project_class}),
                    ground_truth=ground_truth,
                    predictions=predicted,
                    low_support_threshold=low_support_threshold,
                )
            )

    vehicle_asset_ids = [
        asset.asset_id
        for asset in dataset.assets
        if asset.target_classes & ROAD_VEHICLE_CLASSES
    ]
    if vehicle_asset_ids:
        results.append(
            _calculate_result(
                class_name=ROAD_VEHICLE_TOTAL,
                asset_ids=vehicle_asset_ids,
                project_classes=ROAD_VEHICLE_CLASSES,
                ground_truth=ground_truth,
                predictions=predicted,
                low_support_threshold=low_support_threshold,
            )
        )
    return tuple(results)


def _build_coco_inputs(
    dataset: EvaluationDataset,
    predictions: list[PredictionRecord],
    confidence_floor: float,
) -> tuple[COCO, list[dict], dict[str, int], Counter[str]]:
    detection_assets = [
        asset for asset in dataset.assets if asset.annotation_type == "bounding_box"
    ]
    if not detection_assets:
        raise ValueError("Dataset contains no bounding-box evaluation assets")

    image_ids = {
        asset.asset_id: image_id
        for image_id, asset in enumerate(detection_assets, start=1)
    }
    annotations = []
    support: Counter[str] = Counter()
    for annotation_id, ground_truth in enumerate(dataset.ground_truth_boxes, start=1):
        image_id = image_ids.get(ground_truth.asset_id)
        if image_id is None:
            raise ValueError(
                "Ground-truth box references a non-detection asset: "
                f"{ground_truth.asset_id}"
            )
        x, y, width, height = ground_truth.box.as_xywh()
        annotations.append(
            {
                "id": annotation_id,
                "image_id": image_id,
                "category_id": CATEGORY_IDS[ground_truth.project_class],
                "bbox": [x, y, width, height],
                "area": width * height,
                "iscrowd": 0,
            }
        )
        support[ground_truth.project_class] += 1

    coco_dataset = {
        "info": {"description": "Traffic monitoring evaluation"},
        "images": [
            {
                "id": image_ids[asset.asset_id],
                "asset_id": asset.asset_id,
                "width": asset.width,
                "height": asset.height,
            }
            for asset in detection_assets
        ],
        "categories": [
            {"id": category_id, "name": name}
            for name, category_id in CATEGORY_IDS.items()
        ],
        "annotations": annotations,
    }
    with redirect_stdout(io.StringIO()):
        ground_truth_coco = COCO()
        ground_truth_coco.dataset = coco_dataset
        ground_truth_coco.createIndex()

    assets = dataset.asset_by_id()
    result_rows = []
    for prediction in predictions:
        asset = assets.get(prediction.asset_id)
        if asset is None:
            raise ValueError(
                f"Prediction references unknown asset: {prediction.asset_id}"
            )
        if asset.annotation_type != "bounding_box":
            continue
        if prediction.confidence < confidence_floor:
            continue
        if not asset.includes_class(prediction.project_class):
            continue
        result_rows.append(
            {
                "image_id": image_ids[prediction.asset_id],
                "category_id": CATEGORY_IDS[prediction.project_class],
                "bbox": list(prediction.box.as_xywh()),
                "score": prediction.confidence,
            }
        )
    return ground_truth_coco, result_rows, image_ids, support


def _detection_results_coco(ground_truth: COCO, result_rows: list[dict]) -> COCO:
    with redirect_stdout(io.StringIO()):
        if result_rows:
            return ground_truth.loadRes(result_rows)
        results = COCO()
        results.dataset = {
            "info": ground_truth.dataset.get("info", {}),
            "images": ground_truth.dataset["images"],
            "categories": ground_truth.dataset["categories"],
            "annotations": [],
        }
        results.createIndex()
        return results


def _run_average_precision(
    ground_truth: COCO,
    detections: COCO,
    image_ids: list[int],
    category_ids: list[int],
    max_detections: int,
) -> COCOeval:
    evaluator = COCOeval(ground_truth, detections, "bbox")
    evaluator.params.imgIds = image_ids
    evaluator.params.catIds = category_ids
    evaluator.params.maxDets = [1, min(10, max_detections), max_detections]
    with redirect_stdout(io.StringIO()):
        evaluator.evaluate()
        evaluator.accumulate()
    return evaluator


def _run_operating_evaluation(
    ground_truth: COCO,
    result_rows: list[dict],
    image_ids: list[int],
    category_ids: list[int],
    operating_confidence: float,
    operating_iou: float,
    max_detections: int,
) -> COCOeval:
    operating_rows = [
        row for row in result_rows if row["score"] >= operating_confidence
    ]
    detections = _detection_results_coco(ground_truth, operating_rows)
    evaluator = COCOeval(ground_truth, detections, "bbox")
    evaluator.params.imgIds = image_ids
    evaluator.params.catIds = category_ids
    evaluator.params.iouThrs = np.array([operating_iou])
    evaluator.params.areaRng = [[0.0, 1e10]]
    evaluator.params.areaRngLbl = ["all"]
    evaluator.params.maxDets = [max_detections]
    with redirect_stdout(io.StringIO()):
        evaluator.evaluate()
    return evaluator


def _average_valid(values: np.ndarray) -> float | None:
    valid = values[values > -1]
    if valid.size == 0:
        return None
    return float(np.mean(valid))


def _operating_counts(evaluator: COCOeval) -> dict[int, tuple[int, int, int]]:
    counts: dict[int, list[int]] = {
        category_id: [0, 0, 0] for category_id in evaluator.params.catIds
    }
    for image_result in evaluator.evalImgs:
        if image_result is None:
            continue
        category_id = image_result["category_id"]
        detection_matches = np.asarray(image_result["dtMatches"])[0]
        detection_ignored = np.asarray(image_result["dtIgnore"])[0].astype(bool)
        ground_truth_matches = np.asarray(image_result["gtMatches"])[0]
        ground_truth_ignored = np.asarray(image_result["gtIgnore"]).astype(bool)
        counts[category_id][0] += int(
            np.count_nonzero((detection_matches > 0) & ~detection_ignored)
        )
        counts[category_id][1] += int(
            np.count_nonzero((detection_matches == 0) & ~detection_ignored)
        )
        counts[category_id][2] += int(
            np.count_nonzero((ground_truth_matches == 0) & ~ground_truth_ignored)
        )
    return {category_id: tuple(values) for category_id, values in counts.items()}


def calculate_detection_metrics(
    dataset: EvaluationDataset,
    predictions: list[PredictionRecord],
    *,
    confidence_floor: float,
    operating_confidence: float,
    operating_iou: float,
    max_detections: int,
    low_support_threshold: int,
) -> DetectionMetricResult:
    if not 0 < confidence_floor <= operating_confidence <= 1:
        raise ValueError(
            "Confidence floor and operating confidence must satisfy "
            "0 < floor <= operating <= 1"
        )
    if not 0 < operating_iou <= 1:
        raise ValueError("Operating IoU must be greater than 0 and at most 1")
    if max_detections < 1:
        raise ValueError("Maximum detections must be positive")
    if low_support_threshold < 1:
        raise ValueError("Low-support threshold must be positive")

    ground_truth, result_rows, image_lookup, support = _build_coco_inputs(
        dataset, predictions, confidence_floor
    )
    supported_classes = [name for name in PROJECT_CLASSES if support[name] > 0]
    if not supported_classes:
        raise ValueError("Dataset contains no supported bounding-box classes")
    category_ids = [CATEGORY_IDS[name] for name in supported_classes]
    image_ids = list(image_lookup.values())

    detections = _detection_results_coco(ground_truth, result_rows)
    average_precision = _run_average_precision(
        ground_truth, detections, image_ids, category_ids, max_detections
    )
    operating = _run_operating_evaluation(
        ground_truth,
        result_rows,
        image_ids,
        category_ids,
        operating_confidence,
        operating_iou,
        max_detections,
    )
    operating_counts = _operating_counts(operating)

    precision_values = average_precision.eval["precision"]
    map50 = _average_valid(precision_values[0, :, :, 0, -1])
    map50_95 = _average_valid(precision_values[:, :, :, 0, -1])
    if map50 is None or map50_95 is None:
        raise ValueError("COCO evaluation did not produce aggregate precision values")
    per_class = []
    for category_index, class_name in enumerate(supported_classes):
        category_id = CATEGORY_IDS[class_name]
        true_positives, false_positives, false_negatives = operating_counts[category_id]
        precision_denominator = true_positives + false_positives
        recall_denominator = true_positives + false_negatives
        per_class.append(
            DetectionClassMetric(
                class_name=class_name,
                ground_truth_instances=support[class_name],
                true_positives=true_positives,
                false_positives=false_positives,
                false_negatives=false_negatives,
                precision=(
                    true_positives / precision_denominator
                    if precision_denominator
                    else 0.0
                ),
                recall=(
                    true_positives / recall_denominator if recall_denominator else 0.0
                ),
                ap50=_average_valid(precision_values[0, :, category_index, 0, -1]),
                ap50_95=_average_valid(precision_values[:, :, category_index, 0, -1]),
                low_support=support[class_name] < low_support_threshold,
            )
        )

    return DetectionMetricResult(
        evaluated_images=len(image_ids),
        ground_truth_instances=sum(support.values()),
        macro_precision=float(np.mean([metric.precision for metric in per_class])),
        macro_recall=float(np.mean([metric.recall for metric in per_class])),
        map50=map50,
        map50_95=map50_95,
        ap_small=_average_valid(precision_values[:, :, :, 1, -1]),
        ap_medium=_average_valid(precision_values[:, :, :, 2, -1]),
        ap_large=_average_valid(precision_values[:, :, :, 3, -1]),
        per_class=tuple(per_class),
    )
