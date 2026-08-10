# YOLO26m Fine-Tuning Pilot

## Outcome

We completed one controlled fine-tuning pilot and rejected its checkpoint for
the combined traffic and crowd application. The model improved person detection,
but it forgot the vehicle classes that were absent from the training data. We
therefore keep the original VisDrone-trained YOLO26m checkpoint as our current
application candidate.

This is a useful result rather than a failed implementation. It shows that our
training workflow works and that the present data cannot safely improve a
multi-class traffic-and-crowd detector by itself.

## Data Decision

The training audit found 130 previously selected Okutama images with 749 person
boxes. The downloaded publisher data contains many more labelled frames, so we
used every thirtieth frame from the same 13 source groups already assigned to
the training role. This produced 1,610 images and 9,175 person boxes without
moving any validation or held-out source into training.

Adjacent video frames are strongly correlated. The deterministic stride reduces
that repetition while retaining each approved morning and noon scene. The
validation data contains 67 box-labelled images and 773 boxes. It includes both
people and road vehicles, which lets checkpoint selection expose class
forgetting. The held-out test split remained unused.

The DLR crowd annotations contain person points rather than bounding boxes, so
they were not used to train this object detector. The current training role also
contains no vehicle boxes. These two facts are the main limits of this pilot.

## Training Run

We started from the pinned YOLO26m VisDrone checkpoint and trained at image size
960 with batch size 2 on the RTX 5060 Laptop GPU. The run used AdamW, learning
rate 0.001, seed 2026, deterministic mode, mixed precision, and the first ten
model layers frozen. The project-controlled configuration is stored in
`configs/training/yolo26m_okutama_finetune.json`.

The run allowed at most 30 epochs and stopped after epoch 9 because validation
fitness had not improved for seven epochs. Epoch 2 supplied the best checkpoint
using validation mAP50-95. We did not select the final epoch and did not inspect
the held-out test set.

The run used Python 3.10.12, Ultralytics 8.4.51, PyTorch 2.12.0 with CUDA 13.0,
and NVIDIA driver 610.88. The exact augmentations, software versions, checkpoint
hashes, source groups, and artifact paths are preserved in
`data/evaluation/training_experiments.json`.

## Fair Comparison

We evaluated the original and fine-tuned checkpoints again on the same current
validation data and at the same confidence, image size, device, and protocol
settings.

| Metric | Original YOLO26m | Fine-tuned checkpoint | Change |
| --- | ---: | ---: | ---: |
| Overall mAP50 | 0.4301 | 0.1640 | -0.2661 |
| Overall mAP50-95 | 0.2189 | 0.0666 | -0.1523 |
| Person AP50 | 0.5394 | 0.7248 | +0.1854 |
| Person recall | 0.5444 | 0.7611 | +0.2167 |
| Road-vehicle NAE | 0.2852 | 1.0000 | +0.7148 |

The fine-tuned model detected people more reliably, but at the operating
confidence it detected no road vehicles. Its overall quality therefore fell
well below the starting checkpoint. It also remained unsuitable for dense
crowd counting: person NAE improved only from 0.9878 to 0.9790.

## Decision And Next Requirement

We do not promote the fine-tuned checkpoint and we do not run a longer version
of the same experiment. A further multi-class fine-tuning run requires a
licensed vehicle training partition that is independent of validation and
held-out scenes. Dense crowds may also require a dedicated counting or density
estimation approach rather than bounding-box detection alone.

Large generated datasets, plots, logs, and checkpoints remain below
`data/evaluation/derived/training/`, which is excluded from Git. The tracked
configuration and experiment registry retain the information needed to audit or
repeat the run without committing large third-party or binary artifacts.
