import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.training_config import load_training_config
from evaluation.training_data import prepare_training_dataset


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare the source-group-clean YOLO fine-tuning dataset."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/training/yolo26m_okutama_finetune.json"),
    )
    arguments = parser.parse_args()
    config = load_training_config(PROJECT_ROOT / arguments.config)
    prepared = prepare_training_dataset(PROJECT_ROOT, config)
    print(f"Training images: {prepared.training_images}")
    print(f"Training boxes: {prepared.training_boxes}")
    print(f"Validation images: {prepared.validation_images}")
    print(f"Validation boxes: {prepared.validation_boxes}")
    print(f"Dataset YAML: {prepared.dataset_yaml}")


if __name__ == "__main__":
    main()
