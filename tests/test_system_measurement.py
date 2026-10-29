import json
from types import SimpleNamespace

import httpx
import pytest

import evaluation.system_measurement as measurement
import scripts.measure_system_workflows as script
from evaluation.system_measurement import (
    Scenario,
    attach_stage_records,
    check_result_identity,
    load_scenarios,
    measure_request,
    sha256,
    statistics_record,
    summarize,
    validate_local_url,
)


@pytest.fixture
def scenario(tmp_path):
    media = tmp_path / "image.png"
    media.write_bytes(b"fixture")
    return Scenario(
        scenario_id="I1", kind="image", path=media.name, sha256=sha256(media)
    )


def test_scenarios_verify_hashes_options_and_unique_ids(tmp_path, scenario):
    config = tmp_path / "scenarios.json"
    config.write_text(json.dumps([scenario.model_dump()]))
    assert load_scenarios(config, root=tmp_path) == [scenario]
    (tmp_path / scenario.path).write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        load_scenarios(config, root=tmp_path)
    config.write_text(json.dumps([scenario.model_dump()] * 2))
    with pytest.raises(ValueError, match="unique"):
        load_scenarios(config, root=tmp_path)
    config.write_text(json.dumps([{**scenario.model_dump(), "grid_rows": 2}]))
    with pytest.raises(ValueError, match="Both grid"):
        load_scenarios(config, root=tmp_path)


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost",
        "http://example.com",
        "http://user:password@localhost",
        "http://localhost/api",
        "http://localhost?token=x",
    ],
)
def test_runner_rejects_nonlocal_or_secret_bearing_origins(url):
    with pytest.raises(ValueError):
        validate_local_url(url)


@pytest.mark.parametrize(
    "url", ["http://localhost:8083", "http://127.0.0.1", "http://[::1]:8080"]
)
def test_runner_accepts_local_origins(url):
    validate_local_url(url)


def test_image_boundary_excludes_result_read(tmp_path, scenario, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(measurement.time, "monotonic", lambda: now[0])

    def handle(request):
        if request.method == "POST":
            now[0] += 2
            assert b"system-I1-measured-1" in request.content
            return httpx.Response(
                201, json={"session_id": 8}, headers={"x-request-id": "request-8"}
            )
        now[0] += 10
        return httpx.Response(200, json={"id": 8})

    with httpx.Client(
        base_url="http://localhost", transport=httpx.MockTransport(handle)
    ) as client:
        row, result = measure_request(
            client,
            scenario,
            phase="measured",
            repetition=1,
            timeout=10,
            poll_interval=0.25,
            root=tmp_path,
        )
    assert row["status"] == "completed"
    assert row["api_seconds"] == 2
    assert row["request_id"] == "request-8"
    assert result == {"id": 8}


@pytest.mark.parametrize("status", ["completed", "failed", "processing"])
def test_video_polls_retains_failures_and_deadline(
    tmp_path, scenario, monkeypatch, status
):
    scenario = scenario.model_copy(update={"kind": "video"})
    now = [0.0]
    monkeypatch.setattr(measurement.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(
        measurement.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds)
    )

    def handle(request):
        if request.method == "POST":
            return httpx.Response(
                202, json={"session_id": 9}, headers={"x-request-id": "r"}
            )
        if "/videos/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "status": status,
                    "sampled_frames_processed": 3,
                    "failure_code": "video_limit_exceeded",
                },
            )
        return httpx.Response(200, json={"id": 9})

    with httpx.Client(
        base_url="http://localhost", transport=httpx.MockTransport(handle)
    ) as client:
        row, _ = measure_request(
            client,
            scenario,
            phase="measured",
            repetition=1,
            timeout=0.5,
            poll_interval=0.25,
            root=tmp_path,
        )
    assert row["request_id"] == "r"
    assert row["session_id"] == 9
    assert row["status"] == ("completed" if status == "completed" else "failed")
    if status == "processing":
        assert row["failure_code"] == "TimeoutError"
        assert row["api_seconds"] == 0.5
    elif status == "failed":
        assert row["failure_code"] == "video_limit_exceeded"


def test_http_failure_retains_request_id_without_credentials(tmp_path, scenario):
    def handle(_):
        return httpx.Response(
            500, text="private credentials", headers={"x-request-id": "failed"}
        )

    with httpx.Client(
        base_url="http://localhost", transport=httpx.MockTransport(handle)
    ) as client:
        row, result = measure_request(
            client,
            scenario,
            phase="measured",
            repetition=1,
            timeout=1,
            poll_interval=0.25,
            root=tmp_path,
        )
    assert result is None
    assert row["status"] == "failed"
    assert row["request_id"] == "failed"
    assert row["http_status"] == 500
    assert "private" not in json.dumps(row)


def record(stage, seconds, request_id="r", status="completed"):
    return {
        "event": "stage_timing",
        "request_id": request_id,
        "stage": stage,
        "duration_seconds": seconds,
        "stage_status": status,
    }


def test_logs_correlate_all_video_frames_and_detect_missing_or_duplicate_evidence():
    row = {"request_id": "r", "kind": "video", "sampled_frames": 2}
    records = [
        record("inference", 1),
        record("inference", 2),
        record("video_queue", 0.1),
        record("video_persistence", 0.4),
        record("inference", 999, "unrelated"),
    ]
    text = "not json\n" + "\n".join(json.dumps(item) for item in records)
    attach_stage_records([row], text)
    assert row["stage_seconds"]["inference"] == 3
    assert row["stage_evidence_complete"] is True
    attach_stage_records(
        [row], text + "\n" + json.dumps(record("video_persistence", 4))
    )
    assert row["stage_evidence_complete"] is False
    assert row["stage_seconds"]["video_persistence"] is None
    attach_stage_records([row], "")
    assert all(value is None for value in row["stage_seconds"].values())


@pytest.mark.parametrize("duration", [-1, float("nan"), True, "1"])
def test_invalid_stage_durations_are_unavailable(duration):
    row = {"request_id": "r", "kind": "image", "sampled_frames": 1}
    attach_stage_records([row], json.dumps(record("inference", duration)))
    assert row["stage_seconds"]["inference"] is None


def test_provenance_mismatch_and_profile_changes_fail():
    expected = {"id": "a" * 64, "source_sha256": "source"}
    profile = {
        "profile_id": "fixed",
        "runtime_provenance": {"container_id": "a" * 12, "source_sha256": "source"},
        "created_at": "now",
    }
    clean, _ = check_result_identity({"model_profile": profile}, expected, None)
    assert clean == {"profile_id": "fixed"}
    with pytest.raises(ValueError):
        check_result_identity(
            {"model_profile": profile}, {**expected, "id": "b" * 64}, None
        )
    with pytest.raises(ValueError):
        check_result_identity(
            {"model_profile": profile}, expected, {"profile_id": "changed"}
        )


def test_statistics_exclude_warmups_keep_failed_denominator_and_nearest_rank_p95():
    rows = [
        {
            "scenario_id": "I1",
            "phase": "measured",
            "status": "completed",
            "api_seconds": float(index),
        }
        for index in range(1, 11)
    ]
    rows += [
        {
            "scenario_id": "I1",
            "phase": "measured",
            "status": "failed",
            "api_seconds": 90,
        },
        {
            "scenario_id": "I1",
            "phase": "warmup",
            "status": "completed",
            "api_seconds": 99,
        },
    ]
    result = summarize(rows)["I1"]
    assert result["attempted"] == 11
    assert result["failed"] == 1
    assert result["api_seconds"] == {
        "n": 10,
        "median": 5.5,
        "min": 1,
        "max": 10,
        "p95": 10,
    }
    assert result["complete_evidence"] == 0
    assert statistics_record([])["median"] is None


def test_resource_sampler_keeps_failed_readings(monkeypatch):
    sampler = measurement.ResourceSampler("backend")

    def unavailable(*_):
        sampler.stop.set()
        raise OSError("sensitive details")

    monkeypatch.setattr(measurement, "command", unavailable)
    with sampler:
        sampler.thread.join()
    assert len(sampler.samples) == 2
    assert all(
        row["value"] is None and row["error"] == "OSError" for row in sampler.samples
    )
    assert "sensitive" not in json.dumps(sampler.samples)


def test_command_persists_partial_run_and_does_not_retry(
    tmp_path, scenario, monkeypatch
):
    from functools import partial

    monkeypatch.setattr(
        script, "measure_request", partial(measure_request, root=tmp_path)
    )
    monkeypatch.setattr(script, "load_scenarios", lambda _: [scenario])
    monkeypatch.setattr(script, "backend_identity", lambda _: {"id": "a" * 64})
    monkeypatch.setattr(script, "source_identity", lambda _: {})
    monkeypatch.setattr(script, "sha256", lambda _: "hash")

    class Sampler:
        samples = []

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(script, "ResourceSampler", Sampler)
    requests = []

    def handle(request):
        requests.append(request.url.path)
        if request.method == "POST":
            return httpx.Response(500, headers={"x-request-id": "failed"})
        return httpx.Response(200, json={})

    client = httpx.Client(
        base_url="http://localhost", transport=httpx.MockTransport(handle)
    )
    monkeypatch.setattr(script.httpx, "Client", lambda **_: client)
    monkeypatch.setattr(
        script.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="", stderr="")
    )
    output = tmp_path / "report"
    assert (
        script.main(["--backend-container", "test", "--output-directory", str(output)])
        == 1
    )
    report = json.loads((output / "report.json").read_text())
    assert report["status"] == "incomplete"
    assert len(report["requests"]) == 1
    assert requests.count("/api/analyses/images") == 1
    assert (output / "requests.csv").is_file()
    assert (output / "sha256.json").is_file()
    with pytest.raises(SystemExit):
        script.main(["--backend-container", "test", "--output-directory", str(output)])


@pytest.mark.parametrize("problem", [None, "missing_logs", "mismatch", "resources"])
def test_command_success_requires_correlated_evidence(
    tmp_path, scenario, monkeypatch, problem
):
    from functools import partial

    identity = {"id": "a" * 64, "source_sha256": "source"}
    monkeypatch.setattr(
        script, "measure_request", partial(measure_request, root=tmp_path)
    )
    monkeypatch.setattr(script, "load_scenarios", lambda _: [scenario])
    monkeypatch.setattr(script, "backend_identity", lambda _: identity)
    monkeypatch.setattr(script, "source_identity", lambda _: {})
    monkeypatch.setattr(script, "sha256", lambda _: "hash")

    class Sampler:
        samples = [{"resource": "backend_cgroup_mib", "value": 100}]

        def __init__(self, *a, **k):
            if problem == "resources":
                self.samples = [{"value": None, "error": "OSError"}]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(script, "ResourceSampler", Sampler)
    records = []
    submissions = []

    def handle(request):
        if request.method == "POST":
            submissions.append(request)
            request_id = f"r{len(submissions)}"
            records.extend(
                [
                    record("inference", 0.1, request_id),
                    record("image_persistence", 0.02, request_id),
                ]
            )
            return httpx.Response(
                201,
                json={"session_id": len(submissions)},
                headers={"x-request-id": request_id},
            )
        if request.url.path.startswith("/api/analyses/"):
            return httpx.Response(
                200,
                json={
                    "model_profile": {
                        "profile_id": "fixed",
                        "created_at": "now",
                        "runtime_provenance": {
                            "container_id": "a" * 12,
                            "source_sha256": "other"
                            if problem == "mismatch"
                            else "source",
                        },
                    }
                },
            )
        return httpx.Response(200, json={})

    client = httpx.Client(
        base_url="http://localhost", transport=httpx.MockTransport(handle)
    )
    monkeypatch.setattr(script.httpx, "Client", lambda **_: client)
    monkeypatch.setattr(
        script.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            stdout="",
            stderr=""
            if problem == "missing_logs"
            else "\n".join(json.dumps(row) for row in records),
        ),
    )
    output = tmp_path / "complete"
    code = script.main(
        [
            "--backend-container",
            "test",
            "--repetitions",
            "2",
            "--output-directory",
            str(output),
        ]
    )
    report = json.loads((output / "report.json").read_text())
    assert code == (0 if problem is None else 1)
    assert report["status"] == ("recorded" if problem is None else "incomplete")
    if problem != "mismatch":
        assert len(submissions) == 3
        assert report["summary"]["I1"]["attempted"] == 2
        assert report["batches"][0]["completed_sampled_frames"] == 2
    else:
        assert len(submissions) == 1
        assert report["requests"][0]["evidence_error"] == "backend_or_profile_mismatch"


def test_backend_preflight_refuses_stale_image(monkeypatch):
    values = iter([json.dumps({"id": "a" * 64, "running": True}), "old-source"])
    monkeypatch.setattr(measurement, "command", lambda *a: next(values))
    monkeypatch.setattr(measurement, "source_digest", lambda _: "new-source")
    with pytest.raises(ValueError, match="source tree"):
        measurement.backend_identity("backend")


def test_interrupted_request_is_retained(tmp_path, scenario):
    def interrupt(_):
        raise KeyboardInterrupt

    with httpx.Client(
        base_url="http://localhost", transport=httpx.MockTransport(interrupt)
    ) as client:
        row, result = measure_request(
            client,
            scenario,
            phase="measured",
            repetition=1,
            timeout=1,
            poll_interval=0.25,
            root=tmp_path,
        )
    assert row["status"] == "failed"
    assert row["failure_code"] == "KeyboardInterrupt"
    assert result is None
