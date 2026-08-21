import logging
from collections.abc import Callable
from threading import Lock
from typing import Any

from fastapi import Request

from app.api.settings import ApiSettings
from app.config import BASE_DIR
from app.crowd_analysis import load_dense_crowd_analysis_decision
from app.database.connection import check_database_connection
from app.database.monitoring_query_repository import get_monitoring_session
from app.database.video_job_repository import recover_interrupted_video_jobs
from app.model_profile import (
    load_runtime_model_profile,
    verify_runtime_checkpoint,
)
from app.services.alert_service import load_threshold_alert_rules
from app.services.detection_service import ObjectDetector
from app.services.image_analysis_service import ImageAnalysisService
from app.services.image_upload_service import ImageUploadPolicy
from app.services.output_asset_service import OutputAssetService
from app.services.video_analysis_service import VideoAnalysisService
from app.services.video_upload_service import VideoUploadPolicy

DATABASE_READINESS_TIMEOUT_SECONDS = 3
LOGGER = logging.getLogger(__name__)


class ApplicationServices:
    def __init__(
        self,
        *,
        database_probe: Callable[[], bool],
        detector_probe: Callable[[], bool],
        detector_factory: Callable[[], Any],
        image_analysis_factory: Callable[[Any], Any] | None = None,
        video_analysis_factory: Callable[[Callable], Any] | None = None,
        output_asset_factory: Callable[[], Any] | None = None,
        monitoring_session_reader: Callable[[int], Any] = get_monitoring_session,
        startup_function: Callable[[], int] | None = None,
    ) -> None:
        self._database_probe = database_probe
        self._detector_probe = detector_probe
        self._detector_factory = detector_factory
        self._image_analysis_factory = image_analysis_factory
        self._video_analysis_factory = video_analysis_factory
        self._output_asset_factory = output_asset_factory
        self._monitoring_session_reader = monitoring_session_reader
        self._startup_function = startup_function
        self._detector: Any | None = None
        self._image_analysis_service: Any | None = None
        self._video_analysis_service: Any | None = None
        self._output_asset_service: Any | None = None
        self._detector_lock = Lock()
        self._service_lock = Lock()

    def start(self) -> None:
        if self._startup_function is None:
            return
        recovered = self._startup_function()
        if recovered:
            LOGGER.warning("Marked %s interrupted video job(s) as failed", recovered)

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

    def get_image_analysis_service(self) -> Any:
        if self._image_analysis_factory is None:
            raise RuntimeError("Image analysis service is not configured.")
        if self._image_analysis_service is None:
            with self._detector_lock:
                if self._image_analysis_service is None:
                    detector = self._detector
                    if detector is None:
                        detector = self._detector_factory()
                        self._detector = detector
                    self._image_analysis_service = self._image_analysis_factory(
                        detector
                    )
        return self._image_analysis_service

    def get_monitoring_session(self, session_id: int) -> Any:
        return self._monitoring_session_reader(session_id)

    def get_video_analysis_service(self) -> Any:
        if self._video_analysis_factory is None:
            raise RuntimeError("Video analysis service is not configured.")
        if self._video_analysis_service is None:
            with self._service_lock:
                if self._video_analysis_service is None:
                    self._video_analysis_service = self._video_analysis_factory(
                        self.get_detector
                    )
        return self._video_analysis_service

    def get_output_asset_service(self) -> Any:
        if self._output_asset_factory is None:
            raise RuntimeError("Output asset service is not configured.")
        if self._output_asset_service is None:
            with self._service_lock:
                if self._output_asset_service is None:
                    self._output_asset_service = self._output_asset_factory()
        return self._output_asset_service

    def close(self) -> None:
        if self._video_analysis_service is not None:
            self._video_analysis_service.close()
        self._video_analysis_service = None
        self._output_asset_service = None
        self._image_analysis_service = None
        self._detector = None


def create_application_services(
    settings: ApiSettings | None = None,
) -> ApplicationServices:
    settings = settings or ApiSettings.from_environment()
    profile = load_runtime_model_profile()
    crowd_analysis_decision = load_dense_crowd_analysis_decision()
    alert_rules = load_threshold_alert_rules()

    def detector_probe() -> bool:
        verify_runtime_checkpoint(profile, BASE_DIR)
        return True

    return ApplicationServices(
        database_probe=lambda: check_database_connection(
            connect_timeout=DATABASE_READINESS_TIMEOUT_SECONDS
        ),
        detector_probe=detector_probe,
        detector_factory=lambda: ObjectDetector.from_runtime_profile(profile),
        image_analysis_factory=lambda detector: ImageAnalysisService(
            detector=detector,
            model_profile=profile,
            crowd_analysis_decision=crowd_analysis_decision,
            upload_directory=settings.image_upload_directory,
            output_directory=settings.image_output_directory,
            upload_policy=ImageUploadPolicy(
                max_bytes=settings.max_image_upload_bytes,
                max_pixels=settings.max_image_pixels,
            ),
            max_grid_dimension=settings.max_grid_dimension,
            alert_rules=alert_rules,
        ),
        video_analysis_factory=lambda detector_provider: VideoAnalysisService(
            detector_provider=detector_provider,
            model_profile=profile,
            crowd_analysis_decision=crowd_analysis_decision,
            upload_directory=settings.video_upload_directory,
            output_directory=settings.video_output_directory,
            upload_policy=VideoUploadPolicy(
                max_bytes=settings.max_video_upload_bytes,
                max_frame_pixels=settings.max_image_pixels,
            ),
            max_grid_dimension=settings.max_grid_dimension,
            alert_rules=alert_rules,
            worker_count=settings.video_workers,
        ),
        output_asset_factory=lambda: OutputAssetService(
            allowed_directories=(
                settings.image_output_directory,
                settings.video_output_directory,
            )
        ),
        startup_function=recover_interrupted_video_jobs,
    )


def get_application_services(request: Request) -> ApplicationServices:
    return request.app.state.services


def get_detector(request: Request) -> Any:
    return get_application_services(request).get_detector()


def get_image_analysis_service(request: Request) -> Any:
    return get_application_services(request).get_image_analysis_service()


def get_video_analysis_service(request: Request) -> Any:
    return get_application_services(request).get_video_analysis_service()


def get_output_asset_service(request: Request) -> Any:
    return get_application_services(request).get_output_asset_service()
