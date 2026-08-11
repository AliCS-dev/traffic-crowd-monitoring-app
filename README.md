# Traffic and Crowd Monitoring Application

We are developing this application as part of a BSc thesis on traffic and crowd
monitoring from aerial images and videos. Our goal is to turn visual data into
structured information that can be inspected, stored, and later used for
monitoring and analysis.

At this stage, we have a working detection pipeline for a single image. We can
also open video files, read their metadata, and sample frames at controlled time
intervals. Sampled frames can pass through the same preprocessing and detection
logic while the model is reused across frames. The resulting frame metadata,
detections, and class counts can be stored together as one video session.
For image runs, we can also divide the processed image into a configurable grid
and report class counts for each occupied cell. When database storage is enabled,
the application keeps the complete grid and its per-cell counts with the image
result.

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
| Grid-based spatial counting | Implemented as an experimental component |
| Grid-cell database storage | Implemented for image runs |
| Threshold-based alerts | Planned |

The current detector gives us a measured starting point, but it is not reliable
enough for final conclusions about aerial traffic or crowds. We compared three
pretrained candidates and ran a source-group-clean fine-tuning pilot. The pilot
improved person detection but removed useful vehicle performance, so we rejected
its checkpoint. Another combined-detector run now requires independent vehicle
training boxes; dense crowds may need a dedicated counting method.

## What We Use

- Python 3.10 or 3.11
- OpenCV and NumPy
- Ultralytics YOLO
- PostgreSQL 16 and Psycopg 3
- Docker Compose for the local database
- Pytest and Ruff
- GitHub Actions and Dependabot

## Repository Layout

```text
app/
  database/              Database connection, repository, and migrations
  services/              Image, preprocessing, detection, and output logic
  ui/                    Reserved for the future user interface
  config.py              Project paths and local defaults
  main.py                Command-line application entry point
data/
  evaluation/             Evaluation metadata; raw media excluded from Git
  input/                  Local input images and videos
  output/                 Generated annotated output
docs/                     Architecture and development documentation
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

Our current baseline is the COCO-pretrained YOLO26n detection model described in
the [official Ultralytics YOLO26 documentation](https://docs.ultralytics.com/models/yolo26/).
For a clean local setup, we can download the model through Ultralytics and place
it in the project model directory:

```bash
.venv/bin/python -c "from ultralytics import YOLO; YOLO('yolo26n.pt')"
mv yolo26n.pt models/yolo26n.pt
```

The application then loads the weights from:

```text
models/yolo26n.pt
```

We keep model weights out of Git because they are large binary artifacts. For
formal thesis experiments, we will record the exact model source and version so
that the results can be reproduced.

Local database values are stored in `.env`. We create it from the safe example:

```bash
cp .env.example .env
```

The example credentials are only for local development, and `.env` remains
outside version control.

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

## Reading And Sampling Video Input

The video service validates common video formats, reads basic metadata, and gives
us sequential access to frames. The sampling service selects frames at a
user-defined interval while preserving each selected frame's number and
timestamp. The video detection service reuses one model instance across those
frames:

```python
from app.config import MODEL_PATH
from app.database.detection_repository import save_video_detection_results
from app.services.detection_service import ObjectDetector
from app.services.frame_sampling_service import sample_video_frames
from app.services.video_detection_service import process_sampled_video_frames
from app.services.video_service import VideoReader

detector = ObjectDetector(MODEL_PATH)

with VideoReader("data/input/example.mp4") as video:
    sampled_frames = sample_video_frames(
        video,
        sampling_interval_seconds=1.0,
    )
    frame_results = list(process_sampled_video_frames(sampled_frames, detector))

stored_result = save_video_detection_results(
    "data/input/example.mp4",
    frame_results,
    session_name="sample video run",
)
print(stored_result)
```

Supported formats are MP4, AVI, MOV, and MKV. The context manager closes the
OpenCV video resource when we finish reading. Video persistence stores one
session and input source for the video, followed by one processed-frame row for
each sampled frame. The command-line application still handles image runs only;
a later interface can compose the same video services.

## Working with PostgreSQL

For now, PostgreSQL is the only part that we run in Docker. Python, OpenCV, and
YOLO continue to run in the local virtual environment.

We start the database and check its status with:

```bash
docker compose up -d postgres
docker compose ps
```

Once PostgreSQL is ready, these scripts check the connection and create the
initial tables:

```bash
.venv/bin/python scripts/check_db_connection.py
.venv/bin/python scripts/create_database_tables.py
```

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

The selected baseline can be reproduced as one complete validation run with:

```bash
.venv/bin/python scripts/run_detector_evaluation.py \
  --config configs/evaluation/yolo26n_selected_validation.json
```

Its confidence, image size, and preprocessing defaults are also used by the
image and video detection services. The configuration is a comparison baseline;
it did not pass the quality gate and must not be treated as a deployment-ready
model.

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

GitHub Actions starts PostgreSQL, checks the application connection, creates the
schema, and runs a grid-persistence integration test. The test queries the stored
cells and summaries through their real PostgreSQL relationships and removes its
temporary session afterwards.

## Project Documents

- [Architecture](docs/architecture.md)
- [Database schema](docs/database/database_schema.md)
- [Aerial detection evaluation protocol](docs/evaluation/evaluation_protocol.md)
- [Development log](docs/development_log.md)
- [Development workflow](docs/development_workflow.md)

## Scope and Current Limitations

We are building this project for monitoring, analysis, and decision support. We
are not trying to control traffic directly or make autonomous interventions.

There are several limitations that we are keeping visible while the application
is still under development:

- the final held-out detector evaluation failed the overall quality gate;
- the detector can miss or misclassify small aerial objects and dense crowds;
- grid storage is connected to image runs but not yet to sampled video frames;
- video processing is available through services but not through the
  command-line entry point;
- we do not yet generate alerts;
- the project does not yet have a user interface;
- we do not calculate physical crowd density.

Until we add geographic calibration, we use the terms **count per spatial
region** or **crowd concentration**. We reserve **crowd density** for a measured
number of people per physical area, such as people per square metre.
