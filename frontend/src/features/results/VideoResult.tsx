import { useMemo, useState } from "react";
import {
  Box,
  IconButton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { ProcessedFrameResult } from "../../api/analysisResults.ts";
import { FrameResult } from "./FrameResult.tsx";
import { formatVideoTime, orderedVideoFrames } from "./frameNavigation.ts";

export function VideoResult({
  frames,
  filename,
}: {
  frames: ProcessedFrameResult[];
  filename: string;
}) {
  const ordered = useMemo(() => orderedVideoFrames(frames), [frames]);
  const [selectedId, setSelectedId] = useState<number | null>(
    () => ordered[0]?.id ?? null,
  );
  const index = Math.max(
    0,
    ordered.findIndex((frame) => frame.id === selectedId),
  );
  const frame = ordered[index];
  if (!frame) return null;

  return (
    <>
      <Stack spacing={1.5} sx={{ mb: 3 }}>
        <Typography component="h2" variant="h2">
          Sampled video frames
        </Typography>
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: "40px minmax(0, 1fr) 40px",
            gap: 1,
            alignItems: "center",
            maxWidth: 620,
          }}
        >
          <Tooltip title="Previous sampled frame">
            <span>
              <IconButton
                aria-label="Previous sampled frame"
                disabled={index === 0}
                onClick={() => setSelectedId(ordered[index - 1].id)}
                sx={{ width: 40, height: 40 }}
              >
                <ChevronLeft aria-hidden size={20} />
              </IconButton>
            </span>
          </Tooltip>
          <TextField
            select
            label="Sampled frame"
            value={frame.id}
            onChange={(event) => setSelectedId(Number(event.target.value))}
            size="small"
            fullWidth
            slotProps={{
              select: { native: true },
              inputLabel: { shrink: true },
            }}
          >
            {ordered.map((sample, position) => (
              <option key={sample.id} value={sample.id}>
                {position + 1} |{" "}
                {formatVideoTime(sample.frame_timestamp_seconds)}
              </option>
            ))}
          </TextField>
          <Tooltip title="Next sampled frame">
            <span>
              <IconButton
                aria-label="Next sampled frame"
                disabled={index === ordered.length - 1}
                onClick={() => setSelectedId(ordered[index + 1].id)}
                sx={{ width: 40, height: 40 }}
              >
                <ChevronRight aria-hidden size={20} />
              </IconButton>
            </span>
          </Tooltip>
        </Box>
        <Typography role="status" variant="body2" color="text.secondary">
          Sample {index + 1} of {ordered.length} | Source frame{" "}
          {frame.frame_number} |{" "}
          {formatVideoTime(frame.frame_timestamp_seconds)}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Counts belong to this sampled frame, not unique objects across the
          video.
        </Typography>
      </Stack>
      <FrameResult
        key={frame.id}
        frame={frame}
        filename={`${filename}, frame ${frame.frame_number}`}
        video
      />
    </>
  );
}
