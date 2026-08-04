import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.evaluation_report import generate_evaluation_report


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Rebuild a Markdown summary from saved evaluation results."
    )
    parser.add_argument("run_directory", type=Path, help="Saved evaluation run.")
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    run_directory = arguments.run_directory
    if not run_directory.is_absolute():
        run_directory = PROJECT_ROOT / run_directory
    output_path = generate_evaluation_report(run_directory)
    print(f"Report written to {output_path}")


if __name__ == "__main__":
    main()
