# Selected YOLO26n Baseline

## Decision

We selected the COCO-pretrained YOLO26n model with the following operating
configuration as our reference baseline:

| Setting | Selected value |
| --- | ---: |
| Operating confidence | `0.25` |
| Inference image size | `1280` |
| Preprocessing scale factor | `2` |
| Maximum detections per image | `300` |
| Batch size | `1` |
| Numeric precision | `float32` |

The executable configuration is stored in
`configs/evaluation/yolo26n_selected_validation.json`. The original
`yolo26n_validation.json` remains unchanged so that the first pre-tuning result
can still be reproduced.

This selection establishes a consistent reference for later model comparisons.
It does not mean that YOLO26n passed the application quality gate or is ready
for operational traffic and crowd monitoring.

## Evidence Used

We used only the validation partition of dataset version `1.0-draft`. The
held-out test partition was not used or inspected during configuration
selection.

The decision is based on three checksum-backed experiments:

1. The confidence sweep
   `20260805T113920Z-yolo26n-validation-confidence-sweep` compared the five
   predeclared confidence thresholds at image size `1280`.
2. The image-size benchmark
   `20260805T115813Z-yolo26n-validation-image-size-benchmark` compared `640`,
   `960`, and `1280` at the unchanged confidence setting.
3. The qualitative analysis
   `20260805T122251Z-yolo26n-validation-error-analysis` reviewed deterministic
   false-positive, false-negative, classification, and count-error examples at
   the selected operating point.

## Why We Selected Image Size 1280

Image size `1280` produced the strongest detection quality of the three tested
sizes. Its `mAP50` was `0.4035`, compared with `0.3381` at `960` and `0.2431` at
`640`. It also gave the best small-, medium-, and large-object average
precision. This matters for aerial imagery because many relevant objects occupy
only a small part of the frame.

The measured median latency at `1280` was `138.86 ms`, and throughput was `6.55
FPS`. Runtime differences among the three sizes were small in this experiment,
so reducing the image size did not provide evidence of a meaningful speed
benefit. We therefore retained the stronger-quality setting.

## Why We Selected Confidence 0.25

At image size `1280`, confidence `0.25` gave the lowest road-vehicle normalized
absolute error among the tested thresholds: `0.2609`. It also increased
supported-class precision compared with lower thresholds and reduced obvious
false detections, while retaining more recall than `0.40` or `0.50`.

Confidence `0.10` produced a higher macro precision value, but this aggregate
was influenced by the very small bus and truck samples. It also increased
road-vehicle NAE to `0.4557`. Confidence `0.15` retained more recall, but its
vehicle NAE was higher at `0.3287`. The selected value is therefore a practical
traffic-counting trade-off within this baseline rather than a globally optimal
threshold.

No tested confidence produced acceptable dense-crowd results. Person NAE stayed
close to `1.0` throughout the sweep, so confidence tuning cannot solve the
crowd-monitoring limitation.

## Quality-Gate Decision

The selected baseline is assessed against the fixed thresholds in the
[evaluation protocol](evaluation_protocol.md):

| Core measure | Selected result | Outcome |
| --- | ---: | --- |
| Macro precision at IoU 0.50 | `0.4621` | Fail |
| Macro recall at IoU 0.50 | `0.2110` | Fail |
| mAP50 | `0.4035` | Fail |
| mAP50-95 | `0.2244` | Fail |
| Person NAE | `0.9994` | Fail |
| Road-vehicle-total NAE | `0.2609` | Conditional |
| Median in-memory frame latency | `0.13886 s` | Pass |

The operating confidence is applied to the saved confidence-floor predictions
when calculating counts, precision, and recall. It does not change the timed
model inference in this protocol, so the `1280` timing result remains applicable
to the selected threshold.

The overall result is **fail** because several core quality measures fail and
the visual review exposes systematic failures. The detector misses many
vehicles in difficult aerial night scenes, confuses some small overhead
objects, and returns zero people for the largest dense-crowd examples.

The result is still useful. It gives us a measured reference that future aerial
models must improve upon and shows that inference speed is not the present
bottleneck. The next evaluation stage should compare credible aerial-specific
pretrained models before we decide whether fine-tuning is necessary.

## Scope Of The Decision

We may use this configuration for demonstrations, development, and comparison
experiments while clearly identifying it as an experimental baseline. We must
not present its detections as reliable crowd-density measurements or as a basis
for safety-critical decisions.

The model, threshold, image size, class mapping, and other inference settings
remain frozen for baseline comparisons. The held-out test split will remain
unused until a final model configuration, rather than only this baseline, has
been selected.

Issue #45 later reran this frozen baseline alongside two aerial-specific models
from the same clean commit. The result and training decision are recorded in the
[aerial model comparison](aerial_model_decision.md).
