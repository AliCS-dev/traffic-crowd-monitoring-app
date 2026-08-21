from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import (
    ApplicationServices,
    create_application_services,
)
from app.api.errors import register_error_handlers
from app.api.routes.assets import create_asset_router
from app.api.routes.health import create_health_router
from app.api.routes.image_analyses import create_image_analysis_router
from app.api.routes.video_analyses import create_video_analysis_router
from app.api.settings import ApiSettings


def create_app(
    *,
    settings: ApiSettings | None = None,
    service_factory: Callable[[], ApplicationServices] | None = None,
) -> FastAPI:
    settings = settings or ApiSettings.from_environment()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        services = (
            service_factory()
            if service_factory is not None
            else create_application_services(settings)
        )
        application.state.services = services
        try:
            services.start()
            yield
        finally:
            services.close()

    application = FastAPI(
        title=settings.title,
        version=settings.version,
        lifespan=lifespan,
    )
    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    register_error_handlers(application)
    application.include_router(
        create_health_router(settings),
        prefix="/api",
    )
    application.include_router(
        create_asset_router(),
        prefix="/api",
    )
    application.include_router(
        create_video_analysis_router(),
        prefix="/api",
    )
    application.include_router(
        create_image_analysis_router(),
        prefix="/api",
    )
    return application


app = create_app()
