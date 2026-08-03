from pathlib import Path

from evaluation.dataset_selection import sha256
from evaluation.manual_annotation_task import (
    MODEL_CLASS_MAP,
    coco_images,
    create_task_archive,
    task_filename,
)


def test_model_class_mapping_uses_project_categories():
    assert MODEL_CLASS_MAP == {
        "bicycle": 2,
        "motorcycle": 3,
        "car": 4,
        "bus": 5,
        "truck": 6,
    }


def test_task_filename_uses_stable_asset_id_and_original_suffix():
    record = {
        "asset_id": "wikimedia_frame_000001",
        "evaluation_image_path": "data/evaluation/derived/frame.PNG",
    }

    assert task_filename(record) == "wikimedia_frame_000001.png"


def test_coco_images_use_subset_relative_filenames(tmp_path: Path):
    source = tmp_path / "source.png"
    source.write_bytes(b"image")
    image_directory = tmp_path / "images" / "default"
    record = {
        "asset_id": "wikimedia_frame_000001",
        "evaluation_image_path": "source.png",
        "width": "1920",
        "height": "1080",
        "dataset_role": "held_out_test",
        "source_group_id": "wikimedia_video",
        "source_url": "https://example.com/source",
        "license_id": "CC-BY-4.0",
        "creator": "Example Creator",
        "image_sha256": "example-sha256",
    }

    images = coco_images([record], tmp_path, image_directory)

    assert images[0]["file_name"] == "wikimedia_frame_000001.png"
    assert (image_directory / "wikimedia_frame_000001.png").read_bytes() == b"image"


def test_task_archive_is_deterministic(tmp_path: Path):
    task_root = tmp_path / "task"
    task_root.mkdir()
    (task_root / "example.txt").write_text("example\n", encoding="utf-8")
    first_archive = tmp_path / "first.zip"
    second_archive = tmp_path / "second.zip"

    create_task_archive(task_root, first_archive)
    create_task_archive(task_root, second_archive)

    assert sha256(first_archive) == sha256(second_archive)
