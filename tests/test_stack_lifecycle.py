import copy
import json
import subprocess

import httpx
import pytest

import evaluation.stack_lifecycle as lifecycle
import scripts.measure_stack_lifecycle as script
from evaluation.system_measurement import Scenario


def stack():
    instance = lifecycle.DisposableStack(
        "traffic-measure-test", 8086, "backend:test", "frontend:test", "secret"
    )
    instance.images = {s: s for s in ("backend", "frontend", "postgres")}
    return instance


def snapshot():
    return {
        s: {
            "id": s,
            "image": s,
            "mounts": [],
            "running": s != "migrate",
            "exit_code": 0,
            "started_at": "before",
            "health": "healthy",
        }
        for s in lifecycle.SERVICES
    }


@pytest.mark.parametrize(
    "project,port",
    [("demo", 8086), ("traffic-measure-", 8086), ("traffic-measure-test", 80)],
)
def test_project_and_port_are_restricted(project, port):
    with pytest.raises(ValueError):
        lifecycle.DisposableStack(project, port, "backend", "frontend", "secret")


def test_environment_does_not_inherit_application_overrides(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", "evidence")
    monkeypatch.setenv("COMPOSE_FILE", "unsafe.yml")
    monkeypatch.setenv("API_MAX_INFLIGHT_ANALYSES", "99")
    env = stack().env
    assert "POSTGRES_DB" not in env
    assert "COMPOSE_FILE" not in env
    assert "API_MAX_INFLIGHT_ANALYSES" not in env


@pytest.mark.parametrize("resource", ["ps", "volume", "network", "unlabelled_volume"])
def test_preflight_refuses_existing_resources(monkeypatch, resource):
    def command(*args):
        if resource == "unlabelled_volume" and "--format" in args:
            return "traffic-measure-test_postgres_data"
        return "existing" if args[1] == resource else ""

    monkeypatch.setattr(lifecycle, "command", command)
    with pytest.raises(ValueError, match="exists"):
        stack().preflight()


def container_rows():
    rows = {}
    for s in lifecycle.SERVICES:
        row = {
            "id": s,
            "image": "backend" if s == "migrate" else s,
            "state": {"Running": s != "migrate", "ExitCode": 0, "StartedAt": "before"},
            "labels": {
                "com.docker.compose.project": "traffic-measure-test",
                "com.docker.compose.service": s,
            },
            "mounts": [],
            "ports": {},
        }
        if s == "backend":
            row["labels"]["org.traffic-monitoring.measurement"] = "disposable"
            row["mounts"] = [
                {
                    "Type": "volume",
                    "Name": "traffic-measure-test_" + name,
                    "Destination": path,
                }
                for name, path in [
                    ("uploads", "/app/data/input"),
                    ("outputs", "/app/data/output"),
                ]
            ]
        if s == "postgres":
            row["mounts"] = [
                {
                    "Type": "volume",
                    "Name": "traffic-measure-test_postgres_data",
                    "Destination": "/var/lib/postgresql/data",
                }
            ]
        if s == "frontend":
            row["ports"] = {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8086"}]}
        rows[s] = row
    return rows


@pytest.mark.parametrize(
    "problem",
    [
        None,
        "image",
        "project",
        "label",
        "volume",
        "missing_volume",
        "bind",
        "port",
        "missing_service",
    ],
)
def test_snapshot_requires_owned_services_and_data(monkeypatch, problem):
    rows = container_rows()
    backend = rows["backend"]
    if problem == "image":
        backend["image"] = "changed"
    if problem == "project":
        backend["labels"]["com.docker.compose.project"] = "demo"
    if problem == "label":
        backend["labels"]["org.traffic-monitoring.measurement"] = "demo"
    if problem == "volume":
        backend["mounts"][0]["Name"] = "evidence_uploads"
    if problem == "missing_volume":
        backend["mounts"] = []
    if problem == "bind":
        backend["mounts"].append(
            {
                "Type": "bind",
                "Source": "/private",
                "Destination": "/app/models",
                "RW": True,
            }
        )
    if problem == "port":
        rows["frontend"]["ports"]["8080/tcp"][0]["HostIp"] = "0.0.0.0"
    if problem == "missing_service":
        del rows["migrate"]
    monkeypatch.setattr(
        lifecycle,
        "command",
        lambda *a: "\n".join(rows) if a[1] == "ps" else json.dumps(rows[a[-1]]),
    )
    if problem:
        with pytest.raises(ValueError):
            stack().snapshot()
    else:
        actual = stack().snapshot()
        assert set(actual) == lifecycle.SERVICES
        assert len(actual["backend"]["mounts"]) == 2
        assert "labels" not in actual["backend"]


@pytest.mark.parametrize("problem", [None, "deadline", "shell", "migration", "command"])
def test_startup_includes_compose_and_requires_frontend_and_migrations(
    monkeypatch, problem
):
    now, commands = [0.0], []
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(
        lifecycle.time, "sleep", lambda n: now.__setitem__(0, now[0] + n)
    )
    instance = stack()

    def compose(*args, **kwargs):
        commands.append(args)
        now[0] += 2
        if problem == "command":
            raise subprocess.TimeoutExpired("private", 3)

    monkeypatch.setattr(instance, "compose", compose)
    containers = snapshot()
    if problem == "migration":
        containers["migrate"]["exit_code"] = 1
    monkeypatch.setattr(instance, "snapshot", lambda: containers)

    def handle(request):
        if request.url.path == "/workspace":
            return httpx.Response(
                200, text="missing" if problem == "shell" else '<div id="root">'
            )
        return httpx.Response(
            503 if problem == "deadline" else 200, json={"status": "ready"}
        )

    with httpx.Client(
        base_url="http://localhost", transport=httpx.MockTransport(handle)
    ) as client:
        row = lifecycle.measure_startup(instance, client, timeout=3, poll_interval=0.25)
    assert row["status"] == ("completed" if problem is None else "failed")
    assert commands == [("up", "-d", "--no-build", "--pull", "never")]
    assert "private" not in json.dumps(row)
    if problem is None:
        assert row["command_seconds"] == row["ready_seconds"] == 2


@pytest.mark.parametrize("service", ["postgres", "backend"])
@pytest.mark.parametrize(
    "problem",
    [
        None,
        "changed_before",
        "stop",
        "unexpected_response",
        "restore",
        "changed_image",
        "changed_mount",
        "unrelated_restart",
        "same_start",
        "gateway_timeout",
    ],
)
def test_outage_restores_even_after_failure_and_retains_observations(
    monkeypatch, service, problem
):
    instance, before, commands = stack(), snapshot(), []
    current = copy.deepcopy(before)
    if problem == "changed_before":
        current["backend"]["id"] = "other"
    monkeypatch.setattr(instance, "snapshot", lambda: copy.deepcopy(current))

    def run(args, **kwargs):
        commands.append(args)
        assert args[-1] == service
        if args[1] == "stop":
            current[service]["running"] = False
            if problem == "stop":
                raise subprocess.TimeoutExpired("private", 60)
        else:
            if problem == "restore":
                raise subprocess.TimeoutExpired("private", 3)
            current[service]["running"] = True
            current[service]["started_at"] = (
                "before" if problem == "same_start" else "after"
            )
            if problem == "changed_image":
                current[service]["image"] = "other"
            if problem == "changed_mount":
                current[service]["mounts"] = ["other"]
            if problem == "unrelated_restart":
                current["frontend"]["started_at"] = "after"

    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    def handle(request):
        path = request.url.path
        if current[service]["running"]:
            return httpx.Response(200, json={"status": "ready"})
        if path == "/workspace":
            return httpx.Response(200, text='<div id="root">')
        if path == "/healthz":
            return httpx.Response(200)
        if service == "backend":
            return httpx.Response(
                200
                if problem == "unexpected_response"
                else 504
                if problem == "gateway_timeout"
                else 502
            )
        if path == "/api/health":
            return httpx.Response(200)
        if path == "/api/ready":
            return httpx.Response(
                200 if problem == "unexpected_response" else 503,
                json={
                    "status": "not_ready",
                    "checks": {"database": {"status": "not_ready"}},
                },
            )
        return httpx.Response(500, json={"error": {"code": "internal_error"}})

    with httpx.Client(
        base_url="http://localhost", transport=httpx.MockTransport(handle)
    ) as client:
        row = lifecycle.measure_outage(
            instance, client, service, before, 1, timeout=3, poll_interval=0.25
        )
    assert row["status"] == (
        "completed" if problem in {None, "gateway_timeout"} else "failed"
    )
    assert "private" not in json.dumps(row)
    if problem == "changed_before":
        assert commands == []
    else:
        assert [c[1] for c in commands] == ["stop", "start"]
        assert row["restoration_status"] == (
            "failed"
            if problem
            in {
                "restore",
                "changed_image",
                "changed_mount",
                "unrelated_restart",
                "same_start",
            }
            else "completed"
        )
    if problem is None:
        assert len(row["outage_probes"]) == 5
        assert row["outage_verified"] is True


@pytest.mark.parametrize(
    "problem", [None, "startup", "outage", "saved", "request", "provenance"]
)
@pytest.mark.parametrize("custom_scenarios", [False, True])
def test_runner_retains_partial_results_without_retries(
    tmp_path, monkeypatch, problem, custom_scenarios
):
    instance = stack()
    monkeypatch.setattr(script, "DisposableStack", lambda *a: instance)
    monkeypatch.setattr(instance, "preflight", lambda: None)
    monkeypatch.setattr(instance, "snapshot", snapshot)
    monkeypatch.setattr(script, "source_identity", lambda _: {"source_dirty": True})
    monkeypatch.setattr(script, "sha256", lambda _: "hash")
    scenarios = [
        Scenario(scenario_id="I1", kind="image", path="test.png", sha256="a" * 64)
    ]
    loaded_paths = []

    def load(path):
        loaded_paths.append(path)
        return scenarios

    monkeypatch.setattr(script, "load_scenarios", load)
    monkeypatch.setattr(
        script,
        "measure_startup",
        lambda *a, **k: {
            "status": "failed" if problem == "startup" else "completed",
            "containers": snapshot(),
        },
    )
    monkeypatch.setattr(script, "backend_identity", lambda _: {"id": "backend"})
    requests, outages = [], []

    def request(*args, phase, **kwargs):
        requests.append(phase)
        return {
            "status": "failed"
            if problem == "request" and len(requests) > 1
            else "completed",
            "session_id": len(requests),
        }, {}

    def identity(*args):
        if problem == "provenance" and len(requests) > 1:
            raise ValueError("mismatch")
        return {}, {}

    monkeypatch.setattr(script, "check_result_identity", identity)
    monkeypatch.setattr(script, "measure_request", request)
    monkeypatch.setattr(
        script, "saved_result_evidence", lambda c, s, **k: {"session_id": s}
    )
    monkeypatch.setattr(
        script,
        "measure_saved_recovery",
        lambda *a, **k: {"status": "failed" if problem == "saved" else "completed"},
    )

    def outage(stack, client, service, *a, **k):
        outages.append(service)
        return {
            "status": "failed" if problem == "outage" else "completed",
            "service": service,
            "containers_after": snapshot(),
        }

    monkeypatch.setattr(script, "measure_outage", outage)
    directory = tmp_path / "report"
    args = [
        "--project",
        "traffic-measure-test",
        "--backend-image",
        "b",
        "--frontend-image",
        "f",
        "--allow-stack-interruption",
        "--output-directory",
        str(directory),
    ]
    scenario_file = script.ROOT / "configs/evaluation/system_workflows.json"
    if custom_scenarios:
        scenario_file = (
            script.ROOT / "configs/evaluation/system_workflows_candidate.json"
        )
        args.extend(["--scenarios", str(scenario_file)])
    assert script.main(args) == (0 if problem is None else 1)
    assert loaded_paths == [scenario_file] * (2 if problem is None else 1)
    report = json.loads((directory / "report.json").read_text())
    assert str(scenario_file.relative_to(script.ROOT)) in report["tool_sha256"]
    assert report["status"] == ("recorded" if problem is None else "incomplete")
    assert (directory / "lifecycle.csv").exists()
    assert (directory / "sha256.json").exists()
    assert len(outages) == (0 if problem == "startup" else 2 if problem is None else 1)
    if problem in {"request", "provenance"}:
        assert len(requests) == 2
        assert report["outages"][0]["status"] == "failed"
    with pytest.raises(SystemExit):
        script.main(args)


def test_runner_requires_interruption_consent(tmp_path):
    directory = tmp_path / "no-output"
    with pytest.raises(SystemExit):
        script.main(
            [
                "--project",
                "traffic-measure-test",
                "--backend-image",
                "b",
                "--frontend-image",
                "f",
                "--output-directory",
                str(directory),
            ]
        )
    assert not directory.exists()


def test_runner_rejects_external_scenario_config_before_touching_stack(
    tmp_path, monkeypatch
):
    instance = stack()
    monkeypatch.setattr(script, "DisposableStack", lambda *args: instance)

    def unexpected_preflight():
        pytest.fail("External configuration must be rejected before Docker access")

    monkeypatch.setattr(instance, "preflight", unexpected_preflight)
    directory = tmp_path / "external-config"
    with pytest.raises(SystemExit):
        script.main(
            [
                "--project",
                "traffic-measure-test",
                "--backend-image",
                "b",
                "--frontend-image",
                "f",
                "--allow-stack-interruption",
                "--scenarios",
                str(tmp_path / "scenarios.json"),
                "--output-directory",
                str(directory),
            ]
        )
    assert not directory.exists()
