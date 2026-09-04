import { useState, type FormEvent } from "react";
import {
  Box,
  Button,
  FormControlLabel,
  Stack,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import { FileImage, FileVideo, Play } from "lucide-react";

import type { AnalysisCapabilitiesResponse } from "../../api/types.ts";
import {
  initialAnalysisFormDraft,
  validateAnalysisDraft,
  validateMediaFile,
  type AnalysisFormDraft,
  type AnalysisFormErrors,
  type MediaMode,
  type ValidatedAnalysisSubmission,
} from "./analysisForm.ts";
import { MediaFilePicker } from "./MediaFilePicker.tsx";

interface AnalysisSubmissionFormProps {
  capabilities: AnalysisCapabilitiesResponse;
  busy: boolean;
  onSubmit: (submission: ValidatedAnalysisSubmission) => void;
  onResetWorkflow: () => void;
}

export function AnalysisSubmissionForm({
  capabilities,
  busy,
  onSubmit,
  onResetWorkflow,
}: AnalysisSubmissionFormProps) {
  const [draft, setDraft] = useState<AnalysisFormDraft>(() => ({
    ...initialAnalysisFormDraft,
    samplingIntervalSeconds: String(
      capabilities.options.default_sampling_interval_seconds,
    ),
  }));
  const [errors, setErrors] = useState<AnalysisFormErrors>({});

  function updateDraft(update: Partial<AnalysisFormDraft>) {
    setDraft((current) => ({ ...current, ...update }));
  }

  function changeMode(nextMode: MediaMode | null) {
    if (nextMode === null || nextMode === draft.mode) return;
    updateDraft({ mode: nextMode, file: null });
    setErrors({});
    onResetWorkflow();
  }

  function chooseFile(file: File | null) {
    updateDraft({ file });
    setErrors((current) => ({
      ...current,
      file:
        file === null
          ? undefined
          : validateMediaFile(file, draft.mode, capabilities),
    }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = validateAnalysisDraft(draft, capabilities);
    setErrors(result.errors);
    if (result.submission) onSubmit(result.submission);
  }

  return (
    <Box
      component="form"
      noValidate
      onSubmit={handleSubmit}
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
        New analysis
      </Typography>
      <Typography color="text.secondary" sx={{ mt: 0.5, mb: 2.5 }}>
        Choose aerial media and configure how it should be processed.
      </Typography>

      <ToggleButtonGroup
        aria-label="Media type"
        color="primary"
        disabled={busy}
        exclusive
        fullWidth
        onChange={(_, value: MediaMode | null) => changeMode(value)}
        size="small"
        value={draft.mode}
      >
        <ToggleButton value="image">
          <FileImage aria-hidden size={18} />
          <Box component="span" sx={{ ml: 1 }}>
            Image
          </Box>
        </ToggleButton>
        <ToggleButton value="video">
          <FileVideo aria-hidden size={18} />
          <Box component="span" sx={{ ml: 1 }}>
            Video
          </Box>
        </ToggleButton>
      </ToggleButtonGroup>

      <Box sx={{ mt: 2.5 }}>
        <MediaFilePicker
          capabilities={capabilities[draft.mode]}
          disabled={busy}
          error={errors.file}
          file={draft.file}
          mode={draft.mode}
          onReject={(message) =>
            setErrors((current) => ({ ...current, file: message }))
          }
          onSelect={chooseFile}
        />
      </Box>

      <Stack spacing={2} sx={{ mt: 1 }}>
        <TextField
          disabled={busy}
          error={Boolean(errors.sessionName)}
          fullWidth
          helperText={
            errors.sessionName ?? "Optional name shown in session history."
          }
          label="Session name"
          onChange={(event) => {
            updateDraft({ sessionName: event.target.value });
            setErrors((current) => ({ ...current, sessionName: undefined }));
          }}
          size="small"
          slotProps={{
            htmlInput: {
              maxLength: capabilities.options.max_session_name_length + 1,
            },
          }}
          value={draft.sessionName}
        />

        <Box>
          <FormControlLabel
            control={
              <Switch
                checked={draft.gridEnabled}
                disabled={busy}
                onChange={(event) => {
                  updateDraft({ gridEnabled: event.target.checked });
                  if (!event.target.checked) {
                    setErrors((current) => ({
                      ...current,
                      gridRows: undefined,
                      gridColumns: undefined,
                    }));
                  }
                }}
              />
            }
            label="Divide the scene into a grid"
          />
          {draft.gridEnabled && (
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
                gap: 2,
                mt: 1,
              }}
            >
              <TextField
                disabled={busy}
                error={Boolean(errors.gridRows)}
                helperText={errors.gridRows ?? "Number of horizontal rows."}
                label="Grid rows"
                onChange={(event) => {
                  updateDraft({ gridRows: event.target.value });
                  setErrors((current) => ({ ...current, gridRows: undefined }));
                }}
                size="small"
                slotProps={{
                  htmlInput: {
                    inputMode: "numeric",
                    min: 1,
                    max: capabilities.options.max_grid_dimension,
                  },
                }}
                type="number"
                value={draft.gridRows}
              />
              <TextField
                disabled={busy}
                error={Boolean(errors.gridColumns)}
                helperText={errors.gridColumns ?? "Number of vertical columns."}
                label="Grid columns"
                onChange={(event) => {
                  updateDraft({ gridColumns: event.target.value });
                  setErrors((current) => ({
                    ...current,
                    gridColumns: undefined,
                  }));
                }}
                size="small"
                slotProps={{
                  htmlInput: {
                    inputMode: "numeric",
                    min: 1,
                    max: capabilities.options.max_grid_dimension,
                  },
                }}
                type="number"
                value={draft.gridColumns}
              />
            </Box>
          )}
        </Box>

        {draft.mode === "video" && (
          <TextField
            disabled={busy}
            error={Boolean(errors.samplingIntervalSeconds)}
            fullWidth
            helperText={
              errors.samplingIntervalSeconds ??
              "Time between sampled video frames, in seconds."
            }
            label="Sampling interval"
            onChange={(event) => {
              updateDraft({ samplingIntervalSeconds: event.target.value });
              setErrors((current) => ({
                ...current,
                samplingIntervalSeconds: undefined,
              }));
            }}
            size="small"
            slotProps={{
              htmlInput: {
                inputMode: "decimal",
                min: 0.01,
                max: capabilities.options.max_sampling_interval_seconds,
                step: 0.1,
              },
            }}
            type="number"
            value={draft.samplingIntervalSeconds}
          />
        )}

        <Button
          disabled={busy}
          startIcon={<Play aria-hidden size={18} />}
          sx={{ alignSelf: { sm: "flex-start" }, minWidth: 150 }}
          type="submit"
          variant="contained"
        >
          Start analysis
        </Button>
      </Stack>
    </Box>
  );
}
