# Aerial Model Comparison And Training Decision

## Decision

The available pretrained models do not satisfy the application quality gate.
We will therefore continue with a controlled fine-tuning pilot under Issue #46.
We selected the VisDrone-trained YOLO26m checkpoint as the pilot starting point
because it provides the strongest practical balance of aerial detection quality,
vehicle counting, throughput, memory use, and model size.

The follow-up pilot was completed on 10 August 2026. It improved person
detection but caused severe vehicle-class forgetting, so its checkpoint was not
promoted. The setup, measurements, and rejection decision are recorded in the
[fine-tuning pilot report](fine_tuning_pilot.md).

This is a validation-only decision. We did not run, inspect, or use the held-out
test split.

## Comparable Evaluation Conditions

We evaluated the frozen YOLO26n baseline and both predeclared aerial candidates
from clean commit `97016c7b8d7d6d5e8e7ce3b054dd894061cf4ae0`. Every run used:

- protocol version `1.0` and dataset version `1.0-draft`;
- the complete 86-asset validation partition;
- operating confidence `0.25` and confidence floor `0.001`;
- inference image size `1280` and preprocessing scale factor `2`;
- batch size `1`, `max_det` `300`, and `float32` precision;
- the RTX 5060 and the same 20-warm-up, 3-by-100-frame timing procedure.

The three run records have the same dataset manifest hash,
`8dabfe690a0aa162da3172bb46842216d4eac5ef7f73a6e6ba5ad48a2892f37d`,
and the same annotation hashes. Their run manifests and internal artifact
checksums passed verification.

| Model | Run ID | Run-manifest SHA-256 |
| --- | --- | --- |
| YOLO26n COCO baseline | `20260806T113001Z-yolo26n-validation-selected-baseline` | `aac828857273fdc9963add27b67e89ee472aa02f4cc7f26d3e3991f7168cb275` |
| YOLO26m VisDrone | `20260806T113123Z-yolo26m-visdrone-validation` | `736ef843ee13fe4c10b4bc9f74e8ac7eb070af16440ed18514ecaf68a8561aa5` |
| YOLO11x VisDrone | `20260806T113238Z-yolo11x-visdrone-validation` | `a7042e474251b8feca66e81264223fc8b97ec799cdfcda9cd83cfcc5d006fdbf` |

## Decision Table

The latency column is the median complete in-memory frame-processing time. GPU
memory is peak allocated memory during the repeated timing benchmark.

| Model | Precision | Recall | mAP50 | mAP50-95 | Person NAE | Vehicle NAE | Median ms | FPS | GPU MiB | Weights MiB | Integration | Licence | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| YOLO26n COCO | 0.4621 | 0.2110 | 0.4035 | 0.2244 | 0.9994 | 0.2609 | 135.24 | 6.67 | 142.74 | 5.29 | Already integrated, but not aerial-specific | AGPL-3.0 | **Fail** |
| YOLO26m VisDrone | 0.4837 | 0.4315 | 0.4301 | 0.2189 | 0.9878 | 0.2852 | 113.82 | 8.02 | 464.75 | 42.01 | Same Ultralytics pipeline; explicit VisDrone mapping required | AGPL-3.0 | **Fail** |
| YOLO11x VisDrone | 0.5803 | 0.4587 | 0.4478 | 0.2280 | 0.9841 | 0.3948 | 115.87 | 6.92 | 743.65 | 109.11 | Same pipeline, but substantially larger deployment cost | AGPL-3.0 | **Fail** |

YOLO11x produced the strongest detection metrics, but its improvement over
YOLO26m was modest relative to its additional size and memory use. At the fixed
operating point, YOLO26m also produced a lower vehicle-count error and higher
throughput. Both aerial models improved recall substantially over the general
COCO baseline, confirming that aerial-domain weights are useful, but neither
improvement was enough to pass the gate.

All three checkpoints use AGPL-3.0 terms. This is acceptable for our academic
evaluation, while any later public hosted deployment will require a separate
licensing review. The two community model cards are useful sources, but they are
not peer-reviewed releases; the pinned revisions and checkpoint hashes remain
part of our provenance record.

## Quality-Gate Interpretation

At confidence `0.25`, every model failed recall, mAP50, mAP50-95, and person NAE.
The baseline and YOLO26m had conditional vehicle NAE, while YOLO11x failed that
measure. All three passed the latency requirement.

The person-count result is the clearest systematic limitation. Across the 54
person-count examples, the reference total is 138,376 people. At the fixed
operating threshold, the baseline predicted 77, YOLO26m predicted 1,723, and
YOLO11x predicted 2,211. These predictions are not suitable for crowd-density
monitoring.

The validation data also has low support for some road classes: six bus boxes,
three truck boxes, and no supported bicycle boxes. We therefore do not use those
individual class scores to claim general reliability. The grouped split and
dense-crowd evidence are still strong enough to reject the current checkpoints
for the intended application.

## Confidence Sensitivity

We tested only the five thresholds authorized by the protocol: `0.10`, `0.15`,
`0.25`, `0.40`, and `0.50`. These comparisons reused saved confidence-floor
predictions and performed no additional model inference.

- YOLO26n remained a fail at every threshold. Confidence `0.10` improved recall
  but produced failing vehicle NAE, while person NAE remained near `1.0`.
- YOLO26m reached conditional precision and passing vehicle NAE at confidence
  `0.40`, but recall, both average-precision measures, and person NAE still
  failed.
- YOLO11x reached conditional precision and passing vehicle NAE at confidence
  `0.50`, but recall, both average-precision measures, and person NAE still
  failed.

The checksum-verified sweep records are:

| Model | Sweep ID | Comparison-manifest SHA-256 |
| --- | --- | --- |
| YOLO26n COCO | `20260806T113405Z-yolo26n-validation-confidence-sweep` | `149952275df680fe8020dd6ef2a7f5d36ae7938f3f87ed00f0b4a68b947a7dcd` |
| YOLO26m VisDrone | `20260806T113426Z-yolo26m-visdrone-validation-confidence-sweep` | `5270d8b11d3e2e83ac81090ce49e89b3b5e2c3390c383dc44cab777324cbff2a` |
| YOLO11x VisDrone | `20260806T113445Z-yolo11x-visdrone-validation-confidence-sweep` | `02386c0b651d73ccb75db25237cba1238be2e43f3cefafa3fa59e8c2fcfe84ac` |

Threshold adjustment changes the precision, recall, and vehicle-count trade-off,
but it cannot solve the central model-quality problem.

## Training Starting Point

Issue #46 should begin with a small YOLO26m VisDrone pilot rather than a long
training run. Before the pilot, we must audit the training partition for usable
bounding boxes, especially for people, because point-count annotations alone
cannot train an object detector. The training configuration must keep source
groups separated and must not use validation or held-out test images.

The pilot should answer whether domain-specific fine-tuning improves person
detection and maintains vehicle performance within the RTX 5060 memory limit.
YOLO11x remains a quality-oriented reference, but its larger training and
deployment cost does not justify using it as the first experiment.

The final checkpoint is not selected here. It will be chosen from validation
results under Issue #46 and evaluated on the held-out split only after its
weights and operating settings are frozen.
