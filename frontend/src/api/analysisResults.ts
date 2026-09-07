import type {
  DenseCrowdAnalysisResponse,
  MonitoringSessionSourceType,
} from "./types.ts";

export interface ModelRunProfileResult {
  profile_id: string;
  model_id: string;
  quality_gate_status: "not_evaluated" | "conditional" | "passed" | "failed";
  evaluation_reference: string;
  checkpoint_path: string;
  checkpoint_sha256: string;
  class_mapping: Record<string, string>;
  confidence: number;
  image_size: number;
  scale_factor: number;
  max_detections: number;
  numeric_precision: "float16" | "float32";
  device: string;
  created_at: string;
}

export interface InputSourceResult {
  id: number;
  source_type: MonitoringSessionSourceType;
  original_filename: string | null;
  created_at: string;
}

export interface ImageBounds {
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
}

export interface VisualAssetReference {
  asset_id: string;
  url: string;
  content_type: "image/jpeg";
  width: number;
  height: number;
  rendered_overlays: "detections"[];
}

export interface DetectionResult {
  id: number;
  object_class: string;
  confidence: number;
  bounds: ImageBounds;
  created_at: string;
}

export interface ObjectCountSummaryResult {
  id: number;
  object_class: string;
  object_count: number;
  created_at: string;
}

export interface GridCellResult {
  id: number;
  row_index: number;
  column_index: number;
  bounds: ImageBounds;
  summaries: ObjectCountSummaryResult[];
}

export interface AlertResult {
  id: number;
  grid_cell_id: number | null;
  alert_type: string;
  analysis_method: "detector_object_count" | null;
  object_class: string | null;
  scope: "frame" | "grid_cell" | null;
  comparison_operator: "greater_than" | "greater_than_or_equal" | null;
  severity: "information" | "warning" | "critical";
  message: string;
  measured_value: number | null;
  threshold_value: number | null;
  created_at: string;
  resolved_at: string | null;
}

export interface ProcessedFrameResult {
  id: number;
  input_source_id: number;
  frame_number: number;
  frame_timestamp_seconds: number | null;
  image_width: number | null;
  image_height: number | null;
  output_asset_id: string | null;
  visual_asset: VisualAssetReference | null;
  coordinate_space: {
    name: "processed_image_pixels";
    origin: "top_left";
    x_axis_direction: "right";
    y_axis_direction: "down";
    width: number;
    height: number;
  } | null;
  processed_at: string;
  detections: DetectionResult[];
  frame_summaries: ObjectCountSummaryResult[];
  grid_cells: GridCellResult[];
  alerts: AlertResult[];
}

export interface MonitoringSessionResult {
  id: number;
  session_name: string | null;
  status: string;
  started_at: string;
  completed_at: string | null;
  notes: string | null;
  model_profile: ModelRunProfileResult | null;
  dense_crowd_analysis: DenseCrowdAnalysisResponse | null;
  sources: InputSourceResult[];
  frames: ProcessedFrameResult[];
}
