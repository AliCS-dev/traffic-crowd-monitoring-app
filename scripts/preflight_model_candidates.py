import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.evaluation_config import load_evaluation_config
from evaluation.evaluation_data import load_evaluation_dataset
from evaluation.model_candidates import load_model_candidate_selection
from evaluation.model_preflight import (
    build_preflight_report,
    candidate_checkpoint_path,
    download_checkpoint,
    inspect_candidate,
    verify_checkpoint,
    write_preflight_report,
)

DEFAULT_ASSET_ID = "traffic_roundabout_near_3_f000006"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify and smoke-test the predeclared aerial model checkpoints."
    )
    parser.add_argument(
        "--selection",
        type=Path,
        default=Path("configs/evaluation/aerial_model_candidates.json"),
    )
    parser.add_argument(
        "--validation-config",
        type=Path,
        default=Path("configs/evaluation/yolo26n_selected_validation.json"),
    )
    parser.add_argument(
        "--models-directory",
        type=Path,
        default=Path("models/candidates"),
    )
    parser.add_argument("--asset-id", default=DEFAULT_ASSET_ID)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--image-size", type=int, default=1280)
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--max-detections", type=int, default=300)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("data/evaluation/derived/reports/aerial_model_preflight.json"),
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download a missing checkpoint from its pinned source URL.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selection = load_model_candidate_selection(args.selection)
    evaluation_config = load_evaluation_config(args.validation_config)
    if evaluation_config.dataset.role != "validation":
        raise ValueError("Preflight requires a validation dataset configuration")

    dataset = load_evaluation_dataset(PROJECT_ROOT, evaluation_config.dataset)
    asset_lookup = dataset.asset_by_id()
    try:
        validation_asset = asset_lookup[args.asset_id]
    except KeyError as error:
        raise ValueError(
            f"Validation asset is not in the selected dataset: {args.asset_id}"
        ) from error

    import torch
    import ultralytics

    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError(f"Requested device is unavailable: {args.device}")

    results = []
    print(f"Validation asset: {validation_asset.asset_id}")
    print(f"Device: {args.device}")
    for candidate in selection.candidates:
        checkpoint_path = candidate_checkpoint_path(args.models_directory, candidate)
        print(f"\nCandidate: {candidate.candidate_id}")
        if args.download:
            download_checkpoint(candidate, checkpoint_path)
        else:
            verify_checkpoint(checkpoint_path, candidate)
        print("- checkpoint identity: PASS")

        result = inspect_candidate(
            candidate=candidate,
            checkpoint_path=checkpoint_path,
            validation_asset_id=validation_asset.asset_id,
            validation_image_path=validation_asset.image_path,
            device=args.device,
            image_size=args.image_size,
            confidence=args.confidence,
            max_detections=args.max_detections,
        )
        results.append(result)
        print("- model load and class taxonomy: PASS")
        print("- single-image inference: PASS")

    report = build_preflight_report(
        selection=selection,
        selection_path=args.selection,
        results=results,
        torch_version=torch.__version__,
        ultralytics_version=ultralytics.__version__,
        cuda_available=torch.cuda.is_available(),
        cuda_device_name=(
            torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
        ),
    )
    write_preflight_report(args.report, report)
    print(f"\nPreflight report: {args.report}")
    print("Aerial model checkpoint preflight: PASS")


if __name__ == "__main__":
    main()
