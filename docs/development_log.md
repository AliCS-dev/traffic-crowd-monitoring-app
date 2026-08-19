# Development Log

This log follows the main stages of our BSc thesis application. We update it when
work is implemented and tested, so it reflects what we have actually built rather
than everything we hope to add later.

## May 2026: Building the Foundation

### Issues #1-#5: Environment and Repository Setup

We began by setting up the WSL development environment and the first Python
project structure. We added ignore rules for virtual environments, model files,
local data, and generated output, then prepared the initial README and roadmap.
This was also when we began using GitHub issues, separate branches, and pull
requests to keep the work organised.

### Issue #6: Image Input Handling

Our first application feature was image input. We added path handling with
`pathlib`, limited the accepted formats to JPG, JPEG, and PNG, and added clear
errors for missing or unreadable files. We also wrote the first automated tests
for invalid image input.

### Issue #7: Initial Object Detection

We connected an Ultralytics YOLO model to the image pipeline and added options
for confidence threshold and inference image size. During this work, we saw that
small objects in aerial images are difficult for a general pretrained model and
that the chosen inference size changes the output.

This model is still our experimental baseline. We have not yet shown that it is
accurate enough for aerial traffic monitoring, and the current sample image
contains clear misclassifications that we still need to investigate.

### Issues #8, #9, and #13: Output, Counting, and Structure

We added annotated output images, class-wise object counts, and a summary in the
terminal. As the pipeline grew, we moved image loading, preprocessing, detection,
and output into separate service modules. We also added command-line options for
the input path, output path, confidence, image size, and preprocessing scale.

We reserved `app/ui` for the later user interface, but we deliberately kept the
first usable version as a command-line application while the core pipeline was
still changing.

### Issue #10: Initial Database Design

We designed a relational structure around monitoring sessions, input sources,
processed frames, detections, count summaries, grid cells, and alerts. We chose
PostgreSQL because these records have clear relationships and will later support
queries across frames and monitoring sessions.

### Repository Automation

During the same period, we added GitHub issue and pull-request templates, GitHub
Actions checks, Dependabot, Ruff, and Pytest configuration. This gave us automatic
checks for tests, linting, formatting, syntax, and database connectivity.

## June 2026: Connecting PostgreSQL

### Issue #18: Database Connection

We added a PostgreSQL 16 service with Docker Compose, persistent local storage,
and a `pg_isready` health check. The Python side uses Psycopg and reads
`DATABASE_URL` from `.env`. We also added a small script that checks the
connection with `SELECT 1`.

### Issue #19: Initial Database Tables

We implemented the first SQL migration with seven related tables. The schema
includes foreign keys, basic checks, uniqueness rules, and indexes. A separate
script applies this initial schema to the local database.

### Issue #20: Detection Storage

We connected the image pipeline to the database. The repository now stores the
session, source image, processed frame, and individual detections in one
transaction. We added `--save-to-db` and `--session-name` to the command-line
application, along with unit tests for converting model output into database
records.

## July 2026: Storing Count Summaries

### Issue #21: Object Count Summaries

We extended the same transaction to store class-wise count summaries beside the
individual detections. The command-line result now reports how many detections
and summaries were stored, and we added unit tests for the summary conversion.

We merged this implementation into `main` on 13 July 2026 and closed the related
issue after confirming the merged result.

## July 2026: Adding Video Input

### Issue #22: Video Input Handling

We added a video reader around OpenCV's `VideoCapture`. It validates MP4, AVI,
MOV, and MKV files, then exposes the video dimensions, frame rate, frame count,
and duration. Frames can be read in sequence, and the reader releases the OpenCV
resource when processing finishes or an error occurs.

We added five tests covering missing files, unsupported formats, unreadable
videos, metadata extraction, frame order, and resource cleanup. We kept frame
sampling, video detection, and database storage outside this issue so they can be
developed as separate steps.

## July 2026: Sampling Video Frames

### Issue #23: Frame Sampling

We added a separate frame sampling service that selects video frames at
user-defined time intervals. Each sampled frame carries its zero-based frame
number, timestamp in seconds, and image data. Keeping this policy outside the
video reader means that file handling and sampling can be tested independently.

The sampler validates its interval and the video's frame rate, always includes
the first available frame, and reads until the end of the video. We added eleven
focused tests covering whole-second and fractional intervals, short intervals,
invalid values, missing frame-rate information, and empty input.

Video detection and database storage remain outside this issue. They will use
the sampled frames in a later processing step.

### Issue #36: Detection on Sampled Video Frames

We introduced a reusable detector that owns one YOLO model instance. The existing
single-image helper remains compatible, while video processing can now reuse the
same loaded model for every sampled frame instead of loading the weights
repeatedly.

We also added a video detection service that consumes sampled frames and composes
preprocessing, inference, detection-record extraction, and class-wise counting.
Each result preserves its original frame number and timestamp together with the
processed dimensions, detection records, and object counts.

Five new tests verify model reuse, frame metadata, preprocessing dimensions,
record and count extraction, empty input, valid frames with no detections, and
missing model results. The tests mock model inference, so the automated suite
does not depend on model weights or GPU availability.

Database storage, annotated video export, grid counting, and alerts remain
separate tasks.

### Issue #38: Video Detection Storage

We extended the existing PostgreSQL repository to store a sampled-video run as
one transaction. A run creates one monitoring session and one video input source,
then stores each sampled frame with its original frame number, timestamp, and
processed dimensions. Detection rows and class-wise summaries remain associated
with the frame that produced them.

The repository collects the lightweight frame results before opening the
transaction. This keeps model inference outside the transaction and avoids
holding a database connection while a video is still being processed. Frames
with no detections are recorded normally, while an empty frame sequence is
rejected before any database records are created.

Five focused tests cover multi-frame associations, empty-detection frames,
empty input, transaction rollback, and compatibility with existing image
storage. No schema change was needed because the initial design already supports
one video source with many processed frames.

## July 2026: Establishing Evaluation Rules

### Issue #40: Aerial Detection Evaluation Protocol

Before collecting or tuning against a new dataset, we fixed the rules for the
model-quality gate. The protocol defines six operational classes, source-grouped
training, validation, and held-out test partitions, COCO-style detection
metrics, frame-level count errors, synchronized GPU timing, and the information
required to reproduce each run.

We also predeclared the confidence thresholds and image sizes that may be tested
on validation data. The final gate combines precision, recall, average
precision, normalized count error, and processing latency, with separate pass,
conditional-pass, and fail outcomes. These thresholds are project engineering
targets rather than general safety claims.

The protocol records the current RTX 5060 development environment and explains
how future changes must be versioned. No model was evaluated or trained in this
issue. Dataset curation and licensing are the next task.

## Where We Are Now

As of 5 August 2026, we have verified that:

- the single-image pipeline runs from input to annotated output;
- supported video files can be opened, sampled, and processed with one reusable
  detector;
- image and sampled-video results can be stored when PostgreSQL is running;
- all current automated tests pass locally;
- Ruff linting and formatting checks pass;
- the latest GitHub Actions workflow on `main` passes.

The largest unresolved problem is detection quality. On our current aerial
sample, the general pretrained model misses many vehicles and labels two large
road regions as trains. This is a model and evaluation problem that we need to
solve before using the detections for meaningful traffic analysis.

The model-quality gate now has a fixed protocol. No result has passed that gate
yet.

## August 2026: Selecting The YOLO26n Baseline

### Issue #44: Benchmark And Tune The Current YOLO Baseline

We preserved the unchanged YOLO26n result and then compared the confidence
thresholds and image sizes declared in the evaluation protocol. We also
generated a deterministic qualitative review of false positives, false
negatives, class confusions, and the largest crowd-count errors. Every formal
experiment used validation data only and stored provenance and artifact
checksums.

We selected image size `1280` and confidence `0.25` as the baseline reference.
The larger image size produced the strongest detection and object-size results,
while confidence `0.25` gave the lowest road-vehicle count error among the
tested thresholds. We centralized these values as the application defaults and
added a separate executable evaluation configuration, while preserving the
original pre-tuning configuration.

The selected baseline failed the quality gate. Detection precision, recall,
average precision, and person-count error remain outside the required ranges,
although runtime passed and vehicle-count error was conditional. Dense DLR
crowd examples containing thousands of people received zero detections. This
result gives us an honest reference for the next aerial-model comparison rather
than evidence that the present model is ready for deployment.

### Issue #45: Selecting Aerial Model Candidates

Before downloading or comparing another model, we selected two traceable
VisDrone-tuned candidates. YOLO26m represents a practical medium-size option,
while YOLO11x represents a larger quality-oriented option. Both use the current
Ultralytics integration and cover the operational taxonomy through one shared
class mapping.

We pinned each Hugging Face repository revision, expected checkpoint hash, file
size, licence metadata, and source-reported metrics in a strict configuration.
The reported scores are used only to justify that the candidates are plausible;
our validation protocol will produce the evidence used for the actual decision.
We also recorded why several academically interesting models were excluded when
weights, class compatibility, or a maintainable local environment were missing.

### Issue #45: Preflighting The Candidate Checkpoints

We downloaded the two pinned checkpoints into separate local model directories
and verified their recorded file sizes and SHA-256 digests before loading them.
Both models loaded with Ultralytics 8.4.51 and completed one inference on the
same validation asset using the NVIDIA GeForce RTX 5060 Laptop GPU. This was a
technical compatibility check only; we did not calculate model-quality metrics
or inspect the held-out test split.

The first preflight attempt exposed one useful metadata mistake. Both
checkpoints contain an `others` source label in addition to the ten named
VisDrone object classes. We added it to the explicit exclusion list so future
evaluation keeps its raw predictions for traceability without treating them as
one of our six operational classes. The rerun passed checkpoint identity, model
loading, class-taxonomy, and single-image inference checks for both candidates.

The local report records the package versions, GPU, candidate revisions,
checkpoint hashes, and validation image hash. The report and model binaries
remain outside Git because they are machine-specific or large generated
artifacts; the reproducible sources and expected identities remain in the
tracked candidate configuration.

### Issue #45: Comparing The Aerial Models

We evaluated the frozen YOLO26n baseline, YOLO26m VisDrone, and YOLO11x
VisDrone from the same clean commit and against the same 86 validation assets.
All runs used image size 1280, scale factor 2, confidence 0.25, `max_det` 300,
and the complete timing protocol. Their dataset and annotation hashes matched,
and every generated artifact passed its manifest checksum.

The aerial models improved recall and mAP50, but neither met the quality gate.
Person normalized error remained above 0.98 for both candidates, while several
other core measures also failed. Testing the five predeclared confidence values
changed the precision and vehicle-count trade-off but did not change the
overall result.

We selected YOLO26m VisDrone as the starting point for a fine-tuning pilot. It
gave a more practical balance than YOLO11x: lower vehicle-count error, smaller
weights, lower GPU memory, and higher throughput, with only a modest reduction
in aggregate detection quality. The held-out split remains untouched, and the
pilot belongs to Issue #46 rather than this comparison.

## August 2026: Completing Evaluation And Resuming Application Work

### Issues #46-#48: Fine-Tuning And The Final Quality Gate

We ran a controlled YOLO26m fine-tuning pilot on source-group-clean Okutama
person boxes. Person detection improved, but vehicle detection collapsed because
the training partition contained no vehicle boxes, so we rejected the new
checkpoint. We then froze the original VisDrone YOLO26m configuration before
running the held-out split once.

The final model passed road-vehicle-total count error and runtime, but failed
recall, average precision, and dense-crowd person counting. We kept this result
rather than tuning after the test. The central metrics and limitations are
linked from `docs/evaluation/results_index.md`.

### Issue #24: Grid-Based Object Counting

We added a model-independent service that divides an image into configurable
rows and columns and assigns each detection according to its bounding-box
centre. It returns stable records for occupied and empty cells, validates image
dimensions and bounding boxes, and defines deterministic behavior at cell
boundaries. The image command can print an experimental grid summary with
`--grid ROWS COLUMNS`.

The unit tests establish that the spatial assignment code is correct for known
detections. They do not override the detector's failed quality gate, and the
result is not physical crowd density. Database persistence, overlays, and alert
rules remain separate work.

### Issue #63: Grid-Cell Database Persistence

We connected image grid results to the existing PostgreSQL schema without adding
new tables. A stored grid now creates one `grid_cells` row for every configured
region, including empty regions, and links each non-zero per-class count through
`object_count_summaries.grid_cell_id`. Complete-frame summaries keep a null grid
reference, so the two aggregation levels remain easy to distinguish.

Grid records use the same transaction as the session, source, processed frame,
detections, and complete-frame counts. A failure therefore rolls back the whole
image result. Repository tests cover mapping and rollback, while the PostgreSQL
CI job creates the schema, stores a controlled grid, queries the real foreign-key
relationships, and removes its temporary session.

### Issue #65: Ordered Database Migrations

We replaced the one-file database setup behavior with a small ordered migration
runner. It discovers strictly named SQL files, records their versions and
SHA-256 checksums in `schema_migrations`, skips verified migrations, and rejects
changed or missing migration history. All pending migrations and their history
rows share one PostgreSQL transaction, protected by an advisory transaction lock.

The original `001` migration remains idempotent, so databases created by the old
setup script can be adopted without deleting their stored sessions. Isolated
PostgreSQL integration tests verify fresh setup, repeated execution, legacy-data
preservation, and rollback when a later migration fails. The old table-creation
script remains as a compatibility wrapper, while the documented command is now
`scripts/migrate_database.py`.

### Issue #66: Runtime Model Profile And Session Provenance

We replaced the application's hard-coded YOLO26n path and duplicated inference
defaults with one strict runtime profile for the frozen VisDrone-trained
YOLO26m checkpoint. The profile records the exact checkpoint identity, project
class mapping, confidence, image size, preprocessing scale, maximum detections,
device, numeric precision, evaluation reference, and failed quality-gate status.
The application verifies the local checkpoint before YOLO is loaded and uses the
same settings for image and sampled-video processing.

Migration `002` adds one `model_run_profiles` record for each newly stored
monitoring session. This snapshot is written in the same transaction as the
session and its detections, so a result cannot be stored without its declared
runtime provenance. Existing sessions remain intact and are documented as
legacy records without complete model provenance. Alignment makes future
results reproducible; it does not change the detector's failed held-out result.

### Issue #67: Dedicated Dense-Crowd Evaluation

We added a reproducible evaluation path for a dedicated crowd-counting model and
tested the selected checkpoint against the prepared crowd evidence. The result did
not meet the declared acceptance criteria, so we rejected the checkpoint instead
of integrating it into the application. This keeps the limitation visible: the
current system can report detector-based person counts, but it cannot claim a
validated dense-crowd counting capability.

### Issue #68: Dense-Crowd Rejection Path

We connected the dedicated crowd evaluation decision to application results
without promoting the rejected P2PNet checkpoint. A strict loader reads the
tracked machine-readable evidence and accepts only its recorded rejection path.
The API now reports dense-crowd analysis as unsupported with a null count, no
active method or model, the evaluated candidate ID, and a link to the decision
record. Ordinary YOLO person detections remain separate frame summaries.

Migration `005` stores the same capability state once per new session and uses a
constraint to prevent unsupported records from containing a count or active
model. Image and sampled-video repositories write it in the same transaction as
model provenance and detections. Legacy sessions remain readable with a null
capability field. Unit and PostgreSQL tests cover evidence validation,
transaction rollback, persistence, retrieval, and the complete image API flow.

### Issue #69: FastAPI Backend Foundation

We added a separate FastAPI entry point without changing the existing command-line
pipeline. The API now distinguishes basic process health from dependency
readiness, verifies PostgreSQL and checkpoint availability, provides typed error
responses and OpenAPI documentation, and loads the detector only when a future
analysis route requests it. Database and detector dependencies can be replaced in
tests, so API checks do not need to load model weights.

### Issue #73: Stored-Result Query Models

We added the read side that was missing from PostgreSQL persistence. Session
history now has validated page-number pagination and deterministic ordering by
start time and ID. A complete session read reconstructs model provenance, input
metadata, ordered frames, detections, complete-frame summaries, grid cells,
per-cell summaries, and alerts into typed models.

The detail read uses a fixed number of bulk queries rather than one query for each
video frame. Migration `003` adds the matching session-history index. Unit tests
cover pagination, missing and legacy sessions, nested result grouping, and query
count. The PostgreSQL integration test stores and reads both a gridded image and
an intentionally out-of-order sampled video, then removes its controlled records.

### Issue #70: Safe Image Analysis API

We connected the existing image pipeline to FastAPI without duplicating detection
or grid logic. The new endpoint accepts JPG and PNG uploads, applies bounded byte
and decoded-pixel limits, checks extension, MIME type, actual format, and OpenCV
decoding, and replaces uploaded paths with generated UUID filenames. Inference
continues to use the tracked runtime profile, so requests cannot silently change
the checkpoint or evaluated settings.

The orchestration service writes the validated input, processes it with the shared
lazy detector, optionally creates a bounded grid, saves the annotated output, and
persists the complete result and model provenance. Migration `004` stores a public
output-asset UUID with its private path while result schemas expose only the UUID.
A failed validation, detector call, output write, or database transaction does not
leave partial files or a completed session. Controlled API tests cover success,
empty detections, malformed and oversized uploads, invalid grids, and failures;
the PostgreSQL test exercises the complete create-and-read workflow.

### Issue #71: Asynchronous Video Analysis And Progress

We connected the existing video reader, time-based sampler, detector, grid
counter, and repositories through a bounded background service. The upload route
accepts validated MP4, AVI, MOV, and MKV files, stores them under generated names,
creates a durable queued record, and returns HTTP `202` without waiting for
inference. A second route reports queued, processing, completed, or failed state
with sampled-frame progress.

Migration `006` stores video-job configuration, progress, timestamps, and public
failure details. Sampled results stay in memory until processing finishes, then
all frames, detections, summaries, and optional grids are committed together.
The default single worker bounds GPU work, and the detector itself serialises
inference. On restart, abandoned local jobs are marked failed instead of being
presented as resumable. Unit and PostgreSQL tests cover upload validation, prompt
queuing, progress, grid persistence, ordered reads, failures, and restart
recovery.
