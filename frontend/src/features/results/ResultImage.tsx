import { useState, type ReactNode } from "react";
import {
  Box,
  CircularProgress,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import { ExternalLink } from "lucide-react";

import { apiClient } from "../../api/client.ts";
import type { VisualAssetReference } from "../../api/analysisResults.ts";
import { StatePanel } from "../../components/StatePanel.tsx";

export function ResultImage({
  asset,
  filename,
  overlay,
  controls,
}: {
  asset: VisualAssetReference | null;
  filename: string;
  overlay?: ReactNode;
  controls?: ReactNode;
}) {
  const url = asset && apiClient.resolveOutputAssetUrl(asset);
  return asset && url ? (
    <AvailableResultImage
      key={url}
      asset={asset}
      filename={filename}
      url={url}
      overlay={overlay}
      controls={controls}
    />
  ) : (
    <StatePanel
      kind="unavailable"
      title="Result image unavailable"
      description="No accessible result image is attached to this analysis."
    />
  );
}

function AvailableResultImage({
  asset,
  filename,
  url,
  overlay,
  controls,
}: {
  asset: VisualAssetReference;
  filename: string;
  url: string;
  overlay?: ReactNode;
  controls?: ReactNode;
}) {
  const [state, setState] = useState<"loading" | "loaded" | "failed">(
    "loading",
  );
  if (state === "failed") {
    return (
      <StatePanel
        kind="unavailable"
        title="Result image unavailable"
        description="The saved image could not be loaded. Stored counts and detections are still available below."
      />
    );
  }
  return (
    <Box component="figure" sx={{ m: 0, minWidth: 0 }}>
      {controls && (
        <Box
          sx={{ mb: 1, visibility: state === "loaded" ? "visible" : "hidden" }}
        >
          {controls}
        </Box>
      )}
      <Box
        sx={{
          position: "relative",
          aspectRatio: `${asset.width} / ${asset.height}`,
          bgcolor: "action.hover",
        }}
      >
        {state === "loading" && (
          <Box
            role="status"
            aria-label="Loading result image"
            sx={{
              position: "absolute",
              inset: 0,
              display: "grid",
              placeItems: "center",
            }}
          >
            <CircularProgress aria-hidden size={26} />
          </Box>
        )}
        <Box
          component="img"
          alt={`Detection result for ${filename}`}
          src={url}
          width={asset.width}
          height={asset.height}
          onLoad={() => setState("loaded")}
          onError={() => setState("failed")}
          sx={{
            display: "block",
            width: "100%",
            height: "auto",
            visibility: state === "loaded" ? "visible" : "hidden",
          }}
        />
        {state === "loaded" && overlay}
      </Box>
      <Stack
        component="figcaption"
        direction="row"
        spacing={1}
        sx={{ alignItems: "center", justifyContent: "space-between", mt: 1 }}
      >
        <Typography
          color="text.secondary"
          variant="body2"
          sx={{ overflowWrap: "anywhere" }}
        >
          {asset.width} x {asset.height} px
          {asset.rendered_overlays.includes("detections") &&
            " | Saved detection overlay: all classes"}
        </Typography>
        {state === "loaded" && (
          <Tooltip title="Open result image">
            <IconButton
              component="a"
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Open result image"
              size="small"
            >
              <ExternalLink aria-hidden size={18} />
            </IconButton>
          </Tooltip>
        )}
      </Stack>
    </Box>
  );
}
