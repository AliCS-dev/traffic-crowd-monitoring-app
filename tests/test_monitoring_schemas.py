from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.schemas.monitoring import AlertResult, ProcessedFrameResult

ASSET_ID = UUID("12345678-1234-5678-1234-567812345678")
NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


def frame_values():
    return {
        "id": 1,
        "input_source_id": 2,
        "frame_number": 0,
        "frame_timestamp_seconds": 0,
        "image_width": 200,
        "image_height": 100,
        "output_asset_id": ASSET_ID,
        "visual_asset": {
            "asset_id": ASSET_ID,
            "url": f"/api/assets/{ASSET_ID}",
            "width": 200,
            "height": 100,
        },
        "coordinate_space": {"width": 200, "height": 100},
        "processed_at": NOW,
        "detections": [],
        "frame_summaries": [],
        "grid_cells": [],
        "alerts": [],
    }


def test_visual_asset_dimensions_must_match_coordinate_space():
    values = frame_values()
    values["visual_asset"]["width"] = 201

    with pytest.raises(ValidationError, match="must match the processed frame"):
        ProcessedFrameResult.model_validate(values)


def test_overlay_bounds_must_remain_inside_served_media():
    values = frame_values()
    values["detections"] = [
        {
            "id": 3,
            "object_class": "car_or_van",
            "confidence": 0.9,
            "bounds": {
                "x_min": 180,
                "y_min": 20,
                "x_max": 201,
                "y_max": 40,
            },
            "created_at": NOW,
        }
    ]

    with pytest.raises(ValidationError, match="inside the processed frame"):
        ProcessedFrameResult.model_validate(values)


def alert_values(**overrides):
    values = {
        "id": 4,
        "grid_cell_id": None,
        "alert_type": "frame-car-warning",
        "analysis_method": "detector_object_count",
        "object_class": "car_or_van",
        "scope": "frame",
        "comparison_operator": "greater_than_or_equal",
        "severity": "warning",
        "message": "Experimental detector count met its configured threshold.",
        "measured_value": 2,
        "threshold_value": 2,
        "created_at": NOW,
        "resolved_at": None,
    }
    values.update(overrides)
    return values


def test_configured_alert_schema_retains_typed_threshold_values():
    alert = AlertResult.model_validate(alert_values())

    assert alert.analysis_method == "detector_object_count"
    assert alert.scope == "frame"
    assert alert.measured_value == 2
    assert alert.threshold_value == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"scope": "grid_cell", "grid_cell_id": None},
        {"scope": "frame", "grid_cell_id": 3},
        {"object_class": None},
        {"severity": "emergency"},
        {"threshold_value": 0},
    ],
)
def test_invalid_alert_metadata_or_lineage_is_rejected(overrides):
    with pytest.raises(ValidationError):
        AlertResult.model_validate(alert_values(**overrides))
