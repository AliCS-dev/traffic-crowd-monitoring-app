# Application Testing

[Documentation index](README.md) | [System evaluation plan](evaluation/system_evaluation_plan.md)

We test whether the application handles its inputs, stores consistent results
and lets us reopen them. These checks do not establish detector accuracy.
Controlled detections make software failures reproducible; the real-model
regression remains a separate local GPU check.

## Workflow Coverage

The matrix follows the implemented workflows, not a target coverage percentage.
Python unit and API tests use controlled dependencies unless marked PostgreSQL.
Browser tests under `e2e/` use mocked HTTP responses; `stack-tests/` use the real
application. The Compose check uses real Nginx, FastAPI, decoding and PostgreSQL,
but replaces inference with one deterministic detection per frame.

| Workflow or failure | Automated coverage | Boundary |
| --- | --- | --- |
| Image upload, preprocessing, grid and saved result | [Service](../tests/test_image_analysis_service.py), [API](../tests/test_image_analysis_api.py), [PostgreSQL](../tests/integration/test_image_analysis_api_integration.py), [browser submission](../frontend/e2e/submission.spec.ts) | Includes result navigation and clean/annotated assets |
| Video submission, progress, completion and failure | [Service](../tests/test_video_analysis_service.py), [API](../tests/test_video_analysis_api.py), [browser submission](../frontend/e2e/submission.spec.ts), [Compose](../tests/compose/check_workflows.py) | Real worker/decoding/storage in Compose; browser states are controlled |
| Frame sampling and sampled-frame navigation | [Sampling](../tests/test_frame_sampling.py), [video processing](../tests/test_video_detection.py), [browser](../frontend/e2e/dashboard.spec.ts) | No tracking or unique-object claim |
| Counts and boundary cells | [Grid logic](../tests/test_grid_counting.py), [PostgreSQL relationships](../tests/integration/test_grid_persistence.py) | Empty frames, image edges and frame/grid totals |
| Experimental threshold alerts | [Rules](../tests/test_alert_service.py), [stored alerts](../tests/integration/test_image_analysis_api_integration.py), [browser inspection](../frontend/e2e/dashboard.spec.ts) | Rule semantics, not congestion detection |
| History, pagination and stored relationships | [API](../tests/test_analysis_results_api.py), [PostgreSQL queries](../tests/integration/test_monitoring_query_repository_integration.py), [history page](../frontend/src/pages/SessionsPage.test.tsx) | Empty, unavailable and completed states |
| Invalid media, oversized input and invalid options | [Image validation](../tests/test_image_upload_service.py), [video validation](../tests/test_video_upload_service.py), [form validation](../frontend/src/features/analysis/analysisForm.test.ts), [browser rejection](../frontend/e2e/submission.spec.ts) | Rejection before processing; selected file retained for retry |
| Admission limits, deadlines and partial-file cleanup | [Safeguards](../tests/test_operational_safeguards.py), [video service](../tests/test_video_analysis_service.py) | Controlled failures; no load-capacity benchmark |
| Database write failure and rollback | [Result rollback](../tests/integration/test_result_rollback.py), [migration rollback](../tests/integration/test_database_migrations.py), [commit timing](../tests/test_stage_timing.py) | Real constraint violations leave no partial result; video can then be marked failed |
| Missing assets and unsafe paths | [Asset service](../tests/test_output_asset_service.py), [asset API](../tests/test_output_asset_api.py), [browser](../frontend/e2e/dashboard.spec.ts) | Unknown IDs, unavailable files and stored-path restrictions |
| Backend/database unavailable | [Readiness](../tests/test_api_application.py), [safe errors](../tests/test_analysis_results_api.py), [browser recovery](../frontend/e2e/dashboard.spec.ts) | Controlled outage responses; not a timed outage experiment |
| Restart and interrupted video jobs | [PostgreSQL recovery](../tests/integration/test_video_job_repository_integration.py), [Compose restart](../tests/compose/check_workflows.py) | Seeds an abandoned queued job; restart marks it failed and preserves completed assets |
| Scene alignment and accessible interaction | [Browser scene](../frontend/e2e/scene-workspace.spec.ts), [dashboard](../frontend/e2e/dashboard.spec.ts), [components](../frontend/src/features/results/SceneInspection.test.tsx) | Desktop/mobile, keyboard, touch, resize and filters; not a full accessibility certification |
| Startup, migrations, proxy and health | [CI workflow](../.github/workflows/ci.yml), [Compose check](../tests/compose/check_workflows.py) | Production images with an explicit test-only inference override |
| Real GPU and saved image/video workflows | [Regression runner](../scripts/check_runtime_regression.py), [live browser suite](../frontend/stack-tests) | Local GPU required; unchanged licensed fixtures, not held-out accuracy evaluation |

## Running the Checks

The [README](../README.md#testing) lists the everyday commands. Database tests
require a disposable database selected explicitly with `DATABASE_URL` and
`RUN_DATABASE_INTEGRATION_TESTS=1`. Without the latter they are skipped, not passed.
The tests create and remove records; they must not run against thesis evidence.

From the repository root, this example starts a separate local test database:

```bash
docker run --rm -d --name traffic-quality-db \
  -e POSTGRES_DB=traffic_monitoring -e POSTGRES_USER=traffic_user \
  -e POSTGRES_PASSWORD=local_test_only -p 127.0.0.1:5546:5432 postgres:16
docker exec traffic-quality-db pg_isready -U traffic_user -d traffic_monitoring
DATABASE_URL=postgresql://traffic_user:local_test_only@127.0.0.1:5546/traffic_monitoring \
  RUN_DATABASE_INTEGRATION_TESTS=1 .venv/bin/python -m pytest
docker stop traffic-quality-db
```

We wait for `pg_isready` to succeed before running tests. The port and container
name must be unused. The example password belongs only to this disposable local
test database, not the application `.env`.

### Controlled Compose Check

The [test overlay](../docker-compose.test.yml) mounts helpers from
`tests/compose/` read-only. They are excluded from the production image. The
test entrypoint explicitly labels its model `controlled-compose-test` with
`not_evaluated` status. It bypasses checkpoint/inference checks only in that
process; PostgreSQL readiness, migrations, application services and repositories
still run normally. No model file is needed.

In a separate shell, from the repository root:

```bash
export COMPOSE_PROJECT_NAME=traffic-quality-check
export COMPOSE_FILE=docker-compose.app.yml:docker-compose.test.yml
export POSTGRES_PASSWORD=local_test_only
export BACKEND_IMAGE=traffic-quality-backend:local
export TEST_FRONTEND_IMAGE=traffic-quality-frontend:local
export FRONTEND_PORT=8086

docker compose --env-file /dev/null up -d --build --wait --wait-timeout 180
docker compose --env-file /dev/null exec -T backend python /qa/check_workflows.py
docker compose --env-file /dev/null restart backend
docker compose --env-file /dev/null up -d --no-build --wait --wait-timeout 180
docker compose --env-file /dev/null exec -T backend python /qa/check_workflows.py --verify-saved
docker compose --env-file /dev/null down --volumes --remove-orphans
```

The last command deletes **only this disposable project's data**. We never use
this overlay or cleanup command with the demo or measurement project. Each check
prints JSON with session IDs and saved-media hashes; the restart check compares
those hashes and verifies the interrupted-job failure. CI runs the same sequence
inside the existing container job and prints logs on failure.

### Local GPU Check

We start a separate normal stack using `docker-compose.app.yml` and
`docker-compose.gpu.yml`, without the test overlay. The
[Compose guide](compose_stack.md) covers verified weights and GPU prerequisites.
With that stack healthy on port 8087:

```bash
.venv/bin/python scripts/check_runtime_regression.py \
  --base-url http://127.0.0.1:8087 \
  --output data/output/quality-gpu-regression.json
cd frontend
STACK_BASE_URL=http://127.0.0.1:8087 \
  STACK_IMAGE=../data/runtime-regression/fixtures/roundabout_6.png npm run test:stack
```

We do not replace the baseline to make an update pass. The
[fixture attribution](../data/runtime-regression/README.md) and
[manifest](../data/runtime-regression/manifest.json) record the source licence,
hashes and the artificial video timeline. New browser tests use these same
tracked media. GitHub-hosted CI does not claim to run the GPU check.

## Merge Requirements

On 4 November 2026, with Ali's approval, we enabled required checks on `main`:
**Python quality checks**, **PostgreSQL integration tests**, **Frontend quality
checks**, and **Container build and runtime checks**. GitHub ties them to GitHub
Actions, requires the branch to be up to date and applies protection to
administrators too. Existing pull-request settings were retained.

We verified the settings through GitHub's
[branch protection API](https://docs.github.com/en/rest/branches/branch-protection).
The server-side setting is separate from the workflow file; renaming a CI job
requires updating its required-check name. The current setting can be inspected
with `gh api repos/AliCS-dev/traffic-crowd-monitoring-app/branches/main/protection`.

## Verification Record

The 4 November review added missing browser submission paths, real database
rollback cases and the controlled full-stack check. The existing application,
model profile, dependency versions and screenshot baselines are unchanged.

| Check | Local result on 4 November |
| --- | --- |
| Full Python suite, with PostgreSQL enabled | 634 passed on each of two consecutive runs, including 14 integration tests |
| Frontend unit tests | 115 passed on each of two runs |
| Desktop/mobile browser suite | 24 checks repeated twice: 48 passed, retries disabled |
| Controlled Compose image/video, saved media and restart recovery | Two cycles passed; completed assets kept their hashes and abandoned jobs became `worker_interrupted` |
| Real GPU regression | Five frames matched the unchanged baseline; no differences |
| Real GPU browser workflows | Four image/video checks passed across desktop and mobile |
| Static checks | Python lint/format/compilation and frontend lint/format/types/production build passed |
| GitHub branch protection | Four required checks, strict up-to-date mode and administrator enforcement read back successfully |

The runs used isolated `traffic-issue26` (controlled) and `traffic-issue26-gpu`
projects, plus a separate PostgreSQL test container. The real GPU outputs remain
local at `data/output/issue26-gpu-regression.json`; browser screenshots and traces
are under ignored `frontend/test-results/`. The two image browser checks each
returned 27 detections; video samples returned 21, 24 and 30. These are regression
observations, not reference counts or accuracy metrics. The controlled model
always returns one detection and is not used for these GPU checks.

The first new browser-test draft intercepted Vite source imports with an overly
broad API mock, then incorrectly checked the cleared native file input rather
than the retained application selection. We corrected the test setup/assertion
and verified resubmission sends the same file. We did not change the application,
increase timeouts, enable retries or update screenshots to obtain a pass.

Issue #79 still owns final latency/resource measurements, timed restart/outage
experiments, input decisions and the release freeze. Controlled tests and a few
repeated runs are useful regression evidence, not proof that every failure is
covered or that the application is production-ready.
