import { Box, Typography } from "@mui/material";

interface StatusLabelProps {
  status: "ready" | "not_ready";
}

export function StatusLabel({ status }: StatusLabelProps) {
  const ready = status === "ready";

  return (
    <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75 }}>
      <Box
        aria-hidden
        sx={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          bgcolor: ready ? "primary.main" : "warning.main",
        }}
      />
      <Typography component="span" variant="body2">
        {ready ? "Ready" : "Not ready"}
      </Typography>
    </Box>
  );
}
