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

We merged this implementation into `main` on 13 July 2026. The GitHub issue is
still open and can be closed separately after we confirm the merged result.

## Where We Are Now

As of 13 July 2026, we have verified that:

- the single-image pipeline runs from input to annotated output;
- results can be stored when PostgreSQL is running;
- all six current automated tests pass locally;
- Ruff linting and formatting checks pass;
- the latest GitHub Actions workflow on `main` passes.

The largest unresolved problem is detection quality. On our current aerial
sample, the general pretrained model misses many vehicles and labels two large
road regions as trains. This is a model and evaluation problem that we need to
solve before using the detections for meaningful traffic analysis.

## What We Plan to Work on Next

Our next stages are to improve and evaluate aerial detection, add video input and
frame sampling, divide frames into spatial grids, and store counts for those
regions. After that, we plan to add alert rules, broader automated tests, and the
user-facing application interface. The thesis evaluation will bring these parts
together by measuring both detection quality and system performance.
