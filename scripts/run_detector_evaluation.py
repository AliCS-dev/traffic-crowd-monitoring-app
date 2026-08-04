import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.evaluation_command import run_detector_evaluation


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Run the reproducible detector evaluation protocol."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/evaluation/yolo26n_validation.json"),
        help="Evaluation configuration path relative to the repository.",
    )
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    saved = run_detector_evaluation(PROJECT_ROOT, arguments.config)
    print(f"Summary report: {saved.output_directory / 'summary.md'}")


if __name__ == "__main__":
    main()
