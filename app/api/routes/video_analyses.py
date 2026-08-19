from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.api.dependencies import get_video_analysis_service
from app.api.errors import ApiError
from app.api.schemas import ErrorResponse, VideoAnalysisCreatedResponse
from app.schemas.monitoring import VideoAnalysisJobResult
from app.services.video_analysis_service import InvalidVideoAnalysisOptionsError
from app.services.video_upload_service import (
    InvalidVideoUploadError,
    UnsupportedVideoUploadError,
    VideoUploadTooLargeError,
)


def create_video_analysis_router() -> APIRouter:
    router = APIRouter(prefix="/analyses/videos", tags=["video analysis"])

    @router.post(
        "",
        response_model=VideoAnalysisCreatedResponse,
        status_code=status.HTTP_202_ACCEPTED,
        responses={
            413: {"model": ErrorResponse},
            415: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
        summary="Queue one uploaded video for analysis",
    )
    def analyze_video(
        video: Annotated[UploadFile, File()],
        analysis_service: Annotated[Any, Depends(get_video_analysis_service)],
        session_name: Annotated[str | None, Form()] = None,
        sampling_interval_seconds: Annotated[float, Form()] = 1.0,
        grid_rows: Annotated[int | None, Form()] = None,
        grid_columns: Annotated[int | None, Form()] = None,
    ) -> VideoAnalysisCreatedResponse:
        try:
            result = analysis_service.submit_upload(
                video.file,
                filename=video.filename,
                content_type=video.content_type,
                session_name=session_name,
                sampling_interval_seconds=sampling_interval_seconds,
                grid_rows=grid_rows,
                grid_columns=grid_columns,
            )
        except VideoUploadTooLargeError as error:
            raise ApiError(413, "video_too_large", str(error)) from error
        except UnsupportedVideoUploadError as error:
            raise ApiError(415, "unsupported_video", str(error)) from error
        except InvalidVideoUploadError as error:
            raise ApiError(422, "invalid_video", str(error)) from error
        except InvalidVideoAnalysisOptionsError as error:
            raise ApiError(422, "invalid_analysis_options", str(error)) from error

        return VideoAnalysisCreatedResponse(
            session_id=result.session_id,
            status="queued",
            job_url=f"/api/analyses/videos/{result.session_id}",
            result_url=f"/api/analyses/{result.session_id}",
            sampled_frames_total=result.sampled_frames_total,
            sampling_interval_seconds=result.sampling_interval_seconds,
            grid_rows=result.grid_rows,
            grid_columns=result.grid_columns,
        )

    @router.get(
        "/{session_id}",
        response_model=VideoAnalysisJobResult,
        responses={
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
        summary="Read video analysis progress",
    )
    def read_video_job(
        session_id: int,
        analysis_service: Annotated[Any, Depends(get_video_analysis_service)],
    ) -> VideoAnalysisJobResult:
        if session_id < 1:
            raise ApiError(
                422, "invalid_session_id", "Session ID must be a positive integer."
            )
        result = analysis_service.get_job(session_id)
        if result is None:
            raise ApiError(404, "video_job_not_found", "Video analysis job not found.")
        return result

    return router
