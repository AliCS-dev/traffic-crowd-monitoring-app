import type {
  AnalysisCapabilitiesResponse,
  AnalysisSubmissionOptions,
  VideoAnalysisSubmissionOptions,
} from "../../api/types.ts";

export type MediaMode = "image" | "video";

export interface AnalysisFormDraft {
  mode: MediaMode;
  file: File | null;
  sessionName: string;
  gridEnabled: boolean;
  gridRows: string;
  gridColumns: string;
  samplingIntervalSeconds: string;
}

export interface AnalysisFormErrors {
  file?: string;
  sessionName?: string;
  gridRows?: string;
  gridColumns?: string;
  samplingIntervalSeconds?: string;
}

export type ValidatedAnalysisSubmission =
  | {
      mode: "image";
      file: File;
      options: AnalysisSubmissionOptions;
    }
  | {
      mode: "video";
      file: File;
      options: VideoAnalysisSubmissionOptions;
    };

export const initialAnalysisFormDraft: AnalysisFormDraft = {
  mode: "image",
  file: null,
  sessionName: "",
  gridEnabled: false,
  gridRows: "3",
  gridColumns: "3",
  samplingIntervalSeconds: "1",
};

export function validateAnalysisDraft(
  draft: AnalysisFormDraft,
  capabilities: AnalysisCapabilitiesResponse,
): { submission?: ValidatedAnalysisSubmission; errors: AnalysisFormErrors } {
  const errors: AnalysisFormErrors = {};
  if (draft.file === null) {
    errors.file = `Select a ${draft.mode} file.`;
  } else {
    errors.file = validateMediaFile(draft.file, draft.mode, capabilities);
  }

  const sessionName = draft.sessionName.trim();
  if (sessionName.length > capabilities.options.max_session_name_length) {
    errors.sessionName = `Use at most ${capabilities.options.max_session_name_length} characters.`;
  }

  let gridRows: number | null = null;
  let gridColumns: number | null = null;
  if (draft.gridEnabled) {
    gridRows = parseGridDimension(
      draft.gridRows,
      capabilities.options.max_grid_dimension,
    );
    gridColumns = parseGridDimension(
      draft.gridColumns,
      capabilities.options.max_grid_dimension,
    );
    if (gridRows === null) {
      errors.gridRows = `Enter 1-${capabilities.options.max_grid_dimension}.`;
    }
    if (gridColumns === null) {
      errors.gridColumns = `Enter 1-${capabilities.options.max_grid_dimension}.`;
    }
  }

  let samplingIntervalSeconds: number | null = null;
  if (draft.mode === "video") {
    samplingIntervalSeconds = Number(draft.samplingIntervalSeconds);
    if (
      !Number.isFinite(samplingIntervalSeconds) ||
      samplingIntervalSeconds <= 0 ||
      samplingIntervalSeconds >
        capabilities.options.max_sampling_interval_seconds
    ) {
      errors.samplingIntervalSeconds = `Enter more than 0 and at most ${capabilities.options.max_sampling_interval_seconds} seconds.`;
    }
  }

  if (Object.values(errors).some(Boolean) || draft.file === null) {
    return { errors };
  }

  const commonOptions: AnalysisSubmissionOptions = {
    sessionName: sessionName || null,
    gridRows,
    gridColumns,
  };
  if (draft.mode === "video") {
    return {
      errors,
      submission: {
        mode: "video",
        file: draft.file,
        options: {
          ...commonOptions,
          samplingIntervalSeconds: samplingIntervalSeconds as number,
        },
      },
    };
  }

  return {
    errors,
    submission: {
      mode: "image",
      file: draft.file,
      options: commonOptions,
    },
  };
}

export function validateMediaFile(
  file: File,
  mode: MediaMode,
  capabilities: AnalysisCapabilitiesResponse,
): string | undefined {
  const policy = capabilities[mode];
  const extension = file.name.includes(".")
    ? `.${file.name.split(".").pop()!.toLowerCase()}`
    : "";

  if (!policy.extensions.includes(extension)) {
    return `Choose one of: ${policy.extensions.join(", ")}.`;
  }
  if (policy.mime_type_by_extension[extension] !== file.type) {
    return `The selected file type does not match a supported ${mode} format.`;
  }
  if (file.size === 0) {
    return "The selected file is empty.";
  }
  if (file.size > policy.max_upload_bytes) {
    return `The selected file exceeds the ${formatBytes(policy.max_upload_bytes)} limit.`;
  }
  return undefined;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const precision = value >= 10 ? 0 : 1;
  return `${value.toFixed(precision)} ${units[unitIndex]}`;
}

function parseGridDimension(value: string, maximum: number): number | null {
  if (!/^\d+$/.test(value.trim())) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= maximum
    ? parsed
    : null;
}
