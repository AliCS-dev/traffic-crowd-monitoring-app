import { act, fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MonitoringSessionResult } from "../api/analysisResults.ts";
import {
  analysisResultFixture,
  videoResultFixture,
} from "../test/analysisResultFixture.ts";
import { renderApplication } from "../test/render.tsx";
import { ResultsPage } from "./ResultsPage.tsx";

function response(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function mockResult(result: MonitoringSessionResult) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(() => Promise.resolve(response(result))),
  );
}

function renderResults(path = "/analyses/42") {
  return renderApplication(
    <>
      <Link to="/analyses/43">Another session</Link>
      <Routes>
        <Route path="/analyses/:sessionId?" element={<ResultsPage />} />
      </Routes>
    </>,
    path,
  );
}

describe("ResultsPage", () => {
  beforeEach(() => mockResult(analysisResultFixture()));

  it("shows the saved image, frame-only counts, confidence, and recorded limitations", async () => {
    renderResults();
    const image = await screen.findByAltText(
      "Detection result for junction.jpg",
    );
    expect(image).toHaveAttribute("width", "1280");
    expect(image).toHaveAttribute("height", "720");
    expect(image).toHaveAttribute(
      "src",
      "http://localhost:8000/api/assets/12345678-1234-5678-1234-567812345678",
    );
    fireEvent.load(image);
    expect(
      screen.getByRole("link", { name: "Open result image" }),
    ).toHaveAttribute("rel", "noopener noreferrer");
    const counts = screen.getByRole("table", {
      name: "Whole-image object counts",
    });
    expect(within(counts).getAllByRole("row")).toHaveLength(2);
    expect(within(counts).getByText("1")).toBeInTheDocument();
    expect(screen.getByText("82.5%")).toBeInTheDocument();
    expect(
      screen.getByText(/did not pass its evaluation quality gate/),
    ).toBeInTheDocument();
    expect(screen.getByText("Processing: Completed")).toBeInTheDocument();
    expect(
      screen.getByText("Dense-crowd counting unsupported"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Estimated crowd count:/),
    ).not.toBeInTheDocument();
    expect(screen.getByText("evaluated-traffic-detector")).toBeInTheDocument();
  });

  it("keeps stored counts visible when the image cannot be loaded", async () => {
    renderResults();
    fireEvent.error(
      await screen.findByAltText("Detection result for junction.jpg"),
    );
    expect(screen.getByText("Result image unavailable")).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: "Whole-image object counts" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Open result image" }),
    ).not.toBeInTheDocument();
  });

  it("handles missing visual metadata, model profile, crowd decision, and summaries", async () => {
    const result = analysisResultFixture();
    result.model_profile = null;
    result.dense_crowd_analysis = null;
    result.frames[0].visual_asset = null;
    result.frames[0].output_asset_id = null;
    result.frames[0].frame_summaries = [];
    result.frames[0].detections = [];
    mockResult(result);
    renderResults();
    expect(
      await screen.findByText(/No model provenance was recorded/),
    ).toBeInTheDocument();
    expect(screen.getByText("Result image unavailable")).toBeInTheDocument();
    expect(
      screen.getByText("No whole-image count summaries were stored."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No detections were stored for this frame."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "No dense-crowd analysis was recorded for this session.",
      ),
    ).toBeInTheDocument();
  });

  it("does not treat missing frames as a completed zero-count result", async () => {
    const result = analysisResultFixture();
    result.status = "failed";
    result.frames = [];
    mockResult(result);
    renderResults();
    expect(
      await screen.findByText("No processed frames available"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Processing failed/)).toBeInTheDocument();
    expect(
      screen.queryByRole("table", { name: "Whole-image object counts" }),
    ).not.toBeInTheDocument();
  });

  it("browses video samples in time order with matching images and counts", async () => {
    const user = userEvent.setup();
    mockResult(videoResultFixture());
    renderResults();
    await screen.findByText("Sample 1 of 3 | Source frame 0 | 00:00:00.000");
    const previous = screen.getByRole("button", {
      name: "Previous sampled frame",
    });
    const next = screen.getByRole("button", { name: "Next sampled frame" });
    expect(previous).toBeDisabled();
    expect(
      screen.getByAltText("Detection result for junction.mp4, frame 0"),
    ).toBeInTheDocument();
    expect(
      within(
        screen.getByRole("table", { name: "Whole-frame object counts" }),
      ).getByText("1"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("table", { name: "Whole-image object counts" }),
    ).not.toBeInTheDocument();
    await user.click(next);
    expect(
      screen.getByText("Sample 2 of 3 | Source frame 60 | 00:00:02.500"),
    ).toBeInTheDocument();
    expect(screen.getByText("Result image unavailable")).toBeInTheDocument();
    expect(
      screen.queryByAltText("Detection result for junction.mp4, frame 0"),
    ).not.toBeInTheDocument();
    const counts = screen.getByRole("table", {
      name: "Whole-frame object counts",
    });
    expect(within(counts).getByText("Truck")).toBeInTheDocument();
    expect(within(counts).getByText("21")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Go to page 2" }));
    expect(screen.getByText("21-21 of 21 detections")).toBeInTheDocument();
    await user.click(next);
    expect(next).toBeDisabled();
    expect(
      screen.getByAltText("Detection result for junction.mp4, frame 120"),
    ).toHaveAttribute("src", expect.stringContaining("567812345679"));
    expect(
      screen.getByText("No whole-frame count summaries were stored."),
    ).toBeInTheDocument();
    await user.click(previous);
    expect(screen.getByText("1-20 of 21 detections")).toBeInTheDocument();
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Sampled frame" }),
      "20",
    );
    expect(previous).toBeDisabled();
    expect(
      screen.getByAltText("Detection result for junction.mp4, frame 0"),
    ).toBeInTheDocument();
  });

  it("identifies a partial single-frame video and its missing timestamp", async () => {
    const result = videoResultFixture();
    result.status = "processing";
    result.completed_at = null;
    result.frames = [result.frames[1]];
    result.frames[0].frame_timestamp_seconds = null;
    mockResult(result);
    renderResults();
    await screen.findByText(
      "Sample 1 of 1 | Source frame 0 | Time unavailable",
    );
    expect(
      screen.getByText(/Stored results may be partial/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Previous sampled frame" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Next sampled frame" }),
    ).toBeDisabled();
    expect(
      screen.getByText(/not unique objects across the video/),
    ).toBeInTheDocument();
  });

  it("keeps the selected frame by ID when a refresh adds an earlier sample", async () => {
    const user = userEvent.setup();
    const result = videoResultFixture();
    mockResult(result);
    renderResults();
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Sampled frame" }),
      "21",
    );
    const added = structuredClone(result.frames[1]);
    added.id = 23;
    added.frame_number = 24;
    added.frame_timestamp_seconds = 1;
    result.frames.push(added);
    mockResult(result);
    await user.click(screen.getByRole("button", { name: "Refresh analysis" }));
    expect(
      await screen.findByText("Sample 3 of 4 | Source frame 60 | 00:00:02.500"),
    ).toBeInTheDocument();
  });

  it("preserves the initially displayed sample when a refresh adds earlier frames", async () => {
    const user = userEvent.setup();
    const result = videoResultFixture();
    const first = result.frames.splice(1, 1)[0];
    mockResult(result);
    renderResults();
    await screen.findByText("Sample 1 of 2 | Source frame 60 | 00:00:02.500");
    result.frames.push(first);
    mockResult(result);
    await user.click(screen.getByRole("button", { name: "Refresh analysis" }));
    expect(
      await screen.findByText("Sample 2 of 3 | Source frame 60 | 00:00:02.500"),
    ).toBeInTheDocument();
  });

  it("resets video selection when opening another session", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        return Promise.resolve(
          response(videoResultFixture(Number(String(input).split("/").at(-1)))),
        );
      }),
    );
    renderResults();
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Sampled frame" }),
      "22",
    );
    await user.click(screen.getByRole("link", { name: "Another session" }));
    await screen.findByRole("heading", { name: "Analysis 43" });
    expect(screen.getByRole("combobox", { name: "Sampled frame" })).toHaveValue(
      "20",
    );
  });

  it("does not combine frames from unmatched sources into one video timeline", async () => {
    const result = videoResultFixture();
    result.frames[0].input_source_id = 99;
    mockResult(result);
    renderResults();
    expect(
      await screen.findByText("Sampled-frame view unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: "Sampled frame" }),
    ).not.toBeInTheDocument();
  });

  it("paginates detection records without changing the stored image count", async () => {
    const user = userEvent.setup();
    const result = analysisResultFixture();
    result.frames[0].detections = Array.from({ length: 21 }, (_, index) => ({
      ...result.frames[0].detections[0],
      id: 100 + index,
    }));
    result.frames[0].frame_summaries[0].object_count = 21;
    mockResult(result);
    renderResults();
    await screen.findByText("1-20 of 21 detections");
    await user.click(
      within(
        screen.getByRole("navigation", { name: "Detection pages" }),
      ).getByRole("button", { name: "Go to page 2" }),
    );
    expect(screen.getByText("21-21 of 21 detections")).toBeInTheDocument();
    expect(
      within(
        screen.getByRole("table", { name: "Detection records" }),
      ).getByText("120"),
    ).toBeInTheDocument();
    expect(
      within(
        screen.getByRole("table", { name: "Whole-image object counts" }),
      ).getByText("21"),
    ).toBeInTheDocument();
  });

  it("shows pending and not-found states", async () => {
    let resolve!: (response: Response) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockReturnValue(
        new Promise<Response>((done) => {
          resolve = done;
        }),
      ),
    );
    renderResults();
    expect(screen.getByText("Loading analysis 42")).toBeInTheDocument();
    await act(async () =>
      resolve(
        response(
          { error: { code: "analysis_not_found", message: "Not found" } },
          404,
        ),
      ),
    );
    expect(await screen.findByText("Analysis not found")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Session history" }),
    ).toHaveAttribute("href", "/sessions");
  });

  it("recovers from a failed API request", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockRejectedValueOnce(new TypeError("Offline"))
        .mockResolvedValueOnce(response(analysisResultFixture())),
    );
    renderResults();
    await user.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("82.5%")).toBeInTheDocument();
  });

  it.each(["0", "-1", "1e2", "9007199254740993", "not-a-number"])(
    "rejects invalid session reference %s without requesting data",
    (id) => {
      renderResults(`/analyses/${id}`);
      expect(
        screen.getByText("Invalid analysis reference"),
      ).toBeInTheDocument();
      expect(fetch).not.toHaveBeenCalled();
    },
  );

  it("changes session without leaving the previous result or lookup value on screen", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const id = Number(String(input).split("/").at(-1));
        const result = analysisResultFixture(id);
        result.session_name = `Stored run ${id}`;
        return Promise.resolve(response(result));
      }),
    );
    renderResults();
    await screen.findByText("Stored run 42");
    await user.click(screen.getByRole("link", { name: "Another session" }));
    expect(await screen.findByText("Stored run 43")).toBeInTheDocument();
    expect(screen.queryByText("Stored run 42")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Session ID")).toHaveValue("43");
  });
});
