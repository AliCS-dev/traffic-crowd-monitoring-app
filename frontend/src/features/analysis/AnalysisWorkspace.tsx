import { Box } from "@mui/material";

import type { AnalysisCapabilitiesResponse } from "../../api/types.ts";
import { AnalysisStatusPanel } from "./AnalysisStatusPanel.tsx";
import { AnalysisSubmissionForm } from "./AnalysisSubmissionForm.tsx";
import { useAnalysisWorkflow } from "./useAnalysisWorkflow.ts";

export function AnalysisWorkspace({
  capabilities,
}: {
  capabilities: AnalysisCapabilitiesResponse;
}) {
  const workflow = useAnalysisWorkflow();
  const busy = ["submitting", "queued", "processing"].includes(
    workflow.state.phase,
  );

  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: {
          xs: "minmax(0, 1fr)",
          lg: "minmax(0, 3fr) minmax(280px, 2fr)",
        },
        alignItems: "start",
        gap: 3,
      }}
    >
      <AnalysisSubmissionForm
        busy={busy}
        capabilities={capabilities}
        onResetWorkflow={workflow.reset}
        onSubmit={workflow.submit}
      />
      <AnalysisStatusPanel
        onCancelSubmission={workflow.cancelSubmission}
        onRetryStatus={workflow.retryStatus}
        state={workflow.state}
        statusUnavailable={workflow.statusUnavailable}
      />
    </Box>
  );
}
