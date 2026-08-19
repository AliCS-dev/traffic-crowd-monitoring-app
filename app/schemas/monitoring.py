from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class Pagination(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class MonitoringSessionSummary(BaseModel):
    id: int
    session_name: str | None
    status: str
    started_at: datetime
    completed_at: datetime | None


class MonitoringSessionPage(BaseModel):
    items: list[MonitoringSessionSummary]
    pagination: Pagination


class InputSourceResult(BaseModel):
    id: int
    source_type: Literal["image", "video"]
    original_filename: str | None
    created_at: datetime


class ModelRunProfileResult(BaseModel):
    profile_id: str
    model_id: str
    quality_gate_status: Literal["not_evaluated", "conditional", "passed", "failed"]
    evaluation_reference: str
    checkpoint_path: str
    checkpoint_sha256: str
    class_mapping: dict[str, str]
    confidence: float = Field(ge=0, le=1)
    image_size: int = Field(gt=0)
    scale_factor: int = Field(gt=0)
    max_detections: int = Field(gt=0)
    numeric_precision: Literal["float16", "float32"]
    device: str
    created_at: datetime


class DenseCrowdAnalysisResult(BaseModel):
    status: Literal["completed", "unsupported"]
    count: int | None = Field(default=None, ge=0)
    method_id: str | None
    model_id: str | None
    evaluated_candidate_id: str
    quality_gate_status: Literal["conditional", "passed", "failed"]
    evaluation_reference: str
    reason_code: str | None
    message: str

    @model_validator(mode="after")
    def validate_status_fields(self) -> "DenseCrowdAnalysisResult":
        if self.status == "unsupported":
            if any(
                value is not None
                for value in (self.count, self.method_id, self.model_id)
            ):
                raise ValueError(
                    "Unsupported dense-crowd analysis cannot contain a count, "
                    "method, or model."
                )
            if self.quality_gate_status != "failed" or self.reason_code is None:
                raise ValueError(
                    "Unsupported dense-crowd analysis requires a failed quality "
                    "gate and reason code."
                )
        elif (
            self.count is None
            or self.method_id is None
            or self.model_id is None
            or self.quality_gate_status == "failed"
            or self.reason_code is not None
        ):
            raise ValueError(
                "Completed dense-crowd analysis requires a count, method, accepted "
                "model, and no failure reason."
            )
        return self


class ImageBounds(BaseModel):
    x_min: float = Field(ge=0)
    y_min: float = Field(ge=0)
    x_max: float = Field(ge=0)
    y_max: float = Field(ge=0)


class DetectionResult(BaseModel):
    id: int
    object_class: str
    confidence: float = Field(ge=0, le=1)
    bounds: ImageBounds
    created_at: datetime


class ObjectCountSummaryResult(BaseModel):
    id: int
    object_class: str
    object_count: int = Field(ge=0)
    created_at: datetime


class GridCellResult(BaseModel):
    id: int
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    bounds: ImageBounds
    summaries: list[ObjectCountSummaryResult]


class AlertResult(BaseModel):
    id: int
    grid_cell_id: int | None
    alert_type: str
    severity: str
    message: str
    measured_value: float | None
    threshold_value: float | None
    created_at: datetime
    resolved_at: datetime | None


class ProcessedFrameResult(BaseModel):
    id: int
    input_source_id: int
    frame_number: int = Field(ge=0)
    frame_timestamp_seconds: float | None = Field(ge=0)
    image_width: int | None = Field(gt=0)
    image_height: int | None = Field(gt=0)
    output_asset_id: UUID | None
    processed_at: datetime
    detections: list[DetectionResult]
    frame_summaries: list[ObjectCountSummaryResult]
    grid_cells: list[GridCellResult]
    alerts: list[AlertResult]


class MonitoringSessionResult(BaseModel):
    id: int
    session_name: str | None
    status: str
    started_at: datetime
    completed_at: datetime | None
    notes: str | None
    model_profile: ModelRunProfileResult | None
    dense_crowd_analysis: DenseCrowdAnalysisResult | None
    sources: list[InputSourceResult]
    frames: list[ProcessedFrameResult]
