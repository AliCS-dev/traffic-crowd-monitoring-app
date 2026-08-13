# Dedicated Crowd-Counting Result

## Outcome

We evaluated P2PNet as a dedicated alternative for the dense aerial crowd
scenes that the selected object detector could not count reliably. P2PNet
reduced the held-out normalized absolute error from `0.9962` to `0.7275` on the
same 14 DLR images. This is a relative error reduction of 27.0%, but it is not
enough to support application integration.

Following the decision rule fixed before inference, we **reject this P2PNet
checkpoint for integration**. It met the runtime requirement and improved on
YOLO, but its held-out NAE exceeded the defer limit of `0.70`. We did not change
the confidence threshold, tile policy, or decision boundary after seeing the
result.

## Experiment Record

| Field | Value |
| --- | --- |
| Candidate | P2PNet pretrained on ShanghaiTech Part A |
| Candidate role | Point-based crowd counting |
| Development data | DLR-ACD published train partition, 19 images |
| Final data | DLR-ACD published test partition, 14 images |
| Input policy | Original scale, non-overlapping 1024 px tiles |
| Edge policy | Pad to multiple of 16; discard padding points |
| Confidence | 0.5, from the official inference example |
| Device | NVIDIA GeForce RTX 5060 Laptop GPU, float32 |
| Candidate checkpoint | `SHTechA.pth`, 86,372,926 bytes |
| Checkpoint SHA-256 | `506047732b128ff09efef18e94bfacbe35fcfef300e5e9eeeece259b0488c63f` |
| Evaluation Git commit | `6c66c5ae8fc4a31d3a6373659a7154a7b7b6298d` |

The complete settings and compatibility notes are in the
[dedicated crowd-counting protocol](dedicated_crowd_counting_protocol.md).
Machine-readable evidence is stored in
`data/evaluation/dedicated_crowd_counting.json`. Larger per-image run files
remain in the ignored local evaluation directory.

## Development Check

We first ran the frozen method on the DLR published training partition. This
was a compatibility and development check; we did not use it to alter the
checkpoint or operating settings.

| Measure | P2PNet validation result |
| --- | ---: |
| Images | 19 |
| Reference people | 138,196 |
| Predicted people | 55,508 |
| MAE | 4,487.26 people/image |
| RMSE | 5,728.96 people/image |
| NAE | 0.6169 |
| NAE 95% bootstrap interval | 0.5527 to 0.7068 |
| Bias | -4,352.00 people/image |

The negative bias already showed systematic undercounting, but the run
completed consistently and produced substantially more plausible counts than
the detector in dense scenes. We therefore continued with the single planned
held-out run without tuning on this partition.

## Held-Out Comparison

Both models are compared below on exactly the 14 published DLR test images.
The YOLO values are recalculated from the frozen final detector predictions at
its selected operating confidence of `0.25`. They differ slightly from the
overall person NAE of `0.9943`, which also included 50 less-dense Okutama
frames.

| Measure | YOLO detector | P2PNet candidate |
| --- | ---: | ---: |
| Reference people | 88,140 | 88,140 |
| Predicted people | 336 | 24,016 |
| MAE, people/image | 6,271.71 | 4,580.29 |
| RMSE, people/image | 8,615.81 | 6,397.58 |
| NAE | 0.9962 | 0.7275 |
| NAE 95% bootstrap interval | 0.9879 to 0.9999 | 0.6322 to 0.8251 |
| Bias, people/image | -6,271.71 | -4,580.29 |

P2PNet detected many more people and reduced every reported error measure.
However, its prediction total was only 27.2% of the reference total. The NAE
interval and large negative bias show that undercounting remained systematic
rather than being caused by one isolated image.

## Runtime

| Measure | Held-out result |
| --- | ---: |
| Median processing time | 2.081 s/image |
| Median processing time | 0.116 s/megapixel |
| Total processing time | 29.338 s |
| Processed tiles | 318 |
| Peak allocated GPU memory | 1,119.38 MiB |

The normalized runtime passed the integration threshold of `0.5`
seconds/megapixel. The roughly two-second whole-image time reflects the high
18 to 21 megapixel resolution of most DLR images and should not be compared
directly with the detector's resized video-frame latency.

## Interpretation and Limits

This experiment supports three conclusions. First, choosing a model whose task
matches dense crowd counting can materially improve counts. Second, task match
alone is insufficient: P2PNet was trained on ground-level ShanghaiTech scenes,
and the domain difference remains large for nadir aerial imagery. Third, the
runtime and memory results show that a dedicated component is technically
feasible on the development laptop, even though this checkpoint is not
accurate enough.

The result does not evaluate physical crowd density, safety alerts, or the
accuracy of individual predicted point locations. Non-overlapping tiling avoids
duplicate counts but may lose context at tile boundaries. Only one reproducible
pretrained candidate was run, and the P2PNet academic-use licence would need
review outside thesis research.

We should keep the current application claim limited: it can count detected
people in ordinary aerial scenes, but it does not provide reliable dense-crowd
monitoring. A future study could evaluate an aerial-domain checkpoint or train
a compact count model on separated aerial data. That is new research work, not
a reason to reinterpret this held-out result.
