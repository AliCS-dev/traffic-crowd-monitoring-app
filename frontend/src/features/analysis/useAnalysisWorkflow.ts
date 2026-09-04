import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { apiClient, ApiRequestError } from "../../api/client.ts";
import type {
  ImageAnalysisCreatedResponse,
  VideoAnalysisCreatedResponse,
  VideoAnalysisJobResponse,
} from "../../api/types.ts";
import type { ValidatedAnalysisSubmission } from "./analysisForm.ts";

export type AnalysisWorkflowPhase =
  | "idle"
  | "submitting"
  | "queued"
  | "processing"
  | "completed"
  | "failed"
  | "cancelled";

export interface AnalysisWorkflowState {
  phase: AnalysisWorkflowPhase;
  sessionId: number | null;
  sampledFramesTotal: number | null;
  sampledFramesProcessed: number | null;
  progressPercent: number | null;
  failureMessage: string | null;
}

type SubmissionResult =
  | { mode: "image"; response: ImageAnalysisCreatedResponse }
  | { mode: "video"; response: VideoAnalysisCreatedResponse };

const initialState: AnalysisWorkflowState = {
  phase: "idle",
  sessionId: null,
  sampledFramesTotal: null,
  sampledFramesProcessed: null,
  progressPercent: null,
  failureMessage: null,
};

export function useAnalysisWorkflow() {
  const navigate = useNavigate();
  const abortController = useRef<AbortController | null>(null);
  const [state, setState] = useState<AnalysisWorkflowState>(initialState);
  const [videoSessionId, setVideoSessionId] = useState<number | null>(null);

  const submission = useMutation({
    mutationFn: async (
      input: ValidatedAnalysisSubmission,
    ): Promise<SubmissionResult> => {
      const controller = new AbortController();
      abortController.current = controller;
      if (input.mode === "image") {
        return {
          mode: "image",
          response: await apiClient.submitImage(
            input.file,
            input.options,
            controller.signal,
          ),
        };
      }
      return {
        mode: "video",
        response: await apiClient.submitVideo(
          input.file,
          input.options,
          controller.signal,
        ),
      };
    },
    onMutate: () => {
      setVideoSessionId(null);
      setState({ ...initialState, phase: "submitting" });
    },
    onSuccess: (result) => {
      abortController.current = null;
      if (result.mode === "image") {
        const sessionId = result.response.session_id;
        setState({
          ...initialState,
          phase: "completed",
          sessionId,
          progressPercent: 100,
        });
        navigate(`/analyses/${sessionId}`);
        return;
      }

      const { response } = result;
      setState({
        phase: "queued",
        sessionId: response.session_id,
        sampledFramesTotal: response.sampled_frames_total,
        sampledFramesProcessed: 0,
        progressPercent: 0,
        failureMessage: null,
      });
      setVideoSessionId(response.session_id);
    },
    onError: (error) => {
      abortController.current = null;
      if (isAbortError(error)) {
        setState({
          ...initialState,
          phase: "cancelled",
          failureMessage:
            "This browser stopped waiting for the submission response.",
        });
        return;
      }
      setState({
        ...initialState,
        phase: "failed",
        failureMessage: getPublicFailureMessage(error),
      });
    },
  });

  const videoJob = useQuery({
    queryKey: ["analyses", "videos", videoSessionId],
    queryFn: ({ signal }) => {
      if (videoSessionId === null) {
        throw new Error("A video session is required to read job status.");
      }
      return apiClient.getVideoJob(videoSessionId, signal);
    },
    enabled:
      videoSessionId !== null &&
      (state.phase === "queued" || state.phase === "processing"),
    retry: 2,
    refetchInterval: (query) => {
      const job = query.state.data;
      return job?.status === "queued" || job?.status === "processing"
        ? 1_000
        : false;
    },
  });

  useEffect(() => {
    const job = videoJob.data;
    if (!job) return;
    if (job.status === "completed") {
      navigate(`/analyses/${job.session_id}`);
    }
  }, [navigate, videoJob.data]);

  const currentState = videoJob.data
    ? createStateFromVideoJob(videoJob.data)
    : state;

  return {
    state: currentState,
    statusUnavailable: videoJob.isError || videoJob.isRefetchError,
    submit: (input: ValidatedAnalysisSubmission) => submission.mutate(input),
    cancelSubmission: () => abortController.current?.abort(),
    retryStatus: () => videoJob.refetch(),
    reset: () => {
      abortController.current?.abort();
      abortController.current = null;
      setVideoSessionId(null);
      submission.reset();
      setState(initialState);
    },
  };
}

function createStateFromVideoJob(
  job: VideoAnalysisJobResponse,
): AnalysisWorkflowState {
  return {
    phase: job.status,
    sessionId: job.session_id,
    sampledFramesTotal: job.sampled_frames_total,
    sampledFramesProcessed: job.sampled_frames_processed,
    progressPercent: job.progress_percent,
    failureMessage:
      job.status === "failed"
        ? (job.failure_message ?? "Video processing failed. Please retry.")
        : null,
  };
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function getPublicFailureMessage(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message;
  return "The application could not reach the analysis service. Please retry.";
}
