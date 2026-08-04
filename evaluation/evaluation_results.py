import csv
import hashlib
import json
import os
import platform
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from evaluation.evaluation_config import ClassMapping, EvaluationConfig
from evaluation.evaluation_metrics import CountMetricResult, DetectionMetricResult
from evaluation.evaluation_report import generate_evaluation_report
from evaluation.evaluation_runner import PredictionBatch
from evaluation.evaluation_timing import RuntimeBenchmarkResult

DEPENDENCY_DISTRIBUTIONS = (
    "numpy",
    "opencv-python",
    "Pillow",
    "pycocotools",
    "psycopg",
    "python-dotenv",
    "torch",
    "ultralytics",
)


class EvaluationResultError(RuntimeError):
    """Raised when evaluation artifacts cannot be recorded safely."""


@dataclass(frozen=True)
class SavedEvaluationRun:
    run_id: str
    output_directory: Path
    manifest_path: Path


def _json_value(value: Any) -> Any:
    if isinstance(value, ClassMapping):
        return value.as_dict()
    if isinstance(value, Path):
        return value.as_posix()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_value(item) for item in value]
    return value


def _write_json(path: Path, payload: Any) -> None:
    try:
        path.write_text(
            json.dumps(_json_value(payload), indent=2, sort_keys=True, allow_nan=False)
            + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as error:
        raise EvaluationResultError(
            f"Could not write evaluation artifact: {path}"
        ) from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise EvaluationResultError(
            f"Could not hash evaluation input: {path}"
        ) from error
    return digest.hexdigest()


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError as error:
        raise EvaluationResultError(
            f"Could not read evaluation input: {path}"
        ) from error


def _git_information(repository_root: Path) -> dict[str, str | bool]:
    def run_git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repository_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise EvaluationResultError(
                f"Could not read Git state: {result.stderr.strip()}"
            )
        return result.stdout.strip()

    return {
        "commit": run_git("rev-parse", "HEAD"),
        "dirty": bool(run_git("status", "--porcelain")),
    }


def _dependency_versions() -> dict[str, str | None]:
    versions = {}
    for distribution in DEPENDENCY_DISTRIBUTIONS:
        try:
            versions[distribution] = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            versions[distribution] = None
    return versions


def _annotation_file_hashes(
    repository_root: Path,
    manifest_path: Path,
    config: EvaluationConfig,
) -> list[dict[str, str]]:
    try:
        with manifest_path.open(encoding="utf-8", newline="") as file:
            rows = csv.DictReader(file)
            annotation_paths = {
                row["canonical_annotation_path"]
                for row in rows
                if row["dataset_version"] == config.dataset.version
                and row["dataset_role"] == config.dataset.role
            }
    except (OSError, KeyError) as error:
        raise EvaluationResultError(
            f"Could not read annotation paths from dataset manifest: {manifest_path}"
        ) from error
    if not annotation_paths or "" in annotation_paths:
        raise EvaluationResultError(
            "Selected dataset rows must reference canonical annotation files"
        )

    records = []
    for value in sorted(annotation_paths):
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise EvaluationResultError(
                f"Canonical annotation path must be repository-relative: {value}"
            )
        records.append(
            {"path": path.as_posix(), "sha256": _sha256(repository_root / path)}
        )
    return records


def _system_memory_bytes() -> int | None:
    try:
        return int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _optional_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _nvidia_runtime_information(index: int) -> dict[str, Any]:
    unavailable = {
        "driver_version": None,
        "performance_state": None,
        "power_draw_watts": None,
        "power_limit_watts": None,
    }
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                f"--id={index}",
                "--query-gpu=driver_version,pstate,power.draw,power.limit",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return unavailable
    if result.returncode != 0:
        return unavailable
    values = [value.strip() for value in result.stdout.strip().split(",")]
    if len(values) != 4:
        return unavailable
    return {
        "driver_version": values[0] or None,
        "performance_state": values[1] or None,
        "power_draw_watts": _optional_float(values[2]),
        "power_limit_watts": _optional_float(values[3]),
    }


def _hardware_information(device: str) -> dict[str, Any]:
    hardware: dict[str, Any] = {
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "logical_cpu_count": os.cpu_count(),
        "system_memory_bytes": _system_memory_bytes(),
        "gpu": None,
    }
    if not device.startswith("cuda"):
        return hardware

    try:
        import torch
    except ImportError as error:
        raise EvaluationResultError(
            "CUDA hardware was configured, but PyTorch is unavailable"
        ) from error
    if not torch.cuda.is_available():
        raise EvaluationResultError(
            f"CUDA hardware was configured for {device}, but CUDA is unavailable"
        )

    configured_device = torch.device(device)
    index = configured_device.index
    if index is None:
        index = torch.cuda.current_device()
    if index >= torch.cuda.device_count():
        raise EvaluationResultError(f"CUDA device index is unavailable: {index}")
    properties = torch.cuda.get_device_properties(index)
    hardware["gpu"] = {
        "device": f"cuda:{index}",
        "name": properties.name,
        "total_memory_bytes": properties.total_memory,
        "cuda_version": torch.version.cuda,
        "cudnn_version": torch.backends.cudnn.version(),
        **_nvidia_runtime_information(index),
    }
    return hardware


def collect_run_provenance(
    repository_root: Path,
    config: EvaluationConfig,
) -> dict[str, Any]:
    model_path = config.resolve_path(repository_root, config.model.weights_path)
    manifest_path = config.resolve_path(repository_root, config.dataset.manifest_path)
    return {
        "git": _git_information(repository_root),
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "operating_system": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
        },
        "hardware": _hardware_information(config.inference.device),
        "dependencies": _dependency_versions(),
        "model": {
            "name": config.model.name,
            "weights_path": config.model.weights_path.as_posix(),
            "weights_sha256": _sha256(model_path),
            "weights_size_bytes": _file_size(model_path),
        },
        "dataset": {
            "version": config.dataset.version,
            "role": config.dataset.role,
            "manifest_path": config.dataset.manifest_path.as_posix(),
            "manifest_sha256": _sha256(manifest_path),
            "annotation_files": _annotation_file_hashes(
                repository_root, manifest_path, config
            ),
        },
    }


def _normalise_timestamp(created_at: datetime | None) -> datetime:
    timestamp = created_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise EvaluationResultError("Evaluation run timestamp must include a timezone")
    return timestamp.astimezone(timezone.utc)


def save_evaluation_run(
    repository_root: Path,
    config: EvaluationConfig,
    predictions: PredictionBatch,
    detection_metrics: DetectionMetricResult,
    count_metrics: tuple[CountMetricResult, ...],
    timing: RuntimeBenchmarkResult,
    *,
    created_at: datetime | None = None,
    provenance: dict[str, Any] | None = None,
) -> SavedEvaluationRun:
    timestamp = _normalise_timestamp(created_at)
    created_at_utc = timestamp.isoformat(timespec="seconds").replace("+00:00", "Z")
    run_id = f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{config.run_name}"
    output_root = config.resolve_path(repository_root, config.output_directory)
    output_directory = output_root / run_id
    provenance_payload = dict(
        provenance
        if provenance is not None
        else collect_run_provenance(repository_root, config)
    )
    provenance_payload.update(
        {
            "schema_version": 1,
            "run_id": run_id,
            "created_at_utc": created_at_utc,
        }
    )
    try:
        output_directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise EvaluationResultError(
            f"Evaluation run already exists: {run_id}"
        ) from error
    except OSError as error:
        raise EvaluationResultError(
            f"Could not create evaluation run directory: {output_directory}"
        ) from error

    artifacts = {
        "configuration.json": {
            "schema_version": 1,
            "run_id": run_id,
            "configuration": config,
        },
        "predictions.json": {
            "schema_version": 1,
            "run_id": run_id,
            "processed_asset_ids": predictions.asset_ids,
            "predictions": predictions.predictions,
        },
        "metrics.json": {
            "schema_version": 1,
            "run_id": run_id,
            "detection": detection_metrics,
            "counts": count_metrics,
        },
        "timing.json": {
            "schema_version": 1,
            "run_id": run_id,
            "runtime": timing,
        },
        "provenance.json": provenance_payload,
    }
    for filename, payload in artifacts.items():
        _write_json(output_directory / filename, payload)

    report_path = generate_evaluation_report(output_directory)
    artifact_records = [
        {"filename": filename, "sha256": _sha256(output_directory / filename)}
        for filename in sorted((*artifacts, report_path.name))
    ]
    manifest_path = output_directory / "run_manifest.json"
    _write_json(
        manifest_path,
        {
            "schema_version": 1,
            "run_id": run_id,
            "created_at_utc": created_at_utc,
            "artifacts": artifact_records,
        },
    )
    return SavedEvaluationRun(run_id, output_directory, manifest_path)
