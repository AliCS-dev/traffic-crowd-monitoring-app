import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from evaluation.confidence_sweep import SourceEvaluationRun
from evaluation.evaluation_data import EvaluationDataset, PredictionRecord
from evaluation.evaluation_metrics import (
    ROAD_VEHICLE_TOTAL,
    calculate_count_metrics,
    calculate_detection_metrics,
)


class FinalQualityGateError(RuntimeError):
    """Raised when final evidence cannot be derived reproducibly."""


@dataclass(frozen=True)
class FinalReportConfig:
    schema_version: int
    report_name: str
    source_run_id: str
    source_manifest_sha256: str
    bootstrap_iterations: int
    bootstrap_seed: int
    output_directory: Path


HIGHER_IS_BETTER = {
    "macro_precision": (0.70, 0.60),
    "macro_recall": (0.60, 0.50),
    "map50": (0.60, 0.50),
    "map50_95": (0.35, 0.25),
}
LOWER_IS_BETTER = {
    "person_nae": (0.25, 0.35),
    "road_vehicle_total_nae": (0.25, 0.35),
    "median_in_memory_latency_seconds": (0.50, 1.00),
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FinalQualityGateError(f"Could not read JSON file: {path}") from error
    if not isinstance(value, dict):
        raise FinalQualityGateError(f"JSON file must contain an object: {path}")
    return value


def _relative_path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise FinalQualityGateError(f"{field} must be a non-empty string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise FinalQualityGateError(f"{field} must be repository-relative")
    return path


def load_final_report_config(path: Path) -> FinalReportConfig:
    values = _read_json(path)
    required = {
        "schema_version",
        "report_name",
        "source_run_id",
        "source_manifest_sha256",
        "bootstrap_iterations",
        "bootstrap_seed",
        "output_directory",
    }
    if set(values) != required:
        raise FinalQualityGateError("Final-report configuration fields are invalid")
    if values["schema_version"] != 1:
        raise FinalQualityGateError("Final-report schema_version must be 1")
    for field in ("report_name", "source_run_id", "source_manifest_sha256"):
        if not isinstance(values[field], str) or not values[field]:
            raise FinalQualityGateError(f"{field} must be a non-empty string")
    iterations = values["bootstrap_iterations"]
    seed = values["bootstrap_seed"]
    if (
        isinstance(iterations, bool)
        or not isinstance(iterations, int)
        or iterations < 100
    ):
        raise FinalQualityGateError("bootstrap_iterations must be at least 100")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise FinalQualityGateError("bootstrap_seed must be an integer")
    return FinalReportConfig(
        schema_version=1,
        report_name=values["report_name"],
        source_run_id=values["source_run_id"],
        source_manifest_sha256=values["source_manifest_sha256"],
        bootstrap_iterations=iterations,
        bootstrap_seed=seed,
        output_directory=_relative_path(values["output_directory"], "output_directory"),
    )


def _subset_dataset(
    dataset: EvaluationDataset, asset_ids: set[str]
) -> EvaluationDataset:
    return EvaluationDataset(
        role=dataset.role,
        version=dataset.version,
        assets=tuple(asset for asset in dataset.assets if asset.asset_id in asset_ids),
        ground_truth_boxes=tuple(
            box for box in dataset.ground_truth_boxes if box.asset_id in asset_ids
        ),
        count_references=tuple(
            count for count in dataset.count_references if count.asset_id in asset_ids
        ),
    )


def _subset_predictions(
    predictions: list[PredictionRecord], asset_ids: set[str]
) -> list[PredictionRecord]:
    return [item for item in predictions if item.asset_id in asset_ids]


def _metric_settings(source: SourceEvaluationRun) -> dict[str, Any]:
    return {
        "confidence_floor": source.config.inference.confidence_floor,
        "operating_confidence": source.config.inference.operating_confidence,
        "operating_iou": source.config.metrics.operating_iou,
        "max_detections": source.config.inference.max_detections,
        "low_support_threshold": source.config.metrics.low_support_threshold,
    }


def calculate_collection_breakdown(
    dataset: EvaluationDataset, source: SourceEvaluationRun
) -> list[dict[str, Any]]:
    predictions = list(source.predictions.predictions)
    settings = _metric_settings(source)
    collection_assets: dict[str, set[str]] = defaultdict(set)
    for asset in dataset.assets:
        collection_assets[asset.collection_id].add(asset.asset_id)

    rows = []
    for collection_id, asset_ids in sorted(collection_assets.items()):
        subset = _subset_dataset(dataset, asset_ids)
        subset_predictions = _subset_predictions(predictions, asset_ids)
        row: dict[str, Any] = {
            "collection_id": collection_id,
            "source_groups": len({asset.source_group_id for asset in subset.assets}),
            "images": len(subset.assets),
            "detection": None,
            "counts": [],
        }
        if any(asset.annotation_type == "bounding_box" for asset in subset.assets):
            detection = calculate_detection_metrics(
                subset,
                subset_predictions,
                **settings,
            )
            row["detection"] = {
                "evaluated_images": detection.evaluated_images,
                "ground_truth_instances": detection.ground_truth_instances,
                "macro_precision": detection.macro_precision,
                "macro_recall": detection.macro_recall,
                "map50": detection.map50,
                "map50_95": detection.map50_95,
                "ap_small": detection.ap_small,
                "ap_medium": detection.ap_medium,
                "ap_large": detection.ap_large,
            }
        counts = calculate_count_metrics(
            subset,
            subset_predictions,
            operating_confidence=settings["operating_confidence"],
            low_support_threshold=settings["low_support_threshold"],
        )
        row["counts"] = [
            {
                "class_name": metric.class_name,
                "examples": metric.examples,
                "ground_truth_total": metric.ground_truth_total,
                "predicted_total": metric.predicted_total,
                "mean_absolute_error": metric.mean_absolute_error,
                "normalized_absolute_error": metric.normalized_absolute_error,
                "bias": metric.bias,
            }
            for metric in counts
        ]
        rows.append(row)
    return rows


def _percentile_interval(values: list[float]) -> tuple[float, float]:
    lower, upper = np.percentile(np.asarray(values), [2.5, 97.5])
    return float(lower), float(upper)


def calculate_source_group_intervals(
    dataset: EvaluationDataset,
    source: SourceEvaluationRun,
    *,
    iterations: int,
    seed: int,
) -> dict[str, dict[str, float | int]]:
    predictions = list(source.predictions.predictions)
    settings = _metric_settings(source)
    groups: dict[str, set[str]] = defaultdict(set)
    for asset in dataset.assets:
        groups[asset.source_group_id].add(asset.asset_id)

    detection_groups: dict[str, dict[str, tuple[int, int, int]]] = {}
    count_groups: dict[str, dict[str, tuple[float, int]]] = {}
    for group_id, asset_ids in sorted(groups.items()):
        subset = _subset_dataset(dataset, asset_ids)
        subset_predictions = _subset_predictions(predictions, asset_ids)
        if any(asset.annotation_type == "bounding_box" for asset in subset.assets):
            metrics = calculate_detection_metrics(
                subset,
                subset_predictions,
                **settings,
            )
            detection_groups[group_id] = {
                metric.class_name: (
                    metric.true_positives,
                    metric.false_positives,
                    metric.false_negatives,
                )
                for metric in metrics.per_class
            }
        counts = calculate_count_metrics(
            subset,
            subset_predictions,
            operating_confidence=settings["operating_confidence"],
            low_support_threshold=settings["low_support_threshold"],
        )
        count_groups[group_id] = {
            metric.class_name: (
                metric.mean_absolute_error * metric.examples,
                metric.ground_truth_total,
            )
            for metric in counts
        }

    rng = np.random.default_rng(seed)
    detection_ids = tuple(detection_groups)
    person_ids = tuple(
        group_id for group_id, values in count_groups.items() if "person" in values
    )
    vehicle_ids = tuple(
        group_id
        for group_id, values in count_groups.items()
        if ROAD_VEHICLE_TOTAL in values
    )
    sampled_precision: list[float] = []
    sampled_recall: list[float] = []
    sampled_person_nae: list[float] = []
    sampled_vehicle_nae: list[float] = []

    for _ in range(iterations):
        sampled_detection_ids = rng.choice(
            detection_ids, size=len(detection_ids), replace=True
        )
        class_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        for group_id in sampled_detection_ids:
            for class_name, values in detection_groups[str(group_id)].items():
                for index, value in enumerate(values):
                    class_totals[class_name][index] += value
        precisions = []
        recalls = []
        for true_positives, false_positives, false_negatives in class_totals.values():
            if true_positives + false_positives:
                precisions.append(true_positives / (true_positives + false_positives))
            if true_positives + false_negatives:
                recalls.append(true_positives / (true_positives + false_negatives))
        sampled_precision.append(float(np.mean(precisions)))
        sampled_recall.append(float(np.mean(recalls)))

        for group_ids, metric_name, destination in (
            (person_ids, "person", sampled_person_nae),
            (vehicle_ids, ROAD_VEHICLE_TOTAL, sampled_vehicle_nae),
        ):
            sampled_ids = rng.choice(group_ids, size=len(group_ids), replace=True)
            absolute_error = 0.0
            ground_truth = 0
            for group_id in sampled_ids:
                error, support = count_groups[str(group_id)][metric_name]
                absolute_error += error
                ground_truth += support
            destination.append(absolute_error / ground_truth)

    values = {
        "macro_precision": (sampled_precision, len(detection_ids)),
        "macro_recall": (sampled_recall, len(detection_ids)),
        "person_nae": (sampled_person_nae, len(person_ids)),
        "road_vehicle_total_nae": (sampled_vehicle_nae, len(vehicle_ids)),
    }
    intervals = {}
    for name, (samples, group_count) in values.items():
        lower, upper = _percentile_interval(samples)
        intervals[name] = {
            "lower_95": lower,
            "upper_95": upper,
            "source_groups": group_count,
            "bootstrap_iterations": iterations,
            "seed": seed,
        }
    return intervals


def classify_quality_gate(metrics: dict[str, float]) -> dict[str, Any]:
    results = []
    for name, (pass_threshold, conditional_threshold) in HIGHER_IS_BETTER.items():
        value = metrics[name]
        status = (
            "pass"
            if value >= pass_threshold
            else "conditional"
            if value >= conditional_threshold
            else "fail"
        )
        results.append(
            {
                "metric": name,
                "value": value,
                "pass_threshold": pass_threshold,
                "conditional_threshold": conditional_threshold,
                "direction": "higher_is_better",
                "status": status,
            }
        )
    for name, (pass_threshold, conditional_threshold) in LOWER_IS_BETTER.items():
        value = metrics[name]
        status = (
            "pass"
            if value <= pass_threshold
            else "conditional"
            if value <= conditional_threshold
            else "fail"
        )
        results.append(
            {
                "metric": name,
                "value": value,
                "pass_threshold": pass_threshold,
                "conditional_threshold": conditional_threshold,
                "direction": "lower_is_better",
                "status": status,
            }
        )
    if any(row["status"] == "fail" for row in results):
        overall = "fail"
    elif any(row["status"] == "conditional" for row in results):
        overall = "conditional"
    else:
        overall = "pass"
    return {"overall_status": overall, "metrics": results}


def build_final_evidence(
    dataset: EvaluationDataset,
    source: SourceEvaluationRun,
    metrics_artifact: dict[str, Any],
    timing_artifact: dict[str, Any],
    provenance_artifact: dict[str, Any],
    config: FinalReportConfig,
) -> dict[str, Any]:
    if dataset.role != "held_out_test" or source.config.dataset.role != "held_out_test":
        raise FinalQualityGateError("Final report requires a held-out source run")
    if source.run_id != config.source_run_id:
        raise FinalQualityGateError("Configured source run ID does not match")
    if source.manifest_sha256 != config.source_manifest_sha256:
        raise FinalQualityGateError("Configured source manifest hash does not match")
    detection = metrics_artifact["detection"]
    counts = {row["class_name"]: row for row in metrics_artifact["counts"]}
    latency = timing_artifact["runtime"]["summary"]["in_memory"]["median_seconds"]
    gate_values = {
        "macro_precision": detection["macro_precision"],
        "macro_recall": detection["macro_recall"],
        "map50": detection["map50"],
        "map50_95": detection["map50_95"],
        "person_nae": counts["person"]["normalized_absolute_error"],
        "road_vehicle_total_nae": counts[ROAD_VEHICLE_TOTAL][
            "normalized_absolute_error"
        ],
        "median_in_memory_latency_seconds": latency,
    }
    return {
        "schema_version": 1,
        "source_run_id": source.run_id,
        "source_manifest_sha256": source.manifest_sha256,
        "held_out_metrics": metrics_artifact,
        "runtime": {
            "warmup_frames": timing_artifact["runtime"]["warmup_frames"],
            "measured_frames_per_repetition": timing_artifact["runtime"][
                "measured_frames_per_repetition"
            ],
            "repetitions": timing_artifact["runtime"]["repetitions"],
            "summary": timing_artifact["runtime"]["summary"],
        },
        "provenance": {
            "created_at_utc": provenance_artifact["created_at_utc"],
            "git": provenance_artifact["git"],
            "model": provenance_artifact["model"],
            "hardware": provenance_artifact["hardware"],
            "operating_system": provenance_artifact["operating_system"],
            "python": provenance_artifact["python"],
            "dependencies": provenance_artifact["dependencies"],
            "dataset": provenance_artifact["dataset"],
        },
        "quality_gate": classify_quality_gate(gate_values),
        "source_group_bootstrap_95": calculate_source_group_intervals(
            dataset,
            source,
            iterations=config.bootstrap_iterations,
            seed=config.bootstrap_seed,
        ),
        "collection_breakdown": calculate_collection_breakdown(dataset, source),
    }


def _number(value: float | int | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def build_final_summary(evidence: dict[str, Any]) -> str:
    metrics = evidence["held_out_metrics"]
    detection = metrics["detection"]
    lines = [
        "# Generated Final Quality-Gate Tables",
        "",
        f"- Source run: `{evidence['source_run_id']}`",
        f"- Decision: **{evidence['quality_gate']['overall_status'].upper()}**",
        "",
        "## Gate Comparison",
        "",
        "| Metric | Value | Pass threshold | Status |",
        "| --- | ---: | ---: | --- |",
    ]
    for row in evidence["quality_gate"]["metrics"]:
        direction = ">=" if row["direction"] == "higher_is_better" else "<="
        lines.append(
            f"| {row['metric']} | {_number(row['value'])} | "
            f"{direction} {_number(row['pass_threshold'])} | {row['status']} |"
        )
    lines.extend(
        [
            "",
            "## Detection By Class",
            "",
            "| Class | Support | Precision | Recall | AP50 | AP50-95 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in detection["per_class"]:
        lines.append(
            f"| {row['class_name']} | {row['ground_truth_instances']} | "
            f"{_number(row['precision'])} | {_number(row['recall'])} | "
            f"{_number(row['ap50'])} | {_number(row['ap50_95'])} |"
        )
    lines.extend(
        [
            "",
            "## Count Error",
            "",
            "| Class | Examples | Ground truth | Predicted | MAE | NAE | Bias |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in metrics["counts"]:
        lines.append(
            f"| {row['class_name']} | {row['examples']} | "
            f"{row['ground_truth_total']} | {row['predicted_total']} | "
            f"{_number(row['mean_absolute_error'])} | "
            f"{_number(row['normalized_absolute_error'])} | "
            f"{_number(row['bias'])} |"
        )
    lines.extend(
        [
            "",
            "## Collection Breakdown",
            "",
            "| Collection | Images | mAP50 | mAP50-95 | Person NAE | Vehicle NAE |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for collection in evidence["collection_breakdown"]:
        collection_counts = {
            row["class_name"]: row for row in collection["counts"]
        }
        collection_detection = collection["detection"] or {}
        person = collection_counts.get("person", {})
        vehicle = collection_counts.get(ROAD_VEHICLE_TOTAL, {})
        lines.append(
            f"| {collection['collection_id']} | {collection['images']} | "
            f"{_number(collection_detection.get('map50'))} | "
            f"{_number(collection_detection.get('map50_95'))} | "
            f"{_number(person.get('normalized_absolute_error'))} | "
            f"{_number(vehicle.get('normalized_absolute_error'))} |"
        )
    lines.extend(
        [
            "",
            "## Source-Group Bootstrap Intervals",
            "",
            "| Metric | Lower 95% | Upper 95% | Source groups |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for name, interval in evidence["source_group_bootstrap_95"].items():
        lines.append(
            f"| {name} | {_number(interval['lower_95'])} | "
            f"{_number(interval['upper_95'])} | {interval['source_groups']} |"
        )
    runtime = evidence["runtime"]["summary"]
    inference_ms = runtime["inference"]["median_seconds"] * 1000
    in_memory_ms = runtime["in_memory"]["median_seconds"] * 1000
    end_to_end_ms = runtime["end_to_end"]["median_seconds"] * 1000
    in_memory_fps = runtime["in_memory_throughput_fps"]
    end_to_end_fps = runtime["end_to_end_throughput_fps"]
    lines.extend(
        [
            "",
            "## Runtime",
            "",
            "| Measure | Value |",
            "| --- | ---: |",
            f"| Median inference | {inference_ms:.2f} ms |",
            f"| Median in-memory | {in_memory_ms:.2f} ms |",
            f"| Median end-to-end | {end_to_end_ms:.2f} ms |",
            f"| In-memory throughput | {in_memory_fps:.2f} FPS |",
            f"| End-to-end throughput | {end_to_end_fps:.2f} FPS |",
            "",
            "This file is generated from checksum-verified saved predictions. "
            "It does not run inference or tune the model.",
            "",
        ]
    )
    return "\n".join(lines)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_chart(
    path: Path,
    title: str,
    labels: list[str],
    series: list[tuple[str, list[float], tuple[int, int, int]]],
    *,
    maximum: float,
) -> None:
    width = 1200
    row_height = 74
    height = 150 + row_height * len(labels)
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.putText(image, title, (45, 55), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (25, 25, 25), 2)
    chart_left, chart_right = 300, 1120
    for index, label in enumerate(labels):
        y = 115 + index * row_height
        cv2.putText(
            image,
            label,
            (45, y + 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (35, 35, 35),
            1,
        )
        bar_height = max(12, 40 // len(series))
        for series_index, (_, values, color) in enumerate(series):
            value = values[index]
            top = y + series_index * (bar_height + 4)
            relative_width = min(value / maximum, 1.0)
            end = chart_left + int((chart_right - chart_left) * relative_width)
            cv2.rectangle(image, (chart_left, top), (end, top + bar_height), color, -1)
            cv2.putText(
                image,
                f"{value:.3f}",
                (min(end + 8, chart_right - 65), top + bar_height - 1),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (30, 30, 30),
                1,
            )
    legend_x = 45
    for name, _, color in series:
        cv2.rectangle(
            image,
            (legend_x, height - 38),
            (legend_x + 20, height - 18),
            color,
            -1,
        )
        cv2.putText(
            image,
            name,
            (legend_x + 28, height - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (30, 30, 30),
            1,
        )
        legend_x += 190
    if not cv2.imwrite(str(path), image):
        raise FinalQualityGateError(f"Could not write plot: {path}")


def save_final_evidence(
    output_directory: Path,
    evidence: dict[str, Any],
    metrics_artifact: dict[str, Any],
) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    allowed_files = {
        "count_error.png",
        "final_evidence.json",
        "manifest.json",
        "per_class_detection.png",
        "summary.md",
    }
    unexpected = {path.name for path in output_directory.iterdir()} - allowed_files
    if unexpected:
        raise FinalQualityGateError(
            "Final-report directory contains unexpected files: "
            f"{', '.join(sorted(unexpected))}"
        )
    evidence_path = output_directory / "final_evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (output_directory / "summary.md").write_text(
        build_final_summary(evidence), encoding="utf-8"
    )
    detection = metrics_artifact["detection"]
    per_class = detection["per_class"]
    _write_chart(
        output_directory / "per_class_detection.png",
        "Held-out detection by class",
        [row["class_name"] for row in per_class],
        [
            ("AP50", [row["ap50"] for row in per_class], (194, 116, 47)),
            ("Recall", [row["recall"] for row in per_class], (70, 150, 70)),
        ],
        maximum=1.0,
    )
    count_rows = [
        row
        for row in metrics_artifact["counts"]
        if row["normalized_absolute_error"] is not None
    ]
    _write_chart(
        output_directory / "count_error.png",
        "Held-out normalized absolute count error",
        [row["class_name"] for row in count_rows],
        [
            (
                "NAE",
                [row["normalized_absolute_error"] for row in count_rows],
                (65, 91, 210),
            )
        ],
        maximum=1.0,
    )
    artifacts = []
    for path in sorted(output_directory.iterdir()):
        if path.name == "manifest.json":
            continue
        artifacts.append(
            {
                "filename": path.name,
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    manifest_path = output_directory / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_run_id": evidence["source_run_id"],
                "artifacts": artifacts,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path
