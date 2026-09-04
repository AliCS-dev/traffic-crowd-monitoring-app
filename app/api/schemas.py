from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.monitoring import DenseCrowdAnalysisResult


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


class UploadCapabilities(BaseModel):
    extensions: tuple[str, ...]
    mime_types: tuple[str, ...]
    mime_type_by_extension: dict[str, str]
    max_upload_bytes: int = Field(gt=0)
    max_pixels: int = Field(gt=0)


class AnalysisOptionCapabilities(BaseModel):
    max_session_name_length: int = Field(gt=0)
    max_grid_dimension: int = Field(gt=0)
    default_sampling_interval_seconds: float = Field(gt=0)
    max_sampling_interval_seconds: float = Field(gt=0)


class AnalysisCapabilitiesResponse(BaseModel):
    image: UploadCapabilities
    video: UploadCapabilities
    options: AnalysisOptionCapabilities


class ImageAnalysisCreatedResponse(BaseModel):
    session_id: int
    status: Literal["completed"]
    result_url: str
    output_asset_id: UUID
    detection_count: int
    grid_rows: int | None
    grid_columns: int | None
    dense_crowd_analysis: DenseCrowdAnalysisResult


class VideoAnalysisCreatedResponse(BaseModel):
    session_id: int
    status: Literal["queued"]
    job_url: str
    result_url: str
    sampled_frames_total: int
    sampling_interval_seconds: float
    grid_rows: int | None
    grid_columns: int | None
