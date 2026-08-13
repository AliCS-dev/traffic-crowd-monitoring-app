import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from evaluation.evaluation_config import DatasetSettings
from evaluation.evaluation_data import EvaluationAsset, load_evaluation_dataset


class CrowdCountingError(ValueError):
    """Raised when the crowd-counting experiment is not reproducible."""


@dataclass(frozen=True)
class CrowdDatasetSettings:
    version: str
    manifest_path: Path
    count_reference_path: Path
    collection_id: str
    development_role: str
    final_role: str
    expected_development_images: int
    expected_final_images: int


@dataclass(frozen=True)
class CrowdCandidateSettings:
    candidate_id: str
    name: str
    task: str
    training_dataset: str
    repository_url: str
    repository_revision: str
    weights_path: Path
    weights_url: str
    weights_sha256: str
    weights_size_bytes: int
    license_id: str
    license_url: str


@dataclass(frozen=True)
class CrowdInferenceSettings:
    source_directory: Path
    device: str
    numeric_precision: str
    batch_size: int
    tile_size: int
    tile_overlap: int
    edge_tile_policy: str
    resize_policy: str
    normalization: str
    operating_confidence: float
    warmup_tiles: int


@dataclass(frozen=True)
class CrowdMetricSettings:
    bootstrap_iterations: int
    bootstrap_seed: int
    reported_count_metrics: tuple[str, ...]
    reported_runtime_metrics: tuple[str, ...]


@dataclass(frozen=True)
class CrowdComparisonSettings:
    baseline_run_id: str
    baseline_operating_confidence: float
    comparison_class: str
    comparison_policy: str


@dataclass(frozen=True)
class CrowdDecisionSettings:
    integrate_maximum_nae: float
    integrate_maximum_seconds_per_megapixel: float
    defer_maximum_nae: float
    defer_minimum_relative_nae_reduction: float
    defer_maximum_seconds_per_megapixel: float
    otherwise: str


@dataclass(frozen=True)
class CrowdCountingConfig:
    schema_version: int
    evaluation_name: str
    protocol_version: str
    selection_date: str
    random_seed: int
    dataset: CrowdDatasetSettings
    candidate: CrowdCandidateSettings
    inference: CrowdInferenceSettings
    metrics: CrowdMetricSettings
    comparison: CrowdComparisonSettings
    decision: CrowdDecisionSettings
    output_directory: Path


@dataclass(frozen=True)
class CrowdCountExample:
    asset: EvaluationAsset
    reference_count: int


@dataclass(frozen=True)
class CrowdCountObservation:
    asset_id: str
    reference_count: int
    predicted_count: int
    width: int
    height: int
    elapsed_seconds: float
    tile_count: int

    @property
    def megapixels(self) -> float:
        return self.width * self.height / 1_000_000

    @property
    def seconds_per_megapixel(self) -> float:
        return self.elapsed_seconds / self.megapixels


EXPECTED_COUNT_METRICS = (
    "mean_absolute_error",
    "root_mean_squared_error",
    "normalized_absolute_error",
    "bias",
)
EXPECTED_RUNTIME_METRICS = (
    "median_seconds_per_image",
    "median_seconds_per_megapixel",
    "peak_allocated_gpu_memory_mib",
)


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CrowdCountingError(f"{field} must be a JSON object")
    return value


def _fields(values: dict[str, Any], field: str, required: set[str]) -> None:
    missing = required - set(values)
    unknown = set(values) - required
    if missing:
        raise CrowdCountingError(
            f"{field} is missing fields: {', '.join(sorted(missing))}"
        )
    if unknown:
        raise CrowdCountingError(
            f"{field} contains unknown fields: {', '.join(sorted(unknown))}"
        )


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CrowdCountingError(f"{field} must be a non-empty string")
    return value


def _integer(value: Any, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CrowdCountingError(f"{field} must be an integer >= {minimum}")
    return value


def _number(value: Any, field: str, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CrowdCountingError(f"{field} must be a number >= {minimum}")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise CrowdCountingError(f"{field} must be a number >= {minimum}")
    return number


def _relative_path(value: Any, field: str) -> Path:
    path = Path(_string(value, field))
    if path.is_absolute() or ".." in path.parts:
        raise CrowdCountingError(f"{field} must be repository-relative")
    return path


def _string_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise CrowdCountingError(f"{field} must be a list of strings")
    return tuple(value)


def _parse_dataset(values: dict[str, Any]) -> CrowdDatasetSettings:
    required = {
        "version",
        "manifest_path",
        "count_reference_path",
        "collection_id",
        "development_role",
        "final_role",
        "expected_development_images",
        "expected_final_images",
    }
    _fields(values, "dataset", required)
    return CrowdDatasetSettings(
        version=_string(values["version"], "dataset.version"),
        manifest_path=_relative_path(values["manifest_path"], "dataset.manifest_path"),
        count_reference_path=_relative_path(
            values["count_reference_path"], "dataset.count_reference_path"
        ),
        collection_id=_string(values["collection_id"], "dataset.collection_id"),
        development_role=_string(
            values["development_role"], "dataset.development_role"
        ),
        final_role=_string(values["final_role"], "dataset.final_role"),
        expected_development_images=_integer(
            values["expected_development_images"],
            "dataset.expected_development_images",
            1,
        ),
        expected_final_images=_integer(
            values["expected_final_images"], "dataset.expected_final_images", 1
        ),
    )


def _parse_candidate(values: dict[str, Any]) -> CrowdCandidateSettings:
    required = {
        "candidate_id",
        "name",
        "task",
        "training_dataset",
        "repository_url",
        "repository_revision",
        "weights_path",
        "weights_url",
        "weights_sha256",
        "weights_size_bytes",
        "license_id",
        "license_url",
    }
    _fields(values, "candidate", required)
    revision = _string(values["repository_revision"], "candidate.repository_revision")
    digest = _string(values["weights_sha256"], "candidate.weights_sha256")
    if len(revision) != 40 or any(
        character not in "0123456789abcdef" for character in revision
    ):
        raise CrowdCountingError("candidate.repository_revision must be a Git SHA")
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise CrowdCountingError("candidate.weights_sha256 must be a SHA-256 digest")
    return CrowdCandidateSettings(
        candidate_id=_string(values["candidate_id"], "candidate.candidate_id"),
        name=_string(values["name"], "candidate.name"),
        task=_string(values["task"], "candidate.task"),
        training_dataset=_string(
            values["training_dataset"], "candidate.training_dataset"
        ),
        repository_url=_string(values["repository_url"], "candidate.repository_url"),
        repository_revision=revision,
        weights_path=_relative_path(values["weights_path"], "candidate.weights_path"),
        weights_url=_string(values["weights_url"], "candidate.weights_url"),
        weights_sha256=digest,
        weights_size_bytes=_integer(
            values["weights_size_bytes"], "candidate.weights_size_bytes", 1
        ),
        license_id=_string(values["license_id"], "candidate.license_id"),
        license_url=_string(values["license_url"], "candidate.license_url"),
    )


def _parse_inference(values: dict[str, Any]) -> CrowdInferenceSettings:
    required = {
        "source_directory",
        "device",
        "numeric_precision",
        "batch_size",
        "tile_size",
        "tile_overlap",
        "edge_tile_policy",
        "resize_policy",
        "normalization",
        "operating_confidence",
        "warmup_tiles",
    }
    _fields(values, "inference", required)
    tile_size = _integer(values["tile_size"], "inference.tile_size", 128)
    tile_overlap = _integer(values["tile_overlap"], "inference.tile_overlap")
    if tile_overlap >= tile_size:
        raise CrowdCountingError(
            "inference.tile_overlap must be smaller than tile_size"
        )
    confidence = _number(
        values["operating_confidence"], "inference.operating_confidence"
    )
    if confidence > 1:
        raise CrowdCountingError("inference.operating_confidence must not exceed 1")
    return CrowdInferenceSettings(
        source_directory=_relative_path(
            values["source_directory"], "inference.source_directory"
        ),
        device=_string(values["device"], "inference.device"),
        numeric_precision=_string(
            values["numeric_precision"], "inference.numeric_precision"
        ),
        batch_size=_integer(values["batch_size"], "inference.batch_size", 1),
        tile_size=tile_size,
        tile_overlap=tile_overlap,
        edge_tile_policy=_string(
            values["edge_tile_policy"], "inference.edge_tile_policy"
        ),
        resize_policy=_string(values["resize_policy"], "inference.resize_policy"),
        normalization=_string(values["normalization"], "inference.normalization"),
        operating_confidence=confidence,
        warmup_tiles=_integer(values["warmup_tiles"], "inference.warmup_tiles"),
    )


def parse_crowd_counting_config(values: dict[str, Any]) -> CrowdCountingConfig:
    required = {
        "schema_version",
        "evaluation_name",
        "protocol_version",
        "selection_date",
        "random_seed",
        "dataset",
        "candidate",
        "inference",
        "metrics",
        "comparison",
        "decision",
        "output_directory",
    }
    _fields(values, "configuration", required)
    if values["schema_version"] != 1:
        raise CrowdCountingError("schema_version must be 1")

    metric_values = _object(values["metrics"], "metrics")
    _fields(
        metric_values,
        "metrics",
        {
            "bootstrap_iterations",
            "bootstrap_seed",
            "reported_count_metrics",
            "reported_runtime_metrics",
        },
    )
    count_metrics = _string_list(
        metric_values["reported_count_metrics"], "metrics.reported_count_metrics"
    )
    runtime_metrics = _string_list(
        metric_values["reported_runtime_metrics"],
        "metrics.reported_runtime_metrics",
    )
    if (
        count_metrics != EXPECTED_COUNT_METRICS
        or runtime_metrics != EXPECTED_RUNTIME_METRICS
    ):
        raise CrowdCountingError("reported metrics must match protocol version 1.0")

    comparison = _object(values["comparison"], "comparison")
    _fields(
        comparison,
        "comparison",
        {
            "baseline_run_id",
            "baseline_operating_confidence",
            "comparison_class",
            "comparison_policy",
        },
    )
    decision = _object(values["decision"], "decision")
    _fields(
        decision,
        "decision",
        {
            "integrate_maximum_nae",
            "integrate_maximum_seconds_per_megapixel",
            "defer_maximum_nae",
            "defer_minimum_relative_nae_reduction",
            "defer_maximum_seconds_per_megapixel",
            "otherwise",
        },
    )

    config = CrowdCountingConfig(
        schema_version=1,
        evaluation_name=_string(values["evaluation_name"], "evaluation_name"),
        protocol_version=_string(values["protocol_version"], "protocol_version"),
        selection_date=_string(values["selection_date"], "selection_date"),
        random_seed=_integer(values["random_seed"], "random_seed"),
        dataset=_parse_dataset(_object(values["dataset"], "dataset")),
        candidate=_parse_candidate(_object(values["candidate"], "candidate")),
        inference=_parse_inference(_object(values["inference"], "inference")),
        metrics=CrowdMetricSettings(
            bootstrap_iterations=_integer(
                metric_values["bootstrap_iterations"],
                "metrics.bootstrap_iterations",
                100,
            ),
            bootstrap_seed=_integer(
                metric_values["bootstrap_seed"], "metrics.bootstrap_seed"
            ),
            reported_count_metrics=count_metrics,
            reported_runtime_metrics=runtime_metrics,
        ),
        comparison=CrowdComparisonSettings(
            baseline_run_id=_string(
                comparison["baseline_run_id"], "comparison.baseline_run_id"
            ),
            baseline_operating_confidence=_number(
                comparison["baseline_operating_confidence"],
                "comparison.baseline_operating_confidence",
            ),
            comparison_class=_string(
                comparison["comparison_class"], "comparison.comparison_class"
            ),
            comparison_policy=_string(
                comparison["comparison_policy"], "comparison.comparison_policy"
            ),
        ),
        decision=CrowdDecisionSettings(
            integrate_maximum_nae=_number(
                decision["integrate_maximum_nae"], "decision.integrate_maximum_nae"
            ),
            integrate_maximum_seconds_per_megapixel=_number(
                decision["integrate_maximum_seconds_per_megapixel"],
                "decision.integrate_maximum_seconds_per_megapixel",
            ),
            defer_maximum_nae=_number(
                decision["defer_maximum_nae"], "decision.defer_maximum_nae"
            ),
            defer_minimum_relative_nae_reduction=_number(
                decision["defer_minimum_relative_nae_reduction"],
                "decision.defer_minimum_relative_nae_reduction",
            ),
            defer_maximum_seconds_per_megapixel=_number(
                decision["defer_maximum_seconds_per_megapixel"],
                "decision.defer_maximum_seconds_per_megapixel",
            ),
            otherwise=_string(decision["otherwise"], "decision.otherwise"),
        ),
        output_directory=_relative_path(values["output_directory"], "output_directory"),
    )
    if config.inference.batch_size != 1 or config.inference.tile_overlap != 0:
        raise CrowdCountingError("protocol version 1.0 requires batch 1 and no overlap")
    if config.inference.edge_tile_policy != (
        "pad-right-bottom-to-multiple-of-16-and-discard-padding-points"
    ):
        raise CrowdCountingError("protocol version 1.0 requires fixed edge padding")
    if config.decision.integrate_maximum_nae > config.decision.defer_maximum_nae:
        raise CrowdCountingError("integrate NAE must not exceed defer NAE")
    return config


def load_crowd_counting_config(path: Path) -> CrowdCountingConfig:
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CrowdCountingError(f"Could not read configuration: {path}") from error
    return parse_crowd_counting_config(_object(values, "configuration"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise CrowdCountingError(f"Could not hash file: {path}") from error
    return digest.hexdigest()


def load_crowd_count_examples(
    repository_root: Path, config: CrowdCountingConfig, role: str
) -> tuple[CrowdCountExample, ...]:
    expected = {
        config.dataset.development_role: config.dataset.expected_development_images,
        config.dataset.final_role: config.dataset.expected_final_images,
    }.get(role)
    if expected is None:
        raise CrowdCountingError(f"Role is outside this protocol: {role}")
    dataset = load_evaluation_dataset(
        repository_root,
        DatasetSettings(
            version=config.dataset.version,
            role=role,
            manifest_path=config.dataset.manifest_path,
        ),
    )
    assets = {
        asset.asset_id: asset
        for asset in dataset.assets
        if asset.collection_id == config.dataset.collection_id
    }
    references = {
        reference.asset_id: reference.count
        for reference in dataset.count_references
        if reference.asset_id in assets and reference.project_class == "person"
    }
    if set(assets) != set(references):
        raise CrowdCountingError("DLR assets and person-count references do not match")
    if len(assets) != expected:
        raise CrowdCountingError(
            f"Expected {expected} {role} images, found {len(assets)}"
        )
    missing_images = [
        asset.asset_id for asset in assets.values() if not asset.image_path.is_file()
    ]
    if missing_images:
        raise CrowdCountingError(
            f"Evaluation images are missing: {', '.join(sorted(missing_images))}"
        )
    return tuple(
        CrowdCountExample(asset=assets[asset_id], reference_count=references[asset_id])
        for asset_id in sorted(assets)
    )


def calculate_count_metrics(
    observations: tuple[CrowdCountObservation, ...],
) -> dict[str, float | int]:
    if not observations:
        raise CrowdCountingError("At least one count observation is required")
    actual = np.asarray([item.reference_count for item in observations], dtype=float)
    predicted = np.asarray([item.predicted_count for item in observations], dtype=float)
    differences = predicted - actual
    absolute = np.abs(differences)
    support = float(actual.sum())
    if support <= 0:
        raise CrowdCountingError("Count observations require positive support")
    return {
        "images": len(observations),
        "ground_truth_total": int(actual.sum()),
        "predicted_total": int(predicted.sum()),
        "mean_absolute_error": float(absolute.mean()),
        "root_mean_squared_error": float(np.sqrt(np.mean(differences**2))),
        "normalized_absolute_error": float(absolute.sum() / support),
        "bias": float(differences.mean()),
    }


def bootstrap_count_intervals(
    observations: tuple[CrowdCountObservation, ...], *, iterations: int, seed: int
) -> dict[str, dict[str, float | int]]:
    if iterations < 100:
        raise CrowdCountingError("Bootstrap iterations must be at least 100")
    rng = np.random.default_rng(seed)
    sampled: dict[str, list[float]] = {name: [] for name in EXPECTED_COUNT_METRICS}
    for _ in range(iterations):
        indices = rng.integers(0, len(observations), size=len(observations))
        sample = tuple(observations[int(index)] for index in indices)
        metrics = calculate_count_metrics(sample)
        for name in sampled:
            sampled[name].append(float(metrics[name]))
    return {
        name: {
            "lower_95": float(np.percentile(values, 2.5)),
            "upper_95": float(np.percentile(values, 97.5)),
            "bootstrap_iterations": iterations,
            "seed": seed,
        }
        for name, values in sampled.items()
    }


def runtime_summary(
    observations: tuple[CrowdCountObservation, ...], peak_memory_bytes: int | None
) -> dict[str, float | int | None]:
    return {
        "median_seconds_per_image": float(
            np.median([item.elapsed_seconds for item in observations])
        ),
        "median_seconds_per_megapixel": float(
            np.median([item.seconds_per_megapixel for item in observations])
        ),
        "total_seconds": float(sum(item.elapsed_seconds for item in observations)),
        "total_tiles": sum(item.tile_count for item in observations),
        "peak_allocated_gpu_memory_mib": (
            peak_memory_bytes / (1024 * 1024) if peak_memory_bytes is not None else None
        ),
    }


def classify_candidate(
    candidate_nae: float,
    baseline_nae: float,
    seconds_per_megapixel: float,
    settings: CrowdDecisionSettings,
) -> dict[str, float | str]:
    relative_reduction = (baseline_nae - candidate_nae) / baseline_nae
    if (
        candidate_nae <= settings.integrate_maximum_nae
        and candidate_nae < baseline_nae
        and seconds_per_megapixel <= settings.integrate_maximum_seconds_per_megapixel
    ):
        decision = "integrate"
    elif (
        candidate_nae <= settings.defer_maximum_nae
        and relative_reduction >= settings.defer_minimum_relative_nae_reduction
        and seconds_per_megapixel <= settings.defer_maximum_seconds_per_megapixel
    ):
        decision = "defer"
    else:
        decision = settings.otherwise
    return {
        "decision": decision,
        "relative_nae_reduction": relative_reduction,
    }


def load_baseline_observations(
    repository_root: Path,
    config: CrowdCountingConfig,
    examples: tuple[CrowdCountExample, ...],
) -> tuple[CrowdCountObservation, ...]:
    prediction_path = (
        repository_root
        / "data/evaluation/derived/runs"
        / config.comparison.baseline_run_id
        / "predictions.json"
    )
    try:
        payload = json.loads(prediction_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CrowdCountingError(
            f"Could not read baseline predictions: {prediction_path}"
        ) from error
    counts = {example.asset.asset_id: 0 for example in examples}
    for prediction in payload.get("predictions", []):
        asset_id = prediction.get("asset_id")
        if (
            asset_id in counts
            and prediction.get("project_class") == config.comparison.comparison_class
            and prediction.get("confidence", -1)
            >= config.comparison.baseline_operating_confidence
        ):
            counts[asset_id] += 1
    return tuple(
        CrowdCountObservation(
            asset_id=example.asset.asset_id,
            reference_count=example.reference_count,
            predicted_count=counts[example.asset.asset_id],
            width=example.asset.width,
            height=example.asset.height,
            elapsed_seconds=0,
            tile_count=0,
        )
        for example in examples
    )


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return value.as_posix()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            allow_nan=False,
            default=_json_default,
        )
        + "\n",
        encoding="utf-8",
    )
