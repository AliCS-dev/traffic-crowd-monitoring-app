import { Box, ButtonBase, Tooltip } from "@mui/material";
import type { GridCellResult } from "../../api/analysisResults.ts";
import { gridCellLabel } from "./gridGeometry.ts";

export function GridOverlay({
  cells,
  width,
  height,
  selectedId,
  onSelect,
}: {
  cells: GridCellResult[];
  width: number;
  height: number;
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <Box
      role="group"
      aria-label="Image grid"
      sx={{ position: "absolute", inset: 0, pointerEvents: "none" }}
    >
      {cells.map((cell) => (
        <Tooltip key={cell.id} title={gridCellLabel(cell)}>
          <ButtonBase
            aria-label={gridCellLabel(cell)}
            aria-pressed={selectedId === cell.id}
            onClick={() => onSelect(cell.id)}
            sx={{
              position: "absolute",
              left: `${(cell.bounds.x_min / width) * 100}%`,
              top: `${(cell.bounds.y_min / height) * 100}%`,
              width: `${((cell.bounds.x_max - cell.bounds.x_min) / width) * 100}%`,
              height: `${((cell.bounds.y_max - cell.bounds.y_min) / height) * 100}%`,
              minWidth: 0,
              minHeight: 0,
              p: 0,
              borderRadius: 0,
              pointerEvents: "auto",
              border: "1px solid #ffffff",
              boxShadow: "inset 0 0 0 1px #17222b",
              bgcolor:
                selectedId === cell.id
                  ? "rgba(255, 209, 102, 0.22)"
                  : "transparent",
              "&[aria-pressed=true]": {
                borderColor: "#ffd166",
                boxShadow: "inset 0 0 0 2px #17222b",
                zIndex: 1,
              },
              "&:hover": { bgcolor: "rgba(255, 255, 255, 0.18)" },
              "&:focus-visible": {
                outline: "3px solid #ffd166",
                outlineOffset: "-4px",
                zIndex: 2,
              },
            }}
          />
        </Tooltip>
      ))}
    </Box>
  );
}
