# Proxy Recovery

[Results index](results_index.md) | [Failed cold attempt](cold_api_attempt.md) | [Compose guide](../compose_stack.md)

Issue [#172](https://github.com/AliCS-dev/traffic-crowd-monitoring-app/issues/172)
addresses a proxy failure exposed by the 21 November cold-process evaluation.
The video continued processing, but its client received HTTP 502 after earlier
readiness and status requests had succeeded. We preserve that failed observation
and its original database and artifacts.

## What We Found

On 22 November we reproduced the pattern in a separate Docker network, using
the frozen Nginx image and a small HTTP service instead of inference. After the
fifth backend restart, requests began failing about 2.86 seconds after readiness.
The retained proxy log again reported a negative DNS answer followed by
`no live upstreams`. No detector or database was involved in this reproduction.

The old configuration used a background-resolved, shared upstream. Nginx
1.30.5's [resolver handler](https://github.com/nginx/nginx/blob/release-1.30.5/src/http/modules/ngx_http_upstream_zone_module.c)
removes the corresponding addresses on an NXDOMAIN answer. That explains how
the peer list can disappear after a successful request. We have not captured
Docker's DNS packets, so we do not claim to know why the original resolver
returned that negative answer or exactly when the query began.

Our first revision used request-time resolution with the existing automatic
worker count. Ten restarts passed, but the changed-address test failed: one
worker returned ready while another still used the old address. We retained
that failed candidate report too; passing restart checks alone was insufficient.

## What Changed

We now use one Nginx event worker and request-time resolution through Docker
DNS. The address cache lasts five seconds. A resolver timeout is also bounded
at five seconds, and upstream retries are explicitly disabled. There is no
fixed backend IP, upload replay, measurement-runner retry or longer observation
delay to make a failing trial pass.

Nginx documents resolution for a variable-based destination in
[`proxy_pass`](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass).
We omit a replacement URI so the original API path and query are forwarded.
One event worker keeps the resolver state consistent while handling concurrent
connections. This choice fits the local application with one backend process;
it does not establish capacity for a public multi-user deployment.

True DNS/backend outages can still fail requests. The regression checks recovery
after first readiness under controlled restart/address-change scenarios, not
uninterrupted service during an outage or recovery from a GPU job crash.

## Verification

The [regression runner](../../tests/compose/check_proxy_recovery.py) uses the real
frontend image and Docker DNS, with a small HTTP fixture. It checks startup,
ten restarts and a forced address change. Every recovery is followed by at least
12 seconds of requests from persistent and fresh connections, without retries
after the first ready response. Paths, queries, upload bytes and POST delivery
counts are checked separately. It runs in the required container CI job.

| Local check on 22 November | Result |
| --- | --- |
| Final proxy regression | Startup, ten restarts and changed-address recreation passed; 1,400 post-readiness requests succeeded |
| Prior single-worker verification | The same twelve recovery windows passed before the helper's cleanup refinement |
| Real Compose workflows | Image/video storage, eight media hashes and interrupted-job handling passed after restart |
| Python suite with disposable PostgreSQL | 726 passed, none skipped |
| Frontend unit / desktop-mobile browser checks | 115 / 40 passed |
| Real GPU regression | Five unchanged baseline frames matched in each of two runs, before and after restart |
| Real GPU browser workflows | Four passed, retries disabled |
| Static/build checks | Python and frontend checks passed; production frontend built successfully |

The address-change trial recorded 50 unsuccessful readiness probes before the
first 200 response. Those belong to recovery, not the post-readiness success
count; the old cached address is not instantly forgotten. The intentional lost
POST response also remains a 502, with exactly one backend delivery.

Local verification artifacts are under
`data/output/issue172-proxy-recovery/`. The initial reproduction and unsuccessful
multi-worker candidate remain there alongside subsequent checks. Full Compose
and GPU checks cover actual image/video processing and saved results separately.
These checks are compatibility evidence, not new final performance measurements.

## Evaluation Boundary

Ali approved a new candidate and recollection of **all final system-evaluation
phases**, including lifecycle. The old lifecycle results and incomplete cold
attempt remain attributed to the 19 November freeze. We will not combine their
timings with the changed proxy.

The candidate is labelled `proxy-recovery-2026-11-22`. Only the frontend proxy
configuration changes at runtime; the backend, model, database schema, input
fixtures and measurement rules are unchanged. The
[candidate record](../../data/evaluation/proxy_recovery_candidate_2026_11_22.json)
contains immutable image IDs, configuration/test hashes, the unsuccessful
multi-worker report, the final regression and raw-artifact checksums. All 16
served frontend files match the original frozen image; the changed artifact is
the Nginx configuration. This is a verified local candidate, not a claim that
final evaluation is complete. A new pre-collection freeze must
record the reviewed artifacts and environment before final collection resumes.
Issue #79 remains open. The model quality gate is still failed and dense-crowd
counting remains unsupported.
