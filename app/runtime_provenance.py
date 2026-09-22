"""Capture a process-local backend environment without secrets or host paths."""

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from importlib.metadata import distributions
from pathlib import Path

from app.config import BASE_DIR


def source_digest(root: Path) -> str:
    paths = [root / "Dockerfile", root / "requirements-container.txt"]
    paths += list((root / "app").rglob("*.py"))
    paths += list((root / "app").rglob("*.sql"))
    paths += list((root / "configs/runtime").rglob("*.json"))
    paths += [root / "data/evaluation/dedicated_crowd_counting.json"]
    digest = hashlib.sha256()
    for path in sorted(paths):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode() + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def source_identity(root: Path) -> dict:
    digest = source_digest(root)
    build_file = root / "build-info.json"
    if build_file.is_file():
        result = json.loads(build_file.read_text(encoding="utf-8"))
        if result["source_sha256"] != digest:
            result["source_dirty"] = True
        return {**result, "source_sha256": digest}
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=normal"],
                cwd=root,
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=3,
            ).strip()
        )
    except (OSError, subprocess.SubprocessError):
        revision, dirty = None, None
    return {
        "application_commit": revision,
        "source_dirty": dirty,
        "source_sha256": digest,
    }


def dependency_versions() -> dict[str, str]:
    # First entry follows importlib's search path, including venv overlays.
    versions = {}
    for distribution in distributions():
        name = distribution.metadata.get("Name")
        if name:
            versions.setdefault(
                re.sub(r"[-_.]+", "-", name.lower()), distribution.version
            )
    return dict(sorted(versions.items()))


@lru_cache(maxsize=8)
def capture_runtime_provenance(device: str) -> dict:
    import torch

    container = os.getenv("HOSTNAME", "")
    container_id = (
        container
        if Path("/.dockerenv").exists() and re.fullmatch(r"[0-9a-f]{12,64}", container)
        else None
    )
    gpu_name = None
    if device.startswith("cuda") and torch.cuda.is_available():
        try:
            gpu_name = torch.cuda.get_device_name(device)
        except (RuntimeError, AssertionError):
            # Readiness, not metadata collection, rejects an unavailable device.
            gpu_name = None
    return {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        **source_identity(BASE_DIR),
        "python_version": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        "dependencies": dependency_versions(),
        "device": device,
        "gpu_name": gpu_name,
        "cuda_version": torch.version.cuda,
        "cudnn_version": torch.backends.cudnn.version(),
        "container_id": container_id,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-build-info", action="store_true")
    parser.add_argument("--device", default=os.getenv("API_DEVICE", "cpu"))
    args = parser.parse_args()
    if args.write_build_info:
        revision = os.getenv("APP_REVISION", "")
        if revision and not re.fullmatch(r"[0-9a-f]{40}", revision):
            parser.error("APP_REVISION must be a full Git commit hash or empty.")
        dirty = os.getenv("APP_SOURCE_DIRTY", "unknown")
        if dirty not in {"true", "false", "unknown"}:
            parser.error("APP_SOURCE_DIRTY must be true, false or unknown.")
        record = {
            "application_commit": revision or None,
            "source_dirty": {"true": True, "false": False, "unknown": None}[dirty],
            "source_sha256": source_digest(BASE_DIR),
        }
        (BASE_DIR / "build-info.json").write_text(json.dumps(record, indent=2) + "\n")
    else:
        print(json.dumps(capture_runtime_provenance(args.device), indent=2))


if __name__ == "__main__":
    main()
