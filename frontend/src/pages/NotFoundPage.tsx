import { Button } from "@mui/material";
import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

import { StatePanel } from "../components/StatePanel.tsx";

export function NotFoundPage() {
  return (
    <StatePanel
      action={
        <Button
          component={Link}
          startIcon={<ArrowLeft size={18} />}
          to="/workspace"
        >
          Return to workspace
        </Button>
      }
      description="The requested page does not exist."
      kind="error"
      title="Page not found"
    />
  );
}
