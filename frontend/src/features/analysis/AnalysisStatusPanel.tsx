import {
  Alert,
  Box,
  Button,
  CircularProgress,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import { CircleCheck, RefreshCw, Square } from "lucide-react";

import type { AnalysisWorkflowState } from "./useAnalysisWorkflow.ts";

interface AnalysisStatusPanelProps {
  state: AnalysisWorkflowState;
  statusUnavailable: boolean;
  onCancelSubmission: () => void;
  onRetryStatus: () => void;
}

export function AnalysisStatusPanel({
  state,
  statusUnavailable,
  onCancelSubmission,
  onRetryStatus,
}: AnalysisStatusPanelProps) {
  const running = state.phase === "queued" || state.phase === "processing";

  return (
    <Box
      aria-live="polite"
      sx={{
        minWidth: 0,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        bgcolor: "background.paper",
        p: { xs: 2, sm: 3 },
      }}
    >
      <Typography component="h2" variant="h2">
        Processing status
      </Typography>

      {state.phase === "idle" && (
        <Typography color="text.secondary" sx={{ mt: 1 }}>
          The progress of the current submission will appear here.
        </Typography>
      )}

      {state.phase === "submitting" && (
        <Stack spacing={2} sx={{ alignItems: "flex-start", mt: 2 }}>
          <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
            <CircularProgress aria-hidden size={22} thickness={4.5} />
            <Box>
              <Typography sx={{ fontWeight: 700 }}>Uploading media</Typography>
              <Typography color="text.secondary" variant="body2">
                Waiting for the analysis service to accept the file.
              </Typography>
            </Box>
          </Stack>
          <Button
            color="inherit"
            onClick={onCancelSubmission}
            size="small"
            startIcon={<Square aria-hidden size={16} />}
            variant="outlined"
          >
            Stop waiting
          </Button>
          <Typography color="text.secondary" variant="body2">
            This stops the browser request. Processing may continue if the
            server has already received it.
          </Typography>
        </Stack>
      )}

      {running && (
        <Stack spacing={1.5} sx={{ mt: 2 }}>
          <Box>
            <Typography sx={{ fontWeight: 700 }}>
              {state.phase === "queued" ? "Video queued" : "Processing video"}
            </Typography>
            <Typography color="text.secondary" variant="body2">
              Session {state.sessionId}
            </Typography>
          </Box>
          <LinearProgress
            aria-label="Video processing progress"
            value={state.progressPercent ?? 0}
            variant="determinate"
          />
          <Stack
            direction="row"
            spacing={2}
            sx={{ justifyContent: "space-between" }}
          >
            <Typography color="text.secondary" variant="body2">
              {state.sampledFramesProcessed ?? 0} of{" "}
              {state.sampledFramesTotal ?? 0} sampled frames
            </Typography>
            <Typography sx={{ fontWeight: 700 }} variant="body2">
              {Math.round(state.progressPercent ?? 0)}%
            </Typography>
          </Stack>
          {statusUnavailable && (
            <Alert
              action={
                <Button
                  color="inherit"
                  onClick={onRetryStatus}
                  size="small"
                  startIcon={<RefreshCw aria-hidden size={15} />}
                >
                  Check again
                </Button>
              }
              severity="warning"
            >
              Status is temporarily unavailable. The server-side job has not
              been marked as failed.
            </Alert>
          )}
        </Stack>
      )}

      {state.phase === "completed" && (
        <Stack
          direction="row"
          spacing={1.5}
          sx={{ alignItems: "center", mt: 2 }}
        >
          <CircleCheck aria-hidden color="#176b61" size={24} />
          <Box>
            <Typography sx={{ fontWeight: 700 }}>Analysis completed</Typography>
            <Typography color="text.secondary" variant="body2">
              Opening session {state.sessionId}.
            </Typography>
          </Box>
        </Stack>
      )}

      {state.phase === "failed" && (
        <Alert severity="error" sx={{ mt: 2 }}>
          <Typography sx={{ fontWeight: 700 }}>Analysis failed</Typography>
          <Typography variant="body2">{state.failureMessage}</Typography>
          <Typography sx={{ mt: 0.75 }} variant="body2">
            Your selected file and options are still available in the form.
          </Typography>
        </Alert>
      )}

      {state.phase === "cancelled" && (
        <Alert severity="info" sx={{ mt: 2 }}>
          <Typography sx={{ fontWeight: 700 }}>
            Browser request stopped
          </Typography>
          <Typography variant="body2">{state.failureMessage}</Typography>
          <Typography sx={{ mt: 0.75 }} variant="body2">
            Check session history before submitting again because the server may
            already have accepted the request.
          </Typography>
        </Alert>
      )}
    </Box>
  );
}
