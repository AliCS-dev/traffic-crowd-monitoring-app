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
    const [url, request] = fetchFunction.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/health");
    expect((request.headers as Headers).get("Accept")).toBe("application/json");
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

  it("submits an image with supported analysis options", async () => {
    const fetchFunction = vi.fn().mockResolvedValue(
      jsonResponse({
        session_id: 12,
        status: "completed",
        result_url: "/api/analyses/12",
      }),
    );
    const client = new ApiClient("http://localhost:8000", fetchFunction);
    const file = new File(["image"], "aerial.jpg", { type: "image/jpeg" });

    await client.submitImage(file, {
      sessionName: "Morning traffic",
      gridRows: 3,
      gridColumns: 4,
    });

    const [url, request] = fetchFunction.mock.calls[0];
    const body = request.body as FormData;
    expect(url).toBe("http://localhost:8000/api/analyses/images");
    expect(request.method).toBe("POST");
    expect(body.get("image")).toEqual(file);
    expect(body.get("session_name")).toBe("Morning traffic");
    expect(body.get("grid_rows")).toBe("3");
    expect(body.get("grid_columns")).toBe("4");
    expect((request.headers as Headers).has("Content-Type")).toBe(false);
  });

  it("submits a video and reads its persistent job status", async () => {
    const fetchFunction = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          session_id: 21,
          status: "queued",
          job_url: "/api/analyses/videos/21",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          session_id: 21,
          status: "processing",
          progress_percent: 50,
        }),
      );
    const client = new ApiClient("http://localhost:8000", fetchFunction);
    const file = new File(["video"], "junction.mp4", { type: "video/mp4" });

    await client.submitVideo(file, {
      sessionName: null,
      gridRows: null,
      gridColumns: null,
      samplingIntervalSeconds: 2.5,
    });
    await client.getVideoJob(21);

    const videoBody = fetchFunction.mock.calls[0][1].body as FormData;
    expect(videoBody.get("video")).toEqual(file);
    expect(videoBody.get("sampling_interval_seconds")).toBe("2.5");
    expect(videoBody.has("session_name")).toBe(false);
    expect(fetchFunction.mock.calls[1][0]).toBe(
      "http://localhost:8000/api/analyses/videos/21",
    );
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
