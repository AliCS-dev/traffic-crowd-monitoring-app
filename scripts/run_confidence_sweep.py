import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.confidence_sweep import run_confidence_sweep


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Compare predeclared confidence thresholds from a saved run."
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
        default=Path("configs/evaluation/yolo26n_confidence_sweep.json"),
        help="Tracked confidence-sweep configuration.",
    )
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    saved = run_confidence_sweep(
        PROJECT_ROOT,
        arguments.source_run,
        arguments.config,
    )
    print(f"Comparison saved to {saved.output_directory}")
    print(f"Summary report: {saved.summary_path}")


if __name__ == "__main__":
    main()
