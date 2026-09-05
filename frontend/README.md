# Frontend Application

The frontend is a separate React and TypeScript application for the traffic and
crowd monitoring workflow. It calls the FastAPI backend over HTTP and does not
import Python modules or access PostgreSQL directly.

The application provides a responsive shell, image and video submission,
persistent video-job progress, paginated session history, result routes, typed
API requests, and consistent loading, empty, error, and unavailable states.
Complete result visualisation is a separate application stage.

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

## Submitting Media

The **New analysis** tab accepts one supported image or video. We can optionally
name the session and divide the processed scene into a grid. Video submissions
also accept a sampling interval in seconds. The frontend reads formats, size
limits, and option bounds from `/api/capabilities` instead of maintaining a
second copy of backend settings.

Image analysis completes in its upload request. Video analysis returns a queued
session and the browser polls its persistent job status until it completes or
fails. Successful work opens `/analyses/<session-id>`. Validation and API errors
leave the selected file and options in place so we can correct or retry them.

The **Stop waiting** action only aborts a pending browser request. It does not
claim to cancel work that may already have reached the API. We check session
history before resubmitting after an abort. Server-side job cancellation is not
part of the current backend contract.

## Browsing Sessions

The **Sessions** page reads stored image and video analyses from
`GET /api/analyses`. It shows the session name, database ID, original filename,
source type, status, and start time. The API supplies pagination metadata, so we
request one bounded page at a time rather than loading the complete history.
Selecting the arrow at the end of a row opens that session's result route.

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
  features/     Complete workflows such as media submission and job progress
  pages/        Route-level workspace, session, and result views
  test/         Shared unit-test setup and render helpers
  App.tsx       Application routes
  config.ts     Validated browser environment configuration
  theme.ts      Shared Material UI tokens and component defaults
```
