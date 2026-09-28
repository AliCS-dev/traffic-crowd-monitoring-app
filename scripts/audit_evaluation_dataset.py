"""Summarize historical dataset coverage without changing data or running a model."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.dataset_audit import DATA, audit_dataset
from evaluation.dataset_validation import read_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-media", action="store_true")
    args = parser.parse_args()
    report = audit_dataset(
        args.repository_root.resolve(), verify_media=args.verify_media
    )
    _, rows = read_csv(args.repository_root / DATA / "manifest.csv")
    inputs = {
        (args.repository_root / path).resolve() for path in report["input_sha256"]
    }
    inputs.update(
        (args.repository_root / row["evaluation_image_path"]).resolve() for row in rows
    )
    if args.output.resolve() in inputs:
        parser.error("The audit output must not overwrite an input file.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Audited {report['summary']['images']} images; report: {args.output}")


if __name__ == "__main__":
    main()
