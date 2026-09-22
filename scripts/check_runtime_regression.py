"""Run licensed development fixtures through an isolated local API stack."""

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.runtime_regression import compare_records

DATA = ROOT / "data/runtime-regression"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_fixture(client, fixture, interval):
    path = DATA / "fixtures" / fixture["name"]
    if sha256(path) != fixture["sha256"]:
        raise ValueError(f"Fixture checksum mismatch: {fixture['name']}")
    kind = fixture["kind"]
    data = {
        "session_name": f"runtime-regression-{fixture['name']}",
        "grid_rows": "2",
        "grid_columns": "3",
    }
    if kind == "video":
        data["sampling_interval_seconds"] = str(interval)
    with path.open("rb") as handle:
        response = client.post(
            f"/api/analyses/{kind}s",
            data=data,
            files={kind: (path.name, handle, fixture["mime"])},
        )
    response.raise_for_status()
    submission = response.json()
    if kind == "video":
        deadline = time.monotonic() + 360
        while True:
            response = client.get(submission["job_url"])
            response.raise_for_status()
            job = response.json()
            if job["status"] == "completed":
                break
            if job["status"] == "failed" or time.monotonic() > deadline:
                raise RuntimeError("Regression video did not complete.")
            time.sleep(0.25)
    response = client.get(f"/api/analyses/{submission['session_id']}")
    response.raise_for_status()
    return response.json()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--baseline", type=Path, default=DATA / "baseline.json")
    parser.add_argument("--output", type=Path, default=DATA / "latest.json")
    parser.add_argument("--establish-baseline", action="store_true")
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    if parsed.scheme != "http" or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        parser.error("Use an isolated local HTTP stack.")
    if args.output.resolve() == args.baseline.resolve():
        parser.error("The candidate record must not overwrite the baseline.")
    if args.establish_baseline and args.baseline.exists():
        parser.error(
            "Baseline exists; use a new explicit path for a reviewed replacement."
        )
    manifest_path = DATA / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    reference = (
        None if args.establish_baseline else json.loads(args.baseline.read_text())
    )
    report = {
        "schema_version": 1,
        "purpose": "development regression, not accuracy",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": sha256(manifest_path),
        "frames": {},
        "sessions": [],
    }
    with httpx.Client(base_url=args.base_url, timeout=360) as client:
        response = client.get("/api/ready")
        response.raise_for_status()
        for fixture in manifest["fixtures"]:
            result = run_fixture(client, fixture, manifest["sampling_interval_seconds"])
            profile = dict(result["model_profile"])
            runtime = profile.pop("runtime_provenance", None)
            profile.pop("created_at")
            if not runtime:
                raise ValueError(
                    "Runtime provenance is required for regression evidence."
                )
            if "runtime" in report and runtime != report["runtime"]:
                raise ValueError("The backend environment changed during the run.")
            if "model" in report and profile != report["model"]:
                raise ValueError("The model settings changed during the run.")
            report.update(runtime=runtime, model=profile)
            report["sessions"].append(result["id"])
            if not result["frames"]:
                raise ValueError("A regression fixture returned no frames.")
            expected = [0] if fixture["kind"] == "image" else [0, 10, 20]
            if [frame["frame_number"] for frame in result["frames"]] != expected:
                raise ValueError("Unexpected frame sampling in regression fixture.")
            for frame in result["frames"]:
                response = client.get(frame["visual_asset"]["url"])
                response.raise_for_status()
                key = f"{fixture['name']}:{frame['frame_number']}"
                report["frames"][key] = {
                    "dimensions": [frame["image_width"], frame["image_height"]],
                    "timestamp": frame["frame_timestamp_seconds"],
                    "detections": [
                        {
                            "class": d["object_class"],
                            "confidence": d["confidence"],
                            "box": [
                                d["bounds"][name]
                                for name in ("x_min", "y_min", "x_max", "y_max")
                            ],
                        }
                        for d in frame["detections"]
                    ],
                    "output_sha256": hashlib.sha256(response.content).hexdigest(),
                }
    if not any(frame["detections"] for frame in report["frames"].values()):
        raise ValueError(
            "An all-empty run is not a useful detector regression reference."
        )
    report["differences"] = (
        []
        if reference is None
        else compare_records(reference, report, manifest["tolerances"])
    )
    report["status"] = (
        "baseline_established"
        if reference is None
        else "review_required"
        if report["differences"]
        else "pass"
    )
    report["baseline_sha256"] = None if reference is None else sha256(args.baseline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.establish_baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "differences": report["differences"],
                "sessions": report["sessions"],
            },
            indent=2,
        )
    )
    return 1 if report["differences"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
