# Runtime Provenance and Regression Checks

## What We Record

The checkpoint alone does not define a prediction. We also need to know which
code, libraries, settings and device produced it. New sessions keep that
information in `model_run_profiles`, alongside the existing checkpoint hash and
inference settings. Image runs and queued video runs use the same snapshot path.

`runtime_provenance` records the backend commit when available, a measured source
SHA-256, source state, Python and installed distribution versions, device, GPU
name, CUDA/cuDNN versions and container ID. We do not export environment variables,
credentials or host paths. A container ID identifies the running container, not
its image. The separate environment manifest links it to the immutable image ID.
Locally built images need not have a registry digest.

The source fingerprint covers `app` Python/SQL files, runtime configuration,
the Dockerfile, container dependency pins and the crowd-capability decision. It
does not cover the frontend, tests, scripts, secrets or model binaries. The model
has its own hash. The process captures its environment at startup; we restart it
after changing code or packages. Git metadata unavailable in a packaged build
stays null unless supplied during the build. Build arguments identify the intended
revision; the separately measured source hash helps detect changed backend files.

Migration `008` leaves historical metadata null. The browser displays
"Runtime provenance unavailable for this session" for those records, rather
than attributing today's package versions to an older result.

## Development Fixtures

We use two licensed validation images and a three-second MJPEG sequence made
from three existing validation images. The video exercises sampling and storage;
its repeated still images do not represent real traffic motion. The fixture
[README](../data/runtime-regression/README.md) contains attribution, licence and
transformation details. No held-out test media is used here.

Before collecting the baseline, we declared exact per-class counts, a maximum
0.5-pixel difference per box coordinate, and an absolute confidence difference
of 0.0001. Matching is one-to-one within each class, independent of prediction
order. Frame numbers, dimensions, timestamps, model settings and rendered JPEG
hashes must also match. A changed JPEG requires review even when boxes remain
within tolerance. This strict output check can flag encoding or font changes,
not just model changes.

The result is a development regression signal, **not model equivalence on all
inputs, an accuracy measurement, or a successful quality gate**. The detector
remains experimental and dense-crowd counting remains unsupported.

## Running a Comparison

We run these commands from the repository root with the usual Python development
environment, Docker GPU support, `.env` database settings and the recorded model
checkpoint present. A separate Compose project keeps the regression sessions out
of the normal thesis database. The build records a committed, clean checkout:

```bash
git status --short
export APP_REVISION=$(git rev-parse HEAD)
export APP_SOURCE_DIRTY=false
export FRONTEND_PORT=8082
docker compose -p traffic-runtime-check -f docker-compose.app.yml -f docker-compose.gpu.yml build
docker compose -p traffic-runtime-check -f docker-compose.app.yml -f docker-compose.gpu.yml up -d --wait
.venv/bin/python scripts/check_runtime_regression.py --base-url http://127.0.0.1:8082
.venv/bin/python scripts/export_runtime_manifest.py --container traffic-runtime-check-backend-1 --output data/runtime-regression/environment.json
.venv/bin/python scripts/check_runtime_regression_evidence.py
```

We only use `APP_SOURCE_DIRTY=false` after committing the source. An intentionally
modified build uses `true` instead and cannot supply clean dependency-update
evidence. The check submits two images and one video; it reads back five stored
frames and their JPEGs. It writes `latest.json` and exits nonzero when results
change. It never silently overwrites `baseline.json`.

The initial baseline was created with `--establish-baseline`. A deliberate
replacement needs a new explicit baseline path and review of the differences.
We retain the old reference in Git. We do not loosen tolerances simply to make
a dependency PR pass. A reviewed reference change belongs in a separate PR,
with the reason and before/after evidence, before rechecking the dependency PR.

On dependency PRs changing the backend Dockerfile or Python runtime requirement
files, CI checks that committed evidence matches the backend source and pinned
versions, fixture bytes, unchanged reference and actual comparison results. Missing,
stale or changed output fails the Python quality job. The hosted runner does not
claim to run a GPU benchmark: it validates the recorded local GPU evidence.
Review remains necessary, and repository branch protection controls whether a
failed check can be bypassed. Frontend and workflow-only updates use their own
tests and are not claimed to change detector inference.

## Restoring the Backend

The committed `environment.json` identifies the exact backend image used for the
regression. `baseline.json` and `latest.json` contain the model hash and inference
settings. These records contain no model weights, database backup or private media.
Those remain separate recovery requirements. A manifest alone cannot recover an
image that has been deleted from every machine and registry.

We preserve an image before removing it, using the `image_id` from the manifest:

```bash
docker image save --output traffic-backend-runtime.tar sha256:<recorded-image-id>
docker image load --input traffic-backend-runtime.tar
export BACKEND_IMAGE=sha256:<recorded-image-id>
export FRONTEND_PORT=8082
docker compose -p traffic-runtime-restore -f docker-compose.app.yml -f docker-compose.gpu.yml up -d --no-build --wait
.venv/bin/python scripts/check_runtime_regression.py --base-url http://127.0.0.1:8082 --output data/runtime-regression/restore.json
```

The restore command assumes the frontend image is already available and the model
file matches the checkpoint hash. It creates separate database and media volumes.
It restores the backend runtime, not a previous database. We use a fresh project
name and a free port rather than deleting existing volumes. Building again from
the recorded commit and pinned base is a fallback, not proof of byte-identical
recovery, because OS package repositories can change. GPU drivers and hardware
also remain external requirements.

## Evidence

- [Fixture manifest](../data/runtime-regression/manifest.json): source checksums and declared tolerances.
- [Baseline](../data/runtime-regression/baseline.json): initial predictions and settings.
- [Repeated run](../data/runtime-regression/latest.json): comparison with that baseline.
- [Environment](../data/runtime-regression/environment.json): measured backend packages and immutable image identity.
- [Fresh-container run](../data/runtime-regression/restore.json): September reproduction with separate database and media volumes.
- [Fresh-container environment](../data/runtime-regression/restore_environment.json): the September restore used a distinct container with the same image and packages as that month's baseline run. It is not a restore check of subsequent dependency updates.

The fresh-container check uses the same host GPU. It does not establish
cross-hardware reproducibility, and it is not a test of restoring a database
backup.

### Verification on 22 September 2026

We built backend commit `012bc6cebab302017b80031d8ced07bc22bf5bf7` with
source fingerprint `d2717d1bc63e83de65b30c5547d10802389783566dd8bb7420d1272d0779bb4c`.
The run used Python 3.12.3, Ultralytics 8.4.155, PyTorch 2.14.0, CUDA 13.0 and
an NVIDIA GeForce RTX 5060 Laptop GPU. Exact installed versions, including base
image packages, are in the environment manifests.

| Fixture / frame | Total detections | Repeated run | Fresh-container run |
| --- | ---: | --- | --- |
| `roundabout_6.png` | 27 | Pass | Pass |
| `roundabout_29.png` | 32 | Pass | Pass |
| `roundabout_sequence.avi`, frame 0 | 21 | Pass | Pass |
| `roundabout_sequence.avi`, frame 10 | 24 | Pass | Pass |
| `roundabout_sequence.avi`, frame 20 | 30 | Pass | Pass |

These are prediction counts, not reference labels or accuracy scores. The
MJPEG frames are lossy derivatives, so their predictions need not match the PNG
predictions. We compare each fixture only with its own frozen reference.

We saved the backend image to `/tmp/traffic-issue112-backend.tar`, loaded it again,
and started `traffic-issue112-restore` on port 8082 using the recorded image ID
without rebuilding. All eight migrations ran on its new database. Sessions 1-3
in that stack reproduced baseline sessions 18-20 from `traffic-stack-check`;
repeat sessions 21-23 also passed. Counts, matched boxes, confidence values and
rendered hashes met every declared check. The image ID and package versions
matched between the two distinct containers. The temporary archive is local,
not a committed or off-machine backup, and loading it while layers already exist
does not test recovery after loss of the Docker installation.

Verification also passed 427 Python tests, 11 PostgreSQL integration tests,
106 frontend unit tests, eight mocked desktop/mobile browser tests and two live
desktop/mobile image-upload checks. The latter inspected the expanded runtime
panel, loaded the saved image, checked overflow and retained screenshots locally
under `frontend/test-results/stack/`. Linting, formatting, the production frontend
build and container `pip check` passed. Historical session 1 remained readable
through the live API with null runtime provenance. The integration suite also
verified a version-7 database migration without inventing historical metadata.

### Pillow Security Update on 24 October 2026

We tested PR #148 from clean commit
`c00f232ad3b741ac65506a7622cadda5de4ee478`, after bringing it up to date with
main. Pillow changed from 12.3.0 to 13.0.0; the detector checkpoint, runtime
settings and other pinned backend dependencies did not change. The new source
fingerprint is
`44ebff748dcfe77d771cbd68ae8662a561e9566437af234a5fcf7dd4b374327a`.

The isolated `traffic-dependency-review` stack used the RTX 5060 and CUDA 13.0.
All five fixture frames passed against the unchanged September reference:
counts remained 27, 32, 21, 24 and 30, with no reported differences in boxes,
confidence values or rendered JPEG hashes. The Pillow-only comparison and
environment are retained in
[commit d8c259c](https://github.com/AliCS-dev/traffic-crowd-monitoring-app/commit/d8c259ca5f3b2118d8fb9d3eacf493b42f4aacad).
The older baseline and restore records remain unchanged.

The container dependency check, CUDA smoke test, 11 PostgreSQL integration tests
and two live desktop/mobile image workflows passed. We ran integration tests in
a separate test database because the maintenance test requires no active API
lease. The host Python suite also passed 570 tests, with the 11 opt-in database
tests skipped there. These checks support the dependency update, not improved
detector accuracy or a passed model quality gate. Historical evaluation results
are unchanged.

### Combined Runtime Update on 24 October 2026

We combined the PyTorch image change from PR #135 with the matching package
updates in PR #145. The base image supplies PyTorch 2.14.1 and torchvision
0.29.1, so installation does not replace them with a different pair. Pillow
13.0.0 remains in place. We also pinned `opentelemetry-api` 1.45.1, a dependency
introduced by the updated FastAPI package, rather than leaving it unresolved.

Dependabot refreshed #145 after the Pillow merge. We incorporated that refresh
and repeated the comparison with Ultralytics 8.4.183, FastAPI 0.156.8 and
Starlette 1.9.0. The final clean build is commit
`c9547cfd7e743c02fab1f08d56d8e72c94573b02`, with source fingerprint
`7a81c85cf48f67314139eab210e91f7ba1a9860d1a26329fd9bb97922816526a`.
The current `latest.json` and `environment.json` identify this run and its
complete installed package versions.

All five development frames passed against the original September baseline,
including the rendered hashes. We did not alter that reference, its tolerances,
the checkpoint or model settings. Container dependency checks and the CUDA
smoke check passed. A disposable container using the updated runtime passed
all 581 Python tests, including the 11 PostgreSQL integration tests, with a
separate test database. Test-only libraries were installed in that disposable
container, not in the application image.

The frontend passed 106 unit tests, eight mocked browser tests and two live
desktop/mobile image workflows against the final backend. Linting, formatting
and type checks also passed. These checks support merging the dependencies;
they do not re-evaluate the detector's accuracy. The earlier UAVDT results and
the failed model quality gate remain unchanged.
