import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.training_config import load_training_config
from evaluation.training_runner import run_fine_tuning


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fine-tune the selected detector with the declared experiment."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/training/yolo26m_okutama_finetune.json"),
    )
    arguments = parser.parse_args()
    config = load_training_config(PROJECT_ROOT / arguments.config)
    prepared, run_directory = run_fine_tuning(PROJECT_ROOT, config)
    print(f"Training images: {prepared.training_images}")
    print(f"Validation images: {prepared.validation_images}")
    print(f"Training run: {run_directory}")
    print(f"Best checkpoint: {run_directory / 'weights/best.pt'}")


if __name__ == "__main__":
    main()
