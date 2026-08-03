import json
from pathlib import Path

from evaluation.annotation_conversion import PROJECT_CATEGORIES
from evaluation.dataset_validation import (
    ValidationReport,
    duplicates,
    validate_coco_file,
)


def coco_record() -> dict[str, str]:
    return {
        "asset_id": "example_1",
        "dataset_role": "validation",
    }


def write_coco(path: Path, bbox: list[float]) -> None:
    data = {
        "images": [
            {
                "id": 1,
                "asset_id": "example_1",
                "width": 100,
                "height": 80,
            }
        ],
        "annotations": [
            {
                "id": 1,
                "image_id": 1,
                "category_id": 4,
                "bbox": bbox,
                "area": bbox[2] * bbox[3],
            }
        ],
        "categories": PROJECT_CATEGORIES,
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def test_duplicates_returns_only_repeated_values():
    assert duplicates(["a", "b", "a", "c", "b", "b"]) == {"a", "b"}


def test_valid_coco_file_has_no_errors(tmp_path: Path):
    path = tmp_path / "instances.json"
    write_coco(path, [10, 20, 30, 40])
    report = ValidationReport()

    validate_coco_file(path, [coco_record()], report)

    assert report.errors == []
    assert report.statistics["bounding_boxes"]["validation"]["boxes"] == 1


def test_coco_box_outside_image_is_rejected(tmp_path: Path):
    path = tmp_path / "instances.json"
    write_coco(path, [90, 20, 20, 40])
    report = ValidationReport()

    validate_coco_file(path, [coco_record()], report)

    assert any("outside its image" in error for error in report.errors)
