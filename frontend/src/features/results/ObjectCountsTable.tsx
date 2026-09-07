import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
} from "@mui/material";
import type { ObjectCountSummaryResult } from "../../api/analysisResults.ts";
import { formatLabel } from "./resultFormatting.ts";

export function ObjectCountsTable({
  summaries,
  label,
}: {
  summaries: ObjectCountSummaryResult[];
  label: string;
}) {
  return (
    <Table size="small" aria-label={label} sx={{ tableLayout: "fixed" }}>
      <TableHead>
        <TableRow>
          <TableCell>Class</TableCell>
          <TableCell align="right">Count</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {summaries.map((summary) => (
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
