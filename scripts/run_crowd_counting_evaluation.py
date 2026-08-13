import argparse
import platform
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.crowd_counting import (
    bootstrap_count_intervals,
    calculate_count_metrics,
    load_baseline_observations,
    load_crowd_count_examples,
    load_crowd_counting_config,
    runtime_summary,
    sha256_file,
    write_json,
)
from evaluation.p2pnet_adapter import P2PNetAdapter


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Evaluate the frozen dedicated crowd-counting candidate."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/evaluation/dedicated_crowd_counting.json"),
    )
    parser.add_argument(
        "--role", choices=("validation", "held_out_test"), required=True
    )
    return parser.parse_args()


def dependency_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def git_value(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main():
    arguments = parse_arguments()
    config_path = PROJECT_ROOT / arguments.config
    config = load_crowd_counting_config(config_path)
    examples = load_crowd_count_examples(PROJECT_ROOT, config, arguments.role)
    adapter = P2PNetAdapter(PROJECT_ROOT, config.candidate, config.inference)
    adapter.warm_up(examples[0].asset.image_path, config.inference.warmup_tiles)
    adapter.reset_peak_memory()

    observations = []
    for index, example in enumerate(examples, start=1):
        observation = adapter.evaluate(example)
        observations.append(observation)
        print(
            f"[{index}/{len(examples)}] {observation.asset_id}: "
            f"reference={observation.reference_count}, "
            f"predicted={observation.predicted_count}, "
            f"time={observation.elapsed_seconds:.3f}s"
        )
    observation_tuple = tuple(observations)
    metrics = calculate_count_metrics(observation_tuple)
    intervals = bootstrap_count_intervals(
        observation_tuple,
        iterations=config.metrics.bootstrap_iterations,
        seed=config.metrics.bootstrap_seed,
    )
    runtime = runtime_summary(observation_tuple, adapter.peak_memory_bytes())
    baseline = None
    if arguments.role == config.dataset.final_role:
        baseline_observations = load_baseline_observations(
            PROJECT_ROOT, config, examples
        )
        baseline = {
            "observations": [asdict(item) for item in baseline_observations],
            "metrics": calculate_count_metrics(baseline_observations),
            "intervals": bootstrap_count_intervals(
                baseline_observations,
                iterations=config.metrics.bootstrap_iterations,
                seed=config.metrics.bootstrap_seed,
            ),
        }

    timestamp = datetime.now(timezone.utc)
    run_id = (
        timestamp.strftime("%Y%m%dT%H%M%SZ")
        + f"-{config.candidate.candidate_id}-{arguments.role}"
    )
    output_directory = PROJECT_ROOT / config.output_directory / run_id
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at_utc": timestamp.isoformat().replace("+00:00", "Z"),
        "role": arguments.role,
        "configuration": asdict(config),
        "observations": [asdict(item) for item in observation_tuple],
        "metrics": metrics,
        "intervals": intervals,
        "runtime": runtime,
        "baseline": baseline,
        "provenance": {
            "git_commit": git_value("rev-parse", "HEAD"),
            "git_dirty": bool(git_value("status", "--porcelain")),
            "configuration_sha256": sha256_file(config_path),
            "manifest_sha256": sha256_file(PROJECT_ROOT / config.dataset.manifest_path),
            "count_reference_sha256": sha256_file(
                PROJECT_ROOT / config.dataset.count_reference_path
            ),
            "weights_sha256": sha256_file(PROJECT_ROOT / config.candidate.weights_path),
            "python": platform.python_version(),
            "torch": dependency_version("torch"),
            "torchvision": dependency_version("torchvision"),
            "pillow": dependency_version("Pillow"),
            "numpy": dependency_version("numpy"),
            "device": config.inference.device,
            "gpu": (
                adapter.torch.cuda.get_device_name(adapter.device)
                if adapter.device.type == "cuda"
                else None
            ),
        },
    }
    write_json(output_directory / "result.json", payload)
    print(f"Result: {output_directory / 'result.json'}")
    print(f"NAE: {metrics['normalized_absolute_error']:.4f}")


if __name__ == "__main__":
    main()
