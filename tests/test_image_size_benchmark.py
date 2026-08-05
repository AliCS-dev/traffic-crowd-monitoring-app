import copy
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from evaluation import image_size_benchmark
from evaluation.evaluation_config import load_evaluation_config
from evaluation.evaluation_results import SavedEvaluationRun
from evaluation.image_size_benchmark import (
    ImageSizeBenchmarkError,
    calculate_image_size_comparison,
    create_image_size_evaluation_configs,
    load_image_size_benchmark_config,
    load_image_size_run,
    parse_image_size_benchmark_config,
    save_image_size_comparison,
)

BASE_CONFIG_PATH = Path("configs/evaluation/yolo26n_validation.json")
BENCHMARK_CONFIG_PATH = Path("configs/evaluation/yolo26n_image_size_benchmark.json")


def test_tracked_image_size_benchmark_configuration_is_strict():
    config = load_image_size_benchmark_config(BENCHMARK_CONFIG_PATH)

    assert config.image_sizes == (640, 960, 1280)
    assert config.base_evaluation_config == BASE_CONFIG_PATH

    values = read_json(BENCHMARK_CONFIG_PATH)
    values["image_sizes"].append(1600)
    with pytest.raises(ImageSizeBenchmarkError, match="predeclared"):
        parse_image_size_benchmark_config(values)


def test_image_size_configs_change_only_name_and_image_size():
    base = load_evaluation_config(BASE_CONFIG_PATH)
    benchmark = load_image_size_benchmark_config(BENCHMARK_CONFIG_PATH)

    configs = create_image_size_evaluation_configs(base, benchmark)

    assert tuple(config.inference.image_size for config in configs) == (
        640,
        960,
        1280,
    )
    for config in configs:
        expected = replace(
            base,
            run_name=f"{base.run_name}-image-size-{config.inference.image_size}",
            inference=replace(base.inference, image_size=config.inference.image_size),
        )
        assert config == expected

    held_out = replace(base, dataset=replace(base.dataset, role="held_out_test"))
    with pytest.raises(ImageSizeBenchmarkError, match="validation data only"):
        create_image_size_evaluation_configs(held_out, benchmark)


def test_image_size_run_loader_verifies_artifact_checksums(tmp_path: Path):
    run_directory = write_run(tmp_path, 640)

    loaded = load_image_size_run(run_directory)

    assert loaded.result.image_size == 640
    assert loaded.result.map50 == pytest.approx(0.61)
    assert loaded.result.road_vehicle_nae == pytest.approx(0.24)
    assert loaded.result.per_class[0].class_name == "person"

    (run_directory / "metrics.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ImageSizeBenchmarkError, match="checksum failed"):
        load_image_size_run(run_directory)


def test_comparison_requires_identical_fixed_settings(tmp_path: Path):
    benchmark = load_image_size_benchmark_config(BENCHMARK_CONFIG_PATH)
    loaded = tuple(
        load_image_size_run(write_run(tmp_path, size)) for size in benchmark.image_sizes
    )

    result = calculate_image_size_comparison(benchmark, loaded)

    assert tuple(run.image_size for run in result.runs) == (640, 960, 1280)
    assert result.source_commit == "abc123"

    changed = write_run(tmp_path / "changed", 960, operating_confidence=0.25)
    mismatched = (loaded[0], load_image_size_run(changed), loaded[2])
    with pytest.raises(ImageSizeBenchmarkError, match="differ by more"):
        calculate_image_size_comparison(benchmark, mismatched)


def test_image_size_comparison_saves_report_and_checksums(tmp_path: Path):
    benchmark = load_image_size_benchmark_config(BENCHMARK_CONFIG_PATH)
    loaded = tuple(
        load_image_size_run(write_run(tmp_path / "source", size))
        for size in benchmark.image_sizes
    )
    result = calculate_image_size_comparison(benchmark, loaded)

    saved = save_image_size_comparison(
        tmp_path,
        benchmark,
        result,
        created_at=datetime(2026, 8, 5, 14, 0, tzinfo=timezone.utc),
        provenance={"git": {"commit": "abc123", "dirty": False}},
    )

    assert saved.comparison_id == (
        "20260805T140000Z-yolo26n-validation-image-size-benchmark"
    )
    assert {path.name for path in saved.output_directory.iterdir()} == {
        "comparison.json",
        "summary.md",
        "comparison_manifest.json",
    }
    summary = saved.summary_path.read_text(encoding="utf-8")
    assert "| 640 | 0.7000 | 0.6000 | 0.6100 |" in summary
    assert "No held-out test data" in summary
    manifest = read_json(saved.output_directory / "comparison_manifest.json")
    for record in manifest["artifacts"]:
        path = saved.output_directory / record["filename"]
        assert sha256(path) == record["sha256"]


def test_benchmark_command_runs_every_predeclared_size(tmp_path: Path, monkeypatch):
    base_values = read_json(BASE_CONFIG_PATH)
    benchmark_values = read_json(BENCHMARK_CONFIG_PATH)
    base_path = tmp_path / BASE_CONFIG_PATH
    benchmark_path = tmp_path / BENCHMARK_CONFIG_PATH
    base_path.parent.mkdir(parents=True)
    write_json(base_path, base_values)
    write_json(benchmark_path, benchmark_values)
    observed_sizes = []

    def evaluator(repository_root, config, *, progress):
        observed_sizes.append(config.inference.image_size)
        run_directory = write_run(repository_root / "runs", config.inference.image_size)
        return SavedEvaluationRun(
            run_directory.name,
            run_directory,
            run_directory / "run_manifest.json",
        )

    monkeypatch.setattr(
        image_size_benchmark,
        "_comparison_provenance",
        lambda root: {"git": {"commit": "abc123", "dirty": False}},
    )

    saved = image_size_benchmark.run_image_size_benchmark(
        tmp_path,
        BENCHMARK_CONFIG_PATH,
        evaluator=evaluator,
        progress=lambda message: None,
    )

    assert observed_sizes == [640, 960, 1280]
    assert len(saved.source_runs) == 3
    assert saved.summary_path.is_file()


def write_run(
    root: Path,
    image_size: int,
    *,
    operating_confidence: float = 0.15,
) -> Path:
    run_id = f"run-imgsz-{image_size}"
    run_directory = root / run_id
    run_directory.mkdir(parents=True)
    configuration = copy.deepcopy(read_json(BASE_CONFIG_PATH))
    configuration["run_name"] = f"fixture-imgsz-{image_size}"
    configuration["inference"]["image_size"] = image_size
    configuration["inference"]["operating_confidence"] = operating_confidence
    artifacts = {
        "configuration.json": {
            "schema_version": 1,
            "run_id": run_id,
            "configuration": configuration,
        },
        "predictions.json": {
            "schema_version": 1,
            "run_id": run_id,
            "processed_asset_ids": [],
            "predictions": [],
        },
        "metrics.json": metrics_artifact(run_id),
        "timing.json": timing_artifact(run_id),
        "provenance.json": provenance_artifact(run_id),
    }
    for filename, value in artifacts.items():
        write_json(run_directory / filename, value)
    (run_directory / "summary.md").write_text("# Fixture summary\n", encoding="utf-8")
    paths = sorted(run_directory.iterdir())
    write_json(
        run_directory / "run_manifest.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "artifacts": [
                {"filename": path.name, "sha256": sha256(path)} for path in paths
            ],
        },
    )
    return run_directory


def metrics_artifact(run_id: str) -> dict:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "detection": {
            "macro_precision": 0.7,
            "macro_recall": 0.6,
            "map50": 0.61,
            "map50_95": 0.36,
            "ap_small": 0.2,
            "ap_medium": 0.4,
            "ap_large": 0.6,
            "per_class": [
                {
                    "class_name": "person",
                    "ground_truth_instances": 30,
                    "precision": 0.7,
                    "recall": 0.6,
                    "ap50": 0.61,
                    "ap50_95": 0.36,
                    "low_support": False,
                }
            ],
        },
        "counts": [
            {"class_name": "person", "normalized_absolute_error": 0.3},
            {
                "class_name": "road_vehicle_total",
                "normalized_absolute_error": 0.24,
            },
        ],
    }


def timing_artifact(run_id: str) -> dict:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "runtime": {
            "summary": {
                "in_memory": {"median_seconds": 0.2, "p95_seconds": 0.3},
                "in_memory_throughput_fps": 5.0,
                "peak_gpu_memory_bytes": 128 * 1024 * 1024,
            }
        },
    }


def provenance_artifact(run_id: str) -> dict:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "git": {"commit": "abc123", "dirty": False},
        "model": {"weights_sha256": "model-hash"},
        "dataset": {
            "manifest_sha256": "dataset-hash",
            "annotation_files": [
                {"path": "annotations/validation.json", "sha256": "annotation-hash"}
            ],
        },
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
