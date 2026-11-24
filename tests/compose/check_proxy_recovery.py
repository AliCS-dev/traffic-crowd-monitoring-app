"""Opt-in Docker regression: fail on any API error after the first ready response.

Uses a new network and disposable containers, no database, GPU or model. The
real image/video/storage checks remain in check_workflows.py.
"""

import argparse
import hashlib
import http.client
import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

RESTARTS = 10
OBSERVE_SECONDS = 12  # More than two five-second DNS cache lifetimes.


def docker(*args):
    return subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True, timeout=90
    ).stdout.strip()


def request(connection, path, body=None):
    connection.request("GET" if body is None else "POST", path, body=body)
    response = connection.getresponse()
    content = response.read()
    return response.status, content


def wait_ready(connection):
    deadline = time.monotonic() + 45
    observations = []
    while time.monotonic() < deadline:
        try:
            status, body = request(connection, "/api/ready")
        except (OSError, http.client.HTTPException):
            connection.close()
            status, body = 0, b""
        observations.append(status)
        if status == 200 and json.loads(body)["status"] == "ready":
            return observations
        time.sleep(0.1)
    raise AssertionError(f"No ready response within 45 seconds: {observations}")


def observe(connection, port, record):
    started = time.monotonic()
    record["post_ready_requests"] = 0
    # Alternate a persistent client and new connections to exercise worker caches.
    while time.monotonic() - started < OBSERVE_SECONDS:
        fresh = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        client = connection if record["post_ready_requests"] % 2 == 0 else fresh
        try:
            status, body = request(client, "/api/ready")
            record["post_ready_requests"] += 1
            if status != 200:
                record["failure"] = {
                    "status": status,
                    "seconds_after_ready": time.monotonic() - started,
                }
            assert status == 200, record
            assert json.loads(body)["status"] == "ready"
        finally:
            fresh.close()
        time.sleep(0.1)
    record["observed_seconds"] = time.monotonic() - started


def check_forwarding(connection):
    path = "/api/echo/vehicle%20frame?name=a%2Fb&value=1&value=2"
    status, response = request(connection, path)
    assert status == 200 and json.loads(response)["path"] == path
    body = bytes(range(256)) * 4096
    status, response = request(connection, path, body)
    result = json.loads(response)
    assert status == 200 and result["path"] == path
    assert result["bytes"] == len(body)
    assert result["sha256"] == hashlib.sha256(body).hexdigest()
    assert result["submissions"] == 1
    status, _ = request(connection, "/api/disconnect", b"accepted-once")
    assert status == 502, "A lost upstream response must remain visible."
    status, response = request(connection, "/api/ready")
    assert status == 200 and json.loads(response)["submissions"] == 2
    return {"path_and_query": True, "upload_bytes": len(body), "post_replay": False}


def run(args, report):
    prefix = f"traffic-proxy-test-{uuid.uuid4().hex[:12]}"
    backend, frontend, holder = (f"{prefix}-{name}" for name in ("api", "web", "hold"))
    created = []
    network_created = False
    connection = None
    fixture = Path(__file__).with_name("proxy_backend.py").resolve()
    report.update({"project": prefix, "trials": [], "status": "running"})
    report["test_sha256"] = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(__file__), fixture)
    }

    def start_container(name, *options):
        docker("create", "--name", name, "--network", prefix, *options)
        created.append(name)
        docker("start", name)

    def start_backend():
        start_container(
            backend,
            "--network-alias",
            "backend",
            "--mount",
            f"type=bind,src={fixture},dst=/qa/proxy_backend.py,readonly",
            "--entrypoint",
            "python",
            args.backend_image,
            "/qa/proxy_backend.py",
        )

    def address():
        info = json.loads(docker("inspect", backend))[0]
        return info["NetworkSettings"]["Networks"][prefix]["IPAddress"]

    try:
        report["images"] = {
            name: docker("image", "inspect", tag, "--format", "{{.Id}}")
            for name, tag in (
                ("backend", args.backend_image),
                ("frontend", args.frontend_image),
            )
        }
        docker("network", "create", prefix)
        network_created = True
        start_backend()
        start_container(
            frontend,
            "-p",
            "127.0.0.1::8080",
            args.frontend_image,
        )
        info = json.loads(docker("inspect", frontend))[0]
        port = int(info["NetworkSettings"]["Ports"]["8080/tcp"][0]["HostPort"])
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        config = docker("exec", frontend, "cat", "/etc/nginx/nginx.conf") + "\n"
        report["nginx_config_sha256"] = hashlib.sha256(config.encode()).hexdigest()
        for trial in range(RESTARTS + 2):
            record = {"kind": "startup" if trial == 0 else "restart", "index": trial}
            report["trials"].append(record)
            if 0 < trial <= RESTARTS:
                docker("stop", "-t", "0", backend)
                # Vary downtime relative to the resolver timer without hiding failures.
                record["stopped_seconds"] = (trial % 3) * 0.5
                time.sleep(record["stopped_seconds"])
                docker("start", backend)
            elif trial > RESTARTS:
                record["kind"] = "recreate_changed_address"
                record["old_address"] = address()
                docker("rm", "-f", backend)
                created.remove(backend)
                # Occupy the released address so recreation cannot silently reuse it.
                start_container(
                    holder,
                    "--ip",
                    record["old_address"],
                    "--entrypoint",
                    "python",
                    args.backend_image,
                    "-c",
                    "import time; time.sleep(300)",
                )
                start_backend()
                record["new_address"] = address()
                assert record["old_address"] != record["new_address"]
            record["recovery_statuses"] = wait_ready(connection)
            observe(connection, port, record)
            record["forwarding"] = check_forwarding(connection)
            print(json.dumps(record), flush=True)
        report["status"] = "passed"
    finally:
        if connection is not None:
            connection.close()
        for name in reversed(created):
            logs = subprocess.run(
                ["docker", "logs", "--timestamps", name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            (args.output / f"{name}.log").write_text(logs.stdout + logs.stderr)
            docker("rm", "-f", name)
        if network_created:
            docker("network", "rm", prefix)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-image", required=True)
    parser.add_argument("--frontend-image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"started_at": datetime.now(timezone.utc).isoformat()}
    try:
        run(args, report)
    except Exception as exc:
        report.update({"status": "failed", "error": str(exc)})
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
