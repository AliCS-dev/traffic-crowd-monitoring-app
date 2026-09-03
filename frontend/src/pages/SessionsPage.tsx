import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from "@mui/material";

import { PageHeader } from "../components/PageHeader.tsx";
import { StatePanel } from "../components/StatePanel.tsx";

export function SessionsPage() {
  return (
    <>
      <PageHeader
        description="Browse image and video monitoring sessions in one place."
        title="Session history"
      />
      <TableContainer
        sx={{
          bgcolor: "background.paper",
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 1,
        }}
      >
        <Table aria-label="Monitoring sessions">
          <TableHead>
            <TableRow>
              <TableCell>Session</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Started</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            <TableRow>
              <TableCell colSpan={3} sx={{ border: 0, p: 0 }}>
                <StatePanel
                  description="Completed and in-progress sessions will appear here."
                  kind="empty"
                  title="No sessions available"
                />
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </TableContainer>
    </>
  );
}
