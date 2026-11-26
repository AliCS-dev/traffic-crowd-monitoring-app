# Cold-Process API Results

[Results index](results_index.md) | [Current system results](system_results_refrozen.md) | [Measurement method](system_restarts.md)

On **26 November 2026**, we completed all 15 cold-process trials and five setup
analyses for `proxy-recovery-2026-11-22`. No trial failed or was left unattempted.
This is the second phase under the [24 November freeze](system_refreeze.md),
not a continuation of the [failed 21 November attempt](cold_api_attempt.md).
The application, model, inputs and measurement tools were unchanged.

## First Request After Restart

Each scenario has three observations. Times are seconds. The timer begins at
the first analysis POST after backend readiness and ends with the complete
image response or the first video-status poll reporting completion. Video
status is polled every 250 ms. Upload and API processing are included; backend
restart, setup analyses and saved-result checks are outside this timer.

| Scenario | Input | Minimum | Median | Maximum / empirical p95 |
| --- | --- | ---: | ---: | ---: |
| I1 | 1280 x 720 roundabout image, grid | 2.468 | 2.536 | 8.514 |
| I2 | 1280 x 720 roundabout image, no grid | 2.376 | 2.540 | 2.620 |
| I3 | 2160 x 1620 traffic-circle image, grid | 2.588 | 2.758 | 2.818 |
| V1 | Synthetic still-image sequence, three sampled frames | 2.800 | 2.987 | 3.101 |
| V2 | Natural-motion video, 16 sampled frames | 16.511 | 16.703 | 16.818 |

The 8.514-second I1 observation remains in the results. Its recorded inference
stage took 8.207 seconds; the evidence does not establish the cause of that
longer duration. We did not retry or remove it. With only three observations,
nearest-rank p95 is the maximum, not a reliable estimate of tail latency.
These are cold **processes**: host caches were not cleared between trials.

## Restart and Saved Results

Restart-to-ready includes the graceful `docker restart` command, process
startup, proxy requests and readiness polling. Saved recovery means reading
the earlier session's canonical JSON and all clean/annotated JPEGs, then
comparing their hashes. These are separate measurements, not parts of the
cold-request times above.

| Scenario | Restart-to-ready median (s) | Saved-recovery median (s) |
| --- | ---: | ---: |
| I1 | 2.831 | 0.031 |
| I2 | 2.843 | 0.035 |
| I3 | 3.045 | 0.070 |
| V1 | 3.111 | 0.075 |
| V2 | 3.049 | 1.205 |

All **15 saved-session comparisons** and **132 media-hash comparisons** matched
their setup baselines. The 20 analyses processed **88 frames** in total,
including 66 in the measured cold requests. All 20 analyses had complete stage
evidence. This supports recovery for the tested sequence, not a guarantee
against every future failure or a test of a GPU worker crashing mid-video.

## Stage Timings and Memory

These medians come from the existing backend stage logs. Video inference is
summed across sampled frames within each request before taking the median.
Inference includes first-call work under the existing stage boundary, not just
GPU execution. Persistence and queue time have narrower boundaries; the stages
do not form an exhaustive breakdown of API latency, so their medians should
not be added to explain the total.

| Scenario | Inference (s) | Persistence (s) | Video queue (ms) |
| --- | ---: | ---: | ---: |
| I1 | 2.220 | 0.015 | Not applicable |
| I2 | 2.161 | 0.013 | Not applicable |
| I3 | 2.276 | 0.018 | Not applicable |
| V1 | 2.217 | 0.016 | 0.247 |
| V2 | 2.692 | 0.060 | 0.258 |

The following values are the median of each trial's **largest observed sample**,
in MiB. The one-second target sampling interval can miss peaks. Backend cgroup
memory includes process and cache accounting; GPU memory covers the whole
device, not just our application. Sampling covers the cold request and its
evidence read, not the backend restart window.

| Scenario | Backend cgroup | Whole GPU device |
| --- | ---: | ---: |
| I1 | 1337.4 | 1006.0 |
| I2 | 1268.3 | 1006.0 |
| I3 | 1204.2 | 1146.0 |
| V1 | 1317.0 | 1006.0 |
| V2 | 3081.5 | 1006.0 |

All **188 resource readings** were available. The tracked record also contains
the individual readings and minimum/maximum statistics, rather than only these
rounded medians.

## Conditions and Evidence

Ali confirmed mains power and no heavy CPU/GPU work. No local tests or builds
overlapped collection. Ten unrelated frontend/database containers remained
running and were left untouched. Three pre-run GPU readings each reported
279 MiB used and 0% utilization. We do not claim exclusive GPU access.
Docker reported 12 KiB less available memory than at the freeze; we recorded
this sub-MiB WSL reporting difference without changing the frozen value.

The runner used clean revision `7fee585`, after the lifecycle evidence was
merged. The freeze was committed earlier as `36d43eb`. Preflight verified the
frozen files, five inputs, checkpoint, container images, live runtime and
served frontend files. No runtime or dependency update was included.

The [tracked result](../../data/evaluation/system_cold_api_refrozen_2026_11_26.json)
contains all timings, restart polls, saved baselines, sample readings, conditions
and artifact checksums. Repeated runtime details reference verified equality to
the freeze, excluding capture time and container identity. Full originals remain
locally in:

- `data/output/system-measurements/refrozen-cold-api-2026-11-26/`: report, CSV and checksum manifest.
- `data/output/system-measurements/refrozen-cold-preflight-2026-11-26/`: preflight, collector, runtime snapshot and logs.

The isolated `traffic-measure-refrozen-requests` project and its data are retained
for the remaining request phases. The earlier failed-attempt stack and evidence
remain untouched. Warm API and browser collection are next; **#79 remains open**.
These results concern system behavior and performance. They do not change the
failed detector-quality gate or establish support for dense crowds.
