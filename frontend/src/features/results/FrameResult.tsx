import { Box } from "@mui/material";
import type { ProcessedFrameResult } from "../../api/analysisResults.ts";
import { DetectionTable } from "./DetectionTable.tsx";
import { FrameCounts } from "./FrameCounts.tsx";
import { ResultImage } from "./ResultImage.tsx";

export function FrameResult({
  frame,
  filename,
  video = false,
}: {
  frame: ProcessedFrameResult;
  filename: string;
  video?: boolean;
}) {
  return (
    <>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "minmax(0, 1fr)",
            lg: "minmax(0, 2fr) minmax(260px, 1fr)",
          },
          gap: 3,
          alignItems: "start",
        }}
      >
        <ResultImage asset={frame.visual_asset} filename={filename} />
        <FrameCounts frame={frame} video={video} />
      </Box>
      <Box sx={{ mt: 4 }}>
        <DetectionTable detections={frame.detections} />
      </Box>
    </>
  );
}
