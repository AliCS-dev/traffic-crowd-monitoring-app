import { useState } from "react";
import {
  Box,
  Pagination,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import type { DetectionResult } from "../../api/analysisResults.ts";
import { formatConfidence, formatLabel } from "./resultFormatting.ts";

const PAGE_SIZE = 20;

export function DetectionTable({
  detections,
  classFilter = null,
}: {
  detections: DetectionResult[];
  classFilter?: string | null;
}) {
  const [page, setPage] = useState(1);
  const visibleDetections =
    classFilter === null
      ? detections
      : detections.filter(
          (detection) => detection.object_class === classFilter,
        );
  const totalPages = Math.ceil(visibleDetections.length / PAGE_SIZE);
  const currentPage = Math.min(page, Math.max(1, totalPages));
  const offset = (currentPage - 1) * PAGE_SIZE;
  return (
    <Box
      component="section"
      aria-labelledby="detections-title"
      sx={{ minWidth: 0 }}
    >
      <Typography
        component="h2"
        id="detections-title"
        variant="h2"
        sx={{ mb: 2 }}
      >
        Whole-frame detection records
      </Typography>
      {visibleDetections.length ? (
        <>
          <Table
            size="small"
            aria-label="Whole-frame detection records"
            sx={{ tableLayout: "fixed" }}
          >
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
                <TableCell sx={{ width: "25%" }}>ID</TableCell>
                <TableCell>Class</TableCell>
                <TableCell align="right">Confidence</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {visibleDetections
                .slice(offset, offset + PAGE_SIZE)
                .map((detection) => (
                  <TableRow key={detection.id}>
                    <TableCell sx={{ overflowWrap: "anywhere" }}>
                      {detection.id}
                    </TableCell>
                    <TableCell sx={{ overflowWrap: "anywhere" }}>
                      {formatLabel(detection.object_class)}
                    </TableCell>
                    <TableCell align="right">
                      {formatConfidence(detection.confidence)}
                    </TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
          <Stack spacing={1} sx={{ alignItems: "center", mt: 2 }}>
            <Typography variant="body2" color="text.secondary">
              {offset + 1}-
              {Math.min(offset + PAGE_SIZE, visibleDetections.length)} of{" "}
              {visibleDetections.length} detections
            </Typography>
            {totalPages > 1 && (
              <Pagination
                aria-label="Detection pages"
                count={totalPages}
                page={currentPage}
                onChange={(_, value) => setPage(value)}
                size="small"
                siblingCount={0}
              />
            )}
          </Stack>
        </>
      ) : (
        <Typography color="text.secondary">
          {detections.length && classFilter !== null
            ? `No stored detections match ${formatLabel(classFilter)}.`
            : "No detections were stored for this frame."}
        </Typography>
      )}
    </Box>
  );
}
