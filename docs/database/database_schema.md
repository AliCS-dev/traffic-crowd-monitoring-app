# Database Schema

## Why We Use PostgreSQL

We use PostgreSQL to keep the structured information produced during image and
video processing. Instead of storing everything in one record, we separate
processing sessions, input sources, frames, detections, count summaries, grid
cells, and alerts. This gives us a clear history of how each result was produced.

Schema changes are stored as numbered SQL files under:

```text
app/database/migrations/
```

After PostgreSQL is running, we apply all pending migrations with:

```bash
.venv/bin/python scripts/migrate_database.py
```

The runner accepts strict names in the form `NNN_lowercase_name.sql`, orders
them by version, and applies all pending files in one transaction. It also takes
a PostgreSQL advisory transaction lock so two application processes cannot
migrate the same database simultaneously.

### `schema_migrations`

This metadata table records each applied migration's version, name, SHA-256
checksum, and application time. A repeated migration command verifies the
recorded files and skips them. If an applied file has been renamed, edited, or
removed, the command stops rather than pretending the database still matches
the repository.

Databases created before the runner existed have the `001` tables but no history
row. Because `001_create_initial_tables.sql` uses idempotent `CREATE ... IF NOT
EXISTS` statements, the first migration run can execute it again, preserve the
existing rows, and then record its checksum. Later schema changes must be added
as new migration files; applied files are immutable.

## How the Tables Are Connected

```text
monitoring_sessions
  |
  +-- model_run_profiles
  |
  +-- dense_crowd_analysis_results
  |
  +-- video_analysis_jobs
  |
  +-- input_sources
  |     |
  |     +-- processed_frames
  |             |
  |             +-- detection_results
  |             +-- grid_cells
  |             +-- object_count_summaries
  |             +-- alerts
  |
  +-- processed_frames
```

Each processed frame also points directly to its monitoring session. We use this
to make session-based queries straightforward, while the application keeps the
session and input-source relationships consistent.

## What We Store

### `monitoring_sessions`

We create a monitoring session for each processing run. It keeps the session
name, current status, start time, completion time, and optional notes.

### `model_run_profiles`

Each newly stored monitoring session has one snapshot of the runtime model
profile used to produce it. The record includes the profile and model IDs,
quality-gate status, evaluation reference, checkpoint path and SHA-256, class
mapping, confidence, image size, preprocessing scale factor, maximum detections,
numeric precision, and device. We store this snapshot rather than only a pointer
to the current configuration, so later configuration changes do not erase how an
older result was produced.

Sessions created before migration `002` do not have a profile row. They remain
valid historical records, but their exact model provenance was not captured.

### `dense_crowd_analysis_results`

Migration `005` adds one optional dense-crowd analysis record per monitoring
session. For current sessions, the row stores `unsupported`, a null count, no
active method or model, the rejected candidate ID, failed quality-gate status,
the evaluation reference, and a stable reason code. A database constraint
prevents an unsupported result from carrying a numeric count or pretending that
a model was active.

This record is separate from detector summaries. A `person` count in
`object_count_summaries` is the number of YOLO detections, while
`dense_crowd_analysis_results.crowd_count` belongs only to a dedicated crowd
method. Existing sessions remain readable with no crowd-analysis record.

### `input_sources`

An input source describes the image or video that belongs to a session. We store
its source type, file path, original filename, and creation time.

### `video_analysis_jobs`

Migration `006` adds one persistent job record for each API video analysis. It
stores the queue state, sampling interval, optional grid dimensions, source and
sampled frame totals, processed-frame progress, timestamps, and public failure
details. Database checks keep grid dimensions paired, progress within its total,
and completed or failed states internally consistent.

The job row is created together with its queued monitoring session, model
profile, crowd-capability record, and input source before inference begins.
Completed frame results are inserted in a later all-or-nothing transaction.

### `processed_frames`

A processed frame represents either one image or one selected frame from a
video. It contains the frame number, video timestamp, image dimensions, and
processing time. For a still image, we use frame number `0` and timestamp `0`.

Migration `004` adds an optional output-asset UUID and private output path. A
constraint requires both values together, and a partial unique index prevents
two frames from sharing the same public asset identifier. Existing image and
video records remain valid with both fields null. New image analyses and sampled
video frames store generated JPEG references. The read schema exposes the UUID,
controlled asset URL, dimensions, and coordinate-space description, but not the
server path.

### `detection_results`

We store one row for each detected object. A row contains:

- the predicted object class;
- the confidence score;
- the bounding-box coordinates;
- the related processed frame.

The coordinates currently refer to the preprocessed image. We store the frame
dimensions in the same coordinate space so that the values remain meaningful.
Those dimensions also match the generated JPEG served for the frame.

### `object_count_summaries`

We use this table for class-wise counts. A complete-frame summary has a null
`grid_cell_id`. A per-cell summary references its related grid cell. This keeps
both levels in one table while allowing queries to distinguish them directly.

### `grid_cells`

This table describes rectangular regions inside a processed frame. Each region
has a row, column, and image-coordinate boundary. For stored image grids, the
repository inserts every configured cell in row-major order, including empty
cells. It then stores one linked summary for each non-zero class count.

### `alerts`

This table is ready for future threshold-based warnings. It can hold the alert
type, severity, message, measured value, threshold, and resolution time. We have
not implemented the alert rules yet.

## How We Read Stored Results

The write repository creates complete processing transactions. The monitoring
query repository provides the matching read side for application history and
result views. It returns typed application schemas instead of exposing PostgreSQL
rows to API or interface code. The result schema identifies a source by its ID,
type, original filename, and creation time without exposing the server's internal
file path.

Session history uses page numbers and a bounded page size. We order sessions by
`started_at DESC, id DESC`; the ID is the deterministic tie-breaker when two runs
have the same timestamp. Migration `003` adds an index in this order so PostgreSQL
can support the history query as the number of sessions grows.

A complete result is reconstructed with a fixed set of bulk queries. We load the
session and model profile, dense-crowd capability, sources, frames, detections,
grid cells, summaries, and alerts by relationship. The number of queries does not
grow with the number of sampled video frames. Complete-frame summaries and
per-cell summaries remain in separate fields in the returned schema, even though
PostgreSQL stores them in the same table.

When a frame has an output asset, the result model derives its public
`/api/assets/<uuid>` URL from the stored identifier. File access remains a
separate service concern: the private path is checked against configured output
directories before any bytes are returned.

Sessions created before model-profile snapshots were introduced remain readable.
Their `model_profile` field is null, which preserves the historical record without
inventing provenance that was not stored at the time.

## What Happens During a Stored Run

When we use `--save-to-db`, we create the records in this order:

1. a monitoring session;
2. its model and inference profile snapshot;
3. its dense-crowd capability result;
4. an image input source;
5. a processed frame;
6. the individual detection results;
7. the complete-frame class summaries;
8. optional grid cells and their per-cell summaries;
9. the completed session status.

All nine steps are part of one transaction. If one step fails, PostgreSQL rolls
back the transaction and we do not keep a partially stored run.

For a video, we follow the same transaction pattern, but create one
`processed_frames` row for every sampled frame. Each row keeps the original frame
number and timestamp. Its detections and class summaries use that frame's ID, so
results from different moments in the video do not become mixed. A sampled frame
is still stored when it has no detections.

API video jobs add a durable boundary around this process. We first commit the
queued job and input metadata. Progress updates commit after each sampled frame,
but detections, summaries, and grids remain in memory until every frame has
finished. The completion transaction writes all frame results and changes both
the job and session to `completed`. A processing error records a reproducible
`failed` state without leaving partial result frames.

## What We Still Need to Improve

- We do not store processing duration with a result yet.
- CI verifies database migrations, grid persistence, deterministic history
  pagination, complete image reconstruction, and ordered sampled-video reads
  against PostgreSQL. Future write and query paths will need matching coverage.
- The schema does not yet enforce one count summary per frame, grid cell, and
  object class.
- Session status values are not restricted by a database check constraint.

We will handle these improvements as focused changes when the related features
reach that stage of development.
