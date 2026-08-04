from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from evaluation.evaluation_config import load_evaluation_config
from evaluation.evaluation_data import EvaluationAsset, EvaluationDataset
from evaluation.evaluation_runner import (
    EvaluationRunnerError,
    generate_predictions,
)

CONFIG_PATH = Path("configs/evaluation/yolo26n_validation.json")


class FakeDetector:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def detect(self, image, confidence_threshold, image_size, **options):
        self.calls.append(
            {
                "image": image,
                "confidence_threshold": confidence_threshold,
                "image_size": image_size,
                **options,
            }
        )
        return next(self.results)


def result_with_boxes():
    return SimpleNamespace(
        names={0: "car", 1: "train"},
        boxes=[
            SimpleNamespace(cls=[0], conf=[0.9], xyxy=[[2.0, 2.0, 6.0, 4.0]]),
            SimpleNamespace(cls=[1], conf=[0.7], xyxy=[[0.0, 0.0, 4.0, 4.0]]),
        ],
    )


def write_image(path: Path, width: int = 4, height: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.zeros((height, width, 3), dtype=np.uint8)
    assert cv2.imwrite(str(path), image)


def create_dataset(tmp_path: Path) -> EvaluationDataset:
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    write_image(first_path)
    write_image(second_path)
    assets = tuple(
        EvaluationAsset(
            asset_id=asset_id,
            collection_id="fixture",
            source_group_id=asset_id,
            dataset_role="validation",
            image_path=image_path,
            width=4,
            height=3,
            annotation_type="bounding_box",
            target_classes=frozenset({"car_or_van"}),
        )
        for asset_id, image_path in (
            ("first", first_path),
            ("second", second_path),
        )
    )
    return EvaluationDataset("validation", "1.0-draft", assets, (), ())


def test_runner_processes_every_asset_and_normalises_predictions(tmp_path: Path):
    detector = FakeDetector(
        [[result_with_boxes()], [SimpleNamespace(names={}, boxes=[])]]
    )
    config = load_evaluation_config(CONFIG_PATH)

    batch = generate_predictions(create_dataset(tmp_path), detector, config)

    assert batch.asset_ids == ("first", "second")
    assert batch.processed_assets == 2
    assert len(batch.predictions) == 2
    car, train = batch.predictions
    assert car.source_class == "car"
    assert car.project_class == "car_or_van"
    assert car.box.as_xyxy() == pytest.approx((1, 1, 3, 2))
    assert train.source_class == "train"
    assert train.project_class is None
    assert train.box.as_xyxy() == pytest.approx((0, 0, 2, 2))
    assert len(detector.calls) == 2
    assert detector.calls[0]["image"].shape == (6, 8, 3)
    assert detector.calls[0]["confidence_threshold"] == 0.001
    assert detector.calls[0]["image_size"] == 1280
    assert detector.calls[0]["device"] == "cuda:0"
    assert detector.calls[0]["max_detections"] == 300
    assert detector.calls[0]["half_precision"] is False
    assert detector.calls[0]["verbose"] is False


def test_runner_rejects_manifest_dimension_mismatch(tmp_path: Path):
    dataset = create_dataset(tmp_path)
    incorrect_asset = replace(dataset.assets[0], width=5)
    dataset = replace(dataset, assets=(incorrect_asset,))
    detector = FakeDetector([[result_with_boxes()]])

    with pytest.raises(EvaluationRunnerError, match="manifest records 5x3"):
        generate_predictions(dataset, detector, load_evaluation_config(CONFIG_PATH))

    assert detector.calls == []


def test_runner_identifies_asset_when_detector_returns_no_result(tmp_path: Path):
    dataset = create_dataset(tmp_path)
    dataset = replace(dataset, assets=(dataset.assets[0],))

    with pytest.raises(EvaluationRunnerError, match="asset first"):
        generate_predictions(
            dataset,
            FakeDetector([[]]),
            load_evaluation_config(CONFIG_PATH),
        )


def test_runner_rejects_dataset_role_mismatch(tmp_path: Path):
    dataset = replace(create_dataset(tmp_path), role="held_out_test")

    with pytest.raises(EvaluationRunnerError, match="does not match configured role"):
        generate_predictions(
            dataset,
            FakeDetector([]),
            load_evaluation_config(CONFIG_PATH),
        )
