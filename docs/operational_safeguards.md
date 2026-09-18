# Operational Safeguards

Issue #80 keeps the local demonstration within defined workload limits. We retain
one API process, one shared detector and one video worker by default. This is not
a distributed queue or an internet-facing service.

## Limits

| Setting | Default | Purpose |
| --- | ---: | --- |
| `API_MAX_INFLIGHT_ANALYSES` | 3 | Images and queued/running videos share admission slots |
| `API_MAX_VIDEO_DURATION_SECONDS` | 300 | Reject long videos before job creation |
| `API_MAX_VIDEO_SOURCE_FRAMES` | 36,000 | Bound decoding even when sampling is sparse |
| `API_MAX_SAMPLED_FRAMES` | 300 | Bound retained results and saved frame images |
| `API_MAX_VIDEO_DETECTION_RECORDS` | 100,000 | Bound detection records retained until commit |
| `API_MAX_PROCESSED_PIXELS` | 40,000,000 | Bound frame/image size after profile scaling |
| `API_MIN_SAMPLING_INTERVAL_SECONDS` | 0.25 | Prevent excessively dense requested sampling |
| `API_MAX_QUEUE_SECONDS` | 60 | Reject stale work when a worker picks it up |
| `API_MAX_PROCESSING_SECONDS` | 300 | Cooperative processing deadline |

The existing byte limits, input-pixel checks and maximum 20-by-20 grid remain.
Admission happens before service-level decoding/storage; FastAPI has already
parsed multipart uploads at that point. The container accepts at most 16
concurrent connections/tasks and Nginx caps request bodies at 512 MiB. These
are local-demo bounds, not denial-of-service protection. The API's capabilities
endpoint publishes the analysis limits and the frontend uses its sampling floor.

An exhausted analysis budget returns HTTP 503 with `analysis_busy` and
`Retry-After: 5`. An image deadline returns 504. Video failures retain a generic
public message and a specific code such as `video_queue_timeout`,
`video_processing_timeout`, `video_limit_exceeded` or `worker_interrupted`.
Failed partial outputs are removed; the original failed-video input is retained
because its source record remains useful for diagnosis.

## Deadlines And Recovery

We check video deadlines before and after frame reads, including unsampled
frames, and between inference/storage operations. Shutdown signals the worker
to stop at those checkpoints and marks pending jobs failed. A thread cannot
safely cancel an in-progress native decoder or CUDA call. A hung native operation
therefore requires container restart; Compose allows 40 seconds for stopping.
On startup, existing recovery marks abandoned queued/processing jobs failed.
The runtime remains one API process; starting independent workers would require
a different job-ownership and admission design.

Compose bounds database connection establishment to five seconds, statements to
30 seconds and lock waits to five seconds. Non-container runs can use the same
`PGCONNECT_TIMEOUT` and `PGOPTIONS` settings. A filesystem or database outage
can still prevent failure recording; recovery runs at the next successful startup.

The [Compose guide](compose_stack.md) covers stale Docker Desktop/WSL model
mounts. We check `/api/ready`, not only the frontend's `/healthz`, and recreate
the backend with the same project/environment when its mount is stale. A new
model-volume system is not necessary for this local recovery procedure.

## Diagnostics

Each request receives a server-generated `X-Request-ID`. Application JSON logs
include that ID, event, elapsed duration and session ID where one exists. A video
work item carries the submitting request ID into its worker thread. Startup logs
record limits and the selected device. Exception types and failure codes are
logged without serializing credentials or returning native exception text to
clients. Access logs remain separate from application events. Proxy-generated
errors and requests rejected by Uvicorn before reaching the app do not have an
application request ID.

## Media Retention

Cleanup defaults to a dry run and never deletes sessions or database-referenced
media. It selects only unreferenced UUID-named files older than seven days in the
four API media directories, including abandoned `.part` uploads. It skips
symlinks, subdirectories, handwritten filenames and recent files. References are
also compared by generated ID so a container backup does not make its media look
unreferenced merely because host paths differ.

We stop all API and CLI writers before cleanup. API instances hold a PostgreSQL
shared advisory lock for their lifetime; cleanup requires its exclusive variant
and refuses to run with unfinished video jobs or an unavailable database. This
is a second guard, not permission to run maintenance alongside other writers.
After a database restart, session locks are lost, so stopping writers remains
mandatory. Saved thesis results are retained indefinitely; deletion of stored
sessions is deliberately outside this command.

For the isolated GPU verification stack:

```bash
docker compose -p traffic-stack-check --env-file .env.example -f docker-compose.app.yml -f docker-compose.gpu.yml stop backend
docker compose -p traffic-stack-check --env-file .env.example -f docker-compose.app.yml -f docker-compose.gpu.yml run --rm --no-deps backend python scripts/cleanup_media.py --older-than-days 7
# Only after reviewing the dry-run list:
docker compose -p traffic-stack-check --env-file .env.example -f docker-compose.app.yml -f docker-compose.gpu.yml run --rm --no-deps backend python scripts/cleanup_media.py --older-than-days 7 --apply
docker compose -p traffic-stack-check --env-file .env.example -f docker-compose.app.yml -f docker-compose.gpu.yml up -d --wait backend
```

The normal project uses its own project name and environment file. We do not
run cleanup against a thesis database just to demonstrate that deletion works.

## Preliminary Performance Budgets

These warning budgets were declared before the issue #80 measurement. We use
the existing sample JPG and short test MP4, a 2-by-3 grid, four image submissions
(first separately, then three warm samples), and video sampling every four
seconds. Measurements include upload and database work through the frontend
proxy; they are not pure inference latency.

| Measurement | Maximum before warning |
| --- | ---: |
| First image upload-to-result | 60 seconds |
| Warm image median | 10 seconds |
| Short video upload-to-completion | 120 seconds |
| Sampled backend cgroup memory | 4,096 MiB |
| Sampled whole-device GPU memory | 6,144 MiB |

The script reports video sampled frames per elapsed second. Resource samples
are spaced approximately one second apart and can miss allocation peaks. GPU
readings include other applications. Missing resource evidence is `unavailable`,
not a pass. First-request timing is only a cold-model measurement when the
backend was freshly restarted and no inference preceded it.

```bash
.venv/bin/python scripts/measure_system_budget.py --image data/input/sample_image.jpg --video data/input/test_video.mp4 --backend-container traffic-stack-check-backend-1 --output data/output/system-budget.json
```

The command creates five test sessions, so it belongs on an isolated stack.
It records media hashes, application commit, dirty-tree state, backend image,
capabilities, per-request timings and budget outcomes. It exits nonzero on a
warning or unavailable resource evidence. Final representative measurements,
broader scenarios and release-frozen evidence remain issue #79.

## Verification Record: 18 September 2026

We measured commit `6a518673d22c71a9536f1176cf2673c1f328bcc4` with a clean
working tree on the isolated `traffic-stack-check` GPU stack. The backend was
recreated before inference. The device was an RTX 5060 Laptop GPU with 8,151 MiB
reported memory and driver 616.92. We used the existing experimental VisDrone
YOLO26m profile; the model and its failed quality-gate status did not change.

| Measurement | Observed | Budget | Outcome |
| --- | ---: | ---: | --- |
| First image upload-to-result | 21.74 s | 60 s | Pass |
| Warm image median, three requests | 0.143 s | 10 s | Pass |
| Short video upload-to-completion | 4.27 s | 120 s | Pass |
| Sampled backend cgroup memory, maximum | 2,965.11 MiB | 4,096 MiB | Pass |
| Sampled whole-device GPU memory, maximum | 1,085 MiB | 6,144 MiB | Pass |

The video produced three sampled frames, equivalent to 0.703 sampled frames per
elapsed second including upload, decoding, storage and polling. This is not
camera FPS or inference-only throughput. We collected 22 samples per resource
with no sampling errors. The compact [measurement record](../data/evaluation/operational_budget.json)
contains exact timings, media hashes, request/session IDs, capabilities and the
backend image digest. This small single-run check is not a load test or final
system evaluation, and sampled memory is not a guaranteed peak.

Local verification passed 400 Python tests, 10 PostgreSQL integration tests,
104 frontend unit tests, eight mocked browser scenarios and two live Compose
browser workflows. The ordinary Python run skips the 10 integration tests;
we ran them separately against a disposable database. Ruff, frontend lint,
formatting, type checking and container builds passed. Desktop and 320-pixel
mobile screenshots showed loaded result images and no horizontal overflow.
Both live image workflows retained 94 detections and the same annotated-asset
hash as the preceding runtime check; this is regression evidence, not accuracy.

Cleanup was refused with the API running. With the API stopped, its dry run
found no expired orphan files. Automated tests exercise deletion only in
temporary directories and preserve database-referenced media. We restarted the
API afterward; existing image/video results remained available.

Processing deadlines are cooperative and separate from proxy request timeouts.
In particular, a synchronous image can spend time waiting before processing;
the proxy may time out first. These limits do not promise hard cancellation of
native operations or total request latency. Saved records and their media have
no automatic expiry, so retention does not impose a total disk quota.

## References

The timeout boundary follows Python's [executor shutdown behavior](https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.Executor.shutdown).
Maintenance uses PostgreSQL's [session-level advisory locks](https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS).
