import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  Box,
  Button,
  IconButton,
  LinearProgress,
  Pagination,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import {
  ArrowRight,
  FileImage,
  FileQuestion,
  FileVideo,
  RefreshCw,
} from "lucide-react";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client.ts";
import type {
  MonitoringSessionSourceType,
  MonitoringSessionSummary,
} from "../../api/types.ts";
import { StatePanel } from "../../components/StatePanel.tsx";

const PAGE_SIZE = 20;

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

const statusColours: Record<string, string> = {
  completed: "success.main",
  created: "text.secondary",
  failed: "error.main",
  processing: "warning.main",
  queued: "secondary.main",
};

export function SessionHistory() {
  const [page, setPage] = useState(1);
  const history = useQuery({
    queryKey: ["analyses", "history", page, PAGE_SIZE],
    queryFn: ({ signal }) => apiClient.listAnalyses(page, PAGE_SIZE, signal),
    placeholderData: keepPreviousData,
  });

  if (history.isPending) {
    return <StatePanel kind="loading" title="Loading session history" />;
  }

  if (history.isError) {
    return (
      <StatePanel
        action={
          <Button
            onClick={() => history.refetch()}
            startIcon={<RefreshCw aria-hidden size={17} />}
            variant="outlined"
          >
            Retry
          </Button>
        }
        description="We could not retrieve monitoring sessions from the API."
        kind="unavailable"
        title="Session history unavailable"
      />
    );
  }

  if (history.data.items.length === 0) {
    return (
      <StatePanel
        description="Completed and in-progress analyses will appear here."
        kind="empty"
        title="No sessions available"
      />
    );
  }

  const { items, pagination } = history.data;
  const firstItem = (pagination.page - 1) * pagination.page_size + 1;
  const lastItem = Math.min(
    firstItem + items.length - 1,
    pagination.total_items,
  );

  return (
    <Box
      sx={{
        position: "relative",
        overflow: "hidden",
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
      }}
    >
      {history.isFetching && (
        <LinearProgress
          aria-label="Updating session history"
          sx={{ position: "absolute", inset: "0 0 auto", zIndex: 1 }}
        />
      )}
      <TableContainer>
        <Table aria-label="Monitoring sessions" sx={{ tableLayout: "fixed" }}>
          <TableHead>
            <TableRow>
              <TableCell sx={{ width: { xs: "48%", sm: "40%" } }}>
                Session
              </TableCell>
              <TableCell sx={{ width: { xs: "24%", sm: "17%" } }}>
                Source
              </TableCell>
              <TableCell sx={{ width: { xs: "28%", sm: "18%" } }}>
                Status
              </TableCell>
              <TableCell sx={{ display: { xs: "none", sm: "table-cell" } }}>
                Started
              </TableCell>
              <TableCell padding="checkbox" />
            </TableRow>
          </TableHead>
          <TableBody>
            {items.map((session) => (
              <SessionRow key={session.id} session={session} />
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1.5}
        sx={{
          alignItems: "center",
          justifyContent: "space-between",
          borderTop: "1px solid",
          borderColor: "divider",
          px: 2,
          py: 1.5,
        }}
      >
        <Typography
          color="text.secondary"
          sx={{ overflowWrap: "anywhere" }}
          variant="body2"
        >
          {firstItem}-{lastItem} of {pagination.total_items} sessions
        </Typography>
        {pagination.total_pages > 1 && (
          <Pagination
            color="primary"
            count={pagination.total_pages}
            disabled={history.isFetching}
            onChange={(_, selectedPage) => setPage(selectedPage)}
            page={pagination.page}
            showFirstButton
            showLastButton
            size="small"
          />
        )}
      </Stack>
    </Box>
  );
}

function SessionRow({ session }: { session: MonitoringSessionSummary }) {
  const sessionLabel = session.session_name?.trim() || `Analysis ${session.id}`;

  return (
    <TableRow hover>
      <TableCell>
        <Typography
          sx={{ fontWeight: 650, overflowWrap: "anywhere" }}
          variant="body2"
        >
          {sessionLabel}
        </Typography>
        <Typography
          color="text.secondary"
          sx={{ overflowWrap: "anywhere" }}
          variant="body2"
        >
          ID {session.id}
          {session.original_filename && ` · ${session.original_filename}`}
        </Typography>
      </TableCell>
      <TableCell>
        <SourceLabel sourceType={session.source_type} />
      </TableCell>
      <TableCell>
        <StatusLabel status={session.status} />
      </TableCell>
      <TableCell sx={{ display: { xs: "none", sm: "table-cell" } }}>
        <Typography
          component="time"
          dateTime={session.started_at}
          title={session.started_at}
          variant="body2"
        >
          {formatDateTime(session.started_at)}
        </Typography>
      </TableCell>
      <TableCell padding="checkbox">
        <Tooltip title={`Open ${sessionLabel}`}>
          <IconButton
            aria-label={`Open ${sessionLabel}`}
            component={Link}
            size="small"
            to={`/analyses/${session.id}`}
          >
            <ArrowRight aria-hidden size={19} />
          </IconButton>
        </Tooltip>
      </TableCell>
    </TableRow>
  );
}

function SourceLabel({
  sourceType,
}: {
  sourceType: MonitoringSessionSourceType | null;
}) {
  const SourceIcon =
    sourceType === "video"
      ? FileVideo
      : sourceType === "image"
        ? FileImage
        : FileQuestion;
  const label = sourceType ? capitalize(sourceType) : "Unknown";

  return (
    <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
      <SourceIcon aria-hidden size={17} strokeWidth={1.8} />
      <Typography variant="body2">{label}</Typography>
    </Stack>
  );
}

function StatusLabel({ status }: { status: string }) {
  return (
    <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
      <Box
        aria-hidden
        sx={{
          width: 8,
          height: 8,
          flex: "0 0 auto",
          borderRadius: "50%",
          bgcolor: statusColours[status.toLowerCase()] ?? "text.secondary",
        }}
      />
      <Typography sx={{ overflowWrap: "anywhere" }} variant="body2">
        {humanize(status)}
      </Typography>
    </Stack>
  );
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Unknown time"
    : dateTimeFormatter.format(date);
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function humanize(value: string): string {
  return value
    .trim()
    .replaceAll("_", " ")
    .replace(/^./, (character) => character.toUpperCase());
}
