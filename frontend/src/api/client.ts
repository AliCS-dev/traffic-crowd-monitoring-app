import { apiBaseUrl } from "../config.ts";
import type {
  ErrorResponse,
  HealthResponse,
  ReadinessResponse,
} from "./types.ts";

type FetchFunction = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

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
    return this.request("/api/health", signal);
  }

  getReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
    return this.request("/api/ready", signal, [503]);
  }

  private async request<T>(
    path: string,
    signal?: AbortSignal,
    acceptedStatuses: number[] = [],
  ): Promise<T> {
    const response = await this.fetchFunction(`${this.baseUrl}${path}`, {
      headers: {
        Accept: "application/json",
      },
      signal,
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
