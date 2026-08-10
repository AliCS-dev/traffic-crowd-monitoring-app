# Final Model Freeze

## Frozen Configuration

On 10 August 2026, we froze the original VisDrone-trained YOLO26m checkpoint
for the final held-out evaluation in Issue #47. The frozen settings are:

| Setting | Value |
| --- | --- |
| Model | YOLO26m fine-tuned on VisDrone |
| Checkpoint SHA-256 | `e57204b8d77b5b22ea9253cbd5664b707623aeb7c19dbaa9034fe5a60bed6571` |
| Operating confidence | `0.25` |
| Evaluation confidence floor | `0.001` |
| Image size | `1280` |
| Preprocessing scale factor | `2` |
| Maximum detections | `300` |
| Batch size | `1` |
| Precision | `float32` |
| Device | `cuda:0` |

The complete configuration is stored in
`configs/evaluation/yolo26m_visdrone_held_out_test.json`, and the
machine-readable selection record is stored in
`configs/evaluation/final_model_selection.json`.

## Selection Basis

YOLO26m did not pass the validation quality gate, but it gave the strongest
practical balance among the evaluated models. It retained useful road-vehicle
performance, ran comfortably on the RTX 5060, and used substantially less model
storage than YOLO11x. The Okutama fine-tuning pilot improved person detection
but caused vehicle-class forgetting, so that checkpoint was rejected.

We selected the original YOLO26m checkpoint using validation evidence only. At
the time of this freeze, no held-out predictions had been generated or used to
change the model, class mapping, threshold, image size, or preprocessing.

## Final-Evaluation Rule

The held-out split will be evaluated once from the committed frozen
configuration. We will not tune any setting after seeing its results. If an
implementation or annotation error invalidates the run, we will preserve the
invalid artifacts and document the correction before any complete rerun, as
required by protocol version 1.0.

The final report will state the measured outcome even if the model fails. A
quality-gate failure is evidence about the limits of the application, not a
reason to alter the experiment after opening the held-out results.
