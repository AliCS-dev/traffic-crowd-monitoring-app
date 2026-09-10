from fastapi.testclient import TestClient

from app.api.application import create_app
from app.api.dependencies import ApplicationServices
from app.api.settings import ApiSettings


def create_test_client(*, session_lister):
    services = ApplicationServices(
        database_probe=lambda: True,
        detector_probe=lambda: True,
        detector_factory=lambda: object(),
        monitoring_session_lister=session_lister,
    )
    application = create_app(
        settings=ApiSettings(),
        service_factory=lambda: services,
    )
    return TestClient(application, raise_server_exceptions=False)


def session_page(*, page=1, page_size=20):
    return {
        "items": [
            {
                "id": 42,
                "session_name": "Morning junction",
                "source_type": "image",
                "original_filename": "junction.jpg",
                "status": "completed",
                "started_at": "2026-09-05T08:00:00Z",
                "completed_at": "2026-09-05T08:00:03Z",
            }
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": 1,
            "total_pages": 1,
        },
    }


def test_session_history_uses_default_pagination_and_returns_source_metadata():
    calls = []

    def session_lister(**pagination):
        calls.append(pagination)
        return session_page()

    with create_test_client(session_lister=session_lister) as client:
        response = client.get("/api/analyses")

    assert response.status_code == 200
    assert response.json() == session_page()
    assert calls == [{"page": 1, "page_size": 20}]


def test_session_history_forwards_custom_pagination():
    calls = []

    def session_lister(**pagination):
        calls.append(pagination)
        return session_page(**pagination)

    with create_test_client(session_lister=session_lister) as client:
        response = client.get("/api/analyses?page=3&page_size=10")

    assert response.status_code == 200
    assert response.json()["pagination"] == {
        "page": 3,
        "page_size": 10,
        "total_items": 1,
        "total_pages": 1,
    }
    assert calls == [{"page": 3, "page_size": 10}]


def test_session_history_rejects_invalid_pagination_before_database_access():
    calls = []

    def session_lister(**pagination):
        calls.append(pagination)
        return session_page(**pagination)

    with create_test_client(session_lister=session_lister) as client:
        invalid_page = client.get("/api/analyses?page=0")
        oversized_page = client.get("/api/analyses?page_size=101")
        malformed_page = client.get("/api/analyses?page=first")

    for response in (invalid_page, oversized_page, malformed_page):
        assert response.status_code == 422
        assert response.json() == {
            "error": {
                "code": "validation_error",
                "message": "The request contains invalid data.",
            }
        }
    assert calls == []


def test_session_history_failure_does_not_expose_database_details():
    def session_lister(**_pagination):
        raise RuntimeError("private database host and query details")

    with create_test_client(session_lister=session_lister) as client:
        response = client.get("/api/analyses")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected server error occurred.",
        }
    }
    assert "private database" not in response.text
