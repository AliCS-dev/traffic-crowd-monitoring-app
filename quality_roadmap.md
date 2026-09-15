# Quality Improvement Roadmap

We have a working application pipeline, but the detector has not passed its
quality gate. The next phase improves evidence, reliability and the experience
of inspecting aerial results. A more elaborate interface does not, by itself,
make the model more accurate.

The live status is on the [project board](https://github.com/users/AliCS-dev/projects/6)
and [parent issue #85](https://github.com/AliCS-dev/traffic-crowd-monitoring-app/issues/85).
This page records the agreed scope and order, rather than duplicating a changing
completion checklist.

## Work Order

| Issue | Intended outcome | Priority |
| --- | --- | --- |
| [#111](https://github.com/AliCS-dev/traffic-crowd-monitoring-app/issues/111) | Buildable containers and restored local service | P0 |
| [#80](https://github.com/AliCS-dev/traffic-crowd-monitoring-app/issues/80) | Bounded workloads, useful diagnostics and resource budgets | P1 |
| [#112](https://github.com/AliCS-dev/traffic-crowd-monitoring-app/issues/112) | Actual runtime provenance and dependency-regression evidence | P1 |
| [#113](https://github.com/AliCS-dev/traffic-crowd-monitoring-app/issues/113) | More representative aerial data and a new independent holdout | P1 |
| [#114](https://github.com/AliCS-dev/traffic-crowd-monitoring-app/issues/114) | Measured small-object traffic improvements | P1 |
| [#115](https://github.com/AliCS-dev/traffic-crowd-monitoring-app/issues/115) | A bounded aerial crowd-counting adoption decision | P1 |
| [#116](https://github.com/AliCS-dev/traffic-crowd-monitoring-app/issues/116) | Scene-first media inspection with interactive layers | P1 |
| [#117](https://github.com/AliCS-dev/traffic-crowd-monitoring-app/issues/117) | Linked sampled-video playback and count trends | Optional P2 |

We finish #111 first, then #80 and #112. The data controls in #113 precede
candidate selection in #114 and #115. Interface work in #116 can follow the
operational safeguards; it does not require a new frontend framework. #117
depends on that workspace and is the first extension to defer when time is tight.

Automated coverage continues under #26. After choosing the final model and
interface scope, we freeze the release for #79 system evaluation. The stable
architecture sections of #81 can be written alongside this work. Results,
conclusions, release preparation and defence remain #82, #83 and #84.

## Interface Direction

Ali selected [God's Eye View](https://github.com/bilawalsidhu/gods-eye-view)
as a visual reference. We take inspiration from its dominant scene, selectable
layers and focused inspection, while designing our own aerial-analysis workspace.
The actual image or sampled frame stays central, with pan/zoom, switchable boxes
and grids, compact controls, and an inspector connected to the selected object
or region. A concrete layout review precedes implementation.

We do not add a globe without geographic input, simulated detections, unrelated
live feeds or decorative telemetry. Counts remain per-frame observations, not
unique road users, speeds or physical density. The optional timeline makes these
observations easier to follow over time without inventing unsampled results.

## Evidence And Stopping Rules

The [results index](docs/evaluation/results_index.md) remains the entry point
for thesis metrics. Existing failed experiments stay available and unchanged.
The previously opened final test set cannot become a fresh unbiased test merely
by renaming it: new model selection uses development data and a newly reserved
independent final holdout.

Each accuracy issue declares thresholds, permitted regressions and a compute/time
budget before experiments. We keep a candidate only when the evidence supports
it; retaining the baseline or rejecting another crowd model is a valid outcome.
The application continues to report dense-crowd counts as unsupported until an
accepted method exists. We aim for a strong, reproducible BSc application, and
reserve a state-of-the-art claim for genuinely comparable benchmark evidence.
