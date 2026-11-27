# Replacement System Results

[Results index](results_index.md) | [Replacement freeze](system_refreeze.md) | [Protocol](system_evaluation_plan.md)

This collection uses `proxy-recovery-2026-11-22` under the committed
24 November freeze. The earlier [lifecycle results](system_results.md) and
[failed cold attempt](cold_api_attempt.md) belong to the previous candidate and
are not pooled into these tables.

## Collection Status

**27 November 2026:** lifecycle, cold-process API and warm API collection are
complete. Browser collection remains open. The freeze was committed as
`36d43eb` before collection. Lifecycle runners recorded that clean revision;
cold and warm runners used clean `7fee585` and `ffa4c91`, respectively, with
the same frozen images, inputs and tools.

| Phase | Planned work | Status |
| --- | --- | --- |
| Lifecycle | Three new projects, 45 analyses | Complete: 45 successful analyses, no failed trials or analyses |
| Cold API | Three restarts per scenario plus seeds | Complete: 15 cold trials and five setup analyses, no failures |
| Warm API | One warm-up and ten measured requests per scenario | Complete: 50 measured requests and five warm-ups, no failures |
| Browser | One warm-up and ten measured submissions per scenario at each viewport | Not collected |

Successful processing establishes workflow behavior, not detector accuracy.
All attempts, failures and unattempted work will remain visible. Issue #79 is open.

## Cold-Process API

The [26 November cold results](cold_api_refrozen.md) contain the request,
restart, stage and sampled-memory tables. Median first-request times were
**2.536 s (I1)**, **2.540 s (I2)**, **2.758 s (I3)**, **2.987 s (V1)** and
**16.703 s (V2)**, with three observations each. One I1 request took 8.514 s
and remains included. All 15 saved-session comparisons and 132 media-hash
comparisons matched. Setup requests, backend restarts and saved-result checks
are outside those request times; browser rendering is not measured here.

## Warm API

The [27 November warm results](warm_api_refrozen.md) report medians of
**0.138 s (I1)**, **0.114 s (I2)**, **0.256 s (I3)**, **0.574 s (V1)** and
**15.831 s (V2)**, with ten measured requests per scenario. All 55 analyses,
including warm-ups, had complete timing evidence. All 392 resource readings
were available. The report separates API latency, backend stages, sequential
batch throughput and memory, and records the backend startup interruption
before collection. The observed cgroup maximum was 8634.0 MiB, including
file-backed and kernel memory; this is not a Python heap measurement.

The following sections retain the separate **24 November lifecycle** results
and their collection conditions.

## Startup and Recovery

Times are seconds, with three observations per measure.

| Measure | Minimum | Median | Maximum / empirical p95 |
| --- | ---: | ---: | ---: |
| Fresh-stack readiness | 13.242 | 13.436 | 13.470 |
| PostgreSQL start to readiness | 0.481 | 0.493 | 0.519 |
| Backend start to readiness | 1.988 | 1.996 | 2.179 |

Fresh-stack timing begins before Compose creates the containers, network and
empty volumes, and ends at the first successful readiness response through
Nginx. It includes database initialization and migrations, but not image
downloads, builds or first inference. Service recovery begins before
`docker start`; it excludes the earlier stop and outage probes. Neither measure
is total user-visible downtime or submission-to-result latency.

Nearest-rank p95 equals the maximum at this sample size. These are descriptive
observations on one workstation, not a reliable tail-latency estimate or a
controlled before/after speed comparison with the old proxy. Host caches were
not cleared between trials.

## Workflow and Persistence

Each trial ran I1, I2, I3, V1 and V2 before interruption, after the database
outage and after the backend outage. All jobs were complete before stopping a
service. Across the three trials:

| Check | Result |
| --- | ---: |
| Completed analyses | 45 |
| Failed analyses | 0 |
| Processed frames | 198 |
| Saved-session comparisons after recovery | 30, all matched |
| Clean/annotated JPEG hash comparisons | 264, all matched |

During database outages, the web page and API health endpoint remained available;
readiness returned 503 and the saved-result endpoint returned the existing safe
500 response. During backend outages, the web page remained available while API
probes returned 502 or 504. Those expected outage responses are retained, not
reported as successful API calls. After recovery, all saved comparisons and new
analyses passed. This does not test a GPU worker crashing mid-video.

## Conditions and Evidence

Ali confirmed mains power and no heavy work. No local tests or builds overlapped
collection. Ten unrelated frontend/database containers remained running and
were left untouched. Pre-trial GPU samples reported 381 MiB used and utilization
between 0% and 37%; other activity cannot be ruled out. We do not claim exclusive
GPU access or discard a trial because its background reading was higher.

The [tracked record](../../data/evaluation/system_lifecycle_refrozen_2026_11_24.json)
contains every trial's requests, outage responses, saved hashes, conditions and
artifact checksums. Repeated runtime details are represented by verified equality
to the freeze, apart from capture time and container identity. Saved-recovery
entries reference the matching baseline hashes. Full originals remain locally:

- `data/output/system-measurements/refrozen-lifecycle-2026-11-24/`: collection record and invocation logs.
- `data/output/system-measurements/refrozen-lifecycle-2026-11-24-1/`, `-2/`, `-3/`: complete reports, CSVs and checksum manifests.

Only successful trials' disposable projects and volumes were removed, after
their evidence was retained and validated. The old failed-attempt stack remains
untouched. Cold-process and warm API collection are now recorded separately
above. Browser collection is next under the same freeze. Detector accuracy
and dense-crowd limitations have not changed.
