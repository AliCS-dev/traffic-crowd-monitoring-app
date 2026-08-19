# Application Architecture

## Why We Use This Structure

We want the application to stay understandable while it grows from a single
image prototype into a monitoring application for images and videos. We separate
parts that have different responsibilities, but we avoid adding layers that the
project does not yet need.

The current structure lets us combine image and video processing with detection
and database storage without placing everything in one large script.

The application now has two entry points. `app/main.py` remains the image CLI,
while `app/api/application.py` exposes reusable services through HTTP. Neither
entry point contains detection or persistence logic of its own.

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
    v
Bounded local background worker and completion transaction
  - one processed row per sampled frame
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
| `app/services/video_detection_service.py` | Processes sampled frames while preserving frame metadata |
| `app/services/video_analysis_service.py` | Coordinates video uploads, bounded background work, progress, grids, and failures |
| `app/services/video_upload_service.py` | Streams and validates supported uploaded video containers |
| `app/services/output_service.py` | Creates the annotated output image |
| `app/database/connection.py` | Reads `DATABASE_URL` and opens PostgreSQL connections |
| `app/database/migration_runner.py` | Discovers, verifies, and applies ordered SQL migrations |
| `app/database/detection_repository.py` | Stores complete image or sampled-video results in a transaction |
| `app/database/video_job_repository.py` | Persists video-job state, progress, completion, failure, and startup recovery |
| `app/database/monitoring_query_repository.py` | Lists sessions and reconstructs complete stored results with fixed bulk queries |
| `app/schemas/monitoring.py` | Defines database-independent history and result models for later API and frontend use |
| `scripts/` | Contains explicit database setup and diagnostic commands |

`app/main.py` brings these pieces together, while the service modules contain
the individual processing steps. This gives us a simple command-line application
and an HTTP application that can be used by the future frontend without
reimplementing the processing pipeline.

## How We Store a Result

When we use `--save-to-db`, we store the records for one image inside a single
database transaction. Video storage follows the same rule: one transaction
contains the session, its model-profile snapshot, source, every sampled frame,
and all related detections and summaries. An image grid joins the same
transaction when requested. Every cell is stored, while only non-zero per-class
counts create summary rows. The same transaction stores the dense-crowd
capability state. It currently records no active crowd method, no model, and no
count because the evaluated candidate was rejected. If one insert fails, the
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
as a required pair. Result schemas expose only the UUID. If validation,
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

## Decisions We Have Made So Far

### Starting with a command-line interface

We began with a command-line interface because it lets us test the complete
pipeline before deciding what we want from the final desktop or web interface.
When we add that interface, it will call the existing services instead of
reimplementing image detection or database storage.

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
object centres to image cells independently of YOLO. Image runs can now persist
those cells and summaries through the existing repository. Our next
planned extensions are:

1. evaluate grid behavior separately from detector accuracy;
2. connect grid processing to sampled video frames when the application needs it;
3. generate threshold-based alerts only after their input limitations are
   explicit;
4. add a user-facing interface and result views.

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
- **Crowd concentration** means a relative count of people in an image region.
- **Crowd density** means people per measured physical area. We do not currently
  calculate this because the images are not geographically calibrated.

## Limitations We Already Know About

- The reusable detector supports processing multiple frames with one model
  instance, but video processing is not yet connected to the command-line
  application.
- We do not yet store processing duration with a database result.
- Grid counts can be printed and stored for image runs, but they are not drawn on
  output images or connected to sampled video frames yet.
- Detector-based person summaries are not dense-crowd estimates. The dedicated
  crowd result is explicitly unsupported and has a null count because no tested
  candidate passed the evaluation decision rule.
- Repository tests cover transaction behavior with controlled test doubles, but
  live PostgreSQL coverage does not yet include every future API query path.
- `app/ui` is reserved for later work and does not contain an interface yet.
- The API supports synchronous image creation and detail reads, but not video
  jobs, session-history routes, or output-file serving yet.
