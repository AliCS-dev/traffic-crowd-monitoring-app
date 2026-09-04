import { describe, expect, it } from "vitest";

import type { AnalysisCapabilitiesResponse } from "../../api/types.ts";
import {
  formatBytes,
  initialAnalysisFormDraft,
  validateAnalysisDraft,
  validateMediaFile,
} from "./analysisForm.ts";

const capabilities: AnalysisCapabilitiesResponse = {
  image: {
    extensions: [".jpg", ".jpeg", ".png"],
    mime_types: ["image/jpeg", "image/png"],
    mime_type_by_extension: {
      ".jpg": "image/jpeg",
      ".jpeg": "image/jpeg",
      ".png": "image/png",
    },
    max_upload_bytes: 10,
    max_pixels: 40_000_000,
  },
  video: {
    extensions: [".mp4", ".mov"],
    mime_types: ["video/mp4", "video/quicktime"],
    mime_type_by_extension: {
      ".mp4": "video/mp4",
      ".mov": "video/quicktime",
    },
    max_upload_bytes: 20,
    max_pixels: 40_000_000,
  },
  options: {
    max_session_name_length: 150,
    max_grid_dimension: 20,
    default_sampling_interval_seconds: 1,
    max_sampling_interval_seconds: 3600,
  },
};

describe("analysis form validation", () => {
  it("normalizes a valid image submission", () => {
    const file = new File(["image"], "AERIAL.JPG", { type: "image/jpeg" });
    const result = validateAnalysisDraft(
      {
        ...initialAnalysisFormDraft,
        file,
        sessionName: "  Morning junction  ",
        gridEnabled: true,
        gridRows: "4",
        gridColumns: "5",
      },
      capabilities,
    );

    expect(result.errors).toEqual({ file: undefined });
    expect(result.submission).toEqual({
      mode: "image",
      file,
      options: {
        sessionName: "Morning junction",
        gridRows: 4,
        gridColumns: 5,
      },
    });
  });

  it("builds video options with the sampling interval", () => {
    const file = new File(["video"], "junction.mp4", { type: "video/mp4" });
    const result = validateAnalysisDraft(
      {
        ...initialAnalysisFormDraft,
        mode: "video",
        file,
        samplingIntervalSeconds: "2.5",
      },
      capabilities,
    );

    expect(result.submission?.options).toMatchObject({
      samplingIntervalSeconds: 2.5,
    });
  });

  it("rejects unsupported, mismatched, empty, and oversized files", () => {
    expect(
      validateMediaFile(
        new File(["image"], "aerial.gif", { type: "image/gif" }),
        "image",
        capabilities,
      ),
    ).toContain(".jpg");
    expect(
      validateMediaFile(
        new File(["image"], "aerial.jpg", { type: "image/png" }),
        "image",
        capabilities,
      ),
    ).toContain("does not match");
    expect(
      validateMediaFile(
        new File([], "aerial.jpg", { type: "image/jpeg" }),
        "image",
        capabilities,
      ),
    ).toBe("The selected file is empty.");
    expect(
      validateMediaFile(
        new File(["01234567890"], "aerial.jpg", { type: "image/jpeg" }),
        "image",
        capabilities,
      ),
    ).toContain("10 B limit");
  });

  it("reports invalid optional settings together", () => {
    const result = validateAnalysisDraft(
      {
        ...initialAnalysisFormDraft,
        mode: "video",
        file: new File(["video"], "junction.mp4", { type: "video/mp4" }),
        sessionName: "s".repeat(151),
        gridEnabled: true,
        gridRows: "0",
        gridColumns: "21",
        samplingIntervalSeconds: "3601",
      },
      capabilities,
    );

    expect(result.submission).toBeUndefined();
    expect(result.errors).toMatchObject({
      sessionName: "Use at most 150 characters.",
      gridRows: "Enter 1-20.",
      gridColumns: "Enter 1-20.",
      samplingIntervalSeconds: "Enter more than 0 and at most 3600 seconds.",
    });
  });

  it("formats file limits without excessive precision", () => {
    expect(formatBytes(500)).toBe("500 B");
    expect(formatBytes(1024)).toBe("1.0 KB");
    expect(formatBytes(10 * 1024 * 1024)).toBe("10 MB");
  });
});
