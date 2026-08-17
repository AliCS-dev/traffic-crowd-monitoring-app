import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHttpException

LOGGER = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_payload(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(application: FastAPI) -> None:
    @application.exception_handler(ApiError)
    async def handle_api_error(_request: Request, error: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content=error_payload(error.code, error.message),
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_payload(
                "validation_error", "The request contains invalid data."
            ),
        )

    @application.exception_handler(StarletteHttpException)
    async def handle_http_error(
        _request: Request, error: StarletteHttpException
    ) -> JSONResponse:
        message = str(error.detail) if error.status_code != 404 else "Route not found."
        code = "not_found" if error.status_code == 404 else "http_error"
        return JSONResponse(
            status_code=error.status_code,
            content=error_payload(code, message),
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request, error: Exception
    ) -> JSONResponse:
        LOGGER.exception(
            "Unhandled API error for %s %s",
            request.method,
            request.url.path,
            exc_info=(type(error), error, error.__traceback__),
        )
        return JSONResponse(
            status_code=500,
            content=error_payload(
                "internal_error", "An unexpected server error occurred."
            ),
        )
