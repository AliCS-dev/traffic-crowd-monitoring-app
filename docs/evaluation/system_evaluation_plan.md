# Final System Evaluation Plan

[Results index](results_index.md) | [Documentation index](../README.md)

**Prepared 28 October 2026. Status: preparation, not a completed evaluation.**

Issue #79 measures the application as a system. We are not selecting another
detector, reopening the historical held-out test, or turning successful requests
into evidence of detection accuracy. Issues #113-#115 remain deferred.

## Version and Freeze

The application candidate is commit `a229688b8858289ea740efe6433e72cef71bb88b`, merged through PR #155.
The interactive workspace and its corrected browser checks are included.
This identifies the starting version, not the final measured release.

Before final measurements, we need the #26 workflow coverage review, a tested
measurement runner, separate stage timers, and the media decision below.
Any required instrumentation changes produce a new candidate. We then record
one clean commit and immutable container image IDs before running the scenarios.
A later code, dependency, model or configuration change requires a new labelled
run; results from different candidates are not silently combined.

The freeze record will contain:

- Full application and runner commits, clean-tree state and backend source hash.
- Frontend/backend image IDs, PostgreSQL version and migration versions.
- Model profile, checkpoint and alert-rule hashes, with effective runtime settings.
- CPU, RAM, GPU/driver, Docker/WSL, browser and Python dependency versions.
- Input hashes, dimensions, codecs, sampling, grid settings and scenario order.
- Workload limits and polling/resource-sampling intervals, without credentials.

The current model is `yolo26m-visdrone-experimental-v1`: confidence 0.25,
inference size 1280, preprocessing scale 2, maximum 300 detections, float32,
and `cuda:0`. Its quality gate remains failed. The exact profile is
[tracked here](../../configs/runtime/yolo26m_visdrone.json); we record its hash
again at the freeze rather than assuming the present settings cannot change.

## Media and Scenarios

We can measure software behavior without drawing new reference annotations.
The initial media choices are fixed by existing source records, not selected
after comparing timings. The two roundabout images belong to one scene group;
they are not independent evidence of broad aerial-scene performance.

| ID | Input and settings | Purpose |
| --- | --- | --- |
| I1 | Tracked `roundabout_6.png`, 2-by-3 grid | Baseline image request, stored totals, assets and history |
| I2 | Tracked `roundabout_29.png`, no grid | Image path without grid creation |
| I3 | Validation image `Renai_Dunhua_traffic_circle_202006.jpg`, 2-by-3 grid | Larger aerial image from a second scene group |
| V1 | Tracked `roundabout_sequence.avi`, one-second sampling, 2-by-3 grid | Three-frame job, decoding, storage and navigation |
| V2 | Licensed natural-motion video, not yet selected | Longer decoding and job progress; final input decision remains open |

I1, I2 and V1 use the attributed CC BY 4.0
[runtime fixtures](../../data/runtime-regression/README.md); their exact hashes
are in the [manifest](../../data/runtime-regression/manifest.json). V1 repeats
still frames on an artificial three-second timeline. It is a deterministic
workflow fixture, not evidence about motion tracking or natural video behavior.

I3 is MiNe's daytime Ren'ai image, recorded as validation material and CC BY 2.0
in [downloads.csv](../../data/evaluation/downloads.csv) and
[manifest.csv](../../data/evaluation/manifest.csv). Its verified SHA-256 is
`88d8ea239eeee2e6ad1e19f84fd2dff11fdd78845c1ce00611270ae6a2151dc9`.
The local file exists, but remains outside Git. Any published figure retains
the source attribution and describes the application's modifications.

We do not reuse the Jane Byrne video here: its sampled images belong to the
historical held-out group. We also do not assume that an arbitrary local
`test_video.mp4` has a documented publication licence. Before final collection,
V2 needs an existing non-held-out source with recorded permissions, hash, codec,
duration and sampling settings. Otherwise we explicitly narrow the final video
claim to the controlled fixture and record the scope decision. We do not
silently substitute a clip or start another annotation campaign.

## Measurement Boundaries

| Measure | Boundary and interpretation | Current support |
| --- | --- | --- |
| API image completion | Client monotonic time before multipart POST to complete response body | Existing smoke runner provides an initial version |
| API video completion | Before multipart POST to first observed completed job status | Existing smoke runner; includes polling delay |
| Inference service time | Detector call after acquiring its shared lock to completed results, with CUDA completion accounted for | Separate timer still needed |
| Persistence time | Entry to result-persistence operation through successful transaction commit | Separate timer still needed |
| Video queue wait | Accepted job to worker start | Explicit correlation/timing still needed |
| Browser result readiness | Submit action to decoded clean image and visible overlays | Browser runner needs an explicit timing record |
| Throughput | Successful images or sampled frames divided by wall time in a declared sequential batch | Runner extension needed; not source-video FPS |
| Resources | Timestamped backend cgroup memory and whole-device GPU memory samples | Existing sampler; samples can miss peaks |
| Startup/recovery | Container start/restart to API readiness, followed by reopening a saved session | Automated timing and result record still needed |

The current JSON logs contain whole-request and workflow durations, not the
separate inference and persistence values. We must not infer those stages by
subtracting unrelated timings or describe a total request as pure inference.
No new database table, distributed tracing system or external monitoring service
is required for these measurements; structured timing records are sufficient.

## Repetitions and Reporting

The runner will execute one request at a time on an isolated Compose project.
No training or unrelated GPU work runs during the measurement. We record idle
resource use and background workload, rather than claiming exclusive GPU use
when it cannot be verified.

For each accepted media scenario, the planned schedule is three backend-restart
runs with the first request reported separately, followed by one unmeasured
warm-up and ten measured warm requests. Image scenarios run I1, I2, I3, then
video scenarios V1 and the resolved V2. Each cold run waits for readiness and
performs no earlier inference. Restarting the backend does not clear operating
system caches, so these are cold-process/model runs, not cold-machine runs.

We retain every raw observation and report sample count, median, minimum,
maximum and a clearly defined empirical p95 (nearest-rank, rank ceil(0.95*n)).
With only ten warm observations that p95 is the maximum; we state that small
sample limitation rather than presenting it as a precise population estimate.
The runner will poll video status every 250 ms and record that interval.
Resource samples are timestamped at a target interval of one second, with
missing readings and actual gaps retained.

Failures remain rows in the result table with their scenario, request/session
IDs and failure code. They are not removed from the success-rate denominator or
quietly replaced by a successful rerun. The initial experiment is descriptive:
we do not invent performance pass thresholds after seeing its timings.
The earlier #80 warning budgets remain a separate dated smoke result and are
not automatically transferred to larger inputs.

## Correctness and Recovery Checks

Alongside timing, we verify count consistency, saved metadata, both image
variants, grid inspection, display filters, sampled-frame navigation and history.
Threshold alerts are checked against configured rule semantics, not declared
to be real congestion or emergencies. Dense-crowd status must remain unsupported
with a null count.

The #26 review maps each workflow to existing tests and records actual gaps.
Its starting references are the API/service tests, PostgreSQL integration tests,
`frontend/e2e/`, `frontend/stack-tests/` and Compose CI checks.
Invalid uploads, out-of-range options, unavailable assets, admission limits,
database failure and interrupted-video recovery need explicit coverage entries.
Controlled detectors are appropriate for those correctness checks, but their
timings are not mixed with real-GPU measurements.

Destructive recovery experiments use a separate disposable stack and database,
never the demonstration or thesis evidence database. We retain the scenario,
expected response, actual response and recovery outcome, including unsuccessful
cases. A database outage cannot be reported as successfully recorded failure
unless the stored record is actually verified after recovery.

## Evidence and Next Work

The existing commands in the [workspace report](../scene_workspace_verification.md)
and [operations guide](../operational_safeguards.md) reproduce regression and
smoke checks, not this full protocol. There is no final runner command yet.

The next implementation is a small measurement runner and structured stage
timers, with tests for timing boundaries, failed runs and provenance mismatch.
Before running it, we resolve V2, complete the #26 matrix and commit the freeze
record. This plan alone does not close #26 or #79.

We will retain raw JSON/CSV records, the input and runtime manifest, the exact
command, run ID and output hashes. The final report will link compact tracked
evidence and reproducible tables/plots from this results index. Large media and
generated outputs stay outside Git. System timing and workflow results will
have their own section, separate from the unchanged historical model scores.
