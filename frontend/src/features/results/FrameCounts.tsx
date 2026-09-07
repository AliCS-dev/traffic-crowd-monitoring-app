import {
  Box,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import type { ProcessedFrameResult } from "../../api/analysisResults.ts";
import { formatLabel } from "./resultFormatting.ts";

export function FrameCounts({
  frame,
  video = false,
}: {
  frame: ProcessedFrameResult;
  video?: boolean;
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
      </Typography>
      {frame.frame_summaries.length ? (
        <Table
          size="small"
          aria-label={`Whole-${scope} object counts`}
          sx={{ tableLayout: "fixed" }}
        >
          <TableHead>
            <TableRow>
              <TableCell>Class</TableCell>
              <TableCell align="right">Count</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {frame.frame_summaries.map((summary) => (
              <TableRow key={summary.id}>
                <TableCell sx={{ overflowWrap: "anywhere" }}>
                  {formatLabel(summary.object_class)}
                </TableCell>
                <TableCell align="right">{summary.object_count}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
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
