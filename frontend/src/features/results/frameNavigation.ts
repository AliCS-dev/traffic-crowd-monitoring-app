import type { ProcessedFrameResult } from "../../api/analysisResults.ts";

export function orderedVideoFrames(frames: ProcessedFrameResult[]) {
  return [...frames].sort((left, right) => {
    const a = left.frame_timestamp_seconds;
    const b = right.frame_timestamp_seconds;
    // Unknown timestamps follow timed samples; never invent a time from FPS.
    if (a === null && b !== null) return 1;
    if (a !== null && b === null) return -1;
    return (
      (a !== null && b !== null ? a - b : 0) ||
      left.frame_number - right.frame_number ||
      left.id - right.id
    );
  });
}

export function formatVideoTime(seconds: number | null): string {
  if (seconds === null) return "Time unavailable";
  const milliseconds = Math.round(seconds * 1000);
  const hours = Math.floor(milliseconds / 3600000);
  const minutes = Math.floor(milliseconds / 60000) % 60;
  const wholeSeconds = Math.floor(milliseconds / 1000) % 60;
  return `${[hours, minutes, wholeSeconds]
    .map((value) => String(value).padStart(2, "0"))
    .join(":")}.${String(milliseconds % 1000).padStart(3, "0")}`;
}
