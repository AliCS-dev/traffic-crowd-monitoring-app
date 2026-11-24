# Replacement System Freeze

[Results index](results_index.md) | [Protocol](system_evaluation_plan.md) | [Proxy fix](proxy_recovery.md)

On 24 November 2026, PR #174 was merged after all eight checks passed. We
verified the retained `proxy-recovery-2026-11-22` candidate and recorded a new
[pre-collection freeze](../../data/evaluation/system_freeze_2026_11_24.json).
Ali approved repeating every final phase, including lifecycle. The
[original freeze](system_freeze.md) and its observations remain separate.

## Fixed Candidate

| Item | Identity or decision |
| --- | --- |
| Reviewed application checkout | Clean `84f85e2b2c2e842d259e45ae82a8b04920effaaf` |
| Changed component | Nginx configuration: one event worker, request-time DNS, no upstream retries |
| Frontend image | Immutable ID beginning `135f02cd3cdb`; full ID in the freeze |
| Backend image | Unchanged ID beginning `79e5daa60b37`, built from clean `5cbd433` |
| Database | Same PostgreSQL 16.15 image and nine migrations |
| Model and inputs | Unchanged checkpoint, inference settings and I1/I2/I3/V1/V2 checksums |
| Measurement tools | Unchanged timer boundaries, polling and repetition counts |
| Collection order | Three lifecycle trials, cold API, warm API, then both browser viewports |

We did not rebuild the images. The backend keeps its actual earlier build
revision; the complete application now includes the reviewed proxy change.
We verified the image IDs, committed Nginx configuration and all sixteen served
frontend files instead of labelling an old image as newly built. Every run also
records its own clean runner revision.

## Verification and Conditions

The full software gate belongs to **22 November**: 726 Python tests with
PostgreSQL enabled, 115 frontend unit tests, 40 browser checks, four live GPU
browser checks, controlled Compose workflows and the unchanged GPU regression.
Both PR CI runs passed, including the added proxy restart/address-change check.
The [candidate record](../../data/evaluation/proxy_recovery_candidate_2026_11_22.json)
retains those results and their limits.

On **24 November** we checked 73 source, input and evidence hashes, passed 123
focused measurement/proxy tests, and used a new disposable stack to read the
actual dependencies, API settings, database migrations and frontend files.
Everything matched the retained candidate. A fresh five-frame GPU regression
also matched without differences. This is a dated recheck, not a claim that the
entire software gate ran again today. The verification stack was removed before
collection; its artifacts remain under
`data/output/system-measurements/refreeze-preflight-2026-11-24/`.

The hardware remains the Core 7 240H / RTX 5060 Laptop GPU setup under WSL2,
with driver 617.14, Docker 29.9.2 and Compose 5.6.1. The freeze records actual
CPU/RAM allocation and tool versions. Ali confirmed mains power and no heavy
work during measurements. Each trial records background containers and idle
GPU readings; we do not claim exclusive GPU access. Tests and builds finish
before timed collection starts.

## Collection

The freeze is committed before the first trial. Each lifecycle trial uses a
new project and empty volumes, with the fixed images and five-input config:

```bash
.venv/bin/python scripts/measure_stack_lifecycle.py \
  --project traffic-measure-refrozen-lifecycle-1 --port 8089 \
  --backend-image sha256:79e5daa60b37da453e64983683dd203745583213ef5f913f561d1c62c98fd7ad \
  --frontend-image sha256:135f02cd3cdb9edd2a6f51c587658f76c584762e5829a4a682d9bcc2a62c25cf \
  --scenarios configs/evaluation/system_workflows_candidate.json \
  --allow-stack-interruption \
  --output-directory data/output/system-measurements/refrozen-lifecycle-2026-11-24-1
```

Trials two and three use new matching suffixes. The collector checks the
frozen hashes, images and environment before each invocation. Failed trials
remain failed and stop further collection. After retaining successful reports
and their checksums, we remove only that trial's disposable project and volumes.
The old `traffic-measure-final-requests` evidence stack is not reused or removed.

The [replacement results page](system_results_refrozen.md) records progress.
The freeze describes the pre-collection state and will not be rewritten to
incorporate later outcomes. Issue #79 remains open until every phase is reviewed.
The failed model quality gate, unsupported dense-crowd counting and open
OpenTelemetry advisory #60 remain unchanged; this is not an accuracy or security
certification.
