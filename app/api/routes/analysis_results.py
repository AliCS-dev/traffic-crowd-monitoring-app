from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import ApplicationServices, get_application_services
from app.api.errors import ApiError
from app.api.schemas import ErrorResponse
from app.database.monitoring_query_repository import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
)
from app.schemas.monitoring import MonitoringSessionPage, MonitoringSessionResult


def create_analysis_result_router() -> APIRouter:
    router = APIRouter(prefix="/analyses", tags=["analysis results"])

    @router.get(
        "",
        response_model=MonitoringSessionPage,
        responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
        summary="List monitoring sessions",
    )
    def list_analyses(
        services: Annotated[ApplicationServices, Depends(get_application_services)],
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    ) -> MonitoringSessionPage:
        return services.list_monitoring_sessions(page=page, page_size=page_size)

    @router.get(
        "/{session_id}",
        response_model=MonitoringSessionResult,
        responses={
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
        summary="Read one completed analysis",
    )
    def read_analysis(
        session_id: int,
        services: Annotated[ApplicationServices, Depends(get_application_services)],
    ) -> MonitoringSessionResult:
        if session_id < 1:
            raise ApiError(
                422,
                "invalid_session_id",
                "Session ID must be a positive integer.",
            )
        result = services.get_monitoring_session(session_id)
        if result is None:
            raise ApiError(404, "analysis_not_found", "Analysis result not found.")
        return result

    return router
