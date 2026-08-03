import csv
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from evaluation.dataset_selection import sha256
from evaluation.manual_annotation_import import (
    ANNOTATION_MEMBER,
    import_reviewed_annotations,
)

CATEGORY_NAMES = {
    "person",
    "bicycle",
    "motorcycle",
    "car_or_van",
    "bus",
    "truck",
}


def write_fixture(root: Path, *, extra_filename: str = "asset_excluded.png") -> None:
    archive_path = root / "data/reviewed.zip"
    archive_path.parent.mkdir(parents=True)
    categories = [
        {"id": category_id, "name": name}
        for category_id, name in enumerate(sorted(CATEGORY_NAMES), start=1)
    ]
    car_id = next(
        category["id"] for category in categories if category["name"] == "car_or_van"
    )
    data = {
        "images": [
            {
                "id": 1,
                "file_name": "asset_retained.png",
                "width": 100,
                "height": 80,
            },
            {
                "id": 2,
                "file_name": extra_filename,
                "width": 100,
                "height": 80,
            },
        ],
        "annotations": [
            {
                "id": 1,
                "image_id": 1,
                "category_id": car_id,
                "bbox": [10, 20, 30, 40],
                "iscrowd": 0,
            },
            {
                "id": 2,
                "image_id": 2,
                "category_id": car_id,
                "bbox": [1, 2, 3, 4],
                "iscrowd": 0,
            },
        ],
        "categories": categories,
    }
    annotation_bytes = json.dumps(data).encode()
    with ZipFile(archive_path, "w") as archive:
        archive.writestr(ANNOTATION_MEMBER, annotation_bytes)

    metadata_path = root / "data/manual_annotation_exports.csv"
    with metadata_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "annotation_set_id",
                "archive_path",
                "archive_sha256",
                "annotation_sha256",
                "exported_on",
                "tool",
                "format",
                "review_status",
                "notes",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(
            {
                "annotation_set_id": "wikimedia_manual_v1",
                "archive_path": "data/reviewed.zip",
                "archive_sha256": sha256(archive_path),
                "annotation_sha256": hashlib.sha256(annotation_bytes).hexdigest(),
                "exported_on": "2026-08-03",
                "tool": "CVAT Online",
                "format": "COCO 1.0",
                "review_status": "first_pass_complete",
                "notes": "test fixture",
            }
        )

    exclusions_path = root / "data/exclusions.csv"
    exclusions_path.write_text(
        "asset_id,excluded_on,decision_stage,reason\n"
        "asset_excluded,2026-08-03,before_benchmarking,test exclusion\n",
        encoding="utf-8",
    )


def retained_record() -> dict[str, str]:
    return {
        "asset_id": "asset_retained",
        "evaluation_image_path": "images/original.png",
        "annotation_type": "bounding_box",
        "annotation_source_path": "",
        "dataset_role": "held_out_test",
        "width": "100",
        "height": "80",
    }


def test_reviewed_import_retains_manifest_images_and_skips_exclusions(tmp_path: Path):
    write_fixture(tmp_path)

    result = import_reviewed_annotations(
        repository_root=tmp_path,
        records=[retained_record()],
        metadata_path=tmp_path / "data/manual_annotation_exports.csv",
        exclusions_path=tmp_path / "data/exclusions.csv",
        project_category_names=CATEGORY_NAMES,
    )

    assert result.source_images == 2
    assert result.retained_images == 1
    assert result.excluded_images == 1
    assert result.retained_boxes == 1
    assert result.excluded_boxes == 1
    assert result.roles == {"held_out_test": {"images": 1, "boxes": 1}}
    assert result.boxes_by_asset["asset_retained"][0].bbox == (
        10.0,
        20.0,
        30.0,
        40.0,
    )
    assert result.boxes_by_asset["asset_retained"][0].source_rotation_degrees == 0


def test_reviewed_import_rejects_untracked_images(tmp_path: Path):
    write_fixture(tmp_path, extra_filename="unexpected.png")

    with pytest.raises(ValueError, match="untracked images"):
        import_reviewed_annotations(
            repository_root=tmp_path,
            records=[retained_record()],
            metadata_path=tmp_path / "data/manual_annotation_exports.csv",
            exclusions_path=tmp_path / "data/exclusions.csv",
            project_category_names=CATEGORY_NAMES,
        )


def test_reviewed_import_applies_tracked_duplicate_removal(tmp_path: Path):
    write_fixture(tmp_path)
    corrections_path = tmp_path / "data/manual_annotation_corrections.csv"
    corrections_path.write_text(
        "annotation_set_id,source_annotation_id,action,replacement_category,reviewed_on,reason\n"
        "wikimedia_manual_v1,1,remove_duplicate,,2026-08-03,duplicate box\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Retained manual images have no annotations"):
        import_reviewed_annotations(
            repository_root=tmp_path,
            records=[retained_record()],
            metadata_path=tmp_path / "data/manual_annotation_exports.csv",
            exclusions_path=tmp_path / "data/exclusions.csv",
            corrections_path=corrections_path,
            project_category_names=CATEGORY_NAMES,
        )


def test_reviewed_import_rejects_unknown_correction_id(tmp_path: Path):
    write_fixture(tmp_path)
    corrections_path = tmp_path / "data/manual_annotation_corrections.csv"
    corrections_path.write_text(
        "annotation_set_id,source_annotation_id,action,replacement_category,reviewed_on,reason\n"
        "wikimedia_manual_v1,999,remove_duplicate,,2026-08-03,duplicate box\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown annotations: 999"):
        import_reviewed_annotations(
            repository_root=tmp_path,
            records=[retained_record()],
            metadata_path=tmp_path / "data/manual_annotation_exports.csv",
            exclusions_path=tmp_path / "data/exclusions.csv",
            corrections_path=corrections_path,
            project_category_names=CATEGORY_NAMES,
        )


def test_reviewed_import_applies_tracked_relabel(tmp_path: Path):
    write_fixture(tmp_path)
    corrections_path = tmp_path / "data/manual_annotation_corrections.csv"
    corrections_path.write_text(
        "annotation_set_id,source_annotation_id,action,replacement_category,reviewed_on,reason\n"
        "wikimedia_manual_v1,1,relabel,bus,2026-08-03,class correction\n",
        encoding="utf-8",
    )

    result = import_reviewed_annotations(
        repository_root=tmp_path,
        records=[retained_record()],
        metadata_path=tmp_path / "data/manual_annotation_exports.csv",
        exclusions_path=tmp_path / "data/exclusions.csv",
        corrections_path=corrections_path,
        project_category_names=CATEGORY_NAMES,
    )

    assert result.classes == {"bus": 1}
    assert result.relabeled_boxes == 1
    assert result.boxes_by_asset["asset_retained"][0].category_name == "bus"
