import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Box,
  Button,
  Chip,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";

import { apiClient, ApiRequestError } from "../../api/client.ts";
import type { MonitoringSessionResult } from "../../api/analysisResults.ts";
import { StatePanel } from "../../components/StatePanel.tsx";
import { FrameResult } from "./FrameResult.tsx";
import { VideoResult } from "./VideoResult.tsx";
import {
  CrowdResult,
  DetectorQuality,
  ModelProvenance,
} from "./ModelContext.tsx";
import { formatLabel, formatTimestamp } from "./resultFormatting.ts";

export function AnalysisResult({ sessionId }: { sessionId: number }) {
  const result = useQuery({
    queryKey: ["analyses", "detail", sessionId],
    queryFn: ({ signal }) => apiClient.getAnalysis(sessionId, signal),
  });

  if (result.isPending)
    return (
      <StatePanel kind="loading" title={`Loading analysis ${sessionId}`} />
    );
  if (result.isError) {
    const missing =
      result.error instanceof ApiRequestError && result.error.status === 404;
    return (
      <StatePanel
        kind={missing ? "empty" : "unavailable"}
        title={missing ? "Analysis not found" : "Analysis unavailable"}
        description={
          missing
            ? `No stored analysis exists for session ${sessionId}.`
            : "The analysis could not be retrieved. Please try again."
        }
        action={
          missing ? (
            <Button
              component={Link}
              to="/sessions"
              startIcon={<ArrowLeft aria-hidden size={17} />}
            >
              Session history
            </Button>
          ) : (
            <Button
              onClick={() => result.refetch()}
              startIcon={<RefreshCw aria-hidden size={17} />}
              variant="outlined"
            >
              Retry
            </Button>
          )
        }
      />
    );
  }

  return (
    <Box sx={{ minWidth: 0, "& p": { overflowWrap: "anywhere" } }}>
      <Stack
        direction="row"
        spacing={1.5}
        sx={{ alignItems: "flex-start", mb: 3 }}
      >
        <Tooltip title="Back to session history">
          <IconButton
            component={Link}
            to="/sessions"
            aria-label="Back to session history"
          >
            <ArrowLeft aria-hidden size={20} />
          </IconButton>
        </Tooltip>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            component="h2"
            variant="h2"
            sx={{ overflowWrap: "anywhere" }}
          >
            {result.data.session_name?.trim() || `Analysis ${result.data.id}`}
          </Typography>
          <Typography color="text.secondary" variant="body2" sx={{ mt: 0.5 }}>
            Session {result.data.id} |{" "}
            {result.data.sources
              .map((source) => formatLabel(source.source_type))
              .join(", ") || "Source unknown"}
          </Typography>
        </Box>
        <Tooltip title="Refresh analysis">
          <span>
            <IconButton
              aria-label="Refresh analysis"
              disabled={result.isFetching}
              onClick={() => result.refetch()}
            >
              <RefreshCw aria-hidden size={18} />
            </IconButton>
          </span>
        </Tooltip>
      </Stack>
      <ResultMetadata result={result.data} />
      <ResultContent key={result.data.id} result={result.data} />
    </Box>
  );
}

function ResultMetadata({ result }: { result: MonitoringSessionResult }) {
  return (
    <Box sx={{ mb: 3 }}>
      <Stack
        direction="row"
        useFlexGap
        spacing={2}
        sx={{ flexWrap: "wrap", alignItems: "center" }}
      >
        <Chip
          label={`Processing: ${formatLabel(result.status)}`}
          size="small"
          variant="outlined"
          color={result.status === "failed" ? "error" : "default"}
        />
        <Typography color="text.secondary" variant="body2">
          Started{" "}
          <time dateTime={result.started_at}>
            {formatTimestamp(result.started_at)}
          </time>
        </Typography>
        {result.completed_at && (
          <Typography color="text.secondary" variant="body2">
            Completed{" "}
            <time dateTime={result.completed_at}>
              {formatTimestamp(result.completed_at)}
            </time>
          </Typography>
        )}
      </Stack>
      {result.sources.map((source) => (
        <Typography key={source.id} variant="body2" sx={{ mt: 1 }}>
          {source.original_filename || "Original filename unavailable"}
        </Typography>
      ))}
      {result.status !== "completed" && (
        <Alert
          severity={result.status === "failed" ? "error" : "info"}
          sx={{ mt: 2 }}
        >
          {result.status === "failed"
            ? "Processing failed. Any stored results may be incomplete."
            : "This analysis is not complete. Stored results may be partial."}
        </Alert>
      )}
    </Box>
  );
}

function ResultContent({ result }: { result: MonitoringSessionResult }) {
  const frame = result.frames[0];
  const singleImage =
    result.sources.length === 1 &&
    result.sources[0].source_type === "image" &&
    result.frames.length === 1 &&
    frame.input_source_id === result.sources[0].id;
  const singleVideo =
    result.sources.length === 1 &&
    result.sources[0].source_type === "video" &&
    result.frames.length > 0 &&
    result.frames.every(
      (sample) => sample.input_source_id === result.sources[0].id,
    );
  return (
    <Stack spacing={4}>
      {singleImage ? (
        <Box component="section" aria-label="Image result">
          <DetectorQuality profile={result.model_profile} />
          <FrameResult
            key={frame.id}
            frame={frame}
            filename={
              result.sources[0].original_filename || `analysis ${result.id}`
            }
          />
        </Box>
      ) : singleVideo ? (
        <Box component="section" aria-label="Video result">
          <DetectorQuality profile={result.model_profile} />
          <VideoResult
            frames={result.frames}
            filename={
              result.sources[0].original_filename || `analysis ${result.id}`
            }
          />
        </Box>
      ) : (
        <StatePanel
          kind="empty"
          title={
            !frame
              ? "No processed frames available"
              : "Sampled-frame view unavailable"
          }
          description={
            !frame
              ? "This session has no stored processed frames."
              : `${result.frames.length} processed frames are stored. This view requires one matching image or video source.`
          }
        />
      )}
      <CrowdResult result={result.dense_crowd_analysis} />
      <ModelProvenance profile={result.model_profile} />
      {result.notes && (
        <Box component="section">
          <Typography component="h2" variant="h2" sx={{ mb: 1 }}>
            Session notes
          </Typography>
          <Typography sx={{ whiteSpace: "pre-wrap" }}>
            {result.notes}
          </Typography>
        </Box>
      )}
    </Stack>
  );
}
