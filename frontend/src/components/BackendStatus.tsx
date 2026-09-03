import { Box, CircularProgress, Tooltip, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../api/client.ts";
import { apiBaseUrl } from "../config.ts";

export function BackendStatus() {
  const health = useQuery({
    queryKey: ["service", "health"],
    queryFn: ({ signal }) => apiClient.getHealth(signal),
    refetchInterval: 30_000,
  });

  const isOnline = health.data?.status === "ok";
  const label = health.isPending
    ? "Checking service"
    : isOnline
      ? "Backend online"
      : "Backend unavailable";

  return (
    <Tooltip title={`${label}: ${apiBaseUrl}`}>
      <Box
        aria-live="polite"
        role="status"
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 0.75,
          minWidth: { sm: 142 },
        }}
      >
        {health.isPending ? (
          <CircularProgress aria-hidden size={13} thickness={5} />
        ) : (
          <Box
            aria-hidden
            sx={{
              width: 8,
              height: 8,
              flex: "0 0 auto",
              borderRadius: "50%",
              bgcolor: isOnline ? "primary.main" : "error.main",
            }}
          />
        )}
        <Typography
          color={isOnline ? "text.primary" : "text.secondary"}
          noWrap
          variant="body2"
        >
          {label}
        </Typography>
      </Box>
    </Tooltip>
  );
}
