import copy
import hashlib
import json
import platform
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from evaluation.evaluation_command import execute_detector_evaluation
from evaluation.evaluation_config import (
    EvaluationConfig,
    load_evaluation_config,
    parse_evaluation_config,
)
from evaluation.evaluation_results import SavedEvaluationRun

PREDECLARED_IMAGE_SIZES = (640, 960, 1280)


class ImageSizeBenchmarkError(RuntimeError):
    """Raised when an image-size benchmark is invalid or incomplete."""


@dataclass(frozen=True)
class ImageSizeBenchmarkConfig:
    schema_version: int
    benchmark_name: str
    protocol_version: str
    base_evaluation_config: Path
    image_sizes: tuple[int, ...]
    output_directory: Path


@dataclass(frozen=True)
class ImageSizeClassResult:
    class_name: str
    support: int
    precision: float
    recall: float
    ap50: float
    ap50_95: float
    low_support: bool


@dataclass(frozen=True)
class ImageSizeResult:
    image_size: int
    run_id: str
    run_manifest_sha256: str
    macro_precision: float
    macro_recall: float
    map50: float
    map50_95: float
    ap_small: float | None
    ap_medium: float | None
    ap_large: float | None
    person_nae: float | None
    road_vehicle_nae: float | None
    median_latency_seconds: float
    p95_latency_seconds: float
    throughput_fps: float
    peak_gpu_memory_bytes: int | None
    per_class: tuple[ImageSizeClassResult, ...]


@dataclass(frozen=True)
class LoadedImageSizeRun:
    config: EvaluationConfig
    raw_configuration: dict[str, Any]
    result: ImageSizeResult
    git_commit: str
    git_dirty: bool
    model_weights_sha256: str
    dataset_manifest_sha256: str
    annotation_files: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ImageSizeBenchmarkResult:
    protocol_version: str
    source_commit: str
    operating_confidence: float
    fixed_scale_factor: int
    runs: tuple[ImageSizeResult, ...]


@dataclass(frozen=True)
class SavedImageSizeBenchmark:
    comparison_id: str
    output_directory: Path
    summary_path: Path
    source_runs: tuple[SavedEvaluationRun, ...]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ImageSizeBenchmarkError(f"Could not read JSON file: {path}") from error
    except json.JSONDecodeError as error:
        raise ImageSizeBenchmarkError(f"File is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ImageSizeBenchmarkError(f"JSON file must contain an object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    try:
        path.write_text(
            json.dumps(_json_value(value), indent=2, sort_keys=True, allow_nan=False)
            + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as error:
        raise ImageSizeBenchmarkError(
            f"Could not write benchmark artifact: {path}"
        ) from error


def _json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ImageSizeBenchmarkError(f"Could not hash file: {path}") from error
    return digest.hexdigest()


def _relative_path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ImageSizeBenchmarkError(f"{field} must be a non-empty string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ImageSizeBenchmarkError(f"{field} must be repository-relative")
    return path


def parse_image_size_benchmark_config(
    values: dict[str, Any],
) -> ImageSizeBenchmarkConfig:
    required = {
        "schema_version",
        "benchmark_name",
        "protocol_version",
        "base_evaluation_config",
        "image_sizes",
        "output_directory",
    }
    if set(values) != required:
        missing = required - set(values)
        unknown = set(values) - required
        details = []
        if missing:
            details.append(f"missing: {', '.join(sorted(missing))}")
        if unknown:
            details.append(f"unknown: {', '.join(sorted(unknown))}")
        raise ImageSizeBenchmarkError(
            f"Image-size benchmark fields are invalid ({'; '.join(details)})"
        )
    if values["schema_version"] != 1:
        raise ImageSizeBenchmarkError("Image-size benchmark schema_version must be 1")
    name = values["benchmark_name"]
    protocol_version = values["protocol_version"]
    if not isinstance(name, str) or not name:
        raise ImageSizeBenchmarkError("benchmark_name must be a non-empty string")
    if not isinstance(protocol_version, str) or not protocol_version:
        raise ImageSizeBenchmarkError("protocol_version must be a non-empty string")
    image_sizes = values["image_sizes"]
    if not isinstance(image_sizes, list) or any(
        isinstance(value, bool) or not isinstance(value, int) for value in image_sizes
    ):
        raise ImageSizeBenchmarkError("image_sizes must be a list of integers")
    sizes = tuple(image_sizes)
    if sizes != PREDECLARED_IMAGE_SIZES:
        raise ImageSizeBenchmarkError(
            "image_sizes must match the predeclared Issue #40 values"
        )
    return ImageSizeBenchmarkConfig(
        schema_version=1,
        benchmark_name=name,
        protocol_version=protocol_version,
        base_evaluation_config=_relative_path(
            values["base_evaluation_config"], "base_evaluation_config"
        ),
        image_sizes=sizes,
        output_directory=_relative_path(values["output_directory"], "output_directory"),
    )


def load_image_size_benchmark_config(path: Path) -> ImageSizeBenchmarkConfig:
    return parse_image_size_benchmark_config(_read_json(path))


def create_image_size_evaluation_configs(
    base_config: EvaluationConfig,
    benchmark_config: ImageSizeBenchmarkConfig,
) -> tuple[EvaluationConfig, ...]:
    if base_config.dataset.role != "validation":
        raise ImageSizeBenchmarkError("Image-size tuning may use validation data only")
    if base_config.protocol_version != benchmark_config.protocol_version:
        raise ImageSizeBenchmarkError(
            "Benchmark and base protocol versions do not match"
        )
    return tuple(
        replace(
            base_config,
            run_name=f"{base_config.run_name}-image-size-{image_size}",
            inference=replace(base_config.inference, image_size=image_size),
        )
        for image_size in benchmark_config.image_sizes
    )


def _verify_run_manifest(run_directory: Path) -> tuple[str, str]:
    manifest_path = run_directory / "run_manifest.json"
    manifest = _read_json(manifest_path)
    try:
        run_id = manifest["run_id"]
        artifacts = manifest["artifacts"]
    except KeyError as error:
        raise ImageSizeBenchmarkError(
            "Evaluation run manifest is incomplete"
        ) from error
    if not isinstance(run_id, str) or not isinstance(artifacts, list):
        raise ImageSizeBenchmarkError("Evaluation run manifest has invalid fields")
    filenames = []
    for artifact in artifacts:
        try:
            filename = artifact["filename"]
            expected_hash = artifact["sha256"]
        except (KeyError, TypeError) as error:
            raise ImageSizeBenchmarkError(
                "Evaluation artifact record is invalid"
            ) from error
        path = Path(filename)
        if path.name != filename:
            raise ImageSizeBenchmarkError("Evaluation artifact filename must be local")
        if _sha256(run_directory / path) != expected_hash:
            raise ImageSizeBenchmarkError(
                f"Evaluation artifact checksum failed: {filename}"
            )
        filenames.append(filename)
    if len(filenames) != len(set(filenames)):
        raise ImageSizeBenchmarkError(
            "Evaluation run manifest contains duplicate artifacts"
        )
    required = {
        "configuration.json",
        "predictions.json",
        "metrics.json",
        "timing.json",
        "provenance.json",
        "summary.md",
    }
    if not required <= set(filenames):
        raise ImageSizeBenchmarkError(
            "Evaluation run manifest omits required artifacts"
        )
    return run_id, _sha256(manifest_path)


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ImageSizeBenchmarkError(f"{field} must be numeric")
    return float(value)


def _optional_number(value: Any, field: str) -> float | None:
    return None if value is None else _number(value, field)


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ImageSizeBenchmarkError(f"{field} must be an integer")
    return value


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ImageSizeBenchmarkError(f"{field} must be boolean")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ImageSizeBenchmarkError(f"{field} must be a non-empty string")
    return value


def _same_run_id(run_id: str, *artifacts: dict[str, Any]) -> None:
    if any(artifact.get("run_id") != run_id for artifact in artifacts):
        raise ImageSizeBenchmarkError(
            "Evaluation artifacts do not share the manifest run ID"
        )


def load_image_size_run(run_directory: Path) -> LoadedImageSizeRun:
    run_id, manifest_hash = _verify_run_manifest(run_directory)
    configuration_artifact = _read_json(run_directory / "configuration.json")
    metrics_artifact = _read_json(run_directory / "metrics.json")
    timing_artifact = _read_json(run_directory / "timing.json")
    provenance = _read_json(run_directory / "provenance.json")
    _same_run_id(
        run_id, configuration_artifact, metrics_artifact, timing_artifact, provenance
    )
    try:
        raw_configuration = configuration_artifact["configuration"]
        if not isinstance(raw_configuration, dict):
            raise ImageSizeBenchmarkError("Saved evaluation configuration is invalid")
        config = parse_evaluation_config(raw_configuration)
        detection = metrics_artifact["detection"]
        counts = metrics_artifact["counts"]
        runtime = timing_artifact["runtime"]["summary"]
        git = provenance["git"]
        model = provenance["model"]
        dataset = provenance["dataset"]
    except (KeyError, TypeError, ValueError) as error:
        raise ImageSizeBenchmarkError(
            "Evaluation run artifacts are incomplete"
        ) from error
    if not isinstance(counts, list) or not isinstance(detection.get("per_class"), list):
        raise ImageSizeBenchmarkError("Evaluation metric records are invalid")
    count_by_name = {
        value.get("class_name"): value for value in counts if isinstance(value, dict)
    }
    try:
        person_nae = count_by_name["person"]["normalized_absolute_error"]
        vehicle_nae = count_by_name["road_vehicle_total"]["normalized_absolute_error"]
    except (KeyError, TypeError) as error:
        raise ImageSizeBenchmarkError(
            "Evaluation count metrics omit required aggregates"
        ) from error
    per_class = []
    try:
        for value in detection["per_class"]:
            per_class.append(
                ImageSizeClassResult(
                    class_name=_text(value["class_name"], "class_name"),
                    support=_integer(value["ground_truth_instances"], "support"),
                    precision=_number(value["precision"], "precision"),
                    recall=_number(value["recall"], "recall"),
                    ap50=_number(value["ap50"], "ap50"),
                    ap50_95=_number(value["ap50_95"], "ap50_95"),
                    low_support=_boolean(value["low_support"], "low_support"),
                )
            )
        annotation_files = tuple(
            sorted(
                (
                    _text(value["path"], "annotation path"),
                    _text(value["sha256"], "annotation hash"),
                )
                for value in dataset["annotation_files"]
            )
        )
        dirty = _boolean(git["dirty"], "git.dirty")
        peak_memory = runtime["peak_gpu_memory_bytes"]
        if peak_memory is not None:
            peak_memory = _integer(peak_memory, "peak_gpu_memory_bytes")
        result = ImageSizeResult(
            image_size=config.inference.image_size,
            run_id=run_id,
            run_manifest_sha256=manifest_hash,
            macro_precision=_number(detection["macro_precision"], "macro_precision"),
            macro_recall=_number(detection["macro_recall"], "macro_recall"),
            map50=_number(detection["map50"], "map50"),
            map50_95=_number(detection["map50_95"], "map50_95"),
            ap_small=_optional_number(detection["ap_small"], "ap_small"),
            ap_medium=_optional_number(detection["ap_medium"], "ap_medium"),
            ap_large=_optional_number(detection["ap_large"], "ap_large"),
            person_nae=_optional_number(person_nae, "person NAE"),
            road_vehicle_nae=_optional_number(vehicle_nae, "vehicle NAE"),
            median_latency_seconds=_number(
                runtime["in_memory"]["median_seconds"], "median latency"
            ),
            p95_latency_seconds=_number(
                runtime["in_memory"]["p95_seconds"], "p95 latency"
            ),
            throughput_fps=_number(runtime["in_memory_throughput_fps"], "throughput"),
            peak_gpu_memory_bytes=peak_memory,
            per_class=tuple(per_class),
        )
    except (KeyError, TypeError) as error:
        raise ImageSizeBenchmarkError(
            "Evaluation result values are incomplete"
        ) from error
    return LoadedImageSizeRun(
        config=config,
        raw_configuration=raw_configuration,
        result=result,
        git_commit=_text(git["commit"], "git.commit"),
        git_dirty=dirty,
        model_weights_sha256=_text(model["weights_sha256"], "weights_sha256"),
        dataset_manifest_sha256=_text(
            dataset["manifest_sha256"], "dataset manifest hash"
        ),
        annotation_files=annotation_files,
    )


def _fixed_configuration(values: dict[str, Any]) -> str:
    fixed = copy.deepcopy(values)
    try:
        fixed.pop("run_name")
        fixed["inference"].pop("image_size")
    except (KeyError, TypeError) as error:
        raise ImageSizeBenchmarkError(
            "Saved evaluation configuration cannot be compared"
        ) from error
    return json.dumps(fixed, sort_keys=True, allow_nan=False)


def calculate_image_size_comparison(
    benchmark_config: ImageSizeBenchmarkConfig,
    loaded_runs: tuple[LoadedImageSizeRun, ...],
) -> ImageSizeBenchmarkResult:
    by_size = {run.result.image_size: run for run in loaded_runs}
    if len(by_size) != len(loaded_runs):
        raise ImageSizeBenchmarkError("Image-size runs contain duplicate sizes")
    if set(by_size) != set(benchmark_config.image_sizes):
        raise ImageSizeBenchmarkError(
            "Image-size runs do not match the complete predeclared benchmark"
        )
    ordered = tuple(by_size[size] for size in benchmark_config.image_sizes)
    for run in ordered:
        if run.config.dataset.role != "validation":
            raise ImageSizeBenchmarkError("Image-size tuning may use validation only")
        if run.config.protocol_version != benchmark_config.protocol_version:
            raise ImageSizeBenchmarkError(
                "Image-size run protocol does not match the benchmark"
            )
        if run.git_dirty:
            raise ImageSizeBenchmarkError(
                f"Image-size run was created from a dirty tree: {run.result.run_id}"
            )
    first = ordered[0]
    fixed_configuration = _fixed_configuration(first.raw_configuration)
    for run in ordered[1:]:
        if _fixed_configuration(run.raw_configuration) != fixed_configuration:
            raise ImageSizeBenchmarkError(
                "Evaluation settings differ by more than run name and image size"
            )
        if run.git_commit != first.git_commit:
            raise ImageSizeBenchmarkError("Image-size runs use different Git commits")
        if run.model_weights_sha256 != first.model_weights_sha256:
            raise ImageSizeBenchmarkError("Image-size runs use different model weights")
        if (
            run.dataset_manifest_sha256 != first.dataset_manifest_sha256
            or run.annotation_files != first.annotation_files
        ):
            raise ImageSizeBenchmarkError("Image-size runs use different dataset data")
    return ImageSizeBenchmarkResult(
        protocol_version=benchmark_config.protocol_version,
        source_commit=first.git_commit,
        operating_confidence=first.config.inference.operating_confidence,
        fixed_scale_factor=first.config.inference.scale_factor,
        runs=tuple(run.result for run in ordered),
    )


def _display_number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _milliseconds(value: float) -> str:
    return f"{value * 1000:.2f}"


def _memory_mib(value: int | None) -> str:
    return "n/a" if value is None else f"{value / (1024**2):.2f}"


def build_image_size_report(result: ImageSizeBenchmarkResult) -> str:
    lines = [
        "# Image-Size Benchmark",
        "",
        f"- Protocol version: `{result.protocol_version}`",
        f"- Source commit: `{result.source_commit}`",
        f"- Fixed operating confidence: {result.operating_confidence:.2f}",
        f"- Fixed preprocessing scale factor: {result.fixed_scale_factor}",
        "- Dataset role: validation",
        "",
        "## Aggregate Quality And Runtime",
        "",
        "| Image size | Precision | Recall | mAP50 | mAP50-95 | Person NAE | "
        "Vehicle NAE | Median ms | P95 ms | FPS | GPU MiB |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "---: | ---: |",
    ]
    for run in result.runs:
        lines.append(
            f"| {run.image_size} | {run.macro_precision:.4f} | "
            f"{run.macro_recall:.4f} | {run.map50:.4f} | {run.map50_95:.4f} | "
            f"{_display_number(run.person_nae)} | "
            f"{_display_number(run.road_vehicle_nae)} | "
            f"{_milliseconds(run.median_latency_seconds)} | "
            f"{_milliseconds(run.p95_latency_seconds)} | "
            f"{run.throughput_fps:.2f} | {_memory_mib(run.peak_gpu_memory_bytes)} |"
        )
    lines.extend(
        [
            "",
            "## Object-Size Results",
            "",
            "| Image size | AP small | AP medium | AP large |",
            "| ---: | ---: | ---: | ---: |",
        ]
    )
    for run in result.runs:
        lines.append(
            f"| {run.image_size} | {_display_number(run.ap_small)} | "
            f"{_display_number(run.ap_medium)} | {_display_number(run.ap_large)} |"
        )
    lines.extend(
        [
            "",
            "## Per-Class Results",
            "",
            "| Image size | Class | Support | Precision | Recall | AP50 | AP50-95 | "
            "Low support |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for run in result.runs:
        for metric in run.per_class:
            lines.append(
                f"| {run.image_size} | {metric.class_name} | {metric.support} | "
                f"{metric.precision:.4f} | {metric.recall:.4f} | "
                f"{metric.ap50:.4f} | {metric.ap50_95:.4f} | "
                f"{'yes' if metric.low_support else 'no'} |"
            )
    lines.extend(
        [
            "",
            "Every row comes from a complete checksum-verified evaluation run. "
            "Only the inference image size and descriptive run name differ.",
            "Low-support classes must be interpreted alongside their support. "
            "No held-out test data is used in this benchmark.",
            "",
        ]
    )
    return "\n".join(lines)


def _comparison_provenance(repository_root: Path) -> dict[str, Any]:
    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    versions = {}
    for package in ("numpy", "pycocotools", "torch", "ultralytics"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return {
        "git": {
            "commit": git("rev-parse", "HEAD"),
            "dirty": bool(git("status", "--porcelain")),
        },
        "python_version": platform.python_version(),
        "dependencies": versions,
    }


def save_image_size_comparison(
    repository_root: Path,
    benchmark_config: ImageSizeBenchmarkConfig,
    result: ImageSizeBenchmarkResult,
    *,
    source_runs: tuple[SavedEvaluationRun, ...] = (),
    created_at: datetime | None = None,
    provenance: dict[str, Any] | None = None,
) -> SavedImageSizeBenchmark:
    timestamp = created_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ImageSizeBenchmarkError("Comparison timestamp must include a timezone")
    timestamp = timestamp.astimezone(timezone.utc)
    comparison_id = (
        f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{benchmark_config.benchmark_name}"
    )
    output_directory = (
        repository_root / benchmark_config.output_directory / comparison_id
    )
    try:
        output_directory.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        raise ImageSizeBenchmarkError(
            f"Could not create comparison directory: {output_directory}"
        ) from error
    comparison_path = output_directory / "comparison.json"
    _write_json(
        comparison_path,
        {
            "schema_version": 1,
            "comparison_id": comparison_id,
            "created_at_utc": timestamp.isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            ),
            "configuration": benchmark_config,
            "provenance": provenance or _comparison_provenance(repository_root),
            "comparison": result,
        },
    )
    summary_path = output_directory / "summary.md"
    try:
        summary_path.write_text(build_image_size_report(result), encoding="utf-8")
    except OSError as error:
        raise ImageSizeBenchmarkError(
            f"Could not write comparison report: {summary_path}"
        ) from error
    _write_json(
        output_directory / "comparison_manifest.json",
        {
            "schema_version": 1,
            "comparison_id": comparison_id,
            "artifacts": [
                {"filename": path.name, "sha256": _sha256(path)}
                for path in (comparison_path, summary_path)
            ],
        },
    )
    return SavedImageSizeBenchmark(
        comparison_id, output_directory, summary_path, source_runs
    )


def run_image_size_benchmark(
    repository_root: Path,
    config_path: Path,
    *,
    evaluator: Callable[..., SavedEvaluationRun] | None = None,
    progress: Callable[[str], None] = print,
) -> SavedImageSizeBenchmark:
    resolved_config = (
        config_path if config_path.is_absolute() else repository_root / config_path
    )
    benchmark_config = load_image_size_benchmark_config(resolved_config)
    base_path = repository_root / benchmark_config.base_evaluation_config
    base_config = load_evaluation_config(base_path)
    evaluation_configs = create_image_size_evaluation_configs(
        base_config, benchmark_config
    )
    run_evaluation = evaluator or execute_detector_evaluation
    saved_runs = []
    for config in evaluation_configs:
        progress(f"Starting image-size {config.inference.image_size} evaluation.")
        saved_runs.append(run_evaluation(repository_root, config, progress=progress))
    loaded_runs = tuple(
        load_image_size_run(saved.output_directory) for saved in saved_runs
    )
    result = calculate_image_size_comparison(benchmark_config, loaded_runs)
    saved = save_image_size_comparison(
        repository_root,
        benchmark_config,
        result,
        source_runs=tuple(saved_runs),
    )
    progress(f"Saved image-size comparison to {saved.output_directory}.")
    return saved
