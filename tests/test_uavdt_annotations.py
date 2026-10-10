import csv
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from evaluation.error_analysis import analyze_detection_errors
from evaluation.evaluation_config import DatasetSettings
from evaluation.evaluation_data import (
    UAVDT_IGNORE_POLICY,
    BoundingBox,
    EvaluationDataError,
    IgnoredRegion,
    PredictionRecord,
    load_evaluation_dataset,
)
from evaluation.evaluation_metrics import (
    calculate_count_metrics,
    calculate_detection_metrics,
)
from evaluation.final_quality_gate import _subset_dataset
from evaluation.uavdt_annotations import (
    convert_uavdt_manifest,
    read_sequence_attributes,
    read_uavdt_boxes,
)


def write_manifest(root, rows):
    with (root / "selection.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def selection(tmp_path):
    (tmp_path / "gt").mkdir()
    (tmp_path / "attributes/train").mkdir(parents=True)
    (tmp_path / "attributes/train/M0101_attr.txt").write_text(
        "1,0,0,0,1,0,1,1,0,0\n", encoding="utf-8"
    )
    (tmp_path / "gt/M0101_gt_whole.txt").write_text(
        "1,1,10,10,10,10,1,1,1\n1,2,30,30,10,10,2,2,2\n1,3,50,50,10,10,3,4,3\n",
        encoding="utf-8",
    )
    (tmp_path / "gt/M0101_gt_ignore.txt").write_text(
        "1,4,60,0,30,30,1,-1,-1\n", encoding="utf-8"
    )
    image_path = tmp_path / "image.png"
    assert cv2.imwrite(str(image_path), np.zeros((80, 100, 3), dtype=np.uint8))
    row = {
        "asset_id": "uavdt_M0101_000001",
        "dataset_version": "uavdt-day-v1",
        "collection_id": "uavdt",
        "source_group_id": "M0101",
        "dataset_role": "validation",
        "source_split": "train",
        "evaluation_image_path": "image.png",
        "width": "100",
        "height": "80",
        "target_classes": "car_or_van;bus;truck",
        "annotation_type": "bounding_box",
        "canonical_annotation_path": "converted.json",
        "frame_number": "1",
        "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
    }
    write_manifest(tmp_path, [row])
    return row


def convert(root):
    return convert_uavdt_manifest(
        repository_root=root,
        manifest_path=Path("selection.csv"),
        gt_directory=Path("gt"),
        attributes_directory=Path("attributes"),
        role="validation",
        output_path=Path("converted.json"),
    )


def load(root):
    return load_evaluation_dataset(
        root, DatasetSettings("uavdt-day-v1", "validation", Path("selection.csv"))
    )


def test_conversion_preserves_native_labels_attributes_and_provenance(
    tmp_path, selection
):
    result = convert(tmp_path)
    assert [a["category_id"] for a in result["annotations"]] == [4, 6, 5]
    truck_attributes = result["annotations"][1]["source_attributes"]
    assert truck_attributes["occlusion"] == "large"
    assert truck_attributes["out_of_view"] == "medium"
    assert result["annotations"][2]["source_attributes"]["occlusion"] == "small"
    assert result["images"][0]["frame_number"] == 1
    assert result["images"][0]["source_attributes"]["side_view"] == 1
    assert result["info"]["coordinate_policy"] == "source_xywh_unmodified"
    assert (
        result["info"]["selection_manifest_sha256"]
        == hashlib.sha256((tmp_path / "selection.csv").read_bytes()).hexdigest()
    )
    assert len(result["info"]["source_files"]) == 3
    dataset = load(tmp_path)
    assert dataset.ignore_policy == UAVDT_IGNORE_POLICY
    assert len(dataset.ignored_regions) == 1
    assert [b.project_class for b in dataset.ground_truth_boxes] == [
        "car_or_van",
        "truck",
        "bus",
    ]
    assert dataset.ground_truth_boxes[0].box.as_xywh() == (10, 10, 10, 10)
    assert len(_subset_dataset(dataset, {selection["asset_id"]}).ignored_regions) == 1


@pytest.mark.parametrize(
    "line",
    [
        "1,1,1,1,10,10,1,1",
        "0,1,1,1,10,10,1,1,1",
        "1,0,1,1,10,10,1,1,1",
        "1,1,1,1,0,10,1,1,1",
        "1,1,nan,1,10,10,1,1,1",
        "1,1,1,1,10,10,4,1,1",
        "1,1,1,1,10,10,1,5,1",
        "1,1,1,1,10,10,1,1,4",
        "1,1,1,1,10,10,1,1,1\n1,1,2,2,10,10,1,1,1",
    ],
)
def test_malformed_det_rows_fail_with_line_context(tmp_path, line):
    path = tmp_path / "M0101_gt_whole.txt"
    path.write_text(line, encoding="utf-8")
    with pytest.raises(ValueError, match=r"M0101_gt_whole.txt:\d:"):
        read_uavdt_boxes(path)


def test_mot_file_cannot_be_parsed_as_det(tmp_path):
    with pytest.raises(ValueError, match="not MOT"):
        read_uavdt_boxes(tmp_path / "M0101_gt.txt")


def test_missing_ignore_file_is_not_an_empty_exclusion_set(tmp_path, selection):
    (tmp_path / "gt/M0101_gt_ignore.txt").unlink()
    with pytest.raises(FileNotFoundError):
        convert(tmp_path)
    assert not (tmp_path / "converted.json").exists()


def test_empty_ignore_file_is_valid_but_empty_det_is_not(tmp_path, selection):
    path = tmp_path / "gt/M0101_gt_ignore.txt"
    path.write_text("", encoding="utf-8")
    assert read_uavdt_boxes(path, ignored=True) == ()
    assert convert(tmp_path)["ignored_regions"] == []
    assert load(tmp_path).ignore_policy == UAVDT_IGNORE_POLICY
    path = tmp_path / "gt/M0101_gt_whole.txt"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        read_uavdt_boxes(path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("frame_number", "2", "no DET labels"),
        ("width", "99", "dimensions"),
        ("image_sha256", "0" * 64, "checksum"),
        ("evaluation_image_path", "../image.png", "relative"),
        ("source_split", "test", "split/role"),
        ("dataset_role", "held_out_test", "split/role"),
        ("dataset_version", "1.0", "separate dataset version"),
        ("target_classes", "car_or_van;bus;truck;person", "targets only"),
        ("canonical_annotation_path", "historical.json", "output path"),
    ],
)
def test_invalid_selection_fails_before_writing(
    tmp_path, selection, field, value, message
):
    selection[field] = value
    write_manifest(tmp_path, [selection])
    with pytest.raises(ValueError, match=message):
        convert(tmp_path)
    assert not (tmp_path / "converted.json").exists()


def test_existing_output_is_not_overwritten(tmp_path, selection):
    output = tmp_path / "converted.json"
    output.write_text("preserved", encoding="utf-8")
    with pytest.raises(FileExistsError, match="overwrite"):
        convert(tmp_path)
    assert output.read_text(encoding="utf-8") == "preserved"


def test_empty_image_with_matching_hash_is_still_invalid(tmp_path, selection):
    (tmp_path / "image.png").write_bytes(b"")
    selection["image_sha256"] = hashlib.sha256(b"").hexdigest()
    write_manifest(tmp_path, [selection])
    with pytest.raises(ValueError, match="Image is empty"):
        convert(tmp_path)
    assert not (tmp_path / "converted.json").exists()


def test_duplicate_frames_and_sequence_leakage_are_rejected(tmp_path, selection):
    second = dict(selection, asset_id="second")
    write_manifest(tmp_path, [selection, second])
    with pytest.raises(ValueError, match="duplicate"):
        convert(tmp_path)
    second.update(frame_number="2", dataset_role="training")
    write_manifest(tmp_path, [selection, second])
    with pytest.raises(ValueError, match="cannot cross dataset roles"):
        convert(tmp_path)


def test_native_test_split_cannot_be_used_for_validation(tmp_path, selection):
    (tmp_path / "attributes/test").mkdir()
    (tmp_path / "attributes/train/M0101_attr.txt").rename(
        tmp_path / "attributes/test/M0101_attr.txt"
    )
    selection["source_split"] = "test"
    write_manifest(tmp_path, [selection])
    with pytest.raises(ValueError, match="split/role"):
        convert(tmp_path)


def test_night_or_fog_sequence_is_not_selected(tmp_path, selection):
    (tmp_path / "attributes/train/M0101_attr.txt").write_text(
        "0,1,0,0,1,0,1,1,0,0\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="daytime subset"):
        convert(tmp_path)


def test_release_attribute_filename_space_is_handled(tmp_path):
    (tmp_path / "test").mkdir()
    (tmp_path / "test/M0701 _attr.txt").write_text(
        "0,0,1,0,0,1,0,0,1,0", encoding="utf-8"
    )
    metadata = read_sequence_attributes(tmp_path)["M0701"]
    assert metadata["split"] == "test"
    assert metadata["path"].name == "M0701 _attr.txt"


def predictions_for(dataset):
    return [
        PredictionRecord(b.asset_id, b.project_class, b.project_class, 0.9, b.box)
        for b in dataset.ground_truth_boxes
    ]


def detection(dataset, predictions):
    return calculate_detection_metrics(
        dataset,
        predictions,
        confidence_floor=0.001,
        operating_confidence=0.5,
        operating_iou=0.5,
        max_detections=300,
        low_support_threshold=20,
    )


def counts(dataset, predictions):
    return {
        m.class_name: m
        for m in calculate_count_metrics(
            dataset,
            predictions,
            operating_confidence=0.5,
            low_support_threshold=20,
        )
    }


@pytest.mark.parametrize(
    ("box", "excluded"),
    [
        ((70, 10, 5, 5), True),  # Strict interior.
        ((60, 10, 5, 5), False),  # Left edge.
        ((70, 0, 5, 5), False),  # Top edge.
        ((85, 10, 5, 5), False),  # Right edge.
        ((70, 25, 5, 5), False),  # Bottom edge.
        ((60, 0, 30, 30), False),  # Identical rectangle.
        ((58, 10, 5, 5), False),  # Partial overlap.
        ((1, 60, 5, 5), False),  # Disjoint.
    ],
)
def test_ignore_policy_is_identical_for_detection_counts_and_error_analysis(
    tmp_path, selection, box, excluded
):
    convert(tmp_path)
    dataset = load(tmp_path)
    predictions = predictions_for(dataset) + [
        PredictionRecord(
            selection["asset_id"], "car", "car_or_van", 0.99, BoundingBox(*box)
        )
    ]
    result = detection(dataset, predictions)
    car = next(m for m in result.per_class if m.class_name == "car_or_van")
    count = counts(dataset, predictions)["road_vehicle_total"]
    assert car.true_positives == 1
    assert car.false_positives == (0 if excluded else 1)
    assert count.ground_truth_total == 3
    assert count.predicted_total == (3 if excluded else 4)
    if excluded:
        assert result.map50_95 == pytest.approx(1)
        assert count.normalized_absolute_error == 0
    errors = analyze_detection_errors(
        dataset,
        predictions,
        confidence_floor=0.001,
        operating_confidence=0.5,
        operating_iou=0.5,
        max_detections=300,
    )
    assert errors.false_positives == car.false_positives


def test_labelled_boxes_inside_ignored_regions_remain_ground_truth(tmp_path, selection):
    convert(tmp_path)
    dataset = load(tmp_path)
    dataset = replace(
        dataset,
        ignored_regions=(
            IgnoredRegion(selection["asset_id"], BoundingBox(0, 0, 25, 25)),
        ),
    )
    predictions = predictions_for(dataset)
    result = detection(dataset, predictions)
    assert result.ground_truth_instances == 3
    assert result.per_class[0].false_negatives == 1
    assert counts(dataset, predictions)["car_or_van"].ground_truth_total == 1


def test_absent_regions_leave_historical_metric_behavior_unchanged(tmp_path, selection):
    convert(tmp_path)
    dataset = replace(load(tmp_path), ignored_regions=(), ignore_policy=None)
    predictions = predictions_for(dataset)
    explicit_empty = replace(dataset, ignore_policy=UAVDT_IGNORE_POLICY)
    assert detection(dataset, predictions) == detection(explicit_empty, predictions)
    assert counts(dataset, predictions) == counts(explicit_empty, predictions)


@pytest.mark.parametrize("policy", [None, "iou_0.5"])
def test_unknown_or_implicit_ignore_policy_is_rejected(tmp_path, selection, policy):
    result = convert(tmp_path)
    result["ignore_policy"] = policy
    (tmp_path / "converted.json").write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(EvaluationDataError, match="policy"):
        load(tmp_path)


@pytest.mark.parametrize("field", ["iscrowd", "ignore"])
def test_coco_crowd_flags_are_not_silently_treated_as_normal_boxes(
    tmp_path, selection, field
):
    result = convert(tmp_path)
    result["annotations"][0][field] = 1
    (tmp_path / "converted.json").write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(EvaluationDataError, match="crowd/ignore"):
        load(tmp_path)


def test_converter_cli_runs_and_reports_missing_input(tmp_path, selection):
    command = [
        sys.executable,
        "scripts/convert_uavdt_annotations.py",
        "--repository-root",
        str(tmp_path),
        "--manifest",
        "selection.csv",
        "--gt-directory",
        "gt",
        "--attributes-directory",
        "attributes",
        "--role",
        "validation",
        "--output",
        "converted.json",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=True)
    assert "Converted 1 frames, 3 boxes and 1 ignored regions." in completed.stdout
    completed = subprocess.run(command, capture_output=True, text=True)
    assert completed.returncode == 1
    assert "Refusing to overwrite" in completed.stderr


@pytest.mark.parametrize(
    "box", [(float("nan"), 0, 1, 1), (0, float("inf"), 1, 1), (0, 0, float("inf"), 1)]
)
def test_nonfinite_geometry_cannot_bypass_exclusions(box):
    with pytest.raises(ValueError, match="finite"):
        BoundingBox(*box)


@pytest.mark.parametrize(
    "region",
    [
        None,
        {"image_id": 999, "bbox": [0, 0, 10, 10]},
        {"image_id": 1, "bbox": [0, 0, 0, 10]},
        {"image_id": 1, "bbox": [0, 0, float("nan"), 10]},
    ],
)
def test_invalid_canonical_ignored_regions_are_rejected(tmp_path, selection, region):
    result = convert(tmp_path)
    result["ignored_regions"] = [region]
    (tmp_path / "converted.json").write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(EvaluationDataError, match="Ignored region"):
        load(tmp_path)


def test_ignore_regions_are_per_image_not_global(tmp_path, selection):
    convert(tmp_path)
    dataset = load(tmp_path)
    second_asset = replace(dataset.assets[0], asset_id="second")
    second_label = replace(dataset.ground_truth_boxes[0], asset_id="second")
    dataset = replace(
        dataset,
        assets=(*dataset.assets, second_asset),
        ground_truth_boxes=(*dataset.ground_truth_boxes, second_label),
    )
    predictions = predictions_for(dataset) + [
        PredictionRecord("second", "car", "car_or_van", 0.9, BoundingBox(70, 10, 5, 5))
    ]
    assert counts(dataset, predictions)["car_or_van"].predicted_total == 3
    assert detection(dataset, predictions).per_class[0].false_positives == 1
    assert _subset_dataset(dataset, {"second"}).ignored_regions == ()
    unknown = [replace(predictions[-1], asset_id="missing")]
    with pytest.raises(ValueError, match="unknown asset"):
        detection(dataset, unknown)
    with pytest.raises(ValueError, match="unknown asset"):
        counts(dataset, unknown)
