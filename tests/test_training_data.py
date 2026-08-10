import csv
import json
from pathlib import Path

import pytest
import yaml

from evaluation.training_config import load_training_config
from evaluation.training_data import TrainingDataError, prepare_training_dataset


def valid_config() -> dict:
    return {
        "schema_version": 1,
        "run_name": "test-finetune",
        "random_seed": 2026,
        "base_checkpoint": "models/base.pt",
        "base_checkpoint_sha256": "a" * 64,
        "source_classes": ["pedestrian", "car"],
        "project_class_mapping": {"person": "pedestrian", "car_or_van": "car"},
        "dataset": {
            "selection_plan_path": "data/evaluation/selection_plan.csv",
            "validation_annotations_path": "data/evaluation/validation.json",
            "output_directory": "data/evaluation/derived/training/test-data",
            "collection_id": "okutama_action",
            "role": "training",
            "frame_stride": 30,
        },
        "training": {
            "epochs": 10,
            "patience": 3,
            "image_size": 640,
            "batch_size": 2,
            "device": "cpu",
            "workers": 0,
            "freeze_layers": 0,
            "optimizer": "AdamW",
            "learning_rate": 0.001,
            "amp": False,
            "cache": False,
        },
        "output_directory": "data/evaluation/derived/training/runs",
    }


def write_config(tmp_path: Path, values: dict) -> Path:
    path = tmp_path / "training.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    return path


def write_selection_plan(root: Path) -> None:
    path = root / "data/evaluation/selection_plan.csv"
    path.parent.mkdir(parents=True)
    fields = [
        "selection_id",
        "collection_id",
        "source_group_id",
        "dataset_role",
        "source_path",
        "annotation_source",
        "annotation_type",
    ]
    rows = [
        {
            "selection_id": "okutama_train",
            "collection_id": "okutama_action",
            "source_group_id": "train_scene",
            "dataset_role": "training",
            "source_path": "raw/train",
            "annotation_source": "raw/train.txt",
            "annotation_type": "bounding_box",
        },
        {
            "selection_id": "okutama_val",
            "collection_id": "okutama_action",
            "source_group_id": "validation_scene",
            "dataset_role": "validation",
            "source_path": "raw/validation",
            "annotation_source": "raw/validation.txt",
            "annotation_type": "bounding_box",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_source_data(root: Path) -> None:
    image_directory = root / "raw/train"
    image_directory.mkdir(parents=True)
    for frame in (0, 1, 2, 3):
        (image_directory / f"{frame}.jpg").write_bytes(b"image")
    (root / "raw/train.txt").write_text(
        '1 300 600 600 900 0 0 0 0 "Person" "Walking"\n'
        '1 300 600 600 900 2 0 0 0 "Person" "Walking"\n',
        encoding="utf-8",
    )

    validation_image = root / "raw/validation.jpg"
    validation_image.write_bytes(b"image")
    annotations_path = root / "data/evaluation/validation.json"
    annotations_path.write_text(
        json.dumps(
            {
                "images": [
                    {
                        "id": 1,
                        "asset_id": "validation-asset",
                        "file_name": "raw/validation.jpg",
                        "width": 100,
                        "height": 50,
                        "source_group_id": "validation_scene",
                    },
                    {
                        "id": 2,
                        "asset_id": "negative-validation-asset",
                        "file_name": "raw/negative-validation.jpg",
                        "width": 100,
                        "height": 50,
                        "source_group_id": "validation_scene",
                    },
                ],
                "annotations": [
                    {"image_id": 1, "category_id": 4, "bbox": [10, 5, 20, 10]}
                ],
                "categories": [{"id": 4, "name": "car_or_van"}],
            }
        ),
        encoding="utf-8",
    )
    (root / "raw/negative-validation.jpg").write_bytes(b"image")


def test_prepare_training_dataset_samples_and_converts_labels(tmp_path: Path):
    write_selection_plan(tmp_path)
    write_source_data(tmp_path)
    values = valid_config()
    values["dataset"]["frame_stride"] = 2
    config = load_training_config(write_config(tmp_path, values))

    prepared = prepare_training_dataset(tmp_path, config)

    assert prepared.training_images == 2
    assert prepared.training_boxes == 2
    assert prepared.validation_images == 2
    assert prepared.validation_boxes == 1
    assert prepared.training_source_groups == ("train_scene",)

    output = tmp_path / values["dataset"]["output_directory"]
    assert len(list((output / "images/train").iterdir())) == 2
    assert (output / "images/train/okutama_train-f000000.jpg").is_symlink()
    train_label = (output / "labels/train/okutama_train-f000000.txt").read_text()
    assert train_label.startswith("0 ")
    validation_label = (output / "labels/val/validation-asset.txt").read_text()
    assert validation_label.startswith("1 ")
    assert (output / "labels/val/negative-validation-asset.txt").read_text() == ""
    dataset_yaml = yaml.safe_load(prepared.dataset_yaml.read_text())
    assert dataset_yaml["names"] == {0: "pedestrian", 1: "car"}


def test_prepare_training_dataset_rejects_unmapped_validation_class(tmp_path: Path):
    write_selection_plan(tmp_path)
    write_source_data(tmp_path)
    annotations_path = tmp_path / "data/evaluation/validation.json"
    annotations = json.loads(annotations_path.read_text(encoding="utf-8"))
    annotations["categories"][0]["name"] = "truck"
    annotations_path.write_text(json.dumps(annotations), encoding="utf-8")
    config = load_training_config(write_config(tmp_path, valid_config()))

    with pytest.raises(TrainingDataError, match="no training mapping: truck"):
        prepare_training_dataset(tmp_path, config)
