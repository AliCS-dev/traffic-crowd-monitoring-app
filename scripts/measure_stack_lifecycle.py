"""Measure fresh-stack startup and idle outages on a disposable GPU stack."""

import argparse
import csv
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx

from app.runtime_provenance import source_identity
from evaluation.stack_lifecycle import (
    COMPOSE_FILES,
    DisposableStack,
    measure_outage,
    measure_startup,
    require_same_stack,
)
from evaluation.system_measurement import (
    backend_identity,
    check_result_identity,
    load_scenarios,
    measure_request,
    sha256,
    utc_now,
)
from evaluation.system_restart import measure_saved_recovery, saved_result_evidence
from scripts.measure_system_restarts import checkpoint, positive_seconds


def run_workflow(report, client, scenario, backend, args, phase):
    row, result = measure_request(
        client,
        scenario,
        phase=phase,
        repetition=1,
        timeout=args.request_timeout,
        poll_interval=args.poll_interval,
    )
    report["requests"].append(row)
    if row["status"] != "completed" or row.get("evidence_error"):
        raise ValueError("Workflow failed; no later submission will run.")
    try:
        profile, runtime = check_result_identity(
            result, backend, report.get("model_profile")
        )
        report["model_profile"] = profile
        row["runtime_provenance"] = runtime
    except (ValueError, KeyError, TypeError, AttributeError):
        row["evidence_error"] = "backend_or_profile_mismatch"
        raise
    return saved_result_evidence(
        client, row["session_id"], timeout=args.request_timeout
    )


def finish(directory, report):
    report["finished_at"] = utc_now()
    checkpoint(directory, report)
    with (directory / "lifecycle.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "phase",
                "status",
                "ready_seconds",
                "elapsed_seconds",
                "failure_code",
            ],
        )
        writer.writeheader()
        for phase, row in [("fresh_stack_startup", report.get("startup", {}))] + [
            (f"{row['service']}_outage", row) for row in report["outages"]
        ]:
            writer.writerow(
                {
                    "phase": phase,
                    **{k: row.get(k) for k in writer.fieldnames if k != "phase"},
                }
            )
    (directory / "sha256.json").write_text(
        json.dumps(
            {
                name: sha256(directory / name)
                for name in ("report.json", "lifecycle.csv")
            },
            indent=2,
        )
        + "\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--port", type=int, default=8086)
    parser.add_argument("--backend-image", required=True)
    parser.add_argument("--frontend-image", required=True)
    parser.add_argument("--allow-stack-interruption", action="store_true")
    parser.add_argument("--timeout", type=positive_seconds, default=180)
    parser.add_argument("--request-timeout", type=positive_seconds, default=360)
    parser.add_argument("--poll-interval", type=positive_seconds, default=0.25)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=ROOT / "configs/evaluation/system_workflows.json",
    )
    args = parser.parse_args(argv)
    try:
        if not args.allow_stack_interruption:
            raise ValueError("Explicit stack interruption consent is required.")
        stack = DisposableStack(
            args.project,
            args.port,
            args.backend_image,
            args.frontend_image,
            secrets.token_urlsafe(24),
        )
        scenarios_path = args.scenarios.resolve()
        if not scenarios_path.is_relative_to(ROOT):
            raise ValueError("Scenario configuration must be inside the repository.")
        scenarios = load_scenarios(scenarios_path)
        stack.preflight()
        args.output_directory.mkdir(parents=True, exist_ok=False)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    tracked = [
        Path(__file__),
        ROOT / "evaluation/stack_lifecycle.py",
        ROOT / "evaluation/system_restart.py",
        ROOT / "evaluation/system_measurement.py",
        ROOT / "scripts/measure_system_restarts.py",
        scenarios_path,
    ] + [ROOT / p for p in COMPOSE_FILES]
    hashes = {str(p.relative_to(ROOT)): sha256(p) for p in tracked}
    report = {
        "schema_version": 1,
        "status": "in_progress",
        "started_at": utc_now(),
        "purpose": "Lifecycle tooling verification; not final evaluation or accuracy",
        "runner": source_identity(ROOT),
        "tool_sha256": hashes,
        "settings": {
            k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()
        },
        "images": stack.images,
        "scenarios": [s.model_dump() for s in scenarios],
        "requests": [],
        "baselines": [],
        "outages": [],
        "errors": [],
        "retained_project": stack.project,
    }
    checkpoint(args.output_directory, report)
    try:
        with httpx.Client(
            base_url=stack.origin,
            trust_env=False,
            follow_redirects=False,
            timeout=args.request_timeout,
        ) as client:
            report["startup"] = measure_startup(
                stack, client, timeout=args.timeout, poll_interval=args.poll_interval
            )
            checkpoint(args.output_directory, report)
            if report["startup"]["status"] != "completed":
                raise RuntimeError("Startup failed.")
            expected = report["startup"]["containers"]
            backend = backend_identity(expected["backend"]["id"])
            report["backend"] = backend
            for scenario in scenarios:
                report["baselines"].append(
                    run_workflow(report, client, scenario, backend, args, "seed")
                )
                checkpoint(args.output_directory, report)
            for service in ("postgres", "backend"):
                row = {"service": service, "status": "in_progress"}
                report["outages"].append(row)
                checkpoint(args.output_directory, report)
                row.update(
                    measure_outage(
                        stack,
                        client,
                        service,
                        expected,
                        report["baselines"][0]["session_id"],
                        timeout=args.timeout,
                        poll_interval=args.poll_interval,
                    )
                )
                checkpoint(args.output_directory, report)
                if row["status"] != "completed":
                    raise RuntimeError("Outage or restoration check failed.")
                row["status"] = "verifying_saved_results"
                checkpoint(args.output_directory, report)
                try:
                    backend = backend_identity(expected["backend"]["id"])
                    row["backend_after"] = backend
                    row["saved_recovery"] = []
                    for baseline in report["baselines"]:
                        recovery = measure_saved_recovery(
                            client, baseline, timeout=args.request_timeout
                        )
                        row["saved_recovery"].append(recovery)
                        if recovery["status"] != "completed":
                            raise RuntimeError("Saved result integrity check failed.")
                    row["new_results"] = []
                    for scenario in scenarios:
                        row["new_results"].append(
                            run_workflow(
                                report,
                                client,
                                scenario,
                                backend,
                                args,
                                f"after_{service}_outage",
                            )
                        )
                    expected = stack.snapshot()
                    require_same_stack(expected, row["containers_after"])
                    row["status"] = "completed"
                except (Exception, KeyboardInterrupt) as error:
                    row.update(status="failed", failure_code=type(error).__name__)
                    raise
                finally:
                    checkpoint(args.output_directory, report)
            if (
                source_identity(ROOT) != report["runner"]
                or any(sha256(p) != hashes[str(p.relative_to(ROOT))] for p in tracked)
                or load_scenarios(scenarios_path) != scenarios
            ):
                raise ValueError("Source or measurement inputs changed during the run.")
            report["final_containers"] = stack.snapshot()
            require_same_stack(report["final_containers"], expected)
            report["status"] = "recorded"
    except (Exception, KeyboardInterrupt) as error:
        report["errors"].append(type(error).__name__)
        report["status"] = "incomplete"
    finally:
        # Keep the isolated stack for inspection; never automatically delete evidence.
        finish(args.output_directory, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "report": str(args.output_directory / "report.json"),
                "retained_project": stack.project,
            }
        )
    )
    return 0 if report["status"] == "recorded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
