import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.error_analysis import run_error_analysis


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Create a reproducible qualitative detector error analysis."
    )
    parser.add_argument(
        "--source-run",
        type=Path,
        required=True,
        help="Saved validation run containing confidence-floor predictions.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/evaluation/yolo26n_error_analysis.json"),
        help="Tracked error-analysis configuration relative to the repository.",
    )
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    saved = run_error_analysis(
        PROJECT_ROOT,
        arguments.source_run,
        arguments.config,
    )
    print(f"Error analysis saved to {saved.output_directory}")
    print(f"Summary report: {saved.summary_path}")


if __name__ == "__main__":
    main()
