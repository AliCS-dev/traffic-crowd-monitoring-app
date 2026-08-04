from pathlib import Path

import pytest

from evaluation.evaluation_config import ClassMapping
from evaluation.evaluation_data import (
    BoundingBox,
    EvaluationAsset,
    create_prediction_record,
    parse_target_classes,
)


def create_asset() -> EvaluationAsset:
    return EvaluationAsset(
        asset_id="traffic_frame_1",
        collection_id="traffic_uav",
        source_group_id="roundabout_1",
        dataset_role="validation",
        image_path=Path("data/evaluation/raw/frame.png"),
        width=100,
        height=80,
        annotation_type="bounding_box",
        target_classes=frozenset({"car_or_van", "motorcycle"}),
    )


def test_target_classes_are_parsed_from_manifest_format():
    assert parse_target_classes("car_or_van;motorcycle") == frozenset(
        {"car_or_van", "motorcycle"}
    )


def test_unknown_target_class_is_rejected():
    with pytest.raises(ValueError, match="Unknown target classes"):
        parse_target_classes("car_or_van;train")


def test_unknown_dataset_role_is_rejected():
    values = create_asset().__dict__ | {"dataset_role": "tuning"}

    with pytest.raises(ValueError, match="Unknown dataset role"):
        EvaluationAsset(**values)


def test_processed_box_is_restored_and_clipped_to_original_coordinates():
    box = BoundingBox.from_xyxy(20, 10, 220, 180)

    restored = box.to_original_coordinates(
        scale_factor=2, image_width=100, image_height=80
    )

    assert restored.as_xyxy() == pytest.approx((10, 5, 100, 80))


def test_prediction_keeps_raw_class_and_maps_supported_class():
    mapping = ClassMapping.from_dict({"car": "car_or_van"})

    prediction = create_prediction_record(
        asset=create_asset(),
        source_class="car",
        confidence=0.91,
        processed_box=BoundingBox(20, 10, 40, 30),
        scale_factor=2,
        class_mapping=mapping,
    )

    assert prediction.source_class == "car"
    assert prediction.project_class == "car_or_van"
    assert prediction.box.as_xywh() == pytest.approx((10, 5, 20, 15))
    assert create_asset().includes_class(prediction.project_class)


def test_non_target_model_class_is_retained_without_project_mapping():
    prediction = create_prediction_record(
        asset=create_asset(),
        source_class="train",
        confidence=0.72,
        processed_box=BoundingBox(10, 10, 20, 20),
        scale_factor=2,
        class_mapping=ClassMapping.from_dict({"car": "car_or_van"}),
    )

    assert prediction.source_class == "train"
    assert prediction.project_class is None
    assert not create_asset().includes_class(prediction.project_class)
