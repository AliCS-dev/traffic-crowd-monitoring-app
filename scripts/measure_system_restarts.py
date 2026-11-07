"""Measure opt-in disposable backend restarts, cold requests and saved recovery."""

import argparse
import csv
import json
import math
import subprocess
import sys
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
    statistics_record,
    summarize,
    utc_now,
    validate_local_url,
)
from evaluation.system_restart import (
    measure_restart,
    measure_saved_recovery,
    require_disposable_backend,
    saved_result_evidence,
)


def positive_seconds(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Use a finite positive number.")
    return number


def checkpoint(directory, report):
    temporary = directory / "report.json.tmp"
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    temporary.replace(directory / "report.json")


def checked_request(report, client, scenario, identity, args, *, phase, repetition):
    row, result = measure_request(
        client,
        scenario,
        phase=phase,
        repetition=repetition,
        timeout=args.timeout,
        poll_interval=args.poll_interval,
    )
    report["requests"].append(row)
    if row["status"] == "completed" and not row.get("evidence_error"):
        try:
            profile, runtime = check_result_identity(
                result, identity, report.get("model_profile")
            )
            report["model_profile"] = profile
            row["runtime_provenance"] = runtime
        except (ValueError, KeyError, TypeError, AttributeError):
            row["evidence_error"] = "backend_or_profile_mismatch"
    if row["status"] != "completed" or row.get("evidence_error"):
        raise RuntimeError("Request failed; no later requests or restarts will run.")
    return row


def finish_report(directory, report):
    report["cold_summary"] = summarize(report["requests"], phase="cold_process")
    report["restart_summary"] = {}
    for scenario in report["scenarios"]:
        trials = [
            t for t in report["trials"] if t["scenario_id"] == scenario["scenario_id"]
        ]
        completed = [t for t in trials if t["status"] == "completed"]
        report["restart_summary"][scenario["scenario_id"]] = {
            "attempted": len(trials),
            "completed": len(completed),
            "failed": len(trials) - len(completed),
            "restart_ready_seconds": statistics_record(
                [
                    t["restart"]["ready_seconds"]
                    for t in trials
                    if t.get("restart", {}).get("status") == "completed"
                ]
            ),
            "saved_recovery_seconds": statistics_record(
                [
                    t["recovery"]["seconds"]
                    for t in trials
                    if t.get("recovery", {}).get("status") == "completed"
                ]
            ),
        }
    expected = len(report["scenarios"]) * report["settings"]["repetitions"]
    complete = (
        not report["errors"]
        and len(report["trials"]) == expected
        and all(t["status"] == "completed" for t in report["trials"])
        and len(report["requests"]) == expected + len(report["scenarios"])
        and all(
            r["status"] == "completed"
            and r["stage_evidence_complete"]
            and not r.get("evidence_error")
            for r in report["requests"]
        )
    )
    report.update(
        status="recorded" if complete else "incomplete", finished_at=utc_now()
    )
    checkpoint(directory, report)
    columns = [
        "scenario_id",
        "repetition",
        "status",
        "restart_ready_seconds",
        "cold_api_seconds",
        "saved_recovery_seconds",
        "failure_code",
    ]
    with (directory / "restarts.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for trial in report["trials"]:
            writer.writerow(
                {
                    **{
                        key: trial.get(key)
                        for key in (
                            "scenario_id",
                            "repetition",
                            "status",
                            "failure_code",
                        )
                    },
                    "restart_ready_seconds": trial.get("restart", {}).get(
                        "ready_seconds"
                    ),
                    "cold_api_seconds": trial.get("cold_api_seconds"),
                    "saved_recovery_seconds": trial.get("recovery", {}).get("seconds"),
                }
            )
    (directory / "sha256.json").write_text(
        json.dumps(
            {
                name: sha256(directory / name)
                for name in ("report.json", "restarts.csv")
            },
            indent=2,
        )
        + "\n"
    )
    return 0 if complete else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--backend-container", required=True)
    parser.add_argument("--allow-backend-restart", action="store_true")
    parser.add_argument("--gpu-id", default="0")
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=ROOT / "configs/evaluation/system_workflows.json",
    )
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--timeout", type=positive_seconds, default=360)
    parser.add_argument("--restart-timeout", type=positive_seconds, default=180)
    parser.add_argument("--poll-interval", type=positive_seconds, default=0.25)
    parser.add_argument("--sample-interval", type=positive_seconds, default=1)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        validate_local_url(args.base_url)
        if not args.allow_backend_restart or not 1 <= args.repetitions <= 10:
            raise ValueError(
                "Explicit restart consent and 1-10 repetitions are required."
            )
        scenarios = load_scenarios(args.scenarios)
        args.output_directory.mkdir(parents=True, exist_ok=False)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    tracked = {
        "runner": Path(__file__),
        "requests": ROOT / "evaluation/system_measurement.py",
        "restarts": ROOT / "evaluation/system_restart.py",
        "scenarios": args.scenarios,
    }
    hashes = {name: sha256(path) for name, path in tracked.items()}
    report = {
        "schema_version": 1,
        "run_id": str(uuid4()),
        "started_at": utc_now(),
        "purpose": "Restart tooling verification; not final evaluation or accuracy",
        "status": "in_progress",
        "runner": source_identity(ROOT),
        "tool_sha256": hashes,
        "settings": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in vars(args).items()
        },
        "scenarios": [s.model_dump() for s in scenarios],
        "requests": [],
        "baselines": [],
        "trials": [],
        "errors": [],
    }
    checkpoint(args.output_directory, report)
    try:
        identity = backend_identity(args.backend_container)
        report["backend"] = identity
        report["compose_project"] = require_disposable_backend(identity["id"])
        with httpx.Client(
            base_url=args.base_url,
            timeout=args.timeout,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            ready = client.get("/api/ready")
            ready.raise_for_status()
            if ready.json().get("status") != "ready":
                raise ValueError("Backend is not ready.")
            for scenario in scenarios:
                seed = checked_request(
                    report,
                    client,
                    scenario,
                    identity,
                    args,
                    phase="recovery_seed",
                    repetition=0,
                )
                baseline = saved_result_evidence(
                    client, seed["session_id"], timeout=args.timeout
                )
                report["baselines"].append(baseline)
                checkpoint(args.output_directory, report)
                for repetition in range(1, args.repetitions + 1):
                    trial = {
                        "scenario_id": scenario.scenario_id,
                        "repetition": repetition,
                        "status": "in_progress",
                    }
                    report["trials"].append(trial)
                    checkpoint(args.output_directory, report)
                    trial["restart"] = measure_restart(
                        client,
                        identity,
                        timeout=args.restart_timeout,
                        poll_interval=args.poll_interval,
                    )
                    checkpoint(args.output_directory, report)
                    if trial["restart"]["status"] != "completed":
                        raise RuntimeError(
                            "Restart failed; remaining trials were not attempted."
                        )
                    identity = trial["restart"]["backend_after"]
                    sampler = ResourceSampler(
                        identity["id"],
                        gpu_id=args.gpu_id,
                        interval=args.sample_interval,
                    )
                    try:
                        with sampler:
                            row = checked_request(
                                report,
                                client,
                                scenario,
                                identity,
                                args,
                                phase="cold_process",
                                repetition=repetition,
                            )
                            trial["request_id"] = row["request_id"]
                            trial["cold_api_seconds"] = row["api_seconds"]
                    finally:
                        trial["resource_samples"] = sampler.samples
                    trial["recovery"] = measure_saved_recovery(
                        client, baseline, timeout=args.timeout
                    )
                    if trial["recovery"]["status"] != "completed":
                        raise RuntimeError("Saved recovery failed.")
                    if not sampler.samples or any(
                        s.get("error") for s in sampler.samples
                    ):
                        raise ValueError(
                            "Cold-request resource evidence is incomplete."
                        )
                    if backend_identity(identity["id"]) != identity:
                        raise ValueError("Backend changed during a trial.")
                    trial["status"] = "completed"
                    checkpoint(args.output_directory, report)
            if load_scenarios(args.scenarios) != scenarios or any(
                sha256(path) != hashes[name] for name, path in tracked.items()
            ):
                raise ValueError("Measurement inputs or tools changed during the run.")
            if source_identity(ROOT) != report["runner"]:
                raise ValueError("Runner source identity changed.")
    except (Exception, KeyboardInterrupt) as error:
        report["errors"].append(type(error).__name__)
        for trial in report["trials"]:
            if trial["status"] == "in_progress":
                trial.update(status="failed", failure_code=type(error).__name__)
    finally:
        try:
            logs = subprocess.run(
                [
                    "docker",
                    "logs",
                    "--since",
                    report["started_at"],
                    report.get("backend", {}).get("id", args.backend_container),
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
        code = finish_report(args.output_directory, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "trials": len(report["trials"]),
                "report": str(args.output_directory / "report.json"),
            }
        )
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
