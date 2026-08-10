import json
from pathlib import Path

import cv2
import pytest

from evaluation.confidence_sweep import SourceEvaluationRun
from evaluation.evaluation_config import load_evaluation_config
from evaluation.evaluation_data import (
    BoundingBox,
    EvaluationAsset,
    EvaluationDataset,
    GroundTruthBox,
    PredictionRecord,
)
from evaluation.evaluation_runner import PredictionBatch
from evaluation.final_quality_gate import (
    FinalQualityGateError,
    calculate_source_group_intervals,
    classify_quality_gate,
    load_final_report_config,
    save_final_evidence,
)

CONFIG_PATH = Path("configs/evaluation/final_quality_gate_report.json")
FINAL_EVIDENCE_PATH = Path("data/evaluation/final_quality_gate.json")
HELD_OUT_CONFIG_PATH = Path(
    "configs/evaluation/yolo26m_visdrone_held_out_test.json"
)


def test_tracked_final_report_configuration_is_strict(tmp_path):
    config = load_final_report_config(CONFIG_PATH)

    assert config.bootstrap_iterations == 2000
    assert config.bootstrap_seed == 2026
    assert config.source_run_id.endswith("held-out-test")

    values = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    values["unexpected"] = True
    invalid_path = tmp_path / "invalid-final-report-config.json"
    invalid_path.write_text(json.dumps(values), encoding="utf-8")

    with pytest.raises(FinalQualityGateError, match="fields are invalid"):
        load_final_report_config(invalid_path)


def test_quality_gate_fails_when_any_core_metric_fails():
    result = classify_quality_gate(
        {
            "macro_precision": 0.65,
            "macro_recall": 0.49,
            "map50": 0.61,
            "map50_95": 0.36,
            "person_nae": 0.20,
            "road_vehicle_total_nae": 0.20,
            "median_in_memory_latency_seconds": 0.10,
        }
    )

    statuses = {row["metric"]: row["status"] for row in result["metrics"]}
    assert result["overall_status"] == "fail"
    assert statuses["macro_precision"] == "conditional"
    assert statuses["macro_recall"] == "fail"


def test_tracked_final_evidence_matches_the_frozen_source_run():
    config = load_final_report_config(CONFIG_PATH)
    evidence = json.loads(FINAL_EVIDENCE_PATH.read_text(encoding="utf-8"))

    assert evidence["source_run_id"] == config.source_run_id
    assert evidence["source_manifest_sha256"] == config.source_manifest_sha256
    assert evidence["quality_gate"]["overall_status"] == "fail"
    assert evidence["held_out_metrics"]["detection"]["evaluated_images"] == 116
    assert len(evidence["collection_breakdown"]) == 4


def test_source_group_intervals_are_reproducible():
    dataset, source = create_grouped_fixture()

    first = calculate_source_group_intervals(
        dataset, source, iterations=100, seed=2026
    )
    second = calculate_source_group_intervals(
        dataset, source, iterations=100, seed=2026
    )

    assert first == second
    assert first["macro_precision"]["source_groups"] == 2
    assert first["person_nae"]["source_groups"] == 2
    assert 0 <= first["road_vehicle_total_nae"]["lower_95"] <= 1


def test_final_evidence_plots_and_manifest_are_saved(tmp_path):
    metrics = {
        "detection": {
                "per_class": [
                    {
                        "class_name": "person",
                        "ground_truth_instances": 10,
                        "precision": 0.6,
                        "recall": 0.4,
                        "ap50": 0.5,
                        "ap50_95": 0.3,
                    },
                    {
                        "class_name": "car_or_van",
                        "ground_truth_instances": 20,
                        "precision": 0.9,
                        "recall": 0.8,
                        "ap50": 0.7,
                        "ap50_95": 0.5,
                    },
                ]
            },
            "counts": [
                {
                    "class_name": "person",
                    "examples": 2,
                    "ground_truth_total": 10,
                    "predicted_total": 4,
                    "mean_absolute_error": 3.0,
                    "normalized_absolute_error": 0.6,
                    "bias": -3.0,
                },
                {
                    "class_name": "road_vehicle_total",
                    "examples": 2,
                    "ground_truth_total": 20,
                    "predicted_total": 16,
                    "mean_absolute_error": 2.0,
                    "normalized_absolute_error": 0.2,
                    "bias": -2.0,
                },
        ],
    }
    evidence = {
        "source_run_id": "fixture",
        "quality_gate": {"overall_status": "fail", "metrics": []},
        "held_out_metrics": metrics,
        "collection_breakdown": [],
        "source_group_bootstrap_95": {},
        "runtime": {
            "summary": {
                "inference": {"median_seconds": 0.03},
                "in_memory": {"median_seconds": 0.07},
                "end_to_end": {"median_seconds": 0.08},
                "in_memory_throughput_fps": 13.0,
                "end_to_end_throughput_fps": 11.0,
            }
        },
    }

    manifest = save_final_evidence(tmp_path / "report", evidence, metrics)

    values = json.loads(manifest.read_text(encoding="utf-8"))
    assert len(values["artifacts"]) == 4
    for filename in ("per_class_detection.png", "count_error.png"):
        image = cv2.imread(str(manifest.parent / filename))
        assert image is not None
        assert image.shape[0] > 100


def create_grouped_fixture() -> tuple[EvaluationDataset, SourceEvaluationRun]:
    assets = tuple(
        EvaluationAsset(
            asset_id=f"scene-{index}",
            collection_id="fixture",
            source_group_id=f"group-{index}",
            dataset_role="held_out_test",
            image_path=Path(f"scene-{index}.jpg"),
            width=200,
            height=200,
            annotation_type="bounding_box",
            target_classes=frozenset({"person", "car_or_van"}),
        )
        for index in range(2)
    )
    box = BoundingBox(20, 20, 30, 30)
    dataset = EvaluationDataset(
        role="held_out_test",
        version="1.0-draft",
        assets=assets,
        ground_truth_boxes=(
            GroundTruthBox("scene-0", "person", box),
            GroundTruthBox("scene-0", "car_or_van", BoundingBox(80, 80, 40, 30)),
            GroundTruthBox("scene-1", "person", box),
            GroundTruthBox("scene-1", "car_or_van", BoundingBox(80, 80, 40, 30)),
        ),
        count_references=(),
    )
    predictions = (
        PredictionRecord("scene-0", "person", "person", 0.9, box),
        PredictionRecord(
            "scene-0", "car", "car_or_van", 0.9, BoundingBox(80, 80, 40, 30)
        ),
        PredictionRecord("scene-1", "person", "person", 0.9, box),
    )
    source = SourceEvaluationRun(
        run_id="fixture",
        manifest_sha256="fixture-hash",
        config=load_evaluation_config(HELD_OUT_CONFIG_PATH),
        predictions=PredictionBatch(("scene-0", "scene-1"), predictions),
        dataset_manifest_sha256="dataset-hash",
        annotation_files=(("annotations.json", "annotation-hash"),),
    )
    return dataset, source
