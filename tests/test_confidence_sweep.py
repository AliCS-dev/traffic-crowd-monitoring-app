import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from evaluation.confidence_sweep import (
    ConfidenceSweepError,
    SourceEvaluationRun,
    calculate_confidence_sweep,
    load_confidence_sweep_config,
    load_source_evaluation_run,
    parse_confidence_sweep_config,
    save_confidence_sweep,
    verify_source_dataset_identity,
)
from evaluation.evaluation_config import load_evaluation_config
from evaluation.evaluation_data import (
    BoundingBox,
    CountReference,
    EvaluationAsset,
    EvaluationDataset,
    GroundTruthBox,
    PredictionRecord,
)
from evaluation.evaluation_runner import PredictionBatch

EVALUATION_CONFIG_PATH = Path("configs/evaluation/yolo26n_validation.json")
SWEEP_CONFIG_PATH = Path("configs/evaluation/yolo26n_confidence_sweep.json")


def asset(asset_id: str, annotation_type: str, target_classes: set[str]):
    return EvaluationAsset(
        asset_id=asset_id,
        collection_id="fixture",
        source_group_id=asset_id,
        dataset_role="validation",
        image_path=Path(f"images/{asset_id}.png"),
        width=100,
        height=80,
        annotation_type=annotation_type,
        target_classes=frozenset(target_classes),
    )


def create_dataset() -> EvaluationDataset:
    box = BoundingBox(10, 10, 10, 10)
    return EvaluationDataset(
        role="validation",
        version="1.0-draft",
        assets=(
            asset("traffic-1", "bounding_box", {"car_or_van"}),
            asset("traffic-2", "bounding_box", {"car_or_van"}),
            asset("crowd-1", "point_count", {"person"}),
        ),
        ground_truth_boxes=(
            GroundTruthBox("traffic-1", "car_or_van", box),
            GroundTruthBox("traffic-2", "car_or_van", box),
        ),
        count_references=(CountReference("crowd-1", "person", 10),),
    )


def create_source_run() -> SourceEvaluationRun:
    box = BoundingBox(10, 10, 10, 10)
    predictions = (
        PredictionRecord("traffic-1", "car", "car_or_van", 0.12, box),
        PredictionRecord("traffic-2", "car", "car_or_van", 0.30, box),
        PredictionRecord("crowd-1", "person", "person", 0.20, box),
    )
    return SourceEvaluationRun(
        run_id="source-run",
        manifest_sha256="abc123",
        config=load_evaluation_config(EVALUATION_CONFIG_PATH),
        predictions=PredictionBatch(("traffic-1", "traffic-2", "crowd-1"), predictions),
        dataset_manifest_sha256="manifest-hash",
        annotation_files=(("annotations/validation.json", "annotation-hash"),),
    )


def test_tracked_confidence_sweep_configuration_is_strict():
    config = load_confidence_sweep_config(SWEEP_CONFIG_PATH)

    assert config.comparison_name == "yolo26n-validation-confidence-sweep"
    assert config.operating_confidences == (0.10, 0.15, 0.25, 0.40, 0.50)

    values = json.loads(SWEEP_CONFIG_PATH.read_text(encoding="utf-8"))
    values["operating_confidences"].append(0.60)
    with pytest.raises(ConfidenceSweepError, match="predeclared"):
        parse_confidence_sweep_config(values)


def test_confidence_sweep_reuses_predictions_and_changes_operating_metrics():
    result = calculate_confidence_sweep(
        create_dataset(),
        create_source_run(),
        load_confidence_sweep_config(SWEEP_CONFIG_PATH),
    )

    assert len(result.results) == 5
    low, _, medium, _, high = result.results
    assert low.detection.macro_precision == pytest.approx(1.0)
    assert low.detection.macro_recall == pytest.approx(1.0)
    assert medium.detection.macro_recall == pytest.approx(0.5)
    assert high.detection.macro_precision == pytest.approx(0.0)
    assert high.detection.macro_recall == pytest.approx(0.0)
    assert [entry.detection.map50 for entry in result.results] == pytest.approx(
        [1.0] * 5
    )

    low_counts = {metric.class_name: metric for metric in low.counts}
    medium_counts = {metric.class_name: metric for metric in medium.counts}
    high_counts = {metric.class_name: metric for metric in high.counts}
    assert low_counts["road_vehicle_total"].normalized_absolute_error == 0.0
    assert medium_counts["road_vehicle_total"].normalized_absolute_error == 0.5
    assert high_counts["road_vehicle_total"].normalized_absolute_error == 1.0
    assert low_counts["person"].normalized_absolute_error == pytest.approx(0.9)
    assert medium_counts["person"].normalized_absolute_error == pytest.approx(1.0)


def test_confidence_sweep_rejects_non_validation_data():
    dataset = replace(create_dataset(), role="held_out_test")

    with pytest.raises(ConfidenceSweepError, match="validation data only"):
        calculate_confidence_sweep(
            dataset,
            create_source_run(),
            load_confidence_sweep_config(SWEEP_CONFIG_PATH),
        )


def test_source_run_loader_verifies_artifact_checksums(tmp_path: Path):
    run_directory = tmp_path / "source-run"
    run_directory.mkdir()
    run_id = "source-run"
    configuration = {
        "schema_version": 1,
        "run_id": run_id,
        "configuration": json.loads(EVALUATION_CONFIG_PATH.read_text(encoding="utf-8")),
    }
    predictions = {
        "schema_version": 1,
        "run_id": run_id,
        "processed_asset_ids": ["traffic-1"],
        "predictions": [
            {
                "asset_id": "traffic-1",
                "source_class": "car",
                "project_class": "car_or_van",
                "confidence": 0.9,
                "box": {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0},
            }
        ],
    }
    provenance = {
        "schema_version": 1,
        "run_id": run_id,
        "dataset": {
            "manifest_sha256": "manifest-hash",
            "annotation_files": [
                {
                    "path": "annotations/validation.json",
                    "sha256": "annotation-hash",
                }
            ],
        },
    }
    write_json(run_directory / "configuration.json", configuration)
    write_json(run_directory / "predictions.json", predictions)
    write_json(run_directory / "provenance.json", provenance)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "artifacts": [
            artifact_record(run_directory / "configuration.json"),
            artifact_record(run_directory / "predictions.json"),
            artifact_record(run_directory / "provenance.json"),
        ],
    }
    write_json(run_directory / "run_manifest.json", manifest)

    source = load_source_evaluation_run(run_directory)

    assert source.run_id == run_id
    assert source.predictions.asset_ids == ("traffic-1",)
    assert source.predictions.predictions[0].box.as_xyxy() == (1.0, 2.0, 4.0, 6.0)
    assert source.dataset_manifest_sha256 == "manifest-hash"

    (run_directory / "predictions.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ConfidenceSweepError, match="checksum failed"):
        load_source_evaluation_run(run_directory)


def test_source_dataset_identity_rejects_changed_annotations(tmp_path: Path):
    source = create_source_run()
    manifest_path = tmp_path / source.config.dataset.manifest_path
    annotation_path = tmp_path / "annotations/validation.json"
    manifest_path.parent.mkdir(parents=True)
    annotation_path.parent.mkdir(parents=True)
    manifest_path.write_bytes(b"manifest")
    annotation_path.write_bytes(b"annotations")
    source = replace(
        source,
        dataset_manifest_sha256=hashlib.sha256(b"manifest").hexdigest(),
        annotation_files=(
            (
                "annotations/validation.json",
                hashlib.sha256(b"annotations").hexdigest(),
            ),
        ),
    )

    verify_source_dataset_identity(tmp_path, source)
    annotation_path.write_bytes(b"changed annotations")

    with pytest.raises(ConfidenceSweepError, match="Annotation file changed"):
        verify_source_dataset_identity(tmp_path, source)


def test_confidence_sweep_saves_machine_readable_results_and_report(tmp_path):
    sweep_config = load_confidence_sweep_config(SWEEP_CONFIG_PATH)
    result = calculate_confidence_sweep(
        create_dataset(), create_source_run(), sweep_config
    )

    saved = save_confidence_sweep(
        tmp_path,
        sweep_config,
        result,
        created_at=datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc),
        provenance={"git": {"commit": "abc123", "dirty": False}},
    )

    assert saved.comparison_id == (
        "20260805T120000Z-yolo26n-validation-confidence-sweep"
    )
    assert {path.name for path in saved.output_directory.iterdir()} == {
        "comparison.json",
        "summary.md",
        "comparison_manifest.json",
    }
    comparison = read_json(saved.output_directory / "comparison.json")
    assert len(comparison["comparison"]["results"]) == 5
    summary = saved.summary_path.read_text(encoding="utf-8")
    assert "| 0.10 | 1.0000 | 1.0000 |" in summary
    assert "No held-out test data" in summary
    manifest = read_json(saved.output_directory / "comparison_manifest.json")
    for record in manifest["artifacts"]:
        path = saved.output_directory / record["filename"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]


def artifact_record(path: Path) -> dict[str, str]:
    return {
        "filename": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
