import { apiBaseUrl } from "../config.ts";
import type {
  AnalysisCapabilitiesResponse,
  AnalysisSubmissionOptions,
  ErrorResponse,
  HealthResponse,
  ImageAnalysisCreatedResponse,
  MonitoringSessionPage,
  ReadinessResponse,
  VideoAnalysisCreatedResponse,
  VideoAnalysisJobResponse,
  VideoAnalysisSubmissionOptions,
} from "./types.ts";

type FetchFunction = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

interface RequestOptions extends RequestInit {
  acceptedStatuses?: readonly number[];
}

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
  }
}

export class ApiClient {
  readonly baseUrl: string;
  private readonly fetchFunction: FetchFunction;

  constructor(
    baseUrl: string,
    fetchFunction: FetchFunction = (...arguments_) =>
      globalThis.fetch(...arguments_),
  ) {
    this.baseUrl = baseUrl;
    this.fetchFunction = fetchFunction;
  }

  getHealth(signal?: AbortSignal): Promise<HealthResponse> {
    return this.request("/api/health", { signal });
  }

  getReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
    return this.request("/api/ready", { signal, acceptedStatuses: [503] });
  }

  getCapabilities(signal?: AbortSignal): Promise<AnalysisCapabilitiesResponse> {
    return this.request("/api/capabilities", { signal });
  }

  submitImage(
    file: File,
    options: AnalysisSubmissionOptions,
    signal?: AbortSignal,
  ): Promise<ImageAnalysisCreatedResponse> {
    const body = createAnalysisFormData("image", file, options);
    return this.request("/api/analyses/images", {
      method: "POST",
      body,
      signal,
    });
  }

  submitVideo(
    file: File,
    options: VideoAnalysisSubmissionOptions,
    signal?: AbortSignal,
  ): Promise<VideoAnalysisCreatedResponse> {
    const body = createAnalysisFormData("video", file, options);
    body.set(
      "sampling_interval_seconds",
      String(options.samplingIntervalSeconds),
    );
    return this.request("/api/analyses/videos", {
      method: "POST",
      body,
      signal,
    });
  }

  getVideoJob(
    sessionId: number,
    signal?: AbortSignal,
  ): Promise<VideoAnalysisJobResponse> {
    return this.request(`/api/analyses/videos/${sessionId}`, { signal });
  }

  listAnalyses(
    page = 1,
    pageSize = 20,
    signal?: AbortSignal,
  ): Promise<MonitoringSessionPage> {
    const searchParameters = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    return this.request(`/api/analyses?${searchParameters}`, { signal });
  }

  private async request<T>(
    path: string,
    options: RequestOptions = {},
  ): Promise<T> {
    const { acceptedStatuses = [], headers, ...requestOptions } = options;
    const requestHeaders = new Headers(headers);
    requestHeaders.set("Accept", "application/json");
    const response = await this.fetchFunction(`${this.baseUrl}${path}`, {
      ...requestOptions,
      headers: requestHeaders,
    });
    const payload = await readJson(response);

    if (!response.ok && !acceptedStatuses.includes(response.status)) {
      const error = isErrorResponse(payload) ? payload.error : null;
      throw new ApiRequestError(
        response.status,
        error?.code ?? "api_request_failed",
        error?.message ?? `API request failed with status ${response.status}.`,
      );
    }

    return payload as T;
  }
}

async function readJson(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return null;
  }
  return response.json();
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  if (typeof value !== "object" || value === null || !("error" in value)) {
    return false;
  }
  const error = value.error;
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    typeof error.code === "string" &&
    "message" in error &&
    typeof error.message === "string"
  );
}

export const apiClient = new ApiClient(apiBaseUrl);

function createAnalysisFormData(
  mediaField: "image" | "video",
  file: File,
  options: AnalysisSubmissionOptions,
): FormData {
  const body = new FormData();
  body.set(mediaField, file, file.name);
  if (options.sessionName !== null) {
    body.set("session_name", options.sessionName);
  }
  if (options.gridRows !== null && options.gridColumns !== null) {
    body.set("grid_rows", String(options.gridRows));
    body.set("grid_columns", String(options.gridColumns));
  }
  return body;
}
