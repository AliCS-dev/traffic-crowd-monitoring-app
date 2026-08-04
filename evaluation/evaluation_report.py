import json
from pathlib import Path
from typing import Any


class EvaluationReportError(RuntimeError):
    """Raised when a saved evaluation run cannot produce a summary report."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise EvaluationReportError(
            f"Could not read evaluation artifact: {path}"
        ) from error
    except json.JSONDecodeError as error:
        raise EvaluationReportError(
            f"Evaluation artifact is not valid JSON: {path}"
        ) from error
    if not isinstance(value, dict):
        raise EvaluationReportError(
            f"Evaluation artifact must contain an object: {path}"
        )
    return value


def _number(value: float | int | None, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def _milliseconds(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 1000:.2f}"


def _text(value: Any) -> str:
    if value is None or value == "":
        return "not recorded"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _validate_run_ids(artifacts: list[dict[str, Any]]) -> str:
    run_ids = {artifact.get("run_id") for artifact in artifacts}
    if None in run_ids or len(run_ids) != 1:
        raise EvaluationReportError("Saved artifacts do not share one run identifier")
    return str(run_ids.pop())


def build_evaluation_report(
    configuration_artifact: dict[str, Any],
    metrics_artifact: dict[str, Any],
    timing_artifact: dict[str, Any],
    provenance: dict[str, Any],
) -> str:
    run_id = _validate_run_ids(
        [configuration_artifact, metrics_artifact, timing_artifact, provenance]
    )
    try:
        config = configuration_artifact["configuration"]
        detection = metrics_artifact["detection"]
        counts = metrics_artifact["counts"]
        runtime = timing_artifact["runtime"]
        summary = runtime["summary"]
    except (KeyError, TypeError) as error:
        raise EvaluationReportError(
            "Saved evaluation artifacts are incomplete"
        ) from error

    gpu = provenance.get("hardware", {}).get("gpu") or {}
    git = provenance.get("git", {})
    dataset_label = (
        f"{_text(config['dataset']['version'])} ({_text(config['dataset']['role'])})"
    )
    lines = [
        "# Detector Evaluation Summary",
        "",
        "## Run Overview",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Run ID | `{_text(run_id)}` |",
        f"| Timestamp (UTC) | {_text(provenance.get('created_at_utc'))} |",
        f"| Model | {_text(config['model']['name'])} |",
        f"| Dataset | {dataset_label} |",
        f"| Git commit | `{_text(git.get('commit'))}` |",
        f"| Working tree dirty | {_text(git.get('dirty'))} |",
        f"| Device | {_text(config['inference']['device'])} |",
        f"| GPU | {_text(gpu.get('name'))} |",
        "",
        "## Detection Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Evaluated images | {detection['evaluated_images']} |",
        f"| Ground-truth instances | {detection['ground_truth_instances']} |",
        f"| Macro precision | {_number(detection['macro_precision'])} |",
        f"| Macro recall | {_number(detection['macro_recall'])} |",
        f"| mAP50 | {_number(detection['map50'])} |",
        f"| mAP50-95 | {_number(detection['map50_95'])} |",
        f"| AP small | {_number(detection['ap_small'])} |",
        f"| AP medium | {_number(detection['ap_medium'])} |",
        f"| AP large | {_number(detection['ap_large'])} |",
        "",
        "### Per-Class Detection",
        "",
        "| Class | Support | Precision | Recall | AP50 | AP50-95 | Low support |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for metric in detection["per_class"]:
        lines.append(
            f"| {_text(metric['class_name'])} | {metric['ground_truth_instances']} | "
            f"{_number(metric['precision'])} | {_number(metric['recall'])} | "
            f"{_number(metric['ap50'])} | {_number(metric['ap50_95'])} | "
            f"{'yes' if metric['low_support'] else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Count Metrics",
            "",
            "| Class | Examples | Ground truth | Predicted | MAE | NAE | Bias | "
            "Low support |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for metric in counts:
        lines.append(
            f"| {_text(metric['class_name'])} | {metric['examples']} | "
            f"{metric['ground_truth_total']} | {metric['predicted_total']} | "
            f"{_number(metric['mean_absolute_error'])} | "
            f"{_number(metric['normalized_absolute_error'])} | "
            f"{_number(metric['bias'])} | "
            f"{'yes' if metric['low_support'] else 'no'} |"
        )

    stage_labels = (
        ("loading", "Image loading"),
        ("preprocessing", "Application preprocessing"),
        ("inference", "Model inference and postprocessing"),
        ("conversion", "Detection-record conversion"),
        ("in_memory", "Complete in-memory processing"),
        ("end_to_end", "End-to-end processing"),
    )
    lines.extend(
        [
            "",
            "## Runtime Metrics",
            "",
            "| Stage | Median (ms) | P95 (ms) | Total (s) |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for field, label in stage_labels:
        stage = summary[field]
        lines.append(
            f"| {label} | {_milliseconds(stage['median_seconds'])} | "
            f"{_milliseconds(stage['p95_seconds'])} | "
            f"{_number(stage['total_seconds'], 3)} |"
        )

    peak_memory = summary["peak_gpu_memory_bytes"]
    peak_memory_mib = peak_memory / (1024 * 1024) if peak_memory is not None else None
    measured_frames = runtime["measured_frames_per_repetition"]
    in_memory_fps = _number(summary["in_memory_throughput_fps"], 2)
    end_to_end_fps = _number(summary["end_to_end_throughput_fps"], 2)
    lines.extend(
        [
            "",
            f"- Warm-up frames: {runtime['warmup_frames']}",
            f"- Measured frames per repetition: {measured_frames}",
            f"- Repetitions: {runtime['repetitions']}",
            f"- In-memory throughput: {in_memory_fps} FPS",
            f"- End-to-end throughput: {end_to_end_fps} FPS",
            f"- Peak allocated GPU memory: {_number(peak_memory_mib, 2)} MiB",
            "",
            "Low-support classes are reported for transparency but should not be "
            "used alone to make a model-quality claim.",
            "",
        ]
    )
    return "\n".join(lines)


def generate_evaluation_report(run_directory: Path) -> Path:
    configuration = _read_json(run_directory / "configuration.json")
    metrics = _read_json(run_directory / "metrics.json")
    timing = _read_json(run_directory / "timing.json")
    provenance = _read_json(run_directory / "provenance.json")
    report = build_evaluation_report(configuration, metrics, timing, provenance)
    output_path = run_directory / "summary.md"
    try:
        output_path.write_text(report, encoding="utf-8")
    except OSError as error:
        raise EvaluationReportError(
            f"Could not write evaluation report: {output_path}"
        ) from error
    return output_path
