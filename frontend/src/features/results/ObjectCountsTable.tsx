import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import type { ObjectCountSummaryResult } from "../../api/analysisResults.ts";
import { formatLabel } from "./resultFormatting.ts";

export function ObjectCountsTable({
  summaries,
  label,
  classFilter = null,
}: {
  summaries: ObjectCountSummaryResult[];
  label: string;
  classFilter?: string | null;
}) {
  const visibleSummaries =
    classFilter === null
      ? summaries
      : summaries.filter((summary) => summary.object_class === classFilter);
  if (!visibleSummaries.length && classFilter !== null) {
    return (
      <Typography color="text.secondary">
        No stored count summary matches {formatLabel(classFilter)}.
      </Typography>
    );
  }
  return (
    <Table size="small" aria-label={label} sx={{ tableLayout: "fixed" }}>
      {classFilter !== null && (
        <caption
          style={{
            captionSide: "top",
            paddingTop: 0,
            overflowWrap: "anywhere",
          }}
        >
          Class: {formatLabel(classFilter)}
        </caption>
      )}
      <TableHead>
        <TableRow>
          <TableCell>Class</TableCell>
          <TableCell align="right">Count</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {visibleSummaries.map((summary) => (
          <TableRow key={summary.id}>
            <TableCell sx={{ overflowWrap: "anywhere" }}>
              {formatLabel(summary.object_class)}
            </TableCell>
            <TableCell align="right">{summary.object_count}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
