# System Evaluation Results

[Results index](results_index.md) | [Freeze](system_freeze.md) | [Protocol](system_evaluation_plan.md)

**21 November 2026: lifecycle collection is complete; the first cold-process
attempt stopped on a proxy failure. The full evaluation remains open under #79.**
We keep these system measurements separate from
the historical detector scores. Successful processing does not establish that
the detections are correct.

## Collection Status

| Phase | Planned work | Recorded so far |
| --- | --- | --- |
| Fresh-stack startup and idle service recovery | Three independent projects, 45 analyses | Complete: three trials, 45 successful analyses, no failed attempts |
| Cold-process API requests | Three restarts per scenario, plus seeds | Incomplete: ten completed trials, one failed and four not attempted; four setup requests completed |
| Warm API requests | One warm-up and ten measured requests per scenario | Not collected |
| Browser result readiness | One warm-up and ten measured submissions per scenario at each viewport | Not collected |

The [tracked lifecycle record](../../data/evaluation/system_lifecycle_final_2026_11_19.json)
contains every request observation, trial identity, outage response, background
snapshot and raw-artifact checksum. The freeze was committed as `2028ca7` before
the first trial. All three runs used that clean runner checkout and the same
application images, input hashes and model settings. No local test suite, build
or regression run overlapped the timed trials.

## Cold-Process Attempt

The [21 November attempt](cold_api_attempt.md) retains partial timings and the
failed V1 polling request. Nginx returned 502 after a backend DNS-resolution
error; the video finished in the backend later. That later completion does not
turn the client-visible failure into a successful trial. We stopped as planned
and opened [#172](https://github.com/AliCS-dev/traffic-crowd-monitoring-app/issues/172)
before changing the frozen application. Warm and browser collection have not
started. The lifecycle table below still belongs to the original frozen images.

## Startup and Recovery

All times are seconds. The sample count is three for each measure.

| Measure | Minimum | Median | Maximum | Empirical p95 |
| --- | ---: | ---: | ---: | ---: |
| Fresh project to API readiness | 13.005 | 13.056 | 13.074 | 13.074 |
| PostgreSQL start to API readiness | 0.472 | 0.495 | 0.501 | 0.501 |
| Backend start to API readiness | 2.035 | 5.049 | 5.727 | 5.727 |

Fresh startup includes empty-volume database initialization, migrations and
Compose dependency waits. Container images already existed locally; image
downloads and builds are excluded. Recovery starts immediately before
`docker start` and ends at the first completed ready response through Nginx.
It excludes the earlier stop command and outage probes. Neither measure includes
first inference or browser rendering. The exact boundaries are in the
[lifecycle guide](stack_lifecycle.md#what-we-measure).

The p95 uses nearest rank, `ceil(0.95 * n)`. With only three observations it is
the maximum, not a reliable estimate of a population tail. Backend readiness
varied from about two to six seconds; we retain that variation rather than
reporting only the fastest trial. The individual observations and full precision
are in the tracked record. These descriptive measurements are not a service-level
guarantee or proof of production reliability.

## Correctness Alongside Timing

Each trial ran I1, I2, I3, V1 and V2 before any outage, after PostgreSQL recovery,
and after backend recovery. Across all trials, 45 analyses processed 198 image
or sampled-video frames. These are repeated workflow observations, not 198
independent scenes or unique-object counts.

After each outage, we compared all five original saved sessions against their
pre-outage result and media hashes. All **30 session comparisons** and **264
clean/annotated JPEG comparisons** matched. Each recovery was also followed by
five successful new analyses. We verified the unchanged runtime provenance on
every request, including after backend restarts.

The outage responses matched the declared checks:

- With PostgreSQL stopped, the frontend and liveness endpoint remained available,
  readiness returned 503, and the saved-result route returned generic 500
  `internal_error`. That generic error is existing behavior, not an ideal API design.
- With the backend stopped, the frontend shell remained available while API
  requests returned 502 or 504. The individual status codes and probe durations
  are retained rather than replaced with a single invented response.

These were idle service outages. The results do not establish recovery from a
real GPU crash during an active video. Interrupted-job behavior remains covered
by separate controlled tests.

## Conditions and Evidence

Ali confirmed mains power and no unrelated heavy work. Before each trial, three
whole-device readings showed 220 MiB GPU memory in use and 0% sampled GPU
utilization. These readings do not prove exclusive GPU use or exclude activity
between samples. Eight pre-existing containers remained running; their names
and sampled CPU/memory use are retained. No trial backend existed before fresh
startup, so we do not invent a pre-start backend-memory measurement.

Each trial had new volumes and a new Compose project, but host caches were not
cleared. The fixed order, shared machine and small sample count limit broader
claims. All disposable trial containers, networks and volumes were removed
after their evidence was retained. Existing unrelated stacks were untouched.

The full local artifacts are:

- `data/output/system-measurements/final-lifecycle-2026-11-19/`: collection manifest and invocation/cleanup logs.
- `data/output/system-measurements/final-lifecycle-2026-11-19-1/`: first trial's JSON, CSV and checksum manifest.
- `data/output/system-measurements/final-lifecycle-2026-11-19-2/`: second trial.
- `data/output/system-measurements/final-lifecycle-2026-11-19-3/`: third trial.

The tracked summary retains request rows but replaces repeated runtime lists
with explicit comparisons to the freeze. Saved-result entries retain equality
checks, result hashes, asset counts and a SHA-256 of the sorted asset map. Full
maps and readiness polls remain in the hashed raw reports. Large artifacts stay
outside Git and need to be retained separately with the thesis evidence.

From the repository root, we can reproduce the rounded table from the tracked
observations without running inference again:

```python
import json
import math
import statistics
from pathlib import Path

record = json.loads(
    Path("data/evaluation/system_lifecycle_final_2026_11_19.json").read_text()
)
for name, row in record["timing_summary"].items():
    values = sorted(row["observations"])
    p95 = values[math.ceil(0.95 * len(values)) - 1]
    print(
        name,
        len(values),
        *(
            round(v, 3)
            for v in (min(values), statistics.median(values), max(values), p95)
        ),
    )
```

The next step is the proxy-recovery investigation before further cold-process
collection. We do not pool these lifecycle request timings with cold, warm or browser tables.
The failed detector quality gate, unsupported dense-crowd counting and documented
dependency risk remain unchanged.
