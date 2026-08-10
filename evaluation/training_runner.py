import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.model_preflight import checkpoint_identity, sha256, source_class_names
from evaluation.training_config import FineTuningConfig
from evaluation.training_data import PreparedDataset, prepare_training_dataset


class FineTuningError(RuntimeError):
    """Raised when a fine-tuning precondition is not satisfied."""


def verify_base_checkpoint(
    repository_root: Path,
    config: FineTuningConfig,
    model_factory: Any | None = None,
) -> tuple[Path, Any]:
    checkpoint = repository_root / config.base_checkpoint
    if not checkpoint.is_file():
        raise FineTuningError(f"Base checkpoint is missing: {checkpoint}")
    actual_sha256 = sha256(checkpoint)
    if actual_sha256 != config.base_checkpoint_sha256:
        raise FineTuningError(
            "Base checkpoint SHA-256 mismatch: "
            f"expected {config.base_checkpoint_sha256}, found {actual_sha256}"
        )
    if model_factory is None:
        from ultralytics import YOLO

        model_factory = YOLO
    model = model_factory(str(checkpoint))
    actual_classes = source_class_names(model)
    if actual_classes != config.source_classes:
        raise FineTuningError(
            "Base checkpoint class names do not match the training config"
        )
    return checkpoint, model


def run_fine_tuning(
    repository_root: Path, config: FineTuningConfig
) -> tuple[PreparedDataset, Path]:
    checkpoint, model = verify_base_checkpoint(repository_root, config)
    prepared = prepare_training_dataset(repository_root, config)
    training = config.training
    project_directory = repository_root / config.output_directory
    model.train(
        data=str(prepared.dataset_yaml),
        epochs=training.epochs,
        patience=training.patience,
        imgsz=training.image_size,
        batch=training.batch_size,
        device=training.device,
        workers=training.workers,
        freeze=training.freeze_layers,
        optimizer=training.optimizer,
        lr0=training.learning_rate,
        amp=training.amp,
        seed=config.random_seed,
        deterministic=True,
        cache=training.cache,
        project=str(project_directory),
        name=config.run_name,
        exist_ok=False,
        plots=True,
        verbose=True,
    )
    run_directory = Path(model.trainer.save_dir)
    best_checkpoint = run_directory / "weights/best.pt"
    last_checkpoint = run_directory / "weights/last.pt"
    best_identity = checkpoint_identity(best_checkpoint)
    last_identity = checkpoint_identity(last_checkpoint)
    arguments_path = run_directory / "args.yaml"

    import torch
    import ultralytics

    report = {
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_name": config.run_name,
        "config_sha256": config.config_sha256,
        "base_checkpoint": config.base_checkpoint.as_posix(),
        "base_checkpoint_sha256": sha256(checkpoint),
        "dataset_summary": prepared.summary_path.as_posix(),
        "best_checkpoint": best_checkpoint.as_posix(),
        "best_checkpoint_sha256": best_identity.sha256,
        "best_checkpoint_size_bytes": best_identity.size_bytes,
        "last_checkpoint": last_checkpoint.as_posix(),
        "last_checkpoint_sha256": last_identity.sha256,
        "last_checkpoint_size_bytes": last_identity.size_bytes,
        "training_arguments": arguments_path.as_posix(),
        "training_arguments_sha256": sha256(arguments_path),
        "environment": {
            "python": platform.python_version(),
            "ultralytics": ultralytics.__version__,
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "gpu": (
                torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
            ),
        },
    }
    (run_directory / "provenance.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return prepared, run_directory
