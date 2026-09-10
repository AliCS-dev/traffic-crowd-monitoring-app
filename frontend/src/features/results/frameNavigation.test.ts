import { describe, expect, it } from "vitest";
import { videoResultFixture } from "../../test/analysisResultFixture.ts";
import { formatVideoTime, orderedVideoFrames } from "./frameNavigation.ts";

describe("sampled-frame ordering", () => {
  it("orders timestamps without changing the API response", () => {
    const { frames } = videoResultFixture();
    expect(orderedVideoFrames(frames).map((frame) => frame.id)).toEqual([
      20, 21, 22,
    ]);
    expect(frames.map((frame) => frame.id)).toEqual([22, 20, 21]);
  });

  it("puts unknown times last and breaks ties by frame number then ID", () => {
    const { frames } = videoResultFixture();
    frames[0].frame_timestamp_seconds = null;
    frames[1].frame_timestamp_seconds = null;
    expect(orderedVideoFrames(frames).map((frame) => frame.id)).toEqual([
      21, 20, 22,
    ]);
    frames.forEach((frame) => {
      frame.frame_timestamp_seconds = 2;
    });
    frames[0].frame_number = 60;
    expect(orderedVideoFrames(frames).map((frame) => frame.id)).toEqual([
      20, 21, 22,
    ]);
  });

  it.each([
    [null, "Time unavailable"],
    [0, "00:00:00.000"],
    [2.5, "00:00:02.500"],
    [59.9999, "00:01:00.000"],
    [3661.234, "01:01:01.234"],
  ])("formats %s seconds as %s", (seconds, expected) => {
    expect(formatVideoTime(seconds)).toBe(expected);
  });
});
