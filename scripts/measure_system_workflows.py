"""Record warm API workflow timings. This is not the final system evaluation."""

import argparse
import csv
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx

from app.runtime_provenance import source_identity
from evaluation.system_measurement import (
    ResourceSampler,
    attach_stage_records,
    backend_identity,
    check_result_identity,
    load_scenarios,
    measure_request,
    sha256,
    summarize,
    utc_now,
    validate_local_url,
)


def write_report(directory, report):
    temporary = directory / "report.json.tmp"
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    temporary.replace(directory / "report.json")


def write_csv(directory, rows):
    columns = [
        "scenario_id",
        "phase",
        "repetition",
        "status",
        "request_id",
        "session_id",
        "api_seconds",
        "failure_code",
        "evidence_error",
        "stage_evidence_complete",
        "inference",
        "image_persistence",
        "video_persistence",
        "video_queue",
    ]
    with (directory / "requests.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, **row.get("stage_seconds", {})})


def positive_seconds(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Use a finite positive number.")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--backend-container", required=True)
    parser.add_argument("--gpu-id", default="0")
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=ROOT / "configs/evaluation/system_workflows.json",
    )
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--timeout", type=positive_seconds, default=360.0)
    parser.add_argument("--poll-interval", type=positive_seconds, default=0.25)
    parser.add_argument("--sample-interval", type=positive_seconds, default=1.0)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        validate_local_url(args.base_url)
        if not 1 <= args.repetitions <= 100:
            raise ValueError("Repetitions must be between 1 and 100.")
        scenarios = load_scenarios(args.scenarios)
        args.output_directory.mkdir(parents=True, exist_ok=False)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    report = {
        "schema_version": 1,
        "run_id": str(uuid4()),
        "purpose": "Warm workflow instrumentation check; not final evaluation/accuracy",
        "started_at": utc_now(),
        "status": "in_progress",
        "runner": source_identity(ROOT),
        "runner_sha256": sha256(Path(__file__)),
        "measurement_module_sha256": sha256(ROOT / "evaluation/system_measurement.py"),
        "scenario_file_sha256": sha256(args.scenarios),
        "scenarios": [scenario.model_dump() for scenario in scenarios],
        "settings": {
            "base_url": args.base_url,
            "backend_container": args.backend_container,
            "gpu_id": args.gpu_id,
            "repetitions": args.repetitions,
            "warmups_per_scenario": 1,
            "timeout_seconds": args.timeout,
            "poll_interval_seconds": args.poll_interval,
            "resource_target_interval_seconds": args.sample_interval,
            "p95_method": "nearest-rank ceil(0.95*n); n=10 gives maximum",
        },
        "requests": [],
        "batches": [],
        "errors": [],
    }
    write_report(args.output_directory, report)
    sampler = ResourceSampler(
        args.backend_container, gpu_id=args.gpu_id, interval=args.sample_interval
    )
    try:
        identity = backend_identity(args.backend_container)
        report["backend"] = identity
        with (
            sampler,
            httpx.Client(
                base_url=args.base_url,
                timeout=args.timeout,
                trust_env=False,
                follow_redirects=False,
            ) as client,
        ):
            client.get("/api/ready").raise_for_status()
            response = client.get("/api/capabilities")
            response.raise_for_status()
            report["capabilities"] = response.json()
            for scenario in scenarios:
                batch_started = None
                batch = {"scenario_id": scenario.scenario_id, "seconds": None}
                report["batches"].append(batch)
                for repetition in range(args.repetitions + 1):
                    if repetition == 1:
                        batch_started = time.monotonic()
                    row, result = measure_request(
                        client,
                        scenario,
                        phase="warmup" if repetition == 0 else "measured",
                        repetition=repetition,
                        timeout=args.timeout,
                        poll_interval=args.poll_interval,
                    )
                    report["requests"].append(row)
                    if result is not None:
                        try:
                            profile, runtime = check_result_identity(
                                result,
                                identity,
                                report.get("model_profile"),
                            )
                            report["model_profile"] = profile
                            row["runtime_provenance"] = runtime
                        except (ValueError, KeyError, TypeError, AttributeError):
                            row["evidence_error"] = "backend_or_profile_mismatch"
                    if batch_started is not None:
                        batch["seconds"] = time.monotonic() - batch_started
                    write_report(args.output_directory, report)
                    if row["status"] != "completed" or row.get("evidence_error"):
                        # A timed-out job may still run. Never overlap a retry with it.
                        raise RuntimeError(
                            "Workflow failed; remaining requests were not sent."
                        )
            if backend_identity(args.backend_container) != identity:
                raise ValueError("Backend restarted or changed during measurement.")
            load_scenarios(args.scenarios)
    except (Exception, KeyboardInterrupt) as error:
        # Store types, not exception text that may contain server paths or secrets.
        report["errors"].append(type(error).__name__)
    finally:
        report["resource_samples"] = sampler.samples
        report["resource_status"] = (
            "recorded"
            if sampler.samples
            and not any(sample.get("error") for sample in sampler.samples)
            else "incomplete"
        )
        try:
            logs = subprocess.run(
                [
                    "docker",
                    "logs",
                    "--since",
                    report["started_at"],
                    args.backend_container,
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            attach_stage_records(report["requests"], logs.stdout + "\n" + logs.stderr)
        except (OSError, subprocess.SubprocessError):
            report["errors"].append("stage_logs_unavailable")
            attach_stage_records(report["requests"], "")
        report["summary"] = summarize(report["requests"])
        for batch in report["batches"]:
            frames = sum(
                row.get("sampled_frames", 0)
                for row in report["requests"]
                if row["scenario_id"] == batch["scenario_id"]
                and row["phase"] == "measured"
                and row["status"] == "completed"
            )
            batch["completed_sampled_frames"] = frames
            batch["sampled_frames_per_second"] = (
                frames / batch["seconds"] if batch["seconds"] else None
            )
        expected = len(scenarios) * (args.repetitions + 1)
        complete = (
            not report["errors"]
            and report["resource_status"] == "recorded"
            and len(report["requests"]) == expected
            and all(
                row["status"] == "completed"
                and row["stage_evidence_complete"]
                and not row.get("evidence_error")
                for row in report["requests"]
            )
        )
        report["status"] = "recorded" if complete else "incomplete"
        report["finished_at"] = utc_now()
        write_report(args.output_directory, report)
        write_csv(args.output_directory, report["requests"])
        hashes = {
            name: sha256(args.output_directory / name)
            for name in ("report.json", "requests.csv")
        }
        (args.output_directory / "sha256.json").write_text(
            json.dumps(hashes, indent=2) + "\n"
        )
    print(
        json.dumps(
            {
                "status": report["status"],
                "requests": len(report["requests"]),
                "report": str(args.output_directory / "report.json"),
            },
            indent=2,
        )
    )
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
