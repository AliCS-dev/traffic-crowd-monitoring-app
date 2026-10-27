import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Box,
  CircularProgress,
  IconButton,
  Stack,
  Tooltip,
  Typography,
  ToggleButton,
  ToggleButtonGroup,
} from "@mui/material";
import {
  ExternalLink,
  Hand,
  MousePointer2,
  ZoomIn,
  ZoomOut,
  Maximize,
  Scan,
  FileImage,
} from "lucide-react";

import { apiClient } from "../../api/client.ts";
import type { VisualAssetReference } from "../../api/analysisResults.ts";
import { StatePanel } from "../../components/StatePanel.tsx";
import {
  constrainView,
  fitImage,
  type ViewTransform,
} from "./viewportGeometry.ts";

export function ResultImage({
  asset,
  annotatedAsset,
  filename,
  overlay,
  controls,
  onImageStateChange,
}: {
  asset: VisualAssetReference | null;
  annotatedAsset?: VisualAssetReference | null;
  filename: string;
  overlay?: ReactNode;
  controls?: ReactNode;
  onImageStateChange?: (loaded: boolean) => void;
}) {
  const url = asset && apiClient.resolveOutputAssetUrl(asset);
  return asset && url ? (
    <AvailableResultImage
      key={url}
      asset={asset}
      filename={filename}
      url={url}
      annotatedUrl={
        annotatedAsset ? apiClient.resolveOutputAssetUrl(annotatedAsset) : null
      }
      overlay={overlay}
      controls={controls}
      onImageStateChange={onImageStateChange}
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
  annotatedUrl,
  overlay,
  controls,
  onImageStateChange,
}: {
  asset: VisualAssetReference;
  filename: string;
  url: string;
  annotatedUrl: string | null;
  overlay?: ReactNode;
  controls?: ReactNode;
  onImageStateChange?: (loaded: boolean) => void;
}) {
  const [state, setState] = useState<"loading" | "loaded" | "failed">(
    "loading",
  );
  const viewport = useRef<HTMLDivElement>(null);
  const figure = useRef<HTMLElement>(null);
  const [size, setSize] = useState({
    width: asset.width,
    height: asset.height,
  });
  const [view, setView] = useState<ViewTransform>({ zoom: 1, x: 0, y: 0 });
  const [mode, setMode] = useState("select");
  const [fullscreenError, setFullscreenError] = useState(false);
  const drag = useRef<{
    id: number;
    x: number;
    y: number;
    origin: ViewTransform;
  } | null>(null);
  const fitted = fitImage(size.width, size.height, asset.width, asset.height);
  const current = constrainView(view, fitted, size);
  useEffect(() => {
    const element = viewport.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width && entry.contentRect.height) {
        setSize({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        });
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  function zoom(factor: number) {
    setView(
      constrainView({ ...current, zoom: current.zoom * factor }, fitted, size),
    );
  }
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
    <Box
      component="figure"
      ref={figure}
      sx={{
        m: 0,
        minWidth: 0,
        bgcolor: "background.paper",
        "&:fullscreen": {
          p: 2,
          overflow: "auto",
          "& [data-viewport]": { height: "calc(100dvh - 150px)" },
        },
      }}
    >
      <Stack
        direction="row"
        useFlexGap
        sx={{ alignItems: "center", flexWrap: "wrap", gap: 0.5, py: 1 }}
      >
        <ToggleButtonGroup
          size="small"
          exclusive
          value={mode}
          onChange={(_, value) => value && setMode(value)}
          aria-label="Scene interaction"
        >
          <ToggleButton value="select" aria-label="Select objects">
            <Tooltip title="Select objects">
              <MousePointer2 size={18} />
            </Tooltip>
          </ToggleButton>
          <ToggleButton value="pan" aria-label="Pan image">
            <Tooltip title="Pan image">
              <Hand size={18} />
            </Tooltip>
          </ToggleButton>
        </ToggleButtonGroup>
        <Tooltip title="Zoom out">
          <span>
            <IconButton
              aria-label="Zoom out"
              disabled={state !== "loaded" || current.zoom <= 1}
              onClick={() => zoom(1 / 1.5)}
            >
              <ZoomOut size={19} />
            </IconButton>
          </span>
        </Tooltip>
        <Typography variant="body2" sx={{ minWidth: 42, textAlign: "center" }}>
          {Math.round(current.zoom * 100)}%
        </Typography>
        <Tooltip title="Zoom in">
          <span>
            <IconButton
              aria-label="Zoom in"
              disabled={state !== "loaded" || current.zoom >= 8}
              onClick={() => zoom(1.5)}
            >
              <ZoomIn size={19} />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title="Fit image">
          <IconButton
            aria-label="Fit image"
            onClick={() => setView({ zoom: 1, x: 0, y: 0 })}
          >
            <Scan size={19} />
          </IconButton>
        </Tooltip>
        <Tooltip title="Fullscreen">
          <IconButton
            aria-label="Fullscreen"
            onClick={async () => {
              try {
                if (document.fullscreenElement) await document.exitFullscreen();
                else if (figure.current?.requestFullscreen)
                  await figure.current.requestFullscreen();
                else setFullscreenError(true);
              } catch {
                setFullscreenError(true);
              }
            }}
          >
            <Maximize size={19} />
          </IconButton>
        </Tooltip>
      </Stack>
      {fullscreenError && (
        <Typography role="status" variant="body2">
          Fullscreen is unavailable in this browser.
        </Typography>
      )}
      {controls && (
        <Box
          sx={{ mb: 1, visibility: state === "loaded" ? "visible" : "hidden" }}
        >
          {controls}
        </Box>
      )}
      <Box
        ref={viewport}
        data-viewport
        role="group"
        aria-label="Scene viewport"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.target !== event.currentTarget) return;
          if (event.key === "+" || event.key === "=") {
            event.preventDefault();
            zoom(1.5);
          } else if (event.key === "-") {
            event.preventDefault();
            zoom(1 / 1.5);
          } else if (event.key === "0") {
            event.preventDefault();
            setView({ zoom: 1, x: 0, y: 0 });
          } else if (
            ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(
              event.key,
            )
          ) {
            event.preventDefault();
            setView(
              constrainView(
                {
                  ...current,
                  x:
                    current.x +
                    (event.key === "ArrowLeft"
                      ? 40
                      : event.key === "ArrowRight"
                        ? -40
                        : 0),
                  y:
                    current.y +
                    (event.key === "ArrowUp"
                      ? 40
                      : event.key === "ArrowDown"
                        ? -40
                        : 0),
                },
                fitted,
                size,
              ),
            );
          }
        }}
        onPointerDown={(event) => {
          if (mode !== "pan" || event.button !== 0 || drag.current) return;
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = {
            id: event.pointerId,
            x: event.clientX,
            y: event.clientY,
            origin: current,
          };
        }}
        onPointerMove={(event) => {
          const start = drag.current;
          if (!start || event.pointerId !== start.id) return;
          setView(
            constrainView(
              {
                ...start.origin,
                x: start.origin.x + event.clientX - start.x,
                y: start.origin.y + event.clientY - start.y,
              },
              fitted,
              size,
            ),
          );
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
        onLostPointerCapture={() => {
          drag.current = null;
        }}
        sx={{
          position: "relative",
          height: { xs: 240, sm: "min(50vh, 560px)" },
          minHeight: 240,
          overflow: "hidden",
          bgcolor: "#171a1c",
          touchAction: mode === "pan" ? "none" : "pan-y",
          cursor: mode === "pan" ? "grab" : "default",
          "&:focus-visible": {
            outline: "3px solid",
            outlineColor: "primary.main",
            outlineOffset: 2,
          },
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
          data-scene-stage
          sx={{
            position: "absolute",
            left: "50%",
            top: "50%",
            width: fitted.width,
            height: fitted.height,
            transform: `translate(-50%, -50%) translate(${current.x}px, ${current.y}px) scale(${current.zoom})`,
            transformOrigin: "center",
            pointerEvents: mode === "pan" ? "none" : "auto",
          }}
        >
          <Box
            component="img"
            draggable={false}
            alt={`Detection result for ${filename}`}
            src={url}
            width={asset.width}
            height={asset.height}
            onLoad={(event) => {
              const image = event.currentTarget;
              const matches =
                image.naturalWidth === asset.width &&
                image.naturalHeight === asset.height;
              setState(matches ? "loaded" : "failed");
              onImageStateChange?.(matches);
            }}
            onError={() => {
              setState("failed");
              onImageStateChange?.(false);
            }}
            sx={{
              display: "block",
              width: "100%",
              height: "100%",
              visibility: state === "loaded" ? "visible" : "hidden",
            }}
          />
          {state === "loaded" && overlay}
        </Box>
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
        <Stack direction="row">
          {annotatedUrl && annotatedUrl !== url && (
            <Tooltip title="Open annotated image">
              <IconButton
                component="a"
                href={annotatedUrl}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Open annotated image"
                size="small"
              >
                <FileImage aria-hidden size={18} />
              </IconButton>
            </Tooltip>
          )}
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
      </Stack>
    </Box>
  );
}
