import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { renderApplication } from "../../test/render.tsx";
import { AnalysisStatusPanel } from "./AnalysisStatusPanel.tsx";

it("keeps a polling outage separate from a failed server job", async () => {
  const user = userEvent.setup();
  const retryStatus = vi.fn();

  renderApplication(
    <AnalysisStatusPanel
      onCancelSubmission={vi.fn()}
      onRetryStatus={retryStatus}
      state={{
        phase: "processing",
        sessionId: 44,
        sampledFramesTotal: 20,
        sampledFramesProcessed: 8,
        progressPercent: 40,
        failureMessage: null,
      }}
      statusUnavailable
    />,
  );

  expect(screen.getByText("Processing video")).toBeInTheDocument();
  expect(screen.getByText("8 of 20 sampled frames")).toBeInTheDocument();
  expect(screen.getByText("40%")).toBeInTheDocument();
  expect(screen.queryByText("Analysis failed")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Check again" }));
  expect(retryStatus).toHaveBeenCalledOnce();
});
