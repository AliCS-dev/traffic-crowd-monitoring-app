export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
}

export interface DependencyReadiness {
  status: "ready" | "not_ready";
}

export interface ReadinessResponse {
  status: "ready" | "not_ready";
  checks: Record<string, DependencyReadiness>;
}

export interface ErrorResponse {
  error: {
    code: string;
    message: string;
  };
}

export interface UploadCapabilities {
  extensions: string[];
  mime_types: string[];
  mime_type_by_extension: Record<string, string>;
  max_upload_bytes: number;
  max_pixels: number;
}

export interface AnalysisCapabilitiesResponse {
  image: UploadCapabilities;
  video: UploadCapabilities;
  options: {
    max_session_name_length: number;
    max_grid_dimension: number;
    default_sampling_interval_seconds: number;
    max_sampling_interval_seconds: number;
  };
}

export interface AnalysisSubmissionOptions {
  sessionName: string | null;
  gridRows: number | null;
  gridColumns: number | null;
}

export interface VideoAnalysisSubmissionOptions extends AnalysisSubmissionOptions {
  samplingIntervalSeconds: number;
}

export interface DenseCrowdAnalysisResponse {
  status: "completed" | "unsupported";
  count: number | null;
  method_id: string | null;
  model_id: string | null;
  evaluated_candidate_id: string;
  quality_gate_status: "conditional" | "passed" | "failed";
  evaluation_reference: string;
  reason_code: string | null;
  message: string;
}

export interface ImageAnalysisCreatedResponse {
  session_id: number;
  status: "completed";
  result_url: string;
  output_asset_id: string;
  detection_count: number;
  grid_rows: number | null;
  grid_columns: number | null;
  dense_crowd_analysis: DenseCrowdAnalysisResponse;
}

export interface VideoAnalysisCreatedResponse {
  session_id: number;
  status: "queued";
  job_url: string;
  result_url: string;
  sampled_frames_total: number;
  sampling_interval_seconds: number;
  grid_rows: number | null;
  grid_columns: number | null;
}

export type VideoAnalysisJobStatus =
  "queued" | "processing" | "completed" | "failed";

export interface VideoAnalysisJobResponse {
  session_id: number;
  status: VideoAnalysisJobStatus;
  sampling_interval_seconds: number;
  grid_rows: number | null;
  grid_columns: number | null;
  total_source_frames: number;
  sampled_frames_total: number;
  sampled_frames_processed: number;
  progress_percent: number;
  failure_code: string | null;
  failure_message: string | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
}
