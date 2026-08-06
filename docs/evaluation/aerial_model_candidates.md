# Aerial Model Candidate Selection

## Purpose

Before comparing another detector with our YOLO26n baseline, we fixed a small
candidate list. This prevents us from trying many models and reporting only the
ones that happen to perform well on our validation data.

This document records the selection made on 6 August 2026 for Issue #45. It is
not a benchmark result. The source-reported scores below are screening
information only and will not replace measurements from our own validation
protocol.

## Selection Requirements

A candidate had to meet all of the following requirements:

- it has downloadable pretrained weights for aerial imagery;
- its source and exact weight revision can be recorded;
- its classes cover our six operational classes after a documented mapping;
- its licence permits use in this academic project;
- it can run locally on the RTX 5060 with maintainable Python integration;
- it represents a useful quality or deployment trade-off rather than a nearly
  identical duplicate;
- it can be evaluated without using our held-out test split.

The evaluation protocol permits at most three candidates in addition to the
frozen baseline. We selected two because they already provide a meaningful
medium-versus-large comparison.

## Selected Candidates

| Candidate | Role | Parameters | Weight size | Source mAP50 | Source mAP50-95 |
| --- | --- | ---: | ---: | ---: | ---: |
| YOLO26m VisDrone | Practical medium model | 21.9 M | 44.1 MB | 0.3667 | 0.2122 |
| YOLO11x VisDrone | Quality-oriented large model | 57.0 M | 114.4 MB | 0.3844 | 0.2260 |

Both checkpoints were fine-tuned for 300 epochs on VisDrone2019-DET and are
published for the Ultralytics framework. Their model cards identify the weights
as AGPL-3.0. The repository revisions, direct weight URLs, file sizes, and
expected SHA-256 digests are frozen in
`configs/evaluation/aerial_model_candidates.json`.

### YOLO26m VisDrone

We selected [YOLO26m VisDrone](https://huggingface.co/dronefreak/visdrone-yolov26m)
as the practical candidate. It stays in the same model family and inference
framework as our baseline, which keeps integration risk low, while increasing
capacity from the nano baseline to a medium model. Its 44.1 MB checkpoint is
small enough for straightforward local deployment and repeated evaluation.

The frozen repository revision is
`20879fa2d2f351d1e032bfd0a38a5a6b735b0f03`. Its source-reported metrics are
useful evidence that the checkpoint is functional, but we will not assume that
they transfer to our mixed traffic and crowd dataset.

### YOLO11x VisDrone

We selected [YOLO11x VisDrone](https://huggingface.co/dronefreak/visdrone-yolov11x)
as the quality-oriented candidate. Its larger capacity gives the comparison a
reasonable upper bound without requiring us to train a model. The model uses
the same Ultralytics result format, so its integration effort remains much lower
than a detector from an unrelated framework.

The frozen repository revision is
`6832bcfa92a6c71facc8af41de0b1981a19ac7a0`. At 57.0 million parameters and
114.4 MB, it may be slower or use more GPU memory than the medium candidate.
Those costs are part of the comparison rather than reasons to exclude it in
advance.

## Class Mapping

Both candidates use eleven source labels derived from VisDrone. Their ordered
source taxonomy is stored with each candidate so the preflight can compare it
with the checkpoint metadata. We apply the same mapping to each model:

| VisDrone label | Project class |
| --- | --- |
| `pedestrian`, `people` | `person` |
| `bicycle` | `bicycle` |
| `motor` | `motorcycle` |
| `car`, `van` | `car_or_van` |
| `bus` | `bus` |
| `truck` | `truck` |

`tricycle`, `awning-tricycle`, and `others` remain outside the current project
taxonomy. Their raw predictions will be retained for traceability but excluded
from project counts and detection metrics, following the same policy used for
the baseline. The `others` label was confirmed from the embedded checkpoint
metadata during the technical preflight.

## Licensing And Evidence Limits

The two model cards label the checkpoints as AGPL-3.0. We may use and evaluate
them for this thesis, but the weight files will remain outside Git and their
licensing must be revisited before any public hosted deployment. The official
[VisDrone repository](https://github.com/VisDrone/VisDrone-Dataset) provides the
dataset and citation information but does not publish a clear licence file in
the repository. We therefore record dataset provenance and avoid claiming
unrestricted commercial use.

The model cards are community-published rather than peer-reviewed model
releases. Their reported scores were calculated on VisDrone test-dev, not our
application validation set. We treat those values only as evidence for choosing
plausible candidates. Our own checksum-backed results will determine the model
decision.

## Candidates Not Selected

| Model | Reason for exclusion |
| --- | --- |
| [DroneScan-YOLO](https://github.com/yannbellec/dronescan-yolo) | Its repository states that final metrics and pretrained weights are still awaiting release. |
| [QueryDet](https://github.com/ChenhongyiYang/QueryDet-PyTorch) | Its official repository provides VisDrone training and inference code but no released VisDrone checkpoint. |
| [ESOD](https://github.com/alibaba/esod) | Weights are available, but its documented environment uses PyTorch 1.8.1 and CUDA 11.1, while its main VisDrone setting uses image size 1536. This would require a legacy environment and a protocol change. |
| [MMRotate DOTA models](https://github.com/open-mmlab/mmrotate) | The DOTA taxonomy and rotated boxes do not cover people, bicycles, and motorcycles or map cleanly to our axis-aligned protocol. |
| Other models from the same VisDrone model zoo | Two sizes already represent the practical and quality-oriented choices. Testing more checkpoints from the same training pipeline would increase validation selection pressure without adding a substantially different trade-off. |

These are methodological exclusions, not claims that the models are poor. They
may be useful in another project or after a deliberate protocol revision.

## Checkpoint Preflight

The checkpoint preflight is deliberately smaller than the model comparison. It
downloads only these two pinned files into separate ignored directories,
verifies their recorded byte sizes and SHA-256 digests before loading them,
checks their embedded VisDrone class names, and runs one fixed validation image
through each model. It does not calculate evaluation metrics or inspect the
held-out test split.

We run the preflight with:

```bash
.venv/bin/python scripts/preflight_model_candidates.py --download
```

The command writes a local machine-readable report to
`data/evaluation/derived/reports/aerial_model_preflight.json`. The report records
the checkpoint identities, environment versions, validation image identity, and
pass status. Model weights and this machine-specific report remain outside Git.

Full validation benchmarking begins only after both candidates pass this
preflight.

## Outcome

Both candidates passed preflight and were evaluated with the fixed validation
protocol. Neither pretrained checkpoint satisfied the quality gate. The full
comparison and the YOLO26m fine-tuning decision are recorded in the
[aerial model decision](aerial_model_decision.md).
