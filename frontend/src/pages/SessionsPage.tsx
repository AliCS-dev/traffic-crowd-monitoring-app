import { PageHeader } from "../components/PageHeader.tsx";
import { SessionHistory } from "../features/sessions/SessionHistory.tsx";

export function SessionsPage() {
  return (
    <>
      <PageHeader
        description="Browse image and video monitoring sessions in one place."
        title="Session history"
      />
      <SessionHistory />
    </>
  );
}
