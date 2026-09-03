import type { ReactNode } from "react";
import { Box, CircularProgress, Stack, Typography } from "@mui/material";
import { CircleAlert, Inbox, WifiOff } from "lucide-react";

type StateKind = "loading" | "empty" | "error" | "unavailable";

interface StatePanelProps {
  kind: StateKind;
  title: string;
  description?: string;
  action?: ReactNode;
}

const stateIcons = {
  empty: Inbox,
  error: CircleAlert,
  unavailable: WifiOff,
};

export function StatePanel({
  kind,
  title,
  description,
  action,
}: StatePanelProps) {
  const Icon = kind === "loading" ? null : stateIcons[kind];
  const urgent = kind === "error" || kind === "unavailable";

  return (
    <Stack
      aria-live="polite"
      role={urgent ? "alert" : "status"}
      spacing={1.25}
      sx={{
        minHeight: 220,
        alignItems: "center",
        justifyContent: "center",
        border: "1px dashed",
        borderColor: urgent ? "error.light" : "divider",
        bgcolor: "background.paper",
        borderRadius: 1,
        px: 3,
        py: 5,
        textAlign: "center",
      }}
    >
      {kind === "loading" ? (
        <CircularProgress aria-hidden size={26} thickness={4} />
      ) : (
        Icon && <Icon aria-hidden size={26} strokeWidth={1.8} />
      )}
      <Box>
        <Typography component="h2" variant="h2">
          {title}
        </Typography>
        {description && (
          <Typography color="text.secondary" sx={{ mt: 0.5, maxWidth: 480 }}>
            {description}
          </Typography>
        )}
      </Box>
      {action}
    </Stack>
  );
}
