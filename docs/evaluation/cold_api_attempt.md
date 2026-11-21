# Cold-Process Attempt

[System results](system_results.md) | [Freeze](system_freeze.md) | [Restart method](system_restarts.md)

**21 November 2026: this attempt is incomplete.** We stopped after a video-status
poll returned HTTP 502. Ali chose to preserve the evidence and address the
proxy problem in [issue #172](https://github.com/AliCS-dev/traffic-crowd-monitoring-app/issues/172)
before changing the frozen application. We did not retry the failed trial or
start the warm and browser phases.

## What Ran

We planned three backend restarts per scenario, with one setup analysis before
each scenario. Every measured request was the first analysis after its restart.
These are cold-process observations: the host caches were not cleared.

| Scenario | Completed cold trials | Failed | Not attempted | Setup requests completed |
| --- | ---: | ---: | ---: | ---: |
| I1 | 3 | 0 | 0 | 1 |
| I2 | 3 | 0 | 0 | 1 |
| I3 | 3 | 0 | 0 | 1 |
| V1 | 1 | 1 | 1 | 1 |
| V2 | 0 | 0 | 3 | 0 |
| Total | 10 | 1 | 4 | 4 |

Four setup requests and ten measured requests completed successfully from the
client's perspective. The fifteenth submitted analysis was accepted but its
polling sequence failed. Unattempted work is neither a success nor a failure.
The ten completed trials also passed ten saved-session comparisons, including
24 clean/annotated asset-hash comparisons. All 80 collected resource readings
were available. Sampling stopped with the failed trial, not when its background
job eventually completed.

## Partial Timings

The table includes only successful cold requests from this incomplete attempt;
the outcome counts above remain part of the result. Times are seconds and
include upload and processing, with status polling for video. Setup requests
and saved-result verification are excluded. These observations do not complete
the planned final timing table and must not be pooled with a changed candidate.

| Scenario | Successful observations | Minimum | Median | Maximum / empirical p95 |
| --- | ---: | ---: | ---: | ---: |
| I1 | 3 | 2.471 | 2.544 | 8.250 |
| I2 | 3 | 2.386 | 2.744 | 3.278 |
| I3 | 3 | 2.375 | 2.461 | 2.569 |
| V1 | 1 | 3.072 | 3.072 | 3.072 |
| V2 | 0 | Not measured | Not measured | Not measured |

Nearest-rank p95 equals the maximum at these sample sizes. In particular, one
successful V1 observation says nothing useful about its typical or tail latency.
The failed V1 trial's 1.937 seconds is elapsed time until the polling error,
not a successful completion time. We do not insert it into the success table.
Exact request, restart, stage and resource observations remain in the evidence.

## The Failed Trial

V1 repetition 2 restarted the backend and received a ready response through
Nginx. Its upload returned 202 for session 15. Seven status polls then returned
200 before a later poll returned 502 at 10:46:17 UTC.

Nginx logged `backend could not be resolved (3: Host not found)` and
`no live upstreams`. The configuration uses Docker DNS with a dynamically
resolved backend upstream. This identifies an observed proxy-resolution failure;
the underlying cause and exact duration of the DNS failure remain unproven.
One occurrence is not a deterministic reproducer.

The backend continued processing and logged `video_completed` at
10:46:18.410759 UTC, after the runner had stopped. A separate later read found
the job completed, with three saved frames and all six media assets available.
That diagnostic read is not a replacement measurement: the client-visible
trial remains failed, and its original report is unchanged.

The raw request row's `http_status: 202` records the upload response. The failing
poll's 502 is established by the retained Nginx log; we do not misread 202 as the
error response. Stage logs captured before the runner stopped are incomplete
for this job. Later logs are retained separately rather than backfilled into
the original report.

## Conditions and Files

The runner checkout was clean commit `32f481e8a204d4f76e017395284c210d9844dd04`.
All frozen application, measurement-tool, configuration, checkpoint and input
hashes matched. The three image IDs, backend dependency versions, API settings,
Docker version, CPU allocation and GPU driver also matched the 19 November
freeze. WSL reported 8 KiB more memory; the preflight records that difference
without changing the freeze. An initial strict equality check stopped before
stack creation or any analysis. We then accepted and recorded this sub-MiB
allocation-reporting difference, not a runtime-image change.

Ali confirmed mains power and no heavy CPU/GPU work during collection. The three
pre-run GPU readings were 342 MiB with utilization of 19%, 18% and 0%; other
activity cannot be ruled out. We do not claim exclusive GPU use. Eight unrelated
containers remained running and were left untouched. All 118 focused measurement
tests passed before collection, with no overlapping local test or build run.

The [tracked record](../../data/evaluation/system_cold_api_attempt_2026_11_21.json)
contains the preflight, every request/trial, partial summaries, unattempted work,
diagnostic outcome and raw-artifact hashes. Repeated runtime dependency lists are
represented by verified comparisons to the freeze. Full originals remain locally:

- `data/output/system-measurements/final-cold-api-2026-11-21/`: unchanged report, CSV and checksum manifest.
- `data/output/system-measurements/cold-preflight-2026-11-21/`: pre-run environment and idle readings.
- `data/output/system-measurements/cold-diagnostics-2026-11-21/`: proxy/backend logs, later saved result and diagnostic record.

The isolated `traffic-measure-final-requests` stack and its volumes are retained
for inspection, not ordinary demonstration use. Before more measurements we
review #172, decide whether a new candidate/freeze is needed, and use a separately
labelled collection. The original failed attempt and the old lifecycle results
remain attributed to their original candidate. Issue #79 stays open; no model
accuracy or dense-crowd claim has changed.
