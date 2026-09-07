import type { MonitoringSessionResult } from "../api/analysisResults.ts";

export function gridResultFixture(): MonitoringSessionResult {
  const result = analysisResultFixture();
  const frame = result.frames[0];
  const carSummary = frame.frame_summaries[0];
  const personSummary = {
    ...carSummary,
    id: 42,
    object_class: "person",
    object_count: 2,
  };
  frame.frame_summaries.push(personSummary);
  frame.detections.push(
    ...[31, 32].map((id) => ({
      ...frame.detections[0],
      id,
      object_class: "person",
      bounds: { x_min: 700 + id, y_min: 100, x_max: 710 + id, y_max: 120 },
    })),
  );
  frame.grid_cells = Array.from({ length: 4 }, (_, index) => {
    const row = Math.floor(index / 2);
    const column = index % 2;
    return {
      id: 50 + index,
      row_index: row,
      column_index: column,
      bounds: {
        x_min: column * 640,
        y_min: row * 360,
        x_max: (column + 1) * 640,
        y_max: (row + 1) * 360,
      },
      summaries:
        index === 0
          ? [{ ...carSummary, id: 51 }]
          : index === 1
            ? [{ ...personSummary, id: 52 }]
            : [],
    };
  });
  return result;
}

export function videoResultFixture(id = 42): MonitoringSessionResult {
  const result = analysisResultFixture(id);
  result.sources[0].source_type = "video";
  result.sources[0].original_filename = "junction.mp4";
  const first = result.frames[0];
  first.frame_timestamp_seconds = 0;
  const second = structuredClone(first);
  second.id = 21;
  second.frame_number = 60;
  second.frame_timestamp_seconds = 2.5;
  second.output_asset_id = null;
  second.visual_asset = null;
  second.detections = Array.from({ length: 21 }, (_, index) => ({
    ...first.detections[0],
    id: 100 + index,
    object_class: "truck",
  }));
  second.frame_summaries = [
    {
      ...first.frame_summaries[0],
      id: 41,
      object_class: "truck",
      object_count: 21,
    },
  ];
  second.grid_cells = [];
  const third = structuredClone(first);
  third.id = 22;
  third.frame_number = 120;
  third.frame_timestamp_seconds = 5;
  third.output_asset_id = "12345678-1234-5678-1234-567812345679";
  third.visual_asset!.asset_id = third.output_asset_id;
  third.visual_asset!.url = `/api/assets/${third.output_asset_id}`;
  third.detections = [];
  third.frame_summaries = [];
  third.grid_cells = [];
  result.frames = [third, first, second];
  return result;
}

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
