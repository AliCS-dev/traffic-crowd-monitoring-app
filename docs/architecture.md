# Application Architecture

## Why We Use This Structure

We want the application to stay understandable while it grows from a single
image prototype into a monitoring application for images and videos. We separate
parts that have different responsibilities, but we avoid adding layers that the
project does not yet need.

The current structure lets us work on image input, detection, database storage,
and later video processing without placing everything in one large script.

## Current Processing Flow

```text
Command-line input
       |
       v
Load and validate image
       |
       v
Resize image for detection
       |
       v
Run YOLO object detection
       |
       +---------------------> Save annotated image
       |
       v
Extract detections and class counts
       |
       v
Optional PostgreSQL transaction
  - monitoring session
  - input source
  - processed frame
  - detection results
  - object count summaries
```

Video input currently has its own smaller flow:

```text
Video file
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
Future frame sampling and detection
```

## Main Components

| Component | Role in the application |
| --- | --- |
| `app/main.py` | Coordinates one image-processing run |
| `app/config.py` | Keeps project paths and local defaults in one place |
| `app/services/image_service.py` | Checks the input path and loads supported images |
| `app/services/video_service.py` | Opens videos, reads metadata, and provides frames |
| `app/services/preprocessing_service.py` | Resizes images before inference |
| `app/services/detection_service.py` | Runs YOLO and converts its output into counts and records |
| `app/services/output_service.py` | Creates the annotated output image |
| `app/database/connection.py` | Reads `DATABASE_URL` and opens PostgreSQL connections |
| `app/database/detection_repository.py` | Stores one image result in a transaction |
| `scripts/` | Contains explicit database setup and diagnostic commands |

`app/main.py` brings these pieces together, while the service modules contain
the individual processing steps. This gives us a simple command-line application
today and leaves room for a future interface to reuse the same logic.

## How We Store a Result

When we use `--save-to-db`, we store the records for one image inside a single
database transaction. If one insert fails, the transaction is rolled back, so we
do not keep an incomplete processing run.

We use parameterised SQL throughout the repository. Values are passed separately
from the SQL statements, which keeps the queries clear and avoids building SQL
from user-provided strings.

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

### Treating one image as one session

For the current image pipeline, one stored image creates one monitoring session,
one input source, and one processed frame. The same schema can later represent a
video as one source with many sampled frames.

## Where We Plan to Extend It

Our planned sequence is:

1. improve and evaluate the aerial-object detection baseline;
2. sample video frames at controlled time intervals;
3. send selected frames through the detection pipeline;
4. assign detected-object centres to grid cells;
5. store count summaries for each grid cell;
6. generate threshold-based alerts;
7. add a user-facing interface and result views.

We want each step to remain independently testable. The video reader now supplies
frames without knowing how they will be sampled or detected. This lets the next
stage reuse the existing detection service instead of creating a separate
pipeline.

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

- We currently load the model once for every application run. For video, we will
  need to load it once and reuse it across frames.
- The video reader is not yet connected to the command-line detection pipeline.
- We do not yet store model identity, inference settings, or processing time with
  a database result.
- Our migration script currently applies only the first migration file.
- We do not yet have integration tests for database storage.
- `app/ui` is reserved for later work and does not contain an interface yet.
