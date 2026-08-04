from pathlib import Path

import pytest

from evaluation.evaluation_data import (
    BoundingBox,
    CountReference,
    EvaluationAsset,
    EvaluationDataset,
    GroundTruthBox,
    PredictionRecord,
)
from evaluation.evaluation_metrics import (
    calculate_count_metrics,
    calculate_detection_metrics,
)


def asset(asset_id: str, target_classes: set[str]) -> EvaluationAsset:
    return EvaluationAsset(
        asset_id=asset_id,
        collection_id="fixture",
        source_group_id=asset_id,
        dataset_role="validation",
        image_path=Path(f"images/{asset_id}.jpg"),
        width=100,
        height=80,
        annotation_type=(
            "point_count" if target_classes == {"person"} else "bounding_box"
        ),
        target_classes=frozenset(target_classes),
    )


def prediction(
    asset_id: str,
    project_class: str | None,
    confidence: float = 0.9,
    source_class: str = "car",
) -> PredictionRecord:
    return PredictionRecord(
        asset_id=asset_id,
        source_class=source_class,
        project_class=project_class,
        confidence=confidence,
        box=BoundingBox(1, 1, 10, 10),
    )


def create_dataset() -> EvaluationDataset:
    box = BoundingBox(1, 1, 10, 10)
    return EvaluationDataset(
        role="validation",
        version="1.0",
        assets=(
            asset("traffic_1", {"car_or_van", "motorcycle"}),
            asset("traffic_2", {"car_or_van", "motorcycle"}),
            asset("crowd_1", {"person"}),
        ),
        ground_truth_boxes=(
            GroundTruthBox("traffic_1", "car_or_van", box),
            GroundTruthBox("traffic_1", "car_or_van", box),
        ),
        count_references=(CountReference("crowd_1", "person", 100),),
    )


def result_by_name(predictions: list[PredictionRecord]):
    results = calculate_count_metrics(
        create_dataset(),
        predictions,
        operating_confidence=0.5,
        low_support_threshold=20,
    )
    return {result.class_name: result for result in results}


def test_count_metrics_include_zero_ground_truth_images():
    metrics = result_by_name(
        [
            prediction("traffic_1", "car_or_van"),
            prediction("traffic_2", "car_or_van"),
        ]
    )["car_or_van"]

    assert metrics.examples == 2
    assert metrics.ground_truth_total == 2
    assert metrics.predicted_total == 2
    assert metrics.mean_absolute_error == pytest.approx(1.0)
    assert metrics.normalized_absolute_error == pytest.approx(1.0)
    assert metrics.bias == pytest.approx(0.0)
    assert metrics.low_support is True


def test_person_count_metrics_use_point_count_reference():
    predictions = [prediction("crowd_1", "person") for _ in range(80)]

    metrics = result_by_name(predictions)["person"]

    assert metrics.examples == 1
    assert metrics.ground_truth_total == 100
    assert metrics.predicted_total == 80
    assert metrics.mean_absolute_error == pytest.approx(20)
    assert metrics.normalized_absolute_error == pytest.approx(0.2)
    assert metrics.bias == pytest.approx(-20)
    assert metrics.low_support is False


def test_scope_threshold_and_unmapped_predictions_are_excluded():
    predictions = [
        prediction("traffic_1", "car_or_van", confidence=0.49),
        prediction("traffic_1", "person"),
        prediction("traffic_1", None, source_class="train"),
    ]

    metrics = result_by_name(predictions)["car_or_van"]

    assert metrics.predicted_total == 0


def test_road_vehicle_total_combines_vehicle_classes():
    metrics = result_by_name(
        [
            prediction("traffic_1", "car_or_van"),
            prediction("traffic_1", "motorcycle", source_class="motorcycle"),
        ]
    )["road_vehicle_total"]

    assert metrics.ground_truth_total == 2
    assert metrics.predicted_total == 2
    assert metrics.mean_absolute_error == pytest.approx(0.0)


def test_normalized_error_is_absent_when_ground_truth_total_is_zero():
    metrics = result_by_name([])["motorcycle"]

    assert metrics.ground_truth_total == 0
    assert metrics.normalized_absolute_error is None


def create_detection_dataset() -> EvaluationDataset:
    first_box = BoundingBox(10, 10, 10, 10)
    second_box = BoundingBox(40, 40, 10, 10)
    return EvaluationDataset(
        role="validation",
        version="1.0",
        assets=(
            asset("traffic_1", {"car_or_van"}),
            asset("traffic_2", {"car_or_van"}),
            asset("crowd_1", {"person"}),
        ),
        ground_truth_boxes=(
            GroundTruthBox("traffic_1", "car_or_van", first_box),
            GroundTruthBox("traffic_2", "car_or_van", second_box),
        ),
        count_references=(CountReference("crowd_1", "person", 10),),
    )


def detection_metrics(predictions: list[PredictionRecord]):
    return calculate_detection_metrics(
        create_detection_dataset(),
        predictions,
        confidence_floor=0.001,
        operating_confidence=0.5,
        operating_iou=0.5,
        max_detections=300,
        low_support_threshold=20,
    )


def test_perfect_detections_produce_perfect_coco_metrics():
    result = detection_metrics(
        [
            PredictionRecord(
                "traffic_1", "car", "car_or_van", 0.9, BoundingBox(10, 10, 10, 10)
            ),
            PredictionRecord(
                "traffic_2", "car", "car_or_van", 0.8, BoundingBox(40, 40, 10, 10)
            ),
        ]
    )

    assert result.evaluated_images == 2
    assert result.ground_truth_instances == 2
    assert result.macro_precision == pytest.approx(1.0)
    assert result.macro_recall == pytest.approx(1.0)
    assert result.map50 == pytest.approx(1.0)
    assert result.map50_95 == pytest.approx(1.0)
    assert result.ap_small == pytest.approx(1.0)
    assert result.ap_medium is None
    assert result.per_class[0].class_name == "car_or_van"
    assert result.per_class[0].low_support is True


def test_confidence_floor_and_operating_threshold_remain_separate():
    result = detection_metrics(
        [
            PredictionRecord(
                "traffic_1", "car", "car_or_van", 0.9, BoundingBox(10, 10, 10, 10)
            ),
            PredictionRecord(
                "traffic_2", "car", "car_or_van", 0.2, BoundingBox(40, 40, 10, 10)
            ),
        ]
    )

    assert result.map50 == pytest.approx(1.0)
    assert result.macro_precision == pytest.approx(1.0)
    assert result.macro_recall == pytest.approx(0.5)


def test_coco_matching_counts_false_positive_and_false_negative():
    result = detection_metrics(
        [
            PredictionRecord(
                "traffic_1", "car", "car_or_van", 0.9, BoundingBox(10, 10, 10, 10)
            ),
            PredictionRecord(
                "traffic_2", "car", "car_or_van", 0.8, BoundingBox(70, 70, 10, 10)
            ),
        ]
    )

    assert result.macro_precision == pytest.approx(0.5)
    assert result.macro_recall == pytest.approx(0.5)
    assert result.map50 == pytest.approx(0.5049505)
    assert result.per_class[0].true_positives == 1
    assert result.per_class[0].false_positives == 1
    assert result.per_class[0].false_negatives == 1


def test_count_only_and_out_of_scope_predictions_do_not_affect_detection_metrics():
    result = detection_metrics(
        [
            PredictionRecord(
                "traffic_1", "car", "car_or_van", 0.9, BoundingBox(10, 10, 10, 10)
            ),
            PredictionRecord(
                "traffic_2", "car", "car_or_van", 0.8, BoundingBox(40, 40, 10, 10)
            ),
            prediction("traffic_1", "person", source_class="person"),
            prediction("traffic_1", None, source_class="train"),
            prediction("crowd_1", "person", source_class="person"),
        ]
    )

    assert result.map50 == pytest.approx(1.0)
    assert [metric.class_name for metric in result.per_class] == ["car_or_van"]


def test_empty_predictions_are_a_zero_score_not_an_undefined_score():
    result = detection_metrics([])

    assert result.macro_precision == 0
    assert result.macro_recall == 0
    assert result.map50 == 0
    assert result.map50_95 == 0
