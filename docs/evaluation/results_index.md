# Evaluation Results Index

This page is the starting point for our model-evaluation evidence. It keeps the
important decisions and metrics easy to find when we write the thesis, while
the larger generated predictions, images, training logs, and timing samples
remain outside Git.

**Current direction, 25 October:** we are prioritizing application completion
and deferring new model selection, with Ali's approval. The
[reference decision](reference_decision_v2.md) explains why the inspected labels
do not currently supply the proposed v2 reference. This does not change any
score below or turn an unfinished accuracy requirement into a pass.

Deployment checks are separate from these model metrics. The
[September 15 runtime report](../runtime_recovery.md) records a changed sample
output after dependency updates; it does not supersede the frozen quality gate.
The [quality roadmap](../../quality_roadmap.md) links the planned v2 evaluation
and accuracy work. The separate UAVDT development baseline below now has
measured results; the broader six-class v2 evaluation remains incomplete.

The [historical dataset audit](dataset_audit_v1.md) records class support,
object sizes, scene coverage and split limitations before v2 acquisition. It
describes our available evidence; it does not replace the accuracy results below.

The [v2 evaluation plan](evaluation_v2_plan.md) records the agreed daytime scope,
provisional coverage targets and new-holdout rules. It is a planning document,
not a new dataset release or a result. Historical metrics below remain unchanged.

The [v2 source inventory](source_inventory_v2.md) records candidate sources,
permission gaps, model-overlap risks and estimated review effort. It has not
established that the provisional coverage targets can be met.
Ali cannot take on the proposed annotation-review workload. The custom dataset
campaign is on hold while we assess existing-label alternatives; the six-class
protocol and historical gate have not been replaced or declared passed.

The [existing-annotation feasibility report](annotation_feasibility_v2.md)
records measured SDD/UAVDT annotation coverage, mirror provenance and the
ignore-region integration gap. On 10 October Ali approved the separate UAVDT
vehicle evaluation implementation. The [adapter notes](uavdt_adapter.md) record
the tested conversion and exclusion policy. The linked counts are inventory,
not accuracy scores.

The [13 October media check](uavdt_media_check.md) records nine training-image
overlays, checksums and measured class counts, plus two unresolved source-label
concerns. Its [JSON record](../../data/evaluation/uavdt_media_check.json) contains
technical evidence, not model metrics. No test images or predictions were used.

The [15 October UAVDT development protocol](uavdt_daytime_protocol.md) fixes
170 training-source frames from 17 daytime sequences and the current detector's
baseline settings. We retain native labels, including the two questioned
records, and document their uncertainty. The source-specific readiness check
authorizes a development baseline only, not the six-class quality gate or a
final holdout. Acquisition finished on 18 October: all 170 images passed the
readiness check, with 3,059 native labelled instances and 371 ignored rectangles.
The [preparation record](../../data/evaluation/uavdt_daytime_preparation.json)
retains the hashes, per-sequence counts and ten labels inside ignored regions.
These are dataset inventory figures; no new accuracy measurements have been
produced by this step.

## UAVDT Development Result

After preparation, we ran the fixed baseline on 18 October. The
[UAVDT results report](uavdt_daytime_baseline.md) records mAP50 **0.7228**,
mAP50-95 **0.4314**, macro precision **0.6347**, macro recall **0.8552** and
three-class vehicle-count NAE **0.3295**. Counts show overprediction and vary
substantially between source sequences. Median in-memory latency was
**115.20 ms** at the low AP confidence floor; this is not full-app throughput.

The [exact result record](../../data/evaluation/uavdt_daytime_baseline.json)
contains per-class metrics, sequence counts, runtime and artifact hashes.
This is agreement with native labels on development data, not a new final
quality-gate pass. No training, tuning or held-out images were used.

The [20 October saved-prediction review](uavdt_error_review.md) explains why we
cannot treat every disagreement as a detector mistake. M0207 has visible
vehicles without reference boxes, and selected bus/truck cases raise label
semantics concerns. An overlapping duplicate and unmatched references also
remain. No scores or labels changed; source verification comes before tuning.

The [24 October publisher source check](uavdt_source_audit.md) then confirmed
that all 34 baseline annotation files and the 20 selected M0207/M0402 images
match publisher-hosted files. The checked discrepancies are not explained by
a different mirror copy or local pairing. Label completeness and semantics
remain unresolved; this is source verification, not an accuracy improvement.

Application limits and preliminary resource budgets are recorded separately in
the [operational safeguards guide](../operational_safeguards.md). Its upload,
video and memory measurements do not change the model-quality results below.

## Current Final Result

The selected VisDrone YOLO26m model **failed the final held-out quality gate**.
It passed road-vehicle counting and runtime, but it did not meet the required
detection recall, average precision, or dense-crowd counting accuracy.

| Final held-out measure | Value | Gate result |
| --- | ---: | --- |
| Macro precision | 0.6158 | Conditional |
| Macro recall | 0.4866 | Fail |
| mAP50 | 0.4731 | Fail |
| mAP50-95 | 0.1816 | Fail |
| Person NAE | 0.9943 | Fail |
| Road-vehicle-total NAE | 0.2116 | Pass |
| Median in-memory latency | 71.04 ms | Pass |

The full interpretation, per-class tables, scene breakdown, confidence
intervals, runtime, error review, limitations, and artifact hashes are in the
[final quality-gate report](final_quality_gate.md). A compact machine-readable
copy is stored in `data/evaluation/final_quality_gate.json`.

## Dense-Crowd Follow-Up

We evaluated one dedicated point-based crowd counter after the detector failed
on dense aerial scenes. P2PNet reduced same-image DLR person NAE from `0.9962`
to `0.7275`, but it remained above the predeclared defer limit of `0.70`.
We therefore rejected this checkpoint for application integration.

| Held-out DLR measure | YOLO | P2PNet |
| --- | ---: | ---: |
| Predicted / reference people | 336 / 88,140 | 24,016 / 88,140 |
| MAE, people/image | 6,271.71 | 4,580.29 |
| NAE | 0.9962 | 0.7275 |
| NAE 95% interval | 0.9879-0.9999 | 0.6322-0.8251 |

The [dedicated crowd-counting result](dedicated_crowd_counting_result.md)
contains the protocol, runtime, interpretation, limitations, and explicit
decision. Exact compact evidence is in
`data/evaluation/dedicated_crowd_counting.json`.

The application consumes that tracked decision through `app/crowd_analysis.py`.
New stored sessions and API results report dense-crowd analysis as unsupported,
with a null count and no active crowd model. This prevents an empty list of
ordinary person detections from being interpreted as a measured crowd of zero.

## Evidence Map

| Question | Main record |
| --- | --- |
| Did a runtime update change development outputs? | [Runtime provenance and regression](../runtime_provenance.md) |
| What did we decide to measure and why? | [Evaluation protocol](evaluation_protocol.md) |
| Which data did we use, and under what licences? | [Dataset card](dataset_card.md) |
| What coverage is missing before evaluation v2? | [Historical dataset audit](dataset_audit_v1.md) |
| What are we planning for v2, and what still needs approval? | [V2 evaluation plan](evaluation_v2_plan.md) |
| Which new sources are suitable, and how much review might they need? | [V2 source inventory](source_inventory_v2.md) |
| What do existing SDD/UAVDT annotations actually support? | [Annotation feasibility](annotation_feasibility_v2.md) |
| What is fixed for the separate UAVDT vehicle baseline? | [UAVDT development protocol](uavdt_daytime_protocol.md) |
| What did the fixed UAVDT development baseline measure? | [UAVDT baseline results](uavdt_daytime_baseline.md) |
| What explains the UAVDT prediction disagreements? | [Saved-prediction review](uavdt_error_review.md) |
| Do the questioned inputs match the publisher's release? | [Publisher source check](uavdt_source_audit.md) |
| Why are new model-selection experiments deferred? | [Reference decision and refined UAVDT inspection](reference_decision_v2.md) |
| How did we annotate and check the data? | [Annotation guide](annotation_guide.md) |
| How did the original general model perform? | [Baseline selection](baseline_selection.md) |
| Which aerial models did we compare? | [Aerial model decision](aerial_model_decision.md) |
| Did fine-tuning help? | [Fine-tuning pilot](fine_tuning_pilot.md) |
| What was frozen before final testing? | [Final model freeze](final_model_freeze.md) |
| What did the untouched held-out test show? | [Final quality gate](final_quality_gate.md) |
| Did a dedicated counter solve dense crowds? | [Crowd-counting result](dedicated_crowd_counting_result.md) |

## Thesis Use

For the **Materials and Methods** chapter, we can use the protocol, dataset
card, annotation workflow, model selection, split controls, and reproducibility
settings. For **System Design and Implementation**, we can describe the
evaluation modules, saved-run format, checksums, and report generation. For
**Results and Discussion**, the final quality-gate report supplies the tables,
scene comparison, uncertainty, error cases, and limitations.
The UAVDT report adds a separate development comparison; its scores should not
be mixed with the historical held-out table or described as a model improvement.

We should not copy every value into several documents. This index and the final
report are the maintained reference; the LaTeX chapter can cite selected values
and explain what they mean for the research questions.

## Local Generated Artifacts

When present, the complete local evidence is under:

```text
data/evaluation/derived/runs/                 Quantitative runs and provenance
data/evaluation/derived/error_analysis/       Error cases and contact sheets
data/evaluation/derived/final_reports/         Final plots and compact evidence
data/evaluation/derived/uavdt_daytime_runs/    UAVDT development run and predictions
data/evaluation/derived/uavdt_error_review/    UAVDT local comparison images and cases
data/evaluation/derived/uavdt_source_audit/    Publisher comparison and transfer records
data/evaluation/derived/training/              Fine-tuning datasets and logs
```

These directories are intentionally ignored by Git. Their important identities
are retained through configuration files, compact tracked records, run IDs, and
SHA-256 hashes in the reports.
