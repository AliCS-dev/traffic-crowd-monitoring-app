import { describe, expect, it, vi } from "vitest";

import { ApiClient, ApiRequestError } from "./client.ts";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("ApiClient", () => {
  it("reads the typed health endpoint", async () => {
    const fetchFunction = vi.fn().mockResolvedValue(
      jsonResponse({
        status: "ok",
        service: "Traffic and Crowd Monitoring API",
        version: "0.1.0",
      }),
    );
    const client = new ApiClient("http://localhost:8000", fetchFunction);

    await expect(client.getHealth()).resolves.toMatchObject({ status: "ok" });
    expect(fetchFunction).toHaveBeenCalledWith(
      "http://localhost:8000/api/health",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
  });

  it("returns readiness details when the API reports 503", async () => {
    const client = new ApiClient(
      "http://localhost:8000",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            status: "not_ready",
            checks: { database: { status: "not_ready" } },
          },
          503,
        ),
      ),
    );

    await expect(client.getReadiness()).resolves.toEqual({
      status: "not_ready",
      checks: { database: { status: "not_ready" } },
    });
  });

  it("preserves structured API error details", async () => {
    const client = new ApiClient(
      "http://localhost:8000",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(
            { error: { code: "service_failure", message: "Service failed." } },
            500,
          ),
        ),
    );

    const request = client.getHealth();
    await expect(request).rejects.toMatchObject({
      status: 500,
      code: "service_failure",
      message: "Service failed.",
    });
    await expect(request).rejects.toBeInstanceOf(ApiRequestError);
  });

  it("uses a stable fallback for non-JSON failures", async () => {
    const client = new ApiClient(
      "http://localhost:8000",
      vi.fn().mockResolvedValue(new Response("", { status: 502 })),
    );

    await expect(client.getHealth()).rejects.toMatchObject({
      status: 502,
      code: "api_request_failed",
    });
  });
});
