import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  alertFixture,
  alertResultFixture,
} from "../../test/alertResultFixture.ts";
import { renderApplication } from "../../test/render.tsx";
import { FrameAlerts } from "./FrameAlerts.tsx";
import { FrameResult } from "./FrameResult.tsx";
import { VideoResult } from "./VideoResult.tsx";

function field(record: HTMLElement, label: string) {
  return within(record).getByText(label, { selector: "dt" }).nextElementSibling;
}

describe("recorded threshold events", () => {
  it("shows stored values, boundaries, severity and scope with explicit limitations", () => {
    const frame = alertResultFixture().frames[0];
    renderApplication(
      <FrameAlerts
        alerts={frame.alerts}
        cells={frame.grid_cells}
        onSelectCell={vi.fn()}
      />,
    );
    const event = screen.getByRole("article", {
      name: "frame-car-or-van-warning",
    });
    expect(field(event, "Measured value")).toHaveTextContent("20");
    expect(field(event, "Threshold")).toHaveTextContent("20");
    expect(field(event, "Comparison")).toHaveTextContent(
      "Greater than or equal (>=)",
    );
    expect(field(event, "Scope")).toHaveTextContent("Whole frame");
    expect(field(event, "Class")).toHaveTextContent("Car or van");
    expect(field(event, "Method")).toHaveTextContent("Detector object count");
    expect(
      within(event).getByText("Rule severity: Warning"),
    ).toBeInTheDocument();
    expect(
      within(event).getByText("No resolution recorded"),
    ).toBeInTheDocument();
    expect(screen.getByText(/not verified congestion/)).toBeInTheDocument();
    expect(
      screen.getByText(/rule severity is not an assessment/),
    ).toBeInTheDocument();
  });

  it("preserves strict comparisons, zero measurements, and recorded resolution timestamps", () => {
    const event = alertFixture({
      comparison_operator: "greater_than",
      measured_value: 0,
      severity: "critical",
      resolved_at: "2026-09-08T10:00:00Z",
    });
    renderApplication(
      <FrameAlerts alerts={[event]} cells={[]} onSelectCell={vi.fn()} />,
    );
    const record = screen.getByRole("article");
    expect(field(record, "Measured value")).toHaveTextContent(/^0$/);
    expect(field(record, "Comparison")).toHaveTextContent("Greater than (>)");
    expect(
      within(record).getByText("Rule severity: Critical"),
    ).toBeInTheDocument();
    expect(
      record.querySelector('time[datetime="2026-09-08T10:00:00Z"]'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("No resolution recorded"),
    ).not.toBeInTheDocument();
  });

  it("keeps older records with missing metadata without inferring rules from their message", async () => {
    const user = userEvent.setup();
    const event = alertFixture({
      analysis_method: null,
      object_class: null,
      scope: null,
      comparison_operator: null,
      measured_value: null,
      threshold_value: null,
      grid_cell_id: 99,
      message: "Legacy message: count exceeded 10.",
    });
    renderApplication(
      <FrameAlerts alerts={[event]} cells={[]} onSelectCell={vi.fn()} />,
    );
    const record = screen.getByRole("article");
    expect(within(record).getAllByText("Not recorded")).toHaveLength(6);
    expect(
      within(record).getByText("Stored grid-cell reference: 99"),
    ).toBeInTheDocument();
    await user.click(
      within(record).getByText("Stored message (original cell indices)"),
    );
    expect(record.querySelector("details")).toHaveAttribute("open");
    expect(within(record).getByText(event.message)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /Inspect/ }),
    ).not.toBeInTheDocument();
  });

  it("identifies missing referenced cells without selecting another cell", () => {
    const frame = alertResultFixture().frames[0];
    const orphan = alertFixture({ scope: "grid_cell", grid_cell_id: 999 });
    renderApplication(
      <FrameAlerts
        alerts={[orphan]}
        cells={frame.grid_cells}
        onSelectCell={vi.fn()}
      />,
    );
    expect(field(screen.getByRole("article"), "Scope")).toHaveTextContent(
      "Grid cell 999 (unavailable)",
    );
    expect(
      screen.queryByRole("button", { name: /Inspect/ }),
    ).not.toBeInTheDocument();
  });

  it("keeps all events visible while filtering tables and inspecting a referenced cell", async () => {
    const user = userEvent.setup();
    const frame = alertResultFixture().frames[0];
    frame.visual_asset = null;
    renderApplication(<FrameResult frame={frame} filename="junction.jpg" />);
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Table class" }),
      "car_or_van",
    );
    await user.click(
      screen.getByRole("button", { name: "Inspect row 1, column 2" }),
    );
    const selector = screen.getByRole("combobox", { name: "Grid cell" });
    expect(selector).toHaveValue("51");
    expect(selector).toHaveFocus();
    expect(screen.getByRole("combobox", { name: "Table class" })).toHaveValue(
      "car_or_van",
    );
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expect(
      field(
        screen.getByRole("article", { name: "grid-person-information" }),
        "Measured value",
      ),
    ).toHaveTextContent("8");
    expect(
      screen.getByText("No stored count summary matches Car or van."),
    ).toBeInTheDocument();
  });

  it("does not interpret no recorded alerts as safety or successful rule evaluation", () => {
    renderApplication(
      <FrameAlerts alerts={[]} cells={[]} onSelectCell={vi.fn()} />,
    );
    expect(
      screen.getByText(
        "No alerts were recorded for this frame. Rule evaluation status is not recorded.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
  });

  it("sorts by recorded time then ID, paginates, and does not mutate the response", async () => {
    const user = userEvent.setup();
    const alerts = Array.from({ length: 6 }, (_, index) =>
      alertFixture({
        id: 70 + index,
        alert_type: `rule-${index}`,
        created_at:
          index === 0 ? "2026-09-08T12:00:00Z" : "2026-09-07T09:30:00Z",
      }),
    );
    const original = structuredClone(alerts);
    renderApplication(
      <FrameAlerts alerts={alerts} cells={[]} onSelectCell={vi.fn()} />,
    );
    expect(
      screen
        .getAllByRole("article")
        .map((record) => within(record).getByRole("heading").textContent),
    ).toEqual(["rule-0", "rule-5", "rule-4", "rule-3", "rule-2"]);
    await user.click(screen.getByRole("button", { name: "Go to page 2" }));
    expect(screen.getByRole("article", { name: "rule-1" })).toBeInTheDocument();
    expect(screen.getByText("6-6 of 6 events")).toBeInTheDocument();
    expect(alerts).toEqual(original);
  });

  it("changes the event list and resets pagination when switching sampled frames", async () => {
    const user = userEvent.setup();
    const first = alertResultFixture().frames[0];
    first.frame_timestamp_seconds = 0;
    first.alerts = Array.from({ length: 6 }, (_, index) =>
      alertFixture({ id: 70 + index, alert_type: `first-${index}` }),
    );
    const second = {
      ...structuredClone(first),
      id: 21,
      frame_number: 30,
      frame_timestamp_seconds: 1,
      alerts: [alertFixture({ id: 90, alert_type: "second-frame-event" })],
    };
    renderApplication(
      <VideoResult frames={[first, second]} filename="junction.mp4" />,
    );
    await user.click(screen.getByRole("button", { name: "Go to page 2" }));
    await user.click(
      screen.getByRole("button", { name: "Next sampled frame" }),
    );
    expect(
      screen.getByRole("article", { name: "second-frame-event" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("navigation", { name: "Alert pages" }),
    ).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Previous sampled frame" }),
    );
    expect(screen.getByText("1-5 of 6 events")).toBeInTheDocument();
  });
});
