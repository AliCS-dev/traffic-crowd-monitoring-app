import json
import subprocess
from types import SimpleNamespace

import httpx
import pytest

import evaluation.system_restart as restart
import scripts.measure_system_restarts as script
from evaluation.system_measurement import Scenario

IDENTITY = {
    "id": "a" * 64,
    "image": "image",
    "source_sha256": "source",
    "started_at": "before",
    "running": True,
}
LABELS = {
    restart.MEASUREMENT_LABEL: "disposable",
    "com.docker.compose.service": "backend",
    "com.docker.compose.project": "isolated-test",
}


@pytest.mark.parametrize(
    "labels",
    [
        None,
        {},
        {**LABELS, restart.MEASUREMENT_LABEL: "demo"},
        {**LABELS, "com.docker.compose.service": "postgres"},
    ],
)
def test_restart_requires_explicit_disposable_backend_label(monkeypatch, labels):
    monkeypatch.setattr(restart, "command", lambda *a: json.dumps(labels))
    with pytest.raises(ValueError, match="disposable"):
        restart.require_disposable_backend("container")


@pytest.mark.parametrize(
    "problem",
    [
        None,
        "deadline",
        "not_ready",
        "same_start",
        "changed_image",
        "changed_before",
        "command_failure",
    ],
)
def test_restart_boundary_and_failures(monkeypatch, problem):
    now, commands, polls = [0.0], [], []
    monkeypatch.setattr(restart.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(restart.time, "sleep", lambda n: now.__setitem__(0, now[0] + n))
    monkeypatch.setattr(restart, "command", lambda *a: json.dumps(LABELS))
    after = {**IDENTITY, "started_at": "after"}
    if problem == "same_start":
        after = IDENTITY
    if problem == "changed_image":
        after = {**after, "image": "changed"}
    identities = iter(
        [
            {**IDENTITY, "id": "changed"} if problem == "changed_before" else IDENTITY,
            after,
        ]
    )
    monkeypatch.setattr(restart, "backend_identity", lambda _: next(identities))

    def run(arguments, **kwargs):
        commands.append(arguments)
        assert arguments == ["docker", "restart", "--time", "40", IDENTITY["id"]]
        assert kwargs["timeout"] == 3
        now[0] += 2
        if problem == "command_failure":
            raise subprocess.TimeoutExpired("private path", 3)

    monkeypatch.setattr(restart.subprocess, "run", run)

    def handle(request):
        assert request.url.path == "/api/ready"
        polls.append(True)
        if problem == "deadline" or len(polls) == 1:
            return httpx.Response(503, json={"status": "not_ready"})
        return httpx.Response(
            200, json={"status": "not_ready" if problem == "not_ready" else "ready"}
        )

    with httpx.Client(
        base_url="http://localhost", transport=httpx.MockTransport(handle)
    ) as client:
        row = restart.measure_restart(client, IDENTITY, timeout=3, poll_interval=0.25)
    assert row["status"] == ("completed" if problem is None else "failed")
    assert len(commands) == (0 if problem == "changed_before" else 1)
    assert "private path" not in json.dumps(row)
    if problem is None:
        assert row["command_seconds"] == 2
        assert row["ready_seconds"] == 2.25
        assert len(row["polls"]) == 2
    if problem in {"deadline", "not_ready"}:
        assert row["failure_code"] == "TimeoutError"
        assert row["ready_seconds"] is None


def saved_result():
    return {
        "id": 1,
        "status": "completed",
        "frames": [
            {
                "source_asset": {
                    "url": "/api/assets/11111111-1111-1111-1111-111111111111/source"
                },
                "visual_asset": {
                    "url": "/api/assets/11111111-1111-1111-1111-111111111111"
                },
            }
        ],
    }


@pytest.mark.parametrize(
    "problem",
    [
        None,
        "changed_media",
        "changed_result",
        "missing_asset",
        "external_asset",
        "null_result",
        "redirect",
        "no_frames",
    ],
)
def test_saved_result_checks_content_and_asset_hashes(monkeypatch, problem):
    changed, requested = [False], []

    def handle(request):
        requested.append(str(request.url))
        if request.url.path == "/api/analyses/1":
            result = saved_result()
            if changed[0]:
                if problem == "null_result":
                    return httpx.Response(200, content=b"null")
                if problem == "no_frames":
                    result["frames"] = []
                if problem == "changed_result":
                    result["notes"] = "changed"
                if problem == "external_asset":
                    result["frames"][0]["source_asset"]["url"] = (
                        "http://example.com/secret"
                    )
            return httpx.Response(200, json=result)
        if changed[0] and problem == "missing_asset":
            return httpx.Response(404)
        if changed[0] and problem == "redirect":
            return httpx.Response(
                302, headers={"location": "http://example.com/secret"}
            )
        return httpx.Response(
            200,
            content=b"\xff\xd8"
            + (
                b"changed" if changed[0] and problem == "changed_media" else b"original"
            ),
            headers={"content-type": "image/jpeg"},
        )

    with httpx.Client(
        base_url="http://localhost", transport=httpx.MockTransport(handle)
    ) as client:
        baseline = restart.saved_result_evidence(client, 1, timeout=2)
        assert len(baseline["assets"]) == 2
        changed[0] = True
        row = restart.measure_saved_recovery(client, baseline, timeout=2)
    assert row["status"] == ("completed" if problem is None else "failed")
    assert all(url.startswith("http://localhost/") for url in requested)


@pytest.mark.parametrize(
    "problem",
    [
        None,
        "restart",
        "request",
        "provenance",
        "recovery",
        "resources",
        "logs",
        "scenario_change",
        "tool_change",
        "backend_change",
    ],
)
def test_runner_preserves_evidence_and_stops_after_failure(
    tmp_path, monkeypatch, problem
):
    scenario = Scenario(
        scenario_id="I1", kind="image", path="unused.png", sha256="a" * 64
    )
    reads = []

    def scenarios(_):
        reads.append(True)
        return [
            scenario.model_copy(update={"sha256": "b" * 64})
            if problem == "scenario_change" and len(reads) > 1
            else scenario
        ]

    monkeypatch.setattr(script, "load_scenarios", scenarios)
    monkeypatch.setattr(script, "source_identity", lambda _: {"source_dirty": True})
    identity, order, stages, counter = dict(IDENTITY), [], [], [0]
    monkeypatch.setattr(
        script,
        "sha256",
        lambda _: "changed" if problem == "tool_change" and counter[0] > 2 else "hash",
    )
    monkeypatch.setattr(
        script,
        "backend_identity",
        lambda _: (
            {**identity, "started_at": "unexpected"}
            if problem == "backend_change" and counter[0] > 1
            else dict(identity)
        ),
    )
    monkeypatch.setattr(script, "require_disposable_backend", lambda _: "test")

    def request(client, scenario, *, phase, repetition, **_):
        counter[0] += 1
        request_id = f"r{counter[0]}"
        order.append(phase)
        for stage in ("inference", "image_persistence"):
            stages.append(
                {
                    "event": "stage_timing",
                    "stage": stage,
                    "stage_status": "completed",
                    "duration_seconds": 0.1,
                    "request_id": request_id,
                }
            )
        return {
            "scenario_id": "I1",
            "kind": "image",
            "phase": phase,
            "repetition": repetition,
            "request_id": request_id,
            "session_id": counter[0],
            "sampled_frames": 1,
            "status": "failed"
            if problem == "request" and phase == "cold_process"
            else "completed",
            "api_seconds": 1,
        }, None if problem == "provenance" and phase == "cold_process" else {
            "model_profile": {
                "profile_id": "same",
                "runtime_provenance": {
                    "container_id": "a" * 12,
                    "source_sha256": "source",
                },
            }
        }

    monkeypatch.setattr(script, "measure_request", request)

    def perform_restart(client, before, **_):
        order.append("restart")
        identity["started_at"] = f"start-{counter[0]}"
        return {
            "status": "failed" if problem == "restart" else "completed",
            "backend_after": dict(identity),
            "ready_seconds": 2,
        }

    monkeypatch.setattr(script, "measure_restart", perform_restart)
    monkeypatch.setattr(
        script, "saved_result_evidence", lambda *a, **k: {"session_id": 1}
    )

    def recover(*a, **k):
        order.append("recovery")
        return {
            "status": "failed" if problem == "recovery" else "completed",
            "seconds": 0.2,
        }

    monkeypatch.setattr(script, "measure_saved_recovery", recover)

    class Sampler:
        def __init__(self, *a, **k):
            self.samples = (
                [{"error": "OSError"}] if problem == "resources" else [{"value": 10}]
            )

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(script, "ResourceSampler", Sampler)
    client = httpx.Client(
        base_url="http://localhost",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"status": "ready"})
        ),
    )
    monkeypatch.setattr(script.httpx, "Client", lambda **_: client)
    monkeypatch.setattr(
        script.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            stdout=""
            if problem == "logs"
            else "\n".join(json.dumps(s) for s in stages),
            stderr="",
        ),
    )
    directory = tmp_path / "evidence"
    args = [
        "--base-url",
        "http://localhost",
        "--backend-container",
        "test",
        "--allow-backend-restart",
        "--repetitions",
        "2",
        "--output-directory",
        str(directory),
    ]
    code = script.main(args)
    report = json.loads((directory / "report.json").read_text())
    assert code == (0 if problem is None else 1)
    assert report["status"] == ("recorded" if problem is None else "incomplete")
    assert (directory / "restarts.csv").is_file()
    assert (directory / "sha256.json").is_file()
    if problem is None:
        assert order == [
            "recovery_seed",
            "restart",
            "cold_process",
            "recovery",
            "restart",
            "cold_process",
            "recovery",
        ]
        assert report["cold_summary"]["I1"]["attempted"] == 2
        assert report["cold_summary"]["I1"]["api_seconds"]["n"] == 2
        assert report["restart_summary"]["I1"]["completed"] == 2
    elif problem not in {"logs", "scenario_change", "tool_change"}:
        assert order.count("restart") == 1
        assert len(report["trials"]) == 1
        assert report["trials"][0]["status"] == "failed"
    with pytest.raises(SystemExit):
        script.main(args)


def test_runner_refuses_implicit_restart_consent(tmp_path):
    output = tmp_path / "report"
    with pytest.raises(SystemExit):
        script.main(
            [
                "--base-url",
                "http://localhost",
                "--backend-container",
                "demo",
                "--output-directory",
                str(output),
            ]
        )
    assert not output.exists()
