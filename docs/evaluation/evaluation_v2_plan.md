# Evaluation V2 Plan

**Status, 1 October 2026:** Ali confirmed the scenario scope and provisionally
approved 400 images from at least 40 independent scene groups. Detailed coverage
floors below are proposals pending source feasibility and review-effort checks.
This is a planning record for issue #113, not a frozen dataset, accuracy result
or claim of deployment readiness. No v2 acquisition or training has begun.

## Scope We Agreed

We will evaluate daytime aerial road scenes using all six existing classes:
`person`, `bicycle`, `motorcycle`, `car_or_van`, `bus` and `truck`.
We include individually distinguishable pedestrians and moving or parked
vehicles in road segments, intersections and roundabouts. Nadir/near-nadir and
oblique aerial views are recorded separately. We do not infer motion from a
single frame or call elevated ground-camera footage confirmed UAV footage.

Dense crowds remain a separate count-estimation task under #115, with their own
data, thresholds and new holdout. Their application result remains unsupported
with a null count. Point-count references will not enter this detector's box
metrics or pedestrian count gate. Night, adverse weather, tracking, unique
road-user totals, speed, physical density and safety decisions are outside
these claims. Passing daytime tests would not validate those capabilities.

The [historical audit](dataset_audit_v1.md) explains the class and scene gaps.
We retain old data and failed results unchanged; a different dataset cannot
retroactively turn the old quality gate into a pass.

## Provisional Coverage Targets

We prioritize existing licensed annotations followed by human review, rather
than drawing every box from scratch. These are practical coverage floors, not
a statistical power calculation, proven sufficiency or a promise of accuracy.

| Partition | Images | Independent scene groups | Purpose |
| --- | ---: | ---: | --- |
| Training | 240 | 24 | Optional adaptation, retaining all six classes |
| Validation | 80 | 8 | Model, resolution and threshold selection |
| New final holdout | 80 | 8 | One frozen final comparison |

We select at most ten core images per group. More images require more groups,
not more adjacent frames. Related clips, flights, bursts, overlapping views and
repeat visits to the same physical scene belong to one group. Collection names
or train/test folders are not proof of independence. Different road scenes in
one city may be separate groups when provenance supports it, but this does not
establish generalization to unseen cities.

| Class | Training boxes | Validation boxes | Final-holdout boxes |
| --- | ---: | ---: | ---: |
| Person | 300 | 100 | 100 |
| Bicycle | 300 | 100 | 100 |
| Motorcycle | 300 | 100 | 100 |
| Car or van | 1,000 | 300 | 300 |
| Bus | 300 | 100 | 100 |
| Truck | 300 | 100 | 100 |

Each class occurs in at least eight training groups and five groups in each
evaluation partition. No validation/holdout group supplies more than 35 percent
of a class's boxes. Thus one bus depot cannot satisfy the bus target by itself.
The minimum total is 4,100 boxes, not 4,100 unique tracked objects. It is not an
annotation ceiling: every identifiable target object in each selected image
must be labelled. We never discard legitimate boxes to meet balance limits.

Within validation and holdout, separately, the proposed scene targets are:

- At least 20 images from three groups for each view family: nadir/near-nadir
  and oblique. Unknown camera angles do not satisfy either quota.
- At least two groups for each scene family: road segment, intersection and
  roundabout. Groups can carry multiple attributes but remain in one partition.
- At least 20 small boxes per class across three groups, using the historical
  native-pixel area band below 32 squared. This supports descriptive breakdowns,
  not a strong class-by-size accuracy claim on its own.
- At least 20 partially occluded, identifiable objects across three groups.
  Occlusion and boundary truncation are recorded separately, with class support
  reported. Missing attributes never become "not occluded".
- At least eight fully reviewed negative images from three groups with no
  target objects, so false positives on empty scenes remain visible.

These overlapping quotas fit within each 80-image partition; they are not
additional images. If sources and an agreed review workload cannot meet the
floors, we document the gap and revise the plan before experiments. We do not
lower targets after seeing model scores or silently drop missing classes from
a six-class success claim.

## Sources And Independent Holdout

The next source inventory records URLs, annotation completeness, licence terms,
attribution/restrictions, camera provenance, capture/location identifiers,
available groups per class and estimated review effort. We approve it before
bulk downloads or a manual annotation campaign. Metadata links alone are not
permission to redistribute media or labels.

We assign whole groups using seed `2026`, after metadata, exact-hash,
decoded-image similarity and visual checks of suspected duplicates. We check
across proposed partitions and against historical/development media, including
runtime fixtures. Suspect related groups are joined. Unverified capture/location
provenance cannot satisfy the independent holdout quota. Video sampling follows
a recorded fixed temporal rule, not frames selected because a detector works
well on them. Coverage adjustments use labels and provenance, before prediction-
based selection.

Final-test scenes must be new, not renamed historical test frames or new frames
of the same scenes. V1 files and roles remain unchanged; we do not recycle the
opened v1 test into training. Official benchmark splits retain their published
roles and their scores stay separate from the custom application dataset.
Sources lacking verifiable scene metadata may support a labelled external
benchmark, but not our independent-holdout claim.

We also check candidate models' known pretraining/fine-tuning sources. Known
overlap disqualifies a model/holdout pairing as independent evidence. Unknown
pretraining exposure is a recorded limitation, never asserted absent. #114
must respect these restrictions before selecting candidates.

We freeze manifests, annotations, the review ledger and split report with
hashes before tuning. Annotation/QC access is allowed and logged; final-test
predictions and metrics are not used for development. If Ali prepares labels
and selects models, we disclose that this is not blinded independent
adjudication. We do not use candidate-assisted final-test labels or run routine
holdout smoke inference. Runtime checks use development fixtures only.

After #114 freezes weights, runtime, configuration and selection rules, we run
the baseline and selected candidate on the same new holdout as one final
comparison. Its results cannot select another model or threshold. Corrections
preserve the original run and record a versioned reason; an opened test does
not become untouched again by rerunning it.

## Annotation And Release Checks

We retain the [annotation guide](annotation_guide.md), stable category IDs and
original source labels. Each core image needs exhaustive review for all six
classes. Car-only or person-only source labels are insufficient until missing
classes have been reviewed. Rider/vehicle conventions must be harmonized,
not mixed silently across collections.

Source boxes below the manual four-pixel minimum are retained and flagged.
Unresolved objects, ignore regions, crowd flags or incomplete labels cannot be
treated silently as background: our current canonical metric path does not
preserve those ignore semantics. Such images remain outside the core release
until labels are resolved or an explicit, tested ignore policy exists. We
record all exclusions and their effect on difficult-scene coverage.

Preparation and a separate visual QC pass record the actual reviewer, date,
corrections and decision. One researcher doing both passes is disclosed as
non-independent review. We do not approve annotations on another person's
behalf. Manifest and review-ledger statuses must agree; v1's discrepancy is not
carried into v2. Source annotations and model proposals are not human-review
evidence by themselves.

The release needs versioned manifests, a dataset card, source/duplicate checks,
coverage tables, overlay-review records and passing technical validation.
V2 paths remain separate from historical artifacts. Restricted media/annotations
stay local; permitted metadata, hashes, scripts and compact evidence remain
discoverable through the [results index](results_index.md).

## Metrics And Decision Rules

We retain aggregate pass thresholds from the
[original protocol](evaluation_protocol.md#quality-gate):

| Measure | Pass requirement |
| --- | ---: |
| Six-class macro precision, IoU 0.50 | At least 0.70 |
| Six-class macro recall, IoU 0.50 | At least 0.60 |
| mAP50 | At least 0.60 |
| mAP50-95 | At least 0.35 |
| Individually visible person count NAE | At most 0.25 |
| Road-vehicle-total count NAE | At most 0.25 |
| Median in-memory frame latency | At most 0.50 seconds |

Person NAE now covers only the agreed pedestrian scenes. It is not directly
comparable to the old combined person result containing dense-crowd references.
Road-vehicle total still sums bicycle, motorcycle, car/van, bus and truck.
We report per-class precision/recall, AP50/AP50-95, count MAE/NAE and bias,
plus scene/view/size breakdowns with support counts. Undefined metrics remain
unavailable, not zero or permission to drop a class from the gate.

An additional proposed v2 safeguard requires every class to reach precision
0.60 and recall 0.50, so abundant cars cannot hide a failed minority class.
Full support requires every coverage floor and pass requirement. Otherwise the
result is limited/conditional or failed, with affected classes explicit.
Original conditional ranges remain descriptive, not a six-class pass. These
are project engineering requirements, not safety standards or evidence of
state-of-the-art performance.

We retain COCO-compatible AP, confidence floor `0.001`, operating IoU `0.50`
and batch size one. Before experiments, #114 declares candidate/configuration
choices, detection caps, permitted regressions and compute/time limits. A cap
must not silently truncate valid objects. Timing retains 20 warm-ups, at least
100 measured frames and three repetitions on the RTX 5060 Laptop GPU. Median/
p95 latency, throughput and peak GPU memory are reported; database time stays
separate. Accuracy metrics never use repeated timing frames.

For macro precision/recall and person/vehicle NAE, we plan 95 percent percentile
intervals from 2,000 whole-group bootstrap resamples, seed `2026`. All frames
in a sampled group stay together and group multiplicity is preserved. Reporting
must handle all-negative groups, false positives for locally absent classes and
undefined denominators without silently changing the six-class average.
Undefined-resample counts are disclosed. These cases need explicit v2 regression
tests before reusing the existing interval implementation. AP gets point
estimates and per-group breakdowns; the current code does not produce AP
confidence intervals. Point estimates drive the gate, while wide intervals and
the small group count remain explicit limits on interpretation.

## Next Checkpoint

Today delivers the agreed scenario scope, provisional dataset size and a
detailed proposal. It does not deliver a dataset or experimental result.
The next checkpoint is a source inventory and review-effort estimate against
these targets, then approval of the detailed plan before collection.
Any revision records its reason, approval date and plan commit before v2
prediction-based experiments; the later freeze records exact plan/data hashes.

Issue #113 stays open for acquisition, review, split validation and a new
holdout. #114 and #115 retain separate experiment plans. No application code,
dataset labels, model settings, historical results or frontend features change
in this step.

## Method References

Development/test separation and grouping related samples follow the principles
in the [scikit-learn evaluation guidance](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data).
AP uses the [COCO evaluator](https://github.com/cocodataset/cocoapi/blob/master/PythonAPI/pycocotools/cocoeval.py).
Numerical coverage floors and additional class safeguards are our proposals,
not requirements from these references.
