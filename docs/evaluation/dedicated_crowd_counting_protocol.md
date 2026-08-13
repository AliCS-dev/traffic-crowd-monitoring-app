# Dedicated Crowd-Counting Evaluation Protocol

## Purpose

The final detector evaluation showed that the selected YOLO model substantially
undercounted people in dense aerial scenes. This experiment asks a narrow
follow-up question: can a pretrained model designed specifically for crowd
counting provide more useful person counts on the same held-out DLR images?

We freeze this protocol before running the new candidate. The experiment does
not alter the previous detector result, train a new model, estimate people per
square metre, or add a crowd-counting component to the application.

## Candidate Selection

We selected one candidate, P2PNet pretrained on ShanghaiTech Part A. P2PNet
predicts individual person points, so its output maps directly to the available
DLR point-count references. The authors provide source code and a downloadable
checkpoint. We pin both the repository commit and the SHA-256 hash of the
checkpoint in `configs/evaluation/dedicated_crowd_counting.json`.

The P2PNet licence permits use only for academic research. That is suitable for
this thesis evaluation, but it would require a separate licence review before
commercial deployment.

We considered two alternatives but did not evaluate them:

- MRCNet was developed for DLR-ACD and has the strongest domain match, but we
  could not verify an official reusable checkpoint. A result that cannot be
  reproduced from identified weights would not strengthen the thesis.
- CountGD provides permissively licensed weights for open-world counting, but
  its 1.2 GB checkpoint and GroundingDINO, BERT, and optional SAM stack add a
  large compiled dependency surface. That setup is disproportionate to this
  compact experiment on the development laptop's 8 GB GPU.

Evaluating one candidate remains within the issue limit of at most two and
avoids choosing models after viewing test results.

## Data Separation

We use only DLR-ACD because it provides point-derived person counts for dense
aerial scenes. The published partitions remain separated:

| Use | DLR partition | Project role | Images |
| --- | --- | --- | ---: |
| Technical development and compatibility checks | Train | `validation` | 19 |
| Final comparison | Test | `held_out_test` | 14 |

The released P2PNet checkpoint was trained on ShanghaiTech Part A. We do not
train or tune it with DLR data. We use the official inference confidence of
`0.5` on both partitions. The held-out test is run once after the adapter and
configuration pass validation checks.

## Preprocessing and Inference

DLR images are much larger than ordinary model inputs. We preserve their
original pixel scale and divide each image into deterministic, non-overlapping
`1024 x 1024` tiles. Edge tiles retain their natural image content and are
padded on the right and bottom to the next multiple of 16 required by P2PNet's
feature pyramid. Predictions whose point lies in this padding are discarded.
We do not overlap tiles because summing overlapping predictions could count the
same person twice. Each tile is converted to RGB and normalized with ImageNet
mean and standard deviation, matching the official P2PNet demo.

Inference uses batch size `1`, float32 precision, and `cuda:0`. Five tiles are
used for GPU warm-up before timing. The adapter verifies the checkpoint size
and SHA-256 digest before loading it. It also bypasses an obsolete private
ImageNet-checkpoint path in the upstream model builder; the complete released
P2PNet state is loaded immediately afterwards without changing the architecture.
The adapter also bypasses a legacy torchvision version check that reads version
`0.27` as decimal `0.2` and attempts to import a removed empty-tensor helper.
That helper is not used by inference.

## Measures

For image `i`, `p_i` is the predicted count and `g_i` is the reference count.
We report:

```text
MAE  = mean(abs(p_i - g_i))
RMSE = sqrt(mean((p_i - g_i)^2))
NAE  = sum(abs(p_i - g_i)) / sum(g_i)
bias = mean(p_i - g_i)
```

We bootstrap whole images 2,000 times with seed `2026` and report 95% percentile
intervals for MAE, RMSE, NAE, and bias. Runtime is measured for each complete
image after warm-up. We report median seconds per image, median seconds per
megapixel, and peak allocated GPU memory. These numbers describe count
inference only and are not directly interchangeable with the detector's
fixed-size video-frame benchmark.

The comparison baseline is recalculated from the frozen YOLO run at operating
confidence `0.25`, restricted to the same 14 DLR test images. We compare count
error, not bounding-box detection accuracy, because DLR supplies point counts
rather than box annotations for these scenes.

## Decision Rule

We will **integrate** the candidate for a later application design task only if
its test NAE is no greater than `0.35`, it improves on YOLO on the same images,
and median runtime is no greater than `0.5` seconds per megapixel.

We will **defer** integration for further research if NAE is no greater than
`0.70`, relative NAE is at least 10% lower than YOLO, and runtime is no greater
than `1.0` second per megapixel. This category acknowledges a useful direction
that is not yet accurate or efficient enough for the application.

We will **reject** this checkpoint for the application if neither rule is met.
The decision applies only to this checkpoint and preprocessing policy; it does
not claim that dedicated crowd-counting methods in general are unsuitable.

These thresholds are project engineering targets rather than public-safety
requirements. We will report the result even when it is disappointing and will
not change these rules after opening the held-out predictions.
