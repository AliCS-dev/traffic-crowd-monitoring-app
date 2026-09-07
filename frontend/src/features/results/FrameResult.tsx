import { useMemo, useState } from "react";
import { Alert, Box, FormControlLabel, Stack, Switch } from "@mui/material";
import type { ProcessedFrameResult } from "../../api/analysisResults.ts";
import { DetectionTable } from "./DetectionTable.tsx";
import { FrameCounts } from "./FrameCounts.tsx";
import { ResultImage } from "./ResultImage.tsx";
import { GridCellCounts } from "./GridCellCounts.tsx";
import { GridOverlay } from "./GridOverlay.tsx";
import { hasAlignedGridCoordinates } from "./gridGeometry.ts";

export function FrameResult({
  frame,
  filename,
  video = false,
}: {
  frame: ProcessedFrameResult;
  filename: string;
  video?: boolean;
}) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showGrid, setShowGrid] = useState(true);
  const cells = useMemo(
    () =>
      [...frame.grid_cells].sort(
        (a, b) =>
          a.row_index - b.row_index ||
          a.column_index - b.column_index ||
          a.id - b.id,
      ),
    [frame.grid_cells],
  );
  const selectedCell = cells.find((cell) => cell.id === selectedId) ?? null;
  const aligned = cells.length > 0 && hasAlignedGridCoordinates(frame);
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
        <Box sx={{ minWidth: 0 }}>
          {cells.length > 0 && frame.visual_asset && !aligned && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              Grid overlay unavailable: stored coordinates do not match the
              result image.
            </Alert>
          )}
          <ResultImage
            asset={frame.visual_asset}
            filename={filename}
            controls={
              aligned ? (
                <FormControlLabel
                  label="Grid overlay"
                  control={
                    <Switch
                      size="small"
                      checked={showGrid}
                      onChange={(_, checked) => setShowGrid(checked)}
                    />
                  }
                />
              ) : undefined
            }
            overlay={
              aligned && showGrid ? (
                <GridOverlay
                  cells={cells}
                  width={frame.visual_asset!.width}
                  height={frame.visual_asset!.height}
                  selectedId={selectedCell?.id ?? null}
                  onSelect={setSelectedId}
                />
              ) : undefined
            }
          />
        </Box>
        <Stack spacing={4} sx={{ minWidth: 0 }}>
          <FrameCounts frame={frame} video={video} />
          <GridCellCounts
            cells={cells}
            selectedCell={selectedCell}
            onSelect={setSelectedId}
          />
        </Stack>
      </Box>
      <Box sx={{ mt: 4 }}>
        <DetectionTable detections={frame.detections} />
      </Box>
    </>
  );
}
