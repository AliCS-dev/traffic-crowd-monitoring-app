import { useMemo, useState } from "react";
import {
  Alert,
  Box,
  Chip,
  IconButton,
  Pagination,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import { Crosshair } from "lucide-react";
import type { AlertResult, GridCellResult } from "../../api/analysisResults.ts";
import { gridCellLabel } from "./gridGeometry.ts";
import { formatLabel, formatTimestamp } from "./resultFormatting.ts";

const PAGE_SIZE = 5;
const severityColors = {
  information: "info",
  warning: "warning",
  critical: "error",
} as const;
const comparisons = {
  greater_than: "Greater than (>)",
  greater_than_or_equal: "Greater than or equal (>=)",
};

export function FrameAlerts({
  alerts,
  cells,
  onSelectCell,
}: {
  alerts: AlertResult[];
  cells: GridCellResult[];
  onSelectCell: (id: number) => void;
}) {
  const [page, setPage] = useState(1);
  const ordered = useMemo(
    () =>
      [...alerts].sort(
        (a, b) =>
          (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0) ||
          b.id - a.id,
      ),
    [alerts],
  );
  const totalPages = Math.ceil(ordered.length / PAGE_SIZE);
  const currentPage = Math.min(page, Math.max(1, totalPages));
  const offset = (currentPage - 1) * PAGE_SIZE;

  return (
    <Stack
      component="section"
      aria-labelledby="frame-alerts-title"
      spacing={2}
      sx={{ minWidth: 0 }}
    >
      <Typography component="h2" id="frame-alerts-title" variant="h2">
        Experimental alerts
      </Typography>
      <Alert severity="info">
        These records describe experimental threshold events, not verified
        congestion, overcrowding, or emergencies. Counts may miss or misclassify
        objects; rule severity is not an assessment of real-world danger.
      </Alert>
      {ordered.length ? (
        <>
          <Typography variant="body2" color="text.secondary">
            {ordered.length} recorded{" "}
            {ordered.length === 1 ? "event" : "events"} for this frame (all
            classes and cells)
          </Typography>
          <Box
            component="ul"
            aria-label="Recorded threshold events"
            sx={{ m: 0, p: 0, listStyle: "none" }}
          >
            {ordered.slice(offset, offset + PAGE_SIZE).map((event) => (
              <EventRecord
                key={event.id}
                event={event}
                cell={cells.find((cell) => cell.id === event.grid_cell_id)}
                onSelectCell={onSelectCell}
              />
            ))}
          </Box>
          {totalPages > 1 && (
            <Stack spacing={1} sx={{ alignItems: "center" }}>
              <Typography variant="body2" color="text.secondary">
                {offset + 1}-{Math.min(offset + PAGE_SIZE, ordered.length)} of{" "}
                {ordered.length} events
              </Typography>
              <Pagination
                aria-label="Alert pages"
                size="small"
                siblingCount={0}
                page={currentPage}
                count={totalPages}
                onChange={(_, value) => setPage(value)}
              />
            </Stack>
          )}
        </>
      ) : (
        <Typography color="text.secondary">
          No alerts were recorded for this frame. Rule evaluation status is not
          recorded.
        </Typography>
      )}
    </Stack>
  );
}

function EventRecord({
  event,
  cell,
  onSelectCell,
}: {
  event: AlertResult;
  cell: GridCellResult | undefined;
  onSelectCell: (id: number) => void;
}) {
  let scope = "Not recorded";
  if (event.scope === "frame") scope = "Whole frame";
  if (event.scope === "grid_cell") {
    scope = cell
      ? gridCellLabel(cell)
      : `Grid cell ${event.grid_cell_id} (unavailable)`;
  }
  const fields = [
    ["Scope", scope],
    [
      "Class",
      event.object_class === null
        ? "Not recorded"
        : formatLabel(event.object_class),
    ],
    [
      "Method",
      event.analysis_method === "detector_object_count"
        ? "Detector object count"
        : "Not recorded",
    ],
    [
      "Measured value",
      event.measured_value === null
        ? "Not recorded"
        : String(event.measured_value),
    ],
    [
      "Comparison",
      event.comparison_operator === null
        ? "Not recorded"
        : comparisons[event.comparison_operator],
    ],
    [
      "Threshold",
      event.threshold_value === null
        ? "Not recorded"
        : String(event.threshold_value),
    ],
  ];
  return (
    <Box
      component="li"
      sx={{
        py: 2.5,
        borderTop: "1px solid",
        borderColor: "divider",
        overflowWrap: "anywhere",
      }}
    >
      <Box component="article" aria-labelledby={`event-${event.id}-title`}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography
              component="h3"
              id={`event-${event.id}-title`}
              variant="body1"
              sx={{ fontWeight: 650 }}
            >
              {event.alert_type || "Rule not recorded"}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Record {event.id}
            </Typography>
          </Box>
          {event.scope === "grid_cell" && cell && (
            <Tooltip title={`Inspect ${gridCellLabel(cell).toLowerCase()}`}>
              <IconButton
                size="small"
                aria-label={`Inspect ${gridCellLabel(cell).toLowerCase()}`}
                onClick={() => onSelectCell(cell.id)}
              >
                <Crosshair aria-hidden size={18} />
              </IconButton>
            </Tooltip>
          )}
        </Stack>
        <Chip
          size="small"
          variant="outlined"
          color={severityColors[event.severity]}
          label={`Rule severity: ${formatLabel(event.severity)}`}
          sx={{ mt: 1 }}
        />
        <Box
          component="dl"
          sx={{
            m: 0,
            my: 2,
            display: "grid",
            gridTemplateColumns: {
              xs: "minmax(0, 1fr)",
              sm: "repeat(2, minmax(0, 1fr))",
              lg: "repeat(3, minmax(0, 1fr))",
            },
            gap: 2,
          }}
        >
          {fields.map(([label, value]) => (
            <Box key={label}>
              <Typography component="dt" variant="body2" color="text.secondary">
                {label}
              </Typography>
              <Typography component="dd" sx={{ m: 0 }}>
                {value}
              </Typography>
            </Box>
          ))}
        </Box>
        <Stack spacing={0.5} sx={{ mb: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Recorded{" "}
            <time dateTime={event.created_at}>
              {formatTimestamp(event.created_at)}
            </time>
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {event.resolved_at === null ? (
              "No resolution recorded"
            ) : (
              <>
                Resolution recorded{" "}
                <time dateTime={event.resolved_at}>
                  {formatTimestamp(event.resolved_at)}
                </time>
              </>
            )}
          </Typography>
        </Stack>
        {event.scope === null && event.grid_cell_id !== null && (
          <Typography variant="body2" color="text.secondary">
            Stored grid-cell reference: {event.grid_cell_id}
          </Typography>
        )}
        <Box
          component="details"
          sx={{ "& summary": { cursor: "pointer", fontSize: "0.875rem" } }}
        >
          <summary>
            {event.grid_cell_id === null
              ? "Stored message"
              : "Stored message (original cell indices)"}
          </summary>
          <Typography variant="body2" sx={{ mt: 1, whiteSpace: "pre-wrap" }}>
            {event.message || "No message recorded."}
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}
