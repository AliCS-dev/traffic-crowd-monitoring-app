import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from evaluation import error_analysis
from evaluation import uavdt_error_review as review
from evaluation.confidence_sweep import SourceEvaluationRun
from evaluation.error_analysis import DetectionError, DetectionErrorAnalysis
from evaluation.evaluation_config import load_evaluation_config
from evaluation.evaluation_data import (
    UAVDT_IGNORE_POLICY,
    BoundingBox,
    EvaluationAsset,
    EvaluationDataset,
    GroundTruthBox,
    IgnoredRegion,
    PredictionRecord,
)
from evaluation.evaluation_runner import PredictionBatch


@pytest.fixture
def sample(tmp_path):
    image = tmp_path / "image.png"
    assert cv2.imwrite(str(image), np.full((540, 1024, 3), 120, dtype=np.uint8))
    asset = EvaluationAsset(
        "first",
        "uavdt",
        "M0207",
        "validation",
        image,
        1024,
        540,
        "bounding_box",
        frozenset(review.CATEGORY_IDS),
    )
    box = BoundingBox(50, 50, 20, 20)
    dataset = EvaluationDataset(
        "validation",
        "test",
        (asset, replace(asset, asset_id="empty", source_group_id="M0001")),
        (GroundTruthBox("first", "bus", box),),
        (),
        (IgnoredRegion("first", BoundingBox(0, 0, 30, 30)),),
        UAVDT_IGNORE_POLICY,
    )
    predictions = [
        PredictionRecord("first", "bus", "bus", 0.8, box),
        PredictionRecord("first", "truck", "truck", 0.9, BoundingBox(5, 5, 10, 10)),
        PredictionRecord("first", "car", "car_or_van", 0.25, BoundingBox(0, 0, 20, 20)),
        PredictionRecord("first", "person", "person", 0.7, box),
        PredictionRecord("first", "truck", "truck", 0.01, box),
    ]
    return dataset, predictions


def test_inventory_separates_ignore_scope_threshold_and_cap(sample):
    dataset, predictions = sample
    result = review.prediction_inventory(
        dataset, predictions, confidence=0.25, max_detections=5
    )
    assert result["raw_predictions"] == 5
    assert result["ignored_predictions_at_floor"] == 1
    assert result["operating_target_predictions"] == 2
    assert result["images_at_candidate_cap"] == 1
    assert result["capped_tail_min"] == 0.01
    assert result["capped_images_with_tail_at_or_above_operating_confidence"] == 0
    assert result["images"][0]["predicted"] == {"car_or_van": 1, "bus": 1, "truck": 0}
    assert result["images"][0]["reference"]["bus"] == 1
    assert result["images"][1]["lowest_saved_confidence"] is None


def test_empty_and_operating_saturated_inventory(sample):
    dataset, predictions = sample
    empty = review.prediction_inventory(dataset, [], confidence=0.25, max_detections=5)
    assert empty["capped_tail_min"] is None
    assert empty["capped_tail_max"] is None
    result = review.prediction_inventory(
        dataset, predictions[:1], confidence=0.25, max_detections=1
    )
    assert result["capped_images_with_tail_at_or_above_operating_confidence"] == 1


def test_bus_truck_selection_is_deterministic_bounded_and_deduplicated():
    def error(index, expected, predicted, kind):
        return DetectionError(
            str(index),
            kind,
            f"asset-{index}",
            "uavdt",
            f"scene-{index}",
            expected,
            predicted,
            0.9,
            0.8,
            BoundingBox(1, 1, 2, 2),
            BoundingBox(1, 1, 2, 2),
            "small",
        )

    errors = [error(i, None, "bus", "false_positive") for i in range(6)]
    errors += [
        error(10, "bus", "truck", "class_confusion"),
        error(11, None, "car_or_van", "false_positive"),
    ]
    analysis = DetectionErrorAnalysis(0, 8, 1, tuple(errors))
    selected = review.select_bus_truck_errors(analysis)
    assert len(selected) == 4
    assert sum(e.error_id == "10" for e in selected) == 1
    assert all(e.error_id != "11" for e in selected)
    assert (
        review.select_bus_truck_errors(
            replace(analysis, errors=tuple(reversed(errors)))
        )
        == selected
    )


def test_sequence_comparison_renders_only_requested_scene(sample, tmp_path):
    dataset, predictions = sample
    original = dataset.assets[0].image_path.read_bytes()
    paths = review.render_sequence_comparisons(
        dataset, predictions, tmp_path / "out", confidence=0.25
    )
    assert paths == ["m0207/first.png"]
    rendered = cv2.imread(str(tmp_path / "out" / paths[0]))
    assert rendered.shape == (625, 2048, 3)
    assert rendered.std() > 0
    assert dataset.assets[0].image_path.read_bytes() == original


@pytest.mark.parametrize("failure", ["path", "run_id", "hash", "readiness"])
def test_invalid_source_is_rejected_before_rendering(tmp_path, monkeypatch, failure):
    baseline = {
        "source_run_directory": "data/run",
        "source_run_id": "expected",
        "source_manifest_sha256": "hash",
        "provenance": {"source_evaluation_readiness": {"ready": True}},
    }
    if failure == "path":
        baseline["source_run_directory"] = "../outside"
    path = tmp_path / review.BASELINE_RECORD
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(baseline))
    source = SimpleNamespace(
        run_id="changed" if failure == "run_id" else "expected",
        manifest_sha256="changed" if failure == "hash" else "hash",
        config=object(),
    )
    loader = Mock(return_value=source)
    monkeypatch.setattr(review, "load_source_evaluation_run", loader)
    monkeypatch.setattr(review, "verify_source_dataset_identity", Mock())
    monkeypatch.setattr(
        review, "validate_uavdt_evaluation", Mock(return_value={"ready": False})
    )
    render = Mock()
    monkeypatch.setattr(review, "save_error_analysis", render)
    with pytest.raises(ValueError):
        review.review_saved_baseline(tmp_path)
    render.assert_not_called()
    if failure == "path":
        loader.assert_not_called()


def test_complete_saved_review_and_artifact_manifest(sample, tmp_path, monkeypatch):
    dataset, predictions = sample
    config = load_evaluation_config(
        Path("configs/evaluation/uavdt_daytime_baseline.json")
    )
    source = SourceEvaluationRun(
        "baseline",
        "hash",
        config,
        PredictionBatch(tuple(a.asset_id for a in dataset.assets), tuple(predictions)),
        "manifest",
        (),
    )
    baseline = {
        "source_run_directory": "data/run",
        "source_run_id": "baseline",
        "source_manifest_sha256": "hash",
        "provenance": {"source_evaluation_readiness": {"ready": True}},
        "metrics": {
            "detection": {
                "per_class": [
                    {"true_positives": 1, "false_positives": 1, "false_negatives": 0}
                ]
            }
        },
    }
    path = tmp_path / review.BASELINE_RECORD
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(baseline))
    monkeypatch.setattr(review, "load_source_evaluation_run", Mock(return_value=source))
    monkeypatch.setattr(review, "verify_source_dataset_identity", Mock())
    monkeypatch.setattr(
        review, "validate_uavdt_evaluation", Mock(return_value={"ready": True})
    )
    monkeypatch.setattr(review, "load_evaluation_dataset", Mock(return_value=dataset))
    monkeypatch.setattr(error_analysis, "_provenance", lambda _: {"synthetic": True})
    output = review.review_saved_baseline(tmp_path)
    record = json.loads((output / "review.json").read_text())
    assert record["new_inference_run"] is False
    assert record["annotations_changed"] is False
    assert record["human_annotation_review"] is False
    assert record["matching_totals"]["true_positives"] == 1
    assert record["inventory"]["operating_target_predictions"] == 2
    assert record["sequence_comparisons"] == ["m0207/first.png"]
    manifest = json.loads((output / "review_manifest.json").read_text())
    for item in manifest["artifacts"]:
        assert review.file_sha256(output / item["path"]) == item["sha256"]
