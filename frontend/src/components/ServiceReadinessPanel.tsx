import {
  Box,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../api/client.ts";
import { StatePanel } from "./StatePanel.tsx";
import { StatusLabel } from "./StatusLabel.tsx";

function formatCheckName(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

export function ServiceReadinessPanel() {
  const readiness = useQuery({
    queryKey: ["service", "readiness"],
    queryFn: ({ signal }) => apiClient.getReadiness(signal),
    refetchInterval: 30_000,
  });

  if (readiness.isPending) {
    return (
      <StatePanel
        description="Checking application dependencies."
        kind="loading"
        title="Checking system readiness"
      />
    );
  }

  if (readiness.isError) {
    return (
      <StatePanel
        description="The frontend could not reach the configured API."
        kind="unavailable"
        title="System status unavailable"
      />
    );
  }

  const checks = Object.entries(readiness.data.checks).sort(([left], [right]) =>
    left.localeCompare(right),
  );

  return (
    <Box>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 2,
          mb: 2,
        }}
      >
        <Typography component="h2" variant="h2">
          Application dependencies
        </Typography>
        <StatusLabel status={readiness.data.status} />
      </Box>
      <TableContainer
        sx={{
          bgcolor: "background.paper",
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 1,
        }}
      >
        <Table aria-label="Application dependency readiness">
          <TableHead>
            <TableRow>
              <TableCell>Dependency</TableCell>
              <TableCell align="right">Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {checks.map(([name, check]) => (
              <TableRow key={name}>
                <TableCell>{formatCheckName(name)}</TableCell>
                <TableCell align="right">
                  <StatusLabel status={check.status} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
