import type { MonitoringSessionResult } from "../api/analysisResults.ts";

export function analysisResultFixture(id = 42): MonitoringSessionResult {
  const timestamp = "2026-09-07T09:30:00Z";
  const assetId = "12345678-1234-5678-1234-567812345678";
  return {
    id,
    session_name: null,
    status: "completed",
    started_at: timestamp,
    completed_at: "2026-09-07T09:30:04Z",
    notes: null,
    model_profile: {
      profile_id: "aerial-evaluation-v1",
      model_id: "evaluated-traffic-detector",
      quality_gate_status: "failed",
      evaluation_reference: "docs/evaluation/final_quality_gate.md",
      checkpoint_path: "models/traffic.pt",
      checkpoint_sha256: "a".repeat(64),
      class_mapping: { car: "car_or_van", person: "person" },
      confidence: 0.25,
      image_size: 1280,
      scale_factor: 1,
      max_detections: 1000,
      numeric_precision: "float32",
      device: "cpu",
      created_at: timestamp,
    },
    dense_crowd_analysis: {
      status: "unsupported",
      count: null,
      method_id: null,
      model_id: null,
      evaluated_candidate_id: "crowd-candidate",
      quality_gate_status: "failed",
      evaluation_reference:
        "docs/evaluation/dedicated_crowd_counting_result.md",
      reason_code: "no_accepted_dense_crowd_model",
      message: "No evaluated candidate supports reliable dense-crowd counting.",
    },
    sources: [
      {
        id: 10,
        source_type: "image",
        original_filename: "junction.jpg",
        created_at: timestamp,
      },
    ],
    frames: [
      {
        id: 20,
        input_source_id: 10,
        frame_number: 0,
        frame_timestamp_seconds: null,
        image_width: 1280,
        image_height: 720,
        output_asset_id: assetId,
        visual_asset: {
          asset_id: assetId,
          url: `/api/assets/${assetId}`,
          content_type: "image/jpeg",
          width: 1280,
          height: 720,
          rendered_overlays: ["detections"],
        },
        coordinate_space: {
          name: "processed_image_pixels",
          origin: "top_left",
          x_axis_direction: "right",
          y_axis_direction: "down",
          width: 1280,
          height: 720,
        },
        processed_at: timestamp,
        detections: [
          {
            id: 30,
            object_class: "car_or_van",
            confidence: 0.825,
            bounds: { x_min: 100, y_min: 120, x_max: 140, y_max: 180 },
            created_at: timestamp,
          },
        ],
        frame_summaries: [
          {
            id: 40,
            object_class: "car_or_van",
            object_count: 1,
            created_at: timestamp,
          },
        ],
        grid_cells: [
          {
            id: 50,
            row_index: 0,
            column_index: 0,
            bounds: { x_min: 0, y_min: 0, x_max: 640, y_max: 360 },
            summaries: [
              {
                id: 41,
                object_class: "car_or_van",
                object_count: 1,
                created_at: timestamp,
              },
            ],
          },
        ],
        alerts: [],
      },
    ],
  };
}
