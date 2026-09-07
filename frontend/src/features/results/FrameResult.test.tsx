import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { gridResultFixture } from "../../test/analysisResultFixture.ts";
import { renderApplication } from "../../test/render.tsx";
import { FrameResult } from "./FrameResult.tsx";
import { hasAlignedGridCoordinates } from "./gridGeometry.ts";
import { VideoResult } from "./VideoResult.tsx";

function loadImage() {
  fireEvent.load(screen.getByRole("img", { hidden: true }));
}

describe("grid inspection", () => {
  it("selects a stored cell without adding its counts to the whole frame or filtering detection records", async () => {
    const user = userEvent.setup();
    const frame = gridResultFixture().frames[0];
    renderApplication(<FrameResult frame={frame} filename="junction.jpg" />);
    expect(
      screen.queryByRole("group", { name: "Image grid" }),
    ).not.toBeInTheDocument();
    loadImage();
    const grid = screen.getByRole("group", { name: "Image grid" });
    expect(within(grid).getAllByRole("button")).toHaveLength(4);
    const cell = within(grid).getByRole("button", { name: "Row 1, column 2" });
    expect(cell).toHaveStyle({
      left: "50%",
      top: "0%",
      width: "50%",
      height: "50%",
    });
    await user.click(cell);
    expect(cell).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox", { name: "Grid cell" })).toHaveValue(
      "51",
    );
    const counts = screen.getByRole("table", {
      name: "Selected-cell object counts",
    });
    expect(within(counts).getByText("Person")).toBeInTheDocument();
    expect(within(counts).getByText("2")).toBeInTheDocument();
    expect(within(counts).queryByText("Car or van")).not.toBeInTheDocument();
    const whole = screen.getByRole("table", {
      name: "Whole-image object counts",
    });
    expect(within(whole).getAllByRole("row")).toHaveLength(3);
    expect(within(whole).getByText("1")).toBeInTheDocument();
    expect(within(whole).getByText("2")).toBeInTheDocument();
    expect(
      within(
        screen.getByRole("table", { name: "Whole-frame detection records" }),
      ).getAllByRole("row"),
    ).toHaveLength(4);
  });

  it("supports keyboard selection, hiding the grid, and clearing selection", async () => {
    const user = userEvent.setup();
    renderApplication(
      <FrameResult
        frame={gridResultFixture().frames[0]}
        filename="junction.jpg"
      />,
    );
    loadImage();
    const cell = screen.getByRole("button", { name: "Row 1, column 1" });
    cell.focus();
    await user.keyboard("{Enter}");
    expect(cell).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByLabelText("Grid overlay"));
    expect(
      screen.queryByRole("group", { name: "Image grid" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: "Selected-cell object counts" }),
    ).toBeInTheDocument();
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Grid cell" }),
      "51",
    );
    await user.click(screen.getByLabelText("Grid overlay"));
    expect(
      screen.getByRole("button", { name: "Row 1, column 2" }),
    ).toHaveAttribute("aria-pressed", "true");
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Grid cell" }),
      "",
    );
    expect(screen.getByText("No grid cell selected.")).toBeInTheDocument();
    expect(
      screen.queryByRole("table", { name: "Selected-cell object counts" }),
    ).not.toBeInTheDocument();
  });

  it("distinguishes empty summaries from an explicitly stored zero", async () => {
    const user = userEvent.setup();
    const frame = gridResultFixture().frames[0];
    frame.grid_cells[3].summaries = [
      { ...frame.frame_summaries[0], object_count: 0 },
    ];
    renderApplication(<FrameResult frame={frame} filename="junction.jpg" />);
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Grid cell" }),
      "52",
    );
    expect(
      screen.getByText("No class counts were recorded for this cell."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("table", { name: "Selected-cell object counts" }),
    ).not.toBeInTheDocument();
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Grid cell" }),
      "53",
    );
    expect(
      within(
        screen.getByRole("table", { name: "Selected-cell object counts" }),
      ).getByText("0"),
    ).toBeInTheDocument();
  });

  it.each(["missing", "failed"])(
    "keeps cell selection available when the image is %s",
    async (state) => {
      const user = userEvent.setup();
      const frame = gridResultFixture().frames[0];
      if (state === "missing") frame.visual_asset = null;
      renderApplication(<FrameResult frame={frame} filename="junction.jpg" />);
      if (state === "failed")
        fireEvent.error(screen.getByRole("img", { hidden: true }));
      expect(screen.getByText("Result image unavailable")).toBeInTheDocument();
      expect(
        screen.queryByRole("group", { name: "Image grid" }),
      ).not.toBeInTheDocument();
      await user.selectOptions(
        screen.getByRole("combobox", { name: "Grid cell" }),
        "50",
      );
      expect(
        within(
          screen.getByRole("table", { name: "Selected-cell object counts" }),
        ).getByText("1"),
      ).toBeInTheDocument();
    },
  );

  it("does not invent a grid for a legacy result", () => {
    const frame = gridResultFixture().frames[0];
    frame.grid_cells = [];
    renderApplication(<FrameResult frame={frame} filename="junction.jpg" />);
    loadImage();
    expect(
      screen.getByText("No grid was stored for this frame."),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Grid overlay")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: "Grid cell" }),
    ).not.toBeInTheDocument();
  });

  it("keeps stored counts but disables spatial overlays when coordinates mismatch", async () => {
    const user = userEvent.setup();
    const frame = gridResultFixture().frames[0];
    frame.coordinate_space!.width = 640;
    renderApplication(<FrameResult frame={frame} filename="junction.jpg" />);
    loadImage();
    expect(
      screen.getByText(/stored coordinates do not match/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("group", { name: "Image grid" }),
    ).not.toBeInTheDocument();
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Grid cell" }),
      "50",
    );
    expect(
      screen.getByRole("table", { name: "Selected-cell object counts" }),
    ).toBeInTheDocument();
  });

  it("resets cell selection when moving between sampled frames", async () => {
    const user = userEvent.setup();
    const first = gridResultFixture().frames[0];
    first.frame_timestamp_seconds = 0;
    const second = structuredClone(first);
    second.id = 21;
    second.frame_number = 30;
    second.frame_timestamp_seconds = 1;
    renderApplication(
      <VideoResult frames={[first, second]} filename="junction.mp4" />,
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Grid cell" }),
      "50",
    );
    await user.click(
      screen.getByRole("button", { name: "Next sampled frame" }),
    );
    expect(screen.getByRole("combobox", { name: "Grid cell" })).toHaveValue("");
    expect(screen.getByText("No grid cell selected.")).toBeInTheDocument();
  });
});

describe("overlay coordinates", () => {
  it("accepts fractional bounds without rebuilding uniform cells", () => {
    const frame = gridResultFixture().frames[0];
    frame.grid_cells[0].bounds.x_max = 123.25;
    expect(hasAlignedGridCoordinates(frame)).toBe(true);
    renderApplication(<FrameResult frame={frame} filename="junction.jpg" />);
    loadImage();
    expect(screen.getByRole("button", { name: "Row 1, column 1" })).toHaveStyle(
      { width: `${(123.25 / 1280) * 100}%` },
    );
  });

  it.each(["missing", "dimensions", "outside", "zero-area", "not-finite"])(
    "rejects %s coordinate metadata",
    (kind) => {
      const frame = gridResultFixture().frames[0];
      if (kind === "missing") frame.coordinate_space = null;
      if (kind === "dimensions") frame.image_height = 360;
      if (kind === "outside") frame.grid_cells[0].bounds.x_max = 1300;
      if (kind === "zero-area") frame.grid_cells[0].bounds.x_max = 0;
      if (kind === "not-finite") frame.grid_cells[0].bounds.y_min = NaN;
      expect(hasAlignedGridCoordinates(frame)).toBe(false);
    },
  );
});
