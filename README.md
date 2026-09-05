# Traffic and Crowd Monitoring Application

We are developing this application as part of a BSc thesis on traffic and crowd
monitoring from aerial images and videos. Our goal is to turn visual data into
structured information that can be inspected, stored, and later used for
monitoring and analysis.

At this stage, images can be analysed synchronously and videos can be submitted
as background jobs through the API. Both paths reuse the same detector,
preprocessing, grid-counting, and PostgreSQL boundaries. Video jobs preserve the
sampled frame numbers and timestamps while reporting persistent progress. Stored
results also provide controlled URLs and pixel-coordinate metadata for annotated
images and sampled video frames.

## Where the Project Stands

| Capability | Status |
| --- | --- |
| Image input validation | Implemented |
| Image preprocessing | Implemented |
| YOLO object detection | Experimental baseline |
| Class-wise object counting | Implemented |
| Annotated image output | Implemented |
| PostgreSQL connection and initial schema | Implemented |
| Detection and count-summary storage | Implemented |
| Video input and metadata | Implemented |
| Time-based video frame sampling | Implemented |
| Detection on sampled video frames | Implemented |
| Video result storage | Implemented |
| Aerial detection evaluation protocol | Implemented |
| Labelled aerial evaluation dataset | Implemented |
| Reproducible evaluation command | Implemented |
| Baseline model evaluation | Completed; quality gate failed |
| Fine-tuning pilot | Completed; person-only checkpoint rejected |
| Final held-out evaluation | Completed; quality gate failed |
| Validated runtime model profile | Implemented; experimental YOLO26m profile |
| Per-session model provenance | Implemented |
| Grid-based spatial counting | Implemented as an experimental component |
| Grid-cell database storage | Implemented for image and sampled-video runs |
| FastAPI backend foundation | Implemented with health and readiness endpoints |
| Stored-session query layer | Implemented with typed paginated result models |
| Image upload and analysis API | Implemented for validated JPG and PNG files |
| Asynchronous video analysis API | Implemented with persistent progress and failure states |
| Visual result assets and overlay metadata | Implemented for images and sampled video frames |
| Dense-crowd analysis | Explicitly unsupported; rejected candidate is not loaded |
| Threshold-based alerts | Implemented as experimental count notifications |
| Browser frontend foundation | Implemented with responsive routes and live service status |
| Browser media submission | Implemented for images and asynchronous videos |

The current detector gives us a measured starting point, but it is not reliable
enough for final conclusions about aerial traffic or crowds. We compared three
pretrained candidates and ran a source-group-clean fine-tuning pilot. The pilot
improved person detection but removed useful vehicle performance, so we rejected
its checkpoint. The dedicated P2PNet candidate also failed its predeclared
dense-crowd threshold. The application therefore returns an explicit unsupported
state and a null crowd count instead of loading that checkpoint or reporting a
misleading zero.

## What We Use

- Python 3.10 or 3.11
- OpenCV and NumPy
- Ultralytics YOLO
- PostgreSQL 16 and Psycopg 3
- FastAPI and Uvicorn
- React, TypeScript, Vite, and Material UI
- Docker Compose for the local database
- Pytest, Vitest, Ruff, Oxlint, and Prettier
- GitHub Actions and Dependabot

## Repository Layout

```text
app/
  api/                   HTTP application, dependencies, routes, and schemas
  database/              Database connections, repositories, and migrations
  schemas/               Typed monitoring history and result models
  services/              Image, preprocessing, detection, and output logic
  config.py              Project paths
  model_profile.py       Runtime-profile validation and checkpoint verification
  main.py                Command-line application entry point
configs/
  runtime/               Application model and inference profile
data/
  evaluation/             Evaluation metadata; raw media excluded from Git
  input/                  Local input images and videos
  output/                 Generated annotated output
docs/                     Architecture and development documentation
frontend/                 Independent React and TypeScript browser application
models/                   Local model weights, excluded from Git
scripts/                  Setup, validation, evaluation, and diagnostic commands
tests/                    Automated tests
```

The reasoning behind this structure is described in our
[architecture document](docs/architecture.md).

Our model results are collected in the
[evaluation results index](docs/evaluation/results_index.md). It links the
protocol, dataset evidence, model comparisons, fine-tuning record, and final
held-out report so that the metrics remain easy to find while we write the
thesis.

The next aerial detectors are fixed before benchmarking in the
[candidate selection record](docs/evaluation/aerial_model_candidates.md). Their
versioned sources, expected weight hashes, licences, and class mappings are also
stored in `configs/evaluation/aerial_model_candidates.json`.

We can download, verify, and smoke-test the predeclared candidate checkpoints on
the local GPU with:

```bash
.venv/bin/python scripts/preflight_model_candidates.py --download
```

The checkpoints remain under the ignored `models/candidates/` directory. The
command verifies their pinned size and SHA-256 digest before loading them, then
runs one validation image without calculating benchmark metrics.

The completed validation comparison and the decision that led to fine-tuning
are recorded in the
[aerial model decision](docs/evaluation/aerial_model_decision.md). The final
checkpoint was frozen before the held-out split was opened, and the resulting
quality-gate decision is recorded in the
[final report](docs/evaluation/final_quality_gate.md).

The completed pilot, its person-detection gain, its vehicle-class regression,
and the decision not to promote it are recorded in the
[fine-tuning pilot report](docs/evaluation/fine_tuning_pilot.md). Its compact
machine-readable provenance is stored in
`data/evaluation/training_experiments.json`; generated datasets, logs, plots,
and checkpoints remain outside Git.

## Running the Project Locally

We use a virtual environment so that the project dependencies stay separate from
the system Python installation:

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

Local database values are stored in `.env`. We create it from the safe example:

```bash
cp .env.example .env
```

The example credentials are only for local development, and `.env` remains
outside version control.

## Running the API

The FastAPI backend is a separate entry point from the existing image CLI. We
start it locally with:

```bash
.venv/bin/uvicorn app.api.application:app \
  --host 127.0.0.1 \
  --port 8000 \
  --reload
```

The first API routes are deliberately small:

- `GET /api/health` confirms that the HTTP process can respond;
- `GET /api/ready` checks PostgreSQL and verifies the configured checkpoint;
- `GET /api/capabilities` returns public upload formats and option limits;
- `GET /api/analyses` returns paginated monitoring-session history;
- `POST /api/analyses/images` validates, processes, and stores one image;
- `POST /api/analyses/videos` validates and queues one video;
- `GET /api/analyses/videos/{session_id}` returns video-job progress;
- `GET /api/analyses/{session_id}` returns one complete stored result;
- `GET /api/assets/{asset_id}` returns one controlled generated image;
- `GET /docs` opens the generated interactive OpenAPI documentation;
- `GET /openapi.json` returns the machine-readable API contract.

Readiness returns HTTP `503` when a dependency is unavailable. Detector
readiness means that the configured checkpoint exists and matches its recorded
identity. It does not change the failed model quality-gate result or claim that
the detector is accurate enough for operational monitoring.

The detector is loaded only when the first analysis request needs it. Starting
the server, checking health, and generating documentation therefore do not
allocate GPU model memory. PostgreSQL remains the only Docker service at this
stage.

Development browser origins are configured as a comma-separated list in
`.env`:

```text
API_CORS_ORIGINS=http://localhost:5173
API_MAX_IMAGE_UPLOAD_MB=10
API_MAX_IMAGE_PIXELS=40000000
API_MAX_GRID_DIMENSION=20
API_MAX_VIDEO_UPLOAD_MB=500
API_VIDEO_WORKERS=1
```

Wildcard CORS and non-positive upload limits are rejected. The image endpoint
accepts JPG, JPEG, and PNG only. It checks the extension, MIME type, encoded byte
size, actual image format, decoded dimensions, and OpenCV decoding before
inference. Uploaded paths are never trusted as storage paths.

With PostgreSQL running and migrations applied, we can submit a controlled image
analysis from the terminal:

```bash
curl -X POST http://127.0.0.1:8000/api/analyses/images \
  -F "image=@data/input/sample_image.jpg;type=image/jpeg" \
  -F "session_name=sample API image" \
  -F "grid_rows=3" \
  -F "grid_columns=4"
```

The response contains the database session ID and a result URL. The request uses
the tracked runtime model profile; it does not accept ad hoc confidence, image
size, class-mapping, or checkpoint overrides. It also includes a
`dense_crowd_analysis` object. Its current status is `unsupported`, its `count`
is null, and it links to the evaluation that rejected the tested P2PNet
checkpoint. Detector-based person summaries remain ordinary object detections;
they are not presented as a dedicated dense-crowd estimate. A completed result
can then be read with:

```bash
curl http://127.0.0.1:8000/api/analyses/<session-id>
```

Videos use the same stored-result URL but are queued first:

```bash
curl -X POST http://127.0.0.1:8000/api/analyses/videos \
  -F "video=@data/input/example.mp4;type=video/mp4" \
  -F "session_name=sample API video" \
  -F "sampling_interval_seconds=1" \
  -F "grid_rows=3" \
  -F "grid_columns=4"

curl http://127.0.0.1:8000/api/analyses/videos/<session-id>
```

The create request returns HTTP `202` after validation, upload storage, and the
queued database record are complete. The progress route reports `queued`,
`processing`, `completed`, or `failed`. Once completed, the normal result route
returns ordered frames, detections, summaries, optional grids, and a visual asset
reference for each sampled frame. It also returns any experimental threshold
notifications generated from those stored counts.

Successful uploads and generated images use UUID filenames under ignored data
directories. Image outputs are stored in `data/output/analyses/`, while sampled
video-frame outputs are stored in `data/output/video-frames/`. The result JSON
contains a URL such as `/api/assets/<asset-id>` and never exposes the private
server path. We can download that generated JPEG with:

```bash
curl http://127.0.0.1:8000/api/assets/<asset-id> --output result.jpg
```

All visual coordinates use the processed image returned by that URL. The origin
is the top-left corner, x increases to the right, and y increases downwards. The
generated JPEG already contains the detection boxes. Detection records and grid
cells remain in the JSON so the result interface can inspect detections and draw
the grid without changing the saved image.

## Running the Frontend

The browser application is kept in `frontend/` so interface code remains
separate from the Python processing and persistence layers. We use Node.js 24
LTS and install the committed dependency set with:

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

The workspace opens at <http://localhost:5173> and reads the API location from
`VITE_API_BASE_URL`. Its current routes provide image and video submission,
video-job progress, the session-history table, the result view, and live health
and readiness states. The form reads supported formats and limits from the API,
so browser validation stays aligned with the configured backend. A completed
submission opens its result route automatically. Detailed result visualisation
is the next frontend stage.

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

## Trying the Image Pipeline

The default command processes the sample image included in the repository:

```bash
.venv/bin/python -m app.main
```

We can also choose a different image and output location:

```bash
.venv/bin/python -m app.main \
  --image data/input/example.jpg \
  --output data/output/example_detected.jpg
```

The complete list of command-line options is available with:

```bash
.venv/bin/python -m app.main --help
```

## Counting Objects In Grid Cells

We can divide the processed image into a grid and count detections according to
the centre of each bounding box. For example, this command uses three rows and
four columns:

```bash
.venv/bin/python -m app.main \
  --image data/input/example.jpg \
  --grid 3 4
```

The terminal summary reports only occupied cells. The grid service itself
returns every cell, including empty cells, in stable row-major order so that a
later interface can render a complete grid without rebuilding it.

We can store the same grid together with the image result by combining the grid
and database options:

```bash
.venv/bin/python -m app.main \
  --image data/input/example.jpg \
  --grid 3 4 \
  --save-to-db \
  --session-name "three-by-four grid example"
```

Every cell is stored so its layout can be reconstructed later. Per-cell summary
rows are created only for classes actually counted in a cell; empty cells do not
receive artificial zero-count rows. Complete-frame summaries remain separate
and have no grid-cell reference.

Grid counts are relative image-region counts. They depend on the detector's
predictions and do not represent people or vehicles per square metre. The
current command does not draw the grid on the output image.

## Experimental Threshold Notifications

Image and video analyses evaluate the tracked rules in
`configs/runtime/alert_rules.json`. A rule names one object class, selects either
the complete frame or each grid cell, declares whether equality triggers it, and
assigns an information, warning, or critical display level. The current file has
two illustrative rules:

- at least 20 `car_or_van` detections in one frame produces a warning;
- at least 8 `person` detections in one grid cell produces an information notice.

These values are application configuration, not research findings or public
safety limits. A generated alert means only that a model-produced count met its
configured software threshold. It does not establish traffic congestion,
physical crowd density, danger, or an emergency. The complete rule format,
boundary behavior, and limitations are described in the
[alert-rule documentation](docs/alert_rules.md).

## Reading And Sampling Video Input

The video service validates common video formats, reads basic metadata, and gives
us sequential access to frames. The sampling service selects frames at a
user-defined interval while preserving each selected frame's number and
timestamp. The video detection service reuses one model instance across those
frames:

```python
from app.database.detection_repository import save_video_detection_results
from app.model_profile import load_runtime_model_profile
from app.services.detection_service import ObjectDetector
from app.services.frame_sampling_service import sample_video_frames
from app.services.video_detection_service import process_sampled_video_frames
from app.services.video_service import VideoReader

profile = load_runtime_model_profile()
detector = ObjectDetector.from_runtime_profile(profile)

with VideoReader("data/input/example.mp4") as video:
    sampled_frames = sample_video_frames(
        video,
        sampling_interval_seconds=1.0,
    )
    frame_results = list(
        process_sampled_video_frames(sampled_frames, detector, profile)
    )

stored_result = save_video_detection_results(
    "data/input/example.mp4",
    frame_results,
    session_name="sample video run",
    model_profile=profile,
)
print(stored_result)
```

Supported formats are MP4, AVI, MOV, and MKV. The context manager closes the
OpenCV video resource when we finish reading. Video persistence stores one
session and input source for the video, followed by one processed-frame row for
each sampled frame. API video jobs also save one annotated JPEG for every sampled
frame. The command-line application still handles image runs only. The video API
composes these services in a bounded background worker.

## Working with PostgreSQL

For now, PostgreSQL is the only part that we run in Docker. Python, OpenCV, and
YOLO continue to run in the local virtual environment.

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

## Running the Detector Evaluation

The evaluation dataset must pass its quality checks before we create a formal
model result:

```bash
.venv/bin/python scripts/validate_evaluation_dataset.py
```

We then run the configured validation protocol with one command:

```bash
.venv/bin/python scripts/run_detector_evaluation.py \
  --config configs/evaluation/yolo26n_validation.json
```

The command reads the dataset split, model settings, thresholds, timing policy,
and random seed from the configuration. Each run is stored under
`data/evaluation/derived/runs/<run-id>/`. The directory contains raw
predictions, metrics, timing measurements, environment provenance, checksums,
and a concise `summary.md` table.

The summary is derived entirely from the saved JSON files. We can rebuild it
without loading the model or rerunning inference:

```bash
.venv/bin/python scripts/render_evaluation_report.py \
  data/evaluation/derived/runs/<run-id>
```

For validation tuning, confidence thresholds are compared from the saved
confidence-floor predictions. This keeps model inference fixed while changing
only the operating threshold:

```bash
.venv/bin/python scripts/run_confidence_sweep.py \
  --source-run data/evaluation/derived/runs/<run-id>
```

The tracked sweep configuration contains only the five values declared in the
evaluation protocol. The command verifies every source-run checksum and refuses
held-out data before calculating the comparison.

The three predeclared inference image sizes are evaluated with:

```bash
.venv/bin/python scripts/run_image_size_benchmark.py
```

This runs the complete validation and timing protocol at `640`, `960`, and
`1280`. Each size receives its own normal evaluation run, and the command then
creates one checksum-backed comparison report. The configurations are checked
to ensure that only the image size and descriptive run name changed.

Representative detection and count errors are generated from a saved validation
run without repeating model inference:

```bash
.venv/bin/python scripts/run_error_analysis.py \
  --source-run data/evaluation/derived/runs/<run-id>
```

The analysis uses `pycocotools` operating matches for false positives and false
negatives, links overlapping wrong-class predictions as class confusions, and
also retains confusions with raw labels excluded by the taxonomy or an asset's
annotation scope. It keeps count-only crowd failures separate from box-level
errors and saves the complete machine-readable error list, deterministic
example images, contact sheets, a summary, and checksums under
`data/evaluation/derived/error_analysis/`.

The earlier YOLO26n selected baseline can still be reproduced as one complete
validation run with:

```bash
.venv/bin/python scripts/run_detector_evaluation.py \
  --config configs/evaluation/yolo26n_selected_validation.json
```

It remains historical comparison evidence rather than the application runtime
configuration. Image and video processing now use the separate validated
YOLO26m runtime profile described above. Neither evaluated model passed the
quality gate, and neither should be presented as deployment-ready.

Formal results should be created from a committed working tree on the same
documented hardware and power configuration. Generated run directories remain
outside Git because they contain large prediction and timing records.

We can validate the predeclared aerial-model shortlist without downloading any
weights:

```bash
.venv/bin/python scripts/validate_model_candidates.py
```

## Checks We Run

Before opening a pull request, we run the same basic checks that are used in CI:

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

## Project Documents

- [Architecture](docs/architecture.md)
- [Database schema](docs/database/database_schema.md)
- [Experimental alert rules](docs/alert_rules.md)
- [Aerial detection evaluation protocol](docs/evaluation/evaluation_protocol.md)
- [Development log](docs/development_log.md)
- [Development workflow](docs/development_workflow.md)

## Scope and Current Limitations

We are building this project for monitoring, analysis, and decision support. We
are not trying to control traffic directly or make autonomous interventions.

There are several limitations that we are keeping visible while the application
is still under development:

- the final held-out detector evaluation failed the overall quality gate;
- the detector can miss or misclassify small aerial objects;
- no evaluated model currently supports reliable dense-crowd counting, and the
  API reports this with an unsupported state and null count;
- video processing is available through the API but not through the
  command-line entry point;
- threshold notifications inherit the detector's failed quality-gate status and
  must not be interpreted as verified real-world conditions;
- image analysis is synchronous, while video analysis uses a local background
  worker and persistent progress;
- background jobs are local to one API process; interrupted queued or processing
  jobs are marked failed at the next startup and must be submitted again;
- generated result assets are local files served by the API and are not yet
  backed by remote object storage or an authentication layer;
- the browser interface can submit media and track video progress, but detailed
  result visualisation and connection of the session-history table are not yet
  implemented;
- we do not calculate physical crowd density.

Until we add geographic calibration, we use the terms **count per spatial
region** or **crowd concentration**. We reserve **crowd density** for a measured
number of people per physical area, such as people per square metre.
