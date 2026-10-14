# Local Development

[Documentation index](README.md)

We use separate Python and frontend processes when changing the application.
For the complete browser application in containers, see the
[Docker Compose guide](compose_stack.md). Commands below start from the repository
root unless a step changes directory.

## Running the Project Locally

We use Python 3.10 or 3.11 in a virtual environment so that project dependencies
stay separate from the system Python installation:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

The runnable application uses the experimental profile in
`configs/runtime/yolo26m_visdrone.json`. It points to the original
VisDrone-trained YOLO26m checkpoint selected before held-out testing and records
its class mapping, confidence, image size, preprocessing scale, device,
`max_det`, and numeric precision. We can download and verify the pinned candidate
weights with:

```bash
.venv/bin/python scripts/preflight_model_candidates.py --download
```

The runtime profile expects the selected checkpoint at:

```text
models/candidates/yolo26m-visdrone/best.pt
```

Before loading YOLO, the application verifies the checkpoint size and SHA-256.
It stops with a clear error if the file is missing or has changed. Model weights
remain outside Git because they are large binary artifacts. Selecting this
profile aligns runtime provenance with the evaluation record; it does not change
the failed quality-gate result or make the detector deployment-ready.

Local database values are stored in `.env`. If it does not exist, we create it
from the example, then choose a local password. `DATABASE_URL` must use the same
database name, user, password and host port as the PostgreSQL settings:

```bash
cp -n .env.example .env
```

The example credentials are only for local development, and `.env` remains
outside version control.

## Working with PostgreSQL

The default development setup runs PostgreSQL in Docker and Python in the local
virtual environment. The separate backend container uses the same database
contract and ordered migrations.

We start the database and check its status with:

```bash
docker compose up -d postgres
docker compose ps
```

Once PostgreSQL is ready, these scripts check the connection and apply every
pending database migration:

```bash
.venv/bin/python scripts/check_db_connection.py
.venv/bin/python scripts/migrate_database.py
```

Migration files use names such as `001_create_initial_tables.sql` and run in
numerical order. PostgreSQL records each applied version, name, checksum, and
timestamp in `schema_migrations`. Repeating the command is safe: verified
migrations are skipped. We keep `scripts/create_database_tables.py` as a
compatibility wrapper for earlier project instructions, but new documentation
uses the migration command.

To keep the complete-frame results from an image run, we add the database option:

```bash
.venv/bin/python -m app.main \
  --save-to-db \
  --session-name "sample image run"
```

When we finish working locally, we can stop PostgreSQL without deleting its
persistent data:

```bash
docker compose down
```

## Running the API

Once the database is ready and migrations have completed, start the API from
the repository root in its own terminal:

```bash
.venv/bin/uvicorn app.api.application:app --host 127.0.0.1 --port 8000 --reload
```

The interactive API documentation is at <http://localhost:8000/docs>.
The [API guide](api.md) describes its routes and request examples.

## Running the Frontend

The browser application is kept in `frontend/` so interface code remains
separate from the Python processing and persistence layers. We use Node.js 26
to match `.nvmrc`, CI, and the container, and install the committed dependency set with:

```bash
cd frontend
npm ci
cp -n .env.example .env
npm run dev
```

The workspace opens at <http://localhost:5173> and reads the API location from
`VITE_API_BASE_URL`. Its current routes provide image and video submission,
video-job progress, paginated session history, the result view, and live health
and readiness states. The form reads supported formats and limits from the API,
so browser validation stays aligned with the configured backend. A completed
submission opens its result route automatically, and each history row links to
the same route. Image results show the saved detection image, whole-image class
counts, confidence scores, and the model profile recorded for that session.
The browser preserves the image proportions and uses the API's public asset
reference. Counts remain readable when an older result has no accessible image.
Video results have a sampled-frame selector and previous/next controls. Each
sample retains its source frame number, timestamp, image, counts, and detections;
we do not add these counts together as unique objects across a video.

Stored grids appear over the result image without changing the saved JPEG. We
can select a cell on the image or from the cell selector, and hide the overlay
when inspecting detection boxes. Selected-cell counts remain separate from the
whole-frame summaries and detection records. The cells use image pixels, not
calibrated ground areas; these counts do not measure physical crowd density.

The **Table class** filter narrows detection records and both count tables to
one stored class. The saved JPEG still shows all recorded detection boxes and
is labelled accordingly. Filtering changes neither stored counts nor model
settings; a missing matching record is not displayed as an invented zero.

Experimental alerts show the stored measured value, threshold, comparison, class,
scope, and rule severity for the current frame. Grid-cell events link back to
their cell counts. Alerts stay visible independently of table filters, and the
view does not change thresholds or mark events resolved. These records do not
confirm congestion, overcrowding, or emergencies. Details are in
[the alert-rule guide](alert_rules.md).

Processing completion and model quality are shown separately. The recorded
detector decision appears beside the image results, while unsupported
dense-crowd counting is shown without a count. Missing historical model or crowd
records are described as unavailable. The [dashboard verification record](dashboard_verification.md)
collects the automated checks, live workflow results, and remaining limitations.

Stopping an image upload in the browser aborts the local request. It is not a
server-side cancellation guarantee: if the API already accepted the request,
work may continue and appear in session history. Persistent video jobs can be
followed after the create request returns, but the API does not yet provide a
job-cancellation endpoint.

Frontend linting, formatting, type checking, unit tests, and the production
build can be run together as separate explicit checks:

```bash
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
```

The repeatable browser suite uses controlled API responses and does not require
PostgreSQL or a detector. From `frontend/`, we run:

```bash
npx playwright install --with-deps chromium
npm run test:browser
```

## Checks We Run

From the repository root, we run the same basic Python checks used in CI:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m compileall app evaluation scripts
```

GitHub Actions starts PostgreSQL, checks the application connection, exercises
fresh, repeated, legacy, and failed migration paths, and verifies grid, model
provenance, crowd-capability status, query, and image API persistence. The tests
query real PostgreSQL relationships and remove their temporary records and
schemas afterwards.
