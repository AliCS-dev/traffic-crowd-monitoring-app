import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest

from evaluation.confidence_sweep import SourceEvaluationRun
from evaluation.error_analysis import (
    ErrorAnalysisError,
    analyze_count_errors,
    analyze_detection_errors,
    create_error_analysis_result,
    load_error_analysis_config,
    parse_error_analysis_config,
    save_error_analysis,
)
from evaluation.evaluation_config import load_evaluation_config
from evaluation.evaluation_data import (
    BoundingBox,
    CountReference,
    EvaluationAsset,
    EvaluationDataset,
    GroundTruthBox,
    PredictionRecord,
)
from evaluation.evaluation_runner import PredictionBatch

BASE_CONFIG_PATH = Path("configs/evaluation/yolo26n_validation.json")
ANALYSIS_CONFIG_PATH = Path("configs/evaluation/yolo26n_error_analysis.json")


def test_tracked_error_analysis_configuration_is_strict():
    config = load_error_analysis_config(ANALYSIS_CONFIG_PATH)

    assert config.dataset_role == "validation"
    assert config.operating_confidence == 0.25
    assert config.operating_iou == 0.5
    assert config.cases_per_error_type == 6

    values = read_json(ANALYSIS_CONFIG_PATH)
    values["unexpected"] = True
    with pytest.raises(ErrorAnalysisError, match="unknown"):
        parse_error_analysis_config(values)


def test_detection_errors_use_coco_matches_and_link_class_confusions(tmp_path):
    dataset, predictions = create_fixture(tmp_path)

    analysis = analyze_detection_errors(
        dataset,
        list(predictions),
        confidence_floor=0.001,
        operating_confidence=0.25,
        operating_iou=0.5,
        max_detections=300,
    )

    assert analysis.true_positives == 1
    assert analysis.false_positives == 2
    assert analysis.false_negatives == 3
    assert [error.error_type for error in analysis.errors] == [
        "class_confusion",
        "excluded_label_confusion",
        "false_negative",
        "false_positive",
    ]
    confusion = analysis.errors[0]
    assert confusion.expected_class == "person"
    assert confusion.predicted_class == "car_or_van"
    assert confusion.iou == pytest.approx(1.0)


def test_count_only_errors_remain_separate_from_box_matching(tmp_path):
    dataset, predictions = create_fixture(tmp_path)

    errors = analyze_count_errors(dataset, list(predictions), operating_confidence=0.25)

    assert len(errors) == 1
    assert errors[0].asset_id == "crowd-scene"
    assert errors[0].ground_truth_count == 100
    assert errors[0].predicted_count == 1
    assert errors[0].signed_error == -99
    assert errors[0].normalized_absolute_error == pytest.approx(0.99)


def test_complete_analysis_matches_metrics_and_enforces_configured_role(tmp_path):
    dataset, predictions = create_fixture(tmp_path)
    source = create_source(predictions)
    config = load_error_analysis_config(ANALYSIS_CONFIG_PATH)

    result = create_error_analysis_result(dataset, source, config)

    assert result.dataset_role == "validation"
    assert len(result.selected_detection_error_ids) == 4
    assert result.selected_count_asset_ids == ("crowd-scene",)

    held_out = replace(dataset, role="held_out_test")
    with pytest.raises(ErrorAnalysisError, match="must use the same role"):
        create_error_analysis_result(held_out, source, config)


def test_complete_analysis_accepts_explicit_held_out_configuration(tmp_path):
    dataset, predictions = create_fixture(tmp_path)
    held_out_dataset = replace(
        dataset,
        role="held_out_test",
        assets=tuple(
            replace(asset, dataset_role="held_out_test") for asset in dataset.assets
        ),
    )
    source = create_source(predictions)
    held_out_source = replace(
        source,
        config=replace(
            source.config,
            dataset=replace(source.config.dataset, role="held_out_test"),
        ),
    )
    config = replace(
        load_error_analysis_config(ANALYSIS_CONFIG_PATH),
        dataset_role="held_out_test",
    )

    result = create_error_analysis_result(held_out_dataset, held_out_source, config)

    assert result.dataset_role == "held_out_test"


def test_error_analysis_saves_images_report_and_checksums(tmp_path):
    dataset, predictions = create_fixture(tmp_path)
    source = create_source(predictions)
    config = load_error_analysis_config(ANALYSIS_CONFIG_PATH)
    result = create_error_analysis_result(dataset, source, config)

    saved = save_error_analysis(
        tmp_path,
        config,
        result,
        dataset,
        source,
        created_at=datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc),
        provenance={"git": {"commit": "abc123", "dirty": False}},
    )

    assert saved.analysis_id == "20260805T150000Z-yolo26n-validation-error-analysis"
    analysis = read_json(saved.output_directory / "analysis.json")
    assert analysis["analysis"]["detection"]["true_positives"] == 1
    assert len(analysis["rendered_cases"]) == 5
    summary = saved.summary_path.read_text(encoding="utf-8")
    assert "Cross-class confusions | 1" in summary
    assert "Count-only annotations" in summary
    manifest = read_json(saved.output_directory / "analysis_manifest.json")
    assert len(manifest["artifacts"]) == 9
    for record in manifest["artifacts"]:
        path = saved.output_directory / record["filename"]
        assert path.is_file()
        assert sha256(path) == record["sha256"]
    detection_image = next(
        saved.output_directory / record["filename"]
        for record in manifest["artifacts"]
        if record["filename"].startswith("cases/detection/")
    )
    rendered = cv2.imread(str(detection_image), cv2.IMREAD_COLOR)
    assert rendered is not None
    assert rendered.shape[0] > 100
    assert np.any(rendered != rendered[0, 0])


def create_fixture(
    tmp_path: Path,
) -> tuple[EvaluationDataset, tuple[PredictionRecord, ...]]:
    detection_path = tmp_path / "detection.png"
    crowd_path = tmp_path / "crowd.png"
    image = np.full((200, 200, 3), 180, dtype=np.uint8)
    cv2.line(image, (0, 100), (199, 100), (90, 90, 90), 18)
    assert cv2.imwrite(str(detection_path), image)
    assert cv2.imwrite(str(crowd_path), image)
    detection_asset = EvaluationAsset(
        asset_id="detection-scene",
        collection_id="fixture",
        source_group_id="traffic-group",
        dataset_role="validation",
        image_path=detection_path,
        width=200,
        height=200,
        annotation_type="bounding_box",
        target_classes=frozenset({"person", "motorcycle", "car_or_van", "bus"}),
    )
    crowd_asset = EvaluationAsset(
        asset_id="crowd-scene",
        collection_id="fixture",
        source_group_id="crowd-group",
        dataset_role="validation",
        image_path=crowd_path,
        width=200,
        height=200,
        annotation_type="point_count",
        target_classes=frozenset({"person"}),
    )
    car_box = BoundingBox(10, 10, 30, 20)
    person_box = BoundingBox(70, 20, 15, 30)
    motorcycle_box = BoundingBox(120, 100, 20, 15)
    bus_box = BoundingBox(100, 40, 50, 30)
    dataset = EvaluationDataset(
        role="validation",
        version="1.0-draft",
        assets=(detection_asset, crowd_asset),
        ground_truth_boxes=(
            GroundTruthBox("detection-scene", "car_or_van", car_box),
            GroundTruthBox("detection-scene", "person", person_box),
            GroundTruthBox("detection-scene", "motorcycle", motorcycle_box),
            GroundTruthBox("detection-scene", "bus", bus_box),
        ),
        count_references=(CountReference("crowd-scene", "person", 100),),
    )
    predictions = (
        PredictionRecord("detection-scene", "car", "car_or_van", 0.9, car_box),
        PredictionRecord("detection-scene", "car", "car_or_van", 0.8, person_box),
        PredictionRecord(
            "detection-scene",
            "motorcycle",
            "motorcycle",
            0.7,
            BoundingBox(160, 160, 15, 12),
        ),
        PredictionRecord("detection-scene", "train", None, 0.6, motorcycle_box),
        PredictionRecord(
            "crowd-scene", "person", "person", 0.9, BoundingBox(30, 30, 10, 20)
        ),
    )
    return dataset, predictions


def create_source(predictions: tuple[PredictionRecord, ...]) -> SourceEvaluationRun:
    return SourceEvaluationRun(
        run_id="source-run",
        manifest_sha256="manifest-hash",
        config=load_evaluation_config(BASE_CONFIG_PATH),
        predictions=PredictionBatch(("detection-scene", "crowd-scene"), predictions),
        dataset_manifest_sha256="dataset-hash",
        annotation_files=(("annotations/validation.json", "annotation-hash"),),
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
