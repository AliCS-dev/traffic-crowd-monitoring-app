import random
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.services.detection_service import ObjectDetector
from evaluation.dataset_validation import validate_dataset
from evaluation.evaluation_config import load_evaluation_config
from evaluation.evaluation_data import load_evaluation_dataset
from evaluation.evaluation_metrics import (
    calculate_count_metrics,
    calculate_detection_metrics,
)
from evaluation.evaluation_results import (
    SavedEvaluationRun,
    collect_run_provenance,
    save_evaluation_run,
)
from evaluation.evaluation_runner import generate_predictions
from evaluation.evaluation_timing import run_runtime_benchmark


class EvaluationCommandError(RuntimeError):
    """Raised when the complete evaluation workflow cannot start safely."""


def seed_random_generators(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)

    import torch

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True


def run_detector_evaluation(
    repository_root: Path,
    config_path: Path,
    *,
    detector_factory: Callable[[Path], ObjectDetector] | None = None,
    progress: Callable[[str], None] = print,
    created_at: datetime | None = None,
) -> SavedEvaluationRun:
    resolved_config_path = (
        config_path if config_path.is_absolute() else repository_root / config_path
    )
    config = load_evaluation_config(resolved_config_path)
    dataset_validation = validate_dataset(repository_root)
    if not dataset_validation.dataset_ready:
        details = (*dataset_validation.errors, *dataset_validation.incomplete)
        message = details[0] if details else "dataset quality checks did not pass"
        raise EvaluationCommandError(f"Evaluation dataset is not ready: {message}")
    progress("Evaluation dataset quality checks passed.")
    run_started_at = created_at or datetime.now(timezone.utc)
    provenance = collect_run_provenance(repository_root, config)
    progress("Recorded model, dataset, software, and hardware provenance.")
    seed_random_generators(config.random_seed)
    dataset = load_evaluation_dataset(repository_root, config.dataset)
    progress(
        f"Loaded {len(dataset.assets)} {dataset.role} assets from dataset "
        f"version {dataset.version}."
    )

    factory = detector_factory or ObjectDetector
    model_path = config.resolve_path(repository_root, config.model.weights_path)
    detector = factory(model_path)
    progress(f"Running detector predictions with {config.model.name}.")
    predictions = generate_predictions(dataset, detector, config)
    prediction_records = list(predictions.predictions)
    progress(
        f"Processed {predictions.processed_assets} assets and produced "
        f"{len(prediction_records)} raw predictions."
    )

    detection_metrics = calculate_detection_metrics(
        dataset,
        prediction_records,
        confidence_floor=config.inference.confidence_floor,
        operating_confidence=config.inference.operating_confidence,
        operating_iou=config.metrics.operating_iou,
        max_detections=config.inference.max_detections,
        low_support_threshold=config.metrics.low_support_threshold,
    )
    count_metrics = calculate_count_metrics(
        dataset,
        prediction_records,
        operating_confidence=config.inference.operating_confidence,
        low_support_threshold=config.metrics.low_support_threshold,
    )
    progress("Calculated detection and count metrics.")

    progress(
        f"Measuring runtime with {config.timing.warmup_frames} warm-up frames, "
        f"{config.timing.measured_frames} measured frames, and "
        f"{config.timing.repetitions} repetitions."
    )
    timing = run_runtime_benchmark(dataset, detector, config)
    saved = save_evaluation_run(
        repository_root,
        config,
        predictions,
        detection_metrics,
        count_metrics,
        timing,
        created_at=run_started_at,
        provenance=provenance,
    )
    progress(f"Saved evaluation run to {saved.output_directory}.")
    return saved
