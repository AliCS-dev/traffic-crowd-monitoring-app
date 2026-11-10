# Backend Restart Measurements

[Results index](results_index.md) | [Warm measurements](system_measurements.md)

We measure a graceful backend restart, the first analysis request afterwards,
and whether a previously saved result still opens with unchanged media. This
adds a second measurement path for #79. It is not a final evaluation, a full
Compose startup measurement, or a database-outage experiment.

## What the Times Mean

| Record | Boundary |
| --- | --- |
| Restart to readiness | Immediately before `docker restart` to the first completed `/api/ready` response reporting ready through Nginx |
| Restart command | Time spent waiting for the Docker restart command; included in restart-to-readiness time |
| Cold-process request | First image/video POST after readiness to API completion, using the existing request timer |
| Saved recovery | Fetching an earlier result and its clean/annotated JPEGs, through hashing and comparison |

Restart timing includes graceful shutdown, process startup, proxy requests and
readiness polling. It is not just Python startup time. We record failed polls
and their timestamps. Readiness checks dependencies but does not load the
detector for inference; model loading and first-call work occur in the next
request. Stage logs retain their existing narrower timing boundaries.

Before each scenario, we create one saved reference session. Each trial then
restarts the backend, sends the first analysis request and checks that reference
session. Reference creation and saved recovery are outside the cold-request
timer. We compare a canonical JSON hash and all clean/annotated asset hashes,
not just an HTTP success code.

These are **cold-process runs, not cold-machine runs**. Docker does not clear
host caches. No earlier inference is sent by this runner after a restart; the
isolated stack must not receive other analysis requests during collection.
Resource samples cover the cold request and its evidence read, not the restart
window. They can miss peaks and include other GPU users.

## Isolated Run

The [measurement overlay](../../docker-compose.measurement.yml) labels only the
backend as disposable. The runner requires both that label and explicit
`--allow-backend-restart` consent. It checks the Compose backend service label,
pins the container ID and verifies that the image/source stay unchanged while
the process start time changes. Never apply this overlay to the demo or thesis
evidence database.

From the repository root, with Docker GPU support and the verified model present:

```bash
export POSTGRES_PASSWORD=local_restart_test_only
export BACKEND_IMAGE=traffic-restart-backend:local
export MEASUREMENT_FRONTEND_IMAGE=traffic-restart-frontend:local
export FRONTEND_PORT=8086
export APP_REVISION=$(git rev-parse HEAD)
export APP_SOURCE_DIRTY=true
export COMPOSE_PROJECT_NAME=traffic-restart-check
export COMPOSE_FILE=docker-compose.app.yml:docker-compose.gpu.yml:docker-compose.measurement.yml

docker compose --env-file /dev/null up -d --build --wait --wait-timeout 180
.venv/bin/python scripts/measure_system_restarts.py \
  --base-url http://127.0.0.1:8086 \
  --backend-container traffic-restart-check-backend-1 \
  --allow-backend-restart --repetitions 2 \
  --output-directory data/output/system-measurements/restart-check
```

The output directory must be new and port 8086 unused. This deliberately marks
the development build dirty; changing that flag does not create a release
freeze. The default is three restart trials per scenario. The command above
uses two for tooling verification, with 250 ms polling, a 180-second restart
deadline and one-second target resource sampling. The request deadline is
360 seconds. The scenario order and licensed fixture hashes come from
[system_workflows.json](../../configs/evaluation/system_workflows.json).

The runner writes `report.json`, `restarts.csv` and their hashes in `sha256.json`.
The JSON includes seeds, attempts, stage logs, readiness polls, resource samples,
saved-media hashes and source identities. Seeds are excluded from cold summaries.
Failures and missing evidence produce `incomplete` and a nonzero exit code;
later requests and restarts are not attempted. We inspect an interrupted run
before rerunning, since a timed-out job may still be running. A process kill may
leave the last checkpoint marked `in_progress` without final hashes.

After retaining the evidence, this removes only the disposable project above:

```bash
docker compose --env-file /dev/null down --volumes --remove-orphans
```

## Verification on 7 November

The [tracked record](../../data/evaluation/system_restart_verification.json)
retains the corrected run, original artifact hashes, the initial failure and
the separate GPU regression result. We reused the source-matching backend image
from the #26 checks, with an unchanged application and model. The runner tree
was dirty; the exact image, source and tool hashes are recorded.

The first attempt rejected the valid clean-image `/source` route in the
runner's URL allowlist. It stopped after one seed request and before any restart.
We corrected that route and the test fixture, then used a new output directory.
The incomplete attempt was not overwritten or counted as a successful trial.

The corrected run completed six restart trials and nine requests: three seeds
and two cold requests for each of I1, I2 and V1. All six saved-result checks
matched, every request had its expected stage records, and all 54 resource
readings were available. The unchanged five-frame GPU regression passed.

These values verify collection, **not final thesis performance**:

| Scenario | Trials | Median restart-to-ready (s) | Median cold API time (s) | Median saved recovery (s) |
| --- | ---: | ---: | ---: | ---: |
| I1, image with grid | 2 | 3.398 | 6.531 | 0.038 |
| I2, image without grid | 2 | 3.352 | 2.901 | 0.045 |
| V1, artificial three-frame video | 2 | 3.421 | 3.092 | 0.081 |

The I1 observations varied from 2.796 to 10.266 seconds; both remain in the
record. Two observations cannot establish typical or tail latency. The local
test suite finished before collection, but exclusive host/GPU use was not
established. The fixtures cover one scene group and an artificial video timeline.

The full local suite passed 650 tests, with 14 PostgreSQL tests skipped locally.
The 61 focused tests include the unchanged warm runner, restart failures,
changed identities, missing/changed media, unsafe asset URLs and partial reports.
CI runs the PostgreSQL integration suite separately. No application code,
dependency, model setting or regression baseline changed.

## Remaining Work

The [browser runner](browser_readiness.md) now covers decoded-scene readiness.
The [lifecycle runner](stack_lifecycle.md) now covers fresh-stack startup and
controlled idle service outages. Issue #79 still needs I3 preparation, the V2
media decision, final failure-scenario scope and an exact final run order.
We then freeze the evaluated version and collect the planned repetitions.
The native file-chooser MIME limitation remains tracked under #84. These records
do not improve the detector's failed accuracy gate or add dense-crowd support.
