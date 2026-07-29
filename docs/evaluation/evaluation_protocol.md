# Aerial Detection Evaluation Protocol

## Purpose

This protocol defines how we will evaluate object detection before we tune a
model or use its predictions for grid analysis and alerts. It is intended to
keep comparisons reproducible and to prevent us from changing the experiment
after seeing a disappointing result.

Version 1 of this protocol is fixed when Issue #40 is merged. Later corrections
must be made in a reviewed pull request. If a correction affects a metric, split,
or threshold after benchmarking has begun, we will record the reason, create a
new protocol version, and rerun every affected model.

This is a project-specific quality gate for a BSc application. Its thresholds
are engineering targets, not universal claims about safe traffic or crowd
monitoring.

## Evaluation Questions

The evaluation will answer four questions:

1. How accurately does the current general pretrained model detect the objects
   that matter to this application?
2. How much do a limited set of inference settings change detection quality,
   counting error, and processing speed?
3. Does a suitable aerial-specific pretrained model perform well enough, or is
   fine-tuning justified?
4. Can the selected model process sampled frames fast enough on the development
   laptop for an interactive monitoring workflow?

Tracking accuracy, physical crowd density, grid assignment, and alert quality
are outside this model evaluation. They require separate methods and evidence.

## Operational Class Taxonomy

The application uses a small operational taxonomy that can be mapped consistently
across general and aerial datasets.

| Project class | Included objects | COCO-style baseline label | VisDrone-style label |
| --- | --- | --- | --- |
| `person` | Visible individual people | `person` | `pedestrian`, `people` |
| `bicycle` | Pedal bicycles and riders when labelled as a bicycle | `bicycle` | `bicycle` |
| `motorcycle` | Motorcycles and motor scooters | `motorcycle` | `motor` |
| `car_or_van` | Passenger cars, vans, and light commercial vans | `car` | `car`, `van` |
| `bus` | Road passenger buses and coaches | `bus` | `bus` |
| `truck` | Road freight trucks and lorries | `truck` | `truck` |

`road_vehicle_total` is derived by summing `bicycle`, `motorcycle`,
`car_or_van`, `bus`, and `truck`. It is an aggregate count, not another detector
class.

The application does not use a separate `crowd` class. Crowd concentration is
estimated from `person` detections within image regions. We will not describe
these values as people per square metre unless geographic calibration is added.

Predictions such as `train`, `boat`, `cell phone`, and `traffic light` are
outside the operational taxonomy. We will retain raw predictions for error
analysis but exclude non-target classes from displayed counts. If a target
object is predicted only as a non-target class, the target remains a false
negative.

Tricycles, awning tricycles, and unusual local vehicle types are outside the
initial taxonomy. Issue #42 must define how annotators mark such objects. We may
extend the taxonomy before benchmarking if the collected data shows that these
objects are important to the intended use case.

## Evaluation Units

A still image and one sampled video frame are both evaluated as independent
detection examples. Each example must retain:

- a stable example identifier;
- the original source identifier;
- the source type;
- the original frame number and timestamp for video;
- width and height in the coordinate space used by the annotations;
- the licence and provenance recorded by the dataset manifest.

Detection and counting metrics are calculated per image or sampled frame. Video
frames are not evaluated as a tracking sequence in this quality gate.

## Dataset Partitions

### Source-level grouping

The split unit is an independent source group, not an individual frame. All
frames from one video must remain in one partition. Images from the same flight,
burst, location, or near-duplicate sequence must also remain together when they
could share visual content.

For our custom evaluation data, we target an approximate 60/20/20 division of
source groups:

- **training:** 60 percent, reserved for fine-tuning if Issue #45 concludes that
  training is necessary;
- **validation:** 20 percent, used for model comparison, threshold selection,
  image-size selection, and checkpoint selection;
- **held-out test:** 20 percent, used only after the final configuration is
  frozen.

The proportions are targets rather than permission to split one source. If a
balanced grouped split is not possible, we will collect more independent
sources and document the final distribution. A fixed random seed of `2026` will
be recorded for reproducible split generation.

Official external benchmarks keep their published splits. Their results are
reported separately from the custom application dataset rather than being
combined into one score.

### Leakage controls

Before any model is tuned:

- every example receives a source-group identifier;
- file hashes and image similarity checks are used to find duplicates;
- no source-group identifier may appear in more than one partition;
- class and object-size distributions are reviewed for each partition;
- the held-out test labels are not inspected during model selection;
- test predictions are not used to change thresholds, preprocessing, class
  mapping, or model weights.

If a serious implementation or annotation error invalidates the final test run,
we will preserve the invalid run, document the correction, increment the
protocol or dataset version, and rerun the complete final comparison.

## Detection Metrics

We will use a proven COCO-compatible implementation rather than implementing
bounding-box matching ourselves.

### Intersection over Union

Intersection over Union (IoU) is the intersection area of a predicted and
ground-truth box divided by their union area. Matching is class-aware and
one-to-one, so one prediction cannot match multiple ground-truth objects.

### Precision and recall

At the selected operating confidence threshold and IoU `0.50`:

```text
precision = true positives / (true positives + false positives)
recall    = true positives / (true positives + false negatives)
```

We report macro precision and recall across the target classes, as well as
per-class values. Classes with fewer than 20 ground-truth instances in a
partition are marked as low-support and are not used alone to claim that the
quality gate passed.

### Average precision

We report:

- `mAP50`: mean average precision at IoU `0.50`;
- `mAP50-95`: mean average precision over IoU thresholds from `0.50` to `0.95`
  in steps of `0.05`;
- per-class average precision;
- small, medium, and large object results when supported by the evaluation
  library.

Average precision is calculated across confidence levels. The evaluation
confidence floor is therefore `0.001`, while the operating threshold is selected
separately on validation data. `max_det` is fixed at `300` detections per image
for every model unless dense-scene inspection proves that this cap truncates
valid predictions. Any change must be made before final comparison and applied
to all models.

## Count Metrics

For frame `i`, let `p_i` be the predicted count and `g_i` the ground-truth
count.

### Mean absolute error

```text
MAE = mean(abs(p_i - g_i))
```

MAE is reported in objects per frame for every supported class, `person`, and
`road_vehicle_total`.

### Normalized absolute error

```text
NAE = sum(abs(p_i - g_i)) / sum(g_i)
```

NAE gives a dataset-level relative error without dividing by the count in every
individual frame. This avoids the undefined values that ordinary percentage
error produces on empty frames. We report it only when the partition contains
at least one ground-truth object for the class or aggregate.

### Count bias

```text
bias = mean(p_i - g_i)
```

A negative value indicates systematic undercounting, while a positive value
indicates systematic overcounting. Count metrics include frames with zero
ground-truth objects so false detections in empty scenes remain visible.

## Runtime Measurements

All candidate models are measured with batch size `1` on the same machine and
with the same input order. The main evaluation device is the local NVIDIA RTX
5060 Laptop GPU.

We record:

- video decoding or image loading time;
- application preprocessing time;
- model inference and postprocessing time;
- detection-record and count-conversion time;
- complete in-memory frame-processing latency;
- effective processed frames per second;
- peak allocated GPU memory;
- model file size.

Database insertion is measured separately because it is not part of detector
latency.

Each configuration receives 20 warm-up frames followed by at least 100 measured
frames. If the evaluation partition is smaller, examples are repeated in a fixed
order for timing only; quality metrics never use repeated examples. We run three
timing repetitions and report median latency, 95th-percentile latency, and total
throughput.

GPU operations are asynchronous. Timing code must use CUDA events or synchronize
the GPU before reading the clock. The laptop remains connected to power, uses a
consistent performance mode, and runs without another intentional GPU workload.

## Controlled Model Selection

Issue #44 may evaluate the current baseline only at the following predeclared
settings:

- operating confidence: `0.10`, `0.15`, `0.25`, `0.40`, `0.50`;
- inference image size: `640`, `960`, `1280`;
- batch size: `1`;
- IoU used for operating precision and recall: `0.50`;
- maximum detections per image: `300`.

The unchanged application settings are recorded before this grid is tested.
Validation data selects the operating configuration. We do not add settings
because one unplanned value appears likely to improve the score.

Issue #45 may compare at most three credible pretrained candidates in addition
to the current baseline. Candidate selection must be justified by aerial
relevance, class compatibility, licence, local deployment feasibility, and
maintainability before their validation scores are compared.

The held-out test split is evaluated once using the frozen selected model,
weights, class mapping, confidence threshold, image size, and runtime settings.

## Quality Gate

These thresholds are preliminary engineering requirements for this application.
They deliberately combine localization, counting, and speed because a model
with a high aggregate detection score may still be unsuitable for monitoring.

| Measure | Pass | Conditional | Fail |
| --- | ---: | ---: | ---: |
| Macro precision at IoU 0.50 | `>= 0.70` | `>= 0.60 and < 0.70` | `< 0.60` |
| Macro recall at IoU 0.50 | `>= 0.60` | `>= 0.50 and < 0.60` | `< 0.50` |
| mAP50 | `>= 0.60` | `>= 0.50 and < 0.60` | `< 0.50` |
| mAP50-95 | `>= 0.35` | `>= 0.25 and < 0.35` | `< 0.25` |
| Person NAE | `<= 0.25` | `> 0.25 and <= 0.35` | `> 0.35` |
| Road-vehicle-total NAE | `<= 0.25` | `> 0.25 and <= 0.35` | `> 0.35` |
| Median in-memory frame latency | `<= 0.50 s` | `> 0.50 s and <= 1.00 s` | `> 1.00 s` |

The final decision follows these rules:

- **Pass:** every core measure is in the pass range and no supported target
  class shows an unexplained systematic failure.
- **Conditional pass:** no core measure fails, but one or more are conditional.
  Feature work may resume only with the limitation stated in the application
  and thesis.
- **Fail:** any core measure fails, the dataset is too weak to support the
  decision, or qualitative review finds a systematic failure hidden by aggregate
  scores.

Fine-tuning is not automatically required when the current baseline fails.
Issue #45 first compares credible pretrained aerial alternatives. Issue #46
starts only when that comparison shows that available models remain below the
required quality-performance trade-off.

For the final report, key metrics should include source-group bootstrap
confidence intervals where feasible. The gate uses the point estimates above,
while the intervals communicate uncertainty and prevent overconfident claims.

## Reproducibility Record

Every evaluation run must save:

- a unique run identifier and timestamp;
- the Git commit;
- protocol and dataset-manifest versions;
- split-manifest hash and random seed;
- model name, source, licence, weight-file hash, and file size;
- class mapping;
- confidence threshold, image size, IoU policy, `max_det`, batch size, device,
  and numeric precision;
- raw per-image predictions and metrics;
- operating-system, CPU, RAM, GPU, VRAM, driver, and power-mode information;
- Python, Ultralytics, PyTorch, CUDA, OpenCV, and evaluation-library versions;
- warm-up count, measured-frame count, and timing repetitions.

At the time this protocol was written, the local baseline environment was:

| Component | Value |
| --- | --- |
| GPU | NVIDIA GeForce RTX 5060 Laptop GPU |
| GPU memory | 8151 MiB |
| NVIDIA driver | 610.88 |
| Python | 3.10.12 |
| Ultralytics | 8.4.51 |
| PyTorch | 2.12.0 |
| PyTorch CUDA build | 13.0 |
| OpenCV | 4.13.0.92 |

This table describes the current machine, not a substitute for the run-specific
record.

## References

- [Ultralytics model validation documentation](https://docs.ultralytics.com/modes/val/)
- [Ultralytics VisDrone dataset documentation](https://docs.ultralytics.com/datasets/detect/visdrone/)
- [VisDrone benchmark paper](https://arxiv.org/abs/2001.06303)
- [COCO evaluation API](https://github.com/cocodataset/cocoapi/blob/master/PythonAPI/pycocotools/cocoeval.py)
- [Scikit-learn grouped split documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupShuffleSplit.html)
- [Scikit-learn guidance on data leakage](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage)
- [PyTorch CUDA timing guidance](https://docs.pytorch.org/docs/stable/notes/cuda.html#asynchronous-execution)
