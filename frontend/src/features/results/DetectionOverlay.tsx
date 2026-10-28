import { Box, ButtonBase } from "@mui/material";
import type { DetectionResult } from "../../api/analysisResults.ts";
import { formatConfidence, formatLabel } from "./resultFormatting.ts";

const colors: Record<string, string> = {
  car_or_van: "#67e8bc",
  person: "#ffdb70",
  bicycle: "#90caff",
  motorcycle: "#ffa7d2",
  bus: "#fdbb74",
  truck: "#d4bcff",
};

export function DetectionOverlay({
  detections,
  width,
  height,
  selectedId,
  onSelect,
}: {
  detections: DetectionResult[];
  width: number;
  height: number;
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <Box
      role="group"
      aria-label="Detection overlays"
      sx={{ position: "absolute", inset: 0, pointerEvents: "none" }}
    >
      {detections.map((detection) => {
        const selected = selectedId === detection.id;
        return (
          <ButtonBase
            key={detection.id}
            aria-label={`Detection ${detection.id}: ${formatLabel(detection.object_class)}, ${formatConfidence(detection.confidence)}`}
            aria-pressed={selected}
            onClick={() => onSelect(detection.id)}
            sx={{
              position: "absolute",
              left: `${(detection.bounds.x_min / width) * 100}%`,
              top: `${(detection.bounds.y_min / height) * 100}%`,
              width: `${((detection.bounds.x_max - detection.bounds.x_min) / width) * 100}%`,
              height: `${((detection.bounds.y_max - detection.bounds.y_min) / height) * 100}%`,
              minWidth: 0,
              minHeight: 0,
              p: 0,
              borderRadius: 0,
              pointerEvents: "auto",
              border: `${selected ? 3 : 1}px solid ${selected ? "#ffffff" : (colors[detection.object_class] ?? "#ffffff")}`,
              boxShadow: "0 0 0 1px #111111",
              bgcolor: selected ? "rgba(255,255,255,0.18)" : "transparent",
              zIndex: selected ? 2 : 1,
              "&:hover, &:focus-visible": {
                outline: "2px solid white",
                outlineOffset: 2,
                bgcolor: "rgba(255,255,255,0.2)",
              },
            }}
          />
        );
      })}
    </Box>
  );
}
