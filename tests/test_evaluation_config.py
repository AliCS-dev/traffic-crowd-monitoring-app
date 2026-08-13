import json
from pathlib import Path

import pytest

from evaluation.evaluation_config import (
    EvaluationConfigError,
    load_evaluation_config,
    parse_evaluation_config,
)

CONFIG_PATH = Path("configs/evaluation/yolo26n_validation.json")
SELECTED_CONFIG_PATH = Path("configs/evaluation/yolo26n_selected_validation.json")


def load_values() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_baseline_evaluation_configuration_is_valid():
    config = load_evaluation_config(CONFIG_PATH)

    assert config.run_name == "yolo26n-validation-baseline"
    assert config.dataset.role == "validation"
    assert config.random_seed == 2026
    assert config.model.class_mapping.map("car") == "car_or_van"
    assert config.model.class_mapping.map("train") is None
    assert config.inference.confidence_floor == pytest.approx(0.001)
    assert config.inference.operating_confidence == pytest.approx(0.15)
    assert config.inference.max_detections == 300
    assert config.timing.warmup_frames == 20


def test_selected_baseline_configuration_remains_reproducible():
    config = load_evaluation_config(SELECTED_CONFIG_PATH)

    assert config.run_name == "yolo26n-validation-selected-baseline"
    assert config.dataset.role == "validation"
    assert config.inference.operating_confidence == pytest.approx(0.25)
    assert config.inference.image_size == 1280
    assert config.inference.scale_factor == 2
    assert config.inference.confidence_floor == pytest.approx(0.001)
    assert config.inference.max_detections == 300


def test_confidence_floor_cannot_exceed_operating_threshold():
    values = load_values()
    values["inference"]["confidence_floor"] = 0.25
    values["inference"]["operating_confidence"] = 0.15

    with pytest.raises(EvaluationConfigError, match="must not exceed"):
        parse_evaluation_config(values)


def test_unknown_project_class_in_mapping_is_rejected():
    values = load_values()
    values["model"]["class_mapping"]["train"] = "rail_vehicle"

    with pytest.raises(EvaluationConfigError, match="unknown project class"):
        parse_evaluation_config(values)


def test_unknown_configuration_field_is_rejected():
    values = load_values()
    values["inference"]["undocumented_setting"] = True

    with pytest.raises(EvaluationConfigError, match="unknown fields"):
        parse_evaluation_config(values)


def test_configuration_paths_are_resolved_from_repository_root():
    config = load_evaluation_config(CONFIG_PATH)
    root = Path("/tmp/project")

    assert config.resolve_path(root, config.model.weights_path) == (
        root / "models/yolo26n.pt"
    )


def test_configuration_paths_cannot_escape_repository():
    values = load_values()
    values["model"]["weights_path"] = "../untracked-model.pt"

    with pytest.raises(EvaluationConfigError, match="relative to the repository"):
        parse_evaluation_config(values)
