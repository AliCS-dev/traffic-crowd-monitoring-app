# System Evaluation Freeze

[Results index](results_index.md) | [Protocol](system_evaluation_plan.md)

On 19 November 2026 we passed the software gate and fixed the application,
images, settings and inputs for final system measurements. The
[freeze record](../../data/evaluation/system_freeze_2026_11_19.json) was prepared
before collection. Its status describes that point in time, not later progress.
It contains the full versions, hashes, workload limits and test-artifact hashes.

## What Is Fixed

| Item | Evaluated version |
| --- | --- |
| Application | Clean commit `5cbd433eebed9678f2e288329d4a99b8ad295cc4` |
| Measurement tool baseline | Clean commit `dc1ed4573370e0b1dcc63b29c7252cfa5a3334bf` |
| Backend and frontend | Locally built images identified by immutable IDs in the freeze record |
| Database | PostgreSQL 16.15, migrations 1 through 9, with recorded checksums |
| Model | `yolo26m-visdrone-experimental-v1`, unchanged checkpoint and settings |
| Inputs | I1, I2, I3, V1, V2, in that order; all five checksums verified |
| Browser | Playwright 1.65.0, Chrome for Testing 158.0.8127.18 |
| Host environment | WSL2, Intel Core 7 240H, 16 visible logical CPUs, about 15.5 GiB visible RAM |
| GPU | RTX 5060 Laptop GPU, 8151 MiB reported memory, driver 617.14 |
| Containers | Docker Desktop engine 29.9.2, Compose 5.6.1 |

The tool commit changes only report headings. Timers, requests and assertions
are unchanged. Each invocation retains its actual Git commit and clean-tree
state; later documentation commits do not become a different application build.
We compare tool hashes as well as image and input identities. A report heading
alone does not make a run part of the final collection.

The backend was built from the clean application commit with `APP_REVISION`
set to that full commit and `APP_SOURCE_DIRTY=false`. All 16 frontend files
served through Nginx matched the files in the frozen frontend image. We retain
the existing images rather than rebuilding between trials. Image IDs identify
the local artifacts; a future rebuild is not assumed to produce identical bytes.

Ali confirmed that the laptop is plugged in and no gaming, training or other
heavy work is planned during collection. We record background containers and
idle GPU readings before each phase. This does not verify exclusive GPU use.
The CPU and RAM values describe what WSL exposes, not a separate physical-host
inventory. Existing unrelated stacks are left untouched.

## Software Gate

| Check | Result on 19 November |
| --- | --- |
| Full Python suite with real PostgreSQL | 721 passed, none skipped; two runs |
| Frontend unit tests | 115 passed |
| Browser measurement rules | Six passed |
| Desktop/narrow browser checks | 40 passed, no failures or retries |
| Live GPU image/video browser checks | Four passed |
| Unchanged GPU regression | Five frames matched, no differences |
| Controlled Compose recovery | Saved hashes survived restart; abandoned job became `worker_interrupted` |
| Static/build checks | Python lint, formatting and compilation; frontend lint, formatting, types and build; backend dependency consistency passed |

Raw gate evidence is under
`data/output/system-measurements/freeze-gate-2026-11-19/` locally. Its hashes
are tracked in the freeze record. These checks establish software compatibility,
not detector accuracy or final performance. They finish before final collection.

## Collection Commands

The [protocol](system_evaluation_plan.md#repetitions-and-reporting) fixes the
phase order and repetition counts. First come three fresh-stack trials. Each
uses a new project, new output directory and empty volumes. From the repository
root, the first invocation is:

```bash
.venv/bin/python scripts/measure_stack_lifecycle.py \
  --project traffic-measure-final-lifecycle-1 --port 8088 \
  --backend-image sha256:79e5daa60b37da453e64983683dd203745583213ef5f913f561d1c62c98fd7ad \
  --frontend-image sha256:ab569278d359810402704804ec94a2c8f7872f954f56619d1944ad49e6ad5f4b \
  --scenarios configs/evaluation/system_workflows_candidate.json \
  --allow-stack-interruption \
  --output-directory data/output/system-measurements/final-lifecycle-2026-11-19-1
```

Trials 2 and 3 use the corresponding new suffixes. Before each invocation we
verify the frozen hashes, an unused port, sufficient disk space and the local
PostgreSQL image ID. The runner uses `--no-build --pull never`; no dependency
update or image pull belongs inside collection. After retaining each report
and its checksums, we remove only that trial's disposable stack and volumes.
We stop on failure and keep the failed attempt rather than silently retrying it.

Cold API, warm API and browser measurements follow in that order on a separate
request project. Their commands are documented in the
[restart](system_restarts.md), [warm](system_measurements.md) and
[browser](browser_readiness.md) guides; final runs use the five-input config
and repetition counts from the protocol, not the guides' smaller verification
examples. No test suite or regression run overlaps the timing phases.

## Boundaries

The [dependency review](release_dependency_review.md#19-november-recheck) records
one new OpenTelemetry advisory and why we retained this local evaluation
candidate. The affected dependency is still present; this is not a clean
security bill or approval for public deployment.

The model quality gate remains failed and dense-crowd counting is unsupported.
Live outages concern idle services, not a GPU worker crashing mid-video.
Issue #79 remains open until all planned phases, retained failures and final
tables have been reviewed. The thesis chapters still need Ali's own explanation
and discussion of these results.
