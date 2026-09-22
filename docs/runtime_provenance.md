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
- [Fresh-container run](../data/runtime-regression/restore.json): reproduction with separate database and media volumes.

The fresh-container check uses the same host GPU. It does not establish
cross-hardware reproducibility, and it is not a test of restoring a database
backup. Verification results are recorded below after the live checks finish.
