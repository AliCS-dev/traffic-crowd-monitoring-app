# Final System Evaluation Plan

[Results index](results_index.md) | [Documentation index](../README.md)

**Prepared 28 October 2026. Status: preparation, not a completed evaluation.**

On 29 October we added and verified [warm workflow measurements](system_measurements.md)
and structured stage timers. The complete protocol below still needs the
remaining coverage, media, measurement paths and release freeze.

The 4 November [workflow coverage review](../testing.md) maps implemented paths
to tests and records the repeated software checks. It includes controlled
Compose recovery, not the timed real-runtime recovery experiment below.

On 7 November, #26 was merged through PR #161. The separate
[restart runner](system_restarts.md) now records graceful backend restart timing,
cold-process requests and saved-result integrity, verified on the real GPU stack.
This is development evidence, not the release freeze or final collection.

On 9 November, the [browser runner](browser_readiness.md) added submission-to-scene
timing, checked against saved image/video results and served frontend hashes.
Its two-sample verification remains separate from final performance collection.

On 10 November, the [lifecycle runner](stack_lifecycle.md) added fresh-stack
startup and controlled idle PostgreSQL/backend outages, with saved-result
integrity and new analyses after recovery. Its single-run verification and
initial incomplete attempt are retained separately from final collection.

On 12 November, we prepared the separate five-scenario
[candidate inputs](system_scenarios.md), selected the documented V2 source and
fixed the collection order below. Ali approved limiting live recovery to idle
service outages. These decisions do not freeze the application version or
complete the final measurements.

Issue #79 measures the application as a system. We are not selecting another
detector, reopening the historical held-out test, or turning successful requests
into evidence of detection accuracy. Issues #113-#115 remain deferred.

## Version and Freeze

The [13 November dependency review](release_dependency_review.md) records the
agreed boundary: retain the merged versions and defer PRs #153, #154 and #163,
unless a necessary security fix changes that decision. Post-update compatibility
checks passed; the full software gate and clean freeze record still precede
final collection.

The application candidate is commit `a229688b8858289ea740efe6433e72cef71bb88b`, merged through PR #155.
The interactive workspace and its corrected browser checks are included.
This identifies the starting version, not the final measured release.

Before final measurements, we need verified candidate-input compatibility and
release dependency decisions, with the #26 software gate passing on the candidate.
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
| V2 | Pexels highway clip 30106869, two-second sampling, 2-by-3 grid | Portrait 4K input, natural traffic motion, longer decoding and job progress |

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
`test_video.mp4` has a documented publication licence. Ali confirmed that its
original link is unavailable, so it remains excluded. V2 is now the unchanged
publisher download of David Pickup's daytime highway clip, under the Pexels
License. Its [source record](../../data/evaluation/system_scenario_sources.json)
contains the licence links, checksum, decoded metadata and redistribution limits.
It is a system-workflow input without reference labels, not new accuracy evidence.
The old three-scenario config remains unchanged for earlier runs; the five-input
[candidate config](../../configs/evaluation/system_workflows_candidate.json)
must be supplied explicitly with `--scenarios`.

## Measurement Boundaries

| Measure | Boundary and interpretation | Current support |
| --- | --- | --- |
| API image completion | Client monotonic time before multipart POST to complete response body | Warm runner implemented and verified |
| API video completion | Before multipart POST to first observed completed job status | Warm runner; includes polling delay |
| Inference service time | Detector call after acquiring its shared lock to completed results, with CUDA completion accounted for | Request-correlated stage log |
| Persistence time | Entry to result-persistence operation through successful transaction commit | Request-correlated stage log; video progress writes excluded |
| Video queue wait | Submission to executor after job creation commits, to worker entry | Request-correlated stage log |
| Browser result readiness | Captured submit click to decoded image and stable overlay layout; not physical paint or guaranteed viewport visibility | Browser runner implemented and verified; first sampled frame for video |
| Throughput | Successful images or sampled frames divided by wall time in a declared sequential batch | Warm batch recorded, including evidence reads; not source-video FPS |
| Resources | Timestamped backend cgroup memory and whole-device GPU memory samples | Runner records reading times/errors; samples can miss peaks |
| Startup/recovery | Compose startup or service start to API readiness, with saved-result checks afterwards | Backend restart, fresh-stack startup and idle PostgreSQL/backend outage runners verified; active-job crash behavior is not established by these timings |

The JSON logs now contain separate inference, persistence and queue records as
well as the existing whole-request and workflow durations. We do not infer those
stages by subtraction or describe a total request as pure inference.
No new database table, distributed tracing system or external monitoring service
is required for these measurements; structured timing records are sufficient.

## Repetitions and Reporting

The runner will execute one request at a time on an isolated Compose project.
No training or unrelated GPU work runs during the measurement. We record idle
resource use and background workload, rather than claiming exclusive GPU use
when it cannot be verified.

The planned schedule is three backend-restart runs per scenario with the first
request reported separately, followed by a warm phase with one excluded
warm-up and ten measured requests per scenario. Within each phase, scenarios
run I1, I2, I3, V1, V2. Each cold run waits for readiness and
performs no earlier inference. Restarting the backend does not clear operating
system caches, so these are cold-process/model runs, not cold-machine runs.

The exact phase order, declared before final collection, is:

1. Finish the software gate and dependency decisions, then commit the freeze
   record. No test suite or regression run overlaps final collection. Record
   background work and idle backend/GPU memory before each phase.
2. Run the lifecycle runner three times, each with a fresh project and empty
   volumes. Each invocation seeds all five scenarios, stops/starts PostgreSQL,
   checks saved results and runs all five again, then does the same for the
   backend. Retain evidence before removing that invocation's project. These
   are three startup observations, three outages per service and 45 analyses;
   they are not included in warm or cold-request summaries.
3. Start a separate request-measurement project. Run the restart runner with
   three repetitions: one seed then three restart/first-request trials for I1,
   followed by the same for I2, I3, V1 and V2 (20 analyses total).
4. On that running project, execute the warm runner with ten repetitions:
   one warm-up and ten measured requests for each scenario (55 analyses).
5. On the same project, run browser measurements at 1440 by 1000 first, then
   320 by 900. Within each viewport, use the same scenario order, one warm-up
   and ten measured submissions per scenario (110 analyses). Each submission
   uses a fresh browser context. The backend stays warm; these are not mobile
   hardware benchmarks.
6. Check retained reports, identities, failures and output hashes, then remove
   only the disposable projects. Produce separate lifecycle, cold API, warm API
   and browser tables. Do not pool the phases or the different inputs.

The planned total is 230 analyses, including seeds and warm-ups. The unchanged
V2 source is about 352 MiB, so repeated uploads alone may retain roughly 16 GiB,
before generated assets. We check available space before collection and retain
the evidence before cleanup. This is a sequential, fixed-order experiment;
cache, temperature, order and database-growth effects remain limitations.

We retain every raw observation and report sample count, median, minimum,
maximum and a clearly defined empirical p95 (nearest-rank, rank ceil(0.95*n)).
With only ten warm observations that p95 is the maximum; we state that small
sample limitation rather than presenting it as a precise population estimate.
The API runner will poll video status every 250 ms and record that interval.
The browser runner instead retains the application's one-second polling interval;
its timings include that delay and are reported separately from API timings.
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

On 12 November Ali approved the bounded recovery scope: timed live experiments
cover idle database/backend outages only. Interrupted-video behavior remains
supported by the controlled tests in the #26 coverage matrix, not a real-GPU
mid-job crash experiment. We make no measured crash-recovery-time claim for an
active video, and do not describe controlled-detector tests as production proof.

## Evidence and Next Work

The existing commands in the [workspace report](../scene_workspace_verification.md)
and [operations guide](../operational_safeguards.md) reproduce regression and
smoke checks, not this full protocol. The [measurement guide](system_measurements.md)
now provides the warm runner command and its development verification record.

The warm runner and stage timers have tests for timing boundaries, failed runs
and provenance mismatch. The separate restart runner now covers cold-process
requests and saved-result recovery. The browser runner now records decoded-scene
readiness in fresh contexts, with one warm-up per scenario and viewport.
The lifecycle runner now covers fresh-stack startup and idle service outages,
including retained failures and saved media comparisons. It does not establish
active-job crash recovery. The candidate inputs, bounded failure scope and
combined run order are now documented. Before final collection, we finish the
input compatibility checks, resolve release dependency decisions, rerun the #26
software gate and commit the freeze record. The tools do not execute the entire
protocol as one command; each phase has a separate report and explicit command.
Issue #26 is closed; these development checks do not close #79.

We will retain raw JSON/CSV records, the input and runtime manifest, the exact
command, run ID and output hashes. The final report will link compact tracked
evidence and reproducible tables/plots from this results index. Large media and
generated outputs stay outside Git. System timing and workflow results will
have their own section, separate from the unchanged historical model scores.
