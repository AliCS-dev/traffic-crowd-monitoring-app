# Traffic and Crowd Monitoring Application

We are building this application for a BSc thesis on analysing aerial images
and videos. It detects objects, counts them across image regions and stores
the results so we can inspect them later in a browser.

**The application works as an experimental analysis tool. Its selected detector
has not passed our accuracy requirements, and dense-crowd counting is currently
unsupported.** A completed analysis means processing finished, not that every
object was correctly detected.

![An aerial image result with detections, a selected grid cell and separate object counts](docs/images/user-guide/image-result.png)

*A real development-image run, not a ground-truth annotation or accuracy
benchmark. Image credit: Sergio Ghisler, Javier Sanchez-Soriano and Sergio
Bemposta Rosende, CC BY 4.0. [Screenshot details and attribution](docs/images/user-guide/README.md).*

## What We Can Do

- Submit an image or video through the browser.
- Inspect detections, class counts and counts within a selected grid cell.
- Browse sampled video frames with their source timestamps.
- Reopen saved analyses from session history.
- Read the model settings and experimental threshold events stored with a run.

The [illustrated user guide](docs/user_guide.md) follows an image from upload
to its saved result. Video counts belong to individual sampled frames; they
are not totals of unique vehicles or people across a recording.

## Run the Application

The complete application runs locally with Docker Compose. We need Docker
Compose v2, a configured `.env` and the verified model weights before starting.
The GPU option also needs NVIDIA support in Docker.

From the repository root, create `.env` only if it does not already exist:

```bash
cp -n .env.example .env
```

Choose a local database password in `.env`. The selected checkpoint belongs at
`models/candidates/yolo26m-visdrone/best.pt`; it is not included in Git.
The [local setup guide](docs/local_development.md#running-the-project-locally)
explains how we download and verify it.

For our NVIDIA setup:

```bash
docker compose -f docker-compose.app.yml -f docker-compose.gpu.yml up -d --build --wait --wait-timeout 240
```

Open **<http://localhost:8080>**. For CPU execution, omit
`-f docker-compose.gpu.yml`. The [Compose guide](docs/compose_stack.md) covers
prerequisites, storage, shutdown and troubleshooting. The application is a
localhost demonstration without authentication, not a public hosting setup.

## How It Fits Together

We use React and TypeScript for the browser, FastAPI and Python for processing,
YOLO for object detection, and PostgreSQL for structured results. Uploaded media
and generated images live in local files or Docker volumes.

```mermaid
flowchart LR
    Browser[Browser] --> Web[React served by Nginx]
    Web --> API[FastAPI]
    API --> Processing[Image and sampled-video processing]
    Processing --> Detector[YOLO detector]
    Processing --> Counts[Grid counts and threshold events]
    API --> DB[(PostgreSQL)]
    Processing --> Media[(Media files)]
    API --> Media
```

The browser talks to the API, not directly to the database. Processing results
are stored before we reopen them from history. The
[architecture guide](docs/architecture.md) explains the boundaries and decisions.

## Documentation

| What you need | Where to start |
| --- | --- |
| See and use the application | [User guide](docs/user_guide.md) |
| Run the complete stack | [Docker Compose](docs/compose_stack.md) |
| Change or test the code | [Local development](docs/local_development.md) and [development workflow](docs/development_workflow.md) |
| Use the API or image CLI | [API reference](docs/api.md) and [command-line processing](docs/command_line.md) |
| Understand the data model | [Database schema](docs/database/database_schema.md) |
| Find thesis metrics and experiment decisions | [Evaluation results index](docs/evaluation/results_index.md) |
| Find the remaining work | [Quality roadmap](quality_roadmap.md) |

The [documentation index](docs/README.md) separates current guides from dated
verification reports and development history.

## Limits We Keep Visible

The detector can miss or misclassify small aerial objects. The
[recorded held-out evaluation](docs/evaluation/final_quality_gate.md) failed its
overall quality gate; the new evaluation work has not produced replacement
accuracy results. Dense-crowd analysis returns an unsupported status and no
count, rather than a misleading zero.

Grid counts describe regions of an image, not people or vehicles per square
metre. Threshold events do not establish congestion, overcrowding or danger.
Video jobs run in one API process; interrupted jobs are marked failed at the
next startup rather than resumed. We describe these boundaries in the
[user guide](docs/user_guide.md#reading-the-results-carefully) and
[operational guide](docs/operational_safeguards.md).
