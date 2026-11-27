# Warm API Results

[Results index](results_index.md) | [Current system results](system_results_refrozen.md) | [Measurement method](system_measurements.md)

On **27 November 2026**, we completed five warm-ups and **50 measured requests**
under the [24 November freeze](system_refreeze.md). All requests completed with
their timing evidence. None failed or was left unattempted. This is the third
phase for `proxy-recovery-2026-11-22`; the application, model, inputs and
measurement tools were unchanged.

## Request Times

Each scenario has ten measured requests after one excluded warm-up. Times are
seconds, from the multipart POST to the complete image response or first video
status poll reporting completion. Upload and polling delay are included; the
polling interval is 250 ms. These are API times, not browser rendering times.

| Scenario | Input | Minimum | Median | Maximum / empirical p95 |
| --- | --- | ---: | ---: | ---: |
| I1 | 1280 x 720 roundabout image, grid | 0.113 | 0.138 | 0.158 |
| I2 | 1280 x 720 roundabout image, no grid | 0.112 | 0.114 | 0.130 |
| I3 | 2160 x 1620 traffic-circle image, grid | 0.222 | 0.256 | 0.275 |
| V1 | Synthetic still-image sequence, three sampled frames | 0.558 | 0.574 | 0.637 |
| V2 | Natural-motion video, 16 sampled frames | 15.244 | 15.831 | 17.247 |

Nearest-rank p95 equals the maximum with ten observations. This is a small,
sequential workstation measurement, not a reliable population tail estimate
or a concurrent-user benchmark. We retained every observation and did not retry
requests to improve the table. The [cold-process results](cold_api_refrozen.md)
remain separate; the different phase and collection day do not establish a
controlled causal speedup.

## Backend Stages

The table gives median recorded stage durations per measured request, in
milliseconds. Video inference is summed across sampled frames before taking
the median. Inference includes the detector service call and CUDA completion,
not only GPU kernels; prior model loading and lock waiting are excluded.
Persistence covers the result-saving operation through commit, not every
database operation. Video queue time starts after job creation, not at upload.

| Scenario | Inference (ms) | Persistence (ms) | Video queue (ms) |
| --- | ---: | ---: | ---: |
| I1 | 39.358 | 18.724 | Not applicable |
| I2 | 37.532 | 14.609 | Not applicable |
| I3 | 49.807 | 17.369 | Not applicable |
| V1 | 117.544 | 25.010 | 0.239 |
| V2 | 855.497 | 54.382 | 0.193 |

These stages do not account for every part of the request, and their medians
should not be added as an exhaustive latency breakdown. For example, the V2
API median is much longer than its inference-stage median. We have not measured
a separate duration for every upload, decoding and output-generation operation,
so we do not assign the remaining time to one assumed bottleneck.

## Sequential Throughput

Each batch contains ten measured requests, excluding its warm-up. Batch wall
time includes saved-result/provenance reads and intermediate report writes.
For images, one processed frame is one image; for videos, only sampled frames
are counted. This is not source-video FPS, pure inference speed or evidence
of real-time processing of every video frame.

| Scenario | Processed frames | Batch wall time (s) | Sampled frames/s |
| --- | ---: | ---: | ---: |
| I1 | 10 | 1.508 | 6.630 |
| I2 | 10 | 1.341 | 7.455 |
| I3 | 10 | 2.712 | 3.687 |
| V1 | 30 | 6.083 | 4.932 |
| V2 | 160 | 159.491 | 1.003 |

The measured requests processed **220 frames**; including warm-ups, the run
processed **242 frames** across 55 analyses. All 55 had complete stage evidence
and saved-result provenance matching the selected runtime and model.

## Memory Observations

The sampler retained **392 readings**, with no unavailable values: 196 for each
resource below. These statistics cover the whole runner window, including
warm-ups and evidence reads. They are not per-scenario or per-request peaks.
The longer V2 batch dominates this sampling window, so the median is not a
typical value for every input. The one-second target interval can miss peaks.
All values are MiB.

| Resource | Minimum observed | Median reading | Maximum observed |
| --- | ---: | ---: | ---: |
| Backend cgroup memory | 1273.7 | 7467.4 | 8634.0 |
| Whole-device GPU memory | 368.0 | 1407.0 | 1407.0 |

The cgroup total includes file-backed and kernel memory, not just the Python
heap. A separate **post-run** snapshot recorded 2309.5 MiB anonymous memory,
5884.7 MiB file-backed memory and 192.0 MiB kernel memory. It helps explain why
the cgroup total is large, but does not reconstruct its composition at the
earlier sampled maximum or prove the presence or absence of a memory leak.
GPU readings include other processes; they are not isolated model allocation.

## Conditions and Preparation

Ali confirmed mains power and no heavy CPU/GPU work. No local tests or builds
overlapped collection. Ten unrelated frontend/database containers stayed running
and were left untouched. Three pre-run GPU readings reported 367 MiB used and
utilization of 3%, 11% and 18%; we do not claim exclusive GPU access. Docker
reported 4 KiB less memory than at the freeze. We retained this sub-MiB WSL
reporting difference without changing the frozen record.

Before preflight, the retained backend was stopped with exit code 127 and a
missing WSL bind-mount path error. One manual `docker start` succeeded. The
original container, image and named volumes were retained, and preflight checked
the running backend, database and served frontend against the freeze. All five
saved cold-phase baselines and their **44 media hashes** still matched. These
preparation checks are outside the timed warm run; we do not claim uninterrupted
overnight uptime. No restart occurred during collection, and the usual excluded
warm-up preceded each scenario.

## Evidence and Next Step

Collection used clean runner revision `ffa4c91`; the freeze was committed earlier
as `36d43eb`. The [tracked record](../../data/evaluation/system_warm_api_refrozen_2026_11_27.json)
contains individual requests, stage events, resource readings, batch durations,
conditions, the separate memory snapshot and hashes for twelve local artifacts.
Repeated runtime fields reference verified equality to the freeze, excluding
capture time and container identity; the compact observations reconstruct the
original report exactly.

- `data/output/system-measurements/refrozen-warm-api-2026-11-27/`: original report, request CSV and checksum manifest.
- `data/output/system-measurements/refrozen-warm-preflight-2026-11-27/`: preflight, runtime snapshot, logs, collection/summary scripts and post-run memory diagnostic.

The [measurement guide](system_measurements.md) documents the runner. This run
used the five-input candidate config, ten repetitions, origin
`http://127.0.0.1:8089` and the unchanged backend container ID recorded in the
JSON. The isolated project and volumes remain for browser collection at the two
planned viewports. **#79 remains open** until that collection and the final
evidence review are complete. These software results do not change the failed
detector-quality gate or establish support for dense crowds.
