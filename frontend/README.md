# Frontend Application

The frontend is a separate React and TypeScript application for the traffic and
crowd monitoring workflow. It calls the FastAPI backend over HTTP and does not
import Python modules or access PostgreSQL directly.

The application provides a responsive shell, image and video submission,
persistent video-job progress, paginated session history, result routes, typed
API requests, and consistent loading, empty, error, and unavailable states.
Image results include the saved visual output, object counts, confidence scores,
and the model decisions recorded for the session.

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

## Reading Stored Results

At `/analyses/<session-id>`, we can inspect a stored image analysis and its
original filename, processing status, and timestamps. The image already contains
the saved detection boxes, so the browser preserves its proportions without
drawing duplicate boxes. An available image can be opened at full resolution.
Only asset references matching the backend's public asset route become links.

Whole-image counts come from `frame_summaries`; they do not include grid-cell
summaries. Detection records show their stored class and confidence, with
pagination for longer lists. Missing summaries, missing images, and missing
frames have separate states so we do not mistake absent data for zero objects.

We show the detector's recorded quality-gate decision near the image and the
saved model profile below it. These describe that particular run rather than
the application's current default model. Dense-crowd results remain separate
from detector-based person counts. An unsupported crowd decision has no numeric
count, and older sessions without a decision are identified as unrecorded.

For a single video source, we browse stored samples with previous/next controls
or the frame selector. Samples follow timestamp order, with source frame number
and record ID breaking ties. Samples without a recorded timestamp follow the
timed samples in frame-number order; their time remains unavailable. The displayed
source frame number is the stored zero-based index, not the sample's position.

Each selected sample has its own image, whole-frame counts, and detection records.
These counts do not represent unique objects across a video. A frame change resets
detection pagination and image loading; refreshing keeps the selected frame by ID
when it still exists. Partial sessions remain labelled incomplete, and refreshing
retrieves any newly stored results. We do not poll this historical result view.
The model profile and dense-crowd decision below the frames describe the session.

The experimental alert view and final verification are the remaining dashboard work.
Mixed-source sessions are identified as unsupported
rather than combined into a single timeline.

### Inspecting Stored Grids

When a frame includes a stored grid, we display its cell boundaries over the
saved image. The overlay follows the stored pixel bounds, including fractional
coordinates, and scales with the uncropped image. A visibility toggle leaves the
saved image and its detection boxes unchanged.

Cell selection works on the image, with keyboard-focusable cell buttons, or
through the row/column selector. We display rows and columns starting at one;
the stored indices still start at zero. The selected-cell table reads only that
cell's `summaries`. Whole-frame counts and detection records do not change when
we select a cell, and the browser does not repeat the backend's counting logic.
Changing video frames clears cell selection.

Missing images do not prevent selection through the cell selector. Missing or
inconsistent coordinate metadata disables the spatial overlay without hiding
stored counts. A session without grid records has an explicit no-grid state.
Empty cell summaries are reported as having no recorded class counts, rather
than filled with invented values. The backend normally stores only positive
cell counts, but the display also preserves an explicitly stored zero.

These are counts within image-space regions, not equally sized ground areas or
people per square metre. Dense-crowd estimates remain a separate result.

### Filtering Stored Classes

The **Table class** selector offers the classes present in a frame's detections,
whole-frame summaries, or cell summaries. We can inspect one class or return to
**All classes**. Matching uses the stored class name, not a renamed model label.

The filter applies to detection records and both count tables. The tables retain
their whole-frame or selected-cell scope and show the active class in their
captions. The stored detection total remains an all-class total. Missing matches
have a separate message from missing records, and existing zero values are kept.
We display stored summaries rather than rebuilding them from detection rows.

Changing or clearing the filter resets detection pagination, but keeps the
selected grid cell. Refreshing a frame keeps the selected class even if the
updated records have no matches. Opening another frame or session resets the
filter to all classes.

The saved detection JPEG remains unchanged and is labelled as an all-class
overlay. This is a table filter, not a visual-box filter or an inference setting.
Grid boundaries, model provenance, and dense-crowd decisions are unaffected.

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
