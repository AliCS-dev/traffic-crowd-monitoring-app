"""Warm API workflow measurements, separate from model-quality evaluation."""

import hashlib
import json
import math
import mimetypes
import statistics
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.runtime_provenance import source_digest

ROOT = Path(__file__).resolve().parent.parent


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def command(*arguments):
    return subprocess.check_output(
        arguments, cwd=ROOT, text=True, stderr=subprocess.PIPE, timeout=15
    ).strip()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    scenario_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    kind: str = Field(pattern=r"^(image|video)$")
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    grid_rows: int | None = Field(default=None, ge=1, le=20)
    grid_columns: int | None = Field(default=None, ge=1, le=20)
    sampling_interval_seconds: float = Field(default=1.0, ge=0.25, le=3600)


def load_scenarios(path, *, root=ROOT):
    scenarios = [Scenario.model_validate(row) for row in json.loads(path.read_text())]
    if not scenarios or len({row.scenario_id for row in scenarios}) != len(scenarios):
        raise ValueError("Scenarios must be nonempty and have unique IDs.")
    for row in scenarios:
        if (row.grid_rows is None) != (row.grid_columns is None):
            raise ValueError("Both grid dimensions are required together.")
        media = (root / row.path).resolve()
        if not media.is_relative_to(root.resolve()) or sha256(media) != row.sha256:
            raise ValueError(f"Input path or checksum mismatch: {row.scenario_id}")
    return scenarios


def validate_local_url(url):
    parsed = urlparse(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Use a local HTTP origin without credentials or a path.")


def backend_identity(container):
    # Select fields rather than retaining docker inspect's environment/secrets.
    result = json.loads(
        command(
            "docker",
            "inspect",
            "--format",
            '{"id":{{json .Id}},"image":{{json .Image}},'
            '"started_at":{{json .State.StartedAt}},"running":{{json .State.Running}}}',
            container,
        )
    )
    result["source_sha256"] = command(
        "docker",
        "exec",
        container,
        "python",
        "-c",
        "from pathlib import Path; from app.runtime_provenance import source_digest; "
        "print(source_digest(Path('/app')))",
    )
    if not result["running"] or result["source_sha256"] != source_digest(ROOT):
        raise ValueError("The running backend does not match this source tree.")
    return result


class ResourceSampler:
    """Timestamped samples; neither cgroup nor device readings are exact peaks."""

    def __init__(self, container, *, gpu_id="0", interval=1.0):
        self.container, self.gpu_id, self.interval = container, gpu_id, interval
        self.samples = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="system-measurement")

    def _run(self):
        while not self.stop.is_set():
            started = time.monotonic()
            for resource, arguments, divisor in (
                (
                    "backend_cgroup_mib",
                    (
                        "docker",
                        "exec",
                        self.container,
                        "cat",
                        "/sys/fs/cgroup/memory.current",
                    ),
                    1024**2,
                ),
                (
                    "whole_gpu_device_mib",
                    (
                        "nvidia-smi",
                        f"--id={self.gpu_id}",
                        "--query-gpu=memory.used",
                        "--format=csv,noheader,nounits",
                    ),
                    1,
                ),
            ):
                sample = {"resource": resource, "started_at": utc_now()}
                try:
                    value = float(command(*arguments)) / divisor
                    if not math.isfinite(value) or value < 0:
                        raise ValueError("Invalid resource reading")
                    sample["value"] = value
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    sample.update(value=None, error=type(error).__name__)
                sample["finished_at"] = utc_now()
                self.samples.append(sample)
            self.stop.wait(max(0, self.interval - (time.monotonic() - started)))

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.stop.set()
        self.thread.join()


def measure_request(
    client, scenario, *, phase, repetition, timeout, poll_interval, root=ROOT
):
    row = {
        "scenario_id": scenario.scenario_id,
        "kind": scenario.kind,
        "phase": phase,
        "repetition": repetition,
        "started_at": utc_now(),
        "status": "failed",
        "request_id": None,
        "session_id": None,
        "api_seconds": None,
        "failure_code": None,
    }
    data = {"session_name": f"system-{scenario.scenario_id}-{phase}-{repetition}"}
    if scenario.grid_rows is not None:
        data.update(
            grid_rows=str(scenario.grid_rows), grid_columns=str(scenario.grid_columns)
        )
    if scenario.kind == "video":
        data["sampling_interval_seconds"] = str(scenario.sampling_interval_seconds)
    media = root / scenario.path
    started = time.monotonic()
    result = None
    try:
        with media.open("rb") as handle:
            # The boundary starts immediately before the multipart POST.
            started = time.monotonic()
            response = client.post(
                f"/api/analyses/{scenario.kind}s",
                data=data,
                files={
                    scenario.kind: (
                        media.name,
                        handle,
                        mimetypes.guess_type(media.name)[0]
                        or "application/octet-stream",
                    )
                },
                timeout=timeout,
            )
            response_finished = time.monotonic()
        row["request_id"] = response.headers.get("x-request-id")
        row["http_status"] = response.status_code
        response.raise_for_status()
        submitted = response.json()
        row["session_id"] = int(submitted["session_id"])
        if scenario.kind == "video":
            while True:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError("Video completion deadline exceeded")
                response = client.get(
                    f"/api/analyses/videos/{row['session_id']}",
                    timeout=remaining,
                )
                response_finished = time.monotonic()
                response.raise_for_status()
                job = response.json()
                if job["status"] == "completed":
                    row["sampled_frames"] = job["sampled_frames_processed"]
                    break
                if job["status"] == "failed":
                    row["failure_code"] = job.get("failure_code") or "video_failed"
                    raise RuntimeError("Video processing failed")
                time.sleep(min(poll_interval, max(0, remaining)))
        else:
            row["sampled_frames"] = 1
        row["api_seconds"] = response_finished - started
        row["status"] = "completed"
        # Result/provenance reads are not included in API completion latency.
        response = client.get(f"/api/analyses/{row['session_id']}", timeout=timeout)
        response.raise_for_status()
        result = response.json()
    except (
        httpx.HTTPError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        KeyboardInterrupt,
    ) as error:
        row["failure_code"] = row["failure_code"] or type(error).__name__
        if row["api_seconds"] is None:
            row["api_seconds"] = time.monotonic() - started
        if row["status"] == "completed":
            row["evidence_error"] = "result_read_failed"
    row["finished_at"] = utc_now()
    return row, result


def check_result_identity(result, expected_backend, previous_profile):
    profile = dict(result["model_profile"])
    runtime = profile.pop("runtime_provenance")
    profile.pop("created_at", None)
    container_id = runtime.get("container_id") if runtime else None
    if (
        not isinstance(container_id, str)
        or len(container_id) < 12
        or not expected_backend["id"].startswith(container_id)
        or runtime.get("source_sha256") != expected_backend["source_sha256"]
        or (previous_profile is not None and previous_profile != profile)
    ):
        raise ValueError("Backend identity or model settings changed.")
    return profile, runtime


def attach_stage_records(rows, log_text):
    by_request = {row["request_id"]: [] for row in rows if row["request_id"]}
    for line in log_text.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        if (
            record.get("event") == "stage_timing"
            and record.get("request_id") in by_request
        ):
            by_request[record["request_id"]].append(record)
    for row in rows:
        records = by_request.get(row["request_id"], [])
        row["stages"] = records
        expected = {
            "inference": row.get("sampled_frames", 0),
            f"{row['kind']}_persistence": 1,
        }
        if row["kind"] == "video":
            expected["video_queue"] = 1
        row["stage_seconds"] = {}
        complete = True
        for stage, count in expected.items():
            selected = [record for record in records if record.get("stage") == stage]
            valid = (
                count > 0
                and len(selected) == count
                and all(
                    item.get("stage_status") == "completed"
                    and isinstance(item.get("duration_seconds"), (int, float))
                    and not isinstance(item["duration_seconds"], bool)
                    and math.isfinite(item["duration_seconds"])
                    and item["duration_seconds"] >= 0
                    for item in selected
                )
            )
            row["stage_seconds"][stage] = (
                sum(item["duration_seconds"] for item in selected) if valid else None
            )
            complete = complete and valid
        row["stage_evidence_complete"] = complete


def statistics_record(values):
    if not values:
        return {"n": 0, "median": None, "min": None, "max": None, "p95": None}
    ordered = sorted(values)
    return {
        "n": len(values),
        "median": statistics.median(values),
        "min": ordered[0],
        "max": ordered[-1],
        "p95": ordered[math.ceil(0.95 * len(values)) - 1],
    }


def summarize(rows):
    summaries = {}
    for scenario_id in dict.fromkeys(row["scenario_id"] for row in rows):
        measured = [
            row
            for row in rows
            if row["scenario_id"] == scenario_id and row["phase"] == "measured"
        ]
        successes = [row for row in measured if row["status"] == "completed"]
        summaries[scenario_id] = {
            "attempted": len(measured),
            "completed": len(successes),
            "failed": len(measured) - len(successes),
            "complete_evidence": sum(
                row.get("stage_evidence_complete", False)
                and not row.get("evidence_error")
                for row in successes
            ),
            "api_seconds": statistics_record([row["api_seconds"] for row in successes]),
            "stage_seconds": {
                stage: statistics_record(
                    [
                        row["stage_seconds"][stage]
                        for row in successes
                        if row.get("stage_seconds", {}).get(stage) is not None
                        and not row.get("evidence_error")
                    ]
                )
                for stage in (
                    "inference",
                    "image_persistence",
                    "video_persistence",
                    "video_queue",
                )
            },
        }
    return summaries
