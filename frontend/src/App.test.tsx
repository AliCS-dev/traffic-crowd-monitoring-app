import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.tsx";
import { renderApplication } from "./test/render.tsx";

function healthResponse(): Response {
  return new Response(
    JSON.stringify({
      status: "ok",
      service: "Traffic and Crowd Monitoring API",
      version: "0.1.0",
    }),
    { headers: { "content-type": "application/json" } },
  );
}

function readinessResponse(): Response {
  return new Response(
    JSON.stringify({
      status: "ready",
      checks: {
        database: { status: "ready" },
        detector_checkpoint: { status: "ready" },
      },
    }),
    { headers: { "content-type": "application/json" } },
  );
}

function capabilitiesResponse(): Response {
  return new Response(
    JSON.stringify({
      image: {
        extensions: [".jpg", ".jpeg", ".png"],
        mime_types: ["image/jpeg", "image/png"],
        mime_type_by_extension: {
          ".jpg": "image/jpeg",
          ".jpeg": "image/jpeg",
          ".png": "image/png",
        },
        max_upload_bytes: 10 * 1024 * 1024,
        max_pixels: 40_000_000,
      },
      video: {
        extensions: [".avi", ".mkv", ".mov", ".mp4"],
        mime_types: [
          "video/x-msvideo",
          "video/x-matroska",
          "video/quicktime",
          "video/mp4",
        ],
        mime_type_by_extension: {
          ".avi": "video/x-msvideo",
          ".mkv": "video/x-matroska",
          ".mov": "video/quicktime",
          ".mp4": "video/mp4",
        },
        max_upload_bytes: 500 * 1024 * 1024,
        max_pixels: 40_000_000,
      },
      options: {
        max_session_name_length: 150,
        max_grid_dimension: 20,
        default_sampling_interval_seconds: 1,
        max_sampling_interval_seconds: 3600,
      },
    }),
    { headers: { "content-type": "application/json" } },
  );
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/ready")) {
          return Promise.resolve(readinessResponse());
        }
        if (url.endsWith("/api/capabilities")) {
          return Promise.resolve(capabilitiesResponse());
        }
        return Promise.resolve(healthResponse());
      }),
    );
  });

  it("opens on the monitoring workspace", async () => {
    renderApplication(<App />);

    expect(
      await screen.findByRole("heading", { name: "Analysis workspace" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "Primary navigation" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Backend online")).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "New analysis" }),
    ).toBeInTheDocument();
  });

  it("navigates to session history with the keyboard-accessible link", async () => {
    const user = userEvent.setup();
    renderApplication(<App />, "/workspace");

    const sessionsLink = screen.getByRole("link", { name: "Sessions" });
    sessionsLink.focus();
    expect(sessionsLink).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(
      await screen.findByRole("heading", { name: "Session history" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: "Monitoring sessions" }),
    ).toBeInTheDocument();
  });

  it("shows live dependency readiness in the workspace", async () => {
    const user = userEvent.setup();
    renderApplication(<App />, "/workspace");

    await user.click(screen.getByRole("tab", { name: "System readiness" }));

    expect(
      await screen.findByRole("table", {
        name: "Application dependency readiness",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Database")).toBeInTheDocument();
    expect(screen.getByText("Detector Checkpoint")).toBeInTheDocument();
  });

  it("reports an unavailable backend without hiding the workspace", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Offline")));
    renderApplication(<App />, "/workspace");

    expect(await screen.findByText("Backend unavailable")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Analysis workspace" }),
    ).toBeInTheDocument();
  });

  it("submits an image and opens its result route", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(globalThis.fetch);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/capabilities")) {
        return Promise.resolve(capabilitiesResponse());
      }
      if (url.endsWith("/api/analyses/images")) {
        return Promise.resolve(
          jsonResponse(
            {
              session_id: 12,
              status: "completed",
              result_url: "/api/analyses/12",
              output_asset_id: "683bfb20-e02c-4988-aa8c-cab38c169771",
              detection_count: 8,
              grid_rows: null,
              grid_columns: null,
              dense_crowd_analysis: {},
            },
            201,
          ),
        );
      }
      return Promise.resolve(healthResponse());
    });
    renderApplication(<App />, "/workspace");

    const file = new File(["image"], "junction.jpg", {
      type: "image/jpeg",
    });
    await user.upload(await screen.findByLabelText("Choose image file"), file);
    await user.type(screen.getByLabelText("Session name"), "Morning traffic");
    await user.click(screen.getByRole("button", { name: "Start analysis" }));

    expect(
      await screen.findByRole("heading", { name: "Analysis 12" }),
    ).toBeInTheDocument();
    const submission = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith("/api/analyses/images"),
    );
    const body = submission?.[1]?.body as FormData;
    expect(body.get("image")).toEqual(file);
    expect(body.get("session_name")).toBe("Morning traffic");
  });

  it("polls an accepted video and opens its completed result", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(globalThis.fetch);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/capabilities")) {
        return Promise.resolve(capabilitiesResponse());
      }
      if (url.endsWith("/api/analyses/videos")) {
        return Promise.resolve(
          jsonResponse(
            {
              session_id: 21,
              status: "queued",
              job_url: "/api/analyses/videos/21",
              result_url: "/api/analyses/21",
              sampled_frames_total: 4,
              sampling_interval_seconds: 1,
              grid_rows: null,
              grid_columns: null,
            },
            202,
          ),
        );
      }
      if (url.endsWith("/api/analyses/videos/21")) {
        return Promise.resolve(
          jsonResponse({
            session_id: 21,
            status: "completed",
            sampling_interval_seconds: 1,
            grid_rows: null,
            grid_columns: null,
            total_source_frames: 120,
            sampled_frames_total: 4,
            sampled_frames_processed: 4,
            progress_percent: 100,
            failure_code: null,
            failure_message: null,
            queued_at: "2026-09-04T10:00:00Z",
            started_at: "2026-09-04T10:00:01Z",
            finished_at: "2026-09-04T10:00:02Z",
          }),
        );
      }
      return Promise.resolve(healthResponse());
    });
    renderApplication(<App />, "/workspace");

    await user.click(await screen.findByRole("button", { name: "Video" }));
    await user.upload(
      screen.getByLabelText("Choose video file"),
      new File(["video"], "roundabout.mp4", { type: "video/mp4" }),
    );
    await user.click(screen.getByRole("button", { name: "Start analysis" }));

    expect(
      await screen.findByRole("heading", { name: "Analysis 21" }),
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).endsWith("/api/analyses/videos/21"),
      ),
    ).toBe(true);
  });

  it("keeps the form values after a safe API failure", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(globalThis.fetch);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/capabilities")) {
        return Promise.resolve(capabilitiesResponse());
      }
      if (url.endsWith("/api/analyses/images")) {
        return Promise.resolve(
          jsonResponse(
            {
              error: {
                code: "invalid_image",
                message: "The uploaded image could not be decoded.",
              },
            },
            422,
          ),
        );
      }
      return Promise.resolve(healthResponse());
    });
    renderApplication(<App />, "/workspace");

    const longName = `${"junction-".repeat(20)}view.jpg`;
    await user.upload(
      await screen.findByLabelText("Choose image file"),
      new File(["image"], longName, { type: "image/jpeg" }),
    );
    await user.type(screen.getByLabelText("Session name"), "Evening run");
    await user.click(screen.getByRole("button", { name: "Start analysis" }));

    expect(await screen.findByText("Analysis failed")).toBeInTheDocument();
    expect(
      screen.getByText("The uploaded image could not be decoded."),
    ).toBeInTheDocument();
    expect(screen.getByText(longName)).toBeInTheDocument();
    expect(screen.getByLabelText("Session name")).toHaveValue("Evening run");
    expect(
      screen.getByRole("button", { name: "Start analysis" }),
    ).toBeEnabled();
  });

  it("stops a pending browser request without claiming server cancellation", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(globalThis.fetch);
    fetchMock.mockImplementation(
      (input: RequestInfo | URL, request?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/api/capabilities")) {
          return Promise.resolve(capabilitiesResponse());
        }
        if (url.endsWith("/api/analyses/images")) {
          return new Promise<Response>((_, reject) => {
            request?.signal?.addEventListener("abort", () => {
              reject(new DOMException("Request aborted", "AbortError"));
            });
          });
        }
        return Promise.resolve(healthResponse());
      },
    );
    renderApplication(<App />, "/workspace");

    await user.upload(
      await screen.findByLabelText("Choose image file"),
      new File(["image"], "junction.jpg", { type: "image/jpeg" }),
    );
    await user.click(screen.getByRole("button", { name: "Start analysis" }));
    await user.click(
      await screen.findByRole("button", { name: "Stop waiting" }),
    );

    expect(
      await screen.findByText("Browser request stopped"),
    ).toBeInTheDocument();
    expect(screen.getByText("junction.jpg")).toBeInTheDocument();
    expect(
      screen.getByText(/server may already have accepted the request/i),
    ).toBeInTheDocument();
  });

  it("opens and closes application information", async () => {
    const user = userEvent.setup();
    renderApplication(<App />, "/workspace");

    await user.click(
      screen.getByRole("button", { name: "Application information" }),
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("shows an explicit error for an invalid result route", async () => {
    renderApplication(<App />, "/analyses/not-a-number");

    expect(
      await screen.findByRole("heading", {
        name: "Invalid analysis reference",
      }),
    ).toBeInTheDocument();
  });

  it("navigates to a positive session ID from the result lookup", async () => {
    const user = userEvent.setup();
    renderApplication(<App />, "/analyses");

    const input = await screen.findByRole("textbox", { name: "Session ID" });
    await user.type(input, "12");
    await user.click(screen.getByRole("button", { name: "Find" }));

    expect(
      await screen.findByRole("heading", { name: "Analysis 12" }),
    ).toBeInTheDocument();
  });

  it("handles unknown routes", async () => {
    renderApplication(<App />, "/missing");

    expect(
      await screen.findByRole("heading", { name: "Page not found" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Return to workspace" }),
    ).toHaveAttribute("href", "/workspace");
  });
});
