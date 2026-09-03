# Frontend Application

The frontend is a separate React and TypeScript application for the traffic and
crowd monitoring workflow. It calls the FastAPI backend over HTTP and does not
import Python modules or access PostgreSQL directly.

The current foundation provides the responsive application shell, workspace,
session-history and result routes, typed health and readiness requests, and
consistent loading, empty, error, and unavailable states. Media submission and
complete result visualisation are added in the next application stages.

## Local Development

We use Node.js 24 LTS and the committed npm lockfile. From `frontend/`, we
install the exact dependency versions with:

```bash
npm ci
```

The browser reads the backend address from `VITE_API_BASE_URL`. We can create a
local configuration from the safe example:

```bash
cp .env.example .env
```

With the FastAPI server listening on port 8000, we start the frontend with:

```bash
npm run dev
```

The application is then available at <http://localhost:5173>. PostgreSQL and the
backend remain separate processes; the frontend does not require its own Docker
container during local development.

## Quality Checks

Before a pull request, we run:

```bash
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
```

GitHub Actions repeats these commands from a clean `npm ci` installation. The
frontend dependencies are also covered by the repository's weekly Dependabot
configuration.

## Source Structure

```text
src/
  api/          Typed HTTP client and response contracts
  components/   Shared layout, status, and state components
  pages/        Route-level workspace, session, and result views
  test/         Shared unit-test setup and render helpers
  App.tsx       Application routes
  config.ts     Validated browser environment configuration
  theme.ts      Shared Material UI tokens and component defaults
```
