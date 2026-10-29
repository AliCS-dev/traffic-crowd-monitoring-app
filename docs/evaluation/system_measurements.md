# Measuring Application Workflows

[Results index](results_index.md) | [Final evaluation plan](system_evaluation_plan.md)

We now have a runner for repeated image and video requests, with separate
inference, result-saving and video queue timings. We checked it on 29 October
2026. This is the measurement tooling for #79, not a completed final evaluation.
The model, its failed quality gate and the unsupported dense-crowd result have
not changed.

## What We Measure

| Record | Boundary |
| --- | --- |
| Image API time | Immediately before the multipart POST to receipt of the response body |
| Video API time | Before the multipart POST to receipt of the first job response showing completion; includes polling delay |
| Inference | Inside the shared detector lock, after prior CUDA work completes, through the detector call and CUDA completion |
| Image persistence | Entry to the result repository function through transaction commit and return |
| Video persistence | Entry to the final result-saving function through commit and return; not earlier job creation or progress updates |
| Video queue | Submission to the executor, after job creation commits, to worker entry |
| Batch throughput | Successfully completed sampled frames divided by the sequential measured batch's wall time |
| Resources | Timestamped backend cgroup memory and whole-device GPU memory samples |

Inference here means the detector service call, including its internal input
handling and result construction. It is not pure GPU kernel time. Loading the
model before that call and waiting for the shared lock are excluded. Explicit
CPU and CUDA devices are used by the API; CUDA synchronization and timing logs
add some overhead. We record that instrumented version as part of the candidate.

Persistence includes connection opening, validation and commit. Failed operations
have a failed stage record rather than a successful duration. Video queue time
is not upload time. The structured records carry the original upload request ID,
including work performed in the video thread. No table or API response changed.

The runner reads saved results and checks provenance after the API timer stops.
Batch throughput includes those reads, checks and intermediate report writes,
but excludes the warm-up. It is not camera FPS or simultaneous-user capacity.
Resource samples can miss peaks, and GPU readings include other applications.
Each reading has start/end timestamps, so slow or missing readings remain visible.

## Running the Check

We use a separate Compose project with its own database and media volumes. The
following commands assume Docker Desktop's WSL integration is running and the
existing `.env` and model checkpoint are available. Port 8084 must be free.

```bash
export BACKEND_IMAGE=traffic-issue79-backend:local
export FRONTEND_PORT=8084
export APP_REVISION=$(git rev-parse HEAD)
export APP_SOURCE_DIRTY=true

docker compose -p traffic-issue79 -f docker-compose.app.yml -f docker-compose.gpu.yml build backend
docker compose -p traffic-issue79 -f docker-compose.app.yml -f docker-compose.gpu.yml up -d --build

.venv/bin/python scripts/measure_system_workflows.py \
  --base-url http://127.0.0.1:8084 \
  --backend-container traffic-issue79-backend-1 \
  --repetitions 2 \
  --output-directory data/output/system-measurements/development-check
```

We deliberately label this development build as dirty; it is not a release
freeze. The runner also records the actual local Git state. A frozen build later
needs a genuinely clean commit, not just a changed environment value.

The [scenario file](../../configs/evaluation/system_workflows.json) runs I1, I2
and V1 in that order. Their licensed inputs and hashes come from the existing
[runtime fixtures](../../data/runtime-regression/README.md). I2 has no grid.
V1 repeats still images; it is not natural-motion evidence. I3 and V2 are not
silently replaced by these fixtures.

Each scenario gets one warm-up followed by the requested number of measured
requests. The default is ten repetitions; the command above uses two to check
the tooling. Warm-up rows remain in the report but are excluded from summaries.
No container restart occurs, so none of these rows is labelled a cold run.

The output directory must be new. We retain:

- `report.json`: settings, input hashes, backend identity, model/runtime metadata,
  every request, correlated stage records, resource samples and summaries.
- `requests.csv`: one row per request, including failures and unavailable values.
- `sha256.json`: hashes of the JSON and CSV files.

`recorded` means the requested run has its timing and resource evidence. It does
not mean acceptable performance or accuracy. `incomplete` returns a nonzero exit
code. A failed request remains in the file and stops further submissions, because
a timed-out video may still be processing. Unattempted requests are not invented
as failures; the planned repetitions and actual attempts are both recorded.

We check input hashes and the running backend's source hash before requests,
match saved-session provenance to the selected container, compare model settings,
and check container identity again afterwards. Missing or duplicate stage records
are unavailable, not zero. Reports are checkpointed after each returned request;
an abrupt process kill can leave an `in_progress` file without final logs or hashes.
After an interruption, we check that the old job has finished before another run.

Summaries retain the attempted/completed/failed counts and report sample count,
median, minimum, maximum and nearest-rank p95. With ten observations p95 is the
maximum, not a precise estimate of the population's tail latency.

## Verification on 29 October

The [tracked verification record](../../data/evaluation/system_measurement_verification.json)
contains all nine request observations, stage events, resource samples, runtime
details and hashes of the original local artifacts. There were three warm-ups
and six measured requests, with complete timing evidence and no request failures.
We also reran the unchanged five-frame detector regression: no differences.

This small development run was made from a dirty working tree with recorded
source and runner hashes. The final verification overlapped the local test run;
we do not claim an exclusive measurement workload. Its timings establish that
we can collect the intended
records. They are not the final thesis performance table, an accuracy result,
or evidence that our input set represents every traffic scene.

The automated checks cover CUDA timing boundaries, both repositories' commit
failures, thread correlation, polling deadlines, partial reports, source/profile
mismatches, missing logs, resource errors and percentile calculation. Controlled
detectors and mocked HTTP responses test correctness, not real inference speed.
All 630 Python tests passed, including the 12 PostgreSQL integration checks.

## What Remains

Before final collection, we still need the #26 workflow coverage review, the
natural-motion video decision, I3 preparation, backend-restart and recovery
measurements, browser readiness timing, and the complete hardware/configuration
freeze. The runner currently handles the warm API portion, not that whole
protocol. We do not reopen the held-out accuracy test or assign new annotation
work as part of this step.
