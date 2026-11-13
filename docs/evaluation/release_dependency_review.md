# Evaluation Dependency Decision

[Results index](results_index.md) | [System evaluation plan](system_evaluation_plan.md)

On 13 November 2026, Ali approved keeping the current dependency versions for
the system evaluation, with necessary security fixes as an exception. This is
a scope decision, not a completed release freeze or a claim that every pending
update is unsafe.

The starting application commit is `29f212c`, after the scenario work in PR #167
and frontend dependency update in PR #164. We verify that updated frontend
separately from the 12 November checks; those earlier results cannot certify a
later dependency set.

## Pending Updates

| PR | Change | Review and decision |
| --- | --- | --- |
| [#153](https://github.com/AliCS-dev/traffic-crowd-monitoring-app/pull/153) | Nginx base-image digest | Eight reported CI checks passed. Deferred by agreement; we have not verified this image against the final candidate. |
| [#154](https://github.com/AliCS-dev/traffic-crowd-monitoring-app/pull/154) | Node build-image digest | Eight reported CI checks passed. Deferred by agreement; a changed build image would require another served-bundle and workflow check. |
| [#163](https://github.com/AliCS-dev/traffic-crowd-monitoring-app/pull/163) | Nineteen Python dependencies, including PyTorch, Torchvision and Ultralytics | Deferred. The PR's Python quality job fails at the backend dependency regression-evidence check. Container build success does not replace the required GPU evidence. |

PR #163 changes the requirements to PyTorch 2.15.0 while the Dockerfile still
starts from the pinned PyTorch 2.14.1 image. Pip may install an overriding copy;
we do not assume that this preserves the tested CUDA/runtime combination.
The grouped detector, API and serialization changes need their own review and
fresh regression evidence before a future merge. We have not attributed the
CI failure to a measured prediction change: the failing evidence gate alone
does not establish such a change.

The [failing job](https://github.com/AliCS-dev/traffic-crowd-monitoring-app/actions/runs/42584336845/job/129050410515)
records the current gate failure. Existing checks on the image PRs are dated
evidence, not a promise that a later merge would pass. All three PRs stay open;
we neither merge them nor disable dependency checks to complete the evaluation.

## Post-Update Verification

We installed the merged lockfile with `npm ci`, rebuilt the frontend image and
used a new disposable GPU stack on loopback port 8087. Playwright 1.65.0 used
Chromium 158.0.8127.18. The backend reused the source-matching image from earlier
checks; the frontend build and its served assets were verified independently.
This was a dirty documentation branch, not a clean release freeze.

All 115 frontend unit tests, six measurement-rule tests and 40 desktop/narrow
browser tests passed. Lint, formatting, types and the container production build
passed. The 88 focused Python measurement/lifecycle tests also passed. We did
not repeat the entire Python/PostgreSQL suite locally for this documentation-only
change; the final candidate still needs the complete software gate.

The live browser run completed 20 attempts across I1, I2, I3, V1 and V2 at both
viewport sizes. It retained one warm-up and one measured submission per case.
All served-bundle, saved-provenance and first-scene geometry checks passed.
Separate reads verified five saved sessions, 22 frames and all 44 clean/annotated
JPEG assets. The unchanged five-frame GPU regression passed without differences.

The [tracked record](../../data/evaluation/system_scenario_verification.json)
contains all four development runs, including yesterday's two incomplete
attempts, and hashes of their raw files. Today's full report is at
`data/output/system-measurements/release-browser-2026-11-13/`. The image/video
sources and illustrative screenshots are in [system inputs](system_scenarios.md).
Browser checks cover the first sampled frame; the separate asset check covers
all stored frames. Neither establishes that every frame was navigated in the UI.

The reproduction command, after starting an isolated stack as described in the
[browser guide](browser_readiness.md), is:

```bash
npm --prefix frontend run measure:browser -- \
  --base-url http://127.0.0.1:8087 \
  --backend-container traffic-measure-release-review-backend-1 \
  --frontend-container traffic-measure-release-review-frontend-1 \
  --scenarios configs/evaluation/system_workflows_candidate.json \
  --repetitions 1 \
  --output-directory data/output/system-measurements/release-browser-new-check
```

The output directory must be new. This reproduces a compatibility check, not
the final repeated performance protocol. Local tests overlapped parts of this
run; its timings are not used as final performance measurements.

## Security and Freeze Boundary

The repository's paginated Dependabot alert query returned no open alerts on
13 November. Installation of the merged frontend lockfile also reported zero
known npm audit vulnerabilities. Neither result is a complete security audit,
and neither establishes that the container operating-system packages have no
vulnerabilities.

Before final collection we still record the clean application commit, immutable
container IDs, dependency versions, hardware and scenario hashes, then pass the
software gate on that candidate. A later necessary security fix produces a new
labelled candidate and rerun; results from different versions are not pooled.
No final measurements or accuracy claims are approved by this decision.
