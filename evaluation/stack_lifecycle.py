"""Controlled lifecycle checks for a newly created measurement Compose project."""

import json
import os
import re
import socket
import subprocess
import time
from pathlib import Path

import httpx

from evaluation.system_measurement import command, utc_now

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILES = (
    "docker-compose.app.yml",
    "docker-compose.gpu.yml",
    "docker-compose.measurement.yml",
)
SERVICES = {"postgres", "migrate", "backend", "frontend"}


class DisposableStack:
    def __init__(self, project, port, backend_image, frontend_image, password):
        if not re.fullmatch(r"traffic-measure-[a-z0-9-]{1,40}", project):
            raise ValueError("Use a new traffic-measure- project name.")
        if not 1024 <= port <= 65535:
            raise ValueError("Use a nonprivileged local port.")
        self.project, self.port = project, port
        self.origin = f"http://127.0.0.1:{port}"
        # Do not inherit application overrides or credentials from the user's shell.
        self.env = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "HOME", "XDG_RUNTIME_DIR", "SSH_AUTH_SOCK"}
            or key.startswith("DOCKER_")
        }
        self.env.update(
            POSTGRES_PASSWORD=password,
            BACKEND_IMAGE=backend_image,
            MEASUREMENT_FRONTEND_IMAGE=frontend_image,
            FRONTEND_PORT=str(port),
        )
        self.images = {}

    def compose(self, *arguments, timeout):
        prefix = ["docker", "compose", "--env-file", "/dev/null", "-p", self.project]
        for file in COMPOSE_FILES:
            prefix += ["-f", str(ROOT / file)]
        subprocess.run(
            prefix + list(arguments),
            cwd=ROOT,
            env=self.env,
            check=True,
            capture_output=True,
            timeout=timeout,
        )

    def preflight(self):
        # Existing stopped containers and retained volumes count as existing data.
        for args in (
            ("ps", "-aq"),
            ("volume", "ls", "-q"),
            ("network", "ls", "-q"),
        ):
            if command(
                "docker",
                *args,
                "--filter",
                f"label=com.docker.compose.project={self.project}",
            ):
                raise ValueError("Measurement project already exists; refusing reuse.")
        for volume in ("postgres_data", "outputs", "uploads"):
            names = command("docker", "volume", "ls", "--format", "{{.Name}}")
            if f"{self.project}_{volume}" in names.splitlines():
                raise ValueError("A target volume already exists.")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", self.port))
        self.images = {
            service: command("docker", "image", "inspect", "--format", "{{.Id}}", image)
            for service, image in {
                "backend": self.env["BACKEND_IMAGE"],
                "frontend": self.env["MEASUREMENT_FRONTEND_IMAGE"],
                "postgres": "postgres:16",
            }.items()
        }

    def snapshot(self):
        ids = command(
            "docker",
            "ps",
            "-aq",
            "--filter",
            f"label=com.docker.compose.project={self.project}",
        ).splitlines()
        rows = {}
        for container in ids:
            row = json.loads(
                command(
                    "docker",
                    "inspect",
                    "--format",
                    '{"id":{{json .Id}},"image":{{json .Image}},'
                    '"state":{{json .State}},"labels":{{json .Config.Labels}},'
                    '"mounts":{{json .Mounts}},'
                    '"ports":{{json .NetworkSettings.Ports}}}',
                    container,
                )
            )
            service = row["labels"].get("com.docker.compose.service")
            if service not in SERVICES or service in rows:
                raise ValueError("Unexpected or duplicate measurement service.")
            if row["labels"].get("com.docker.compose.project") != self.project:
                raise ValueError("Container project changed.")
            expected_image = self.images["backend" if service == "migrate" else service]
            if row["image"] != expected_image:
                raise ValueError("Container image differs from preflight.")
            if (
                service == "backend"
                and row["labels"].get("org.traffic-monitoring.measurement")
                != "disposable"
            ):
                raise ValueError("Backend lacks measurement consent label.")
            mounts = []
            expected_volumes = {
                "postgres": {"/var/lib/postgresql/data": "postgres_data"},
                "backend": {
                    "/app/data/input": "uploads",
                    "/app/data/output": "outputs",
                },
            }.get(service, {})
            for mount in row["mounts"]:
                if mount["Type"] == "volume":
                    suffix = expected_volumes.get(mount["Destination"])
                    if not suffix or mount["Name"] != f"{self.project}_{suffix}":
                        raise ValueError("Unexpected shared volume.")
                    mounts.append(
                        {"name": mount["Name"], "destination": mount["Destination"]}
                    )
                elif not (
                    service == "backend"
                    and mount["Type"] == "bind"
                    and mount["Source"] == str(ROOT / "models")
                    and mount["Destination"] == "/app/models"
                    and not mount["RW"]
                ):
                    raise ValueError("Unexpected bind mount.")
            if {m["destination"] for m in mounts} != set(expected_volumes):
                raise ValueError("A required data volume is missing.")
            if service == "frontend" and row["ports"].get("8080/tcp") != [
                {"HostIp": "127.0.0.1", "HostPort": str(self.port)}
            ]:
                raise ValueError("Frontend is not bound to the selected loopback port.")
            state = row["state"]
            rows[service] = {
                "id": row["id"],
                "image": row["image"],
                "mounts": mounts,
                "running": state["Running"],
                "exit_code": state["ExitCode"],
                "started_at": state["StartedAt"],
                "health": state.get("Health", {}).get("Status"),
            }
        if set(rows) != SERVICES:
            raise ValueError("The complete measurement stack is required.")
        return rows


def probe(client, path, *, timeout):
    row = {"path": path, "started_at": utc_now(), "http_status": None}
    started = time.monotonic()
    try:
        response = client.get(path, timeout=timeout)
        row.update(
            http_status=response.status_code,
            request_id=response.headers.get("x-request-id"),
        )
        if path.startswith("/api/"):
            try:
                body = response.json()
                if isinstance(body, dict):
                    row["status"] = body.get("status")
                    row["checks"] = body.get("checks")
                    row["error_code"] = body.get("error", {}).get("code")
            except (ValueError, AttributeError):
                row["json_unavailable"] = True
        elif path == "/workspace":
            row["app_shell"] = 'id="root"' in response.text
    except httpx.HTTPError as error:
        row["failure_code"] = type(error).__name__
    row["seconds"] = time.monotonic() - started
    return row


def wait_ready(client, row, started, *, timeout, poll_interval):
    row["polls"] = []
    while True:
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("Readiness deadline exceeded.")
        poll = probe(client, "/api/ready", timeout=min(2, remaining))
        elapsed = time.monotonic() - started
        poll["elapsed_seconds"] = elapsed
        row["polls"].append(poll)
        if (
            poll["http_status"] == 200
            and poll.get("status") == "ready"
            and elapsed <= timeout
        ):
            row["ready_seconds"] = elapsed
            return
        time.sleep(min(poll_interval, max(0, timeout - elapsed)))


def require_healthy(snapshot):
    for service, row in snapshot.items():
        if service == "migrate":
            if row["running"] or row["exit_code"] != 0:
                raise ValueError("Migrations did not complete successfully.")
        elif not row["running"]:
            raise ValueError("A required service is stopped.")


def require_same_stack(actual, expected):
    if any(
        actual[name][key] != expected[name][key]
        for name in SERVICES
        for key in ("id", "image", "mounts", "running", "started_at")
    ):
        raise ValueError("Stack identity or process state changed.")


def measure_startup(stack, client, *, timeout, poll_interval):
    row = {"status": "failed", "started_at": utc_now(), "ready_seconds": None}
    started = time.monotonic()
    try:
        # Includes container/network/volume creation and first database initialization.
        stack.compose("up", "-d", "--no-build", "--pull", "never", timeout=timeout)
        row["command_seconds"] = time.monotonic() - started
        wait_ready(client, row, started, timeout=timeout, poll_interval=poll_interval)
        row["frontend"] = probe(client, "/workspace", timeout=5)
        if row["frontend"]["http_status"] != 200 or not row["frontend"].get(
            "app_shell"
        ):
            raise ValueError("Frontend shell is unavailable.")
        row["containers"] = stack.snapshot()
        require_healthy(row["containers"])
        row["status"] = "completed"
    except (Exception, KeyboardInterrupt) as error:
        row["failure_code"] = type(error).__name__
    row.update(elapsed_seconds=time.monotonic() - started, finished_at=utc_now())
    return row


def measure_outage(
    stack, client, service, expected, session_id, *, timeout, poll_interval
):
    if service not in {"postgres", "backend"}:
        raise ValueError("Only the measurement database or backend may be interrupted.")
    row = {
        "service": service,
        "status": "failed",
        "started_at": utc_now(),
        "ready_seconds": None,
    }
    restore = False
    started = time.monotonic()
    try:
        before = stack.snapshot()
        require_same_stack(before, expected)
        container = before[service]["id"]
        restore = True
        stop_started = time.monotonic()
        subprocess.run(
            ["docker", "stop", "--time", "40", container],
            capture_output=True,
            check=True,
            timeout=60,
        )
        row["stop_seconds"] = time.monotonic() - stop_started
        stopped = stack.snapshot()
        if stopped[service]["running"]:
            raise ValueError("Service did not stop.")
        row["outage_probes"] = [
            probe(client, path, timeout=10)
            for path in (
                "/healthz",
                "/workspace",
                "/api/health",
                "/api/ready",
                f"/api/analyses/{session_id}",
            )
        ]
        health, shell, api_health, ready, saved = row["outage_probes"]
        expected_codes = (
            [[200], [200], [200], [503], [500]]
            if service == "postgres"
            else [[200], [200], [502, 504], [502, 504], [502, 504]]
        )
        row["expected_http_statuses"] = expected_codes
        if any(
            p["http_status"] not in allowed
            for p, allowed in zip(row["outage_probes"], expected_codes, strict=True)
        ) or not shell.get("app_shell"):
            raise ValueError("Outage response differs from the declared expectation.")
        if service == "postgres" and (
            ready.get("status") != "not_ready"
            or ready.get("checks", {}).get("database", {}).get("status") != "not_ready"
            or saved.get("error_code") != "internal_error"
        ):
            raise ValueError(
                "Database outage response lacks expected safe error/readiness fields."
            )
        row["outage_verified"] = True
    except (Exception, KeyboardInterrupt) as error:
        row["failure_code"] = type(error).__name__
    finally:
        if restore:
            # Restoration is attempted even when a stop or observation failed.
            recovery_started = time.monotonic()
            row["recovery_started_at"] = utc_now()
            try:
                subprocess.run(
                    ["docker", "start", container],
                    capture_output=True,
                    check=True,
                    timeout=timeout,
                )
                row["start_command_seconds"] = time.monotonic() - recovery_started
                wait_ready(
                    client,
                    row,
                    recovery_started,
                    timeout=timeout,
                    poll_interval=poll_interval,
                )
                after = stack.snapshot()
                row["containers_after"] = after
                require_healthy(after)
                for name in SERVICES:
                    for key in ("id", "image", "mounts"):
                        if after[name][key] != before[name][key]:
                            raise ValueError(
                                "Container identity or mounts changed during recovery."
                            )
                    if (
                        name != service
                        and after[name]["started_at"] != before[name]["started_at"]
                    ):
                        raise ValueError("An unrelated service restarted.")
                if after[service]["started_at"] == before[service]["started_at"]:
                    raise ValueError("No new service start observed.")
                row["restoration_status"] = "completed"
                if not row.get("failure_code"):
                    row["status"] = "completed"
            except (Exception, KeyboardInterrupt) as error:
                row["restoration_status"] = "failed"
                row["restoration_failure_code"] = type(error).__name__
    row.update(elapsed_seconds=time.monotonic() - started, finished_at=utc_now())
    return row
