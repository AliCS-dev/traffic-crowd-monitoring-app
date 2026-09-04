import { useState } from "react";
import { Box, Button, Tab, Tabs } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { apiClient } from "../api/client.ts";
import { PageHeader } from "../components/PageHeader.tsx";
import { ServiceReadinessPanel } from "../components/ServiceReadinessPanel.tsx";
import { StatePanel } from "../components/StatePanel.tsx";
import { AnalysisWorkspace } from "../features/analysis/AnalysisWorkspace.tsx";

export function WorkspacePage() {
  const [activeTab, setActiveTab] = useState(0);
  const capabilities = useQuery({
    queryKey: ["analysis", "capabilities"],
    queryFn: ({ signal }) => apiClient.getCapabilities(signal),
  });

  return (
    <>
      <PageHeader
        description="Submit aerial images or videos and follow their processing state."
        title="Analysis workspace"
      />
      <Box sx={{ borderBottom: "1px solid", borderColor: "divider", mb: 3 }}>
        <Tabs
          aria-label="Workspace views"
          onChange={(_, value: number) => setActiveTab(value)}
          value={activeTab}
        >
          <Tab
            aria-controls="workspace-panel-new-analysis"
            id="workspace-tab-new-analysis"
            label="New analysis"
          />
          <Tab
            aria-controls="workspace-panel-readiness"
            id="workspace-tab-readiness"
            label="System readiness"
          />
        </Tabs>
      </Box>
      <Box
        aria-labelledby="workspace-tab-new-analysis"
        hidden={activeTab !== 0}
        id="workspace-panel-new-analysis"
        role="tabpanel"
      >
        {activeTab === 0 && capabilities.isPending && (
          <StatePanel
            description="Reading supported formats and processing limits."
            kind="loading"
            title="Preparing analysis form"
          />
        )}
        {activeTab === 0 && capabilities.isError && (
          <StatePanel
            action={
              <Button
                onClick={() => capabilities.refetch()}
                startIcon={<RefreshCw aria-hidden size={17} />}
                variant="outlined"
              >
                Try again
              </Button>
            }
            description="The application could not read upload settings from the API."
            kind="unavailable"
            title="Analysis form unavailable"
          />
        )}
        {activeTab === 0 && capabilities.data && (
          <AnalysisWorkspace capabilities={capabilities.data} />
        )}
      </Box>
      <Box
        aria-labelledby="workspace-tab-readiness"
        hidden={activeTab !== 1}
        id="workspace-panel-readiness"
        role="tabpanel"
      >
        {activeTab === 1 && <ServiceReadinessPanel />}
      </Box>
    </>
  );
}
