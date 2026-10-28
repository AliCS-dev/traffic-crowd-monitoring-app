from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.api.dependencies import get_output_asset_service
from app.api.errors import ApiError
from app.api.schemas import ErrorResponse
from app.services.output_asset_service import (
    OutputAssetNotFoundError,
    OutputAssetUnavailableError,
)


def create_asset_router() -> APIRouter:
    router = APIRouter(prefix="/assets", tags=["result assets"])

    @router.get(
        "/{asset_id}",
        response_class=FileResponse,
        responses={
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
        summary="Read one generated result asset",
    )
    def read_output_asset(
        asset_id: UUID,
        asset_service: Annotated[Any, Depends(get_output_asset_service)],
    ) -> FileResponse:
        return serve_asset(asset_service, asset_id)

    @router.get(
        "/{asset_id}/source",
        response_class=FileResponse,
        responses={404: {"model": ErrorResponse}},
        summary="Read the unannotated processed image for a stored result",
    )
    def read_source_asset(
        asset_id: UUID,
        asset_service: Annotated[Any, Depends(get_output_asset_service)],
    ) -> FileResponse:
        return serve_asset(asset_service, asset_id, source=True)

    def serve_asset(asset_service, asset_id, *, source=False):
        try:
            asset = (
                asset_service.resolve(asset_id, source=True)
                if source
                else asset_service.resolve(asset_id)
            )
        except OutputAssetNotFoundError as error:
            raise ApiError(404, "asset_not_found", str(error)) from error
        except OutputAssetUnavailableError as error:
            raise ApiError(404, "asset_unavailable", str(error)) from error

        return FileResponse(
            asset.file_path,
            media_type=asset.content_type,
            headers={
                "Cache-Control": "private, max-age=3600",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
