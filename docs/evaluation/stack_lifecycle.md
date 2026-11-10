# Stack Startup and Recovery

[Results index](results_index.md) | [System evaluation plan](system_evaluation_plan.md)

We checked fresh-stack startup and two controlled service outages on 10 November
2026. The runner starts PostgreSQL, migrations, FastAPI and Nginx together, then
checks whether saved results survive a database outage and a backend outage.
It also submits new analyses after each recovery. This is development verification
for #79, not the final repeated system evaluation.

## What We Measure

| Record | Timer boundary |
| --- | --- |
| Fresh-stack readiness | Immediately before `docker compose up -d --no-build --pull never` to the first completed ready response through Nginx |
| Compose command | The Compose invocation itself, included in fresh-stack readiness |
| Service stop | The explicit `docker stop --time 40` command |
| Service recovery | Immediately before `docker start` to the first ready response through Nginx |
| Saved-result recovery | Fetching and comparing a previously saved result and its clean/annotated JPEG hashes |
| New analysis | The existing API request timer, reported separately from service readiness |

The fresh project has no containers, network or data volumes before the run.
Startup includes their creation, database initialization, migrations and Compose
dependency waits. Images must already exist locally: downloads and builds are
excluded. Readiness checks dependencies but does not perform first inference.
The subsequent frontend-shell and container checks are outside the readiness
timer and must also pass. This is not browser rendering time.

Recovery timing excludes the earlier stop command and outage observations.
It is not total user-visible downtime or time to load the detector. Readiness
polling has a target interval of 250 ms; actual elapsed times and unsuccessful
polls remain in the report. The default readiness deadline is 180 seconds.

## Scenarios and Expected Responses

We first submit I1, I2 and V1 from the existing
[scenario file](../../configs/evaluation/system_workflows.json), then retain
their result and media hashes. These are the licensed
[runtime fixtures](../../data/runtime-regression/README.md), not new accuracy
material. V1 repeats still images on an artificial timeline.

With those jobs completed, we stop PostgreSQL, observe the responses below,
start it again and wait for readiness. We compare all three saved results and
submit I1, I2 and V1 again. We repeat that sequence for the backend alone.

| Endpoint | PostgreSQL stopped | Backend stopped |
| --- | --- | --- |
| Nginx `/healthz` | 200 | 200 |
| `/workspace` application shell | 200, root element present | 200, root element present |
| `/api/health` | 200 | 502 or 504 |
| `/api/ready` | 503, database not ready | 502 or 504 |
| Saved `/api/analyses/{id}` | 500, generic `internal_error` | 502 or 504 |

Nginx may time out while connecting to a stopped backend (504), or report an
unavailable upstream (502). We retain each actual code and response time; these
are not interchangeable with a successful response. A database failure does not
currently have a dedicated error code on the saved-result route. The generic
500 is the existing API behavior, not a claim of ideal error presentation.

These are **idle service outages**, not interrupted in-flight videos, network
partitions, disk corruption or concurrent-user tests. No analysis is submitted
while a service is deliberately stopped, and we do not claim a stored failed
job for those read-only probes. Browser error states are covered separately by
the [workflow tests](../testing.md). Maintenance is also separate: PostgreSQL
session locks are lost on database restart, so the existing instruction to
[stop all writers before media cleanup](../operational_safeguards.md) still applies.

## Reproduction

The runner needs Docker GPU support, the verified model, the repository's Python
environment and already-built images. The [Compose guide](../compose_stack.md)
covers image builds. The command below reuses the local images used for our #26
checks; other builds need their own recorded image names and evidence.

From the repository root, with port 8086 unused:

```bash
.venv/bin/python scripts/measure_stack_lifecycle.py \
  --project traffic-measure-lifecycle-check \
  --port 8086 \
  --backend-image traffic-issue26-backend:local \
  --frontend-image traffic-issue26-frontend:local \
  --allow-stack-interruption \
  --output-directory data/output/system-measurements/lifecycle-check
```

Both the project and output directory must be new. Project names must start
with `traffic-measure-`. The runner refuses existing containers, volumes and
networks for that project. It uses the fixed measurement Compose files, ignores
`.env` and application overrides, and supplies a random disposable database
password that is not written to the report. The frontend binds only to loopback.

Before any interruption, it checks the full stack, image IDs, measurement label,
container IDs and project-specific mounts. Stop/start commands use immutable
container IDs. Restoration is attempted even when a stop or observation fails.
Failed checks stop further analyses; they are not automatically retried.
Source, input, tool, model and container identities are checked during the run.

The output contains `report.json`, `lifecycle.csv` and `sha256.json`. Reports
retain startup observations, outage responses, readiness polls, request IDs,
saved-media hashes, runtime details and failures. Each invocation performs one
startup and one outage per service; there is no implicit repetition or warm-up
exclusion. The isolated stack remains running for inspection. An abrupt kill
may leave an incomplete checkpoint or a stopped service; we inspect the project
before another run. The runner never deletes volumes automatically.

Once evidence is retained, this removes only the example project:

```bash
POSTGRES_PASSWORD=unused_for_cleanup docker compose --env-file /dev/null \
  -p traffic-measure-lifecycle-check \
  -f docker-compose.app.yml -f docker-compose.gpu.yml \
  -f docker-compose.measurement.yml down --volumes --remove-orphans
```

The dummy value only lets Compose parse the configuration for removal; it does
not change the running database password. It is not an application credential.

## Verification on 10 November

The [tracked record](../../data/evaluation/stack_lifecycle_verification.json)
retains both development runs and hashes of their full local artifacts. Repeated
dependency lists are represented by runtime references and dependency hashes;
the separate GPU regression retains its complete runtime versions. Repeated
saved-result evidence is summarized by explicit equality checks against the
recorded baselines. The full reports remain under
`data/output/system-measurements/lifecycle-verification-2026-11-10*`.

The first run stopped after the backend outage because the runner accepted only
502, while Nginx returned 504, 504 and 502. Restoration still succeeded. We kept
that incomplete report, corrected the assertion, added tests and used a new
project and empty volumes for the second run. We did not change Nginx, the API,
model settings or a regression baseline to obtain a pass.

The corrected run completed nine analyses, six saved-result comparisons and
both controlled outages. All saved JSON and clean/annotated JPEG hashes matched.
The unchanged five-frame GPU regression passed after recovery.

These are **single observations for tooling verification**, not medians or final
performance estimates:

| Measurement | Seconds |
| --- | ---: |
| Fresh-stack readiness, local images and empty database | 12.9459 |
| PostgreSQL start to readiness | 0.4841 |
| Backend start to readiness | 1.9443 |
| First I1 analysis after fresh startup | 16.4070 |
| First I1 analysis after backend recovery | 7.8300 |

The first-inference times show why readiness cannot substitute for analysis
latency. Host caches were not cleared, and exclusive host/GPU use was not
established. The local test suite finished before collection. Runtime images
were reused with a source-matching backend; the runner tree was dirty, and no
release was frozen. These observations are not pooled with earlier warm,
restart or browser runs.

All 110 focused measurement tests passed, including 49 new lifecycle tests.
The full local Python suite passed 699 tests, with 14 PostgreSQL integration
tests skipped locally; CI runs those separately. Ruff and formatting passed.

## Remaining Work

The final protocol still needs I3 preparation, the V2 media or scope decision,
the exact combined run order and release freeze. Any active-job recovery claims
need their own declared experiment; these idle-outage checks do not establish
them. We then collect the agreed repetitions on the frozen version. Issue #79
remains open, and detector-quality and dense-crowd limitations are unchanged.
