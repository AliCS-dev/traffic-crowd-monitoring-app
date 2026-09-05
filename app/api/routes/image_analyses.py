from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.api.dependencies import get_image_analysis_service
from app.api.errors import ApiError
from app.api.schemas import ErrorResponse, ImageAnalysisCreatedResponse
from app.schemas.monitoring import DenseCrowdAnalysisResult
from app.services.image_analysis_service import InvalidImageAnalysisOptionsError
from app.services.image_upload_service import (
    ImageUploadTooLargeError,
    InvalidImageUploadError,
    UnsupportedImageUploadError,
)


def create_image_analysis_router() -> APIRouter:
    router = APIRouter(prefix="/analyses", tags=["image analysis"])

    @router.post(
        "/images",
        response_model=ImageAnalysisCreatedResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            413: {"model": ErrorResponse},
            415: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
        summary="Upload and analyse one image",
    )
    def analyze_image(
        image: Annotated[UploadFile, File()],
        analysis_service: Annotated[Any, Depends(get_image_analysis_service)],
        session_name: Annotated[str | None, Form()] = None,
        grid_rows: Annotated[int | None, Form()] = None,
        grid_columns: Annotated[int | None, Form()] = None,
    ) -> ImageAnalysisCreatedResponse:
        try:
            result = analysis_service.analyze_upload(
                image.file,
                filename=image.filename,
                content_type=image.content_type,
                session_name=session_name,
                grid_rows=grid_rows,
                grid_columns=grid_columns,
            )
        except ImageUploadTooLargeError as error:
            raise ApiError(413, "image_too_large", str(error)) from error
        except UnsupportedImageUploadError as error:
            raise ApiError(415, "unsupported_image", str(error)) from error
        except InvalidImageUploadError as error:
            raise ApiError(422, "invalid_image", str(error)) from error
        except InvalidImageAnalysisOptionsError as error:
            raise ApiError(422, "invalid_analysis_options", str(error)) from error

        return ImageAnalysisCreatedResponse(
            session_id=result.session_id,
            status="completed",
            result_url=f"/api/analyses/{result.session_id}",
            output_asset_id=result.output_asset_id,
            detection_count=result.detection_count,
            grid_rows=result.grid_rows,
            grid_columns=result.grid_columns,
            dense_crowd_analysis=DenseCrowdAnalysisResult(
                status=result.dense_crowd_analysis.status,
                count=result.dense_crowd_analysis.count,
                method_id=result.dense_crowd_analysis.method_id,
                model_id=result.dense_crowd_analysis.model_id,
                evaluated_candidate_id=(
                    result.dense_crowd_analysis.evaluated_candidate_id
                ),
                quality_gate_status=(result.dense_crowd_analysis.quality_gate_status),
                evaluation_reference=(
                    result.dense_crowd_analysis.evaluation_reference.as_posix()
                ),
                reason_code=result.dense_crowd_analysis.reason_code,
                message=result.dense_crowd_analysis.message,
            ),
        )

    return router
