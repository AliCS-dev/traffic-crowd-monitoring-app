# Database Schema

## Why We Use PostgreSQL

We use PostgreSQL to keep the structured information produced during image and
video processing. Instead of storing everything in one record, we separate
processing sessions, input sources, frames, detections, count summaries, grid
cells, and alerts. This gives us a clear history of how each result was produced.

Our first schema is defined in:

```text
app/database/migrations/001_create_initial_tables.sql
```

After PostgreSQL is running, we apply it with:

```bash
.venv/bin/python scripts/create_database_tables.py
```

## How the Tables Are Connected

```text
monitoring_sessions
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

### `input_sources`

An input source describes the image or video that belongs to a session. We store
its source type, file path, original filename, and creation time.

### `processed_frames`

A processed frame represents either one image or one selected frame from a
video. It contains the frame number, video timestamp, image dimensions, and
processing time. For a still image, we use frame number `0` and timestamp `0`.

### `detection_results`

We store one row for each detected object. A row contains:

- the predicted object class;
- the confidence score;
- the bounding-box coordinates;
- the related processed frame.

The coordinates currently refer to the preprocessed image. We store the frame
dimensions in the same coordinate space so that the values remain meaningful.

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

## What Happens During a Stored Run

When we use `--save-to-db`, we create the records in this order:

1. a monitoring session;
2. an image input source;
3. a processed frame;
4. the individual detection results;
5. the complete-frame class summaries;
6. optional grid cells and their per-cell summaries;
7. the completed session status.

All seven steps are part of one transaction. If one step fails, PostgreSQL rolls
back the transaction and we do not keep a partially stored run.

For a video, we follow the same transaction pattern, but create one
`processed_frames` row for every sampled frame. Each row keeps the original frame
number and timestamp. Its detections and class summaries use that frame's ID, so
results from different moments in the video do not become mixed. A sampled frame
is still stored when it has no detections.

## What We Still Need to Improve

- Our setup script applies only migration `001`; it does not yet discover or
  track later migrations.
- We do not store the model identity, model version, inference settings, or
  processing duration with a result yet.
- CI verifies grid-cell and per-cell summary relationships in PostgreSQL, but it
  does not yet cover every repository path with live database queries.
- The schema does not yet enforce one count summary per frame, grid cell, and
  object class.
- Session status values are not restricted by a database check constraint.

We will handle these improvements as focused changes when the related features
reach that stage of development.
