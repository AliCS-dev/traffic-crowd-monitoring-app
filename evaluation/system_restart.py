"""Opt-in backend restart measurements and saved-result integrity checks."""

import hashlib
import json
import re
import subprocess
import time

import httpx

from evaluation.system_measurement import backend_identity, command, utc_now

MEASUREMENT_LABEL = "org.traffic-monitoring.measurement"


def require_disposable_backend(container_id):
    labels = json.loads(
        command(
            "docker", "inspect", "--format", "{{json .Config.Labels}}", container_id
        )
    )
    if (
        not isinstance(labels, dict)
        or labels.get(MEASUREMENT_LABEL) != "disposable"
        or labels.get("com.docker.compose.service") != "backend"
        or not labels.get("com.docker.compose.project")
    ):
        raise ValueError("Restart measurements require a labelled disposable backend.")
    return labels["com.docker.compose.project"]


def measure_restart(client, expected, *, timeout, poll_interval):
    row = {
        "status": "failed",
        "started_at": utc_now(),
        "backend_before": expected,
        "ready_seconds": None,
        "command_seconds": None,
        "polls": [],
    }
    started = time.monotonic()
    try:
        require_disposable_backend(expected["id"])
        if backend_identity(expected["id"]) != expected:
            raise ValueError("Backend changed before restart.")
        # Pin the immutable ID, not a container name that could be reassigned.
        started = time.monotonic()
        row["command_started_at"] = utc_now()
        subprocess.run(
            ["docker", "restart", "--time", "40", expected["id"]],
            check=True,
            capture_output=True,
            timeout=timeout,
        )
        row["command_seconds"] = time.monotonic() - started
        while True:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("Readiness deadline exceeded.")
            poll = {"started_at": utc_now()}
            ready = False
            try:
                response = client.get("/api/ready", timeout=min(2, remaining))
                poll["http_status"] = response.status_code
                ready = (
                    response.status_code == 200
                    and response.json().get("status") == "ready"
                )
            except (httpx.HTTPError, ValueError, AttributeError) as error:
                poll["error"] = type(error).__name__
            elapsed = time.monotonic() - started
            poll.update(elapsed_seconds=elapsed, ready=ready)
            row["polls"].append(poll)
            if ready and elapsed <= timeout:
                row["ready_seconds"] = elapsed
                break
            time.sleep(min(poll_interval, max(0, timeout - elapsed)))
        after = backend_identity(expected["id"])
        row["backend_after"] = after
        if any(after[key] != expected[key] for key in ("id", "image", "source_sha256")):
            raise ValueError("Backend identity changed across restart.")
        if after["started_at"] == expected["started_at"]:
            raise ValueError("No new backend process start was observed.")
        row["status"] = "completed"
    except (Exception, KeyboardInterrupt) as error:
        # Exception messages may include local paths or server details.
        row["failure_code"] = type(error).__name__
    row["elapsed_seconds"] = time.monotonic() - started
    row["finished_at"] = utc_now()
    return row


def saved_result_evidence(client, session_id, *, timeout):
    response = client.get(f"/api/analyses/{session_id}", timeout=timeout)
    response.raise_for_status()
    result = response.json()
    if (
        result["id"] != session_id
        or result["status"] != "completed"
        or not result["frames"]
    ):
        raise ValueError("A completed saved result with frames is required.")
    assets = {}
    for frame in result["frames"]:
        for variant in ("source_asset", "visual_asset"):
            url = frame[variant]["url"]
            # Never follow a server-provided external URL or redirect.
            if not re.fullmatch(r"/api/assets/[0-9a-fA-F-]{36}(?:/source)?", url):
                raise ValueError("Unexpected saved asset URL.")
            media = client.get(url, timeout=timeout, follow_redirects=False)
            media.raise_for_status()
            if media.headers.get(
                "content-type"
            ) != "image/jpeg" or not media.content.startswith(b"\xff\xd8"):
                raise ValueError("Saved media is not a JPEG response.")
            assets[url] = hashlib.sha256(media.content).hexdigest()
    return {
        "session_id": session_id,
        "frames": len(result["frames"]),
        "result_sha256": hashlib.sha256(
            json.dumps(result, sort_keys=True, allow_nan=False).encode()
        ).hexdigest(),
        "assets": assets,
    }


def measure_saved_recovery(client, baseline, *, timeout):
    row = {"status": "failed", "started_at": utc_now(), "seconds": None}
    started = time.monotonic()
    try:
        actual = saved_result_evidence(client, baseline["session_id"], timeout=timeout)
        row["seconds"] = time.monotonic() - started
        row["actual"] = actual
        if actual != baseline:
            raise ValueError("Saved result or media changed after restart.")
        row["status"] = "completed"
    except (Exception, KeyboardInterrupt) as error:
        row["failure_code"] = type(error).__name__
    row["elapsed_seconds"] = time.monotonic() - started
    row["finished_at"] = utc_now()
    return row
