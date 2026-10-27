import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { gridResultFixture } from "../../test/analysisResultFixture.ts";
import { renderApplication } from "../../test/render.tsx";
import { FrameResult } from "./FrameResult.tsx";

function cleanFrame() {
  const frame = gridResultFixture().frames[0];
  frame.source_asset = {
    ...frame.visual_asset!,
    url: `${frame.visual_asset!.url}/source`,
    rendered_overlays: [],
  };
  return frame;
}

describe("interactive scene", () => {
  it("does not report visible boxes while media is loading or unavailable", () => {
    renderApplication(
      <FrameResult frame={cleanFrame()} filename="junction.jpg" />,
    );
    expect(screen.getByText("0 visible boxes")).toBeVisible();
    fireEvent.error(screen.getByRole("img", { hidden: true }));
    expect(screen.getByText("0 visible boxes")).toBeVisible();
    expect(screen.getByText("Result image unavailable")).toBeVisible();
    expect(screen.getByText("1-3 of 3 detections")).toBeVisible();
  });

  it("rejects media whose decoded dimensions do not match the stored coordinates", () => {
    renderApplication(
      <FrameResult frame={cleanFrame()} filename="junction.jpg" />,
    );
    const image = screen.getByRole("img", { hidden: true });
    Object.defineProperty(image, "naturalWidth", { value: 100 });
    Object.defineProperty(image, "naturalHeight", { value: 50 });
    fireEvent.load(image);
    expect(screen.getByText("Result image unavailable")).toBeVisible();
    expect(
      screen.queryByRole("group", { name: "Detection overlays" }),
    ).not.toBeInTheDocument();
  });
  it("links box selection to its record and inspector without changing stored data", async () => {
    const user = userEvent.setup();
    const frame = cleanFrame();
    const before = structuredClone(frame);
    renderApplication(<FrameResult frame={frame} filename="junction.jpg" />);
    const image = screen.getByRole("img", { hidden: true });
    expect(image).toHaveAttribute("src", expect.stringContaining("/source"));
    fireEvent.load(image);
    const record = frame.detections[0];
    const box = screen.getByRole("button", {
      name: new RegExp(`^Detection ${record.id}:`),
    });
    await user.click(box);
    expect(box).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByRole("button", { name: `Inspect detection ${record.id}` }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      within(
        screen.getByRole("complementary", { name: "Selection inspector" }),
      ).getByText(`Detection ${record.id}`),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Row 1, column 2" }));
    expect(box).toHaveAttribute("aria-pressed", "false");
    expect(frame).toEqual(before);
  });

  it("filters overlays and records while preserving summaries and alerts", async () => {
    const user = userEvent.setup();
    const frame = cleanFrame();
    const before = structuredClone(frame);
    renderApplication(<FrameResult frame={frame} filename="junction.jpg" />);
    fireEvent.load(screen.getByRole("img", { hidden: true }));
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Class filter" }),
      "person",
    );
    const overlays = screen.getByRole("group", { name: "Detection overlays" });
    expect(within(overlays).getAllByRole("button")).toHaveLength(2);
    fireEvent.change(screen.getByRole("slider"), { target: { value: 100 } });
    expect(within(overlays).queryAllByRole("button")).toHaveLength(0);
    expect(
      screen.getByText("0 matching records / 3 stored detections"),
    ).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "Stored counts" }));
    expect(
      within(
        screen.getByRole("table", { name: "Whole-image object counts" }),
      ).getByText("2"),
    ).toBeVisible();
    expect(frame).toEqual(before);
  });

  it("hides interactive boxes without deleting records and keeps legacy overlays explicit", async () => {
    const user = userEvent.setup();
    renderApplication(
      <FrameResult frame={cleanFrame()} filename="junction.jpg" />,
    );
    fireEvent.load(screen.getByRole("img", { hidden: true }));
    await user.click(screen.getByRole("switch", { name: "Detections" }));
    expect(
      screen.queryByRole("group", { name: "Detection overlays" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("1-3 of 3 detections")).toBeVisible();
  });
});
