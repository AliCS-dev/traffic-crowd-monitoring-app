import logging
from collections.abc import Callable
from threading import Lock
from typing import Any

from fastapi import Request

from app.config import BASE_DIR
from app.database.connection import check_database_connection
from app.model_profile import (
    load_runtime_model_profile,
    verify_runtime_checkpoint,
)
from app.services.detection_service import ObjectDetector

DATABASE_READINESS_TIMEOUT_SECONDS = 3
LOGGER = logging.getLogger(__name__)


class ApplicationServices:
    def __init__(
        self,
        *,
        database_probe: Callable[[], bool],
        detector_probe: Callable[[], bool],
        detector_factory: Callable[[], Any],
    ) -> None:
        self._database_probe = database_probe
        self._detector_probe = detector_probe
        self._detector_factory = detector_factory
        self._detector: Any | None = None
        self._detector_lock = Lock()

    def readiness(self) -> dict[str, bool]:
        return {
            "database": self._run_probe("database", self._database_probe),
            "detector": self._run_probe("detector", self._detector_probe),
        }

    @staticmethod
    def _run_probe(name: str, probe: Callable[[], bool]) -> bool:
        try:
            return probe() is True
        except Exception:
            LOGGER.warning("Readiness probe failed: %s", name, exc_info=True)
            return False

    def get_detector(self) -> Any:
        if self._detector is not None:
            return self._detector
        with self._detector_lock:
            if self._detector is None:
                self._detector = self._detector_factory()
        return self._detector

    def close(self) -> None:
        self._detector = None


def create_application_services() -> ApplicationServices:
    profile = load_runtime_model_profile()

    def detector_probe() -> bool:
        verify_runtime_checkpoint(profile, BASE_DIR)
        return True

    return ApplicationServices(
        database_probe=lambda: check_database_connection(
            connect_timeout=DATABASE_READINESS_TIMEOUT_SECONDS
        ),
        detector_probe=detector_probe,
        detector_factory=lambda: ObjectDetector.from_runtime_profile(profile),
    )


def get_application_services(request: Request) -> ApplicationServices:
    return request.app.state.services


def get_detector(request: Request) -> Any:
    return get_application_services(request).get_detector()
