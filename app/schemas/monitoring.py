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


class VideoAnalysisJobResult(BaseModel):
    session_id: int = Field(gt=0)
    status: Literal["queued", "processing", "completed", "failed"]
    sampling_interval_seconds: float = Field(gt=0)
    grid_rows: int | None = Field(default=None, gt=0)
    grid_columns: int | None = Field(default=None, gt=0)
    total_source_frames: int = Field(gt=0)
    sampled_frames_total: int = Field(gt=0)
    sampled_frames_processed: int = Field(ge=0)
    progress_percent: float = Field(ge=0, le=100)
    failure_code: str | None
    failure_message: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @model_validator(mode="after")
    def validate_progress_and_grid(self) -> "VideoAnalysisJobResult":
        if (self.grid_rows is None) != (self.grid_columns is None):
            raise ValueError("Video grid rows and columns must be provided together.")
        if self.sampled_frames_processed > self.sampled_frames_total:
            raise ValueError("Processed sampled frames cannot exceed the total.")
        if self.status == "completed" and (
            self.sampled_frames_processed != self.sampled_frames_total
            or self.finished_at is None
            or self.failure_code is not None
            or self.failure_message is not None
        ):
            raise ValueError("Completed video jobs require complete progress.")
        if self.status == "failed" and (
            self.finished_at is None
            or self.failure_code is None
            or self.failure_message is None
        ):
            raise ValueError("Failed video jobs require public failure details.")
        return self


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

    @model_validator(mode="after")
    def validate_order(self) -> "ImageBounds":
        if self.x_max < self.x_min or self.y_max < self.y_min:
            raise ValueError(
                "Image bounds must use ordered minimum and maximum values."
            )
        return self


class PixelCoordinateSpace(BaseModel):
    name: Literal["processed_image_pixels"] = "processed_image_pixels"
    origin: Literal["top_left"] = "top_left"
    x_axis_direction: Literal["right"] = "right"
    y_axis_direction: Literal["down"] = "down"
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class VisualAssetReference(BaseModel):
    asset_id: UUID
    url: str
    content_type: Literal["image/jpeg"] = "image/jpeg"
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    rendered_overlays: tuple[Literal["detections"], ...] = ("detections",)


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
    analysis_method: Literal["detector_object_count"] | None
    object_class: str | None
    scope: Literal["frame", "grid_cell"] | None
    comparison_operator: Literal["greater_than", "greater_than_or_equal"] | None
    severity: Literal["information", "warning", "critical"]
    message: str
    measured_value: float | None = Field(ge=0)
    threshold_value: float | None = Field(gt=0)
    created_at: datetime
    resolved_at: datetime | None

    @model_validator(mode="after")
    def validate_rule_metadata_and_lineage(self) -> "AlertResult":
        metadata = (
            self.analysis_method,
            self.object_class,
            self.scope,
            self.comparison_operator,
        )
        if all(value is None for value in metadata):
            return self
        if any(value is None for value in metadata) or (
            self.measured_value is None or self.threshold_value is None
        ):
            raise ValueError("Configured alerts require complete rule metadata.")
        if self.scope == "frame" and self.grid_cell_id is not None:
            raise ValueError("Frame alerts cannot reference a grid cell.")
        if self.scope == "grid_cell" and self.grid_cell_id is None:
            raise ValueError("Grid-cell alerts require grid-cell lineage.")
        return self


class ProcessedFrameResult(BaseModel):
    id: int
    input_source_id: int
    frame_number: int = Field(ge=0)
    frame_timestamp_seconds: float | None = Field(ge=0)
    image_width: int | None = Field(gt=0)
    image_height: int | None = Field(gt=0)
    output_asset_id: UUID | None
    visual_asset: VisualAssetReference | None = None
    coordinate_space: PixelCoordinateSpace | None = None
    processed_at: datetime
    detections: list[DetectionResult]
    frame_summaries: list[ObjectCountSummaryResult]
    grid_cells: list[GridCellResult]
    alerts: list[AlertResult]

    @model_validator(mode="after")
    def validate_visual_coordinates(self) -> "ProcessedFrameResult":
        if (self.image_width is None) != (self.image_height is None):
            raise ValueError("Frame width and height must be provided together.")

        if self.image_width is None or self.image_height is None:
            if self.coordinate_space is not None or self.visual_asset is not None:
                raise ValueError("Visual metadata requires frame dimensions.")
            return self

        if self.coordinate_space is None or (
            self.coordinate_space.width != self.image_width
            or self.coordinate_space.height != self.image_height
        ):
            raise ValueError("Coordinate-space dimensions must match the frame.")

        if self.output_asset_id is None:
            if self.visual_asset is not None:
                raise ValueError("Visual assets require a stored output asset ID.")
        elif self.visual_asset is None or (
            self.visual_asset.asset_id != self.output_asset_id
            or self.visual_asset.width != self.image_width
            or self.visual_asset.height != self.image_height
        ):
            raise ValueError("Visual asset metadata must match the processed frame.")

        for detection in self.detections:
            self._validate_bounds(detection.bounds)
        for cell in self.grid_cells:
            self._validate_bounds(cell.bounds)
        return self

    def _validate_bounds(self, bounds: ImageBounds) -> None:
        if bounds.x_max > self.image_width or bounds.y_max > self.image_height:
            raise ValueError("Overlay bounds must remain inside the processed frame.")


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
