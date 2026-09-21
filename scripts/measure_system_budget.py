"""Measure a small local API workflow; this is not a detector-accuracy benchmark."""

import argparse
import hashlib
import json
import statistics
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

REPOSITORY = Path(__file__).resolve().parent.parent
BUDGETS = {
    "first_image_seconds": 60,
    "warm_image_median_seconds": 10,
    "video_seconds": 120,
    "backend_sampled_memory_mib": 4096,
    "gpu_device_sampled_memory_mib": 6144,
}


def command(*arguments):
    return subprocess.check_output(
        arguments, cwd=REPOSITORY, text=True, timeout=10
    ).strip()


def media_record(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "filename": path.name,
        "sha256": digest.hexdigest(),
        "bytes": path.stat().st_size,
    }


def assess_budgets(measurements):
    return {
        name: {
            "observed": measurements.get(name),
            "maximum": limit,
            "status": "unavailable"
            if measurements.get(name) is None
            else "pass"
            if measurements[name] <= limit
            else "warning",
        }
        for name, limit in BUDGETS.items()
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--backend-container", required=True)
    parser.add_argument(
        "--output", type=Path, default=REPOSITORY / "data/output/system-budget.json"
    )
    arguments = parser.parse_args()
    parsed = urlparse(arguments.base_url)
    if parsed.scheme != "http" or parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        parser.error("This smoke measurement accepts only a local HTTP stack.")
    if not arguments.image.is_file() or not arguments.video.is_file():
        parser.error("Image and video must exist.")
    samples = {"backend": [], "gpu": [], "errors": []}
    stop = threading.Event()

    def sample_resources():
        while not stop.is_set():
            try:
                memory = command(
                    "docker",
                    "exec",
                    arguments.backend_container,
                    "cat",
                    "/sys/fs/cgroup/memory.current",
                )
                samples["backend"].append(int(memory) / 1024**2)
            except (OSError, ValueError, subprocess.SubprocessError):
                samples["errors"].append("backend_memory_unavailable")
            try:
                memory = command(
                    "nvidia-smi",
                    "--id=0",
                    "--query-gpu=memory.used",
                    "--format=csv,noheader,nounits",
                )
                samples["gpu"].append(float(memory))
            except (OSError, ValueError, subprocess.SubprocessError):
                samples["errors"].append("gpu_memory_unavailable")
            stop.wait(1)

    report = {
        "purpose": "Operational smoke measurement, not final evaluation or accuracy",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "commit": command("git", "rev-parse", "HEAD"),
        "working_tree_dirty": bool(command("git", "status", "--porcelain")),
        "backend_image": command(
            "docker", "inspect", "--format", "{{.Image}}", arguments.backend_container
        ),
        "media": {
            "image": media_record(arguments.image),
            "video": media_record(arguments.video),
        },
        "budgets": BUDGETS,
    }
    monitor = threading.Thread(target=sample_resources, name="resource-sampler")
    monitor.start()
    try:
        with httpx.Client(base_url=arguments.base_url, timeout=180) as client:
            response = client.get("/api/ready")
            response.raise_for_status()
            report["capabilities"] = client.get("/api/capabilities").json()
            images = []
            for index in range(4):
                started = time.monotonic()
                with arguments.image.open("rb") as handle:
                    response = client.post(
                        "/api/analyses/images",
                        files={"image": (arguments.image.name, handle, "image/jpeg")},
                        data={
                            "session_name": f"budget-image-{index}",
                            "grid_rows": "2",
                            "grid_columns": "3",
                        },
                    )
                response.raise_for_status()
                images.append(
                    {
                        "session_id": response.json()["session_id"],
                        "request_id": response.headers.get("x-request-id"),
                        "seconds": time.monotonic() - started,
                    }
                )
            started = time.monotonic()
            with arguments.video.open("rb") as handle:
                response = client.post(
                    "/api/analyses/videos",
                    files={"video": (arguments.video.name, handle, "video/mp4")},
                    data={
                        "session_name": "budget-video",
                        "sampling_interval_seconds": "4",
                        "grid_rows": "2",
                        "grid_columns": "3",
                    },
                )
            response.raise_for_status()
            queued = response.json()
            while True:
                response = client.get(queued["job_url"])
                response.raise_for_status()
                job = response.json()
                if job["status"] == "completed":
                    break
                if job["status"] == "failed" or time.monotonic() - started > 180:
                    raise RuntimeError("Video smoke workflow failed or timed out.")
                time.sleep(0.25)
            video_seconds = time.monotonic() - started
            report["images"] = images
            report["video"] = {
                "session_id": queued["session_id"],
                "seconds": video_seconds,
                "sampled_frames": job["sampled_frames_processed"],
                "sampled_frames_per_second": job["sampled_frames_processed"]
                / video_seconds,
            }
    finally:
        stop.set()
        monitor.join()
    measurements = {
        "first_image_seconds": images[0]["seconds"],
        "warm_image_median_seconds": statistics.median(
            row["seconds"] for row in images[1:]
        ),
        "video_seconds": video_seconds,
        "backend_sampled_memory_mib": max(samples["backend"], default=None),
        "gpu_device_sampled_memory_mib": max(samples["gpu"], default=None),
    }
    report["resource_sampling"] = {
        "backend_samples": len(samples["backend"]),
        "gpu_samples": len(samples["gpu"]),
        "errors": sorted(set(samples["errors"])),
        "scope": (
            "Sampled cgroup memory and whole GPU device use; not guaranteed "
            "allocation peaks. Other GPU applications affect readings."
        ),
    }
    report["checks"] = assess_budgets(measurements)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["checks"], indent=2))
    return (
        0 if all(item["status"] == "pass" for item in report["checks"].values()) else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
