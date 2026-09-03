import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell.tsx";
import { StatePanel } from "./components/StatePanel.tsx";

const WorkspacePage = lazy(() =>
  import("./pages/WorkspacePage.tsx").then(({ WorkspacePage }) => ({
    default: WorkspacePage,
  })),
);
const SessionsPage = lazy(() =>
  import("./pages/SessionsPage.tsx").then(({ SessionsPage }) => ({
    default: SessionsPage,
  })),
);
const ResultsPage = lazy(() =>
  import("./pages/ResultsPage.tsx").then(({ ResultsPage }) => ({
    default: ResultsPage,
  })),
);
const NotFoundPage = lazy(() =>
  import("./pages/NotFoundPage.tsx").then(({ NotFoundPage }) => ({
    default: NotFoundPage,
  })),
);

function DeferredRoute({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={<StatePanel kind="loading" title="Loading workspace" />}
    >
      {children}
    </Suspense>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate replace to="/workspace" />} />
        <Route
          path="workspace"
          element={
            <DeferredRoute>
              <WorkspacePage />
            </DeferredRoute>
          }
        />
        <Route
          path="sessions"
          element={
            <DeferredRoute>
              <SessionsPage />
            </DeferredRoute>
          }
        />
        <Route
          path="analyses"
          element={
            <DeferredRoute>
              <ResultsPage />
            </DeferredRoute>
          }
        />
        <Route
          path="analyses/:sessionId"
          element={
            <DeferredRoute>
              <ResultsPage />
            </DeferredRoute>
          }
        />
        <Route
          path="*"
          element={
            <DeferredRoute>
              <NotFoundPage />
            </DeferredRoute>
          }
        />
      </Route>
    </Routes>
  );
}
