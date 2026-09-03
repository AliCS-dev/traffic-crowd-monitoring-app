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
