import json
from pathlib import Path

import pytest

from evaluation.training_config import TrainingConfigError, load_training_config


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


def test_training_config_loads_class_mapping(tmp_path: Path):
    config = load_training_config(write_config(tmp_path, valid_config()))

    assert config.run_name == "test-finetune"
    assert config.dataset.frame_stride == 30
    assert config.mapped_class_ids() == {"car_or_van": 1, "person": 0}
    assert len(config.config_sha256) == 64


def test_training_config_rejects_output_outside_derived_data(tmp_path: Path):
    values = valid_config()
    values["dataset"]["output_directory"] = "."

    with pytest.raises(TrainingConfigError, match="data/evaluation/derived"):
        load_training_config(write_config(tmp_path, values))


def test_training_config_rejects_unknown_mapping_target(tmp_path: Path):
    values = valid_config()
    values["project_class_mapping"]["person"] = "people"

    with pytest.raises(TrainingConfigError, match="unknown source classes"):
        load_training_config(write_config(tmp_path, values))
