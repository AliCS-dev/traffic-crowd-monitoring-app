# Traffic and Crowd Monitoring Application

We are developing this application as part of a BSc thesis on traffic and crowd
monitoring from aerial images and videos. Our goal is to turn visual data into
structured information that can be inspected, stored, and later used for
monitoring and analysis.

At this stage, we have a working pipeline for a single image. We can load and
preprocess an image, run object detection, count the detected classes, generate
an annotated output image, and optionally store the results in PostgreSQL. Video
processing, spatial grid analysis, and alerts are the next parts of the project.

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
| Video input and frame sampling | Planned |
| Grid-based spatial counting | Planned |
| Threshold-based alerts | Planned |

The current detector gives us a useful starting point, but it is not yet reliable
enough for final conclusions about aerial traffic. We still need to evaluate the
model properly, restrict the relevant classes, and decide whether an
aerial-specific or fine-tuned model is needed.

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
  input/                  Local input images and videos
  output/                 Generated annotated output
docs/                     Architecture and development documentation
models/                   Local model weights, excluded from Git
scripts/                  Database setup and connection checks
tests/                    Automated tests
```

The reasoning behind this structure is described in our
[architecture document](docs/architecture.md).

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

To keep the results from an image run, we add the database option:

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

## Checks We Run

Before opening a pull request, we run the same basic checks that are used in CI:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m compileall app scripts
```

GitHub Actions also starts PostgreSQL and checks that the application can connect
to it. At the moment, this is only a connection smoke test. Full database
integration tests are still part of our planned work.

## Project Documents

- [Architecture](docs/architecture.md)
- [Database schema](docs/database/database_schema.md)
- [Development log](docs/development_log.md)
- [Development workflow](docs/development_workflow.md)

## Scope and Current Limitations

We are building this project for monitoring, analysis, and decision support. We
are not trying to control traffic directly or make autonomous interventions.

There are several limitations that we are keeping visible while the application
is still under development:

- we have not yet completed a formal evaluation of detection quality;
- the general pretrained model can misclassify small aerial objects;
- we currently store counts for a complete image, not for individual grid cells;
- we do not yet process video or generate alerts;
- the project does not yet have a user interface;
- we do not calculate physical crowd density.

Until we add geographic calibration, we use the terms **count per spatial
region** or **crowd concentration**. We reserve **crowd density** for a measured
number of people per physical area, such as people per square metre.
