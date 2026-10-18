# UAVDT Daytime Baseline Results

**18 October 2026, issue #113.** We ran the selected YOLO26m VisDrone checkpoint
on the 170 images fixed in the [development protocol](uavdt_daytime_protocol.md).
The model finds many of the labelled vehicles, but it also overcounts. Trucks
and buses remain less reliable than cars/vans. These results help us decide
what to investigate next; they do not establish deployment readiness.

This is a three-class development comparison against native source labels,
not an independent final test or an official UAVDT challenge score. The
[historical failed quality gate](final_quality_gate.md) and the application's
unsupported dense-crowd status are unchanged. We did not train a model, tune
settings, run a confidence sweep or use held-out images.

The [compact result record](../../data/evaluation/uavdt_daytime_baseline.json)
retains exact metrics, settings, provenance, artifact hashes and counts for all
17 sequences. Values below are rounded for reading.

## Detection

All 170 images and 3,059 reference boxes were evaluated. Precision and recall
use confidence 0.25 and matching IoU 0.50; AP uses the fixed confidence floor
0.001. Macro precision and recall give each of the three classes equal weight.

| Measure | Value |
| --- | ---: |
| Macro precision | 0.6347 |
| Macro recall | 0.8552 |
| mAP50 | 0.7228 |
| mAP50-95 | 0.4314 |
| AP small / medium / large | 0.4158 / 0.4747 / 0.5290 |

| Class | Reference boxes | Precision | Recall | AP50 | AP50-95 | TP / FP / FN |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Car/van | 2,804 | 0.7148 | 0.9365 | 0.8727 | 0.4542 | 2,626 / 1,048 / 178 |
| Bus | 91 | 0.6364 | 0.7692 | 0.6225 | 0.4695 | 70 / 40 / 21 |
| Truck | 164 | 0.5529 | 0.8598 | 0.6733 | 0.3704 | 141 / 114 / 23 |

High recall does not mean every prediction is correct. At the operating point,
we have substantial false positives relative to the source labels. We need a
visual error review before attributing those discrepancies to particular model
failures or annotation omissions. The lower AP50-95 also shows that agreement
falls when tighter box overlap is required.

## Counting

These are sums of per-frame observations, not unique vehicles. Every class has
170 evaluated images, including images with zero source boxes for that class.
The vehicle total includes only car/van, bus and truck.

| Class | Reference total | Predicted total | MAE, objects/image | NAE | Bias, objects/image |
| --- | ---: | ---: | ---: | ---: | ---: |
| Car/van | 2,804 | 3,674 | 5.2471 | 0.3181 | +5.1176 |
| Bus | 91 | 110 | 0.3235 | 0.6044 | +0.1118 |
| Truck | 164 | 255 | 0.7118 | 0.7378 | +0.5353 |
| Vehicle total | 3,059 | 4,039 | 5.9294 | 0.3295 | +5.7647 |

NAE is the sum of absolute per-image count errors divided by the reference
total. Vehicle NAE 0.3295 therefore means absolute count error equal to about
33% of the reference total; it is not a detection error rate or the fraction
of vehicles missed. Positive bias indicates overcounting. A small bus or truck
MAE alone can be misleading because those classes are sparse.

### Variation Between Sequences

The following descriptive breakdown uses the same saved predictions and fixed
threshold. We did not rerun inference or remove difficult sequences.

| Sequence | Images | Reference vehicles | Predicted vehicles | MAE | NAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| M0101 | 10 | 133 | 190 | 5.70 | 0.4286 |
| M0201 | 10 | 64 | 89 | 2.50 | 0.3906 |
| M0207 | 10 | 18 | 200 | 18.20 | 10.1111 |
| M0210 | 10 | 113 | 122 | 2.10 | 0.1858 |
| M0301 | 10 | 51 | 69 | 2.20 | 0.4314 |
| M0401 | 10 | 181 | 255 | 7.40 | 0.4088 |
| M0402 | 10 | 249 | 296 | 4.70 | 0.1888 |
| M0603 | 10 | 208 | 262 | 5.40 | 0.2596 |
| M0604 | 10 | 147 | 253 | 10.60 | 0.7211 |
| M0605 | 10 | 144 | 259 | 11.50 | 0.7986 |
| M0702 | 10 | 581 | 686 | 10.50 | 0.1807 |
| M0703 | 10 | 241 | 271 | 3.00 | 0.1245 |
| M1201 | 10 | 225 | 237 | 1.40 | 0.0622 |
| M1202 | 10 | 164 | 171 | 1.50 | 0.0915 |
| M1304 | 10 | 174 | 224 | 5.00 | 0.2874 |
| M1305 | 10 | 189 | 242 | 5.30 | 0.2804 |
| M1306 | 10 | 177 | 213 | 3.80 | 0.2147 |

M0207 warrants particular attention: only 18 reference instances accompany 200
predicted instances. Its NAE can exceed 1 because normalized absolute error is
not a bounded accuracy score. This discrepancy is a reason to inspect the
source labels, ignored regions and predictions together, not to discard the
sequence or assume all extra detections are wrong.

## Runtime

We used the RTX 5060 Laptop GPU, float32 and batch size 1. After 20 warm-up
frames, the benchmark processed the first 100 manifest images in each of three
repetitions, giving 300 timing observations. These repetitions are not three
independent accuracy evaluations or timing coverage of all 170 images.

| Stage | Median, ms | P95, ms |
| --- | ---: | ---: |
| Image loading | 2.52 | 3.22 |
| Preprocessing | 2.47 | 3.11 |
| Model inference and postprocessing | 29.46 | 34.27 |
| Detection-record conversion | 82.50 | 107.75 |
| Complete in-memory processing | 115.20 | 138.18 |
| Loading plus in-memory processing | 117.62 | 140.44 |

In-memory throughput was 8.89 FPS; including image loading, it was 8.69 FPS.
Peak PyTorch-allocated GPU memory was 285.45 MiB, not total process or system
VRAM usage. Detection-record conversion took more time than model inference
in this run. That identifies a possible profiling target, not a measured fix.

These timings use the AP confidence floor of 0.001 and include conversion of
many low-confidence candidates. They exclude API handling, database writes,
grid/alert processing, UI rendering, model loading and metric computation.
They should not be presented as full-application video throughput. The laptop
power limit was not recorded by the runtime query; timing reflects this machine
and environment rather than a hardware-independent guarantee.

## Limitations And Decision

We saved 47,950 raw prediction records; 14,520 are excluded by the strict
ignore-region rule before confidence and target-class filtering. On 141 of
170 images, the saved raw count reaches the fixed `max_det=300` limit. The
candidate cap may constrain AP, including when ignored or out-of-scope
predictions occupy those slots. We did not increase it after seeing results.

The [source-label limitations](uavdt_daytime_protocol.md#the-source-label-decision)
still apply. Ten target boxes are strictly inside ignored regions, and the two
questioned M0210 records remain unchanged. Bus support is concentrated: 46 of
91 labels come from M0702. The low-support flag checks box count only; it does
not establish scene diversity. Frames within sequences are correlated, and
sequence IDs are not verified independent locations. We report point estimates
and sequence variation here, not population confidence intervals.

This dataset is development data from the source training split. Pretraining
exposure is not ruled out; no independent human label review or equivalence
between the mirror and original publisher copy is claimed. Person, bicycle,
motorcycle, dense crowds, night and adverse-weather performance are not
evaluated here. Scores are not directly comparable to the older six-class
held-out results, which used different images, labels and class coverage.

We keep the current model and application decisions unchanged. The next useful
step is a review of saved prediction/label discrepancies, particularly M0207,
bus/truck errors and the candidate cap. Any subsequent model comparison,
threshold search, training or protocol change needs its own declared scope
before new results are inspected. Issue #113 remains open.

## Reproducibility

Run ID: `20261018T111801Z-yolo26m-uavdt-daytime-source-baseline`.
The source revision was clean commit
`60c105f046e16329974cf9c08be7c1bd95a3ea62`, after PRs #139 and #143 merged.
The run used Python 3.10.12, PyTorch 2.12.0 with CUDA 13.0 and Ultralytics 8.4.51
in the existing local environment. It was not run in the deployment container;
the complete recorded dependency and hardware versions are in the JSON record.

```bash
.venv/bin/python scripts/run_detector_evaluation.py \
  --config configs/evaluation/uavdt_daytime_baseline.json
```

The first sandboxed launch stopped during hardware provenance collection
because CUDA was unavailable, before loading the detector or producing
predictions. The same command completed with GPU access outside the sandbox;
there was no CPU fallback or setting change. Only one inference run completed.

Local artifacts are under
`data/evaluation/derived/uavdt_daytime_runs/20261018T111801Z-yolo26m-uavdt-daytime-source-baseline/`.
The run-manifest SHA-256 is
`d7b3959cf1d386ad4c23484a9cc654be3b5a32516cd9f08ce2a86fb93b7ca1b8`.
It covers configuration, raw predictions, metrics, timing, provenance and the
generated summary. We verified every artifact checksum, dataset identity and
saved readiness record, then recomputed detection and count metrics from the
saved predictions with exact agreement. The sequence table uses those same
predictions. Raw media, labels, predictions and individual timing records stay
local; the compact record preserves the result and its identity in Git.
