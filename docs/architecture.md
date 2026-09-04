# Application Architecture

## Why We Use This Structure

We want the application to stay understandable while it grows from a single
image prototype into a monitoring application for images and videos. We separate
parts that have different responsibilities, but we avoid adding layers that the
project does not yet need.

The current structure lets us combine image and video processing with detection
and database storage without placing everything in one large script.

The Python application has two entry points. `app/main.py` remains the image
CLI, while `app/api/application.py` exposes reusable services through HTTP.
Neither entry point contains detection or persistence logic of its own. The
separate `frontend/` workspace is the browser client for that HTTP boundary; it
does not import Python code or access PostgreSQL directly.

## Current Processing Flow

```text
Command-line input
       |
       v
Load runtime model profile
       |
       v
Load and validate image
       |
       v
Resize image for detection
       |
       v
Verify checkpoint identity and run YOLO object detection
       |
       +---------------------> Save annotated image
       |
       v
Extract detections and class counts
       |
       +---------------------> Optional grid-cell counts
       |
       +---------------------> Experimental count-threshold alerts
       |
       v
Optional PostgreSQL transaction
  - monitoring session
  - model and inference profile snapshot
  - input source
  - processed frame
  - detection results
  - complete-frame object count summaries
  - optional grid cells and per-cell summaries
```

Video API input follows an asynchronous flow:

```text
Validated MP4, AVI, MOV, or MKV upload
    |
    v
Commit queued session, source, profile, and job
    |
    +---------------------> Return HTTP 202 and job URL
    |
    v
Validate and open with OpenCV
    |
    +---------------------> Read metadata
    |
    v
Read frames in sequence
    |
    v
Select frames at a time interval
    |
    +---------------------> Frame number and timestamp
    |
    v
Preprocess and detect sampled frames
    |
    +---------------------> Detections and class counts
    |
    +---------------------> Optional grids and experimental alerts
    |
    v
Render one annotated JPEG per sampled frame
    |
    v
Bounded local background worker and completion transaction
  - one processed row and output-asset reference per sampled frame
  - per-frame detections, class counts, and optional grids
  - persistent progress or public failure state
```

The HTTP foundation currently has a smaller service-status flow:

```text
HTTP request
    |
    v
FastAPI routing and typed response schema
    |
    +---------------------> /api/health: process responds
    |
    v
Injected application services
    |
    +---------------------> PostgreSQL connection probe
    |
    +---------------------> Runtime checkpoint identity probe
    |
    v
/api/ready: 200 ready or 503 not ready
```

The detector itself is created lazily through the same dependency container.
Health checks, OpenAPI generation, and API unit tests do not load YOLO.

The frontend follows this browser flow:

```text
React route and shared application shell
    |
    +---------------------> /api/capabilities: formats and limits
    |
    v
Validated image or video form
    |
    +---------------------> Image: synchronous multipart request
    |
    +---------------------> Video: create persistent background job
    |
    v
Typed API client using VITE_API_BASE_URL
    |
    +---------------------> Poll persistent video status and progress
    |
    +---------------------> Preserve form on validation or API failure
    |
    v
Completed session result route
```

React Query owns remote service state, React Router owns browser navigation,
and Material UI provides one accessible component baseline. The route pages do
not call `fetch` directly. The same client also reads health and readiness. The
browser derives its upload rules from a public capability endpoint, while the
backend remains authoritative and repeats all validation before processing.

Image requests now add one synchronous application flow:

```text
Multipart JPG or PNG
    |
    v
Bounded byte, MIME, format, dimension, and decode validation
    |
    v
Generated input and output asset names
    |
    v
Fixed runtime profile -> preprocessing -> shared detector
    |
    +---------------------> Optional validated grid counts
    |
    +---------------------> Experimental count-threshold alerts
    |
    v
Annotated output + one PostgreSQL transaction
    |
    +---------------------> Persisted dense-crowd capability: unsupported
    |
    v
Session ID and typed result URL
```

The endpoint runs blocking inference in FastAPI's worker thread and serialises use
of the shared detector. This is appropriate for the current single-user image
workflow. Video processing uses a separate background-job design rather than
holding an HTTP request open.

## Main Components

| Component | Role in the application |
| --- | --- |
| `app/main.py` | Coordinates one image-processing run |
| `app/api/application.py` | Creates the FastAPI application and manages its lifecycle |
| `app/api/dependencies.py` | Provides readiness probes and lazy detector access |
| `app/api/errors.py` | Converts API failures into one public JSON error format |
| `app/api/routes/health.py` | Exposes process health and dependency readiness |
| `app/api/routes/capabilities.py` | Exposes public upload formats and analysis-option bounds |
| `app/api/routes/assets.py` | Serves generated images through controlled asset identifiers |
| `app/api/routes/image_analyses.py` | Creates image analyses and returns complete stored results |
| `app/api/routes/video_analyses.py` | Queues video analyses and returns persistent job progress |
| `app/config.py` | Keeps project paths in one place |
| `app/crowd_analysis.py` | Converts the recorded crowd evaluation rejection into a validated runtime decision |
| `app/model_profile.py` | Validates the runtime profile and verifies checkpoint identity |
| `app/services/image_service.py` | Checks the input path and loads supported images |
| `app/services/image_upload_service.py` | Validates uploaded image metadata, bytes, format, and decoded dimensions |
| `app/services/image_analysis_service.py` | Coordinates upload storage, inference, grids, output, persistence, and cleanup |
| `app/services/video_service.py` | Opens videos, reads metadata, and provides frames |
| `app/services/frame_sampling_service.py` | Selects video frames at controlled time intervals |
| `app/services/preprocessing_service.py` | Resizes images before inference |
| `app/services/detection_service.py` | Loads YOLO, runs inference, and converts output into counts and records |
| `app/services/grid_counting_service.py` | Assigns detection centres to configurable image cells and counts classes per cell |
| `app/services/alert_service.py` | Validates and evaluates model-independent count-threshold rules |
| `app/services/video_detection_service.py` | Processes sampled frames while preserving frame metadata |
| `app/services/video_analysis_service.py` | Coordinates video uploads, bounded background work, progress, grids, and failures |
| `app/services/video_upload_service.py` | Streams and validates supported uploaded video containers |
| `app/services/output_service.py` | Creates the annotated output image |
| `app/services/output_asset_service.py` | Resolves stored assets inside configured output directories |
| `app/database/connection.py` | Reads `DATABASE_URL` and opens PostgreSQL connections |
| `app/database/migration_runner.py` | Discovers, verifies, and applies ordered SQL migrations |
| `app/database/detection_repository.py` | Stores complete image or sampled-video results in a transaction |
| `app/database/video_job_repository.py` | Persists video-job state, progress, completion, failure, and startup recovery |
| `app/database/monitoring_query_repository.py` | Lists sessions and reconstructs complete stored results with fixed bulk queries |
| `app/database/output_asset_repository.py` | Finds a private generated-file path by public asset UUID |
| `app/schemas/monitoring.py` | Defines database-independent history and result models for later API and frontend use |
| `frontend/src/api/` | Validates the API base URL and contains typed HTTP requests and response contracts |
| `frontend/src/components/` | Provides the responsive shell and shared status, dialog, and state patterns |
| `frontend/src/features/analysis/` | Owns media validation, submission, progress polling, and recovery state |
| `frontend/src/pages/` | Defines the workspace, session-history, result, and not-found routes |
| `frontend/src/theme.ts` | Defines shared colours, typography, spacing, and component defaults |
| `scripts/` | Contains explicit database setup and diagnostic commands |

`app/main.py` brings these pieces together, while the service modules contain
the individual processing steps. This gives us a simple command-line application
and an HTTP application that the frontend can use without reimplementing the
processing pipeline.

## How We Store a Result

When we use `--save-to-db`, we store the records for one image inside a single
database transaction. Video storage follows the same rule: one transaction
contains the session, its model-profile snapshot, source, every sampled frame,
and all related detections and summaries. An image grid joins the same
transaction when requested. Every cell is stored, while only non-zero per-class
counts create summary rows. The same transaction stores the dense-crowd
capability state. It currently records no active crowd method, no model, and no
count because the evaluated candidate was rejected. Experimental alerts are
evaluated before persistence and inserted after their frame and optional grid
cell exist, preserving their source lineage. If one insert fails, the
transaction is rolled back,
so we do not keep an incomplete processing run.

The tracked runtime profile is aligned with the frozen YOLO26m VisDrone
evaluation configuration. It includes the checkpoint hash, class mapping, and
inference settings. The application verifies the local weights before inference
and maps the model's source labels into the six project classes. The profile's
stored quality-gate status is `failed`; alignment improves traceability but does
not imply acceptable model accuracy.

We use parameterised SQL throughout the repository. Values are passed separately
from the SQL statements, which keeps the queries clear and avoids building SQL
from user-provided strings.

The monitoring query repository is the read boundary for stored results. It
returns typed nested models rather than cursor tuples or column dictionaries.
Session pages use the stable order `started_at DESC, id DESC`. A detail read uses
bulk child queries across all frame IDs, so a video with many sampled frames does
not cause one database query per frame. Missing sessions return `None` for the
future API layer to translate into a consistent not-found response.

For uploaded images, one generated UUID names both the private files and the
public output-asset reference. PostgreSQL stores the UUID and private output path
as a required pair. Result schemas expose the UUID, a controlled API URL, media
dimensions, and the coordinate-space definition. If validation,
inference, output writing, or database persistence fails, the orchestration
service removes any partial input and output files; the repository transaction
rolls back incomplete database records.

Uploaded videos also receive generated UUID filenames. A bounded
`ThreadPoolExecutor` handles local jobs, with one worker by default. The shared
detector serialises inference so concurrent image and video requests cannot use
the same model instance simultaneously. This is intentionally a single-process
design for the thesis prototype, not a distributed queue. On startup, abandoned
`queued` or `processing` records are marked `failed` because in-memory work
cannot be resumed honestly after a process interruption.

### Keeping media and overlays aligned

The result API uses one coordinate system for images and sampled video frames:
pixels in the preprocessed image, with the origin at the top-left, x increasing
to the right, and y increasing downwards. The width and height in
`coordinate_space` match both the detection and grid coordinates and the JPEG
served through `visual_asset.url`. Output writing rejects a rendered image when
its dimensions do not match this metadata.

Detection boxes are already rendered in the generated JPEG, which is stated in
`visual_asset.rendered_overlays`. The API still returns each detection box for
inspection and interaction. Grid cells are returned as metadata and will be
drawn by the result interface, so they can be shown or hidden without generating
a second image.

The asset route accepts only a stored UUID. It looks up the private path in
PostgreSQL, resolves symbolic links and relative path components, and serves only
supported image files inside the configured image or video output directories.
Unknown IDs, missing files, unsupported types, and paths outside those roots are
not exposed.

## Decisions We Have Made So Far

### Keeping the browser application separate

The React and TypeScript application lives in `frontend/`, with its own lockfile,
tests, and production build. It communicates with FastAPI through a validated
environment-based URL. This keeps presentation concerns out of the Python
packages and gives us a clear container boundary for later deployment. We chose
Material UI for consistent accessible controls, React Router for route state,
and React Query for server state rather than creating local replacements for
those established concerns.

### Starting with a command-line interface

We began with a command-line interface because it let us test the complete
pipeline before adding the browser application. The frontend now calls the
existing HTTP boundary instead of reimplementing image detection or database
storage.

### Running only PostgreSQL in Docker

At this stage, we run PostgreSQL in Docker and keep Python, OpenCV, and YOLO in a
local virtual environment. This makes it easier for us to experiment with models
and hardware while keeping the database setup repeatable.

### Keeping health separate from readiness

Process health answers only whether the HTTP server is running. Readiness checks
whether PostgreSQL is reachable and whether the runtime checkpoint matches its
recorded identity. A missing dependency therefore returns `503` from readiness
without making the health route unavailable. Checkpoint readiness is an
operational state, not evidence of model accuracy.

### Loading the detector lazily

The API dependency container loads the runtime profile at startup but constructs
YOLO only when an analysis route requests it. This keeps startup and API tests
lightweight while still giving future routes one shared detector instance. The
container clears its reference during application shutdown.

### Keeping object detection and dense-crowd analysis separate

The runtime YOLO profile produces object detections and class summaries. Its
`person` values are counts of accepted bounding-box predictions, not a dedicated
crowd estimate. Dense-crowd analysis has its own typed result and persisted
record so the two meanings cannot be merged accidentally.

`app/crowd_analysis.py` reads the tracked evaluation outcome at startup. Because
the outcome is `reject`, it creates only the rejection path: `unsupported`, a
null count, no active method or model, and the evaluation reference. It raises an
error if the evidence no longer records that decision, forcing us to implement
and review a new path before any future accepted model can enter the application.
We do not infer whether an upload is a dense crowd and we do not load P2PNet.

### Treating one image as one session

For the current image pipeline, one stored image creates one monitoring session,
one input source, and one processed frame. A stored video also creates one
session and source, but it has one processed-frame row for each sampled frame.
Detection and summary rows therefore remain linked to the correct frame number
and timestamp.

## Where We Plan to Extend It

The evaluation protocol, labelled data, model comparison, fine-tuning pilot,
and held-out quality gate are complete. The grid service now assigns detected
object centres to image cells independently of YOLO. Image and sampled-video runs
can persist those cells and summaries through the existing repositories. The
model-independent alert service now evaluates tracked frame and grid thresholds
over those counts. Our next planned extension is a user-facing result interface
built on the existing query and visual-asset APIs.

We want each step to remain independently testable. The video reader now supplies
frames without knowing how they will be sampled or detected. The sampling service
selects frames without knowing how detection works. The video detection service
then reuses one detector instance and converts each sampled frame into records
that later stages can store or aggregate.

The grid service follows the same rule. It accepts ordinary detection records
and image dimensions, so controlled tests can verify spatial assignment without
loading a model. It uses the bounding-box centre as the assignment point. A
centre exactly on an internal boundary belongs to the cell on the right or
below, while the outer image edges remain part of the final row and column.

## How We Use Important Terms

- **Detection** means one model prediction with a class, confidence score, and
  bounding box.
- **Object count** means the number of detections for one class in an image or
  frame.
- **Grid count** means the number of detections assigned to one image region.
- **Experimental alert** means a stored count crossed a configured software
  threshold; it is not confirmation of a real-world condition.
- **Crowd concentration** means a relative count of people in an image region.
- **Crowd density** means people per measured physical area. We do not currently
  calculate this because the images are not geographically calibrated.

## Limitations We Already Know About

- The reusable detector supports processing multiple frames with one model
  instance, but video processing is not yet connected to the command-line
  application.
- We do not yet store processing duration with a database result.
- Grid counts are stored for image and sampled-video runs. They are returned as
  frontend metadata rather than drawn into the generated JPEG.
- Detector-based person summaries are not dense-crowd estimates. The dedicated
  crowd result is explicitly unsupported and has a null count because no tested
  candidate passed the evaluation decision rule.
- Repository tests cover transaction behavior with controlled test doubles, but
  live PostgreSQL coverage does not yet include every future API query path.
- The API does not yet expose the paginated session-history query, so the
  frontend session-history route currently presents an explicit empty state.
- The browser can stop waiting for a pending request, but the API does not yet
  provide server-side cancellation for accepted image or video work.
- Generated assets are stored on the local filesystem and the API does not yet
  include user authentication.
