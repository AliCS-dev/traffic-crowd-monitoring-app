from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from evaluation import evaluation_command
from evaluation.evaluation_config import load_evaluation_config
from evaluation.evaluation_results import SavedEvaluationRun
from evaluation.evaluation_runner import PredictionBatch

CONFIG_PATH = Path("configs/evaluation/yolo26n_validation.json")


def test_evaluation_command_connects_the_reproducible_pipeline(tmp_path, monkeypatch):
    config = load_evaluation_config(CONFIG_PATH)
    dataset = SimpleNamespace(
        assets=(object(), object()),
        role="validation",
        version="1.0-draft",
    )
    predictions = PredictionBatch(("first", "second"), ())
    detection_metrics = object()
    count_metrics = (object(),)
    timing = object()
    saved = SavedEvaluationRun(
        "run-id",
        tmp_path / "runs/run-id",
        tmp_path / "runs/run-id/run_manifest.json",
    )
    detector = object()
    detector_factory = Mock(return_value=detector)
    progress_messages = []
    created_at = datetime(2026, 8, 4, 14, 0, tzinfo=timezone.utc)

    load_config = Mock(return_value=config)
    load_dataset = Mock(return_value=dataset)
    generate = Mock(return_value=predictions)
    detection = Mock(return_value=detection_metrics)
    counts = Mock(return_value=count_metrics)
    benchmark = Mock(return_value=timing)
    save = Mock(return_value=saved)
    seed = Mock()
    provenance = {"git": {"commit": "abc123", "dirty": False}}
    collect_provenance = Mock(return_value=provenance)
    validation = Mock(
        return_value=SimpleNamespace(dataset_ready=True, errors=[], incomplete=[])
    )
    monkeypatch.setattr(evaluation_command, "load_evaluation_config", load_config)
    monkeypatch.setattr(evaluation_command, "validate_dataset", validation)
    monkeypatch.setattr(evaluation_command, "load_evaluation_dataset", load_dataset)
    monkeypatch.setattr(evaluation_command, "generate_predictions", generate)
    monkeypatch.setattr(evaluation_command, "calculate_detection_metrics", detection)
    monkeypatch.setattr(evaluation_command, "calculate_count_metrics", counts)
    monkeypatch.setattr(evaluation_command, "run_runtime_benchmark", benchmark)
    monkeypatch.setattr(evaluation_command, "save_evaluation_run", save)
    monkeypatch.setattr(evaluation_command, "seed_random_generators", seed)
    monkeypatch.setattr(
        evaluation_command, "collect_run_provenance", collect_provenance
    )

    result = evaluation_command.run_detector_evaluation(
        tmp_path,
        CONFIG_PATH,
        detector_factory=detector_factory,
        progress=progress_messages.append,
        created_at=created_at,
    )

    assert result is saved
    load_config.assert_called_once_with(tmp_path / CONFIG_PATH)
    validation.assert_called_once_with(tmp_path)
    collect_provenance.assert_called_once_with(tmp_path, config)
    seed.assert_called_once_with(2026)
    load_dataset.assert_called_once_with(tmp_path, config.dataset)
    detector_factory.assert_called_once_with(tmp_path / config.model.weights_path)
    generate.assert_called_once_with(dataset, detector, config)
    detection.assert_called_once_with(
        dataset,
        [],
        confidence_floor=0.001,
        operating_confidence=0.15,
        operating_iou=0.5,
        max_detections=300,
        low_support_threshold=20,
    )
    counts.assert_called_once_with(
        dataset,
        [],
        operating_confidence=0.15,
        low_support_threshold=20,
    )
    benchmark.assert_called_once_with(dataset, detector, config)
    save.assert_called_once_with(
        tmp_path,
        config,
        predictions,
        detection_metrics,
        count_metrics,
        timing,
        created_at=created_at,
        provenance=provenance,
    )
    assert progress_messages[-1] == f"Saved evaluation run to {saved.output_directory}."


def test_evaluation_command_rejects_a_dataset_that_is_not_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(
        evaluation_command,
        "load_evaluation_config",
        Mock(return_value=load_evaluation_config(CONFIG_PATH)),
    )
    monkeypatch.setattr(
        evaluation_command,
        "validate_dataset",
        Mock(
            return_value=SimpleNamespace(
                dataset_ready=False,
                errors=["annotation file hash changed"],
                incomplete=[],
            )
        ),
    )
    detector_factory = Mock()

    with pytest.raises(
        evaluation_command.EvaluationCommandError,
        match="annotation file hash changed",
    ):
        evaluation_command.run_detector_evaluation(
            tmp_path,
            CONFIG_PATH,
            detector_factory=detector_factory,
            progress=Mock(),
        )

    detector_factory.assert_not_called()
