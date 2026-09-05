import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MonitoringSessionPage } from "../api/types.ts";
import { renderApplication } from "../test/render.tsx";
import { SessionsPage } from "./SessionsPage.tsx";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function sessionPage(
  overrides: Partial<MonitoringSessionPage> = {},
): MonitoringSessionPage {
  return {
    items: [
      {
        id: 42,
        session_name: "Morning interchange",
        source_type: "image",
        original_filename: "junction-aerial.jpg",
        status: "completed",
        started_at: "2026-09-05T08:30:00Z",
        completed_at: "2026-09-05T08:30:04Z",
      },
    ],
    pagination: {
      page: 1,
      page_size: 20,
      total_items: 1,
      total_pages: 1,
    },
    ...overrides,
  };
}

describe("SessionsPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(sessionPage())),
    );
  });

  it("shows a loading state while session history is pending", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    renderApplication(<SessionsPage />, "/sessions");

    expect(
      screen.getByRole("heading", { name: "Loading session history" }),
    ).toBeInTheDocument();
  });

  it("renders stored session metadata and a result link", async () => {
    renderApplication(<SessionsPage />, "/sessions");

    expect(
      await screen.findByRole("table", { name: "Monitoring sessions" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Morning interchange")).toBeInTheDocument();
    expect(screen.getByText(/junction-aerial\.jpg/)).toBeInTheDocument();
    expect(screen.getByText("Image")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText(/2026/).closest("time")).toHaveAttribute(
      "datetime",
      "2026-09-05T08:30:00Z",
    );
    expect(
      screen.getByRole("link", { name: "Open Morning interchange" }),
    ).toHaveAttribute("href", "/analyses/42");
  });

  it("requests the selected history page", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const secondPage = String(input).includes("page=2");
      return Promise.resolve(
        jsonResponse(
          sessionPage({
            items: [
              {
                id: secondPage ? 21 : 1,
                session_name: secondPage
                  ? "Second page session"
                  : "First page session",
                source_type: "video",
                original_filename: "traffic.mp4",
                status: "processing",
                started_at: "2026-09-05T08:30:00Z",
                completed_at: null,
              },
            ],
            pagination: {
              page: secondPage ? 2 : 1,
              page_size: 20,
              total_items: 21,
              total_pages: 2,
            },
          }),
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApplication(<SessionsPage />, "/sessions");

    await screen.findByText("First page session");
    await user.click(screen.getByRole("button", { name: "Go to page 2" }));

    expect(await screen.findByText("Second page session")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining("/api/analyses?page=2&page_size=20"),
      expect.any(Object),
    );
  });

  it("shows the empty state when no sessions have been stored", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          sessionPage({
            items: [],
            pagination: {
              page: 1,
              page_size: 20,
              total_items: 0,
              total_pages: 0,
            },
          }),
        ),
      ),
    );

    renderApplication(<SessionsPage />, "/sessions");

    expect(
      await screen.findByRole("heading", { name: "No sessions available" }),
    ).toBeInTheDocument();
  });

  it("retries after the session-history API is unavailable", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Offline"))
      .mockResolvedValueOnce(
        jsonResponse(
          sessionPage({
            items: [],
            pagination: {
              page: 1,
              page_size: 20,
              total_items: 0,
              total_pages: 0,
            },
          }),
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    renderApplication(<SessionsPage />, "/sessions");

    await user.click(await screen.findByRole("button", { name: "Retry" }));

    expect(
      await screen.findByRole("heading", { name: "No sessions available" }),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
