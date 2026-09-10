import type { AlertResult } from "../api/analysisResults.ts";
import { gridResultFixture } from "./analysisResultFixture.ts";

export function alertFixture(
  overrides: Partial<AlertResult> = {},
): AlertResult {
  return {
    id: 70,
    grid_cell_id: null,
    alert_type: "frame-car-or-van-warning",
    analysis_method: "detector_object_count",
    object_class: "car_or_van",
    scope: "frame",
    comparison_operator: "greater_than_or_equal",
    severity: "warning",
    message:
      "Experimental detector count met or exceeded its recorded threshold.",
    measured_value: 20,
    threshold_value: 20,
    created_at: "2026-09-07T09:30:00Z",
    resolved_at: null,
    ...overrides,
  };
}

export function alertResultFixture() {
  const result = gridResultFixture();
  result.frames[0].alerts = [
    alertFixture(),
    alertFixture({
      id: 71,
      grid_cell_id: 51,
      alert_type: "grid-person-information",
      object_class: "person",
      scope: "grid_cell",
      severity: "information",
      measured_value: 8,
      threshold_value: 8,
      message:
        "Experimental detector count for 'person' in grid cell (0, 1) met or exceeded threshold 8 (measured 8).",
    }),
  ];
  return result;
}
