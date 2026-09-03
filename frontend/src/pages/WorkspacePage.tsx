import { useState } from "react";
import { Box, Tab, Tabs } from "@mui/material";

import { PageHeader } from "../components/PageHeader.tsx";
import { ServiceReadinessPanel } from "../components/ServiceReadinessPanel.tsx";
import { StatePanel } from "../components/StatePanel.tsx";

export function WorkspacePage() {
  const [activeTab, setActiveTab] = useState(0);

  return (
    <>
      <PageHeader
        description="Review active processing work and the services required for analysis."
        title="Analysis workspace"
      />
      <Box sx={{ borderBottom: "1px solid", borderColor: "divider", mb: 3 }}>
        <Tabs
          aria-label="Workspace views"
          onChange={(_, value: number) => setActiveTab(value)}
          value={activeTab}
        >
          <Tab
            aria-controls="workspace-panel-queue"
            id="workspace-tab-queue"
            label="Analysis queue"
          />
          <Tab
            aria-controls="workspace-panel-readiness"
            id="workspace-tab-readiness"
            label="System readiness"
          />
        </Tabs>
      </Box>
      <Box
        aria-labelledby="workspace-tab-queue"
        hidden={activeTab !== 0}
        id="workspace-panel-queue"
        role="tabpanel"
      >
        {activeTab === 0 && (
          <StatePanel
            description="Submitted image and video analyses will appear here."
            kind="empty"
            title="No active analyses"
          />
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
