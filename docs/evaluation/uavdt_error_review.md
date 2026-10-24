# UAVDT Saved-Prediction Review

[Results index](results_index.md) | [Baseline results](uavdt_daytime_baseline.md)

**20 October 2026.** We reviewed the saved 18 October predictions to understand
the large M0207 count discrepancy, bus/truck disagreements and the 300-candidate
limit. We did not run the detector again, change annotations or tune settings.
The [compact record](../../data/evaluation/uavdt_error_review.json) retains
the exact counts, case identifiers and evidence hashes.

## Main Finding

The baseline measures agreement with the labels we downloaded, but those labels
do not explain every visible vehicle. In M0207, many predictions counted as
false positives cover visible vehicles without reference boxes. Some bus/truck
disagreements also appear to involve source-label semantics. There are model
problems too, including an overlapping duplicate prediction and unmatched
reference objects.

We therefore cannot interpret every false positive as an invented vehicle, or
every class disagreement as a model mistake. Equally, this review does not show
that all unmatched predictions are correct. The original scores remain unchanged.
Before another model comparison, we need to establish whether the native
annotation release, image pairing and intended task explain these discrepancies.

## What We Reviewed

We reused the existing COCO-based operating matcher at confidence **0.25** and
IoU **0.50**, including the fixed strict-containment ignore policy. Its totals
reproduce the baseline: **2,837 true positives, 1,202 false positives and
222 false negatives**.

The error analyser links 67 overlapping wrong-class pairs. Each pair accounts
for one false positive and one false negative; after grouping, the list contains
67 class disagreements, 1,135 remaining false positives and 155 remaining false
negatives. The directions below mean **reference label to predicted class**:

| Label disagreement | Pairs |
| --- | ---: |
| Car/van to truck | 29 |
| Car/van to bus | 17 |
| Bus to car/van | 8 |
| Truck to car/van | 7 |
| Bus to truck | 6 |

We inspected all ten selected M0207 frames side by side, with native labels on
the left and scored predictions on the right. For bus/truck cases, the existing
size- and scene-diverse selector chose up to three examples per error type and
class. Deduplication left 18 crops: six disagreements, six misses and six
unmatched predictions. These are diagnostic examples, not a random sample from
which we can estimate error prevalence.

The visual observations are **assistant-assisted inspection**, not an
independent human annotation review or approval by Ali. No replacement ground
truth has been created.

## M0207: Missing Reference Coverage

Across the ten selected frames, the native labels contain 18 vehicle instances,
while the fixed operating predictions contain 200:

| Source frame | Reference vehicles | Predicted vehicles |
| --- | ---: | ---: |
| 1 | 1 | 9 |
| 64 | 1 | 8 |
| 127 | 1 | 9 |
| 191 | 2 | 10 |
| 254 | 3 | 16 |
| 317 | 3 | 23 |
| 381 | 3 | 27 |
| 444 | 2 | 31 |
| 507 | 1 | 30 |
| 571 | 1 | 37 |

The images show additional visible cars and a second bus without reference
boxes. The local native whole-sequence file contains 1,062 rows but only three
track IDs; its ignore file is empty. The conversion and source hashes still
match the preparation record. This is a concern about our available source
annotations, not evidence that the adapter dropped those visible vehicles.
The reason for the limited coverage remains unresolved; we do not generalise
this finding to every UAVDT release.

Frame 507 also contains a real duplicate-like prediction: selected bus error
`fp-uavdt_M0207_000507-440` overlaps a higher-confidence bus prediction at
IoU **0.9747**, and overlaps the native bus box at IoU **0.8946**. Missing labels
are therefore not the only explanation for the count difference.

## Bus and Truck Cases

| Example | Observation and limit |
| --- | --- |
| M0402 frame 137, track 9 | The native category is car, while the box covers what appears to be a white box-body truck. The truck prediction has confidence 0.9505 and reference IoU 0.9253. |
| M0402 frames 273 and 364, track 17 | A long green vehicle appears to be a bus, but the native category is car. Bus predictions overlap the reference at IoU 0.9704 and 0.9622. These are two views of the same track, not independent examples. |
| M0210 frame 1, reference 221 | The truck reference covers a toll canopy area. A corresponding vehicle cannot be identified confidently from this still; we retain the label and uncertainty. |
| M0301 frame 253, reference 365 | The truck reference lies strictly inside an ignored region. Our fixed policy filters contained predictions but retains this reference, so its miss is not straightforward evidence of model failure. |
| M0604 frame 839, reference 1118 | The large foreground vehicle is partly obscured. Its best scored prediction overlap is only 0.3041, below the matching threshold; visibility and localisation need consideration. |

We checked the three questioned M0402 records against the native file. All use
native category `1`, which the adapter maps to `car_or_van`. This disagreement
was not introduced by the overlay colour fix described below. These observations
are not permission to relabel the development set after seeing predictions.

## Candidate Limit

The saved run contains 47,950 raw predictions. Ignore filtering removes 14,520
at the confidence floor; threshold and class filtering leave 4,039 operating
vehicle predictions.

On 141 images the raw list reaches 300 candidates. Their lowest saved
confidences range from **0.001006 to 0.056235**. None reaches the operating
threshold of 0.25 at the end of its saved list. We therefore see no operating-
threshold saturation in these lists. The cap can still truncate low-confidence
candidates used for AP; we have not measured the effect of increasing it.
This observation is not a reason to change the frozen baseline.

## Evidence and Reproduction

The command is documented in [Running evaluations](running_evaluations.md).
It verifies the saved run, dataset identity, source readiness and matching
totals before writing a new local review. The authoritative review is:

```text
data/evaluation/derived/uavdt_error_review/
  20261020T085821Z-uavdt-saved-prediction-review/
```

It contains ten `m0207/` comparison PNGs, 18 detection crops, a contact sheet,
the complete error list, `review.json` and `review_manifest.json`. We verified
all 33 artifacts listed in that manifest. Source media, coordinates and derived
crops remain outside Git; only compact counts, hashes and observations are
published. We have not cleared these images for redistribution in documentation.

The first local review, `20261020T085633Z-uavdt-saved-prediction-review`, is
superseded: its new M0207 panels used swapped bus/truck colour IDs. We corrected
the renderer to use the shared category mapping, added a regression test and
regenerated the review from clean commit
`92e73b0e3b6a4164a9e3ff79494b82582e6020a0`. Inventories, matching totals,
selected cases and the original baseline metrics are identical between reviews.

## Next Decision

**Follow-up, 24 October:** the [publisher source check](uavdt_source_audit.md)
confirmed byte equality for all 34 baseline annotation files and the 20 selected
M0207/M0402 images. Their DET and MOT box inventories also agree. This resolves
the mirror/local-pairing question for those examples, not label correctness.
The original next-step rationale below is retained for context.

We will first check the annotation release and image-to-label pairing for M0207
and the questioned M0402 records against the original source documentation.
Any correction or exclusion would require a documented dataset revision and a
separately named result, not an overwrite of this baseline. Only then can we
decide which remaining model errors justify another controlled experiment.

Issue #113 remains open. This review does not satisfy the broader six-class,
human-review or independent-holdout requirements, and does not change the
historical failed quality gate or unsupported dense-crowd status.
