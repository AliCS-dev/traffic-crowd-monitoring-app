import { useMemo, useState } from "react";
import {
  Alert,
  Box,
  FormControlLabel,
  Stack,
  Switch,
  TextField,
} from "@mui/material";
import type { ProcessedFrameResult } from "../../api/analysisResults.ts";
import { DetectionTable } from "./DetectionTable.tsx";
import { FrameCounts } from "./FrameCounts.tsx";
import { ResultImage } from "./ResultImage.tsx";
import { GridCellCounts } from "./GridCellCounts.tsx";
import { GridOverlay } from "./GridOverlay.tsx";
import { hasAlignedGridCoordinates } from "./gridGeometry.ts";
import { formatLabel } from "./resultFormatting.ts";

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
  const [classFilter, setClassFilter] = useState<string | null>(null);
  const classes = useMemo(
    () =>
      [
        ...new Set([
          ...frame.detections.map((record) => record.object_class),
          ...frame.frame_summaries.map((record) => record.object_class),
          ...frame.grid_cells.flatMap((cell) =>
            cell.summaries.map((record) => record.object_class),
          ),
          ...(classFilter === null ? [] : [classFilter]),
        ]),
      ].sort((a, b) => a.localeCompare(b)),
    [frame.detections, frame.frame_summaries, frame.grid_cells, classFilter],
  );
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
      <TextField
        select
        label="Table class"
        size="small"
        value={classFilter ?? ""}
        onChange={(event) => setClassFilter(event.target.value || null)}
        disabled={classes.length === 0}
        slotProps={{ select: { native: true }, inputLabel: { shrink: true } }}
        sx={{ width: "100%", maxWidth: 320, mb: 3 }}
      >
        <option value="">All classes</option>
        {classes.map((objectClass) => (
          <option key={objectClass} value={objectClass}>
            {formatLabel(objectClass)}
          </option>
        ))}
      </TextField>
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
          <FrameCounts frame={frame} video={video} classFilter={classFilter} />
          <GridCellCounts
            cells={cells}
            selectedCell={selectedCell}
            onSelect={setSelectedId}
            classFilter={classFilter}
          />
        </Stack>
      </Box>
      <Box sx={{ mt: 4 }}>
        <DetectionTable
          key={classFilter ?? ""}
          detections={frame.detections}
          classFilter={classFilter}
        />
      </Box>
    </>
  );
}
