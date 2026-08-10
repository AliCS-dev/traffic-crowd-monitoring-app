# Final Model Quality Gate

## Outcome

The frozen VisDrone-trained YOLO26m model **failed** the final held-out quality
gate. It passed the road-vehicle count and runtime requirements, but it failed
recall, both average-precision requirements, and dense-crowd counting. Macro
precision was in the conditional range.

This does not make the application work worthless. It gives us a defensible
boundary for the thesis: the pipeline can process aerial media quickly and can
produce useful vehicle counts in some traffic scenes, but the selected detector
is not reliable enough for general traffic and crowd monitoring. In particular,
we must not present bounding-box detections as accurate crowd counts in very
dense scenes.

Under protocol version `1.0`, grid counting and alert development cannot resume
as validated monitoring features after a failed gate. We can still demonstrate
the software architecture and study those components later as explicitly
experimental prototypes, but operational claims require better model evidence.

## Test Integrity

We froze the checkpoint, class mapping, confidence threshold, image size, and
preprocessing settings in commit
`d36a581aea1208b32a3c2a0b9a59192326b2bf25` before opening the held-out test
results. The working tree was clean when the run began. The run used the
original VisDrone YOLO26m checkpoint because the Okutama fine-tuning pilot had
improved person detection while removing useful vehicle performance.

The held-out split was evaluated once on 10 August 2026. We did not change the
model, threshold, class mapping, or preprocessing after seeing the result. The
frozen settings and their selection basis remain in the
[final model freeze](final_model_freeze.md).

| Record | Value |
| --- | --- |
| Run ID | `20260810T135010Z-yolo26m-visdrone-held-out-test` |
| Run-manifest SHA-256 | `4cf8cea0ec31ef520b128a0b02157c0cfd9d4dbff8e25ed8b333e86434cb9c32` |
| Dataset manifest SHA-256 | `8dabfe690a0aa162da3172bb46842216d4eac5ef7f73a6e6ba5ad48a2892f37d` |
| Checkpoint SHA-256 | `e57204b8d77b5b22ea9253cbd5664b707623aeb7c19dbaa9034fe5a60bed6571` |
| Held-out assets | 130 |
| Box-evaluated images | 116 |
| Ground-truth boxes | 1,873 |
| Raw predictions retained | 20,455 |

## Gate Decision

The following table compares the held-out point estimates directly with the
requirements declared before final testing.

| Measure | Held-out value | Required for pass | Result |
| --- | ---: | ---: | --- |
| Macro precision | 0.6158 | >= 0.70 | Conditional |
| Macro recall | 0.4866 | >= 0.60 | **Fail** |
| mAP50 | 0.4731 | >= 0.60 | **Fail** |
| mAP50-95 | 0.1816 | >= 0.35 | **Fail** |
| Person NAE | 0.9943 | <= 0.25 | **Fail** |
| Road-vehicle-total NAE | 0.2116 | <= 0.25 | Pass |
| Median in-memory latency | 0.0710 s | <= 0.50 s | Pass |

The overall result is **fail** because the protocol states that one failing core
measure is enough to fail the gate. Four core measures failed here, including
the person-count requirement that is central to crowd monitoring.

## Detection Results

| Class | Support | Precision | Recall | AP50 | AP50-95 | Support note |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Person | 247 | 0.6587 | 0.5547 | 0.5776 | 0.1898 | Sufficient |
| Car or van | 1,587 | 0.5794 | 0.4991 | 0.4302 | 0.1854 | Sufficient |
| Bus | 4 | 0.6000 | 0.7500 | 0.6959 | 0.2716 | Low |
| Truck | 35 | 0.6250 | 0.1429 | 0.1886 | 0.0795 | Sufficient but limited |

Bus performance must not be treated as a strong result because only four buses
were labelled. Bicycle and motorcycle had no supported held-out boxes, so no
box-level accuracy claim is possible for those classes.

Object size had a strong effect:

| Object-size group | AP50-95 |
| --- | ---: |
| Small | 0.1482 |
| Medium | 0.2864 |
| Large | 0.3787 |

This progression agrees with the visual review: small distant objects were much
harder to localise consistently than larger vehicles and people.

## Counting Results

| Class or aggregate | Frames | Reference total | Predicted total | MAE | NAE | Bias |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Person | 64 | 88,387 | 544 | 1,373.1094 | 0.9943 | -1,372.5469 |
| Car or van | 66 | 1,587 | 1,367 | 5.1212 | 0.2130 | -3.3333 |
| Bus | 6 | 4 | 5 | 0.5000 | 0.7500 | +0.1667 |
| Truck | 6 | 35 | 8 | 4.5000 | 0.7714 | -4.5000 |
| All road vehicles | 66 | 1,626 | 1,400 | 5.2121 | 0.2116 | -3.4242 |

The model missed nearly all people in the count-only dense-crowd photographs.
This is not a small calibration error: a detector designed around individual
bounding boxes cannot resolve thousands of tiny, overlapping people at this
altitude. The road-vehicle aggregate, by contrast, remained within the declared
count-error requirement.

## Scene Breakdown

The four collections represent different scene conditions, so their separate
results are more useful than treating the held-out split as homogeneous.

| Collection and scene | Images | Main box result | Main count result |
| --- | ---: | --- | --- |
| Traffic-UAV urban intersection | 60 | mAP50 0.9706; mAP50-95 0.5827 | Vehicle NAE 0.2013 |
| Wikimedia highway interchange | 6 | mAP50 0.3865; mAP50-95 0.1445 | Vehicle NAE 0.2139 |
| Okutama staged activity | 50 | Person AP50 0.5776; recall 0.5547 | Person NAE 0.3036 |
| DLR-ACD dense crowd | 14 | Count-only annotations | Person NAE 0.9962 |

The very high Traffic-UAV result should be interpreted carefully because its 60
frames come from one source group. The highway interchange is more complex and
contains many small vehicles, occlusions, and overlapping roads. Okutama shows
that individual-person detection can be useful in sparse or moderate staged
scenes. DLR-ACD demonstrates that this method does not generalise to extreme
crowd density.

## Uncertainty

We used a fixed seed of `2026` and 2,000 source-group bootstrap resamples. The
intervals are percentile 95% intervals. They communicate variation between
independent source groups; the gate itself continues to use the predeclared
point estimates.

| Measure | Point estimate | Bootstrap 95% interval | Source groups |
| --- | ---: | ---: | ---: |
| Macro precision | 0.6158 | 0.5831 to 0.7528 | 7 |
| Macro recall | 0.4866 | 0.4376 to 0.7955 | 7 |
| Person NAE | 0.9943 | 0.2187 to 0.9959 | 6 |
| Road-vehicle-total NAE | 0.2116 | 0.2013 to 0.2139 | 2 |

These intervals are exploratory because the number of independent groups is
small. The broad person interval reflects the major difference between staged
Okutama activity and the one independent DLR dense-crowd group. The vehicle
interval is based on only two source groups and must not be read as evidence of
general real-world reliability.

## Runtime And Environment

| Measure | Result |
| --- | ---: |
| Image loading, median | 15.41 ms |
| Application preprocessing, median | 4.15 ms |
| Model inference and postprocessing, median | 30.35 ms |
| Complete in-memory processing, median | 71.04 ms |
| Complete in-memory processing, p95 | 120.51 ms |
| End-to-end processing, median | 78.85 ms |
| In-memory throughput | 13.16 FPS |
| End-to-end throughput | 11.57 FPS |
| Peak allocated GPU memory | 293.43 MiB |
| Checkpoint size | 42.01 MiB |

The measurements used batch size one, 20 warm-up frames, 100 measured frames,
and three repetitions on the NVIDIA RTX 5060 Laptop GPU. The run used Python
3.10.12, Ultralytics 8.4.51, PyTorch 2.12.0 with CUDA 13.0, OpenCV 4.13.0.92,
and pycocotools 2.0.11 under WSL2. Full hardware and software provenance remains
in the checksum-backed local run.

## Error Review

The saved-prediction review counted 937 true positives, 651 metric false
positives, and 936 metric false negatives. Its representative cases showed:

- missed small vehicles and people;
- missed medium and large trucks;
- trucks confused with cars, vans, or buses;
- people confused with the VisDrone `motor` label in several top-down scenes;
- false vehicle detections around occlusion and complex road geometry;
- almost complete undercounting in the densest DLR crowd images.

The analysis reused the frozen run's predictions and did not perform inference
or tuning. The clean analysis record is
`20260810T140714Z-yolo26m-visdrone-held-out-error-analysis`, and its manifest
SHA-256 is
`55cb798b30e95751ebfd47041cbd7e00cb3ad634513e29a8b2a611305b6147c4`.

## Reproducing The Evidence

The compact machine-readable result is stored in
`data/evaluation/final_quality_gate.json`. Full predictions, timing samples,
error images, and generated plots remain under the ignored
`data/evaluation/derived/` directory because they are large local artifacts.

From a machine that has the evaluation media, checkpoint, and saved run, we can
rebuild the final tables and plots with:

```bash
.venv/bin/python scripts/build_final_quality_gate_report.py
```

We can rebuild the qualitative examples from the same saved predictions with:

```bash
.venv/bin/python scripts/run_error_analysis.py \
  --source-run data/evaluation/derived/runs/20260810T135010Z-yolo26m-visdrone-held-out-test \
  --config configs/evaluation/yolo26m_visdrone_held_out_error_analysis.json
```

The generated final-report manifest has SHA-256
`4d83d00470543bfa89fc04617a0ccbf6733d94ad5be7e8e2410ed9d938d279b7`.
