import { useState } from "react";
import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { gridResultFixture } from "../../test/analysisResultFixture.ts";
import { renderApplication } from "../../test/render.tsx";
import { FrameResult } from "./FrameResult.tsx";
import { VideoResult } from "./VideoResult.tsx";

describe("result class filters", () => {
  it("filters all three tables without changing stored counts, images, or cell selection", async () => {
    const user = userEvent.setup();
    const frame = gridResultFixture().frames[0];
    const original = structuredClone(frame);
    renderApplication(<FrameResult frame={frame} filename="junction.jpg" />);
    const image = screen.getByRole("img", { hidden: true });
    const imageUrl = image.getAttribute("src");
    fireEvent.load(image);
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Grid cell" }),
      "51",
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Table class" }),
      "person",
    );
    for (const name of [
      "Whole-image object counts",
      "Selected-cell object counts",
    ]) {
      const counts = screen.getByRole("table", { name });
      expect(within(counts).getByText("Person")).toBeInTheDocument();
      expect(within(counts).getByText("2")).toBeInTheDocument();
      expect(within(counts).queryByText("Car or van")).not.toBeInTheDocument();
    }
    const records = screen.getByRole("table", {
      name: "Whole-frame detection records",
    });
    expect(within(records).getAllByRole("row")).toHaveLength(3);
    expect(
      screen.getByText("3 stored detections (all classes)"),
    ).toBeInTheDocument();
    expect(image).toHaveAttribute("src", imageUrl);
    expect(
      screen.getByText(/Saved detection overlay: all classes/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Row 1, column 2" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(frame).toEqual(original);
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Table class" }),
      "",
    );
    expect(
      within(
        screen.getByRole("table", { name: "Whole-image object counts" }),
      ).getByText("Car or van"),
    ).toBeInTheDocument();
  });

  it("distinguishes a cell with no class match from a cell with no recorded summaries", async () => {
    const user = userEvent.setup();
    renderApplication(
      <FrameResult
        frame={gridResultFixture().frames[0]}
        filename="junction.jpg"
      />,
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Grid cell" }),
      "50",
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Table class" }),
      "person",
    );
    expect(
      screen.getByText("No stored count summary matches Person."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("table", { name: "Selected-cell object counts" }),
    ).not.toBeInTheDocument();
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Grid cell" }),
      "52",
    );
    expect(
      screen.getByText("No class counts were recorded for this cell."),
    ).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Table class" })).toHaveValue(
      "person",
    );
  });

  it("includes classes recorded only in summaries and does not recount them from detections", async () => {
    const user = userEvent.setup();
    const frame = gridResultFixture().frames[0];
    frame.grid_cells[0].summaries.push({
      ...frame.frame_summaries[0],
      id: 90,
      object_class: "truck",
      object_count: 4,
    });
    frame.frame_summaries.push({
      ...frame.frame_summaries[0],
      id: 91,
      object_class: "bus",
      object_count: 0,
    });
    frame.detections.push({
      ...frame.detections[0],
      id: 92,
      object_class: "train",
    });
    renderApplication(<FrameResult frame={frame} filename="junction.jpg" />);
    const select = screen.getByRole("combobox", { name: "Table class" });
    expect(
      within(select)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["All classes", "Bus", "Car or van", "Person", "Train", "Truck"]);
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Grid cell" }),
      "50",
    );
    await user.selectOptions(select, "truck");
    expect(
      screen.getByText("No stored detections match Truck."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No stored count summary matches Truck."),
    ).toBeInTheDocument();
    expect(
      within(
        screen.getByRole("table", { name: "Selected-cell object counts" }),
      ).getByText("4"),
    ).toBeInTheDocument();
    await user.selectOptions(select, "bus");
    expect(
      within(
        screen.getByRole("table", { name: "Whole-image object counts" }),
      ).getByText("0"),
    ).toBeInTheDocument();
  });

  it("resets detection pagination when applying or clearing a class filter", async () => {
    const user = userEvent.setup();
    const frame = gridResultFixture().frames[0];
    frame.detections = [
      ...Array.from({ length: 21 }, (_, index) => ({
        ...frame.detections[0],
        id: 100 + index,
      })),
      ...frame.detections.slice(1),
    ];
    renderApplication(<FrameResult frame={frame} filename="junction.jpg" />);
    await user.click(screen.getByRole("button", { name: "Go to page 2" }));
    expect(screen.getByText("21-23 of 23 detections")).toBeInTheDocument();
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Table class" }),
      "person",
    );
    expect(screen.getByText("1-2 of 2 detections")).toBeInTheDocument();
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Table class" }),
      "",
    );
    expect(screen.getByText("1-20 of 23 detections")).toBeInTheDocument();
  });

  it("works without a result image", async () => {
    const user = userEvent.setup();
    const frame = gridResultFixture().frames[0];
    frame.visual_asset = null;
    renderApplication(<FrameResult frame={frame} filename="junction.jpg" />);
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Table class" }),
      "person",
    );
    expect(screen.getByText("Result image unavailable")).toBeInTheDocument();
    expect(screen.getByText("1-2 of 2 detections")).toBeInTheDocument();
  });

  it("disables the selector when no classes were recorded", () => {
    const frame = gridResultFixture().frames[0];
    frame.detections = [];
    frame.frame_summaries = [];
    frame.grid_cells = [];
    renderApplication(<FrameResult frame={frame} filename="junction.jpg" />);
    expect(
      screen.getByRole("combobox", { name: "Table class" }),
    ).toBeDisabled();
    expect(
      screen.getByText("No detections were stored for this frame."),
    ).toBeInTheDocument();
  });

  it("keeps an active filter explicit if refreshed records no longer contain that class", async () => {
    const user = userEvent.setup();
    function RefreshedResult() {
      const [frame, setFrame] = useState(gridResultFixture().frames[0]);
      return (
        <>
          <button
            onClick={() =>
              setFrame({
                ...frame,
                detections: frame.detections.filter(
                  (record) => record.object_class !== "person",
                ),
                frame_summaries: frame.frame_summaries.filter(
                  (record) => record.object_class !== "person",
                ),
                grid_cells: [],
              })
            }
          >
            Refresh fixture
          </button>
          <FrameResult frame={frame} filename="junction.jpg" />
        </>
      );
    }
    renderApplication(<RefreshedResult />);
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Table class" }),
      "person",
    );
    await user.click(screen.getByRole("button", { name: "Refresh fixture" }));
    expect(screen.getByRole("combobox", { name: "Table class" })).toHaveValue(
      "person",
    );
    expect(
      screen.getByText("No stored detections match Person."),
    ).toBeInTheDocument();
  });

  it("resets the table class when moving to another sampled frame", async () => {
    const user = userEvent.setup();
    const first = gridResultFixture().frames[0];
    first.frame_timestamp_seconds = 0;
    const second = {
      ...structuredClone(first),
      id: 21,
      frame_number: 30,
      frame_timestamp_seconds: 1,
    };
    renderApplication(
      <VideoResult frames={[first, second]} filename="junction.mp4" />,
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Table class" }),
      "person",
    );
    await user.click(
      screen.getByRole("button", { name: "Next sampled frame" }),
    );
    expect(screen.getByRole("combobox", { name: "Table class" })).toHaveValue(
      "",
    );
    expect(
      within(
        screen.getByRole("table", { name: "Whole-frame object counts" }),
      ).getByText("Car or van"),
    ).toBeInTheDocument();
  });
});
