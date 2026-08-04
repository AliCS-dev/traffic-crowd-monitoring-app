import csv
import json
from pathlib import Path

import pytest

from evaluation.evaluation_config import DatasetSettings
from evaluation.evaluation_data import EvaluationDataError, load_evaluation_dataset


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_fixture(root: Path, *, dataset_version: str = "1.0") -> DatasetSettings:
    manifest_fields = [
        "asset_id",
        "dataset_version",
        "collection_id",
        "source_group_id",
        "dataset_role",
        "evaluation_image_path",
        "width",
        "height",
        "target_classes",
        "annotation_type",
        "canonical_annotation_path",
    ]
    write_csv(
        root / "manifest.csv",
        manifest_fields,
        [
            {
                "asset_id": "traffic_1",
                "dataset_version": dataset_version,
                "collection_id": "traffic_uav",
                "source_group_id": "traffic_group",
                "dataset_role": "validation",
                "evaluation_image_path": "images/traffic.png",
                "width": 100,
                "height": 80,
                "target_classes": "car_or_van;motorcycle",
                "annotation_type": "bounding_box",
                "canonical_annotation_path": "annotations/instances.json",
            },
            {
                "asset_id": "crowd_1",
                "dataset_version": dataset_version,
                "collection_id": "dlr_acd",
                "source_group_id": "crowd_group",
                "dataset_role": "validation",
                "evaluation_image_path": "images/crowd.jpg",
                "width": 120,
                "height": 90,
                "target_classes": "person",
                "annotation_type": "point_count",
                "canonical_annotation_path": "annotations/counts.csv",
            },
        ],
    )
    coco = {
        "categories": [
            {"id": 1, "name": "person"},
            {"id": 4, "name": "car_or_van"},
        ],
        "images": [{"id": 1, "asset_id": "traffic_1"}],
        "annotations": [
            {
                "id": 1,
                "image_id": 1,
                "category_id": 4,
                "bbox": [10, 20, 30, 15],
            },
            {"id": 2, "image_id": 1, "category_id": 1, "bbox": [5, 5, 10, 20]},
        ],
    }
    annotation_path = root / "annotations/instances.json"
    annotation_path.parent.mkdir(parents=True, exist_ok=True)
    annotation_path.write_text(json.dumps(coco), encoding="utf-8")
    write_csv(
        root / "annotations/counts.csv",
        ["asset_id", "dataset_role", "person_count"],
        [
            {
                "asset_id": "crowd_1",
                "dataset_role": "validation",
                "person_count": 42,
            },
            {
                "asset_id": "crowd_other_split",
                "dataset_role": "held_out_test",
                "person_count": 100,
            },
        ],
    )
    return DatasetSettings(
        version="1.0", role="validation", manifest_path=Path("manifest.csv")
    )


def test_selected_manifest_and_annotations_are_loaded(tmp_path: Path):
    settings = write_fixture(tmp_path)

    dataset = load_evaluation_dataset(tmp_path, settings)

    assert dataset.role == "validation"
    assert [asset.asset_id for asset in dataset.assets] == ["traffic_1", "crowd_1"]
    assert dataset.ground_truth_boxes[0].project_class == "car_or_van"
    assert dataset.ground_truth_boxes[0].box.as_xywh() == (10, 20, 30, 15)
    assert len(dataset.ground_truth_boxes) == 1
    assert dataset.count_references[0].project_class == "person"
    assert dataset.count_references[0].count == 42


def test_manifest_dataset_version_must_match_configuration(tmp_path: Path):
    settings = write_fixture(tmp_path, dataset_version="2.0")

    with pytest.raises(EvaluationDataError, match="expected '1.0'"):
        load_evaluation_dataset(tmp_path, settings)


def test_coco_membership_must_match_selected_manifest(tmp_path: Path):
    settings = write_fixture(tmp_path)
    coco_path = tmp_path / "annotations/instances.json"
    coco = json.loads(coco_path.read_text(encoding="utf-8"))
    coco["images"][0]["asset_id"] = "unexpected_asset"
    coco_path.write_text(json.dumps(coco), encoding="utf-8")

    with pytest.raises(EvaluationDataError, match="membership does not match"):
        load_evaluation_dataset(tmp_path, settings)
