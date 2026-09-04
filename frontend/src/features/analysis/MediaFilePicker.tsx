import { useRef, useState, type DragEvent } from "react";
import {
  Box,
  Button,
  FormHelperText,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import { FileImage, FileVideo, Upload, X } from "lucide-react";

import type { UploadCapabilities } from "../../api/types.ts";
import { formatBytes, type MediaMode } from "./analysisForm.ts";

interface MediaFilePickerProps {
  mode: MediaMode;
  capabilities: UploadCapabilities;
  file: File | null;
  error?: string;
  disabled?: boolean;
  onSelect: (file: File | null) => void;
  onReject: (message: string) => void;
}

export function MediaFilePicker({
  mode,
  capabilities,
  file,
  error,
  disabled = false,
  onSelect,
  onReject,
}: MediaFilePickerProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const label = mode === "image" ? "image" : "video";
  const Icon = mode === "image" ? FileImage : FileVideo;

  function acceptFiles(files: FileList | null) {
    if (!files?.length) return;
    if (files.length !== 1) {
      onReject("Select one file at a time.");
      return;
    }
    onSelect(files[0]);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    if (!disabled) acceptFiles(event.dataTransfer.files);
  }

  return (
    <Box>
      <Typography component="h3" sx={{ fontSize: 15, fontWeight: 700, mb: 1 }}>
        Source file
      </Typography>
      {file ? (
        <Stack
          direction="row"
          spacing={1.5}
          sx={{
            minHeight: 92,
            minWidth: 0,
            alignItems: "center",
            border: "1px solid",
            borderColor: error ? "error.main" : "divider",
            borderRadius: 1,
            bgcolor: "background.paper",
            p: 2,
          }}
        >
          <Icon aria-hidden color="#315b85" size={24} strokeWidth={1.8} />
          <Box sx={{ minWidth: 0, flexGrow: 1 }}>
            <Typography
              title={file.name}
              sx={{ overflowWrap: "anywhere", fontWeight: 650 }}
            >
              {file.name}
            </Typography>
            <Typography color="text.secondary" variant="body2">
              {formatBytes(file.size)}
            </Typography>
          </Box>
          <Tooltip title="Remove selected file">
            <span>
              <IconButton
                aria-label="Remove selected file"
                disabled={disabled}
                onClick={() => onSelect(null)}
                size="small"
              >
                <X aria-hidden size={19} />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
      ) : (
        <Box
          onDragEnter={(event) => {
            event.preventDefault();
            if (!disabled) setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
          sx={{
            minHeight: 150,
            display: "grid",
            placeItems: "center",
            border: "1px dashed",
            borderColor: error
              ? "error.main"
              : dragActive
                ? "primary.main"
                : "divider",
            borderRadius: 1,
            bgcolor: dragActive ? "primary.light" : "background.paper",
            px: 2,
            py: 3,
            textAlign: "center",
          }}
        >
          <Stack spacing={1} sx={{ alignItems: "center" }}>
            <Upload aria-hidden size={25} strokeWidth={1.8} />
            <Typography sx={{ fontWeight: 650 }}>
              Drop one {label} here
            </Typography>
            <Button
              disabled={disabled}
              onClick={() => inputRef.current?.click()}
              size="small"
              variant="outlined"
            >
              Choose file
            </Button>
            <Typography color="text.secondary" variant="body2">
              {capabilities.extensions.join(", ")} up to{" "}
              {formatBytes(capabilities.max_upload_bytes)}
            </Typography>
          </Stack>
        </Box>
      )}
      <input
        accept={capabilities.extensions.join(",")}
        aria-label={`Choose ${label} file`}
        disabled={disabled}
        hidden
        onChange={(event) => {
          acceptFiles(event.target.files);
          event.target.value = "";
        }}
        ref={inputRef}
        type="file"
      />
      <FormHelperText error={Boolean(error)} sx={{ minHeight: 20, mx: 0 }}>
        {error ?? " "}
      </FormHelperText>
    </Box>
  );
}
