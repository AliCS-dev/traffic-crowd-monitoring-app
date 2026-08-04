import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from evaluation.evaluation_config import load_evaluation_config
from evaluation.evaluation_data import BoundingBox, PredictionRecord
from evaluation.evaluation_metrics import (
    CountMetricResult,
    DetectionClassMetric,
    DetectionMetricResult,
)
from evaluation.evaluation_report import generate_evaluation_report
from evaluation.evaluation_results import (
    EvaluationResultError,
    collect_run_provenance,
    save_evaluation_run,
)
from evaluation.evaluation_runner import PredictionBatch
from evaluation.evaluation_timing import (
    RuntimeBenchmarkResult,
    RuntimeMeasurement,
    RuntimeSummary,
    StageStatistics,
)

CONFIG_PATH = Path("configs/evaluation/yolo26n_validation.json")
CREATED_AT = datetime(2026, 8, 4, 13, 15, tzinfo=timezone.utc)


def create_predictions() -> PredictionBatch:
    return PredictionBatch(
        asset_ids=("asset-1", "asset-2"),
        predictions=(
            PredictionRecord(
                asset_id="asset-1",
                source_class="car",
                project_class="car_or_van",
                confidence=0.9,
                box=BoundingBox(1.0, 2.0, 3.0, 4.0),
            ),
        ),
    )


def create_detection_metrics() -> DetectionMetricResult:
    return DetectionMetricResult(
        evaluated_images=2,
        ground_truth_instances=1,
        macro_precision=1.0,
        macro_recall=1.0,
        map50=1.0,
        map50_95=0.8,
        ap_small=0.7,
        ap_medium=None,
        ap_large=None,
        per_class=(
            DetectionClassMetric(
                class_name="car_or_van",
                ground_truth_instances=1,
                true_positives=1,
                false_positives=0,
                false_negatives=0,
                precision=1.0,
                recall=1.0,
                ap50=1.0,
                ap50_95=0.8,
                low_support=True,
            ),
        ),
    )


def create_count_metrics() -> tuple[CountMetricResult, ...]:
    return (
        CountMetricResult(
            class_name="car_or_van",
            examples=2,
            ground_truth_total=1,
            predicted_total=1,
            mean_absolute_error=0.0,
            normalized_absolute_error=0.0,
            bias=0.0,
            low_support=True,
        ),
    )


def create_timing() -> RuntimeBenchmarkResult:
    stage = StageStatistics(0.01, 0.02, 0.02)
    measurement = RuntimeMeasurement(
        repetition=1,
        sample=1,
        asset_id="asset-1",
        loading_seconds=0.01,
        preprocessing_seconds=0.01,
        inference_seconds=0.02,
        conversion_seconds=0.01,
        in_memory_seconds=0.04,
        end_to_end_seconds=0.05,
    )
    summary = RuntimeSummary(
        sample_count=1,
        loading=stage,
        preprocessing=stage,
        inference=stage,
        conversion=stage,
        in_memory=stage,
        end_to_end=stage,
        in_memory_throughput_fps=25.0,
        end_to_end_throughput_fps=20.0,
        peak_gpu_memory_bytes=1024,
    )
    return RuntimeBenchmarkResult(
        warmup_frames=1,
        measured_frames_per_repetition=1,
        repetitions=1,
        measurements=(measurement,),
        peak_gpu_memory_bytes_by_repetition=(1024,),
        summary=summary,
    )


def test_save_evaluation_run_writes_machine_readable_artifacts(tmp_path: Path):
    config = load_evaluation_config(CONFIG_PATH)

    saved = save_evaluation_run(
        tmp_path,
        config,
        create_predictions(),
        create_detection_metrics(),
        create_count_metrics(),
        create_timing(),
        created_at=CREATED_AT,
        provenance={"test_environment": True},
    )

    assert saved.run_id == "20260804T131500Z-yolo26n-validation-baseline"
    assert saved.output_directory.parent == (tmp_path / "data/evaluation/derived/runs")
    expected_files = {
        "configuration.json",
        "predictions.json",
        "metrics.json",
        "timing.json",
        "provenance.json",
        "summary.md",
        "run_manifest.json",
    }
    assert {path.name for path in saved.output_directory.iterdir()} == expected_files

    configuration = read_json(saved.output_directory / "configuration.json")
    assert configuration["configuration"]["model"]["class_mapping"]["car"] == (
        "car_or_van"
    )
    predictions = read_json(saved.output_directory / "predictions.json")
    assert predictions["processed_asset_ids"] == ["asset-1", "asset-2"]
    assert predictions["predictions"][0]["box"] == {
        "height": 4.0,
        "width": 3.0,
        "x": 1.0,
        "y": 2.0,
    }
    metrics = read_json(saved.output_directory / "metrics.json")
    assert metrics["detection"]["ap_medium"] is None
    assert metrics["counts"][0]["class_name"] == "car_or_van"
    provenance = read_json(saved.output_directory / "provenance.json")
    assert provenance["created_at_utc"] == "2026-08-04T13:15:00Z"
    assert provenance["test_environment"] is True
    summary = (saved.output_directory / "summary.md").read_text(encoding="utf-8")
    assert "# Detector Evaluation Summary" in summary
    assert "| mAP50 | 1.0000 |" in summary
    assert "| car_or_van | 2 | 1 | 1 | 0.0000 | 0.0000 | 0.0000 | yes |" in summary
    assert "- End-to-end throughput: 20.00 FPS" in summary

    generate_evaluation_report(saved.output_directory)

    assert (saved.output_directory / "summary.md").read_text(
        encoding="utf-8"
    ) == summary


def test_run_manifest_contains_valid_artifact_hashes(tmp_path: Path):
    config = load_evaluation_config(CONFIG_PATH)
    saved = save_evaluation_run(
        tmp_path,
        config,
        create_predictions(),
        create_detection_metrics(),
        create_count_metrics(),
        create_timing(),
        created_at=CREATED_AT,
        provenance={},
    )

    manifest = read_json(saved.manifest_path)
    assert manifest["run_id"] == saved.run_id
    for artifact in manifest["artifacts"]:
        artifact_path = saved.output_directory / artifact["filename"]
        assert (
            artifact["sha256"] == hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        )


def test_save_evaluation_run_does_not_overwrite_an_existing_run(tmp_path: Path):
    config = load_evaluation_config(CONFIG_PATH)
    arguments = (
        tmp_path,
        config,
        create_predictions(),
        create_detection_metrics(),
        create_count_metrics(),
        create_timing(),
    )
    save_evaluation_run(*arguments, created_at=CREATED_AT, provenance={})

    with pytest.raises(EvaluationResultError, match="already exists"):
        save_evaluation_run(*arguments, created_at=CREATED_AT, provenance={})


def test_collect_provenance_hashes_model_and_dataset_inputs(tmp_path, monkeypatch):
    config = load_evaluation_config(CONFIG_PATH)
    config = replace(config, inference=replace(config.inference, device="cpu"))
    model_path = tmp_path / config.model.weights_path
    manifest_path = tmp_path / config.dataset.manifest_path
    annotation_path = tmp_path / "annotations/validation.json"
    model_path.parent.mkdir(parents=True)
    manifest_path.parent.mkdir(parents=True)
    annotation_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"model weights")
    manifest_path.write_text(
        "dataset_version,dataset_role,canonical_annotation_path\n"
        "1.0-draft,validation,annotations/validation.json\n",
        encoding="utf-8",
    )
    annotation_path.write_bytes(b"ground truth")
    monkeypatch.setattr(
        "evaluation.evaluation_results._git_information",
        lambda root: {"commit": "abc123", "dirty": False},
    )
    monkeypatch.setattr(
        "evaluation.evaluation_results._dependency_versions",
        lambda: {"torch": "1.2.3"},
    )

    provenance = collect_run_provenance(tmp_path, config)

    assert provenance["git"] == {"commit": "abc123", "dirty": False}
    assert provenance["dependencies"] == {"torch": "1.2.3"}
    assert provenance["hardware"]["gpu"] is None
    assert (
        provenance["model"]["weights_sha256"]
        == hashlib.sha256(b"model weights").hexdigest()
    )
    assert provenance["model"]["weights_size_bytes"] == len(b"model weights")
    assert (
        provenance["dataset"]["manifest_sha256"]
        == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    )
    assert provenance["dataset"]["annotation_files"] == [
        {
            "path": "annotations/validation.json",
            "sha256": hashlib.sha256(b"ground truth").hexdigest(),
        }
    ]


def test_save_evaluation_run_rejects_a_naive_timestamp(tmp_path: Path):
    config = load_evaluation_config(CONFIG_PATH)

    with pytest.raises(EvaluationResultError, match="timezone"):
        save_evaluation_run(
            tmp_path,
            config,
            create_predictions(),
            create_detection_metrics(),
            create_count_metrics(),
            create_timing(),
            created_at=datetime(2026, 8, 4, 13, 15),
            provenance={},
        )


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
