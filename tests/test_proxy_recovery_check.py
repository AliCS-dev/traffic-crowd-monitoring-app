"""Failure semantics of the opt-in Docker check; these tests need no Docker."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

SPEC = importlib.util.spec_from_file_location(
    "proxy_check", Path(__file__).parent / "compose" / "check_proxy_recovery.py"
)
proxy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proxy)


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(proxy.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(proxy.time, "sleep", lambda n: now.__setitem__(0, now[0] + n))
    return now


def test_readiness_polling_stops_at_first_ready(monkeypatch, clock):
    request = Mock(side_effect=[(502, b"bad gateway"), (200, b'{"status":"ready"}')])
    monkeypatch.setattr(proxy, "request", request)
    assert proxy.wait_ready(Mock()) == [502, 200]
    assert request.call_count == 2


def test_readiness_timeout_is_bounded(monkeypatch, clock):
    monkeypatch.setattr(proxy, "request", Mock(return_value=(502, b"bad gateway")))
    with pytest.raises(AssertionError, match="No ready response"):
        proxy.wait_ready(Mock())
    assert 45 <= clock[0] < 46


def test_post_ready_failure_is_not_retried(monkeypatch, clock):
    request = Mock(side_effect=[(200, b'{"status":"ready"}'), (502, b"failed")])
    monkeypatch.setattr(proxy, "request", request)
    monkeypatch.setattr(proxy.http.client, "HTTPConnection", Mock())
    record = {}
    with pytest.raises(AssertionError):
        proxy.observe(Mock(), 1234, record)
    assert request.call_count == 2
    assert record["failure"] == {"status": 502, "seconds_after_ready": 0.1}


def test_observation_covers_multiple_dns_lifetimes(monkeypatch, clock):
    request = Mock(return_value=(200, b'{"status":"ready"}'))
    monkeypatch.setattr(proxy, "request", request)
    monkeypatch.setattr(proxy.http.client, "HTTPConnection", Mock())
    record = {}
    proxy.observe(Mock(), 1234, record)
    assert record["observed_seconds"] >= 12
    assert record["post_ready_requests"] >= 120


def test_network_error_after_readiness_is_not_retried(monkeypatch, clock):
    request = Mock(side_effect=ConnectionResetError("connection lost"))
    monkeypatch.setattr(proxy, "request", request)
    monkeypatch.setattr(proxy.http.client, "HTTPConnection", Mock())
    with pytest.raises(ConnectionResetError):
        proxy.observe(Mock(), 1234, {})
    assert request.call_count == 1
