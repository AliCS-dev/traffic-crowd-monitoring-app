import { Box, Typography } from "@mui/material";
import type { ProcessedFrameResult } from "../../api/analysisResults.ts";
import { ObjectCountsTable } from "./ObjectCountsTable.tsx";

export function FrameCounts({
  frame,
  video = false,
  classFilter = null,
}: {
  frame: ProcessedFrameResult;
  video?: boolean;
  classFilter?: string | null;
}) {
  const scope = video ? "frame" : "image";
  return (
    <Box
      component="section"
      aria-labelledby="frame-counts-title"
      sx={{ minWidth: 0 }}
    >
      <Typography component="h2" id="frame-counts-title" variant="h2">
        Whole-{scope} object counts
      </Typography>
      <Typography sx={{ mt: 1, mb: 2 }} color="text.secondary" variant="body2">
        {frame.detections.length} stored{" "}
        {frame.detections.length === 1 ? "detection" : "detections"}
        {classFilter !== null && " (all classes)"}
      </Typography>
      {frame.frame_summaries.length ? (
        <ObjectCountsTable
          summaries={frame.frame_summaries}
          label={`Whole-${scope} object counts`}
          classFilter={classFilter}
        />
      ) : (
        <Typography color="text.secondary">
          No whole-{scope} count summaries were stored.
        </Typography>
      )}
      <Typography color="text.secondary" variant="body2" sx={{ mt: 2 }}>
        Person detections are not a dense-crowd estimate or a measurement of
        people per square metre.
      </Typography>
    </Box>
  );
}
