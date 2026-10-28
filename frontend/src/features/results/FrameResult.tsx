import { useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  FormControlLabel,
  Stack,
  Switch,
  TextField,
  Tabs,
  Tab,
  Typography,
  Slider,
} from "@mui/material";
import type { ProcessedFrameResult } from "../../api/analysisResults.ts";
import { DetectionTable } from "./DetectionTable.tsx";
import { DetectionOverlay } from "./DetectionOverlay.tsx";
import { FrameCounts } from "./FrameCounts.tsx";
import { ResultImage } from "./ResultImage.tsx";
import { GridCellCounts } from "./GridCellCounts.tsx";
import { GridOverlay } from "./GridOverlay.tsx";
import { hasAlignedGridCoordinates } from "./gridGeometry.ts";
import { formatConfidence, formatLabel } from "./resultFormatting.ts";
import { FrameAlerts } from "./FrameAlerts.tsx";

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
  const [detectionId, setDetectionId] = useState<number | null>(null);
  const [showGrid, setShowGrid] = useState(true);
  const [showDetections, setShowDetections] = useState(true);
  const [classFilter, setClassFilter] = useState<string | null>(null);
  const [confidence, setConfidence] = useState(0);
  const [tab, setTab] = useState(0);
  const [loadedUrl, setLoadedUrl] = useState<string | null>(null);
  const cellSelector = useRef<HTMLSelectElement>(null);
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
      ].sort(),
    [frame, classFilter],
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
  const filtered = frame.detections.filter(
    (record) =>
      (classFilter === null || record.object_class === classFilter) &&
      record.confidence * 100 >= confidence,
  );
  const detection =
    filtered.find((record) => record.id === detectionId) ?? null;
  const asset = frame.source_asset ?? frame.visual_asset;
  const aligned = hasAlignedGridCoordinates({ ...frame, visual_asset: asset });
  const clean = asset !== null && asset.rendered_overlays.length === 0;
  const validBoxes =
    !!asset &&
    filtered.every(
      ({ bounds }) =>
        Object.values(bounds).every(Number.isFinite) &&
        bounds.x_min >= 0 &&
        bounds.y_min >= 0 &&
        bounds.x_max > bounds.x_min &&
        bounds.y_max > bounds.y_min &&
        bounds.x_max <= asset.width &&
        bounds.y_max <= asset.height,
    );
  function selectCell(id: number | null) {
    setSelectedId(id);
    setDetectionId(null);
  }
  function selectDetection(id: number) {
    setDetectionId(id);
    setSelectedId(null);
    setTab(0);
  }

  return (
    <>
      <Stack
        direction="row"
        useFlexGap
        sx={{ gap: 1, flexWrap: "wrap", alignItems: "center", pb: 1.5, pt: 1 }}
      >
        <TextField
          select
          label="Class filter"
          size="small"
          value={classFilter ?? ""}
          onChange={(event) => {
            setClassFilter(event.target.value || null);
            setDetectionId(null);
          }}
          disabled={!classes.length}
          slotProps={{ select: { native: true }, inputLabel: { shrink: true } }}
          sx={{ width: { xs: "100%", sm: 185 } }}
        >
          <option value="">All classes</option>
          {classes.map((value) => (
            <option key={value} value={value}>
              {formatLabel(value)}
            </option>
          ))}
        </TextField>
        <FormControlLabel
          sx={{ m: 0, "& .MuiFormControlLabel-label": { fontSize: 14 } }}
          label="Detections"
          control={
            <Switch
              size="small"
              checked={showDetections}
              disabled={!clean || !aligned || !validBoxes}
              onChange={(_, checked) => setShowDetections(checked)}
            />
          }
        />
        {cells.length > 0 && (
          <FormControlLabel
            sx={{ m: 0, "& .MuiFormControlLabel-label": { fontSize: 14 } }}
            label="Grid overlay"
            control={
              <Switch
                size="small"
                checked={showGrid}
                disabled={!aligned}
                onChange={(_, checked) => setShowGrid(checked)}
              />
            }
          />
        )}
        <Box sx={{ width: { xs: "100%", sm: 180 }, px: 1 }}>
          <Typography id="display-confidence" variant="caption">
            Display confidence: {confidence}%
          </Typography>
          <Slider
            aria-labelledby="display-confidence"
            value={confidence}
            onChange={(_, value) => {
              setConfidence(value as number);
              setDetectionId(null);
            }}
            valueLabelDisplay="auto"
            size="small"
          />
        </Box>
      </Stack>
      {!clean && asset && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          Legacy annotated preview: saved boxes cannot be hidden or filtered.
          Filters apply to records only.
        </Typography>
      )}
      {asset && (!aligned || !validBoxes) && (
        <Alert severity="warning" sx={{ mb: 1 }}>
          Spatial overlays unavailable: stored coordinates do not match the
          result image.
        </Alert>
      )}
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "minmax(0, 1fr)",
            lg: "minmax(0, 1fr) 280px",
          },
          gap: 2,
          alignItems: "start",
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          <ResultImage
            key={asset?.url ?? "missing"}
            asset={asset}
            annotatedAsset={frame.visual_asset}
            filename={filename}
            onImageStateChange={(loaded) =>
              setLoadedUrl(loaded ? (asset?.url ?? null) : null)
            }
            overlay={
              aligned ? (
                <>
                  {showGrid && cells.length > 0 && (
                    <GridOverlay
                      cells={cells}
                      width={asset!.width}
                      height={asset!.height}
                      selectedId={selectedCell?.id ?? null}
                      onSelect={selectCell}
                    />
                  )}
                  {clean && showDetections && validBoxes && (
                    <DetectionOverlay
                      detections={filtered}
                      width={asset!.width}
                      height={asset!.height}
                      selectedId={detection?.id ?? null}
                      onSelect={selectDetection}
                    />
                  )}
                </>
              ) : undefined
            }
          />
          <Stack
            direction="row"
            useFlexGap
            sx={{
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: 1,
              py: 1.5,
              borderBottom: "1px solid",
              borderColor: "divider",
            }}
          >
            <Typography variant="body2" role="status">
              {filtered.length} matching records / {frame.detections.length}{" "}
              stored detections
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {clean
                ? `${loadedUrl === asset?.url && showDetections && aligned && validBoxes ? filtered.length : 0} visible boxes`
                : asset
                  ? "Saved overlay: all classes"
                  : "No visual asset"}
            </Typography>
          </Stack>
        </Box>
        <Box
          component="aside"
          aria-label="Selection inspector"
          sx={{
            minWidth: 0,
            pt: 1,
            px: { xs: 0, lg: 2 },
            borderLeft: { lg: "1px solid" },
            borderColor: "divider",
          }}
        >
          <Typography component="h2" variant="h2" sx={{ mb: 2 }}>
            Selection
          </Typography>
          {detection ? (
            <Box sx={{ mb: 3 }}>
              <Typography variant="overline">
                Detection {detection.id}
              </Typography>
              <Typography component="h3" variant="h2">
                {formatLabel(detection.object_class)}
              </Typography>
              <Typography sx={{ mt: 1 }}>
                Confidence {formatConfidence(detection.confidence)}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                Bounds (px): ({detection.bounds.x_min.toFixed(1)},{" "}
                {detection.bounds.y_min.toFixed(1)}) to (
                {detection.bounds.x_max.toFixed(1)},{" "}
                {detection.bounds.y_max.toFixed(1)})
              </Typography>
            </Box>
          ) : (
            <Typography color="text.secondary" variant="body2" sx={{ mb: 2 }}>
              No detection selected.
            </Typography>
          )}
          <GridCellCounts
            cells={cells}
            selectedCell={selectedCell}
            onSelect={selectCell}
            classFilter={classFilter}
            inputRef={cellSelector}
          />
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mt: 2 }}
          >
            Cell summaries are stored counts. Display confidence does not
            recalculate them.
          </Typography>
        </Box>
      </Box>
      <Box sx={{ mt: 3, borderBottom: "1px solid", borderColor: "divider" }}>
        <Tabs
          value={tab}
          onChange={(_, value) => setTab(value)}
          variant="scrollable"
          scrollButtons="auto"
          aria-label="Frame records"
        >
          {["Detections", "Stored counts", "Experimental alerts"].map(
            (label, index) => (
              <Tab
                key={label}
                id={`frame-tab-${index}`}
                aria-controls={`frame-panel-${index}`}
                label={label}
              />
            ),
          )}
        </Tabs>
      </Box>
      <Box
        role="tabpanel"
        id="frame-panel-0"
        aria-labelledby="frame-tab-0"
        hidden={tab !== 0}
        sx={{ py: 2 }}
      >
        <DetectionTable
          key={`${classFilter}-${confidence}`}
          emptyMessage={
            confidence > 0 && frame.detections.length > 0
              ? "No detections match the display filters."
              : undefined
          }
          detections={frame.detections.filter(
            (record) => record.confidence * 100 >= confidence,
          )}
          classFilter={classFilter}
          selectedId={detection?.id ?? null}
          onSelect={selectDetection}
          onClearSelection={() => setDetectionId(null)}
        />
      </Box>
      <Box
        role="tabpanel"
        id="frame-panel-1"
        aria-labelledby="frame-tab-1"
        hidden={tab !== 1}
        sx={{ py: 2 }}
      >
        <FrameCounts frame={frame} video={video} classFilter={classFilter} />
      </Box>
      <Box
        role="tabpanel"
        id="frame-panel-2"
        aria-labelledby="frame-tab-2"
        hidden={tab !== 2}
        sx={{ py: 2 }}
      >
        <FrameAlerts
          alerts={frame.alerts}
          cells={cells}
          onSelectCell={(id) => {
            selectCell(id);
            cellSelector.current?.focus();
            cellSelector.current?.scrollIntoView?.({ block: "center" });
          }}
        />
      </Box>
    </>
  );
}
