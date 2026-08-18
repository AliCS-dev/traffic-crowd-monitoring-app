from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class DependencyReadiness(BaseModel):
    status: Literal["ready", "not_ready"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, DependencyReadiness]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ImageAnalysisCreatedResponse(BaseModel):
    session_id: int
    status: Literal["completed"]
    result_url: str
    output_asset_id: UUID
    detection_count: int
    grid_rows: int | None
    grid_columns: int | None
