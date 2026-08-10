#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.confidence_sweep import (
    load_source_evaluation_run,
    verify_source_dataset_identity,
)
from evaluation.dataset_validation import validate_dataset
from evaluation.evaluation_data import load_evaluation_dataset
from evaluation.final_quality_gate import (
    build_final_evidence,
    load_final_report_config,
    save_final_evidence,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build final quality-gate evidence from a saved held-out run."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/evaluation/final_quality_gate_report.json"),
    )
    parser.add_argument(
        "--source-run",
        type=Path,
        default=Path(
            "data/evaluation/derived/runs/"
            "20260810T135010Z-yolo26m-visdrone-held-out-test"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repository_root = PROJECT_ROOT
    config = load_final_report_config(repository_root / args.config)
    source_directory = repository_root / args.source_run
    validation = validate_dataset(repository_root)
    if not validation.dataset_ready:
        raise SystemExit("Evaluation dataset validation failed")
    source = load_source_evaluation_run(source_directory)
    verify_source_dataset_identity(repository_root, source)
    dataset = load_evaluation_dataset(repository_root, source.config.dataset)
    metrics = json.loads(
        (source_directory / "metrics.json").read_text(encoding="utf-8")
    )
    timing = json.loads((source_directory / "timing.json").read_text(encoding="utf-8"))
    provenance = json.loads(
        (source_directory / "provenance.json").read_text(encoding="utf-8")
    )
    evidence = build_final_evidence(
        dataset, source, metrics, timing, provenance, config
    )
    output_directory = repository_root / config.output_directory / config.report_name
    manifest = save_final_evidence(output_directory, evidence, metrics)
    print(f"Final quality-gate evidence saved to {output_directory}")
    print(f"Artifact manifest: {manifest}")
    print(f"Decision: {evidence['quality_gate']['overall_status'].upper()}")


if __name__ == "__main__":
    main()
