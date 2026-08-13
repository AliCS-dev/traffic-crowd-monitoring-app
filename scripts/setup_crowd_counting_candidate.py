import argparse
import subprocess
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.crowd_counting import (
    CrowdCountingError,
    load_crowd_counting_config,
    sha256_file,
)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Download and verify the frozen P2PNet evaluation candidate."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/evaluation/dedicated_crowd_counting.json"),
    )
    return parser.parse_args()


def run(*arguments: str, cwd: Path | None = None) -> None:
    subprocess.run(arguments, cwd=cwd, check=True)


def prepare_source(source_directory: Path, repository_url: str, revision: str) -> None:
    if not source_directory.exists():
        source_directory.parent.mkdir(parents=True, exist_ok=True)
        run("git", "clone", "--no-checkout", repository_url, str(source_directory))
    if not (source_directory / ".git").is_dir():
        raise CrowdCountingError(
            f"Candidate source is not a Git checkout: {source_directory}"
        )
    run("git", "fetch", "origin", revision, cwd=source_directory)
    run("git", "checkout", "--detach", revision, cwd=source_directory)


def prepare_weights(
    weights_path: Path, url: str, expected_size: int, expected_sha256: str
) -> None:
    if not weights_path.is_file():
        weights_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = weights_path.with_suffix(weights_path.suffix + ".download")
        try:
            urllib.request.urlretrieve(url, temporary_path)
            temporary_path.replace(weights_path)
        finally:
            temporary_path.unlink(missing_ok=True)
    if weights_path.stat().st_size != expected_size:
        raise CrowdCountingError("Downloaded checkpoint size is incorrect")
    if sha256_file(weights_path) != expected_sha256:
        raise CrowdCountingError("Downloaded checkpoint hash is incorrect")


def main():
    arguments = parse_arguments()
    config = load_crowd_counting_config(PROJECT_ROOT / arguments.config)
    source_directory = PROJECT_ROOT / config.inference.source_directory
    weights_path = PROJECT_ROOT / config.candidate.weights_path
    prepare_source(
        source_directory,
        config.candidate.repository_url,
        config.candidate.repository_revision,
    )
    prepare_weights(
        weights_path,
        config.candidate.weights_url,
        config.candidate.weights_size_bytes,
        config.candidate.weights_sha256,
    )
    print(f"Source ready: {source_directory}")
    print(f"Checkpoint ready: {weights_path}")


if __name__ == "__main__":
    main()
