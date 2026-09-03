const DEFAULT_API_BASE_URL = "http://localhost:8000";

export class FrontendConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FrontendConfigurationError";
  }
}

export function resolveApiBaseUrl(rawValue?: string): string {
  const value = (rawValue ?? DEFAULT_API_BASE_URL).trim();

  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new FrontendConfigurationError(
      "VITE_API_BASE_URL must be an absolute HTTP or HTTPS URL.",
    );
  }

  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new FrontendConfigurationError(
      "VITE_API_BASE_URL must use HTTP or HTTPS.",
    );
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new FrontendConfigurationError(
      "VITE_API_BASE_URL cannot include credentials, a query, or a fragment.",
    );
  }

  const path = parsed.pathname.replace(/\/+$/, "");
  return `${parsed.origin}${path}`;
}

export const apiBaseUrl = resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL);
