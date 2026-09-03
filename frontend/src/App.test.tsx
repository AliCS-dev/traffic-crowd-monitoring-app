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

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementation((input: RequestInfo | URL) =>
          String(input).endsWith("/api/ready")
            ? Promise.resolve(readinessResponse())
            : Promise.resolve(healthResponse()),
        ),
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
