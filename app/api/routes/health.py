from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import ApplicationServices, get_application_services
from app.api.schemas import (
    DependencyReadiness,
    ErrorResponse,
    HealthResponse,
    ReadinessResponse,
)
from app.api.settings import ApiSettings


def create_health_router(settings: ApiSettings) -> APIRouter:
    health_router = APIRouter(tags=["service"])

    @health_router.get(
        "/health",
        response_model=HealthResponse,
        summary="Check process health",
    )
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=settings.title,
            version=settings.version,
        )

    @health_router.get(
        "/ready",
        response_model=ReadinessResponse,
        responses={
            503: {"model": ReadinessResponse},
            500: {"model": ErrorResponse},
        },
        summary="Check application dependencies",
    )
    def readiness(
        response: Response,
        services: Annotated[ApplicationServices, Depends(get_application_services)],
    ) -> ReadinessResponse:
        checks = {
            name: DependencyReadiness(status="ready" if available else "not_ready")
            for name, available in services.readiness().items()
        }
        is_ready = all(check.status == "ready" for check in checks.values())
        if not is_ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="ready" if is_ready else "not_ready",
            checks=checks,
        )

    return health_router
