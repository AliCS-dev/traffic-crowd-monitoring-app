from fastapi import APIRouter

from app.api.schemas import (
    AnalysisCapabilitiesResponse,
    AnalysisOptionCapabilities,
    UploadCapabilities,
)
from app.api.settings import ApiSettings
from app.services.image_upload_service import FORMAT_BY_SUFFIX, MIME_BY_FORMAT
from app.services.video_analysis_service import (
    MAX_SAMPLING_INTERVAL_SECONDS,
    MAX_SESSION_NAME_LENGTH,
)
from app.services.video_upload_service import MIME_BY_SUFFIX

DEFAULT_SAMPLING_INTERVAL_SECONDS = 1.0


def create_capabilities_router(settings: ApiSettings) -> APIRouter:
    router = APIRouter(tags=["configuration"])

    @router.get(
        "/capabilities",
        response_model=AnalysisCapabilitiesResponse,
        summary="Read public analysis constraints",
    )
    def read_capabilities() -> AnalysisCapabilitiesResponse:
        return AnalysisCapabilitiesResponse(
            image=UploadCapabilities(
                extensions=tuple(FORMAT_BY_SUFFIX),
                mime_types=tuple(MIME_BY_FORMAT.values()),
                mime_type_by_extension={
                    suffix: MIME_BY_FORMAT[image_format]
                    for suffix, image_format in FORMAT_BY_SUFFIX.items()
                },
                max_upload_bytes=settings.max_image_upload_bytes,
                max_pixels=settings.max_image_pixels,
            ),
            video=UploadCapabilities(
                extensions=tuple(MIME_BY_SUFFIX),
                mime_types=tuple(MIME_BY_SUFFIX.values()),
                mime_type_by_extension=dict(MIME_BY_SUFFIX),
                max_upload_bytes=settings.max_video_upload_bytes,
                max_pixels=settings.max_image_pixels,
            ),
            options=AnalysisOptionCapabilities(
                max_session_name_length=MAX_SESSION_NAME_LENGTH,
                max_grid_dimension=settings.max_grid_dimension,
                default_sampling_interval_seconds=(DEFAULT_SAMPLING_INTERVAL_SECONDS),
                max_sampling_interval_seconds=MAX_SAMPLING_INTERVAL_SECONDS,
            ),
        )

    return router
