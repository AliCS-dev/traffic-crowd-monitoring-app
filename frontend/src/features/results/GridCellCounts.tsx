import type { Ref } from "react";
import { Box, Stack, TextField, Typography } from "@mui/material";
import type { GridCellResult } from "../../api/analysisResults.ts";
import { gridCellLabel } from "./gridGeometry.ts";
import { ObjectCountsTable } from "./ObjectCountsTable.tsx";

const pixels = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });

export function GridCellCounts({
  cells,
  selectedCell,
  onSelect,
  classFilter = null,
  inputRef,
}: {
  cells: GridCellResult[];
  selectedCell: GridCellResult | null;
  onSelect: (id: number | null) => void;
  classFilter?: string | null;
  inputRef?: Ref<HTMLSelectElement>;
}) {
  return (
    <Stack
      component="section"
      aria-labelledby="cell-counts-title"
      spacing={2}
      sx={{ minWidth: 0 }}
    >
      <Typography component="h2" id="cell-counts-title" variant="h2">
        Selected-cell object counts
      </Typography>
      {!cells.length ? (
        <Typography color="text.secondary">
          No grid was stored for this frame.
        </Typography>
      ) : (
        <>
          <TextField
            select
            label="Grid cell"
            inputRef={inputRef}
            size="small"
            fullWidth
            value={selectedCell?.id ?? ""}
            onChange={(event) =>
              onSelect(
                event.target.value === "" ? null : Number(event.target.value),
              )
            }
            slotProps={{
              select: { native: true },
              inputLabel: { shrink: true },
            }}
          >
            <option value="">None selected</option>
            {cells.map((cell) => (
              <option key={cell.id} value={cell.id}>
                {gridCellLabel(cell)}
              </option>
            ))}
          </TextField>
          {selectedCell ? (
            <Box>
              <Typography role="status" variant="body2" sx={{ mb: 1 }}>
                {gridCellLabel(selectedCell)}
              </Typography>
              {selectedCell.summaries.length ? (
                <ObjectCountsTable
                  summaries={selectedCell.summaries}
                  label="Selected-cell object counts"
                  classFilter={classFilter}
                />
              ) : (
                <Typography color="text.secondary">
                  No class counts were recorded for this cell.
                </Typography>
              )}
              <Typography color="text.secondary" variant="body2" sx={{ mt: 2 }}>
                Processed-image bounds (px): x{" "}
                {pixels.format(selectedCell.bounds.x_min)} to{" "}
                {pixels.format(selectedCell.bounds.x_max)}, y{" "}
                {pixels.format(selectedCell.bounds.y_min)} to{" "}
                {pixels.format(selectedCell.bounds.y_max)}
              </Typography>
            </Box>
          ) : (
            <Typography color="text.secondary">
              No grid cell selected.
            </Typography>
          )}
        </>
      )}
    </Stack>
  );
}
