# Evaluation Results Index

This page is the starting point for our model-evaluation evidence. It keeps the
important decisions and metrics easy to find when we write the thesis, while
the larger generated predictions, images, training logs, and timing samples
remain outside Git.

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

## Evidence Map

| Question | Main record |
| --- | --- |
| What did we decide to measure and why? | [Evaluation protocol](evaluation_protocol.md) |
| Which data did we use, and under what licences? | [Dataset card](dataset_card.md) |
| How did we annotate and check the data? | [Annotation guide](annotation_guide.md) |
| How did the original general model perform? | [Baseline selection](baseline_selection.md) |
| Which aerial models did we compare? | [Aerial model decision](aerial_model_decision.md) |
| Did fine-tuning help? | [Fine-tuning pilot](fine_tuning_pilot.md) |
| What was frozen before final testing? | [Final model freeze](final_model_freeze.md) |
| What did the untouched held-out test show? | [Final quality gate](final_quality_gate.md) |

## Thesis Use

For the **Materials and Methods** chapter, we can use the protocol, dataset
card, annotation workflow, model selection, split controls, and reproducibility
settings. For **System Design and Implementation**, we can describe the
evaluation modules, saved-run format, checksums, and report generation. For
**Results and Discussion**, the final quality-gate report supplies the tables,
scene comparison, uncertainty, error cases, and limitations.

We should not copy every value into several documents. This index and the final
report are the maintained reference; the LaTeX chapter can cite selected values
and explain what they mean for the research questions.

## Local Generated Artifacts

When present, the complete local evidence is under:

```text
data/evaluation/derived/runs/                 Quantitative runs and provenance
data/evaluation/derived/error_analysis/       Error cases and contact sheets
data/evaluation/derived/final_reports/         Final plots and compact evidence
data/evaluation/derived/training/              Fine-tuning datasets and logs
```

These directories are intentionally ignored by Git. Their important identities
are retained through configuration files, compact tracked records, run IDs, and
SHA-256 hashes in the reports.
