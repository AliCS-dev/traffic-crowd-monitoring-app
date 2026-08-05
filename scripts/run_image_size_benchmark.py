import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.image_size_benchmark import run_image_size_benchmark


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Run the predeclared detector image-size benchmark."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/evaluation/yolo26n_image_size_benchmark.json"),
        help="Image-size benchmark configuration relative to the repository.",
    )
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    saved = run_image_size_benchmark(PROJECT_ROOT, arguments.config)
    for run in saved.source_runs:
        print(f"Evaluation run: {run.output_directory}")
    print(f"Comparison saved to {saved.output_directory}")
    print(f"Summary report: {saved.summary_path}")


if __name__ == "__main__":
    main()
