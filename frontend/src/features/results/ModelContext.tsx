import { Alert, Box, Typography } from "@mui/material";
import type {
  ModelRunProfileResult,
  RuntimeProvenanceResult,
} from "../../api/analysisResults.ts";
import type { DenseCrowdAnalysisResponse } from "../../api/types.ts";
import { formatConfidence, formatLabel } from "./resultFormatting.ts";

const qualityMessages: Record<
  ModelRunProfileResult["quality_gate_status"],
  string
> = {
  failed:
    "This detector did not pass its evaluation quality gate. Counts may miss or misclassify objects and are experimental.",
  conditional:
    "This detector has conditional evaluation acceptance. Counts remain limited to the tested scenes and conditions.",
  not_evaluated:
    "This detector has no recorded evaluation decision. Its counts have not been validated for this monitoring task.",
  passed:
    "This detector passed its recorded evaluation quality gate. Individual detections can still be incorrect.",
};

export function DetectorQuality({
  profile,
}: {
  profile: ModelRunProfileResult | null;
}) {
  return (
    <Alert
      severity={profile?.quality_gate_status === "passed" ? "info" : "warning"}
      sx={{ mb: 3 }}
    >
      {profile
        ? qualityMessages[profile.quality_gate_status]
        : "No model provenance was recorded for this session. Detection accuracy and evaluation status are unknown."}
    </Alert>
  );
}

export function ModelProvenance({
  profile,
}: {
  profile: ModelRunProfileResult | null;
}) {
  return (
    <Box component="section" aria-labelledby="model-title" sx={{ minWidth: 0 }}>
      <Typography component="h2" id="model-title" variant="h2" sx={{ mb: 2 }}>
        Model used for this analysis
      </Typography>
      {profile ? (
        <Box
          component="dl"
          sx={{
            m: 0,
            display: "grid",
            gridTemplateColumns: "minmax(100px, 1fr) minmax(0, 2fr)",
            gap: 1,
            "& dt": { color: "text.secondary" },
            "& dd": { m: 0, overflowWrap: "anywhere" },
          }}
        >
          <Typography component="dt" variant="body2">
            Model
          </Typography>
          <Typography component="dd" variant="body2">
            {profile.model_id}
          </Typography>
          <Typography component="dt" variant="body2">
            Profile
          </Typography>
          <Typography component="dd" variant="body2">
            {profile.profile_id}
          </Typography>
          <Typography component="dt" variant="body2">
            Quality gate
          </Typography>
          <Typography component="dd" variant="body2">
            {formatLabel(profile.quality_gate_status)}
          </Typography>
          <Typography component="dt" variant="body2">
            Confidence threshold
          </Typography>
          <Typography component="dd" variant="body2">
            {formatConfidence(profile.confidence)}
          </Typography>
          <Typography component="dt" variant="body2">
            Inference size
          </Typography>
          <Typography component="dd" variant="body2">
            {profile.image_size} px
          </Typography>
          <Typography component="dt" variant="body2">
            Evaluation record
          </Typography>
          <Typography component="dd" variant="body2">
            {profile.evaluation_reference}
          </Typography>
          <Typography component="dt" variant="body2">
            Checkpoint SHA-256
          </Typography>
          <Typography component="dd" variant="body2">
            {profile.checkpoint_sha256}
          </Typography>
          <Typography component="dt" variant="body2">
            Device
          </Typography>
          <Typography component="dd" variant="body2">
            {profile.device}
          </Typography>
        </Box>
      ) : (
        <Typography color="text.secondary">
          Model details were not stored for this session.
        </Typography>
      )}
      <RuntimeProvenance runtime={profile?.runtime_provenance ?? null} />
    </Box>
  );
}

function RuntimeProvenance({
  runtime,
}: {
  runtime: RuntimeProvenanceResult | null;
}) {
  if (!runtime) {
    return (
      <Typography color="text.secondary" sx={{ mt: 2 }}>
        Runtime provenance unavailable for this session.
      </Typography>
    );
  }
  const fields = [
    ["Application commit", runtime.application_commit ?? "Unavailable"],
    [
      "Source state",
      runtime.source_dirty === null
        ? "Unknown"
        : runtime.source_dirty
          ? "Modified"
          : "Clean",
    ],
    ["Backend source SHA-256", runtime.source_sha256],
    ["Captured", new Date(runtime.captured_at).toLocaleString()],
    ["Python", runtime.python_version],
    ["Platform", runtime.platform],
    ["GPU", runtime.gpu_name ?? "Unavailable"],
    ["CUDA", runtime.cuda_version ?? "Unavailable"],
    ["cuDNN", runtime.cudnn_version ?? "Unavailable"],
    ["Container ID", runtime.container_id ?? "Unavailable"],
  ];
  return (
    <Box component="details" sx={{ mt: 2, minWidth: 0 }}>
      <Box component="summary" sx={{ cursor: "pointer", py: 1 }}>
        Runtime environment
      </Box>
      <Box
        component="dl"
        sx={{
          m: 0,
          display: "grid",
          gridTemplateColumns: "minmax(100px, 1fr) minmax(0, 2fr)",
          gap: 1,
          "& dt": { color: "text.secondary" },
          "& dd": { m: 0, overflowWrap: "anywhere" },
        }}
      >
        {fields.map(([label, value]) => (
          <Box key={label} sx={{ display: "contents" }}>
            <Typography component="dt" variant="body2">
              {label}
            </Typography>
            <Typography component="dd" variant="body2">
              {value}
            </Typography>
          </Box>
        ))}
      </Box>
      <Box component="details" sx={{ mt: 1 }}>
        <Box component="summary" sx={{ cursor: "pointer", py: 1 }}>
          Dependencies
        </Box>
        <Box
          component="dl"
          sx={{
            m: 0,
            display: "grid",
            gridTemplateColumns: "minmax(0, 2fr) minmax(0, 1fr)",
            gap: 1,
            overflowWrap: "anywhere",
            "& dd": { m: 0 },
          }}
        >
          {Object.entries(runtime.dependencies)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([name, version]) => (
              <Box key={name} sx={{ display: "contents" }}>
                <Typography component="dt" variant="body2">
                  {name}
                </Typography>
                <Typography component="dd" variant="body2">
                  {version}
                </Typography>
              </Box>
            ))}
        </Box>
      </Box>
    </Box>
  );
}

export function CrowdResult({
  result,
}: {
  result: DenseCrowdAnalysisResponse | null;
}) {
  return (
    <Box component="section" aria-labelledby="crowd-title" sx={{ minWidth: 0 }}>
      <Typography component="h2" id="crowd-title" variant="h2" sx={{ mb: 2 }}>
        Dense-crowd analysis
      </Typography>
      {result === null ? (
        <Typography color="text.secondary">
          No dense-crowd analysis was recorded for this session.
        </Typography>
      ) : (
        <>
          <Alert
            severity={
              result.status === "unsupported" ||
              result.quality_gate_status !== "passed"
                ? "warning"
                : "info"
            }
          >
            <Typography sx={{ fontWeight: 650 }}>
              {result.status === "unsupported"
                ? "Dense-crowd counting unsupported"
                : `Estimated crowd count: ${result.count}`}
            </Typography>
            <Typography variant="body2">{result.message}</Typography>
            {result.status === "completed" && (
              <Typography variant="body2">
                Quality gate: {formatLabel(result.quality_gate_status)}
              </Typography>
            )}
          </Alert>
          <Typography
            color="text.secondary"
            variant="body2"
            sx={{ mt: 1, overflowWrap: "anywhere" }}
          >
            Evaluation record: {result.evaluation_reference}
          </Typography>
        </>
      )}
    </Box>
  );
}
